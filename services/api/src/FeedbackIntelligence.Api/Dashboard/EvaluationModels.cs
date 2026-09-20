namespace FeedbackIntelligence.Api.Dashboard;

public sealed record EvaluationReference(
    string Kind,
    string Model,
    string Reasoning);

public sealed record EvaluationCandidate(
    string RequestedModel,
    string ResolvedModel);

public sealed record EvaluationCostObservation(
    string Scope,
    string Status,
    long Tokens,
    double CostUsd,
    int? SuccessfulRecords,
    int? TargetRecords,
    double? EstimatedTargetCostUsd,
    string EstimateMethod);

public sealed record EvaluationMetrics(
    double? MacroF1,
    double? Accuracy);

public sealed record EvaluationLanguageSlice(
    string Language,
    int RecordCount,
    int SuccessCount,
    int ErrorCount,
    EvaluationMetrics PrimaryTopic);

public sealed record EvaluationComparisonResponse(
    string Kind,
    string ContractVersion,
    string Context,
    Availability Availability,
    string Status,
    EvaluationReference? Reference,
    int RecordCount,
    int SuccessCount,
    int ErrorCount,
    EvaluationCandidate? Semif,
    EvaluationMetrics? SemifPrimaryTopic,
    IReadOnlyList<EvaluationLanguageSlice> SemifLanguageSlices,
    EvaluationCandidate? Rules,
    EvaluationMetrics? RulePrimaryTopic,
    IReadOnlyList<EvaluationLanguageSlice> RuleLanguageSlices,
    EvaluationCandidate? Llm,
    EvaluationCostObservation? SemifCost,
    EvaluationCostObservation? LlmCost,
    EvaluationMetrics? LlmPrimaryTopic,
    IReadOnlyList<EvaluationLanguageSlice> LlmLanguageSlices);
