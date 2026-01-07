using System;
using Autodesk.Revit.UI;
using Serilog;

namespace RevitBridge.Bridge;

public class RevitCommandExecutor : IExternalEventHandler
{
    private readonly CommandQueue _queue;

    public RevitCommandExecutor(CommandQueue queue)
    {
        _queue = queue;
    }

    public void Execute(UIApplication app)
    {
        while (_queue.TryDequeue(out var request))
        {
            if (request == null) continue;

            try
            {
                Log.Information("Executing {Tool} request {RequestId}", request.Tool, request.RequestId);

                var result = BridgeCommandFactory.Execute(app, request.Tool, request.Payload);

                var response = new CommandResponse
                {
                    Status = "ok",
                    Tool = request.Tool,
                    Result = result
                };

                _queue.Complete(request.RequestId, response);
                Log.Information("Completed {Tool} request {RequestId}", request.Tool, request.RequestId);
            }
            catch (Exception ex)
            {
                Log.Error(ex, "Error executing {Tool} request {RequestId}", request.Tool, request.RequestId);

                var errorResponse = new CommandResponse
                {
                    Status = "error",
                    Tool = request.Tool,
                    Message = ex.Message,
                    StackTrace = ex.StackTrace
                };

                _queue.Complete(request.RequestId, errorResponse);
            }
        }
    }

    public string GetName() => "RevitMCP Command Executor";
}
