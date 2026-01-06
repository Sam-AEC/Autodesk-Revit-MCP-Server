# Tool Catalog

The rebuilt MCP server exposes 25 Revit tools. Input/output schemas live under `packages/mcp-server-revit/src/revit_mcp_server/schemas.py` and are validated via JSON Schema.

Tools:
1. `revit.health`
2. `revit.open_document`
3. `revit.list_views`
4. `revit.model_health_summary`
5. `revit.warning_triage_report`
6. `revit.naming_standards_audit`
7. `revit.parameter_compliance_audit`
8. `revit.shared_parameter_binding_audit`
9. `revit.view_template_compliance_check`
10. `revit.tag_coverage_audit`
11. `revit.room_space_completeness_report`
12. `revit.link_monitor_report`
13. `revit.coordinate_sanity_check`
14. `revit.export_schedules`
15. `revit.export_quantities`
16. `revit.baseline_export`
17. `revit.baseline_diff`
18. `revit.batch_create_sheets_from_csv`
19. `revit.batch_place_views_on_sheets`
20. `revit.titleblock_fill_from_csv`
21. `revit.create_print_set`
22. `revit.export_pdf_by_sheet_set`
23. `revit.export_dwg_by_sheet_set`
24. `revit.export_ifc_named_setup`
25. `revit.publish_package_builder`
26. `revit.export_report`
