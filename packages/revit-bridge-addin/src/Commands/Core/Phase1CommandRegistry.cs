using System;
using System.Text.Json;
using Autodesk.Revit.UI;
using RevitBridge.Commands.Core.Filtering;
using RevitBridge.Commands.Core.Units;
using RevitBridge.Commands.Core.Schedules;
using RevitBridge.Commands.Core.Views;

namespace RevitBridge.Commands.Core
{
    /// <summary>
    /// Registry for Phase 1 commands (40 critical tools)
    /// These are the highest priority tools based on API usage analysis
    /// </summary>
    public static class Phase1CommandRegistry
    {
        public static object Execute(UIApplication app, string tool, JsonElement payload)
        {
            return tool switch
            {
                // === FILTERING COMMANDS (15 tools) - Highest Priority ===
                // FilteredElementCollector is #1 ranked API (Score: 294)

                "revit.filter_elements_by_parameter" => FilteringCommands.FilterElementsByParameter(app, payload),
                "revit.filter_elements_by_level" => FilteringCommands.FilterElementsByLevel(app, payload),
                "revit.filter_elements_by_workset" => FilteringCommands.FilterElementsByWorkset(app, payload),
                "revit.filter_elements_by_bounding_box" => FilteringCommands.FilterElementsByBoundingBox(app, payload),
                "revit.filter_elements_intersecting" => FilteringCommands.FilterElementsIntersecting(app, payload),
                "revit.filter_elements_by_view" => FilteringCommands.FilterElementsByView(app, payload),
                "revit.find_elements_at_point" => FilteringCommands.FindElementsAtPoint(app, payload),
                "revit.filter_by_multiple_criteria" => FilteringCommands.FilterByMultipleCriteria(app, payload),
                "revit.get_all_elements_of_type" => FilteringCommands.GetAllElementsOfType(app, payload),
                "revit.get_dependent_elements" => FilteringCommands.GetDependentElements(app, payload),
                "revit.get_hosted_elements" => FilteringCommands.GetHostedElements(app, payload),
                "revit.find_similar_elements" => FilteringCommands.FindSimilarElements(app, payload),
                "revit.get_elements_by_unique_id" => FilteringCommands.GetElementsByUniqueId(app, payload),
                "revit.get_linked_elements" => FilteringCommands.GetLinkedElements(app, payload),
                // Note: trace_element_relationships can be added as extension of get_dependent_elements

                // === UNITS COMMANDS (5 tools) - Critical ===
                // UnitUtils is #15 ranked API (Score: 275)

                "revit.convert_to_internal_units" => UnitsCommands.ConvertToInternalUnits(app, payload),
                "revit.convert_from_internal_units" => UnitsCommands.ConvertFromInternalUnits(app, payload),
                "revit.get_project_units" => UnitsCommands.GetProjectUnits(app, payload),
                "revit.set_project_units" => UnitsCommands.SetProjectUnits(app, payload),
                "revit.format_value_with_units" => UnitsCommands.FormatValueWithUnits(app, payload),

                // === SCHEDULE COMMANDS (10 tools) - Critical ===
                // ViewSchedule is #146 ranked API (Score: 198)

                "revit.add_schedule_field" => ScheduleCommands.AddScheduleField(app, payload),
                "revit.remove_schedule_field" => ScheduleCommands.RemoveScheduleField(app, payload),
                "revit.set_schedule_filter" => ScheduleCommands.SetScheduleFilter(app, payload),
                "revit.set_schedule_sorting" => ScheduleCommands.SetScheduleSorting(app, payload),
                "revit.set_schedule_grouping" => ScheduleCommands.SetScheduleGrouping(app, payload),
                "revit.calculate_schedule_totals" => ScheduleCommands.CalculateScheduleTotals(app, payload),
                "revit.format_schedule_field" => ScheduleCommands.FormatScheduleField(app, payload),
                "revit.export_schedule_to_csv" => ScheduleCommands.ExportScheduleToCSV(app, payload),
                "revit.create_key_schedule" => ScheduleCommands.CreateKeySchedule(app, payload),
                "revit.create_material_takeoff" => ScheduleCommands.CreateMaterialTakeoff(app, payload),

                // === VIEW MANAGEMENT COMMANDS (10 tools) - High Value ===
                // View is #6 ranked API (Score: 283)

                "revit.create_ceiling_plan_view" => ViewManagementCommands.CreateCeilingPlanView(app, payload),
                "revit.create_elevation_view" => ViewManagementCommands.CreateElevationView(app, payload),
                "revit.duplicate_view" => ViewManagementCommands.DuplicateView(app, payload),
                "revit.set_view_template" => ViewManagementCommands.SetViewTemplate(app, payload),
                "revit.create_view_filter" => ViewManagementCommands.CreateViewFilter(app, payload),
                "revit.set_view_visibility" => ViewManagementCommands.SetViewVisibility(app, payload),
                "revit.isolate_elements_in_view" => ViewManagementCommands.IsolateElementsInView(app, payload),
                "revit.hide_elements_in_view" => ViewManagementCommands.HideElementsInView(app, payload),
                "revit.unhide_elements_in_view" => ViewManagementCommands.UnhideElementsInView(app, payload),
                "revit.crop_view" => ViewManagementCommands.CropView(app, payload),

                _ => null // Return null to let main factory handle unknown commands
            };
        }

        /// <summary>
        /// Get list of all Phase 1 command names for documentation/validation
        /// </summary>
        public static string[] GetCommandNames()
        {
            return new[]
            {
                // Filtering (15)
                "revit.filter_elements_by_parameter",
                "revit.filter_elements_by_level",
                "revit.filter_elements_by_workset",
                "revit.filter_elements_by_bounding_box",
                "revit.filter_elements_intersecting",
                "revit.filter_elements_by_view",
                "revit.find_elements_at_point",
                "revit.filter_by_multiple_criteria",
                "revit.get_all_elements_of_type",
                "revit.get_dependent_elements",
                "revit.get_hosted_elements",
                "revit.find_similar_elements",
                "revit.get_elements_by_unique_id",
                "revit.get_linked_elements",

                // Units (5)
                "revit.convert_to_internal_units",
                "revit.convert_from_internal_units",
                "revit.get_project_units",
                "revit.set_project_units",
                "revit.format_value_with_units",

                // Schedules (10)
                "revit.add_schedule_field",
                "revit.remove_schedule_field",
                "revit.set_schedule_filter",
                "revit.set_schedule_sorting",
                "revit.set_schedule_grouping",
                "revit.calculate_schedule_totals",
                "revit.format_schedule_field",
                "revit.export_schedule_to_csv",
                "revit.create_key_schedule",
                "revit.create_material_takeoff",

                // Views (10)
                "revit.create_ceiling_plan_view",
                "revit.create_elevation_view",
                "revit.duplicate_view",
                "revit.set_view_template",
                "revit.create_view_filter",
                "revit.set_view_visibility",
                "revit.isolate_elements_in_view",
                "revit.hide_elements_in_view",
                "revit.unhide_elements_in_view",
                "revit.crop_view"
            };
        }
    }
}
