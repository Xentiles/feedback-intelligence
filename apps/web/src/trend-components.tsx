import {
  ErrorPanel,
  LoadingPanel,
  StatePanel,
  StatusBadge,
} from './dashboard-components'
import { formatCount, formatDate, formatRate } from './dashboard-format'
import type {
  TrendEvaluationResult,
  TrendGateReason,
  TrendOverviewResponse,
  TrendSeries,
  TrendWindow,
} from './dashboard-types'

export type TrendAsyncState =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; data: TrendOverviewResponse }
  | { status: 'error'; message: string }

const oneDecimal = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 1,
})

const twoDecimals = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
})

const gateLabels: Record<TrendGateReason, string> = {
  current_denominator_met: 'Current denominator met',
  baseline_denominator_met: 'Baseline denominator met',
  current_numerator_met: 'Current numerator met',
  absolute_delta_met: 'Absolute change met',
  relative_change_met: 'Relative change met',
  probability_direction_met: 'Posterior probability met',
  current_denominator_below_minimum: 'Current denominator below minimum',
  baseline_denominator_below_minimum: 'Baseline denominator below minimum',
  current_numerator_below_minimum: 'Current numerator below minimum',
  absolute_delta_below_minimum: 'Absolute change below minimum',
  relative_change_below_minimum: 'Relative change below minimum',
  probability_direction_below_minimum: 'Posterior probability below minimum',
  baseline_rate_zero: 'Baseline rate is zero',
}

