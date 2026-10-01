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
import type { workbench } from './workbench-api'

export type FixtureState =
  | 'ready'
  | 'empty'
  | 'loading'
  | 'error'
  | 'locked'
  | 'disabled'
  | 'partial'
  | 'running'
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

// Injected only by tests and the development-only visual-review entry point.
// This never changes production authentication or invokes external providers.
export function visualWorkbench(
  state: FixtureState = 'ready',
): typeof workbench {
  const partial = state === 'partial' || state === 'running'
  const shownRun = {
    ...run,
    status: state === 'running' ? 'running' : partial ? 'paused' : 'completed',
    succeeded: partial ? 12 : 24,
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
    else if (path === '/datasets') result = state === 'empty' ? [] : [dataset]
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
      result = {
        run: shownRun,
        runUsage: { inputTokens: 0, outputTokens: 0, reusedRecords: 0 },
        summary: {
          total: 24,
          processed: partial ? 12 : 24,
          dated: partial ? 11 : 23,
          topics: partial
            ? { service: 8, quality: 3, unclassified: 1 }
            : { service: 16, quality: 6, unclassified: 2 },
          sentiments: partial
            ? { positive: 8, negative: 3, mixed: 1 }
            : { positive: 16, negative: 6, mixed: 2 },
          days: Array.from({ length: partial ? 11 : 23 }, (_, i) => ({
            date: `2026-09-${String(i + 1).padStart(2, '0')}`,
            total: 1,
            service: i < (partial ? 7 : 15) ? 1 : 0,
            quality: i >= (partial ? 7 : 15) && i < (partial ? 10 : 21) ? 1 : 0,
            unclassified: i >= (partial ? 10 : 21) ? 1 : 0,
          })),
          ratingCount: partial ? 10 : 20,
          normalizedRatingMean: 0.72,
          inputTokens: 0,
          outputTokens: 0,
          reusedRecords: 0,
        },
        rows: Array.from({ length: 6 }, (_, i) => ({
          id: `record-${i}`,
          position: i + 1,
          sourceId: `review-${i + 1}`,
          text: classification.redactedText,
          occurredAt: i ? '2026-09-30T10:00:00Z' : null,
          language: i % 2 ? 'en' : 'sv',
          groups: { product: 'Example product', group: 'Customer comments' },
          rating: { value: 4, min: 1, max: 5 },
          result: { ...classification, topic: i === 4 ? 'quality' : 'service' },
        })),
        page: 1,
        filtered: partial ? 12 : 24,
        groups: { product: ['Example product'], group: ['Customer comments'] },
        projectionPending: state === 'partial' ? 12 : 0,
      }
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
