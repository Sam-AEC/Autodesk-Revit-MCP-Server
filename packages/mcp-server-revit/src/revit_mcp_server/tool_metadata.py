"""Presentation metadata for the MCP tool listing.

Providers define tools with terse descriptions and schemas that often leave
individual parameters undocumented. MCP directories (Glama, ToolBench, Smithery,
...) and the LLMs that call the tools both score/depend on three things: a clear
description, a documented input schema, and behaviour annotations
(readOnlyHint / destructiveHint / idempotentHint / openWorldHint).

This module layers that metadata on top of the provider definitions at listing
time. It never changes what a tool does or how it is gated: `enrich_tool` returns
a copy, and the annotations are *derived from* the existing `is_mutating` /
`destructive` flags plus an explicit table of the few tools whose flag alone
would be misleading (for example exports, which are not gated but do write files).
"""
from __future__ import annotations

import copy
from typing import Any

from mcp.types import Tool, ToolAnnotations

from .providers.base import ProviderTool

APPROVAL_SUFFIX = (
    " Write operation: when approval mode is 'required' (the default) it only runs "
    "with the plan_id of an approved plan (see plan_actions and approve_plan)."
)

PLAN_ID_DESCRIPTION = (
    "ID of an approved ActionPlan authorising this write (created with plan_actions, "
    "approved with approve_plan). Required while approval mode is 'required'."
)

