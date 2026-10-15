using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Autodesk.Revit.DB;

namespace RevitBridge.Bridge;

/// <summary>A native command transaction: warnings are recorded, errors roll back.</summary>
/// <remarks>Script-owned transactions and per-element skip policies are separate.</remarks>
public sealed class BridgeTransaction : IDisposable
{
    private readonly Transaction _transaction;
    private readonly BridgeFailureCollector _failures = new();
    private readonly Action<IReadOnlyList<BridgeFailureMessage>>? _report;
    private readonly string _name;

    public BridgeTransaction(Document doc, string name,
        Action<IReadOnlyList<BridgeFailureMessage>>? report = null)
    {
        _transaction = new Transaction(doc, name);
        _name = name;
        _report = report;
    }

    public TransactionStatus Start()
    {
        var status = _transaction.Start();
        if (status != TransactionStatus.Started)
            throw Failure(status, "transaction_not_started");

        // Revit resets failure options at Start, so install the preprocessor afterwards.
        using (var options = _transaction.GetFailureHandlingOptions())
        {
            options.SetFailuresPreprocessor(_failures);
            options.SetClearAfterRollback(true);
            // Modeless processing can return Pending before rollback completes. The
            // preprocessor handles every posted warning/error without handing off to UI.
            options.SetForcedModalHandling(true);
            _transaction.SetFailureHandlingOptions(options);
        }
        return status;
    }

    public TransactionStatus GetStatus() => _transaction.GetStatus();

    public TransactionStatus RollBack() => _transaction.RollBack();

    public TransactionStatus CommitChecked()
    {
        TransactionStatus status;
        try
        {
            status = _transaction.Commit();
        }
        catch (Exception ex)
        {
            var current = RollBackIfStarted();
            throw Failure(current, current == TransactionStatus.Pending
                ? "revit_dialog_blocked" : "transaction_commit_failed", ex);
        }

        var finalStatus = _transaction.GetStatus();
        if (status != TransactionStatus.Committed || finalStatus != TransactionStatus.Committed || _failures.HasErrors)
        {
            finalStatus = RollBackIfStarted();
            throw Failure(finalStatus, finalStatus == TransactionStatus.Pending
                ? "revit_dialog_blocked" : finalStatus == TransactionStatus.RolledBack
                    ? "rolled_back" : "transaction_commit_failed");
        }

        _report?.Invoke(_failures.Messages);
        return status;
    }

    private TransactionStatus RollBackIfStarted()
    {
        if (_transaction.GetStatus() == TransactionStatus.Started)
            _transaction.RollBack();
        return _transaction.GetStatus();
    }

    private BridgeTransactionException Failure(TransactionStatus status, string kind, Exception? inner = null)
        => new(_name, status, kind, _failures.Messages, inner);

    public void Dispose()
    {
        // Exception paths before CommitChecked must not strand the next command.
        // A Pending transaction belongs to Revit failure processing and cannot be
        // rolled back/disposed here; the failed result explicitly reports that state.
        if (_transaction.GetStatus() == TransactionStatus.Pending) return;
        try { RollBackIfStarted(); }
        finally { _transaction.Dispose(); }
    }
}

internal sealed class BridgeFailureCollector : IFailuresPreprocessor
{
    public List<BridgeFailureMessage> Messages { get; } = new();
    public bool HasErrors { get; private set; }

    public FailureProcessingResult PreprocessFailures(FailuresAccessor accessor)
    {
        foreach (var failure in accessor.GetFailureMessages())
        {
            var severity = failure.GetSeverity();
            var message = new BridgeFailureMessage
            {
                Severity = severity.ToString(),
                Message = failure.GetDescriptionText(),
                FailureId = failure.GetFailureDefinitionId().Guid.ToString(),
                ElementIds = failure.GetFailingElementIds().Select(id => id.Value).Distinct().ToList(),
                AdditionalElementIds = failure.GetAdditionalElementIds().Select(id => id.Value).Distinct().ToList()
            };
            // Failure processing may visit the same message more than once.
            if (!Messages.Any(old => old.FailureId == message.FailureId && old.Message == message.Message
                && old.Severity == message.Severity && old.ElementIds.SequenceEqual(message.ElementIds)
                && old.AdditionalElementIds.SequenceEqual(message.AdditionalElementIds)))
                Messages.Add(message);

            if (severity == FailureSeverity.Warning)
                accessor.DeleteWarning(failure);
            else if (severity != FailureSeverity.None)
                HasErrors = true;
        }

        return HasErrors ? FailureProcessingResult.ProceedWithRollBack : FailureProcessingResult.Continue;
    }
}

public sealed class BridgeTransactionException : Exception
{
    public string Kind { get; }
    public TransactionStatus TransactionStatus { get; }
    public IReadOnlyList<BridgeFailureMessage> RevitMessages { get; }
    public List<long> FailedElementIds { get; }

    public BridgeTransactionException(string name, TransactionStatus status, string kind,
        IEnumerable<BridgeFailureMessage> messages, Exception? inner = null)
        : base(BridgeFailureText.Describe(name, status.ToString(), messages, inner), inner)
    {
        Kind = kind;
        TransactionStatus = status;
        RevitMessages = messages.ToList();
        FailedElementIds = BridgeFailureText.FailedElementIds(RevitMessages);
    }

    public object ToResult() => new
    {
        ok = false,
        success = false,
        kind = Kind,
        message = Message,
        transaction_status = TransactionStatus.ToString(),
        rolled_back = TransactionStatus == Autodesk.Revit.DB.TransactionStatus.RolledBack,
        failed_element_ids = FailedElementIds,
        element_ids = FailedElementIds,
        revit_messages = RevitMessages,
        warnings = BridgeFailureText.Warnings(RevitMessages)
    };

    public static BridgeTransactionException? Find(Exception error)
    {
        for (Exception? current = error; current != null; current = current.InnerException)
            if (current is BridgeTransactionException failure) return failure;
        return null;
    }
}
