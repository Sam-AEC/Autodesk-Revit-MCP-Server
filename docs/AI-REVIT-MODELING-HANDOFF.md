# Handoff: reliable AI modeling in Revit, tested on the villa

## Objective and completion contract

Take over the existing villa, correct its geometry and spatial placement, refine its architectural detailing and facade, create coordinated native MEP systems, and provide a permanent MEP-only 3D review view. Use the villa to discover and fix bridge and assistant limitations. The deliverable is both a better verified model and reusable modeling tools/workflows, not a collection of successful API calls or attractive screenshots.

The user reports that elements still overlap and the architecture remains visually unfinished. Treat that as an unresolved requirement. Do not declare completion from the narrow placement checks below.

**First read:** [machine-readable live state](villa-coding-agent-state-2026-10-13.json), [session findings](villa-bridge-limitations-2026-10-13.md), [review workflow](workflows/villa-refinement-review.md), and the earlier [builder/reviewer findings](bim-agent-findings.md). Historical “done” labels in earlier notes are not proof that the current model passes.

## Authoritative takeover state

Last live checks: **2026-10-13 13:08 Amsterdam / 11:08 UTC**. Revit 2024.3, document `R24_2026_HWC_B01_HEIJ_BWK_GEV-IND_TAS - Copy`. The document is modified; this agent did not save it. The bridge was healthy at `:50901`; the port is ephemeral. Resolve the current connection through supported bridge discovery, not a hard-coded URL.

The original selection had 194 elements. Ownership comments generally begin `AMB_VILLA:`. The selection is incomplete: overlapping floor pieces 23841023 and 23841030 were outside it. The machine-readable state preserves the selected IDs/UniqueIds, extra known elements, rooms, changed elements and review view IDs. Revalidate all IDs, ownership, document identity and current geometry before making changes.

**Already changed live:**

- Basins **23841919, 23841920, 23841924 and 23841925**: mounting origins now 850 mm above the first-floor datum, a stated schematic design assumption. Two basins were rotated 180 degrees; backs were aligned to the relevant room wall with 10 mm allowance. A final solid-intersection rerun reports zero volume against slab 23843041 for all four. This does not establish the entire plumbing installation or clearances.
- Kitchen cabinets **23841900–23841903**: rotated 180 degrees and aligned to a common back line 20 mm clear of the exterior wall face. Solid checks against walls 23839613 and 23839618 passed. The placement script records before/after geometry and marks instances `AMB_REFINED:placement_v1`; do not rotate these again blindly.
- Furniture sets **23842041–43, 23842047–49, 23842050–52, 23842053–55**: moved into their intended room envelopes. All envelope corners were checked with `Room.IsPointInRoom`, using a 75 mm rectangular boundary allowance. The first set moved about 2.293 m; the other sets about 268 mm. The beds contain meshes: exact mesh collision and usable access remain unverified.
- Added **23843617 `AMB_QA Architecture Front`** and **23843628 `AMB_QA Architecture Rear`**. These isolate the villa spatially and hide vegetation/boundary obstructions in these review views. Crops were fitted in view coordinates; the original contextual views remain.
- Created and loaded **`AMB_Refined_DetailBlock`**, family 23843815, symbol 23844633. Its instance parameters are `AMB_Width`, `AMB_Depth`, `AMB_Height` and `AMB_Material`. The native extrusion/reference-plane family passed a width/depth/height flex test. **No detail instances have been placed.** The family is available as an editable primitive for sills, reveals, coping and similar details; an assembly needs more than a box.

**Not done:** general facade/material refinement, detailed junctions and roof drainage, complete collision/clearance review, MEP equipment/networks/circuits, and the requested MEP-only view. No add-in deployment or Revit restart was performed.

## Immediate remaining defects: start here

