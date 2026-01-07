using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevitBridge.Bridge;

public static class BridgeCommandFactory
{
    public static object Execute(UIApplication app, string tool, JsonElement payload)
    {
        return tool switch
        {
            "revit.health" => ExecuteHealth(app),
            "revit.open_document" => ExecuteOpenDocument(app, payload),
            "revit.list_views" => ExecuteListViews(app),
            "revit.export_schedules" => ExecuteExportSchedules(app, payload),
            "revit.export_pdf_by_sheet_set" => ExecuteExportPdf(app, payload),
            _ => new { status = "error", message = $"Unknown tool: {tool}" }
        };
    }

    public static List<string> GetToolCatalog()
    {
        return new List<string>
        {
            "revit.health",
            "revit.open_document",
            "revit.list_views",
            "revit.export_schedules",
            "revit.export_pdf_by_sheet_set"
        };
    }

    private static object ExecuteHealth(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        return new
        {
            status = "healthy",
            revit_version = app.Application.VersionNumber,
            revit_build = app.Application.VersionBuild,
            active_document = doc?.Title ?? "none",
            document_is_modified = doc?.IsModified ?? false,
            username = app.Application.Username
        };
    }

    private static object ExecuteOpenDocument(UIApplication app, JsonElement payload)
    {
        var path = payload.GetProperty("path").GetString();
        if (string.IsNullOrEmpty(path))
            throw new ArgumentException("Missing 'path' parameter");

        var docPath = new FilePath(path);
        var openOptions = new OpenOptions();
        var doc = app.Application.OpenDocumentFile(docPath, openOptions);

        return new
        {
            path = doc.PathName,
            title = doc.Title,
            is_family = doc.IsFamilyDocument,
            is_modified = doc.IsModified
        };
    }

    private static object ExecuteListViews(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var views = new FilteredElementCollector(doc)
            .OfClass(typeof(View))
            .Cast<View>()
            .Where(v => !v.IsTemplate)
            .Select(v => new
            {
                id = v.Id.IntegerValue,
                name = v.Name,
                type = v.ViewType.ToString(),
                scale = v.Scale,
                detail_level = v.DetailLevel.ToString()
            })
            .ToList();

        return new { views, count = views.Count };
    }

    private static object ExecuteExportSchedules(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var outputPath = payload.GetProperty("output_path").GetString();
        if (string.IsNullOrEmpty(outputPath))
            throw new ArgumentException("Missing 'output_path' parameter");

        var schedules = new FilteredElementCollector(doc)
            .OfClass(typeof(ViewSchedule))
            .Cast<ViewSchedule>()
            .ToList();

        var exported = new List<string>();

        using (var trans = new Transaction(doc, "Export Schedules"))
        {
            trans.Start();

            foreach (var schedule in schedules)
            {
                try
                {
                    var options = new ViewScheduleExportOptions
                    {
                        Title = false,
                        FieldDelimiter = ",",
                        TextQualifier = ExportTextQualifier.DoubleQuote
                    };

                    var filename = $"{SanitizeFileName(schedule.Name)}.csv";
                    var fullPath = System.IO.Path.Combine(outputPath, filename);
                    schedule.Export(outputPath, filename, options);
                    exported.Add(fullPath);
                }
                catch (Exception ex)
                {
                    // Log error but continue with other schedules
                    Serilog.Log.Warning(ex, "Failed to export schedule {ScheduleName}", schedule.Name);
                }
            }

            trans.Commit();
        }

        return new { schedules = exported, count = exported.Count };
    }

    private static object ExecuteExportPdf(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var outputPath = payload.GetProperty("output_path").GetString();
        if (string.IsNullOrEmpty(outputPath))
            throw new ArgumentException("Missing 'output_path' parameter");

        var sheets = new FilteredElementCollector(doc)
            .OfClass(typeof(ViewSheet))
            .Cast<ViewSheet>()
            .Where(s => !s.IsPlaceholder)
            .Select(s => s.Id)
            .ToList();

        if (sheets.Count == 0)
        {
            return new
            {
                output_path = outputPath,
                sheets_exported = 0,
                status = "no_sheets",
                message = "No sheets found in document"
            };
        }

        var options = new PDFExportOptions
        {
            FileName = System.IO.Path.GetFileNameWithoutExtension(outputPath),
            Combine = true
        };

        var exportDir = System.IO.Path.GetDirectoryName(outputPath);
        doc.Export(exportDir, sheets, options);

        return new
        {
            output_path = outputPath,
            sheets_exported = sheets.Count,
            status = "exported"
        };
    }

    private static string SanitizeFileName(string fileName)
    {
        var invalidChars = System.IO.Path.GetInvalidFileNameChars();
        return new string(fileName.Select(c => invalidChars.Contains(c) ? '_' : c).ToArray());
    }
}
