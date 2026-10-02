using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FeedbackIntelligence.Api.Workbench;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Configuration;

namespace FeedbackIntelligence.Api.Tests;

public sealed class WorkbenchConnectionTests
{
    [Fact]
    public async Task OauthRegistrationVerifiesIdentityEncryptsTokensAndRejectsReplay()
    {
        var directory = Path.Combine(Path.GetTempPath(), "workbench-auth-" + Guid.NewGuid());
        Directory.CreateDirectory(directory);
        using var handler = new FakeOpenAi();
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { ["Workbench:VaultPath"] = directory }).Build();
        using var connections = new Connections(DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(directory, "keys"))), config, handler);
        var result = JsonSerializer.SerializeToElement(await connections.Start(null));
        var query = QueryHelpers.ParseQuery(new Uri(result.GetProperty("url").GetString()!).Query);
        Assert.Equal("dynamic_agent_client", query["client_id"]);
        handler.Nonce = query["nonce"].ToString();
        var callback = new QueryCollection(new Dictionary<string, Microsoft.Extensions.Primitives.StringValues> { ["state"] = query["state"], ["client_id"] = "oaiapp_test", ["code"] = "one-time-code" });
        await connections.Complete(callback);
        var list = JsonSerializer.SerializeToElement(connections.List());
        var identity = list[0].GetProperty("id").GetString()!;
        Assert.True(list[0].GetProperty("planEnabled").GetBoolean());
        Assert.Equal("access-secret", await connections.Credential(identity));
        Assert.DoesNotContain("access-secret", File.ReadAllText(Directory.GetFiles(directory, "*.credential").Single()));
        await Assert.ThrowsAsync<InvalidOperationException>(() => connections.Complete(callback));
        var again = JsonSerializer.SerializeToElement(await connections.Start(identity));
        Assert.Equal("oaiapp_test", QueryHelpers.ParseQuery(new Uri(again.GetProperty("url").GetString()!).Query)["client_id"]);
        var models = JsonSerializer.SerializeToElement(await connections.Models(identity));
        Assert.Equal("test-model", models[0].GetProperty("slug").GetString());
        await connections.Disconnect(identity);
        await Assert.ThrowsAsync<InvalidOperationException>(() => connections.Credential(identity));
    }

    [Fact]
    public async Task MissingOrDeclinedScopeNeverAuthorizesPlanUsage()
    {
        var directory = Path.Combine(Path.GetTempPath(), "workbench-auth-" + Guid.NewGuid());
        using var handler = new FakeOpenAi { Scope = "openid profile email" };
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { ["Workbench:VaultPath"] = directory }).Build();
        using var connections = new Connections(DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(directory, "keys"))), config, handler);
        var start = JsonSerializer.SerializeToElement(await connections.Start(null));
        var query = QueryHelpers.ParseQuery(new Uri(start.GetProperty("url").GetString()!).Query);
        handler.Nonce = query["nonce"].ToString();
        await connections.Complete(new QueryCollection(new Dictionary<string, Microsoft.Extensions.Primitives.StringValues> { ["state"] = query["state"], ["client_id"] = "oaiapp_test", ["code"] = "code" }));
        var profiles = JsonSerializer.SerializeToElement(connections.List());
        Assert.False(profiles[0].GetProperty("planEnabled").GetBoolean());
        await Assert.ThrowsAsync<InvalidOperationException>(() => connections.Credential(profiles[0].GetProperty("id").GetString()!));
        await Assert.ThrowsAsync<InvalidOperationException>(() => connections.Complete(new QueryCollection(new Dictionary<string, Microsoft.Extensions.Primitives.StringValues> { ["state"] = "wrong-state" })));
    }

    private sealed class FakeOpenAi : HttpMessageHandler
    {
        private readonly RSA _rsa = RSA.Create(2048);
        public string Nonce { get; set; } = "";
        public string Scope { get; set; } = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct";
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            object response;
            var path = request.RequestUri!.AbsolutePath;
            if (path.EndsWith("jwks.json", StringComparison.Ordinal))
            {
                var key = _rsa.ExportParameters(false);
                response = new { keys = new[] { new { kid = "key", kty = "RSA", n = WebEncoders.Base64UrlEncode(key.Modulus!), e = WebEncoders.Base64UrlEncode(key.Exponent!) } } };
            }
            else if (path.EndsWith("openid-configuration", StringComparison.Ordinal)) response = new { revocation_endpoint = "https://auth.openai.com/revoke" };
            else if (path == "/revoke") return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
            else if (path == "/v1/models") response = new { models = new[] { new { visibility = "list", slug = "test-model", display_name = "Test model" }, new { visibility = "hidden", slug = "hidden-model", display_name = "Hidden" } } };
            else
            {
                var header = WebEncoders.Base64UrlEncode(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { alg = "RS256", kid = "key" })));
                var payload = WebEncoders.Base64UrlEncode(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { iss = "https://auth.openai.com", aud = "oaiapp_test", nonce = Nonce, sub = "owner", email = "owner@example.test", exp = DateTimeOffset.UtcNow.AddHours(1).ToUnixTimeSeconds(), iat = DateTimeOffset.UtcNow.ToUnixTimeSeconds() })));
                var signature = WebEncoders.Base64UrlEncode(_rsa.SignData(Encoding.ASCII.GetBytes(header + "." + payload), HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1));
                response = new { access_token = "access-secret", refresh_token = "refresh-secret", id_token = header + "." + payload + "." + signature, scope = Scope, expires_in = 3600 };
            }
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(response), Encoding.UTF8, "application/json") });
        }
        protected override void Dispose(bool disposing) { if (disposing) _rsa.Dispose(); base.Dispose(disposing); }
    }
}