| Priority | Current evidence | Required investigation and acceptance |
|---|---|---|
| P0 | Revit warnings: **23841023 / 23843041** and **23841030 / 23843041** overlap. The small pieces and main slab have `AMB_VILLA` comments. | Inspect profiles, holes, stair/landing intent, joins and dependents. Resolve redundant overlap or trim intended pieces while preserving stair opening and support. Do not delete solely because a warning exists. Verify solids and warning removal after commit. |
| P0 | Ground floor **23839624**, upper floor **23843041**, and the two small pieces have `FloorType.IsFoundationSlab=true`; category is **Structural Foundations**, despite their `AMB_Floor` names. Types are 23833326/23833332. | Investigate how the wrong native type lineage was selected. Rebuild/change to a genuine floor type through a dependency-aware plan, preserving levels, layers, shape and openings. Assert native class, category and `IsFoundationSlab` in the create/fix tools. |
| P0 | Warning: window **23840036** conflicts with joined internal wall **23839620**. Its host is exterior wall **23839609**. | Inspect opening extent, jamb, partition intersection and door/window function. Correct host/join/location/detail as appropriate. Require a clean solid/section check and no insert-conflict warning. |
| P0 | User still sees other overlaps; only a small list of pairs has been checked. | Expand scope by ownership, hosts/dependents, spatial adjacency and rooms. Run a scoped collision audit including solids **and meshes**. Produce candidates with exact evidence, exception rules and unresolved counts; inspect each remaining reported defect. |
| P1 | Large plain facade planes, exposed grey bands, competing trim/material colours; original views are heavily obscured by trees/boundary walls. | Review unobstructed elevations and details. Produce a coherent finish and junction system, not per-face recolouring alone. |
| P1 | No villa MEP networks/equipment/circuits created by this agent. | Establish schematic assumptions, create native connector-bearing elements and networks, verify connectivity/clearance, and provide `AMB_MEP_Only_3D`. Do not represent arbitrary disconnected curves as a system. |

## Build the deterministic modeling layer first

The bridge can reach Revit's API. The largest weakness is that agents must repeatedly invent geometry interpretation and verification in arbitrary Python. A stronger language model helps design judgment; deterministic spatial tools should do coordinate arithmetic, host selection, collision checks and acceptance.

Implement the following tools as a thin typed layer over a shared native inspection/geometry service. Names below are proposed contracts, not tools already available.

