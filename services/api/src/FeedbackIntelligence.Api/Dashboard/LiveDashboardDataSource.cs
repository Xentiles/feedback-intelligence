using System.Globalization;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Npgsql;
using NpgsqlTypes;

namespace FeedbackIntelligence.Api.Dashboard;

public sealed class LiveDashboardDataSource : IDashboardDataSource
{
    private const string ContractVersion = "1.0";
    private static readonly IReadOnlyDictionary<string, LiveSignalDefinition> SignalDefinitions =
        new Dictionary<string, LiveSignalDefinition>(StringComparer.Ordinal)
        {
            ["overall_negative"] = new("Overall negative", "Eligible feedback classified as an overall negative experience.", fact => fact.OverallEligible, fact => fact.OverallNegative),
            ["delivery_negative"] = new("Delivery negative", "Eligible feedback classified as a negative delivery experience.", fact => fact.DeliveryEligible, fact => fact.DeliveryNegative),
            ["support_negative"] = new("Support negative", "Eligible feedback classified as a negative support experience.", fact => fact.SupportEligible, fact => fact.SupportNegative),
            ["product_defect"] = new("Product defect", "Eligible feedback indicating a product defect.", fact => fact.DefectEligible, fact => fact.ProductDefect),
            ["actionable"] = new("Actionable feedback", "Eligible feedback indicating an actionable customer issue.", fact => fact.ActionableEligible, fact => fact.Actionable)
        };

    private readonly string? _connectionString;
    private readonly string? _clickHouseUrl;
    private readonly string? _clickHouseUser;
    private readonly string? _clickHousePassword;
    private readonly IHttpClientFactory _httpClientFactory;

    public LiveDashboardDataSource(IConfiguration configuration, IHttpClientFactory httpClientFactory)
    {
        _connectionString = configuration.GetConnectionString("Dashboard")
            ?? configuration["Dashboard:PostgresConnectionString"];
        _clickHouseUrl = configuration["Dashboard:ClickHouse:Url"]?.TrimEnd('/');
        _clickHouseUser = configuration["Dashboard:ClickHouse:User"];
        _clickHousePassword = configuration["Dashboard:ClickHouse:Password"];
        _httpClientFactory = httpClientFactory;
    }

    public string Context => "live";

    public async Task<MetadataResponse> GetMetadataAsync(
        string? sourceKey,
        CancellationToken cancellationToken)
    {
        await using var connection = await OpenConnectionAsync(cancellationToken);
        var sources = await ReadSourcesAsync(connection, cancellationToken);
        SourceIdentity? selected = null;
        if (sourceKey is not null)
        {
            selected = sources.SingleOrDefault(source => source.Key == sourceKey)
                ?? throw new DashboardSourceNotFoundException(sourceKey);
        }
        else if (sources.Count == 1)
        {
            selected = sources[0];
        }

        TimeRange? range = null;
        FilterOptions options = new([], [], [], [], []);
        if (selected is not null)
        {
            range = await ReadRangeAsync(connection, selected, cancellationToken);
            options = await ReadFilterOptionsAsync(connection, selected, cancellationToken);
        }

        return new MetadataResponse(
            "metadata",
            ContractVersion,
            Context,
            selected,
            sources,
            range,
            new Capabilities(
                options.Products.Count > 0,
                options.Categories.Count > 0,
                options.Languages.Count > 0,
                options.Channels.Count > 0,
                false),
            options,
            "awaiting_calibration");
    }

