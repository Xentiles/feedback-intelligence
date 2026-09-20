import {
  ErrorPanel,
  LoadingPanel,
  StatePanel,
  StatusBadge,
} from './dashboard-components'
import { formatCount } from './dashboard-format'
import type { EvaluationComparisonResponse } from './dashboard-types'

export type EvaluationAsyncState =
  | { status: 'idle' | 'loading' }
  | { status: 'ready'; data: EvaluationComparisonResponse }
  | { status: 'error'; message: string }

function formatScore(value: number | null) {
  return value === null ? 'Pending' : `${(value * 100).toFixed(1)}%`
}

function formatUsd(value: number) {
  if (value === 0) return '$0.00'
  return `$${value.toFixed(value < 0.1 ? 4 : 2)}`
}

export function EvaluationComparisonRegion({
  evaluation,
  onRetry,
}: {
  evaluation: EvaluationAsyncState
  onRetry: () => void
}) {
  if (evaluation.status === 'error') {
    return (
      <ErrorPanel
        title="Evaluation comparison could not be loaded"
        message={evaluation.message}
        onRetry={onRetry}
      />
    )
  }

  if (evaluation.status !== 'ready') {
    return <LoadingPanel label="Loading experimental AI-reference comparison" />
  }

  const report = evaluation.data
  if (report.availability.state === 'unavailable') {
    return (
      <StatePanel
        title="Evaluation unavailable — awaiting human labels"
        tone="warning"
        description="Live quality reporting will remain unavailable until the human-reviewed reference set is complete."
      />
    )
  }

  if (
    !report.reference ||
    !report.semif ||
    !report.semifPrimaryTopic ||
    !report.semifCost ||
    !report.rules ||
    !report.rulePrimaryTopic ||
    !report.llm ||
    !report.llmCost ||
    !report.llmPrimaryTopic
  )
    return null

  const placeholder = report.status === 'placeholder_pending_run'
  return (
    <section
      className="panel evaluation-comparison"
      aria-label="Experimental AI-reference comparison"
    >
      <div className="panel__header">
        <div>
          <p className="eyebrow">Experimental evaluation</p>
          <h2>Experimental AI-reference comparison</h2>
          <p>
            A local SemIf open-model run and a deterministic rule baseline are
            compared with an AI-reviewed Sol medium reference across{' '}
            {formatCount(report.recordCount)} records. This is{' '}
            <strong>not human gold</strong> and must not be read as calibrated
            production quality. A separate GPT-5.4 Mini cost experiment closed
            after 192 successful records.
          </p>
        </div>
        <StatusBadge tone={placeholder ? 'warning' : 'illustrative'}>
          {placeholder
            ? 'Placeholder · run pending'
            : 'AI reference · not human gold'}
        </StatusBadge>
      </div>

      <dl className="evaluation-reference">
        <div>
          <dt>Evaluation reference</dt>
          <dd>
            {report.reference.model} · {report.reference.reasoning}
          </dd>
        </div>
        <div>
          <dt>Reference type</dt>
          <dd>AI-reviewed · not human gold</dd>
        </div>
      </dl>

      <div className="table-region model-comparison-region">
        <table className="model-comparison-table">
          <caption>Tested models and methods</caption>
          <thead>
            <tr>
              <th scope="col">Measure</th>
              <th scope="col">
                <span>Local open model</span>
                <strong>SemIf · Qwen3.5-4B</strong>
              </th>
              <th scope="col">
                <span>General-purpose LLM</span>
                <strong>GPT-5.4 Mini</strong>
              </th>
              <th scope="col">
                <span>Deterministic method</span>
                <strong>Rules baseline</strong>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Version</th>
              <td>{report.semif.resolvedModel}</td>
              <td>{report.llm.resolvedModel}</td>
              <td>{report.rules.resolvedModel}</td>
            </tr>
            <tr>
              <th scope="row">Run status</th>
              <td>Complete</td>
              <td>Closed partial</td>
              <td>Complete</td>
            </tr>
            <tr>
              <th scope="row">Successful records</th>
              <td>
                {formatCount(report.successCount)} /{' '}
                {formatCount(report.recordCount)}
              </td>
              <td>
                {formatCount(report.llmCost.successfulRecords ?? 0)} /{' '}
                {formatCount(report.llmCost.targetRecords ?? 0)}
              </td>
              <td>
                {formatCount(report.successCount)} /{' '}
                {formatCount(report.recordCount)}
              </td>
            </tr>
            <tr>
              <th scope="row">Recorded errors</th>
              <td>{formatCount(report.errorCount)}</td>
              <td>0</td>
              <td>{formatCount(report.errorCount)}</td>
            </tr>
            <tr>
              <th scope="row">Topic accuracy</th>
              <td>{formatScore(report.semifPrimaryTopic.accuracy)}</td>
              <td>{formatScore(report.llmPrimaryTopic.accuracy)}</td>
              <td>{formatScore(report.rulePrimaryTopic.accuracy)}</td>
            </tr>
            <tr>
              <th scope="row">Topic macro-F1</th>
              <td>{formatScore(report.semifPrimaryTopic.macroF1)}</td>
              <td>{formatScore(report.llmPrimaryTopic.macroF1)}</td>
              <td>{formatScore(report.rulePrimaryTopic.macroF1)}</td>
            </tr>
            <tr>
              <th scope="row">Measured tokens</th>
              <td>
                {formatCount(report.semifCost.tokens)} tokens
                <small>Local inference input</small>
              </td>
              <td>
                {formatCount(report.llmCost.tokens)} tokens
                <small>Experiment total</small>
              </td>
              <td>
                0 tokens
                <small>Local execution</small>
              </td>
            </tr>
            <tr>
              <th scope="row">Observed provider cost</th>
              <td>
                {formatUsd(report.semifCost.costUsd)}
                <small>No API charge · local execution</small>
              </td>
              <td>
                {formatUsd(report.llmCost.costUsd)}
                <small>192-record experiment</small>
              </td>
              <td>
                $0.00
                <small>No external provider</small>
              </td>
            </tr>
            <tr>
              <th scope="row">Estimated 480-record cost</th>
              <td>
                {formatUsd(report.semifCost.estimatedTargetCostUsd ?? 0)}
                <small>No API charge · hardware excluded</small>
              </td>
              <td>
                {report.llmCost.estimatedTargetCostUsd === null
                  ? 'Not estimated'
                  : formatUsd(report.llmCost.estimatedTargetCostUsd)}
                <small>Linear extrapolation</small>
              </td>
              <td>
                $0.00
                <small>No external provider</small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p className="evaluation-caveat">
        Rules nearly saturate this template-derived sample. That exposes limited
        linguistic variety in the synthetic corpus and strengthens the case for
        the human-reviewed challenge set; it is not evidence of real-world
        generalisation. The LLM estimate linearly extrapolates the
        owner-reported $0.39 spend for 192 successful records to approximately
        $0.98 for 480. SemIf ran locally through MLX, so its $0 figure means no
        model-provider API charge; it excludes hardware and electricity. LLM
        quality values use only the 192 completed records and are not directly
        equivalent to the complete 480-record SemIf and rule results.
      </p>

      <div className="table-region">
        <table>
          <caption>Primary-topic results by language</caption>
          <thead>
            <tr>
              <th scope="col" rowSpan={2}>
                Language
              </th>
              <th scope="colgroup" colSpan={3}>
                SemIf · Qwen3.5-4B
              </th>
              <th scope="colgroup" colSpan={3}>
                GPT-5.4 Mini
              </th>
              <th scope="colgroup" colSpan={3}>
                Rules baseline
              </th>
            </tr>
            <tr>
              <th scope="col">Evaluated</th>
              <th scope="col">F1</th>
              <th scope="col">Accuracy</th>
              <th scope="col">Evaluated</th>
              <th scope="col">F1</th>
              <th scope="col">Accuracy</th>
              <th scope="col">Evaluated</th>
              <th scope="col">F1</th>
              <th scope="col">Accuracy</th>
            </tr>
          </thead>
          <tbody>
            {report.semifLanguageSlices.map((slice) => {
              const ruleSlice = report.ruleLanguageSlices.find(
                (candidate) => candidate.language === slice.language,
              )
              const llmSlice = report.llmLanguageSlices.find(
                (candidate) => candidate.language === slice.language,
              )
              return (
                <tr key={slice.language}>
                  <th scope="row">{slice.language}</th>
                  <td>{formatCount(slice.successCount)}</td>
                  <td>{formatScore(slice.primaryTopic.macroF1)}</td>
                  <td>{formatScore(slice.primaryTopic.accuracy)}</td>
                  <td>
                    {llmSlice
                      ? formatCount(llmSlice.successCount)
                      : 'Not evaluated'}
                  </td>
                  <td>{formatScore(llmSlice?.primaryTopic.macroF1 ?? null)}</td>
                  <td>
                    {formatScore(llmSlice?.primaryTopic.accuracy ?? null)}
                  </td>
                  <td>
                    {ruleSlice
                      ? formatCount(ruleSlice.successCount)
                      : 'Not evaluated'}
                  </td>
                  <td>
                    {formatScore(ruleSlice?.primaryTopic.macroF1 ?? null)}
                  </td>
                  <td>
                    {formatScore(ruleSlice?.primaryTopic.accuracy ?? null)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
