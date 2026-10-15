using System;
using System.IO;
using System.Text.Json;
using Xunit;

namespace RevitBridge.Tests;

/// <summary>Tests that change process environment variables must not run in parallel with each other.</summary>
[CollectionDefinition(Name, DisableParallelization = true)]
public sealed class EnvironmentCollection
{
    public const string Name = "environment";
}

internal sealed class FakeClock
{
    public DateTime Now { get; set; } = new DateTime(2026, 1, 1, 12, 0, 0, DateTimeKind.Utc);
    public DateTime Read() => Now;
    public void Advance(TimeSpan span) => Now += span;
}

/// <summary>Sets environment variables for one test and restores them on dispose.</summary>
internal sealed class EnvScope : IDisposable
{
    private readonly (string Name, string? Old)[] _saved;

    public EnvScope(params (string Name, string? Value)[] values)
    {
        _saved = new (string, string?)[values.Length];
        for (var i = 0; i < values.Length; i++)
        {
            _saved[i] = (values[i].Name, Environment.GetEnvironmentVariable(values[i].Name));
            Environment.SetEnvironmentVariable(values[i].Name, values[i].Value);
        }
    }

    public void Dispose()
    {
        foreach (var (name, old) in _saved) Environment.SetEnvironmentVariable(name, old);
    }
}

internal static class Json
{
    public static JsonElement Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }
}

internal sealed class TempDir : IDisposable
{
    public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "aec-bridge-tests-" + Guid.NewGuid().ToString("N"));

    public TempDir() => Directory.CreateDirectory(Path);

    public void Dispose()
    {
        try { Directory.Delete(Path, true); } catch { /* best effort */ }
    }
}
