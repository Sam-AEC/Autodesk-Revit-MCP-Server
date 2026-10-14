using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using System.Text.Json;

namespace RevitBridge.Bridge;

public class CommandRequest
{
    public string RequestId { get; set; } = string.Empty;
    public string Tool { get; set; } = string.Empty;
    public JsonElement Payload { get; set; }
}

public class CommandResponse
{
    public string Status { get; set; } = "ok";
    public string Tool { get; set; } = string.Empty;
    public object? Result { get; set; }
    public string? Message { get; set; }
    public string? StackTrace { get; set; }
}

/// <summary>What the queue knows about one request id: its state and, once finished, the response.</summary>
public sealed class RequestSnapshot
{
    public string RequestId { get; set; } = string.Empty;
    public string Tool { get; set; } = string.Empty;
    /// <summary>queued, running, done or failed.</summary>
    public string State { get; set; } = "queued";
    public long ElapsedMs { get; set; }
    /// <summary>The serialized CommandResponse, set when State is done or failed.</summary>
    public string? ResponseJson { get; set; }

    public bool IsFinished => State == "done" || State == "failed";
}

public class CommandQueue
{
    private sealed class Entry
    {
        public string RequestId = string.Empty;
        public string Tool = string.Empty;
        public string State = "queued";
        public DateTime EnqueuedUtc;
        public DateTime? StartedUtc;
        public DateTime? FinishedUtc;
        public DateTime LastTouchedUtc;
        public string? ResponseJson;
        public TaskCompletionSource<bool> Finished = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool IsFinished => State == "done" || State == "failed";
    }

    private readonly object _sync = new();
    private readonly Queue<CommandRequest> _queue = new();
    private readonly Dictionary<string, Entry> _entries = new();
    // Ids that are queued or running right now. A client that times out and retries with the same
    // request id must wait for that work, not queue a second copy of it: a heavy command queued three
    // times ran three times in a row and froze Revit.
    private readonly ConcurrentDictionary<string, byte> _inflight = new();
    private long _finishedBytes;

    /// <summary>How long a finished result stays retrievable by request id.</summary>
    public TimeSpan ResultTtl { get; } = TimeSpan.FromSeconds(EnvInt("AEC_BRIDGE_RESULT_TTL_SECONDS", 900, 30, 86400));
    /// <summary>A queued request nobody has asked about for this long is dropped before it starts.</summary>
    public TimeSpan AbandonAfter { get; } = TimeSpan.FromSeconds(EnvInt("AEC_BRIDGE_ABANDON_SECONDS", 120, 10, 3600));
    /// <summary>Finished results are kept in memory up to this many entries and bytes (oldest go first).</summary>
    public int MaxFinishedEntries { get; } = EnvInt("AEC_BRIDGE_RESULT_MAX_ENTRIES", 500, 10, 100000);
    public long MaxFinishedBytes { get; } = EnvInt("AEC_BRIDGE_RESULT_MAX_MB", 64, 1, 1024) * 1024L * 1024L;

    public int Count
    {
        get { lock (_sync) { return _queue.Count; } }
    }

    public void Enqueue(CommandRequest request)
    {
        lock (_sync)
        {
            Sweep(DateTime.UtcNow);

            if (_entries.TryGetValue(request.RequestId, out var existing))
            {
                // Same id again: a retry. Finished work is answered from the stored result, never re-run.
                existing.LastTouchedUtc = DateTime.UtcNow;
                if (existing.IsFinished) return;
            }
            else
            {
                var now = DateTime.UtcNow;
                _entries[request.RequestId] = new Entry
                {
                    RequestId = request.RequestId,
                    Tool = request.Tool,
                    EnqueuedUtc = now,
                    LastTouchedUtc = now
                };
            }

            if (!_inflight.TryAdd(request.RequestId, 0))
            {
                return;
            }

            _queue.Enqueue(request);
        }
    }

    public bool TryDequeue(out CommandRequest? request)
    {
        lock (_sync)
        {
            if (_queue.Count > 0)
            {
                request = _queue.Dequeue();
                return true;
            }
        }

        request = null;
        return false;
    }

    /// <summary>
    /// False when nobody is waiting for this request any more (no HTTP call or result poll has asked
    /// about it for AbandonAfter). Such a request is dropped before it starts instead of running for
    /// nothing.
    /// </summary>
    public bool IsWanted(string requestId)
    {
        lock (_sync)
        {
            return _entries.TryGetValue(requestId, out var entry)
                && !entry.IsFinished
                && DateTime.UtcNow - entry.LastTouchedUtc <= AbandonAfter;
        }
    }

