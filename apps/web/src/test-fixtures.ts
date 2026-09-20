import type {
  DashboardFilters,
  EvidenceDetailResponse,
  EvidencePageResponse,
  EvaluationComparisonResponse,
  MetadataResponse,
  OverviewResponse,
  SignalResponse,
  SourceIdentity,
  TrendOverviewResponse,
} from './dashboard-types'

export const demoSource: SourceIdentity = {
  key: 'synthetic/feedback-decision-ai-reference/1.0.0',
  providerId: 'synthetic',
  datasetName: 'feedback-decision-ai-reference',
  datasetVersion: '1.0.0+sol-medium',
  displayName: 'Sol-medium reference feedback',
  synthetic: true,
}

export const semifDemoSource: SourceIdentity = {
  key: 'synthetic/feedback-decision-semif/1.0.0',
  providerId: 'synthetic',
  datasetName: 'feedback-decision-semif',
  datasetVersion: '1.0.0+qwen3.5-4b-mlx-q4',
  displayName: 'SemIf-reviewed synthetic feedback',
  synthetic: true,
}

export const rulesDemoSource: SourceIdentity = {
  key: 'synthetic/feedback-decision-rules/1.0.0',
  providerId: 'synthetic',
  datasetName: 'feedback-decision-rules',
  datasetVersion: '1.0.0',
  displayName: 'Rules-baseline synthetic feedback',
  synthetic: true,
}

export const liveSource: SourceIdentity = {
  key: 'synthetic/connected-demo/v1',
  providerId: 'synthetic',
  datasetName: 'connected-demo',
  datasetVersion: 'v1',
  displayName: 'Connected synthetic demo',
  synthetic: true,
}

export const demoFilters: DashboardFilters = {
  sourceKey: demoSource.key,
  from: '2026-05-01T00:00:00Z',
  toExclusive: '2026-06-01T00:00:00Z',
  topic: null,
  product: null,
  category: null,
  language: null,
  channel: null,
}

export const liveFilters: DashboardFilters = {
  ...demoFilters,
  sourceKey: liveSource.key,
  from: '2026-01-01T00:00:00Z',
  toExclusive: '2026-02-01T00:00:00Z',
}

const capabilities = {
  products: true,
  categories: true,
  languages: true,
  channels: true,
  evidenceText: true,
}

const options = {
  topics: ['delivery_delay'],
  products: ['Sample parcel'],
  categories: ['illustrative_orders'],
  languages: ['en'],
  channels: ['illustrative_survey'],
}

export const demoMetadata: MetadataResponse = {
  kind: 'metadata',
  contractVersion: '1.0',
  context: 'demo',
  source: demoSource,
  sources: [semifDemoSource, rulesDemoSource, demoSource],
  availableRange: {
    from: demoFilters.from,
    toExclusive: demoFilters.toExclusive,
  },
  capabilities,
  filterOptions: options,
  policyStatus: 'illustrative',
}

export const liveMetadata: MetadataResponse = {
  kind: 'metadata',
  contractVersion: '1.0',
  context: 'live',
  source: liveSource,
  sources: [liveSource],
  availableRange: {
    from: liveFilters.from,
    toExclusive: liveFilters.toExclusive,
  },
  capabilities: { ...capabilities, evidenceText: false },
  filterOptions: options,
  policyStatus: 'awaiting_calibration',
}

export const emptyLiveMetadata: MetadataResponse = {
  ...liveMetadata,
  source: null,
  sources: [],
  availableRange: null,
  capabilities: {
    products: false,
    categories: false,
    languages: false,
    channels: false,
    evidenceText: false,
  },
  filterOptions: {
    topics: [],
    products: [],
    categories: [],
    languages: [],
    channels: [],
  },
}

