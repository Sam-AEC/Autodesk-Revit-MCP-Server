using System;
using System.IO;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.Revit.UI;
using Serilog;

namespace RevitBridge.Bridge;

public class BridgeServer
{
    private readonly HttpListener _listener;
    private readonly CommandQueue _queue;
    private readonly ExternalEvent _externalEvent;
    private CancellationTokenSource _cts = new();
    private readonly DateTime _startTime = DateTime.UtcNow;
    private Task? _listenerTask;
    private int _totalRequests = 0;
    private int _activeConnections = 0;

    public BridgeServer(CommandQueue queue, ExternalEvent externalEvent, string prefix = "http://127.0.0.1:3000/")
    {
        _queue = queue;
        _externalEvent = externalEvent;
        _listener = new HttpListener();
        _listener.Prefixes.Add(prefix);
    }

    public bool IsListening { get; private set; }
    public bool IsRunning => IsListening;
    public int ActiveConnections => _activeConnections;
    public int TotalRequests => _totalRequests;
    public double UptimeSeconds => (DateTime.UtcNow - _startTime).TotalSeconds;

    public void Start()
    {
        if (IsListening) return;

        try
        {
            if (_cts.IsCancellationRequested)
                _cts = new CancellationTokenSource();

            _listener.Start();
            _listenerTask = Task.Run(ListenerLoop, _cts.Token);
            IsListening = true;
            Log.Information("BridgeServer started on {Prefixes}", string.Join(", ", _listener.Prefixes));
        }
        catch (Exception ex)
        {
             Log.Error(ex, "Failed to start listener");
             IsListening = false;
        }
    }

    public void Stop()
    {
        if (!IsListening) return;

        try
        {
            _cts.Cancel();
            _listener.Stop();
            // _listenerTask?.Wait(5000); // Avoid blocking UI thread
            IsListening = false;
            Log.Information("BridgeServer stopped");
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Failed to stop listener");
        }
    }

    private async Task ListenerLoop()
    {
        while (!_cts.Token.IsCancellationRequested)
        {
            try
            {
                var context = await _listener.GetContextAsync();
                _ = Task.Run(() => HandleRequest(context), _cts.Token);
            }
            catch (HttpListenerException) when (_cts.Token.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                Log.Error(ex, "Listener error");
            }
        }
    }

    private async Task HandleRequest(HttpListenerContext context)
    {
        Interlocked.Increment(ref _activeConnections);
        Interlocked.Increment(ref _totalRequests);

        try
        {
            var path = context.Request.Url?.AbsolutePath ?? "/";

            if (path == "/health")
            {
                await HandleHealth(context);
            }
            else if (path == "/tools")
            {
                await HandleTools(context);
            }
            else if (path == "/execute" && context.Request.HttpMethod == "POST")
            {
                await HandleExecute(context);
            }
            else
            {
                Respond(context, 404, new { error = "Not found" });
            }
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Request handling error");
            Respond(context, 500, new { error = ex.Message });
        }
        finally
        {
            Interlocked.Decrement(ref _activeConnections);
        }
    }

    private async Task HandleExecute(HttpListenerContext context)
    {
        var startTime = DateTime.UtcNow;

        using var reader = new StreamReader(context.Request.InputStream);
        var body = await reader.ReadToEndAsync();
        var doc = JsonDocument.Parse(body);
        var root = doc.RootElement;

        var requestId = root.GetProperty("request_id").GetString() ?? Guid.NewGuid().ToString();
        var tool = root.GetProperty("tool").GetString() ?? string.Empty;
        var payload = root.GetProperty("payload");

        var request = new CommandRequest
        {
            RequestId = requestId,
            Tool = tool,
            Payload = payload
        };

        Log.Information("Request received: {RequestId} {Tool} from {ClientIP}",
            requestId, tool, context.Request.RemoteEndPoint?.Address.ToString());

        _queue.Enqueue(request);
        _externalEvent.Raise();

        var response = await _queue.WaitForResponse(requestId);

        Log.Information("Request completed: {RequestId} {Tool} {Status} {DurationMs}ms",
            requestId, tool, response.Status, (DateTime.UtcNow - startTime).TotalMilliseconds);

        Respond(context, 200, response);
    }

    private Task HandleHealth(HttpListenerContext context)
    {
        var health = new
        {
            status = "healthy",
            version = System.Reflection.Assembly.GetExecutingAssembly().GetName().Version?.ToString(),
            uptime_seconds = (DateTime.UtcNow - _startTime).TotalSeconds,
            revit_version = App.RevitVersion ?? "unknown",
            active_document = App.ActiveDocumentName ?? "none"
        };
        Respond(context, 200, health);
        return Task.CompletedTask;
    }

    private Task HandleTools(HttpListenerContext context)
    {
        var tools = BridgeCommandFactory.GetToolCatalog();
        Respond(context, 200, new { tools });
        return Task.CompletedTask;
    }

    private void Respond(HttpListenerContext context, int statusCode, object data)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/json";
        var json = JsonSerializer.Serialize(data);
        var buffer = Encoding.UTF8.GetBytes(json);
        context.Response.OutputStream.Write(buffer, 0, buffer.Length);
        context.Response.Close();
    }
}
