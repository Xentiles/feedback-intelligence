namespace FeedbackIntelligence.Api.Dashboard;

public interface ITrendDataSource
{
    string Context { get; }

    Task<TrendOverviewResponse> GetTrendsAsync(
        string? sourceKey,
        CancellationToken cancellationToken);
}
