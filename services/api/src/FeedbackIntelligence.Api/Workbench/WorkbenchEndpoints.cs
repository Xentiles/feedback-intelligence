using System.Collections.Concurrent;
using System.Net.Http.Headers;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Npgsql;

namespace FeedbackIntelligence.Api.Workbench;

public static class WorkbenchEndpoints
{
    private static readonly ConcurrentDictionary<string, (string Csrf, DateTimeOffset Expires)> Sessions = new();
    private static string Secret(IConfiguration configuration, string name) => File.ReadAllText(configuration[$"Workbench:{name}File"] ?? throw new InvalidOperationException("Workbench has not been initialized")).Trim();

    public static void AddWorkbench(this IServiceCollection services, IConfiguration configuration)
    {
        services.AddDataProtection().PersistKeysToFileSystem(new DirectoryInfo(configuration["Workbench:KeysPath"] ?? "/workbench/keys"));
        services.AddSingleton<Connections>();
        services.AddHttpClient("workbench", client => { client.BaseAddress = new Uri(configuration["Workbench:WorkerUrl"] ?? "http://workbench-worker:8090"); client.Timeout = TimeSpan.FromSeconds(90); }).RemoveAllLoggers();
    }

    public static bool AllowedOrigin(string? origin, string configured)
    {
        if (!Uri.TryCreate(origin, UriKind.Absolute, out var actual) || !Uri.TryCreate(configured, UriKind.Absolute, out var expected)) return false;
        return actual.Scheme == expected.Scheme && actual.Port == expected.Port && actual.Host == expected.Host;
    }

    public static void MapWorkbench(this WebApplication app)
    {
        var config = app.Configuration;
        var enabled = config.GetValue<bool>("Workbench:Enabled");
        app.MapGet("/api/v1/workbench/session", (HttpContext context) =>
        {
            context.Response.Headers.CacheControl = "no-store";
            var authenticated = context.Request.Cookies.TryGetValue("workbench-session", out var id) && Sessions.TryGetValue(id, out var session) && session.Expires > DateTimeOffset.UtcNow;
            return Results.Json(new { enabled, authenticated, csrf = authenticated ? Sessions[id!].Csrf : null });
        });
        if (!enabled) return;
        app.MapPost("/api/v1/workbench/session", async (HttpContext context) =>
        {
            if (!AllowedOrigin(context.Request.Headers.Origin, config["Workbench:Origin"] ?? "http://localhost:8080")) return Results.StatusCode(403);
            var body = await context.Request.ReadFromJsonAsync<JsonElement>();
            if (body.ValueKind != JsonValueKind.Object || !body.TryGetProperty("code", out var ownerCode) || ownerCode.ValueKind != JsonValueKind.String) return Results.BadRequest();
            if (!Connections.Equal(body.GetProperty("code").GetString() ?? "", Secret(config, "OwnerCode"))) return Results.Unauthorized();
            foreach (var entry in Sessions.Where(p => p.Value.Expires <= DateTimeOffset.UtcNow)) Sessions.TryRemove(entry.Key, out _);
            var id = Connections.Random();
            var csrf = Connections.Random();
            Sessions[id] = (csrf, DateTimeOffset.UtcNow.AddHours(12));
            context.Response.Cookies.Append("workbench-session", id, new CookieOptions { HttpOnly = true, SameSite = SameSiteMode.Strict, Secure = context.Request.IsHttps, Path = "/api/v1/workbench", MaxAge = TimeSpan.FromHours(12) });
            context.Response.Headers.CacheControl = "no-store";
            return Results.Json(new { authenticated = true, csrf });
        }).RequireRateLimiting("ingestion");

        app.MapMethods("/api/v1/workbench/{**path}", ["GET", "POST", "DELETE"], async (HttpContext context, string path, Connections connections, IHttpClientFactory clients) =>
        {
            context.Response.Headers.CacheControl = "no-store";
            if (!context.Request.Cookies.TryGetValue("workbench-session", out var id) || !Sessions.TryGetValue(id, out var session) || session.Expires <= DateTimeOffset.UtcNow) return Results.Unauthorized();
            if (context.Request.Method != "GET" && (!AllowedOrigin(context.Request.Headers.Origin, config["Workbench:Origin"] ?? "http://localhost:8080") || !Connections.Equal(context.Request.Headers["X-Workbench-CSRF"].ToString(), session.Csrf))) return Results.StatusCode(403);
            try
            {
                JsonElement body = JsonSerializer.SerializeToElement(new { });
                if (context.Request.Method == "POST") body = await context.Request.ReadFromJsonAsync<JsonElement>();
                if (body.ValueKind != JsonValueKind.Object) return Results.BadRequest();
                if (path == "session" && context.Request.Method == "DELETE") { Sessions.TryRemove(id, out _); context.Response.Cookies.Delete("workbench-session", new CookieOptions { Path = "/api/v1/workbench" }); return Results.Ok(); }
                if (path == "connections" && context.Request.Method == "GET") return Results.Json(connections.List());
                if (path == "connections/api-key" && context.Request.Method == "POST") return Results.Json(await connections.ApiKey(body.GetProperty("key").GetString()!, body.GetProperty("label").GetString()!));
                if (path == "connections/chatgpt" && context.Request.Method == "POST") return Results.Json(await connections.Start(body.TryGetProperty("connectionId", out var existing) ? existing.GetString() : null));
                var parts = path.Split('/');
                if (parts.Length == 3 && parts[0] == "connections" && parts[2] == "models" && context.Request.Method == "GET") return Results.Json(await connections.Models(parts[1]));
                if (parts.Length == 2 && parts[0] == "connections" && context.Request.Method == "DELETE")
                {
                    var paused = false;
                    try
                    {
                        await using var db = new NpgsqlConnection(File.ReadAllText(config["Workbench:DatabaseFile"]!).Trim());
                        await db.OpenAsync(context.RequestAborted);
                        await using var command = new NpgsqlCommand("UPDATE workbench.runs SET status='paused' WHERE status IN ('queued','running') AND snapshot->>'connectionId'=@id", db);
                        command.Parameters.AddWithValue("id", Guid.Parse(parts[1]).ToString());
                        await command.ExecuteNonQueryAsync(context.RequestAborted);
                        paused = true;
                    }
                    catch (Exception error) when (error is NpgsqlException or IOException) { }
                    var revoked = await connections.Disconnect(parts[1]);
                    return Results.Json(new { disconnected = true, remoteRevocationConfirmed = revoked, runsPaused = paused });
                }
                using var request = new HttpRequestMessage(HttpMethod.Post, "/command");
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Secret(config, "ServiceToken"));
                request.Content = new StringContent(JsonSerializer.Serialize(new { method = context.Request.Method, path = "/" + path, body, query = context.Request.Query.ToDictionary(p => p.Key, p => p.Value.ToArray()) }), System.Text.Encoding.UTF8, "application/json");
                using var response = await clients.CreateClient("workbench").SendAsync(request, context.RequestAborted);
                return Results.Content(await response.Content.ReadAsStringAsync(context.RequestAborted), "application/json", statusCode: (int)response.StatusCode);
            }
            catch (Exception error) when (error is InvalidOperationException or FormatException or JsonException or KeyNotFoundException or IOException or HttpRequestException)
            {
                return Results.Problem(statusCode: 400, title: "Workbench request could not complete", detail: "Check your connection, request fields and local runtime; reconnect if necessary.");
            }
        }).RequireRateLimiting("workbench");

