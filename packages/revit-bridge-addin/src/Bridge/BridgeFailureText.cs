using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace RevitBridge.Bridge;

public sealed class BridgeFailureMessage
{
    [JsonPropertyName("severity")]
    public string Severity { get; set; } = "";
    [JsonPropertyName("message")]
    public string Message { get; set; } = "";
    [JsonPropertyName("failure_id")]
    public string FailureId { get; set; } = "";
    [JsonPropertyName("element_ids")]
    public List<long> ElementIds { get; set; } = new();
    [JsonPropertyName("additional_element_ids")]
    public List<long> AdditionalElementIds { get; set; } = new();
}

/// <summary>
/// How a failed checked transaction is worded and which element ids it reports. No Revit types here
/// (the status arrives as text), so packages/revit-bridge-addin-tests can cover it.
/// </summary>
internal static class BridgeFailureText
{
    public static string Describe(string name, string status,
        IEnumerable<BridgeFailureMessage> messages, Exception? inner)
    {
        var details = messages.Select(m => $"{m.Severity}: {m.Message} (element ids: "
            + string.Join(", ", m.ElementIds.Concat(m.AdditionalElementIds).Distinct()) + ")").ToList();
        if (inner != null) details.Add(inner.Message);
        return $"Transaction '{name}' did not commit (status: {status}). " + string.Join("; ", details);
    }

    public static List<long> FailedElementIds(IEnumerable<BridgeFailureMessage> messages)
    {
        return messages.Where(m => m.Severity != "Warning" && m.Severity != "None")
            .SelectMany(m => m.ElementIds.Concat(m.AdditionalElementIds)).Distinct().ToList();
    }

    public static List<BridgeFailureMessage> Warnings(IEnumerable<BridgeFailureMessage> messages)
    {
        return messages.Where(m => m.Severity == "Warning").ToList();
    }
}

internal static class BridgeTransactionResults
{
    public static object AppendWarnings(object result, IReadOnlyList<BridgeFailureMessage> messages)
    {
        if (messages.Count == 0) return result;
        var serialized = JsonSerializer.SerializeToElement(result);
        var fields = new Dictionary<string, object?>();
        if (serialized.ValueKind == JsonValueKind.Object)
            foreach (var property in serialized.EnumerateObject())
                fields[property.Name] = property.Value.Clone();
        else
            fields["result"] = serialized;

        var warnings = new List<object>();
        if (fields.TryGetValue("warnings", out var previous) && previous is JsonElement old
            && old.ValueKind == JsonValueKind.Array)
            warnings.AddRange(old.EnumerateArray().Select(value => (object)value.Clone()));
        warnings.AddRange(messages.Where(message => message.Severity == "Warning"));
        fields["warnings"] = warnings;
        fields["revit_messages"] = messages;
        return fields;
    }
}
