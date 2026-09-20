export type PresentationContext = 'live' | 'demo'

export type UnavailableReason =
  | 'uncalibrated'
  | 'awaiting_calibration'
  | 'no_eligible_evidence'
  | 'insufficient_data'
  | 'unsupported_dimension'
  | 'source_unavailable'
  | 'awaiting_human_labels'

export type Availability =
  | { state: 'available'; reason: null }
  | { state: 'unavailable'; reason: UnavailableReason }

export interface SourceIdentity {
  key: string
  providerId: string
  datasetName: string
  datasetVersion: string
  displayName: string
  synthetic: boolean
}

export interface TimeRange {
  from: string
  toExclusive: string
}

export interface DashboardFilters extends TimeRange {
  sourceKey: string
  topic: string | null
  product: string | null
  category: string | null
  language: string | null
  channel: string | null
}

export interface Capabilities {
  products: boolean
  categories: boolean
  languages: boolean
  channels: boolean
  evidenceText: boolean
}

export interface FilterOptions {
  topics: string[]
  products: string[]
  categories: string[]
  languages: string[]
  channels: string[]
}

export interface MetadataResponse {
  kind: 'metadata'
  contractVersion: '1.0'
  context: PresentationContext
  source: SourceIdentity | null
  sources: SourceIdentity[]
  availableRange: TimeRange | null
  capabilities: Capabilities
  filterOptions: FilterOptions
  policyStatus: 'awaiting_calibration' | 'illustrative'
}

export interface Metric {
  id: string
  label: string
  unit: 'count' | 'percent' | 'score'
  value: number | null
  numerator: number | null
  denominator: number | null
  availability: Availability
}

export interface ProcessingSummary {
  feedbackRecords: number
  decisionRuns: number
  typedAnswers: number
  jobsByStatus: Record<string, number>
  projectionByDestination: Record<string, number>
}

export interface SeriesPoint {
  periodStart: string
  importedCount: number
  eligibleCount: number
  topicNumerator: number
  value: number | null
}

export interface Comparison {
  range: TimeRange
  numerator: number
  denominator: number
  rate: number | null
}

export interface SignalSummary {
  id: string
  label: string
  definition: string
  numerator: number
  denominator: number
  rate: number | null
  comparison: Comparison | null
  deltaPoints: number | null
  availability: Availability
}

export interface OverviewResponse {
  kind: 'overview'
  contractVersion: '1.0'
  context: PresentationContext
  filters: DashboardFilters
  processing: ProcessingSummary
  metrics: Metric[]
  series: SeriesPoint[]
  signals: SignalSummary[]
}

export interface TrendMethod {
  id: 'simple_rate_change' | 'candidate_statistical'
  version: string
  configurationChecksum: string
  currentWindowDays: 7
  baselineWindowDays: 28
  minimumCurrentDenominator: number
  minimumBaselineDenominator: number
  minimumCurrentNumerator: number
  minimumAbsoluteDeltaPoints: number
  minimumRelativeChangePercent: number
  claim:
    | 'emerging_signal_not_statistical_significance'
    | 'posterior_probability_not_multiple_test_adjusted'
  betaPriorAlpha: number | null
  betaPriorBeta: number | null
  minimumProbabilityOfDirection: number | null
}

export interface TrendEvaluationSummary {
  plantedIncidentCount: number
  alertEpisodeCount: number
  evaluableSeriesDayCount: number
  recall: number
  precision: number
  medianDetectionDelayDays: number
  falseAlertEpisodesPer100SeriesDays: number
}

export interface TrendSeries {
  seriesId: string
  signalId: string
  signalLabel: string
  product: string | null
  direction: 'increase' | 'decrease'
}

export interface TrendWindow {
  range: TimeRange
  numerator: number
  denominator: number
  rate: number | null
}

export type TrendGateReason =
  | 'current_denominator_met'
  | 'baseline_denominator_met'
  | 'current_numerator_met'
  | 'absolute_delta_met'
  | 'relative_change_met'
  | 'probability_direction_met'
  | 'current_denominator_below_minimum'
  | 'baseline_denominator_below_minimum'
  | 'current_numerator_below_minimum'
  | 'absolute_delta_below_minimum'
  | 'relative_change_below_minimum'
  | 'probability_direction_below_minimum'
  | 'baseline_rate_zero'

