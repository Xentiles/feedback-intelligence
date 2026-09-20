import { useEffect, useRef, useState } from 'react'

import { dashboardClient, type DashboardClient } from './dashboard-api'
import {
  ContextSwitch,
  DecisionDetail,
  DemoMethodSwitch,
  ErrorPanel,
  EvidenceTable,
  FilterBar,
  LoadingPanel,
  MetricGrid,
  PageHeader,
  ProcessingPanel,
  SignalList,
  SourceSummary,
  StatePanel,
  StatusBadge,
  TimeSeriesPanel,
} from './dashboard-components'
import { formatCount, formatDate, formatRate } from './dashboard-format'
import {
  EvaluationComparisonRegion,
  type EvaluationAsyncState,
} from './evaluation-components'
import { OrbitalSurface } from './orbital-surface'
import { TrendEvaluationRegion, type TrendAsyncState } from './trend-components'
import type {
  DashboardFilters,
  EvidenceDetailResponse,
  EvidencePageResponse,
  MetadataResponse,
  Metric,
  OverviewResponse,
  PresentationContext,
  SignalResponse,
} from './dashboard-types'

type AsyncState<T> =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

type View =
  | { name: 'overview' }
  | { name: 'signal'; signalId: string; page: number }
  | {
      name: 'detail'
      signalId: string
      feedbackId: string
      decisionId: string
      page: number
    }

const PAGE_SIZE = 5

function utcDayBoundary(value: string, roundUp: boolean) {
  const instant = new Date(value)
  if (Number.isNaN(instant.getTime())) return value
  const start = Date.UTC(
    instant.getUTCFullYear(),
    instant.getUTCMonth(),
    instant.getUTCDate(),
  )
  const boundary =
    roundUp && instant.getTime() > start ? start + 86_400_000 : start
  return new Date(boundary).toISOString().replace('.000Z', 'Z')
}

function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : 'An unexpected request error occurred.'
}

function initialFilters(metadata: MetadataResponse): DashboardFilters | null {
  if (!metadata.source || !metadata.availableRange) return null
  return {
    sourceKey: metadata.source.key,
    from: utcDayBoundary(metadata.availableRange.from, false),
    toExclusive: utcDayBoundary(metadata.availableRange.toExclusive, true),
    topic: null,
    product: null,
    category: null,
    language: null,
    channel: null,
  }
}

