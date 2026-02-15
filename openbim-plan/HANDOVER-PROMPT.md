# Ralph Scaffolding Loop - Solibri-Like Model Checker

## Delivery Plan Overview

Build a comprehensive BIM model checking and quality assurance system (better than Solibri) using the Revit MCP Server framework.

---

## RALPH SCAFFOLDING LOOP: ORIENT > BUILD > TEST > REFLECT > ADVANCE

Execute per scaffold. Commit per task. Test per task. Push per scaffold.

### Scaffold 1: Core Model Validation Framework
**Goal:** Create foundation for model checking with rule engine

**Task 1.1:** Create model checker module structure
- Location: `packages/model-checker/`
- Files: `__init__.py`, `rule_engine.py`, `validator.py`
- Test: Import modules successfully

**Task 1.2:** Implement basic rule engine
- Function: `RuleEngine` class with rule registration
- Validation: Rules can be added and executed
- Test: Create and execute a simple rule

**Task 1.3:** Create validation report structure
- Class: `ValidationReport` with issues tracking
- Properties: severity, category, element_id, description
- Test: Generate report with sample issues

### Scaffold 2: Geometric Clash Detection
**Goal:** Detect spatial conflicts between elements

**Task 2.1:** Implement bounding box intersection checker
- Function: `check_bounding_box_clashes()`
- Use: `revit.get_element_bounding_box` tool
- Test: Detect overlapping elements

**Task 2.2:** Create detailed geometry clash detection
- Function: `check_precise_clashes()` using solid geometry
- Use: `revit.invoke_method` for GeometryElement
- Test: Find actual geometric intersections

**Task 2.3:** Build clash visualization report
- Output: JSON with clash pairs and locations
- Include: Element IDs, clash volume, coordinates
- Test: Generate clash report for test model

### Scaffold 3: Standards Compliance Checker
**Goal:** Validate against BIM standards and naming conventions

**Task 3.1:** Implement naming convention validator
- Rules: Check view names, sheet numbers, family names
- Patterns: Regex-based validation
- Test: Flag non-compliant names

**Task 3.2:** Create parameter validation
- Check: Required parameters exist and are filled
- Validate: Parameter value ranges and formats
- Test: Detect missing/invalid parameters

**Task 3.3:** Build level and grid validation
- Rules: Check level naming, spacing, alignment
- Grid: Validate grid spacing and labeling
- Test: Report level/grid issues

### Scaffold 4: MEP Systems Validation
**Goal:** Check MEP systems for connectivity and compliance

**Task 4.1:** Implement MEP connectivity checker
- Function: `validate_mep_connections()`
- Use: `revit.get_mep_systems` tool
- Test: Find disconnected components

**Task 4.2:** Create duct/pipe sizing validation
- Check: Velocity, pressure drop, sizing
- Rules: Industry standards (ASHRAE, etc.)
- Test: Flag undersized/oversized elements

**Task 4.3:** Build clearance validation
- Function: Check minimum clearances for MEP
- Detect: Insufficient headroom, access space
- Test: Report clearance violations

### Scaffold 5: Structural Integrity Checks
**Goal:** Validate structural elements and connections

**Task 5.1:** Implement column-beam connection validator
- Check: Structural framing connections
- Use: `revit.list_elements_by_category` for structural
- Test: Find unconnected beams

**Task 5.2:** Create foundation validation
- Rules: Check foundation placement and sizing
- Validate: Foundation under all columns
- Test: Detect missing foundations

**Task 5.3:** Build load path validation
- Function: Trace load path from roof to foundation
- Check: Continuous load transfer
- Test: Report broken load paths

### Scaffold 6: Room and Space Validation
**Goal:** Validate rooms, spaces, and boundaries

**Task 6.1:** Implement room boundary checker
- Function: `validate_room_boundaries()`
- Use: `revit.get_room_boundary` tool
- Test: Find unbound or overlapping rooms

**Task 6.2:** Create area calculation validation
- Check: Room areas match requirements
- Compare: Calculated vs. required areas
- Test: Flag area discrepancies

**Task 6.3:** Build occupancy and egress validation
- Rules: Validate exit access, occupant load
- Code: Apply building code requirements
- Test: Report code violations

### Scaffold 7: Documentation Completeness
**Goal:** Ensure complete and consistent documentation

**Task 7.1:** Implement view completeness checker
- Function: `validate_view_coverage()`
- Check: All elements appear in required views
- Test: Find elements missing from plans

**Task 7.2:** Create sheet validation
- Rules: All sheets have titleblocks, views placed
- Use: `revit.list_sheets` and `revit.get_sheet_info`
- Test: Report incomplete sheets

**Task 7.3:** Build revision tracking validation
- Function: Check revision clouds and schedules
- Validate: Revisions properly documented
- Test: Find missing revision markers

### Scaffold 8: Quality Assurance Dashboard
**Goal:** Create comprehensive reporting and visualization

**Task 8.1:** Implement HTML report generator
- Output: Interactive HTML dashboard
- Include: Charts, tables, element highlighting
- Test: Generate full validation report

**Task 8.2:** Create issue prioritization system
- Function: Rank issues by severity and impact
- Categories: Critical, High, Medium, Low
- Test: Prioritized issue list

**Task 8.3:** Build export capabilities
- Formats: CSV, JSON, PDF reports
- Use: `revit.export_schedules` integration
- Test: Export reports in all formats

### Scaffold 9: MCP Integration and CLI
**Goal:** Integrate with Revit MCP Server and create user interface

**Task 9.1:** Create MCP server tools for model checking
- Tools: `solibri.run_all_checks`, `solibri.run_check_by_category`
- Integration: Add to mcp_server.py
- Test: Execute checks via MCP protocol

**Task 9.2:** Build CLI interface
- Command: `python -m model_checker --project <file> --checks <type>`
- Options: Select specific checks, output format
- Test: Run from command line

**Task 9.3:** Create automated check runner
- Function: Scheduled validation runs
- Integration: Hook into Revit events
- Test: Auto-run on file save/sync

---

## Testing Strategy

Each task must have:
1. Unit test for the function/class
2. Integration test with Revit MCP Server
3. Sample data test case
4. Performance benchmark

## Success Criteria

- All 27 tasks completed (9 scaffolds × 3 tasks)
- All tests passing (green baseline maintained)
- Complete documentation
- Working demo on sample Revit model
- Better than Solibri: faster, more comprehensive, AI-integrated

## Git Workflow

- Commit after each task completion
- Test after each commit
- Push after each scaffold (9 pushes total)
- Branch: `claude/ralph-scaffolding-solibri-NEjMU`