# --------------------------------------------------------------------------- #
# Tool descriptions (only tools whose provider-defined text is too terse)
# --------------------------------------------------------------------------- #
DESCRIPTIONS: dict[str, str] = {
    # --- Revit: model authoring -------------------------------------------
    "revit_health": "Check that the Revit bridge is reachable and return its status information. Call this first to confirm Revit is running.",
    "revit_create_wall": "Create a straight wall between two points on a level in the active Revit document. Coordinates and height are in feet (Revit internal units).",
    "revit_create_floor": "Create a floor on a level from a closed boundary of points in the active Revit document. Coordinates are in feet.",
    "revit_create_roof": "Create a roof on a level from a closed footprint of points, with an optional slope, in the active Revit document. Coordinates are in feet.",
    "revit_list_levels": "List all levels in the active Revit project with their names and elevations.",
    "revit_list_views": "List all views in the active Revit project with their names, ids and view types.",
    "revit_list_elements": "List the elements of one Revit category (for example Walls, Floors, Roofs, Doors or Windows) in the active document.",
    "revit_get_document_info": "Return metadata about the active Revit document, such as its title, path and workshare status.",
    "revit_create_level": "Create a new level with the given name at the given elevation (feet) in the active Revit document.",
    "revit_save_document": "Save the active Revit document, optionally to a path inside the allowed workspace directories.",
    "revit_create_grid": "Create a straight grid line between two points in the active Revit document. Coordinates are in feet.",
    "revit_create_room": "Create a room at an x/y point on a level, with a name and number, in the active Revit document. The point must lie inside an enclosed area.",
    "revit_delete_element": "Delete one element by its Revit ElementId from the active document. Dependent elements (for example hosted doors) may be deleted with it.",
    "revit_place_family_instance": "Place an instance of a loaded family type (for example furniture or equipment) at a point on a level. Coordinates are in feet.",
    "revit_place_door": "Place a door of a given family and type in a host wall at a location. Coordinates are in feet.",
    "revit_place_window": "Place a window of a given family and type in a host wall at a location. Coordinates are in feet.",
    "revit_list_families": "List the families loaded in the active Revit document together with their types.",
    "revit_create_floor_plan_view": "Create a floor plan view for the named level in the active Revit document.",
    "revit_create_3d_view": "Create a new 3D view with the given name in the active Revit document.",
    "revit_create_section_view": "Create a section view between two points with the given height in the active Revit document. Coordinates and height are in feet.",
    "revit_get_element_parameters": "Return every instance parameter of one element (name, value, storage type and read-only flag).",
    "revit_set_parameter_value": "Set one instance parameter on one element to a new value in the active Revit document.",
    "revit_get_parameter_value": "Read the value of one named parameter on one element.",
    "revit_list_shared_parameters": "List the shared parameters defined in the active Revit document.",
    "revit_create_shared_parameter": "Create a new shared parameter with a name, parameter group and data type in the active Revit document.",
    "revit_list_project_parameters": "List the project parameters defined in the active Revit document with the categories they are bound to.",
    "revit_create_project_parameter": "Create a new project parameter and bind it to a category in the active Revit document.",
    "revit_batch_set_parameters": "Set the same parameter to the same value on many elements, given by ElementId, in one Revit transaction.",
    "revit_get_type_parameters": "Return the type parameters of the family type that an element belongs to.",
    "revit_set_type_parameter": "Set one type parameter on the family type of an element. This changes every instance of that type.",
    "revit_list_sheets": "List all sheets in the active Revit project with their numbers, names and ids.",
    "revit_create_sheet": "Create a new sheet with a name, number and title block in the active Revit document.",
    "revit_delete_sheet": "Delete a sheet by ElementId. Views placed on it are not deleted, only their viewports.",
    "revit_place_viewport_on_sheet": "Place a view on a sheet at an x/y position (feet on the sheet).",
    "revit_batch_create_sheets_from_csv": "Create many sheets from a CSV file inside the allowed workspace, using the named title block.",
    "revit_populate_titleblock": "Write a set of parameter values into the title block of a sheet.",
    "revit_list_titleblocks": "List the title block family types available in the active Revit document.",
    "revit_get_sheet_info": "Return detailed information about one sheet, such as its number, name, title block and placed views.",
    "revit_duplicate_sheet": "Duplicate a sheet, optionally with its views, using one of Revit's duplicate options.",
    "revit_renumber_sheets": "Renumber all sheets in one batch using a prefix and a starting number.",
    "revit_get_selection": "Return the ElementIds of the elements currently selected in the Revit UI.",
    "revit_set_selection": "Replace the current Revit UI selection with the given ElementIds. Does not modify the model.",
    "revit_select_by_unique_ids": "Select elements by UniqueId and zoom to them in the active view. Changes the Revit UI selection and view only, not the model.",
    "revit_create_text_note": "Create a text note at an x/y position in a view of the active Revit document.",
    "revit_create_tag": "Tag one element at an x/y position in a view.",
    "revit_create_column": "Create a structural column of a given family type at an x/y point on a level. Coordinates are in feet.",
    "revit_create_beam": "Create a structural beam of a given family type between two x/y points on a level. Coordinates are in feet.",
    "revit_create_foundation": "Create a foundation element of a given family type at a point on a level. Coordinates are in feet.",
    "revit_create_duct": "Create a duct between two points at an elevation on a level, with a mechanical system type and duct type. Coordinates are in feet.",
    "revit_create_pipe": "Create a pipe between two points at an elevation on a level, with a piping system type and pipe type. Coordinates are in feet.",
    "revit_get_categories": "List the Revit categories available in the active document.",
    "revit_get_element_type": "Find element types by category name and family name in the active document.",
    "revit_close_document": "Close the active Revit document, optionally saving changes first.",
    "revit_create_new_document": "Create a new Revit project, optionally from a template file inside the allowed workspace.",
    "revit_export_dwg": "Export a view to a DWG file at a path inside the allowed workspace. Writes a file; does not change the model.",
    "revit_export_ifc": "Export the model to an IFC file at a path inside the allowed workspace. Writes a file; does not change the model.",
    "revit_export_navisworks": "Export the model to a Navisworks NWC file at a path inside the allowed workspace. Writes a file; does not change the model.",
    "revit_export_image": "Export a view to an image file of the given pixel size at a path inside the allowed workspace. Writes a file; does not change the model.",
    "revit_render_3d": "Render a 3D view to an image file at a chosen quality level. Writes a file; does not change the model.",
    "revit_move_element": "Move one element by an offset vector in feet.",
    "revit_copy_element": "Copy one element and place the copy at an offset vector in feet from the original.",
    "revit_rotate_element": "Rotate one element about a vertical axis through a centre point by an angle in radians.",
    "revit_mirror_element": "Mirror one element about a plane given by an origin point and a normal vector.",
    "revit_pin_element": "Pin an element so it cannot be moved by accident.",
    "revit_unpin_element": "Unpin a previously pinned element so it can be moved again.",
    "revit_sync_to_central": "Synchronise a workshared model with the central model with a comment, optionally relinquishing ownership. Ignored if the document is not workshared.",
    "revit_relinquish_all": "Relinquish every element and workset the current user owns in a workshared model.",
    "revit_get_worksets": "List the worksets of a workshared model with their owners and open state.",
    "revit_create_schedule": "Create a schedule view for a category with the given name.",
    "revit_get_schedule_data": "Return the rows and columns of an existing schedule.",
    "revit_get_element_bounding_box": "Return the axis-aligned bounding box (min and max corner, feet) of an element.",
    "revit_get_phases": "List the project phases of the active Revit document.",
    "revit_get_phase_filters": "List the phase filters of the active Revit document.",
    "revit_get_design_options": "List the design option sets and options of the active Revit document.",
    "revit_create_group": "Create a model group from a list of ElementIds, with a name.",
    "revit_ungroup": "Dissolve a model group into its member elements.",
    "revit_get_group_members": "List the member elements of a model group.",
    "revit_get_rvt_links": "List the linked Revit models (link types) in the active document.",
    "revit_get_link_instances": "List the placed instances of linked Revit models in the active document.",
    "revit_create_conduit": "Create an electrical conduit between two points at a given diameter on a level. Coordinates and diameter are in feet.",
    "revit_check_clashes": "Check for geometric clashes between elements of two categories, within a tolerance (feet). Read-only.",
    "revit_create_material": "Create a new material with a colour, transparency, shininess and smoothness.",
    "revit_set_element_material": "Assign a material, by name, to an element or to one of its faces.",
    "revit_convert_to_group": "Convert a set of elements into a named model group.",
    "revit_edit_family": "Open a family for editing in the Revit family editor.",
    "revit_create_dimension": "Create a linear dimension between two points or two elements in the active view.",
    "revit_get_revision_sequences": "List the revision sequences defined in the active Revit document.",
    "revit_tag_all_in_view": "Tag every element of a category in the active view.",
    "revit_get_view_templates": "List the view templates available in the active Revit document.",
    "revit_apply_view_template": "Apply a view template to a view.",
    "revit_calculate_material_quantities": "Calculate material volumes and areas for all elements of a category. Read-only.",
    "revit_get_warnings": "Return the current warnings of the active Revit project (for example overlapping or duplicate elements).",
    "revit_invoke_method": (
        "Advanced escape hatch: call any public Revit API method by class and method name through reflection, "
        "optionally inside a transaction. Can change anything the Revit API can change; prefer a dedicated tool."
    ),
    "revit_reflect_get": "Advanced: read any public Revit API property of an object identified by target_id, through reflection. Read-only.",
    "revit_reflect_set": "Advanced escape hatch: set any writable Revit API property of an object identified by target_id, through reflection. Prefer a dedicated tool.",
    # --- Approval tools ----------------------------------------------------
    "plan_actions": (
        "Create a draft ActionPlan describing the model changes you want to make, capturing the before-state of each. "
        "Nothing is changed in the model; the plan must be approved before any write tool will run."
    ),
    "list_pending_plans": "List all ActionPlans that are waiting for review. Read-only.",
    "approve_plan": "Approve a pending ActionPlan so that its actions may be executed. This is the human approval step.",
    "reject_plan": "Reject and archive a pending ActionPlan so that it can never be executed.",
    "get_proof_bundle": "Return the proof bundle (plan hash, approver, document, per-element before and new values, skipped elements and execution outcome) of a finished ActionPlan. Read-only.",
    "plan_revert": "Draft a new ActionPlan that sets each parameter back to the before value recorded in an executed plan's proof bundle. Refuses if the plan was not fully executed, a before value is missing, or the model changed since. Never executes; the draft needs approval.",
    "rollback_plan": "Undo an already executed ActionPlan by applying the inverse of each recorded change, in reverse order. Actions without a rollback handler are reported as warnings.",
    # --- Modules (panel commands) -----------------------------------------
    "module_list_commands": "List all registered modules and the commands they expose to the dockable Revit panel. Read-only.",
    "familytype_mapper_audit_families": "Audit the families in a saved snapshot and report problems such as unmapped or inconsistent family types. Read-only.",
    "familytype_mapper_list_type_mappings": "List family-type mappings found in a saved snapshot, optionally for one category. Read-only.",
    "hello_world_say_hello": "Example module command that returns a greeting; use it to confirm the module system works.",
    "model_inspector_summarize_model": "Summarise a saved snapshot, for example element counts by category. Read-only.",
    "model_inspector_ask": "Answer a question about a saved snapshot by filtering its element records with the filter DSL. Read-only.",
    "model_inspector_list_groups": "List the model groups found in a saved snapshot. Read-only.",
    "model_inspector_inspect_selection": "Return the snapshot records of the given elements (by UniqueId). Read-only.",
    "model_inspector_save_query": "Save a named filter query so it can be re-run later with model_inspector_run_saved_query.",
    "model_inspector_run_saved_query": "Run a previously saved named query against a saved snapshot. Read-only.",
    "model_inspector_list_saved_queries": "List the saved named queries. Read-only.",
    "parameter_manager_filter_params": "Return a parameter grid for the elements of a snapshot that match a filter, optionally including read-only parameters. Read-only.",
    "parameter_manager_diff_params": "Compare parameter values between two saved snapshots and list the differences. Read-only.",
    "parameter_manager_plan_set_params": "Create a draft ActionPlan that sets parameter values on the elements of a snapshot matching a filter. Review and approve the plan before it runs.",
    "parameter_manager_export_params_csv": "Export parameters of the matching snapshot elements to a CSV file in the workspace. Writes a file; does not change the model.",
    "parameter_manager_import_params_csv": "Read parameter values from a CSV file in the workspace and create a draft ActionPlan that applies them. Does not change the model; review and approve the plan before it runs.",
    "links_worksets_audit_audit": "Check linked models and worksets for problems (unloaded or missing links, links not pinned or placed Origin to Origin, empty or default-named worksets, worksets owned by someone else, elements on the wrong workset) and give plain next steps. Read-only.",
    "qaqc_checker_run_check": "Run a QA/QC rule pack against a saved snapshot and record the issues it finds.",
    "qaqc_checker_list_issues": "List recorded QA/QC issues for a document, optionally filtered by status and severity. Read-only.",
    "qaqc_checker_resolve_issue": "Mark one recorded QA/QC issue as resolved.",
    "clash_triage_match_clashes": "Match each clash from a Navisworks clash test to the Revit elements it involves, by UniqueId or IFC GUID, and say how sure each match is (exact, ambiguous or unmatched). Never guesses and never changes the model; records the result as issues in the workspace.",
    "clash_triage_list_clash_issues": "List the clash issues recorded by clash triage, optionally filtered by status and match confidence. Read-only.",
    "qaqc_checker_list_rules": "List the QA/QC rules that are available, optionally for one rule pack. Read-only.",
    "sheet_view_audit_run_audit": "Check the sheets and views in a saved snapshot for empty sheets, unplaced views, duplicate sheet numbers, missing sheet parameters and default view names. Read-only.",
    "warnings_triage_review_warnings": "Group the open project's Revit warnings by type, rank them by how many elements they touch, flag duplicate marks, overlapping elements and rooms not enclosed for the coordinator, and suggest a next step for each group. Read-only.",
    "bcf_exchange_export_bcf": "Save issues (your own list and/or the recorded QA/QC issues) to a BCF 2.1 .bcfzip file in the workspace. Writes a file; does not change the model. Not yet checked against other BCF tools.",
    "bcf_exchange_import_bcf": "Read a BCF .bcfzip file from the workspace and return its issues (title, description, status, priority, element ids). Read-only; unsafe zip files are refused.",
    "recipe_runner_run_recipe": "Run a named automation recipe (a YAML-defined sequence of tool calls) with arguments; set dry_run to list the steps without executing them.",
    "recipe_runner_list_recipes": "List the available automation recipes. Read-only.",
    "recipe_runner_list_runs": "List past recipe runs, optionally for one recipe. Read-only.",
    "recipe_runner_get_run_status": "Return the status and results of one recipe run. Read-only.",
    "report_generator_export_excel": "Export a snapshot (optionally filtered, with chosen parameters and QA/QC findings) to an Excel workbook in the workspace. Writes a file; does not change the model.",
    "report_generator_build_review_pack": "Build one Excel 'Model review' workbook from a snapshot: cover, findings from the QA/QC rules, counts by category and what to do next. Writes a file; does not change the model.",
    "report_generator_export_sqlite_summary": "Export a summary of a snapshot to a SQLite database file in the workspace. Writes a file; does not change the model.",
    "selection_tools_set_selection": "Select the given elements (by UniqueId) in the Revit UI. Does not modify the model.",
    "selection_tools_save_selection": "Save a set of element UniqueIds under a name for later restore.",
    "selection_tools_restore_selection": "Re-select a previously saved named selection in the Revit UI.",
    "selection_tools_select_by_query": "Select in Revit the elements of a snapshot that match a filter query.",
    "selection_tools_list_saved_selections": "List the saved named selections. Read-only.",
    "selection_tools_group_rename": "Rename a model group identified by its UniqueId.",
    "selection_tools_group_ungroup": "Ungroup a model group identified by its UniqueId. Its members stay in the model as separate elements.",
    "selection_tools_group_convert_to_detail": "Convert a model group into a detail group.",
    # --- Navisworks --------------------------------------------------------
    "navisworks_health": "Check that the Navisworks bridge is reachable and return its status.",
    "navisworks_get_document_info": "Return metadata about the active Navisworks document. Read-only.",
    "navisworks_get_model_tree": "Return the model hierarchy tree of the active Navisworks document down to a maximum depth. Read-only.",
    "navisworks_get_selection": "Return the items currently selected in Navisworks. Read-only.",
    "navisworks_append_file": "Append a model file (for example NWD, NWC or IFC) from the allowed workspace to the active Navisworks document.",
    "navisworks_refresh": "Refresh all appended files that changed on disk in the active Navisworks document.",
    "navisworks_list_viewpoints": "List the saved viewpoints of the active Navisworks document. Read-only.",
    "navisworks_create_viewpoint": "Create a saved viewpoint with the given name from the current view.",
    "navisworks_activate_viewpoint": "Switch the Navisworks view to a saved viewpoint identified by its Guid.",
    "navisworks_list_clash_tests": "List the clash tests defined in Clash Detective. Read-only.",
    "navisworks_run_clash_test": "Run one Clash Detective test, identified by Guid, and update its results.",
    "navisworks_get_clash_results": "Return the results of one clash test, with paging by skip and limit. Read-only.",
    "navisworks_invoke_method": "Advanced escape hatch: call a public C# method in Navisworks through reflection. Prefer a dedicated tool.",
    "navisworks_reflect_get": "Advanced: read a C# property of a Navisworks object through reflection. Read-only.",
    "navisworks_reflect_set": "Advanced escape hatch: set a C# property of a Navisworks object through reflection.",
    # --- Rhino -------------------------------------------------------------
    "rhino_health": "Check that the Rhino bridge is reachable and healthy.",
    "rhino_get_document_info": "Return the active Rhino document name, path, unit system and object count. Read-only.",
    "rhino_get_lines": "Return all curves and lines in the active Rhino document. Read-only.",
    "rhino_get_scene": "Return every object in the Rhino scene with its type, layer and bounding box. Read-only.",
    "rhino_list_layers": "List all layers of the Rhino document with name, colour, visibility and lock state. Read-only.",
    "rhino_clear_scene": "Delete all objects in the Rhino document, or only the objects on one layer.",
    "rhino_reflect_get": "Advanced: read a C# property of a Rhino object through reflection. Read-only.",
    "rhino_invoke_method": "Advanced escape hatch: call a public C# method on a Rhino object through reflection. Prefer a dedicated tool.",
    "rhino_reflect_set": "Advanced escape hatch: set a C# property of a Rhino object through reflection.",
    # --- Graph / Speckle / jobs / snapshots --------------------------------
    "snapshot_take": "Extract and save a complete semantic BIM snapshot of the active Revit model into the workspace and return its snapshot_id.",
    "snapshot_query": "Query the element records of a saved snapshot with the filter DSL. Read-only.",
    "snapshot_diff": "Compare two saved snapshots and report added, deleted and modified elements. Read-only.",
    "speckle_health": "Check that the Speckle provider is configured and report whether it can reach the Speckle server.",
    "speckle_auth_status": "Report the current Speckle OAuth authentication status of this server (signed in or not).",
    "speckle_oauth_refresh": "Refresh the Speckle OAuth access token so later Speckle calls keep working.",
    "speckle_list_projects": "List the Speckle projects the signed-in user can access, up to a limit.",
    "speckle_get_version_metadata": "Read the metadata of one Speckle version by project and version ID. Read-only.",
    "speckle_checkout_version": "Retrieve the metadata of one Speckle version by ID. Does not change data on the Speckle server.",
    "job_status":"Return the status, progress, result or error of a background job started with run_async. Read-only.",
    "job_cancel": "Cancel a running or queued background job.",
}