        app.MapGet("/auth/callback", async (HttpContext context, Connections connections) =>
        {
            context.Response.Headers.CacheControl = "no-store";
            try
            {
                var state = await connections.Complete(context.Request.Query);
                return Results.Redirect((config["Workbench:Origin"] ?? "http://localhost:8081") + "/?connection=" + state + "#workbench");
            }
            catch (Exception)
            {
                return Results.Redirect((config["Workbench:Origin"] ?? "http://localhost:8081") + "/?connection=error#workbench");
            }
        });

        app.MapPost("/internal/workbench/{operation}", async (HttpContext context, string operation, Connections connections) =>
        {
            context.Response.Headers.CacheControl = "no-store";
            if (!Connections.Equal(context.Request.Headers.Authorization.ToString(), "Bearer " + Secret(config, "ServiceToken"))) return Results.Unauthorized();
            try
            {
                var body = await context.Request.ReadFromJsonAsync<JsonElement>();
                var connectionId = body.GetProperty("connectionId").GetString()!;
                if (operation == "validate-connection")
                {
                    var models = JsonSerializer.SerializeToElement(await connections.Models(connectionId));
                    if (!models.EnumerateArray().Any(m => m.GetProperty("slug").GetString() == body.GetProperty("model").GetString())) return Results.BadRequest();
                    return Results.Json(new { valid = true, billingMode = connections.BillingMode(connectionId) });
                }
                if (operation != "credential") return Results.NotFound();
                await using var db = new NpgsqlConnection(File.ReadAllText(config["Workbench:DatabaseFile"]!).Trim());
                await db.OpenAsync(context.RequestAborted);
                await using var cmd = new NpgsqlCommand("SELECT r.snapshot->>'connectionId' FROM workbench.runs r JOIN workbench.datasets d ON d.id=r.dataset_id WHERE r.id=@id AND r.status='running' AND d.status='ready'", db);
                cmd.Parameters.AddWithValue("id", Guid.Parse(body.GetProperty("runId").GetString()!));
                if (await cmd.ExecuteScalarAsync(context.RequestAborted) is not string expected || expected != connectionId) return Results.StatusCode(403);
                return Results.Json(new { token = await connections.Credential(connectionId), mode = connections.BillingMode(connectionId) });
            }
            catch (Exception) { return Results.StatusCode(409); }
        });
    }
}
