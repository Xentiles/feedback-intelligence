import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { Inspectable } from './inspection-components'
import {
  useInspection,
  chartAnchor,
  type PreviewAnchor,
  type InspectionDetail,
} from './inspection-context'
import {
  aggregateDailySeries,
  timeBucketLabel,
  type DailySeriesRow,
  type TimeBucket,
} from './time-aggregation'

export type WorkbenchTimeChartProps = {
  dailySeries: DailySeriesRow[]
  onDrillDown?: (from: string, to: string) => void
  scopeLabel?: string
  provenance?: InspectionDetail['fields']
}

const HEIGHT = 280
const LEFT = 56
const RIGHT = 16
const TOP = 16
const BOTTOM = 52
const PLOT_HEIGHT = HEIGHT - TOP - BOTTOM

export function WorkbenchTimeChart({
  dailySeries,
  onDrillDown,
  scopeLabel = 'Current run · applied filters',
  provenance = [],
}: WorkbenchTimeChartProps) {
  const aggregated = useMemo(
    () => aggregateDailySeries(dailySeries),
    [dailySeries],
  )
  const { buckets, resolution, yearStep } = aggregated
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const selected = Math.min(
    selectedIndex ?? buckets.length - 1,
    buckets.length - 1,
  )
  const current = buckets[selected]
  const target = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(720)
  useEffect(() => {
    const element = target.current
    if (!element) return
    const measure = () => {
      const measured = element.getBoundingClientRect().width
      if (measured > 0) setWidth(Math.max(240, Math.round(measured)))
    }
    measure()
    if (!window.ResizeObserver) return
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [buckets.length])
  const plotWidth = width - LEFT - RIGHT
  const hintId = useId()
  const { inspect, preview, clearPreview, previewId } = useInspection()
  const maximum = Math.max(1, ...buckets.map((bucket) => bucket.total ?? 0))
  const columnWidth = buckets.length ? plotWidth / buckets.length : plotWidth
  const axisMaximum = Math.max(1, Math.ceil(maximum / 4) * 4)
  const labelInterval = Math.max(
    1,
    Math.ceil(buckets.length / Math.max(2, Math.floor(width / 140))),
  )

  const detailFor = (bucket: TimeBucket): InspectionDetail => ({
    title: timeBucketLabel(bucket),
    scopeLabel,
    description:
      bucket.total === null
        ? 'No supplied observations in this period. Coverage is unknown; this is not zero feedback.'
        : 'Record volume reflects successfully classified feedback with supplied review dates. Missing dates are excluded; unobserved days have unknown coverage.',
    fields: [
      {
        label: 'Classified records',
        value: bucket.total?.toLocaleString() ?? 'Unknown',
      },
      {
        label: 'Observed dates / calendar dates',
        value: `${bucket.observedDays} / ${bucket.calendarDays}`,
      },
      {
        label: 'Grouping',
        value: resolution === 'multiyear' ? `${yearStep} years` : resolution,
      },
      { label: 'Date boundary', value: 'UTC · both displayed dates included' },
      ...provenance,
    ],
    content:
      bucket.total !== null ? (
        <>
          <h3>Topic counts and rates</h3>
          <dl className="inspection-fields">
            {Object.entries(bucket.topics).map(([topic, count]) => (
              <div key={topic}>
                <dt>{topic}</dt>
                <dd>
                  {count}/{bucket.total} ·{' '}
                  {bucket.total
                    ? ((100 * count) / bucket.total).toFixed(1)
                    : '0'}
                  %
                </dd>
              </div>
            ))}
          </dl>
        </>
      ) : undefined,
    action:
      bucket.total !== null && onDrillDown
        ? {
            label: 'View matching records',
            onClick: () => onDrillDown(bucket.from, bucket.to),
          }
        : undefined,
  })

  const indexAt = (clientX: number) => {
    const bounds = target.current?.getBoundingClientRect()
    if (!bounds?.width || !buckets.length) return Math.max(0, selected)
    const x = ((clientX - bounds.left) / bounds.width) * width
    return Math.max(
      0,
      Math.min(buckets.length - 1, Math.floor((x - LEFT) / columnWidth)),
    )
  }
  const show = (index: number, anchor?: PreviewAnchor) => {
    const bucket = buckets[index]
    if (!bucket) return
    setSelectedIndex(index)
    if (target.current)
      preview(
        detailFor(bucket),
        target.current,
        anchor ??
          (() =>
            chartAnchor(
              target.current?.querySelector('svg') ?? null,
              LEFT + (index + 0.5) * columnWidth,
              TOP +
                PLOT_HEIGHT -
                ((bucket.total ?? 0) / axisMaximum) * PLOT_HEIGHT,
            )),
      )
  }

  if (!buckets.length)
    return <p>No dated records; time analysis is unavailable.</p>

  return (
    <section className="wb-volume-chart" aria-label="Observed record volume">
      <p className="wb-volume-chart__hint" id={hintId}>
        {buckets.length}{' '}
        {resolution === 'multiyear' ? `${yearStep}-year` : resolution} periods ·
        UTC. Dashed gaps mean unknown coverage. Hover or select to inspect; use
        arrow keys, then Enter for details.
      </p>
      <div
        ref={target}
        className="wb-volume-chart__target"
        role="button"
        tabIndex={0}
        aria-label={`Inspect observed record volume: ${current ? timeBucketLabel(current) : ''}`}
        aria-describedby={[hintId, previewId].filter(Boolean).join(' ')}
        onFocus={() => show(selected)}
        onBlur={clearPreview}
        onPointerMove={(event) =>
          show(indexAt(event.clientX), { x: event.clientX, y: event.clientY })
        }
        onPointerLeave={clearPreview}
        onClick={(event) => {
          const index = event.detail > 0 ? indexAt(event.clientX) : selected
          const bucket = buckets[index]
          if (bucket) {
            setSelectedIndex(index)
            inspect(detailFor(bucket), event.currentTarget)
          }
        }}
        onKeyDown={(event) => {
          let index: number
          if (event.key === 'ArrowRight')
            index = Math.min(buckets.length - 1, selected + 1)
          else if (event.key === 'ArrowLeft') index = Math.max(0, selected - 1)
          else if (event.key === 'Home') index = 0
          else if (event.key === 'End') index = buckets.length - 1
          else if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            if (current) inspect(detailFor(current), event.currentTarget)
            return
          } else return
          event.preventDefault()
          show(index)
        }}
      >
        <svg viewBox={`0 0 ${width} ${HEIGHT}`} aria-hidden="true">
          {[0, 1, 2, 3, 4].map((step) => {
            const count = (axisMaximum * step) / 4
            const y = TOP + PLOT_HEIGHT - (PLOT_HEIGHT * step) / 4
            return (
              <g key={step}>
                <line
                  className="wb-volume-chart__grid"
                  x1={LEFT}
                  x2={width - RIGHT}
                  y1={y}
                  y2={y}
                />
                <text x={LEFT - 8} y={y + 4} textAnchor="end">
                  {Number.isInteger(count)
                    ? count.toLocaleString()
                    : count.toFixed(1)}
                </text>
              </g>
            )
          })}
          {buckets.map((bucket, index) => {
            const x = LEFT + index * columnWidth + columnWidth * 0.15
            const width = columnWidth * 0.7
            const height =
              bucket.total === null
                ? 0
                : (PLOT_HEIGHT * bucket.total) / axisMaximum
            return (
              <g key={bucket.from}>
                {bucket.total === null ? (
                  <rect
                    className="wb-volume-chart__gap"
                    x={x}
                    y={TOP + 4}
                    width={width}
                    height={PLOT_HEIGHT - 8}
                  />
                ) : (
                  <rect
                    className="wb-volume-chart__bar"
                    x={x}
                    y={TOP + PLOT_HEIGHT - height}
                    width={width}
                    height={height}
                  />
                )}
                {index === selected && (
                  <rect
                    className="wb-volume-chart__selection"
                    x={x - 2}
                    y={TOP + 2}
                    width={width + 4}
                    height={PLOT_HEIGHT - 4}
                  />
                )}
                {(index % labelInterval === 0 ||
                  index === buckets.length - 1) && (
                  <text
                    x={LEFT + (index + 0.5) * columnWidth}
                    y={HEIGHT - 20}
                    textAnchor={
                      index === 0
                        ? 'start'
                        : index === buckets.length - 1
                          ? 'end'
                          : 'middle'
                    }
                  >
                    {resolution === 'day' || resolution === 'week'
                      ? bucket.from.slice(5)
                      : resolution === 'month'
                        ? bucket.from.slice(0, 7)
                        : bucket.from.slice(0, 4)}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>
      {current && (
        <div
          className="wb-volume-chart__readout"
          aria-live="polite"
          aria-atomic="true"
        >
          <p>
            {timeBucketLabel(current)} ·{' '}
            {current.total === null
              ? 'Unknown volume'
              : `${current.total.toLocaleString()} classified records`}{' '}
            · {current.observedDays}/{current.calendarDays} dates observed
          </p>
        </div>
      )}
      <details>
        <summary>Chart periods and coverage</summary>
        <div
          className="wb-table-wrap"
          role="region"
          aria-label="Observed period counts"
          tabIndex={0}
        >
          <table className="wb-volume-chart__table">
            <thead>
              <tr>
                <th scope="col">Period</th>
                <th scope="col">Classified records</th>
                <th scope="col">Observed dates / calendar dates</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((bucket) => (
                <tr key={bucket.from}>
                  <th scope="row">
                    <Inspectable
                      detail={detailFor(bucket)}
                      className="inspection-value"
                    >
                      {timeBucketLabel(bucket)}
                    </Inspectable>
                  </th>
                  <td>
                    {bucket.total?.toLocaleString() ?? 'Unknown coverage'}
                  </td>
                  <td>
                    {bucket.observedDays}/{bucket.calendarDays}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}
