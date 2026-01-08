using System;
using System.Text.Json;
using Autodesk.Revit.UI;
using RevitBridge.Commands.Enhancements.Transactions;
using RevitBridge.Commands.Enhancements.Analysis;
using RevitBridge.Commands.Enhancements.Batch;

namespace RevitBridge.Commands.Enhancements
{
    /// <summary>
    /// Registry for Phase 4 commands (24 enhancement tools)
    /// These are advanced control and optimization tools for power users
    /// </summary>
    public static class Phase4CommandRegistry
    {
        public static object Execute(UIApplication app, string tool, JsonElement payload)
        {
            return tool switch
            {
                // === TRANSACTION CONTROL COMMANDS (8 tools) - Advanced Change Management ===
                // Transaction (#2, Score: 293), TransactionGroup (#82, Score: 222)

                "revit.begin_transaction_group" => TransactionCommands.BeginTransactionGroup(app, payload),
                "revit.commit_transaction_group" => TransactionCommands.CommitTransactionGroup(app, payload),
                "revit.rollback_transaction_group" => TransactionCommands.RollbackTransactionGroup(app, payload),
                "revit.get_document_changes" => TransactionCommands.GetDocumentChanges(app, payload),
                "revit.get_undo_record" => TransactionCommands.GetUndoRecord(app, payload),
                "revit.clear_undo_stack" => TransactionCommands.ClearUndoStack(app, payload),
                "revit.set_failure_handling_options" => TransactionCommands.SetFailureHandlingOptions(app, payload),
                "revit.get_warnings" => TransactionCommands.GetWarnings(app, payload),

                // === ANALYSIS & VALIDATION COMMANDS (7 tools) - Model Quality ===
                // Reference (#92, Score: 217), ReferenceIntersector (#93, Score: 217)

                "revit.analyze_model_performance" => AnalysisCommands.AnalyzeModelPerformance(app, payload),
                "revit.find_element_intersections" => AnalysisCommands.FindElementIntersections(app, payload),
                "revit.validate_elements" => AnalysisCommands.ValidateElements(app, payload),
                "revit.find_duplicate_elements" => AnalysisCommands.FindDuplicateElements(app, payload),
                "revit.analyze_element_dependencies" => AnalysisCommands.AnalyzeElementDependencies(app, payload),
                "revit.check_model_integrity" => AnalysisCommands.CheckModelIntegrity(app, payload),
                "revit.get_element_statistics" => AnalysisCommands.GetElementStatistics(app, payload),

                // === BATCH OPERATIONS COMMANDS (9 tools) - High-Performance Bulk Ops ===
                // ElementId (#4, Score: 285), Element (#5, Score: 284)

                "revit.batch_set_parameters" => BatchCommands.BatchSetParameters(app, payload),
                "revit.batch_delete_elements" => BatchCommands.BatchDeleteElements(app, payload),
                "revit.batch_copy_elements" => BatchCommands.BatchCopyElements(app, payload),
                "revit.batch_move_elements" => BatchCommands.BatchMoveElements(app, payload),
                "revit.batch_rotate_elements" => BatchCommands.BatchRotateElements(app, payload),
                "revit.batch_mirror_elements" => BatchCommands.BatchMirrorElements(app, payload),
                "revit.batch_change_type" => BatchCommands.BatchChangeType(app, payload),
                "revit.batch_isolate_in_views" => BatchCommands.BatchIsolateInViews(app, payload),
                "revit.batch_export_to_csv" => BatchCommands.BatchExportToCSV(app, payload),

                _ => null // Return null to let main factory handle unknown commands
            };
        }

        /// <summary>
        /// Get list of all Phase 4 command names for documentation/validation
        /// </summary>
        public static string[] GetCommandNames()
        {
            return new[]
            {
                // Transaction Control (8)
                "revit.begin_transaction_group",
                "revit.commit_transaction_group",
                "revit.rollback_transaction_group",
                "revit.get_document_changes",
                "revit.get_undo_record",
                "revit.clear_undo_stack",
                "revit.set_failure_handling_options",
                "revit.get_warnings",

                // Analysis & Validation (7)
                "revit.analyze_model_performance",
                "revit.find_element_intersections",
                "revit.validate_elements",
                "revit.find_duplicate_elements",
                "revit.analyze_element_dependencies",
                "revit.check_model_integrity",
                "revit.get_element_statistics",

                // Batch Operations (9)
                "revit.batch_set_parameters",
                "revit.batch_delete_elements",
                "revit.batch_copy_elements",
                "revit.batch_move_elements",
                "revit.batch_rotate_elements",
                "revit.batch_mirror_elements",
                "revit.batch_change_type",
                "revit.batch_isolate_in_views",
                "revit.batch_export_to_csv"
            };
        }
    }
}
