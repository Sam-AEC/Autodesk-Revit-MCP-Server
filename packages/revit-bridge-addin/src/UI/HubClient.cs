using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace RevitBridge.UI
{
    /// <summary>
    /// Calls the Python MCP hub's local panel HTTP shim (packages/mcp-server-revit's
    /// panel_server.py). MCP itself is stdio-only — a WebView2 page cannot launch or
    /// speak to a stdio subprocess — so the panel reaches the hub over a small
    /// loopback HTTP shim instead.
    /// This is the one piece of the add-in that bridges that gap.
    /// </summary>
    internal static class HubClient
    {
        private static readonly HttpClient Client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };

        // Chat turns shell out to a CLI (agent_bridge.py) that can call the model and
        // run several tool calls before replying — matches that module's own
        // 180s subprocess ceiling with headroom, well past the 30s tool-call timeout above.
        private static readonly HttpClient ChatClient = new HttpClient { Timeout = TimeSpan.FromSeconds(200) };

        static HubClient()
        {
            // The hub requires this per-launch bearer token on every endpoint but /health.
            var auth = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", RevitBridge.Bridge.PanelHubLauncher.HubToken);
            Client.DefaultRequestHeaders.Authorization = auth;
            ChatClient.DefaultRequestHeaders.Authorization = auth;
        }

        private static int Port
        {
            get
            {
                var raw = Environment.GetEnvironmentVariable("MCP_PANEL_HTTP_PORT");
                return int.TryParse(raw, out var port) ? port : 8787;
            }
        }

        public static async Task<HubResult> ExecuteToolAsync(string tool, object arguments)
        {
            var requestBody = JsonSerializer.Serialize(new { tool, arguments });

            try
            {
                using (var content = new StringContent(requestBody, Encoding.UTF8, "application/json"))
                using (var response = await Client.PostAsync($"http://127.0.0.1:{Port}/execute", content).ConfigureAwait(false))
                {
                    var text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                    return ParseResponse(text, (int)response.StatusCode);
                }
            }
            catch (Exception ex)
            {
                return HubResult.Failure($"Could not reach the AEC Model Bridge hub on 127.0.0.1:{Port}: {ex.Message}");
            }
        }

        public static async Task<HubResult> ListReportsAsync()
        {
            try
            {
                using (var response = await Client.GetAsync($"http://127.0.0.1:{Port}/reports").ConfigureAwait(false))
                {
                    var text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                    return ParseReportsResponse(text, (int)response.StatusCode);
                }
            }
            catch (Exception ex)
            {
                return HubResult.Failure($"Could not reach the AEC Model Bridge hub on 127.0.0.1:{Port}: {ex.Message}");
            }
        }

        public static async Task<ProvidersResult> GetProvidersAsync()
        {
            try
            {
                using (var response = await Client.GetAsync($"http://127.0.0.1:{Port}/agent/providers").ConfigureAwait(false))
                {
                    var text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                    return ParseProvidersResponse(text, (int)response.StatusCode);
                }
            }
            catch (Exception ex)
            {
                return ProvidersResult.Failure($"Could not reach the AEC Model Bridge hub on 127.0.0.1:{Port}: {ex.Message}");
            }
        }

        public static async Task<ChatResult> ChatAsync(string provider, string message, string sessionId)
        {
            var requestBody = JsonSerializer.Serialize(new { provider, message, session_id = sessionId });

            try
            {
                using (var content = new StringContent(requestBody, Encoding.UTF8, "application/json"))
                using (var response = await ChatClient.PostAsync($"http://127.0.0.1:{Port}/agent/chat", content).ConfigureAwait(false))
                {
                    var text = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
                    return ParseChatResponse(text, (int)response.StatusCode);
                }
            }
            catch (Exception ex)
            {
                return ChatResult.Failure($"Could not reach the AEC Model Bridge hub on 127.0.0.1:{Port}: {ex.Message}");
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
