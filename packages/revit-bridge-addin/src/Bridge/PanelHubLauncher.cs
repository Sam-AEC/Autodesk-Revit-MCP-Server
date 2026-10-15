using System;
using System.Diagnostics;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Serilog;

namespace RevitBridge.Bridge;

/// <summary>
/// Ensures the Python MCP hub's panel HTTP shim (packages/mcp-server-revit's
/// panel_server.py) is reachable on 127.0.0.1 before the dockable panel needs it.
///
/// HubClient.cs assumes something is already listening on the panel port — this
/// class is what makes that true on a machine where nobody has manually started
/// `aec-model-bridge-panel-server`. It never manages a hub it didn't start itself:
/// if something is already answering /health (a developer's own instance, or a
/// future bundled-runtime launcher), this leaves it alone entirely, both at
/// startup and at shutdown.
///
/// Python provisioning is not yet bundled with the installer (still open,
/// D-010); this is a best-effort launch matching the interpreter conventions
/// docs/install.md already documents
/// (a project .venv, or a bare `python`/`py` on PATH), not a substitute for that
/// installer work.
/// </summary>
public sealed class PanelHubLauncher
{
    private const int HealthCheckTimeoutMs = 800;
    private const int PostLaunchPollIntervalMs = 500;
    private const int PostLaunchMaxAttempts = 10;

    private static readonly HttpClient HealthClient = new HttpClient { Timeout = TimeSpan.FromMilliseconds(HealthCheckTimeoutMs) };

    private Process? _launchedProcess;

    /// <summary>
    /// Per-launch bearer token for the hub's panel HTTP shim (env
    /// MCP_PANEL_HTTP_TOKEN). Uses an operator-supplied value if one is already
    /// set in this process's environment (so a hand-started hub with the same
    /// variable keeps working), otherwise a fresh random one. HubClient sends it
    /// as "Authorization: Bearer" on every request. Kept in memory only.
    /// </summary>
    internal static string HubToken { get; } = CreateToken();

    private static string CreateToken()
    {
        var existing = Environment.GetEnvironmentVariable("MCP_PANEL_HTTP_TOKEN");
        if (!string.IsNullOrWhiteSpace(existing))
        {
            return existing!;
        }

        var bytes = new byte[32];
        using (var rng = System.Security.Cryptography.RandomNumberGenerator.Create())
        {
            rng.GetBytes(bytes);
        }

        return BitConverter.ToString(bytes).Replace("-", string.Empty).ToLowerInvariant();
    }

    private static int Port
    {
        get
        {
            var raw = Environment.GetEnvironmentVariable("MCP_PANEL_HTTP_PORT");
            return int.TryParse(raw, out var port) ? port : 8787;
        }
    }

    /// <summary>
    /// Checks whether the panel hub is reachable and launches it in the background
    /// if not. Returns immediately; the check/launch/poll sequence runs on a
    /// background task so it never blocks Revit's OnStartup.
    /// </summary>
    public void EnsureRunning()
    {
        _ = Task.Run(EnsureRunningAsync);
    }

    private async Task EnsureRunningAsync()
    {
        if (await IsHealthyAsync().ConfigureAwait(false))
        {
            Log.Information("Panel hub already reachable on 127.0.0.1:{Port} — not launching a new one", Port);
            return;
        }

        var interpreter = ResolvePythonInterpreter();
        if (interpreter == null)
        {
            Log.Warning(
                "Panel hub is not reachable on 127.0.0.1:{Port} and no Python interpreter could be found to " +
                "launch it. Set AEC_MODEL_BRIDGE_PYTHON to a python.exe, or start it manually with " +
                "'aec-model-bridge-panel-server' / 'python -m revit_mcp_server.panel_server' — see docs/install.md. " +
                "The panel will show a connection error until the hub is reachable.",
                Port);
            return;
        }

        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = interpreter,
                Arguments = "-m revit_mcp_server.panel_server",
                UseShellExecute = false,
                CreateNoWindow = true,
                // Do NOT redirect stdout/stderr: redirected but unread pipes deadlock
                // once the subprocess writes more than ~4KB (the pipe buffer). The hub
                // logs at startup so this threshold is reachable. Output is discarded
                // anyway — the health-poll loop is the correct readiness signal (H4 fix).
            };