| Priority | Proposed tool/capability | Minimum useful contract | Regression proving its value |
|---|---|---|---|
| P0 | `revit_get_context` | Host/session identity, document identity, effective approval mode and expiry, configured workspace identity, runtime/version capabilities, active view and selection, model change token. No credentials. Explicit mismatch/reconnect diagnostics. | Panel Auto in one workspace and client in another yields an actionable mismatch, never silent permission relaxation. Stale endpoint yields a reconnect-required result; no model write is automatically replayed against another document. |
| P0 | `revit_inspect_scene` | Explicit selection/ownership/spatial scope; local coordinate frame; rooms and boundary loops; native type/category semantics; levels; hosts/dependents; family transforms; parameter IDs with raw values, units and formatted values; solids/meshes and visibility; connectors and systems. Stable element IDs/UniqueIds; section completeness and time/element budgets. | Include the two floor pieces outside the initial selection. Detect foundation-slab types, phase-indexed room membership, rotated/mirrored family geometry, missing geometry and truncated capture correctly. |
| P0 | `revit_check_intersections` | Broad-phase spatial index followed by solid/solid and mesh/solid/mesh narrow-phase checks. Pair IDs, tolerance, contact versus penetration, intersection depth/volume where available, witness geometry and status `verified`, `candidate`, `unavailable` or `failed`. | Reproduce the original basin/slab and cabinet/wall collisions; distinguish valid host-opening/recess contacts. The mesh beds cannot be reported “no clash” merely because no solids exist. |
| P0 | Verified create/move/change tools | Explicit native type/host/level/local placement intent, preconditions, transaction/failure handling, measured before/after geometry, dependent impact, warning delta and caller-defined acceptance. Roll back failed placement rather than returning a malformed element as success. | Reject a foundation slab for an ordinary-floor intent; detect wrong level-relative offsets, reversed basin orientation and an insert hosted in the wrong vertical wall. A commit-time error rolls back the atomic action. |
| P0 | Reliable review export | Actual file paths and dimensions/format, changed-artifact detection, fit to explicit scoped/view-coordinate crop, clean selection state, annotated plan/section/3D images with IDs. Match cameras across before/after. | Original 1800-pixel PNG request must not return a 150-pixel JPEG, absent path or blank model-at-project-origin view. Stale/empty artifacts fail. |
| P1 | `revit_probe_family` | Cache real geometry extents, insertion origin, geometry-derived front/back/head directions, mirroring behavior, placement/host mode, parameters, connector types and intended clearance zones. Record uncertainty and family version. | `FacingOrientation` is not treated as a universal front direction; probe the bed mesh and basin back geometry. Detect unresizable mesh families and connectorless architectural fixture families. |
| P1 | Semantic placement | `place_back_to_wall`, `place_in_room`, `align_openings`, `flank`, `route_in_service_zone`; use real finish faces, room polygons, geometry and declared clearance/installation constraints. Return a proposal/diff and acceptance evidence. | Reposition furniture without crossing partitions or stacking tables, account for family-origin offsets, and preserve already corrected instances on repeat runs. |
| P1 | `revit_inspect_mep` / verified connection tools | Connectors with domain/classification/shape/size/flow and references; native system graph, equipment association, fittings, circuit/panel membership, disconnected ends and declared external connections. | Existing basin has only one piping connector; do not attach hot/cold supply to it without classification verification. Reject “connected system” when curves merely share coordinates. |
| P1 | Clearance/circulation checks | Separate physical clash and functional clearance volumes: door swing, furniture access, stairs/headroom, plant maintenance, route envelopes including insulation. Use project-design criteria with provenance. | A model can have zero solid intersections while door swings or maintenance zones still fail. Do not invent regulatory compliance from default dimensions. |
| P1 | Material/detail assembly tools | Inspect real layer stacks/side orientation; duplicate types only for scoped instances; place editable, semantically named details with physical junctions and measured extents. | Detect material on the wrong wall side; avoid changing unrelated Heijmans type instances; prove sills/coping/plinth are modeled and attached consistently in sections. |
| P2 | Layout/service solver | Offline constraint solver using the scene packet; propose alternatives with violation scores, never commit directly. Separate assistant design selection from deterministic feasibility. | Compare viable options against room polygons, clearance, hosts and service zones, then reverify the accepted option live. |

A mesh/glTF scene preview plus an element-linked inspector would help both the agent and person understand shape and placement. It must complement the semantic scene packet and readable sections; a screenshot or opaque mesh alone loses hosts, units, levels and systems. Keep heavy meshing/optimization outside Revit's UI thread where possible, with bounded native extraction and revision-aware caches.

## Required closed verification cycle

1. **Read:** confirm live document/session, change token and approved/Auto state; gather a complete scoped scene packet and warning baseline.
2. **Propose:** resolve explicit design constraints and type semantics; generate a concrete diff. Separate observed defects, design choices and unverified engineering assumptions.
3. **Check offline:** validate coordinates, units, scope, ownership, constraints, route graph and idempotency. Use strict schemas and property-based geometry cases where useful.
4. **Apply:** one writer to the live model; small atomic, guarded transactions. Respect human-managed approval/Auto. Never approve the agent's own plans, forge Auto state, invoke the add-in endpoint to bypass the gate or retry an uncertain mutation blindly.
5. **Measure after commit:** reread geometry/topology and dependencies; collision/clearance checks, category/type assertions and warning delta. Handle commit errors and partial results explicitly.
6. **Look:** export matched plan/section/3D views; inspect images for architectural finish and functional errors that numerical checks do not cover.
7. **Repair or accept:** independent reviewer compares against the same criteria. Continue until all scoped defects and acceptance requirements are resolved or explicitly remain unverified. Save a machine-readable proof bundle and concise human report.

