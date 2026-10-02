import { useEffect, useRef, useState } from 'react'
import {
  workbench as defaultClient,
  WorkbenchError,
  type Results,
  type Run,
  type Dataset,
  type Evidence,
  type TrendResult,
  type Comparison,
} from './workbench-api'
import {
  emptyResultFilters,
  facetFields,
  facetChoice,
  resultQuery,
  selectFacet,
  type ResultFilters,
  type FacetField,
} from './workbench-query'
import { InspectionProvider, Inspectable } from './inspection-components'
import { useInspection, type InspectionDetail } from './inspection-context'
import { WorkbenchTimeChart } from './workbench-time-chart'
import { useConfirmation } from './confirmation-context'
import { priceReference } from './workbench-pricing'
import { effortLabel } from './use-model-catalog'

type Client = typeof defaultClient
type Props = {
  runId: string
  runs: Run[]
  datasets: Dataset[]
  client: Client
  active: boolean
  busy: boolean
  onRunChange: (id: string) => void
  onUnavailable: () => void
  onClassify: () => void
  onRemaining: (run: Run) => void
}
const titles: Record<FacetField, string> = {
  topic: 'Topic',
  sentiment: 'Sentiment',
  language: 'Language',
  product: 'Product',
  group: 'Group',
}
const allLabels: Record<FacetField, string> = {
  topic: 'All topics',
  sentiment: 'All sentiments',
  language: 'All languages',
  product: 'All products',
  group: 'All groups',
}
function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : 'The local request could not complete.'
}

