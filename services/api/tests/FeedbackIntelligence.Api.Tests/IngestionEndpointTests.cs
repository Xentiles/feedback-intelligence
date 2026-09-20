using System.Diagnostics;
using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Nodes;
using FeedbackIntelligence.Api.Ingestion;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace FeedbackIntelligence.Api.Tests;

public sealed class IngestionEndpointTests
{
    private const string ValidRecord = """
        {
          "schemaVersion": "feedback-record/1.0.0",
          "feedbackId": "1c10e7d7-057b-5b2b-ac6d-fa0b943504c4",
          "source": {
            "providerId": "synthetic",
            "datasetName": "Feedback Intelligence synthetic demo",
            "datasetVersion": "demo-data/0.1.0",
            "sourceRecordId": "demo-001"
          },
          "originalText": "The monitor is sharp, bright, and exactly what I hoped for.",
          "title": "Excellent display",
          "occurredAt": "2026-01-05T10:00:00Z",
          "rating": { "value": 5, "scaleMin": 1, "scaleMax": 5 },
          "relatedProducts": [
            {
              "productId": "DISPLAY-A1",
              "productName": "Aster 27-inch display",
              "category": "displays",
              "categoryLanguage": "en",
              "quantity": 1,
              "sellerIds": [],
              "price": null,
              "freightCost": null
            }
          ],
          "orderId": "DEMO-ORDER-001",
          "channel": "product_review",
          "language": "en-GB",
          "metadata": {},
          "operationalContext": null,
          "privacyStatus": "uninspected"
        }
        """;

    [Fact]
    public async Task PostFeedbackCreatesOneDeterministicJobAndIsIdempotent()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();

        using var first = await PostAsync(client, ValidRecord);
        using var second = await PostAsync(client, ValidRecord);
        var firstReceipt = await first.Content.ReadFromJsonAsync<IngestionReceipt>();
        var secondReceipt = await second.Content.ReadFromJsonAsync<IngestionReceipt>();

