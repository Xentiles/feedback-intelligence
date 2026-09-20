using System.Net;
using System.Text.Json;
using FeedbackIntelligence.Api.Dashboard;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace FeedbackIntelligence.Api.Tests;

public sealed class TrendEndpointTests : IClassFixture<WebApplicationFactory<Program>>
{
    private static readonly string[] ExpectedIncidentOutcomes =
        ["delivery_delay_increase", "product_defect_noise_increase", "return_unresolved_increase", "support_praise_increase"];

    private readonly HttpClient _client;
    private readonly WebApplicationFactory<Program> _factory;

    public TrendEndpointTests(WebApplicationFactory<Program> factory)
    {
        _factory = factory;
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task DemoTrendsExposeTypedMethodAndCoherentEvaluation()
    {
        using var response = await _client.GetAsync("/api/v1/dashboard/trends?context=demo");
        var text = await response.Content.ReadAsStringAsync();
        using var json = JsonDocument.Parse(text);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var root = json.RootElement;
        Assert.Equal("trend-overview", root.GetProperty("kind").GetString());
        Assert.Equal("available", root.GetProperty("availability").GetProperty("state").GetString());
        Assert.True(root.GetProperty("source").GetProperty("synthetic").GetBoolean());

        var method = root.GetProperty("method");
        Assert.Equal("simple_rate_change", method.GetProperty("id").GetString());
        Assert.Equal(7, method.GetProperty("currentWindowDays").GetInt32());
        Assert.Equal(28, method.GetProperty("baselineWindowDays").GetInt32());
        Assert.Equal(20, method.GetProperty("minimumCurrentDenominator").GetInt32());
        Assert.Equal(50, method.GetProperty("minimumBaselineDenominator").GetInt32());
        Assert.Equal(3, method.GetProperty("minimumCurrentNumerator").GetInt32());
        Assert.Equal("emerging_signal_not_statistical_significance", method.GetProperty("claim").GetString());
        Assert.DoesNotContain("statistically significant", text, StringComparison.OrdinalIgnoreCase);

        var series = root.GetProperty("series").EnumerateArray().ToDictionary(
            item => item.GetProperty("seriesId").GetString()!);
        var results = root.GetProperty("results").EnumerateArray().ToArray();
        Assert.NotEmpty(results);

        foreach (var result in results)
        {
            var current = result.GetProperty("current");
            var baseline = result.GetProperty("baseline");
            AssertRateIsCoherent(current);
            AssertRateIsCoherent(baseline);
            AssertWindowDays(current.GetProperty("range"), 7);
            AssertWindowDays(baseline.GetProperty("range"), 28);
            Assert.Equal(
                baseline.GetProperty("range").GetProperty("toExclusive").GetDateTimeOffset(),
                current.GetProperty("range").GetProperty("from").GetDateTimeOffset());
            Assert.Equal(
                current.GetProperty("range").GetProperty("toExclusive").GetDateTimeOffset(),
                result.GetProperty("anchor").GetDateTimeOffset());

            var currentRate = current.GetProperty("rate").GetDouble();
            var baselineRate = baseline.GetProperty("rate").GetDouble();
            Assert.Equal(currentRate - baselineRate, result.GetProperty("deltaPoints").GetDouble(), 6);
            Assert.Equal(currentRate / baselineRate, result.GetProperty("rateRatio").GetDouble(), 6);
            Assert.Equal(
                (currentRate / baselineRate - 1) * 100,
                result.GetProperty("relativeChangePercent").GetDouble(),
                6);

            if (result.GetProperty("state").GetString() == "emerging_signal")
            {
                AssertEmergingGatesHold(result, series[result.GetProperty("seriesId").GetString()!], method);
            }
        }
    }

    [Fact]
    public async Task DemoTrendsIncludeAllFourSyntheticIncidentOutcomes()
    {
        using var response = await _client.GetAsync("/api/v1/dashboard/trends?context=demo");
        using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync());

        var incidents = json.RootElement.GetProperty("incidents").EnumerateArray().ToArray();
        Assert.Equal(4, incidents.Length);
        Assert.Equal(
            ExpectedIncidentOutcomes,
            incidents.Select(item => item.GetProperty("outcome").GetString()!).Order().ToArray());
        Assert.All(incidents, incident =>
        {
            Assert.StartsWith("synthetic-incident-", incident.GetProperty("incidentId").GetString());
            Assert.True(incident.GetProperty("detected").GetBoolean());
            Assert.NotEqual(JsonValueKind.Null, incident.GetProperty("matchedEvaluationId").ValueKind);
        });

        var summary = json.RootElement.GetProperty("summary");
        Assert.Equal(4, summary.GetProperty("plantedIncidentCount").GetInt32());
        Assert.Equal(13, summary.GetProperty("alertEpisodeCount").GetInt32());
        Assert.Equal(1.0, summary.GetProperty("recall").GetDouble());
        Assert.Equal(4.0 / 13.0, summary.GetProperty("precision").GetDouble(), 12);
        Assert.Equal(6.5, summary.GetProperty("medianDetectionDelayDays").GetDouble());
        Assert.Equal(0.5408653846153846, summary.GetProperty("falseAlertEpisodesPer100SeriesDays").GetDouble(), 12);
    }

