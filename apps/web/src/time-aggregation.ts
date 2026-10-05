export type DailySeriesRow = {
  date: string
  total: number
  topics: Record<string, number>
}

export type TimeResolution = 'day' | 'week' | 'month' | 'year' | 'multiyear'
export type TimeBucket = {
  from: string
  to: string
  total: number | null
  topics: Record<string, number>
  observedDays: number
  calendarDays: number
}
export type AggregatedTimeSeries = {
  resolution: TimeResolution
  yearStep: number
  buckets: TimeBucket[]
  dailyRows: DailySeriesRow[]
}

const DAY = 86_400_000
const utc = (year: number, month = 0, day = 1) => {
  const value = new Date(0)
  value.setUTCFullYear(year, month, day)
  value.setUTCHours(0, 0, 0, 0)
  return value
}
const iso = (value: Date) => value.toISOString().slice(0, 10)

function copyTopics(topics: Record<string, number>): Record<string, number> {
  const copy = Object.create(null) as Record<string, number>
  for (const [topic, count] of Object.entries(topics)) {
    if (!Number.isSafeInteger(count) || count < 0)
      throw new Error('Observed topic counts must be non-negative integers.')
    copy[topic] = count
  }
  return copy
}

function addTopic(
  topics: Record<string, number>,
  topic: string,
  count: number,
) {
  const current = Object.hasOwn(topics, topic) ? topics[topic] : 0
  topics[topic] = (current ?? 0) + count
}

function parse(value: string): Date {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value))
    throw new Error('Observed dates must use YYYY-MM-DD.')
  const parsed = new Date(`${value}T00:00:00.000Z`)
  if (!Number.isFinite(parsed.getTime()) || iso(parsed) !== value)
    throw new Error('Observed dates must be valid UTC calendar dates.')
  return parsed
}

function floor(value: Date, resolution: TimeResolution, step: number): Date {
  if (resolution === 'day') return new Date(value)
  if (resolution === 'week')
    return new Date(value.getTime() - ((value.getUTCDay() + 6) % 7) * DAY)
  if (resolution === 'month')
    return utc(value.getUTCFullYear(), value.getUTCMonth())
  return utc(Math.floor(value.getUTCFullYear() / step) * step)
}

function next(value: Date, resolution: TimeResolution, step: number): Date {
  if (resolution === 'day' || resolution === 'week')
    return new Date(value.getTime() + (resolution === 'day' ? 1 : 7) * DAY)
  if (resolution === 'month')
    return utc(value.getUTCFullYear(), value.getUTCMonth() + 1)
  return utc(value.getUTCFullYear() + step)
}

/** Retain observed days, group only for display, and never treat missing dates as zero. */
export function aggregateDailySeries(
  source: DailySeriesRow[],
  maximumBuckets = 60,
): AggregatedTimeSeries {
  if (!Number.isInteger(maximumBuckets) || maximumBuckets < 2)
    throw new Error('Use at least two display buckets.')
  const dailyRows = [...source].sort((a, b) => a.date.localeCompare(b.date))
  const days = new Map<string, DailySeriesRow>()
  for (const row of dailyRows) {
    parse(row.date)
    if (!Number.isSafeInteger(row.total) || row.total < 0)
      throw new Error('Observed record counts must be non-negative integers.')
    const existing = days.get(row.date)
    const topics = copyTopics(row.topics)
    if (existing) {
      existing.total += row.total
      for (const [topic, count] of Object.entries(topics))
        addTopic(existing.topics, topic, count)
    } else days.set(row.date, { ...row, topics })
  }
  if (!dailyRows.length)
    return { resolution: 'day', yearStep: 1, buckets: [], dailyRows }
  const first = parse(dailyRows[0]!.date)
  const last = parse(dailyRows.at(-1)!.date)
  const span = Math.floor((last.getTime() - first.getTime()) / DAY) + 1
  const months =
    (last.getUTCFullYear() - first.getUTCFullYear()) * 12 +
    last.getUTCMonth() -
    first.getUTCMonth() +
    1
  const years = last.getUTCFullYear() - first.getUTCFullYear() + 1
  let resolution: TimeResolution = 'day'
  let yearStep = 1
  if (span > maximumBuckets) {
    const weeks = Math.ceil((span + ((first.getUTCDay() + 6) % 7)) / 7)
    if (weeks <= maximumBuckets) resolution = 'week'
    else if (months <= maximumBuckets) resolution = 'month'
    else if (years <= maximumBuckets) resolution = 'year'
    else {
      resolution = 'multiyear'
      yearStep = Math.ceil(years / maximumBuckets)
      while (
        Math.floor(last.getUTCFullYear() / yearStep) -
          Math.floor(first.getUTCFullYear() / yearStep) +
          1 >
        maximumBuckets
      )
        yearStep += 1
    }
  }
  const buckets: TimeBucket[] = []
  const indexed = new Map<number, TimeBucket>()
  for (
    let start = floor(first, resolution, yearStep);
    start <= last;
    start = next(start, resolution, yearStep)
  ) {
    const end = next(start, resolution, yearStep)
    const boundedStart = new Date(Math.max(start.getTime(), first.getTime()))
    const boundedEnd = new Date(Math.min(end.getTime() - DAY, last.getTime()))
    const bucket: TimeBucket = {
      from: iso(boundedStart),
      to: iso(boundedEnd),
      total: null,
      topics: Object.create(null) as Record<string, number>,
      observedDays: 0,
      calendarDays:
        Math.floor((boundedEnd.getTime() - boundedStart.getTime()) / DAY) + 1,
    }
    buckets.push(bucket)
    indexed.set(start.getTime(), bucket)
  }
  for (const row of days.values()) {
    const bucket = indexed.get(
      floor(parse(row.date), resolution, yearStep).getTime(),
    )!
    bucket.total = (bucket.total ?? 0) + row.total
    bucket.observedDays += 1
    for (const [topic, count] of Object.entries(row.topics))
      addTopic(bucket.topics, topic, count)
  }
  return { resolution, yearStep, buckets, dailyRows }
}

export function timeBucketLabel(bucket: TimeBucket): string {
  return bucket.from === bucket.to
    ? bucket.from
    : `${bucket.from} – ${bucket.to}`
}
