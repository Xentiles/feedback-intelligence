namespace FeedbackIntelligence.Api.Dashboard;

public sealed record TrendMethod(
    string Id,
    string Version,
    string ConfigurationChecksum,
    int CurrentWindowDays,
    int BaselineWindowDays,
    int MinimumCurrentDenominator,
    int MinimumBaselineDenominator,
    int MinimumCurrentNumerator,
    double MinimumAbsoluteDeltaPoints,
    double MinimumRelativeChangePercent,
    string Claim,
    int? BetaPriorAlpha,
    int? BetaPriorBeta,
    double? MinimumProbabilityOfDirection);

public sealed record TrendEvaluationSummary(
    int PlantedIncidentCount,
    int AlertEpisodeCount,
    int EvaluableSeriesDayCount,
    double Recall,
    double Precision,
    double MedianDetectionDelayDays,
    double FalseAlertEpisodesPer100SeriesDays);

public sealed record TrendSeries(
    string SeriesId,
    string SignalId,
    string SignalLabel,
    string? Product,
    string Direction);

public sealed record TrendWindow(
    TimeRange Range,
    int Numerator,
    int Denominator,
    double? Rate);

public sealed record TrendEvaluationResult(
    string EvaluationId,
    string SeriesId,
    DateTimeOffset Anchor,
    string State,
    TrendWindow Current,
    TrendWindow Baseline,
    double DeltaPoints,
    double? RateRatio,
    double? RelativeChangePercent,
    IReadOnlyList<string> GateReasons,
    double? ProbabilityOfDirection);

public sealed record TrendIncident(
    string IncidentId,
    string Outcome,
    string SeriesId,
    DateTimeOffset PlantedAt,
    bool Detected,
    string? MatchedEvaluationId,
    int? DetectionDelayDays);

public sealed record TrendOverviewResponse(
    string Kind,
    string ContractVersion,
    string Context,
    Availability Availability,
    SourceIdentity? Source,
    TrendMethod Method,
    TrendEvaluationSummary? Summary,
    IReadOnlyList<TrendSeries> Series,
    IReadOnlyList<TrendEvaluationResult> Results,
    IReadOnlyList<TrendIncident> Incidents);