export const demoOverview: OverviewResponse = {
  kind: 'overview',
  contractVersion: '1.0',
  context: 'demo',
  filters: demoFilters,
  processing: {
    feedbackRecords: 12,
    decisionRuns: 12,
    typedAnswers: 168,
    jobsByStatus: { completed: 12 },
    projectionByDestination: {},
  },
  metrics: [
    {
      id: 'imported_feedback',
      label: 'Imported feedback',
      unit: 'count',
      value: 12,
      numerator: 12,
      denominator: null,
      availability: { state: 'available', reason: null },
    },
    {
      id: 'classified_feedback',
      label: 'Classified feedback',
      unit: 'percent',
      value: 100,
      numerator: 12,
      denominator: 12,
      availability: { state: 'available', reason: null },
    },
    {
      id: 'analytical_coverage',
      label: 'Illustrative analytical coverage',
      unit: 'percent',
      value: 83.3,
      numerator: 10,
      denominator: 12,
      availability: { state: 'available', reason: null },
    },
    {
      id: 'topic_rate',
      label: 'Illustrative delivery-delay rate',
      unit: 'percent',
      value: 60,
      numerator: 6,
      denominator: 10,
      availability: { state: 'available', reason: null },
    },
  ],
  series: [
    {
      periodStart: '2026-05-01T00:00:00Z',
      importedCount: 3,
      eligibleCount: 2,
      topicNumerator: 1,
      value: 50,
    },
    {
      periodStart: '2026-05-08T00:00:00Z',
      importedCount: 3,
      eligibleCount: 3,
      topicNumerator: 2,
      value: 66.7,
    },
  ],
  signals: [
    {
      id: 'delivery_delay',
      label: 'Illustrative delivery delay',
      definition:
        'Distinct illustrative records curated with the delivery-delay topic among eligible records.',
      numerator: 6,
      denominator: 10,
      rate: 60,
      comparison: {
        range: {
          from: '2026-04-01T00:00:00Z',
          toExclusive: '2026-05-01T00:00:00Z',
        },
        numerator: 3,
        denominator: 8,
        rate: 37.5,
      },
      deltaPoints: 22.5,
      availability: { state: 'available', reason: null },
    },
  ],
}

export const demoSignal: SignalResponse = {
  kind: 'signal',
  contractVersion: '1.0',
  context: 'demo',
  filters: demoFilters,
  signal: demoOverview.signals[0]!,
  series: demoOverview.series,
  method:
    'Illustrative fixture counts only; no calibrated probability or statistical-significance claim.',
}

const firstEvidence = {
  feedbackId: '11111111-1111-4111-8111-111111111111',
  decisionId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
  occurredAt: '2026-05-24T10:00:00Z',
  sourceRecordId: 'illustrative-006',
  channel: 'illustrative_survey',
  productLabel: 'Sample parcel',
  excerpt: 'The sample parcel arrived after the illustrated delivery date.',
  evidenceAccess: 'permitted_synthetic' as const,
  inclusionReason:
    'The curated illustrative answer marks this record eligible.',
}

export function demoEvidence(page = 1): EvidencePageResponse {
  return {
    kind: 'evidence-page',
    contractVersion: '1.0',
    context: 'demo',
    filters: demoFilters,
    signalId: 'delivery_delay',
    page,
    pageSize: 5,
    total: 7,
    items: [
      {
        ...firstEvidence,
        feedbackId:
          page === 1
            ? firstEvidence.feedbackId
            : '22222222-2222-4222-8222-222222222222',
        sourceRecordId: page === 1 ? 'illustrative-006' : 'illustrative-012',
      },
    ],
  }
}

