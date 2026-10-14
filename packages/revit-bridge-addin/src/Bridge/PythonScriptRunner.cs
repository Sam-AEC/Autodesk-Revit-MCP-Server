using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Events;
using Autodesk.Revit.UI;

namespace RevitBridge.Bridge;

/// <summary>
/// Runs the script behind revit.execute_python on an engine from <see cref="PythonEngineFactory"/>
/// (which has no Revit dependency, so scripts/test-ironpython-runtime.ps1 can compile it alone).
/// Read mode is a safety rail against mistakes, not a security boundary: a text check refuses scripts
/// that name Transaction, SubTransaction or TransactionGroup, and a run-time backstop reports (and for
/// saves, cancels) anything that still touches the model.
/// </summary>
internal static class PythonScriptRunner
{
    internal const string ModeRead = "read";
    internal const string ModeWrite = "write";
    private const int MaxProgressLines = 200;
    private const int MaxProgressLineLength = 500;

    // Keep in step with revit_mcp_server/security/read_mode.py (a test compares the rule names).
    private static readonly (string Name, Regex Pattern)[] ReadModeRules =
    {
        ("Transaction", new Regex(@"\bTransaction\b", RegexOptions.CultureInvariant)),
        ("SubTransaction", new Regex(@"\bSubTransaction\b", RegexOptions.CultureInvariant)),
        ("TransactionGroup", new Regex(@"\bTransactionGroup\b", RegexOptions.CultureInvariant)),
        ("Save", new Regex(@"\.\s*Save(?:As)?\s*\(", RegexOptions.CultureInvariant)),
        ("SynchronizeWithCentral", new Regex(@"\bSynchronizeWithCentral\b", RegexOptions.CultureInvariant)),
        ("PostCommand", new Regex(@"\bPostCommand\b", RegexOptions.CultureInvariant)),
        ("eval", new Regex(@"\beval\b", RegexOptions.CultureInvariant)),
        ("exec", new Regex(@"\bexec(?:file)?\b", RegexOptions.CultureInvariant)),
        ("__import__", new Regex(@"\b__import__\b", RegexOptions.CultureInvariant)),
    };

    /// <summary>Progress lines of the script that is running now, for a future live status endpoint.</summary>
    internal static ProgressBuffer? ActiveProgress { get; private set; }

    internal static string NormalizeMode(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return ModeWrite;
        var mode = value!.Trim().ToLowerInvariant();
        if (mode == ModeRead || mode == ModeWrite) return mode;
        throw new ArgumentException($"mode must be 'read' or 'write', got '{value}'");
    }

    internal static List<string> FindReadModeViolations(string script)
    {
        return ReadModeRules.Where(rule => rule.Pattern.IsMatch(script)).Select(rule => rule.Name).ToList();
    }

    internal static object Run(UIApplication app, Document doc, string script, string? requestedMode)
    {
        var mode = NormalizeMode(requestedMode);
        var progress = new ProgressBuffer(MaxProgressLines, MaxProgressLineLength);

        if (mode == ModeRead)
        {
            var violations = FindReadModeViolations(script);
            if (violations.Count > 0)
            {
                return Result(false, "", "Read mode refuses scripts that could change the model (found: "
                    + string.Join(", ", violations)
                    + "). Use mode='write' with an approved plan for scripts that open transactions.",
                    mode, progress, "read_mode_violation", 0, null);
            }
        }

        var outputMs = new MemoryStream();
        var errorMs = new MemoryStream();
        object? runtime = null;
        var changedCount = 0;
        var savesBlocked = 0;
        EventHandler<DocumentChangedEventArgs>? onChanged = null;
        EventHandler<DocumentSavingEventArgs>? onSaving = null;
        EventHandler<DocumentSavingAsEventArgs>? onSavingAs = null;

