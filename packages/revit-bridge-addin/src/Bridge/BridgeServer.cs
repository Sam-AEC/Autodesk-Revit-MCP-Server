using System.IO;
using System.Net;
using System.Text.Json;

namespace RevitBridge.Bridge;

public class BridgeServer
{
    private readonly HttpListener _listener;

    public BridgeServer(string prefix = "http://localhost:3000/")
    {
        _listener = new HttpListener();
        _listener.Prefixes.Add(prefix);
    }

    public void Start()
    {
        _listener.Start();
    }

    public void Stop()
    {
        if (_listener.IsListening)
        {
            _listener.Stop();
        }
    }

    public void ProcessNext()
    {
        if (!_listener.IsListening)
        {
            return;
        }

        var context = _listener.GetContext();
        using var reader = new StreamReader(context.Request.InputStream);
        var body = reader.ReadToEnd();
        using var doc = JsonDocument.Parse(body);
        var root = doc.RootElement;
        var tool = root.GetProperty("tool").GetString() ?? string.Empty;
        var payload = root.GetProperty("payload");
        object result = BridgeCommandFactory.Execute(tool, payload);

        var buffer = JsonSerializer.SerializeToUtf8Bytes(new { status = "ok", tool, result });
        context.Response.ContentType = "application/json";
        context.Response.OutputStream.Write(buffer, 0, buffer.Length);
        context.Response.Close();
    }
}