# --------------------------------------------------------------------------- #
# Parameter descriptions, used only where a schema property has none.
# Lookup order: (tool, param) -> (provider, param) -> param
# --------------------------------------------------------------------------- #
PARAM_DESCRIPTIONS: dict[str, str] = {
    "element_id": "Revit ElementId (integer) of the target element.",
    "element_ids": "List of Revit ElementIds (integers).",
    "element_uids": "List of Revit UniqueIds (strings) of the target elements.",
    "name": "Name to give to the new item.",
    "snapshot_id": "ID of a saved semantic snapshot (returned by snapshot_take or revit_extract_snapshot).",
    "snapshot_a_id": "ID of the first (baseline) saved snapshot.",
    "snapshot_b_id": "ID of the second (comparison) saved snapshot.",
    "x": "X coordinate in feet (Revit internal units).",
    "y": "Y coordinate in feet (Revit internal units).",
    "z": "Z coordinate or elevation in feet (Revit internal units).",
    "start_x": "Start point X in feet.",
    "start_y": "Start point Y in feet.",
    "start_z": "Start point Z in feet.",
    "end_x": "End point X in feet.",
    "end_y": "End point Y in feet.",
    "end_z": "End point Z in feet.",
    "center_x": "X of the rotation centre in feet.",
    "center_y": "Y of the rotation centre in feet.",
    "center_z": "Z of the rotation centre in feet.",
    "plane_origin_x": "X of a point on the mirror plane, in feet.",
    "plane_origin_y": "Y of a point on the mirror plane, in feet.",
    "plane_origin_z": "Z of a point on the mirror plane, in feet.",
    "plane_normal_x": "X component of the mirror plane normal vector.",
    "plane_normal_y": "Y component of the mirror plane normal vector.",
    "plane_normal_z": "Z component of the mirror plane normal vector.",
    "angle_radians": "Rotation angle in radians (counter-clockwise positive).",
    "level": "Name of the Revit level, for example 'Level 1'.",
    "level_name": "Name of the Revit level, for example 'Level 1'.",
    "family_name": "Name of the loaded Revit family.",
    "type_name": "Name of the family type within the family.",
    "family_symbol_id": "ElementId (integer) of the family symbol (type).",
    "family_instance_id": "ElementId (integer) of the family instance.",
    "category": "Revit category name, for example 'Walls', 'Doors' or 'Windows'.",
    "category_name": "Revit category name, for example 'Walls', 'Doors' or 'Windows'.",
    "category1": "First Revit category name, for example 'Ducts'.",
    "category2": "Second Revit category name, for example 'Structural Framing'.",
    "view_id": "Revit ElementId (integer) of the view.",
    "view_name": "Name for the new view.",
    "sheet_id": "Revit ElementId (integer) of the sheet.",
    "schedule_id": "Revit ElementId (integer) of the schedule.",
    "titleblock_id": "ElementId (integer) of the title block family type.",
    "titleblock_name": "Name of the title block family type.",
    "template_id": "ElementId (integer) of the view template.",
    "template_path": "Path of a Revit template file inside the allowed workspace.",
    "wall_id": "ElementId (integer) of the host wall.",
    "group_id": "ElementId (integer) of the model group.",
    "group": "Parameter group the parameter is shown under.",
    "type": "Data type of the parameter.",
    "visible": "Whether the parameter is visible in the properties palette.",
    "output_path": "Destination file path; must be inside the allowed workspace directories.",
    "output_filename": "File name for the output, written into the workspace.",
    "csv_path": "Path of a CSV file inside the allowed workspace.",
    "csv_filename": "Name of a CSV file in the workspace.",
    "path": "File path; must be inside the allowed workspace directories.",
    "limit": "Maximum number of items to return.",
    "skip": "Number of items to skip (for paging).",
    "offset": "Number of items to skip (for paging).",
    "idempotency_key": "Optional unique key; repeating a call with the same key does not repeat the write.",
    "plan_id": "ID of an ActionPlan (from plan_actions).",
    "skipped": "Elements or parameters excluded when drafting (for example the blocked list of a parameter plan), each with a reason.",
    "approver": "Name of the person approving the plan; recorded in the proof bundle but not authenticated.",
    "allow_conflicts": "If true, draft the revert even where the model's current value differs from the value the plan wrote, listing those elements as conflicts for explicit review.",
    "actions": "List of proposed tool calls, each with a tool name and its arguments.",
    "parameter_name": "Name of the Revit parameter.",
    "param_name": "Name of the parameter.",
    "param_names": "List of parameter names.",
    "value": "New value to write; a string, number or boolean that matches the parameter's type.",
    "location": "Location object with x, y and optional z in feet.",
    "height": "Height in feet.",
    "width": "Width in pixels.",
    "quality": "Render quality level.",
    "tolerance": "Distance tolerance in feet.",
    "radius": "Radius in the document's units.",
    "diameter": "Diameter in feet.",
    "system_type": "Name of the system type (for example a piping or duct system).",
    "duct_type": "Name of the duct type.",
    "pipe_type": "Name of the pipe type.",
    "text": "Text content.",
    "comment": "Comment recorded with the operation.",
    "relinquish": "Whether to relinquish ownership of elements and worksets after syncing.",
    "save_changes": "Whether to save changes before closing.",
    "with_views": "Whether to also duplicate the views placed on the sheet.",
    "duplicate_option": "How to duplicate the sheet's content (Revit duplicate option name).",
    "prefix": "Prefix for the new sheet numbers.",
    "start_number": "First number to use.",
    "parameters": "Map of parameter name to value.",
    "color": "Colour as an object with r, g and b values (0-255) or, for Rhino, an [r, g, b] array.",
    "transparency": "Transparency of the material.",
    "shininess": "Shininess of the material (0-100).",
    "smoothness": "Smoothness of the material (0-100).",
    "reflectivity": "Reflectivity of the material (0-1).",
    "material_name": "Name of an existing material.",
    "start_point": "Start point as an object with x, y and z in feet.",
    "end_point": "End point as an object with x, y and z in feet.",
    "element1_id": "ElementId (integer) of the first element.",
    "element2_id": "ElementId (integer) of the second element.",
    "use_transaction": "Wrap the call in a Revit transaction.",
    "max_depth": "Maximum tree depth to return.",
    "filter": "Filter DSL object selecting records, for example by category, level or parameter value.",
    "element_filter": "Filter DSL object selecting elements, for example by category, level or parameter value.",
    "include_readonly": "Whether to include read-only parameters.",
    "doc_guid": "GUID of the document the issues belong to.",
    "severity": "Severity filter, for example 'error' or 'warning'.",
    "issue_id": "ID of the QA/QC issue.",
    "rule_pack": "Name of the QA/QC rule pack.",
    "class_name": "Fully qualified class name that holds the method to call.",
    "method_name": "Name of the method to call.",
    "arguments": "Positional arguments for the method, as a JSON array.",
    "target_id": "Identifier of the target object (for example a Revit ElementId).",
    "property_name": "Name of the property.",
    "guid": "Guid of the item, as returned by the corresponding list command.",
    "node_ids": "List of graph node IDs.",
    "message": "Message recorded with the operation.",
    "number": "Number (identifier string) to assign.",
    "project_id": "ID of the Speckle project.",
    "model_id": "ID of the Speckle model.",
    "version_id": "ID of the Speckle version.",
    "branch_id": "ID of the Speckle branch.",
    "object_id": "ID of the Speckle object to publish.",
    "source_model_id": "ID of the Speckle model or branch to merge from.",
    "target_model_id": "ID of the Speckle model or branch to merge into.",
    "source_application": "Name of the application the data comes from.",
    "description": "Free-text description.",
    "layer": "Name of the Rhino layer.",
    "ids": "List of Rhino object GUIDs.",
    "base_id": "GUID of the base Rhino object.",
    "cutter_ids": "List of GUIDs of Rhino objects to subtract.",
    "rotation": "Rotation object (angle and axis).",
    "node_id": "ID of the graph node.",
    "related_node_id": "ID of the related graph node.",
    "relation": "Relation type, for example SUPPORTED_BY.",
    "direction": "Relation direction to follow: incoming or outgoing.",
    "relation_types": "List of relation types to consider.",
    "node_types": "List of node types to consider.",
    "min_degree": "Minimum number of connections a node must have.",
    "attributes": "Free-form attributes stored on the relation.",
    "code": "Authorization code returned by the OAuth flow.",
    "state": "State value returned by the OAuth flow.",
    "source_id": "Identifier to translate.",
    "model_name": "Name of the Speckle model.",
    "data": "JSON object to send.",
}

