namespace FeedbackIntelligence.Api.Dashboard;

public enum TrendAlgorithmKind
{
    SimpleRateChange,
    CandidateStatistical,
}

public static class TrendAlgorithmKindExtensions
{
    public static string ToConfigurationValue(this TrendAlgorithmKind algorithm) =>
        algorithm switch
        {
            TrendAlgorithmKind.SimpleRateChange => "simple_rate_change",
            TrendAlgorithmKind.CandidateStatistical => "candidate_statistical",
            _ => throw new ArgumentOutOfRangeException(nameof(algorithm)),
        };

    public static TrendAlgorithmKind ParseConfigurationValue(string value) =>
        value.Trim().ToLowerInvariant() switch
        {
            "simple_rate_change" => TrendAlgorithmKind.SimpleRateChange,
            "candidate_statistical" => TrendAlgorithmKind.CandidateStatistical,
            _ => throw new InvalidOperationException(
                "Trend:Algorithm must be 'simple_rate_change' or 'candidate_statistical'."),
        };
}

public sealed record TrendOptions
{
    public string Algorithm { get; init; } = "simple_rate_change";

    public TrendAlgorithmKind SelectedAlgorithm =>
        TrendAlgorithmKindExtensions.ParseConfigurationValue(Algorithm);
}
