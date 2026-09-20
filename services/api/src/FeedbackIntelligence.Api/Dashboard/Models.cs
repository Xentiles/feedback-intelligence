namespace FeedbackIntelligence.Api.Dashboard;

public sealed record SourceIdentity(
    string Key,
    string ProviderId,
    string DatasetName,
    string DatasetVersion,
    string DisplayName,
    bool Synthetic);

public sealed record TimeRange(DateTimeOffset From, DateTimeOffset ToExclusive);

public sealed record DashboardFilters(
    string SourceKey,
    DateTimeOffset From,
    DateTimeOffset ToExclusive,
    string? Topic,
    string? Product,
    string? Category,
    string? Language,
    string? Channel);

public sealed record Capabilities(
    bool Products,
    bool Categories,
    bool Languages,
    bool Channels,
    bool EvidenceText);

public sealed record FilterOptions(
    IReadOnlyList<string> Topics,
    IReadOnlyList<string> Products,
    IReadOnlyList<string> Categories,
    IReadOnlyList<string> Languages,
    IReadOnlyList<string> Channels);

public sealed record Availability(string State, string? Reason)
{
    public static Availability Available { get; } = new("available", null);

    public static Availability Unavailable(string reason) => new("unavailable", reason);
}

public sealed record MetadataResponse(
    string Kind,
    string ContractVersion,
    string Context,
    SourceIdentity? Source,
    IReadOnlyList<SourceIdentity> Sources,
    TimeRange? AvailableRange,
    Capabilities Capabilities,
    FilterOptions FilterOptions,
    string PolicyStatus);

public sealed record Metric(
    string Id,
    string Label,
    string Unit,
    double? Value,
    int? Numerator,
    int? Denominator,
    Availability Availability);

public sealed record ProcessingSummary(
    int FeedbackRecords,
    int DecisionRuns,
    int TypedAnswers,
    IReadOnlyDictionary<string, int> JobsByStatus,
    IReadOnlyDictionary<string, int> ProjectionByDestination);

public sealed record SeriesPoint(
    DateTimeOffset PeriodStart,
    int ImportedCount,
    int EligibleCount,
    int TopicNumerator,
    double? Value);

public sealed record Comparison(TimeRange Range, int Numerator, int Denominator, double? Rate);

public sealed record SignalSummary(
    string Id,
    string Label,
    string Definition,
    int Numerator,
    int Denominator,
    double? Rate,
    Comparison? Comparison,
    double? DeltaPoints,
    Availability Availability);

public sealed record OverviewResponse(
    string Kind,
    string ContractVersion,
    string Context,
    DashboardFilters Filters,
    ProcessingSummary Processing,
    IReadOnlyList<Metric> Metrics,
    IReadOnlyList<SeriesPoint> Series,
    IReadOnlyList<SignalSummary> Signals);

public sealed record SignalResponse(
    string Kind,
    string ContractVersion,
    string Context,
    DashboardFilters Filters,
    SignalSummary Signal,
    IReadOnlyList<SeriesPoint> Series,
    string Method);

public sealed record EvidenceRow(
    Guid FeedbackId,
    Guid DecisionId,
    DateTimeOffset OccurredAt,
    string SourceRecordId,
    string? Channel,
    string? ProductLabel,
    string? Excerpt,
    string EvidenceAccess,
    string InclusionReason);

public sealed record EvidencePageResponse(
    string Kind,
    string ContractVersion,
    string Context,
    DashboardFilters Filters,
    string SignalId,
    int Page,
    int PageSize,
    int Total,
    IReadOnlyList<EvidenceRow> Items);

public sealed record Answer(
    string QuestionId,
    string Label,
    string Primitive,
    object? Value,
    string? ConfidenceLabel,
    string Eligibility);

public sealed record Provenance(
    Guid DecisionId,
    string SchemaName,
    string SchemaVersion,
    string ModelVersion,
    string? PolicyVersion,
    string PolicyStatus,
    Guid TraceId,
    DateTimeOffset DecidedAt);

public sealed record EvidenceContent(string Access, string? Title, string? Body);

public sealed record EvidenceDetailResponse(
    string Kind,
    string ContractVersion,
    string Context,
    SourceIdentity Source,
    EvidenceRow Record,
    EvidenceContent Evidence,
    IReadOnlyList<Answer> Answers,
    Provenance Provenance,
    string InclusionReason);

public sealed record DashboardQuery(
    string SourceKey,
    DateTimeOffset From,
    DateTimeOffset ToExclusive,
    string? Topic,
    string? Product,
    string? Category,
    string? Language,
    string? Channel)
{
    public DashboardFilters ToFilters() =>
        new(SourceKey, From, ToExclusive, Topic, Product, Category, Language, Channel);
}