export const demoDetail: EvidenceDetailResponse = {
  kind: 'evidence-detail',
  contractVersion: '1.0',
  context: 'demo',
  source: demoSource,
  record: firstEvidence,
  evidence: {
    access: 'permitted_synthetic',
    title: 'Illustrative late arrival',
    body: 'The sample parcel arrived after the illustrated delivery date. This sentence was written only for the repository-owned demo journey.',
  },
  answers: [
    {
      questionId: 'primary_topic',
      label: 'Primary topic',
      primitive: 'choice',
      value: 'delivery_delay',
      confidenceLabel: null,
      eligibility: 'illustrative_eligible',
    },
  ],
  provenance: {
    decisionId: firstEvidence.decisionId,
    schemaName: 'feedback-decision',
    schemaVersion: '1.0.0',
    modelVersion: 'illustrative-fixture/1.0',
    policyVersion: 'illustrative-demo/1.0',
    policyStatus: 'illustrative',
    traceId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
    decidedAt: '2026-05-24T10:01:00Z',
  },
  inclusionReason: firstEvidence.inclusionReason,
}

export const restrictedDetail: EvidenceDetailResponse = {
  ...demoDetail,
  context: 'live',
  source: liveSource,
  record: {
    ...firstEvidence,
    excerpt: null,
    evidenceAccess: 'restricted',
  },
  evidence: { access: 'restricted', title: null, body: null },
  answers: [
    {
      ...demoDetail.answers[0]!,
      eligibility: 'withheld_uncalibrated',
    },
  ],
  provenance: {
    ...demoDetail.provenance,
    policyStatus: 'awaiting_calibration',
  },
}

export const liveOverview: OverviewResponse = {
  ...demoOverview,
  context: 'live',
  filters: liveFilters,
  processing: {
    feedbackRecords: 9,
    decisionRuns: 9,
    typedAnswers: 126,
    jobsByStatus: { completed: 9 },
    projectionByDestination: { clickhouse: 0 },
  },
  metrics: [
    {
      ...demoOverview.metrics[0]!,
      value: 9,
      numerator: 9,
    },
    {
      ...demoOverview.metrics[1]!,
      value: 100,
      numerator: 9,
      denominator: 9,
    },
    {
      id: 'analytical_coverage',
      label: 'Analytical coverage',
      unit: 'percent',
      value: null,
      numerator: 0,
      denominator: 9,
      availability: { state: 'unavailable', reason: 'uncalibrated' },
    },
    {
      id: 'topic_rate',
      label: 'Delivery-delay rate',
      unit: 'percent',
      value: null,
      numerator: 0,
      denominator: 0,
      availability: { state: 'unavailable', reason: 'uncalibrated' },
    },
  ],
  series: demoOverview.series.map((point) => ({
    ...point,
    eligibleCount: 0,
    topicNumerator: 0,
    value: null,
  })),
  signals: [],
}

const trendMethod = {
  id: 'simple_rate_change' as const,
  version: '1.0.0',
  configurationChecksum:
    'b5cebc1b2a55a5b0dcfdc0be202eaf205d3b5d7d39ac7e1f6492336557a3758c',
  currentWindowDays: 7 as const,
  baselineWindowDays: 28 as const,
  minimumCurrentDenominator: 50,
  minimumBaselineDenominator: 100,
  minimumCurrentNumerator: 5,
  minimumAbsoluteDeltaPoints: 10,
  minimumRelativeChangePercent: 50,
  claim: 'emerging_signal_not_statistical_significance' as const,
  betaPriorAlpha: null,
  betaPriorBeta: null,
  minimumProbabilityOfDirection: null,
}

