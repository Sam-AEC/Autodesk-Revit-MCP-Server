using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Events;
using Autodesk.Revit.UI;
using Microsoft.Scripting.Hosting;

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
        return ReadModeRules.FindViolations(script);
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
        ScriptEngine? engine = null;
        ScriptScope? scope = null;
        var changedCount = 0;
        var savesBlocked = 0;
        EventHandler<DocumentChangedEventArgs>? onChanged = null;
        EventHandler<DocumentSavingEventArgs>? onSaving = null;
        EventHandler<DocumentSavingAsEventArgs>? onSavingAs = null;
        TransactionGroup? readGuard = null;

        try
        {
            engine = PythonEngineFactory.Create();
            runtime = PythonEngineFactory.Describe(engine);
            // Pre-load Revit assemblies so the script can use "from Autodesk.Revit.DB import *"
            engine.Runtime.LoadAssembly(typeof(Document).Assembly);       // RevitAPI.dll
            engine.Runtime.LoadAssembly(typeof(UIApplication).Assembly);  // RevitAPIUI.dll

            engine.Runtime.IO.SetOutput(outputMs, Encoding.UTF8);
            engine.Runtime.IO.SetErrorOutput(errorMs, Encoding.UTF8);

            scope = engine.CreateScope();
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

                // The name check above only catches scripts that spell out Transaction. A script that builds the name
                // at run time (seen live on Revit 2024: getattr(DB, 'Trans' + 'action')) changed the model without
                // approval. Everything a read-mode script does therefore runs inside a group that is always rolled back.
                readGuard = new TransactionGroup(doc, "AEC Model Bridge read-mode guard");
                readGuard.Start();
            }

            ActiveProgress = progress;
            engine.Execute(script, scope);

            outputMs.Position = 0;
            var output = new StreamReader(outputMs, Encoding.UTF8).ReadToEnd();

            // Also honour __output__ if the script set it explicitly
            if (scope.TryGetVariable("__output__", out object outVar) && outVar is string outStr && !string.IsNullOrEmpty(outStr))
                output = string.IsNullOrEmpty(output) ? outStr : outStr + "\n" + output;

            // A script that started a transaction and never committed it would block the next command
            // ("a transaction is already open"). Roll it back and say so instead of reporting success.
            var left = RollBackOpenTransactions(doc, scope);
            if (left.RolledBack > 0)
            {
                return Result(false, output,
                    "The script ended with a transaction still open (started, never committed). It was rolled back, so its changes were discarded."
                    + (left.StillOpen ? " The document still reports an open transaction that the bridge cannot reach; check Revit before continuing." : "")
                    + " Commit inside the script, or use 'with Transaction(...) as t:' and call t.Commit().",
                    mode, progress, "transaction_left_open", changedCount, runtime, left.RolledBack);
            }

            var guardNote = EndReadGuard(ref readGuard, app, onChanged, ref changedCount);
            if (changedCount > 0 || savesBlocked > 0)
            {
                return Result(false, output,
                    $"Read-mode violation: the script touched the model ({changedCount} element changes, {savesBlocked} save attempts blocked). "
                    + guardNote,
                    mode, progress, "read_mode_violation", changedCount, runtime);
            }
            if (guardNote.Length > 0)
            {
                return Result(false, output, guardNote, mode, progress, "read_mode_guard_failed", changedCount, runtime);
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
            var left = RollBackOpenTransactions(doc, scope);
            var guardNote = EndReadGuard(ref readGuard, app, onChanged, ref changedCount);
            if (guardNote.Length > 0) error += Environment.NewLine + guardNote;
            var kind = changedCount > 0 || savesBlocked > 0 ? "read_mode_violation" : null;
            if (left.RolledBack > 0 || left.StillOpen)
            {
                error += $"\nThe failed script left {left.RolledBack} transaction(s) open; they were rolled back so the next command can run."
                    + (left.StillOpen ? " The document still reports an open transaction that the bridge could not reach." : "");
                kind ??= "transaction_left_open";
            }
            if (!PythonEngineFactory.StandardLibraryAvailable && error.Contains("No module named"))
                error += "\n" + PythonEngineFactory.MissingLibraryWarning;
            return Result(false, "", error, mode, progress, kind, changedCount, runtime, left.RolledBack);
        }
        finally
        {
            ActiveProgress = null;
            if (readGuard != null)
            {
                int unused = 0;
                EndReadGuard(ref readGuard, app, onChanged, ref unused);
            }
            // Shut the runtime down after every script, success or failure, so nothing carries over.
            PythonEngineFactory.ShutdownQuietly(engine);
            if (onChanged != null) app.Application.DocumentChanged -= onChanged;
            if (onSaving != null) app.Application.DocumentSaving -= onSaving;
            if (onSavingAs != null) app.Application.DocumentSavingAs -= onSavingAs;
        }
    }

    /// <summary>
    /// Closes the read-mode guard group by rolling it back, so nothing a read-mode script did stays in the model.
    /// The change counter is frozen first (the roll-back itself raises DocumentChanged). Returns a sentence for the
    /// result, empty when nothing needs saying.
    /// </summary>
    private static string EndReadGuard(ref TransactionGroup? guard, UIApplication app,
        EventHandler<DocumentChangedEventArgs>? onChanged, ref int changedCount)
    {
        if (guard == null) return "";
        var group = guard;
        guard = null;
        if (onChanged != null) app.Application.DocumentChanged -= onChanged;
        try
        {
            if (group.IsValidObject && group.GetStatus() == TransactionStatus.Started)
            {
                group.RollBack();
                return changedCount > 0
                    ? "The bridge rolled those changes back; the model is as it was. Use mode='write' with an approved plan for scripts that change the model."
                    : "";
            }
            return changedCount > 0
                ? "The read-mode guard group was already closed by the script, so the changes could not be rolled back; check the model."
                : "The read-mode guard group was closed by the script; nothing was rolled back. Check the model before relying on this result.";
        }
        catch (Exception ex)
        {
            return "The read-mode guard could not be rolled back (" + ex.Message + "); check the model.";
        }
    }

    /// <summary>
    /// Rolls back transactions the script left started. Revit has no list of open transactions, so this
    /// looks at the objects the script kept in its top-level variables (and one level into lists, tuples
    /// and dictionaries): sub-transactions first, then transactions, then groups. A transaction held only
    /// in a function's local variable cannot be found; <c>StillOpen</c> reports that case.
    /// </summary>
    internal static (int RolledBack, bool StillOpen) RollBackOpenTransactions(Document doc, ScriptScope? scope)
    {
        var rolledBack = 0;
        try
        {
            var found = new List<object>();
            if (scope != null)
            {
                foreach (var item in scope.GetItems())
                {
                    CollectTransactions(item.Value, found, 1);
                }
            }
            foreach (var order in new[] { 0, 1, 2 })
            {
                foreach (var candidate in found)
                {
                    try
                    {
                        if (order == 0 && candidate is SubTransaction sub && sub.IsValidObject && sub.GetStatus() == TransactionStatus.Started)
                        {
                            sub.RollBack();
                            rolledBack++;
                        }
                        else if (order == 1 && candidate is Transaction tx && tx.IsValidObject && tx.GetStatus() == TransactionStatus.Started)
                        {
                            tx.RollBack();
                            rolledBack++;
                        }
                        else if (order == 2 && candidate is TransactionGroup group && group.IsValidObject && group.GetStatus() == TransactionStatus.Started)
                        {
                            group.RollBack();
                            rolledBack++;
                        }
                    }
                    catch
                    {
                        // Keep going: the remaining objects may still be reachable.
                    }
                }
            }
        }
        catch
        {
            // Scope enumeration failed; fall through to the IsModifiable check.
        }
        var stillOpen = false;
        try { stillOpen = doc.IsValidObject && doc.IsModifiable; } catch { /* document went away */ }
        return (rolledBack, stillOpen);
    }

    private static void CollectTransactions(object? value, List<object> found, int depth)
    {
        if (value == null) return;
        if (value is Transaction || value is SubTransaction || value is TransactionGroup)
        {
            if (!found.Contains(value)) found.Add(value);
            return;
        }
        if (depth <= 0 || value is string) return;
        if (value is System.Collections.IDictionary dict)
        {
            foreach (System.Collections.DictionaryEntry entry in dict) CollectTransactions(entry.Value, found, depth - 1);
        }
        else if (value is System.Collections.IEnumerable items)
        {
            var seen = 0;
            foreach (var entry in items)
            {
                CollectTransactions(entry, found, depth - 1);
                if (++seen >= 1000) break;
            }
        }
    }

    private static object Result(bool success, string output, string error, string mode, ProgressBuffer progress, string? kind, int changedCount, object? runtime, int transactionsRolledBack = 0)
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
            transactions_rolled_back = transactionsRolledBack,
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
