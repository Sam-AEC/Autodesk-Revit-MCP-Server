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

    public void Enqueue(CommandRequest request)
    {
        var tcs = new TaskCompletionSource<CommandResponse>();
        _pending[request.RequestId] = tcs;
        _queue.Enqueue(request);
    }

    public bool TryDequeue(out CommandRequest? request)
    {
        return _queue.TryDequeue(out request);
    }

    public void Complete(string requestId, CommandResponse response)
    {
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
