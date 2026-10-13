using System;
using Autodesk.Revit.UI;
using Serilog;

namespace RevitBridge.Bridge;

public class RevitCommandExecutor : IExternalEventHandler
{
    private readonly CommandQueue _queue;

    /// <summary>Set by App after the event is created, so the executor can ask Revit for another turn.</summary>
    public ExternalEvent? Event { get; set; }

    public RevitCommandExecutor(CommandQueue queue)
    {
        _queue = queue;
    }

    public void Execute(UIApplication app)
    {
        // One request per turn. Looping over the whole queue inside a single Execute kept Revit's
        // UI thread busy until every queued request finished; now Revit processes its own messages
        // between requests, and we ask for another turn if more are waiting.
        try
        {
            while (_queue.TryDequeue(out var request))
            {
                if (request == null) continue;

                if (!_queue.IsWanted(request.RequestId))
                {
                    Log.Information("Skipping {Tool} request {RequestId}: the caller gave up waiting for it", request.Tool, request.RequestId);
                    _queue.Complete(request.RequestId, new CommandResponse { Status = "error", Tool = request.Tool, Message = "Abandoned before it started" });
                    continue;
                }

                RunOne(app, request);
                break;
            }
        }
        finally
        {
            if (_queue.Count > 0)
            {
                try { Event?.Raise(); } catch (Exception ex) { Log.Warning(ex, "Could not re-raise the command executor"); }
            }
        }
    }

    private void RunOne(UIApplication app, CommandRequest request)
    {
        try
        {
            Log.Information("Executing {Tool} request {RequestId}", request.Tool, request.RequestId);

            var result = BridgeCommandFactory.Execute(app, request.Tool, request.Payload);

            _queue.Complete(request.RequestId, new CommandResponse
            {
                Status = "ok",
                Tool = request.Tool,
                Result = result
            });
            Log.Information("Completed {Tool} request {RequestId}", request.Tool, request.RequestId);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Error executing {Tool} request {RequestId}", request.Tool, request.RequestId);

            _queue.Complete(request.RequestId, new CommandResponse
            {
                Status = "error",
                Tool = request.Tool,
                Message = ex.Message,
                StackTrace = ex.StackTrace
            });
        }
    }

    public string GetName() => "AEC Model Bridge Command Executor";
}
