using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace FeedbackIntelligence.Api.Ingestion;

public static partial class IngestionValidator
{
    private static readonly JsonSerializerOptions CanonicalJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    private static readonly Guid FeedbackNamespace =
        Guid.Parse("f31fe881-b783-42b2-851e-ce62ab486855");

    private static readonly Guid JobNamespace =
        Guid.Parse("705aa244-e7a5-42e6-bc1f-da629fd24ec4");

    public static IngestionCommand Validate(
        FeedbackIngestionRequest record,
        IngestionOptions options)
    {
        if (!options.Enabled)
        {
            throw new IngestionUnavailableException(
                "Feedback ingestion is disabled for this deployment.");
        }

        if (record.SchemaVersion != "feedback-record/1.0.0")
        {
            throw new ArgumentException("schemaVersion must be 'feedback-record/1.0.0'.");
        }

        if (record.Source is null)
        {
            throw new ArgumentException("source is required.");
        }

        RequireText(record.Source.ProviderId, "source.providerId", 100);
        RequireText(record.Source.DatasetName, "source.datasetName", 200);
        RequireText(record.Source.DatasetVersion, "source.datasetVersion", 100);
        RequireText(record.Source.SourceRecordId, "source.sourceRecordId", 200);
        RequireText(record.OriginalText, "originalText", options.MaximumTextCharacters);

        if (record.Title?.Length > 500)
        {
            throw new ArgumentException("title cannot exceed 500 characters.");
        }

        if (record.OccurredAt == default)
        {
            throw new ArgumentException("occurredAt is required.");
        }

        if (record.OccurredAt.Offset != TimeSpan.Zero)
        {
            throw new ArgumentException("occurredAt must be an ISO-8601 UTC date-time.");
        }

        if (record.PrivacyStatus != "uninspected")
        {
            throw new ArgumentException("privacyStatus must be 'uninspected'.");
        }

        if (record.Metadata.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("metadata must be an object.");
        }

        var expectedFeedbackId = CreateVersion5(
            FeedbackNamespace,
            $"{record.Source.ProviderId}:{record.Source.SourceRecordId}");
        if (record.FeedbackId != expectedFeedbackId)
        {
            throw new ArgumentException(
                "feedbackId must be the deterministic UUID for source.providerId and source.sourceRecordId.");
        }

        ValidateRating(record.Rating);
        ValidateProducts(record.RelatedProducts);
        ValidateOperationalContext(record.OperationalContext);

        if (ContainsPaymentCard(record.OriginalText))
        {
            throw new ArgumentException("originalText appears to contain payment-card data.");
        }

        var identity = string.Join(
            ':',
            record.FeedbackId,
            options.DecisionSchemaSha256,
            options.DecisionEngine.ToConfigurationValue(),
            options.RequestedModel);
        var jobId = CreateVersion5(JobNamespace, identity);
        var idempotencyKey = $"sha256:{Sha256(identity)}";
        var canonicalSha256 = CanonicalSha256(record);
        return new IngestionCommand(record, jobId, idempotencyKey, canonicalSha256, options);
    }

    private static void ValidateRating(Rating? rating)
    {
        if (rating is null)
        {
            return;
        }

        if (rating.ScaleMin >= rating.ScaleMax
            || rating.Value < rating.ScaleMin
            || rating.Value > rating.ScaleMax)
        {
            throw new ArgumentException("rating must be within a valid declared scale.");
        }
    }