export const demoTrends: TrendOverviewResponse = {
  kind: 'trend-overview',
  contractVersion: '1.0',
  context: 'demo',
  availability: { state: 'available', reason: null },
  source: {
    key: 'synthetic/trend-backtest/2026.1',
    providerId: 'synthetic',
    datasetName: 'trend-backtest',
    datasetVersion: '2026.1',
    displayName: 'Illustrative planted-incident trend backtest',
    synthetic: true,
  },
  method: trendMethod,
  summary: {
    plantedIncidentCount: 2,
    alertEpisodeCount: 2,
    evaluableSeriesDayCount: 200,
    recall: 0.5,
    precision: 0.5,
    medianDetectionDelayDays: 2,
    falseAlertEpisodesPer100SeriesDays: 0.5,
  },
  series: [
    {
      seriesId: 'series-delivery-delay-all',
      signalId: 'delivery_delay',
      signalLabel: 'Delivery delay',
      product: null,
      direction: 'increase',
    },
    {
      seriesId: 'series-billing-issue-nimbus',
      signalId: 'billing_issue',
      signalLabel: 'Billing issue',
      product: 'Nimbus Backpack',
      direction: 'increase',
    },
  ],
  results: [
    {
      evaluationId: 'evaluation-delivery-delay-2026-03-08',
      seriesId: 'series-delivery-delay-all',
      anchor: '2026-03-08T00:00:00Z',
      state: 'emerging_signal',
      current: {
        range: {
          from: '2026-03-01T00:00:00Z',
          toExclusive: '2026-03-08T00:00:00Z',
        },
        numerator: 16,
        denominator: 70,
        rate: 22.8571428571,
      },
      baseline: {
        range: {
          from: '2026-02-01T00:00:00Z',
          toExclusive: '2026-03-01T00:00:00Z',
        },
        numerator: 18,
        denominator: 280,
        rate: 6.4285714286,
      },
      deltaPoints: 16.4285714285,
      rateRatio: 3.5555555556,
      relativeChangePercent: 255.5555555556,
      probabilityOfDirection: null,
      gateReasons: [
        'current_denominator_met',
        'baseline_denominator_met',
        'current_numerator_met',
        'absolute_delta_met',
        'relative_change_met',
      ],
    },
    {
      evaluationId: 'evaluation-billing-issue-nimbus-2026-03-08',
      seriesId: 'series-billing-issue-nimbus',
      anchor: '2026-03-08T00:00:00Z',
      state: 'insufficient_coverage',
      current: {
        range: {
          from: '2026-03-01T00:00:00Z',
          toExclusive: '2026-03-08T00:00:00Z',
        },
        numerator: 3,
        denominator: 14,
        rate: 21.4285714286,
      },
      baseline: {
        range: {
          from: '2026-02-01T00:00:00Z',
          toExclusive: '2026-03-01T00:00:00Z',
        },
        numerator: 10,
        denominator: 280,
        rate: 3.5714285714,
      },
      deltaPoints: 17.8571428572,
      rateRatio: 6,
      relativeChangePercent: 500,
      probabilityOfDirection: null,
      gateReasons: [
        'current_denominator_below_minimum',
        'current_numerator_below_minimum',
      ],
    },
  ],
  incidents: [
    {
      incidentId: 'synthetic-incident-topic-escalation',
      outcome: 'delivery_delay_increase',
      seriesId: 'series-delivery-delay-all',
      plantedAt: '2026-03-06T00:00:00Z',
      detected: true,
      matchedEvaluationId: 'evaluation-delivery-delay-2026-03-08',
      detectionDelayDays: 2,
    },
    {
      incidentId: 'synthetic-incident-product-specific-defect',
      outcome: 'product_defect_noise_increase',
      seriesId: 'series-billing-issue-nimbus',
      plantedAt: '2026-03-07T00:00:00Z',
      detected: false,
      matchedEvaluationId: null,
      detectionDelayDays: null,
    },
  ],
}

export const liveTrends: TrendOverviewResponse = {
  kind: 'trend-overview',
  contractVersion: '1.0',
  context: 'live',
  availability: { state: 'unavailable', reason: 'awaiting_calibration' },
  source: null,
  method: trendMethod,
  summary: null,
  series: [],
  results: [],
  incidents: [],
}

