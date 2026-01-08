using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevitBridge.Commands.Core.Views
{
    /// <summary>
    /// Advanced view management commands
    /// View is #6 ranked API (Score: 283) - visualization foundation
    /// </summary>
    public static class ViewManagementCommands
    {
        #region 1. Create Ceiling Plan View

        public static object CreateCeilingPlanView(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string levelName = payload.GetProperty("level_name").GetString();
            string viewName = payload.TryGetProperty("view_name", out var vn) ? vn.GetString() : null;

            // Find level
            Level level = new FilteredElementCollector(doc)
                .OfClass(typeof(Level))
                .Cast<Level>()
                .FirstOrDefault(l => l.Name.Equals(levelName, StringComparison.OrdinalIgnoreCase));

            if (level == null)
            {
                throw new Exception($"Level '{levelName}' not found");
            }

            using (var trans = new Transaction(doc, "Create Ceiling Plan View"))
            {
                trans.Start();

                // Get ceiling plan view family type
                ViewFamilyType viewFamilyType = new FilteredElementCollector(doc)
                    .OfClass(typeof(ViewFamilyType))
                    .Cast<ViewFamilyType>()
                    .FirstOrDefault(vft => vft.ViewFamily == ViewFamily.CeilingPlan);

                if (viewFamilyType == null)
                {
                    throw new Exception("Ceiling Plan view family type not found");
                }

                ViewPlan ceilingPlan = ViewPlan.Create(doc, viewFamilyType.Id, level.Id);

                if (!string.IsNullOrEmpty(viewName))
                {
                    ceilingPlan.Name = viewName;
                }

                trans.Commit();

                return new
                {
                    success = true,
                    viewId = ceilingPlan.Id.IntegerValue,
                    viewName = ceilingPlan.Name,
                    levelName = levelName,
                    viewType = "CeilingPlan"
                };
            }
        }

        #endregion

        #region 2. Create Elevation View

        public static object CreateElevationView(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string viewName = payload.GetProperty("view_name").GetString();
            var markerPoint = payload.GetProperty("marker_point");

            XYZ point = new XYZ(
                markerPoint.GetProperty("x").GetDouble(),
                markerPoint.GetProperty("y").GetDouble(),
                markerPoint.GetProperty("z").GetDouble()
            );

            using (var trans = new Transaction(doc, "Create Elevation View"))
            {
                trans.Start();

                // Get elevation view family type
                ViewFamilyType viewFamilyType = new FilteredElementCollector(doc)
                    .OfClass(typeof(ViewFamilyType))
                    .Cast<ViewFamilyType>()
                    .FirstOrDefault(vft => vft.ViewFamily == ViewFamily.Elevation);

                if (viewFamilyType == null)
                {
                    throw new Exception("Elevation view family type not found");
                }

                // Create elevation marker
                ElevationMarker marker = ElevationMarker.CreateElevationMarker(doc, viewFamilyType.Id, point, 50);

                // Create elevation view (index 0 = North, 1 = East, 2 = South, 3 = West)
                ViewSection elevationView = marker.CreateElevation(doc, doc.ActiveView.Id, 0);
                elevationView.Name = viewName;

                trans.Commit();

                return new
                {
                    success = true,
                    viewId = elevationView.Id.IntegerValue,
                    viewName = elevationView.Name,
                    markerId = marker.Id.IntegerValue,
                    markerLocation = new { point.X, point.Y, point.Z },
                    viewType = "Elevation"
                };
            }
        }

        #endregion

        #region 3. Duplicate View

        public static object DuplicateView(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int viewId = payload.GetProperty("view_id").GetInt32();
            string duplicateOption = payload.TryGetProperty("duplicate_option", out var opt) ? opt.GetString() : "Duplicate";
            string newName = payload.TryGetProperty("new_name", out var nn) ? nn.GetString() : null;

            View view = doc.GetElement(new ElementId(viewId)) as View;
            if (view == null)
            {
                throw new Exception($"View {viewId} not found");
            }

            ViewDuplicateOption dupOption = duplicateOption.ToLower() switch
            {
                "duplicate" => ViewDuplicateOption.Duplicate,
                "with_detailing" => ViewDuplicateOption.WithDetailing,
                "as_dependent" => ViewDuplicateOption.AsDependent,
                _ => ViewDuplicateOption.Duplicate
            };

            using (var trans = new Transaction(doc, "Duplicate View"))
            {
                trans.Start();

                ElementId newViewId = view.Duplicate(dupOption);
                View newView = doc.GetElement(newViewId) as View;

                if (!string.IsNullOrEmpty(newName))
                {
                    newView.Name = newName;
                }

                trans.Commit();

                return new
                {
                    success = true,
                    originalViewId = viewId,
                    originalViewName = view.Name,
                    newViewId = newView.Id.IntegerValue,
                    newViewName = newView.Name,
                    duplicateOption = duplicateOption
                };
            }
        }

        #endregion

        #region 4. Set View Template

        public static object SetViewTemplate(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int viewId = payload.GetProperty("view_id").GetInt32();
            int templateId = payload.GetProperty("template_id").GetInt32();

            View view = doc.GetElement(new ElementId(viewId)) as View;
            if (view == null)
            {
                throw new Exception($"View {viewId} not found");
            }

            View template = doc.GetElement(new ElementId(templateId)) as View;
            if (template == null || !template.IsTemplate)
            {
                throw new Exception($"Template {templateId} not found or is not a template");
            }

            using (var trans = new Transaction(doc, "Set View Template"))
            {
                trans.Start();

                view.ViewTemplateId = template.Id;

                trans.Commit();

                return new
                {
                    success = true,
                    viewId = viewId,
                    viewName = view.Name,
                    templateId = templateId,
                    templateName = template.Name
                };
            }
        }

        #endregion

        #region 5. Create View Filter

        public static object CreateViewFilter(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string filterName = payload.GetProperty("filter_name").GetString();
            var categories = payload.GetProperty("categories").EnumerateArray();

            using (var trans = new Transaction(doc, "Create View Filter"))
            {
                trans.Start();

                // Create category set
                List<ElementId> categoryIds = new List<ElementId>();
                foreach (var cat in categories)
                {
                    string catName = cat.GetString();
                    if (Enum.TryParse(catName, out BuiltInCategory builtInCat))
                    {
                        categoryIds.Add(new ElementId(builtInCat));
                    }
                }

                // Create parameter filter element
                ParameterFilterElement filter = ParameterFilterElement.Create(doc, filterName, categoryIds);

                trans.Commit();

                return new
                {
                    success = true,
                    filterId = filter.Id.IntegerValue,
                    filterName = filter.Name,
                    categories = categories.Select(c => c.GetString()).ToList()
                };
            }
        }

        #endregion

        #region 6. Set View Visibility

        public static object SetViewVisibility(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int viewId = payload.GetProperty("view_id").GetInt32();
            string category = payload.GetProperty("category").GetString();
            bool visible = payload.GetProperty("visible").GetBoolean();

            View view = doc.GetElement(new ElementId(viewId)) as View;
            if (view == null)
            {
                throw new Exception($"View {viewId} not found");
            }

            if (!Enum.TryParse(category, out BuiltInCategory builtInCat))
            {
                throw new Exception($"Unknown category: {category}");
            }

            using (var trans = new Transaction(doc, "Set View Visibility"))
            {
                trans.Start();

                Category cat = Category.GetCategory(doc, builtInCat);
                if (cat != null)
                {
                    view.SetCategoryHidden(cat.Id, !visible);
                }

                trans.Commit();

                return new
                {
                    success = true,
                    viewId = viewId,
                    viewName = view.Name,
                    category = category,
                    visible = visible
                };
            }
        }

        #endregion

        #region 7. Isolate Elements in View

        public static object IsolateElementsInView(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int viewId = payload.GetProperty("view_id").GetInt32();
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();

            View view = doc.GetElement(new ElementId(viewId)) as View;
            if (view == null)
            {
                throw new Exception($"View {viewId} not found");
            }

            using (var trans = new Transaction(doc, "Isolate Elements in View"))
            {
                trans.Start();

                view.IsolateElementsTemporary(elementIds);

                trans.Commit();

                return new
                {
                    success = true,
                    viewId = viewId,
                    viewName = view.Name,
                    isolatedElementCount = elementIds.Count
                };
            }
        }

        #endregion

        #region 8. Hide Elements in View

        public static object HideElementsInView(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int viewId = payload.GetProperty("view_id").GetInt32();
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();

            View view = doc.GetElement(new ElementId(viewId)) as View;
            if (view == null)
            {
                throw new Exception($"View {viewId} not found");
            }

            using (var trans = new Transaction(doc, "Hide Elements in View"))
            {
                trans.Start();

                view.HideElementsTemporary(elementIds);

                trans.Commit();

                return new
                {
                    success = true,
                    viewId = viewId,
                    viewName = view.Name,
                    hiddenElementCount = elementIds.Count
                };
            }
        }

        #endregion

        #region 9. Unhide Elements in View

        public static object UnhideElementsInView(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int viewId = payload.GetProperty("view_id").GetInt32();
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();

            View view = doc.GetElement(new ElementId(viewId)) as View;
            if (view == null)
            {
                throw new Exception($"View {viewId} not found");
            }

            using (var trans = new Transaction(doc, "Unhide Elements in View"))
            {
                trans.Start();

                view.UnhideElements(elementIds);

                trans.Commit();

                return new
                {
                    success = true,
                    viewId = viewId,
                    viewName = view.Name,
                    unhiddenElementCount = elementIds.Count
                };
            }
        }

        #endregion

        #region 10. Crop View

        public static object CropView(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int viewId = payload.GetProperty("view_id").GetInt32();
            bool enabled = payload.TryGetProperty("enabled", out var en) ? en.GetBoolean() : true;

            View view = doc.GetElement(new ElementId(viewId)) as View;
            if (view == null)
            {
                throw new Exception($"View {viewId} not found");
            }

            using (var trans = new Transaction(doc, "Crop View"))
            {
                trans.Start();

                view.CropBoxActive = enabled;
                view.CropBoxVisible = enabled;

                // If custom crop region is provided
                if (enabled && payload.TryGetProperty("crop_box", out var cropBox))
                {
                    var min = cropBox.GetProperty("min");
                    var max = cropBox.GetProperty("max");

                    XYZ minPoint = new XYZ(
                        min.GetProperty("x").GetDouble(),
                        min.GetProperty("y").GetDouble(),
                        min.GetProperty("z").GetDouble()
                    );

                    XYZ maxPoint = new XYZ(
                        max.GetProperty("x").GetDouble(),
                        max.GetProperty("y").GetDouble(),
                        max.GetProperty("z").GetDouble()
                    );

                    BoundingBoxXYZ bbox = view.CropBox;
                    bbox.Min = minPoint;
                    bbox.Max = maxPoint;
                    view.CropBox = bbox;
                }

                trans.Commit();

                return new
                {
                    success = true,
                    viewId = viewId,
                    viewName = view.Name,
                    cropEnabled = view.CropBoxActive,
                    cropVisible = view.CropBoxVisible
                };
            }
        }

        #endregion
    }
}
