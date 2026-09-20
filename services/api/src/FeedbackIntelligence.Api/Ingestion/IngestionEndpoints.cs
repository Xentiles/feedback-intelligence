using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using FeedbackIntelligence.Api.Observability;
using Microsoft.Extensions.Options;
using Microsoft.AspNetCore.Mvc;

namespace FeedbackIntelligence.Api.Ingestion;

public static class IngestionEndpoints
{
    public static IEndpointRouteBuilder MapIngestionEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/api/v1/feedback", async (
            FeedbackIngestionRequest request,
            HttpRequest httpRequest,
            IOptions<IngestionOptions> configuredOptions,
            IFeedbackIngestionStore store,
            CancellationToken cancellationToken) =>
        {
            var started = Stopwatch.GetTimestamp();
            using var activity = Telemetry.StartIngestion();
            try
            {
                var options = configuredOptions.Value;
                Authorize(httpRequest, options);
                var command = IngestionValidator.Validate(request, options) with
                {
                    TraceParent = Activity.Current?.Id,
                    TraceState = Activity.Current?.TraceStateString,
                };
                activity?.SetTag("feedback.id", request.FeedbackId);
                var decisionEngine = options.DecisionEngine.ToConfigurationValue();
                activity?.SetTag("decision.engine", decisionEngine);
                activity?.SetTag("schema.version", options.DecisionSchemaVersion);
                activity?.SetTag("source.type", request.Source.ProviderId);
                var result = await store.EnqueueAsync(command, cancellationToken);
                activity?.SetTag("ingestion.outcome", result.Created ? "created" : "idempotent");
                var durationMs = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
                Telemetry.RecordIngestion(result.Created, decisionEngine, durationMs);
                var receipt = new IngestionReceipt(
                    "feedback-ingestion-receipt/1.0.0",
                    request.FeedbackId,
                    result.JobId,
                    command.IdempotencyKey,
                    result.Status,
                    result.Created);

                return result.Created
                    ? Results.Accepted($"/api/v1/feedback/{request.FeedbackId}", receipt)
                    : Results.Ok(receipt);
            }
            catch (Exception error)
            {
                activity?.SetTag("error.type", error.GetType().Name);
                activity?.SetStatus(ActivityStatusCode.Error);
                Telemetry.RecordIngestionError(
                    error.GetType().Name,
                    Stopwatch.GetElapsedTime(started).TotalMilliseconds);
                throw;
            }
        })
        .WithName("IngestFeedback")
        .Accepts<FeedbackIngestionRequest>("application/json")
        .Produces<IngestionReceipt>(StatusCodes.Status202Accepted)
        .Produces<IngestionReceipt>(StatusCodes.Status200OK)
        .ProducesProblem(StatusCodes.Status400BadRequest)
        .ProducesProblem(StatusCodes.Status409Conflict)
        .ProducesProblem(StatusCodes.Status401Unauthorized)
        .ProducesProblem(StatusCodes.Status429TooManyRequests)
        .ProducesProblem(StatusCodes.Status503ServiceUnavailable)
        .WithMetadata(new RequestSizeLimitAttribute(64 * 1024))
        .RequireRateLimiting("ingestion");

        return endpoints;
    }

    private static void Authorize(HttpRequest request, IngestionOptions options)
    {
        if (!options.Enabled)
        {
            throw new IngestionUnavailableException(
                "Feedback ingestion is disabled for this deployment.");
        }

        if (string.IsNullOrWhiteSpace(options.ApiKey))
        {
            throw new IngestionUnavailableException(
                "Feedback ingestion requires a configured server-side API key.");
        }

        var supplied = request.Headers["X-Feedback-Ingestion-Key"].ToString();
        var expectedHash = SHA256.HashData(Encoding.UTF8.GetBytes(options.ApiKey));
        var suppliedHash = SHA256.HashData(Encoding.UTF8.GetBytes(supplied));
        if (!CryptographicOperations.FixedTimeEquals(expectedHash, suppliedHash))
        {
            throw new IngestionUnauthorizedException("A valid ingestion API key is required.");
        }
    }
}
