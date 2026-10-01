using System.Text.Json;
using FeedbackIntelligence.Api.Workbench;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;

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

    [Fact]
    public async Task FailedCallbackReturnsOnlyAnAppOwnedErrorFlag()
    {
        var directory = Path.Combine(Path.GetTempPath(), "workbench-callback-" + Guid.NewGuid());
        await using var application = new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.ConfigureAppConfiguration((_, configuration) => configuration.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Workbench:Enabled"] = "true",
                ["Workbench:Origin"] = "http://localhost:8081",
                ["Workbench:VaultPath"] = Path.Combine(directory, "vault"),
                ["Workbench:KeysPath"] = Path.Combine(directory, "keys")
            }));
            builder.ConfigureServices((context, services) => services.AddWorkbench(context.Configuration));
        });
        using var client = application.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false });
        var response = await client.GetAsync("/auth/callback?state=invalid&code=private-code&error=private-description");
        Assert.Equal(System.Net.HttpStatusCode.Redirect, response.StatusCode);
        Assert.Equal("http://localhost:8081/?connection=error#workbench", response.Headers.Location!.OriginalString);
        Assert.Empty(await response.Content.ReadAsStringAsync());
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
