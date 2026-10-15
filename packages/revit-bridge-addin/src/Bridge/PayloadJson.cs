using System;
using System.Text.Json;

namespace RevitBridge.Bridge;

/// <summary>Small readers for optional payload fields. No Revit types here, so they can be tested without Revit.</summary>
internal static class PayloadJson
{
    /// <summary>The string value, or null when the field is missing, not a string, empty or blank.</summary>
    public static string? OptionalString(JsonElement payload, string name)
    {
        if (!payload.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String)
            return null;
        var text = value.GetString();
        return string.IsNullOrWhiteSpace(text) ? null : text;
    }

    /// <summary>True or false for a JSON boolean, null when missing or null; anything else is an error.</summary>
    public static bool? OptionalBool(JsonElement payload, string name)
    {
        if (!payload.TryGetProperty(name, out var value)) return null;
        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Null => (bool?)null,
            _ => throw new ArgumentException($"{name} must be a boolean")
        };
    }

    /// <summary>The integer field clamped to min..max, or the fallback when missing or not an int.</summary>
    public static int ClampedInt(JsonElement payload, string name, int fallback, int min, int max)
    {
        if (payload.ValueKind == JsonValueKind.Object && payload.TryGetProperty(name, out var el)
            && el.ValueKind == JsonValueKind.Number && el.TryGetInt32(out var v))
        {
            return Math.Max(min, Math.Min(max, v));
        }

        return fallback;
    }
}
