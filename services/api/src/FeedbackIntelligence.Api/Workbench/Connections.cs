using System.Collections.Concurrent;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.WebUtilities;

namespace FeedbackIntelligence.Api.Workbench;

public sealed class Connections(IDataProtectionProvider protection, IConfiguration configuration, HttpMessageHandler? handler = null) : IDisposable
{
    private readonly IDataProtector _protector = protection.CreateProtector("workbench.credentials.v1");
    private readonly HttpClient _http = new(handler ?? new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(30) };
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly ConcurrentDictionary<string, Attempt> _attempts = new();
    private readonly string _directory = configuration["Workbench:VaultPath"] ?? "/workbench/vault";
    private const string Issuer = "https://auth.openai.com";
    private const string Resource = "https://api.openai.com/v1";
    public string Callback => configuration["Workbench:Callback"] ?? "http://127.0.0.1:8080/auth/callback";
    private sealed record Attempt(string Nonce, string Verifier, string? ConnectionId, DateTimeOffset Expires);

    public sealed record Profile(string Id, string Mode, string Label, string? Subject, string? ClientId,
        string AccessToken, string? RefreshToken, string? IdToken, string Scope, DateTimeOffset Expires, bool ReconnectRequired = false);

    public static string Random() => WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(32));
    public static bool Equal(string left, string right) => CryptographicOperations.FixedTimeEquals(SHA256.HashData(Encoding.UTF8.GetBytes(left)), SHA256.HashData(Encoding.UTF8.GetBytes(right)));

    private void Save(Profile profile)
    {
        Directory.CreateDirectory(_directory);
        var path = Path.Combine(_directory, $"{Guid.Parse(profile.Id)}.credential");
        var temp = path + ".tmp";
        File.WriteAllText(temp, _protector.Protect(JsonSerializer.Serialize(profile)));
        if (!OperatingSystem.IsWindows()) File.SetUnixFileMode(temp, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        File.Move(temp, path, true);
    }

    private Profile Read(string id) => JsonSerializer.Deserialize<Profile>(_protector.Unprotect(
        File.ReadAllText(Path.Combine(_directory, $"{Guid.Parse(id)}.credential")))) ?? throw new InvalidOperationException("Connection unavailable");
    public string BillingMode(string id) => Read(id).Mode;

    public object[] List()
    {
        if (!Directory.Exists(_directory)) return [];
        return Directory.GetFiles(_directory, "*.credential").Select(path => Read(Path.GetFileNameWithoutExtension(path)))
            .Select(p => (object)new { id = p.Id, mode = p.Mode, label = p.Label, reconnectRequired = p.ReconnectRequired, planEnabled = p.Mode == "chatgpt" && p.Scope.Split(' ').Contains("chatgpt.tokens.use.direct") }).ToArray();
    }

    public async Task<object> ApiKey(string key, string label)
    {
        if (key.Length is < 10 or > 512 || key.Any(char.IsWhiteSpace)) throw new InvalidOperationException("Invalid API key");
        var profile = new Profile(Guid.NewGuid().ToString(), "api", label.Length is > 0 and <= 100 ? label : "OpenAI API", null, null, key, null, null, "", DateTimeOffset.MaxValue);
        await Catalog(profile);
        await _gate.WaitAsync();
        try { Save(profile); }
        finally { _gate.Release(); }
        return new { id = profile.Id, mode = "api", label = profile.Label };
    }

    public async Task<object> Start(string? connectionId)
    {
        var uri = new Uri(Callback);
        if (uri.Scheme != "http" || uri.Host != "127.0.0.1" || uri.AbsolutePath != "/auth/callback") throw new InvalidOperationException("Callback must be an HTTP 127.0.0.1 loopback /auth/callback URL");
        await _gate.WaitAsync();
        try
        {
            Directory.CreateDirectory(_directory);
            var hostPath = Path.Combine(_directory, "host-id");
            if (!File.Exists(hostPath)) File.WriteAllText(hostPath, $"urn:uuid:{Guid.NewGuid()}");
            var previous = connectionId is null ? null : Read(connectionId);
            if (previous is not null && previous.Mode != "chatgpt") throw new InvalidOperationException("Select a ChatGPT connection");
            foreach (var entry in _attempts.Where(p => p.Value.Expires < DateTimeOffset.UtcNow)) _attempts.TryRemove(entry.Key, out _);
            var state = Random();
            var attempt = new Attempt(Random(), Random(), connectionId, DateTimeOffset.UtcNow.AddMinutes(10));
            _attempts[state] = attempt;
            var parameters = new Dictionary<string, string?>
            {
                ["client_id"] = previous?.ClientId ?? "dynamic_agent_client",
                ["ext_agent_host_id"] = File.ReadAllText(hostPath),
                ["response_type"] = "code",
                ["redirect_uri"] = Callback,
                ["resource"] = Resource,
                ["scope"] = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct",
                ["state"] = state,
                ["nonce"] = attempt.Nonce,
                ["code_challenge_method"] = "S256",
                ["code_challenge"] = WebEncoders.Base64UrlEncode(SHA256.HashData(Encoding.ASCII.GetBytes(attempt.Verifier)))
            };
            if (previous is null) parameters["agent_name_hint"] = "Feedback Intelligence";
            else if (previous.IdToken is not null) parameters["id_token_hint"] = previous.IdToken;
            return new { url = QueryHelpers.AddQueryString(Issuer + "/api/accounts/authorize", parameters) };
        }
        finally { _gate.Release(); }
    }

    public async Task<string> Complete(IQueryCollection query)
    {
        if (!_attempts.TryRemove(query["state"].ToString(), out var attempt) || attempt.Expires < DateTimeOffset.UtcNow)
            throw new InvalidOperationException("Sign-in expired or could not be verified");
        if (query.ContainsKey("error") || !query.ContainsKey("code")) throw new InvalidOperationException("Sign-in was declined");
        await _gate.WaitAsync();
        try
        {
            var previous = attempt.ConnectionId is null ? null : Read(attempt.ConnectionId);
            var clientId = query["client_id"].ToString();
            if (previous is not null)
            {
                if (clientId.Length > 0 && clientId != previous.ClientId) throw new InvalidOperationException("Account registration mismatch");
                clientId = previous.ClientId!;
            }
            if (!clientId.StartsWith("oaiapp_", StringComparison.Ordinal)) throw new InvalidOperationException("Registration did not issue a client ID");
            // Persist issued registration before code exchange so invalid_grant can reauthorize it.
            var registration = previous ?? new Profile(Guid.NewGuid().ToString(), "chatgpt", "ChatGPT registration pending", null, clientId, "", null, null, "", DateTimeOffset.MinValue);
            Save(registration);
            var data = await Token(new()
            {
                ["grant_type"] = "authorization_code",
                ["client_id"] = clientId,
                ["code"] = query["code"].ToString(),
                ["code_verifier"] = attempt.Verifier,
                ["redirect_uri"] = Callback,
                ["resource"] = Resource
            });
            var identity = await VerifyIdentity(data.GetProperty("id_token").GetString()!, clientId, attempt.Nonce);
            if (previous?.Subject is not null && previous.Subject != identity.Subject) throw new InvalidOperationException("Signed-in account differs from selected registration");
            var profile = registration with
            {
                Label = identity.Email + " · " + clientId[^6..],
                Subject = identity.Subject,
                ReconnectRequired = false,
                AccessToken = data.TryGetProperty("access_token", out var access) ? access.GetString() ?? "" : "",
                RefreshToken = data.TryGetProperty("refresh_token", out var refresh) ? refresh.GetString() : null,
                IdToken = data.GetProperty("id_token").GetString(),
                Scope = data.TryGetProperty("scope", out var scopes) ? scopes.GetString() ?? "" : "",
                Expires = DateTimeOffset.UtcNow.AddSeconds(data.TryGetProperty("expires_in", out var lifetime) ? lifetime.GetDouble() : 0)
            };
            Save(profile);
            return profile.Scope.Split(' ').Contains("chatgpt.tokens.use.direct")
                ? previous?.Subject is null ? "plan" : "reconnected" : "identity";
        }
        finally { _gate.Release(); }
    }

    public static (string Subject, string Email) ValidateClaims(JsonElement claims, string clientId, string nonce)
    {
        var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var audience = claims.GetProperty("aud");
        var matches = audience.ValueKind == JsonValueKind.Array ? audience.EnumerateArray().Any(a => a.GetString() == clientId) : audience.GetString() == clientId;
        if (claims.GetProperty("iss").GetString() != Issuer || !matches || claims.GetProperty("exp").GetInt64() <= now
            || claims.GetProperty("iat").GetInt64() > now + 60 || !Equal(claims.GetProperty("nonce").GetString() ?? "", nonce))
            throw new InvalidOperationException("Identity token claims are invalid");
        if (claims.TryGetProperty("nbf", out var notBefore) && notBefore.GetInt64() > now + 60)
            throw new InvalidOperationException("Identity token is not yet valid");
        if (audience.ValueKind == JsonValueKind.Array && audience.GetArrayLength() > 1
            && (!claims.TryGetProperty("azp", out var party) || party.GetString() != clientId))
            throw new InvalidOperationException("Identity token authorized party is invalid");
        var subject = claims.GetProperty("sub").GetString();
        if (string.IsNullOrWhiteSpace(subject)) throw new InvalidOperationException("Identity has no subject");
        return (subject, claims.TryGetProperty("email", out var email) ? email.GetString() ?? "ChatGPT account" : "ChatGPT account");
    }

    private async Task<(string Subject, string Email)> VerifyIdentity(string token, string clientId, string nonce)
    {
        var parts = token.Split('.');
        if (parts.Length != 3) throw new InvalidOperationException("Invalid identity token");
        var header = JsonDocument.Parse(WebEncoders.Base64UrlDecode(parts[0])).RootElement;
        if (header.GetProperty("alg").GetString() != "RS256" || header.TryGetProperty("crit", out _)) throw new InvalidOperationException("Unsupported identity signature");
        var jwks = await _http.GetFromJsonAsync<JsonElement>(Issuer + "/.well-known/jwks.json");
        var key = jwks.GetProperty("keys").EnumerateArray().Single(k => k.GetProperty("kid").GetString() == header.GetProperty("kid").GetString() && k.GetProperty("kty").GetString() == "RSA");
        using var rsa = RSA.Create();
        rsa.ImportParameters(new RSAParameters { Modulus = WebEncoders.Base64UrlDecode(key.GetProperty("n").GetString()!), Exponent = WebEncoders.Base64UrlDecode(key.GetProperty("e").GetString()!) });
        if (!rsa.VerifyData(Encoding.ASCII.GetBytes(parts[0] + "." + parts[1]), WebEncoders.Base64UrlDecode(parts[2]), HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1)) throw new InvalidOperationException("Invalid identity signature");
        return ValidateClaims(JsonDocument.Parse(WebEncoders.Base64UrlDecode(parts[1])).RootElement, clientId, nonce);
    }

    private async Task<JsonElement> Token(Dictionary<string, string> fields)
    {
        using var response = await _http.PostAsync(Issuer + "/api/accounts/oauth/token", new FormUrlEncodedContent(fields));
        if (!response.IsSuccessStatusCode)
        {
            var code = "unknown";
            try
            {
                var failure = JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement;
                if (failure.TryGetProperty("error", out var error))
                {
                    var value = error.ValueKind == JsonValueKind.String ? error.GetString() : error.ValueKind == JsonValueKind.Object && error.TryGetProperty("code", out var nested) && nested.ValueKind == JsonValueKind.String ? nested.GetString() : null;
                    if (value is "invalid_grant" or "invalid_client" or "invalid_request" or "invalid_target" or "invalid_refresh_token" or "token_expired" or "refresh_token_expired" or "refresh_token_invalidated" or "refresh_token_reused") code = value;
                }
            }
            catch (JsonException) { }
            var reconnect = code is "invalid_grant" or "invalid_refresh_token" or "token_expired" or "refresh_token_expired" or "refresh_token_invalidated" or "refresh_token_reused";
            throw new ConnectionFailureException("connection_renewal_" + code, $"OpenAI connection renewal failed (HTTP {(int)response.StatusCode}; {code}). " + (reconnect ? "Reconnect this account in Connections." : "Check the connection configuration or retry a temporary failure."), reconnect);
        }
        return JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement.Clone();
    }

    public async Task<string> Credential(string id)
    {
        await _gate.WaitAsync();
        try
        {
            var profile = Read(id);
            if (profile.ReconnectRequired) throw new ConnectionFailureException("reconnect_required", "The saved ChatGPT session cannot be renewed. Reconnect this account in Connections.", true);
            if (profile.Mode == "chatgpt" && !profile.Scope.Split(' ').Contains("chatgpt.tokens.use.direct")) throw new InvalidOperationException("ChatGPT plan usage permission is not enabled");
            if (profile.Mode == "chatgpt" && profile.Expires < DateTimeOffset.UtcNow.AddMinutes(1))
            {
                if (profile.RefreshToken is null) throw new ConnectionFailureException("reconnect_required", "Reconnect your ChatGPT account in Connections.", true);
                JsonElement data;
                try
                {
                    data = await Token(new() { ["grant_type"] = "refresh_token", ["client_id"] = profile.ClientId!, ["refresh_token"] = profile.RefreshToken, ["resource"] = Resource });
                }
                catch (ConnectionFailureException error) when (error.Reconnect)
                {
                    Save(profile with { AccessToken = "", RefreshToken = null, Expires = DateTimeOffset.MinValue, ReconnectRequired = true });
                    throw;
                }
                profile = profile with
                {
                    AccessToken = data.GetProperty("access_token").GetString()!,
                    RefreshToken = data.TryGetProperty("refresh_token", out var refresh) ? refresh.GetString() : profile.RefreshToken,
                    Expires = DateTimeOffset.UtcNow.AddSeconds(data.GetProperty("expires_in").GetDouble())
                };
                Save(profile);
            }
            if (string.IsNullOrEmpty(profile.AccessToken)) throw new InvalidOperationException("Connection is incomplete");
            return profile.AccessToken;
        }
        finally { _gate.Release(); }
    }

    public async Task<ModelCatalogEntry[]> Models(string id) => await Catalog(Read(id) with { AccessToken = await Credential(id) });

    private async Task<ModelCatalogEntry[]> Catalog(Profile profile)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, Resource + "/models");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", profile.AccessToken);
        using var response = await _http.SendAsync(request);
        if (!response.IsSuccessStatusCode) throw new ConnectionFailureException("catalog_unavailable", $"OpenAI model catalog is unavailable (HTTP {(int)response.StatusCode}). " + (response.StatusCode == System.Net.HttpStatusCode.Unauthorized ? "Reconnect this account in Connections." : response.StatusCode == System.Net.HttpStatusCode.Forbidden ? "Check this account's permissions and eligibility in Connections." : "Try Refresh models again shortly."), response.StatusCode == System.Net.HttpStatusCode.Unauthorized);
        var data = JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement;
        if (profile.Mode == "chatgpt" && !data.TryGetProperty("models", out _)) throw new ConnectionFailureException("catalog_format", "OpenAI returned a model catalog format the local runtime could not read.");
        if (profile.Mode == "chatgpt") return data.GetProperty("models").EnumerateArray().Where(m => m.GetProperty("visibility").GetString() == "list")
            .Select(m => ModelCapabilities.Describe(m.GetProperty("slug").GetString()!, m.GetProperty("display_name").GetString()!, m)).ToArray();
        return data.GetProperty("data").EnumerateArray().Where(m =>
        {
            var name = m.GetProperty("id").GetString() ?? "";
            return (name.StartsWith("gpt-", StringComparison.Ordinal) || name.StartsWith('o')) && !name.Contains("image", StringComparison.Ordinal) && !name.Contains("audio", StringComparison.Ordinal) && !name.Contains("realtime", StringComparison.Ordinal);
        }).Select(m => ModelCapabilities.Describe(m.GetProperty("id").GetString()!, m.GetProperty("id").GetString()!, m)).ToArray();
    }

    public async Task<bool> Disconnect(string id)
    {
        await _gate.WaitAsync();
        try
        {
            var profile = Read(id);
            // Stop local credential use even if the remote revocation service is unavailable.
            Save(profile with { AccessToken = "", RefreshToken = null, IdToken = null, Scope = "", Expires = DateTimeOffset.MinValue });
            var confirmed = true;
            if (profile.RefreshToken is not null)
            {
                try
                {
                    var discovery = await _http.GetFromJsonAsync<JsonElement>(Issuer + "/.well-known/openid-configuration");
                    var endpoint = discovery.GetProperty("revocation_endpoint").GetString()!;
                    if (new Uri(endpoint).GetLeftPart(UriPartial.Authority) != Issuer) throw new InvalidOperationException("Invalid revocation endpoint");
                    using var response = await _http.PostAsync(endpoint, new FormUrlEncodedContent(new Dictionary<string, string> { ["token"] = profile.RefreshToken, ["token_type_hint"] = "refresh_token", ["client_id"] = profile.ClientId! }));
                    confirmed = response.IsSuccessStatusCode;
                }
                catch (Exception error) when (error is HttpRequestException or TaskCanceledException or JsonException or InvalidOperationException)
                { confirmed = false; }
            }
            return confirmed;
        }
        finally { _gate.Release(); }
    }

    public void Dispose() { _http.Dispose(); _gate.Dispose(); }
}
