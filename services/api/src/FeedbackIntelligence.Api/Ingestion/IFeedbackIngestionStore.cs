namespace FeedbackIntelligence.Api.Ingestion;

public interface IFeedbackIngestionStore
{
    Task<IngestionStoreResult> EnqueueAsync(
        IngestionCommand command,
        CancellationToken cancellationToken);
}
