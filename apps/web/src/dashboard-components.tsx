import type { ReactNode } from 'react'

import {
  formatCount,
  formatDate,
  formatDateTime,
  formatMonth,
  formatRate,
} from './dashboard-format'
import type {
  Availability,
  Capabilities,
  DashboardFilters,
  EvidenceDetailResponse,
  EvidencePageResponse,
  FilterOptions,
  MetadataResponse,
  Metric,
  ProcessingSummary,
  SeriesPoint,
  SignalSummary,
  SourceIdentity,
} from './dashboard-types'

const reasonLabels: Record<string, string> = {
  uncalibrated: 'Awaiting calibration',
  awaiting_calibration: 'Awaiting calibration',
  no_eligible_evidence: 'No eligible evidence',
  insufficient_data: 'Insufficient data',
  unsupported_dimension: 'Unsupported dimension',
  source_unavailable: 'Source unavailable',
}

export function StatusBadge({
  children,
  tone = 'info',
}: {
  children: ReactNode
  tone?: 'success' | 'warning' | 'danger' | 'info' | 'illustrative'
}) {
  return (
    <span className={`status-badge status-badge--${tone}`}>{children}</span>
  )
}

export function ContextSwitch({
  context,
  disabled,
  onChange,
}: {
  context: 'live' | 'demo'
  disabled?: boolean
  onChange: (context: 'live' | 'demo') => void
}) {
  return (
    <div
      className="context-switch"
      role="group"
      aria-label="Presentation context"
    >
      <button
        type="button"
        aria-pressed={context === 'live'}
        disabled={disabled}
        onClick={() => onChange('live')}
      >
        Live
      </button>
      <button
        type="button"
        aria-pressed={context === 'demo'}
        disabled={disabled}
        onClick={() => onChange('demo')}
      >
        Demo
      </button>
    </div>
  )
}

const demoMethodLabels: Record<string, { label: string; category: string }> = {
  'feedback-decision-semif': {
    label: 'SemIf',
    category: 'Local open model',
  },
  'feedback-decision-rules': {
    label: 'Rules baseline',
    category: 'Deterministic method',
  },
  'feedback-decision-ai-reference': {
    label: 'Sol medium',
    category: 'AI reference',
  },
}

export function DemoMethodSwitch({
  sources,
  selectedKey,
  disabled,
  onChange,
}: {
  sources: SourceIdentity[]
  selectedKey: string
  disabled?: boolean
  onChange: (sourceKey: string) => void
}) {
  return (
    <section className="demo-method-switch" aria-label="Demo decision method">
      <div>
        <p className="eyebrow">Decision source</p>
        <h2>Choose the 480-record review method</h2>
      </div>
      <div className="demo-method-switch__options">
        {sources.map((source) => {
          const description = demoMethodLabels[source.datasetName] ?? {
            label: source.displayName,
            category: source.datasetVersion,
          }
          return (
            <button
              key={source.key}
              type="button"
              aria-pressed={selectedKey === source.key}
              disabled={disabled}
              onClick={() => onChange(source.key)}
            >
              <strong>{description.label}</strong>
              <small>{description.category}</small>
            </button>
          )
        })}
      </div>
    </section>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  aside,
}: {
  eyebrow: string
  title: string
  description: string
  aside?: ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {aside ? <div className="page-header__aside">{aside}</div> : null}
    </header>
  )
}

function SelectField({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string
  label: string
  value: string | null
  options: string[]
  onChange: (value: string | null) => void
}) {
  return (
    <label className="filter-field" htmlFor={id}>
      <span>{label}</span>
      <select
        id={id}
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value || null)}
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  )
}