    public async Task<OverviewResponse> GetOverviewAsync(
        DashboardQuery query,
        CancellationToken cancellationToken)
    {
        ValidateRange(query);
        await using var connection = await OpenConnectionAsync(cancellationToken);
        var source = await ResolveSourceAsync(connection, query.SourceKey, cancellationToken);
        var selected = await ReadSelectedRecordsAsync(connection, source, query, cancellationToken);
        var processing = await ReadProcessingAsync(connection, selected.Select(row => row.FeedbackId).ToArray(), cancellationToken);
        var facts = await ReadFactsAsync(selected, cancellationToken);
        facts = ApplyAnalyticalFilters(facts, query).ToArray();
        var eligibleFeedback = facts.Where(IsEligible).Select(fact => fact.FeedbackId).Distinct().Count();
        var unavailableReason = processing.ProjectionByDestination.TryGetValue("skipped.uncalibrated", out var withheld)
            && withheld > 0
                ? "uncalibrated"
                : "no_eligible_evidence";
        var imported = selected.Count;
        var classified = selected.Count(row => row.DecisionId is not null);
        var anyNegative = facts.Where(IsEligible).Count(HasAnyNegative);
        var metrics = new Metric[]
        {
            new("imported_feedback", "Imported feedback", "count", imported, imported, null, Availability.Available),
            new("classified_feedback", "Classified feedback", "count", classified, classified, imported, Availability.Available),
            new("analytical_coverage", "Analytical coverage", "percent",
                eligibleFeedback == 0 ? null : Rate(eligibleFeedback, imported),
                eligibleFeedback,
                imported,
                eligibleFeedback == 0 ? Availability.Unavailable(unavailableReason) : Availability.Available),
            new("observed_issue_rate", "Observed issue rate", "percent",
                eligibleFeedback == 0 ? null : Rate(anyNegative, eligibleFeedback),
                eligibleFeedback == 0 ? null : anyNegative,
                eligibleFeedback == 0 ? null : eligibleFeedback,
                eligibleFeedback == 0 ? Availability.Unavailable(unavailableReason) : Availability.Available)
        };

        var signals = eligibleFeedback == 0
            ? []
            : SignalDefinitions.Keys
                .Select(signalId => BuildSignal(signalId, facts, query, unavailableReason))
                .Where(signal => signal.Denominator > 0)
                .OrderByDescending(signal => signal.Rate)
                .ToArray();
        return new OverviewResponse(
            "overview",
            ContractVersion,
            Context,
            query.ToFilters(),
            processing,
            metrics,
            BuildSeries(selected, facts, null),
            signals);
    }

    public async Task<SignalResponse?> GetSignalAsync(
        string signalId,
        DashboardQuery query,
        CancellationToken cancellationToken)
    {
        ValidateRange(query);
        if (!SignalDefinitions.ContainsKey(signalId))
        {
            return null;
        }

        await using var connection = await OpenConnectionAsync(cancellationToken);
        var source = await ResolveSourceAsync(connection, query.SourceKey, cancellationToken);
        var selected = await ReadSelectedRecordsAsync(connection, source, query, cancellationToken);
        var processing = await ReadProcessingAsync(connection, selected.Select(row => row.FeedbackId).ToArray(), cancellationToken);
        var facts = ApplyAnalyticalFilters(
            await ReadFactsAsync(selected, cancellationToken), query).ToArray();
        var reason = processing.ProjectionByDestination.TryGetValue("skipped.uncalibrated", out var withheld)
            && withheld > 0 ? "uncalibrated" : "no_eligible_evidence";
        return new SignalResponse(
            "signal",
            ContractVersion,
            Context,
            query.ToFilters(),
            BuildSignal(signalId, facts, query, reason),
            BuildSeries(selected, facts, signalId),
            "Counts use distinct feedback records from explicitly deduplicated analytical projections. Percentages appear only for policy-eligible evidence.");
    }