        try
        {
            var engine = PythonEngineFactory.Create();
            runtime = PythonEngineFactory.Describe(engine);
            // Pre-load Revit assemblies so the script can use "from Autodesk.Revit.DB import *"
            engine.Runtime.LoadAssembly(typeof(Document).Assembly);       // RevitAPI.dll
            engine.Runtime.LoadAssembly(typeof(UIApplication).Assembly);  // RevitAPIUI.dll

            engine.Runtime.IO.SetOutput(outputMs, Encoding.UTF8);
            engine.Runtime.IO.SetErrorOutput(errorMs, Encoding.UTF8);

            var scope = engine.CreateScope();
            scope.SetVariable("doc", doc);
            scope.SetVariable("uidoc", app.ActiveUIDocument);
            scope.SetVariable("uiapp", app);
            scope.SetVariable("app", app.Application);
            scope.SetVariable("__output__", "");
            scope.SetVariable("__mode__", mode);
            scope.SetVariable("progress", new Action<object?>(progress.Add));

            if (mode == ModeRead)
            {
                onChanged = (_, e) =>
                    changedCount += e.GetAddedElementIds().Count + e.GetModifiedElementIds().Count + e.GetDeletedElementIds().Count;
                onSaving = (_, e) => { savesBlocked++; e.Cancel(); };
                onSavingAs = (_, e) => { savesBlocked++; e.Cancel(); };
                app.Application.DocumentChanged += onChanged;
                app.Application.DocumentSaving += onSaving;
                app.Application.DocumentSavingAs += onSavingAs;
            }

            ActiveProgress = progress;
            engine.Execute(script, scope);

            outputMs.Position = 0;
            var output = new StreamReader(outputMs, Encoding.UTF8).ReadToEnd();

            // Also honour __output__ if the script set it explicitly
            if (scope.TryGetVariable("__output__", out object outVar) && outVar is string outStr && !string.IsNullOrEmpty(outStr))
                output = string.IsNullOrEmpty(output) ? outStr : outStr + "\n" + output;

            if (changedCount > 0 || savesBlocked > 0)
            {
                return Result(false, output,
                    $"Read-mode violation: the script touched the model ({changedCount} element changes, {savesBlocked} save attempts blocked). "
                    + "Changes made before this report are NOT rolled back; check the model.",
                    mode, progress, "read_mode_violation", changedCount, runtime);
            }

            return Result(true, output, "", mode, progress, null, 0, runtime);
        }
        catch (Exception ex)
        {
            string error;
            try
            {
                errorMs.Position = 0;
                var errText = new StreamReader(errorMs, Encoding.UTF8).ReadToEnd();
                error = string.IsNullOrEmpty(errText) ? ex.Message : errText + "\n" + ex.Message;
            }
            catch
            {
                error = ex.Message;
            }
            var kind = changedCount > 0 || savesBlocked > 0 ? "read_mode_violation" : null;
            return Result(false, "", error, mode, progress, kind, changedCount, runtime);
        }
        finally
        {
            ActiveProgress = null;
            if (onChanged != null) app.Application.DocumentChanged -= onChanged;
            if (onSaving != null) app.Application.DocumentSaving -= onSaving;
            if (onSavingAs != null) app.Application.DocumentSavingAs -= onSavingAs;
        }
    }

    private static object Result(bool success, string output, string error, string mode, ProgressBuffer progress, string? kind, int changedCount, object? runtime)
    {
        return new
        {
            success,
            output,
            error,
            mode,
            progress = progress.Snapshot(),
            error_kind = kind,
            model_changes_in_read_mode = changedCount,
            runtime,
        };
    }
}

/// <summary>Thread-safe, bounded list of progress lines written by progress("...") in a script.</summary>
internal sealed class ProgressBuffer
{
    private readonly object _gate = new();
    private readonly Queue<string> _lines = new();
    private readonly int _maxLines;
    private readonly int _maxLineLength;

    public ProgressBuffer(int maxLines, int maxLineLength)
    {
        _maxLines = maxLines;
        _maxLineLength = maxLineLength;
    }

    public void Add(object? message)
    {
        var text = message?.ToString() ?? "";
        if (text.Length > _maxLineLength) text = text.Substring(0, _maxLineLength);
        lock (_gate)
        {
            _lines.Enqueue(text);
            while (_lines.Count > _maxLines) _lines.Dequeue();
        }
    }

    public string[] Snapshot()
    {
        lock (_gate) return _lines.ToArray();
    }
}
