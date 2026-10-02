import type { DashboardClient } from './dashboard-api'
import {
  demoMetadata,
  demoOverview,
  demoSignal,
  demoEvidence,
  demoDetail,
  demoTrends,
  demoEvaluation,
  liveMetadata,
  liveOverview,
  liveTrends,
  liveEvaluation,
} from './test-fixtures'
import type { Evidence, Results, Run, workbench } from './workbench-api'

export type FixtureState =
  | 'ready'
  | 'empty'
  | 'loading'
  | 'error'
  | 'locked'
  | 'disabled'
  | 'partial'
  | 'running'
  | 'dense'
  | 'results-error'
  | 'results-loading'
  | 'models-error'
  | 'models-empty'
  | 'session-error'
export const visualDashboard: DashboardClient = {
  metadata: async (context) =>
    context === 'live' ? liveMetadata : demoMetadata,
  overview: async (context) =>
    context === 'live' ? liveOverview : demoOverview,
  trends: async (context) => (context === 'live' ? liveTrends : demoTrends),
  evaluation: async (context) =>
    context === 'live' ? liveEvaluation : demoEvaluation,
  signal: async () => demoSignal,
  evidence: async (_context, _signal, _filters, page) => demoEvidence(page),
  detail: async () => demoDetail,
}

const revision = 'c'.repeat(64)
const topics = [
  {
    id: 'service',
    label: 'Service and support',
    description: 'Customer service, support and assistance.',
    keywords: ['support', 'service', 'kundtjänst'],
    priority: 0,
  },
  {
    id: 'quality',
    label: 'Product quality',
    description: 'Reliability and reported defects.',
    keywords: ['broken', 'quality', 'trasig'],
    priority: 1,
  },
]
const template = {
  id: 'template',
  name: 'General feedback',
  revision,
  payload: { name: 'General feedback', topics },
}
const dataset = {
  id: 'dataset',
  name: 'Demonstration reviews',
  status: 'ready',
  count: 24,
  snapshot: 'a'.repeat(64),
  created_at: '2026-09-30T10:00:00Z',
  validation: {
    summary: {
      total: 24,
      accepted: 24,
      invalid: 0,
      empty: 0,
      duplicateIds: 0,
      repeatedText: 0,
      missingDates: 1,
    },
  },
}
const classification = {
  schemaVersion: 'workbench-classification/1.0.0',
  topic: 'service',
  sentiment: 'positive',
  actionable: false,
  redactedText:
    'Support explained the compatibility issue clearly. Thank you for the patient help.',
  matches: [{ topic: 'service', phrases: ['support'], priority: 0 }],
  requestedModel: 'keywords-1.0.0',
  resolvedModel: 'keywords-1.0.0',
  inputTokens: 0,
  outputTokens: 0,
  latencyMs: 0,
  templateRevision: revision,
  inputStateSha256: 'b'.repeat(64),
  redactions: { email: 1 },
  calibrated: false,
}
const run = {
  id: 'run',
  dataset_id: 'dataset',
  template_id: 'template',
  status: 'completed',
  target: 24,
  succeeded: 24,
  failed: 0,
  elapsedSeconds: 4,
  errors: [],
  created_at: '2026-09-30T10:00:00Z',
  completed_at: '2026-09-30T10:00:04Z',
  snapshot: {
    engine: 'rules',
    mode: 'full',
    model: 'keywords-1.0.0',
    billingMode: 'none',
    connectionId: null,
    templateRevision: revision,
    template: template.payload,
    datasetSnapshot: dataset.snapshot,
    protocolHash: 'd'.repeat(64),
  },
}

