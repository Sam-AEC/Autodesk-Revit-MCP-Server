using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB.Structure;
using Autodesk.Revit.DB.Mechanical;
using Autodesk.Revit.DB.Plumbing;
using IronPython.Hosting;
using Microsoft.Scripting.Hosting;

namespace RevitBridge.Bridge;

public static partial class BridgeCommandFactory
{
    private static readonly Dictionary<string, Func<UIApplication, JsonElement, object>> _handlers = new();
    private static readonly List<object> _capabilities = new();
    private static readonly List<string> _catalog = new();

    [ThreadStatic]
    private static string? _currentActionId;

    [ThreadStatic]
    private static List<BridgeFailureMessage>? _currentTransactionMessages;

    public static string? CurrentActionId
    {
        get => _currentActionId;
        set => _currentActionId = value;
    }

    public static BridgeTransaction CreateTransaction(Document doc, string name)
    {
        var actionId = CurrentActionId;
        string txName = string.IsNullOrEmpty(actionId) ? $"AMB: {name}" : $"AMB: {name} #{actionId}";
        return new BridgeTransaction(doc, txName, messages => _currentTransactionMessages?.AddRange(messages));
    }

    static BridgeCommandFactory()
    {
        var methods = typeof(BridgeCommandFactory).GetMethods(System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
        foreach (var method in methods)
        {
            var attr = (BridgeCommandAttribute)Attribute.GetCustomAttribute(method, typeof(BridgeCommandAttribute));
            if (attr != null)
            {
                var func = CreateHandlerDelegate(method);
                _handlers[attr.Name] = func;
                _catalog.Add(attr.Name);

                _capabilities.Add(new
                {
                    name = attr.Name,
                    is_mutating = attr.IsMutating,
                    confirmation_required = attr.ConfirmationRequired
                });
            }
        }
    }

    private static Func<UIApplication, JsonElement, object> CreateHandlerDelegate(System.Reflection.MethodInfo method)
    {
        var parameters = method.GetParameters();
        if (parameters.Length == 1)
        {
            return (app, payload) => method.Invoke(null, new object[] { app });
        }
        else if (parameters.Length == 2)
        {
            return (app, payload) => method.Invoke(null, new object[] { app, payload });
        }
        throw new InvalidOperationException($"Method {method.Name} has invalid parameters.");
    }

    public static object Execute(UIApplication app, string tool, JsonElement payload)
    {
        if (_handlers.TryGetValue(tool, out var handler))
        {
            try
            {
                _currentTransactionMessages = new List<BridgeFailureMessage>();
                if (payload.ValueKind == JsonValueKind.Object && payload.TryGetProperty("action_id", out var actionProp))
                {
                    CurrentActionId = actionProp.GetString();
                }
                else
                {
                    CurrentActionId = null;
                }

                var result = handler(app, payload);
                return BridgeTransactionResults.AppendWarnings(result, _currentTransactionMessages);
            }
            catch (System.Reflection.TargetInvocationException ex)
            {
                throw ex.InnerException ?? ex;
            }
            finally
            {
                CurrentActionId = null;
                _currentTransactionMessages = null;
            }
        }
        return new { status = "error", message = $"Unknown tool: {tool}" };
    }

    public static List<string> GetToolCatalog()
    {
        return _catalog;
    }

    public static object GetCapabilities()
    {
        return _capabilities;
    }

    // ==================== EXISTING TOOLS ====================

    [BridgeCommand("revit.health", IsMutating = false)]
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

    [BridgeCommand("revit.open_document", IsMutating = true)]
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

    [BridgeCommand("revit.list_views", IsMutating = false)]
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

    [BridgeCommand("revit.export_schedules", IsMutating = false)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Export Schedules"))
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

            trans.CommitChecked();
        }

        return new { schedules = exported, count = exported.Count };
    }

    [BridgeCommand("revit.export_pdf_by_sheet_set", IsMutating = false)]
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

    [BridgeCommand("revit.save_document", IsMutating = true)]
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

    [BridgeCommand("revit.close_document", IsMutating = true)]
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

    [BridgeCommand("revit.create_new_document", IsMutating = true)]
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

    [BridgeCommand("revit.get_document_info", IsMutating = false)]
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

    [BridgeCommand("revit.list_levels", IsMutating = false)]
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

