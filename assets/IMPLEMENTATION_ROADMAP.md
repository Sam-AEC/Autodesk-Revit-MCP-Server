# Revit MCP Toolbox - Implementation Roadmap

> Phased implementation plan for expanding the MCP Bridge from 90 to 210+ tools based on the top 3000 most-used Revit APIs.

**Created:** 2026-01-08
**Status:** Ready for Execution
**Current Tools:** ~90
**Target Tools:** 210+ (Tier 1 + Tier 2)

---

## Executive Summary

### Current Situation
- ✅ **90 tools implemented** covering 80% of basic use cases
- ✅ **Universal Reflection Bridge** operational (100% API access)
- ⚠️ **Missing critical tools** for professional workflows
- ⚠️ **Limited advanced filtering** (most important API category)

### Target Outcome
- 🎯 **210 tools** covering 95% of professional workflows
- 🎯 **Natural language ready** for all major operations
- 🎯 **Best-in-class** Revit automation platform
- 🎯 **Production ready** for enterprise use

---

## Phase 1: CRITICAL FOUNDATIONS (Weeks 1-2)

**Goal:** Fill critical gaps that block 50% of professional workflows
**Effort:** 40 tools, ~80 hours
**Priority:** 🔴 MUST HAVE

### 1.1 Advanced Element Filtering (15 tools) - HIGHEST PRIORITY

**Why Critical:** FilteredElementCollector is #1 ranked API (Score: 294)

```csharp
// Tools to implement:
1.  revit_filter_elements_by_parameter        // Filter by param value/range
2.  revit_filter_elements_by_level            // Filter by level
3.  revit_filter_elements_by_workset          // Filter by workset
4.  revit_filter_elements_by_bounding_box     // Spatial containment
5.  revit_filter_elements_intersecting        // Find intersecting
6.  revit_filter_elements_by_view             // Visible in view
7.  revit_find_elements_at_point              // Pick at coordinate
8.  revit_filter_by_multiple_criteria         // AND/OR logic
9.  revit_get_all_elements_of_type            // By ElementType
10. revit_get_dependent_elements              // Dependencies
11. revit_get_hosted_elements                 // Hosted by element
12. revit_trace_element_relationships         // Full dependency tree
13. revit_find_similar_elements               // Find similar
14. revit_get_elements_by_unique_id           // By UniqueId
15. revit_get_linked_elements                 // From links
```

**Implementation Notes:**
- Base on `FilteredElementCollector` API
- Support parameter-based filtering (most requested)
- Enable spatial queries (bounding box, intersections)
- Use quick filters where possible for performance