    private static void ValidateProducts(IReadOnlyList<RelatedProduct>? products)
    {
        if (products is null)
        {
            throw new ArgumentException("relatedProducts is required.");
        }

        var productIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var product in products)
        {
            if (product is null)
            {
                throw new ArgumentException("relatedProducts cannot contain null values.");
            }

            RequireText(product.ProductId, "relatedProducts.productId", 200);
            if (!productIds.Add(product.ProductId))
            {
                throw new ArgumentException("relatedProducts must be unique by productId.");
            }

            if (product.Quantity < 1)
            {
                throw new ArgumentException("relatedProducts.quantity must be at least one.");
            }

            if (product.SellerIds is null
                || product.SellerIds.Any(string.IsNullOrWhiteSpace)
                || product.SellerIds.Distinct(StringComparer.Ordinal).Count() != product.SellerIds.Count)
            {
                throw new ArgumentException(
                    "relatedProducts.sellerIds must contain unique non-blank values.");
            }

            ValidateMoney(product.Price);
            ValidateMoney(product.FreightCost);
        }
    }

    private static void ValidateOperationalContext(OperationalContext? context)
    {
        if (context is null)
        {
            return;
        }

        foreach (var timestamp in new[]
                 {
                     context.PurchasedAt,
                     context.DeliveredAt,
                     context.ExpectedDeliveryAt,
                 })
        {
            if (timestamp.HasValue && timestamp.Value.Offset != TimeSpan.Zero)
            {
                throw new ArgumentException("operationalContext timestamps must be UTC.");
            }
        }

        if (context.SellerCount < 0)
        {
            throw new ArgumentException("operationalContext.sellerCount cannot be negative.");
        }

        ValidateMoney(context.TotalPrice);
        ValidateMoney(context.TotalFreightCost);
    }

    private static void ValidateMoney(Money? money)
    {
        if (money is null)
        {
            return;
        }

        if (!decimal.TryParse(money.Amount, NumberStyles.Number, CultureInfo.InvariantCulture, out _)
            || !CurrencyRegex().IsMatch(money.Currency))
        {
            throw new ArgumentException(
                "money requires a decimal amount and a three-letter uppercase currency.");
        }
    }

    private static void RequireText(string? value, string name, int maximum)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > maximum)
        {
            throw new ArgumentException($"{name} must contain 1 to {maximum} characters.");
        }
    }

    private static string CanonicalSha256(FeedbackIngestionRequest record)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(record, CanonicalJsonOptions);
        return Sha256(bytes);
    }

    private static Guid CreateVersion5(Guid namespaceId, string name)
    {
        var namespaceBytes = namespaceId.ToByteArray();
        SwapGuidByteOrder(namespaceBytes);
        var nameBytes = Encoding.UTF8.GetBytes(name);
        var input = new byte[namespaceBytes.Length + nameBytes.Length];
        namespaceBytes.CopyTo(input, 0);
        nameBytes.CopyTo(input, namespaceBytes.Length);
#pragma warning disable CA5350 // UUIDv5 is defined by RFC 9562 as SHA-1 namespace hashing.
        var hash = SHA1.HashData(input);
#pragma warning restore CA5350
        hash[6] = (byte)((hash[6] & 0x0f) | 0x50);
        hash[8] = (byte)((hash[8] & 0x3f) | 0x80);
        var guidBytes = hash[..16];
        SwapGuidByteOrder(guidBytes);
        return new Guid(guidBytes);
    }

    private static void SwapGuidByteOrder(Span<byte> bytes)
    {
        (bytes[0], bytes[3]) = (bytes[3], bytes[0]);
        (bytes[1], bytes[2]) = (bytes[2], bytes[1]);
        (bytes[4], bytes[5]) = (bytes[5], bytes[4]);
        (bytes[6], bytes[7]) = (bytes[7], bytes[6]);
    }

    private static string Sha256(string value) => Sha256(Encoding.UTF8.GetBytes(value));

    private static string Sha256(byte[] value) =>
        Convert.ToHexStringLower(SHA256.HashData(value));

    private static bool ContainsPaymentCard(string text)
    {
        foreach (Match match in PaymentCardCandidateRegex().Matches(text))
        {
            var digits = string.Concat(match.Value.Where(char.IsAsciiDigit));
            if (digits.Length is >= 13 and <= 19 && PassesLuhn(digits))
            {
                return true;
            }
        }

        return false;
    }

    private static bool PassesLuhn(string digits)
    {
        var sum = 0;
        var doubleDigit = false;
        for (var index = digits.Length - 1; index >= 0; index--)
        {
            var value = digits[index] - '0';
            if (doubleDigit)
            {
                value *= 2;
                if (value > 9)
                {
                    value -= 9;
                }
            }

            sum += value;
            doubleDigit = !doubleDigit;
        }

        return sum % 10 == 0;
    }

    [GeneratedRegex("^[A-Z]{3}$", RegexOptions.CultureInvariant)]
    private static partial Regex CurrencyRegex();

    [GeneratedRegex(@"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)", RegexOptions.CultureInvariant)]
    private static partial Regex PaymentCardCandidateRegex();
}