export function WorkbenchResults(props: Props) {
  const [filters, setFilters] = useState<ResultFilters>(emptyResultFilters)
  const [data, setData] = useState<Results | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  )
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [accessEpoch, setAccessEpoch] = useState(0)
  const [restricted, setRestricted] = useState(false)
  const focusEvidence = useRef(false)
  const unavailable = useRef(props.onUnavailable)
  useEffect(() => {
    unavailable.current = props.onUnavailable
  }, [props.onUnavailable])
  const query = resultQuery(filters)
  const cohort = resultQuery(filters, false)
  const advancedQuery = !!(
    filters.dateFrom ||
    filters.dateTo ||
    filters.missing.length
  )
  const { runId, client, active } = props
  useEffect(() => {
    if (!runId || !active) return
    const abort = new AbortController()
    let timer = 0
    const reload = async () => {
      try {
        const next = await client<Results>(
          `/runs/${runId}/results?${query}`,
          undefined,
          'GET',
          abort.signal,
        )
        if (abort.signal.aborted) return
        if (advancedQuery && !next.filters)
          throw new WorkbenchError(
            'Update the local runtime to apply date and missing-value filters safely.',
            400,
          )
        setData({ ...next, loadedQuery: query })
        setRestricted(false)
        setError('')
        setLoadState('ready')
        if (next.page !== filters.page)
          setFilters((current) => ({ ...current, page: next.page }))
      } catch (failure) {
        if (abort.signal.aborted) return
        if (
          failure instanceof WorkbenchError &&
          [401, 403, 404].includes(failure.status)
        ) {
          setData(null)
          setRestricted(true)
          setAccessEpoch((value) => value + 1)
          if (failure.status === 404) unavailable.current()
        }
        setError(message(failure))
        setLoadState('error')
      } finally {
        if (!abort.signal.aborted)
          timer = window.setTimeout(() => {
            void reload()
          }, 5000)
      }
    }
    void reload()
    return () => {
      abort.abort()
      window.clearTimeout(timer)
    }
  }, [runId, client, active, query, retry, filters.page, advancedQuery])
  const change = (next: ResultFilters, inspectEvidence = false) => {
    focusEvidence.current = inspectEvidence
    setFilters(next)
    setLoadState('loading')
    setError('')
  }
  const current =
    data?.run.id === runId && data.loadedQuery === query ? data : null
  const catalog = data?.run.id === runId ? data.facets : undefined
  const advanced = !!catalog && !!data?.filters
  useEffect(() => {
    if (!active || !current || !focusEvidence.current) return
    focusEvidence.current = false
    const heading = document.getElementById('workbench-evidence')
    heading?.focus()
    heading?.scrollIntoView?.({ block: 'start' })
  }, [active, current])
  return (
    <InspectionProvider
      scope={`${runId}:${cohort}:${accessEpoch}`}
      active={active && !restricted}
    >
      <label>
        Selected run
        <select
          value={runId}
          onChange={(event) => props.onRunChange(event.target.value)}
        >
          <option value="">Choose run</option>
          {props.runs.map((run) => (
            <option key={run.id} value={run.id}>
              {run.id.slice(0, 8)} · {run.snapshot.template.name} ·{' '}
              {run.snapshot.engine} · {run.status}
            </option>
          ))}
        </select>
      </label>
      {!runId ? (
        <section className="wb-panel">
          <h2>
            {props.runs.length
              ? 'Choose a run to inspect results'
              : 'No classification runs yet'}
          </h2>
          <p>
            Classify a dataset to explore saved results and prepared evidence.
          </p>
          <div className="wb-actions">
            <button onClick={props.onClassify}>Go to Classification</button>
          </div>
        </section>
      ) : (
        <>
          <section className="wb-panel" aria-label="Result filters">
            <h2>Explore classifications</h2>
            <p>
              Options and counts cover all successfully processed records in
              this run. Topics and sentiment are classification outputs;
              language, product and group are imported metadata.
            </p>
            <div className="wb-grid">
              {facetFields.map((field) => (
                <label key={field}>
                  {titles[field]}
                  <select
                    value={facetChoice(filters, field)}
                    disabled={!catalog || !catalog[field].length}
                    onChange={(event) =>
                      change(
                        selectFacet(
                          filters,
                          field,
                          event.target.value === ''
                            ? undefined
                            : (JSON.parse(event.target.value) as string | null),
                        ),
                      )
                    }
                  >
                    <option value="">{allLabels[field]}</option>
                    {(catalog?.[field] || []).map((option) => (
                      <option
                        key={JSON.stringify(option.value)}
                        value={JSON.stringify(option.value)}
                        disabled={option.value === null && !advanced}
                      >
                        {option.label} ({option.count.toLocaleString()})
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <label>
                Date from (UTC)
                <input
                  type="date"
                  disabled={!advanced}
                  value={filters.dateFrom}
                  onChange={(event) =>
                    change({
                      ...filters,
                      dateFrom: event.target.value,
                      page: 1,
                    })
                  }
                />
              </label>
              <label>
                Date through (UTC)
                <input
                  type="date"
                  disabled={!advanced}
                  value={filters.dateTo}
                  onChange={(event) =>
                    change({ ...filters, dateTo: event.target.value, page: 1 })
                  }
                />
              </label>
            </div>
            {data && !catalog && (
              <p>
                Filter options are unavailable from this runtime. Refresh or
                update the local runtime.
              </p>
            )}
            <div className="wb-actions" aria-label="Active filters">
              {facetFields
                .filter(
                  (field) => filters[field] || filters.missing.includes(field),
                )
                .map((field) => (
                  <button
                    key={field}
                    onClick={() =>
                      change(selectFacet(filters, field, undefined))
                    }
                  >
                    Clear {titles[field]}:{' '}
                    {filters.missing.includes(field)
                      ? 'Not supplied / unavailable'
                      : catalog?.[field].find(
                          (option) => option.value === filters[field],
                        )?.label || filters[field]}
                  </button>
                ))}
              {(filters.dateFrom || filters.dateTo) && (
                <button
                  onClick={() =>
                    change({ ...filters, dateFrom: '', dateTo: '', page: 1 })
                  }
                >
                  Clear date range
                </button>
              )}
              <button
                disabled={!cohort}
                onClick={() => change(emptyResultFilters())}
              >
                Clear all filters
              </button>
            </div>
            {(filters.dateFrom || filters.dateTo) && (
              <p>
                Dates are inclusive UTC review dates. Undated records are
                excluded from this date selection.
              </p>
            )}
          </section>
          {error && (
            <div className="wb-error" role="alert">
              <p>
                {current
                  ? `Refresh failed; showing the last successful snapshot. ${error}`
                  : error}
              </p>
              <button
                onClick={() => {
                  setLoadState('loading')
                  setError('')
                  setRetry((value) => value + 1)
                }}
              >
                Retry results
              </button>
            </div>
          )}
          {!current ? (
            <p role="status">
              {loadState === 'error'
                ? 'Results are unavailable. Review filters and retry the local request.'
                : 'Loading results…'}
            </p>
          ) : (
            <ResultsData
              key={`${cohort}:${current.run.succeeded}:${current.run.failed}:${props.runs.map((run) => `${run.id}:${run.succeeded}:${run.failed}`).join('|')}`}
              {...props}
              data={current}
              filters={filters}
              cohort={cohort}
              advanced={advanced}
              change={change}
            />
          )}
        </>
      )}
    </InspectionProvider>
  )
}

function ResultsData({
  data,
  filters,
  cohort,
  advanced,
  change,
  ...props
}: Props & {
  data: Results
  filters: ResultFilters
  cohort: string
  advanced: boolean
  change: (next: ResultFilters, inspectEvidence?: boolean) => void
}) {
  const { inspect } = useInspection()
  const confirm = useConfirmation()
  const [consent, setConsent] = useState(false)
  const [original, setOriginal] = useState(false)
  const [counterpart, setCounterpart] = useState('')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [trend, setTrend] = useState<TrendResult | null>(null)
  const [actionError, setActionError] = useState('')
  const [working, setWorking] = useState(false)
  const sequence = useRef(0)
  useEffect(
    () => () => {
      sequence.current++
    },
    [],
  )
  const action = async (operation: () => Promise<void>) => {
    setActionError('')
    setWorking(true)
    const ticket = ++sequence.current
    try {
      await operation()
    } catch (failure) {
      if (ticket === sequence.current) setActionError(message(failure))
    } finally {
      if (ticket === sequence.current) setWorking(false)
    }
  }
  const busy = working || props.busy
  const scope = cohort
    ? `Run ${data.run.id.slice(0, 8)} · filtered successful records`
    : `Run ${data.run.id.slice(0, 8)} · all successful records`
  const provenance: InspectionDetail['fields'] = [
    { label: 'Dataset snapshot', value: data.run.snapshot.datasetSnapshot },
    { label: 'Template revision', value: data.run.snapshot.templateRevision },
    {
      label: 'Method / model',
      value: `${data.run.snapshot.engine} / ${data.run.snapshot.model} / ${effortLabel(data.run.snapshot.reasoningEffort)} effort`,
    },
    { label: 'Protocol hash', value: data.run.snapshot.protocolHash },
    {
      label: 'Read snapshot (UTC)',
      value: data.readAt || 'Not recorded by this earlier runtime',
    },
  ]
  const describe = (
    title: string,
    description: string,
    fields: InspectionDetail['fields'] = [],
  ): InspectionDetail => ({
    title,
    scopeLabel: scope,
    description,
    fields: [...(fields || []), ...(provenance || [])],
  })
  const inspectRecord = (row: Evidence, trigger: HTMLElement) =>
    inspect(
      {
        ...describe(
          `Record ${row.position}`,
          'Prepared feedback and saved classification evidence. These outcomes are exploratory, not calibrated accuracy.',
          [
            { label: 'Source ID', value: row.sourceId },
            { label: 'Recorded date', value: row.occurredAt || 'Not supplied' },
            { label: 'Language', value: row.language || 'Not supplied' },
            { label: 'Product', value: row.groups.product || 'Not supplied' },
            { label: 'Group', value: row.groups.group || 'Not supplied' },
            {
              label: 'Rating / declared scale',
              value: row.rating
                ? `${row.rating.value} (${row.rating.min}–${row.rating.max})`
                : 'Not supplied',
            },
            {
              label: 'Topic / sentiment',
              value: `${row.result.topic} / ${row.result.sentiment || 'Unavailable'}`,
            },
            {
              label: 'Actionable outcome',
              value: String(row.result.actionable),
            },
            {
              label: 'Requested / resolved model',
              value: `${row.result.requestedModel} / ${row.result.resolvedModel} / ${effortLabel(row.result.reasoningEffort ?? data.run.snapshot.reasoningEffort)} effort`,
            },
            {
              label: 'Prepared input hash',
              value: row.result.inputStateSha256 || 'Not recorded',
            },
            {
              label: 'Detected redactions',
              value: row.result.redactions
                ? Object.entries(row.result.redactions)
                    .map(([kind, count]) => `${kind}: ${count}`)
                    .join(', ') || 'None'
                : 'Not recorded',
            },
          ],
        ),
        content: (
          <>
            <p>{row.result.redactedText}</p>
            <h3>Matched rules and competing topics</h3>
            {row.result.matches.length ? (
              row.result.matches.map((match) => (
                <p key={match.topic}>
                  {match.topic} · priority {match.priority}:{' '}
                  {match.phrases.join(', ')}
                </p>
              ))
            ) : (
              <p>No keyword explanation was recorded by this method.</p>
            )}
            <h3>Recorded sentiment matches</h3>
            {row.result.sentimentMatches ? (
              <>
                <p>
                  Positive:{' '}
                  {row.result.sentimentMatches.positive.join(', ') || 'None'}
                </p>
                <p>
                  Negative:{' '}
                  {row.result.sentimentMatches.negative.join(', ') || 'None'}
                </p>
              </>
            ) : (
              <p>Not recorded by this method.</p>
            )}
          </>
        ),
      },
      trigger,
    )
  const rate = priceReference(data.run.snapshot.model)
  const daily =
    data.summary.dailySeries ||
    data.summary.days.map(({ date, total, ...topics }) => ({
      date,
      total,
      topics: Object.fromEntries(
        Object.entries(topics).map(([topic, value]) => [topic, Number(value)]),
      ),
    }))
  const pageSize = data.pageSize || 50
  return (
    <>
      {actionError && (
        <div className="wb-error" role="alert">
          <p>{actionError}</p>
          <p>
            Review the operation’s inputs or connection, then explicitly retry
            its action.
          </p>
        </div>
      )}
      <section className="wb-panel">
        <h2>Processing and coverage</h2>
        <p>
          Run duration: {data.run.elapsedSeconds} seconds. Distributions and
          evidence cover the current filters; processing and token usage cover
          the whole run.
        </p>
        <div className="wb-metrics">
          <ResultMetric
            label="Run coverage"
            value={`${data.run.succeeded} / ${data.run.target}`}
            detail={describe(
              'Run processing coverage',
              'Successful decisions among selected run records; filtering does not change run-wide coverage.',
              [
                {
                  label: 'Succeeded / target',
                  value: `${data.run.succeeded} / ${data.run.target}`,
                },
                { label: 'Failed', value: data.run.failed },
                { label: 'Status', value: data.run.status },
              ],
            )}
          />
          <ResultMetric
            label="Filtered results"
            value={data.filtered.toLocaleString()}
            detail={describe(
              'Filtered successful records',
              'Count includes all matching successful records, independently of the displayed evidence page.',
              [
                { label: 'Matching records', value: data.filtered },
                { label: 'Displayed rows', value: data.rows.length },
              ],
            )}
          />
          <ResultMetric
            label="Dated results"
            value={`${data.summary.dated} / ${data.summary.processed}`}
            detail={describe(
              'Review-date coverage',
              'Only supplied review dates enter the time chart. Import time never replaces a missing date.',
              [
                {
                  label: 'Dated / processed',
                  value: `${data.summary.dated} / ${data.summary.processed}`,
                },
                {
                  label: 'Undated',
                  value: data.summary.processed - data.summary.dated,
                },
              ],
            )}
          />
          <ResultMetric
            label="Recorded tokens"
            value={`${data.runUsage.inputTokens.toLocaleString()} in / ${data.runUsage.outputTokens.toLocaleString()} out`}
            detail={describe(
              'Whole-run recorded usage',
              'New successful requests only; reused sample decisions are excluded. Interrupted attempts may consume provider usage that is not recorded here. Tokens do not represent remaining subscription allowance.',
              [
                { label: 'Billing mode', value: data.run.snapshot.billingMode },
                { label: 'Reused records', value: data.runUsage.reusedRecords },
              ],
            )}
          />
        </div>
        <p>
          {data.run.status} · {data.run.failed} failed ·{' '}
          {data.runUsage.reusedRecords} reused sample records ·{' '}
          {data.projectionPending} awaiting analytical projection.
        </p>
        {data.run.errors.length > 0 && (
          <details>
            <summary>
              Processing errors and interruptions ({data.run.errors.length}{' '}
              shown)
            </summary>
            {data.run.errors.map((error) => (
              <p key={error.record_id}>
                {error.record_id} · {error.status} · {error.error_code}. Review
                the import or reconnect before resuming.
              </p>
            ))}
          </details>
        )}
        {data.run.snapshot.billingMode === 'api' && rate && (
          <p>
            Estimated API cost for new successful records: $
            {rate
              .cost(data.runUsage.inputTokens, data.runUsage.outputTokens)
              .toFixed(4)}{' '}
            using rates reviewed {rate.reviewedAt}. This is not an invoice;
            failed attempts and billing adjustments may add usage.{' '}
            {data.run.snapshot.mode === 'sample' && data.run.succeeded > 0 && (
              <>
                Linear full-dataset estimate: $
                {(
                  (rate.cost(
                    data.runUsage.inputTokens,
                    data.runUsage.outputTokens,
                  ) *
                    (props.datasets.find(
                      (dataset) => dataset.id === data.run.dataset_id,
                    )?.count || data.run.target)) /
                  data.run.succeeded
                ).toFixed(2)}
                ; actual totals may differ.
              </>
            )}
          </p>
        )}
        {data.run.snapshot.mode === 'sample' &&
          data.run.status === 'completed' && (
            <>
              <label className="wb-check">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(event) => setConsent(event.target.checked)}
                />
                Approve processing the remaining dataset with the same
                configuration.
              </label>
              <div className="wb-actions">
                <button
                  className="button--primary"
                  disabled={busy || !consent}
                  onClick={() => props.onRemaining(data.run)}
                >
                  Run remaining dataset
                </button>
              </div>
            </>
          )}
      </section>
      <section className="wb-panel">
        <h2>Classification distributions</h2>
        {data.filtered === 0 ? (
          <p>
            {data.run.succeeded === 0
              ? 'No successfully processed records yet. Review the run state and errors; active runs refresh automatically.'
              : 'No successfully processed records match these filters. Clear or adjust filters to explore another cohort.'}
          </p>
        ) : (
          <div className="wb-grid">
            {(['topic', 'sentiment'] as const).map((field) => (
              <ResultDistribution
                key={field}
                title={field === 'topic' ? 'Topics' : 'Sentiment'}
                values={
                  field === 'topic'
                    ? data.summary.topics
                    : data.summary.sentiments
                }
                total={data.summary.processed}
                detail={(value, count) => ({
                  ...describe(
                    `${titles[field]}: ${value}`,
                    'Share within the current filtered successful records, not validated accuracy.',
                    [
                      {
                        label: 'Count / denominator',
                        value: `${count} / ${data.summary.processed}`,
                      },
                      {
                        label: 'Share',
                        value: data.summary.processed
                          ? `${((100 * count) / data.summary.processed).toFixed(1)}%`
                          : 'Unavailable',
                      },
                    ],
                  ),
                  action:
                    field === 'sentiment' &&
                    value === 'unavailable' &&
                    !advanced
                      ? undefined
                      : {
                          label: 'View matching records',
                          onClick: () =>
                            change(
                              selectFacet(
                                filters,
                                field,
                                field === 'sentiment' && value === 'unavailable'
                                  ? null
                                  : value,
                              ),
                              true,
                            ),
                        },
                })}
              />
            ))}
          </div>
        )}
        <h3>Observed over time</h3>
        {daily.length ? (
          <WorkbenchTimeChart
            dailySeries={daily}
            scopeLabel={scope}
            provenance={provenance}
            onDrillDown={
              advanced
                ? (dateFrom, dateTo) =>
                    change({ ...filters, dateFrom, dateTo, page: 1 }, true)
                : undefined
            }
          />
        ) : (
          <p>No dated records; time analysis is unavailable.</p>
        )}
        <DailyBreakdown
          rows={daily}
          scope={scope}
          onDrill={
            advanced
              ? (date) =>
                  change(
                    { ...filters, dateFrom: date, dateTo: date, page: 1 },
                    true,
                  )
              : undefined
          }
        />
        <p>
          Rating coverage: {data.summary.ratingCount}/{data.summary.processed}.
          Normalized average:{' '}
          {data.summary.normalizedRatingMean === null
            ? 'unavailable'
            : `${(100 * data.summary.normalizedRatingMean).toFixed(1)}% of declared scales`}
          .
        </p>
      </section>
      <section className="wb-panel">
        <h2 id="workbench-evidence" tabIndex={-1}>
          Record evidence
        </h2>
        {!data.rows.length ? (
          <p>No matching evidence on this page.</p>
        ) : (
          <div
            className="wb-table-wrap"
            role="region"
            aria-label="Classified record evidence table"
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>Source row</th>
                  <th>Prepared feedback</th>
                  <th>Topic</th>
                  <th>Sentiment</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.position}</td>
                    <td>{row.text.slice(0, 160)}</td>
                    <td>{row.result.topic}</td>
                    <td>{row.result.sentiment || 'Unavailable'}</td>
                    <td>
                      <button
                        onClick={(event) =>
                          inspectRecord(row, event.currentTarget)
                        }
                      >
                        Inspect row {row.position}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="wb-actions" aria-label="Evidence pagination">
          <button
            disabled={data.page <= 1}
            onClick={() => change({ ...filters, page: data.page - 1 })}
          >
            Previous
          </button>
          <span>
            Page {data.page} of{' '}
            {Math.max(1, Math.ceil(data.filtered / pageSize))} · {data.filtered}{' '}
            results
          </span>
          <button
            disabled={data.page * pageSize >= data.filtered}
            onClick={() => change({ ...filters, page: data.page + 1 })}
          >
            Next
          </button>
        </div>
      </section>
      <section className="wb-panel">
        <h2>Exploratory trend candidates</h2>
        <p>
          Latest 7 days compared with the previous 28. Unobserved dates have
          unknown coverage. These are not calibrated business alerts.
        </p>
        {filters.topic && (
          <p>
            Clear the topic filter to analyze topic rates against the full
            selected cohort.{' '}
            <button
              onClick={() => change(selectFacet(filters, 'topic', undefined))}
            >
              Clear topic filter
            </button>
          </p>
        )}
        <div className="wb-actions">
          {(['simple_rate_change', 'candidate_statistical'] as const).map(
            (method) => (
              <button
                key={method}
                disabled={busy || !!filters.topic || !data.summary.dated}
                onClick={() => {
                  void action(async () => {
                    setTrend(null)
                    const ticket = sequence.current
                    const next = await props.client<TrendResult>(
                      `/runs/${data.run.id}/trends?${cohort}&method=${method}`,
                    )
                    if (ticket === sequence.current) setTrend(next)
                  })
                }}
              >
                {method === 'simple_rate_change'
                  ? 'Simple rate change'
                  : 'Beta-Binomial candidate'}
              </button>
            ),
          )}
        </div>
        {trend &&
          (trend.reason ? (
            <p>{trend.reason.replaceAll('_', ' ')}</p>
          ) : (
            <div className="result-trend-list">
              {trend.candidates.map((candidate, index) => (
                <Inspectable
                  key={index}
                  className="result-inspect-row"
                  detail={describe(
                    `${candidate.series_id}: ${candidate.direction}`,
                    `Exploratory ${trend.method}. ${candidate.reasons.join(', ') || 'Support gates evaluated'}`,
                    [
                      { label: 'Status', value: candidate.status },
                      {
                        label: 'Current numerator / denominator',
                        value: candidate.current
                          ? `${candidate.current.accepted_count} / ${candidate.current.eligible_count}`
                          : 'Not recorded',
                      },
                      {
                        label: 'Baseline numerator / denominator',
                        value: candidate.baseline
                          ? `${candidate.baseline.accepted_count} / ${candidate.baseline.eligible_count}`
                          : 'Not recorded',
                      },
                      {
                        label: 'Current interval [start, end)',
                        value: candidate.current
                          ? `${candidate.current.start} – ${candidate.current.end_exclusive}`
                          : 'Not recorded',
                      },
                      {
                        label: 'Baseline interval [start, end)',
                        value: candidate.baseline
                          ? `${candidate.baseline.start} – ${candidate.baseline.end_exclusive}`
                          : 'Not recorded',
                      },
                      {
                        label: 'Implementation',
                        value:
                          trend.implementation ||
                          candidate.detector_version ||
                          'Earlier runtime',
                      },
                      {
                        label: 'Analysis ID',
                        value: trend.analysisId || 'Not recorded',
                      },
                      {
                        label: 'Change',
                        value:
                          candidate.delta_pp === null
                            ? 'Unavailable'
                            : `${candidate.delta_pp.toFixed(2)} percentage points`,
                      },
                      ...(candidate.probability_of_direction === undefined
                        ? []
                        : [
                            {
                              label:
                                'Posterior direction probability (not correctness; not multiple-test adjusted)',
                              value:
                                candidate.probability_of_direction.toFixed(4),
                            },
                          ]),
                    ],
                  )}
                >
                  {candidate.series_id} · {candidate.direction} ·{' '}
                  {candidate.status}
                </Inspectable>
              ))}
            </div>
          ))}
      </section>
      <section className="wb-panel">
        <h2>Compare and export</h2>
        <p>
          Comparisons cover whole-run shared successful records and ignore
          Explore filters. Agreement is not accuracy. Exports use the current
          filters and include all matching records across pages.
        </p>
        <label>
          Compare to run
          <select
            value={counterpart}
            onChange={(event) => {
              sequence.current++
              setWorking(false)
              setCounterpart(event.target.value)
              setComparison(null)
            }}
          >
            <option value="">Choose matching run</option>
            {props.runs
              .filter(
                (run) =>
                  run.id !== data.run.id &&
                  run.dataset_id === data.run.dataset_id &&
                  run.snapshot.datasetSnapshot ===
                    data.run.snapshot.datasetSnapshot &&
                  run.snapshot.templateRevision ===
                    data.run.snapshot.templateRevision &&
                  run.snapshot.protocolHash === data.run.snapshot.protocolHash,
              )
              .map((run) => (
                <option key={run.id} value={run.id}>
                  {run.id.slice(0, 8)} · {run.snapshot.model} ·{' '}
                  {effortLabel(run.snapshot.reasoningEffort)} effort ·{' '}
                  {run.succeeded}/{run.target}
                </option>
              ))}
          </select>
        </label>
        <div className="wb-actions">
          <button
            disabled={busy || !counterpart}
            onClick={() => {
              void action(async () => {
                setComparison(null)
                const ticket = sequence.current
                const next = await props.client<Comparison>('/compare', {
                  left: data.run.id,
                  right: counterpart,
                })
                if (ticket === sequence.current) setComparison(next)
              })
            }}
          >
            Compare shared records
          </button>
        </div>
        {comparison && (
          <>
            <Inspectable
              className="result-inspect-row"
              detail={{
                title: 'Whole-run shared-record agreement',
                scopeLabel: `Whole runs ${data.run.id.slice(0, 8)} ↔ ${counterpart.slice(0, 8)}`,
                description:
                  'Shared successful records with matching topic, sentiment and actionable outcomes. Explore filters are not applied. Agreement is not accuracy.',
                fields: [
                  {
                    label: 'Left run',
                    value: `${data.run.id} · ${data.run.snapshot.model} · ${effortLabel(data.run.snapshot.reasoningEffort)} effort`,
                  },
                  {
                    label: 'Right run',
                    value: `${counterpart} · ${props.runs.find((row) => row.id === counterpart)?.snapshot.model || ''} · ${effortLabel(props.runs.find((row) => row.id === counterpart)?.snapshot.reasoningEffort)} effort`,
                  },
                  {
                    label: 'Dataset snapshot',
                    value: data.run.snapshot.datasetSnapshot,
                  },
                  {
                    label: 'Template revision',
                    value: data.run.snapshot.templateRevision,
                  },
                  {
                    label: 'Protocol hash',
                    value: data.run.snapshot.protocolHash,
                  },
                  { label: 'Shared records', value: comparison.shared },
                  {
                    label: 'Left / right processed',
                    value: `${comparison.leftProcessed} / ${comparison.rightProcessed}`,
                  },
                  {
                    label: 'Disagreements',
                    value: comparison.disagreementCount,
                  },
                ],
              }}
            >
              {comparison.label}:{' '}
              {comparison.agreement === null
                ? 'Unavailable'
                : `${(100 * comparison.agreement).toFixed(1)}%`}{' '}
              across {comparison.shared} shared records
            </Inspectable>
            {comparison.disagreements.map((row) => (
              <details key={row.recordId}>
                <summary>
                  {row.left.topic} ↔ {row.right.topic}
                </summary>
                <p>{row.text}</p>
                <p>
                  Sentiment: {row.left.sentiment || 'Unavailable'} ↔{' '}
                  {row.right.sentiment || 'Unavailable'}; actionable:{' '}
                  {String(row.left.actionable)} ↔ {String(row.right.actionable)}
                </p>
              </details>
            ))}
          </>
        )}
        <label className="wb-check">
          <input
            type="checkbox"
            checked={original}
            onChange={(event) => setOriginal(event.target.checked)}
          />
          Include original text in this local export.
        </label>
        <div className="wb-actions">
          {['csv', 'json'].map((format) => (
            <button
              key={format}
              disabled={busy}
              onClick={() => {
                void action(async () => {
                  const ticket = sequence.current
                  if (
                    original &&
                    !(await confirm({
                      title: 'Export original text',
                      confirmLabel: 'Export original text',
                      message:
                        'Export original text, including any private content? The local download will contain source feedback rather than only prepared text.',
                    }))
                  )
                    return
                  if (ticket !== sequence.current) return
                  const file = await props.client<{
                    filename: string
                    content: string
                  }>(
                    `/runs/${data.run.id}/export?${cohort}&format=${format}&original=${original}`,
                  )
                  if (ticket !== sequence.current) return
                  const url = URL.createObjectURL(
                    new Blob([file.content], {
                      type: format === 'csv' ? 'text/csv' : 'application/json',
                    }),
                  )
                  const link = document.createElement('a')
                  link.href = url
                  link.download = file.filename
                  link.click()
                  window.setTimeout(() => URL.revokeObjectURL(url), 0)
                })
              }}
            >
              Export {format.toUpperCase()}
            </button>
          ))}
        </div>
      </section>
    </>
  )
}
function DailyBreakdown({
  rows,
  scope,
  onDrill,
}: {
  rows: { date: string; total: number; topics: Record<string, number> }[]
  scope: string
  onDrill?: (date: string) => void
}) {
  const [page, setPage] = useState(1)
  return (
    <details>
      <summary>Daily counts and topic rates</summary>
      <div
        className="wb-table-wrap"
        role="region"
        aria-label="Daily counts table"
        tabIndex={0}
      >
        <table>
          <thead>
            <tr>
              <th>Date (UTC)</th>
              <th>Records</th>
              <th>Topic shares within this cohort</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice((page - 1) * 50, page * 50).map((row) => (
              <tr key={row.date}>
                <td>
                  <Inspectable
                    className="inspection-value"
                    detail={{
                      title: row.date,
                      scopeLabel: scope,
                      description:
                        'Observed dated classifications only. Unobserved days have unknown coverage.',
                      fields: [
                        { label: 'Records', value: row.total },
                        ...Object.entries(row.topics).map(([topic, count]) => ({
                          label: topic,
                          value: `${count} / ${row.total}`,
                        })),
                      ],
                      action: onDrill
                        ? {
                            label: 'View matching records',
                            onClick: () => onDrill(row.date),
                          }
                        : undefined,
                    }}
                  >
                    {row.date}
                  </Inspectable>
                </td>
                <td>{row.total}</td>
                <td>
                  {Object.entries(row.topics)
                    .map(
                      ([topic, count]) =>
                        `${topic}: ${row.total ? ((100 * count) / row.total).toFixed(1) + '%' : 'Unavailable'} (${count}/${row.total})`,
                    )
                    .join(' · ')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="wb-actions">
        <button
          disabled={page === 1}
          onClick={() => setPage((value) => value - 1)}
        >
          Previous dates
        </button>
        <span>
          Daily page {page} of {Math.max(1, Math.ceil(rows.length / 50))}
        </span>
        <button
          disabled={page * 50 >= rows.length}
          onClick={() => setPage((value) => value + 1)}
        >
          Next dates
        </button>
      </div>
    </details>
  )
}

function ResultMetric({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail: InspectionDetail
}) {
  return (
    <div>
      <Inspectable className="metric-inspect" detail={detail}>
        <span>{label}</span>
        <strong>{value}</strong>
        <span className="sr-only">Inspect details</span>
      </Inspectable>
    </div>
  )
}
function ResultDistribution({
  title,
  values,
  total,
  detail,
}: {
  title: string
  values: Record<string, number>
  total: number
  detail: (value: string, count: number) => InspectionDetail
}) {
  return (
    <div>
      <h3>{title}</h3>
      {Object.entries(values)
        .sort((a, b) => b[1] - a[1])
        .map(([value, count]) => (
          <Inspectable
            key={value}
            className="wb-distribution result-inspect-row"
            detail={detail(value, count)}
          >
            <span>{value}</span>
            <meter
              aria-label={`${title}: ${value}`}
              min={0}
              max={Math.max(total, 1)}
              value={count}
            >
              {count}
            </meter>
            <span>
              {count}/{total} ·{' '}
              {total ? ((100 * count) / total).toFixed(1) : 'Unavailable'}%
            </span>
          </Inspectable>
        ))}
    </div>
  )
}
