using System.Text.Json;
using FeedbackIntelligence.Api.Observability;
using Microsoft.Extensions.Options;
using Npgsql;
using NpgsqlTypes;

namespace FeedbackIntelligence.Api.Ingestion;

public sealed class PostgresFeedbackIngestionStore(
    IConfiguration configuration,
    IOptions<IngestionOptions> configuredOptions) : IFeedbackIngestionStore
{
    private static readonly JsonSerializerOptions DatabaseJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    private readonly string? _connectionString =
        configuration.GetConnectionString("Operational");

    private readonly IngestionOptions _options = configuredOptions.Value;

    public async Task<IngestionStoreResult> EnqueueAsync(
        IngestionCommand command,
        CancellationToken cancellationToken)
    {
        using var activity = Telemetry.StartPersistence();
        activity?.SetTag("feedback.id", command.Record.FeedbackId);
        activity?.SetTag(
            "decision.engine",
            command.Options.DecisionEngine.ToConfigurationValue());
        activity?.SetTag("schema.version", command.Options.DecisionSchemaVersion);
        if (!_options.Enabled || string.IsNullOrWhiteSpace(_connectionString))
        {
            throw new IngestionUnavailableException(
                "Feedback ingestion requires an enabled operational PostgreSQL connection.");
        }

        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using (var setRole = new NpgsqlCommand("SET LOCAL ROLE feedback_api", connection, transaction))
        {
            await setRole.ExecuteNonQueryAsync(cancellationToken);
        }

        var insertedRecord = await InsertRecordAsync(connection, transaction, command, cancellationToken);
        if (!insertedRecord)
        {
            var checksum = await ReadChecksumAsync(
                connection,
                transaction,
                command.Record.FeedbackId,
                cancellationToken);
            if (!string.Equals(checksum, command.CanonicalSha256, StringComparison.Ordinal)
                && !await ContentMatchesAsync(connection, transaction, command, cancellationToken))
            {
                throw new IngestionConflictException(
                    $"Feedback identity {command.Record.FeedbackId} already exists with different content.");
            }
        }

        await InsertRestrictedTextAsync(connection, transaction, command, cancellationToken);
        var created = await InsertJobAsync(connection, transaction, command, cancellationToken);
        var result = await ReadJobAsync(connection, transaction, command.IdempotencyKey, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return result with { Created = created };
    }

    private static async Task<bool> InsertRecordAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        IngestionCommand command,
        CancellationToken cancellationToken)
    {
        const string sql = """
            INSERT INTO feedback.feedback_records (
                feedback_id, schema_version, source_provider_id, source_dataset_name,
                source_dataset_version, source_record_id, occurred_at, channel, language,
                rating, related_products, order_id, metadata, operational_context,
                canonical_sha256
            ) VALUES (
                @feedback_id, @schema_version, @provider_id, @dataset_name,
                @dataset_version, @source_record_id, @occurred_at, @channel, @language,
                @rating, @related_products, @order_id, @metadata, @operational_context,
                @canonical_sha256
            ) ON CONFLICT (feedback_id) DO NOTHING
            RETURNING feedback_id
            """;
        await using var query = new NpgsqlCommand(sql, connection, transaction);
        var record = command.Record;
        query.Parameters.AddWithValue("feedback_id", record.FeedbackId);
        query.Parameters.AddWithValue("schema_version", record.SchemaVersion);
        query.Parameters.AddWithValue("provider_id", record.Source.ProviderId);
        query.Parameters.AddWithValue("dataset_name", record.Source.DatasetName);
        query.Parameters.AddWithValue("dataset_version", record.Source.DatasetVersion);
        query.Parameters.AddWithValue("source_record_id", record.Source.SourceRecordId);
        query.Parameters.AddWithValue("occurred_at", record.OccurredAt);
        query.Parameters.AddWithValue("channel", (object?)record.Channel ?? DBNull.Value);
        query.Parameters.AddWithValue("language", (object?)record.Language ?? DBNull.Value);
        AddJson(query, "rating", record.Rating);
        AddJson(query, "related_products", record.RelatedProducts);
        query.Parameters.AddWithValue("order_id", (object?)record.OrderId ?? DBNull.Value);
        AddJson(query, "metadata", record.Metadata);
        AddJson(query, "operational_context", record.OperationalContext);
        query.Parameters.AddWithValue("canonical_sha256", command.CanonicalSha256);
        return await query.ExecuteScalarAsync(cancellationToken) is not null;
    }

    private static async Task<string?> ReadChecksumAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid feedbackId,
        CancellationToken cancellationToken)
    {
        await using var query = new NpgsqlCommand(
            "SELECT canonical_sha256 FROM feedback.feedback_records WHERE feedback_id = @id",
            connection,
            transaction);
        query.Parameters.AddWithValue("id", feedbackId);
        return (string?)await query.ExecuteScalarAsync(cancellationToken);
    }

    private static async Task<bool> ContentMatchesAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        IngestionCommand command,
        CancellationToken cancellationToken)
    {
        await using var query = new NpgsqlCommand(
            "SELECT feedback.record_content_matches(@id, @content)",
            connection,
            transaction);
        query.Parameters.AddWithValue("id", command.Record.FeedbackId);
        AddJson(query, "content", command.Record);
        return await query.ExecuteScalarAsync(cancellationToken) is true;
    }

    private static async Task InsertRestrictedTextAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        IngestionCommand command,
        CancellationToken cancellationToken)
    {
        const string sql = """
            INSERT INTO feedback.restricted_feedback_text (
                feedback_id, original_text, title, privacy_status
            ) VALUES (@feedback_id, @original_text, @title, @privacy_status)
            ON CONFLICT (feedback_id) DO NOTHING
            """;
        await using var query = new NpgsqlCommand(sql, connection, transaction);
        query.Parameters.AddWithValue("feedback_id", command.Record.FeedbackId);
        query.Parameters.AddWithValue("original_text", command.Record.OriginalText);
        query.Parameters.AddWithValue("title", (object?)command.Record.Title ?? DBNull.Value);
        query.Parameters.AddWithValue("privacy_status", command.Record.PrivacyStatus);
        await query.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task<bool> InsertJobAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        IngestionCommand command,
        CancellationToken cancellationToken)
    {
        const string sql = """
            INSERT INTO feedback.processing_jobs (
                job_id, idempotency_key, feedback_id, decision_schema_name,
                decision_schema_version, decision_schema_sha256, engine, requested_model,
                traceparent, tracestate
            ) VALUES (
                @job_id, @idempotency_key, @feedback_id, @schema_name,
                @schema_version, @schema_sha256, @engine, @requested_model,
                @traceparent, @tracestate
            ) ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING job_id
            """;
        await using var query = new NpgsqlCommand(sql, connection, transaction);
        query.Parameters.AddWithValue("job_id", command.JobId);
        query.Parameters.AddWithValue("idempotency_key", command.IdempotencyKey);
        query.Parameters.AddWithValue("feedback_id", command.Record.FeedbackId);
        query.Parameters.AddWithValue("schema_name", command.Options.DecisionSchemaName);
        query.Parameters.AddWithValue("schema_version", command.Options.DecisionSchemaVersion);
        query.Parameters.AddWithValue("schema_sha256", command.Options.DecisionSchemaSha256);
        query.Parameters.AddWithValue(
            "engine",
            command.Options.DecisionEngine.ToConfigurationValue());
        query.Parameters.AddWithValue("requested_model", command.Options.RequestedModel);
        query.Parameters.AddWithValue("traceparent", (object?)command.TraceParent ?? DBNull.Value);
        query.Parameters.AddWithValue("tracestate", (object?)command.TraceState ?? DBNull.Value);
        return await query.ExecuteScalarAsync(cancellationToken) is not null;
    }

    private static async Task<IngestionStoreResult> ReadJobAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        string idempotencyKey,
        CancellationToken cancellationToken)
    {
        await using var query = new NpgsqlCommand(
            "SELECT job_id, status FROM feedback.processing_jobs WHERE idempotency_key = @key",
            connection,
            transaction);
        query.Parameters.AddWithValue("key", idempotencyKey);
        await using var reader = await query.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException("The processing job could not be read after enqueue.");
        }

        return new IngestionStoreResult(reader.GetGuid(0), reader.GetString(1), false);
    }

    private static void AddJson(NpgsqlCommand command, string name, object? value)
    {
        var parameter = command.Parameters.Add(name, NpgsqlDbType.Jsonb);
        parameter.Value = value is null
            ? DBNull.Value
            : JsonSerializer.Serialize(value, DatabaseJsonOptions);
    }
}
