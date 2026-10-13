# How Revit behaves through the AEC Model Bridge, and how to improve it

Written 2026-10-13 after building a second villa (from a DWG) and a first MEP layer through the bridge, in a live Revit 2024.3 session
(1.7 GB project, ~2,080 existing warnings). Everything below was **measured in that session**; where something is inferred it says so.
The detailed per-issue catalogue is `docs/bim-agent-findings.md` (sections A-F). This file explains the *behaviour model* and ranks the
improvements. Working recipes are in `docs/recipes/villa2/` and `docs/recipes/toolkit/`.

## 1. The shape of the stack, as it actually behaves

```
agent (Claude Code)  --MCP stdio-->  revit_mcp_server (Python, approval gate)  --HTTP-->  add-in (C#, Revit UI thread)  -->  Revit API
                                                                                                          \-> IronPython 2.7 engine for revit_execute_python
```

| Fact | Evidence | Consequence |
|---|---|---|
| Every Revit call runs on the single UI thread, one at a time. Calls queue. | Two scripts sent back to back executed strictly in order; a long script blocked every later call, including `revit_health`. | Only one writer. Use `revit_health` as an "is Revit idle?" probe: it returns only when the queue is empty. |
| The HTTP request gives up after **30 s**, but Revit keeps executing the script. The result is lost. | `Request ... timed out after 30000ms` while the model changed anyway (52 openings were placed after the timeout). | Never trust a timeout as failure. Split work (one family / one chunk per call), then verify state with a read-only audit. Needs an async job API (see section 4). |
| `revit_execute_python` is IronPython **2.7**, new scope per call, predefined `doc`, `uidoc`; no `__revit__`; no `json`/`time` module in the deployed build. | `name '__revit__' is not defined`; objects (Transactions) do not survive between calls. | Build scripts from a prelude + data literal. Return text through `__output__`. Keep state in the model (tags, marks), not in Python. |
| Python is gated (approval / Auto mode) and tool errors come back as text with `isError`. | Auto mode valid for 8 h; `success:false` payloads for exceptions. | Dev mode must exist for production use of the Python tool (user request). Keep the gate for the default. |
| The loaded add-in is an **older build** than the repository source. | `revit_export_image` still returns `file_exists:false` and a wrong name although the source is fixed. | Deploy and verify; tests against source prove nothing about the loaded process. |

## 2. Revit-side behaviour that cost time (with the rule that fixes each)

### Geometry and joins
- **`Wall.Flip()` after creation breaks corner joins** (11 of 27 ends unjoined). Revit puts the exterior face on the *left* of the drawing direction. Rule: reverse the curve before creating the wall. Verify with `LocationCurve.get_ElementsAtJoin`.
- **Walls running through slab edges clash** (34 wall/floor overlaps, 4.5 m3). Rule: walls stop at the slab underside, slabs run to the outer wall faces; check with solid intersection (`toolkit/intersections.py`), not with bounding boxes.
- A 45-degree wall that is 0.2 degrees off raises "slightly off axis". Rule: build diagonals from exact dx = dy.
- Snapping wall ends to the nearest wall can collapse a short nib to zero length ("curve length too small"). Rule: guard the minimum length.
- A door or window wider than its wall piece makes Revit roll the *whole* transaction back (host wall in the failing set). Rule: check fit (centre +- half width inside the wall) before placing.
- **Several windows placed in one big transaction were left uncut in six walls** (ray test), while the identical window placed in its own transaction cut the wall. Rule: one transaction per opening. Cause not identified; the measurement is reliable.