# Per-tool overrides where the generic text would be wrong or vague.
TOOL_PARAM_DESCRIPTIONS: dict[tuple[str, str], str] = {
    ("revit_move_element", "x"): "X component of the offset vector in feet.",
    ("revit_move_element", "y"): "Y component of the offset vector in feet.",
    ("revit_move_element", "z"): "Z component of the offset vector in feet.",
    ("revit_copy_element", "x"): "X component of the offset vector in feet.",
    ("revit_copy_element", "y"): "Y component of the offset vector in feet.",
    ("revit_copy_element", "z"): "Z component of the offset vector in feet.",
    ("revit_place_viewport_on_sheet", "x"): "X position on the sheet in feet.",
    ("revit_place_viewport_on_sheet", "y"): "Y position on the sheet in feet.",
    ("revit_create_text_note", "x"): "X position in the view in feet.",
    ("revit_create_text_note", "y"): "Y position in the view in feet.",
    ("revit_create_tag", "x"): "X position in the view in feet.",
    ("revit_create_tag", "y"): "Y position in the view in feet.",
    ("revit_create_level", "name"): "Name of the new level.",
    ("revit_create_grid", "name"): "Name (label) of the new grid line.",
    ("revit_create_room", "name"): "Name of the new room.",
    ("revit_create_room", "number"): "Room number.",
    ("revit_create_sheet", "name"): "Name of the new sheet.",
    ("revit_create_sheet", "number"): "Sheet number, for example 'A101'.",
    ("revit_create_schedule", "name"): "Name of the new schedule.",
    ("revit_create_material", "name"): "Name of the new material.",
    ("revit_create_group", "name"): "Name of the new group.",
    ("revit_convert_to_group", "name"): "Name of the new group.",
    ("revit_create_shared_parameter", "name"): "Name of the new shared parameter.",
    ("revit_create_project_parameter", "name"): "Name of the new project parameter.",
    ("revit_create_project_parameter", "category"): "Revit category the parameter is bound to.",
    ("revit_create_shared_parameter", "type"): "Parameter data type, for example 'Text', 'Number' or 'Length'.",
    ("revit_create_project_parameter", "type"): "Parameter data type, for example 'Text', 'Number' or 'Length'.",
    ("revit_render_3d", "view_id"): "ElementId (integer) of the 3D view to render.",
    ("revit_create_floor_plan_view", "view_name"): "Name for the new floor plan view.",
    ("revit_check_clashes", "tolerance"): "Clash tolerance in feet (the add-in defaults to 0.01 ft).",
    ("revit_set_type_parameter", "element_id"): "ElementId (integer) of any element of the type to change.",
    ("revit_get_type_parameters", "element_id"): "ElementId (integer) of any element of the type to read.",
    ("revit_set_element_material", "face_index"): "Optional index of a single face; omit to apply to the whole element.",
    ("revit_save_document", "path"): "Optional path to save to; must be inside the allowed workspace directories. Omit to save in place.",
    ("navisworks_create_viewpoint", "name"): "Name of the new saved viewpoint.",
    ("navisworks_append_file", "path"): "Path of the file to append; must be inside the allowed workspace directories.",
    ("navisworks_get_clash_results", "limit"): "Maximum number of clash results to return.",
    ("hello_world_say_hello", "name"): "Name to greet.",
    ("graph_add_relation", "source_id"): "ID of the source graph node.",
    ("graph_add_relation", "target_id"): "ID of the target graph node.",
    ("graph_add_relation", "relation"): "Relation type, for example SUPPORTED_BY.",
    ("speckle_create_model", "name"): "Name of the new Speckle model.",
    ("speckle_create_branch", "name"): "Name of the new Speckle branch.",
    ("speckle_create_model", "description"): "Optional description of the new model.",
    ("speckle_create_branch", "description"): "Optional description of the new branch.",
    ("rhino_set_view", "view"): "Display mode or projection to switch to.",
    ("rhino_create_box", "min_pt"): "Minimum corner as [x, y, z] in metres.",
    ("rhino_create_box", "max_pt"): "Maximum corner as [x, y, z] in metres.",
    ("rhino_create_sphere", "center"): "Centre as [x, y, z] in metres.",
    ("rhino_create_sphere", "radius"): "Radius in metres.",
    ("rhino_create_cylinder", "base"): "Base centre as [x, y, z] in metres.",
    ("rhino_create_cylinder", "height"): "Height in metres.",
    ("rhino_create_cylinder", "radius"): "Radius in metres.",
    ("rhino_boolean_union", "layer"): "Layer to place the resulting object on.",
    ("rhino_set_material", "layer"): "Apply the material to every object on this layer.",
    ("rhino_set_material", "ids"): "GUIDs of the objects to apply the material to.",
    ("rhino_set_material", "name"): "Name of the material.",
    ("rhino_set_material", "color"): "Material colour as an [r, g, b] array (0-255).",
    ("rhino_set_material", "transparency"): "Transparency of the material (0-1).",
    ("rhino_transform_objects", "ids"): "GUIDs of the objects to transform.",
    ("rhino_transform_objects", "translation"): "Translation vector [x, y, z] in metres.",
    ("rhino_transform_objects", "scale"): "Scale factors [x, y, z].",
    ("rhino_run_python", "code"): "IronPython source to run inside Rhino; stdout is captured and returned.",
    ("revit_execute_python", "script"): "Python/IronPython source to run inside Revit with access to the Revit API.",
    ("revit_invoke_method", "target_id"): "Identifier of the object to call the method on; omit for a static method.",
    ("revit_reflect_set", "value"): "New value for the property.",
    ("navisworks_reflect_set", "value"): "New value for the property.",
    ("rhino_reflect_set", "value"): "New value for the property.",
    ("ifc_get_properties", "element_id"): "GlobalId or step id of the IFC element.",
    ("ifc_get_bounding_box", "element_id"): "GlobalId or step id of the IFC element.",
    ("ifc_query_elements", "property_value"): "Value the property must have.",
    ("ifc_query_elements", "guid"): "IFC GlobalId to look for.",
    ("ifc_query_elements", "name_filter"): "Substring that the element name must contain.",
    ("ifc_query_elements", "ifc_class"): "IFC class to filter by, for example IfcWall.",
    ("exporter_to_sqlite", "db_path"): "SQLite database file path; must be inside the allowed workspace directories.",
    ("exporter_graph_to_sqlite", "db_path"): "SQLite database file path; must be inside the allowed workspace directories.",
}

