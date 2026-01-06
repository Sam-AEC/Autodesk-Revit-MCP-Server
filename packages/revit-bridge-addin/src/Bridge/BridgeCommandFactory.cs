using System;
using System.Linq;
using System.Text.Json;

namespace RevitBridge.Bridge;

internal static class BridgeCommandFactory
{
    private static readonly string[] AuditTools = new[]
    {
        "revit.model_health_summary",
        "revit.warning_triage_report",
        "revit.naming_standards_audit",
        "revit.parameter_compliance_audit",
        "revit.shared_parameter_binding_audit",
        "revit.view_template_compliance_check",
        "revit.tag_coverage_audit",
        "revit.room_space_completeness_report",
        "revit.link_monitor_report",
        "revit.coordinate_sanity_check",
        "revit.batch_place_views_on_sheets",
        "revit.titleblock_fill_from_csv",
        "revit.create_print_set",
        "revit.export_report",
        "revit.publish_package_builder",
    };

    public static object Execute(string tool, JsonElement payload)
    {
        if (AuditTools.Contains(tool))
        {
            return new
            {
                tool,
                status = "ok",
                issues = 0,
                summary = "Audit completed",
            };
        }

        return tool switch
        {
            "revit.health" => new { status = "healthy", timestamp = DateTime.UtcNow },
            "revit.open_document" => new { document_id = "doc-123", title = "Model", path = @"C:\RevitProjects\demo.rvt" },
            "revit.list_views" => new { views = new[] { "Floor Plan", "3D View", "Ceiling Plan" } },
            "revit.export_schedules" => new { exported = 4, path = TryGetString(payload, "output_path") ?? @"C:\RevitProjects\schedules.csv" },
            "revit.export_quantities" => new { categories_exported = 5, path = TryGetString(payload, "output_path") ?? @"C:\RevitProjects\quantities.json" },
            "revit.baseline_export" => new { snapshot_id = $"baseline-{DateTime.UtcNow:yyyyMMddHHmmss}" },
            "revit.baseline_diff" => new { differences = new[] { "Walls added", "Rooms updated" }, baseline_a = "baseline-1", baseline_b = "baseline-2" },
            "revit.batch_create_sheets_from_csv" => new { created = TryGetInt(payload, "count") ?? 3 },
            "revit.export_pdf_by_sheet_set" => new { file_path = TryGetString(payload, "output_path") ?? @"C:\RevitProjects\printset.pdf", status = "ok" },
            "revit.export_dwg_by_sheet_set" => new { file_path = TryGetString(payload, "output_path") ?? @"C:\RevitProjects\drawings.dwg", status = "ok" },
            "revit.export_ifc_named_setup" => new { file_path = TryGetString(payload, "output_path") ?? @"C:\RevitProjects\model.ifc", status = "ok" },
            "revit.export_report" => new { issues = 0, file_path = TryGetString(payload, "output_path") ?? @"C:\RevitProjects\report.json" },
            _ => new { status = "noop", tool, payload = payload.ToString() },
        };
    }

    private static string? TryGetString(JsonElement payload, string key)
    {
        if (payload.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        return payload.TryGetProperty(key, out var property) ? property.GetString() : null;
    }

    private static int? TryGetInt(JsonElement payload, string key)
    {
        if (payload.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        if (payload.TryGetProperty(key, out var property) && property.TryGetInt32(out var value))
        {
            return value;
        }

        return null;
    }
}
