# Villa refinement and bridge evaluation

Use a real villa as a regression case for the assistant and bridge. Deliver two separate results: a verified model improvement and an evidence-backed tool/workflow improvement. An attractive image, successful tool invocation, or correct level name alone does not satisfy either result.

## 1. Establish scope and baseline

Read `revit_health`, document info, current selection and levels. Record the document title, selected IDs, date, intended architectural style and required deliverable. Expand groups through dedicated member reads when present. A selection is an explicit starting scope: rooms, hosted dependents, equipment, systems and views may be omitted. Do not silently modify all similarly named types or other buildings.

Use `revit_inspect_elements` in small batches with `expected_document_title`. Maximums: 50 unique positive IDs, 20 exact parameter names and 200 total geometry/parameter sections per request. Start with geometry only; request role-specific parameters for candidates. Preserve failures and missing fields. Endpoint document checks are not an atomic snapshot and cannot detect a switch away and back or changes during the reads. The tool reduces assistant tool round trips; it still executes the existing Revit reads sequentially.

Keep captures in the configured bridge workspace. The coding repository and bridge workspace can differ. Do not change workspace permissions to force an export through. Check the returned artifact and open it before using it as visual evidence.

## 2. Check spatial behavior, not just insertion points

Compare level-relative geometric extents with the semantic role. A basin may have its insertion origin at floor level while its geometry lies below it. Recessed lights, foundations, window frames and downward-extending façade fins have different valid relationships to their datums.

For a suspected defect, gather the family/type, raw and formatted offsets, host, orientation and transform, nearby construction and actual solids/meshes. AABB intersections are candidates, not confirmed clashes. Include mesh geometry or explicitly report that it is unavailable. Obtain plan and section views at a readable pixel size. Distinguish a family-origin error, wrong offset, wrong orientation, wrong host and a legitimate recess before choosing a correction.

In the October 2026 villa case, basin IDs 23841919, 23841920, 23841924 and 23841925 had insertion points at 3.200 m while most of their bounding-box height lay below that level. The observed zero offsets do not define the correct mounting height. Establish the intended rim height from the design/family specification; do not blindly lift every plumbing fixture by one constant.

## 3. Make architectural refinement reviewable

Assess circulation, usable room dimensions, doors and swings, stairs and headroom, furniture access, structure/envelope intersections and levels. Then define a coherent façade composition: opening alignment and proportions, material transitions, depth/reveals, sill and coping details, shading, balconies/railings and roof drainage. Use native elements and editable types where suitable, scoped to the villa. Detail improvements need plan/section checks as well as exterior views.

Separate measured defects from design preferences. Record proposed before/after dimensions and affected IDs. For each change, define an acceptance check and the required view. Do not promise structural, accessibility, fire or code compliance from bounding boxes or uncalculated design assumptions.

## 4. Treat MEP as connected systems

Inventory system types, equipment, terminals, connectors, wet rooms, plant space, service entry points, distribution zones and loads. Read-only category counts establish presence/absence, not system connectivity or adequacy. Architectural plumbing families may lack usable MEP connectors.

Before creating networks, establish the heating/ventilation concept, drainage and water supply routes, electrical circuits and plant assumptions. Equipment needs suitable families, connectors, host/orientation and maintenance access. Routes need space, fittings, slopes where relevant and penetrations. Creating pipes, ducts or conduits alone does not establish a connected or sized system.

Acceptance evidence includes connector/system membership, fitting continuity, equipment association, circuit/panel assignment where applicable, disconnected-end reporting and geometry coordination. Engineering sizing and regulatory verification require their own documented calculations and criteria. Label a concept model as a concept until those checks are performed.

## 5. Execute and verify through the approval gate

Prepare concrete, bounded changes and validation scripts before requesting approval. `plan_actions` records proposed writes; the person approves through the panel or approval CLI. The assistant must not approve its own plan or call the add-in endpoint to bypass this gate. Arbitrary Python/reflection stays gated even when a submitted script appears read-only. Prefer dedicated readers and never implement a `read_only=true` escape hatch based on trust or keyword scanning.

Assert document identity and the baseline for the affected elements. Keep Revit UI-thread scripts short, transactional and resumable; verify actual commit status. Read the result and post-change geometry, check dependents and new warnings, and inspect the expected views. Preserve before/after evidence. Do not infer a finished model from a successful API call.

## 6. Turn failures into regression cases

For each issue, record the exact tool/arguments, expected/observed behavior, evidence level, code location, impact, proposed fix, regression test and live verification status. Distinguish:

- **MEASURED:** observed in the running Revit session.
- **OFFLINE:** proved by tests/builds, not revalidated in the running add-in.
- **INFERRED:** plausible explanation requiring further evidence.
- **UNTESTED:** proposed behavior or unavailable checks.

Use narrow independent agents for code fixes, spatial screening and research when useful. Give them separate file ownership and concise evidence requirements. Keep the configured capable model unless a task-specific reason supports changing it. Load only relevant skills. The lead agent integrates findings and verifies the complete result.

An upgrade is ready for live acceptance only after tests/builds pass and the intended server/add-in version is loaded. Reconnecting the MCP server refreshes its tool definitions; replacing a DLL on disk does not replace an already loaded Revit assembly. Do not close a modified Revit document without the user's handling of unsaved work.