function fixtureRows(count: number): Evidence[] {
  return Array.from({ length: count }, (_, index) => {
    const topic =
      index % 11 === 0
        ? 'unclassified'
        : index % 4 === 0
          ? 'quality'
          : 'service'
    const language =
      index % 5 === 0 ? null : index % 4 === 0 ? 'fi' : index % 2 ? 'en' : 'sv'
    const sentiment =
      !language || language === 'fi'
        ? null
        : topic === 'quality'
          ? 'negative'
          : topic === 'unclassified'
            ? 'neutral'
            : 'positive'
    const text =
      topic === 'quality'
        ? 'The product was broken and poor quality.'
        : topic === 'unclassified'
          ? 'We received the order.'
          : `Great support. ${classification.redactedText}`
    const product =
      index % 7 === 0 ? 'None' : index % 5 === 0 ? '' : 'Example product'
    const date = new Date(
      Date.UTC(
        count > 24 ? 2025 : 2026,
        count > 24 ? 0 : 8,
        1 + (index % (count > 24 ? 450 : 24)),
      ),
    )
    return {
      id: `record-${index}`,
      position: index + 1,
      sourceId: `review-${index + 1}`,
      text,
      occurredAt: count <= 24 && index === 0 ? null : date.toISOString(),
      language,
      groups: {
        ...(product ? { product } : {}),
        ...(index % 6 ? { group: 'Customer comments' } : {}),
      },
      rating: index % 5 ? { value: 4, min: 1, max: 5 } : null,
      result: {
        ...classification,
        topic,
        sentiment,
        redactedText: text,
        actionable: sentiment === 'negative',
        matches:
          topic === 'unclassified'
            ? []
            : [
                {
                  topic,
                  phrases: [topic === 'quality' ? 'broken' : 'support'],
                  priority: topic === 'quality' ? 1 : 0,
                },
              ],
        sentimentMatches: {
          positive: sentiment === 'positive' ? ['support'] : [],
          negative: sentiment === 'negative' ? ['broken', 'poor'] : [],
        },
      },
    }
  })
}
function fixtureResults(
  all: Evidence[],
  runValue: Run,
  search: URLSearchParams,
): Results {
  const missing = (search.get('missing') || '').split(',')
  const get = (row: Evidence, field: string): string | null =>
    field === 'topic' || field === 'sentiment'
      ? row.result[field]
      : field === 'language'
        ? row.language
        : row.groups[field] || null
  const fields = ['topic', 'sentiment', 'language', 'product', 'group'] as const
  const facets = Object.fromEntries(
    fields.map((field) => {
      const counts = new Map<string | null, number>()
      for (const row of all) {
        const value = get(row, field)
        counts.set(value, (counts.get(value) || 0) + 1)
      }
      return [
        field,
        Array.from(counts, ([value, count]) => ({
          value,
          count,
          label:
            value === null
              ? field === 'sentiment'
                ? 'Unavailable'
                : 'Not supplied'
              : field === 'topic'
                ? topics.find((topic) => topic.id === value)?.label || value
                : value,
        })),
      ]
    }),
  ) as NonNullable<Results['facets']>
  const rows = all.filter(
    (row) =>
      fields.every((field) =>
        missing.includes(field)
          ? get(row, field) === null
          : !search.get(field) || get(row, field) === search.get(field),
      ) &&
      (!search.get('dateFrom') ||
        (!!row.occurredAt &&
          row.occurredAt.slice(0, 10) >= search.get('dateFrom')!)) &&
      (!search.get('dateTo') ||
        (!!row.occurredAt &&
          row.occurredAt.slice(0, 10) <= search.get('dateTo')!)),
  )
  const countValues = (field: 'topic' | 'sentiment') =>
    Object.fromEntries(
      Array.from(
        new Set(rows.map((row) => row.result[field] || 'unavailable')),
        (value) => [
          value,
          rows.filter((row) => (row.result[field] || 'unavailable') === value)
            .length,
        ],
      ),
    )
  const days = new Map<
    string,
    { date: string; total: number; topics: Record<string, number> }
  >()
  for (const row of rows)
    if (row.occurredAt) {
      const date = row.occurredAt.slice(0, 10)
      const day = days.get(date) || { date, total: 0, topics: {} }
      day.total++
      day.topics[row.result.topic] = (day.topics[row.result.topic] || 0) + 1
      days.set(date, day)
    }
  const dailySeries = Array.from(days.values()).sort((a, b) =>
    a.date.localeCompare(b.date),
  )
  const page = Math.max(
    1,
    Math.min(Number(search.get('page') || 1), Math.ceil(rows.length / 50) || 1),
  )
  return {
    run: runValue,
    readAt: '2026-10-01T10:00:00Z',
    facets,
    filters: Object.fromEntries([
      ...fields.map((field) => [field, search.get(field) || '']),
      ['missing', missing.filter(Boolean)],
      ['dateFrom', search.get('dateFrom') || ''],
      ['dateTo', search.get('dateTo') || ''],
    ]),
    pageSize: 50,
    returned: Math.min(50, Math.max(0, rows.length - (page - 1) * 50)),
    runUsage: { inputTokens: 0, outputTokens: 0, reusedRecords: 0 },
    summary: {
      total: runValue.target,
      processed: rows.length,
      dated: rows.filter((row) => row.occurredAt).length,
      topics: countValues('topic'),
      sentiments: countValues('sentiment'),
      dailySeries,
      days: dailySeries.map((day) => ({
        date: day.date,
        total: day.total,
        ...day.topics,
      })),
      ratingCount: rows.filter((row) => row.rating).length,
      normalizedRatingMean: rows.some((row) => row.rating) ? 0.75 : null,
      inputTokens: 0,
      outputTokens: 0,
      reusedRecords: 0,
    },
    rows: rows.slice((page - 1) * 50, page * 50),
    page,
    filtered: rows.length,
    groups: {
      product: ['Example product', 'None'],
      group: ['Customer comments'],
    },
    projectionPending: 0,
  }
}

