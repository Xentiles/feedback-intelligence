namespace FeedbackIntelligence.Api.Dashboard;

public sealed class LiveEvaluationDataSource : IEvaluationDataSource
{
    public string Context => "live";

    public Task<EvaluationComparisonResponse> GetEvaluationAsync(
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(new EvaluationComparisonResponse(
            "evaluation-comparison",
            "1.0",
            "live",
            Availability.Unavailable("awaiting_human_labels"),
            "awaiting_human_labels",
            null,
            0,
            0,
            0,
            null,
            null,
            [],
            null,
            null,
            [],
            null,
            null,
            null,
            null,
            []));
    }
}
