namespace FeedbackIntelligence.Api.Dashboard;

public interface IEvaluationDataSource
{
    string Context { get; }

    Task<EvaluationComparisonResponse> GetEvaluationAsync(
        CancellationToken cancellationToken);
}
