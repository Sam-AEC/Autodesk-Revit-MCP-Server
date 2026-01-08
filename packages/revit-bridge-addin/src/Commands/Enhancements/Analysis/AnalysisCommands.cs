using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevitBridge.Commands.Enhancements.Analysis
{
    /// <summary>
    /// Analysis and validation commands for model quality
    /// Reference (#92, Score: 217), ReferenceIntersector (#93, Score: 217)
    /// </summary>
    public static class AnalysisCommands
    {
        #region 1. Analyze Model Performance

        public static object AnalyzeModelPerformance(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;

            try
            {
                // Count elements by category
                FilteredElementCollector collector = new FilteredElementCollector(doc);
                var allElements = collector.WhereElementIsNotElementType().ToElements();

                var categoryCount = allElements
                    .Where(e => e.Category != null)
                    .GroupBy(e => e.Category.Name)
                    .Select(g => new { category = g.Key, count = g.Count() })
                    .OrderByDescending(x => x.count)
                    .ToList();

                // Count views
                FilteredElementCollector viewCollector = new FilteredElementCollector(doc);
                int viewCount = viewCollector.OfClass(typeof(View)).ToElements().Count;

                // Count families
                FilteredElementCollector familyCollector = new FilteredElementCollector(doc);
                int familyCount = familyCollector.OfClass(typeof(Family)).ToElements().Count;

                return new
                {
                    success = true,
                    totalElements = allElements.Count,
                    viewCount = viewCount,
                    familyCount = familyCount,
                    topCategories = categoryCount.Take(10).ToList(),
                    fileSize = "N/A - requires file system access"
                };
            }
            catch (Exception ex)
            {
                return new { success = false, error = ex.Message };
            }
        }

        #endregion

        #region 2. Find Element Intersections

        public static object FindElementIntersections(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int elementId = payload.GetProperty("element_id").GetInt32();
            string targetCategory = payload.TryGetProperty("target_category", out var tc) ? tc.GetString() : null;

            Element element = doc.GetElement(new ElementId(elementId));
            if (element == null)
            {
                throw new Exception($"Element {elementId} not found");
            }

            try
            {
                // Get element's bounding box
                BoundingBoxXYZ bbox = element.get_BoundingBox(null);
                if (bbox == null)
                {
                    return new { success = false, error = "Element has no bounding box" };
                }

                // Use outline for intersection test
                Outline outline = new Outline(bbox.Min, bbox.Max);
                BoundingBoxIntersectsFilter filter = new BoundingBoxIntersectsFilter(outline);

                FilteredElementCollector collector = new FilteredElementCollector(doc);
                collector.WherePasses(filter);

                if (!string.IsNullOrEmpty(targetCategory) && Enum.TryParse(targetCategory, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }

                var intersectingElements = collector
                    .WhereElementIsNotElementType()
                    .Where(e => e.Id.IntegerValue != elementId)
                    .Select(e => new
                    {
                        elementId = e.Id.IntegerValue,
                        category = e.Category?.Name,
                        elementType = e.GetType().Name
                    })
                    .ToList();

                return new
                {
                    success = true,
                    sourceElementId = elementId,
                    intersectingCount = intersectingElements.Count,
                    intersectingElements = intersectingElements
                };
            }
            catch (Exception ex)
            {
                return new { success = false, error = ex.Message };
            }
        }

        #endregion

        #region 3. Validate Elements

        public static object ValidateElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            var elementIds = payload.GetProperty("element_ids").EnumerateArray().Select(e => new ElementId(e.GetInt32())).ToList();

            var validationResults = new List<object>();

            foreach (var elemId in elementIds)
            {
                Element element = doc.GetElement(elemId);
                if (element == null)
                {
                    validationResults.Add(new
                    {
                        elementId = elemId.IntegerValue,
                        isValid = false,
                        issues = new[] { "Element not found" }
                    });
                    continue;
                }

                var issues = new List<string>();

                // Check for missing parameters
                if (element.Category == null)
                {
                    issues.Add("Missing category");
                }

                // Check for geometry
                Options options = new Options();
                GeometryElement geomElem = element.get_Geometry(options);
                if (geomElem == null || !geomElem.Any())
                {
                    issues.Add("No geometry");
                }

                // Check if element is valid
                if (!element.IsValidObject)
                {
                    issues.Add("Invalid object");
                }

                validationResults.Add(new
                {
                    elementId = elemId.IntegerValue,
                    isValid = issues.Count == 0,
                    category = element.Category?.Name,
                    issues = issues
                });
            }

            return new
            {
                success = true,
                validatedCount = validationResults.Count,
                validCount = validationResults.Count(r => ((dynamic)r).isValid),
                invalidCount = validationResults.Count(r => !((dynamic)r).isValid),
                results = validationResults
            };
        }

        #endregion

        #region 4. Find Duplicate Elements

        public static object FindDuplicateElements(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;
            double tolerance = payload.TryGetProperty("tolerance", out var tol) ? tol.GetDouble() : 0.01; // feet

            try
            {
                FilteredElementCollector collector = new FilteredElementCollector(doc);
                collector.WhereElementIsNotElementType();

                if (!string.IsNullOrEmpty(category) && Enum.TryParse(category, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }

                var elements = collector.ToElements();

                // Group by location
                var duplicateGroups = new List<object>();
                var processed = new HashSet<int>();

                foreach (var element in elements)
                {
                    if (processed.Contains(element.Id.IntegerValue))
                        continue;

                    LocationPoint locPoint = element.Location as LocationPoint;
                    if (locPoint == null)
                        continue;

                    XYZ point1 = locPoint.Point;
                    var duplicates = new List<int> { element.Id.IntegerValue };
                    processed.Add(element.Id.IntegerValue);

                    foreach (var otherElement in elements)
                    {
                        if (processed.Contains(otherElement.Id.IntegerValue))
                            continue;

                        LocationPoint otherLocPoint = otherElement.Location as LocationPoint;
                        if (otherLocPoint == null)
                            continue;

                        XYZ point2 = otherLocPoint.Point;
                        if (point1.DistanceTo(point2) < tolerance)
                        {
                            duplicates.Add(otherElement.Id.IntegerValue);
                            processed.Add(otherElement.Id.IntegerValue);
                        }
                    }

                    if (duplicates.Count > 1)
                    {
                        duplicateGroups.Add(new
                        {
                            location = new { x = point1.X, y = point1.Y, z = point1.Z },
                            duplicateCount = duplicates.Count,
                            elementIds = duplicates
                        });
                    }
                }

                return new
                {
                    success = true,
                    duplicateGroupCount = duplicateGroups.Count,
                    totalDuplicates = duplicateGroups.Sum(g => ((dynamic)g).duplicateCount - 1),
                    duplicateGroups = duplicateGroups
                };
            }
            catch (Exception ex)
            {
                return new { success = false, error = ex.Message };
            }
        }

        #endregion

        #region 5. Analyze Element Dependencies

        public static object AnalyzeElementDependencies(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int elementId = payload.GetProperty("element_id").GetInt32();

            Element element = doc.GetElement(new ElementId(elementId));
            if (element == null)
            {
                throw new Exception($"Element {elementId} not found");
            }

            try
            {
                // Get dependent elements
                var dependentIds = element.GetDependentElements(null);

                var dependents = dependentIds
                    .Select(id => doc.GetElement(id))
                    .Where(e => e != null)
                    .Select(e => new
                    {
                        elementId = e.Id.IntegerValue,
                        category = e.Category?.Name,
                        elementType = e.GetType().Name
                    })
                    .ToList();

                // Get host element
                Element host = null;
                if (element is FamilyInstance fi && fi.Host != null)
                {
                    host = fi.Host;
                }

                return new
                {
                    success = true,
                    elementId = elementId,
                    dependentCount = dependents.Count,
                    dependents = dependents,
                    hostElementId = host?.Id.IntegerValue,
                    hostCategory = host?.Category?.Name
                };
            }
            catch (Exception ex)
            {
                return new { success = false, error = ex.Message };
            }
        }

        #endregion

        #region 6. Check Model Integrity

        public static object CheckModelIntegrity(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;

            try
            {
                var issues = new List<object>();

                // Check for elements without geometry
                FilteredElementCollector collector = new FilteredElementCollector(doc);
                var elements = collector.WhereElementIsNotElementType().ToElements();

                int noGeometryCount = 0;
                foreach (var element in elements)
                {
                    Options options = new Options();
                    GeometryElement geomElem = element.get_Geometry(options);
                    if (geomElem == null || !geomElem.Any())
                    {
                        noGeometryCount++;
                    }
                }

                if (noGeometryCount > 0)
                {
                    issues.Add(new
                    {
                        issueType = "Elements without geometry",
                        count = noGeometryCount,
                        severity = "Warning"
                    });
                }

                // Check warnings
                IList<FailureMessage> warnings = doc.GetWarnings();
                if (warnings.Count > 0)
                {
                    issues.Add(new
                    {
                        issueType = "Document warnings",
                        count = warnings.Count,
                        severity = "Warning"
                    });
                }

                // Check for unplaced rooms
                FilteredElementCollector roomCollector = new FilteredElementCollector(doc);
                var rooms = roomCollector.OfCategory(BuiltInCategory.OST_Rooms).ToElements();
                int unplacedRooms = rooms.Count(r =>
                {
                    Room room = r as Room;
                    return room != null && room.Area == 0;
                });

                if (unplacedRooms > 0)
                {
                    issues.Add(new
                    {
                        issueType = "Unplaced rooms",
                        count = unplacedRooms,
                        severity = "Error"
                    });
                }

                return new
                {
                    success = true,
                    totalIssues = issues.Count,
                    isHealthy = issues.Count == 0,
                    issues = issues
                };
            }
            catch (Exception ex)
            {
                return new { success = false, error = ex.Message };
            }
        }

        #endregion

        #region 7. Get Element Statistics

        public static object GetElementStatistics(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string category = payload.TryGetProperty("category", out var cat) ? cat.GetString() : null;

            try
            {
                FilteredElementCollector collector = new FilteredElementCollector(doc);
                collector.WhereElementIsNotElementType();

                if (!string.IsNullOrEmpty(category) && Enum.TryParse(category, out BuiltInCategory builtInCat))
                {
                    collector.OfCategory(builtInCat);
                }

                var elements = collector.ToElements();

                // Calculate statistics
                var typeGroups = elements
                    .GroupBy(e => e.GetTypeId().IntegerValue)
                    .Select(g => new
                    {
                        typeId = g.Key,
                        typeName = doc.GetElement(new ElementId(g.Key))?.Name,
                        count = g.Count()
                    })
                    .OrderByDescending(x => x.count)
                    .ToList();

                var levelGroups = elements
                    .Where(e => e.LevelId != null && e.LevelId != ElementId.InvalidElementId)
                    .GroupBy(e => e.LevelId.IntegerValue)
                    .Select(g => new
                    {
                        levelId = g.Key,
                        levelName = doc.GetElement(new ElementId(g.Key))?.Name,
                        count = g.Count()
                    })
                    .OrderByDescending(x => x.count)
                    .ToList();

                return new
                {
                    success = true,
                    totalCount = elements.Count,
                    uniqueTypes = typeGroups.Count,
                    topTypes = typeGroups.Take(10).ToList(),
                    distributionByLevel = levelGroups
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