### Floors, levels, views
- A floor type duplicated from the project's first `FloorType` was a **foundation slab**, so all floors were Structural Foundations. Rule: assert `IsFoundationSlab == False` when creating floors.
- Levels created through the API have **no plan view**; `NewFootPrintRoof` then fails with "Value cannot be null". Rule: create the plan view first.
- **Setting `VIEW_NAME` on the primary plan view of a level renames the level.** Rule: never rename a level's own view.
- An isometric 3D view that was never opened exports **blank** (model at the project origin; the villa is 3.9 km from it). Rule: crop the view to the projected section box before `ExportImage`. `Realistic` ignores material colours; use `ShadingWithEdges`.
- `revit_export_image` (loaded build): requested PNG at 1800 px returns success, `file_exists:false`, the real file is `<stem> - <ViewType> - <view>.png`. Rule: export with `ImageExportOptions` in Python and list the folder.

### Roofs and stairs
- `NewFootPrintRoof` has an `out` parameter: from IronPython it fails; from the add-in it fails when no roof type is passed. `revit_raw_command revit.create_roof` **works with `roof_type`**; the MCP tool `revit_create_roof` has no such argument. Slopes are then set from Python with `FootPrintRoof.GetProfiles()`, `set_DefinesSlope`, `set_SlopeAngle`. The roof's thickness extends **above** the level plane: apply a negative offset to put the top on the level.
- Stairs by component: the second run needs `TopElevation` raised first, then `BaseElevation` onto the landing. `ActualTreadDepth` and `DesiredRisersNumber` must be set on the stair before creating runs. A stair that starts on an upper level behaved differently from the ground stair and needed `ExtensionBelowRiserBase = 0` (still being resolved at the time of writing).

### Families
- **A generic family used as a base can carry hidden content.** The project's "Pole" contains a nested "wallbox" (an EV charger). Every family generated from it inherited a car charger. Rule: delete nested `FamilyInstance`s, and verify with a content probe of the generated family.
- Setting the type parameters `Width`/`Height` of a generated door/window family **from the project rescales its geometry** (a 4.1 m window became 7.3 m). Rule: set them inside the family before drawing, never from the project.
- Window geometry must start at the family's **Sill reference plane** or the instance sits 0.9 m too low (instance origin = sill - default sill).
- **Non-rectangular openings do not cut the host** when made as a family `Opening` or as a void form inside a door/window family (measured with rays; rectangular M_Fixed cuts). A void-family instance with `InstanceVoidCutUtils.AddInstanceVoidCut` is the documented alternative; the manual Cut Geometry attempt in the UI also did not work. Arches therefore stay rectangular for now.
- `ConnectorElement.Radius` is read-only: the size is set through `CONNECTOR_DIAMETER`/`CONNECTOR_RADIUS` parameters. The family category *can* be changed (`OwnerFamily.FamilyCategory`) from Generic Model to Mechanical/Electrical/Air Terminals, and connectors can be created on the faces of small "port cubes" to place any number of connectors anywhere.
- Family names are case-insensitive: loading `X_Horseshoe` over `X_horseshoe` replaces it; `SaveAs` needs `OverwriteExistingFile = True`.
- `EditFamily` documents must be closed in `finally`; an uncommitted transaction in a temporary document blocks `Close` until the reference is dropped and `GC.Collect()` runs (that rolls it back).

### Reading a DWG without a converter
`app.NewProjectDocument` + `Document.Import(dwg, DWGImportOptions, draftingView)` in the **temporary** document, read the `ImportInstance` geometry into a text file, close the temporary document. Nothing touches the project. A flattened DWG has one layer, so walls are recovered by pairing parallel lines at the wall thickness. The DWG units were not stated: scale was recovered from known sizes (a door leaf, wall thickness) and confirmed against the elevations.

## 3. Method that worked (and should be the product's default flow)