            // Config() (config.py) requires MCP_REVIT_WORKSPACE_DIR and
            // MCP_REVIT_ALLOWED_DIRECTORIES and has no fallback for an installed
            // layout with no discoverable .env - without these the subprocess crashed
            // on import every time and never became reachable. Respect any value the
            // user already has set system-wide; otherwise default to Documents, same
            // as install.ps1's own default.json.
            SetEnvironmentDefault(startInfo, "MCP_REVIT_MODE", "bridge");
            var defaultWorkspace = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            SetEnvironmentDefault(startInfo, "MCP_REVIT_WORKSPACE_DIR", defaultWorkspace);
            SetEnvironmentDefault(startInfo, "MCP_REVIT_ALLOWED_DIRECTORIES", defaultWorkspace);

            startInfo.EnvironmentVariables["MCP_PANEL_HTTP_TOKEN"] = HubToken;

            _launchedProcess = Process.Start(startInfo);
            Log.Information("Launched panel hub via '{Interpreter} -m revit_mcp_server.panel_server' (pid {Pid})",
                interpreter, _launchedProcess?.Id);
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Failed to launch the panel hub with interpreter '{Interpreter}'", interpreter);
            return;
        }

        for (var attempt = 0; attempt < PostLaunchMaxAttempts; attempt++)
        {
            await Task.Delay(PostLaunchPollIntervalMs).ConfigureAwait(false);
            if (await IsHealthyAsync().ConfigureAwait(false))
            {
                Log.Information("Panel hub is up on 127.0.0.1:{Port}", Port);
                return;
            }
        }

        Log.Warning(
            "Launched the panel hub but it never became reachable on 127.0.0.1:{Port} after {Attempts} attempts. " +
            "Check %LOCALAPPDATA%\\AECModelBridge or the process's own logs for why it failed to start.",
            Port, PostLaunchMaxAttempts);
    }

    private static void SetEnvironmentDefault(ProcessStartInfo startInfo, string name, string defaultValue)
    {
        if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable(name)))
        {
            startInfo.EnvironmentVariables[name] = defaultValue;
        }
    }

    private static async Task<bool> IsHealthyAsync()
    {
        try
        {
            using var response = await HealthClient.GetAsync($"http://127.0.0.1:{Port}/health").ConfigureAwait(false);
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Finds a Python interpreter capable of running revit_mcp_server, preferring
    /// an explicit override, then falling back to whatever's on PATH. Does not
    /// search for a project .venv, since the add-in has no reliable way to know
    /// where the hub's source checkout lives once installed — that's exactly the
    /// gap the bundled-runtime installer (D-010) is meant to close.
    /// </summary>
    private static string? ResolvePythonInterpreter()
    {
        var overridePath = Environment.GetEnvironmentVariable("AEC_MODEL_BRIDGE_PYTHON");
        if (!string.IsNullOrWhiteSpace(overridePath) && System.IO.File.Exists(overridePath))
        {
            return overridePath;
        }

        const string bundledPath = @"C:\ProgramData\AECModelBridge\python\python.exe";
        if (System.IO.File.Exists(bundledPath))
        {
            return bundledPath;
        }

        foreach (var candidate in new[] { "python", "py" })
        {
            if (CanRun(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private static bool CanRun(string command)
    {
        try
        {
            using var process = Process.Start(new ProcessStartInfo
            {
                FileName = command,
                Arguments = "--version",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            });
            process?.WaitForExit(2000);
            return process is { HasExited: true, ExitCode: 0 };
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Kills the hub process only if this launcher started it — a hub that was
    /// already running before Revit started (a developer's own instance) is left
    /// untouched, matching the same restraint EnsureRunning applies at startup.
    /// </summary>
    public void StopIfLaunched()
    {
        if (_launchedProcess == null)
        {
            return;
        }

        try
        {
            if (!_launchedProcess.HasExited)
            {
                _launchedProcess.Kill();
                Log.Information("Stopped the panel hub process this launcher started (pid {Pid})", _launchedProcess.Id);
            }
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Failed to stop the panel hub process cleanly");
        }
        finally
        {
            _launchedProcess.Dispose();
            _launchedProcess = null;
        }
    }
}