    public void MarkRunning(string requestId)
    {
        lock (_sync)
        {
            if (_entries.TryGetValue(requestId, out var entry) && !entry.IsFinished)
            {
                entry.State = "running";
                entry.StartedUtc = DateTime.UtcNow;
            }
        }
    }

    public void Complete(string requestId, CommandResponse response)
    {
        // Serialize now: the result must stay readable after the command is long gone.
        string json;
        try
        {
            json = JsonSerializer.Serialize(response);
        }
        catch (Exception ex)
        {
            json = JsonSerializer.Serialize(new CommandResponse
            {
                Status = "error",
                Tool = response.Tool,
                Message = "The command finished but its result could not be serialized: " + ex.Message
            });
        }

        lock (_sync)
        {
            _inflight.TryRemove(requestId, out _);
            if (!_entries.TryGetValue(requestId, out var entry) || entry.IsFinished) return;

            var now = DateTime.UtcNow;
            entry.State = response.Status == "ok" ? "done" : "failed";
            entry.FinishedUtc = now;
            entry.ResponseJson = json;
            _finishedBytes += json.Length;
            entry.Finished.TrySetResult(true);
            Sweep(now);
        }
    }

    /// <summary>Waits up to timeoutMs for the request to finish; returns its state either way (null if unknown).</summary>
    public async Task<RequestSnapshot?> WaitForResponse(string requestId, int timeoutMs = 30000)
    {
        Task finished;
        lock (_sync)
        {
            if (!_entries.TryGetValue(requestId, out var entry)) return null;
            entry.LastTouchedUtc = DateTime.UtcNow;
            finished = entry.Finished.Task;
        }

        if (!finished.IsCompleted)
        {
            await Task.WhenAny(finished, Task.Delay(timeoutMs));
        }

        return GetSnapshot(requestId);
    }

    /// <summary>The current state of a request, or null if the id is unknown or its result has expired.</summary>
    public RequestSnapshot? GetSnapshot(string requestId)
    {
        lock (_sync)
        {
            if (!_entries.TryGetValue(requestId, out var entry)) return null;
            entry.LastTouchedUtc = DateTime.UtcNow;
            return ToSnapshot(entry, DateTime.UtcNow);
        }
    }

    /// <summary>The request Revit is executing right now, if any.</summary>
    public RequestSnapshot? GetRunning()
    {
        lock (_sync)
        {
            var now = DateTime.UtcNow;
            var running = _entries.Values.FirstOrDefault(e => e.State == "running");
            return running == null ? null : ToSnapshot(running, now);
        }
    }

    public int FinishedCount
    {
        get { lock (_sync) { return _entries.Values.Count(e => e.IsFinished); } }
    }

    private static RequestSnapshot ToSnapshot(Entry entry, DateTime now)
    {
        var since = entry.State == "running" ? entry.StartedUtc ?? entry.EnqueuedUtc : entry.EnqueuedUtc;
        var until = entry.FinishedUtc ?? now;
        return new RequestSnapshot
        {
            RequestId = entry.RequestId,
            Tool = entry.Tool,
            State = entry.State,
            ElapsedMs = (long)(until - since).TotalMilliseconds,
            ResponseJson = entry.ResponseJson
        };
    }

    // Callers hold _sync. Drops expired results, then the oldest ones while over the entry or byte cap.
    private void Sweep(DateTime now)
    {
        var finished = _entries.Values.Where(e => e.IsFinished).OrderBy(e => e.FinishedUtc).ToList();
        var count = finished.Count;
        foreach (var entry in finished)
        {
            var expired = now - (entry.FinishedUtc ?? now) > ResultTtl;
            if (!expired && count <= MaxFinishedEntries && _finishedBytes <= MaxFinishedBytes) break;

            _entries.Remove(entry.RequestId);
            _finishedBytes -= entry.ResponseJson?.Length ?? 0;
            count--;
        }
    }

    private static int EnvInt(string name, int fallback, int min, int max)
    {
        var raw = Environment.GetEnvironmentVariable(name);
        return int.TryParse(raw, out var value) ? Math.Min(max, Math.Max(min, value)) : fallback;
    }
}