    public async Task<EvidencePageResponse?> GetEvidenceAsync(
        string signalId,
        DashboardQuery query,
        int page,
        int pageSize,
        CancellationToken cancellationToken)
    {
        ValidateRange(query);
        if (!SignalDefinitions.TryGetValue(signalId, out var definition))
        {
            return null;
        }

        await using var connection = await OpenConnectionAsync(cancellationToken);
        var source = await ResolveSourceAsync(connection, query.SourceKey, cancellationToken);
        var selected = await ReadSelectedRecordsAsync(connection, source, query, cancellationToken);
        var facts = ApplyAnalyticalFilters(
                await ReadFactsAsync(selected, cancellationToken), query)
            .Where(fact => definition.IsEligible(fact) && definition.Value(fact) >= 0.5)
            .GroupBy(fact => fact.FeedbackId)
            .Select(group => group.OrderByDescending(fact => fact.EventTime).First())
            .ToDictionary(fact => fact.FeedbackId);
        var matching = selected
            .Where(row => facts.ContainsKey(row.FeedbackId))
            .OrderByDescending(row => row.OccurredAt)
            .ThenBy(row => row.FeedbackId)
            .ToArray();
        var items = matching.Skip((page - 1) * pageSize).Take(pageSize).Select(row =>
            new EvidenceRow(
                row.FeedbackId,
                facts[row.FeedbackId].DecisionId,
                row.OccurredAt,
                row.SourceRecordId,
                row.Channel,
                row.ProductLabel,
                null,
                "restricted",
                $"The calibrated analytical projection includes this record in {definition.Label}."))
            .ToArray();
        return new EvidencePageResponse(
            "evidence-page",
            ContractVersion,
            Context,
            query.ToFilters(),
            signalId,
            page,
            pageSize,
            matching.Length,
            items);
    }

    public async Task<EvidenceDetailResponse?> GetEvidenceDetailAsync(
        Guid feedbackId,
        Guid decisionId,
        CancellationToken cancellationToken)
    {
        await using var connection = await OpenConnectionAsync(cancellationToken);
        const string sql = """
            SELECT fr.source_provider_id, fr.source_dataset_name, fr.source_dataset_version,
                   fr.source_record_id, fr.occurred_at, fr.channel,
                   fr.related_products -> 0 ->> 'product_name' AS product_label,
                   dr.decided_at, dr.schema_name, dr.schema_version, dr.resolved_model,
                   dr.policy_version, dr.trace_id
            FROM feedback.dashboard_feedback_records fr
            JOIN feedback.dashboard_decision_runs dr ON dr.feedback_id = fr.feedback_id
            WHERE fr.feedback_id = @feedback_id AND dr.decision_id = @decision_id
            """;
        await using var command = new NpgsqlCommand(sql, connection);
        command.Parameters.AddWithValue("feedback_id", feedbackId);
        command.Parameters.AddWithValue("decision_id", decisionId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            return null;
        }

        var source = CreateSource(
            reader.GetString(0), reader.GetString(1), reader.GetString(2), synthetic: false);
        var sourceRecordId = reader.GetString(3);
        var occurredAt = reader.GetFieldValue<DateTimeOffset>(4);
        var channel = reader.IsDBNull(5) ? null : reader.GetString(5);
        var productLabel = reader.IsDBNull(6) ? null : reader.GetString(6);
        var decidedAt = reader.GetFieldValue<DateTimeOffset>(7);
        var schemaName = reader.GetString(8);
        var schemaVersion = reader.GetString(9);
        var modelVersion = reader.GetString(10);
        var policyVersion = reader.IsDBNull(11) ? null : reader.GetString(11);
        var traceId = reader.GetGuid(12);
        await reader.CloseAsync();

        var answers = await ReadAnswersAsync(connection, decisionId, cancellationToken);
        const string reason = "Decision metadata is available, while feedback text remains behind the restricted evidence boundary.";
        var row = new EvidenceRow(
            feedbackId,
            decisionId,
            occurredAt,
            sourceRecordId,
            channel,
            productLabel,
            null,
            "restricted",
            reason);
        return new EvidenceDetailResponse(
            "evidence-detail",
            ContractVersion,
            Context,
            source,
            row,
            new EvidenceContent("restricted", null, null),
            answers,
            new Provenance(
                decisionId,
                schemaName,
                schemaVersion,
                modelVersion,
                policyVersion,
                "awaiting_calibration",
                traceId,
                decidedAt),
            reason);
    }

    private async Task<NpgsqlConnection> OpenConnectionAsync(CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(_connectionString))
        {
            throw new DashboardSourceUnavailableException("The live PostgreSQL dashboard connection is not configured.");
        }