**Sample Implementation (C#):**
```csharp
[CommandMethod("revit.filter_elements_by_parameter")]
public class FilterElementsByParameter : IBridgeCommand
{
    public object Execute(Document doc, Dictionary<string, object> args)
    {
        string paramName = args["parameter_name"];
        string operator = args["operator"]; // equals, greater, less, contains
        object value = args["value"];
        string category = args.Get("category", null);

        var collector = new FilteredElementCollector(doc);

        if (category != null)
            collector.OfCategory((BuiltInCategory)Enum.Parse(...));

        var paramFilter = CreateParameterFilter(paramName, operator, value);
        collector.WherePasses(paramFilter);

        return collector.Select(e => new {
            id = e.Id.IntegerValue,
            category = e.Category?.Name,
            name = e.Name
        }).ToList();
    }
}
```

---

### 1.2 Unit Conversion (5 tools) - CRITICAL

**Why Critical:** UnitUtils is #15 ranked (Score: 275) - essential for international work

```csharp
16. revit_convert_to_internal_units           // Convert to feet
17. revit_convert_from_internal_units         // Convert from feet
18. revit_get_project_units                   // Get doc units
19. revit_set_project_units                   // Set doc units
20. revit_format_value_with_units             // Display formatting
```

**Implementation Notes:**
- Use `UnitUtils.ConvertToInternalUnits()` / `ConvertFromInternalUnits()`
- Support all common unit types (length, area, volume, angle)
- Handle ForgeTypeId for Revit 2021+
- Provide unit presets (metric, imperial)

---

### 1.3 Schedule Management (10 tools) - CRITICAL

**Why Critical:** ViewSchedule is #146 ranked (Score: 198) - documentation essential

```csharp
21. revit_add_schedule_field                  // Add column
22. revit_remove_schedule_field               // Remove column
23. revit_set_schedule_filter                 // Apply filter
24. revit_set_schedule_sorting                // Set sort order
25. revit_set_schedule_grouping               // Group rows
26. revit_calculate_schedule_totals           // Calculate sums
27. revit_format_schedule_field               // Field formatting
28. revit_export_schedule_to_csv              // CSV export
29. revit_create_key_schedule                 // Key schedule
30. revit_create_material_takeoff             // Material schedule
```

**Implementation Notes:**
- Use `ScheduleDefinition` for configuration
- Support `ScheduleField` manipulation
- Enable `ScheduleFilter` and `ScheduleSortGroupField`
- Export using `ViewSchedule.Export()`

---

### 1.4 View Management Essentials (10 tools) - HIGH

**Why Critical:** View is #6 ranked (Score: 283) - visualization foundation

```csharp
31. revit_create_ceiling_plan_view            // Ceiling RCP
32. revit_create_elevation_view               // Elevation
33. revit_duplicate_view                      // Duplicate with options
34. revit_set_view_template                   // Apply template
35. revit_create_view_filter                  // Visibility filter
36. revit_set_view_visibility                 # Category visibility
37. revit_isolate_elements_in_view            // Isolate
38. revit_hide_elements_in_view               // Hide specific
39. revit_unhide_elements_in_view             // Unhide
40. revit_crop_view                           // Set crop region
```

**Implementation Notes:**
- Use `ViewPlan.Create()` for ceiling plans
- `ElevationMarker` for elevations
- `View.Duplicate()` with `ViewDuplicateOption`
- `ParameterFilterElement` for filters
- `View.IsolateCategoryTemporary()` / `HideElementTemporary()`

---

## Phase 2: HIGH VALUE ADDITIONS (Weeks 3-6)

**Goal:** Professional-grade workflows for all disciplines
**Effort:** 51 tools, ~100 hours
**Priority:** 🟡 SHOULD HAVE

### 2.1 Advanced Geometry Operations (20 tools)

```csharp
41. revit_get_element_geometry               // Extract geometry
42. revit_get_element_faces                  // Get faces
43. revit_get_element_edges                  // Get edges
44. revit_join_geometry                      // Join elements
45. revit_unjoin_geometry                    // Unjoin
46. revit_cut_geometry                       // Boolean subtract
47. revit_array_elements_linear              // Linear array
48. revit_array_elements_radial              // Radial array
49. revit_align_elements                     // Align multiple
50. revit_distribute_elements                // Distribute evenly
51. revit_offset_curves                      // Offset curves
52. revit_create_direct_shape               # Custom geometry
53. revit_create_solid_extrusion            // Extrude profile
54. revit_create_solid_revolution           // Revolve
55. revit_create_solid_sweep                // Sweep
56. revit_create_solid_blend                // Blend
57. revit_boolean_union                     // Unite solids
58. revit_boolean_intersect                 // Intersect
59. revit_boolean_subtract                  // Subtract
60. revit_create_curve_loop                 // Create boundary
```

**Key APIs:**
- `Element.get_Geometry()`
- `GeometryElement`, `Solid`, `Face`, `Edge`
- `JoinGeometryUtils`
- `SolidSolidCutUtils`
- `ElementTransformUtils.CopyElement()` with offset
- `DirectShape.CreateElement()`
- `BRepBuilder` for custom solids

---

### 2.2 Family & Type Management (12 tools)

```csharp
61. revit_load_family                        // Load RFA
62. revit_reload_family                      // Reload updated
63. revit_duplicate_family_type              // Create new type
64. revit_rename_family_type                 // Rename type
65. revit_set_family_type_parameter          // Modify type param
66. revit_get_nested_families                // Get nested
67. revit_replace_family                     // Swap family
68. revit_transfer_standards                 // Transfer settings
69. revit_purge_unused_families              // Cleanup
70. revit_get_family_category                // Get category
71. revit_list_family_instances              // Find instances
72. revit_swap_family_type                   // Change type
```

**Key APIs:**
- `Family.Load()`
- `FamilySymbol.Duplicate()`
- `Element.Name` setter
- `FamilyManager` for nested families
- `Document.LoadFamily()` with `IFamilyLoadOptions`

---

### 2.3 Worksharing Tools (10 tools)

```csharp
73. revit_create_workset                     // Create workset
74. revit_rename_workset                     // Rename
75. revit_set_element_workset                // Move to workset
76. revit_get_element_workset                // Get element's workset
77. revit_checkout_elements                  // Request ownership
78. revit_get_workset_owner                  // Get owner info
79. revit_enable_worksharing                 // Enable
80. revit_get_central_path                   // Central path
81. revit_set_workset_visibility             // Show/hide in view
82. revit_get_workset_visibility             // Get visibility
```

**Key APIs:**
- `Workset.Create()`
- `WorksetTable`
- `Parameter` with `ELEM_PARTITION_PARAM`
- `WorksharingUtils`
- `WorksetConfiguration`

---

### 2.4 Link Management (9 tools)

```csharp
83. revit_load_link                          // Load RVT link
84. revit_unload_link                        // Unload
85. revit_reload_link                        // Reload from file
86. revit_get_link_elements                  // Query linked
87. revit_get_link_transform                 // Placement
88. revit_set_link_visibility                // Show/hide
89. revit_import_cad                         // Import DWG/DXF
90. revit_manage_cad_import                  // Control layers
91. revit_bind_link                          // Convert to group
```

**Key APIs:**
- `RevitLinkType.Load()`
- `RevitLinkInstance`
- `RevitLinkType.LoadFrom()`
- `FilteredElementCollector` on link document
- `Transform` from `RevitLinkInstance`

---

## Phase 3: SPECIALIZED WORKFLOWS (Weeks 7-10)

**Goal:** Discipline-specific professional tools
**Effort:** 28 tools, ~60 hours
**Priority:** 🟠 NICE TO HAVE

### 3.1 MEP Advanced (10 tools)

```csharp
92.  revit_create_mep_system                 // Create system
93.  revit_add_to_system                     // Add element
94.  revit_connect_mep_elements              // Auto-connect
95.  revit_size_mep_element                  // Calculate size
96.  revit_route_mep                         // Auto-route
97.  revit_create_space                      // HVAC space
98.  revit_get_space_properties              // Space data
99.  revit_calculate_loads                   // Load calc
100. revit_balance_system                    // Flow balance
101. revit_analyze_flow                      // Flow analysis
```

---

### 3.2 Structural Advanced (8 tools)

```csharp
102. revit_create_structural_framing         // Framing
103. revit_create_truss                      // Truss
104. revit_place_rebar                       // Reinforcement
105. revit_create_rebar_set                  // Rebar set
106. revit_create_load_case                  // Load case
107. revit_apply_point_load                  // Point load
108. revit_get_analytical_model              // Analytical
109. revit_update_analytical_model           // Sync analytical
```

---

### 3.3 Stairs & Railings (4 tools)

```csharp
110. revit_create_stair_by_sketch            // Create stair
111. revit_create_railing                    // Railing
112. revit_set_stair_path                    // Define path
113. revit_modify_stair_run                  // Modify run
```

---

### 3.4 Phasing & Design Options (6 tools)

```csharp
114. revit_create_phase                      // Create phase
115. revit_set_element_phase                 // Set phase
116. revit_create_design_option_set          // Option set
117. revit_create_design_option              // Add option
118. revit_set_primary_option                // Set primary
119. revit_add_to_design_option              // Add elements
```

---

## Phase 4: OPTIMIZATION & ENHANCEMENT (Weeks 11-12)

**Goal:** Developer-level control and productivity features
**Effort:** 21 tools, ~40 hours
**Priority:** 🟢 ENHANCEMENT

### 4.1 Transaction Control (6 tools)

```csharp
120. revit_begin_transaction                 // Explicit control
121. revit_commit_transaction                // Commit
122. revit_rollback_transaction              // Rollback
123. revit_get_transaction_names             // History
124. revit_undo_last                         // Undo
125. revit_redo_last                         // Redo
```

---

### 4.2 Analysis & Validation (5 tools)

```csharp
126. revit_find_intersections                // All intersections
127. revit_get_clearance_distance            // Min distance
128. revit_validate_element_placement        // Validation
129. revit_resolve_warning                   // Auto-fix warning
130. revit_suppress_warning                  // Suppress type
```

---

### 4.3 Batch Operations (10 tools)

```csharp
131. revit_batch_create_elements             // Bulk create
132. revit_batch_modify_parameters           // Bulk modify
133. revit_batch_delete_elements             // Bulk delete
134. revit_batch_apply_material              // Bulk material
135. revit_batch_tag_elements                // Bulk tag
136. revit_batch_rename_views                // Bulk rename
137. revit_batch_set_workset                 // Bulk workset
138. revit_batch_hide_elements               // Bulk hide
139. revit_batch_export_views                // Bulk export
140. revit_process_csv_operations            // CSV-driven ops
```

---

## Implementation Guidelines

### Code Structure

```
packages/revit-bridge-addin/src/
  Commands/
    Core/                    # Phase 1 (existing + new)
      Filtering/
        FilterByParameter.cs
        FilterByLevel.cs
        FilterMultiCriteria.cs
        ...
      Units/
        ConvertToInternal.cs
        ConvertFromInternal.cs
        ...
      Schedules/
        AddScheduleField.cs
        SetScheduleFilter.cs
        ...
      Views/
        CreateCeilingPlan.cs
        SetViewVisibility.cs
        ...
    Advanced/                # Phase 2
      Geometry/
        GetElementGeometry.cs
        JoinGeometry.cs
        CreateDirectShape.cs
        ...
      Families/
        LoadFamily.cs
        DuplicateFamilyType.cs
        ...
      Worksharing/
        CreateWorkset.cs
        SetElementWorkset.cs
        ...
      Links/
        LoadLink.cs
        GetLinkElements.cs
        ...
    Specialized/             # Phase 3
      MEP/
        CreateMEPSystem.cs
        RouteMEP.cs
        ...
      Structural/
        PlaceRebar.cs
        CreateLoadCase.cs
        ...
      Stairs/
        CreateStair.cs
        ...
    Utilities/               # Phase 4
      Transactions/
        BeginTransaction.cs
        ...
      Analysis/
        FindIntersections.cs
        ...
      Batch/
        BatchOperations.cs
        ...
```

---

### Testing Strategy

#### Unit Tests
```csharp
[TestClass]
public class FilterByParameterTests
{
    [TestMethod]
    public void TestFilterWallsByHeight()
    {
        // Arrange
        var cmd = new FilterByParameter();
        var args = new Dictionary<string, object> {
            {"parameter_name", "Height"},
            {"operator", "greater"},
            {"value", 10.0},
            {"category", "Walls"}
        };

        // Act
        var result = cmd.Execute(doc, args);

        // Assert
        Assert.IsTrue(result.Count > 0);
        Assert.IsTrue(result.All(e => GetHeight(e.id) > 10.0));
    }
}
```

#### Integration Tests
- Test with real Revit project
- Verify transaction handling
- Check error recovery
- Validate output schemas

#### Performance Tests
- Benchmark large collections
- Test with 100k+ elements
- Measure memory usage
- Optimize bottlenecks

---

### Documentation Requirements

Each tool needs:

1. **API Documentation**
```python
"""
Filter elements by parameter value.

Args:
    parameter_name (str): Name of parameter to filter by
    operator (str): Comparison operator (equals, greater, less, contains)
    value (any): Value to compare against
    category (str, optional): Limit to category

Returns:
    list[dict]: Filtered elements with id, category, name

Example:
    # Find all walls taller than 10 feet
    walls = revit_filter_elements_by_parameter(
        parameter_name="Height",
        operator="greater",
        value=10.0,
        category="Walls"
    )
"""
```

2. **Natural Language Examples**
```
User: "Show me all walls taller than 10 feet"
→ revit_filter_elements_by_parameter(parameter_name="Height", operator="greater", value=10.0, category="Walls")

User: "Find rooms larger than 200 square feet"
→ revit_filter_elements_by_parameter(parameter_name="Area", operator="greater", value=200.0, category="Rooms")
```

3. **Error Handling Guide**
- Common errors and solutions
- Parameter name mismatches
- Type conversion issues
- Transaction failures

---

## Resource Planning

### Development Team
- **Phase 1:** 2 developers x 2 weeks = 160 hours
- **Phase 2:** 2 developers x 4 weeks = 320 hours
- **Phase 3:** 1 developer x 4 weeks = 160 hours
- **Phase 4:** 1 developer x 2 weeks = 80 hours
- **Total:** 720 development hours (~4.5 months)

### Testing Team
- Unit testing: 100 hours
- Integration testing: 80 hours
- User acceptance: 40 hours
- Total: 220 hours

### Documentation
- API docs: 60 hours
- User guides: 40 hours
- Video tutorials: 20 hours
- Total: 120 hours

**Grand Total:** ~1,060 hours (~6 months with 2 developers)

---

## Success Metrics

### Coverage Metrics
- [ ] 210+ tools implemented
- [ ] 95% workflow coverage
- [ ] 100% of top 100 APIs accessible
- [ ] All 27 functional categories covered

### Quality Metrics
- [ ] >95% tool execution success rate
- [ ] <5% error rate in production
- [ ] >90% natural language accuracy
- [ ] <500ms average tool execution time

### Adoption Metrics
- [ ] 100+ active users
- [ ] 1000+ tool invocations/day
- [ ] >4.5/5 user satisfaction
- [ ] <2 support tickets/week

---

## Risk Mitigation

### Technical Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API breaking changes | Medium | High | Version compatibility layer |
| Performance issues | Low | Medium | Caching + optimization |
| Transaction failures | Medium | High | Robust error handling |
| Memory leaks | Low | High | Proper disposal patterns |

### Schedule Risks
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Resource unavailability | Low | High | Cross-training team |
| Scope creep | High | Medium | Strict prioritization |
| Testing delays | Medium | Medium | Automated testing |
| Integration issues | Low | Medium | Continuous integration |

---

## Next Steps

### Week 1 Actions
1. ✅ Review and approve this roadmap
2. ⬜ Set up development environment for Phase 1
3. ⬜ Create feature branches for filtering tools
4. ⬜ Begin implementation of top 5 filtering tools
5. ⬜ Set up automated testing framework

### Month 1 Milestones
- [ ] Phase 1 complete (40 tools)
- [ ] Integration tests passing
- [ ] Documentation published
- [ ] Beta release to select users

### Quarter 1 Goals
- [ ] Phase 2 complete (91 tools total)
- [ ] Production deployment
- [ ] 50+ active users
- [ ] Case studies published

---

## Conclusion

This roadmap provides a clear path from the current 90 tools to a comprehensive 210+ tool platform that covers 95% of professional Revit workflows. The phased approach ensures:

1. **Quick Wins:** Phase 1 delivers critical missing functionality in 2 weeks
2. **Professional Grade:** Phase 2 adds advanced features needed by power users
3. **Specialized Support:** Phase 3 covers discipline-specific needs
4. **Enterprise Ready:** Phase 4 adds polish and optimization

With the Universal Reflection Bridge already in place, users have access to 100% of the Revit API while we systematically add high-level tools for common workflows. This hybrid approach provides both power and usability.

**Recommendation:** Begin Phase 1 implementation immediately to capitalize on market opportunity and user demand.

---

**Document Version:** 1.0
**Status:** Ready for Approval
**Owner:** Development Team
**Review Date:** 2026-01-15
