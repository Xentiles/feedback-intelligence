using System.Text.Json;
using System.Text.RegularExpressions;

namespace FeedbackIntelligence.Api.Workbench;

public sealed record ModelCatalogEntry(string slug, string displayName, string[]? reasoningEfforts, string capabilitySource, string? capabilityReviewedAt);

public static partial class ModelCapabilities
{
    private static readonly string[] Reasoning = ["low", "medium", "high", "xhigh", "max"];
    private static readonly string[] OptionalReasoning = ["none", "low", "medium", "high", "xhigh", "max"];
    private static readonly string[] Mini = ["none", "low", "medium", "high", "xhigh"];
    private static readonly HashSet<string> Values = ["none", "minimal", "low", "medium", "high", "xhigh", "max"];

    public static ModelCatalogEntry Describe(string slug, string displayName, JsonElement provider)
    {
        foreach (var property in new[] { "supported_reasoning_efforts", "supported_reasoning_levels" })
        {
            if (!provider.TryGetProperty(property, out var levels) || levels.ValueKind != JsonValueKind.Array) continue;
            var values = levels.EnumerateArray().Select(level => level.ValueKind == JsonValueKind.String ? level.GetString() :
                level.ValueKind == JsonValueKind.Object && level.TryGetProperty("effort", out var effort) && effort.ValueKind == JsonValueKind.String ? effort.GetString() : null).ToArray();
            if (values.All(value => value is not null && Values.Contains(value)))
                return new(slug, displayName, values.Select(value => value!).Distinct(StringComparer.Ordinal).ToArray(), "catalog", null);
        }
        var identity = SnapshotSuffix().Replace(slug, "");
        var documented = identity switch
        {
            "gpt-6-astra" or "gpt-6.1-sol" => Reasoning,
            "gpt-6-sol" or "gpt-6-luna" => OptionalReasoning,
            "gpt-5.4-mini" or "gpt-5.4-nano" => Mini,
            _ => null
        };
        return new(slug, displayName, documented, documented is null ? "unknown" : "documented", documented is null ? null : "2026-10-02");
    }

    public static bool AcceptsEffort(ModelCatalogEntry model, JsonElement effort) => effort.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined ||
        effort.ValueKind == JsonValueKind.String && model.reasoningEfforts is not null && model.reasoningEfforts.Contains(effort.GetString(), StringComparer.Ordinal);

    [GeneratedRegex(@"-\d{4}-\d{2}-\d{2}$", RegexOptions.CultureInvariant)]
    private static partial Regex SnapshotSuffix();
}
