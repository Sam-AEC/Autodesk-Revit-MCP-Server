using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using RevitBridge.Bridge;
using Serilog;

namespace RevitBridge.UI
{
    public partial class BridgePanel : UserControl
    {
        private WebView2? _browser;
        private bool _initializing;
        private bool _browserReady;
        private bool _isLoaded;
        private bool _pageReady;
        private readonly Queue<string> _pendingMessages = new Queue<string>();
        private string? _chatSessionId;

        public BridgePanel()
        {
            InitializeComponent();
            FallbackLogo.Source = BrandMark.CreateImageSource();
            Loaded += async (_, _) =>
            {
                _isLoaded = true;
                await InitializeWebViewAsync();
            };
            // Revit re-parents / hides dockable panes, and WPF's WebView2 disposes itself
            // when it is unloaded. A disposed control can't be reused, so the next Loaded
            // builds a fresh one instead of trusting the old instance.
            Unloaded += (_, _) =>
            {
                _isLoaded = false;
                _browserReady = false;
                _pageReady = false;
            };
        }

        // CoreWebView2 throws once the control is disposed; treat that as "not available".
        private CoreWebView2? Core
        {
            get
            {
                try
                {
                    return _browser?.CoreWebView2;
                }
                catch (Exception)
                {
                    return null;
                }
            }
        }

        private WebView2 AttachNewBrowser()
        {
            if (_browser != null)
            {
                try
                {
                    BrowserHost.Children.Remove(_browser);
                    _browser.Dispose();
                }
                catch (Exception ex)
                {
                    Log.Debug(ex, "Previous WebView2 control was already disposed");
                }
            }

            _browser = new WebView2();
            BrowserHost.Children.Add(_browser);
            return _browser;
        }

        private void ShowFallback(string message, bool canRetry)
        {
            BrowserHost.Visibility = Visibility.Collapsed;
            Fallback.Visibility = Visibility.Visible;
            FallbackMessage.Text = message;
            RetryButton.Visibility = canRetry ? Visibility.Visible : Visibility.Collapsed;
        }

        private async void OnRetryClick(object sender, RoutedEventArgs e)
        {
            Fallback.Visibility = Visibility.Collapsed;
            BrowserHost.Visibility = Visibility.Visible;
            await InitializeWebViewAsync();
        }

        private async Task InitializeWebViewAsync(int attempt = 1)
        {
            if (_initializing || _browserReady)
            {
                return;
            }

            _initializing = true;
            var browser = AttachNewBrowser();

            try
            {
                // Default WebView2 user data folder is next to the host executable —
                // for a Revit add-in that's Revit.exe under Program Files, which the
                // current user can't write to (0x80070005 ACCESS_DENIED). Point it at
                // a writable per-user folder instead; this is Microsoft's documented
                // fix for any WebView2 host that doesn't run from a writable directory.
                var userDataFolder = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "AECModelBridge", "WebView2");
                Directory.CreateDirectory(userDataFolder);

                var environment = await CoreWebView2Environment.CreateAsync(
                    browserExecutableFolder: null,
                    userDataFolder: userDataFolder);

                await browser.EnsureCoreWebView2Async(environment);
                var core = browser.CoreWebView2;
                core.WebMessageReceived += OnWebMessageReceived;
                core.NavigationCompleted += (_, _) =>
                {
                    _pageReady = true;
                    PostHostStatus();
                    FlushPendingMessages();
                };
                _browserReady = true;
                LoadPanelApp(browser);
            }
            catch (WebView2RuntimeNotFoundException ex)
            {
                Log.Warning(ex, "WebView2 runtime is not installed");
                ShowFallback(
                    "The Microsoft Edge WebView2 Runtime is not installed. Install the Evergreen runtime and restart Revit.",
                    canRetry: true);
            }
            catch (Exception ex)
            {
                // The runtime is installed (a missing one throws WebView2RuntimeNotFoundException
                // above). Anything else is a lifecycle or environment failure, e.g. the control
                // being disposed while Revit re-docks the pane (0x8007139F). Log it in full.
                Log.Warning(ex, "WebView2 panel failed to start (attempt {Attempt})", attempt);

                if (!_isLoaded || !ReferenceEquals(browser, _browser))
                {
                    // Pane was unloaded mid-init; the next Loaded rebuilds the control.
                    return;
                }

                if (attempt < 3)
                {
                    _initializing = false;
                    await Task.Delay(500 * attempt);
                    await InitializeWebViewAsync(attempt + 1);
                    return;
                }

                ShowFallback(
                    "The panel could not start: " + ex.Message + " Details are in %APPDATA%\\AECModelBridge\\Logs.",
                    canRetry: true);
            }
            finally
            {
                _initializing = false;
            }
        }