export function FilterBar({
  filters,
  capabilities,
  options,
  disabled,
  onChange,
}: {
  filters: DashboardFilters
  capabilities: Capabilities
  options: FilterOptions
  disabled?: boolean
  onChange: (next: DashboardFilters) => void
}) {
  const update = <K extends keyof DashboardFilters>(
    key: K,
    value: DashboardFilters[K],
  ) => onChange({ ...filters, [key]: value })

  const updateDate = (key: 'from' | 'toExclusive', value: string) => {
    if (!value) return
    const next = { ...filters, [key]: `${value}T00:00:00Z` }
    if (Date.parse(next.from) >= Date.parse(next.toExclusive)) return
    onChange(next)
  }

  return (
    <fieldset className="filter-bar" disabled={disabled}>
      <legend>Applied filters</legend>
      <label className="filter-field" htmlFor="from-filter">
        <span>From</span>
        <input
          id="from-filter"
          type="date"
          value={filters.from.slice(0, 10)}
          onChange={(event) => updateDate('from', event.target.value)}
        />
      </label>
      <label className="filter-field" htmlFor="to-filter">
        <span>To (exclusive)</span>
        <input
          id="to-filter"
          type="date"
          value={filters.toExclusive.slice(0, 10)}
          onChange={(event) => updateDate('toExclusive', event.target.value)}
        />
      </label>
      <SelectField
        id="topic-filter"
        label="Topic"
        value={filters.topic}
        options={options.topics}
        onChange={(value) => update('topic', value)}
      />
      {capabilities.products ? (
        <SelectField
          id="product-filter"
          label="Product"
          value={filters.product}
          options={options.products}
          onChange={(value) => update('product', value)}
        />
      ) : null}
      {capabilities.categories ? (
        <SelectField
          id="category-filter"
          label="Category"
          value={filters.category}
          options={options.categories}
          onChange={(value) => update('category', value)}
        />
      ) : null}
      {capabilities.languages ? (
        <SelectField
          id="language-filter"
          label="Language"
          value={filters.language}
          options={options.languages}
          onChange={(value) => update('language', value)}
        />
      ) : null}
      {capabilities.channels ? (
        <SelectField
          id="channel-filter"
          label="Channel"
          value={filters.channel}
          options={options.channels}
          onChange={(value) => update('channel', value)}
        />
      ) : null}
    </fieldset>
  )
}

function availabilityText(availability: Availability) {
  if (availability.state === 'available') return 'Available'
  return reasonLabels[availability.reason]
}

export function MetricCard({ metric }: { metric: Metric }) {
  const available = metric.availability.state === 'available'
  const displayValue = !available
    ? '—'
    : metric.unit === 'percent'
      ? formatRate(metric.value)
      : metric.unit === 'score'
        ? metric.value === null
          ? '—'
          : `${metric.value > 0 ? '+' : ''}${metric.value.toFixed(1)} pp`
        : metric.value === null
          ? '—'
          : formatCount(metric.value)

  return (
    <article className={`metric-card ${available ? '' : 'metric-card--muted'}`}>
      <div className="metric-card__heading">
        <h3>{metric.label}</h3>
        <StatusBadge tone={available ? 'success' : 'warning'}>
          {availabilityText(metric.availability)}
        </StatusBadge>
      </div>
      <p className="metric-card__value">{displayValue}</p>
      {metric.numerator !== null && metric.denominator !== null ? (
        <p className="metric-card__denominator">
          {metricDenominatorText(metric)}
        </p>
      ) : metric.numerator !== null ? (
        <p className="metric-card__denominator">
          {formatCount(metric.numerator)} records
        </p>
      ) : (
        <p className="metric-card__denominator">
          No eligible denominator is available
        </p>
      )}
    </article>
  )
}

function metricDenominatorText(metric: Metric) {
  const numerator = formatCount(metric.numerator ?? 0)
  const denominator = formatCount(metric.denominator ?? 0)
  switch (metric.id) {
    case 'classified_feedback':
      return `${numerator} classified of ${denominator} imported`
    case 'analytical_coverage':
      return `${numerator} eligible of ${denominator} imported`
    case 'observed_issue_rate':
    case 'topic_rate':
      return `${numerator} of ${denominator} eligible`
    case 'signal-change':
      return `${numerator} of ${denominator} eligible in comparison`
    default:
      return `${numerator} of ${denominator}`
  }
}

export function MetricGrid({ metrics }: { metrics: Metric[] }) {
  return (
    <section className="metric-grid" aria-label="Overview metrics">
      {metrics.map((metric) => (
        <MetricCard key={metric.id} metric={metric} />
      ))}
    </section>
  )
}