# --------------------------------------------------------------------------- #
# Behaviour annotations
# --------------------------------------------------------------------------- #
# Tools that the gate does NOT treat as mutating (is_mutating=False) but that are
# not read-only either (they write files, plan state, UI state or in-memory
# state). value = (destructiveHint, idempotentHint).
NOT_READ_ONLY: dict[str, tuple[bool, bool]] = {
    "plan_actions": (False, False),
    "approve_plan": (False, True),
    "reject_plan": (False, True),
    "rollback_plan": (True, False),
    "plan_revert": (False, False),
    "execute_plan": (True, False),
    "revit_extract_snapshot": (False, False),
    "snapshot_take": (False, False),
    "revit_export_dwg": (False, True),
    "revit_export_ifc": (False, True),
    "revit_export_navisworks": (False, True),
    "revit_export_image": (False, True),
    "revit_render_3d": (False, True),
    "revit_select_by_unique_ids": (False, True),
    "navisworks_append_file": (False, False),
    "navisworks_refresh": (False, True),
    "navisworks_activate_viewpoint": (False, True),
    "exporter_to_sqlite": (False, False),
    "exporter_graph_to_sqlite": (False, False),
    "parameter_manager_export_params_csv": (False, True),
    "report_generator_export_excel": (False, True),
    "report_generator_build_review_pack": (False, True),
    "report_generator_export_sqlite_summary": (False, True),
    "model_inspector_save_query": (False, True),
    "selection_tools_save_selection": (False, True),
    "bcf_exchange_export_bcf": (False, True),
    "qaqc_checker_run_check": (False, False),
    "clash_triage_match_clashes": (False, True),
    "qaqc_checker_resolve_issue": (False, True),
    "recipe_runner_run_recipe": (True, False),
    "aec_register_mapping": (False, True),
    "graph_compile": (False, False),
    "graph_add_relation": (False, True),
    "speckle_oauth_start": (False, False),
    "speckle_oauth_exchange_code": (False, False),
    "speckle_oauth_refresh": (False, True),
    "speckle_checkout_version": (False, True),
    "job_cancel": (True, True),
    "rhino_generate_diagrid_tower": (False, False),
}

