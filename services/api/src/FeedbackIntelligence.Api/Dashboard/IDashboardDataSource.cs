namespace FeedbackIntelligence.Api.Dashboard;

public interface IDashboardDataSource
{
    string Context { get; }

    Task<MetadataResponse> GetMetadataAsync(string? sourceKey, CancellationToken cancellationToken);

    Task<OverviewResponse> GetOverviewAsync(DashboardQuery query, CancellationToken cancellationToken);

    Task<SignalResponse?> GetSignalAsync(
        string signalId,
        DashboardQuery query,
        CancellationToken cancellationToken);

    Task<EvidencePageResponse?> GetEvidenceAsync(
        string signalId,
        DashboardQuery query,
        int page,
        int pageSize,
        CancellationToken cancellationToken);

    Task<EvidenceDetailResponse?> GetEvidenceDetailAsync(
        Guid feedbackId,
        Guid decisionId,
        CancellationToken cancellationToken);
}

public sealed class DashboardSourceUnavailableException(string detail, Exception? inner = null)
    : Exception(detail, inner);

public sealed class DashboardSourceNotFoundException(string sourceKey)
    : Exception($"Dashboard source '{sourceKey}' is not available in this context.");
