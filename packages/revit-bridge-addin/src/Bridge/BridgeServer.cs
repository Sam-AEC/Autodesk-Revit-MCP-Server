using System;
using System.IO;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Linq;
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
    private SemaphoreSlim _concurrencySemaphore = new(10, 10);
    private const long MaxRequestSizeBytes = 5 * 1024 * 1024; // 5 MB
    private readonly WorkspaceMonitor _workspaceMonitor = new();
    // How long /execute holds the HTTP call before answering "running" (a client can ask for less or more
    // with wait_ms). The command is not cancelled when this passes.
    private static readonly int SoftWaitMs = EnvMs("AEC_BRIDGE_SOFT_WAIT_MS", 25000);
    private const int MaxWaitMs = 55000;

    public BridgeServer(CommandQueue queue, ExternalEvent externalEvent)
    {
        _queue = queue;
        _externalEvent = externalEvent;
        _listener = new HttpListener();
        SessionToken = Guid.NewGuid().ToString("N") + Guid.NewGuid().ToString("N");
        
        var legacyEnv = Environment.GetEnvironmentVariable("MCP_REVIT_LEGACY_PORT");
        LegacyMode = !string.IsNullOrEmpty(legacyEnv) && (legacyEnv.ToLower() == "true" || legacyEnv == "1");
    }

    public CommandQueue Queue => _queue;

    private static int EnvMs(string name, int fallback)
    {
        return int.TryParse(Environment.GetEnvironmentVariable(name), out var value)
            ? Math.Min(MaxWaitMs, Math.Max(1000, value))
            : fallback;
    }

    public string SessionToken { get; }
    public int Port { get; private set; }
    public string RegistryFilePath { get; private set; }
    public bool LegacyMode { get; }

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

            if (LegacyMode)
            {
                Port = 3000;
            }
            else
            {
                var tcp = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
                tcp.Start();
                Port = ((IPEndPoint)tcp.LocalEndpoint).Port;
                tcp.Stop();
            }

            var prefix = $"http://127.0.0.1:{Port}/";
            _listener.Prefixes.Clear();
            _listener.Prefixes.Add(prefix);

            _listener.Start();
            _listenerTask = Task.Run(ListenerLoop, _cts.Token);
            IsListening = true;
            Log.Information("BridgeServer started on {Prefixes}", string.Join(", ", _listener.Prefixes));

            WriteRegistryFile(prefix);
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
            
            if (!string.IsNullOrEmpty(RegistryFilePath) && File.Exists(RegistryFilePath))
            {
                try { File.Delete(RegistryFilePath); } catch { }
            }
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
            await _concurrencySemaphore.WaitAsync(_cts.Token);
        }
        catch (OperationCanceledException)
        {
            Interlocked.Decrement(ref _activeConnections);
            return;
        }

        try
        {
            if (context.Request.ContentLength64 > MaxRequestSizeBytes)
            {
                Respond(context, 413, new { error = "Payload too large" });
                return;
            }

            var path = context.Request.Url?.AbsolutePath ?? "/";

            if (!LegacyMode && path != "/health")
            {
                var authHeader = context.Request.Headers["Authorization"];
                if (string.IsNullOrEmpty(authHeader) || authHeader != $"Bearer {SessionToken}")
                {
                    Respond(context, 401, new { error = "Unauthorized" });
                    return;
                }
            }

            if (path == "/health")
            {
                await HandleHealth(context);
            }
            else if (path == "/tools")
            {
                await HandleTools(context);
            }
            else if (path == "/capabilities")
            {
                await HandleCapabilities(context);
            }
            else if (path == "/execute" && context.Request.HttpMethod == "POST")
            {
                await HandleExecute(context);
            }
            else if (path.StartsWith("/result/", StringComparison.Ordinal) && context.Request.HttpMethod == "GET")
            {
                await HandleResult(context, Uri.UnescapeDataString(path.Substring("/result/".Length)));
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
            _concurrencySemaphore.Release();
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

        try
        {
            ValidatePayloadPaths(payload);
        }
        catch (UnauthorizedAccessException ex)
        {
            Log.Warning("Workspace violation in request {RequestId} {Tool}: {Message}", requestId, tool, ex.Message);
            Respond(context, 403, new { error = "Workspace violation: " + ex.Message });
            return;
        }

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

        var waitMs = SoftWaitMs;
        if (root.TryGetProperty("wait_ms", out var waitProp) && waitProp.ValueKind == JsonValueKind.Number && waitProp.TryGetInt32(out var asked))
        {
            waitMs = Math.Min(MaxWaitMs, Math.Max(0, asked));
        }

        var snapshot = await _queue.WaitForResponse(requestId, waitMs);

        if (snapshot != null && snapshot.IsFinished && snapshot.ResponseJson != null)
        {
            Log.Information("Request completed: {RequestId} {Tool} {State} {DurationMs}ms",
                requestId, tool, snapshot.State, (DateTime.UtcNow - startTime).TotalMilliseconds);
            RespondRaw(context, 200, snapshot.ResponseJson);
            return;
        }

        // Still queued or running: the work goes on and its result is kept. The client collects it
        // with GET /result/{request_id}.
        Log.Information("Request still {State} after {WaitMs}ms: {RequestId} {Tool}", snapshot?.State ?? "unknown", waitMs, requestId, tool);
        Respond(context, 200, new
        {
            status = "running",
            state = snapshot?.State ?? "running",
            request_id = requestId,
            tool,
            elapsed_ms = snapshot?.ElapsedMs ?? 0,
            message = $"Request {requestId} is still {snapshot?.State ?? "running"} in Revit; fetch it with GET /result/{requestId}"
        });
    }

    private Task HandleResult(HttpListenerContext context, string requestId)
    {
        var snapshot = _queue.GetSnapshot(requestId);
        if (snapshot == null)
        {
            Respond(context, 404, new { error = "unknown_or_expired", request_id = requestId });
            return Task.CompletedTask;
        }

        var json = "{\"request_id\":" + JsonSerializer.Serialize(snapshot.RequestId)
            + ",\"tool\":" + JsonSerializer.Serialize(snapshot.Tool)
            + ",\"state\":" + JsonSerializer.Serialize(snapshot.State)
            + ",\"elapsed_ms\":" + snapshot.ElapsedMs
            + ",\"ttl_seconds\":" + (int)_queue.ResultTtl.TotalSeconds
            + ",\"response\":" + (snapshot.ResponseJson ?? "null")
            + "}";
        RespondRaw(context, 200, json);
        return Task.CompletedTask;
    }

    private void ValidatePayloadPaths(JsonElement element)
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
                        _workspaceMonitor.AssertInWorkspace(val);
                    }
                }
                else
                {
                    ValidatePayloadPaths(property.Value);
                }
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray())
            {
                ValidatePayloadPaths(item);
            }
        }
    }

    private Task HandleHealth(HttpListenerContext context)
    {
        var running = _queue.GetRunning();
        var health = new
        {
            status = "healthy",
            version = System.Reflection.Assembly.GetExecutingAssembly().GetName().Version?.ToString(),
            uptime_seconds = (DateTime.UtcNow - _startTime).TotalSeconds,
            revit_version = App.RevitVersion ?? "unknown",
            active_document = App.ActiveDocumentName ?? "none",
            build = ProductInfo.BuildInfo,
            queue_depth = _queue.Count,
            retained_results = _queue.FinishedCount,
            running = running == null
                ? null
                : new { request_id = running.RequestId, tool = running.Tool, age_ms = running.ElapsedMs }
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

    private Task HandleCapabilities(HttpListenerContext context)
    {
        var tools = BridgeCommandFactory.GetCapabilities();
        Respond(context, 200, new { tools });
        return Task.CompletedTask;
    }

    private void WriteRegistryFile(string endpoint)
    {
        try
        {
            int pid = System.Diagnostics.Process.GetCurrentProcess().Id;
            var registryDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AECModelBridge", "registry");
            Directory.CreateDirectory(registryDir);

            RegistryFilePath = Path.Combine(registryDir, $"revit-{pid}.json");

            var data = new
            {
                provider_id = "revit",
                endpoint = endpoint.TrimEnd('/'),
                pid = pid,
                host_version = App.RevitVersion ?? "unknown",
                connector_version = System.Reflection.Assembly.GetExecutingAssembly().GetName().Version?.ToString() ?? "1.0",
                protocol_version = 2,
                capability_digest = "dynamic",
                session_token = SessionToken,
                started_at = _startTime.ToString("o")
            };

            var json = JsonSerializer.Serialize(data, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(RegistryFilePath, json);
            Log.Information("Wrote registry file to {RegistryFilePath}", RegistryFilePath);
        }
        catch (Exception ex)
        {
            Log.Error(ex, "Failed to write registry file");
        }
    }

    private void Respond(HttpListenerContext context, int statusCode, object data)
    {
        RespondRaw(context, statusCode, JsonSerializer.Serialize(data));
    }

    private void RespondRaw(HttpListenerContext context, int statusCode, string json)
    {
        context.Response.StatusCode = statusCode;
        context.Response.ContentType = "application/json";
        var buffer = Encoding.UTF8.GetBytes(json);
        context.Response.OutputStream.Write(buffer, 0, buffer.Length);
        context.Response.Close();
    }
}