# Mutating tools that only add things (or only change UI/plan state): they cannot
# destroy existing model content, so destructiveHint is false. Every other
# mutating tool defaults to destructive=true, which is the safe MCP default.
ADDITIVE_NAME_PARTS = frozenset({"create", "place", "copy", "duplicate", "tag", "pin", "unpin"})
ADDITIVE_NAMES = frozenset(
    {
        "revit_save_document",
        "revit_set_selection",
        "selection_tools_set_selection",
        "selection_tools_restore_selection",
        "selection_tools_select_by_query",
        "navisworks_run_clash_test",
        "speckle_publish_version",
        "speckle_send_object",
    }
)
# Verbs that make a repeated identical call a no-op.
IDEMPOTENT_NAME_PARTS = frozenset({"set", "pin", "unpin", "delete", "save", "apply", "restore", "select"})
# Providers whose tools talk to remote services (open world).
OPEN_WORLD_PROVIDERS = frozenset({"speckle", "aps", "autodesk_data", "cloud"})

_ACRONYMS = {
    "ifc": "IFC", "dwg": "DWG", "nwc": "NWC", "rvt": "RVT", "csv": "CSV", "sqlite": "SQLite",
    "aps": "APS", "3d": "3D", "qaqc": "QA/QC", "id": "ID", "ids": "IDs", "uids": "UIDs", "aec": "AEC",
}


