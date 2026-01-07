using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB.Structure;
using Autodesk.Revit.DB.Mechanical;
using Autodesk.Revit.DB.Plumbing;

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

            // Batch 2: Selection
            "revit.get_selection" => ExecuteGetSelection(app),
            "revit.set_selection" => ExecuteSetSelection(app, payload),

            // Batch 2: Annotation
            "revit.create_text_note" => ExecuteCreateTextNote(app, payload),
            "revit.create_dimension" => ExecuteCreateDimension(app, payload),
            "revit.create_tag" => ExecuteCreateTag(app, payload),

            // Batch 2: Structure
            "revit.create_column" => ExecuteCreateColumn(app, payload),
            "revit.create_beam" => ExecuteCreateBeam(app, payload),
            "revit.create_foundation" => ExecuteCreateFoundation(app, payload),

            // Batch 2: MEP
            "revit.create_duct" => ExecuteCreateDuct(app, payload),
            "revit.create_pipe" => ExecuteCreatePipe(app, payload),

            // Batch 2: General Helper
            "revit.get_categories" => ExecuteGetCategories(app),
            "revit.get_element_type" => ExecuteGetElementType(app, payload),

            // Batch 3: Editing
            "revit.move_element" => ExecuteMoveElement(app, payload),
            "revit.copy_element" => ExecuteCopyElement(app, payload),
            "revit.rotate_element" => ExecuteRotateElement(app, payload),
            "revit.mirror_element" => ExecuteMirrorElement(app, payload),
            "revit.pin_element" => ExecutePinElement(app, payload),
            "revit.unpin_element" => ExecuteUnpinElement(app, payload),

            // Batch 3: Worksharing
            "revit.sync_to_central" => ExecuteSyncToCentral(app, payload),
            "revit.relinquish_all" => ExecuteRelinquishAll(app),
            "revit.get_worksets" => ExecuteGetWorksets(app),

            // Batch 3: Schedules & Data
            "revit.create_schedule" => ExecuteCreateSchedule(app, payload),
            "revit.get_schedule_data" => ExecuteGetScheduleData(app, payload),
            "revit.get_element_bounding_box" => ExecuteGetElementBoundingBox(app, payload),

            // Batch 4: Phasing
            "revit.get_phases" => ExecuteGetPhases(app),
            "revit.get_phase_filters" => ExecuteGetPhaseFilters(app),

            // Batch 4: Design Options
            "revit.get_design_options" => ExecuteGetDesignOptions(app),

            // Batch 4: Groups
            "revit.create_group" => ExecuteCreateGroup(app, payload),
            "revit.ungroup" => ExecuteUngroup(app, payload),
            "revit.get_group_members" => ExecuteGetGroupMembers(app, payload),

            // Batch 4: Links
            "revit.get_rvt_links" => ExecuteGetRvtLinks(app),
            "revit.get_link_instances" => ExecuteGetLinkInstances(app),

            // Batch 5: Advanced MEP & Engineering
            // "revit.create_cable_tray" => ExecuteCreateCableTray(app, payload), // Temp disabled - API compat issue
            "revit.create_conduit" => ExecuteCreateConduit(app, payload),
            // "revit.get_mep_systems" => ExecuteGetMepSystems(app, payload), // Temp disabled - API compat issue
            "revit.check_clashes" => ExecuteCheckClashes(app, payload),

            // Batch 6: Materials & Visuals
            "revit.create_material" => ExecuteCreateMaterial(app, payload),
            "revit.set_element_material" => ExecuteSetElementMaterial(app, payload),
            // "revit.get_render_settings" => ExecuteGetRenderSettings(app), // Temp disabled - API compat issue

            // Batch 7: Family Management
            "revit.convert_to_group" => ExecuteConvertToGroup(app, payload),
            "revit.edit_family" => ExecuteEditFamily(app, payload),

            // Batch 8: High-Value Documentation (Reaching 100 Tools)
            // "revit.create_revision_cloud" => ExecuteCreateRevisionCloud(app, payload), // Temp disabled - API compat issue
            "revit.get_revision_sequences" => ExecuteGetRevisionSequences(app),
            "revit.tag_all_in_view" => ExecuteTagAllInView(app, payload),
            // "revit.create_text_type" => ExecuteCreateTextType(app, payload), // Temp disabled - API compat issue
            "revit.get_view_templates" => ExecuteGetViewTemplates(app),
            "revit.apply_view_template" => ExecuteApplyViewTemplate(app, payload),
            "revit.calculate_material_quantities" => ExecuteCalculateMaterialQuantities(app, payload),
            // "revit.get_room_boundary" => ExecuteGetRoomBoundary(app, payload), // Temp disabled - API compat issue
            // "revit.get_project_location" => ExecuteGetProjectLocation(app), // Temp disabled - API compat issue
            "revit.get_warnings" => ExecuteGetWarnings(app),

            // Universal Bridge - Reflection API (10,000+ methods accessible!)
            "revit.invoke_method" => ExecuteInvokeMethod(app, payload),
            "revit.reflect_get" => ExecuteReflectGet(app, payload),
            "revit.reflect_set" => ExecuteReflectSet(app, payload),

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
            "revit.render_3d_view",

            // Batch 2: Selection
            "revit.get_selection",
            "revit.set_selection",

            // Batch 2: Annotation
            "revit.create_text_note",
            "revit.create_dimension",
            "revit.create_tag",

            // Batch 2: Structure
            "revit.create_column",
            "revit.create_beam",
            "revit.create_foundation",

            // Batch 2: MEP
            "revit.create_duct",
            "revit.create_pipe",

            // Batch 2: General Helper
            "revit.get_categories",
            "revit.get_element_type",

            // Batch 3: Editing
            "revit.move_element",
            "revit.copy_element",
            "revit.rotate_element",
            "revit.mirror_element",
            "revit.pin_element",
            "revit.unpin_element",

            // Batch 3: Worksharing
            "revit.sync_to_central",
            "revit.relinquish_all",
            "revit.get_worksets",

            // Batch 3: Schedules & Data
            "revit.create_schedule",
            "revit.get_schedule_data",
            "revit.get_element_bounding_box",

            // Batch 4: Phasing
            "revit.get_phases",
            "revit.get_phase_filters",

            // Batch 4: Design Options
            "revit.get_design_options",

            // Batch 4: Groups
            "revit.create_group",
            "revit.ungroup",
            "revit.get_group_members",

            // Batch 4: Links
            "revit.get_rvt_links",
            "revit.get_link_instances",

            // Batch 5: Advanced MEP & Engineering
            "revit.create_cable_tray",
            "revit.create_conduit",
            "revit.get_mep_systems",
            "revit.check_clashes",

            // Batch 6: Materials & Visuals
            "revit.create_material",
            "revit.set_element_material",
            "revit.get_render_settings",

            // Batch 7: Family Management
            "revit.convert_to_group",
            "revit.edit_family",

            // Batch 8: High-Value Documentation
            "revit.create_dimension",
            "revit.create_revision_cloud",
            "revit.get_revision_sequences",
            "revit.tag_all_in_view",
            "revit.create_text_type",
            "revit.get_view_templates",
            "revit.apply_view_template",
            "revit.calculate_material_quantities",
            "revit.get_room_boundary",
            "revit.get_project_location",
            "revit.get_warnings",

            // Batch 9: Universal Reflection
            "revit.invoke_method",
            "revit.reflect_get",
            "revit.reflect_set"
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

    // ==================== BATCH 2: SELECTION & ANNOTATION IMPL ====================

    private static object ExecuteGetSelection(UIApplication app)
    {
        var uidoc = app.ActiveUIDocument;
        if (uidoc == null) throw new InvalidOperationException("No active UIDocument");

        var ids = uidoc.Selection.GetElementIds().Select(id => id.Value).ToList();
        return new { count = ids.Count, element_ids = ids };
    }

    private static object ExecuteSetSelection(UIApplication app, JsonElement payload)
    {
        var uidoc = app.ActiveUIDocument;
        if (uidoc == null) throw new InvalidOperationException("No active UIDocument");

        var ids = payload.GetProperty("element_ids").EnumerateArray()
            .Select(x => new ElementId((long)x.GetInt32()))
            .ToList();

        uidoc.Selection.SetElementIds(ids);
        return new { selected_count = ids.Count };
    }

    private static object ExecuteCreateTextNote(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var text = payload.GetProperty("text").GetString();
        var location = ParseXYZ(payload.GetProperty("location"));
        var viewId = payload.TryGetProperty("view_id", out var v) ? v.GetInt32() : doc.ActiveView.Id.Value;

        using (var trans = new Transaction(doc, "Create Text Note"))
        {
            trans.Start();
            var view = doc.GetElement(new ElementId((long)viewId)) as View;
            var note = TextNote.Create(doc, view.Id, location, text, new ElementId(BuiltInParameter.TEXT_SIZE)); // Using default type logic simplifiction
            trans.Commit();

            return new { text_note_id = note.Id.Value, text = note.Text, view_id = view.Id.Value };
        }
    }

    private static object ExecuteCreateTag(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt32();
        var location = ParseXYZ(payload.GetProperty("location"));
        var viewId = payload.TryGetProperty("view_id", out var v) ? v.GetInt32() : doc.ActiveView.Id.Value;

        using (var trans = new Transaction(doc, "Create Tag"))
        {
            trans.Start();
            var view = doc.GetElement(new ElementId((long)viewId)) as View;
            // IndependentTag.Create replaced NewTag in 2018+
            // For Revit 2024 it's Create
            var element = doc.GetElement(new ElementId((long)elementId));
            if (element == null) throw new ArgumentException($"Element {elementId} not found");
            var tag = IndependentTag.Create(doc, view.Id, new Reference(element), false, TagMode.TM_ADDBY_CATEGORY, TagOrientation.Horizontal, location);
            trans.Commit();
            return new { tag_id = tag.Id.Value, tagged_element_id = elementId };
        }
    }

    // ==================== BATCH 2: STRUCTURE IMPL ====================
    
    private static object ExecuteCreateColumn(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var location = ParseXYZ(payload.GetProperty("location"));
        var levelName = payload.GetProperty("level").GetString();
        var familyName = payload.GetProperty("family_name").GetString();
        var typeName = payload.GetProperty("type_name").GetString();

        using (var trans = new Transaction(doc, "Create Structural Column"))
        {
             trans.Start();
             var level = GetLevelByName(doc, levelName);
             var symbol = GetFamilySymbolByName(doc, familyName, typeName);
             if(!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }
             
             var instance = doc.Create.NewFamilyInstance(location, symbol, level, StructuralType.Column);
             trans.Commit();
             
             return new { column_id = instance.Id.Value, family = familyName, type = typeName };
        }
    }

    private static object ExecuteCreateBeam(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var start = ParseXYZ(payload.GetProperty("start_point"));
        var end = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var familyName = payload.GetProperty("family_name").GetString();
        var typeName = payload.GetProperty("type_name").GetString();

        using (var trans = new Transaction(doc, "Create Beam"))
        {
             trans.Start();
             var level = GetLevelByName(doc, levelName);
             var symbol = GetFamilySymbolByName(doc, familyName, typeName);
             if(!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }
             
             var line = Line.CreateBound(start, end);
             var instance = doc.Create.NewFamilyInstance(line, symbol, level, StructuralType.Beam);
             trans.Commit();
             
             return new { beam_id = instance.Id.Value, family = familyName, type = typeName, length = line.Length };
        }
    }

    private static object ExecuteCreateFoundation(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var location = ParseXYZ(payload.GetProperty("location"));
        var levelName = payload.GetProperty("level").GetString();
        var familyName = payload.GetProperty("family_name").GetString();
        var typeName = payload.GetProperty("type_name").GetString();

        using (var trans = new Transaction(doc, "Create Foundation"))
        {
             trans.Start();
             var level = GetLevelByName(doc, levelName);
             var symbol = GetFamilySymbolByName(doc, familyName, typeName);
             if(!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }
             
             var instance = doc.Create.NewFamilyInstance(location, symbol, level, StructuralType.Footing);
             trans.Commit();
             
             return new { foundation_id = instance.Id.Value, family = familyName, type = typeName };
        }
    }

    // ==================== BATCH 2: MEP IMPL ====================

    private static object ExecuteCreateDuct(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var start = ParseXYZ(payload.GetProperty("start_point"));
        var end = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var systemTypeName = payload.TryGetProperty("system_type", out var s) ? s.GetString() : "Supply Air";
        var ductTypeName = payload.TryGetProperty("duct_type", out var d) ? d.GetString() : null; // Default to first available

        using (var trans = new Transaction(doc, "Create Duct"))
        {
             trans.Start();
             var level = GetLevelByName(doc, levelName);
             
             // Get System Type
             var mechanicalSystemType = new FilteredElementCollector(doc)
                 .OfClass(typeof(MEPSystemType))
                 .Cast<MEPSystemType>()
                 .FirstOrDefault(x => x.Name.Contains(systemTypeName)) 
                 ?? throw new ArgumentException($"MEP System Type '{systemTypeName}' not found");

             // Get Duct Type
             var ductType = new FilteredElementCollector(doc)
                 .OfClass(typeof(DuctType))
                 .Cast<DuctType>()
                 .FirstOrDefault(x => ductTypeName == null || x.Name == ductTypeName); // First available if null
             
             if (ductType == null) throw new ArgumentException("No Duct Type found");

             var duct = Duct.Create(doc, mechanicalSystemType.Id, ductType.Id, level.Id, start, end);
             trans.Commit();
             
             return new { duct_id = duct.Id.Value, system_type = mechanicalSystemType.Name, duct_type = ductType.Name };
        }
    }

    private static object ExecuteCreatePipe(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var start = ParseXYZ(payload.GetProperty("start_point"));
        var end = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var systemTypeName = payload.TryGetProperty("system_type", out var s) ? s.GetString() : "Hydronic Supply";
        var pipeTypeName = payload.TryGetProperty("pipe_type", out var p) ? p.GetString() : null;

        using (var trans = new Transaction(doc, "Create Pipe"))
        {
             trans.Start();
             var level = GetLevelByName(doc, levelName);
             
             var pipingSystemType = new FilteredElementCollector(doc)
                 .OfClass(typeof(MEPSystemType))
                 .Cast<MEPSystemType>()
                 .FirstOrDefault(x => x.Name.Contains(systemTypeName))
                 ?? throw new ArgumentException($"Piping System Type '{systemTypeName}' not found");

             var pipeType = new FilteredElementCollector(doc)
                 .OfClass(typeof(PipeType))
                 .Cast<PipeType>()
                 .FirstOrDefault(x => pipeTypeName == null || x.Name == pipeTypeName);
             
             if (pipeType == null) throw new ArgumentException("No Pipe Type found");

             var pipe = Pipe.Create(doc, pipingSystemType.Id, pipeType.Id, level.Id, start, end);
             trans.Commit();
             
             return new { pipe_id = pipe.Id.Value, system_type = pipingSystemType.Name, pipe_type = pipeType.Name };
        }
    }

    // ==================== BATCH 2: GENERAL HELPER IMPL ====================

    private static object ExecuteGetCategories(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var categories = doc.Settings.Categories.Cast<Category>()
            .Where(c => c.CategoryType == CategoryType.Model && c.CanAddSubcategory) // Filter mainly model categories
            .Select(c => c.Name)
            .OrderBy(n => n)
            .ToList();
            
        return new { categories };
    }
    
    private static object ExecuteGetElementType(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var categoryName = payload.GetProperty("category_name").GetString();
        var familyName = payload.TryGetProperty("family_name", out var f) ? f.GetString() : null;
        
        var category = GetCategoryByName(doc, categoryName);
        var collector = new FilteredElementCollector(doc)
            .OfClass(typeof(ElementType))
            .OfCategoryId(category.Id);
            
        if (!string.IsNullOrEmpty(familyName))
        {
            // Filter by family name if provided
             var types = collector.Cast<ElementType>()
                .Where(x => x.FamilyName == familyName)
                .Select(x => new { family = x.FamilyName, type = x.Name, id = x.Id.Value })
                .ToList();
             return new { types };
        }
        else
        {
             var types = collector.Cast<ElementType>()
                .Select(x => new { family = x.FamilyName, type = x.Name, id = x.Id.Value })
                .ToList();
             return new { types };
        }
    }

    // ==================== BATCH 3: EDITING IMPL ====================

    private static object ExecuteMoveElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var vector = ParseXYZ(payload.GetProperty("vector"));

        using (var trans = new Transaction(doc, "Move Element"))
        {
            trans.Start();
            ElementTransformUtils.MoveElement(doc, elementId, vector);
            trans.Commit();
            return new { status = "success", moved_element_id = elementId.Value };
        }
    }

    private static object ExecuteCopyElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var vector = ParseXYZ(payload.GetProperty("vector"));

        using (var trans = new Transaction(doc, "Copy Element"))
        {
            trans.Start();
            var newIds = ElementTransformUtils.CopyElement(doc, elementId, vector);
            trans.Commit();
            return new { status = "success", original_id = elementId.Value, new_element_ids = newIds.Select(id => id.Value).ToList() };
        }
    }

    private static object ExecuteRotateElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var axisPoint = ParseXYZ(payload.GetProperty("axis_point"));
        var angleRadians = payload.GetProperty("angle_radians").GetDouble();

        using (var trans = new Transaction(doc, "Rotate Element"))
        {
            trans.Start();
            var axis = Line.CreateBound(axisPoint, axisPoint + XYZ.BasisZ); // Default to Z-axis rotation for now
            ElementTransformUtils.RotateElement(doc, elementId, axis, angleRadians);
            trans.Commit();
            return new { status = "success", element_id = elementId.Value, angle = angleRadians };
        }
    }

    private static object ExecuteMirrorElement(UIApplication app, JsonElement payload)
    {
        // Minimal implementation assuming mirroring around a detailed plane is complex to pass via JSON.
        // We will implement a simple "Mirror by selecting an existing planar element" (like a Grid or Wall) or just return not implemented for now to be safe?
        // Let's implement mirror by a plane defined by point and normal.
        
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var planeOrigin = ParseXYZ(payload.GetProperty("plane_origin"));
        var planeNormal = ParseXYZ(payload.GetProperty("plane_normal")); // e.g., (1,0,0) for YZ plane
        
        using (var trans = new Transaction(doc, "Mirror Element"))
        {
             trans.Start();
             var plane = Plane.CreateByNormalAndOrigin(planeNormal, planeOrigin);
             ElementTransformUtils.MirrorElement(doc, elementId, plane);
             trans.Commit();
             return new { status = "success", element_id = elementId.Value };
        }
    }
    
    private static object ExecutePinElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        
        using (var trans = new Transaction(doc, "Pin Element"))
        {
             trans.Start();
             var el = doc.GetElement(elementId);
             if(el != null) el.Pinned = true;
             trans.Commit();
             return new { status = "success", element_id = elementId.Value, pinned = true };
        }
    }

    private static object ExecuteUnpinElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        
        using (var trans = new Transaction(doc, "Unpin Element"))
        {
             trans.Start();
             var el = doc.GetElement(elementId);
             if(el != null) el.Pinned = false;
             trans.Commit();
             return new { status = "success", element_id = elementId.Value, pinned = false };
        }
    }

    // ==================== BATCH 3: WORKSHARING IMPL ====================
    
    private static object ExecuteSyncToCentral(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        if (!doc.IsWorkshared) return new { status = "ignored", message = "Document is not workshared" };
        
        var comment = payload.TryGetProperty("comment", out var c) ? c.GetString() : "Sync via MCP";
        var relinquish = payload.TryGetProperty("relinquish", out var r) ? r.GetBoolean() : true;
        
        var transOptions = new TransactWithCentralOptions();
        var syncOptions = new SynchronizeWithCentralOptions();
        syncOptions.Comment = comment;
        
        if (relinquish)
        {
             var ro = new RelinquishOptions(true);
             ro.CheckedOutElements = true;
             ro.StandardWorksets = true;
             ro.UserWorksets = true;
             ro.FamilyWorksets = true;
             ro.ViewWorksets = true;
             syncOptions.SetRelinquishOptions(ro);
        }

        doc.SynchronizeWithCentral(transOptions, syncOptions);
        
        return new { status = "success", message = "Synchronized to Central" };
    }

    private static object ExecuteRelinquishAll(UIApplication app)
    {
         var doc = app.ActiveUIDocument?.Document;
         if (doc == null) throw new InvalidOperationException("No active document");
         
         if (!doc.IsWorkshared) return new { status = "ignored", message = "Document is not workshared" };

         var transOptions = new TransactWithCentralOptions();
         var ro = new RelinquishOptions(true);
         WorksharingUtils.RelinquishOwnership(doc, ro, transOptions);
         
         return new { status = "success", message = "Relinquished all ownership" };
    }
    
    private static object ExecuteGetWorksets(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        if (!doc.IsWorkshared) return new { is_workshared = false, worksets = new List<object>() };

        var worksets = new FilteredWorksetCollector(doc)
            .OfKind(WorksetKind.UserWorkset)
            .Select(w => new { name = w.Name, id = w.Id.IntegerValue, is_open = w.IsOpen })
            .ToList();

        return new { is_workshared = true, worksets };
    }

    // ==================== BATCH 3: SCHEDULES & GEO IMPL ====================

    private static object ExecuteCreateSchedule(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var categoryName = payload.GetProperty("category_name").GetString();
        var name = payload.GetProperty("name").GetString();
        
        var category = GetCategoryByName(doc, categoryName);

        using (var trans = new Transaction(doc, "Create Schedule"))
        {
             trans.Start();
             var schedule = ViewSchedule.CreateSchedule(doc, category.Id);
             schedule.Name = name;
             trans.Commit();
             
             return new { schedule_id = schedule.Id.Value, name = schedule.Name };
        }
    }
    
    private static object ExecuteGetScheduleData(UIApplication app, JsonElement payload)
    {
        // Getting actual data rows from a ViewSchedule is surprisingly hard in the API (ViewSchedule.GetCellText is for header section mostly or specific calls).
        // Best simplified way is TableData, but that's for parsing the visual table.
        // A robust implementation would be: element collector of the schedule's category, formatted by schedule fields.
        // For simplified v1: Just return fields.
        
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var scheduleId = new ElementId((long)payload.GetProperty("schedule_id").GetInt32());
        var schedule = doc.GetElement(scheduleId) as ViewSchedule;
        if(schedule == null) throw new ArgumentException("Schedule not found");
        
        var fields = schedule.Definition.GetSchedulableFields()
             .Select(f => f.GetName(doc))
             .ToList();
             
        return new { schedule_name = schedule.Name, fields = fields, note = "Data extraction limited to fields list in this version." };
    }
    
    private static object ExecuteGetElementBoundingBox(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var element = doc.GetElement(elementId);
        if (element == null) throw new ArgumentException("Element not found");
        
        var bbox = element.get_BoundingBox(null); // active view
        if (bbox == null) return new { element_id = elementId.Value, has_bbox = false };
        
        return new { 
            element_id = elementId.Value,
            has_bbox = true,
            min = new { x = bbox.Min.X, y = bbox.Min.Y, z = bbox.Min.Z },
            max = new { x = bbox.Max.X, y = bbox.Max.Y, z = bbox.Max.Z }
        };
    }

    // ==================== BATCH 4: PHASING IMPL ====================
    
    private static object ExecuteGetPhases(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var phases = doc.Phases.Cast<Phase>()
            .OrderBy(p => p.Name)
            .Select(p => new { name = p.Name, id = p.Id.Value })
            .ToList();
            
        return new { phases };
    }

    private static object ExecuteGetPhaseFilters(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var filters = new FilteredElementCollector(doc)
            .OfClass(typeof(PhaseFilter))
            .Cast<PhaseFilter>()
            .OrderBy(f => f.Name)
            .Select(f => new { name = f.Name, id = f.Id.Value })
            .ToList();
            
        return new { phase_filters = filters };
    }

    // ==================== BATCH 4: DESIGN OPTIONS IMPL ====================

    private static object ExecuteGetDesignOptions(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var options = new FilteredElementCollector(doc)
            .OfClass(typeof(DesignOption))
            .Cast<DesignOption>()
            .Select(o => new { name = o.Name, id = o.Id.Value, set_id = o.get_Parameter(BuiltInParameter.OPTION_SET_ID).AsElementId().Value })
            .ToList();
            
        // Assuming DesignOptionSets are harder to get directly without looping options or specific collection
        // Actually DesignOptionSet is an element too
        
        return new { design_options = options };
    }

    // ==================== BATCH 4: GROUPS IMPL ====================

    private static object ExecuteCreateGroup(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementIds = payload.GetProperty("element_ids").EnumerateArray()
            .Select(x => new ElementId((long)x.GetInt32()))
            .ToList();
        var name = payload.TryGetProperty("name", out var n) ? n.GetString() : null;

        using (var trans = new Transaction(doc, "Create Group"))
        {
             trans.Start();
             var group = doc.Create.NewGroup(elementIds);
             if (!string.IsNullOrEmpty(name))
             {
                 group.GroupType.Name = name;
             }
             trans.Commit();
             
             return new { group_id = group.Id.Value, name = group.GroupType.Name };
        }
    }

    private static object ExecuteUngroup(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var groupId = new ElementId((long)payload.GetProperty("group_id").GetInt32());

        using (var trans = new Transaction(doc, "Ungroup"))
        {
             trans.Start();
             var group = doc.GetElement(groupId) as Group;
             if (group == null) throw new ArgumentException("Group not found");
             
             var memberIds = group.UngroupMembers().Select(id => id.Value).ToList();
             trans.Commit();
             
             return new { status = "success", ungrouped_count = memberIds.Count, member_ids = memberIds };
        }
    }

    private static object ExecuteGetGroupMembers(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var groupId = new ElementId((long)payload.GetProperty("group_id").GetInt32());
        var group = doc.GetElement(groupId) as Group;
        if (group == null) throw new ArgumentException("Group not found");
        
        var members = group.GetMemberIds().Select(id => id.Value).ToList();
        return new { group_id = groupId.Value, member_count = members.Count, member_ids = members };
    }

    // ==================== BATCH 4: LINKS IMPL ====================

    private static object ExecuteGetRvtLinks(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var links = new FilteredElementCollector(doc)
            .OfClass(typeof(RevitLinkType))
            .Cast<RevitLinkType>()
            .Select(l => new { 
                name = l.Name, 
                id = l.Id.Value, 
                is_loaded = (RevitLinkType.IsLoaded(doc, l.Id)), 
                is_nested = l.IsNestedLink,
                path = l.IsNestedLink ? "Nested" : (l.GetExternalFileReference()?.GetPath() != null ? ModelPathUtils.ConvertModelPathToUserVisiblePath(l.GetExternalFileReference().GetPath()) : "Unknown")
            })
            .ToList();

        return new { links };
    }

    private static object ExecuteGetLinkInstances(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var instances = new FilteredElementCollector(doc)
            .OfClass(typeof(RevitLinkInstance))
            .Cast<RevitLinkInstance>()
            .Select(i => new { 
                name = i.Name, 
                id = i.Id.Value, 
                type_id = i.GetTypeId().Value,
                link_name = (doc.GetElement(i.GetTypeId()) as RevitLinkType)?.Name 
            })
            .ToList();

        return new { instances };
    }

    // ==================== BATCH 5: ADVANCED MEP & ENGINEERING ====================

    private static object ExecuteCreateCableTray(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var width = payload.TryGetProperty("width", out var w) ? w.GetDouble() : 12.0 / 12.0; // Default 12 inches
        var height = payload.TryGetProperty("height", out var h) ? h.GetDouble() : 4.0 / 12.0; // Default 4 inches
        var cableTrayTypeName = payload.TryGetProperty("cable_tray_type", out var ct) ? ct.GetString() : null;

        using (var trans = new Transaction(doc, "Create Cable Tray"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            
            // Get cable tray type
            CableTrayType cableTrayType = null;
            if (!string.IsNullOrEmpty(cableTrayTypeName))
            {
                cableTrayType = new FilteredElementCollector(doc)
                    .OfClass(typeof(CableTrayType))
                    .Cast<CableTrayType>()
                    .FirstOrDefault(t => t.Name.Equals(cableTrayTypeName, StringComparison.OrdinalIgnoreCase));
            }
            
            if (cableTrayType == null)
            {
                cableTrayType = new FilteredElementCollector(doc)
                    .OfClass(typeof(CableTrayType))
                    .Cast<CableTrayType>()
                    .FirstOrDefault();
            }

            if (cableTrayType == null)
                throw new InvalidOperationException("No cable tray types found in document");

            // Create cable tray
            var cableTray = Autodesk.Revit.DB.Electrical.CableTray.Create(
                doc, 
                cableTrayType.Id, 
                startPoint, 
                endPoint, 
                level.Id
            );

            // Set width and height if parameters exist
            var widthParam = cableTray.get_Parameter(BuiltInParameter.RBS_CABLETRAY_WIDTH_PARAM);
            if (widthParam != null && !widthParam.IsReadOnly)
            {
                widthParam.Set(width);
            }

            var heightParam = cableTray.get_Parameter(BuiltInParameter.RBS_CABLETRAY_HEIGHT_PARAM);
            if (heightParam != null && !heightParam.IsReadOnly)
            {
                heightParam.Set(height);
            }

            trans.Commit();

            var length = startPoint.DistanceTo(endPoint);

            return new
            {
                cable_tray_id = cableTray.Id.Value,
                length_ft = length,
                length_m = UnitUtils.ConvertFromInternalUnits(length, UnitTypeId.Meters),
                width_ft = width,
                height_ft = height,
                level = levelName
            };
        }
    }

    private static object ExecuteCreateConduit(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var diameter = payload.TryGetProperty("diameter", out var d) ? d.GetDouble() : 0.75 / 12.0; // Default 0.75 inches
        var conduitTypeName = payload.TryGetProperty("conduit_type", out var ct) ? ct.GetString() : null;

        using (var trans = new Transaction(doc, "Create Conduit"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            
            // Get conduit type
            Autodesk.Revit.DB.Electrical.ConduitType conduitType = null;
            if (!string.IsNullOrEmpty(conduitTypeName))
            {
                conduitType = new FilteredElementCollector(doc)
                    .OfClass(typeof(Autodesk.Revit.DB.Electrical.ConduitType))
                    .Cast<Autodesk.Revit.DB.Electrical.ConduitType>()
                    .FirstOrDefault(t => t.Name.Equals(conduitTypeName, StringComparison.OrdinalIgnoreCase));
            }
            
            if (conduitType == null)
            {
                conduitType = new FilteredElementCollector(doc)
                    .OfClass(typeof(Autodesk.Revit.DB.Electrical.ConduitType))
                    .Cast<Autodesk.Revit.DB.Electrical.ConduitType>()
                    .FirstOrDefault();
            }

            if (conduitType == null)
                throw new InvalidOperationException("No conduit types found in document");

            // Create conduit
            var conduit = Autodesk.Revit.DB.Electrical.Conduit.Create(
                doc, 
                conduitType.Id, 
                startPoint, 
                endPoint, 
                level.Id
            );

            // Set diameter if parameter exists
            var diameterParam = conduit.get_Parameter(BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM);
            if (diameterParam != null && !diameterParam.IsReadOnly)
            {
                diameterParam.Set(diameter);
            }

            trans.Commit();

            var length = startPoint.DistanceTo(endPoint);

            return new
            {
                conduit_id = conduit.Id.Value,
                length_ft = length,
                length_m = UnitUtils.ConvertFromInternalUnits(length, UnitTypeId.Meters),
                diameter_ft = diameter,
                diameter_inches = diameter * 12.0,
                level = levelName
            };
        }
    }

    private static object ExecuteGetMepSystems(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var systemType = payload.TryGetProperty("system_type", out var st) ? st.GetString() : "all";

        var systems = new FilteredElementCollector(doc)
            .OfClass(typeof(MEPSystem))
            .Cast<MEPSystem>()
            .Where(s => systemType.Equals("all", StringComparison.OrdinalIgnoreCase) || 
                       s.GetType().Name.Contains(systemType, StringComparison.OrdinalIgnoreCase))
            .Select(s => new
            {
                id = s.Id.Value,
                name = s.Name,
                system_type = s.GetType().Name,
                is_well_connected = s.IsWellConnected,
                element_count = s.Elements.Size,
                base_equipment_id = s.BaseEquipment?.Id.Value ?? -1,
                base_equipment_name = s.BaseEquipment?.Name ?? "None"
            })
            .ToList();

        return new
        {
            systems,
            count = systems.Count,
            filter = systemType
        };
    }

    private static object ExecuteCheckClashes(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var category1Name = payload.GetProperty("category1").GetString();
        var category2Name = payload.GetProperty("category2").GetString();
        var tolerance = payload.TryGetProperty("tolerance", out var tol) ? tol.GetDouble() : 0.01; // Default 0.01 ft

        // Get built-in categories
        var cat1 = GetBuiltInCategoryByName(category1Name);
        var cat2 = GetBuiltInCategoryByName(category2Name);

        // Collect elements from both categories
        var elements1 = new FilteredElementCollector(doc)
            .OfCategory(cat1)
            .WhereElementIsNotElementType()
            .ToList();

        var elements2 = new FilteredElementCollector(doc)
            .OfCategory(cat2)
            .WhereElementIsNotElementType()
            .ToList();

        var clashes = new List<object>();

        // Check for clashes using bounding box intersection
        foreach (var elem1 in elements1)
        {
            var bb1 = elem1.get_BoundingBox(null);
            if (bb1 == null) continue;

            foreach (var elem2 in elements2)
            {
                if (elem1.Id == elem2.Id) continue;

                var bb2 = elem2.get_BoundingBox(null);
                if (bb2 == null) continue;

                // Expand bounding boxes by tolerance
                var expandedBB1 = new BoundingBoxXYZ
                {
                    Min = new XYZ(bb1.Min.X - tolerance, bb1.Min.Y - tolerance, bb1.Min.Z - tolerance),
                    Max = new XYZ(bb1.Max.X + tolerance, bb1.Max.Y + tolerance, bb1.Max.Z + tolerance)
                };

                // Check if bounding boxes intersect
                if (BoundingBoxesIntersect(expandedBB1, bb2))
                {
                    clashes.Add(new
                    {
                        element1_id = elem1.Id.Value,
                        element1_name = elem1.Name,
                        element1_category = elem1.Category?.Name,
                        element2_id = elem2.Id.Value,
                        element2_name = elem2.Name,
                        element2_category = elem2.Category?.Name,
                        clash_type = "bounding_box_intersection"
                    });
                }
            }
        }

        return new
        {
            clashes,
            clash_count = clashes.Count,
            category1 = category1Name,
            category2 = category2Name,
            tolerance_ft = tolerance,
            elements_checked_cat1 = elements1.Count,
            elements_checked_cat2 = elements2.Count
        };
    }

    // Helper method for bounding box intersection
    private static bool BoundingBoxesIntersect(BoundingBoxXYZ bb1, BoundingBoxXYZ bb2)
    {
        return !(bb1.Max.X < bb2.Min.X || bb1.Min.X > bb2.Max.X ||
                 bb1.Max.Y < bb2.Min.Y || bb1.Min.Y > bb2.Max.Y ||
                 bb1.Max.Z < bb2.Min.Z || bb1.Min.Z > bb2.Max.Z);
    }

    // Helper method to get BuiltInCategory by name
    private static BuiltInCategory GetBuiltInCategoryByName(string categoryName)
    {
        return categoryName.ToLower() switch
        {
            "walls" => BuiltInCategory.OST_Walls,
            "floors" => BuiltInCategory.OST_Floors,
            "roofs" => BuiltInCategory.OST_Roofs,
            "columns" => BuiltInCategory.OST_Columns,
            "beams" => BuiltInCategory.OST_StructuralFraming,
            "ducts" => BuiltInCategory.OST_DuctCurves,
            "pipes" => BuiltInCategory.OST_PipeCurves,
            "cable_trays" => BuiltInCategory.OST_CableTray,
            "conduits" => BuiltInCategory.OST_Conduit,
            "doors" => BuiltInCategory.OST_Doors,
            "windows" => BuiltInCategory.OST_Windows,
            "furniture" => BuiltInCategory.OST_Furniture,
            "mechanical_equipment" => BuiltInCategory.OST_MechanicalEquipment,
            "electrical_equipment" => BuiltInCategory.OST_ElectricalEquipment,
            "plumbing_fixtures" => BuiltInCategory.OST_PlumbingFixtures,
            _ => throw new ArgumentException($"Unknown category: {categoryName}")
        };
    }

    // ==================== BATCH 6: MATERIALS & VISUALS ====================

    private static object ExecuteCreateMaterial(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var name = payload.GetProperty("name").GetString();
        var color = payload.TryGetProperty("color", out var c) ? ParseColor(c) : new Color(128, 128, 128);
        var transparency = payload.TryGetProperty("transparency", out var t) ? t.GetInt32() : 0;
        var shininess = payload.TryGetProperty("shininess", out var s) ? s.GetInt32() : 50;
        var smoothness = payload.TryGetProperty("smoothness", out var sm) ? sm.GetInt32() : 50;

        using (var trans = new Transaction(doc, "Create Material"))
        {
            trans.Start();

            // Create material
            var materialId = Material.Create(doc, name);
            var material = doc.GetElement(materialId) as Material;

            if (material == null)
                throw new InvalidOperationException("Failed to create material");

            // Set appearance properties
            material.Color = color;
            material.Transparency = transparency;
            material.Shininess = shininess;
            material.Smoothness = smoothness;

            trans.Commit();

            return new
            {
                material_id = material.Id.Value,
                name = material.Name,
                color = new { r = color.Red, g = color.Green, b = color.Blue },
                transparency,
                shininess,
                smoothness
            };
        }
    }

    private static object ExecuteSetElementMaterial(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var materialName = payload.GetProperty("material_name").GetString();
        var faceIndex = payload.TryGetProperty("face_index", out var fi) ? (int?)fi.GetInt32() : null;

        using (var trans = new Transaction(doc, "Set Element Material"))
        {
            trans.Start();

            var element = doc.GetElement(elementId);
            if (element == null)
                throw new ArgumentException($"Element not found: {elementId}");

            // Find material by name
            var material = new FilteredElementCollector(doc)
                .OfClass(typeof(Material))
                .Cast<Material>()
                .FirstOrDefault(m => m.Name.Equals(materialName, StringComparison.OrdinalIgnoreCase));

            if (material == null)
                throw new ArgumentException($"Material not found: {materialName}");

            // Set material
            if (faceIndex.HasValue)
            {
                // Set material on specific face (for walls, floors, etc.)
                var geometryElement = element.get_Geometry(new Options());
                if (geometryElement != null)
                {
                    int currentIndex = 0;
                    foreach (GeometryObject geomObj in geometryElement)
                    {
                        if (geomObj is Solid solid)
                        {
                            foreach (Face face in solid.Faces)
                            {
                                if (currentIndex == faceIndex.Value)
                                {
                                    doc.Paint(elementId, face, material.Id);
                                    trans.Commit();
                                    return new
                                    {
                                        element_id = elementId.Value,
                                        material_id = material.Id.Value,
                                        material_name = material.Name,
                                        face_index = faceIndex.Value,
                                        method = "face_paint"
                                    };
                                }
                                currentIndex++;
                            }
                        }
                    }
                    throw new ArgumentException($"Face index {faceIndex} not found");
                }
            }
            else
            {
                // Set material on entire element
                var param = element.get_Parameter(BuiltInParameter.MATERIAL_ID_PARAM);
                if (param != null && !param.IsReadOnly)
                {
                    param.Set(material.Id);
                }
                else
                {
                    // Try structural material parameter
                    param = element.get_Parameter(BuiltInParameter.STRUCTURAL_MATERIAL_PARAM);
                    if (param != null && !param.IsReadOnly)
                    {
                        param.Set(material.Id);
                    }
                    else
                    {
                        throw new InvalidOperationException("Element does not have a settable material parameter");
                    }
                }
            }

            trans.Commit();

            return new
            {
                element_id = elementId.Value,
                material_id = material.Id.Value,
                material_name = material.Name,
                method = "parameter"
            };
        }
    }

    private static object ExecuteGetRenderSettings(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        // Get render settings
        var renderSettings = RenderingSettings.GetRenderingSettings(doc);
        
        if (renderSettings == null)
        {
            return new
            {
                status = "no_settings",
                message = "No rendering settings found in document"
            };
        }

        // Get quality settings
        var qualityParam = renderSettings.get_Parameter(BuiltInParameter.RENDER_QUALITY_SETTING);
        var resolutionParam = renderSettings.get_Parameter(BuiltInParameter.RENDER_RESOLUTION_SETTING);
        var exposureParam = renderSettings.get_Parameter(BuiltInParameter.RENDER_EXPOSURE_SETTING);
        var backgroundStyleParam = renderSettings.get_Parameter(BuiltInParameter.RENDER_BACKGROUND_STYLE);

        return new
        {
            quality = qualityParam?.AsValueString() ?? "Unknown",
            resolution = resolutionParam?.AsValueString() ?? "Unknown",
            exposure = exposureParam?.AsDouble() ?? 0.0,
            background_style = backgroundStyleParam?.AsValueString() ?? "Unknown",
            settings_id = renderSettings.Id.Value
        };
    }

    // Helper method to parse color from JSON
    private static Color ParseColor(JsonElement colorElement)
    {
        if (colorElement.ValueKind == JsonValueKind.Object)
        {
            var r = (byte)colorElement.GetProperty("r").GetInt32();
            var g = (byte)colorElement.GetProperty("g").GetInt32();
            var b = (byte)colorElement.GetProperty("b").GetInt32();
            return new Color(r, g, b);
        }
        else if (colorElement.ValueKind == JsonValueKind.String)
        {
            // Parse hex color like "#FF0000"
            var hex = colorElement.GetString();
            if (hex.StartsWith("#"))
            {
                hex = hex.Substring(1);
            }
            var r = Convert.ToByte(hex.Substring(0, 2), 16);
            var g = Convert.ToByte(hex.Substring(2, 2), 16);
            var b = Convert.ToByte(hex.Substring(4, 2), 16);
            return new Color(r, g, b);
        }
        return new Color(128, 128, 128); // Default gray
    }

    // ==================== BATCH 7: FAMILY MANAGEMENT ====================

    private static object ExecuteConvertToGroup(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        JsonElement idsElement;
        if (!payload.TryGetProperty("element_ids", out idsElement))
            throw new ArgumentException("element_ids is required");

        var elementIds = new List<ElementId>();
        foreach (var id in idsElement.EnumerateArray())
        {
            elementIds.Add(new ElementId((long)id.GetInt32()));
        }

        if (elementIds.Count == 0)
            throw new ArgumentException("element_ids list cannot be empty");

        var name = payload.TryGetProperty("name", out var n) ? n.GetString() : null;

        using (var trans = new Transaction(doc, "Create Group"))
        {
            trans.Start();

            var group = doc.Create.NewGroup(elementIds);
            
            if (!string.IsNullOrEmpty(name))
            {
                // Uniqueness check handled by Revit usually, but good practice to handle errors
                try {
                    group.GroupType.Name = name;
                } catch {
                    // Ignore name conflict if auto-naming is acceptable, or handle specifically
                }
            }

            trans.Commit();

            return new
            {
                group_id = group.Id.Value,
                group_name = group.Name,
                group_type_name = group.GroupType.Name,
                member_count = elementIds.Count
            };
        }
    }

    private static object ExecuteEditFamily(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        // This is a special command - it might change the Active Document context
        // This generally works best in the UI context, but for API automation, we open the family document.

        var familyName = payload.TryGetProperty("family_name", out var fn) ? fn.GetString() : null;
        var familySymbolId = payload.TryGetProperty("family_symbol_id", out var fsid) ? (int?)fsid.GetInt32() : null;
        var familyInstanceId = payload.TryGetProperty("family_instance_id", out var fiid) ? (int?)fiid.GetInt32() : null;

        Family family = null;

        if (familyInstanceId.HasValue)
        {
            var instance = doc.GetElement(new ElementId((long)familyInstanceId.Value)) as FamilyInstance;
            family = instance?.Symbol.Family;
        }
        else if (familySymbolId.HasValue)
        {
            var symbol = doc.GetElement(new ElementId((long)familySymbolId.Value)) as FamilySymbol;
            family = symbol?.Family;
        }
        else if (!string.IsNullOrEmpty(familyName))
        {
            family = new FilteredElementCollector(doc)
                .OfClass(typeof(Family))
                .Cast<Family>()
                .FirstOrDefault(f => f.Name.Equals(familyName, StringComparison.OrdinalIgnoreCase));
        }

        if (family == null)
            throw new ArgumentException("Could not identify family to edit from provided arguments");

        if (!family.IsEditable)
            throw new InvalidOperationException($"Family '{family.Name}' is not editable");

        // Open the family document
        var familyDoc = doc.EditFamily(family);
        
        // In a real UI workflow, this would switch the view. In API context, it returns the document.
        // We can't easily "switch" the user's view via pure API without some hacks, 
        // but we can make it the active document if using the OpenAndActivateDocument method (UIApp).
        // For now, we return info that it was opened, but the user might need to manually switch or we can try to activate it.

        // Attempt to activate (only works if no other command is running, tricky in nested context)
        // app.OpenAndActivateDocument(familyDoc.PathName); // PathName might be empty for in-memory edit

        return new
        {
            status = "family_document_opened",
            family_name = family.Name,
            family_document_title = familyDoc.Title,
            is_family_document = familyDoc.IsFamilyDocument,
            categories = new FilteredElementCollector(familyDoc).OfClass(typeof(Category)).Cast<Category>().Select(c => c.Name).Take(10).ToList()
        };
    }

    // ==================== BATCH 8: HIGH-VALUE DOCUMENTATION & ANALYSIS ====================

    private static object ExecuteCreateDimension(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var lineStart = ParseXYZ(payload.GetProperty("start_point"));
        var lineEnd = ParseXYZ(payload.GetProperty("end_point"));
        var view = doc.ActiveView;

        // Try to get references (very simplified - normally needs specific element references)
        var ref1Id = new ElementId((long)payload.GetProperty("element1_id").GetInt32());
        var ref2Id = new ElementId((long)payload.GetProperty("element2_id").GetInt32());
        
        using (var trans = new Transaction(doc, "Create Dimension"))
        {
            trans.Start();

            var elem1 = doc.GetElement(ref1Id);
            var elem2 = doc.GetElement(ref2Id);
            
            Reference ref1 = null;
            Reference ref2 = null;

            if (elem1 is Grid g1) ref1 = new Reference(g1);
            if (elem2 is Grid g2) ref2 = new Reference(g2);
            
            if (ref1 == null) ref1 = new Reference(elem1);
            if (ref2 == null) ref2 = new Reference(elem2);

            var line = Autodesk.Revit.DB.Line.CreateBound(lineStart, lineEnd);
            var refArray = new ReferenceArray();
            refArray.Append(ref1);
            refArray.Append(ref2);

            var dim = doc.Create.NewDimension(view, line, refArray);
            
            trans.Commit();

            return new { dimension_id = dim.Id.Value, value_ft = dim.Value, value_string = dim.ValueString };
        }
    }

    private static object ExecuteCreateRevisionCloud(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var viewId = new ElementId((long)payload.GetProperty("view_id").GetInt32());
        var pointsElement = payload.GetProperty("points");
        var revisionId = payload.TryGetProperty("revision_id", out var rid) ? new ElementId((long)rid.GetInt32()) : ElementId.InvalidElementId;

        // Parse points
        var points = new List<XYZ>();
        foreach (var p in pointsElement.EnumerateArray())
        {
            points.Add(ParseXYZ(p));
        }

        using (var trans = new Transaction(doc, "Create Revision Cloud"))
        {
            trans.Start();

            // Create curves from points (closed loop)
            var curves = new List<Curve>();
            for (int i = 0; i < points.Count; i++)
            {
                var p1 = points[i];
                var p2 = points[(i + 1) % points.Count];
                curves.Add(Autodesk.Revit.DB.Line.CreateBound(p1, p2));
            }

            RevisionCloud cloud;
            if (revisionId != ElementId.InvalidElementId)
            {
                cloud = RevisionCloud.Create(doc, viewId, revisionId, curves);
            }
            else
            {
                // Use default revision
                cloud = RevisionCloud.Create(doc, viewId, curves);
            }

            trans.Commit();

            return new { cloud_id = cloud.Id.Value, revision_id = cloud.RevisionId.Value, view_id = viewId.Value };
        }
    }

    private static object ExecuteGetRevisionSequences(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var revisions = new FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_Revisions)
            .Select(e => new 
            { 
                id = e.Id.Value, 
                name = e.Name, 
                date = e.get_Parameter(BuiltInParameter.PROJECT_REVISION_REVISION_DATE)?.AsString(),
                description = e.get_Parameter(BuiltInParameter.PROJECT_REVISION_REVISION_DESCRIPTION)?.AsString(),
                sequence = e.get_Parameter(BuiltInParameter.PROJECT_REVISION_SEQUENCE_NUM)?.AsInteger() ?? 0,
                issued = e.get_Parameter(BuiltInParameter.PROJECT_REVISION_ISSUED)?.AsInteger() == 1
            })
            .OrderBy(x => x.sequence)
            .ToList();

        return new { revisions, count = revisions.Count };
    }

    private static object ExecuteTagAllInView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var categoryName = payload.GetProperty("category").GetString();
        var category = GetBuiltInCategoryByName(categoryName);
        var view = doc.ActiveView;

        using (var trans = new Transaction(doc, "Tag All Not Tagged"))
        {
            trans.Start();

            // Collect untagged elements in view
            var elementsInView = new FilteredElementCollector(doc, view.Id)
                .OfCategory(category)
                .WhereElementIsNotElementType()
                .ToElementIds();

            int taggedCount = 0;
            
            foreach (var elemId in elementsInView)
            {
                var elem = doc.GetElement(elemId);
                XYZ loc = null;
                if (elem.Location is LocationPoint lp) loc = lp.Point;
                else if (elem.Location is LocationCurve lc) loc = lc.Curve.Evaluate(0.5, true);
                
                if (loc != null)
                {
                    try {
                        IndependentTag.Create(doc, view.Id, new Reference(elem), false, TagMode.TM_ADDBY_CATEGORY, TagOrientation.Horizontal, loc);
                        taggedCount++;
                    } catch { /* Tag family might be missing */ }
                }
            }

            trans.Commit();
            return new { tagged_count = taggedCount, view_name = view.Name, category = categoryName };
        }
    }

    private static object ExecuteCreateTextType(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var name = payload.GetProperty("name").GetString();
        var font = payload.TryGetProperty("font", out var f) ? f.GetString() : "Arial";
        var size = payload.TryGetProperty("size_inches", out var s) ? s.GetDouble() : 3.0 / 32.0;

        using (var trans = new Transaction(doc, "Create Text Type"))
        {
            trans.Start();

            var existingType = new FilteredElementCollector(doc)
                .OfClass(typeof(TextNoteType))
                .Cast<TextNoteType>()
                .FirstOrDefault();

            if (existingType == null) throw new InvalidOperationException("No default text type found");

            var newType = existingType.Duplicate(name) as TextNoteType;
            newType.get_Parameter(BuiltInParameter.TEXT_FONT_TYPE_NAME).Set(font);
            newType.get_Parameter(BuiltInParameter.TEXT_SIZE).Set(size / 12.0); // Convert inches to feet

            trans.Commit();
            return new { name = newType.Name, id = newType.Id.Value, font = font, size_inches = size };
        }
    }

    private static object ExecuteGetViewTemplates(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var templates = new FilteredElementCollector(doc)
            .OfClass(typeof(View))
            .Cast<View>()
            .Where(v => v.IsTemplate)
            .Select(v => new { id = v.Id.Value, name = v.Name, view_type = v.ViewType.ToString() })
            .ToList();

        return new { templates, count = templates.Count };
    }

    private static object ExecuteApplyViewTemplate(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var viewId = new ElementId((long)payload.GetProperty("view_id").GetInt32());
        var templateId = new ElementId((long)payload.GetProperty("template_id").GetInt32());

        using (var trans = new Transaction(doc, "Apply View Template"))
        {
            trans.Start();

            var view = doc.GetElement(viewId) as View;
            var template = doc.GetElement(templateId) as View;

            if (view == null) throw new ArgumentException("View not found");
            if (template == null || !template.IsTemplate) throw new ArgumentException("Template not found or not a template");

            view.ViewTemplateId = templateId;
            trans.Commit();

            return new { view_id = viewId.Value, template_name = template.Name, status = "applied" };
        }
    }

    private static object ExecuteCalculateMaterialQuantities(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var categoryName = payload.GetProperty("category").GetString();
        var cat = GetBuiltInCategoryByName(categoryName);

        var elements = new FilteredElementCollector(doc)
            .OfCategory(cat)
            .WhereElementIsNotElementType()
            .ToList();

        var quantities = new Dictionary<string, double>(); // Material Name -> Volume (CF)

        foreach (var elem in elements)
        {
            foreach (ElementId matId in elem.GetMaterialIds(false))
            {
                var material = doc.GetElement(matId) as Material;
                if (material == null) continue;

                double volume = elem.GetMaterialVolume(matId);
                if (quantities.ContainsKey(material.Name))
                    quantities[material.Name] += volume;
                else
                    quantities[material.Name] = volume;
            }
        }
        
        // Convert to list for JSON
        var result = quantities.Select(q => new 
        { 
            material = q.Key, 
            volume_cf = q.Value, 
            volume_cy = q.Value / 27.0 // cubic yards
        }).ToList();

        return new { category = categoryName, totals = result, element_count = elements.Count };
    }

    private static object ExecuteGetRoomBoundary(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var roomId = new ElementId((long)payload.GetProperty("room_id").GetInt32());
        var room = doc.GetElement(roomId) as Room;
        if (room == null) throw new ArgumentException("Room not found");

        var options = new SpatialElementBoundaryOptions();
        var boundaries = room.GetBoundarySegments(options);
        
        var loops = new List<object>();

        foreach (var segmentList in boundaries)
        {
            var points = new List<object>();
            foreach (var segment in segmentList)
            {
                var curve = segment.GetCurve();
                var p = curve.GetEndPoint(0);
                points.Add(new { x = p.X, y = p.Y, z = p.Z });
            }
            loops.Add(points);
        }

        return new 
        { 
            room_name = room.Name, 
            room_number = room.Number, 
            area_sf = room.Area, 
            perimeter_ft = room.Perimeter,
            boundary_loops = loops 
        };
    }

    private static object ExecuteGetProjectLocation(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var loc = doc.ActiveProjectLocation;
        
        // Get Project Base Point & Survey Point (Tricky in API, usually finding by Category works)
        var basePoint = new FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_ProjectBasePoint)
            .FirstOrDefault();
            
        var surveyPoint = new FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_SharedBasePoint)
            .FirstOrDefault();

        // Safe parameter access helpers
        Func<Element, string, double> getParam = (e, name) => 
        {
            var p = e?.LookupParameter(name);
            return p?.AsDouble() ?? 0.0;
        };

        return new 
        {
            project_name = loc.Name,
            site_name = loc.SiteName,
            project_base_point = new 
            {
                n_s = getParam(basePoint, "N/S"),
                e_w = getParam(basePoint, "E/W"),
                elev = getParam(basePoint, "Elev"),
                angle_to_north = getParam(basePoint, "Angle to True North")
            },
            survey_point = new
            {
                n_s = getParam(surveyPoint, "N/S"),
                e_w = getParam(surveyPoint, "E/W"),
                elev = getParam(surveyPoint, "Elev")
            }
        };
    }

    private static object ExecuteGetWarnings(UIApplication app)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var warnings = doc.GetWarnings();
        var result = warnings.Select(w => new
        {
            description = w.GetDescriptionText(),
            severity = w.GetSeverity().ToString(),
            failing_elements = w.GetFailingElements().Select(id => id.Value).ToList()
        }).ToList();

        return new { warnings = result, count = warnings.Count };
    }

    // ==================== BATCH 9: UNIVERSAL REFLECTION BRIDGE ====================

    private static object ExecuteInvokeMethod(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        string className = payload.GetProperty("class_name").GetString();
        string methodName = payload.GetProperty("method_name").GetString();
        JsonElement args = payload.GetProperty("arguments");
        string targetId = payload.TryGetProperty("target_id", out var t) ? t.GetString() : null;

        using (var trans = new Transaction(doc, $"Invoke {methodName}"))
        {
            if (payload.TryGetProperty("use_transaction", out var ut) && ut.GetBoolean())
                trans.Start();
            
            try
            {
                object result = ReflectionHelper.InvokeMethod(doc, className, methodName, args, targetId);
                
                if (trans.GetStatus() == TransactionStatus.Started)
                    trans.Commit();
                    
                return result ?? new { status = "void" };
            }
            catch (Exception ex)
            {
                if (trans.GetStatus() == TransactionStatus.Started)
                    trans.RollBack();
                throw new Exception($"Invocation failed: {ex.Message}", ex);
            }
        }
    }

    private static object ExecuteReflectGet(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        string targetId = payload.GetProperty("target_id").GetString();
        string propertyName = payload.GetProperty("property_name").GetString();

        object target = ReflectionHelper.GetObject(targetId, doc);
        if (target == null) throw new Exception($"Target '{targetId}' not found");

        var prop = target.GetType().GetProperty(propertyName);
        if (prop == null) throw new Exception($"Property '{propertyName}' not found on type '{target.GetType().Name}'");

        object value = prop.GetValue(target);
        
        if (value == null) return null;
        if (value.GetType().IsPrimitive || value is string || value is double || value is int || value is bool) return value;
        if (value is ElementId eid) return eid.Value;
        if (value is Element e) return e.Id.Value;

        string refId = ReflectionHelper.RegisterObject(value);
        return new { type = "reference", id = refId, class_name = value.GetType().Name, str = value.ToString() };
    }

    private static object ExecuteReflectSet(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        string targetId = payload.GetProperty("target_id").GetString();
        string propertyName = payload.GetProperty("property_name").GetString();
        JsonElement valueElement = payload.GetProperty("value");

        using (var trans = new Transaction(doc, $"Set {propertyName}"))
        {
            trans.Start();
            object target = ReflectionHelper.GetObject(targetId, doc);
            if (target == null) throw new Exception($"Target '{targetId}' not found");

            var prop = target.GetType().GetProperty(propertyName);
            if (prop == null) throw new Exception($"Property '{propertyName}' not found on type '{target.GetType().Name}'");

            object value = ReflectionHelper.ParseArgument(valueElement, doc);
            
            // Convert type if needed
            if (value != null && !prop.PropertyType.IsAssignableFrom(value.GetType()))
            {
                 value = Convert.ChangeType(value, prop.PropertyType);
            }

            prop.SetValue(target, value);
            trans.Commit();
        }

        return new { status = "success", target_id = targetId, property = propertyName };
    }
}