function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function App({
  client = dashboardClient,
}: {
  client?: DashboardClient
}) {
  const [context, setContext] = useState<PresentationContext>('demo')
  const [headerCollapsed, setHeaderCollapsed] = useState(false)
  const [view, setView] = useState<View>({ name: 'overview' })
  const [filters, setFilters] = useState<DashboardFilters | null>(null)
  const [metadata, setMetadata] = useState<AsyncState<MetadataResponse>>({
    status: 'idle',
  })
  const [overview, setOverview] = useState<AsyncState<OverviewResponse>>({
    status: 'idle',
  })
  const [trends, setTrends] = useState<TrendAsyncState>({ status: 'idle' })
  const [evaluation, setEvaluation] = useState<EvaluationAsyncState>({
    status: 'idle',
  })
  const [signal, setSignal] = useState<AsyncState<SignalResponse>>({
    status: 'idle',
  })
  const [evidence, setEvidence] = useState<AsyncState<EvidencePageResponse>>({
    status: 'idle',
  })
  const [detail, setDetail] = useState<AsyncState<EvidenceDetailResponse>>({
    status: 'idle',
  })
  const [metadataRetry, setMetadataRetry] = useState(0)
  const [overviewRetry, setOverviewRetry] = useState(0)
  const [trendsRetry, setTrendsRetry] = useState(0)
  const [evaluationRetry, setEvaluationRetry] = useState(0)
  const [signalRetry, setSignalRetry] = useState(0)
  const [evidenceRetry, setEvidenceRetry] = useState(0)
  const [detailRetry, setDetailRetry] = useState(0)
  const generation = useRef(0)

  const signalId = view.name === 'signal' ? view.signalId : null
  const evidencePage = view.name === 'signal' ? view.page : null
  const detailIdentity =
    view.name === 'detail' ? `${view.feedbackId}:${view.decisionId}` : null

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const requestGeneration = generation.current
    client
      .trends(context, { signal: controller.signal })
      .then((response) => {
        if (
          !active ||
          generation.current !== requestGeneration ||
          response.context !== context
        ) {
          return
        }
        setTrends({ status: 'ready', data: response })
      })
      .catch((error: unknown) => {
        if (
          !active ||
          isAbort(error) ||
          generation.current !== requestGeneration
        )
          return
        setTrends({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, context, trendsRetry])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const requestGeneration = generation.current
    client
      .evaluation(context, { signal: controller.signal })
      .then((response) => {
        if (
          !active ||
          generation.current !== requestGeneration ||
          response.context !== context
        ) {
          return
        }
        setEvaluation({ status: 'ready', data: response })
      })
      .catch((error: unknown) => {
        if (
          !active ||
          isAbort(error) ||
          generation.current !== requestGeneration
        )
          return
        setEvaluation({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, context, evaluationRetry])

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const requestGeneration = generation.current
    client
      .metadata(context, { signal: controller.signal })
      .then((response) => {
        if (
          !active ||
          generation.current !== requestGeneration ||
          response.context !== context
        ) {
          return
        }
        setMetadata({ status: 'ready', data: response })
        setFilters(initialFilters(response))
      })
      .catch((error: unknown) => {
        if (
          !active ||
          isAbort(error) ||
          generation.current !== requestGeneration
        )
          return
        setMetadata({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, context, metadataRetry])

  useEffect(() => {
    if (
      metadata.status !== 'ready' ||
      !metadata.data.source ||
      !metadata.data.availableRange ||
      !filters
    ) {
      return
    }
    const controller = new AbortController()
    let active = true
    const requestGeneration = generation.current
    client
      .overview(context, filters, { signal: controller.signal })
      .then((response) => {
        if (
          !active ||
          generation.current !== requestGeneration ||
          response.context !== context
        ) {
          return
        }
        setOverview({ status: 'ready', data: response })
      })
      .catch((error: unknown) => {
        if (
          !active ||
          isAbort(error) ||
          generation.current !== requestGeneration
        )
          return
        setOverview({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, context, filters, metadata, overviewRetry])

  useEffect(() => {
    if (!signalId || !filters) return
    const controller = new AbortController()
    let active = true
    const requestGeneration = generation.current
    client
      .signal(context, signalId, filters, {
        signal: controller.signal,
      })
      .then((response) => {
        if (
          !active ||
          generation.current !== requestGeneration ||
          response.context !== context
        ) {
          return
        }
        setSignal({ status: 'ready', data: response })
      })
      .catch((error: unknown) => {
        if (
          !active ||
          isAbort(error) ||
          generation.current !== requestGeneration
        )
          return
        setSignal({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, context, filters, signalId, signalRetry])

  useEffect(() => {
    if (!signalId || evidencePage === null || !filters) return
    const controller = new AbortController()
    let active = true
    const requestGeneration = generation.current
    client
      .evidence(context, signalId, filters, evidencePage, PAGE_SIZE, {
        signal: controller.signal,
      })
      .then((response) => {
        if (
          !active ||
          generation.current !== requestGeneration ||
          response.context !== context
        ) {
          return
        }
        setEvidence({ status: 'ready', data: response })
      })
      .catch((error: unknown) => {
        if (
          !active ||
          isAbort(error) ||
          generation.current !== requestGeneration
        )
          return
        setEvidence({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, context, evidencePage, evidenceRetry, filters, signalId])

  useEffect(() => {
    if (view.name !== 'detail') return
    const controller = new AbortController()
    let active = true
    const requestGeneration = generation.current
    client
      .detail(context, view.feedbackId, view.decisionId, {
        signal: controller.signal,
      })
      .then((response) => {
        if (
          !active ||
          generation.current !== requestGeneration ||
          response.context !== context
        ) {
          return
        }
        setDetail({ status: 'ready', data: response })
      })
      .catch((error: unknown) => {
        if (
          !active ||
          isAbort(error) ||
          generation.current !== requestGeneration
        )
          return
        setDetail({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [client, context, detailIdentity, detailRetry, view])

  function changeContext(next: PresentationContext) {
    if (next === context) return
    generation.current += 1
    setContext(next)
    setView({ name: 'overview' })
    setFilters(null)
    setMetadata({ status: 'idle' })
    setOverview({ status: 'idle' })
    setTrends({ status: 'idle' })
    setEvaluation({ status: 'idle' })
    setSignal({ status: 'idle' })
    setEvidence({ status: 'idle' })
    setDetail({ status: 'idle' })
  }

  function changeFilters(next: DashboardFilters) {
    setFilters(next)
    if (view.name === 'signal') {
      setSignal({ status: 'idle' })
      setEvidence({ status: 'idle' })
      setView({ ...view, page: 1 })
    } else {
      setOverview({ status: 'idle' })
    }
  }

  const overviewValue = overview.status === 'ready' ? overview.data : null
  const activeSignalId =
    view.name === 'signal' || view.name === 'detail' ? view.signalId : null
  const firstSignalId = overviewValue?.signals[0]?.id ?? activeSignalId
  const activeSource =
    metadata.status === 'ready' && filters
      ? (metadata.data.sources.find(
          (source) => source.key === filters.sourceKey,
        ) ?? metadata.data.source)
      : metadata.status === 'ready'
        ? metadata.data.source
        : null

  return (
    <div className="application" data-header-collapsed={headerCollapsed}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <OrbitalSurface />
      <button
        type="button"
        className="header-toggle"
        aria-controls="app-header"
        aria-expanded={!headerCollapsed}
        aria-label={headerCollapsed ? 'Open navigation' : 'Collapse navigation'}
        title={headerCollapsed ? 'Open navigation' : 'Collapse navigation'}
        onClick={() => setHeaderCollapsed((collapsed) => !collapsed)}
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          aria-hidden="true"
        >
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M9 4v16" />
          <path d={headerCollapsed ? 'm13 9 3 3-3 3' : 'm16 9-3 3 3 3'} />
        </svg>
      </button>
      <header id="app-header" className="app-header" hidden={headerCollapsed}>
        <a
          className="brand"
          href="#main"
          aria-label="Feedback Intelligence home"
        >
          <span className="brand__mark" aria-hidden="true" />
          <span>
            <strong>Feedback Intelligence</strong>
            <small>Confidence-aware analytics</small>
          </span>
        </a>
        <span className="rail-section-label">Workspace</span>
        <nav className="primary-nav" aria-label="Primary navigation">
          <button
            type="button"
            aria-current={view.name === 'overview' ? 'page' : undefined}
            onClick={() => setView({ name: 'overview' })}
          >
            Overview
          </button>
          <button
            type="button"
            aria-current={view.name !== 'overview' ? 'page' : undefined}
            disabled={!firstSignalId}
            onClick={() => {
              if (!firstSignalId) return
              setSignal({ status: 'idle' })
              setEvidence({ status: 'idle' })
              setView({ name: 'signal', signalId: firstSignalId, page: 1 })
            }}
          >
            Signals
          </button>
        </nav>
        <div className="header-actions">
          <ContextSwitch context={context} onChange={changeContext} />
        </div>
      </header>

      <div
        className={`context-banner context-banner--${context}`}
        role="status"
      >
        <strong>
          {context === 'demo'
            ? 'Demo — selectable synthetic decisions'
            : 'Live — connected data'}
        </strong>
        <span>
          {context === 'demo'
            ? `${activeSource?.displayName ?? 'The selected 480-record method'} powers the overview, filters, and evidence.`
            : 'Operational records are live. Analytics remain subject to the active calibration policy.'}
        </span>
      </div>

      <main id="main" className="app-main">
        {metadata.status === 'error' ? (
          <>
            <PageHeader
              eyebrow="Dashboard"
              title="Feedback Intelligence"
              description="Read-only processing, analytics, and evidence trace."
            />
            <ErrorPanel
              title="Source metadata could not be loaded"
              message={metadata.message}
              onRetry={() => {
                setMetadata({ status: 'idle' })
                setMetadataRetry((value) => value + 1)
              }}
            />
          </>
        ) : metadata.status !== 'ready' ? (
          <>
            <PageHeader
              eyebrow="Dashboard"
              title="Feedback Intelligence"
              description="Read-only processing, analytics, and evidence trace."
            />
            <LoadingPanel label="Loading source metadata" />
          </>
        ) : view.name === 'overview' ? (
          <OverviewView
            context={context}
            metadata={metadata.data}
            filters={filters}
            overview={overview}
            trends={trends}
            evaluation={evaluation}
            onFilters={changeFilters}
            onSelectSignal={(selectedSignalId) => {
              setSignal({ status: 'idle' })
              setEvidence({ status: 'idle' })
              setView({
                name: 'signal',
                signalId: selectedSignalId,
                page: 1,
              })
            }}
            onDemo={() => changeContext('demo')}
            onRetry={() => {
              setOverview({ status: 'idle' })
              setOverviewRetry((value) => value + 1)
            }}
            onRetryTrends={() => {
              setTrends({ status: 'idle' })
              setTrendsRetry((value) => value + 1)
            }}
            onRetryEvaluation={() => {
              setEvaluation({ status: 'idle' })
              setEvaluationRetry((value) => value + 1)
            }}
          />
        ) : view.name === 'signal' ? (
          <SignalView
            metadata={metadata.data}
            filters={filters}
            signal={signal}
            evidence={evidence}
            onFilters={changeFilters}
            onBack={() => setView({ name: 'overview' })}
            onPage={(page) => {
              setEvidence({ status: 'idle' })
              setView({ ...view, page })
            }}
            onOpen={(feedbackId, decisionId) => {
              setDetail({ status: 'idle' })
              setView({ ...view, name: 'detail', feedbackId, decisionId })
            }}
            onRetrySignal={() => {
              setSignal({ status: 'idle' })
              setSignalRetry((value) => value + 1)
            }}
            onRetryEvidence={() => {
              setEvidence({ status: 'idle' })
              setEvidenceRetry((value) => value + 1)
            }}
          />
        ) : (
          <DetailView
            detail={detail}
            onBack={() =>
              setView({
                name: 'signal',
                signalId: view.signalId,
                page: view.page,
              })
            }
            onRetry={() => {
              setDetail({ status: 'idle' })
              setDetailRetry((value) => value + 1)
            }}
          />
        )}
      </main>

      <footer className="app-footer">
        Read-only dashboard · UTC intervals use [from, to exclusive)
      </footer>
    </div>
  )
}

function OverviewView({
  context,
  metadata,
  filters,
  overview,
  trends,
  evaluation,
  onFilters,
  onSelectSignal,
  onDemo,
  onRetry,
  onRetryTrends,
  onRetryEvaluation,
}: {
  context: PresentationContext
  metadata: MetadataResponse
  filters: DashboardFilters | null
  overview: AsyncState<OverviewResponse>
  trends: TrendAsyncState
  evaluation: EvaluationAsyncState
  onFilters: (filters: DashboardFilters) => void
  onSelectSignal: (signalId: string) => void
  onDemo: () => void
  onRetry: () => void
  onRetryTrends: () => void
  onRetryEvaluation: () => void
}) {
  return (
    <>
      <PageHeader
        eyebrow={
          context === 'demo' ? 'Illustrative overview' : 'Connected overview'
        }
        title="Feedback overview"
        description="See what was imported, what was classified, and which records are eligible for analysis."
        aside={
          <StatusBadge tone={context === 'demo' ? 'illustrative' : 'info'}>
            {metadata.policyStatus.replaceAll('_', ' ')}
          </StatusBadge>
        }
      />
      {context === 'demo' && filters && metadata.sources.length > 1 ? (
        <DemoMethodSwitch
          sources={metadata.sources}
          selectedKey={filters.sourceKey}
          disabled={overview.status === 'loading'}
          onChange={(sourceKey) =>
            onFilters({
              ...filters,
              sourceKey,
              topic: null,
              product: null,
              category: null,
              language: null,
              channel: null,
            })
          }
        />
      ) : null}
      <SourceSummary
        metadata={{
          ...metadata,
          source:
            metadata.sources.find(
              (source) => source.key === filters?.sourceKey,
            ) ?? metadata.source,
        }}
      />
      {filters ? (
        <FilterBar
          filters={filters}
          capabilities={metadata.capabilities}
          options={metadata.filterOptions}
          disabled={overview.status === 'loading'}
          onChange={onFilters}
        />
      ) : null}
      {!metadata.source ? (
        <>
          <StatePanel
            title="No imported feedback yet"
            description="The connected storage is available, but it does not contain an imported source. Date and analytical filters will appear after records arrive."
          />
          <ProcessingPanel
            processing={{
              feedbackRecords: 0,
              decisionRuns: 0,
              typedAnswers: 0,
              jobsByStatus: {},
              projectionByDestination: {},
            }}
          />
        </>
      ) : overview.status === 'error' ? (
        <ErrorPanel
          title="Overview could not be loaded"
          message={overview.message}
          onRetry={onRetry}
        />
      ) : overview.status !== 'ready' ? (
        <LoadingPanel label="Loading overview" />
      ) : (
        <>
          <MetricGrid metrics={overview.data.metrics} />
          {context === 'live' &&
          metadata.policyStatus === 'awaiting_calibration' ? (
            <StatePanel
              title="Analytics withheld — awaiting calibration"
              tone="warning"
              description="Processed records can exist while zero records are eligible for analytical projection. This does not mean that no complaints or issues were observed."
              action={
                <button
                  className="button button--primary"
                  type="button"
                  onClick={onDemo}
                >
                  View illustrative demo
                </button>
              }
            />
          ) : (
            <>
              <TimeSeriesPanel
                title="Eligible signal rate"
                series={overview.data.series}
              />
              <SignalList
                signals={overview.data.signals}
                onSelect={onSelectSignal}
              />
            </>
          )}
          <ProcessingPanel processing={overview.data.processing} />
        </>
      )}
      <EvaluationComparisonRegion
        evaluation={evaluation}
        onRetry={onRetryEvaluation}
      />
      <TrendEvaluationRegion trends={trends} onRetry={onRetryTrends} />
    </>
  )
}

function signalMetrics(response: SignalResponse): Metric[] {
  const imported = response.series.reduce(
    (total, point) => total + point.importedCount,
    0,
  )
  const eligible = response.series.reduce(
    (total, point) => total + point.eligibleCount,
    0,
  )
  return [
    {
      id: 'signal-numerator',
      label: 'Contributing records',
      unit: 'count',
      value: response.signal.numerator,
      numerator: response.signal.numerator,
      denominator: null,
      availability: response.signal.availability,
    },
    {
      id: 'signal-denominator',
      label: 'Eligible denominator',
      unit: 'count',
      value: response.signal.denominator,
      numerator: response.signal.denominator,
      denominator: null,
      availability: response.signal.availability,
    },
    {
      id: 'signal-coverage',
      label: 'Eligible coverage',
      unit: 'percent',
      value: imported > 0 ? (eligible / imported) * 100 : null,
      numerator: eligible,
      denominator: imported,
      availability:
        imported > 0
          ? { state: 'available', reason: null }
          : { state: 'unavailable', reason: 'insufficient_data' },
    },
    {
      id: 'signal-change',
      label: 'Observed change',
      unit: 'score',
      value: response.signal.deltaPoints,
      numerator: response.signal.comparison?.numerator ?? null,
      denominator: response.signal.comparison?.denominator ?? null,
      availability:
        response.signal.deltaPoints !== null && response.signal.comparison
          ? { state: 'available', reason: null }
          : { state: 'unavailable', reason: 'insufficient_data' },
    },
  ]
}

function SignalView({
  metadata,
  filters,
  signal,
  evidence,
  onFilters,
  onBack,
  onPage,
  onOpen,
  onRetrySignal,
  onRetryEvidence,
}: {
  metadata: MetadataResponse
  filters: DashboardFilters | null
  signal: AsyncState<SignalResponse>
  evidence: AsyncState<EvidencePageResponse>
  onFilters: (filters: DashboardFilters) => void
  onBack: () => void
  onPage: (page: number) => void
  onOpen: (feedbackId: string, decisionId: string) => void
  onRetrySignal: () => void
  onRetryEvidence: () => void
}) {
  return (
    <>
      <button className="breadcrumb" type="button" onClick={onBack}>
        ← Back to overview
      </button>
      <PageHeader
        eyebrow="Signal explorer"
        title={
          signal.status === 'ready'
            ? signal.data.signal.label
            : 'Observed signal'
        }
        description={
          signal.status === 'ready'
            ? signal.data.signal.definition
            : 'Inspect the series, eligibility context, and contributing feedback.'
        }
        aside={
          <StatusBadge
            tone={metadata.context === 'demo' ? 'illustrative' : 'info'}
          >
            {metadata.context === 'demo'
              ? 'Illustrative scenario'
              : 'Connected result'}
          </StatusBadge>
        }
      />
      {filters ? (
        <FilterBar
          filters={filters}
          capabilities={metadata.capabilities}
          options={metadata.filterOptions}
          disabled={signal.status === 'loading'}
          onChange={onFilters}
        />
      ) : null}
      {signal.status === 'error' ? (
        <ErrorPanel
          title="Signal could not be loaded"
          message={signal.message}
          onRetry={onRetrySignal}
        />
      ) : signal.status !== 'ready' ? (
        <LoadingPanel label="Loading signal" />
      ) : (
        <>
          <div className="signal-context" aria-label="Signal method and range">
            <span>{signal.data.method}</span>
            <span>
              {formatDate(signal.data.filters.from)} –{' '}
              {formatDate(signal.data.filters.toExclusive)} (exclusive)
            </span>
          </div>
          <MetricGrid metrics={signalMetrics(signal.data)} />
          {signal.data.signal.comparison ? (
            <p className="comparison-note">
              Comparison: {formatCount(signal.data.signal.comparison.numerator)}{' '}
              of {formatCount(signal.data.signal.comparison.denominator)}{' '}
              eligible ({formatRate(signal.data.signal.comparison.rate)}) from{' '}
              {formatDate(signal.data.signal.comparison.range.from)} to{' '}
              {formatDate(signal.data.signal.comparison.range.toExclusive)}.
            </p>
          ) : null}
          <TimeSeriesPanel
            title={`${signal.data.signal.label} rate`}
            series={signal.data.series}
            availability={signal.data.signal.availability}
          />
        </>
      )}
      {evidence.status === 'error' ? (
        <ErrorPanel
          title="Contributing feedback could not be loaded"
          message={evidence.message}
          onRetry={onRetryEvidence}
        />
      ) : evidence.status !== 'ready' ? (
        <LoadingPanel label="Loading contributing feedback" />
      ) : (
        <EvidenceTable
          evidence={evidence.data}
          capabilities={metadata.capabilities}
          onOpen={onOpen}
          onPage={onPage}
        />
      )}
    </>
  )
}

function DetailView({
  detail,
  onBack,
  onRetry,
}: {
  detail: AsyncState<EvidenceDetailResponse>
  onBack: () => void
  onRetry: () => void
}) {
  return (
    <>
      <button className="breadcrumb" type="button" onClick={onBack}>
        ← Back to contributing feedback
      </button>
      <PageHeader
        eyebrow="Feedback and decision detail"
        title="Evidence trace"
        description="Inspect the permitted record evidence, curated answers, and immutable decision provenance."
      />
      {detail.status === 'error' ? (
        <ErrorPanel
          title="Decision detail could not be loaded"
          message={detail.message}
          onRetry={onRetry}
        />
      ) : detail.status !== 'ready' ? (
        <LoadingPanel label="Loading decision detail" />
      ) : (
        <DecisionDetail detail={detail.data} />
      )}
    </>
  )
}