Use a builder and an independent reviewer with narrow tasks, shared evidence and separate file ownership. **Only one agent writes the live Revit document at a time.** Agents doing code/research can work independently. Do not repeatedly pass the whole model into prompts; use bounded retrieval and store large geometry/evidence artifacts outside chat.

## Architectural continuation

Read `artifacts/villa-bridge-audit/architectural-refinement-proposal.md`. The proposed schematic language preserves massing/openings: warm taupe mineral/masonry ground floor, muted vertical timber upper volume, darker timber fins and charcoal frames/coping. Check material assignments; shaded pixels do not identify real material/type properties.

After resolving the geometry/type issues, model a coherent package: window/jamb/head reveals and sills, coping with corner returns and drip/overhang, base plinth relative to adjacent grade, intentional slab-edge treatment, entry canopy/soffit/light and approach, and roof drainage/overflow paths. Give each detail a function and a section. Do not hide a poor joint behind a material colour. Keep schematic assumptions documented and distinguish fabrication/waterproofing design still requiring specialist input.

The detail family is editable and reusable, but no details have been placed. Its geometry starts at its local lower corner; verify the transform before rotating/placing it. Attach/check details using measured host faces rather than manually guessed global coordinates. Do not infer universal family “front” from orientation properties.

## MEP continuation and required review view

Read `artifacts/villa-bridge-audit/mep-types.json`, `mep-layout-proposal.md` and `route-recipe.json`. The route recipe is a **schematic proposal requiring live clearance/connector verification**, not an executable or sized design. Plant/shaft anchors were checked against room polygons offline; actual slabs, roof, ceilings, doors and maintenance zones must be checked live.

- Four basins have one unconnected piping connector each; its system classification still needs inspection. Their connector origins have moved with the placement correction: reread them. Shower/WC families lack captured usable connectors. The kitchen sink is furniture, not a native connected plumbing terminal.
- Loaded pipe type 3099279 is PVC-U drainage. Create/select appropriate pressure-water and hydronic types rather than using it for all systems. Electrical fixture `Meterkast` is not evidence of a circuitable distribution panel.
- Supply/extract mechanical system types, sanitary/vent, domestic hot/cold and hydronic supply/return system types exist. Required suitable HRV, heat-pump, cylinder, manifold, terminals, panel and devices largely need vetted families or generated **native connector-bearing** families.
- Coordinate ducts/pipe/service runs, shafts and penetrations before routing. Native fittings, connector references, system membership, declared source/outlet endpoints, slopes and circuit/panel assignment must be verified. Perform engineering sizing separately; do not fabricate capacity claims.
- Create a permanent **`AMB_MEP_Only_3D`** view after systems exist. Show only villa MEP equipment, terminals, plumbing, ducts/pipes, fittings/accessories, electrical devices/conduit and relevant circuits/routes; hide architecture/site/furniture and unrelated project systems. Use a fitted villa/service section box, readable category/system colours and Fine detail. An empty MEP view is not completion. Also provide an architectural coordination view to verify hidden clashes.

The user explicitly wants to review this MEP-only view in Revit. Preserve that requirement through the implementation and final report.

## Source improvements already prepared: integrate, test, then deploy

All changes are **uncommitted**. Inspect the current diff before changing or committing anything.

