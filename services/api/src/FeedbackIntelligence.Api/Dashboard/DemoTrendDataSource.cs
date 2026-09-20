using System.Text.Json;
using Microsoft.Extensions.Options;

namespace FeedbackIntelligence.Api.Dashboard;

public sealed class DemoTrendDataSource : ITrendDataSource
{
    private static readonly JsonSerializerOptions FixtureJsonOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    private readonly TrendOverviewResponse _fixture;

    public DemoTrendDataSource(
        IWebHostEnvironment environment,
        IOptions<TrendOptions> configuredOptions)
    {
        var selected = configuredOptions.Value.SelectedAlgorithm;
        var fixtureName = selected switch
        {
            TrendAlgorithmKind.SimpleRateChange => "trend-demo.json",
            TrendAlgorithmKind.CandidateStatistical => "trend-demo-candidate-statistical.json",
            _ => throw new ArgumentOutOfRangeException(nameof(configuredOptions)),
        };
        var path = Path.Combine(environment.ContentRootPath, "Fixtures", fixtureName);
        using var stream = File.OpenRead(path);
        _fixture = JsonSerializer.Deserialize<TrendOverviewResponse>(stream, FixtureJsonOptions)
            ?? throw new InvalidOperationException("The trend demo fixture is empty.");
        var selectedAlgorithm = selected.ToConfigurationValue();
        if (_fixture.Method.Id != selectedAlgorithm)
        {
            throw new InvalidOperationException(
                $"The trend fixture does not support configured algorithm '{selectedAlgorithm}'.");
        }
    }

    public string Context => "demo";

    public Task<TrendOverviewResponse> GetTrendsAsync(
        string? sourceKey,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (sourceKey is not null && sourceKey != _fixture.Source?.Key)
        {
            throw new DashboardSourceNotFoundException(
                $"Source '{sourceKey}' is not available in the demo context.");
        }

        return Task.FromResult(_fixture);
    }
}
