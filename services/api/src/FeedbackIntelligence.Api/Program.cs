using System.Text.Json;
using System.Threading.RateLimiting;
using FeedbackIntelligence.Api.Dashboard;
using FeedbackIntelligence.Api.Ingestion;
using FeedbackIntelligence.Api.Observability;
using Microsoft.AspNetCore.RateLimiting;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddHealthChecks();
builder.Services.AddProblemDetails();
builder.Services.Configure<IngestionOptions>(builder.Configuration.GetSection("Ingestion"));
builder.Services.Configure<TrendOptions>(builder.Configuration.GetSection("Trend"));
var trendOptions = builder.Configuration.GetSection("Trend").Get<TrendOptions>()
    ?? new TrendOptions();
_ = trendOptions.SelectedAlgorithm;
var ingestionOptions = builder.Configuration
    .GetSection("Ingestion")
    .Get<IngestionOptions>() ?? new IngestionOptions();
builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    options.OnRejected = async (context, cancellationToken) =>
    {
        await Results.Problem(
            statusCode: StatusCodes.Status429TooManyRequests,
            title: "Feedback ingestion rate limit exceeded",
            detail: "Try the request again after the current rate-limit window.")
            .ExecuteAsync(context.HttpContext);
    };
    options.AddPolicy("ingestion", context =>
        RateLimitPartition.GetFixedWindowLimiter(
            context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
            _ => new FixedWindowRateLimiterOptions
            {
                AutoReplenishment = true,
                PermitLimit = Math.Clamp(ingestionOptions.RateLimitPermitLimit, 1, 10_000),
                Window = TimeSpan.FromSeconds(
                    Math.Clamp(ingestionOptions.RateLimitWindowSeconds, 1, 3_600)),
                QueueLimit = 0,
            }));
});
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
});
builder.Services.AddHttpClient("clickhouse", client =>
{
    client.Timeout = TimeSpan.FromSeconds(10);
});
builder.Services.AddSingleton<IDashboardDataSource, DemoDashboardDataSource>();
builder.Services.AddSingleton<IDashboardDataSource, LiveDashboardDataSource>();
builder.Services.AddSingleton<ITrendDataSource, DemoTrendDataSource>();
builder.Services.AddSingleton<ITrendDataSource, LiveTrendDataSource>();
builder.Services.AddSingleton<IEvaluationDataSource, DemoEvaluationDataSource>();
builder.Services.AddSingleton<IEvaluationDataSource, LiveEvaluationDataSource>();
builder.Services.AddSingleton<IFeedbackIngestionStore, PostgresFeedbackIngestionStore>();

if (builder.Configuration.GetValue<bool>("Observability:Enabled"))
{
    var serviceName = builder.Configuration["Observability:ServiceName"]
        ?? "feedback-intelligence-api";
    builder.Services.AddOpenTelemetry()
        .ConfigureResource(resource => resource.AddService(serviceName))
        .WithTracing(tracing => tracing
            .AddSource(Telemetry.SourceName)
            .AddAspNetCoreInstrumentation(options =>
            {
                options.Filter = context => context.Request.Path != "/health";
                options.RecordException = false;
            })
            .AddOtlpExporter())
        .WithMetrics(metrics => metrics
            .AddMeter(Telemetry.SourceName)
            .AddOtlpExporter());
}

var app = builder.Build();

app.UseDashboardProblemDetails();
app.UseRouting();
app.UseRateLimiter();
app.MapHealthChecks("/health");
app.MapDashboardEndpoints();
app.MapIngestionEndpoints();

app.Run();

public partial class Program;