export const demoEvaluation: EvaluationComparisonResponse = {
  kind: 'evaluation-comparison',
  contractVersion: '1.0',
  context: 'demo',
  availability: { state: 'available', reason: null },
  status: 'complete',
  reference: {
    kind: 'ai_reviewed_not_human_gold',
    model: 'gpt-5.6-sol',
    reasoning: 'medium',
  },
  recordCount: 480,
  successCount: 480,
  errorCount: 0,
  semif: {
    requestedModel: 'semif-qwen3.5-4b-mlx-q4-851bf6e8',
    resolvedModel: 'semif-qwen3.5-4b-mlx-q4-851bf6e8',
  },
  semifPrimaryTopic: {
    macroF1: 0.8333071569443776,
    accuracy: 0.88125,
  },
  semifLanguageSlices: [
    {
      language: 'en-GB',
      recordCount: 302,
      successCount: 302,
      errorCount: 0,
      primaryTopic: {
        macroF1: 0.8692667371910173,
        accuracy: 0.9006622516556292,
      },
    },
    {
      language: 'sv-SE',
      recordCount: 178,
      successCount: 178,
      errorCount: 0,
      primaryTopic: {
        macroF1: 0.7407656570606828,
        accuracy: 0.848314606741573,
      },
    },
  ],
  rules: {
    requestedModel: 'rules-1.0.0',
    resolvedModel: 'rules-1.0.0',
  },
  rulePrimaryTopic: {
    macroF1: 0.9987936390814087,
    accuracy: 0.9979166666666667,
  },
  ruleLanguageSlices: [
    {
      language: 'en-GB',
      recordCount: 302,
      successCount: 302,
      errorCount: 0,
      primaryTopic: { macroF1: 1, accuracy: 1 },
    },
    {
      language: 'sv-SE',
      recordCount: 178,
      successCount: 178,
      errorCount: 0,
      primaryTopic: {
        macroF1: 0.9970136144049186,
        accuracy: 0.9943820224719101,
      },
    },
  ],
  llm: {
    requestedModel: 'gpt-5.4-mini-2026-03-17',
    resolvedModel: 'gpt-5.4-mini-2026-03-17',
  },
  semifCost: {
    scope: 'local_inference',
    status: 'measured_complete',
    tokens: 1_515_670,
    costUsd: 0,
    successfulRecords: 480,
    targetRecords: 480,
    estimatedTargetCostUsd: 0,
    estimateMethod: 'local_mlx_no_api_charge',
  },
  llmCost: {
    scope: 'partial_experiment',
    status: 'closed_partial',
    tokens: 477_777,
    costUsd: 0.39,
    successfulRecords: 192,
    targetRecords: 480,
    estimatedTargetCostUsd: 0.98,
    estimateMethod: 'linear_extrapolation_from_owner_reported_partial_spend',
  },
  llmPrimaryTopic: {
    macroF1: 0.782838358729344,
    accuracy: 0.8489583333333334,
  },
  llmLanguageSlices: [
    {
      language: 'en-GB',
      recordCount: 125,
      successCount: 125,
      errorCount: 0,
      primaryTopic: { macroF1: 0.758919348902371, accuracy: 0.832 },
    },
    {
      language: 'sv-SE',
      recordCount: 67,
      successCount: 67,
      errorCount: 0,
      primaryTopic: {
        macroF1: 0.8400673400673401,
        accuracy: 0.8805970149253731,
      },
    },
  ],
}

export const liveEvaluation: EvaluationComparisonResponse = {
  kind: 'evaluation-comparison',
  contractVersion: '1.0',
  context: 'live',
  availability: { state: 'unavailable', reason: 'awaiting_human_labels' },
  status: 'awaiting_human_labels',
  reference: null,
  recordCount: 0,
  successCount: 0,
  errorCount: 0,
  semif: null,
  semifPrimaryTopic: null,
  semifLanguageSlices: [],
  rules: null,
  rulePrimaryTopic: null,
  ruleLanguageSlices: [],
  llm: null,
  semifCost: null,
  llmCost: null,
  llmPrimaryTopic: null,
  llmLanguageSlices: [],
}
