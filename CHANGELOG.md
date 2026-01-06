# Changelog

All notable changes to MCP Revit Bridge will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-07

### Added
- Initial release of MCP Revit Bridge
- MCP server exposing 25 Revit tools via stdio protocol
- Revit bridge add-in (.NET 4.8) with HTTP listener and ExternalEvent pattern
- Mock mode for CI/testing without Revit dependency
- Workspace sandboxing with configurable allowed directories
- JSON schema validation for all tool inputs using Pydantic
- Structured audit logging with request tracking
- Demo client showcasing end-to-end workflow
- Comprehensive documentation (install, tools, architecture, security)
- GitHub Actions CI with Python linting and testing
- PowerShell helper scripts for development and deployment

### Tool Catalog
- Health check: `revit.health`
- Document operations: `open_document`, `list_views`
- QA audits: `model_health_summary`, `warning_triage_report`, `naming_standards_audit`, `parameter_compliance_audit`, `shared_parameter_binding_audit`, `view_template_compliance_check`, `tag_coverage_audit`, `room_space_completeness_report`, `link_monitor_report`, `coordinate_sanity_check`
- Export operations: `export_schedules`, `export_quantities`, `export_pdf_by_sheet_set`, `export_dwg_by_sheet_set`, `export_ifc_named_setup`, `export_report`
- Baseline tracking: `baseline_export`, `baseline_diff`
- Sheet automation: `batch_create_sheets_from_csv`, `batch_place_views_on_sheets`, `titleblock_fill_from_csv`, `create_print_set`
- Package builder: `publish_package_builder`

[Unreleased]: https://github.com/Sam-AEC/mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Sam-AEC/mcp/releases/tag/v0.1.0