- `BridgeCommandFactory.cs`: non-shared `Parameter.GUID` guard; image export filename prefix/pixel size/all-view format/actual changed-artifact reporting; Python engine initialization/runtime metadata.
- `PythonEngineFactory.cs` + `RevitBridge.csproj`: bundle matching official IronPython stdlib, preload matching adjacent `IronPython.Modules.dll`, prioritize bundled `Lib`, verify `json`/`time`. The loaded Revit 2024 runtime lacked `json` and `time`; CLR `JavaScriptSerializer`/`Stopwatch` worked for this audit. The fixed bundle needs live acceptance after installation. IronPython 2.7 for Revit 2024 and 3.4 for modern targets are separate from the MCP server's CPython.
- `mcp_server.py`: structured MCP errors, explicit provider-failure handling and failed-plan outcomes, including queued failures. Successful result text remains compatible. Confirm deployed clients actually receive the intended `isError` behavior rather than assuming source tests prove loaded-runtime behavior.
- `providers/revit.py`, `providers/element_inspection.py`: `revit_inspect_elements` composes dedicated reads sequentially, with strict schema/runtime limits, endpoint document checks and per-section completeness. **This is not a native atomic snapshot or fewer internal Revit calls.** It is available in the reconnected MCP tool inventory.
- Persisted tests: `scripts/test-addin-behavior.ps1`, `scripts/test-ironpython-runtime.ps1` and MCP unit/stdio tests. Stdlib licenses/notices are included.

Recorded checks: Revit 2024/2026 builds passed with zero errors and existing warnings; 133 approval/state/stdio tests passed; an 87-test integrated inspection/error/metadata/stdio run passed before the final queued-failure case; the final error-result file passed 15 tests. Real IronPython runtime tests for both target bundles passed imports/functions, working-directory shadowing and missing/mismatched dependency cases. These are offline evidence, not proof of deployment or model completion.

Useful commands from the repository root:

```powershell
git status --short
git diff --check
./scripts/test-addin-behavior.ps1
./scripts/test-ironpython-runtime.ps1
.\.venv\Scripts\python.exe -m pytest packages/mcp-server-revit/tests/test_element_inspection.py packages/mcp-server-revit/tests/test_mcp_error_results.py packages/mcp-server-revit/tests/test_mcp_stdio_smoke.py -q
```

The pre-existing dirty files `scripts/revit/bim_review/bim-review.ps1`, `review_checks.py` and `new_checks.txt` belong to the user's ongoing work. Read and integrate deliberately; do not overwrite/reset them. Never add co-author trailers or generated/tool-credit lines to commits or PRs.

## Connection/workspace lessons

The panel's Auto window was valid in `C:/Users/samo3/Documents/AEC Model Bridge`, while the old client gate used `C:/Users/samo3/Documents`. The client also cached an obsolete Revit endpoint. Aligning workspace settings and restarting VS Code restored the supported tool path. The user has authorized Auto mode; do not repeatedly ask for per-action permission while that supported mode is active. Recheck expiry and current mode instead of assuming it lasts forever.

Codex config now uses the panel workspace first and retains Documents as an additional allowed directory. A backup is `C:/Users/samo3/.codex/config.toml.villa-workspace-20261013T104106Z.bak`. No approval record/token was copied, edited or forged. New diagnostics should expose the mismatch; do not silently borrow permission from a different workspace.

## Evidence locations and first milestone

Large captures/scripts live in ignored local `artifacts/villa-bridge-audit/`; they are present on this machine but are not shipped by a repository checkout. Files include `baseline.json`, `handoff-final-diagnostics.json`, `placement-result.json`, `handoff-warning-elements.json`, the proposals and route recipe. Exported PNGs and `AMB_Refined_DetailBlock.rfa` are under `C:/Users/samo3/Documents/AEC Model Bridge/villa-review/`. The tracked state JSON preserves critical IDs/results if local artifacts are unavailable.

**First milestone:** produce a complete villa issue inventory with witness geometry/images, including the two unselected overlapping floor pieces and wrong native floor categories. Implement the minimum reliable native inspection/collision/verified-placement tools needed to resolve those cases. Fix and independently recheck those defects live, then continue architecture and MEP. This is a starting milestone, not a substitute for completing the villa.

Final completion requires: correct geometry and functional placement; coherent physically modeled facade/details visible in clean review views; verified native MEP topology and declared engineering limits; the nonempty MEP-only 3D view; and tested, documented reusable tools/workflows with live proof for the installed version.
