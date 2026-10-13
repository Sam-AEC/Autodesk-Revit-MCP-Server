using System;
using System.Collections.Concurrent;
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

public class CommandQueue
{
    private readonly ConcurrentQueue<CommandRequest> _queue = new();
    private readonly ConcurrentDictionary<string, TaskCompletionSource<CommandResponse>> _pending = new();
    // Ids that are queued or running right now. A client that times out and retries with the same
    // request id must wait for that work, not queue a second copy of it: a heavy command queued three
    // times ran three times in a row and froze Revit.
    private readonly ConcurrentDictionary<string, byte> _inflight = new();

    public int Count => _queue.Count;

    public void Enqueue(CommandRequest request)
    {
        _pending.GetOrAdd(request.RequestId, _ => new TaskCompletionSource<CommandResponse>());
        if (!_inflight.TryAdd(request.RequestId, 0))
        {
            return;
        }

        _queue.Enqueue(request);
    }

    public bool TryDequeue(out CommandRequest? request)
    {
        return _queue.TryDequeue(out request);
    }

    /// <summary>
    /// False when nobody is waiting for this request any more (the HTTP call timed out and no retry
    /// came). Such a request is dropped before it starts instead of running for nothing.
    /// </summary>
    public bool IsWanted(string requestId) => _pending.ContainsKey(requestId);

    public void Complete(string requestId, CommandResponse response)
    {
        _inflight.TryRemove(requestId, out _);
        if (_pending.TryRemove(requestId, out var tcs))
        {
            tcs.SetResult(response);
        }
    }

    public async Task<CommandResponse> WaitForResponse(string requestId, int timeoutMs = 30000)
    {
        if (!_pending.TryGetValue(requestId, out var tcs))
        {
            throw new InvalidOperationException($"No pending request: {requestId}");
        }

        var timeoutTask = Task.Delay(timeoutMs);
        var completedTask = await Task.WhenAny(tcs.Task, timeoutTask);

        if (completedTask == timeoutTask)
        {
            _pending.TryRemove(requestId, out _);
            return new CommandResponse
            {
                Status = "error",
                Message = $"Request {requestId} timed out after {timeoutMs}ms"
            };
        }

        return await tcs.Task;
    }
}