        try
        {
            var connection = new NpgsqlConnection(_connectionString);
            await connection.OpenAsync(cancellationToken);
            await using var roleCommand = new NpgsqlCommand("SET ROLE feedback_dashboard", connection);
            await roleCommand.ExecuteNonQueryAsync(cancellationToken);
            return connection;
        }
        catch (Exception exception) when (exception is NpgsqlException or TimeoutException)
        {
            throw new DashboardSourceUnavailableException("The live PostgreSQL dashboard source is unavailable.", exception);
        }
    }

    private static async Task<IReadOnlyList<SourceIdentity>> ReadSourcesAsync(
        NpgsqlConnection connection,
        CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT source_provider_id, source_dataset_name, source_dataset_version
            FROM feedback.dashboard_feedback_records
            GROUP BY source_provider_id, source_dataset_name, source_dataset_version
            ORDER BY source_provider_id, source_dataset_name, source_dataset_version
            """;
        await using var command = new NpgsqlCommand(sql, connection);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var sources = new List<SourceIdentity>();
        while (await reader.ReadAsync(cancellationToken))
        {
            sources.Add(CreateSource(reader.GetString(0), reader.GetString(1), reader.GetString(2), false));
        }

        return sources;
    }

    private static async Task<SourceIdentity> ResolveSourceAsync(
        NpgsqlConnection connection,
        string sourceKey,
        CancellationToken cancellationToken)
    {
        var sources = await ReadSourcesAsync(connection, cancellationToken);
        return sources.SingleOrDefault(source => source.Key == sourceKey)
            ?? throw new DashboardSourceNotFoundException(sourceKey);
    }

    private static async Task<TimeRange?> ReadRangeAsync(
        NpgsqlConnection connection,
        SourceIdentity source,
        CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT min(occurred_at), max(occurred_at)
            FROM feedback.dashboard_feedback_records
            WHERE source_provider_id = @provider AND source_dataset_name = @dataset
              AND source_dataset_version = @version
            """;
        await using var command = new NpgsqlCommand(sql, connection);
        AddSourceParameters(command, source);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        await reader.ReadAsync(cancellationToken);
        return reader.IsDBNull(0)
            ? null
            : new TimeRange(
                reader.GetFieldValue<DateTimeOffset>(0),
                reader.GetFieldValue<DateTimeOffset>(1).AddMilliseconds(1));
    }

    private static async Task<FilterOptions> ReadFilterOptionsAsync(
        NpgsqlConnection connection,
        SourceIdentity source,
        CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT
              coalesce(array_agg(DISTINCT p.product_id) FILTER (WHERE p.product_id IS NOT NULL), '{}'),
              coalesce(array_agg(DISTINCT p.category) FILTER (WHERE p.category IS NOT NULL), '{}'),
              coalesce(array_agg(DISTINCT fr.language) FILTER (WHERE fr.language IS NOT NULL), '{}'),
              coalesce(array_agg(DISTINCT fr.channel) FILTER (WHERE fr.channel IS NOT NULL), '{}')
            FROM feedback.dashboard_feedback_records fr
            LEFT JOIN LATERAL (
              SELECT item ->> 'product_id' AS product_id, item ->> 'category' AS category
              FROM jsonb_array_elements(fr.related_products) item
            ) p ON true
            WHERE fr.source_provider_id = @provider AND fr.source_dataset_name = @dataset
              AND fr.source_dataset_version = @version
            """;
        await using var command = new NpgsqlCommand(sql, connection);
        AddSourceParameters(command, source);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        await reader.ReadAsync(cancellationToken);
        return new FilterOptions(
            [],
            reader.GetFieldValue<string[]>(0).Order().ToArray(),
            reader.GetFieldValue<string[]>(1).Order().ToArray(),
            reader.GetFieldValue<string[]>(2).Order().ToArray(),
            reader.GetFieldValue<string[]>(3).Order().ToArray());
    }

    private static async Task<List<LiveRecord>> ReadSelectedRecordsAsync(
        NpgsqlConnection connection,
        SourceIdentity source,
        DashboardQuery query,
        CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT fr.feedback_id, fr.occurred_at, fr.source_record_id, fr.channel, fr.language,
                   fr.related_products -> 0 ->> 'product_id' AS product_id,
                   fr.related_products -> 0 ->> 'product_name' AS product_label,
                   fr.related_products -> 0 ->> 'category' AS category,
                   latest.decision_id
            FROM feedback.dashboard_feedback_records fr
            LEFT JOIN LATERAL (
                SELECT dr.decision_id
                FROM feedback.dashboard_decision_runs dr
                WHERE dr.feedback_id = fr.feedback_id
                ORDER BY dr.decided_at DESC, dr.decision_id
                LIMIT 1
            ) latest ON true
            WHERE fr.source_provider_id = @provider AND fr.source_dataset_name = @dataset
              AND fr.source_dataset_version = @version
              AND fr.occurred_at >= @from AND fr.occurred_at < @to_exclusive
              AND (@language IS NULL OR fr.language = @language)
              AND (@channel IS NULL OR fr.channel = @channel)
              AND (@product IS NULL OR EXISTS (
                  SELECT 1 FROM jsonb_array_elements(fr.related_products) p
                  WHERE p ->> 'product_id' = @product))
              AND (@category IS NULL OR EXISTS (
                  SELECT 1 FROM jsonb_array_elements(fr.related_products) p
                  WHERE p ->> 'category' = @category))
            ORDER BY fr.occurred_at DESC, fr.feedback_id
            """;
        await using var command = new NpgsqlCommand(sql, connection);
        AddSourceParameters(command, source);
        command.Parameters.AddWithValue("from", query.From);
        command.Parameters.AddWithValue("to_exclusive", query.ToExclusive);
        AddNullableText(command, "language", query.Language);
        AddNullableText(command, "channel", query.Channel);
        AddNullableText(command, "product", query.Product);
        AddNullableText(command, "category", query.Category);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var records = new List<LiveRecord>();
        while (await reader.ReadAsync(cancellationToken))
        {
            records.Add(new LiveRecord(
                reader.GetGuid(0),
                reader.GetFieldValue<DateTimeOffset>(1),
                reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3),
                reader.IsDBNull(4) ? null : reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.IsDBNull(6) ? null : reader.GetString(6),
                reader.IsDBNull(7) ? null : reader.GetString(7),
                reader.IsDBNull(8) ? null : reader.GetGuid(8)));
        }

        return records;
    }

    private static async Task<ProcessingSummary> ReadProcessingAsync(
        NpgsqlConnection connection,
        Guid[] feedbackIds,
        CancellationToken cancellationToken)
    {
        if (feedbackIds.Length == 0)
        {
            return new ProcessingSummary(0, 0, 0, new Dictionary<string, int>(), new Dictionary<string, int>());
        }

        const string countsSql = """
            SELECT
              count(DISTINCT ids.feedback_id)::int,
              count(DISTINCT dr.decision_id)::int,
              count(da.question_id)::int
            FROM unnest(@feedback_ids::uuid[]) ids(feedback_id)
            LEFT JOIN feedback.dashboard_decision_runs dr ON dr.feedback_id = ids.feedback_id
            LEFT JOIN feedback.dashboard_decision_answers da ON da.decision_id = dr.decision_id
            """;
        await using var countsCommand = new NpgsqlCommand(countsSql, connection);
        countsCommand.Parameters.AddWithValue("feedback_ids", feedbackIds);
        await using var countsReader = await countsCommand.ExecuteReaderAsync(cancellationToken);
        await countsReader.ReadAsync(cancellationToken);
        var feedbackRecords = countsReader.GetInt32(0);
        var decisionRuns = countsReader.GetInt32(1);
        var typedAnswers = countsReader.GetInt32(2);
        await countsReader.CloseAsync();

        var jobs = await ReadGroupedCountsAsync(connection, """
            SELECT pj.status, count(*)::int
            FROM feedback.dashboard_processing_jobs pj
            WHERE pj.feedback_id = ANY(@feedback_ids)
            GROUP BY pj.status ORDER BY pj.status
            """, feedbackIds, cancellationToken);
        var projections = await ReadGroupedCountsAsync(connection, """
            SELECT pl.destination, count(*)::int
            FROM feedback.dashboard_projection_ledger pl
            JOIN feedback.dashboard_decision_runs dr ON dr.decision_id = pl.decision_id
            WHERE dr.feedback_id = ANY(@feedback_ids)
            GROUP BY pl.destination ORDER BY pl.destination
            """, feedbackIds, cancellationToken);
        return new ProcessingSummary(feedbackRecords, decisionRuns, typedAnswers, jobs, projections);
    }

    private static async Task<IReadOnlyDictionary<string, int>> ReadGroupedCountsAsync(
        NpgsqlConnection connection,
        string sql,
        Guid[] feedbackIds,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(sql, connection);
        command.Parameters.AddWithValue("feedback_ids", feedbackIds);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var counts = new Dictionary<string, int>(StringComparer.Ordinal);
        while (await reader.ReadAsync(cancellationToken))
        {
            counts[reader.GetString(0)] = reader.GetInt32(1);
        }

        return counts;
    }

    private async Task<IReadOnlyList<AnalyticalFact>> ReadFactsAsync(
        IReadOnlyList<LiveRecord> records,
        CancellationToken cancellationToken)
    {
        var selected = records.Where(record => record.DecisionId is not null).ToArray();
        if (selected.Length == 0)
        {
            return [];
        }

        if (string.IsNullOrWhiteSpace(_clickHouseUrl))
        {
            throw new DashboardSourceUnavailableException("The live ClickHouse dashboard connection is not configured.");
        }

        var selectedPairs = string.Join(',', selected.Select(record =>
            $"('{record.FeedbackId:D}'::UUID,'{record.DecisionId!.Value:D}'::UUID)"));
        var sql = $$"""
            SELECT feedback_id, decision_id, event_time, product_id, product_family, source_type,
                   locale, primary_topic, primary_topic_eligible, overall_negative_probability,
                   overall_experience_eligible, delivery_negative_probability,
                   delivery_experience_eligible, support_negative_probability,
                   support_experience_eligible, product_defect_probability, product_defect_eligible,
                   actionable_probability, actionable_eligible
            FROM (
                SELECT *
                FROM feedback_intelligence.signal_facts
                WHERE (feedback_id, decision_id) IN ({{selectedPairs}})
                ORDER BY projected_at DESC
                LIMIT 1 BY projection_id
            )
            ORDER BY projected_at DESC
            LIMIT 1 BY feedback_id
            FORMAT JSONEachRow
            """;
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, _clickHouseUrl);
            request.Content = new StringContent(sql, Encoding.UTF8, "text/plain");
            if (!string.IsNullOrWhiteSpace(_clickHouseUser))
            {
                request.Headers.Add("X-ClickHouse-User", _clickHouseUser);
            }
            if (_clickHousePassword is not null)
            {
                request.Headers.Add("X-ClickHouse-Key", _clickHousePassword);
            }

            using var response = await _httpClientFactory.CreateClient("clickhouse")
                .SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            if (!response.IsSuccessStatusCode)
            {
                throw new DashboardSourceUnavailableException(
                    $"The live ClickHouse dashboard source returned HTTP {(int)response.StatusCode}.");
            }

            await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
            using var reader = new StreamReader(stream);
            var facts = new List<AnalyticalFact>();
            while (await reader.ReadLineAsync(cancellationToken) is { } line)
            {
                if (line.Length == 0)
                {
                    continue;
                }
                facts.Add(ParseFact(line));
            }

            return facts;
        }
        catch (DashboardSourceUnavailableException)
        {
            throw;
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or JsonException)
        {
            throw new DashboardSourceUnavailableException("The live ClickHouse dashboard source is unavailable.", exception);
        }
    }

    private static AnalyticalFact ParseFact(string json)
    {
        using var document = JsonDocument.Parse(json);
        var value = document.RootElement;
        return new AnalyticalFact(
            value.GetProperty("feedback_id").GetGuid(),
            value.GetProperty("decision_id").GetGuid(),
            DateTimeOffset.Parse(value.GetProperty("event_time").GetString()!, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal),
            NullableString(value, "product_id"),
            NullableString(value, "product_family"),
            value.GetProperty("source_type").GetString(),
            value.GetProperty("locale").GetString(),
            NullableString(value, "primary_topic"),
            value.GetProperty("primary_topic_eligible").GetInt32() == 1,
            NullableDouble(value, "overall_negative_probability"),
            value.GetProperty("overall_experience_eligible").GetInt32() == 1,
            NullableDouble(value, "delivery_negative_probability"),
            value.GetProperty("delivery_experience_eligible").GetInt32() == 1,
            NullableDouble(value, "support_negative_probability"),
            value.GetProperty("support_experience_eligible").GetInt32() == 1,
            NullableDouble(value, "product_defect_probability"),
            value.GetProperty("product_defect_eligible").GetInt32() == 1,
            NullableDouble(value, "actionable_probability"),
            value.GetProperty("actionable_eligible").GetInt32() == 1);
    }

    private static async Task<IReadOnlyList<Answer>> ReadAnswersAsync(
        NpgsqlConnection connection,
        Guid decisionId,
        CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT question_id, primitive, answer
            FROM feedback.dashboard_decision_answers
            WHERE decision_id = @decision_id
            ORDER BY question_id
            """;
        await using var command = new NpgsqlCommand(sql, connection);
        command.Parameters.AddWithValue("decision_id", decisionId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var answers = new List<Answer>();
        while (await reader.ReadAsync(cancellationToken))
        {
            var questionId = reader.GetString(0);
            var primitive = reader.GetString(1);
            using var answerJson = JsonDocument.Parse(reader.GetString(2));
            var root = answerJson.RootElement;
            object? value = primitive switch
            {
                "choice" => NullableString(root, "choice"),
                "score" => NullableDouble(root, "score"),
                "noul" => NullableDouble(root, "noul"),
                _ => null
            };
            var confidence = NullableDouble(root, "confidence");
            answers.Add(new Answer(
                questionId,
                CultureInfo.InvariantCulture.TextInfo.ToTitleCase(questionId.Replace('_', ' ')),
                primitive,
                value,
                confidence is null ? null : $"Recorded confidence {confidence.Value:0.00}",
                "withheld_uncalibrated"));
        }

        return answers;
    }

    private static SeriesPoint[] BuildSeries(
        IReadOnlyList<LiveRecord> records,
        IReadOnlyList<AnalyticalFact> facts,
        string? signalId)
    {
        var factsByMonth = facts.GroupBy(fact => (fact.EventTime.Year, fact.EventTime.Month))
            .ToDictionary(group => group.Key, group => group.ToArray());
        return records.GroupBy(record => new DateTimeOffset(record.OccurredAt.Year, record.OccurredAt.Month, 1, 0, 0, 0, TimeSpan.Zero))
            .OrderBy(group => group.Key)
            .Select(group =>
            {
                var monthFacts = factsByMonth.GetValueOrDefault((group.Key.Year, group.Key.Month), []);
                if (signalId is not null && SignalDefinitions.TryGetValue(signalId, out var definition))
                {
                    var eligible = monthFacts.Where(definition.IsEligible).ToArray();
                    var numerator = eligible.Count(fact => definition.Value(fact) >= 0.5);
                    return new SeriesPoint(group.Key, group.Count(), eligible.Length, numerator, Rate(numerator, eligible.Length));
                }

                var eligibleFeedback = monthFacts.Where(IsEligible).Select(fact => fact.FeedbackId).Distinct().Count();
                var numeratorAny = monthFacts.Where(IsEligible).Count(HasAnyNegative);
                return new SeriesPoint(group.Key, group.Count(), eligibleFeedback, numeratorAny,
                    Rate(numeratorAny, eligibleFeedback));
            }).ToArray();
    }

    private static SignalSummary BuildSignal(
        string signalId,
        IReadOnlyList<AnalyticalFact> facts,
        DashboardQuery query,
        string unavailableReason)
    {
        var definition = SignalDefinitions[signalId];
        var eligible = facts.Where(definition.IsEligible)
            .GroupBy(fact => fact.FeedbackId)
            .Select(group => group.First())
            .ToArray();
        var numerator = eligible.Count(fact => definition.Value(fact) >= 0.5);
        return new SignalSummary(
            signalId,
            definition.Label,
            definition.Definition,
            numerator,
            eligible.Length,
            Rate(numerator, eligible.Length),
            null,
            null,
            eligible.Length == 0 ? Availability.Unavailable(unavailableReason) : Availability.Available);
    }

    private static IEnumerable<AnalyticalFact> ApplyAnalyticalFilters(
        IEnumerable<AnalyticalFact> facts,
        DashboardQuery query) => facts.Where(fact =>
            (query.Topic is null || fact.PrimaryTopic == query.Topic) &&
            (query.Product is null || fact.ProductId == query.Product) &&
            (query.Category is null || fact.ProductFamily == query.Category) &&
            (query.Language is null || fact.Locale == query.Language) &&
            (query.Channel is null || fact.SourceType == query.Channel));

    private static bool IsEligible(AnalyticalFact fact) =>
        fact.PrimaryTopicEligible || fact.OverallEligible || fact.DeliveryEligible || fact.SupportEligible
        || fact.DefectEligible || fact.ActionableEligible;

    private static bool HasAnyNegative(AnalyticalFact fact) =>
        (fact.OverallEligible && fact.OverallNegative >= 0.5)
        || (fact.DeliveryEligible && fact.DeliveryNegative >= 0.5)
        || (fact.SupportEligible && fact.SupportNegative >= 0.5)
        || (fact.DefectEligible && fact.ProductDefect >= 0.5)
        || (fact.ActionableEligible && fact.Actionable >= 0.5);

    private static double? Rate(int numerator, int denominator) =>
        denominator == 0 ? null : Math.Round(numerator * 100d / denominator, 2);

    private static void AddSourceParameters(NpgsqlCommand command, SourceIdentity source)
    {
        command.Parameters.AddWithValue("provider", source.ProviderId);
        command.Parameters.AddWithValue("dataset", source.DatasetName);
        command.Parameters.AddWithValue("version", source.DatasetVersion);
    }

    private static void AddNullableText(NpgsqlCommand command, string name, string? value)
    {
        var parameter = command.Parameters.Add(name, NpgsqlDbType.Text);
        parameter.Value = value is null ? DBNull.Value : value;
    }

    private static void ValidateRange(DashboardQuery query)
    {
        if (query.ToExclusive <= query.From)
        {
            throw new ArgumentException("toExclusive must be later than from.");
        }
    }

    private static SourceIdentity CreateSource(
        string provider,
        string dataset,
        string version,
        bool synthetic) =>
        new(
            $"{provider}/{dataset}/{version}",
            provider,
            dataset,
            version,
            $"{dataset} ({version})",
            synthetic || string.Equals(provider, "synthetic", StringComparison.OrdinalIgnoreCase));

    private static string? NullableString(JsonElement value, string property) =>
        !value.TryGetProperty(property, out var item) || item.ValueKind == JsonValueKind.Null
            ? null
            : item.GetString();

    private static double? NullableDouble(JsonElement value, string property) =>
        !value.TryGetProperty(property, out var item) || item.ValueKind == JsonValueKind.Null
            ? null
            : item.GetDouble();

    private sealed record LiveRecord(
        Guid FeedbackId,
        DateTimeOffset OccurredAt,
        string SourceRecordId,
        string? Channel,
        string? Language,
        string? ProductId,
        string? ProductLabel,
        string? Category,
        Guid? DecisionId);

    private sealed record AnalyticalFact(
        Guid FeedbackId,
        Guid DecisionId,
        DateTimeOffset EventTime,
        string? ProductId,
        string? ProductFamily,
        string? SourceType,
        string? Locale,
        string? PrimaryTopic,
        bool PrimaryTopicEligible,
        double? OverallNegative,
        bool OverallEligible,
        double? DeliveryNegative,
        bool DeliveryEligible,
        double? SupportNegative,
        bool SupportEligible,
        double? ProductDefect,
        bool DefectEligible,
        double? Actionable,
        bool ActionableEligible);

    private sealed record LiveSignalDefinition(
        string Label,
        string Definition,
        Func<AnalyticalFact, bool> IsEligible,
        Func<AnalyticalFact, double?> Value);
}
