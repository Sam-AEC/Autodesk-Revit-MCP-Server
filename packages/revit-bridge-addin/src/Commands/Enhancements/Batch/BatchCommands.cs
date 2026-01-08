using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevitBridge.Commands.Enhancements.Batch
{
    /// <summary>
    /// Batch operation commands for high-performance bulk modifications
    /// ElementId (#4, Score: 285), Element (#5, Score: 284)
    /// </summary>
    public static class BatchCommands
    {
        #region 1. Batch Set Parameters

        public static object BatchSetParameters(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();
            string parameterName = payload.GetProperty("parameter_name").GetString();
            var value = payload.GetProperty("value");

            using (var trans = new Transaction(doc, "Batch Set Parameters"))
            {
                trans.Start();

                int successCount = 0;
                var failures = new List<object>();

                foreach (var elemId in elementIds)
                {
                    try
                    {
                        Element element = doc.GetElement(elemId);
                        if (element == null)
                        {
                            failures.Add(new { elementId = elemId.IntegerValue, error = "Element not found" });
                            continue;
                        }

                        Parameter param = element.LookupParameter(parameterName);
                        if (param == null || param.IsReadOnly)
                        {
                            failures.Add(new { elementId = elemId.IntegerValue, error = "Parameter not found or read-only" });
                            continue;
                        }

                        // Set value based on parameter type
                        if (param.StorageType == StorageType.Double)
                        {
                            param.Set(value.GetDouble());
                        }
                        else if (param.StorageType == StorageType.Integer)
                        {
                            param.Set(value.GetInt32());
                        }
                        else if (param.StorageType == StorageType.String)
                        {
                            param.Set(value.GetString());
                        }

                        successCount++;
                    }
                    catch (Exception ex)
                    {
                        failures.Add(new { elementId = elemId.IntegerValue, error = ex.Message });
                    }
                }

                trans.Commit();

                return new
                {
                    success = true,
                    totalElements = elementIds.Count,
                    successCount = successCount,
                    failureCount = failures.Count,
                    failures = failures
                };
            }
        }

        #endregion

        #region 2. Batch Delete Elements

        public static object BatchDeleteElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();

            using (var trans = new Transaction(doc, "Batch Delete Elements"))
            {
                trans.Start();

                try
                {
                    ICollection<ElementId> deletedIds = doc.Delete(elementIds);

                    trans.Commit();

                    return new
                    {
                        success = true,
                        requestedCount = elementIds.Count,
                        deletedCount = deletedIds.Count,
                        deletedElementIds = deletedIds.Select(id => id.IntegerValue).ToList()
                    };
                }
                catch (Exception ex)
                {
                    return new { success = false, error = ex.Message };
                }
            }
        }

        #endregion

        #region 3. Batch Copy Elements

        public static object BatchCopyElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();
            var translation = payload.GetProperty("translation");

            XYZ offset = new XYZ(
                translation.GetProperty("x").GetDouble(),
                translation.GetProperty("y").GetDouble(),
                translation.GetProperty("z").GetDouble()
            );

            using (var trans = new Transaction(doc, "Batch Copy Elements"))
            {
                trans.Start();

                try
                {
                    ICollection<ElementId> copiedIds = ElementTransformUtils.CopyElements(doc, elementIds, offset);

                    trans.Commit();

                    return new
                    {
                        success = true,
                        originalCount = elementIds.Count,
                        copiedCount = copiedIds.Count,
                        copiedElementIds = copiedIds.Select(id => id.IntegerValue).ToList()
                    };
                }
                catch (Exception ex)
                {
                    return new { success = false, error = ex.Message };
                }
            }
        }

        #endregion

        #region 4. Batch Move Elements

        public static object BatchMoveElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();
            var translation = payload.GetProperty("translation");

            XYZ offset = new XYZ(
                translation.GetProperty("x").GetDouble(),
                translation.GetProperty("y").GetDouble(),
                translation.GetProperty("z").GetDouble()
            );

            using (var trans = new Transaction(doc, "Batch Move Elements"))
            {
                trans.Start();

                try
                {
                    ElementTransformUtils.MoveElements(doc, elementIds, offset);

                    trans.Commit();

                    return new
                    {
                        success = true,
                        movedCount = elementIds.Count,
                        translation = new { x = offset.X, y = offset.Y, z = offset.Z }
                    };
                }
                catch (Exception ex)
                {
                    return new { success = false, error = ex.Message };
                }
            }
        }

        #endregion

        #region 5. Batch Rotate Elements

        public static object BatchRotateElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();
            var axisStart = payload.GetProperty("axis_start");
            var axisEnd = payload.GetProperty("axis_end");
            double angle = payload.GetProperty("angle").GetDouble(); // radians

            XYZ start = new XYZ(
                axisStart.GetProperty("x").GetDouble(),
                axisStart.GetProperty("y").GetDouble(),
                axisStart.GetProperty("z").GetDouble()
            );

            XYZ end = new XYZ(
                axisEnd.GetProperty("x").GetDouble(),
                axisEnd.GetProperty("y").GetDouble(),
                axisEnd.GetProperty("z").GetDouble()
            );

            using (var trans = new Transaction(doc, "Batch Rotate Elements"))
            {
                trans.Start();

                try
                {
                    Line axis = Line.CreateBound(start, end);
                    ElementTransformUtils.RotateElements(doc, elementIds, axis, angle);

                    trans.Commit();

                    return new
                    {
                        success = true,
                        rotatedCount = elementIds.Count,
                        angle = angle,
                        angleDegrees = angle * 180.0 / Math.PI
                    };
                }
                catch (Exception ex)
                {
                    return new { success = false, error = ex.Message };
                }
            }
        }

        #endregion

        #region 6. Batch Mirror Elements

        public static object BatchMirrorElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();
            var planeOrigin = payload.GetProperty("plane_origin");
            var planeNormal = payload.GetProperty("plane_normal");

            XYZ origin = new XYZ(
                planeOrigin.GetProperty("x").GetDouble(),
                planeOrigin.GetProperty("y").GetDouble(),
                planeOrigin.GetProperty("z").GetDouble()
            );

            XYZ normal = new XYZ(
                planeNormal.GetProperty("x").GetDouble(),
                planeNormal.GetProperty("y").GetDouble(),
                planeNormal.GetProperty("z").GetDouble()
            );

            using (var trans = new Transaction(doc, "Batch Mirror Elements"))
            {
                trans.Start();

                try
                {
                    Plane plane = Plane.CreateByNormalAndOrigin(normal, origin);
                    ElementTransformUtils.MirrorElements(doc, elementIds, plane, true); // true = copy

                    trans.Commit();

                    return new
                    {
                        success = true,
                        mirroredCount = elementIds.Count,
                        planeOrigin = new { x = origin.X, y = origin.Y, z = origin.Z },
                        planeNormal = new { x = normal.X, y = normal.Y, z = normal.Z }
                    };
                }
                catch (Exception ex)
                {
                    return new { success = false, error = ex.Message };
                }
            }
        }

        #endregion

        #region 7. Batch Change Type

        public static object BatchChangeType(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();
            int newTypeId = payload.GetProperty("new_type_id").GetInt32();

            using (var trans = new Transaction(doc, "Batch Change Type"))
            {
                trans.Start();

                int successCount = 0;
                var failures = new List<object>();

                foreach (var elemId in elementIds)
                {
                    try
                    {
                        Element element = doc.GetElement(elemId);
                        if (element == null)
                        {
                            failures.Add(new { elementId = elemId.IntegerValue, error = "Element not found" });
                            continue;
                        }

                        element.ChangeTypeId(new ElementId(newTypeId));
                        successCount++;
                    }
                    catch (Exception ex)
                    {
                        failures.Add(new { elementId = elemId.IntegerValue, error = ex.Message });
                    }
                }

                trans.Commit();

                return new
                {
                    success = true,
                    totalElements = elementIds.Count,
                    successCount = successCount,
                    failureCount = failures.Count,
                    newTypeId = newTypeId,
                    failures = failures
                };
            }
        }

        #endregion

        #region 8. Batch Isolate in Views

        public static object BatchIsolateInViews(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();
            var viewIds = payload.GetProperty("view_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();

            using (var trans = new Transaction(doc, "Batch Isolate in Views"))
            {
                trans.Start();

                int successCount = 0;
                var failures = new List<object>();

                foreach (var viewId in viewIds)
                {
                    try
                    {
                        View view = doc.GetElement(viewId) as View;
                        if (view == null)
                        {
                            failures.Add(new { viewId = viewId.IntegerValue, error = "View not found" });
                            continue;
                        }

                        view.IsolateElementsTemporary(elementIds);
                        successCount++;
                    }
                    catch (Exception ex)
                    {
                        failures.Add(new { viewId = viewId.IntegerValue, error = ex.Message });
                    }
                }

                trans.Commit();

                return new
                {
                    success = true,
                    totalViews = viewIds.Count,
                    successCount = successCount,
                    failureCount = failures.Count,
                    isolatedElementCount = elementIds.Count,
                    failures = failures
                };
            }
        }

        #endregion

        #region 9. Batch Export to CSV

        public static object BatchExportToCSV(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();
            var parameterNames = payload.GetProperty("parameter_names").EnumerateArray().Select(e => e.GetString()).ToList();

            try
            {
                var rows = new List<object>();

                foreach (var elemId in elementIds)
                {
                    Element element = doc.GetElement(elemId);
                    if (element == null)
                        continue;

                    var rowData = new Dictionary<string, object>
                    {
                        { "ElementId", element.Id.IntegerValue },
                        { "Category", element.Category?.Name },
                        { "Type", doc.GetElement(element.GetTypeId())?.Name }
                    };

                    foreach (var paramName in parameterNames)
                    {
                        Parameter param = element.LookupParameter(paramName);
                        if (param != null)
                        {
                            rowData[paramName] = param.AsValueString() ?? param.AsString() ?? "N/A";
                        }
                        else
                        {
                            rowData[paramName] = "N/A";
                        }
                    }

                    rows.Add(rowData);
                }

                return new
                {
                    success = true,
                    rowCount = rows.Count,
                    data = rows,
                    message = "Export to CSV requires file writing - data returned as JSON"
                };
            }
            catch (Exception ex)
            {
                return new { success = false, error = ex.Message };
            }
        }

        #endregion
    }
}