// Injected only by tests and the development-only visual-review entry point.
// This never changes production authentication or invokes external providers.
export function visualWorkbench(
  state: FixtureState = 'ready',
): typeof workbench {
  const recordCount = state === 'dense' ? 10000 : 24
  const allRows = fixtureRows(recordCount)
  const partial = state === 'partial' || state === 'running'
  const shownRun = {
    ...run,
    target: recordCount,
    status: state === 'running' ? 'running' : partial ? 'paused' : 'completed',
    succeeded: partial ? 12 : recordCount,
    errors:
      state === 'partial'
        ? [
            {
              record_id: 'record-13',
              status: 'interrupted',
              error_code: 'subscription_sharing_usage_limit_exceeded',
            },
          ]
        : [],
  }
  return async <T>(path: string, body?: unknown): Promise<T> => {
    if (state === 'session-error' && path === '/session')
      throw new Error('Fixture: local workspace connection failed.')
    if (state === 'results-error' && path.includes('/results'))
      throw new Error('Fixture: results could not be loaded.')
    if (state === 'results-loading' && path.includes('/results'))
      return new Promise<T>(() => {})
    if (state === 'models-error' && path.includes('/models'))
      throw new Error('Fixture: model catalog could not be loaded.')
    if (state === 'models-empty' && path.includes('/models')) return [] as T
    if (state === 'loading' && path === '/session')
      return new Promise<T>(() => {})
    if (state === 'error' && path !== '/session')
      throw new Error(
        'Fixture: data could not be loaded. Retry the local operation.',
      )
    let result: unknown
    if (path === '/session')
      result = {
        enabled: state !== 'disabled',
        authenticated: state !== 'locked',
        csrf: 'visual-fixture-only',
      }
    else if (path === '/datasets')
      result = state === 'empty' ? [] : [{ ...dataset, count: recordCount }]
    else if (path === '/templates') result = [template]
    else if (path === '/connections')
      result = [
        {
          id: 'connection',
          mode: 'chatgpt',
          label: 'Demonstration account',
          planEnabled: true,
        },
      ]
    else if (path === '/runs')
      result = body ? run : state === 'empty' ? [] : [shownRun]
    else if (path === '/runs/preview')
      result = {
        selected: 24,
        blocked: 0,
        reused: 0,
        prepared: [{ row: 1, redactedText: classification.redactedText }],
      }
    else if (path.startsWith('/runs/run/results'))
      result = fixtureResults(
        partial ? allRows.slice(0, 12) : allRows,
        shownRun,
        new URLSearchParams(path.split('?')[1] || ''),
      )
    else if (path === '/imports/preview')
      result = {
        uploadId: 'preview',
        columns: ['text', 'date', 'language', 'rating'],
        sheets: [],
        rows: [
          {
            text: classification.redactedText,
            date: null,
            language: 'en',
            rating: 4,
          },
        ],
        total: 24,
      }
    else if (path === '/imports/validate')
      result = {
        summary: {
          total: 24,
          accepted: 23,
          invalid: 1,
          empty: 0,
          duplicateIds: 1,
          repeatedText: 2,
          missingDates: 1,
        },
        issues: [
          {
            row: 7,
            message:
              'Duplicate source ID; repair the mapping or exclude this row.',
          },
        ],
        privacyPreview: [{ row: 1, redactedText: classification.redactedText }],
        blocked: 0,
      }
    else if (path === '/imports/commit' || path === '/datasets/demo')
      result = dataset
    else if (path.startsWith('/runs/run/trends'))
      result = {
        method: 'simple_rate_change',
        candidates: [
          {
            series_id: 'service',
            status: 'insufficient_coverage',
            direction: 'flat',
            reasons: ['missing_days'],
            delta_pp: null,
          },
        ],
      }
    else if (path === '/compare')
      result = {
        shared: 24,
        leftProcessed: 24,
        rightProcessed: 24,
        agreement: 0.92,
        disagreements: [],
        disagreementCount: 2,
        label: 'Classification agreement, not accuracy',
      }
    else if (path.includes('/models'))
      result = [
        { slug: 'demonstration-model', displayName: 'Demonstration model' },
      ]
    else if (path.endsWith('/cancel') || path.endsWith('/resume')) result = run
    else if (path.includes('/export'))
      result = { filename: 'demonstration.json', content: '{"fixture":true}' }
    else if (path.startsWith('/datasets/')) result = { status: 'deleting' }
    else throw new Error('No visual fixture for ' + path)
    return structuredClone(result) as T
  }
}
