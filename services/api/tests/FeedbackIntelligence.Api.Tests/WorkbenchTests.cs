using System.Text.Json;
using FeedbackIntelligence.Api.Workbench;
using Microsoft.AspNetCore.Mvc.Testing;

namespace FeedbackIntelligence.Api.Tests;

public sealed class WorkbenchTests
{
    private static readonly string[] ClientAudience = ["client"];
    [Fact]
    public async Task DefaultDemoDoesNotExposeWorkbenchMutations()
    {
        await using var application = new WebApplicationFactory<Program>();
        using var client = application.CreateClient();
        var state = await client.GetStringAsync("/api/v1/workbench/session");
        Assert.False(JsonDocument.Parse(state).RootElement.GetProperty("enabled").GetBoolean());
        Assert.Equal(System.Net.HttpStatusCode.NotFound, (await client.GetAsync("/api/v1/workbench/datasets")).StatusCode);
    }

    [Theory]
    [InlineData("http://localhost:8081", true)]
    [InlineData("https://localhost:8081", false)]
    [InlineData("http://localhost:8080", false)]
    [InlineData("http://attacker.test:8081", false)]
    [InlineData("null", false)]
    public void WorkbenchRejectsForeignOrigins(string origin, bool allowed)
        => Assert.Equal(allowed, WorkbenchEndpoints.AllowedOrigin(origin, "http://localhost:8081"));

    [Theory]
    [InlineData("wrong", "nonce", "https://auth.openai.com")]
    [InlineData("client", "wrong", "https://auth.openai.com")]
    [InlineData("client", "nonce", "https://attacker.test")]
    public void OauthIdentityRequiresExactAudienceNonceAndIssuer(string audience, string nonce, string issuer)
    {
        var token = JsonSerializer.SerializeToElement(new { iss = issuer, aud = audience, nonce, sub = "subject", exp = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), iat = DateTimeOffset.UtcNow.ToUnixTimeSeconds() });
        Assert.Throws<InvalidOperationException>(() => Connections.ValidateClaims(token, "client", "nonce"));
    }

    [Fact]
    public void OauthIdentityAcceptsAudienceArrayAndRejectsExpiry()
    {
        var token = JsonSerializer.SerializeToElement(new { iss = "https://auth.openai.com", aud = ClientAudience, nonce = "nonce", sub = "subject", email = "owner@example.test", exp = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), iat = DateTimeOffset.UtcNow.ToUnixTimeSeconds() });
        Assert.Equal("subject", Connections.ValidateClaims(token, "client", "nonce").Subject);
        var expired = JsonSerializer.SerializeToElement(new { iss = "https://auth.openai.com", aud = "client", nonce = "nonce", sub = "subject", exp = 1, iat = 1 });
        Assert.Throws<InvalidOperationException>(() => Connections.ValidateClaims(expired, "client", "nonce"));
    }
}
