using System.Text.Json;
using FeedbackIntelligence.Api.Workbench;

namespace FeedbackIntelligence.Api.Tests;

public sealed class ModelCapabilitiesTests
{
    private static readonly string[] Supported = ["low", "medium"];
    private static readonly string[] Invalid = ["ultra"];
    [Theory]
    [InlineData("gpt-6.1-sol", false)]
    [InlineData("gpt-6-astra", false)]
    [InlineData("gpt-6-sol", true)]
    [InlineData("gpt-6-luna", true)]
    [InlineData("gpt-6.1-sol-2026-10-01", false)]
    public void KnownModelsHaveDocumentedEfforts(string model, bool supportsNone)
    {
        var entry = ModelCapabilities.Describe(model, model, JsonSerializer.SerializeToElement(new { }));
        Assert.Equal(supportsNone, entry.reasoningEfforts!.Contains("none"));
        Assert.Contains("max", entry.reasoningEfforts!);
        Assert.DoesNotContain("minimal", entry.reasoningEfforts!);
        Assert.Equal("documented", entry.capabilitySource);
    }

    [Fact]
    public void InvalidAndUnknownEffortsAreRejectedBeforeRunCreation()
    {
        var model = ModelCapabilities.Describe("gpt-6.1-sol", "Sol", JsonSerializer.SerializeToElement(new { }));
        Assert.True(ModelCapabilities.AcceptsEffort(model, JsonSerializer.SerializeToElement("high")));
        Assert.True(ModelCapabilities.AcceptsEffort(model, JsonSerializer.SerializeToElement<string?>(null)));
        Assert.False(ModelCapabilities.AcceptsEffort(model, JsonSerializer.SerializeToElement("none")));
        Assert.False(ModelCapabilities.AcceptsEffort(model, JsonSerializer.SerializeToElement(3)));
        var unknown = ModelCapabilities.Describe("future", "Future", JsonSerializer.SerializeToElement(new { }));
        Assert.False(ModelCapabilities.AcceptsEffort(unknown, JsonSerializer.SerializeToElement("high")));
    }

    [Fact]
    public void FutureModelsRemainDiscoverableAndProviderMetadataTakesPrecedence()
    {
        var unknown = ModelCapabilities.Describe("future", "Future", JsonSerializer.SerializeToElement(new { }));
        Assert.Null(unknown.reasoningEfforts);
        Assert.Equal("future", unknown.slug);
        var provider = JsonSerializer.SerializeToElement(new { supported_reasoning_efforts = Supported });
        Assert.Equal(["low", "medium"], ModelCapabilities.Describe("gpt-6.1-sol", "Sol", provider).reasoningEfforts!);
        var invalid = JsonSerializer.SerializeToElement(new { supported_reasoning_efforts = Invalid });
        Assert.Null(ModelCapabilities.Describe("future", "Future", invalid).reasoningEfforts);
    }
}
