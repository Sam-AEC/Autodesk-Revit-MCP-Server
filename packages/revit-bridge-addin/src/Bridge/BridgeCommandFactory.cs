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
            // Existing 5 tools
            "revit.health" => ExecuteHealth(app),
            "revit.open_document" => ExecuteOpenDocument(app, payload),
            "revit.list_views" => ExecuteListViews(app),
            "revit.export_schedules" => ExecuteExportSchedules(app, payload),
            "revit.export_pdf_by_sheet_set" => ExecuteExportPdf(app, payload),

            // Document Management (5 new)
            "revit.save_document" => ExecuteSaveDocument(app, payload),
            "revit.close_document" => ExecuteCloseDocument(app, payload),
            "revit.create_new_document" => ExecuteCreateNewDocument(app, payload),
            "revit.get_document_info" => ExecuteGetDocumentInfo(app),
            "revit.list_levels" => ExecuteListLevels(app),

            // Geometry Creation (8 new)
            "revit.create_wall" => ExecuteCreateWall(app, payload),
            "revit.create_floor" => ExecuteCreateFloor(app, payload),
            "revit.create_roof" => ExecuteCreateRoof(app, payload),
            "revit.create_level" => ExecuteCreateLevel(app, payload),
            "revit.create_grid" => ExecuteCreateGrid(app, payload),
            "revit.create_room" => ExecuteCreateRoom(app, payload),
            "revit.list_elements_by_category" => ExecuteListElementsByCategory(app, payload),
            "revit.delete_element" => ExecuteDeleteElement(app, payload),

            // Component Placement (4 new)
            "revit.place_family_instance" => ExecutePlaceFamilyInstance(app, payload),
            "revit.place_door" => ExecutePlaceDoor(app, payload),
            "revit.place_window" => ExecutePlaceWindow(app, payload),
            "revit.list_families" => ExecuteListFamilies(app, payload),

            // View Creation (3 new)
            "revit.create_floor_plan_view" => ExecuteCreateFloorPlanView(app, payload),
            "revit.create_3d_view" => ExecuteCreate3DView(app, payload),
            "revit.create_section_view" => ExecuteCreateSectionView(app, payload),

            // Parameters & Properties (10 new)
            "revit.get_element_parameters" => ExecuteGetElementParameters(app, payload),
            "revit.set_parameter_value" => ExecuteSetParameterValue(app, payload),
            "revit.get_parameter_value" => ExecuteGetParameterValue(app, payload),
            "revit.list_shared_parameters" => ExecuteListSharedParameters(app),
            "revit.create_shared_parameter" => ExecuteCreateSharedParameter(app, payload),
            "revit.list_project_parameters" => ExecuteListProjectParameters(app),
            "revit.create_project_parameter" => ExecuteCreateProjectParameter(app, payload),
            "revit.batch_set_parameters" => ExecuteBatchSetParameters(app, payload),
            "revit.get_type_parameters" => ExecuteGetTypeParameters(app, payload),
            "revit.set_type_parameter" => ExecuteSetTypeParameter(app, payload),

            // Sheets & Documentation (10 new)
            "revit.list_sheets" => ExecuteListSheets(app),
            "revit.create_sheet" => ExecuteCreateSheet(app, payload),
            "revit.delete_sheet" => ExecuteDeleteSheet(app, payload),
            "revit.place_viewport_on_sheet" => ExecutePlaceViewportOnSheet(app, payload),
            "revit.batch_create_sheets_from_csv" => ExecuteBatchCreateSheetsFromCsv(app, payload),
            "revit.populate_titleblock" => ExecutePopulateTitleblock(app, payload),
            "revit.list_titleblocks" => ExecuteListTitleblocks(app),
            "revit.get_sheet_info" => ExecuteGetSheetInfo(app, payload),
            "revit.duplicate_sheet" => ExecuteDuplicateSheet(app, payload),
            "revit.renumber_sheets" => ExecuteRenumberSheets(app, payload),

            // Advanced Exports (5 new)
            "revit.export_dwg_by_view" => ExecuteExportDwgByView(app, payload),
            "revit.export_ifc_with_settings" => ExecuteExportIfcWithSettings(app, payload),
            "revit.export_navisworks" => ExecuteExportNavisworks(app, payload),
            "revit.export_image" => ExecuteExportImage(app, payload),
            "revit.render_3d_view" => ExecuteRender3DView(app, payload),

            _ => new { status = "error", message = $"Unknown tool: {tool}" }
        };
    }

    public static List<string> GetToolCatalog()
    {
        return new List<string>
        {
            // Original 5
            "revit.health",
            "revit.open_document",
            "revit.list_views",
            "revit.export_schedules",
            "revit.export_pdf_by_sheet_set",

            // Document Management
            "revit.save_document",
            "revit.close_document",
            "revit.create_new_document",
            "revit.get_document_info",
            "revit.list_levels",

            // Geometry Creation
            "revit.create_wall",
            "revit.create_floor",
            "revit.create_roof",
            "revit.create_level",
            "revit.create_grid",
            "revit.create_room",
            "revit.list_elements_by_category",
            "revit.delete_element",

            // Component Placement
            "revit.place_family_instance",
            "revit.place_door",
            "revit.place_window",
            "revit.list_families",

            // View Creation
            "revit.create_floor_plan_view",
            "revit.create_3d_view",
            "revit.create_section_view",

            // Parameters & Properties
            "revit.get_element_parameters",
            "revit.set_parameter_value",
            "revit.get_parameter_value",
            "revit.list_shared_parameters",
            "revit.create_shared_parameter",
            "revit.list_project_parameters",
            "revit.create_project_parameter",
            "revit.batch_set_parameters",
            "revit.get_type_parameters",
            "revit.set_type_parameter",

            // Sheets & Documentation
            "revit.list_sheets",
            "revit.create_sheet",
            "revit.delete_sheet",
            "revit.place_viewport_on_sheet",
            "revit.batch_create_sheets_from_csv",
            "revit.populate_titleblock",
            "revit.list_titleblocks",
            "revit.get_sheet_info",
            "revit.duplicate_sheet",
            "revit.renumber_sheets",

            // Advanced Exports
            "revit.export_dwg_by_view",
            "revit.export_ifc_with_settings",
            "revit.export_navisworks",
            "revit.export_image",
            "revit.render_3d_view"
        };
    }

    // ==================== EXISTING TOOLS ====================

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
                id = v.Id.Value,
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

    // ==================== DOCUMENT MANAGEMENT (5 NEW) ====================

    private static object ExecuteSaveDocument(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var savePath = payload.TryGetProperty("path", out var pathProp) ? pathProp.GetString() : null;

        if (!string.IsNullOrEmpty(savePath))
        {
            // Save As
            var saveAsOptions = new SaveAsOptions { OverwriteExistingFile = true };
            doc.SaveAs(savePath, saveAsOptions);
            return new { path = savePath, saved_as = true };
        }
        else
        {
            // Save
            doc.Save();
            return new { path = doc.PathName, saved_as = false };
        }
    }

    private static object ExecuteCloseDocument(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var saveChanges = payload.TryGetProperty("save_changes", out var saveProp) && saveProp.GetBoolean();
        var title = doc.Title;

        if (saveChanges && doc.IsModified)
        {
            doc.Save();
        }

        doc.Close(saveChanges);
        return new { closed = title, saved = saveChanges };
    }

    private static object ExecuteCreateNewDocument(UIApplication app, JsonElement payload)
    {
        var templatePath = payload.TryGetProperty("template_path", out var tpl) ? tpl.GetString() : null;

        Document doc;
        if (!string.IsNullOrEmpty(templatePath))
        {
            doc = app.Application.NewProjectDocument(templatePath);
        }
        else
        {
            doc = app.Application.NewProjectDocument(UnitSystem.Metric);
        }

        return new
        {
            title = doc.Title,
            path = doc.PathName ?? "unsaved",
            is_modified = doc.IsModified
        };
    }

    private static object ExecuteGetDocumentInfo(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var projectInfo = doc.ProjectInformation;

        return new
        {
            title = doc.Title,
            path = doc.PathName ?? "unsaved",
            is_modified = doc.IsModified,
            is_family = doc.IsFamilyDocument,
            is_workshared = doc.IsWorkshared,
            project_name = projectInfo?.get_Parameter(BuiltInParameter.PROJECT_NAME)?.AsString(),
            project_number = projectInfo?.get_Parameter(BuiltInParameter.PROJECT_NUMBER)?.AsString(),
            project_address = projectInfo?.get_Parameter(BuiltInParameter.PROJECT_ADDRESS)?.AsString(),
            project_status = projectInfo?.get_Parameter(BuiltInParameter.PROJECT_STATUS)?.AsString()
        };
    }

    private static object ExecuteListLevels(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var levels = new FilteredElementCollector(doc)
            .OfClass(typeof(Level))
            .Cast<Level>()
            .OrderBy(l => l.Elevation)
            .Select(l => new
            {
                id = l.Id.Value,
                name = l.Name,
                elevation = l.Elevation,
                elevation_ft = l.Elevation,
                elevation_m = UnitUtils.ConvertFromInternalUnits(l.Elevation, UnitTypeId.Meters)
            })
            .ToList();

        return new { levels, count = levels.Count };
    }

    // ==================== GEOMETRY CREATION (8 NEW) ====================

    private static object ExecuteCreateWall(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var height = payload.GetProperty("height").GetDouble();
        var levelName = payload.GetProperty("level").GetString();
        var wallTypeName = payload.TryGetProperty("wall_type", out var wt) ? wt.GetString() : null;

        using (var trans = new Transaction(doc, "Create Wall"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            var line = Line.CreateBound(startPoint, endPoint);

            Wall wall;
            if (!string.IsNullOrEmpty(wallTypeName))
            {
                var wallType = GetWallTypeByName(doc, wallTypeName);
                wall = Wall.Create(doc, line, wallType.Id, level.Id, height, 0, false, false);
            }
            else
            {
                wall = Wall.Create(doc, line, level.Id, false);
                var param = wall.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM);
                if (param != null && !param.IsReadOnly)
                {
                    param.Set(height);
                }
            }

            trans.Commit();

            return new
            {
                wall_id = wall.Id.Value,
                length = line.Length,
                length_ft = line.Length,
                length_m = UnitUtils.ConvertFromInternalUnits(line.Length, UnitTypeId.Meters),
                height = height
            };
        }
    }

    private static object ExecuteCreateFloor(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var boundaryPoints = ParsePointArray(payload.GetProperty("boundary_points"));
        var levelName = payload.GetProperty("level").GetString();
        var floorTypeName = payload.TryGetProperty("floor_type", out var ft) ? ft.GetString() : null;

        using (var trans = new Transaction(doc, "Create Floor"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            var curveLoop = new CurveLoop();

            for (int i = 0; i < boundaryPoints.Count; i++)
            {
                var start = boundaryPoints[i];
                var end = boundaryPoints[(i + 1) % boundaryPoints.Count];
                curveLoop.Append(Line.CreateBound(start, end));
            }

            Floor floor;
            if (!string.IsNullOrEmpty(floorTypeName))
            {
                var floorType = GetFloorTypeByName(doc, floorTypeName);
                floor = Floor.Create(doc, new List<CurveLoop> { curveLoop }, floorType.Id, level.Id);
            }
            else
            {
                var defaultFloorType = new FilteredElementCollector(doc)
                    .OfClass(typeof(FloorType))
                    .Cast<FloorType>()
                    .FirstOrDefault();

                if (defaultFloorType == null)
                    throw new InvalidOperationException("No floor types found in document");

                floor = Floor.Create(doc, new List<CurveLoop> { curveLoop }, defaultFloorType.Id, level.Id);
            }

            trans.Commit();

            var area = floor.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)?.AsDouble() ?? 0;

            return new
            {
                floor_id = floor.Id.Value,
                area_sf = area,
                area_sm = UnitUtils.ConvertFromInternalUnits(area, UnitTypeId.SquareMeters),
                level = levelName
            };
        }
    }

    private static object ExecuteCreateRoof(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var boundaryPoints = ParsePointArray(payload.GetProperty("boundary_points"));
        var levelName = payload.GetProperty("level").GetString();
        var roofTypeName = payload.TryGetProperty("roof_type", out var rt) ? rt.GetString() : null;

        using (var trans = new Transaction(doc, "Create Roof"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            var curveArray = new CurveArray();

            for (int i = 0; i < boundaryPoints.Count; i++)
            {
                var start = boundaryPoints[i];
                var end = boundaryPoints[(i + 1) % boundaryPoints.Count];
                curveArray.Append(Line.CreateBound(start, end));
            }

            RoofType roofType = null;
            if (!string.IsNullOrEmpty(roofTypeName))
            {
                roofType = GetRoofTypeByName(doc, roofTypeName);
            }

            var modelCurveArray = new ModelCurveArray();
            var footprint = doc.Create.NewFootPrintRoof(curveArray, level, roofType, out modelCurveArray);

            trans.Commit();

            return new
            {
                roof_id = footprint.Id.Value,
                level = levelName,
                curve_count = curveArray.Size
            };
        }
    }

    private static object ExecuteCreateLevel(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var name = payload.GetProperty("name").GetString();
        var elevation = payload.GetProperty("elevation").GetDouble();

        using (var trans = new Transaction(doc, "Create Level"))
        {
            trans.Start();

            var level = Level.Create(doc, elevation);
            level.Name = name;

            trans.Commit();

            return new
            {
                level_id = level.Id.Value,
                name = level.Name,
                elevation = level.Elevation,
                elevation_ft = level.Elevation,
                elevation_m = UnitUtils.ConvertFromInternalUnits(level.Elevation, UnitTypeId.Meters)
            };
        }
    }

    private static object ExecuteCreateGrid(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var name = payload.TryGetProperty("name", out var n) ? n.GetString() : null;

        using (var trans = new Transaction(doc, "Create Grid"))
        {
            trans.Start();

            var line = Line.CreateBound(startPoint, endPoint);
            var grid = Grid.Create(doc, line);

            if (!string.IsNullOrEmpty(name))
            {
                grid.Name = name;
            }

            trans.Commit();

            return new
            {
                grid_id = grid.Id.Value,
                name = grid.Name,
                curve_type = grid.Curve.GetType().Name
            };
        }
    }

    private static object ExecuteCreateRoom(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var locationPoint = ParseXYZ(payload.GetProperty("location_point"));
        var levelName = payload.GetProperty("level").GetString();
        var roomName = payload.TryGetProperty("name", out var n) ? n.GetString() : "Room";
        var roomNumber = payload.TryGetProperty("number", out var num) ? num.GetString() : null;

        using (var trans = new Transaction(doc, "Create Room"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            var uvPoint = new UV(locationPoint.X, locationPoint.Y);
            var room = doc.Create.NewRoom(level, uvPoint);

            if (!string.IsNullOrEmpty(roomName))
            {
                room.Name = roomName;
            }

            if (!string.IsNullOrEmpty(roomNumber))
            {
                room.Number = roomNumber;
            }

            trans.Commit();

            var area = room.Area;
            var volume = room.Volume;

            return new
            {
                room_id = room.Id.Value,
                name = room.Name,
                number = room.Number,
                area_sf = area,
                area_sm = UnitUtils.ConvertFromInternalUnits(area, UnitTypeId.SquareMeters),
                volume_cf = volume,
                volume_cm = UnitUtils.ConvertFromInternalUnits(volume, UnitTypeId.CubicMeters)
            };
        }
    }

    private static object ExecuteListElementsByCategory(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var categoryName = payload.GetProperty("category").GetString();
        var category = GetCategoryByName(doc, categoryName);

        var elements = new FilteredElementCollector(doc)
            .OfCategoryId(category.Id)
            .WhereElementIsNotElementType()
            .Select(e => new
            {
                id = e.Id.Value,
                name = e.Name,
                category = e.Category?.Name,
                type = doc.GetElement(e.GetTypeId())?.Name
            })
            .ToList();

        return new { elements, count = elements.Count, category = categoryName };
    }

    private static object ExecuteDeleteElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt32();

        using (var trans = new Transaction(doc, "Delete Element"))
        {
            trans.Start();

            var id = new ElementId((long)elementId);
            var deletedIds = doc.Delete(id);

            trans.Commit();

            return new
            {
                deleted_count = deletedIds.Count,
                deleted_ids = deletedIds.Select(i => i.Value).ToList()
            };
        }
    }

    // ==================== COMPONENT PLACEMENT (4 NEW) ====================

    private static object ExecutePlaceFamilyInstance(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var location = ParseXYZ(payload.GetProperty("location"));
        var familyName = payload.GetProperty("family_name").GetString();
        var typeName = payload.GetProperty("type_name").GetString();
        var levelName = payload.GetProperty("level").GetString();

        using (var trans = new Transaction(doc, "Place Family Instance"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            var familySymbol = GetFamilySymbolByName(doc, familyName, typeName);

            if (!familySymbol.IsActive)
            {
                familySymbol.Activate();
                doc.Regenerate();
            }

            var instance = doc.Create.NewFamilyInstance(location, familySymbol, level, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);

            trans.Commit();

            return new
            {
                instance_id = instance.Id.Value,
                family = familyName,
                type = typeName,
                level = levelName
            };
        }
    }

    private static object ExecutePlaceDoor(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var wallId = payload.GetProperty("wall_id").GetInt32();
        var location = ParseXYZ(payload.GetProperty("location"));
        var familyName = payload.TryGetProperty("family_name", out var fn) ? fn.GetString() : "Single-Flush";
        var typeName = payload.TryGetProperty("type_name", out var tn) ? tn.GetString() : "0915 x 2134mm";

        using (var trans = new Transaction(doc, "Place Door"))
        {
            trans.Start();

            var wall = doc.GetElement(new ElementId((long)wallId)) as Wall;
            if (wall == null)
                throw new ArgumentException($"Wall with ID {wallId} not found");

            var familySymbol = GetFamilySymbolByName(doc, familyName, typeName);

            if (!familySymbol.IsActive)
            {
                familySymbol.Activate();
                doc.Regenerate();
            }

            var door = doc.Create.NewFamilyInstance(location, familySymbol, wall, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);

            trans.Commit();

            return new
            {
                door_id = door.Id.Value,
                family = familyName,
                type = typeName,
                wall_id = wallId
            };
        }
    }

    private static object ExecutePlaceWindow(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var wallId = payload.GetProperty("wall_id").GetInt32();
        var location = ParseXYZ(payload.GetProperty("location"));
        var familyName = payload.TryGetProperty("family_name", out var fn) ? fn.GetString() : "Fixed";
        var typeName = payload.TryGetProperty("type_name", out var tn) ? tn.GetString() : "1200 x 1500mm";

        using (var trans = new Transaction(doc, "Place Window"))
        {
            trans.Start();

            var wall = doc.GetElement(new ElementId((long)wallId)) as Wall;
            if (wall == null)
                throw new ArgumentException($"Wall with ID {wallId} not found");

            var familySymbol = GetFamilySymbolByName(doc, familyName, typeName);

            if (!familySymbol.IsActive)
            {
                familySymbol.Activate();
                doc.Regenerate();
            }

            var window = doc.Create.NewFamilyInstance(location, familySymbol, wall, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);

            trans.Commit();

            return new
            {
                window_id = window.Id.Value,
                family = familyName,
                type = typeName,
                wall_id = wallId
            };
        }
    }

    private static object ExecuteListFamilies(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var categoryFilter = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

        var families = new FilteredElementCollector(doc)
            .OfClass(typeof(Family))
            .Cast<Family>()
            .Where(f => string.IsNullOrEmpty(categoryFilter) ||
                       f.FamilyCategory?.Name.Equals(categoryFilter, StringComparison.OrdinalIgnoreCase) == true)
            .Select(f => new
            {
                family_id = f.Id.Value,
                name = f.Name,
                category = f.FamilyCategory?.Name,
                types = GetFamilySymbols(doc, f).Select(fs => new
                {
                    type_id = fs.Id.Value,
                    name = fs.Name
                }).ToList()
            })
            .ToList();

        return new { families, count = families.Count };
    }

    // ==================== VIEW CREATION (3 NEW) ====================

    private static object ExecuteCreateFloorPlanView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var levelName = payload.GetProperty("level").GetString();
        var viewName = payload.TryGetProperty("name", out var n) ? n.GetString() : null;

        using (var trans = new Transaction(doc, "Create Floor Plan View"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            var viewFamilyType = GetViewFamilyType(doc, ViewFamily.FloorPlan);

            var view = ViewPlan.Create(doc, viewFamilyType.Id, level.Id);

            if (!string.IsNullOrEmpty(viewName))
            {
                view.Name = viewName;
            }

            trans.Commit();

            return new
            {
                view_id = view.Id.Value,
                name = view.Name,
                level = levelName,
                view_type = view.ViewType.ToString()
            };
        }
    }

    private static object ExecuteCreate3DView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var viewName = payload.TryGetProperty("name", out var n) ? n.GetString() : "3D View";

        using (var trans = new Transaction(doc, "Create 3D View"))
        {
            trans.Start();

            var viewFamilyType = GetViewFamilyType(doc, ViewFamily.ThreeDimensional);
            var view3d = View3D.CreateIsometric(doc, viewFamilyType.Id);
            view3d.Name = viewName;

            trans.Commit();

            return new
            {
                view_id = view3d.Id.Value,
                name = view3d.Name,
                view_type = view3d.ViewType.ToString()
            };
        }
    }

    private static object ExecuteCreateSectionView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var viewName = payload.TryGetProperty("name", out var n) ? n.GetString() : "Section";

        using (var trans = new Transaction(doc, "Create Section View"))
        {
            trans.Start();

            var viewFamilyType = GetViewFamilyType(doc, ViewFamily.Section);

            // Create bounding box for section
            var direction = (endPoint - startPoint).Normalize();
            var up = XYZ.BasisZ;
            var viewDirection = new XYZ(-direction.Y, direction.X, 0);

            var transform = Transform.Identity;
            transform.Origin = (startPoint + endPoint) / 2;
            transform.BasisX = direction;
            transform.BasisY = up;
            transform.BasisZ = viewDirection;

            var min = new XYZ(-10, -10, -10);
            var max = new XYZ(10, 10, 10);
            var bbox = new BoundingBoxXYZ { Transform = transform, Min = min, Max = max };

            var section = ViewSection.CreateSection(doc, viewFamilyType.Id, bbox);
            section.Name = viewName;

            trans.Commit();

            return new
            {
                view_id = section.Id.Value,
                name = section.Name,
                view_type = section.ViewType.ToString()
            };
        }
    }

    // ==================== HELPER METHODS ====================

    private static XYZ ParseXYZ(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Array)
        {
            var array = element.EnumerateArray().Select(e => e.GetDouble()).ToArray();
            return new XYZ(array[0], array[1], array.Length > 2 ? array[2] : 0);
        }

        var x = element.GetProperty("x").GetDouble();
        var y = element.GetProperty("y").GetDouble();
        var z = element.TryGetProperty("z", out var zProp) ? zProp.GetDouble() : 0;
        return new XYZ(x, y, z);
    }

    private static List<XYZ> ParsePointArray(JsonElement element)
    {
        return element.EnumerateArray()
            .Select(ParseXYZ)
            .ToList();
    }

    private static Level GetLevelByName(Document doc, string name)
    {
        var level = new FilteredElementCollector(doc)
            .OfClass(typeof(Level))
            .Cast<Level>()
            .FirstOrDefault(l => l.Name.Equals(name, StringComparison.OrdinalIgnoreCase));

        if (level == null)
            throw new ArgumentException($"Level '{name}' not found");

        return level;
    }

    private static WallType GetWallTypeByName(Document doc, string name)
    {
        var wallType = new FilteredElementCollector(doc)
            .OfClass(typeof(WallType))
            .Cast<WallType>()
            .FirstOrDefault(wt => wt.Name.Equals(name, StringComparison.OrdinalIgnoreCase));

        if (wallType == null)
            throw new ArgumentException($"Wall type '{name}' not found");

        return wallType;
    }

    private static FloorType GetFloorTypeByName(Document doc, string name)
    {
        var floorType = new FilteredElementCollector(doc)
            .OfClass(typeof(FloorType))
            .Cast<FloorType>()
            .FirstOrDefault(ft => ft.Name.Equals(name, StringComparison.OrdinalIgnoreCase));

        if (floorType == null)
            throw new ArgumentException($"Floor type '{name}' not found");

        return floorType;
    }

    private static RoofType GetRoofTypeByName(Document doc, string name)
    {
        var roofType = new FilteredElementCollector(doc)
            .OfClass(typeof(RoofType))
            .Cast<RoofType>()
            .FirstOrDefault(rt => rt.Name.Equals(name, StringComparison.OrdinalIgnoreCase));

        if (roofType == null)
            throw new ArgumentException($"Roof type '{name}' not found");

        return roofType;
    }

    private static Category GetCategoryByName(Document doc, string name)
    {
        var category = doc.Settings.Categories.Cast<Category>()
            .FirstOrDefault(c => c.Name.Equals(name, StringComparison.OrdinalIgnoreCase));

        if (category == null)
            throw new ArgumentException($"Category '{name}' not found");

        return category;
    }

    private static FamilySymbol GetFamilySymbolByName(Document doc, string familyName, string typeName)
    {
        var familySymbol = new FilteredElementCollector(doc)
            .OfClass(typeof(FamilySymbol))
            .Cast<FamilySymbol>()
            .FirstOrDefault(fs =>
                fs.Family.Name.Equals(familyName, StringComparison.OrdinalIgnoreCase) &&
                fs.Name.Equals(typeName, StringComparison.OrdinalIgnoreCase));

        if (familySymbol == null)
            throw new ArgumentException($"Family symbol '{familyName}: {typeName}' not found");

        return familySymbol;
    }

    private static IEnumerable<FamilySymbol> GetFamilySymbols(Document doc, Family family)
    {
        return family.GetFamilySymbolIds()
            .Select(id => doc.GetElement(id) as FamilySymbol)
            .Where(fs => fs != null);
    }

    private static ViewFamilyType GetViewFamilyType(Document doc, ViewFamily viewFamily)
    {
        var vft = new FilteredElementCollector(doc)
            .OfClass(typeof(ViewFamilyType))
            .Cast<ViewFamilyType>()
            .FirstOrDefault(x => x.ViewFamily == viewFamily);

        if (vft == null)
            throw new ArgumentException($"View family type for '{viewFamily}' not found");

        return vft;
    }

    private static string SanitizeFileName(string fileName)
    {
        var invalidChars = System.IO.Path.GetInvalidFileNameChars();
        return new string(fileName.Select(c => invalidChars.Contains(c) ? '_' : c).ToArray());
    }

    // ==================== PARAMETERS & PROPERTIES TOOLS ====================

    private static object ExecuteGetElementParameters(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt32();
        var element = doc.GetElement(new ElementId((long)elementId));
        if (element == null)
            throw new ArgumentException($"Element with ID {elementId} not found");

        var parameters = element.Parameters
            .Cast<Parameter>()
            .Where(p => p.HasValue)
            .Select(p => new
            {
                name = p.Definition.Name,
                value = GetParameterValueAsString(p),
                parameter_type = GetDefinitionDataTypeName(p.Definition),
                storage_type = p.StorageType.ToString(),
                is_read_only = p.IsReadOnly,
                is_shared = p.IsShared,
                guid = p.GUID.ToString()
            })
            .ToList();

        return new
        {
            element_id = elementId,
            element_type = element.GetType().Name,
            element_name = element.Name,
            parameter_count = parameters.Count,
            parameters
        };
    }

    private static object ExecuteSetParameterValue(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt32();
        var parameterName = payload.GetProperty("parameter_name").GetString();
        var value = payload.GetProperty("value");

        var element = doc.GetElement(new ElementId((long)elementId));
        if (element == null)
            throw new ArgumentException($"Element with ID {elementId} not found");

        using (var trans = new Transaction(doc, "Set Parameter Value"))
        {
            trans.Start();

            var parameter = element.LookupParameter(parameterName);
            if (parameter == null)
                throw new ArgumentException($"Parameter '{parameterName}' not found on element");

            if (parameter.IsReadOnly)
                throw new InvalidOperationException($"Parameter '{parameterName}' is read-only");

            SetParameterValue(parameter, value);

            trans.Commit();

            return new
            {
                element_id = elementId,
                parameter_name = parameterName,
                new_value = GetParameterValueAsString(parameter),
                status = "success"
            };
        }
    }

    private static object ExecuteGetParameterValue(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt32();
        var parameterName = payload.GetProperty("parameter_name").GetString();

        var element = doc.GetElement(new ElementId((long)elementId));
        if (element == null)
            throw new ArgumentException($"Element with ID {elementId} not found");

        var parameter = element.LookupParameter(parameterName);
        if (parameter == null)
            throw new ArgumentException($"Parameter '{parameterName}' not found on element");

        return new
        {
            element_id = elementId,
            parameter_name = parameterName,
            value = GetParameterValueAsString(parameter),
            storage_type = parameter.StorageType.ToString(),
            parameter_type = GetDefinitionDataTypeName(parameter.Definition),
            is_read_only = parameter.IsReadOnly
        };
    }

    private static object ExecuteListSharedParameters(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sharedParams = new FilteredElementCollector(doc)
            .OfClass(typeof(SharedParameterElement))
            .Cast<SharedParameterElement>()
            .Select(sp => new
            {
                name = sp.Name,
                guid = sp.GuidValue.ToString(),
                definition_group = GetDefinitionGroupName(sp.GetDefinition())
            })
            .ToList();

        return new
        {
            count = sharedParams.Count,
            shared_parameters = sharedParams
        };
    }

    private static object ExecuteCreateSharedParameter(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var parameterName = payload.GetProperty("name").GetString();
        var parameterType = payload.GetProperty("parameter_type").GetString();
        var groupName = payload.GetProperty("group_name").GetString();
        var categoryNames = payload.GetProperty("categories").EnumerateArray()
            .Select(e => e.GetString())
            .ToList();

        // Note: Creating shared parameters requires a shared parameter file
        // This is a simplified implementation
        throw new NotImplementedException(
            "Creating shared parameters requires a shared parameter file to be configured. " +
            "Use Revit UI to set up shared parameter file first, or provide file path in payload.");
    }

    private static object ExecuteListProjectParameters(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var projectParams = new FilteredElementCollector(doc)
            .OfClass(typeof(ParameterElement))
            .Cast<ParameterElement>()
            .Select(pe => new
            {
                name = pe.Name,
                id = pe.Id.Value,
                parameter_type = pe.get_Parameter(BuiltInParameter.ELEM_TYPE_PARAM)?.AsValueString() ?? "Unknown"
            })
            .ToList();

        return new
        {
            count = projectParams.Count,
            project_parameters = projectParams
        };
    }

    private static object ExecuteCreateProjectParameter(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var parameterName = payload.GetProperty("name").GetString();
        var parameterType = payload.GetProperty("parameter_type").GetString();
        var groupName = payload.GetProperty("group").GetString();
        var isInstance = payload.GetProperty("is_instance").GetBoolean();

        // Note: Creating project parameters is complex and requires category binding
        throw new NotImplementedException(
            "Creating project parameters requires category binding setup. " +
            "This functionality is planned for a future release.");
    }

    private static object ExecuteBatchSetParameters(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var updates = payload.GetProperty("updates").EnumerateArray()
            .Select(item => new
            {
                ElementId = item.GetProperty("element_id").GetInt32(),
                ParameterName = item.GetProperty("parameter_name").GetString(),
                Value = item.GetProperty("value")
            })
            .ToList();

        var results = new List<object>();
        var successCount = 0;
        var errorCount = 0;

        using (var trans = new Transaction(doc, "Batch Set Parameters"))
        {
            trans.Start();

            foreach (var update in updates)
            {
                try
                {
                    var element = doc.GetElement(new ElementId((long)update.ElementId));
                    if (element == null)
                    {
                        results.Add(new { element_id = update.ElementId, status = "error", message = "Element not found" });
                        errorCount++;
                        continue;
                    }

                    var parameter = element.LookupParameter(update.ParameterName);
                    if (parameter == null)
                    {
                        results.Add(new { element_id = update.ElementId, status = "error", message = $"Parameter '{update.ParameterName}' not found" });
                        errorCount++;
                        continue;
                    }

                    SetParameterValue(parameter, update.Value);
                    results.Add(new { element_id = update.ElementId, parameter_name = update.ParameterName, status = "success" });
                    successCount++;
                }
                catch (Exception ex)
                {
                    results.Add(new { element_id = update.ElementId, status = "error", message = ex.Message });
                    errorCount++;
                }
            }

            trans.Commit();
        }

        return new
        {
            total = updates.Count,
            success_count = successCount,
            error_count = errorCount,
            results
        };
    }

    private static object ExecuteGetTypeParameters(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt32();
        var element = doc.GetElement(new ElementId((long)elementId));
        if (element == null)
            throw new ArgumentException($"Element with ID {elementId} not found");

        var elementType = doc.GetElement(element.GetTypeId()) as ElementType;
        if (elementType == null)
            throw new InvalidOperationException("Element has no associated type");

        var typeParameters = elementType.Parameters
            .Cast<Parameter>()
            .Where(p => p.HasValue)
            .Select(p => new
            {
                name = p.Definition.Name,
                value = GetParameterValueAsString(p),
                parameter_type = GetDefinitionDataTypeName(p.Definition),
                storage_type = p.StorageType.ToString(),
                is_read_only = p.IsReadOnly
            })
            .ToList();

        return new
        {
            element_id = elementId,
            type_id = elementType.Id.Value,
            type_name = elementType.Name,
            type_family = elementType.FamilyName,
            parameter_count = typeParameters.Count,
            parameters = typeParameters
        };
    }

    private static object ExecuteSetTypeParameter(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var typeId = payload.GetProperty("type_id").GetInt32();
        var parameterName = payload.GetProperty("parameter_name").GetString();
        var value = payload.GetProperty("value");

        var elementType = doc.GetElement(new ElementId((long)typeId)) as ElementType;
        if (elementType == null)
            throw new ArgumentException($"Element type with ID {typeId} not found");

        using (var trans = new Transaction(doc, "Set Type Parameter"))
        {
            trans.Start();

            var parameter = elementType.LookupParameter(parameterName);
            if (parameter == null)
                throw new ArgumentException($"Parameter '{parameterName}' not found on type");

            if (parameter.IsReadOnly)
                throw new InvalidOperationException($"Parameter '{parameterName}' is read-only");

            SetParameterValue(parameter, value);

            trans.Commit();

            return new
            {
                type_id = typeId,
                type_name = elementType.Name,
                parameter_name = parameterName,
                new_value = GetParameterValueAsString(parameter),
                status = "success"
            };
        }
    }

    // Helper methods for parameter handling
    private static string GetParameterValueAsString(Parameter parameter)
    {
        if (!parameter.HasValue)
            return null;

        return parameter.StorageType switch
        {
            StorageType.String => parameter.AsString(),
            StorageType.Integer => parameter.AsInteger().ToString(),
            StorageType.Double => parameter.AsDouble().ToString(),
            StorageType.ElementId => parameter.AsElementId().Value.ToString(),
            _ => parameter.AsValueString()
        };
    }

    private static string GetDefinitionDataTypeName(Definition definition)
    {
        if (definition == null)
            return null;

        try
        {
            var dataType = definition.GetDataType();
            if (dataType == null)
                return null;

            var label = LabelUtils.GetLabelForSpec(dataType);
            if (!string.IsNullOrEmpty(label))
                return label;

            return dataType.TypeId;
        }
        catch
        {
            return null;
        }
    }

    private static string GetDefinitionGroupName(Definition definition)
    {
        if (definition == null)
            return null;

        try
        {
            var groupTypeId = definition.GetGroupTypeId();
            return groupTypeId.TypeId;
        }
        catch
        {
            return null;
        }
    }

    private static void SetParameterValue(Parameter parameter, JsonElement value)
    {
        switch (parameter.StorageType)
        {
            case StorageType.String:
                parameter.Set(value.GetString());
                break;

            case StorageType.Integer:
                parameter.Set(value.GetInt32());
                break;

            case StorageType.Double:
                parameter.Set(value.GetDouble());
                break;

            case StorageType.ElementId:
                parameter.Set(new ElementId(value.GetInt64()));
                break;

            default:
                throw new InvalidOperationException($"Unsupported storage type: {parameter.StorageType}");
        }
    }

    // ==================== SHEETS & DOCUMENTATION TOOLS ====================

    private static object ExecuteListSheets(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheets = new FilteredElementCollector(doc)
            .OfClass(typeof(ViewSheet))
            .Cast<ViewSheet>()
            .Select(sheet => new
            {
                id = sheet.Id.Value,
                sheet_number = sheet.SheetNumber,
                sheet_name = sheet.Name,
                is_placeholder = sheet.IsPlaceholder,
                titleblock_id = sheet.GetAllViewports().Count > 0
                    ? doc.GetElement(sheet.GetAllViewports().First())?.GetTypeId().Value
                    : (int?)null,
                viewport_count = sheet.GetAllViewports().Count
            })
            .OrderBy(s => s.sheet_number)
            .ToList();

        return new
        {
            count = sheets.Count,
            sheets
        };
    }

    private static object ExecuteCreateSheet(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheetNumber = payload.GetProperty("sheet_number").GetString();
        var sheetName = payload.GetProperty("sheet_name").GetString();
        var titleblockName = payload.TryGetProperty("titleblock_name", out var tbName)
            ? tbName.GetString()
            : null;

        using (var trans = new Transaction(doc, "Create Sheet"))
        {
            trans.Start();

            ViewSheet sheet;
            if (string.IsNullOrEmpty(titleblockName))
            {
                // Create placeholder sheet
                sheet = ViewSheet.CreatePlaceholder(doc);
            }
            else
            {
                // Get titleblock family symbol
                var titleblock = new FilteredElementCollector(doc)
                    .OfClass(typeof(FamilySymbol))
                    .Cast<FamilySymbol>()
                    .FirstOrDefault(fs =>
                        fs.Family.FamilyCategory.Name == "Title Blocks" &&
                        fs.Family.Name.Equals(titleblockName, StringComparison.OrdinalIgnoreCase));

                if (titleblock == null)
                    throw new ArgumentException($"Titleblock '{titleblockName}' not found");

                sheet = ViewSheet.Create(doc, titleblock.Id);
            }

            sheet.SheetNumber = sheetNumber;
            sheet.Name = sheetName;

            trans.Commit();

            return new
            {
                sheet_id = sheet.Id.Value,
                sheet_number = sheet.SheetNumber,
                sheet_name = sheet.Name,
                is_placeholder = sheet.IsPlaceholder,
                status = "success"
            };
        }
    }

    private static object ExecuteDeleteSheet(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheetId = payload.GetProperty("sheet_id").GetInt32();

        using (var trans = new Transaction(doc, "Delete Sheet"))
        {
            trans.Start();

            var sheet = doc.GetElement(new ElementId((long)sheetId)) as ViewSheet;
            if (sheet == null)
                throw new ArgumentException($"Sheet with ID {sheetId} not found");

            var sheetNumber = sheet.SheetNumber;
            var sheetName = sheet.Name;

            doc.Delete(new ElementId((long)sheetId));

            trans.Commit();

            return new
            {
                sheet_id = sheetId,
                sheet_number = sheetNumber,
                sheet_name = sheetName,
                status = "deleted"
            };
        }
    }

    private static object ExecutePlaceViewportOnSheet(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheetId = payload.GetProperty("sheet_id").GetInt32();
        var viewId = payload.GetProperty("view_id").GetInt32();
        var location = payload.TryGetProperty("location", out var loc)
            ? ParseXYZ(loc)
            : new XYZ(0.5, 0.5, 0);

        using (var trans = new Transaction(doc, "Place Viewport"))
        {
            trans.Start();

            var sheet = doc.GetElement(new ElementId((long)sheetId)) as ViewSheet;
            if (sheet == null)
                throw new ArgumentException($"Sheet with ID {sheetId} not found");

            var view = doc.GetElement(new ElementId((long)viewId)) as View;
            if (view == null)
                throw new ArgumentException($"View with ID {viewId} not found");

            if (view.ViewType == ViewType.DrawingSheet)
                throw new InvalidOperationException("Cannot place a sheet view on another sheet");

            if (Viewport.CanAddViewToSheet(doc, new ElementId((long)sheetId), new ElementId((long)viewId)))
            {
                var viewport = Viewport.Create(doc, sheet.Id, view.Id, location);

                trans.Commit();

                return new
                {
                    viewport_id = viewport.Id.Value,
                    sheet_id = sheetId,
                    view_id = viewId,
                    view_name = view.Name,
                    status = "success"
                };
            }
            else
            {
                throw new InvalidOperationException($"View '{view.Name}' cannot be placed on sheet (may already be on another sheet)");
            }
        }
    }

    private static object ExecuteBatchCreateSheetsFromCsv(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheets = payload.GetProperty("sheets").EnumerateArray()
            .Select(item => new
            {
                SheetNumber = item.GetProperty("sheet_number").GetString(),
                SheetName = item.GetProperty("sheet_name").GetString(),
                TitleblockName = item.TryGetProperty("titleblock_name", out var tb) ? tb.GetString() : null
            })
            .ToList();

        var results = new List<object>();
        var successCount = 0;
        var errorCount = 0;

        using (var trans = new Transaction(doc, "Batch Create Sheets"))
        {
            trans.Start();

            foreach (var sheetData in sheets)
            {
                try
                {
                    ViewSheet sheet;
                    if (string.IsNullOrEmpty(sheetData.TitleblockName))
                    {
                        sheet = ViewSheet.CreatePlaceholder(doc);
                    }
                    else
                    {
                        var titleblock = new FilteredElementCollector(doc)
                            .OfClass(typeof(FamilySymbol))
                            .Cast<FamilySymbol>()
                            .FirstOrDefault(fs =>
                                fs.Family.FamilyCategory.Name == "Title Blocks" &&
                                fs.Family.Name.Equals(sheetData.TitleblockName, StringComparison.OrdinalIgnoreCase));

                        if (titleblock == null)
                        {
                            results.Add(new { sheet_number = sheetData.SheetNumber, status = "error", message = $"Titleblock '{sheetData.TitleblockName}' not found" });
                            errorCount++;
                            continue;
                        }

                        sheet = ViewSheet.Create(doc, titleblock.Id);
                    }

                    sheet.SheetNumber = sheetData.SheetNumber;
                    sheet.Name = sheetData.SheetName;

                    results.Add(new {
                        sheet_id = sheet.Id.Value,
                        sheet_number = sheet.SheetNumber,
                        sheet_name = sheet.Name,
                        status = "success"
                    });
                    successCount++;
                }
                catch (Exception ex)
                {
                    results.Add(new { sheet_number = sheetData.SheetNumber, status = "error", message = ex.Message });
                    errorCount++;
                }
            }

            trans.Commit();
        }

        return new
        {
            total = sheets.Count,
            success_count = successCount,
            error_count = errorCount,
            results
        };
    }

    private static object ExecutePopulateTitleblock(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheetId = payload.GetProperty("sheet_id").GetInt32();
        var parameters = payload.GetProperty("parameters").EnumerateObject()
            .ToDictionary(p => p.Name, p => p.Value);

        using (var trans = new Transaction(doc, "Populate Titleblock"))
        {
            trans.Start();

            var sheet = doc.GetElement(new ElementId((long)sheetId)) as ViewSheet;
            if (sheet == null)
                throw new ArgumentException($"Sheet with ID {sheetId} not found");

            var updated = new List<string>();
            var failed = new List<string>();

            foreach (var param in parameters)
            {
                try
                {
                    var parameter = sheet.LookupParameter(param.Key);
                    if (parameter != null && !parameter.IsReadOnly)
                    {
                        SetParameterValue(parameter, param.Value);
                        updated.Add(param.Key);
                    }
                    else
                    {
                        failed.Add(param.Key);
                    }
                }
                catch (Exception)
                {
                    failed.Add(param.Key);
                }
            }

            trans.Commit();

            return new
            {
                sheet_id = sheetId,
                sheet_number = sheet.SheetNumber,
                updated_count = updated.Count,
                failed_count = failed.Count,
                updated_parameters = updated,
                failed_parameters = failed,
                status = "success"
            };
        }
    }

    private static object ExecuteListTitleblocks(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var titleblocks = new FilteredElementCollector(doc)
            .OfClass(typeof(FamilySymbol))
            .Cast<FamilySymbol>()
            .Where(fs => fs.Family.FamilyCategory.Name == "Title Blocks")
            .Select(fs => new
            {
                id = fs.Id.Value,
                family_name = fs.Family.Name,
                type_name = fs.Name,
                full_name = $"{fs.Family.Name}: {fs.Name}"
            })
            .ToList();

        return new
        {
            count = titleblocks.Count,
            titleblocks
        };
    }

    private static object ExecuteGetSheetInfo(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheetId = payload.GetProperty("sheet_id").GetInt32();

        var sheet = doc.GetElement(new ElementId((long)sheetId)) as ViewSheet;
        if (sheet == null)
            throw new ArgumentException($"Sheet with ID {sheetId} not found");

        var viewports = sheet.GetAllViewports()
            .Select(vpId => doc.GetElement(vpId) as Viewport)
            .Where(vp => vp != null)
            .Select(vp => new
            {
                viewport_id = vp.Id.Value,
                view_id = vp.ViewId.Value,
                view_name = doc.GetElement(vp.ViewId)?.Name
            })
            .ToList();

        var parameters = sheet.Parameters
            .Cast<Parameter>()
            .Where(p => p.HasValue)
            .Select(p => new
            {
                name = p.Definition.Name,
                value = GetParameterValueAsString(p)
            })
            .ToDictionary(p => p.name, p => p.value);

        return new
        {
            sheet_id = sheetId,
            sheet_number = sheet.SheetNumber,
            sheet_name = sheet.Name,
            is_placeholder = sheet.IsPlaceholder,
            viewport_count = viewports.Count,
            viewports,
            parameters
        };
    }

    private static object ExecuteDuplicateSheet(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sourceSheetId = payload.GetProperty("source_sheet_id").GetInt32();
        var newSheetNumber = payload.GetProperty("new_sheet_number").GetString();
        var newSheetName = payload.GetProperty("new_sheet_name").GetString();
        var duplicateViewports = payload.TryGetProperty("duplicate_viewports", out var dv)
            ? dv.GetBoolean()
            : false;

        using (var trans = new Transaction(doc, "Duplicate Sheet"))
        {
            trans.Start();

            var sourceSheet = doc.GetElement(new ElementId((long)sourceSheetId)) as ViewSheet;
            if (sourceSheet == null)
                throw new ArgumentException($"Source sheet with ID {sourceSheetId} not found");

            // Get titleblock from source sheet
            ViewSheet newSheet;
            if (sourceSheet.IsPlaceholder)
            {
                newSheet = ViewSheet.CreatePlaceholder(doc);
            }
            else
            {
                var titleblockId = new FilteredElementCollector(doc, sourceSheet.Id)
                    .OfCategory(BuiltInCategory.OST_TitleBlocks)
                    .WhereElementIsNotElementType()
                    .FirstOrDefault()
                    ?.GetTypeId();

                if (titleblockId == null)
                    throw new InvalidOperationException("Cannot find titleblock on source sheet");

                newSheet = ViewSheet.Create(doc, titleblockId);
            }

            newSheet.SheetNumber = newSheetNumber;
            newSheet.Name = newSheetName;

            // Copy parameters
            foreach (Parameter sourceParam in sourceSheet.Parameters)
            {
                if (!sourceParam.IsReadOnly && sourceParam.HasValue)
                {
                    var targetParam = newSheet.LookupParameter(sourceParam.Definition.Name);
                    if (targetParam != null && !targetParam.IsReadOnly)
                    {
                        try
                        {
                            switch (sourceParam.StorageType)
                            {
                                case StorageType.String:
                                    targetParam.Set(sourceParam.AsString());
                                    break;
                                case StorageType.Integer:
                                    targetParam.Set(sourceParam.AsInteger());
                                    break;
                                case StorageType.Double:
                                    targetParam.Set(sourceParam.AsDouble());
                                    break;
                            }
                        }
                        catch { /* Skip parameters that can't be copied */ }
                    }
                }
            }

            var viewportInfo = new List<object>();
            if (duplicateViewports)
            {
                // Note: This creates new viewports but doesn't duplicate the views themselves
                foreach (var vpId in sourceSheet.GetAllViewports())
                {
                    var sourceVp = doc.GetElement(vpId) as Viewport;
                    if (sourceVp != null)
                    {
                        viewportInfo.Add(new
                        {
                            note = "Viewport duplication requires view duplication - not implemented",
                            source_view_id = sourceVp.ViewId.Value
                        });
                    }
                }
            }

            trans.Commit();

            return new
            {
                new_sheet_id = newSheet.Id.Value,
                new_sheet_number = newSheet.SheetNumber,
                new_sheet_name = newSheet.Name,
                source_sheet_id = sourceSheetId,
                viewports_duplicated = viewportInfo.Count,
                viewport_info = viewportInfo,
                status = "success"
            };
        }
    }

    private static object ExecuteRenumberSheets(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var renumbering = payload.GetProperty("sheets").EnumerateArray()
            .Select(item => new
            {
                SheetId = item.GetProperty("sheet_id").GetInt32(),
                NewNumber = item.GetProperty("new_sheet_number").GetString()
            })
            .ToList();

        var results = new List<object>();
        var successCount = 0;
        var errorCount = 0;

        using (var trans = new Transaction(doc, "Renumber Sheets"))
        {
            trans.Start();

            foreach (var item in renumbering)
            {
                try
                {
                    var sheet = doc.GetElement(new ElementId((long)item.SheetId)) as ViewSheet;
                    if (sheet == null)
                    {
                        results.Add(new { sheet_id = item.SheetId, status = "error", message = "Sheet not found" });
                        errorCount++;
                        continue;
                    }

                    var oldNumber = sheet.SheetNumber;
                    sheet.SheetNumber = item.NewNumber;

                    results.Add(new
                    {
                        sheet_id = item.SheetId,
                        old_number = oldNumber,
                        new_number = sheet.SheetNumber,
                        sheet_name = sheet.Name,
                        status = "success"
                    });
                    successCount++;
                }
                catch (Exception ex)
                {
                    results.Add(new { sheet_id = item.SheetId, status = "error", message = ex.Message });
                    errorCount++;
                }
            }

            trans.Commit();
        }

        return new
        {
            total = renumbering.Count,
            success_count = successCount,
            error_count = errorCount,
            results
        };
    }

    // ==================== ADVANCED EXPORT TOOLS ====================

    private static object ExecuteExportDwgByView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var viewIds = payload.GetProperty("view_ids").EnumerateArray()
            .Select(e => new ElementId(e.GetInt64()))
            .ToList();
        var outputDirectory = payload.GetProperty("output_directory").GetString();
        var dwgVersion = payload.TryGetProperty("dwg_version", out var ver)
            ? ver.GetString()
            : "AutoCAD2018";

        if (!System.IO.Directory.Exists(outputDirectory))
            System.IO.Directory.CreateDirectory(outputDirectory);

        var exportedFiles = new List<object>();
        var dwgOptions = new DWGExportOptions
        {
            FileVersion = dwgVersion switch
            {
                "AutoCAD2018" => ACADVersion.R2018,
                "AutoCAD2013" => ACADVersion.R2013,
                "AutoCAD2010" => ACADVersion.R2010,
                _ => ACADVersion.R2018
            }
        };

        using (var trans = new Transaction(doc, "Export DWG"))
        {
            trans.Start();

            foreach (var viewId in viewIds)
            {
                var view = doc.GetElement(viewId) as View;
                if (view == null)
                {
                    exportedFiles.Add(new { view_id = viewId.Value, status = "error", message = "View not found" });
                    continue;
                }

                var fileName = SanitizeFileName(view.Name);
                var filePath = System.IO.Path.Combine(outputDirectory, $"{fileName}.dwg");

                try
                {
                    doc.Export(outputDirectory, fileName, new List<ElementId> { viewId }, dwgOptions);
                    exportedFiles.Add(new {
                        view_id = viewId.Value,
                        view_name = view.Name,
                        file_path = filePath,
                        status = "success"
                    });
                }
                catch (Exception ex)
                {
                    exportedFiles.Add(new {
                        view_id = viewId.Value,
                        view_name = view.Name,
                        status = "error",
                        message = ex.Message
                    });
                }
            }

            trans.Commit();
        }

        return new
        {
            exported_count = exportedFiles.Count(f => ((dynamic)f).status == "success"),
            error_count = exportedFiles.Count(f => ((dynamic)f).status == "error"),
            files = exportedFiles
        };
    }

    private static object ExecuteExportIfcWithSettings(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var outputPath = payload.GetProperty("output_path").GetString();
        var ifcVersion = payload.TryGetProperty("ifc_version", out var ver)
            ? ver.GetString()
            : "IFC2x3";
        var exportBaseQuantities = payload.TryGetProperty("export_base_quantities", out var ebq)
            ? ebq.GetBoolean()
            : true;

        var options = new IFCExportOptions
        {
            FileVersion = ifcVersion switch
            {
                "IFC4" => IFCVersion.IFC4,
                "IFC2x3" => IFCVersion.IFC2x3,
                "IFC2x2" => IFCVersion.IFC2x2,
                _ => IFCVersion.IFC2x3
            },
            ExportBaseQuantities = exportBaseQuantities,
            WallAndColumnSplitting = true,
            SpaceBoundaryLevel = 1
        };

        using (var trans = new Transaction(doc, "Export IFC"))
        {
            trans.Start();

            var result = doc.Export(
                System.IO.Path.GetDirectoryName(outputPath),
                System.IO.Path.GetFileNameWithoutExtension(outputPath),
                options
            );

            trans.Commit();

            return new
            {
                file_path = outputPath,
                ifc_version = ifcVersion,
                export_succeeded = result,
                file_size_bytes = System.IO.File.Exists(outputPath)
                    ? new System.IO.FileInfo(outputPath).Length
                    : (long?)null,
                status = result ? "success" : "error"
            };
        }
    }

    private static object ExecuteExportNavisworks(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var outputPath = payload.GetProperty("output_path").GetString();
        var viewId = payload.TryGetProperty("view_id", out var vId)
            ? new ElementId(vId.GetInt64())
            : doc.ActiveView.Id;
        var exportScope = payload.TryGetProperty("export_scope", out var scope)
            ? scope.GetString()
            : "EntireProject";

        var options = new NavisworksExportOptions
        {
            ExportScope = exportScope switch
            {
                "CurrentView" => NavisworksExportScope.View,
                "EntireProject" => NavisworksExportScope.Model,
                _ => NavisworksExportScope.Model
            },
            ExportLinks = true,
            ExportRoomAsAttribute = true,
            ExportRoomGeometry = true,
            ConvertElementProperties = true,
            Coordinates = NavisworksCoordinates.Shared
        };

        if (exportScope == "CurrentView")
        {
            options.ViewId = viewId;
        }

        using (var trans = new Transaction(doc, "Export Navisworks"))
        {
            trans.Start();

            var exportSucceeded = true;
            string exportError = null;

            try
            {
                doc.Export(
                    System.IO.Path.GetDirectoryName(outputPath),
                    System.IO.Path.GetFileNameWithoutExtension(outputPath),
                    options
                );
            }
            catch (Exception ex)
            {
                exportSucceeded = false;
                exportError = ex.Message;
            }

            trans.Commit();

            return new
            {
                file_path = outputPath,
                export_scope = exportScope,
                view_id = viewId.Value,
                export_succeeded = exportSucceeded,
                file_size_bytes = System.IO.File.Exists(outputPath)
                    ? new System.IO.FileInfo(outputPath).Length
                    : (long?)null,
                status = exportSucceeded ? "success" : "error",
                error = exportError
            };
        }
    }

    private static object ExecuteExportImage(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var viewId = payload.GetProperty("view_id").GetInt32();
        var outputPath = payload.GetProperty("output_path").GetString();
        var imageFormat = payload.TryGetProperty("format", out var fmt)
            ? fmt.GetString()
            : "PNG";
        var resolution = payload.TryGetProperty("resolution", out var res)
            ? res.GetInt32()
            : 150;

        var view = doc.GetElement(new ElementId((long)viewId)) as View;
        if (view == null)
            throw new ArgumentException($"View with ID {viewId} not found");

        var options = new ImageExportOptions
        {
            ZoomType = ZoomFitType.FitToPage,
            PixelSize = resolution,
            ImageResolution = ImageResolution.DPI_150,
            FilePath = System.IO.Path.GetDirectoryName(outputPath),
            FitDirection = FitDirectionType.Horizontal,
            HLRandWFViewsFileType = imageFormat switch
            {
                "PNG" => ImageFileType.PNG,
                "JPG" => ImageFileType.JPEGLossless,
                "JPEG" => ImageFileType.JPEGLossless,
                "BMP" => ImageFileType.BMP,
                "TIFF" => ImageFileType.TIFF,
                _ => ImageFileType.PNG
            },
            ExportRange = ExportRange.SetOfViews
        };

        options.SetViewsAndSheets(new List<ElementId> { view.Id });

        using (var trans = new Transaction(doc, "Export Image"))
        {
            trans.Start();

            doc.ExportImage(options);

            trans.Commit();

            var expectedFile = System.IO.Path.Combine(
                System.IO.Path.GetDirectoryName(outputPath),
                $"{SanitizeFileName(view.Name)}.{imageFormat.ToLower()}"
            );

            return new
            {
                view_id = viewId,
                view_name = view.Name,
                expected_file_path = expectedFile,
                format = imageFormat,
                resolution_dpi = resolution,
                file_exists = System.IO.File.Exists(expectedFile),
                status = "success"
            };
        }
    }

    private static object ExecuteRender3DView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var viewId = payload.GetProperty("view_id").GetInt32();
        var outputPath = payload.GetProperty("output_path").GetString();
        var renderQuality = payload.TryGetProperty("quality", out var qual)
            ? qual.GetString()
            : "Medium";
        var imageWidth = payload.TryGetProperty("width", out var w)
            ? w.GetInt32()
            : 1920;
        var imageHeight = payload.TryGetProperty("height", out var h)
            ? h.GetInt32()
            : 1080;

        var view = doc.GetElement(new ElementId((long)viewId)) as View3D;
        if (view == null)
            throw new ArgumentException($"3D View with ID {viewId} not found");

        var imageResolution = renderQuality switch
        {
            "Draft" => ImageResolution.DPI_72,
            "High" => ImageResolution.DPI_300,
            _ => ImageResolution.DPI_150
        };

        using (var trans = new Transaction(doc, "Render 3D View"))
        {
            trans.Start();

            var renderOptions = new ImageExportOptions
            {
                ZoomType = ZoomFitType.FitToPage,
                PixelSize = Math.Max(imageWidth, imageHeight),
                ImageResolution = imageResolution,
                FilePath = System.IO.Path.GetDirectoryName(outputPath),
                ExportRange = ExportRange.SetOfViews
            };

            renderOptions.SetViewsAndSheets(new List<ElementId> { view.Id });
            doc.ExportImage(renderOptions);

            trans.Commit();

            return new
            {
                view_id = viewId,
                view_name = view.Name,
                output_path = outputPath,
                quality = renderQuality,
                width = imageWidth,
                height = imageHeight,
                note = "Exported 3D view image via ImageExportOptions.",
                status = "success"
            };
        }
    }
}
