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
    private const int PostLaunchMaxAttempts = 40; // cold start of the bundled Python hub takes ~6 s

    private static readonly HttpClient HealthClient = new HttpClient { Timeout = TimeSpan.FromMilliseconds(HealthCheckTimeoutMs) };

    private Process? _launchedProcess;

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
            LogTokenFileState();
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
                // Output is redirected so a crash on startup (a traceback before the hub's own
                // log file exists) is not lost, but it is ALWAYS drained: PumpOutput keeps
                // reading after its size cap, because unread pipes deadlock the subprocess once
                // it writes more than ~4KB. The health poll below is still the readiness signal.
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };

            // Config() (config.py) requires MCP_REVIT_WORKSPACE_DIR and
            // MCP_REVIT_ALLOWED_DIRECTORIES and has no fallback for an installed
            // layout with no discoverable .env - without these the subprocess crashed
            // on import every time and never became reachable. Respect any value the
            // user already has set system-wide; otherwise default to Documents, same
            // as install.ps1's own default.json.
            SetEnvironmentDefault(startInfo, "MCP_REVIT_MODE", "bridge");
            var defaultWorkspace = WorkspaceDirectory.Default(); // same as config.py's default_workspace_dir()
            SetEnvironmentDefault(startInfo, "MCP_REVIT_WORKSPACE_DIR", defaultWorkspace);
            SetEnvironmentDefault(startInfo, "MCP_REVIT_ALLOWED_DIRECTORIES", defaultWorkspace);

            // The hub refuses to start if its workspace folder does not exist, and the default
            // (~/Documents/AEC Model Bridge) does not exist on a fresh install or when Documents
            // is redirected (OneDrive). Create it here rather than let the hub die unseen.
            var workspace = startInfo.EnvironmentVariables["MCP_REVIT_WORKSPACE_DIR"];
            if (!string.IsNullOrWhiteSpace(workspace))
            {
                try
                {
                    System.IO.Directory.CreateDirectory(workspace);
                    // The hub, and every CLI and MCP server it starts, run from the workspace: a plain
                    // writable folder. Not Revit's install folder (its own DLLs), and NOT the bundled
                    // Python folder: from there a second Python on PATH loads that folder's
                    // python311.dll and the MCP server fails to start, leaving the panel chat with no tools.
                    startInfo.WorkingDirectory = workspace;
                }
                catch (Exception ex)
                {
                    Log.Warning(ex, "Could not create the AEC Model Bridge workspace folder {Workspace}", workspace);
                }
            }

            _launchedProcess = Process.Start(startInfo);
            PumpOutput(_launchedProcess);
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
                LogTokenFileState();
                return;
            }
        }

        Log.Warning(
            "Launched the panel hub but it never became reachable on 127.0.0.1:{Port} after {Attempts} attempts. " +
            "Check %LOCALAPPDATA%\\AECModelBridge or the process's own logs for why it failed to start.",
            Port, PostLaunchMaxAttempts);
    }

    /// <summary>
    /// The hub (not this add-in) creates the per-user token file the panel needs on every call
    /// (see UI/HubClient.cs, HubTokenStore). Logs whether it is readable; never logs the token.
    /// UNVERIFIED: not compiled or run against Revit.
    /// </summary>
    private static void LogTokenFileState()
    {
        try
        {
            if (RevitBridge.UI.HubTokenStore.Get(true) == null)
            {
                Log.Warning(
                    "The panel hub is reachable but its access token file was not found or is unreadable at {TokenFile}. " +
                    "Panel calls will be refused until a current hub (this version of the add-in expects one that " +
                    "creates the file) is running.",
                    RevitBridge.UI.HubTokenStore.FilePath);
            }
        }
        catch (Exception ex)
        {
            Log.Warning(ex, "Could not check the panel hub token file");
        }
    }

    private const long LaunchLogCapBytes = 64 * 1024;

    /// <summary>
    /// Copies the hub's stdout/stderr to %APPDATA%\AECModelBridge\Logs\panel-hub-launch.log (first 64 KB,
    /// truncated per launch) and then keeps draining and discarding, so the pipes never fill.
    /// </summary>
    private static void PumpOutput(Process? process)
    {
        if (process == null)
        {
            return;
        }

        System.IO.StreamWriter? writer = null;
        long written = 0;
        var gate = new object();
        try
        {
            var logPath = System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                "AECModelBridge", "Logs", "panel-hub-launch.log");
            System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(logPath)!);
            writer = new System.IO.StreamWriter(
                new System.IO.FileStream(logPath, System.IO.FileMode.Create, System.IO.FileAccess.Write, System.IO.FileShare.ReadWrite))
            {
                AutoFlush = true,
            };
        }
        catch (Exception ex)
        {
            Log.Debug(ex, "Could not open the panel hub launch log; hub output will be discarded");
        }

        DataReceivedEventHandler handler = (_, e) =>
        {
            if (e.Data == null)
            {
                return;
            }

            lock (gate)
            {
                if (writer == null || written >= LaunchLogCapBytes)
                {
                    return;
                }

                try
                {
                    writer.WriteLine(e.Data);
                    written += e.Data.Length + 2;
                }
                catch (System.IO.IOException)
                {
                    writer = null;
                }
            }
        };

        process.OutputDataReceived += handler;
        process.ErrorDataReceived += handler;
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
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
