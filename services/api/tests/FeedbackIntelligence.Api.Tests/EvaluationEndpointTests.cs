using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc.Testing;

namespace FeedbackIntelligence.Api.Tests;

public sealed class EvaluationEndpointTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;

    public EvaluationEndpointTests(WebApplicationFactory<Program> factory)
    {
        _client = factory.CreateClient();
    }

    [Fact]
    public async Task DemoEvaluationExposesMeasuredAiReferenceComparison()
    {
        using var response = await _client.GetAsync("/api/v1/dashboard/evaluation?context=demo");
        using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync());

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var root = json.RootElement;
        Assert.Equal("evaluation-comparison", root.GetProperty("kind").GetString());
        Assert.Equal("demo", root.GetProperty("context").GetString());
        Assert.Equal("available", root.GetProperty("availability").GetProperty("state").GetString());
        Assert.Equal("complete", root.GetProperty("status").GetString());
        Assert.Equal(480, root.GetProperty("recordCount").GetInt32());
        Assert.Equal(480, root.GetProperty("successCount").GetInt32());
        Assert.Equal(0, root.GetProperty("errorCount").GetInt32());
        Assert.Equal("ai_reviewed_not_human_gold", root.GetProperty("reference").GetProperty("kind").GetString());
        Assert.Equal("gpt-5.6-sol", root.GetProperty("reference").GetProperty("model").GetString());
        Assert.Equal("medium", root.GetProperty("reference").GetProperty("reasoning").GetString());
        Assert.Equal("semif-qwen3.5-4b-mlx-q4-851bf6e8",
            root.GetProperty("semif").GetProperty("requestedModel").GetString());
        Assert.InRange(root.GetProperty("semifPrimaryTopic").GetProperty("macroF1").GetDouble(), 0, 1);
        Assert.InRange(root.GetProperty("semifPrimaryTopic").GetProperty("accuracy").GetDouble(), 0, 1);
        Assert.Equal("rules-1.0.0", root.GetProperty("rules").GetProperty("requestedModel").GetString());
        Assert.Equal(0.9987936390814087, root.GetProperty("rulePrimaryTopic").GetProperty("macroF1").GetDouble());
        Assert.Equal(0.9979166666666667, root.GetProperty("rulePrimaryTopic").GetProperty("accuracy").GetDouble());
        Assert.Equal(2, root.GetProperty("semifLanguageSlices").GetArrayLength());
        Assert.Equal(2, root.GetProperty("ruleLanguageSlices").GetArrayLength());
        Assert.Equal("gpt-5.4-mini-2026-03-17", root.GetProperty("llm").GetProperty("requestedModel").GetString());
        Assert.Equal("measured_complete", root.GetProperty("semifCost").GetProperty("status").GetString());
        Assert.True(root.GetProperty("semifCost").GetProperty("tokens").GetInt64() > 0);
        Assert.Equal(0, root.GetProperty("semifCost").GetProperty("costUsd").GetDouble());
        Assert.Equal(480, root.GetProperty("semifCost").GetProperty("successfulRecords").GetInt32());
        Assert.Equal("closed_partial", root.GetProperty("llmCost").GetProperty("status").GetString());
        Assert.Equal(192, root.GetProperty("llmCost").GetProperty("successfulRecords").GetInt32());
        Assert.Equal(477777, root.GetProperty("llmCost").GetProperty("tokens").GetInt64());
        Assert.Equal(0.39, root.GetProperty("llmCost").GetProperty("costUsd").GetDouble());
        Assert.Equal(0.98, root.GetProperty("llmCost").GetProperty("estimatedTargetCostUsd").GetDouble());
        Assert.Equal(2, root.GetProperty("llmLanguageSlices").GetArrayLength());
        Assert.Equal(125, root.GetProperty("llmLanguageSlices")[0].GetProperty("successCount").GetInt32());
        Assert.Equal(0.782838358729344, root.GetProperty("llmPrimaryTopic").GetProperty("macroF1").GetDouble());
        Assert.Equal(0.8489583333333334, root.GetProperty("llmPrimaryTopic").GetProperty("accuracy").GetDouble());
    }

    [Fact]
    public async Task LiveEvaluationWaitsForHumanLabelsWithoutDemoResults()
    {
        using var response = await _client.GetAsync("/api/v1/dashboard/evaluation?context=live");
        var text = await response.Content.ReadAsStringAsync();
        using var json = JsonDocument.Parse(text);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var root = json.RootElement;
        Assert.Equal("unavailable", root.GetProperty("availability").GetProperty("state").GetString());
        Assert.Equal("awaiting_human_labels", root.GetProperty("availability").GetProperty("reason").GetString());
        Assert.Equal("awaiting_human_labels", root.GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.Null, root.GetProperty("reference").ValueKind);
        Assert.Equal(JsonValueKind.Null, root.GetProperty("semif").ValueKind);
        Assert.Equal(JsonValueKind.Null, root.GetProperty("semifPrimaryTopic").ValueKind);
        Assert.Equal(JsonValueKind.Null, root.GetProperty("rules").ValueKind);
        Assert.Equal(JsonValueKind.Null, root.GetProperty("rulePrimaryTopic").ValueKind);
        Assert.Equal(JsonValueKind.Null, root.GetProperty("llm").ValueKind);
        Assert.Equal(JsonValueKind.Null, root.GetProperty("semifCost").ValueKind);
        Assert.Equal(JsonValueKind.Null, root.GetProperty("llmCost").ValueKind);
        Assert.Empty(root.GetProperty("llmLanguageSlices").EnumerateArray());
        Assert.Equal(JsonValueKind.Null, root.GetProperty("llmPrimaryTopic").ValueKind);
        Assert.Empty(root.GetProperty("semifLanguageSlices").EnumerateArray());
        Assert.Empty(root.GetProperty("ruleLanguageSlices").EnumerateArray());
        Assert.DoesNotContain("gpt-5.6-sol", text, StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData("")]
    [InlineData("unknown")]
    public async Task EvaluationRequiresKnownContext(string context)
    {
        using var response = await _client.GetAsync($"/api/v1/dashboard/evaluation?context={context}");
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
    }
}
