export type Topic = {
  id: string
  label: string
  description: string
  keywords: string[]
  priority: number
}
export type Template = {
  id: string
  name: string
  revision: string
  payload: { name: string; topics: Topic[] }
}
export type Dataset = {
  id: string
  name: string
  snapshot: string
  status: string
  count: number
  validation: { summary: ValidationSummary }
  created_at: string
}
export type ValidationSummary = {
  total: number
  accepted: number
  invalid: number
  empty: number
  duplicateIds: number
  repeatedText: number
  missingDates: number
}
export type Validation = {
  summary: ValidationSummary
  issues: { row: number; message: string }[]
  privacyPreview: { row: number; redactedText: string }[]
  blocked: number
}
export type Preview = {
  uploadId: string
  columns: string[]
  sheets: string[]
  rows: Record<string, unknown>[]
  total: number
}
export type Connection = {
  id: string
  mode: 'api' | 'chatgpt'
  label: string
  planEnabled: boolean
}
export type Run = {
  elapsedSeconds: number
  errors: { record_id: string; status: string; error_code: string }[]
  id: string
  dataset_id: string
  template_id: string
  status: string
  target: number
  succeeded: number
  failed: number
  created_at: string
  completed_at: string | null
  snapshot: {
    engine: string
    mode: string
    model: string
    connectionId: string | null
    billingMode: string
    templateRevision: string
    protocolHash: string
    datasetSnapshot: string
    template: { name: string; topics: Topic[] }
  }
}
export type Classification = {
  sentimentMatches?: { positive: string[]; negative: string[] }
  redactions?: Record<string, number>
  inputStateSha256?: string
  topic: string
  sentiment: string | null
  actionable: boolean
  redactedText: string
  matches: { topic: string; phrases: string[]; priority: number }[]
  requestedModel: string
  resolvedModel: string
  inputTokens: number
  outputTokens: number
  latencyMs: number
  templateRevision: string
  reusedFromRun?: string
}
export type Evidence = {
  id: string
  position: number
  sourceId: string
  text: string
  occurredAt: string | null
  language: string | null
  groups: Record<string, string>
  rating: { value: number; min: number; max: number } | null
  result: Classification
}
export type Results = {
  readAt?: string
  facets?: Record<
    'topic' | 'sentiment' | 'language' | 'product' | 'group',
    { value: string | null; label: string; count: number }[]
  >
  filters?: Record<string, string | string[]>
  pageSize?: number
  returned?: number
  runUsage: { inputTokens: number; outputTokens: number; reusedRecords: number }
  loadedQuery?: string
  run: Run
  summary: {
    total: number
    processed: number
    reusedRecords: number
    dated: number
    topics: Record<string, number>
    sentiments: Record<string, number>
    days: { date: string; total: number; [key: string]: number | string }[]
    dailySeries?: {
      date: string
      total: number
      topics: Record<string, number>
    }[]
    inputTokens: number
    outputTokens: number
    ratingCount: number
    normalizedRatingMean: number | null
  }
  rows: Evidence[]
  filtered: number
  page: number
  groups: Record<string, string[]>
  projectionPending: number
}
export type Comparison = {
  shared: number
  leftProcessed: number
  rightProcessed: number
  agreement: number | null
  disagreements: {
    recordId: string
    text: string
    left: Classification
    right: Classification
  }[]
  disagreementCount: number
  label: string
}
export type TrendResult = {
  analysisId?: string
  protocolHash?: string
  implementation?: string
  method: string
  reason?: string
  candidates: {
    series_id: string
    status: string
    direction: string
    reasons: string[]
    delta_pp: number | null
    probability_of_direction?: number
    current?: {
      start: string
      end_exclusive: string
      accepted_count: number
      eligible_count: number
      rate: number | null
    }
    baseline?: {
      start: string
      end_exclusive: string
      accepted_count: number
      eligible_count: number
      rate: number | null
    }
    detector_version?: string
  }[]
}

let csrf = ''
export class WorkbenchError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'WorkbenchError'
    this.status = status
  }
}
export function setWorkbenchCsrf(value: string) {
  csrf = value
}
export async function workbench<T>(
  path: string,
  body?: unknown,
  method = body === undefined ? 'GET' : 'POST',
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1/workbench${path}`, {
    method,
    credentials: 'same-origin',
    signal,
    headers: { 'Content-Type': 'application/json', 'X-Workbench-CSRF': csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event('workbench-session-expired'))
    const error = (await response.json().catch(() => ({}))) as {
      error?: string
      detail?: string
    }
    throw new WorkbenchError(
      error.error ??
        error.detail ??
        `Request failed (${response.status}). Unlock the workspace or check the runtime.`,
      response.status,
    )
  }
  return response.json() as Promise<T>
}