export interface TrendEvaluationResult {
  evaluationId: string
  seriesId: string
  anchor: string
  state: 'emerging_signal' | 'not_emerging' | 'insufficient_coverage'
  current: TrendWindow
  baseline: TrendWindow
  deltaPoints: number
  rateRatio: number | null
  relativeChangePercent: number | null
  probabilityOfDirection: number | null
  gateReasons: TrendGateReason[]
}

export interface TrendIncident {
  incidentId: string
  outcome:
    | 'product_defect_noise_increase'
    | 'delivery_delay_increase'
    | 'support_praise_increase'
    | 'return_unresolved_increase'
  seriesId: string
  plantedAt: string
  detected: boolean
  matchedEvaluationId: string | null
  detectionDelayDays: number | null
}

export interface TrendOverviewResponse {
  kind: 'trend-overview'
  contractVersion: '1.0'
  context: PresentationContext
  availability: Availability
  source: SourceIdentity | null
  method: TrendMethod
  summary: TrendEvaluationSummary | null
  series: TrendSeries[]
  results: TrendEvaluationResult[]
  incidents: TrendIncident[]
}

export interface EvaluationMetrics {
  macroF1: number | null
  accuracy: number | null
}

export interface EvaluationLanguageSlice {
  language: string
  recordCount: number
  successCount: number
  errorCount: number
  primaryTopic: EvaluationMetrics
}

export interface EvaluationCostObservation {
  scope: string
  status: string
  tokens: number
  costUsd: number
  successfulRecords: number | null
  targetRecords: number | null
  estimatedTargetCostUsd: number | null
  estimateMethod: string
}

export interface EvaluationComparisonResponse {
  kind: 'evaluation-comparison'
  contractVersion: '1.0'
  context: PresentationContext
  availability: Availability
  status: 'placeholder_pending_run' | 'complete' | 'awaiting_human_labels'
  reference: {
    kind: 'ai_reviewed_not_human_gold'
    model: string
    reasoning: string
  } | null
  recordCount: number
  successCount: number
  errorCount: number
  semif: {
    requestedModel: string
    resolvedModel: string
  } | null
  semifPrimaryTopic: EvaluationMetrics | null
  semifLanguageSlices: EvaluationLanguageSlice[]
  rules: {
    requestedModel: string
    resolvedModel: string
  } | null
  rulePrimaryTopic: EvaluationMetrics | null
  ruleLanguageSlices: EvaluationLanguageSlice[]
  llm: {
    requestedModel: string
    resolvedModel: string
  } | null
  semifCost: EvaluationCostObservation | null
  llmCost: EvaluationCostObservation | null
  llmPrimaryTopic: EvaluationMetrics | null
  llmLanguageSlices: EvaluationLanguageSlice[]
}

export interface SignalResponse {
  kind: 'signal'
  contractVersion: '1.0'
  context: PresentationContext
  filters: DashboardFilters
  signal: SignalSummary
  series: SeriesPoint[]
  method: string
}

export interface EvidenceRow {
  feedbackId: string
  decisionId: string
  occurredAt: string
  sourceRecordId: string
  channel: string | null
  productLabel: string | null
  excerpt: string | null
  evidenceAccess: 'permitted_synthetic' | 'restricted'
  inclusionReason: string
}

export interface EvidencePageResponse {
  kind: 'evidence-page'
  contractVersion: '1.0'
  context: PresentationContext
  filters: DashboardFilters
  signalId: string
  page: number
  pageSize: number
  total: number
  items: EvidenceRow[]
}

export interface Answer {
  questionId: string
  label: string
  primitive: 'choice' | 'score' | 'noul'
  value: string | number | boolean | null
  confidenceLabel: string | null
  eligibility:
    'illustrative_eligible' | 'withheld_uncalibrated' | 'not_applicable'
}

export interface Provenance {
  decisionId: string
  schemaName: string
  schemaVersion: string
  modelVersion: string
  policyVersion: string | null
  policyStatus: 'awaiting_calibration' | 'illustrative'
  traceId: string
  decidedAt: string
}

export interface EvidenceDetailResponse {
  kind: 'evidence-detail'
  contractVersion: '1.0'
  context: PresentationContext
  source: SourceIdentity
  record: EvidenceRow
  evidence:
    | { access: 'permitted_synthetic'; title: string | null; body: string }
    | { access: 'restricted'; title: null; body: null }
  answers: Answer[]
  provenance: Provenance
  inclusionReason: string
}
