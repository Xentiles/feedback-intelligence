using System.Text.Json;

namespace FeedbackIntelligence.Api.Dashboard;

public sealed class DemoEvaluationDataSource : IEvaluationDataSource
{
    private static readonly JsonSerializerOptions FixtureJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    private readonly EvaluationComparisonResponse _fixture;

    public DemoEvaluationDataSource(IWebHostEnvironment environment)
    {
        var path = Path.Combine(environment.ContentRootPath, "Fixtures", "evaluation-demo.json");
        using var stream = File.OpenRead(path);
        _fixture = JsonSerializer.Deserialize<EvaluationComparisonResponse>(stream, FixtureJsonOptions)
            ?? throw new InvalidOperationException("The evaluation demo fixture is empty.");
    }

    public string Context => "demo";

    public Task<EvaluationComparisonResponse> GetEvaluationAsync(
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(_fixture);
    }
}
