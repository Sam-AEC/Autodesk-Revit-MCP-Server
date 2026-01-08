using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.IO;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RevitBridge.Commands.Core.Schedules
{
    /// <summary>
    /// Schedule management commands
    /// ViewSchedule is #146 ranked API (Score: 198) - documentation essential
    /// </summary>
    public static class ScheduleCommands
    {
        #region 1. Add Schedule Field

        public static object AddScheduleField(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int scheduleId = payload.GetProperty("schedule_id").GetInt32();
            string fieldName = payload.GetProperty("field_name").GetString();

            ViewSchedule schedule = doc.GetElement(new ElementId(scheduleId)) as ViewSchedule;
            if (schedule == null)
            {
                throw new Exception($"Schedule {scheduleId} not found");
            }

            using (var trans = new Transaction(doc, "Add Schedule Field"))
            {
                trans.Start();

                ScheduleDefinition definition = schedule.Definition;

                // Find schedulable field
                SchedulableField schedulableField = definition.GetSchedulableFields()
                    .FirstOrDefault(sf => sf.GetName(doc).Equals(fieldName, StringComparison.OrdinalIgnoreCase));

                if (schedulableField == null)
                {
                    throw new Exception($"Field '{fieldName}' not found in schedulable fields");
                }

                // Add field
                ScheduleField field = definition.AddField(schedulableField);

                trans.Commit();

                return new
                {
                    success = true,
                    scheduleId = scheduleId,
                    scheduleName = schedule.Name,
                    fieldName = fieldName,
                    fieldId = field.FieldId.IntegerValue,
                    columnPosition = field.ColumnHeadingOffset
                };
            }
        }

        #endregion

        #region 2. Remove Schedule Field

        public static object RemoveScheduleField(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int scheduleId = payload.GetProperty("schedule_id").GetInt32();
            string fieldName = payload.GetProperty("field_name").GetString();

            ViewSchedule schedule = doc.GetElement(new ElementId(scheduleId)) as ViewSchedule;
            if (schedule == null)
            {
                throw new Exception($"Schedule {scheduleId} not found");
            }

            using (var trans = new Transaction(doc, "Remove Schedule Field"))
            {
                trans.Start();

                ScheduleDefinition definition = schedule.Definition;

                // Find field by name
                ScheduleField fieldToRemove = null;
                int fieldIndex = -1;

                for (int i = 0; i < definition.GetFieldCount(); i++)
                {
                    ScheduleField field = definition.GetField(i);
                    if (field.GetName().Equals(fieldName, StringComparison.OrdinalIgnoreCase))
                    {
                        fieldToRemove = field;
                        fieldIndex = i;
                        break;
                    }
                }

                if (fieldToRemove == null)
                {
                    throw new Exception($"Field '{fieldName}' not found in schedule");
                }

                definition.RemoveField(fieldIndex);

                trans.Commit();

                return new
                {
                    success = true,
                    scheduleId = scheduleId,
                    scheduleName = schedule.Name,
                    removedField = fieldName,
                    remainingFieldCount = definition.GetFieldCount()
                };
            }
        }

        #endregion

        #region 3. Set Schedule Filter

        public static object SetScheduleFilter(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int scheduleId = payload.GetProperty("schedule_id").GetInt32();
            string fieldName = payload.GetProperty("field_name").GetString();
            string filterType = payload.GetProperty("filter_type").GetString(); // equals, greater, less, contains, etc.
            var value = payload.GetProperty("value");

            ViewSchedule schedule = doc.GetElement(new ElementId(scheduleId)) as ViewSchedule;
            if (schedule == null)
            {
                throw new Exception($"Schedule {scheduleId} not found");
            }

            using (var trans = new Transaction(doc, "Set Schedule Filter"))
            {
                trans.Start();

                ScheduleDefinition definition = schedule.Definition;

                // Find field
                ScheduleField field = null;
                for (int i = 0; i < definition.GetFieldCount(); i++)
                {
                    var f = definition.GetField(i);
                    if (f.GetName().Equals(fieldName, StringComparison.OrdinalIgnoreCase))
                    {
                        field = f;
                        break;
                    }
                }

                if (field == null)
                {
                    throw new Exception($"Field '{fieldName}' not found");
                }

                // Create filter
                ScheduleFilterType schedFilterType = filterType.ToLower() switch
                {
                    "equals" => ScheduleFilterType.Equal,
                    "not_equals" => ScheduleFilterType.NotEqual,
                    "greater" => ScheduleFilterType.GreaterThan,
                    "greater_equal" => ScheduleFilterType.GreaterThanOrEqual,
                    "less" => ScheduleFilterType.LessThan,
                    "less_equal" => ScheduleFilterType.LessThanOrEqual,
                    "contains" => ScheduleFilterType.Contains,
                    "not_contains" => ScheduleFilterType.NotContains,
                    "begins_with" => ScheduleFilterType.BeginsWith,
                    "ends_with" => ScheduleFilterType.EndsWith,
                    _ => ScheduleFilterType.Equal
                };

                // Convert value based on field type
                string filterValue = value.ValueKind == JsonValueKind.String
                    ? value.GetString()
                    : value.ToString();

                ScheduleFilter filter = new ScheduleFilter(field.FieldId, schedFilterType, filterValue);
                definition.AddFilter(filter);

                trans.Commit();

                return new
                {
                    success = true,
                    scheduleId = scheduleId,
                    scheduleName = schedule.Name,
                    fieldName = fieldName,
                    filterType = filterType,
                    value = filterValue,
                    totalFilters = definition.GetFilterCount()
                };
            }
        }

        #endregion

        #region 4. Set Schedule Sorting

        public static object SetScheduleSorting(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int scheduleId = payload.GetProperty("schedule_id").GetInt32();
            string fieldName = payload.GetProperty("field_name").GetString();
            bool ascending = payload.TryGetProperty("ascending", out var asc) ? asc.GetBoolean() : true;

            ViewSchedule schedule = doc.GetElement(new ElementId(scheduleId)) as ViewSchedule;
            if (schedule == null)
            {
                throw new Exception($"Schedule {scheduleId} not found");
            }

            using (var trans = new Transaction(doc, "Set Schedule Sorting"))
            {
                trans.Start();

                ScheduleDefinition definition = schedule.Definition;

                // Find field
                ScheduleField field = null;
                for (int i = 0; i < definition.GetFieldCount(); i++)
                {
                    var f = definition.GetField(i);
                    if (f.GetName().Equals(fieldName, StringComparison.OrdinalIgnoreCase))
                    {
                        field = f;
                        break;
                    }
                }

                if (field == null)
                {
                    throw new Exception($"Field '{fieldName}' not found");
                }

                // Add sorting
                ScheduleSortGroupField sortField = new ScheduleSortGroupField(field.FieldId);
                sortField.SortOrder = ascending ? ScheduleSortOrder.Ascending : ScheduleSortOrder.Descending;

                definition.AddSortGroupField(sortField);

                trans.Commit();

                return new
                {
                    success = true,
                    scheduleId = scheduleId,
                    scheduleName = schedule.Name,
                    fieldName = fieldName,
                    sortOrder = ascending ? "Ascending" : "Descending",
                    totalSortFields = definition.GetSortGroupFieldCount()
                };
            }
        }

        #endregion

        #region 5. Set Schedule Grouping

        public static object SetScheduleGrouping(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int scheduleId = payload.GetProperty("schedule_id").GetInt32();
            string fieldName = payload.GetProperty("field_name").GetString();
            bool showHeader = payload.TryGetProperty("show_header", out var sh) ? sh.GetBoolean() : true;
            bool showFooter = payload.TryGetProperty("show_footer", out var sf) ? sf.GetBoolean() : false;
            bool showBlankLine = payload.TryGetProperty("show_blank_line", out var sb) ? sb.GetBoolean() : true;

            ViewSchedule schedule = doc.GetElement(new ElementId(scheduleId)) as ViewSchedule;
            if (schedule == null)
            {
                throw new Exception($"Schedule {scheduleId} not found");
            }

            using (var trans = new Transaction(doc, "Set Schedule Grouping"))
            {
                trans.Start();

                ScheduleDefinition definition = schedule.Definition;

                // Find field
                ScheduleField field = null;
                for (int i = 0; i < definition.GetFieldCount(); i++)
                {
                    var f = definition.GetField(i);
                    if (f.GetName().Equals(fieldName, StringComparison.OrdinalIgnoreCase))
                    {
                        field = f;
                        break;
                    }
                }

                if (field == null)
                {
                    throw new Exception($"Field '{fieldName}' not found");
                }

                // Create group field
                ScheduleSortGroupField groupField = new ScheduleSortGroupField(field.FieldId);
                groupField.ShowHeader = showHeader;
                groupField.ShowFooter = showFooter;
                groupField.ShowBlankLine = showBlankLine;

                definition.AddSortGroupField(groupField);

                trans.Commit();

                return new
                {
                    success = true,
                    scheduleId = scheduleId,
                    scheduleName = schedule.Name,
                    fieldName = fieldName,
                    showHeader = showHeader,
                    showFooter = showFooter,
                    showBlankLine = showBlankLine
                };
            }
        }

        #endregion

        #region 6. Calculate Schedule Totals

        public static object CalculateScheduleTotals(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int scheduleId = payload.GetProperty("schedule_id").GetInt32();
            string fieldName = payload.GetProperty("field_name").GetString();

            ViewSchedule schedule = doc.GetElement(new ElementId(scheduleId)) as ViewSchedule;
            if (schedule == null)
            {
                throw new Exception($"Schedule {scheduleId} not found");
            }

            using (var trans = new Transaction(doc, "Calculate Schedule Totals"))
            {
                trans.Start();

                ScheduleDefinition definition = schedule.Definition;

                // Find field
                ScheduleField field = null;
                for (int i = 0; i < definition.GetFieldCount(); i++)
                {
                    var f = definition.GetField(i);
                    if (f.GetName().Equals(fieldName, StringComparison.OrdinalIgnoreCase))
                    {
                        field = f;
                        break;
                    }
                }

                if (field == null)
                {
                    throw new Exception($"Field '{fieldName}' not found");
                }

                // Enable calculate totals
                field.DisplayType = ScheduleFieldDisplayType.Totals;

                trans.Commit();

                // Get table data to calculate actual sum
                TableData tableData = schedule.GetTableData();
                TableSectionData sectionData = tableData.GetSectionData(SectionType.Body);

                double total = 0;
                int fieldIndex = -1;

                // Find field column index
                for (int i = 0; i < definition.GetFieldCount(); i++)
                {
                    if (definition.GetField(i).FieldId == field.FieldId)
                    {
                        fieldIndex = i;
                        break;
                    }
                }

                if (fieldIndex >= 0)
                {
                    for (int row = 0; row < sectionData.NumberOfRows; row++)
                    {
                        string cellText = schedule.GetCellText(SectionType.Body, row, fieldIndex);
                        if (double.TryParse(cellText, out double value))
                        {
                            total += value;
                        }
                    }
                }

                return new
                {
                    success = true,
                    scheduleId = scheduleId,
                    scheduleName = schedule.Name,
                    fieldName = fieldName,
                    total = total,
                    rowCount = sectionData.NumberOfRows
                };
            }
        }

        #endregion

        #region 7. Format Schedule Field

        public static object FormatScheduleField(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int scheduleId = payload.GetProperty("schedule_id").GetInt32();
            string fieldName = payload.GetProperty("field_name").GetString();

            ViewSchedule schedule = doc.GetElement(new ElementId(scheduleId)) as ViewSchedule;
            if (schedule == null)
            {
                throw new Exception($"Schedule {scheduleId} not found");
            }

            using (var trans = new Transaction(doc, "Format Schedule Field"))
            {
                trans.Start();

                ScheduleDefinition definition = schedule.Definition;

                // Find field
                ScheduleField field = null;
                for (int i = 0; i < definition.GetFieldCount(); i++)
                {
                    var f = definition.GetField(i);
                    if (f.GetName().Equals(fieldName, StringComparison.OrdinalIgnoreCase))
                    {
                        field = f;
                        break;
                    }
                }

                if (field == null)
                {
                    throw new Exception($"Field '{fieldName}' not found");
                }

                // Apply formatting options
                if (payload.TryGetProperty("heading", out var heading))
                {
                    field.ColumnHeading = heading.GetString();
                }

                if (payload.TryGetProperty("heading_orientation", out var orient))
                {
                    string orientation = orient.GetString().ToLower();
                    field.HeadingOrientation = orientation == "horizontal"
                        ? ScheduleHeadingOrientation.Horizontal
                        : ScheduleHeadingOrientation.Vertical;
                }

                if (payload.TryGetProperty("horizontal_alignment", out var hAlign))
                {
                    string alignment = hAlign.GetString().ToLower();
                    field.HorizontalAlignment = alignment switch
                    {
                        "left" => ScheduleHorizontalAlignment.Left,
                        "center" => ScheduleHorizontalAlignment.Center,
                        "right" => ScheduleHorizontalAlignment.Right,
                        _ => ScheduleHorizontalAlignment.Left
                    };
                }

                if (payload.TryGetProperty("width", out var width))
                {
                    field.SheetColumnWidth = width.GetDouble();
                }

                trans.Commit();

                return new
                {
                    success = true,
                    scheduleId = scheduleId,
                    scheduleName = schedule.Name,
                    fieldName = fieldName,
                    columnHeading = field.ColumnHeading,
                    width = field.SheetColumnWidth
                };
            }
        }

        #endregion

        #region 8. Export Schedule to CSV

        public static object ExportScheduleToCSV(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            int scheduleId = payload.GetProperty("schedule_id").GetInt32();
            string outputPath = payload.GetProperty("output_path").GetString();

            ViewSchedule schedule = doc.GetElement(new ElementId(scheduleId)) as ViewSchedule;
            if (schedule == null)
            {
                throw new Exception($"Schedule {scheduleId} not found");
            }

            // Use Revit's built-in export
            ViewScheduleExportOptions options = new ViewScheduleExportOptions();
            options.TextQualifier = ExportTextQualifier.DoubleQuote;
            options.FieldDelimiter = ",";

            string directory = Path.GetDirectoryName(outputPath);
            string fileName = Path.GetFileNameWithoutExtension(outputPath);

            if (!Directory.Exists(directory))
            {
                Directory.CreateDirectory(directory);
            }

            schedule.Export(directory, fileName, options);

            return new
            {
                success = true,
                scheduleId = scheduleId,
                scheduleName = schedule.Name,
                outputPath = Path.Combine(directory, fileName + ".csv"),
                exportedRows = schedule.GetTableData().GetSectionData(SectionType.Body).NumberOfRows
            };
        }

        #endregion

        #region 9. Create Key Schedule

        public static object CreateKeySchedule(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string scheduleName = payload.GetProperty("name").GetString();
            string category = payload.GetProperty("category").GetString();

            if (!Enum.TryParse(category, out BuiltInCategory builtInCat))
            {
                throw new Exception($"Unknown category: {category}");
            }

            using (var trans = new Transaction(doc, "Create Key Schedule"))
            {
                trans.Start();

                ElementId categoryId = new ElementId(builtInCat);
                ViewSchedule schedule = ViewSchedule.CreateKeySchedule(doc, categoryId);
                schedule.Name = scheduleName;

                trans.Commit();

                return new
                {
                    success = true,
                    scheduleId = schedule.Id.IntegerValue,
                    scheduleName = schedule.Name,
                    category = category,
                    isKeySchedule = schedule.Definition.IsKeySchedule
                };
            }
        }

        #endregion

        #region 10. Create Material Takeoff

        public static object CreateMaterialTakeoff(UIApplication app, JsonElement payload)
        {
            var doc = app.ActiveUIDocument.Document;
            string scheduleName = payload.GetProperty("name").GetString();
            string category = payload.GetProperty("category").GetString();

            if (!Enum.TryParse(category, out BuiltInCategory builtInCat))
            {
                throw new Exception($"Unknown category: {category}");
            }

            using (var trans = new Transaction(doc, "Create Material Takeoff"))
            {
                trans.Start();

                ElementId categoryId = new ElementId(builtInCat);
                ViewSchedule schedule = ViewSchedule.CreateMaterialTakeoff(doc, categoryId);
                schedule.Name = scheduleName;

                trans.Commit();

                return new
                {
                    success = true,
                    scheduleId = schedule.Id.IntegerValue,
                    scheduleName = schedule.Name,
                    category = category,
                    isMaterialTakeoff = schedule.IsMaterialTakeoff
                };
            }
        }

        #endregion
    }
}
