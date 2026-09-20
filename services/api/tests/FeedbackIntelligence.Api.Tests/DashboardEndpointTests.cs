using System.Net;
using System.Text.Json;
using FeedbackIntelligence.Api.Dashboard;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace FeedbackIntelligence.Api.Tests;

public sealed class DashboardEndpointTests : IClassFixture<WebApplicationFactory<Program>>
{
    private const string DemoSource = "synthetic%2Ffeedback-decision-ai-reference%2F1.0.0";
    private const string SemifSource = "synthetic%2Ffeedback-decision-semif%2F1.0.0";
    private const string RulesSource = "synthetic%2Ffeedback-decision-rules%2F1.0.0";
    private readonly HttpClient _client;

    public DashboardEndpointTests(WebApplicationFactory<Program> factory)
    {
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task DemoMetadataDeclaresSyntheticSourceAndActualRange()
    {
        using var response = await _client.GetAsync("/api/v1/dashboard/metadata?context=demo");
        using var json = await ReadJsonAsync(response);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("metadata", json.RootElement.GetProperty("kind").GetString());
        Assert.Equal("1.0", json.RootElement.GetProperty("contractVersion").GetString());
        Assert.Equal("demo", json.RootElement.GetProperty("context").GetString());
        Assert.True(json.RootElement.GetProperty("source").GetProperty("synthetic").GetBoolean());
        Assert.Equal(3, json.RootElement.GetProperty("sources").GetArrayLength());
        Assert.Equal("illustrative", json.RootElement.GetProperty("policyStatus").GetString());
        Assert.Equal("2025-01-01T11:34:44+00:00",
            json.RootElement.GetProperty("availableRange").GetProperty("from").GetString());
        Assert.Equal(9, json.RootElement.GetProperty("filterOptions").GetProperty("topics").GetArrayLength());
        Assert.Equal(13, json.RootElement.GetProperty("filterOptions").GetProperty("products").GetArrayLength());
    }

    [Fact]
    public async Task DemoSourceSelectionUsesTheChosenCompleteDecisionOutput()
    {
        using var semifResponse = await _client.GetAsync(Query(
            "/api/v1/dashboard/overview",
            "",
            SemifSource));
        using var semif = await ReadJsonAsync(semifResponse);
        using var rulesResponse = await _client.GetAsync(Query(
            "/api/v1/dashboard/overview",
            "",
            RulesSource));
        using var rules = await ReadJsonAsync(rulesResponse);

        Assert.Equal(HttpStatusCode.OK, semifResponse.StatusCode);
        Assert.Equal(HttpStatusCode.OK, rulesResponse.StatusCode);
        Assert.InRange(ReadMetric(semif.RootElement, "observed_issue_rate"), 0, 100);
        Assert.Equal(50.42, ReadMetric(rules.RootElement, "observed_issue_rate"));
        Assert.Equal(480, semif.RootElement.GetProperty("processing")
            .GetProperty("projectionByDestination").GetProperty("demo.semif").GetInt32());
        Assert.Equal(480, rules.RootElement.GetProperty("processing")
            .GetProperty("projectionByDestination").GetProperty("demo.rules").GetInt32());
    }

    [Fact]
    public async Task DemoOverviewMetricsAreDerivedFromFilteredFixtureRecords()
    {
        using var response = await _client.GetAsync(Query("/api/v1/dashboard/overview", "&category=graphics_card"));
        using var json = await ReadJsonAsync(response);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var metrics = json.RootElement.GetProperty("metrics").EnumerateArray().ToDictionary(
            metric => metric.GetProperty("id").GetString()!);
        Assert.Equal(86, metrics["imported_feedback"].GetProperty("value").GetInt32());
        Assert.Equal(86, metrics["classified_feedback"].GetProperty("numerator").GetInt32());
        Assert.Equal(86, metrics["observed_issue_rate"].GetProperty("denominator").GetInt32());
        Assert.Equal(53.49, metrics["observed_issue_rate"].GetProperty("value").GetDouble());
    }

    [Fact]
    public async Task DemoOverviewUsesAllAiReviewedRecordsAcrossFifteenMonths()
    {
        using var response = await _client.GetAsync(Query("/api/v1/dashboard/overview", ""));
        using var json = await ReadJsonAsync(response);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var metrics = json.RootElement.GetProperty("metrics").EnumerateArray().ToDictionary(
            metric => metric.GetProperty("id").GetString()!);
        Assert.Equal(480, metrics["imported_feedback"].GetProperty("value").GetInt32());
        Assert.Equal(480, json.RootElement.GetProperty("processing").GetProperty("decisionRuns").GetInt32());
        Assert.Equal(6_720, json.RootElement.GetProperty("processing").GetProperty("typedAnswers").GetInt32());
        Assert.Equal(15, json.RootElement.GetProperty("series").GetArrayLength());
    }

    [Fact]
    public async Task TopicFilterKeepsIssueRateSeriesStatisticallyUseful()
    {
        using var response = await _client.GetAsync(Query(
            "/api/v1/dashboard/overview",
            "&topic=product_quality&language=sv-SE&channel=product_review"));
        using var json = await ReadJsonAsync(response);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var values = json.RootElement.GetProperty("series").EnumerateArray()
            .Select(point => point.GetProperty("value").GetDouble())
            .ToArray();
        Assert.Equal(14, values.Length);
        Assert.Contains(values, value => value < 100);
        Assert.True(values.Distinct().Count() > 3);
    }

    [Fact]
    public async Task EvidencePaginationUsesStableDescendingOrder()
    {
        using var response = await _client.GetAsync(Query(
            "/api/v1/dashboard/signals/delivery_delay/evidence",
            "&page=1&pageSize=2"));
        using var json = await ReadJsonAsync(response);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(49, json.RootElement.GetProperty("total").GetInt32());
        var items = json.RootElement.GetProperty("items").EnumerateArray().ToArray();
        Assert.Equal("synthetic:20260919:009699", items[0].GetProperty("sourceRecordId").GetString());
        Assert.Equal("synthetic:20260919:009599", items[1].GetProperty("sourceRecordId").GetString());
        Assert.All(items, item => Assert.Equal(
            "permitted_synthetic",
            item.GetProperty("evidenceAccess").GetString()));
    }

    [Fact]
    public async Task DemoDetailKeepsIllustrativeProvenanceExplicit()
    {
        using var response = await _client.GetAsync(
            "/api/v1/dashboard/evidence/a062186b-120d-5448-a987-f64b6f754013" +
            "?context=demo&decisionId=abe59496-1f7d-5436-9bd2-dc9b755424f8");
        var text = await response.Content.ReadAsStringAsync();
        using var json = JsonDocument.Parse(text);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("permitted_synthetic",
            json.RootElement.GetProperty("evidence").GetProperty("access").GetString());
        Assert.Equal("illustrative",
            json.RootElement.GetProperty("provenance").GetProperty("policyStatus").GetString());
        Assert.Contains("Sol medium AI reference", text, StringComparison.Ordinal);
        Assert.Contains("not human gold", text, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("SemIf", text, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("/api/v1/dashboard/metadata?context=preview")]
    [InlineData("/api/v1/dashboard/overview?context=demo&sourceKey=synthetic%2Ffeedback-journey%2F2026.1&from=2026-01-01T00%3A00%3A00%2B01%3A00&toExclusive=2026-04-01T00%3A00%3A00Z")]
    [InlineData("/api/v1/dashboard/signals/delivery_delay/evidence?context=demo&sourceKey=synthetic%2Ffeedback-journey%2F2026.1&from=2026-01-01T00%3A00%3A00Z&toExclusive=2026-04-01T00%3A00%3A00Z&pageSize=51")]
    [InlineData("/api/v1/dashboard/signals/delivery_delay/evidence?context=demo&sourceKey=synthetic%2Ffeedback-decision-ai-reference%2F1.0.0&from=2025-01-01T00%3A00%3A00Z&toExclusive=2026-04-01T00%3A00%3A00Z&page=2147483647&pageSize=50")]
    public async Task InvalidRequestsReturnProblemDetails(string path)
    {
        using var response = await _client.GetAsync(path);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
    }

    [Fact]
    public async Task UnconfiguredLiveSourceReturnsProblemDetails()
    {
        using var response = await _client.GetAsync("/api/v1/dashboard/metadata?context=live");

        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
    }

    [Fact]
    public async Task EmptyConnectedLiveSourceHasNoInventedIdentityOrRange()
    {
        await using var factory = new StubLiveFactory(empty: true);
        using var client = factory.CreateClient();
        using var response = await client.GetAsync("/api/v1/dashboard/metadata?context=live");
        using var json = await ReadJsonAsync(response);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(JsonValueKind.Null, json.RootElement.GetProperty("source").ValueKind);
        Assert.Empty(json.RootElement.GetProperty("sources").EnumerateArray());
        Assert.Equal(JsonValueKind.Null, json.RootElement.GetProperty("availableRange").ValueKind);
    }

    [Fact]
    public async Task LiveZeroEligibilityPreservesProcessingCountsAndRestrictedEvidence()
    {
        await using var factory = new StubLiveFactory(empty: false);
        using var client = factory.CreateClient();
        using var overviewResponse = await client.GetAsync(
            "/api/v1/dashboard/overview?context=live&sourceKey=live%2Fsample%2Fv1" +
            "&from=2026-01-01T00%3A00%3A00Z&toExclusive=2026-04-01T00%3A00%3A00Z");
        using var overview = await ReadJsonAsync(overviewResponse);

        Assert.Equal(9, overview.RootElement.GetProperty("processing").GetProperty("feedbackRecords").GetInt32());
        var analytical = overview.RootElement.GetProperty("metrics").EnumerateArray()
            .Single(metric => metric.GetProperty("id").GetString() == "analytical_coverage");
        Assert.Equal(JsonValueKind.Null, analytical.GetProperty("value").ValueKind);
        Assert.Equal("uncalibrated", analytical.GetProperty("availability").GetProperty("reason").GetString());

        using var detailResponse = await client.GetAsync(
            "/api/v1/dashboard/evidence/30000000-0000-0000-0000-000000000001" +
            "?context=live&decisionId=40000000-0000-0000-0000-000000000001");
        var detailText = await detailResponse.Content.ReadAsStringAsync();
        using var detail = JsonDocument.Parse(detailText);
        Assert.Equal("restricted", detail.RootElement.GetProperty("evidence").GetProperty("access").GetString());
        Assert.Equal(JsonValueKind.Null, detail.RootElement.GetProperty("evidence").GetProperty("body").ValueKind);
        Assert.DoesNotContain("restricted_feedback_text", detailText, StringComparison.Ordinal);
        Assert.DoesNotContain("metadata", detailText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("payload", detailText, StringComparison.OrdinalIgnoreCase);
    }

    private static string Query(string path, string suffix, string source = DemoSource) =>
        path + $"?context=demo&sourceKey={source}" +
        "&from=2025-01-01T00%3A00%3A00Z&toExclusive=2026-04-01T00%3A00%3A00Z" + suffix;

    private static double ReadMetric(JsonElement root, string id) =>
        root.GetProperty("metrics").EnumerateArray()
            .Single(metric => metric.GetProperty("id").GetString() == id)
            .GetProperty("value").GetDouble();

    private static async Task<JsonDocument> ReadJsonAsync(HttpResponseMessage response) =>
        JsonDocument.Parse(await response.Content.ReadAsStringAsync());

    private sealed class StubLiveFactory(bool empty) : WebApplicationFactory<Program>
    {
        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.ConfigureServices(services =>
            {
                services.RemoveAll<IDashboardDataSource>();
                services.AddSingleton<IDashboardDataSource>(new StubLiveSource(empty));
            });
        }
    }

    private sealed class StubLiveSource(bool empty) : IDashboardDataSource
    {
        private static readonly SourceIdentity Source = new("live/sample/v1", "live", "sample", "v1", "sample (v1)", false);
        public string Context => "live";

        public Task<MetadataResponse> GetMetadataAsync(string? sourceKey, CancellationToken cancellationToken) =>
            Task.FromResult(new MetadataResponse(
                "metadata", "1.0", "live", empty ? null : Source, empty ? [] : [Source],
                empty ? null : new TimeRange(
                    new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero),
                    new DateTimeOffset(2026, 4, 1, 0, 0, 0, TimeSpan.Zero)),
                new Capabilities(true, true, true, true, false), new FilterOptions([], [], [], [], []), "awaiting_calibration"));

        public Task<OverviewResponse> GetOverviewAsync(DashboardQuery query, CancellationToken cancellationToken) =>
            Task.FromResult(new OverviewResponse(
                "overview", "1.0", "live", query.ToFilters(),
                new ProcessingSummary(9, 9, 126, new Dictionary<string, int> { ["succeeded"] = 9 },
                    new Dictionary<string, int> { ["skipped.uncalibrated"] = 9 }),
                [new Metric("analytical_coverage", "Analytical coverage", "percent", null, 0, 9, Availability.Unavailable("uncalibrated"))],
                [], []));

        public Task<SignalResponse?> GetSignalAsync(string signalId, DashboardQuery query, CancellationToken cancellationToken) =>
            Task.FromResult<SignalResponse?>(null);

        public Task<EvidencePageResponse?> GetEvidenceAsync(string signalId, DashboardQuery query, int page, int pageSize, CancellationToken cancellationToken) =>
            Task.FromResult<EvidencePageResponse?>(null);

        public Task<EvidenceDetailResponse?> GetEvidenceDetailAsync(Guid feedbackId, Guid decisionId, CancellationToken cancellationToken)
        {
            var occurredAt = new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
            var row = new EvidenceRow(feedbackId, decisionId, occurredAt, "record-1", "review", null, null, "restricted", "Withheld pending calibration.");
            return Task.FromResult<EvidenceDetailResponse?>(new EvidenceDetailResponse(
                "evidence-detail", "1.0", "live", Source, row,
                new EvidenceContent("restricted", null, null), [],
                new Provenance(decisionId, "schema", "1", "model", null, "awaiting_calibration", Guid.NewGuid(), occurredAt.AddMinutes(1)),
                "Withheld pending calibration."));
        }
    }
}