1. **Digitise before modelling**: render zoomed windows of the DWG with a coordinate grid, read coordinates, overlay the extracted walls/doors/windows on the drawing and compare *visually* before touching Revit.
2. **Data-driven phases**: each phase is a template + a JSON data file; re-runnable because everything is tagged (`Comments = AMB_V2:<phase>`, `Mark = id`) and purged by tag.
3. **Measure every phase**: wall ends joined, wall volume removed per opening, floor category, stair risers, roof tops, warnings.
4. **A measured audit as a gate** (`toolkit/audit_villa.py`): host, position vs DWG, true geometry z/width, cut volume, door swing vs the drawing's arcs, roof tops and parapet edges. First run: 26 FAIL; after fixes: 0 FAIL. It found the arch windows that did not cut and the roof edges without parapets, none of which the placement log showed.
5. **Look at renders** after every phase (cropped 3D from four sides, plans). Three real defects (pit around a hip roof, open tower, missing parapets) were visible only there.
6. **One writer, chunked calls, idle probe**: long phases are a PowerShell loop that calls one script at a time and, on a timeout, waits until `revit_health` answers.

## 4. Improvements, in priority order

### P0 - makes the bridge dependable
1. **Async jobs instead of a 30 s window.** `revit_run_job(script|command)` returns a job id at once; `revit_job_status(id)` returns state, progress lines and the final output. Removes the lost-result failure that hit this session four times.
2. **Honest errors.** Revit failure messages ("Instance(s) ... not cutting anything", "Wall is slightly off axis") should arrive structured (`kind`, element ids, severity) and a transaction that Revit rolled back must be reported as a failed call, not `success`.
3. **Deploy the fixed add-in** (image export naming/size, parameter GUID guard, IronPython stdlib) and add a `revit_get_context` that reports the loaded add-in build, document, active view, approval mode and expiry, workspace.
4. **Native read tools** for what the audit needed, so no Python is required to inspect: `inspect_scene` (hosts, levels, rooms, geometry extents in a local frame, connectors, systems), `check_intersections` (solid, mesh-aware, with volumes), `audit_openings`, `get_warnings_delta`.
5. **Dev mode**: an explicit, time-boxed, logged mode in which `revit_execute_python` is allowed without per-plan approval, with every script and its diff recorded. (Requested; keep the gate as the default.)

### P1 - makes building faster and safer
6. **Verified creation tools** that bake in the rules above: `create_walls(polyline, kind)` (pre-orient, join check), `create_floor(...)` (asserts not a foundation slab), `place_opening(...)` (own transaction, fit check, cut-volume check, door swing from hinge/side), `create_roof(..., roof_type, slope, offset)`, `create_stair_u(...)`.
7. **Views**: `make_view(3d|plan|section, scope)` that crops/frames, never renames levels, and `export_view` that returns the real file path and size.
8. **Family service**: `make_mep_family(spec)` (box + port cubes + connectors, category), `make_void_family`, a content probe, and a "base family sanity" check (no nested instances, one type, parameters consistent).
9. **MEP routing**: `route(connector_a, connector_b)` with fittings, `branch(trunk, connector)` with takeoffs, and `system_report` (open ends, membership, circuits).
10. **Transaction policy** parameter: per-element transactions for placements (measured to matter).

### P2 - quality of life
11. A DWG/PDF reader tool (temporary-document import; line pairing; overlay PNG) and a scale-calibration helper.
12. A review-loop tool that runs the audit, renders the standard views and returns the failing lines only.
13. Warning triage by owner tag (which warnings belong to my elements).

## 5. How to reproduce the flow

```
python docs/recipes/... (data built by the digitising scripts in scratch)       # DWG -> JSON
revit_execute_python  p1_types, p3_walls, p4_floors, p5_openings (chunked), p6_stair, p7_roofs
revit_execute_python  toolkit/audit_villa.py      # must say 0 FAIL
revit_execute_python  toolkit/intersections.py    # solid overlaps in m3
revit_execute_python  views.py                    # cropped 3D + plans -> PNG
```

## 6. Open items (honest list)
- Arched/horseshoe openings that cut the wall (needs a working void or a different construction).
- Stair to the roof (the second stair run still needs its elevation logic fixed).
- MEP: connector-bearing families exist; routing, fittings, circuits and the MEP-only view are in progress; engineering sizing is not done and must not be claimed.
- The loaded add-in build and MCP tool inventory differ from the repository source; deployment and live acceptance are pending.
