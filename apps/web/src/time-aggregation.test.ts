import { describe, expect, it } from 'vitest'
import { aggregateDailySeries, type DailySeriesRow } from './time-aggregation'

const day = (date: string, total = 3): DailySeriesRow => ({
  date,
  total,
  topics: { service: total - 1, unclassified: 1 },
})

describe('bounded UTC display aggregation', () => {
  it('retains 450 daily observations while displaying at most 60 complete buckets', () => {
    const source = Array.from({ length: 450 }, (_, index) =>
      day(new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10)),
    )
    const result = aggregateDailySeries(source)
    expect(result.resolution).toBe('month')
    expect(result.buckets.length).toBeLessThanOrEqual(60)
    expect(result.dailyRows).toEqual(source)
    expect(
      result.buckets.reduce((sum, bucket) => sum + (bucket.total ?? 0), 0),
    ).toBe(1350)
    expect(
      result.buckets.reduce((sum, bucket) => sum + bucket.observedDays, 0),
    ).toBe(450)
    expect(
      result.buckets.reduce(
        (sum, bucket) => sum + (bucket.topics.service ?? 0),
        0,
      ),
    ).toBe(900)
  })

  it('marks unobserved dates unknown instead of inventing zero counts', () => {
    const result = aggregateDailySeries([day('2026-02-27'), day('2026-03-01')])
    expect(result.buckets).toEqual([
      expect.objectContaining({
        from: '2026-02-27',
        total: 3,
        observedDays: 1,
      }),
      expect.objectContaining({
        from: '2026-02-28',
        total: null,
        observedDays: 0,
      }),
      expect.objectContaining({
        from: '2026-03-01',
        total: 3,
        observedDays: 1,
      }),
    ])
  })

  it('uses UTC Monday weeks and clips edge ranges to the supplied date span', () => {
    const result = aggregateDailySeries(
      [day('2025-12-31'), day('2026-01-02')],
      2,
    )
    expect(result.resolution).toBe('week')
    expect(result.buckets).toEqual([
      {
        from: '2025-12-31',
        to: '2026-01-02',
        total: 6,
        topics: { service: 4, unclassified: 2 },
        observedDays: 2,
        calendarDays: 3,
      },
    ])
  })

  it('keeps sparse extreme calendar ranges bounded and unknown intervening periods', () => {
    const result = aggregateDailySeries([day('0001-01-01'), day('9999-12-31')])
    expect(result.resolution).toBe('multiyear')
    expect(result.buckets.length).toBeLessThanOrEqual(60)
    expect(result.buckets[0]?.from).toBe('0001-01-01')
    expect(result.buckets.at(-1)?.to).toBe('9999-12-31')
    expect(
      result.buckets.filter((bucket) => bucket.total === null).length,
    ).toBeGreaterThan(1)
    expect(
      result.buckets.reduce((sum, bucket) => sum + (bucket.total ?? 0), 0),
    ).toBe(6)
  })

  it('supports years, leap days and duplicate date rows without mutating input', () => {
    const source = [day('2024-02-29'), day('2024-02-29'), day('2030-01-01')]
    const copy = structuredClone(source)
    const result = aggregateDailySeries(source)
    expect(result.resolution).toBe('year')
    expect(result.buckets[0]).toMatchObject({ total: 6, observedDays: 1 })
    expect(source).toEqual(copy)
    expect(result.dailyRows).toHaveLength(3)
  })

  it('aggregates allowed constructor topics numerically across rows and buckets', () => {
    const source: DailySeriesRow[] = [
      { date: '2026-01-01', total: 2, topics: { service: 2 } },
      { date: '2026-01-01', total: 3, topics: { constructor: 3 } },
      { date: '2026-01-03', total: 4, topics: { constructor: 4 } },
    ]
    const result = aggregateDailySeries(source, 2)
    expect(result.buckets[0]?.topics).toEqual({ service: 2, constructor: 7 })
    expect(result.buckets[0]?.total).toBe(9)
    expect(typeof result.buckets[0]?.topics.constructor).toBe('number')
    expect(Object.getPrototypeOf(result.buckets[0]!.topics)).toBeNull()
    expect(source[0]?.topics).toEqual({ service: 2 })
    expect(() =>
      aggregateDailySeries([
        { date: '2026-01-01', total: 1, topics: { service: Number.NaN } },
      ]),
    ).toThrow(/topic counts/)
  })

  it('rejects malformed dates and invalid display limits, while handling no supplied dates', () => {
    expect(aggregateDailySeries([]).buckets).toEqual([])
    expect(() => aggregateDailySeries([day('2026-02-30')])).toThrow(/valid UTC/)
    expect(() => aggregateDailySeries([day('02/03/2026')])).toThrow(
      /YYYY-MM-DD/,
    )
    expect(() => aggregateDailySeries([], 1)).toThrow(/at least two/)
  })
})