        private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs args)
        {
            string message;
            try
            {
                message = args.TryGetWebMessageAsString();
            }
            catch
            {
                message = args.WebMessageAsJson;
            }

            Log.Information("Bridge panel message received: {Message}", message);

            try
            {
                await DispatchToHubAsync(message);
            }
            catch (JsonException)
            {
                // The connectivity-check fallback shell (BuildShellHtml) posts bare
                // strings like "panel.loaded", not JSON objects — nothing to dispatch.
            }
            catch (Exception ex)
            {
                Log.Warning(ex, "Failed to dispatch panel message: {Message}", message);
            }

            PostHostStatus();
        }

        /// <summary>
        /// Maps a panel message type to a real hub tool call and posts the result back.
        /// chat.message shells out to a CLI agent (see agent_bridge.py) rather than
        /// calling a tool directly; reports.refresh/open and selection.set have no MCP
        /// tool for one side of the round trip (reports.open opens a local file, and
        /// reports.refresh lists the workspace directly via the panel hub's /reports
        /// endpoint, not a tool call). settings remains local-only for now (no
        /// corresponding hub tool).
        /// </summary>
        private async Task DispatchToHubAsync(string message)
        {
            using var doc = JsonDocument.Parse(message);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("type", out var typeEl))
            {
                return;
            }

            var type = typeEl.GetString();
            switch (type)
            {
                case "qaqc.runHealthCheck":
                    await RunToolAndPostAsync("qaqc_checker_run_check", new { }, "findings.updated", type);
                    break;

                case "plans.refresh":
                    await RunToolAndPostAsync("list_pending_plans", new { }, "plans.updated", type);
                    break;

                case "plan.approve":
                case "plan.reject":
                {
                    var planId = root.TryGetProperty("planId", out var idEl) ? idEl.GetString() : null;
                    if (string.IsNullOrEmpty(planId))
                    {
                        break;
                    }

                    // The approval carries the hash of the plan the panel displayed; the hub
                    // refuses it if the plan changed after it was listed.
                    var planHash = root.TryGetProperty("planHash", out var hashEl) && hashEl.ValueKind == JsonValueKind.String
                        ? hashEl.GetString()
                        : null;
                    var decision = type == "plan.approve"
                        ? await HubClient.ExecuteToolAsync("approve_plan", new { plan_id = planId, expected_hash = planHash ?? "" })
                        : await HubClient.ExecuteToolAsync("reject_plan", new { plan_id = planId });
                    if (!decision.Ok)
                    {
                        PostToPanel(new { type = "tool.error", action = type, message = decision.Error });
                        break;
                    }

                    await RunToolAndPostAsync("list_pending_plans", new { }, "plans.updated", type);
                    break;
                }

                case "reports.exportExcel":
                    await RunToolAndPostAsync("report_generator_export_excel", new { }, "reports.updated", type);
                    break;

                case "reports.refresh":
                {
                    var reports = await HubClient.ListReportsAsync();
                    if (!reports.Ok)
                    {
                        PostToPanel(new { type = "tool.error", action = type, message = reports.Error });
                        break;
                    }

                    PostToPanel(new { type = "reports.list", reports = reports.Result });
                    break;
                }

                // UNVERIFIED (not compiled): forwards the hub's GET /diagnostics to the panel's Setup check.
                case "diagnostics.refresh":
                {
                    var diagnostics = await HubClient.GetDiagnosticsAsync();
                    if (!diagnostics.Ok)
                    {
                        PostToPanel(new { type = "tool.error", action = type, message = diagnostics.Error });
                        break;
                    }

                    PostToPanel(new { type = "diagnostics.updated", diagnostics = diagnostics.Result });
                    break;
                }

                case "settings.save":
                {
                    // Only the approval mode is a real setting: it goes to the hub, which keeps it
                    // (signed, with an expiry) for every gate that shares the workspace. The panel
                    // has already asked the person to confirm before sending "auto".
                    var requested = root.TryGetProperty("approvalMode", out var modeEl) && modeEl.ValueKind == JsonValueKind.String
                        ? modeEl.GetString()
                        : null;
                    var mode = requested == "auto" ? "auto" : "ask_first";
                    var minutes = root.TryGetProperty("minutes", out var minEl) && minEl.ValueKind == JsonValueKind.Number && minEl.TryGetInt32(out var m)
                        ? m
                        : 30;
                    var saved = await HubClient.SetApprovalModeAsync(mode, minutes);
                    if (!saved.Ok)
                    {
                        PostToPanel(new { type = "tool.error", action = type, message = saved.Error });
                        break;
                    }

                    PostToPanel(new { type = "diagnostics.updated", diagnostics = saved.Result });
                    break;
                }

                case "providers.refresh":
                {
                    var providers = await HubClient.GetProvidersAsync();
                    if (!providers.Ok)
                    {
                        PostToPanel(new { type = "tool.error", action = type, message = providers.Error });
                        break;
                    }

                    PostToPanel(new { type = "providers.updated", providers = new { claude = providers.Claude, codex = providers.Codex } });
                    break;
                }

                case "reports.open":
                {
                    var path = root.TryGetProperty("reportId", out var pathEl) ? pathEl.GetString() : null;
                    if (string.IsNullOrEmpty(path))
                    {
                        break;
                    }

                    if (!File.Exists(path))
                    {
                        PostToPanel(new { type = "tool.error", action = type, message = $"Report file not found: {path}" });
                        break;
                    }

                    try
                    {
                        Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
                    }
                    catch (Exception ex)
                    {
                        Log.Warning(ex, "Failed to open report file {Path}", path);
                        PostToPanel(new { type = "tool.error", action = type, message = $"Could not open report: {ex.Message}" });
                    }
                    break;
                }

                case "selection.set":
                {
                    var elementUids = new List<string>();
                    if (root.TryGetProperty("elementUids", out var uidsEl) && uidsEl.ValueKind == JsonValueKind.Array)
                    {
                        foreach (var uidEl in uidsEl.EnumerateArray())
                        {
                            var uid = uidEl.GetString();
                            if (!string.IsNullOrEmpty(uid))
                            {
                                elementUids.Add(uid);
                            }
                        }
                    }

                    if (elementUids.Count == 0)
                    {
                        break;
                    }

                    await RunToolAndPostAsync(
                        "revit_select_by_unique_ids",
                        new { element_uids = elementUids },
                        "selection.result",
                        type);
                    break;
                }

                case "chat.message":
                {
                    var text = root.TryGetProperty("message", out var msgEl) ? msgEl.GetString() : null;
                    if (string.IsNullOrWhiteSpace(text))
                    {
                        break;
                    }

                    var provider = root.TryGetProperty("provider", out var providerEl) ? providerEl.GetString() : "claude";
                    var chatResult = await HubClient.ChatAsync(provider ?? "claude", text, _chatSessionId);
                    if (!chatResult.Ok)
                    {
                        PostToPanel(new { type = "chat.error", message = chatResult.Error });
                        break;
                    }

                    _chatSessionId = chatResult.SessionId;
                    PostToPanel(new { type = "chat.response", message = chatResult.Response });
                    break;
                }

                case "chat.reset":
                    _chatSessionId = null;
                    break;
            }
        }

        private async Task RunToolAndPostAsync(string tool, object arguments, string successType, string action)
        {
            var result = await HubClient.ExecuteToolAsync(tool, arguments);
            if (result.Ok)
            {
                PostToPanel(new { type = successType, action, result = result.Result });
            }
            else
            {
                PostToPanel(new { type = "tool.error", action, message = result.Error });
            }
        }

        /// <summary>
        /// Called when Revit's UI theme changes mid-session (subscribed in
        /// BridgePanelProvider.Register) so the panel re-themes live via a fresh
        /// host.status. Only the panel updates live - ribbon icons are generated
        /// once at startup (see App.CreateModernRibbonInterface).
        /// </summary>
        internal void OnRevitThemeChanged()
        {
            Dispatcher.BeginInvoke(new Action(() =>
            {
                if (!_pageReady)
                {
                    return;
                }

                try
                {
                    PostHostStatus();
                }
                catch (Exception ex)
                {
                    Log.Warning(ex, "Failed to post host status after Revit theme change");
                }
            }));
        }

        private void PostHostStatus()
        {
            var dirtyCount = DocumentDirtyTracker.GetDirtyUniqueIds().Count;
            var payload = JsonSerializer.Serialize(new
            {
                type = "host.status",
                serverRunning = App.Server?.IsRunning == true,
                port = App.Server?.Port,
                revitVersion = App.RevitVersion,
                activeDocument = App.ActiveDocumentName,
                dirtyElementCount = dirtyCount,
                snapshotStale = dirtyCount > 0,
                isDarkTheme = IconGenerator.IsDarkTheme()
            });

            Core?.PostWebMessageAsJson(payload);
        }

        public void PostToPanel(object payload)
        {
            var json = JsonSerializer.Serialize(payload);
            var core = Core;
            if (!_pageReady || core == null)
            {
                _pendingMessages.Enqueue(json);
                return;
            }

            core.PostWebMessageAsJson(json);
        }

        private void FlushPendingMessages()
        {
            var core = Core;
            while (_pendingMessages.Count > 0 && core != null)
            {
                core.PostWebMessageAsJson(_pendingMessages.Dequeue());
            }
        }

        private void LoadPanelApp(WebView2 browser)
        {
            // AppContext.BaseDirectory resolves to the host process's directory (Revit.exe,
            // under Program Files) for an add-in assembly Revit loads into its own process -
            // not this DLL's directory - so it silently missed the real panel every time and
            // fell back to BuildShellHtml() below. Assembly.Location is what App.cs already
            // uses for the same reason when locating ribbon icons next to this DLL.
            var assemblyDir = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location) ?? AppContext.BaseDirectory;
            var panelPath = Path.Combine(assemblyDir, "panel", "index.html");
            if (File.Exists(panelPath))
            {
                browser.Source = new Uri(panelPath);
                return;
            }

            browser.NavigateToString(BuildShellHtml());
        }

        private static string BuildShellHtml()
        {
            return @"
<!doctype html>
<html lang=""en"">
<head>
  <meta charset=""utf-8"">
  <meta name=""viewport"" content=""width=device-width, initial-scale=1"">
  <style>
    :root { color-scheme: light dark; font-family: Segoe UI, system-ui, sans-serif; }
    body { margin: 0; min-height: 100vh; background: #f8fafc; color: #1f2937; }
    main { box-sizing: border-box; min-height: 100vh; padding: 18px; display: grid; gap: 14px; align-content: start; }
    header { border-bottom: 1px solid #d1d5db; padding-bottom: 12px; }
    h1 { margin: 0; font-size: 18px; line-height: 1.25; font-weight: 650; }
    p { margin: 6px 0 0; color: #4b5563; font-size: 12px; line-height: 1.5; }
    button { width: max-content; border: 0; border-radius: 6px; background: #2563eb; color: white; font: inherit; font-size: 13px; padding: 8px 12px; cursor: pointer; }
    button:hover { background: #1d4ed8; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; border: 1px solid #d1d5db; border-radius: 6px; padding: 10px; background: white; color: #111827; font-size: 12px; }
    @media (prefers-color-scheme: dark) {
      body { background: #202124; color: #f3f4f6; }
      header { border-color: #3f3f46; }
      p { color: #cbd5e1; }
      pre { background: #111827; border-color: #374151; color: #e5e7eb; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>AEC Model Bridge</h1>
      <p id=""state"">Panel host connected.</p>
    </header>
    <button id=""ping"" type=""button"">Refresh Host Status</button>
    <pre id=""status"">Waiting for host status...</pre>
  </main>
  <script>
    const statusEl = document.getElementById('status');
    const stateEl = document.getElementById('state');
    function post(message) {
      if (window.chrome && window.chrome.webview) {
        window.chrome.webview.postMessage(message);
      }
    }
    document.getElementById('ping').addEventListener('click', () => post('status.request'));
    window.chrome.webview.addEventListener('message', event => {
      stateEl.textContent = 'Host bridge active.';
      statusEl.textContent = JSON.stringify(event.data, null, 2);
    });
    post('panel.loaded');
  </script>
</body>
</html>";
        }
    }
}