    [Fact]
    public async Task LiveTrendsRemainUnavailableWithoutLeakingEvaluationOrRawEvidence()
    {
        using var response = await _client.GetAsync("/api/v1/dashboard/trends?context=live");
        var text = await response.Content.ReadAsStringAsync();
        using var json = JsonDocument.Parse(text);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var root = json.RootElement;
        Assert.Equal("live", root.GetProperty("context").GetString());
        Assert.Equal("unavailable", root.GetProperty("availability").GetProperty("state").GetString());
        Assert.Equal("awaiting_calibration", root.GetProperty("availability").GetProperty("reason").GetString());
        Assert.Equal(JsonValueKind.Null, root.GetProperty("source").ValueKind);
        Assert.Equal(JsonValueKind.Null, root.GetProperty("summary").ValueKind);
        Assert.Empty(root.GetProperty("series").EnumerateArray());
        Assert.Empty(root.GetProperty("results").EnumerateArray());
        Assert.Empty(root.GetProperty("incidents").EnumerateArray());
        Assert.DoesNotContain("scenario", text, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("rawText", text, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("excerpt", text, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("body", text, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UnknownDemoTrendSourceReturnsProblemDetails()
    {
        using var response = await _client.GetAsync(
            "/api/v1/dashboard/trends?context=demo&sourceKey=synthetic%2Funknown%2Fv1");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
    }

    [Fact]
    public void TrendAlgorithmConfigurationParsesToTheTypedSelection()
    {
        var selected = TrendAlgorithmKindExtensions.ParseConfigurationValue(
            "simple_rate_change");

        Assert.Equal(TrendAlgorithmKind.SimpleRateChange, selected);
        Assert.Equal("simple_rate_change", selected.ToConfigurationValue());
    }

    [Fact]
    public async Task StatisticalCandidateCanBeSelectedWithTypedConfiguration()
    {
        using var client = _factory.WithWebHostBuilder(builder =>
            builder.UseSetting("Trend:Algorithm", "candidate_statistical")).CreateClient();

        using var response = await client.GetAsync("/api/v1/dashboard/trends?context=demo");
        using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync());

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var method = json.RootElement.GetProperty("method");
        Assert.Equal("candidate_statistical", method.GetProperty("id").GetString());
        Assert.Equal(0.98, method.GetProperty("minimumProbabilityOfDirection").GetDouble());
        Assert.Equal(1, method.GetProperty("betaPriorAlpha").GetInt32());
        Assert.Equal(11, json.RootElement.GetProperty("summary").GetProperty("alertEpisodeCount").GetInt32());
        Assert.All(json.RootElement.GetProperty("results").EnumerateArray(), result =>
            Assert.True(result.GetProperty("probabilityOfDirection").GetDouble() >= 0.98));
    }

    [Fact]
    public void StatisticalTrendAlgorithmConfigurationParsesToTheTypedSelection()
    {
        var selected = TrendAlgorithmKindExtensions.ParseConfigurationValue(
            "candidate_statistical");

        Assert.Equal(TrendAlgorithmKind.CandidateStatistical, selected);
        Assert.Equal("candidate_statistical", selected.ToConfigurationValue());
    }

    [Fact]
    public void UnknownTrendAlgorithmConfigurationFailsFast()
    {
        var error = Assert.Throws<InvalidOperationException>(() =>
            TrendAlgorithmKindExtensions.ParseConfigurationValue("magic_detector"));

        Assert.Contains("Trend:Algorithm", error.Message, StringComparison.Ordinal);
    }

    private static void AssertRateIsCoherent(JsonElement window)
    {
        var numerator = window.GetProperty("numerator").GetInt32();
        var denominator = window.GetProperty("denominator").GetInt32();
        var expected = numerator / (double)denominator * 100;
        Assert.Equal(expected, window.GetProperty("rate").GetDouble(), 6);
    }

    private static void AssertWindowDays(JsonElement range, int days)
    {
        var from = range.GetProperty("from").GetDateTimeOffset();
        var toExclusive = range.GetProperty("toExclusive").GetDateTimeOffset();
        Assert.Equal(TimeSpan.FromDays(days), toExclusive - from);
    }

    private static void AssertEmergingGatesHold(
        JsonElement result,
        JsonElement series,
        JsonElement method)
    {
        var current = result.GetProperty("current");
        var baseline = result.GetProperty("baseline");
        var delta = result.GetProperty("deltaPoints").GetDouble();
        var relative = result.GetProperty("relativeChangePercent").GetDouble();
        Assert.True(current.GetProperty("denominator").GetInt32() >= method.GetProperty("minimumCurrentDenominator").GetInt32());
        Assert.True(baseline.GetProperty("denominator").GetInt32() >= method.GetProperty("minimumBaselineDenominator").GetInt32());
        Assert.True(current.GetProperty("numerator").GetInt32() >= method.GetProperty("minimumCurrentNumerator").GetInt32());
        Assert.True(Math.Abs(delta) >= method.GetProperty("minimumAbsoluteDeltaPoints").GetDouble());
        Assert.True(Math.Abs(relative) >= method.GetProperty("minimumRelativeChangePercent").GetDouble());
        Assert.True(series.GetProperty("direction").GetString() == "increase" ? delta > 0 : delta < 0);
        Assert.DoesNotContain(
            result.GetProperty("gateReasons").EnumerateArray().Select(reason => reason.GetString()),
            reason => reason?.Contains("below_minimum", StringComparison.Ordinal) == true);
    }
}
