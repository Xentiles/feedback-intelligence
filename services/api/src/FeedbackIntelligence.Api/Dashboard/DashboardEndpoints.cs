using System.Globalization;
using FeedbackIntelligence.Api.Ingestion;
using Microsoft.AspNetCore.Mvc;

namespace FeedbackIntelligence.Api.Dashboard;

public static class DashboardEndpoints
{
    public static IEndpointRouteBuilder MapDashboardEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/v1/dashboard");

        group.MapGet("/metadata", async (
            string? context,
            string? sourceKey,
            IEnumerable<IDashboardDataSource> sources,
            CancellationToken cancellationToken) =>
        {
            var source = ResolveSource(context, sources);
            return Results.Ok(await source.GetMetadataAsync(sourceKey, cancellationToken));
        });

        group.MapGet("/trends", async (
            string? context,
            string? sourceKey,
            IEnumerable<ITrendDataSource> sources,
            CancellationToken cancellationToken) =>
        {
            var source = ResolveTrendSource(context, sources);
            return Results.Ok(await source.GetTrendsAsync(sourceKey, cancellationToken));
        });

        group.MapGet("/evaluation", async (
            string? context,
            IEnumerable<IEvaluationDataSource> sources,
            CancellationToken cancellationToken) =>
        {
            var source = ResolveEvaluationSource(context, sources);
            return Results.Ok(await source.GetEvaluationAsync(cancellationToken));
        });

        group.MapGet("/overview", async (
            HttpRequest request,
            IEnumerable<IDashboardDataSource> sources,
            CancellationToken cancellationToken) =>
        {
            var source = ResolveSource(request.Query["context"].FirstOrDefault(), sources);
            var query = ParseQuery(request);
            return Results.Ok(await source.GetOverviewAsync(query, cancellationToken));
        });

        group.MapGet("/signals/{signalId}", async (
            string signalId,
            HttpRequest request,
            IEnumerable<IDashboardDataSource> sources,
            CancellationToken cancellationToken) =>
        {
            var source = ResolveSource(request.Query["context"].FirstOrDefault(), sources);
            var query = ParseQuery(request);
            var response = await source.GetSignalAsync(signalId, query, cancellationToken);
            return response is null
                ? Results.Problem(
                    statusCode: StatusCodes.Status404NotFound,
                    title: "Signal not found",
                    detail: $"Signal '{signalId}' is not available in the selected context.")
                : Results.Ok(response);
        });

        group.MapGet("/signals/{signalId}/evidence", async (
            string signalId,
            HttpRequest request,
            IEnumerable<IDashboardDataSource> sources,
            CancellationToken cancellationToken) =>
        {
            var source = ResolveSource(request.Query["context"].FirstOrDefault(), sources);
            var query = ParseQuery(request);
            var page = ParsePositiveInteger(request, "page", 1, int.MaxValue);
            var pageSize = ParsePositiveInteger(request, "pageSize", 10, 50);
            if ((long)(page - 1) * pageSize > int.MaxValue)
            {
                throw new ArgumentException("page and pageSize exceed the supported paging range.");
            }
            var response = await source.GetEvidenceAsync(signalId, query, page, pageSize, cancellationToken);
            return response is null
                ? Results.Problem(
                    statusCode: StatusCodes.Status404NotFound,
                    title: "Signal not found",
                    detail: $"Signal '{signalId}' is not available in the selected context.")
                : Results.Ok(response);
        });

        group.MapGet("/evidence/{feedbackId:guid}", async (
            Guid feedbackId,
            HttpRequest request,
            IEnumerable<IDashboardDataSource> sources,
            CancellationToken cancellationToken) =>
        {
            var source = ResolveSource(request.Query["context"].FirstOrDefault(), sources);
            var decisionIdValue = request.Query["decisionId"].FirstOrDefault();
            if (!Guid.TryParse(decisionIdValue, out var decisionId))
            {
                throw new ArgumentException("decisionId must be a UUID.");
            }

            var response = await source.GetEvidenceDetailAsync(feedbackId, decisionId, cancellationToken);
            return response is null
                ? Results.Problem(
                    statusCode: StatusCodes.Status404NotFound,
                    title: "Evidence not found",
                    detail: "The requested feedback and decision pair was not found.")
                : Results.Ok(response);
        });

