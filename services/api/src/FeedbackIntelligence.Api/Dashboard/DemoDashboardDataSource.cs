using System.Text.Json;

namespace FeedbackIntelligence.Api.Dashboard;

public sealed class DemoDashboardDataSource : IDashboardDataSource
{
    private const string ContractVersion = "1.0";
    private const string DefaultSourceKey = "synthetic/feedback-decision-ai-reference/1.0.0";
    private static readonly string[] FixtureFileNames =
        ["dashboard-demo-semif.json", "dashboard-demo-rules.json", "dashboard-demo.json"];
    private static readonly JsonSerializerOptions FixtureJsonOptions =
        new() { PropertyNameCaseInsensitive = true };
    private static readonly IReadOnlyDictionary<string, (string Label, string Definition)> SignalDefinitions =
        new Dictionary<string, (string, string)>(StringComparer.Ordinal)
        {
            ["delivery_delay"] = ("Delivery friction", "Delivery records with a poor delivery-experience score."),
            ["product_defect"] = ("Product defect", "Records classified as explicitly reporting a product defect."),
            ["support_friction"] = ("Support friction", "Support records with a poor support-experience score."),
            ["return_unresolved"] = ("Unresolved return", "Return or refund records whose resolution remains unresolved or unclear."),
            ["checkout_friction"] = ("Checkout friction", "Checkout records with a low overall-experience score."),
            ["compatibility_issue"] = ("Compatibility issue", "Compatibility records with a low product-experience score.")
        };
    private static readonly IReadOnlyDictionary<string, string> AnswerLabels =
        new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["primary_topic"] = "Primary topic",
            ["mentions_product"] = "Mentions product",
            ["mentions_delivery"] = "Mentions delivery",
            ["mentions_support"] = "Mentions support",
            ["overall_experience"] = "Overall experience",
            ["product_experience"] = "Product experience",
            ["delivery_experience"] = "Delivery experience",
            ["support_experience"] = "Support experience",
            ["reports_product_defect"] = "Reports product defect",
            ["issue_severity"] = "Issue severity",
            ["resolution_status"] = "Resolution status",
            ["actionable_feedback"] = "Actionable feedback",
            ["explicit_repurchase_risk"] = "Explicit repurchase risk",
            ["defect_type"] = "Defect type"
        };

    private readonly IReadOnlyDictionary<string, DemoFixture> _fixtures;

    public DemoDashboardDataSource(IWebHostEnvironment environment)
    {
        _fixtures = FixtureFileNames
            .Select(fileName => LoadFixture(environment.ContentRootPath, fileName))
            .ToDictionary(fixture => fixture.Source.Key, StringComparer.Ordinal);
    }

    public string Context => "demo";

    public Task<MetadataResponse> GetMetadataAsync(string? sourceKey, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var fixture = ResolveFixture(sourceKey);
        var records = fixture.Records.OrderBy(record => record.OccurredAt).ToArray();
        var source = ToSourceIdentity(fixture.Source);
        var response = new MetadataResponse(
            "metadata",
            ContractVersion,
            Context,
            source,
            _fixtures.Values.Select(item => ToSourceIdentity(item.Source)).ToArray(),
            records.Length == 0
                ? null
                : new TimeRange(records[0].OccurredAt, records[^1].OccurredAt.AddMilliseconds(1)),
            new Capabilities(true, true, true, true, true),
            new FilterOptions(
                records.Select(record => record.Topic).Distinct().Order().ToArray(),
                records.Select(record => record.Product).Distinct().Order().ToArray(),
                records.Select(record => record.Category).Distinct().Order().ToArray(),
                records.Select(record => record.Language).Distinct().Order().ToArray(),
                records.Select(record => record.Channel).Distinct().Order().ToArray()),
            "illustrative");
        return Task.FromResult(response);
    }

    public Task<OverviewResponse> GetOverviewAsync(DashboardQuery query, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ValidateQuery(query);
        var fixture = ResolveFixture(query.SourceKey);
        var records = Filter(fixture, query).ToArray();
        var imported = records.Length;
        var eligible = records.Length;
        var anyIssue = records.Count(record => record.Signals.Count > 0);
        var availability = eligible > 0
            ? Availability.Available
            : Availability.Unavailable("no_eligible_evidence");
        var metrics = new Metric[]
        {
            new("imported_feedback", "Imported feedback", "count", imported, imported, null, Availability.Available),
            new("classified_feedback", "Classified feedback", "count", imported, imported, imported, Availability.Available),
            new("analytical_coverage", "Analytical coverage", "percent", Rate(eligible, imported), eligible, imported,
                imported > 0 ? Availability.Available : Availability.Unavailable("insufficient_data")),
            new("observed_issue_rate", "Observed issue rate", "percent", Rate(anyIssue, eligible), anyIssue, eligible, availability)
        };
        var signals = SignalDefinitions.Keys
            .Select(signalId => BuildSignal(fixture, signalId, query, records))
            .OrderByDescending(signal => Math.Abs(signal.DeltaPoints ?? 0))
            .ThenBy(signal => signal.Label, StringComparer.Ordinal)
            .ToArray();
        var response = new OverviewResponse(
            "overview",
            ContractVersion,
            Context,
            query.ToFilters(),
            new ProcessingSummary(
                imported,
                imported,
                imported * AnswerLabels.Count,
                new Dictionary<string, int> { ["succeeded"] = imported },
                new Dictionary<string, int> { [fixture.Source.ProjectionDestination] = imported }),
            metrics,
            BuildSeries(records, null),
            signals);
        return Task.FromResult(response);
    }

    public Task<SignalResponse?> GetSignalAsync(
        string signalId,
        DashboardQuery query,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ValidateQuery(query);
        if (!SignalDefinitions.ContainsKey(signalId))
        {
            return Task.FromResult<SignalResponse?>(null);
        }

        var fixture = ResolveFixture(query.SourceKey);
        var records = Filter(fixture, query).ToArray();
        SignalResponse response = new(
            "signal",
            ContractVersion,
            Context,
            query.ToFilters(),
            BuildSignal(fixture, signalId, query, records),
            BuildSeries(records, signalId),
            $"Descriptive counts from the frozen {fixture.Source.ReviewLabel} output. This is synthetic, illustrative, and not calibrated production quality.");
        return Task.FromResult<SignalResponse?>(response);
    }

    public Task<EvidencePageResponse?> GetEvidenceAsync(
        string signalId,
        DashboardQuery query,
        int page,
        int pageSize,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ValidateQuery(query);
        if (!SignalDefinitions.ContainsKey(signalId))
        {
            return Task.FromResult<EvidencePageResponse?>(null);
        }

        var fixture = ResolveFixture(query.SourceKey);
        var matching = Filter(fixture, query)
            .Where(record => record.Signals.Contains(signalId, StringComparer.Ordinal))
            .OrderByDescending(record => record.OccurredAt)
            .ThenBy(record => record.FeedbackId)
            .ToArray();
        var items = matching
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Select(record => ToEvidenceRow(fixture.Source, record, signalId))
            .ToArray();
        EvidencePageResponse response = new(
            "evidence-page",
            ContractVersion,
            Context,
            query.ToFilters(),
            signalId,
            page,
            pageSize,
            matching.Length,
            items);
        return Task.FromResult<EvidencePageResponse?>(response);
    }

    public Task<EvidenceDetailResponse?> GetEvidenceDetailAsync(
        Guid feedbackId,
        Guid decisionId,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        DemoFixture? fixture = null;
        DemoRecord? record = null;
        foreach (var candidateFixture in _fixtures.Values)
        {
            var candidateRecord = candidateFixture.Records.SingleOrDefault(candidate =>
                candidate.FeedbackId == feedbackId && candidate.DecisionId == decisionId);
            if (candidateRecord is null)
            {
                continue;
            }

            fixture = candidateFixture;
            record = candidateRecord;
            break;
        }
        if (fixture is null || record is null)
        {
            return Task.FromResult<EvidenceDetailResponse?>(null);
        }

        var inclusionReason = record.Signals.Count == 0
            ? $"Included as an eligible record in the synthetic {fixture.Source.ReviewLabel} output."
            : $"The {fixture.Source.ReviewLabel} marks this record as contributing to: {string.Join(", ", record.Signals.Select(IdToLabel))}.";
        var answers = record.Answers
            .OrderBy(pair => Array.IndexOf(AnswerLabels.Keys.ToArray(), pair.Key))
            .Select(pair => new Answer(
                pair.Key,
                AnswerLabels.GetValueOrDefault(pair.Key, IdToLabel(pair.Key)),
                pair.Value.Type,
                pair.Value.Value,
                $"{fixture.Source.ReviewLabel} · illustrative",
                "illustrative_eligible"))
            .ToArray();
        var traceId = record.FeedbackId.ToByteArray();
        traceId[0] ^= 0x5a;
        EvidenceDetailResponse response = new(
            "evidence-detail",
            ContractVersion,
            Context,
            ToSourceIdentity(fixture.Source),
            new EvidenceRow(
                record.FeedbackId,
                record.DecisionId,
                record.OccurredAt,
                record.SourceRecordId,
                record.Channel,
                record.Product,
                Excerpt(record.Body),
                "permitted_synthetic",
                inclusionReason),
            new EvidenceContent("permitted_synthetic", record.Title, record.Body),
            answers,
            new Provenance(
                record.DecisionId,
                "feedback-decision",
                "1.0.0",
                fixture.Source.ModelVersion,
                $"demo/{fixture.Source.DatasetVersion}",
                "illustrative",
                new Guid(traceId),
                record.OccurredAt.AddMinutes(1)),
            inclusionReason);
        return Task.FromResult<EvidenceDetailResponse?>(response);
    }

    private static SignalSummary BuildSignal(
        DemoFixture fixture,
        string signalId,
        DashboardQuery query,
        DemoRecord[] records)
    {
        var definition = SignalDefinitions[signalId];
        var numerator = records.Count(record => record.Signals.Contains(signalId, StringComparer.Ordinal));
        var denominator = records.Length;
        var comparisonFrom = query.From - (query.ToExclusive - query.From);
        var comparisonRecords = Filter(
            fixture,
            query with { From = comparisonFrom, ToExclusive = query.From }).ToArray();
        var comparisonNumerator = comparisonRecords.Count(record =>
            record.Signals.Contains(signalId, StringComparer.Ordinal));
        var comparison = comparisonRecords.Length == 0
            ? null
            : new Comparison(
                new TimeRange(comparisonFrom, query.From),
                comparisonNumerator,
                comparisonRecords.Length,
                Rate(comparisonNumerator, comparisonRecords.Length));
        var rate = Rate(numerator, denominator);
        double? delta = comparison?.Rate is null || rate is null
            ? null
            : rate.Value - comparison.Rate.Value;
        return new SignalSummary(
            signalId,
            definition.Label,
            definition.Definition,
            numerator,
            denominator,
            rate,
            comparison,
            delta,
            denominator > 0 ? Availability.Available : Availability.Unavailable("no_eligible_evidence"));
    }

    private static SeriesPoint[] BuildSeries(
        DemoRecord[] records,
        string? selectedSignal)
    {
        var periods = records
            .GroupBy(record => new DateTimeOffset(record.OccurredAt.Year, record.OccurredAt.Month, 1, 0, 0, 0, TimeSpan.Zero))
            .OrderBy(group => group.Key);
        return periods.Select(group =>
        {
            var periodRecords = group.ToArray();
            var numerator = selectedSignal is not null && SignalDefinitions.ContainsKey(selectedSignal)
                ? periodRecords.Count(record => record.Signals.Contains(selectedSignal, StringComparer.Ordinal))
                : selectedSignal is not null
                    ? periodRecords.Count(record => record.Topic == selectedSignal)
                    : periodRecords.Count(record => record.Signals.Count > 0);
            return new SeriesPoint(group.Key, periodRecords.Length, periodRecords.Length, numerator,
                Rate(numerator, periodRecords.Length));
        }).ToArray();
    }

    private static IEnumerable<DemoRecord> Filter(DemoFixture fixture, DashboardQuery query) =>
        fixture.Records.Where(record =>
            record.OccurredAt >= query.From &&
            record.OccurredAt < query.ToExclusive &&
            (query.Topic is null || record.Topic == query.Topic) &&
            (query.Product is null || record.Product == query.Product) &&
            (query.Category is null || record.Category == query.Category) &&
            (query.Language is null || record.Language == query.Language) &&
            (query.Channel is null || record.Channel == query.Channel));

    private void ValidateQuery(DashboardQuery query)
    {
        ResolveFixture(query.SourceKey);
        if (query.ToExclusive <= query.From)
        {
            throw new ArgumentException("toExclusive must be later than from.");
        }
    }

    private DemoFixture ResolveFixture(string? sourceKey)
    {
        var selectedKey = sourceKey ?? DefaultSourceKey;
        return _fixtures.TryGetValue(selectedKey, out var fixture)
            ? fixture
            : throw new DashboardSourceNotFoundException(selectedKey);
    }

    private static DemoFixture LoadFixture(string contentRootPath, string fileName)
    {
        var path = Path.Combine(contentRootPath, "Fixtures", fileName);
        using var stream = File.OpenRead(path);
        return JsonSerializer.Deserialize<DemoFixture>(stream, FixtureJsonOptions)
            ?? throw new InvalidOperationException($"Dashboard demo fixture '{fileName}' is empty.");
    }

    private static SourceIdentity ToSourceIdentity(DemoSource source) =>
        new(source.Key, source.ProviderId, source.DatasetName, source.DatasetVersion, source.DisplayName, true);

    private static EvidenceRow ToEvidenceRow(
        DemoSource source,
        DemoRecord record,
        string signalId) =>
        new(
            record.FeedbackId,
            record.DecisionId,
            record.OccurredAt,
            record.SourceRecordId,
            record.Channel,
            record.Product,
            Excerpt(record.Body),
            "permitted_synthetic",
            $"The {source.ReviewLabel} marks this record as contributing to {IdToLabel(signalId)}; this is illustrative demo evidence.");

    private static double? Rate(int numerator, int denominator) =>
        denominator == 0 ? null : Math.Round(numerator * 100d / denominator, 2);

    private static string Excerpt(string body) => body.Length <= 120 ? body : $"{body[..117]}…";

    private static string IdToLabel(string id) =>
        SignalDefinitions.TryGetValue(id, out var definition) ? definition.Label : id.Replace('_', ' ');

    private sealed record DemoFixture(DemoSource Source, IReadOnlyList<DemoRecord> Records);

    private sealed record DemoSource(
        string Key,
        string ProviderId,
        string DatasetName,
        string DatasetVersion,
        string DisplayName,
        bool Synthetic,
        string ModelVersion,
        string ReviewLabel,
        string ProjectionDestination);

    private sealed record DemoRecord(
        Guid FeedbackId,
        Guid DecisionId,
        DateTimeOffset OccurredAt,
        string SourceRecordId,
        string Channel,
        string Product,
        string Category,
        string Language,
        string Title,
        string Body,
        string Topic,
        IReadOnlyList<string> Signals,
        IReadOnlyDictionary<string, DemoAnswer> Answers);

    private sealed record DemoAnswer(string Type, JsonElement Value);
}
