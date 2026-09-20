using System.Text.Json;
using FeedbackIntelligence.Api.Ingestion;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;

namespace FeedbackIntelligence.Api.Tests;

public sealed class QualityPostgresFactAttribute : FactAttribute
{
    public QualityPostgresFactAttribute()
    {
        if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("QUALITY_POSTGRES_DSN")))
        {
            Skip = "Run scripts/quality_ingestion_check.py for isolated PostgreSQL interoperability.";
        }
    }
}

public sealed class PostgresIngestionTests
{
    private static readonly JsonSerializerOptions CanonicalJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    [QualityPostgresFact]
    public async Task PythonAndApiDuplicatesCompareStoredContentWithoutRewritingIt()
    {
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(
            new Dictionary<string, string?>
            {
                ["ConnectionStrings:Operational"] = Environment.GetEnvironmentVariable("QUALITY_POSTGRES_DSN"),
            }).Build();
        var options = new IngestionOptions { Enabled = true };
        var store = new PostgresFeedbackIngestionStore(configuration, Options.Create(options));
        var records = File.ReadLines("/work/data/demo/feedback.jsonl").Take(2)
            .Select(line => JsonSerializer.Deserialize<FeedbackIngestionRequest>(line, CanonicalJsonOptions)!)
            .ToArray();

        // The harness first inserted this record with the Python writer/hash.
        var duplicate = await store.EnqueueAsync(IngestionValidator.Validate(records[0], options), default);
        Assert.False(duplicate.Created);
        await Assert.ThrowsAsync<IngestionConflictException>(() => store.EnqueueAsync(
            IngestionValidator.Validate(records[0] with { OriginalText = "Changed content" }, options), default));

        // Reverse direction: Python will retry this API-written record after this test.
        var second = records[1] with
        {
            Metadata = JsonSerializer.SerializeToElement(new { z = 1.0m, a = "å" }),
        };
        var created = await store.EnqueueAsync(IngestionValidator.Validate(second, options), default);
        Assert.True(created.Created);
        var reordered = second with
        {
            Metadata = JsonSerializer.SerializeToElement(new { a = "å", z = 1 }),
        };
        var retried = await store.EnqueueAsync(IngestionValidator.Validate(reordered, options), default);
        Assert.False(retried.Created);
        Assert.Equal(created.JobId, retried.JobId);
    }
}
