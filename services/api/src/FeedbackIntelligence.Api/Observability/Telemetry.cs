using System.Diagnostics;
using System.Diagnostics.Metrics;

namespace FeedbackIntelligence.Api.Observability;

public static class Telemetry
{
    public const string SourceName = "FeedbackIntelligence.Api";

    private static readonly ActivitySource Activities = new(SourceName);
    private static readonly Meter Meter = new(SourceName);
    private static readonly Counter<long> Ingested =
        Meter.CreateCounter<long>("feedback_ingested_total");
    private static readonly Counter<long> IngestionErrors =
        Meter.CreateCounter<long>("feedback_ingest_errors_total");
    private static readonly Histogram<double> IngestionDuration =
        Meter.CreateHistogram<double>("feedback_ingest_duration_ms", "ms");

    public static Activity? StartIngestion() =>
        Activities.StartActivity("feedback.ingest", ActivityKind.Internal);

    public static Activity? StartPersistence() =>
        Activities.StartActivity("feedback.persist", ActivityKind.Internal);

    public static void RecordIngestion(bool created, string engine, double durationMs)
    {
        var tags = new TagList
        {
            { "decision.engine", engine },
            { "ingestion.outcome", created ? "created" : "idempotent" },
        };
        Ingested.Add(1, tags);
        IngestionDuration.Record(durationMs, tags);
    }

    public static void RecordIngestionError(string errorType, double durationMs)
    {
        var tags = new TagList { { "error.type", errorType } };
        IngestionErrors.Add(1, tags);
        IngestionDuration.Record(durationMs, tags);
    }
}