function sentenceCase(value: string) {
  const words = value.replaceAll('_', ' ')
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`
}

function signed(value: number, suffix: string) {
  return `${value > 0 ? '+' : ''}${oneDecimal.format(value)}${suffix}`
}

function windowMeasure(window: TrendWindow) {
  return (
    <div className="trend-window">
      <strong>
        {formatCount(window.numerator)} / {formatCount(window.denominator)}
      </strong>
      <span>{formatRate(window.rate)}</span>
      <small>
        {formatDate(window.range.from)}–{formatDate(window.range.toExclusive)}
      </small>
    </div>
  )
}

function resultTone(state: TrendEvaluationResult['state']) {
  if (state === 'emerging_signal') return 'warning' as const
  if (state === 'insufficient_coverage') return 'info' as const
  return 'success' as const
}

function TrendSummary({ response }: { response: TrendOverviewResponse }) {
  const summary = response.summary
  if (!summary) return null

  const metrics = [
    { label: 'Recall', value: `${oneDecimal.format(summary.recall * 100)}%` },
    {
      label: 'Precision',
      value: `${oneDecimal.format(summary.precision * 100)}%`,
    },
    {
      label: 'Median detection delay',
      value: `${oneDecimal.format(summary.medianDetectionDelayDays)} days`,
    },
    {
      label: 'False alert episodes',
      value: `${twoDecimals.format(summary.falseAlertEpisodesPer100SeriesDays)} per 100 evaluable series-days`,
    },
  ]

  return (
    <dl className="trend-summary" aria-label="Detector evaluation summary">
      {metrics.map((metric) => (
        <div key={metric.label}>
          <dt>{metric.label}</dt>
          <dd>{metric.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function EvaluationTable({ response }: { response: TrendOverviewResponse }) {
  const series = new Map(
    response.series.map((item) => [item.seriesId, item] as const),
  )

  return (
    <div className="table-region">
      <table>
        <caption className="sr-only">
          Detector results with raw current and baseline counts
        </caption>
        <thead>
          <tr>
            <th scope="col">Signal</th>
            <th scope="col">Direction</th>
            <th scope="col">Status</th>
            <th scope="col">Current</th>
            <th scope="col">Baseline</th>
            <th scope="col">Change</th>
            <th scope="col">Support gates</th>
          </tr>
        </thead>
        <tbody>
          {response.results.map((result) => {
            const descriptor = series.get(result.seriesId)
            return (
              <tr key={result.evaluationId}>
                <th scope="row">
                  {descriptor?.signalLabel ?? result.seriesId}
                  {descriptor?.product ? (
                    <small>{descriptor.product}</small>
                  ) : null}
                </th>
                <td>{sentenceCase(descriptor?.direction ?? 'unknown')}</td>
                <td>
                  <StatusBadge tone={resultTone(result.state)}>
                    {sentenceCase(result.state)}
                  </StatusBadge>
                </td>
                <td>{windowMeasure(result.current)}</td>
                <td>{windowMeasure(result.baseline)}</td>
                <td>
                  <div className="trend-change">
                    <strong>{signed(result.deltaPoints, ' pp')}</strong>
                    {result.relativeChangePercent !== null ? (
                      <span>
                        {signed(result.relativeChangePercent, '%')} relative
                      </span>
                    ) : null}
                    {result.rateRatio !== null ? (
                      <small>
                        {twoDecimals.format(result.rateRatio)}× rate
                      </small>
                    ) : null}
                    {result.probabilityOfDirection !== null ? (
                      <small>
                        {twoDecimals.format(
                          result.probabilityOfDirection * 100,
                        )}
                        %{' posterior probability'}
                      </small>
                    ) : null}
                  </div>
                </td>
                <td>
                  <ul className="gate-list">
                    {result.gateReasons.map((reason) => (
                      <li key={reason}>{gateLabels[reason]}</li>
                    ))}
                  </ul>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function IncidentTable({ response }: { response: TrendOverviewResponse }) {
  const series = new Map<string, TrendSeries>(
    response.series.map((item) => [item.seriesId, item]),
  )

  return (
    <div className="trend-incidents">
      <div className="panel__subheader">
        <div>
          <p className="eyebrow">Ground truth</p>
          <h3>Planted incidents</h3>
        </div>
        <span>
          {formatCount(response.incidents.length)} of{' '}
          {formatCount(response.summary?.plantedIncidentCount ?? 0)} listed
        </span>
      </div>
      <div className="table-region">
        <table>
          <caption className="sr-only">
            Every planted synthetic incident and its detector outcome
          </caption>
          <thead>
            <tr>
              <th scope="col">Incident</th>
              <th scope="col">Series</th>
              <th scope="col">Planted</th>
              <th scope="col">Detector outcome</th>
              <th scope="col">Delay</th>
            </tr>
          </thead>
          <tbody>
            {response.incidents.map((incident) => (
              <tr key={incident.incidentId}>
                <th scope="row">{sentenceCase(incident.outcome)}</th>
                <td>
                  {series.get(incident.seriesId)?.signalLabel ??
                    incident.seriesId}
                </td>
                <td>{formatDate(incident.plantedAt)}</td>
                <td>
                  <StatusBadge tone={incident.detected ? 'success' : 'danger'}>
                    {incident.detected ? 'Detected' : 'Missed'}
                  </StatusBadge>
                </td>
                <td>
                  {incident.detectionDelayDays === null
                    ? 'Not detected'
                    : `${formatCount(incident.detectionDelayDays)} days`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AvailableTrendEvaluation({
  response,
}: {
  response: TrendOverviewResponse
}) {
  if (!response.summary || !response.source) {
    return (
      <StatePanel
        title="Trend evaluation is incomplete"
        tone="warning"
        description="The detector response did not include its synthetic source and measured evaluation summary."
      />
    )
  }

  return (
    <section className="panel trend-evaluation" aria-labelledby="trend-title">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Detector backtest</p>
          <h2 id="trend-title">Synthetic detector evaluation</h2>
          <p>
            A detector-only backtest against planted synthetic incidents. It is
            separate from the descriptive dashboard and evidence journey.
          </p>
        </div>
        <StatusBadge tone="illustrative">Synthetic detector only</StatusBadge>
      </div>

      <div className="trend-method" aria-label="Detector method">
        <div>
          <span>Window method</span>
          <strong>
            {response.method.currentWindowDays}-day current window vs previous{' '}
            {response.method.baselineWindowDays}-day baseline
          </strong>
        </div>
        <div>
          <span>Detector label</span>
          <strong>
            {response.method.id === 'candidate_statistical'
              ? 'Beta-Binomial candidate'
              : 'Emerging signal'}
          </strong>
        </div>
        <div>
          <span>Minimum support</span>
          <strong>
            {formatCount(response.method.minimumCurrentNumerator)} current
            numerator · {formatCount(response.method.minimumCurrentDenominator)}
            {' current / '}
            {formatCount(response.method.minimumBaselineDenominator)} baseline
            denominator
          </strong>
        </div>
        {response.method.minimumProbabilityOfDirection !== null ? (
          <div>
            <span>Posterior gate</span>
            <strong>
              {oneDecimal.format(
                response.method.minimumProbabilityOfDirection * 100,
              )}
              % probability in the expected direction
            </strong>
          </div>
        ) : null}
      </div>

      <TrendSummary response={response} />

      <div className="trend-table-heading">
        <div>
          <p className="eyebrow">Alert episodes</p>
          <h3>First evaluation in each episode</h3>
        </div>
        <p>
          Raw numerator / eligible denominator and rate are shown for every
          current and baseline window.
        </p>
      </div>
      <EvaluationTable response={response} />
      <IncidentTable response={response} />
    </section>
  )
}

export function TrendEvaluationRegion({
  trends,
  onRetry,
}: {
  trends: TrendAsyncState
  onRetry: () => void
}) {
  if (trends.status === 'error') {
    return (
      <ErrorPanel
        title="Trend evaluation could not be loaded"
        message={trends.message}
        onRetry={onRetry}
      />
    )
  }

  if (trends.status !== 'ready') {
    return <LoadingPanel label="Loading trend evaluation" />
  }

  if (trends.data.availability.state === 'unavailable') {
    return (
      <StatePanel
        title="Trend detection unavailable — awaiting calibration"
        tone="warning"
        description="No detector evaluation is available in the live context. Counts and rates remain withheld until the calibration policy is active."
      />
    )
  }

  return <AvailableTrendEvaluation response={trends.data} />
}
