using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevitBridge.Commands.Core.Filtering
{
    /// <summary>
    /// Advanced element filtering commands - highest priority tools
    /// FilteredElementCollector is #1 ranked API (Score: 294)
    /// </summary>
    public static class FilteringCommands
    {
        #region 1. Filter Elements by Parameter

        public static object FilterElementsByParameter(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string paramName = payload.GetProperty("parameter_name").GetString();
            string op = payload.GetProperty("operator").GetString(); // equals, greater, less, contains, not_equals
            var value = payload.GetProperty("value");
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

            using (var trans = new Transaction(doc, "Filter Elements by Parameter"))
            {
                trans.Start();

                var collector = new FilteredElementCollector(doc).WhereElementIsNotElementType();

                // Apply category filter if specified
                if (!string.IsNullOrEmpty(category))
                {
                    if (Enum.TryParse(category, out BuiltInCategory builtInCat))
                    {
                        collector.OfCategory(builtInCat);
                    }
                }

                // Create parameter filter
                var elements = collector.ToElements()
                    .Where(e => MatchesParameterFilter(e, paramName, op, value))
                    .Select(e => new
                    {
                        id = e.Id.IntegerValue,
                        category = e.Category?.Name ?? "Unknown",
                        name = e.Name ?? "Unnamed",
                        uniqueId = e.UniqueId
                    })
                    .ToList();

                trans.Commit();

                return new
                {
                    count = elements.Count,
                    elements = elements
                };
            }
        }

        private static bool MatchesParameterFilter(Element element, string paramName, string op, JsonElement value)
        {
            Parameter param = element.LookupParameter(paramName);
            if (param == null) return false;

            switch (param.StorageType)
            {
                case StorageType.Integer:
                    int intValue = value.GetInt32();
                    int paramIntValue = param.AsInteger();
                    return op switch
                    {
                        "equals" => paramIntValue == intValue,
                        "not_equals" => paramIntValue != intValue,
                        "greater" => paramIntValue > intValue,
                        "less" => paramIntValue < intValue,
                        "greater_equal" => paramIntValue >= intValue,
                        "less_equal" => paramIntValue <= intValue,
                        _ => false
                    };

                case StorageType.Double:
                    double doubleValue = value.GetDouble();
                    double paramDoubleValue = param.AsDouble();
                    return op switch
                    {
                        "equals" => Math.Abs(paramDoubleValue - doubleValue) < 0.0001,
                        "not_equals" => Math.Abs(paramDoubleValue - doubleValue) >= 0.0001,
                        "greater" => paramDoubleValue > doubleValue,
                        "less" => paramDoubleValue < doubleValue,
                        "greater_equal" => paramDoubleValue >= doubleValue,
                        "less_equal" => paramDoubleValue <= doubleValue,
                        _ => false
                    };

                case StorageType.String:
                    string stringValue = value.GetString();
                    string paramStringValue = param.AsString() ?? "";
                    return op switch
                    {
                        "equals" => paramStringValue.Equals(stringValue, StringComparison.OrdinalIgnoreCase),
                        "not_equals" => !paramStringValue.Equals(stringValue, StringComparison.OrdinalIgnoreCase),
                        "contains" => paramStringValue.Contains(stringValue, StringComparison.OrdinalIgnoreCase),
                        "starts_with" => paramStringValue.StartsWith(stringValue, StringComparison.OrdinalIgnoreCase),
                        "ends_with" => paramStringValue.EndsWith(stringValue, StringComparison.OrdinalIgnoreCase),
                        _ => false
                    };

                case StorageType.ElementId:
                    int elemIdValue = value.GetInt32();
                    int paramElemId = param.AsElementId().IntegerValue;
                    return op switch
                    {
                        "equals" => paramElemId == elemIdValue,
                        "not_equals" => paramElemId != elemIdValue,
                        _ => false
                    };

                default:
                    return false;
            }
        }

        #endregion

        #region 2. Filter Elements by Level

        public static object FilterElementsByLevel(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string levelName = payload.GetProperty("level_name").GetString();
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

            // Find level
            Level level = new FilteredElementCollector(doc)
                .OfClass(typeof(Level))
                .Cast<Level>()
                .FirstOrDefault(l => l.Name.Equals(levelName, StringComparison.OrdinalIgnoreCase));

            if (level == null)
            {
                throw new Exception($"Level '{levelName}' not found");
            }

            var collector = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType();

            // Apply category filter if specified
            if (!string.IsNullOrEmpty(category))
            {
                if (Enum.TryParse(category, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }
            }

            // Filter by level using ElementLevelFilter
            var levelFilter = new ElementLevelFilter(level.Id);
            collector.WherePasses(levelFilter);

            var elements = collector.Select(e => new
            {
                id = e.Id.IntegerValue,
                category = e.Category?.Name ?? "Unknown",
                name = e.Name ?? "Unnamed",
                levelName = levelName,
                uniqueId = e.UniqueId
            }).ToList();

            return new
            {
                level = levelName,
                levelId = level.Id.IntegerValue,
                count = elements.Count,
                elements = elements
            };
        }

        #endregion

        #region 3. Filter Elements by Workset

        public static object FilterElementsByWorkset(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string worksetName = payload.GetProperty("workset_name").GetString();

            if (!doc.IsWorkshared)
            {
                throw new Exception("Document is not workshared");
            }

            // Find workset
            Workset targetWorkset = null;
            foreach (Workset ws in new FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset))
            {
                if (ws.Name.Equals(worksetName, StringComparison.OrdinalIgnoreCase))
                {
                    targetWorkset = ws;
                    break;
                }
            }

            if (targetWorkset == null)
            {
                throw new Exception($"Workset '{worksetName}' not found");
            }

            var collector = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType();

            var worksetFilter = new ElementWorksetFilter(targetWorkset.Id);
            collector.WherePasses(worksetFilter);

            var elements = collector.Select(e => new
            {
                id = e.Id.IntegerValue,
                category = e.Category?.Name ?? "Unknown",
                name = e.Name ?? "Unnamed",
                workset = worksetName,
                uniqueId = e.UniqueId
            }).ToList();

            return new
            {
                workset = worksetName,
                worksetId = targetWorkset.Id.IntegerValue,
                count = elements.Count,
                elements = elements
            };
        }

        #endregion

        #region 4. Filter Elements by Bounding Box

        public static object FilterElementsByBoundingBox(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var minPoint = payload.GetProperty("min_point");
            var maxPoint = payload.GetProperty("max_point");
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

            XYZ min = new XYZ(
                minPoint.GetProperty("x").GetDouble(),
                minPoint.GetProperty("y").GetDouble(),
                minPoint.GetProperty("z").GetDouble()
            );

            XYZ max = new XYZ(
                maxPoint.GetProperty("x").GetDouble(),
                maxPoint.GetProperty("y").GetDouble(),
                maxPoint.GetProperty("z").GetDouble()
            );

            Outline outline = new Outline(min, max);
            BoundingBoxIntersectsFilter bbFilter = new BoundingBoxIntersectsFilter(outline);

            var collector = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .WherePasses(bbFilter);

            if (!string.IsNullOrEmpty(category))
            {
                if (Enum.TryParse(category, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }
            }

            var elements = collector.Select(e => new
            {
                id = e.Id.IntegerValue,
                category = e.Category?.Name ?? "Unknown",
                name = e.Name ?? "Unnamed",
                uniqueId = e.UniqueId
            }).ToList();

            return new
            {
                boundingBox = new { min = new { min.X, min.Y, min.Z }, max = new { max.X, max.Y, max.Z } },
                count = elements.Count,
                elements = elements
            };
        }

        #endregion

        #region 5. Filter Elements Intersecting

        public static object FilterElementsIntersecting(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int targetElementId = payload.GetProperty("element_id").GetInt32();
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

            Element targetElement = doc.GetElement(new ElementId(targetElementId));
            if (targetElement == null)
            {
                throw new Exception($"Element {targetElementId} not found");
            }

            // Get element geometry
            Options geomOptions = new Options { ComputeReferences = true, DetailLevel = ViewDetailLevel.Fine };
            GeometryElement geomElem = targetElement.get_Geometry(geomOptions);

            if (geomElem == null)
            {
                throw new Exception("Element has no geometry");
            }

            // Create solid from geometry
            Solid targetSolid = null;
            foreach (GeometryObject geomObj in geomElem)
            {
                if (geomObj is Solid solid && solid.Volume > 0)
                {
                    targetSolid = solid;
                    break;
                }
            }

            if (targetSolid == null)
            {
                throw new Exception("Element has no solid geometry");
            }

            var intersectFilter = new ElementIntersectsSolidFilter(targetSolid);
            var collector = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .WherePasses(intersectFilter);

            if (!string.IsNullOrEmpty(category))
            {
                if (Enum.TryParse(category, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }
            }

            var elements = collector.Where(e => e.Id.IntegerValue != targetElementId)
                .Select(e => new
                {
                    id = e.Id.IntegerValue,
                    category = e.Category?.Name ?? "Unknown",
                    name = e.Name ?? "Unnamed",
                    uniqueId = e.UniqueId
                }).ToList();

            return new
            {
                targetElement = new { id = targetElementId, name = targetElement.Name },
                count = elements.Count,
                intersectingElements = elements
            };
        }

        #endregion

        #region 6. Filter Elements by View

        public static object FilterElementsByView(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int viewId = payload.GetProperty("view_id").GetInt32();
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

            View view = doc.GetElement(new ElementId(viewId)) as View;
            if (view == null)
            {
                throw new Exception($"View {viewId} not found");
            }

            var collector = new FilteredElementCollector(doc, view.Id)
                .WhereElementIsNotElementType();

            if (!string.IsNullOrEmpty(category))
            {
                if (Enum.TryParse(category, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }
            }

            var elements = collector.Select(e => new
            {
                id = e.Id.IntegerValue,
                category = e.Category?.Name ?? "Unknown",
                name = e.Name ?? "Unnamed",
                uniqueId = e.UniqueId
            }).ToList();

            return new
            {
                view = new { id = viewId, name = view.Name },
                count = elements.Count,
                elements = elements
            };
        }

        #endregion

        #region 7. Find Elements at Point

        public static object FindElementsAtPoint(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var point = payload.GetProperty("point");
            double tolerance = payload.TryGetProperty("tolerance", out var tol) ? tol.GetDouble() : 0.1;

            XYZ searchPoint = new XYZ(
                point.GetProperty("x").GetDouble(),
                point.GetProperty("y").GetDouble(),
                point.GetProperty("z").GetDouble()
            );

            // Create small bounding box around point
            XYZ min = new XYZ(searchPoint.X - tolerance, searchPoint.Y - tolerance, searchPoint.Z - tolerance);
            XYZ max = new XYZ(searchPoint.X + tolerance, searchPoint.Y + tolerance, searchPoint.Z + tolerance);

            Outline outline = new Outline(min, max);
            BoundingBoxIntersectsFilter bbFilter = new BoundingBoxIntersectsFilter(outline);

            var collector = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .WherePasses(bbFilter);

            var elements = collector.Select(e => new
            {
                id = e.Id.IntegerValue,
                category = e.Category?.Name ?? "Unknown",
                name = e.Name ?? "Unnamed",
                uniqueId = e.UniqueId
            }).ToList();

            return new
            {
                searchPoint = new { searchPoint.X, searchPoint.Y, searchPoint.Z },
                tolerance = tolerance,
                count = elements.Count,
                elements = elements
            };
        }

        #endregion

        #region 8. Filter by Multiple Criteria

        public static object FilterByMultipleCriteria(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string logicOperator = payload.GetProperty("logic").GetString(); // "and" or "or"
            var criteria = payload.GetProperty("criteria").EnumerateArray();

            var collector = new FilteredElementCollector(doc).WhereElementIsNotElementType();
            List<ElementId> resultIds = null;

            foreach (var criterion in criteria)
            {
                string filterType = criterion.GetProperty("type").GetString();
                var currentIds = new List<ElementId>();

                switch (filterType)
                {
                    case "category":
                        string catName = criterion.GetProperty("value").GetString();
                        if (Enum.TryParse(catName, out BuiltInCategory builtInCat))
                        {
                            currentIds = new FilteredElementCollector(doc)
                                .WhereElementIsNotElementType()
                                .OfCategory(builtInCat)
                                .ToElementIds()
                                .ToList();
                        }
                        break;

                    case "parameter":
                        // Similar to FilterElementsByParameter
                        string paramName = criterion.GetProperty("parameter_name").GetString();
                        string op = criterion.GetProperty("operator").GetString();
                        var value = criterion.GetProperty("value");
                        currentIds = new FilteredElementCollector(doc)
                            .WhereElementIsNotElementType()
                            .ToElements()
                            .Where(e => MatchesParameterFilter(e, paramName, op, value))
                            .Select(e => e.Id)
                            .ToList();
                        break;

                    case "level":
                        string levelName = criterion.GetProperty("value").GetString();
                        Level level = new FilteredElementCollector(doc)
                            .OfClass(typeof(Level))
                            .Cast<Level>()
                            .FirstOrDefault(l => l.Name.Equals(levelName, StringComparison.OrdinalIgnoreCase));
                        if (level != null)
                        {
                            currentIds = new FilteredElementCollector(doc)
                                .WhereElementIsNotElementType()
                                .WherePasses(new ElementLevelFilter(level.Id))
                                .ToElementIds()
                                .ToList();
                        }
                        break;
                }

                // Apply logic operator
                if (resultIds == null)
                {
                    resultIds = currentIds;
                }
                else
                {
                    resultIds = logicOperator == "and"
                        ? resultIds.Intersect(currentIds).ToList()
                        : resultIds.Union(currentIds).ToList();
                }
            }

            var elements = resultIds?.Select(id => doc.GetElement(id))
                .Where(e => e != null)
                .Select(e => new
                {
                    id = e.Id.IntegerValue,
                    category = e.Category?.Name ?? "Unknown",
                    name = e.Name ?? "Unnamed",
                    uniqueId = e.UniqueId
                })
                .ToList() ?? new List<object>();

            return new
            {
                logic = logicOperator,
                criteriaCount = criteria.Count(),
                count = elements.Count,
                elements = elements
            };
        }

        #endregion

        #region 9. Get All Elements of Type

        public static object GetAllElementsOfType(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string typeName = payload.GetProperty("type_name").GetString();
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

            var collector = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType();

            if (!string.IsNullOrEmpty(category))
            {
                if (Enum.TryParse(category, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }
            }

            var elements = collector
                .Where(e => e.GetTypeId() != ElementId.InvalidElementId)
                .Where(e =>
                {
                    var elemType = doc.GetElement(e.GetTypeId());
                    return elemType != null && elemType.Name.Contains(typeName, StringComparison.OrdinalIgnoreCase);
                })
                .Select(e => new
                {
                    id = e.Id.IntegerValue,
                    category = e.Category?.Name ?? "Unknown",
                    name = e.Name ?? "Unnamed",
                    typeName = doc.GetElement(e.GetTypeId())?.Name ?? "Unknown",
                    uniqueId = e.UniqueId
                })
                .ToList();

            return new
            {
                searchTypeName = typeName,
                count = elements.Count,
                elements = elements
            };
        }

        #endregion

        #region 10. Get Dependent Elements

        public static object GetDependentElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int elementId = payload.GetProperty("element_id").GetInt32();

            Element element = doc.GetElement(new ElementId(elementId));
            if (element == null)
            {
                throw new Exception($"Element {elementId} not found");
            }

            var dependentIds = element.GetDependentElements(null);

            var elements = dependentIds.Select(id => doc.GetElement(id))
                .Where(e => e != null)
                .Select(e => new
                {
                    id = e.Id.IntegerValue,
                    category = e.Category?.Name ?? "Unknown",
                    name = e.Name ?? "Unnamed",
                    uniqueId = e.UniqueId
                })
                .ToList();

            return new
            {
                sourceElement = new { id = elementId, name = element.Name },
                count = elements.Count,
                dependentElements = elements
            };
        }

        #endregion

        #region 11. Get Hosted Elements

        public static object GetHostedElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int hostElementId = payload.GetProperty("host_element_id").GetInt32();

            Element hostElement = doc.GetElement(new ElementId(hostElementId));
            if (hostElement == null)
            {
                throw new Exception($"Host element {hostElementId} not found");
            }

            // Get all elements and filter by those hosted on this element
            var hostedElements = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .Where(e =>
                {
                    if (e is FamilyInstance fi && fi.Host != null)
                    {
                        return fi.Host.Id.IntegerValue == hostElementId;
                    }
                    return false;
                })
                .Select(e => new
                {
                    id = e.Id.IntegerValue,
                    category = e.Category?.Name ?? "Unknown",
                    name = e.Name ?? "Unnamed",
                    uniqueId = e.UniqueId
                })
                .ToList();

            return new
            {
                hostElement = new { id = hostElementId, name = hostElement.Name },
                count = hostedElements.Count,
                hostedElements = hostedElements
            };
        }

        #endregion

        #region 12-15. Additional Filters (Simplified)

        public static object FindSimilarElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int referenceElementId = payload.GetProperty("element_id").GetInt32();

            Element refElement = doc.GetElement(new ElementId(referenceElementId));
            if (refElement == null)
            {
                throw new Exception($"Element {referenceElementId} not found");
            }

            // Find elements of same category and type
            var similarElements = new FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .WherePasses(new ElementCategoryFilter(refElement.Category.Id))
                .Where(e => e.GetTypeId().IntegerValue == refElement.GetTypeId().IntegerValue)
                .Where(e => e.Id.IntegerValue != referenceElementId)
                .Select(e => new
                {
                    id = e.Id.IntegerValue,
                    category = e.Category?.Name ?? "Unknown",
                    name = e.Name ?? "Unnamed",
                    uniqueId = e.UniqueId
                })
                .ToList();

            return new
            {
                referenceElement = new { id = referenceElementId, name = refElement.Name, category = refElement.Category.Name },
                count = similarElements.Count,
                similarElements = similarElements
            };
        }

        public static object GetElementsByUniqueId(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var uniqueIds = payload.GetProperty("unique_ids").EnumerateArray().Select(e => e.GetString()).ToList();

            var elements = uniqueIds
                .Select(uid => doc.GetElement(uid))
                .Where(e => e != null)
                .Select(e => new
                {
                    id = e.Id.IntegerValue,
                    category = e.Category?.Name ?? "Unknown",
                    name = e.Name ?? "Unnamed",
                    uniqueId = e.UniqueId
                })
                .ToList();

            return new
            {
                requestedCount = uniqueIds.Count,
                foundCount = elements.Count,
                elements = elements
            };
        }

        public static object GetLinkedElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int linkInstanceId = payload.GetProperty("link_instance_id").GetInt32();
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

            RevitLinkInstance linkInstance = doc.GetElement(new ElementId(linkInstanceId)) as RevitLinkInstance;
            if (linkInstance == null)
            {
                throw new Exception($"Link instance {linkInstanceId} not found");
            }

            Document linkedDoc = linkInstance.GetLinkDocument();
            if (linkedDoc == null)
            {
                throw new Exception("Linked document is not loaded");
            }

            var collector = new FilteredElementCollector(linkedDoc).WhereElementIsNotElementType();

            if (!string.IsNullOrEmpty(category))
            {
                if (Enum.TryParse(category, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }
            }

            var elements = collector.Select(e => new
            {
                id = e.Id.IntegerValue,
                category = e.Category?.Name ?? "Unknown",
                name = e.Name ?? "Unnamed",
                uniqueId = e.UniqueId,
                linkName = linkedDoc.Title
            }).ToList();

            return new
            {
                linkInstance = new { id = linkInstanceId, name = linkedDoc.Title },
                count = elements.Count,
                elements = elements
            };
        }

        #endregion
    }
}
