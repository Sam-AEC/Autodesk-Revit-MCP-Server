using System;
using System.Text.Json;

namespace RevitBridge.Bridge;

/// <summary>
/// Finds the path-like strings in a request payload and hands each to the workspace check.
/// No Revit types here, so packages/revit-bridge-addin-tests can cover it.
/// </summary>
internal static class PayloadPathValidator
{
    /// <summary>
    /// Walks objects and arrays. Every string value whose property name contains "path" or "file"
    /// (any case) goes to <paramref name="assertInWorkspace"/>, which throws when the path is not allowed.
    /// </summary>
    public static void Validate(JsonElement element, Action<string> assertInWorkspace)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in element.EnumerateObject())
            {
                var name = property.Name.ToLower();
                if (property.Value.ValueKind == JsonValueKind.String)
                {
                    var val = property.Value.GetString();
                    if (!string.IsNullOrEmpty(val) && (name.Contains("path") || name.Contains("file")))
                    {
                        assertInWorkspace(val!);
                    }
                }
                else
                {
                    Validate(property.Value, assertInWorkspace);
                }
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray())
            {
                Validate(item, assertInWorkspace);
            }
        }
    }
}