        return endpoints;
    }

    public static void UseDashboardProblemDetails(this WebApplication app)
    {
        app.UseExceptionHandler(errorApp => errorApp.Run(async context =>
        {
            var exception = context.Features.Get<Microsoft.AspNetCore.Diagnostics.IExceptionHandlerFeature>()?.Error;
            var (status, title, detail) = exception switch
            {
                DashboardSourceUnavailableException unavailable =>
                    (StatusCodes.Status503ServiceUnavailable, "Dashboard source unavailable", unavailable.Message),
                DashboardSourceNotFoundException missing =>
                    (StatusCodes.Status404NotFound, "Dashboard source not found", missing.Message),
                ArgumentException invalid =>
                    (StatusCodes.Status400BadRequest, "Invalid request", invalid.Message),
                IngestionConflictException conflict =>
                    (StatusCodes.Status409Conflict, "Feedback identity conflict", conflict.Message),
                IngestionUnavailableException unavailable =>
                    (StatusCodes.Status503ServiceUnavailable, "Feedback ingestion unavailable", unavailable.Message),
                IngestionUnauthorizedException unauthorized =>
                    (StatusCodes.Status401Unauthorized, "Feedback ingestion unauthorized", unauthorized.Message),
                _ =>
                    (StatusCodes.Status500InternalServerError, "Request failed", "The request could not be completed.")
            };
            context.Response.StatusCode = status;
            await Results.Problem(statusCode: status, title: title, detail: detail)
                .ExecuteAsync(context);
        }));
    }

    private static IDashboardDataSource ResolveSource(
        string? context,
        IEnumerable<IDashboardDataSource> sources)
    {
        if (context is not ("live" or "demo"))
        {
            throw new ArgumentException("context must be either 'live' or 'demo'.");
        }

        return sources.Single(source => source.Context == context);
    }

    private static ITrendDataSource ResolveTrendSource(
        string? context,
        IEnumerable<ITrendDataSource> sources)
    {
        if (context is not ("live" or "demo"))
        {
            throw new ArgumentException("context must be either 'live' or 'demo'.");
        }

        return sources.Single(source => source.Context == context);
    }

    private static IEvaluationDataSource ResolveEvaluationSource(
        string? context,
        IEnumerable<IEvaluationDataSource> sources)
    {
        if (context is not ("live" or "demo"))
        {
            throw new ArgumentException("context must be either 'live' or 'demo'.");
        }

        return sources.Single(source => source.Context == context);
    }

    private static DashboardQuery ParseQuery(HttpRequest request)
    {
        var sourceKey = Required(request, "sourceKey");
        var from = ParseUtc(request, "from");
        var toExclusive = ParseUtc(request, "toExclusive");
        if (toExclusive <= from)
        {
            throw new ArgumentException("toExclusive must be later than from.");
        }

        return new DashboardQuery(
            sourceKey,
            from,
            toExclusive,
            Optional(request, "topic"),
            Optional(request, "product"),
            Optional(request, "category"),
            Optional(request, "language"),
            Optional(request, "channel"));
    }

    private static DateTimeOffset ParseUtc(HttpRequest request, string key)
    {
        var raw = Required(request, key);
        if (!DateTimeOffset.TryParse(
                raw,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AllowWhiteSpaces | DateTimeStyles.AssumeUniversal,
                out var parsed)
            || parsed.Offset != TimeSpan.Zero)
        {
            throw new ArgumentException($"{key} must be an ISO-8601 UTC date-time.");
        }

        return parsed;
    }

    private static int ParsePositiveInteger(HttpRequest request, string key, int defaultValue, int maximum)
    {
        var raw = request.Query[key].FirstOrDefault();
        if (raw is null)
        {
            return defaultValue;
        }

        if (!int.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var parsed)
            || parsed < 1
            || parsed > maximum)
        {
            throw new ArgumentException($"{key} must be between 1 and {maximum}.");
        }

        return parsed;
    }

    private static string Required(HttpRequest request, string key)
    {
        var value = Optional(request, key);
        return value ?? throw new ArgumentException($"{key} is required.");
    }

    private static string? Optional(HttpRequest request, string key)
    {
        var value = request.Query[key].FirstOrDefault()?.Trim();
        return string.IsNullOrEmpty(value) ? null : value;
    }
}