        Assert.Equal(HttpStatusCode.Accepted, first.StatusCode);
        Assert.Equal(HttpStatusCode.OK, second.StatusCode);
        Assert.NotNull(firstReceipt);
        Assert.NotNull(secondReceipt);
        Assert.True(firstReceipt.Created);
        Assert.False(secondReceipt.Created);
        Assert.Equal(Guid.Parse("a4c820d9-94a8-5a60-97fd-152a20c0a85f"), firstReceipt.JobId);
        Assert.Equal(firstReceipt.JobId, secondReceipt.JobId);
        Assert.Equal(
            "sha256:71fef030622cc254eafb17ff00ee08bb29e9e379cebea64f6764aae1d7429cfc",
            firstReceipt.IdempotencyKey);
        Assert.Equal(2, store.Calls);
        Assert.Single(store.Commands.Select(command => command.IdempotencyKey).Distinct());
    }

    [Fact]
    public async Task PostFeedbackRejectsNonDeterministicFeedbackIdBeforePersistence()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();
        var invalid = ValidRecord.Replace(
            "1c10e7d7-057b-5b2b-ac6d-fa0b943504c4",
            "00000000-0000-0000-0000-000000000001",
            StringComparison.Ordinal);

        using var response = await PostAsync(client, invalid);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, store.Calls);
    }

    [Fact]
    public async Task PostFeedbackRejectsPaymentCardDataBeforePersistence()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();
        var invalid = ValidRecord.Replace(
            "The monitor is sharp, bright, and exactly what I hoped for.",
            "My card is 4111 1111 1111 1111.",
            StringComparison.Ordinal);

        using var response = await PostAsync(client, invalid);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, store.Calls);
    }

    [Fact]
    public async Task PostFeedbackRejectsNullSourceBeforePersistence()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();
        var invalid = JsonNode.Parse(ValidRecord)!.AsObject();
        invalid["source"] = null;

        using var response = await PostAsync(client, invalid.ToJsonString());

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, store.Calls);
    }

    [Fact]
    public async Task PostFeedbackRejectsMissingOccurredAtBeforePersistence()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();
        var invalid = JsonNode.Parse(ValidRecord)!.AsObject();
        invalid.Remove("occurredAt");

        using var response = await PostAsync(client, invalid.ToJsonString());

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, store.Calls);
    }

    [Fact]
    public async Task PostFeedbackRejectsNullRelatedProductBeforePersistence()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();
        var invalid = JsonNode.Parse(ValidRecord)!.AsObject();
        invalid["relatedProducts"] = new JsonArray((JsonNode?)null);

        using var response = await PostAsync(client, invalid.ToJsonString());

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, store.Calls);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task PostFeedbackAcceptsNullOrOmittedOperationalTimestamps(
        bool includeNullTimestamps)
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();
        var operationalContext = includeNullTimestamps
            ? """
              {
                "purchasedAt": null,
                "deliveredAt": null,
                "expectedDeliveryAt": null,
                "deliveryDeltaDays": null,
                "orderStatus": null,
                "totalPrice": null,
                "totalFreightCost": null,
                "sellerCount": null
              }
              """
            : """
              {
                "deliveryDeltaDays": null,
                "orderStatus": null,
                "totalPrice": null,
                "totalFreightCost": null,
                "sellerCount": null
              }
              """;
        var valid = ValidRecord.Replace(
            "\"operationalContext\": null",
            $"\"operationalContext\": {operationalContext}",
            StringComparison.Ordinal);

        using var response = await PostAsync(client, valid);

        Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        Assert.Single(store.Commands);
    }

    [Fact]
    public async Task PostFeedbackRejectsNonUtcOperationalTimestampsBeforePersistence()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();
        var invalid = ValidRecord.Replace(
            "\"operationalContext\": null",
            """
            "operationalContext": {
              "purchasedAt": "2026-01-05T11:00:00+01:00",
              "deliveredAt": null,
              "expectedDeliveryAt": null,
              "deliveryDeltaDays": null,
              "orderStatus": null,
              "totalPrice": null,
              "totalFreightCost": null,
              "sellerCount": null
            }
            """,
            StringComparison.Ordinal);

        using var response = await PostAsync(client, invalid);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal(0, store.Calls);
    }

    [Fact]
    public async Task PostFeedbackIsUnavailableInReadOnlyDeployments()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: false);
        using var client = factory.CreateClient();

        using var response = await PostAsync(client, ValidRecord);

        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.Equal(0, store.Calls);
    }

    [Fact]
    public async Task PostFeedbackRequiresTheConfiguredIngestionKey()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();

        using var response = await PostAsync(client, ValidRecord, apiKey: "wrong-key");

        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal(0, store.Calls);
    }

    [Fact]
    public async Task PostFeedbackBindsTheDecisionEngineAsTypedConfiguration()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true, engine: "semif");
        using var client = factory.CreateClient();

        using var response = await PostAsync(client, ValidRecord);

        Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        var command = Assert.Single(store.Commands);
        Assert.Equal(DecisionEngineKind.Semif, command.Options.DecisionEngine);
        Assert.Equal("semif", command.Options.DecisionEngine.ToConfigurationValue());
    }

    [Fact]
    public void UnknownDecisionEngineConfigurationFailsBinding()
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Ingestion:DecisionEngine"] = "unknown-provider",
            })
            .Build();

        Assert.Throws<InvalidOperationException>(() =>
            configuration.GetSection("Ingestion").Get<IngestionOptions>());
    }

    [Fact]
    public async Task PostFeedbackUsesTheDedicatedFixedWindowRateLimit()
    {
        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();

        for (var requestNumber = 0; requestNumber < 30; requestNumber++)
        {
            using var accepted = await PostAsync(client, ValidRecord);
            Assert.True(accepted.IsSuccessStatusCode);
        }

        using var rejected = await PostAsync(client, ValidRecord);

        Assert.Equal(HttpStatusCode.TooManyRequests, rejected.StatusCode);
        Assert.Equal(30, store.Calls);
    }

    [Fact]
    public async Task PostFeedbackPropagatesTraceContextWithoutRecordingFeedbackContent()
    {
        var stopped = new List<Activity>();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == "FeedbackIntelligence.Api",
            Sample = (ref ActivityCreationOptions<ActivityContext> _) =>
                ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = stopped.Add,
        };
        ActivitySource.AddActivityListener(listener);

        var store = new FakeIngestionStore();
        using var factory = CreateFactory(store, enabled: true);
        using var client = factory.CreateClient();

        using var response = await PostAsync(client, ValidRecord);

        Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        var command = Assert.Single(store.Commands);
        Assert.NotNull(command.TraceParent);
        Assert.Matches(
            "^00-[0-9a-f]{32}-[0-9a-f]{16}-0[01]$",
            command.TraceParent);

        var ingest = Assert.Single(
            stopped,
            activity => activity.OperationName == "feedback.ingest");
        var recorded = string.Join(
            " ",
            ingest.TagObjects.Select(tag => $"{tag.Key}={tag.Value}"));
        Assert.Contains("decision.engine=rules", recorded, StringComparison.Ordinal);
        Assert.Contains("schema.version=1.0.0", recorded, StringComparison.Ordinal);
        Assert.DoesNotContain("originalText", recorded, StringComparison.Ordinal);
        Assert.DoesNotContain("The monitor is sharp", recorded, StringComparison.Ordinal);
    }

    private static WebApplicationFactory<Program> CreateFactory(
        FakeIngestionStore store,
        bool enabled,
        string engine = "rules")
    {
        return new WebApplicationFactory<Program>().WithWebHostBuilder(builder =>
        {
            builder.ConfigureAppConfiguration((_, configuration) =>
            {
                configuration.AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["Ingestion:Enabled"] = enabled.ToString(),
                    ["Ingestion:ApiKey"] = "test-ingestion-key",
                    ["Ingestion:DecisionEngine"] = engine,
                    ["Ingestion:RequestedModel"] = engine == "semif"
                        ? "semif-qwen3.5-4b-mlx-q4-851bf6e8"
                        : "rules-1.0.0",
                    ["Ingestion:RateLimitPermitLimit"] = "30",
                    ["Ingestion:RateLimitWindowSeconds"] = "60",
                });
            });
            builder.ConfigureServices(services =>
            {
                services.RemoveAll<IFeedbackIngestionStore>();
                services.AddSingleton<IFeedbackIngestionStore>(store);
            });
        });
    }

    private static Task<HttpResponseMessage> PostAsync(
        HttpClient client,
        string body,
        string apiKey = "test-ingestion-key")
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/feedback")
        {
            Content = new StringContent(body, Encoding.UTF8, "application/json"),
        };
        request.Headers.Add("X-Feedback-Ingestion-Key", apiKey);
        return client.SendAsync(request);
    }

    private sealed class FakeIngestionStore : IFeedbackIngestionStore
    {
        private readonly HashSet<string> _keys = new(StringComparer.Ordinal);

        public List<IngestionCommand> Commands { get; } = [];

        public int Calls => Commands.Count;

        public Task<IngestionStoreResult> EnqueueAsync(
            IngestionCommand command,
            CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Commands.Add(command);
            var created = _keys.Add(command.IdempotencyKey);
            return Task.FromResult(new IngestionStoreResult(command.JobId, "pending", created));
        }
    }
}
