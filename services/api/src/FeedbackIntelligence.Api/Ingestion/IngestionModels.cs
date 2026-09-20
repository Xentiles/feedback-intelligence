using System.Text.Json;

namespace FeedbackIntelligence.Api.Ingestion;

public sealed record FeedbackIngestionRequest(
    string SchemaVersion,
    Guid FeedbackId,
    SourceReference Source,
    string OriginalText,
    string? Title,
    DateTimeOffset OccurredAt,
    Rating? Rating,
    IReadOnlyList<RelatedProduct> RelatedProducts,
    string? OrderId,
    string? Channel,
    string? Language,
    JsonElement Metadata,
    OperationalContext? OperationalContext,
    string PrivacyStatus);

public sealed record SourceReference(
    string ProviderId,
    string DatasetName,
    string DatasetVersion,
    string SourceRecordId);

public sealed record Rating(decimal Value, decimal ScaleMin, decimal ScaleMax);

public sealed record Money(string Amount, string Currency);

public sealed record RelatedProduct(
    string ProductId,
    string? ProductName,
    string? Category,
    string? CategoryLanguage,
    int Quantity,
    IReadOnlyList<string> SellerIds,
    Money? Price,
    Money? FreightCost);

public sealed record OperationalContext(
    DateTimeOffset? PurchasedAt,
    DateTimeOffset? DeliveredAt,
    DateTimeOffset? ExpectedDeliveryAt,
    decimal? DeliveryDeltaDays,
    string? OrderStatus,
    Money? TotalPrice,
    Money? TotalFreightCost,
    int? SellerCount);

public enum DecisionEngineKind
{
    Fixture,
    Semif,
    Rules,
    Llm,
}

public static class DecisionEngineKindExtensions
{
    public static string ToConfigurationValue(this DecisionEngineKind engine) =>
        engine.ToString().ToLowerInvariant();
}

public sealed record IngestionReceipt(
    string ReceiptVersion,
    Guid FeedbackId,
    Guid JobId,
    string IdempotencyKey,
    string Status,
    bool Created);

public sealed record IngestionOptions
{
    public bool Enabled { get; init; }

    public int MaximumTextCharacters { get; init; } = 10_000;

    public string ApiKey { get; init; } = string.Empty;

    public int RateLimitPermitLimit { get; init; } = 30;

    public int RateLimitWindowSeconds { get; init; } = 60;

    public DecisionEngineKind DecisionEngine { get; init; } = DecisionEngineKind.Rules;

    public string RequestedModel { get; init; } = "rules-1.0.0";

    public string DecisionSchemaName { get; init; } = "feedback-decision";

    public string DecisionSchemaVersion { get; init; } = "1.0.0";

    public string DecisionSchemaSha256 { get; init; } =
        "sha256:9314b38daf329f4c61fbea3d64f9a76a8d6334511888dcd61f7c75563c8f7094";
}

public sealed record IngestionCommand(
    FeedbackIngestionRequest Record,
    Guid JobId,
    string IdempotencyKey,
    string CanonicalSha256,
    IngestionOptions Options,
    string? TraceParent = null,
    string? TraceState = null);

public sealed record IngestionStoreResult(Guid JobId, string Status, bool Created);

public sealed class IngestionConflictException(string message) : Exception(message);

public sealed class IngestionUnavailableException(string message) : Exception(message);

public sealed class IngestionUnauthorizedException(string message) : Exception(message);
