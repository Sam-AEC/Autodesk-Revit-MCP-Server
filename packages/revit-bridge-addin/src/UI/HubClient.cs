using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using RevitBridge.Bridge;

namespace RevitBridge.UI
{
    /// <summary>
    /// The panel hub's access token, read from the per-user file the hub creates
    /// (%LOCALAPPDATA%\AECModelBridge\panel-hub.token, same folder as the bridge
    /// registry; MCP_PANEL_TOKEN_FILE overrides the path). Every Revit instance of
    /// this Windows user reads the same file, so one token works for all of them.
    /// The add-in never creates the file (the hub does) and never logs the token or
    /// passes it to the panel's JavaScript: the page talks to C# over the WebView2
    /// message bridge and only C# calls the hub.
    /// UNVERIFIED: not compiled or run against Revit/WebView2 in this change.
    /// </summary>
    internal static class HubTokenStore
    {
        private static readonly object Gate = new object();
        private static readonly Regex TokenPattern = new Regex("^[A-Za-z0-9_-]{43}$");
        private static string? _cached;

        internal static string FilePath
        {
            get
            {
                var overridePath = Environment.GetEnvironmentVariable("MCP_PANEL_TOKEN_FILE");
                if (!string.IsNullOrWhiteSpace(overridePath))
                {
                    return overridePath!;
                }

                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "AECModelBridge",
                    "panel-hub.token");
            }
        }