def humanize(name: str) -> str:
    return " ".join(_ACRONYMS.get(p, p.capitalize()) for p in name.split("_"))


def annotations_for(provider_id: str, tool: ProviderTool) -> ToolAnnotations:
    """Derive MCP behaviour hints from the tool's existing gate flags."""
    parts = set(tool.name.split("_"))
    open_world = provider_id in OPEN_WORLD_PROVIDERS or provider_id.startswith("proxy")

    if tool.name in NOT_READ_ONLY:
        read_only, (destructive, idempotent) = False, NOT_READ_ONLY[tool.name]
    elif tool.is_mutating:
        read_only = False
        if tool.destructive:
            destructive = True
        else:
            destructive = not (
                tool.name in ADDITIVE_NAMES or bool(parts & ADDITIVE_NAME_PARTS)
            )
        idempotent = bool(parts & IDEMPOTENT_NAME_PARTS) and not (parts & {"create"})
    else:
        read_only, destructive, idempotent = True, False, True

    if tool.destructive:
        destructive = True
    return ToolAnnotations(
        title=humanize(tool.name),
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=open_world,
    )


def enrich_tool(provider_id: str, tool: ProviderTool) -> Tool:
    """Return the MCP `Tool` for a provider tool, with fuller metadata.

    The provider's own description is kept when it is already substantial; the
    approval requirement is appended to every mutating tool.
    """
    description = DESCRIPTIONS.get(tool.name, tool.description)
    if tool.is_mutating and "plan_id" not in description:
        description += APPROVAL_SUFFIX

    schema = copy.deepcopy(tool.input_schema) if tool.input_schema else {"type": "object"}
    schema.setdefault("type", "object")
    props: dict[str, Any] = schema.setdefault("properties", {})
    if tool.is_mutating and "plan_id" not in props:
        props["plan_id"] = {"type": "string", "description": PLAN_ID_DESCRIPTION}
    for key, prop in props.items():
        if not isinstance(prop, dict) or prop.get("description"):
            continue
        text = (
            TOOL_PARAM_DESCRIPTIONS.get((tool.name, key))
            or PARAM_DESCRIPTIONS.get(key)
        )
        if text:
            prop["description"] = text
    return Tool(
        name=tool.name,
        title=humanize(tool.name),
        description=description,
        inputSchema=schema,
        annotations=annotations_for(provider_id, tool),
    )