function smoothLinePath(values: Array<{ x: number; y: number }>) {
  if (values.length < 2)
    return values.length ? `M ${values[0]!.x} ${values[0]!.y}` : ''
  const tension = 0.18
  return values.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x} ${point.y}`
    const previous = values[index - 1]!
    const beforePrevious = values[index - 2] ?? previous
    const next = values[index + 1] ?? point
    const control1X = previous.x + (point.x - beforePrevious.x) * tension
    const control1Y = previous.y + (point.y - beforePrevious.y) * tension
    const control2X = point.x - (next.x - previous.x) * tension
    const control2Y = point.y - (next.y - previous.y) * tension
    return `${path} C ${control1X} ${control1Y}, ${control2X} ${control2Y}, ${point.x} ${point.y}`
  }, '')
}

export function TimeSeriesPanel({
  title,
  series,
  availability,
}: {
  title: string
  series: SeriesPoint[]
  availability?: Availability
}) {
  if (availability?.state === 'unavailable') {
    return (
      <StatePanel
        title="Analytics withheld"
        tone="warning"
        description={`${availabilityText(availability)}. Processing activity does not establish an eligible analytical result.`}
      />
    )
  }

  const availablePoints = series.filter(
    (point): point is SeriesPoint & { value: number } => point.value !== null,
  )
  if (availablePoints.length === 0) {
    return (
      <StatePanel
        title="No series for this selection"
        description="No eligible observations fall inside the applied source, time range, and filters."
      />
    )
  }

  const width = 720
  const height = 280
  const padX = 44
  const padTop = 22
  const padBottom = 42
  const plot = availablePoints.map((point, index) => ({
    data: point,
    x:
      availablePoints.length === 1
        ? width / 2
        : padX + (index / (availablePoints.length - 1)) * (width - padX * 2),
    y: height - padBottom - (point.value / 100) * (height - padTop - padBottom),
  }))
  const line = smoothLinePath(plot)
  const area = `${line} L ${plot.at(-1)!.x} ${height - padBottom} L ${plot[0]!.x} ${height - padBottom} Z`
  const average =
    availablePoints.reduce((sum, point) => sum + point.value, 0) /
    availablePoints.length
  const minimum = Math.min(...availablePoints.map((point) => point.value))
  const maximum = Math.max(...availablePoints.map((point) => point.value))
  const current = availablePoints.at(-1)?.value ?? 0
  const yTicks = [0, 25, 50, 75, 100]
  const labelInterval = Math.max(1, Math.ceil(plot.length / 7))

  return (
    <section className="panel series-panel" aria-labelledby="series-title">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Observed over time</p>
          <h2 id="series-title">{title}</h2>
        </div>
        <StatusBadge tone="illustrative">Descriptive</StatusBadge>
      </div>
      <dl className="series-summary" aria-label={`${title} summary`}>
        <div>
          <dt>Latest</dt>
          <dd>{formatRate(current)}</dd>
        </div>
        <div>
          <dt>Average</dt>
          <dd>{formatRate(average)}</dd>
        </div>
        <div>
          <dt>Observed range</dt>
          <dd>
            {formatRate(minimum)}–{formatRate(maximum)}
          </dd>
        </div>
        <div>
          <dt>Periods</dt>
          <dd>{availablePoints.length}</dd>
        </div>
      </dl>
      <svg
        className="series-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title}. ${availablePoints.length} observed periods. A data table follows.`}
      >
        <defs>
          <linearGradient id="series-area-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.34" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <g className="series-chart__grid">
          {yTicks.map((tick) => {
            const y =
              height - padBottom - (tick / 100) * (height - padTop - padBottom)
            return (
              <g key={tick}>
                <line x1={padX} y1={y} x2={width - padX} y2={y} />
                <text x={padX - 10} y={y + 4} textAnchor="end">
                  {tick}%
                </text>
              </g>
            )
          })}
        </g>
        <line
          className="series-chart__average"
          x1={padX}
          y1={
            height - padBottom - (average / 100) * (height - padTop - padBottom)
          }
          x2={width - padX}
          y2={
            height - padBottom - (average / 100) * (height - padTop - padBottom)
          }
        />
        <path className="series-chart__area" d={area} />
        <path className="series-chart__line" d={line} />
        {plot.map((point, index) => (
          <g className="series-chart__point" key={point.data.periodStart}>
            <circle
              cx={point.x}
              cy={point.y}
              r={index === plot.length - 1 ? 6 : 4}
            >
              <title>
                {formatDate(point.data.periodStart)}:{' '}
                {formatRate(point.data.value)} ·{' '}
                {formatCount(point.data.topicNumerator)} of{' '}
                {formatCount(point.data.eligibleCount)}
              </title>
            </circle>
            {(index % labelInterval === 0 || index === plot.length - 1) && (
              <text
                className="series-chart__x-label"
                x={point.x}
                y={height - 14}
                textAnchor="middle"
              >
                {formatMonth(point.data.periodStart)}
              </text>
            )}
          </g>
        ))}
      </svg>
      <details className="data-disclosure">
        <summary>View chart data</summary>
        <div
          className="table-region"
          role="region"
          aria-label={`${title} data`}
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th scope="col">Period</th>
                <th scope="col">Imported</th>
                <th scope="col">Eligible</th>
                <th scope="col">Signal count</th>
                <th scope="col">Rate</th>
              </tr>
            </thead>
            <tbody>
              {series.map((point) => (
                <tr key={point.periodStart}>
                  <th scope="row">{formatDate(point.periodStart)}</th>
                  <td>{formatCount(point.importedCount)}</td>
                  <td>{formatCount(point.eligibleCount)}</td>
                  <td>{formatCount(point.topicNumerator)}</td>
                  <td>{formatRate(point.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}

export function StatePanel({
  title,
  description,
  tone = 'info',
  action,
}: {
  title: string
  description: string
  tone?: 'info' | 'warning' | 'danger'
  action?: ReactNode
}) {
  return (
    <section className={`state-panel state-panel--${tone}`} aria-live="polite">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {action ? <div className="state-panel__action">{action}</div> : null}
    </section>
  )
}

export function ProcessingPanel({
  processing,
}: {
  processing: ProcessingSummary
}) {
  return (
    <section className="panel" aria-labelledby="processing-title">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Operational state</p>
          <h2 id="processing-title">Processing activity</h2>
        </div>
      </div>
      <dl className="processing-grid">
        <div>
          <dt>Feedback records</dt>
          <dd>{formatCount(processing.feedbackRecords)}</dd>
        </div>
        <div>
          <dt>Decision runs</dt>
          <dd>{formatCount(processing.decisionRuns)}</dd>
        </div>
        <div>
          <dt>Typed answers</dt>
          <dd>{formatCount(processing.typedAnswers)}</dd>
        </div>
      </dl>
      <div className="processing-details">
        <KeyValueList title="Jobs" values={processing.jobsByStatus} />
        <KeyValueList
          title="Projection ledger"
          values={processing.projectionByDestination}
        />
      </div>
    </section>
  )
}

function KeyValueList({
  title,
  values,
}: {
  title: string
  values: Record<string, number>
}) {
  const entries = Object.entries(values)
  return (
    <div>
      <h3>{title}</h3>
      {entries.length ? (
        <dl className="key-value-list">
          {entries.map(([key, value]) => (
            <div key={key}>
              <dt>{key.replaceAll('_', ' ')}</dt>
              <dd>{formatCount(value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="muted">No activity</p>
      )}
    </div>
  )
}

export function SignalList({
  signals,
  onSelect,
}: {
  signals: SignalSummary[]
  onSelect: (signalId: string) => void
}) {
  if (!signals.length) return null

  return (
    <section className="panel" aria-labelledby="signals-title">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Evidence-led exploration</p>
          <h2 id="signals-title">Observed signals</h2>
        </div>
        <p className="muted">Ordered by descriptive change</p>
      </div>
      <div className="signal-list">
        {signals.map((signal) => (
          <article className="signal-row" key={signal.id}>
            <div>
              <h3>{signal.label}</h3>
              <p>{signal.definition}</p>
            </div>
            <div className="signal-row__measure">
              <strong>{formatRate(signal.rate)}</strong>
              <span>
                {formatCount(signal.numerator)} of{' '}
                {formatCount(signal.denominator)} eligible
              </span>
            </div>
            <div className="signal-row__change">
              <span>Observed change</span>
              <strong>
                {signal.deltaPoints === null
                  ? '—'
                  : `${signal.deltaPoints > 0 ? '+' : ''}${signal.deltaPoints.toFixed(1)} pp`}
              </strong>
            </div>
            <button
              className="button button--secondary"
              type="button"
              aria-label={`Explore ${signal.label}`}
              onClick={() => onSelect(signal.id)}
            >
              Explore signal
            </button>
          </article>
        ))}
      </div>
    </section>
  )
}

export function SourceSummary({ metadata }: { metadata: MetadataResponse }) {
  if (!metadata.source) return null
  return (
    <dl className="source-summary" aria-label="Selected source">
      <div>
        <dt>Current source</dt>
        <dd>{metadata.source.displayName}</dd>
      </div>
      <div>
        <dt>Dataset</dt>
        <dd>{metadata.source.datasetName}</dd>
      </div>
      <div>
        <dt>Version</dt>
        <dd>{metadata.source.datasetVersion}</dd>
      </div>
      {metadata.availableRange ? (
        <div>
          <dt>Available range</dt>
          <dd>
            {formatDate(metadata.availableRange.from)} –{' '}
            {formatDate(metadata.availableRange.toExclusive)} (exclusive)
          </dd>
        </div>
      ) : null}
    </dl>
  )
}

export function EvidenceTable({
  evidence,
  capabilities,
  onOpen,
  onPage,
}: {
  evidence: EvidencePageResponse
  capabilities: Capabilities
  onOpen: (feedbackId: string, decisionId: string) => void
  onPage: (page: number) => void
}) {
  if (evidence.items.length === 0) {
    return (
      <StatePanel
        title="No contributing evidence"
        description="No eligible records support this signal under the applied filters."
      />
    )
  }

  const first = (evidence.page - 1) * evidence.pageSize + 1
  const last = Math.min(evidence.total, evidence.page * evidence.pageSize)
  const totalPages = Math.max(1, Math.ceil(evidence.total / evidence.pageSize))

  return (
    <section className="panel" aria-labelledby="evidence-title">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Traceable support</p>
          <h2 id="evidence-title">Contributing feedback</h2>
        </div>
        <p className="muted">
          {first}–{last} of {formatCount(evidence.total)}
        </p>
      </div>
      <div
        className="table-region"
        role="region"
        aria-label="Contributing feedback records"
        tabIndex={0}
      >
        <table>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Evidence</th>
              {capabilities.channels ? <th scope="col">Channel</th> : null}
              {capabilities.products ? <th scope="col">Product</th> : null}
              <th scope="col">Inclusion</th>
              <th scope="col">
                <span className="sr-only">Action</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {evidence.items.map((row) => (
              <tr key={`${row.feedbackId}:${row.decisionId}`}>
                <td>{formatDate(row.occurredAt)}</td>
                <td className="evidence-copy">
                  {row.evidenceAccess === 'restricted' ? (
                    <StatusBadge tone="danger">Evidence restricted</StatusBadge>
                  ) : (
                    row.excerpt
                  )}
                </td>
                {capabilities.channels ? <td>{row.channel ?? '—'}</td> : null}
                {capabilities.products ? (
                  <td>{row.productLabel ?? '—'}</td>
                ) : null}
                <td>{row.inclusionReason}</td>
                <td>
                  <button
                    className="text-button"
                    type="button"
                    aria-label={`View decision for ${row.sourceRecordId}`}
                    onClick={() => onOpen(row.feedbackId, row.decisionId)}
                  >
                    View decision
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <nav className="pagination" aria-label="Evidence pagination">
        <button
          className="button button--secondary"
          type="button"
          disabled={evidence.page <= 1}
          onClick={() => onPage(evidence.page - 1)}
        >
          Previous
        </button>
        <span aria-live="polite">
          Page {evidence.page} of {totalPages}
        </span>
        <button
          className="button button--secondary"
          type="button"
          disabled={evidence.page >= totalPages}
          onClick={() => onPage(evidence.page + 1)}
        >
          Next
        </button>
      </nav>
    </section>
  )
}

function displayAnswer(value: string | number | boolean | null) {
  if (value === null) return 'Not answered'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

export function DecisionDetail({ detail }: { detail: EvidenceDetailResponse }) {
  return (
    <div className="detail-layout">
      <section className="panel detail-record" aria-labelledby="record-title">
        <div className="panel__header">
          <div>
            <p className="eyebrow">Feedback record</p>
            <h2 id="record-title">{detail.record.sourceRecordId}</h2>
          </div>
          <StatusBadge
            tone={
              detail.evidence.access === 'restricted'
                ? 'danger'
                : 'illustrative'
            }
          >
            {detail.evidence.access === 'restricted'
              ? 'Restricted evidence'
              : 'Permitted synthetic evidence'}
          </StatusBadge>
        </div>
        <dl className="detail-list">
          <div>
            <dt>Source</dt>
            <dd>{detail.source.displayName}</dd>
          </div>
          <div>
            <dt>Dataset version</dt>
            <dd>{detail.source.datasetVersion}</dd>
          </div>
          <div>
            <dt>Occurred</dt>
            <dd>{formatDateTime(detail.record.occurredAt)}</dd>
          </div>
          <div>
            <dt>Inclusion</dt>
            <dd>{detail.inclusionReason}</dd>
          </div>
        </dl>
        {detail.evidence.access === 'permitted_synthetic' ? (
          <article className="evidence-body">
            {detail.evidence.title ? <h3>{detail.evidence.title}</h3> : null}
            <p>{detail.evidence.body}</p>
          </article>
        ) : (
          <StatePanel
            title="Evidence text is restricted"
            tone="warning"
            description="This live read boundary exposes allow-listed record metadata and curated typed answers only. The feedback body remains protected."
          />
        )}
      </section>

      <section className="panel" aria-labelledby="answers-title">
        <div className="panel__header">
          <div>
            <p className="eyebrow">Curated decision output</p>
            <h2 id="answers-title">Typed answers</h2>
          </div>
        </div>
        {detail.answers.length ? (
          <div className="answer-list">
            {detail.answers.map((answer) => (
              <article className="answer-row" key={answer.questionId}>
                <div>
                  <h3>{answer.label}</h3>
                  <p>{answer.primitive}</p>
                </div>
                <strong>{displayAnswer(answer.value)}</strong>
                <span>{answer.confidenceLabel ?? 'No confidence label'}</span>
                <StatusBadge
                  tone={
                    answer.eligibility === 'illustrative_eligible'
                      ? 'illustrative'
                      : 'warning'
                  }
                >
                  {answer.eligibility.replaceAll('_', ' ')}
                </StatusBadge>
              </article>
            ))}
          </div>
        ) : (
          <p className="muted">
            No curated answers are available for this decision.
          </p>
        )}
      </section>

      <section
        className="panel detail-provenance"
        aria-labelledby="provenance-title"
      >
        <div className="panel__header">
          <div>
            <p className="eyebrow">Immutable lineage</p>
            <h2 id="provenance-title">Decision provenance</h2>
          </div>
        </div>
        <dl className="detail-list detail-list--code">
          <div>
            <dt>Decision ID</dt>
            <dd>{detail.provenance.decisionId}</dd>
          </div>
          <div>
            <dt>Schema</dt>
            <dd>
              {detail.provenance.schemaName} v{detail.provenance.schemaVersion}
            </dd>
          </div>
          <div>
            <dt>Model version</dt>
            <dd>{detail.provenance.modelVersion}</dd>
          </div>
          <div>
            <dt>Policy</dt>
            <dd>
              {detail.provenance.policyVersion ?? 'Not versioned'} ·{' '}
              {detail.provenance.policyStatus.replaceAll('_', ' ')}
            </dd>
          </div>
          <div>
            <dt>Trace ID</dt>
            <dd>{detail.provenance.traceId}</dd>
          </div>
          <div>
            <dt>Decided</dt>
            <dd>{formatDateTime(detail.provenance.decidedAt)}</dd>
          </div>
        </dl>
      </section>
    </div>
  )
}

export function LoadingPanel({ label }: { label: string }) {
  return (
    <section className="loading-panel" role="status">
      <span className="loading-mark" aria-hidden="true" />
      <div>
        <h2>{label}</h2>
        <p>Reading the selected dashboard context…</p>
      </div>
    </section>
  )
}

export function ErrorPanel({
  title,
  message,
  onRetry,
}: {
  title: string
  message: string
  onRetry: () => void
}) {
  return (
    <StatePanel
      title={title}
      tone="danger"
      description={message}
      action={
        <button
          className="button button--primary"
          type="button"
          onClick={onRetry}
        >
          Retry
        </button>
      }
    />
  )
}