    [BridgeCommand("revit.create_wall", IsMutating = true)]
    private static object ExecuteCreateWall(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var height = payload.GetProperty("height").GetDouble();
        var levelName = payload.GetProperty("level").GetString();
        var wallTypeName = payload.TryGetProperty("wall_type", out var wt) && wt.ValueKind == JsonValueKind.String ? wt.GetString() : null;
        // reverse flips the wall so its exterior face is on the other side of the drawn line.
        var reverse = payload.TryGetProperty("reverse", out var rv) && rv.ValueKind == JsonValueKind.True;

        if (height <= 0)
            throw new ArgumentException("height must be greater than zero");

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Wall"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            var line = Line.CreateBound(startPoint, endPoint);

            var wallType = !string.IsNullOrEmpty(wallTypeName)
                ? GetWallTypeByName(doc, wallTypeName)
                : GetDefaultWallType(doc);

            var wall = Wall.Create(doc, line, wallType.Id, level.Id, height, 0, reverse, false);

            trans.CommitChecked();

            return new
            {
                wall_id = wall.Id.Value,
                wall_type = wallType.Name,
                reversed = reverse,
                length = line.Length,
                length_ft = line.Length,
                length_m = UnitUtils.ConvertFromInternalUnits(line.Length, UnitTypeId.Meters),
                height = height
            };
        }
    }

    [BridgeCommand("revit.create_floor", IsMutating = true)]
    private static object ExecuteCreateFloor(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var boundaryPoints = ParsePointArray(payload.GetProperty("boundary_points"));
        var levelName = payload.GetProperty("level").GetString();
        var floorTypeName = payload.TryGetProperty("floor_type", out var ft) && ft.ValueKind == JsonValueKind.String ? ft.GetString() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Floor"))
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

            var floorType = !string.IsNullOrEmpty(floorTypeName)
                ? GetFloorTypeByName(doc, floorTypeName)
                : GetDefaultFloorType(doc);
            var floor = Floor.Create(doc, new List<CurveLoop> { curveLoop }, floorType.Id, level.Id);

            trans.CommitChecked();

            var area = floor.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED)?.AsDouble() ?? 0;

            return new
            {
                floor_id = floor.Id.Value,
                floor_type = floorType.Name,
                area_sf = area,
                area_sm = UnitUtils.ConvertFromInternalUnits(area, UnitTypeId.SquareMeters),
                level = levelName
            };
        }
    }

    [BridgeCommand("revit.create_roof", IsMutating = true)]
    private static object ExecuteCreateRoof(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var boundaryPoints = ParsePointArray(payload.GetProperty("boundary_points"));
        var levelName = payload.GetProperty("level").GetString();
        var roofTypeName = payload.TryGetProperty("roof_type", out var rt) && rt.ValueKind == JsonValueKind.String ? rt.GetString() : null;
        // slope is rise over run (0.5 = 1:2). Omitted or 0 gives a flat roof.
        var slope = payload.TryGetProperty("slope", out var sl) && sl.ValueKind == JsonValueKind.Number ? sl.GetDouble() : 0.0;
        if (slope < 0)
            throw new ArgumentException("slope must not be negative");

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Roof"))
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

            var roofType = !string.IsNullOrEmpty(roofTypeName)
                ? GetRoofTypeByName(doc, roofTypeName)
                : GetDefaultRoofType(doc);

            var modelCurveArray = new ModelCurveArray();
            var footprint = doc.Create.NewFootPrintRoof(curveArray, level, roofType, out modelCurveArray);

            if (slope > 0)
            {
                foreach (ModelCurve modelCurve in modelCurveArray)
                {
                    footprint.set_DefinesSlope(modelCurve, true);
                    footprint.set_SlopeAngle(modelCurve, slope);
                }
            }

            trans.CommitChecked();

            return new
            {
                roof_id = footprint.Id.Value,
                roof_type = roofType.Name,
                slope = slope,
                level = levelName,
                curve_count = curveArray.Size
            };
        }
    }

    [BridgeCommand("revit.create_level", IsMutating = true)]
    private static object ExecuteCreateLevel(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var name = payload.GetProperty("name").GetString();
        var elevation = payload.GetProperty("elevation").GetDouble();
        var createPlanView = !payload.TryGetProperty("create_plan_view", out var cpv) || cpv.ValueKind != JsonValueKind.False;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Level"))
        {
            trans.Start();

            var level = Level.Create(doc, elevation);
            level.Name = name;

            // A level without a plan view is invisible in the project browser; make the view in the same transaction.
            ViewPlan planView = null;
            if (createPlanView)
            {
                var planType = new FilteredElementCollector(doc)
                    .OfClass(typeof(ViewFamilyType))
                    .Cast<ViewFamilyType>()
                    .FirstOrDefault(v => v.ViewFamily == ViewFamily.FloorPlan);
                if (planType == null)
                    throw new InvalidOperationException("No floor plan view type found; pass create_plan_view=false to create the level only");
                planView = ViewPlan.Create(doc, planType.Id, level.Id);
            }

            trans.CommitChecked();

            return new
            {
                level_id = level.Id.Value,
                name = level.Name,
                elevation = level.Elevation,
                elevation_ft = level.Elevation,
                elevation_m = UnitUtils.ConvertFromInternalUnits(level.Elevation, UnitTypeId.Meters),
                plan_view_id = planView?.Id.Value,
                plan_view_name = planView?.Name
            };
        }
    }

    [BridgeCommand("revit.create_grid", IsMutating = true)]
    private static object ExecuteCreateGrid(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var name = payload.TryGetProperty("name", out var n) ? n.GetString() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Grid"))
        {
            trans.Start();

            var line = Line.CreateBound(startPoint, endPoint);
            var grid = Grid.Create(doc, line);

            if (!string.IsNullOrEmpty(name))
            {
                grid.Name = name;
            }

            trans.CommitChecked();

            return new
            {
                grid_id = grid.Id.Value,
                name = grid.Name,
                curve_type = grid.Curve.GetType().Name
            };
        }
    }

    [BridgeCommand("revit.create_room", IsMutating = true)]
    private static object ExecuteCreateRoom(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var locationPoint = ParseXYZ(payload.GetProperty("location_point"));
        var levelName = payload.GetProperty("level").GetString();
        var roomName = payload.TryGetProperty("name", out var n) ? n.GetString() : "Room";
        var roomNumber = payload.TryGetProperty("number", out var num) ? num.GetString() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Room"))
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

            trans.CommitChecked();

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

    [BridgeCommand("revit.list_elements_by_category", IsMutating = false)]
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

    [BridgeCommand("revit.delete_element", IsMutating = true)]
    private static object ExecuteDeleteElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt32();

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Delete Element"))
        {
            trans.Start();

            var id = new ElementId((long)elementId);
            var deletedIds = doc.Delete(id);

            trans.CommitChecked();

            return new
            {
                deleted_count = deletedIds.Count,
                deleted_ids = deletedIds.Select(i => i.Value).ToList()
            };
        }
    }

    // ==================== COMPONENT PLACEMENT (4 NEW) ====================

    [BridgeCommand("revit.place_family_instance", IsMutating = true)]
    private static object ExecutePlaceFamilyInstance(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var location = ParseXYZ(payload.GetProperty("location"));
        var familyName = payload.GetProperty("family_name").GetString();
        var typeName = payload.GetProperty("type_name").GetString();
        var levelName = payload.GetProperty("level").GetString();

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Place Family Instance"))
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

            trans.CommitChecked();

            return new
            {
                instance_id = instance.Id.Value,
                family = familyName,
                type = typeName,
                level = levelName
            };
        }
    }

    [BridgeCommand("revit.place_door", IsMutating = true)]
    private static object ExecutePlaceDoor(UIApplication app, JsonElement payload)
        => PlaceHostedOpening(app, payload, BuiltInCategory.OST_Doors, "Door", "Place Door");

    [BridgeCommand("revit.place_window", IsMutating = true)]
    private static object ExecutePlaceWindow(UIApplication app, JsonElement payload)
        => PlaceHostedOpening(app, payload, BuiltInCategory.OST_Windows, "Window", "Place Window");

    private const double OpeningFitToleranceFt = 0.005;   // about 1.5 mm
    private const double FeetToMm = 304.8;
    private const double CubicFeetToCubicMetres = 0.028316846592;

    /// <summary>
    /// Shared door/window placement. All checks that can refuse run before the transaction opens, so a
    /// refusal never touches the model. One transaction per call; the host is re-verified before and after commit.
    /// </summary>
    private static object PlaceHostedOpening(UIApplication app, JsonElement payload,
        BuiltInCategory category, string label, string transactionName)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var isWindow = category == BuiltInCategory.OST_Windows;
        var wallId = payload.GetProperty("wall_id").GetInt64();
        var location = ParseXYZ(payload.GetProperty("location"));
        var wall = doc.GetElement(new ElementId(wallId)) as Wall;
        if (wall == null)
            throw new ArgumentException($"Wall with ID {wallId} not found");

        var familyName = OptionalString(payload, "family_name");
        var typeName = OptionalString(payload, "type_name");
        var wantHandFlipped = OptionalBool(payload, "hand_flipped");
        var wantFacingFlipped = OptionalBool(payload, "facing_flipped");

        var symbol = ResolveOpeningSymbol(doc, category, label, familyName, typeName, out var symbolSource);
        var level = GetPlacementLevel(doc, wall, location);
        var fit = CheckOpeningFit(wall, wallId, symbol, label, location, level, isWindow);

        var volumeBefore = WallVolumeCubicFeet(wall);
        FamilyInstance instance;
        using (var trans = BridgeCommandFactory.CreateTransaction(doc, transactionName))
        {
            trans.Start();

            if (!symbol.IsActive)
            {
                symbol.Activate();
                doc.Regenerate();
            }

            instance = isWindow
                ? doc.Create.NewFamilyInstance(location, symbol, wall, level, StructuralType.NonStructural)
                : doc.Create.NewFamilyInstance(location, symbol, wall, StructuralType.NonStructural);
            if (isWindow)
                SetWindowSillHeight(instance, location, level);

            ApplyFlip(instance, wantHandFlipped, instance.CanFlipHand, instance.HandFlipped,
                () => instance.flipHand(), "hand_flipped", label, wallId);
            ApplyFlip(instance, wantFacingFlipped, instance.CanFlipFacing, instance.FacingFlipped,
                () => instance.flipFacing(), "facing_flipped", label, wallId);

            doc.Regenerate();
            VerifyOpeningHost(doc, instance.Id, wallId, label, committed: false);

            trans.CommitChecked();
        }

        var placed = VerifyOpeningHost(doc, instance.Id, wallId, label, committed: true);
        var volumeAfter = WallVolumeCubicFeet(wall);
        double? volumeDeltaM3 = volumeBefore.HasValue && volumeAfter.HasValue
            ? Math.Round((volumeAfter.Value - volumeBefore.Value) * CubicFeetToCubicMetres, 6)
            : (double?)null;

        var result = new Dictionary<string, object?>
        {
            [isWindow ? "window_id" : "door_id"] = placed.Id.Value,
            ["family"] = symbol.Family.Name,
            ["type"] = symbol.Name,
            ["symbol_source"] = symbolSource,
            ["wall_id"] = wallId,
            ["host_wall_id"] = placed.Host?.Id.Value,
            ["level"] = level.Name,
            ["hand_flipped"] = placed.HandFlipped,
            ["facing_flipped"] = placed.FacingFlipped,
            ["fit_check"] = fit,
            ["volume_delta_m3"] = volumeDeltaM3
        };
        if (isWindow)
            result["sill_height"] = location.Z - level.Elevation;
        return result;
    }

    private static string? OptionalString(JsonElement payload, string name)
        => PayloadJson.OptionalString(payload, name);

    private static bool? OptionalBool(JsonElement payload, string name)
        => PayloadJson.OptionalBool(payload, name);

    /// <summary>Exact family+type when both are given; otherwise the first loaded symbol of the category (reported).</summary>
    private static FamilySymbol ResolveOpeningSymbol(Document doc, BuiltInCategory category, string label,
        string? familyName, string? typeName, out string source)
    {
        var symbols = new FilteredElementCollector(doc)
            .OfCategory(category)
            .OfClass(typeof(FamilySymbol))
            .Cast<FamilySymbol>()
            .OrderBy(s => s.Family.Name, StringComparer.OrdinalIgnoreCase)
            .ThenBy(s => s.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();

        if (symbols.Count == 0)
            throw new InvalidOperationException(
                $"No {label.ToLowerInvariant()} family type is loaded in this project. Load a {label.ToLowerInvariant()} family first.");

        var candidates = symbols
            .Where(s => familyName == null || s.Family.Name.Equals(familyName, StringComparison.OrdinalIgnoreCase))
            .Where(s => typeName == null || s.Name.Equals(typeName, StringComparison.OrdinalIgnoreCase))
            .ToList();

        if (candidates.Count == 0)
        {
            var sample = string.Join("; ", symbols.Take(8).Select(s => $"{s.Family.Name}: {s.Name}"));
            throw new ArgumentException(
                $"No loaded {label.ToLowerInvariant()} type matches family '{familyName ?? "(any)"}' / type '{typeName ?? "(any)"}'. " +
                $"Available ({symbols.Count}): {sample}");
        }

        source = familyName != null && typeName != null ? "requested" : "first_available";
        return candidates[0];
    }

    private static double? ReadSymbolLength(FamilySymbol symbol, BuiltInParameter builtIn, params string[] names)
    {
        var p = symbol.get_Parameter(builtIn);
        if (p != null && p.HasValue && p.StorageType == StorageType.Double && p.AsDouble() > 0)
            return p.AsDouble();
        foreach (var name in names)
        {
            p = symbol.LookupParameter(name);
            if (p != null && p.HasValue && p.StorageType == StorageType.Double && p.AsDouble() > 0)
                return p.AsDouble();
        }
        return null;
    }

    /// <summary>Refuses with the wall id and the numbers when the opening cannot fit; returns the numbers on success.</summary>
    private static object CheckOpeningFit(Wall wall, long wallId, FamilySymbol symbol, string label,
        XYZ location, Level level, bool isWindow)
    {
        var width = isWindow
            ? ReadSymbolLength(symbol, BuiltInParameter.WINDOW_WIDTH, "Width", "Rough Width")
            : ReadSymbolLength(symbol, BuiltInParameter.DOOR_WIDTH, "Width", "Rough Width");
        var height = isWindow
            ? ReadSymbolLength(symbol, BuiltInParameter.WINDOW_HEIGHT, "Height", "Rough Height")
            : ReadSymbolLength(symbol, BuiltInParameter.DOOR_HEIGHT, "Height", "Rough Height");

        var who = $"{label} '{symbol.Family.Name}: {symbol.Name}' in wall {wallId}";
        var notes = new List<string>();
        double? wallLength = null, distAlong = null, wallBottom = null, wallTop = null;

        if (wall.Location is LocationCurve lc && lc.Curve != null && lc.Curve.IsBound)
        {
            var curve = lc.Curve;
            // Distance from the wall is measured in plan: a window or door sits above the wall's base line.
            var flat = new XYZ(location.X, location.Y, curve.GetEndPoint(0).Z);
            var proj = curve.Project(flat);
            if (proj != null)
            {
                wallLength = curve.Length;
                distAlong = curve.ComputeNormalizedParameter(proj.Parameter) * curve.Length;
                var offWall = proj.Distance;
                if (offWall > wall.Width + 0.5)
                    throw new ArgumentException(
                        $"{who}: location is {offWall * FeetToMm:0} mm from the wall line (wall thickness {wall.Width * FeetToMm:0} mm). " +
                        "Pick a point on the wall.");
            }
        }
        else
        {
            notes.Add("wall has no bounded location curve; width check skipped");
        }

        var bb = wall.get_BoundingBox(null);
        if (bb != null)
        {
            wallBottom = bb.Min.Z;
            wallTop = bb.Max.Z;
        }
        else
        {
            notes.Add("wall has no bounding box; height check skipped");
        }

        // Windows are placed with location.Z as the sill; doors sit at the placement level.
        var sillZ = isWindow ? location.Z : level.Elevation;
        double? headZ = height.HasValue ? sillZ + height.Value : (double?)null;

        if (width.HasValue && wallLength.HasValue && distAlong.HasValue)
        {
            var from = distAlong.Value - width.Value / 2;
            var to = distAlong.Value + width.Value / 2;
            if (from < -OpeningFitToleranceFt || to > wallLength.Value + OpeningFitToleranceFt)
                throw new ArgumentException(
                    $"{who} does not fit: opening width {width.Value * FeetToMm:0} mm centred {distAlong.Value * FeetToMm:0} mm along a wall " +
                    $"{wallLength.Value * FeetToMm:0} mm long would span {from * FeetToMm:0} to {to * FeetToMm:0} mm. " +
                    "Move the location inboard or use a narrower type.");
        }
        else if (!width.HasValue)
        {
            notes.Add("type has no readable width parameter; width check skipped");
        }

        if (height.HasValue && wallBottom.HasValue && wallTop.HasValue)
        {
            if (sillZ < wallBottom.Value - OpeningFitToleranceFt || headZ!.Value > wallTop.Value + OpeningFitToleranceFt)
                throw new ArgumentException(
                    $"{who} does not fit vertically: sill at {sillZ * FeetToMm:0} mm and head at {headZ!.Value * FeetToMm:0} mm " +
                    $"(opening height {height.Value * FeetToMm:0} mm) against wall extent {wallBottom.Value * FeetToMm:0} to {wallTop.Value * FeetToMm:0} mm (project Z).");
        }
        else if (!height.HasValue)
        {
            notes.Add("type has no readable height parameter; height check skipped");
        }

        return new
        {
            checked_width = width.HasValue && wallLength.HasValue,
            checked_height = height.HasValue && wallBottom.HasValue,
            opening_width_mm = width.HasValue ? Math.Round(width.Value * FeetToMm, 1) : (double?)null,
            opening_height_mm = height.HasValue ? Math.Round(height.Value * FeetToMm, 1) : (double?)null,
            wall_length_mm = wallLength.HasValue ? Math.Round(wallLength.Value * FeetToMm, 1) : (double?)null,
            distance_along_wall_mm = distAlong.HasValue ? Math.Round(distAlong.Value * FeetToMm, 1) : (double?)null,
            wall_z_min_mm = wallBottom.HasValue ? Math.Round(wallBottom.Value * FeetToMm, 1) : (double?)null,
            wall_z_max_mm = wallTop.HasValue ? Math.Round(wallTop.Value * FeetToMm, 1) : (double?)null,
            notes
        };
    }

    private static void ApplyFlip(FamilyInstance instance, bool? wanted, bool canFlip, bool current,
        Action flip, string name, string label, long wallId)
    {
        if (!wanted.HasValue || wanted.Value == current) return;
        if (!canFlip)
            throw new InvalidOperationException(
                $"{label} {instance.Id.Value} in wall {wallId} cannot be flipped ({name} was requested but this family does not support it).");
        flip();
    }

    private static FamilyInstance VerifyOpeningHost(Document doc, ElementId id, long wallId, string label, bool committed)
    {
        var placed = doc.GetElement(id) as FamilyInstance;
        var phase = committed ? "after commit" : "before commit";
        if (placed == null)
            throw new InvalidOperationException($"{label} {id.Value} does not exist {phase}; placement into wall {wallId} failed.");
        if (placed.Host == null || placed.Host.Id.Value != wallId)
            throw new InvalidOperationException(
                $"{label} {id.Value} {phase} is hosted by {(placed.Host == null ? "nothing" : placed.Host.Id.Value.ToString())}, not wall {wallId}.");
        return placed;
    }

    private static double? WallVolumeCubicFeet(Wall wall)
    {
        var p = wall.get_Parameter(BuiltInParameter.HOST_VOLUME_COMPUTED);
        return p != null && p.HasValue ? p.AsDouble() : (double?)null;
    }

    [BridgeCommand("revit.list_families", IsMutating = false)]
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

    [BridgeCommand("revit.create_floor_plan_view", IsMutating = true)]
    private static object ExecuteCreateFloorPlanView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var levelName = payload.GetProperty("level").GetString();
        var viewName = payload.TryGetProperty("name", out var n) ? n.GetString() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Floor Plan View"))
        {
            trans.Start();

            var level = GetLevelByName(doc, levelName);
            var viewFamilyType = GetViewFamilyType(doc, ViewFamily.FloorPlan);

            var view = ViewPlan.Create(doc, viewFamilyType.Id, level.Id);

            if (!string.IsNullOrEmpty(viewName))
            {
                view.Name = viewName;
            }

            trans.CommitChecked();

            return new
            {
                view_id = view.Id.Value,
                name = view.Name,
                level = levelName,
                view_type = view.ViewType.ToString()
            };
        }
    }

    [BridgeCommand("revit.create_3d_view", IsMutating = true)]
    private static object ExecuteCreate3DView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var viewName = payload.TryGetProperty("name", out var n) ? n.GetString() : "3D View";

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create 3D View"))
        {
            trans.Start();

            var viewFamilyType = GetViewFamilyType(doc, ViewFamily.ThreeDimensional);
            var view3d = View3D.CreateIsometric(doc, viewFamilyType.Id);
            view3d.Name = viewName;

            trans.CommitChecked();

            return new
            {
                view_id = view3d.Id.Value,
                name = view3d.Name,
                view_type = view3d.ViewType.ToString()
            };
        }
    }

    [BridgeCommand("revit.create_section_view", IsMutating = true)]
    private static object ExecuteCreateSectionView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var viewName = payload.TryGetProperty("name", out var n) ? n.GetString() : "Section";

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Section View"))
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

            trans.CommitChecked();

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

    private static Level GetPlacementLevel(Document doc, Wall wall, XYZ location)
    {
        if (wall.LevelId != ElementId.InvalidElementId)
        {
            var wallLevel = doc.GetElement(wall.LevelId) as Level;
            if (wallLevel != null)
                return wallLevel;
        }

        var level = new FilteredElementCollector(doc)
            .OfClass(typeof(Level))
            .Cast<Level>()
            .OrderBy(l => Math.Abs(l.Elevation - location.Z))
            .FirstOrDefault();

        if (level == null)
            throw new InvalidOperationException("No levels found for hosted placement");

        return level;
    }

    private static void SetWindowSillHeight(FamilyInstance window, XYZ location, Level level)
    {
        var sillHeight = location.Z - level.Elevation;
        var sillParam = window.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM);
        if (sillParam != null && !sillParam.IsReadOnly)
            sillParam.Set(sillHeight);
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

    private static WallType GetDefaultWallType(Document doc)
    {
        if (doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.WallType)) is WallType preferred
            && preferred.Kind == WallKind.Basic)
            return preferred;

        var basic = new FilteredElementCollector(doc)
            .OfClass(typeof(WallType))
            .Cast<WallType>()
            .Where(wt => wt.Kind == WallKind.Basic)
            .OrderBy(wt => wt.Name)
            .FirstOrDefault();
        return basic ?? throw new InvalidOperationException("No basic wall types found in document; pass wall_type");
    }

    private static FloorType GetDefaultFloorType(Document doc)
    {
        // Foundation slabs are floor types too and must not be the silent default for a storey floor.
        if (doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.FloorType)) is FloorType preferred
            && !preferred.IsFoundationSlab)
            return preferred;

        var floorType = new FilteredElementCollector(doc)
            .OfClass(typeof(FloorType))
            .Cast<FloorType>()
            .Where(ft => !ft.IsFoundationSlab)
            .OrderBy(ft => ft.Name)
            .FirstOrDefault();
        return floorType ?? throw new InvalidOperationException("No non-foundation floor types found in document; pass floor_type");
    }

    private static RoofType GetDefaultRoofType(Document doc)
    {
        if (doc.GetElement(doc.GetDefaultElementTypeId(ElementTypeGroup.RoofType)) is RoofType preferred)
            return preferred;

        var roofType = new FilteredElementCollector(doc)
            .OfClass(typeof(RoofType))
            .Cast<RoofType>()
            .OrderBy(rt => rt.Name)
            .FirstOrDefault();
        return roofType ?? throw new InvalidOperationException("No roof types found in document; pass roof_type");
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

    [BridgeCommand("revit.get_element_parameters", IsMutating = false)]
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
                // Revit throws when GUID is read from a non-shared parameter.
                guid = p.IsShared ? p.GUID.ToString() : null
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

    [BridgeCommand("revit.set_parameter_value", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Set Parameter Value"))
        {
            trans.Start();

            var parameter = element.LookupParameter(parameterName);
            if (parameter == null)
                throw new ArgumentException($"Parameter '{parameterName}' not found on element");

            if (parameter.IsReadOnly)
                throw new InvalidOperationException($"Parameter '{parameterName}' is read-only");

            SetParameterValue(parameter, value);

            trans.CommitChecked();

            return new
            {
                element_id = elementId,
                parameter_name = parameterName,
                new_value = GetParameterValueAsString(parameter),
                status = "success"
            };
        }
    }

    [BridgeCommand("revit.get_parameter_value", IsMutating = false)]
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

    [BridgeCommand("revit.list_shared_parameters", IsMutating = false)]
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

    [BridgeCommand("revit.create_shared_parameter", IsMutating = true)]
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

    [BridgeCommand("revit.list_project_parameters", IsMutating = false)]
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

    [BridgeCommand("revit.create_project_parameter", IsMutating = true)]
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

    [BridgeCommand("revit.batch_set_parameters", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Batch Set Parameters"))
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

            trans.CommitChecked();
        }

        return new
        {
            total = updates.Count,
            success_count = successCount,
            error_count = errorCount,
            results
        };
    }

    [BridgeCommand("revit.get_type_parameters", IsMutating = false)]
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

    [BridgeCommand("revit.set_type_parameter", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Set Type Parameter"))
        {
            trans.Start();

            var parameter = elementType.LookupParameter(parameterName);
            if (parameter == null)
                throw new ArgumentException($"Parameter '{parameterName}' not found on type");

            if (parameter.IsReadOnly)
                throw new InvalidOperationException($"Parameter '{parameterName}' is read-only");

            SetParameterValue(parameter, value);

            trans.CommitChecked();

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

    [BridgeCommand("revit.list_sheets", IsMutating = false)]
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

    [BridgeCommand("revit.create_sheet", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Sheet"))
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

            trans.CommitChecked();

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

    [BridgeCommand("revit.delete_sheet", IsMutating = true)]
    private static object ExecuteDeleteSheet(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheetId = payload.GetProperty("sheet_id").GetInt32();

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Delete Sheet"))
        {
            trans.Start();

            var sheet = doc.GetElement(new ElementId((long)sheetId)) as ViewSheet;
            if (sheet == null)
                throw new ArgumentException($"Sheet with ID {sheetId} not found");

            var sheetNumber = sheet.SheetNumber;
            var sheetName = sheet.Name;

            doc.Delete(new ElementId((long)sheetId));

            trans.CommitChecked();

            return new
            {
                sheet_id = sheetId,
                sheet_number = sheetNumber,
                sheet_name = sheetName,
                status = "deleted"
            };
        }
    }

    [BridgeCommand("revit.place_viewport_on_sheet", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Place Viewport"))
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

                trans.CommitChecked();

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

    [BridgeCommand("revit.batch_create_sheets_from_csv", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Batch Create Sheets"))
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

            trans.CommitChecked();
        }

        return new
        {
            total = sheets.Count,
            success_count = successCount,
            error_count = errorCount,
            results
        };
    }

    [BridgeCommand("revit.populate_titleblock", IsMutating = true)]
    private static object ExecutePopulateTitleblock(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var sheetId = payload.GetProperty("sheet_id").GetInt32();
        var parameters = payload.GetProperty("parameters").EnumerateObject()
            .ToDictionary(p => p.Name, p => p.Value);

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Populate Titleblock"))
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

            trans.CommitChecked();

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

    [BridgeCommand("revit.list_titleblocks", IsMutating = false)]
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

    [BridgeCommand("revit.get_sheet_info", IsMutating = false)]
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

        // A sheet can carry two parameters with the same name (built-in "Category" and a shared one),
        // so a plain ToDictionary threw "An item with the same key has already been added".
        var parameters = new Dictionary<string, string?>();
        foreach (Parameter p in sheet.Parameters)
        {
            if (!p.HasValue) continue;
            var name = p.Definition.Name;
            var value = GetParameterValueAsString(p);
            if (parameters.TryGetValue(name, out var existing))
            {
                if (existing == value) continue;
                var n = 2;
                while (parameters.ContainsKey($"{name} ({n})")) n++;
                name = $"{name} ({n})";
            }
            parameters[name] = value;
        }

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

    [BridgeCommand("revit.duplicate_sheet", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Duplicate Sheet"))
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

            trans.CommitChecked();

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

    [BridgeCommand("revit.renumber_sheets", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Renumber Sheets"))
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

            trans.CommitChecked();
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

    [BridgeCommand("revit.export_dwg_by_view", IsMutating = false)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Export DWG"))
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

            trans.CommitChecked();
        }

        return new
        {
            exported_count = exportedFiles.Count(f => ((dynamic)f).status == "success"),
            error_count = exportedFiles.Count(f => ((dynamic)f).status == "error"),
            files = exportedFiles
        };
    }

    [BridgeCommand("revit.export_ifc_with_settings", IsMutating = false)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Export IFC"))
        {
            trans.Start();

            var result = doc.Export(
                System.IO.Path.GetDirectoryName(outputPath),
                System.IO.Path.GetFileNameWithoutExtension(outputPath),
                options
            );

            trans.CommitChecked();

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

    [BridgeCommand("revit.export_navisworks", IsMutating = false)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Export Navisworks"))
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

            trans.CommitChecked();

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

    [BridgeCommand("revit.export_image", IsMutating = false)]
    private static object ExecuteExportImage(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var viewId = payload.GetProperty("view_id").GetInt32();
        var outputPath = payload.GetProperty("output_path").GetString();
        if (string.IsNullOrWhiteSpace(outputPath))
            throw new ArgumentException("output_path must name an image file");

        outputPath = System.IO.Path.GetFullPath(outputPath);
        var imageFormat = payload.TryGetProperty("format", out var fmt)
            ? fmt.GetString()?.ToUpperInvariant()
            : System.IO.Path.GetExtension(outputPath).TrimStart('.').ToUpperInvariant();
        var resolution = payload.TryGetProperty("resolution", out var res)
            ? res.GetInt32()
            : 150;
        var hasWidth = payload.TryGetProperty("width", out var width) && width.ValueKind == JsonValueKind.Number;
        var hasHeight = payload.TryGetProperty("height", out var height) && height.ValueKind == JsonValueKind.Number;
        var pixelSize = hasWidth ? width.GetInt32() : hasHeight ? height.GetInt32() : resolution;

        var fileType = imageFormat switch
        {
            "JPG" or "JPEG" => ImageFileType.JPEGLossless,
            "BMP" => ImageFileType.BMP,
            "TIF" or "TIFF" => ImageFileType.TIFF,
            _ => ImageFileType.PNG
        };
        imageFormat = fileType == ImageFileType.PNG ? "PNG" : imageFormat;

        var view = doc.GetElement(new ElementId((long)viewId)) as View;
        if (view == null)
            throw new ArgumentException($"View with ID {viewId} not found");

        var outputDirectory = System.IO.Path.GetDirectoryName(outputPath)!;
        var filePrefix = System.IO.Path.GetFileNameWithoutExtension(outputPath);
        if (string.IsNullOrWhiteSpace(filePrefix))
            throw new ArgumentException("output_path must name an image file");
        System.IO.Directory.CreateDirectory(outputDirectory);

        // SetOfViews appends Revit's view name to this file prefix. Track changed
        // artifacts so an old export cannot make a failed export look successful.
        var existingFiles = System.IO.Directory.EnumerateFiles(outputDirectory, filePrefix + "*")
            .ToDictionary(path => path, path =>
            {
                var file = new System.IO.FileInfo(path);
                return (file.Length, file.LastWriteTimeUtc);
            }, StringComparer.OrdinalIgnoreCase);

        var options = new ImageExportOptions
        {
            ZoomType = ZoomFitType.FitToPage,
            PixelSize = pixelSize,
            ImageResolution = ImageResolution.DPI_150,
            FilePath = System.IO.Path.Combine(outputDirectory, filePrefix),
            FitDirection = hasHeight && !hasWidth ? FitDirectionType.Vertical : FitDirectionType.Horizontal,
            HLRandWFViewsFileType = fileType,
            ShadowViewsFileType = fileType,
            ExportRange = ExportRange.SetOfViews
        };

        options.SetViewsAndSheets(new List<ElementId> { view.Id });

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Export Image"))
        {
            trans.Start();

            doc.ExportImage(options);

            trans.CommitChecked();

            var exportedFiles = System.IO.Directory.EnumerateFiles(outputDirectory, filePrefix + "*")
                .Select(path => new System.IO.FileInfo(path))
                .Where(file => file.Length > 0 &&
                    new[] { ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff" }
                        .Contains(file.Extension, StringComparer.OrdinalIgnoreCase) &&
                    (!existingFiles.TryGetValue(file.FullName, out var previous) ||
                     previous.Length != file.Length || previous.LastWriteTimeUtc != file.LastWriteTimeUtc))
                .OrderBy(file => file.FullName, StringComparer.OrdinalIgnoreCase)
                .ToList();
            var actualFile = exportedFiles.FirstOrDefault()?.FullName;
            var exportSucceeded = exportedFiles.Count > 0;

            return new
            {
                view_id = viewId,
                view_name = view.Name,
                requested_file_path = outputPath,
                expected_file_path = actualFile,
                file_path = actualFile,
                file_paths = exportedFiles.Select(file => file.FullName).ToArray(),
                // Size of the file named in file_path; total_size_bytes covers every file Revit wrote.
                file_size_bytes = exportedFiles.FirstOrDefault()?.Length ?? 0L,
                total_size_bytes = exportedFiles.Sum(file => file.Length),
                format = imageFormat,
                resolution_dpi = 150,
                pixel_size = pixelSize,
                file_exists = exportSucceeded,
                status = exportSucceeded ? "success" : "error",
                error = exportSucceeded ? null : "Revit did not produce a new or updated image file."
            };
        }
    }

    [BridgeCommand("revit.render_3d_view", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Render 3D View"))
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

            trans.CommitChecked();

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

    [BridgeCommand("revit.get_selection", IsMutating = false)]
    private static object ExecuteGetSelection(UIApplication app)
    {
        var uidoc = app.ActiveUIDocument;
        if (uidoc == null) throw new InvalidOperationException("No active UIDocument");

        var ids = uidoc.Selection.GetElementIds().Select(id => id.Value).ToList();
        return new { count = ids.Count, element_ids = ids };
    }

    [BridgeCommand("revit.set_selection", IsMutating = true)]
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

    // UniqueId is stable across sessions (unlike ElementId, which revit.set_selection
    // takes) - the panel only has UniqueIds from QA/QC findings, which come from a
    // stored snapshot, not the live document. Not mutating: this only changes the
    // active view's selection/framing, never the document.
    [BridgeCommand("revit.select_by_unique_ids", IsMutating = false)]
    private static object ExecuteSelectByUniqueIds(UIApplication app, JsonElement payload)
    {
        var uidoc = app.ActiveUIDocument;
        if (uidoc == null) throw new InvalidOperationException("No active UIDocument");

        var doc = uidoc.Document;
        var requestedUids = payload.GetProperty("element_uids").EnumerateArray()
            .Select(x => x.GetString())
            .ToList();

        var ids = requestedUids
            .Select(uid => doc.GetElement(uid))
            .Where(element => element != null)
            .Select(element => element.Id)
            .ToList();

        if (ids.Count == 0)
        {
            return new { selected_count = 0, not_found_count = requestedUids.Count };
        }

        uidoc.Selection.SetElementIds(ids);
        uidoc.ShowElements(ids);
        return new { selected_count = ids.Count, not_found_count = requestedUids.Count - ids.Count };
    }

    // Preview in model (UNVERIFIED: not compiled or run in live Revit by the author).
    // Read-only by design: selects + zooms, and optionally applies Revit's TEMPORARY
    // hide/isolate view mode, which is never saved with the model. Persistent graphic
    // overrides (View.SetElementOverrides) are deliberately NOT used because they
    // would be stored in the document. Reverted by revit.clear_preview.
    [BridgeCommand("revit.preview_elements", IsMutating = false)]
    private static object ExecutePreviewElements(UIApplication app, JsonElement payload)
    {
        var uidoc = app.ActiveUIDocument;
        if (uidoc == null) throw new InvalidOperationException("No active UIDocument");

        var doc = uidoc.Document;
        var view = uidoc.ActiveView;
        var ids = new List<ElementId>();
        var requested = 0;

        if (payload.TryGetProperty("element_uids", out var uidsProp) && uidsProp.ValueKind == JsonValueKind.Array)
        {
            foreach (var x in uidsProp.EnumerateArray())
            {
                requested++;
                var element = doc.GetElement(x.GetString());
                if (element != null) ids.Add(element.Id);
            }
        }

        if (payload.TryGetProperty("element_ids", out var idsProp) && idsProp.ValueKind == JsonValueKind.Array)
        {
            foreach (var x in idsProp.EnumerateArray())
            {
                requested++;
                var element = doc.GetElement(new ElementId((long)x.GetInt32()));
                if (element != null) ids.Add(element.Id);
            }
        }

        if (ids.Count == 0)
        {
            return new { previewed_count = 0, not_found_count = requested, isolated = false };
        }

        var isolate = !payload.TryGetProperty("isolate", out var isolateProp) || isolateProp.ValueKind != JsonValueKind.False;

        uidoc.Selection.SetElementIds(ids);
        uidoc.ShowElements(ids);

        var isolated = false;
        if (isolate && view.CanUseTemporaryVisibilityModes())
        {
            using (var tx = BridgeCommandFactory.CreateTransaction(doc, "Preview elements (temporary isolate)"))
            {
                tx.Start();
                view.IsolateElementsTemporary(ids);
                tx.CommitChecked();
            }
            isolated = true;
        }

        return new { previewed_count = ids.Count, not_found_count = requested - ids.Count, isolated };
    }

    [BridgeCommand("revit.clear_preview", IsMutating = false)]
    private static object ExecuteClearPreview(UIApplication app)
    {
        var uidoc = app.ActiveUIDocument;
        if (uidoc == null) throw new InvalidOperationException("No active UIDocument");

        var doc = uidoc.Document;
        var view = uidoc.ActiveView;
        var restored = false;

        if (view.IsInTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate))
        {
            using (var tx = BridgeCommandFactory.CreateTransaction(doc, "Clear preview (end temporary isolate)"))
            {
                tx.Start();
                view.DisableTemporaryViewMode(TemporaryViewMode.TemporaryHideIsolate);
                tx.CommitChecked();
            }
            restored = true;
        }

        uidoc.Selection.SetElementIds(new List<ElementId>());
        return new { cleared = true, temporary_isolate_ended = restored };
    }

    [BridgeCommand("revit.create_text_note", IsMutating = true)]
    private static object ExecuteCreateTextNote(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var text = payload.GetProperty("text").GetString();
        var location = ParseXYZ(payload.GetProperty("location"));
        var viewId = payload.TryGetProperty("view_id", out var v) ? v.GetInt32() : doc.ActiveView.Id.Value;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Text Note"))
        {
            trans.Start();
            var view = doc.GetElement(new ElementId((long)viewId)) as View;
            var note = TextNote.Create(doc, view.Id, location, text, new ElementId(BuiltInParameter.TEXT_SIZE)); // Using default type logic simplifiction
            trans.CommitChecked();

            return new { text_note_id = note.Id.Value, text = note.Text, view_id = view.Id.Value };
        }
    }

    [BridgeCommand("revit.create_tag", IsMutating = true)]
    private static object ExecuteCreateTag(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt32();
        var location = ParseXYZ(payload.GetProperty("location"));
        var viewId = payload.TryGetProperty("view_id", out var v) ? v.GetInt32() : doc.ActiveView.Id.Value;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Tag"))
        {
            trans.Start();
            var view = doc.GetElement(new ElementId((long)viewId)) as View;
            // IndependentTag.Create replaced NewTag in 2018+
            // For Revit 2024 it's Create
            var element = doc.GetElement(new ElementId((long)elementId));
            if (element == null) throw new ArgumentException($"Element {elementId} not found");
            var tag = IndependentTag.Create(doc, view.Id, new Reference(element), false, TagMode.TM_ADDBY_CATEGORY, TagOrientation.Horizontal, location);
            trans.CommitChecked();
            return new { tag_id = tag.Id.Value, tagged_element_id = elementId };
        }
    }

    // ==================== BATCH 2: STRUCTURE IMPL ====================
    
    [BridgeCommand("revit.create_column", IsMutating = true)]
    private static object ExecuteCreateColumn(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var location = ParseXYZ(payload.GetProperty("location"));
        var levelName = payload.GetProperty("level").GetString();
        var familyName = payload.GetProperty("family_name").GetString();
        var typeName = payload.GetProperty("type_name").GetString();

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Structural Column"))
        {
             trans.Start();
             var level = GetLevelByName(doc, levelName);
             var symbol = GetFamilySymbolByName(doc, familyName, typeName);
             if(!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }
             
             var instance = doc.Create.NewFamilyInstance(location, symbol, level, StructuralType.Column);
             trans.CommitChecked();
             
             return new { column_id = instance.Id.Value, family = familyName, type = typeName };
        }
    }

    [BridgeCommand("revit.create_beam", IsMutating = true)]
    private static object ExecuteCreateBeam(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var start = ParseXYZ(payload.GetProperty("start_point"));
        var end = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var familyName = payload.GetProperty("family_name").GetString();
        var typeName = payload.GetProperty("type_name").GetString();

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Beam"))
        {
             trans.Start();
             var level = GetLevelByName(doc, levelName);
             var symbol = GetFamilySymbolByName(doc, familyName, typeName);
             if(!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }
             
             var line = Line.CreateBound(start, end);
             var instance = doc.Create.NewFamilyInstance(line, symbol, level, StructuralType.Beam);
             trans.CommitChecked();
             
             return new { beam_id = instance.Id.Value, family = familyName, type = typeName, length = line.Length };
        }
    }

    [BridgeCommand("revit.create_foundation", IsMutating = true)]
    private static object ExecuteCreateFoundation(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var location = ParseXYZ(payload.GetProperty("location"));
        var levelName = payload.GetProperty("level").GetString();
        var familyName = payload.GetProperty("family_name").GetString();
        var typeName = payload.GetProperty("type_name").GetString();

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Foundation"))
        {
             trans.Start();
             var level = GetLevelByName(doc, levelName);
             var symbol = GetFamilySymbolByName(doc, familyName, typeName);
             if(!symbol.IsActive) { symbol.Activate(); doc.Regenerate(); }
             
             var instance = doc.Create.NewFamilyInstance(location, symbol, level, StructuralType.Footing);
             trans.CommitChecked();
             
             return new { foundation_id = instance.Id.Value, family = familyName, type = typeName };
        }
    }

    // ==================== BATCH 2: MEP IMPL ====================

    [BridgeCommand("revit.create_duct", IsMutating = true)]
    private static object ExecuteCreateDuct(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var start = ParseXYZ(payload.GetProperty("start_point"));
        var end = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var systemTypeName = payload.TryGetProperty("system_type", out var s) ? s.GetString() : "Supply Air";
        var ductTypeName = payload.TryGetProperty("duct_type", out var d) ? d.GetString() : null; // Default to first available

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Duct"))
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
             trans.CommitChecked();
             
             return new { duct_id = duct.Id.Value, system_type = mechanicalSystemType.Name, duct_type = ductType.Name };
        }
    }

    [BridgeCommand("revit.create_pipe", IsMutating = true)]
    private static object ExecuteCreatePipe(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var start = ParseXYZ(payload.GetProperty("start_point"));
        var end = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var systemTypeName = payload.TryGetProperty("system_type", out var s) ? s.GetString() : "Hydronic Supply";
        var pipeTypeName = payload.TryGetProperty("pipe_type", out var p) ? p.GetString() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Pipe"))
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
             trans.CommitChecked();
             
             return new { pipe_id = pipe.Id.Value, system_type = pipingSystemType.Name, pipe_type = pipeType.Name };
        }
    }

    // ==================== BATCH 2: GENERAL HELPER IMPL ====================

    [BridgeCommand("revit.get_categories", IsMutating = false)]
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
    
    [BridgeCommand("revit.get_element_type", IsMutating = false)]
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

    [BridgeCommand("revit.move_element", IsMutating = true)]
    private static object ExecuteMoveElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var vector = ParseXYZ(payload.GetProperty("vector"));

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Move Element"))
        {
            trans.Start();
            ElementTransformUtils.MoveElement(doc, elementId, vector);
            trans.CommitChecked();
            return new { status = "success", moved_element_id = elementId.Value };
        }
    }

    [BridgeCommand("revit.copy_element", IsMutating = true)]
    private static object ExecuteCopyElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var vector = ParseXYZ(payload.GetProperty("vector"));

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Copy Element"))
        {
            trans.Start();
            var newIds = ElementTransformUtils.CopyElement(doc, elementId, vector);
            trans.CommitChecked();
            return new { status = "success", original_id = elementId.Value, new_element_ids = newIds.Select(id => id.Value).ToList() };
        }
    }

    [BridgeCommand("revit.rotate_element", IsMutating = true)]
    private static object ExecuteRotateElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var axisPoint = ParseXYZ(payload.GetProperty("axis_point"));
        var angleRadians = payload.GetProperty("angle_radians").GetDouble();

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Rotate Element"))
        {
            trans.Start();
            var axis = Line.CreateBound(axisPoint, axisPoint + XYZ.BasisZ); // Default to Z-axis rotation for now
            ElementTransformUtils.RotateElement(doc, elementId, axis, angleRadians);
            trans.CommitChecked();
            return new { status = "success", element_id = elementId.Value, angle = angleRadians };
        }
    }

    [BridgeCommand("revit.mirror_element", IsMutating = true)]
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
        
        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Mirror Element"))
        {
             trans.Start();
             var plane = Plane.CreateByNormalAndOrigin(planeNormal, planeOrigin);
             ElementTransformUtils.MirrorElement(doc, elementId, plane);
             trans.CommitChecked();
             return new { status = "success", element_id = elementId.Value };
        }
    }
    
    [BridgeCommand("revit.pin_element", IsMutating = true)]
    private static object ExecutePinElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        
        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Pin Element"))
        {
             trans.Start();
             var el = doc.GetElement(elementId);
             if(el != null) el.Pinned = true;
             trans.CommitChecked();
             return new { status = "success", element_id = elementId.Value, pinned = true };
        }
    }

    [BridgeCommand("revit.unpin_element", IsMutating = true)]
    private static object ExecuteUnpinElement(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        
        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Unpin Element"))
        {
             trans.Start();
             var el = doc.GetElement(elementId);
             if(el != null) el.Pinned = false;
             trans.CommitChecked();
             return new { status = "success", element_id = elementId.Value, pinned = false };
        }
    }

    // ==================== BATCH 3: WORKSHARING IMPL ====================
    
    [BridgeCommand("revit.sync_to_central", IsMutating = true)]
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

    [BridgeCommand("revit.relinquish_all", IsMutating = true)]
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
    
    [BridgeCommand("revit.get_worksets", IsMutating = false)]
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

    [BridgeCommand("revit.create_schedule", IsMutating = true)]
    private static object ExecuteCreateSchedule(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var categoryName = payload.GetProperty("category_name").GetString();
        var name = payload.GetProperty("name").GetString();
        
        var category = GetCategoryByName(doc, categoryName);

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Schedule"))
        {
             trans.Start();
             var schedule = ViewSchedule.CreateSchedule(doc, category.Id);
             schedule.Name = name;
             trans.CommitChecked();
             
             return new { schedule_id = schedule.Id.Value, name = schedule.Name };
        }
    }
    
    [BridgeCommand("revit.get_schedule_data", IsMutating = false)]
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
    
    [BridgeCommand("revit.get_element_bounding_box", IsMutating = false)]
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
    
    [BridgeCommand("revit.get_phases", IsMutating = false)]
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

    [BridgeCommand("revit.get_phase_filters", IsMutating = false)]
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

    [BridgeCommand("revit.get_design_options", IsMutating = false)]
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

    [BridgeCommand("revit.create_group", IsMutating = true)]
    private static object ExecuteCreateGroup(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementIds = payload.GetProperty("element_ids").EnumerateArray()
            .Select(x => new ElementId((long)x.GetInt32()))
            .ToList();
        var name = payload.TryGetProperty("name", out var n) ? n.GetString() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Group"))
        {
             trans.Start();
             var group = doc.Create.NewGroup(elementIds);
             if (!string.IsNullOrEmpty(name))
             {
                 group.GroupType.Name = name;
             }
             trans.CommitChecked();
             
             return new { group_id = group.Id.Value, name = group.GroupType.Name };
        }
    }

    [BridgeCommand("revit.ungroup", IsMutating = true)]
    private static object ExecuteUngroup(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var groupId = new ElementId((long)payload.GetProperty("group_id").GetInt32());

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Ungroup"))
        {
             trans.Start();
             var group = doc.GetElement(groupId) as Group;
             if (group == null) throw new ArgumentException("Group not found");
             
             var memberIds = group.UngroupMembers().Select(id => id.Value).ToList();
             trans.CommitChecked();
             
             return new { status = "success", ungrouped_count = memberIds.Count, member_ids = memberIds };
        }
    }

    [BridgeCommand("revit.get_group_members", IsMutating = false)]
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

    [BridgeCommand("revit.get_rvt_links", IsMutating = false)]
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

    [BridgeCommand("revit.get_link_instances", IsMutating = false)]
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

    [BridgeCommand("revit.create_cable_tray", IsMutating = true)]
    private static object ExecuteCreateCableTray(UIApplication app, JsonElement payload)
    {
        // TODO: Revit 2024 API compatibility issue - CableTrayType is inaccessible
        // Use Universal Bridge instead: revit.invoke_method with class_name="Autodesk.Revit.DB.Electrical.CableTray"
        return new {
            status = "not_implemented",
            message = "CableTray creation not available in Revit 2024 API. Use Universal Bridge (revit.invoke_method) instead."
        };
    }

    [BridgeCommand("revit.create_conduit", IsMutating = true)]
    private static object ExecuteCreateConduit(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var startPoint = ParseXYZ(payload.GetProperty("start_point"));
        var endPoint = ParseXYZ(payload.GetProperty("end_point"));
        var levelName = payload.GetProperty("level").GetString();
        var diameter = payload.TryGetProperty("diameter", out var d) ? d.GetDouble() : 0.75 / 12.0; // Default 0.75 inches
        var conduitTypeName = payload.TryGetProperty("conduit_type", out var ct) ? ct.GetString() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Conduit"))
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

            trans.CommitChecked();

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

    [BridgeCommand("revit.get_mep_systems", IsMutating = false)]
    private static object ExecuteGetMepSystems(UIApplication app, JsonElement payload)
    {
        // TODO: Revit 2024 API compatibility issue - MEPSystem.IsWellConnected not available
        // Use Universal Bridge instead for advanced MEP queries
        return new {
            status = "not_implemented",
            message = "MEP system queries not available in Revit 2024 API. Use Universal Bridge (revit.invoke_method) instead."
        };
    }

    [BridgeCommand("revit.check_clashes", IsMutating = false)]
    private static object ExecuteCheckClashes(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var category1Name = payload.GetProperty("category1").GetString();
        var category2Name = payload.GetProperty("category2").GetString();
        var tolerance = payload.TryGetProperty("tolerance", out var tol) && tol.ValueKind == JsonValueKind.Number
            ? tol.GetDouble() : 0.01; // Default 0.01 ft
        // Budgets keep a big model from holding the Revit UI thread; the bridge itself waits only 30 s.
        var maxPairs = payload.TryGetProperty("max_pairs", out var mp) && mp.ValueKind == JsonValueKind.Number
            ? Math.Max(1L, Math.Min(mp.GetInt64(), 100000000L)) : 200_000L;
        var timeBudgetS = payload.TryGetProperty("time_budget_s", out var tb) && tb.ValueKind == JsonValueKind.Number
            ? Math.Max(0.5, Math.Min(tb.GetDouble(), 25.0)) : 20.0;
        var clock = System.Diagnostics.Stopwatch.StartNew();

        // Get built-in categories
        var cat1 = GetBuiltInCategoryByName(category1Name);
        var cat2 = GetBuiltInCategoryByName(category2Name);
        var sameCategory = cat1 == cat2;

        // Cache each element's bounding box once, outside the pair loop (elements without one cannot clash).
        var list1 = CollectClashCandidates(doc, cat1);
        var list2 = sameCategory ? list1 : CollectClashCandidates(doc, cat2);
        // Sorted by MinX so a sweep over list2 can stop as soon as MinX passes the expanded box.
        var sorted2 = list2.OrderBy(c => c.MinX).ToArray();

        var clashes = new List<object>();
        var nameCache = new Dictionary<long, (string? Name, string? Category)>();
        (string? Name, string? Category) Describe(Element e)
        {
            if (!nameCache.TryGetValue(e.Id.Value, out var info))
            {
                info = (e.Name, e.Category?.Name);
                nameCache[e.Id.Value] = info;
            }
            return info;
        }

        long pairsExamined = 0;
        int firstChecked = 0;
        string? truncatedReason = null;

        foreach (var a in list1)
        {
            if (truncatedReason != null) break;
            if (clock.Elapsed.TotalSeconds >= timeBudgetS) { truncatedReason = "time_budget_s"; break; }
            firstChecked++;
            var loX = a.MinX - tolerance; var hiX = a.MaxX + tolerance;
            var loY = a.MinY - tolerance; var hiY = a.MaxY + tolerance;
            var loZ = a.MinZ - tolerance; var hiZ = a.MaxZ + tolerance;

            foreach (var b in sorted2)
            {
                if (b.MinX > hiX) break; // everything after this starts beyond the box
                if (pairsExamined >= maxPairs) { truncatedReason = "max_pairs"; break; }
                if ((pairsExamined & 1023) == 0 && clock.Elapsed.TotalSeconds >= timeBudgetS)
                {
                    truncatedReason = "time_budget_s";
                    break;
                }
                pairsExamined++;

                if (a.Element.Id == b.Element.Id) continue;
                // One category against itself: report each pair once.
                if (sameCategory && a.Element.Id.Value > b.Element.Id.Value) continue;
                if (b.MaxX < loX || b.MinY > hiY || b.MaxY < loY || b.MinZ > hiZ || b.MaxZ < loZ) continue;

                var d1 = Describe(a.Element);
                var d2 = Describe(b.Element);
                clashes.Add(new
                {
                    element1_id = a.Element.Id.Value,
                    element1_name = d1.Name,
                    element1_category = d1.Category,
                    element2_id = b.Element.Id.Value,
                    element2_name = d2.Name,
                    element2_category = d2.Category,
                    clash_type = "bounding_box_intersection"
                });
            }
        }

        var truncated = truncatedReason != null;
        return new
        {
            clashes,
            clash_count = clashes.Count,
            category1 = category1Name,
            category2 = category2Name,
            tolerance_ft = tolerance,
            elements_checked_cat1 = list1.Count,
            elements_checked_cat2 = list2.Count,
            truncated,
            truncated_reason = truncatedReason,
            pairs_examined = pairsExamined,
            elements_of_cat1_examined = firstChecked,
            max_pairs = maxPairs,
            time_budget_s = timeBudgetS,
            elapsed_s = Math.Round(clock.Elapsed.TotalSeconds, 2),
            note = truncated
                ? "Budget reached: the clash list is partial. Narrow the categories or raise max_pairs / time_budget_s."
                : null
        };
    }

    private sealed class ClashCandidate
    {
        public Element Element = null!;
        public double MinX, MinY, MinZ, MaxX, MaxY, MaxZ;
    }

    private static List<ClashCandidate> CollectClashCandidates(Document doc, BuiltInCategory category)
    {
        var list = new List<ClashCandidate>();
        foreach (var element in new FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType())
        {
            var bb = element.get_BoundingBox(null);
            if (bb == null) continue;
            list.Add(new ClashCandidate
            {
                Element = element,
                MinX = bb.Min.X, MinY = bb.Min.Y, MinZ = bb.Min.Z,
                MaxX = bb.Max.X, MaxY = bb.Max.Y, MaxZ = bb.Max.Z
            });
        }
        return list;
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
            "structural_columns" => BuiltInCategory.OST_StructuralColumns,
            "beams" => BuiltInCategory.OST_StructuralFraming,
            "structural_framing" => BuiltInCategory.OST_StructuralFraming,
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
            "rooms" => BuiltInCategory.OST_Rooms,
            "ceilings" => BuiltInCategory.OST_Ceilings,
            "stairs" => BuiltInCategory.OST_Stairs,
            "railings" => BuiltInCategory.OST_Railings,
            "curtain_walls" => BuiltInCategory.OST_Walls,
            "generic_models" => BuiltInCategory.OST_GenericModel,
            "specialty_equipment" => BuiltInCategory.OST_SpecialityEquipment,
            "mass" => BuiltInCategory.OST_Mass,
            _ => throw new ArgumentException($"Unknown category: '{categoryName}'. Supported: walls, floors, roofs, doors, windows, columns, structural_columns, beams, rooms, ceilings, stairs, railings, furniture, mechanical_equipment, electrical_equipment, plumbing_fixtures, ducts, pipes, cable_trays, conduits, generic_models")
        };
    }

    // ==================== BATCH 6: MATERIALS & VISUALS ====================

    [BridgeCommand("revit.create_material", IsMutating = true)]
    private static object ExecuteCreateMaterial(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var name = payload.GetProperty("name").GetString();
        var color = payload.TryGetProperty("color", out var c) ? ParseColor(c) : new Color(128, 128, 128);
        var transparency = payload.TryGetProperty("transparency", out var t) ? t.GetInt32() : 0;
        var shininess = payload.TryGetProperty("shininess", out var s) ? s.GetInt32() : 50;
        var smoothness = payload.TryGetProperty("smoothness", out var sm) ? sm.GetInt32() : 50;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Material"))
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

            trans.CommitChecked();

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

    [BridgeCommand("revit.set_element_material", IsMutating = true)]
    private static object ExecuteSetElementMaterial(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = new ElementId((long)payload.GetProperty("element_id").GetInt32());
        var materialName = payload.GetProperty("material_name").GetString();
        var faceIndex = payload.TryGetProperty("face_index", out var fi) ? (int?)fi.GetInt32() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Set Element Material"))
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
                                    trans.CommitChecked();
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

            trans.CommitChecked();

            return new
            {
                element_id = elementId.Value,
                material_id = material.Id.Value,
                material_name = material.Name,
                method = "parameter"
            };
        }
    }

    [BridgeCommand("revit.get_render_settings", IsMutating = false)]
    private static object ExecuteGetRenderSettings(UIApplication app)
    {
        // TODO: Revit 2024 API compatibility issue - RenderingSettings API changed
        // Use Universal Bridge instead for render settings access
        return new {
            status = "not_implemented",
            message = "Rendering settings API not available in Revit 2024. Use Universal Bridge (revit.invoke_method) instead."
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

    [BridgeCommand("revit.convert_to_group", IsMutating = true)]
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

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Group"))
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

            trans.CommitChecked();

            return new
            {
                group_id = group.Id.Value,
                group_name = group.Name,
                group_type_name = group.GroupType.Name,
                member_count = elementIds.Count
            };
        }
    }

    [BridgeCommand("revit.edit_family", IsMutating = true)]
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
            categories = familyDoc.Settings.Categories.Cast<Category>().Select(c => c.Name).Take(10).ToList()
        };
    }

    // ==================== BATCH 8: HIGH-VALUE DOCUMENTATION & ANALYSIS ====================

    [BridgeCommand("revit.create_dimension", IsMutating = true)]
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
        
        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Create Dimension"))
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
            
            trans.CommitChecked();

            return new { dimension_id = dim.Id.Value, value_ft = dim.Value, value_string = dim.ValueString };
        }
    }

    [BridgeCommand("revit.create_revision_cloud", IsMutating = true)]
    private static object ExecuteCreateRevisionCloud(UIApplication app, JsonElement payload)
    {
        // TODO: Revit 2024 API compatibility issue - RevisionCloud.Create signature changed
        // Use Universal Bridge instead for revision cloud creation
        return new {
            status = "not_implemented",
            message = "Revision cloud creation API changed in Revit 2024. Use Universal Bridge (revit.invoke_method) instead."
        };
    }

    [BridgeCommand("revit.get_revision_sequences", IsMutating = false)]
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
                issued = false // TODO: PROJECT_REVISION_ISSUED not available in Revit 2024
            })
            .OrderBy(x => x.sequence)
            .ToList();

        return new { revisions, count = revisions.Count };
    }

    [BridgeCommand("revit.tag_all_in_view", IsMutating = true)]
    private static object ExecuteTagAllInView(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");
        
        var categoryName = payload.GetProperty("category").GetString();
        var category = GetBuiltInCategoryByName(categoryName);
        var view = doc.ActiveView;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Tag All Not Tagged"))
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

            trans.CommitChecked();
            return new { tagged_count = taggedCount, view_name = view.Name, category = categoryName };
        }
    }

    [BridgeCommand("revit.create_text_type", IsMutating = true)]
    private static object ExecuteCreateTextType(UIApplication app, JsonElement payload)
    {
        // TODO: Revit 2024 API compatibility issue - TEXT_FONT_TYPE_NAME parameter not found
        // Use Universal Bridge instead for text type creation
        return new {
            status = "not_implemented",
            message = "Text type creation parameters changed in Revit 2024. Use Universal Bridge (revit.invoke_method) instead."
        };
    }

    [BridgeCommand("revit.get_view_templates", IsMutating = false)]
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

    [BridgeCommand("revit.apply_view_template", IsMutating = true)]
    private static object ExecuteApplyViewTemplate(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var viewId = new ElementId((long)payload.GetProperty("view_id").GetInt32());
        var templateId = new ElementId((long)payload.GetProperty("template_id").GetInt32());

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, "Apply View Template"))
        {
            trans.Start();

            var view = doc.GetElement(viewId) as View;
            var template = doc.GetElement(templateId) as View;

            if (view == null) throw new ArgumentException("View not found");
            if (template == null || !template.IsTemplate) throw new ArgumentException("Template not found or not a template");

            view.ViewTemplateId = templateId;
            trans.CommitChecked();

            return new { view_id = viewId.Value, template_name = template.Name, status = "applied" };
        }
    }

    [BridgeCommand("revit.calculate_material_quantities", IsMutating = true)]
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

    [BridgeCommand("revit.get_room_boundary", IsMutating = false)]
    private static object ExecuteGetRoomBoundary(UIApplication app, JsonElement payload)
    {
        // TODO: Revit 2024 API compatibility issue - Room type not found (namespace issue)
        // Use Universal Bridge instead for room boundary queries
        return new {
            status = "not_implemented",
            message = "Room boundary API not available in Revit 2024. Use Universal Bridge (revit.invoke_method) instead."
        };
    }

    [BridgeCommand("revit.get_project_location", IsMutating = false)]
    private static object ExecuteGetProjectLocation(UIApplication app)
    {
        // TODO: Revit 2024 API compatibility issue - ProjectLocation.SiteName not available
        // Use Universal Bridge instead for project location queries
        return new {
            status = "not_implemented",
            message = "Project location API changed in Revit 2024. Use Universal Bridge (revit.invoke_method) instead."
        };
    }

    [BridgeCommand("revit.get_warnings", IsMutating = false)]
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

    [BridgeCommand("revit.invoke_method", IsMutating = true)]
    private static object ExecuteInvokeMethod(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        string className = payload.GetProperty("class_name").GetString();
        string methodName = payload.GetProperty("method_name").GetString();
        JsonElement args = payload.GetProperty("arguments");
        string targetId = payload.TryGetProperty("target_id", out var t) ? t.GetString() : null;

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, $"Invoke {methodName}"))
        {
            if (payload.TryGetProperty("use_transaction", out var ut) && ut.GetBoolean())
                trans.Start();
            
            try
            {
                object result = ReflectionHelper.InvokeMethod(doc, className, methodName, args, targetId);
                
                if (trans.GetStatus() == TransactionStatus.Started)
                    trans.CommitChecked();
                    
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

    [BridgeCommand("revit.reflect_get", IsMutating = true)]
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

    [BridgeCommand("revit.reflect_set", IsMutating = true)]
    private static object ExecuteReflectSet(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        string targetId = payload.GetProperty("target_id").GetString();
        string propertyName = payload.GetProperty("property_name").GetString();
        JsonElement valueElement = payload.GetProperty("value");

        using (var trans = BridgeCommandFactory.CreateTransaction(doc, $"Set {propertyName}"))
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
            trans.CommitChecked();
        }

        return new { status = "success", target_id = targetId, property = propertyName };
    }

    // ==================== BATCH 10: LLM POWER TOOLS ====================

    [BridgeCommand("revit.execute_python", IsMutating = true)]
    private static object ExecuteExecutePython(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var script = payload.GetProperty("script").GetString() ?? "";
        string? mode = payload.TryGetProperty("mode", out var modeProp) && modeProp.ValueKind == JsonValueKind.String
            ? modeProp.GetString()
            : null;

        // Engine, scope, read-mode guard and progress() live in PythonScriptRunner.cs / PythonEngineFactory.cs.
        return PythonScriptRunner.Run(app, doc, script, mode);
    }

    [BridgeCommand("revit.change_element_type", IsMutating = true)]
    private static object ExecuteChangeElementType(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var sourceTypeId = new ElementId(payload.GetProperty("source_type_id").GetInt64());
        var targetTypeId = new ElementId(payload.GetProperty("target_type_id").GetInt64());

        // Validate that target type exists
        if (doc.GetElement(targetTypeId) == null)
            return new { success = false, error = $"Target type ID {targetTypeId.Value} not found", error_code = "TYPE_NOT_FOUND", changed = 0, failed = 0, failed_ids = new List<long>() };

        var collector = new FilteredElementCollector(doc).WhereElementIsNotElementType();

        if (payload.TryGetProperty("category", out var catProp) && catProp.ValueKind != JsonValueKind.Null)
        {
            var bic = GetBuiltInCategoryByName(catProp.GetString()!);
            collector = collector.OfCategory(bic);
        }

        var elements = collector.Where(e => e.GetTypeId() == sourceTypeId).ToList();

        int changed = 0, failed = 0;
        var failedIds = new List<long>();

        using (var tx = BridgeCommandFactory.CreateTransaction(doc, "MCP: Change Element Type"))
        {
            tx.Start();
            foreach (var el in elements)
            {
                try
                {
                    el.ChangeTypeId(targetTypeId);
                    changed++;
                }
                catch
                {
                    failedIds.Add(el.Id.Value);
                    failed++;
                }
            }
            tx.CommitChecked();
        }

        return new { success = true, changed, failed, failed_ids = failedIds };
    }

    [BridgeCommand("revit.get_elements_by_type", IsMutating = false)]
    private static object ExecuteGetElementsByType(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        int offset = payload.TryGetProperty("offset", out var oProp) ? oProp.GetInt32() : 0;
        int limit  = payload.TryGetProperty("limit",  out var lProp) ? lProp.GetInt32() : 200;
        limit = Math.Min(limit, 500); // Hard cap to prevent response bloat

        var collector = new FilteredElementCollector(doc).WhereElementIsNotElementType();

        // Optional category filter (applied at collector level for best performance)
        if (payload.TryGetProperty("category", out var catProp) && catProp.ValueKind != JsonValueKind.Null)
        {
            var bic = GetBuiltInCategoryByName(catProp.GetString()!);
            collector = collector.OfCategory(bic);
        }

        IEnumerable<Element> query = collector;

        // Optional type_id filter
        if (payload.TryGetProperty("type_id", out var typeProp) && typeProp.ValueKind != JsonValueKind.Null)
        {
            var typeId = new ElementId(typeProp.GetInt64());
            query = query.Where(e => e.GetTypeId() == typeId);
        }

        // Optional level filter
        if (payload.TryGetProperty("level", out var lvlProp) && lvlProp.ValueKind != JsonValueKind.Null)
        {
            var levelName = lvlProp.GetString();
            var level = new FilteredElementCollector(doc)
                .OfClass(typeof(Level)).Cast<Level>()
                .FirstOrDefault(lv => lv.Name.Equals(levelName, StringComparison.OrdinalIgnoreCase));
            if (level != null)
                query = query.Where(e => e.LevelId == level.Id);
        }

        // Which fields to return (null = default set)
        HashSet<string>? fields = null;
        if (payload.TryGetProperty("fields", out var fieldsProp) && fieldsProp.ValueKind == JsonValueKind.Array)
            fields = fieldsProp.EnumerateArray().Select(f => f.GetString()!).ToHashSet(StringComparer.OrdinalIgnoreCase);

        var allElements = query.ToList();
        int total = allElements.Count;
        var page = allElements.Skip(offset).Take(limit);

        var elements = page.Select(el =>
        {
            var d = new Dictionary<string, object?> { ["id"] = el.Id.Value };

            bool want(string f) => fields == null || fields.Contains(f);

            if (want("name"))     d["name"]     = el.Name ?? "";
            if (want("category")) d["category"] = el.Category?.Name ?? "";
            if (want("type_id"))  d["type_id"]  = el.GetTypeId()?.Value ?? -1;
            if (want("level"))
            {
                d["level"] = (el.LevelId != null && el.LevelId != ElementId.InvalidElementId)
                    ? doc.GetElement(el.LevelId)?.Name ?? ""
                    : "";
            }
            if (want("length"))
            {
                var p = el.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
                     ?? el.get_Parameter(BuiltInParameter.INSTANCE_LENGTH_PARAM);
                d["length"] = p?.AsDouble();
            }
            if (want("area"))
            {
                var p = el.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED);
                d["area"] = p?.AsDouble();
            }
            if (want("volume"))
            {
                var p = el.get_Parameter(BuiltInParameter.HOST_VOLUME_COMPUTED);
                d["volume"] = p?.AsDouble();
            }
            return d;
        }).ToList();

        return new
        {
            total,
            returned = elements.Count,
            offset,
            limit,
            truncated = total > offset + limit,
            elements
        };
    }

    [BridgeCommand("revit.batch_set_parameters_by_filter", IsMutating = true)]
    private static object ExecuteBatchSetParametersByFilter(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var parameterName = payload.GetProperty("parameter_name").GetString()!;
        var value = payload.GetProperty("value");

        if (!payload.TryGetProperty("filter", out var filter) || filter.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("Missing or invalid 'filter' object");

        var collector = new FilteredElementCollector(doc).WhereElementIsNotElementType();

        if (filter.TryGetProperty("category", out var catProp) && catProp.ValueKind != JsonValueKind.Null)
        {
            var bic = GetBuiltInCategoryByName(catProp.GetString()!);
            collector = collector.OfCategory(bic);
        }

        IEnumerable<Element> query = collector;

        if (filter.TryGetProperty("type_id", out var typeProp) && typeProp.ValueKind != JsonValueKind.Null)
        {
            var typeId = new ElementId(typeProp.GetInt64());
            query = query.Where(e => e.GetTypeId() == typeId);
        }

        if (filter.TryGetProperty("level", out var lvlProp) && lvlProp.ValueKind != JsonValueKind.Null)
        {
            var levelName = lvlProp.GetString();
            var level = new FilteredElementCollector(doc)
                .OfClass(typeof(Level)).Cast<Level>()
                .FirstOrDefault(lv => lv.Name.Equals(levelName, StringComparison.OrdinalIgnoreCase));
            if (level != null)
                query = query.Where(e => e.LevelId == level.Id);
        }

        if (filter.TryGetProperty("parameter_filter", out var pf) && pf.ValueKind != JsonValueKind.Null)
        {
            var filterName  = pf.GetProperty("name").GetString()!;
            var filterValue = pf.GetProperty("value").ToString();
            query = query.Where(e =>
            {
                var p = e.LookupParameter(filterName);
                return p != null && GetParameterValueAsString(p) == filterValue;
            });
        }

        var elements = query.ToList();
        int updated = 0, failed = 0;

        using (var tx = BridgeCommandFactory.CreateTransaction(doc, "MCP: Batch Set Parameters by Filter"))
        {
            tx.Start();
            foreach (var el in elements)
            {
                try
                {
                    var param = el.LookupParameter(parameterName);
                    if (param == null || param.IsReadOnly) { failed++; continue; }
                    SetParameterValue(param, value);
                    updated++;
                }
                catch
                {
                    failed++;
                }
            }
            tx.CommitChecked();
        }

        return new { success = true, updated, failed, total = elements.Count };
    }

    [BridgeCommand("revit.replace_family_type", IsMutating = true)]
    private static object ExecuteReplaceFamilyType(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var oldFamily = payload.GetProperty("old_family").GetString()!;
        var oldType   = payload.GetProperty("old_type").GetString()!;
        var newFamily = payload.GetProperty("new_family").GetString()!;
        var newType   = payload.GetProperty("new_type").GetString()!;

        var allSymbols = new FilteredElementCollector(doc)
            .OfClass(typeof(FamilySymbol))
            .Cast<FamilySymbol>()
            .ToList();

        var oldSymbol = allSymbols.FirstOrDefault(fs =>
            fs.FamilyName.Equals(oldFamily, StringComparison.OrdinalIgnoreCase) &&
            fs.Name.Equals(oldType, StringComparison.OrdinalIgnoreCase));

        if (oldSymbol == null)
            return new { success = false, error = $"Source family type '{oldFamily} / {oldType}' not found in document", error_code = "TYPE_NOT_FOUND", changed = 0, failed = 0, failed_ids = new List<long>() };

        var newSymbol = allSymbols.FirstOrDefault(fs =>
            fs.FamilyName.Equals(newFamily, StringComparison.OrdinalIgnoreCase) &&
            fs.Name.Equals(newType, StringComparison.OrdinalIgnoreCase));

        if (newSymbol == null)
            return new { success = false, error = $"Target family type '{newFamily} / {newType}' not found in document", error_code = "TYPE_NOT_FOUND", changed = 0, failed = 0, failed_ids = new List<long>() };

        var instances = new FilteredElementCollector(doc)
            .WhereElementIsNotElementType()
            .Where(e => e.GetTypeId() == oldSymbol.Id)
            .ToList();

        int changed = 0, failed = 0;
        var failedIds = new List<long>();

        using (var tx = BridgeCommandFactory.CreateTransaction(doc, "MCP: Replace Family Type"))
        {
            tx.Start();
            if (!newSymbol.IsActive)
                newSymbol.Activate();
            foreach (var inst in instances)
            {
                try
                {
                    inst.ChangeTypeId(newSymbol.Id);
                    changed++;
                }
                catch
                {
                    failedIds.Add(inst.Id.Value);
                    failed++;
                }
            }
            tx.CommitChecked();
        }

        return new { success = true, changed, failed, failed_ids = failedIds };
    }

    [BridgeCommand("revit.get_element_geometry", IsMutating = false)]
    private static object ExecuteGetElementGeometry(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null) throw new InvalidOperationException("No active document");

        var elementId = payload.GetProperty("element_id").GetInt64();
        var element = doc.GetElement(new ElementId(elementId));
        if (element == null)
            return new { success = false, error = $"Element {elementId} not found", error_code = "ELEMENT_NOT_FOUND" };

        // Bounding box
        object? bbObj = null;
        var bb = element.get_BoundingBox(null);
        if (bb != null)
            bbObj = new
            {
                min = new { x = Math.Round(bb.Min.X, 6), y = Math.Round(bb.Min.Y, 6), z = Math.Round(bb.Min.Z, 6) },
                max = new { x = Math.Round(bb.Max.X, 6), y = Math.Round(bb.Max.Y, 6), z = Math.Round(bb.Max.Z, 6) }
            };

        // Location
        string locationType = "none";
        object? point = null, start = null, end = null;
        double? curveLength = null;

        var location = element.Location;
        if (location is LocationPoint lp)
        {
            locationType = "point";
            point = new { x = Math.Round(lp.Point.X, 6), y = Math.Round(lp.Point.Y, 6), z = Math.Round(lp.Point.Z, 6) };
        }
        else if (location is LocationCurve lc)
        {
            locationType = "curve";
            var p0 = lc.Curve.GetEndPoint(0);
            var p1 = lc.Curve.GetEndPoint(1);
            start = new { x = Math.Round(p0.X, 6), y = Math.Round(p0.Y, 6), z = Math.Round(p0.Z, 6) };
            end   = new { x = Math.Round(p1.X, 6), y = Math.Round(p1.Y, 6), z = Math.Round(p1.Z, 6) };
            curveLength = Math.Round(lc.Curve.Length, 6);
        }

        // Level
        string? levelName = null;
        if (element.LevelId != null && element.LevelId != ElementId.InvalidElementId)
            levelName = doc.GetElement(element.LevelId)?.Name;

        // Common quantity parameters
        var areaParam   = element.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED);
        var volParam    = element.get_Parameter(BuiltInParameter.HOST_VOLUME_COMPUTED);
        var lenParam    = element.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
                       ?? element.get_Parameter(BuiltInParameter.INSTANCE_LENGTH_PARAM);

        return new
        {
            success = true,
            element_id = elementId,
            element_type = element.GetType().Name,
            element_name = element.Name,
            location_type = locationType,
            point,
            start,
            end,
            length = curveLength ?? lenParam?.AsDouble(),
            bounding_box = bbObj,
            level = levelName,
            area   = areaParam?.AsDouble(),
            volume = volParam?.AsDouble()
        };
    }

    // Defaults keep a snapshot well inside the bridge's 30 s request limit. A big model is captured in
    // scoped pieces (categories, max_elements), never as one unbounded pass on Revit's UI thread.
    private const int SnapshotDefaultMaxElements = 5000;
    private const int SnapshotDefaultBudgetMs = 20000;

    private static int ReadSnapshotInt(JsonElement payload, string name, int fallback, int min, int max)
        => PayloadJson.ClampedInt(payload, name, fallback, min, max);

    private static List<BuiltInCategory> ReadSnapshotCategories(JsonElement payload, List<string> unknown)
    {
        var result = new List<BuiltInCategory>();
        if (payload.ValueKind != JsonValueKind.Object || !payload.TryGetProperty("categories", out var arr)
            || arr.ValueKind != JsonValueKind.Array)
        {
            return result;
        }

        foreach (var item in arr.EnumerateArray())
        {
            var name = item.ValueKind == JsonValueKind.String ? item.GetString() : null;
            if (string.IsNullOrWhiteSpace(name)) continue;
            var key = name!.Trim();
            if (!key.StartsWith("OST_", StringComparison.OrdinalIgnoreCase)) key = "OST_" + key;
            if (Enum.TryParse(key, true, out BuiltInCategory bic)) result.Add(bic);
            else unknown.Add(name);
        }

        return result;
    }

    // Area / volume / perimeter values are computed from geometry on first read. Reading them for every
    // element of a large model is what made Revit stop responding (journal: "reducing faceting tolerance
    // for volume/area computation"). Rooms/spaces keep theirs: those are cheap and the QA rules need them.
    private static readonly HashSet<BuiltInParameter> SnapshotHeavyBuiltIns = new HashSet<BuiltInParameter>
    {
        BuiltInParameter.HOST_AREA_COMPUTED,
        BuiltInParameter.HOST_VOLUME_COMPUTED,
        BuiltInParameter.HOST_PERIMETER_COMPUTED,
    };

    private static bool IsHeavySnapshotParameter(Element elem, Parameter param)
    {
        if (param.StorageType != StorageType.Double || elem is Autodesk.Revit.DB.SpatialElement) return false;
        try
        {
            var id = param.Id.Value;
            if (id < 0 && id > int.MinValue && SnapshotHeavyBuiltIns.Contains((BuiltInParameter)(int)id)) return true;
            var dataType = param.Definition.GetDataType();
            return dataType == SpecTypeId.Area || dataType == SpecTypeId.Volume;
        }
        catch
        {
            return false;
        }
    }

    [BridgeCommand("revit.extract_snapshot", IsMutating = false)]
    private static object ExecuteExtractSnapshot(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var clock = System.Diagnostics.Stopwatch.StartNew();
        bool dirtyOnly = payload.ValueKind == JsonValueKind.Object &&
                         payload.TryGetProperty("dirty_only", out var dirtyProp) &&
                         dirtyProp.ValueKind == JsonValueKind.True;
        var maxElements = ReadSnapshotInt(payload, "max_elements", SnapshotDefaultMaxElements, 1, 200000);
        var budgetMs = ReadSnapshotInt(payload, "time_budget_ms", SnapshotDefaultBudgetMs, 1000, 25000);
        var unknownCategories = new List<string>();
        var categories = ReadSnapshotCategories(payload, unknownCategories);
        string snapshotId = Guid.NewGuid().ToString("N");

        var workspaceDir = WorkspaceDirectory.Resolve();
        var snapshotDir = Path.Combine(workspaceDir, "snapshots");
        Directory.CreateDirectory(snapshotDir);
        var snapshotPath = Path.Combine(snapshotDir, $"{snapshotId}.json");

        // Ids first: no element objects are built until they are actually written.
        var idsToExtract = new List<ElementId>();
        var dirtyIds = DocumentDirtyTracker.GetDirtyUniqueIds();

        if (dirtyOnly)
        {
            foreach (var uid in dirtyIds)
            {
                if (uid.StartsWith("deleted:")) continue;
                try
                {
                    var elem = doc.GetElement(uid);
                    if (elem != null) idsToExtract.Add(elem.Id);
                }
                catch { }
            }
        }
        else if (categories.Count > 0)
        {
            idsToExtract.AddRange(new FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .WherePasses(new ElementMulticategoryFilter(categories))
                .ToElementIds());
        }
        else
        {
            var classes = new List<Type>
            {
                typeof(FamilyInstance), typeof(Wall), typeof(Floor), typeof(RoofBase),
                typeof(Level), typeof(Grid), typeof(ViewSheet), typeof(ViewDrafting)
            };
            var classFilter = new ElementMulticlassFilter(classes);
            var roomFilter = new ElementCategoryFilter(BuiltInCategory.OST_Rooms);
            idsToExtract.AddRange(new FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .WherePasses(new LogicalOrFilter(classFilter, roomFilter))
                .ToElementIds());
        }

        var totalCandidates = idsToExtract.Count;
        var truncated = false;
        var skippedHeavy = 0;
        var elementRecords = new List<object>();
        foreach (var id in idsToExtract)
        {
            if (elementRecords.Count >= maxElements || clock.ElapsedMilliseconds > budgetMs)
            {
                truncated = true;
                break;
            }

            var elem = doc.GetElement(id);
            if (elem == null || string.IsNullOrEmpty(elem.UniqueId)) continue;

            Element? typeElem = null;
            try { typeElem = doc.GetElement(elem.GetTypeId()); } catch { }

            var paramsDict = new Dictionary<string, object>();
            foreach (Parameter param in elem.Parameters)
            {
                if (!param.HasValue) continue;
                if (IsHeavySnapshotParameter(elem, param)) { skippedHeavy++; continue; }

                object val = param.StorageType switch
                {
                    StorageType.Integer => param.AsInteger(),
                    StorageType.Double => param.AsDouble(),
                    StorageType.String => param.AsString() ?? string.Empty,
                    StorageType.ElementId => param.AsElementId().Value.ToString(),
                    _ => string.Empty
                };

                paramsDict[param.Definition.Name] = new
                {
                    v = val,
                    storage = param.StorageType.ToString(),
                    instance = true,
                    @readonly = param.IsReadOnly
                };
            }

            string catName = elem.Category?.BuiltInCategory.ToString() ?? elem.Category?.Name ?? "None";

            elementRecords.Add(new
            {
                uid = elem.UniqueId,
                amb_uid = elem.UniqueId,
                element_id = elem.Id.Value,
                category = catName,
                @class = elem.GetType().Name,
                type_uid = elem.GetTypeId().Value.ToString(),
                family = typeElem?.get_Parameter(BuiltInParameter.ALL_MODEL_FAMILY_NAME)?.AsString() ?? typeElem?.Name ?? string.Empty,
                type_name = typeElem?.Name ?? string.Empty,
                level_uid = (elem as FamilyInstance)?.LevelId.Value.ToString() ?? (elem as Wall)?.LevelId.Value.ToString() ?? string.Empty,
                // The QA rules (door_no_host, window_no_host) test host_uid. Without it every hosted door
                // was reported as unhosted (1,006 false errors on a real model).
                host_uid = (elem as FamilyInstance)?.Host?.UniqueId,
                @params = paramsDict
            });
        }

        var deletedIdsList = dirtyOnly
            ? dirtyIds.Where(id => id.StartsWith("deleted:")).Select(id => id.Substring(8)).ToList()
            : new List<string>();

        // Coverage travels with the snapshot (in "counts") so a partial capture can never be mistaken
        // for the whole model by the QA and parameter tools that read the file later.
        var counts = new Dictionary<string, object>
        {
            ["candidates"] = totalCandidates,
            ["captured"] = elementRecords.Count,
            ["truncated"] = truncated,
            ["max_elements"] = maxElements,
            ["time_budget_ms"] = budgetMs,
            ["elapsed_ms"] = clock.ElapsedMilliseconds,
            ["skipped_area_volume_values"] = skippedHeavy,
            ["categories"] = categories.Select(c => c.ToString()).ToList(),
        };

        var snapshot = new
        {
            schema = "amb.snapshot/1",
            snapshot_id = snapshotId,
            taken_at = DateTime.UtcNow.ToString("o"),
            source = new
            {
                app = "revit",
                app_version = app.Application.VersionNumber,
                doc_guid = doc.ProjectInformation?.UniqueId ?? doc.Title,
                doc_title = doc.Title,
                units = "SI"
            },
            elements = elementRecords,
            counts,
            deleted = deletedIdsList
        };

        var json = JsonSerializer.Serialize(snapshot, new JsonSerializerOptions { WriteIndented = false });
        File.WriteAllText(snapshotPath, json);

        return new
        {
            snapshot_id = snapshotId,
            path = snapshotPath,
            element_count = elementRecords.Count,
            deleted_count = deletedIdsList.Count,
            candidates = totalCandidates,
            truncated,
            elapsed_ms = clock.ElapsedMilliseconds,
            unknown_categories = unknownCategories,
            note = truncated
                ? $"Partial snapshot: {elementRecords.Count} of {totalCandidates} elements captured within the " +
                  $"{maxElements}-element / {budgetMs} ms limits. Pass 'categories' (for example [\"Doors\",\"Rooms\"]) " +
                  "or raise max_elements to capture what the check needs."
                : null
        };
    }

    [BridgeCommand("revit.get_snapshot_delta", IsMutating = false)]
    private static object ExecuteGetSnapshotDelta(UIApplication app, JsonElement payload)
    {
        var doc = app.ActiveUIDocument?.Document;
        if (doc == null)
            throw new InvalidOperationException("No active document");

        var dirtyIds = DocumentDirtyTracker.GetDirtyUniqueIds();
        
        var addedAndModified = new List<string>();
        var deleted = new List<string>();

        foreach (var id in dirtyIds)
        {
            if (id.StartsWith("deleted:"))
            {
                deleted.Add(id.Substring(8));
            }
            else
            {
                addedAndModified.Add(id);
            }
        }

        return new
        {
            added_or_modified = addedAndModified,
            deleted = deleted,
            count = dirtyIds.Count
        };
    }
}