        /// <summary>Returns the token, or null if the file is missing or malformed.</summary>
        internal static string? Get(bool reload)
        {
            lock (Gate)
            {
                if (!reload && _cached != null)
                {
                    return _cached;
                }

                try
                {
                    var path = FilePath;
                    if (!File.Exists(path))
                    {
                        _cached = null;
                        return null;
                    }

                    var value = File.ReadAllText(path).Trim();
                    _cached = TokenPattern.IsMatch(value) ? value : null;
                    return _cached;
                }
                catch (IOException)
                {
                    return null;
                }
                catch (UnauthorizedAccessException)
                {
                    return null;
                }
            }
        }
    }

    /// <summary>A hub call failed for a token reason. The message is safe to show and never contains the token.</summary>
    internal sealed class HubTokenException : Exception
    {
        public HubTokenException(string message) : base(message)
        {
        }
    }

    /// <summary>
    /// Calls the Python MCP hub's local panel HTTP shim (packages/mcp-server-revit's
    /// panel_server.py). MCP itself is stdio-only — a WebView2 page cannot launch or
    /// speak to a stdio subprocess — so the panel reaches the hub over a small
    /// loopback HTTP shim instead.
    /// This is the one piece of the add-in that bridges that gap.
    ///
    /// Every call except GET /health carries the per-user token in the X-AMB-Token
    /// header (see HubTokenStore). Calls that act on Revit also carry "instance"
    /// (this Revit's process id and active document title) so the hub routes them to
    /// this Revit's bridge when several Revits share the hub.
    /// </summary>
    internal static class HubClient
    {
        private const string TokenHeader = "X-AMB-Token";

        private const string MissingTokenMessage =
            "The AEC Model Bridge hub token file was not found. The hub creates it when it starts: " +
            "start the hub (restart Revit, or run 'aec-model-bridge-panel-server') and try again.";

        private const string TokenFileGoneMessage =
            "The AEC Model Bridge hub token file is gone (it was deleted after the hub started). " +
            "Restart the panel hub (end the 'revit_mcp_server.panel_server' python process) and restart Revit " +
            "so a new token file is created.";

        private const string RejectedTokenMessage =
            "The hub rejected the panel's access token (token changed). The token file was replaced after the " +
            "hub started, or this hub was started by another user. Restart the panel hub " +
            "(end the 'revit_mcp_server.panel_server' python process) and restart Revit.";

        private static readonly HttpClient Client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };

        // Chat turns shell out to a CLI (agent_bridge.py) that can call the model and
        // run several tool calls before replying — matches that module's own
        // 180s subprocess ceiling with headroom, well past the 30s tool-call timeout above.
        private static readonly HttpClient ChatClient = new HttpClient { Timeout = TimeSpan.FromSeconds(200) };

        private static int Port
        {
            get
            {
                var raw = Environment.GetEnvironmentVariable("MCP_PANEL_HTTP_PORT");
                return int.TryParse(raw, out var port) ? port : 8787;
            }
        }

        private sealed class RawResponse
        {
            public int Status;
            public string Body = string.Empty;
        }

        // Process.GetCurrentProcess() returns a new disposable object each call; the id never changes.
        private static readonly int ProcessId = GetProcessId();

        private static int GetProcessId()
        {
            using (var current = Process.GetCurrentProcess())
            {
                return current.Id;
            }
        }

        private static object InstanceInfo()
        {
            return new
            {
                pid = ProcessId,
                document = App.ActiveDocumentName ?? string.Empty,
            };
        }

        private static string Describe(Exception ex)
        {
            return ex is HubTokenException
                ? ex.Message
                : $"Could not reach the AEC Model Bridge hub on 127.0.0.1:{Port}: {ex.Message}";
        }

        private static async Task<RawResponse> SendOnceAsync(HttpClient client, HttpMethod method, string path, string? json, string token)
        {
            using (var request = new HttpRequestMessage(method, $"http://127.0.0.1:{Port}{path}"))
            {
                request.Headers.Add(TokenHeader, token);
                if (json != null)
                {
                    request.Content = new StringContent(json, Encoding.UTF8, "application/json");
                }

                using (var response = await client.SendAsync(request).ConfigureAwait(false))
                {
                    var text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                    return new RawResponse { Status = (int)response.StatusCode, Body = text };
                }
            }
        }

        /// <summary>
        /// Sends one authenticated hub request. On 401 it re-reads the token file once (the hub may
        /// have been restarted with a new token) and retries; a second 401 is reported as
        /// "token changed, restart the panel hub".
        /// </summary>
        private static async Task<RawResponse> SendAsync(HttpClient client, HttpMethod method, string path, string? json)
        {
            var token = HubTokenStore.Get(false);
            if (token == null)
            {
                token = HubTokenStore.Get(true);
            }

            if (token == null)
            {
                throw new HubTokenException(MissingTokenMessage);
            }

            var result = await SendOnceAsync(client, method, path, json, token).ConfigureAwait(false);
            // 429 is treated like 401: after a burst of failures the hub answers 429 even to a stale
            // token, and the panel must still get to re-read the file once.
            if (result.Status == 401 || result.Status == 429)
            {
                var fresh = HubTokenStore.Get(true);
                if (fresh == null)
                {
                    throw new HubTokenException(TokenFileGoneMessage);
                }

                if (fresh != token)
                {
                    result = await SendOnceAsync(client, method, path, json, fresh).ConfigureAwait(false);
                }

                if (result.Status == 401 || result.Status == 429)
                {
                    throw new HubTokenException(RejectedTokenMessage);
                }
            }

            return result;
        }

        public static async Task<HubResult> ExecuteToolAsync(string tool, object arguments)
        {
            var requestBody = JsonSerializer.Serialize(new { tool, arguments, instance = InstanceInfo() });

            try
            {
                var response = await SendAsync(Client, HttpMethod.Post, "/execute", requestBody).ConfigureAwait(false);
                return ParseResponse(response.Body, response.Status);
            }
            catch (Exception ex)
            {
                return HubResult.Failure(Describe(ex));
            }
        }

        public static async Task<HubResult> ListReportsAsync()
        {
            try
            {
                var response = await SendAsync(Client, HttpMethod.Get, "/reports", null).ConfigureAwait(false);
                return ParseReportsResponse(response.Body, response.Status);
            }
            catch (Exception ex)
            {
                return HubResult.Failure(Describe(ex));
            }
        }

        // UNVERIFIED (not compiled): forwards GET /diagnostics for the panel's Setup check.
        public static async Task<HubResult> GetDiagnosticsAsync()
        {
            try
            {
                var response = await SendAsync(Client, HttpMethod.Get, "/diagnostics", null).ConfigureAwait(false);
                var text = response.Body;
                try
                {
                    using (var doc = JsonDocument.Parse(text))
                    {
                        if (doc.RootElement.ValueKind == JsonValueKind.Object && doc.RootElement.TryGetProperty("checks", out _))
                        {
                            // The whole payload is the result: {ok, checks:[...]}; ok=false is still a valid answer.
                            return HubResult.Success(doc.RootElement.Clone());
                        }
                    }
                }
                catch (JsonException)
                {
                }

                return HubResult.Failure($"Hub returned an unusable diagnostics response (HTTP {response.Status})");
            }
            catch (Exception ex)
            {
                return HubResult.Failure(Describe(ex));
            }
        }

        /// <summary>
        /// Switches the hub (and every gate sharing its workspace) to a limited "auto" window, or back
        /// to ask-first. The hub answers with its fresh diagnostics payload on success. The caller must
        /// have asked the person to confirm before passing "auto".
        /// </summary>
        public static async Task<HubResult> SetApprovalModeAsync(string mode, int minutes)
        {
            var isAuto = mode == "auto";
            var requestBody = JsonSerializer.Serialize(new { mode, minutes, confirm = isAuto });

            try
            {
                var response = await SendAsync(Client, HttpMethod.Post, "/approval-mode", requestBody).ConfigureAwait(false);
                try
                {
                    using (var doc = JsonDocument.Parse(response.Body))
                    {
                        var root = doc.RootElement;
                        if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("checks", out _))
                        {
                            return HubResult.Success(root.Clone());
                        }

                        var error = root.ValueKind == JsonValueKind.Object && root.TryGetProperty("error", out var errEl)
                            ? errEl.GetString()
                            : null;
                        return HubResult.Failure(error ?? $"Hub returned HTTP {response.Status}");
                    }
                }
                catch (JsonException)
                {
                    return HubResult.Failure($"Hub returned an unparseable response (HTTP {response.Status})");
                }
            }
            catch (Exception ex)
            {
                return HubResult.Failure(Describe(ex));
            }
        }

        public static async Task<ProvidersResult> GetProvidersAsync()
        {
            try
            {
                var response = await SendAsync(Client, HttpMethod.Get, "/agent/providers", null).ConfigureAwait(false);
                return ParseProvidersResponse(response.Body, response.Status);
            }
            catch (Exception ex)
            {
                return ProvidersResult.Failure(Describe(ex));
            }
        }

        public static async Task<ChatResult> ChatAsync(string provider, string message, string sessionId)
        {
            var requestBody = JsonSerializer.Serialize(new { provider, message, session_id = sessionId, instance = InstanceInfo() });

            try
            {
                var response = await SendAsync(ChatClient, HttpMethod.Post, "/agent/chat", requestBody).ConfigureAwait(false);
                return ParseChatResponse(response.Body, response.Status);
            }
            catch (Exception ex)
            {
                return ChatResult.Failure(Describe(ex));
            }
        }

        private static HubResult ParseReportsResponse(string text, int statusCode)
        {
            try
            {
                using (var doc = JsonDocument.Parse(text))
                {
                    var root = doc.RootElement;
                    var ok = root.TryGetProperty("ok", out var okEl) && okEl.ValueKind == JsonValueKind.True;
                    if (ok && root.TryGetProperty("reports", out var reportsEl))
                    {
                        return HubResult.Success(reportsEl.Clone());
                    }

                    var error = root.TryGetProperty("error", out var errEl) ? errEl.GetString() : null;
                    return HubResult.Failure(error ?? $"Hub returned HTTP {statusCode}");
                }
            }
            catch (JsonException)
            {
                return HubResult.Failure($"Hub returned an unparseable response (HTTP {statusCode})");
            }
        }

        private static HubResult ParseResponse(string text, int statusCode)
        {
            try
            {
                using (var doc = JsonDocument.Parse(text))
                {
                    var root = doc.RootElement;
                    var ok = root.TryGetProperty("ok", out var okEl) && okEl.ValueKind == JsonValueKind.True;
                    if (ok && root.TryGetProperty("result", out var resultEl))
                    {
                        return HubResult.Success(resultEl.Clone());
                    }

                    var error = root.TryGetProperty("error", out var errEl) ? errEl.GetString() : null;
                    return HubResult.Failure(error ?? $"Hub returned HTTP {statusCode}");
                }
            }
            catch (JsonException)
            {
                return HubResult.Failure($"Hub returned an unparseable response (HTTP {statusCode})");
            }
        }

        private static ProvidersResult ParseProvidersResponse(string text, int statusCode)
        {
            try
            {
                using (var doc = JsonDocument.Parse(text))
                {
                    var root = doc.RootElement;
                    var ok = root.TryGetProperty("ok", out var okEl) && okEl.ValueKind == JsonValueKind.True;
                    if (ok && root.TryGetProperty("providers", out var providersEl))
                    {
                        var claude = providersEl.TryGetProperty("claude", out var claudeEl) && claudeEl.ValueKind == JsonValueKind.True;
                        var codex = providersEl.TryGetProperty("codex", out var codexEl) && codexEl.ValueKind == JsonValueKind.True;
                        return ProvidersResult.Success(claude, codex);
                    }

                    var error = root.TryGetProperty("error", out var errEl) ? errEl.GetString() : null;
                    return ProvidersResult.Failure(error ?? $"Hub returned HTTP {statusCode}");
                }
            }
            catch (JsonException)
            {
                return ProvidersResult.Failure($"Hub returned an unparseable response (HTTP {statusCode})");
            }
        }

        private static ChatResult ParseChatResponse(string text, int statusCode)
        {
            try
            {
                using (var doc = JsonDocument.Parse(text))
                {
                    var root = doc.RootElement;
                    var ok = root.TryGetProperty("ok", out var okEl) && okEl.ValueKind == JsonValueKind.True;
                    if (ok && root.TryGetProperty("response", out var responseEl))
                    {
                        var sessionId = root.TryGetProperty("session_id", out var sidEl) ? sidEl.GetString() : null;
                        return ChatResult.Success(responseEl.GetString() ?? string.Empty, sessionId);
                    }

                    var error = root.TryGetProperty("error", out var errEl) ? errEl.GetString() : null;
                    return ChatResult.Failure(error ?? $"Hub returned HTTP {statusCode}");
                }
            }
            catch (JsonException)
            {
                return ChatResult.Failure($"Hub returned an unparseable response (HTTP {statusCode})");
            }
        }
    }

    internal readonly struct HubResult
    {
        public bool Ok { get; }
        public JsonElement Result { get; }
        public string Error { get; }

        private HubResult(bool ok, JsonElement result, string error)
        {
            Ok = ok;
            Result = result;
            Error = error;
        }

        public static HubResult Success(JsonElement result) => new HubResult(true, result, null);

        public static HubResult Failure(string error) => new HubResult(false, default, error);
    }

    internal readonly struct ChatResult
    {
        public bool Ok { get; }
        public string Response { get; }
        public string SessionId { get; }
        public string Error { get; }

        private ChatResult(bool ok, string response, string sessionId, string error)
        {
            Ok = ok;
            Response = response;
            SessionId = sessionId;
            Error = error;
        }

        public static ChatResult Success(string response, string sessionId) => new ChatResult(true, response, sessionId, null);

        public static ChatResult Failure(string error) => new ChatResult(false, null, null, error);
    }

    internal readonly struct ProvidersResult
    {
        public bool Ok { get; }
        public bool Claude { get; }
        public bool Codex { get; }
        public string Error { get; }

        private ProvidersResult(bool ok, bool claude, bool codex, string error)
        {
            Ok = ok;
            Claude = claude;
            Codex = codex;
            Error = error;
        }

        public static ProvidersResult Success(bool claude, bool codex) => new ProvidersResult(true, claude, codex, null);

        public static ProvidersResult Failure(string error) => new ProvidersResult(false, false, false, error);
    }
}
