using Microsoft.Extensions.Options;

namespace FeedbackIntelligence.Api.Dashboard;

public sealed class LiveTrendDataSource : ITrendDataSource
{
    internal static readonly TrendMethod Method = new(
        "simple_rate_change",
        "simple-rate/1.0.0",
        "af56b0b602fae5cc36339bcf24632e2dc3ba0a9367c44aacb1dcd2ba705e3fe2",
        7,
        28,
        20,
        50,
        3,
        20.0,
        30.0,
        "emerging_signal_not_statistical_significance",
        null,
        null,
        null);

    internal static readonly TrendMethod CandidateMethod = new(
        "candidate_statistical",
        "beta-binomial/1.0.0",
        "887f919a80f229126324a5544e503c8987b90e16a5bbfe63bf7d2cccb8dfc360",
        7,
        28,
        20,
        50,
        3,
        20.0,
        30.0,
        "posterior_probability_not_multiple_test_adjusted",
        1,
        1,
        0.98);

    private readonly TrendMethod _method;

    public LiveTrendDataSource(IOptions<TrendOptions> configuredOptions)
    {
        _method = configuredOptions.Value.SelectedAlgorithm switch
        {
            TrendAlgorithmKind.SimpleRateChange => Method,
            TrendAlgorithmKind.CandidateStatistical => CandidateMethod,
            _ => throw new ArgumentOutOfRangeException(nameof(configuredOptions)),
        };
    }

    public string Context => "live";

    public Task<TrendOverviewResponse> GetTrendsAsync(
        string? sourceKey,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(new TrendOverviewResponse(
            "trend-overview",
            "1.0",
            "live",
            Availability.Unavailable("awaiting_calibration"),
            null,
            _method,
            null,
            [],
            [],
            []));
    }
}
