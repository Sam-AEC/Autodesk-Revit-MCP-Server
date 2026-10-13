# What went wrong building a villa with an AI agent in live Revit, and how to harden against it

Session of 2026-10-13, Revit 2024, AEC Model Bridge 1.4.0, builder agent plus an independent reviewer. The goal was not a
finished villa. It was to **discover the failure modes** so each can be fixed in the tool, worked around, or made
impossible to repeat by a check. Every row below was observed, not assumed; evidence is a measurement or a rendered view.

Remedy types: **Fix** (change the tool), **Workaround** (a proven recipe), **Harden** (an automatic check, skill rule or
test so the agent cannot repeat it), **Content** (something the environment must supply), **Accept** (a limit to live with).
Status: **done** (in the repo, committed), **open**.

## A. Revit API and convention traps

| ID | Symptom | Root cause | Remedy | Status |
|---|---|---|---|---|
| RV-01 | 16 of 20 exterior walls had brick on the inside | The exterior side depends on drawing direction (counter-clockwise faces inward) | Harden: reviewer `WALL_ORIENT` probes a point 0.6 m out along the exterior normal; it must not be inside a room | done |
| RV-02 | First-floor furniture 3.2 m too high | For level-based families the placement height is an offset from the level, not absolute | Harden: reviewer `FIXTURE_LEVEL`; skill rule | done |
| RV-03 | Beds floated about 1 m off the wall; nightstands stacked | A family's origin is not its centre, and rotation is about the origin | Fix: measure real geometry, then move (`place_back_to_wall`) | done (v0) |
| RV-04 | WC placed backwards in one bathroom | `FacingOrientation` is family-specific: for the WC it points to the BACK, for beds it points sideways | Harden: reviewer `FIXTURE_BACK` measures the back/head from geometry; long term a per-family datasheet | done / datasheet open |
| RV-05 | Beds still 0.22 m from the wall after snapping | The bounding box includes hidden extent that is not visible geometry | Fix: snap to mesh/solid vertex extents, never the bounding box | done |
| RV-06 | Bounding box and geometry were `None` right after creation | Geometry is not computed until `Regenerate()` inside the transaction | Workaround: regenerate inside the transaction; never outside one (a helper tripped on this twice) | open: make the safe path the default |
| RV-07 | Roof creation always failed from IronPython | `NewFootPrintRoof` has an `out` parameter IronPython cannot marshal | Workaround: use the add-in command `revit.create_roof` | done |
| RV-08 | Scripts failed with `'Name'`, `no module named collections`, `'indexer#' object has no attribute 'Id'` | IronPython 2.7: no standard library; `Name` and phase-indexed properties (`FromRoom`, `ToRoom`, `Room`) do not map as properties | Workaround: parameters instead of `Name`; `get_FromRoom(phase)`; no stdlib imports | done (skill) |
| RV-09 | Layered types refused (`CompoundStructure is not valid`, `BadShellOrder`, wrong end-cap) | Layer order outside the core is fixed (substrate, insulation, membrane, finish); membrane must be 0 mm; end-cap depends on element kind | Workaround: edit the duplicated type's own structure with `SetLayers` | done |
| RV-10 | Blocking dialogs froze the bridge three times (Duplicate Types; "Can't cut instance"; "not cutting anything") | No failure handler in the add-in | Fix: add-in failure handler (open). Workaround: `IDuplicateTypeNamesHandler` and an `IFailuresPreprocessor` in recipes | partial |
| RV-11 | Doors hosted in the underground foundation wall; nothing cut | Nearest-wall picking ignored height | Harden: host must reach above the floor; reviewer `OPENINGS` | done |
| RV-12 | A 4.8 m "door" drew a giant swing arc | A hinged-door family used for a garage door | Content: a non-swinging type. Accept as window category until a sectional door family exists | open |
| RV-13 | Stair: 21 risers for a 3.2 m storey; slab opening mismatch; door swing hitting the stair foot | Riser count follows run length; no clash check | Harden: reviewer `STAIR`; a swing-versus-stair check is open | partial |
| RV-14 | 3D export was blank | Export fits to the whole project extents, not the section box | Workaround: set the view crop box to the villa | done |
| RV-15 | Plans looked like line sketches | Materials without cut patterns; Coarse detail level | Workaround: solid cut fill per material, Fine detail; reviewer `DETAIL` | done |
| RV-16 | Swallowed warnings hid real defects (overlapping floors, identical instances) | A failure handler that deletes warnings also hides the evidence | Harden: always re-measure the model warning count before and after; reviewer `WARNINGS` | done |
| RV-17 | Purge-and-rebuild left duplicates | Floors keep Comments under a different parameter, so tagging silently failed | Fix: tag fallback; the tag helper now reports failures | done |
| RV-18 | The project already has 2,077 warnings | Production model baseline | Accept: measure deltas, never absolutes | done |

## B. Tool and add-in limits

| ID | Symptom | Root cause | Remedy | Status |
|---|---|---|---|---|
| TL-01 | Revit hung on a model snapshot | One unbounded pass over every element on the UI thread, reading geometry-computed values | Fix: element and time budget, category scope, `truncated` flag | done |
| TL-02 | A timed-out request ran three times back to back | Client retry re-queued the same request id and the executor drained the whole queue in one turn | Fix: de-duplicate by id, drop abandoned requests, one request per Revit turn | done |
| TL-03 | Curated wrapper tools lose parameters (no wall type) | The hub maps only a fixed subset | Fix: `revit_raw_command` and `revit_list_commands`; promote proven recipes to typed commands | partial |
| TL-04 | QA rule `door_no_host` flagged all 1,006 doors | The snapshot never wrote `host_uid` | Fix: written now (source); not installed until Revit is closed | open (install) |
| TL-05 | The hub never started; the panel chat had no Revit tools | Missing workspace folder crashed import; then the hub's working folder poisoned the chat's MCP server | Fix: create workspace; run from the workspace; keep launch output | done |
| TL-06 | The 30 s bridge limit | By design | Accept: keep scripts under 20 s; export one image per call | accept |
| TL-07 | Every add-in change needs Revit closed to install | DLL locked while loaded | Accept; batch changes | accept |

## C. Content and environment

| ID | Finding | Remedy |
|---|---|---|
| CT-01 | The Autodesk content folder has structural and annotation content only: no doors, windows, furniture, planting | Use the model's own families, or Autodesk templates (`DefaultMetric.rte` has door and window families) |
| CT-02 | Heijmans door and window families are "sparing" openings, not real doors | Real families needed |
| CT-03 | 82 of 91 furniture families are generic "Furniture N" with unknown content; no king bed, wardrobe, kitchen set, railings, lighting | Provide a vetted Heijmans family kit; or generate families by API (done for a king bed) |
| CT-04 | Bed families have imported mesh geometry and no size parameters | Cannot be resized; choose by measured size or create parametric ones |
| CT-05 | `W:\BIM` is empty or restricted | Ask for the library location |

## D. Agent errors (mine)

| ID | Error | Hardening |
|---|---|---|
| AG-01 | Coordinates computed by hand from unstated assumptions (origin, rotation, offsets). The root of most spatial errors | Placement by measurement; semantic placement tools (open) |
| AG-02 | Naive checks reported false facts (a centroid orientation test; a join check on a method that does not exist) | Exact tests; self-audit of the reviewer before reporting |
| AG-03 | Declared the first villa done without looking at it | Builder skill: no "done" without the reviewer and rendered views |
| AG-04 | Chose types by name (a screed layer as the floor, a 3 mm membrane as the roof) | Inspect real layer stacks first |
| AG-05 | Bed sizes never checked against standards (single bed in the master) | Family datasheet with real sizes |
| AG-06 | Layout flaws (door swing into the stair; no corridor) | Circulation check (done); swing and clearance checks (open) |
| AG-07 | A blanket `Stop-Process -Name python` killed the user's MCP servers | Never kill processes by name; target by command line |

## E. Process and harness gaps (what would make the agent reliable)

| ID | Gap | Proposed layer |
|---|---|---|
| PG-01 | No geometric verification at the moment of placement | Every placement tool measures and verifies before returning |
| PG-02 | No per-family datasheet (true size, origin offset, front/back/head vector, clearances) | Probe each family once; store as JSON; checks read it |
| PG-03 | No semantic placement API | `place_back_to_wall`, `center_in_room`, `flank`, `align_to_grid` over real room boundaries |
| PG-04 | No clash, clearance or swing checker | Door-swing, circulation width (0.9 m), bed clearances (0.6 m sides, 0.8 m foot), stair headroom |
| PG-05 | The agent cannot see positions | Scene graph (rooms, walls, openings, free space) plus plan renders with a coordinate grid and ids |
| PG-06 | No layout solver | Constraint or packing solver proposes plan options; the agent chooses and verifies |
| PG-07 | Standards live in memory, not as rules | Heijmans and building-code rules as executable checks |
| PG-08 | Reviewer started naive | Reviewer is part of the harness and is itself reviewed |

## The pattern

Almost every spatial error had the same shape: **coordinates computed by hand from hidden conventions, with no geometric
feedback until later.** A stronger model does not remove Revit's conventions. What removes the errors is (1) measurement
at placement time, (2) a deterministic geometry layer that does the arithmetic, and (3) automatic checks that make the
error impossible to ship. The reviewer in `scripts/revit/bim_review` is the first layer of that; its checks `WALL_ORIENT`,
`FIXTURE_LEVEL` and `FIXTURE_BACK` were each added after a defect was found, and each now fails if the defect returns.

## F. Villa 2 session (DWG to Revit, 2026-10-13): new findings

| ID | Measured finding | Consequence | Status |
|---|---|---|---|
| V2-01 | The villa-1 floor types were duplicated from the project's first `FloorType`, which was a foundation slab. All 12 villa floors were **Structural Foundations**, not Floors | Rebuilt as genuine Floors; the floor builder now asserts `IsFoundationSlab == False` | fixed + guarded in `docs/recipes/villa2/p4_floors.py` |
| V2-02 | `Wall.Flip()` after creation **breaks the corner joins** of that wall (11 of 27 ends unjoined). Revit puts the exterior face on the LEFT of the drawing direction | Reverse the segment before creating the wall; verify with `LocationCurve.get_ElementsAtJoin` | fixed in `p3_walls.py` (`preorient`) |
| V2-03 | Ground walls ran up to the level while the slab edge sat in the same zone: 34 wall/floor solid overlaps, 4.5 m3 | Walls stop at the slab underside (top offset = slab thickness); slabs run to the outer wall faces; check with solid intersection | 34 -> 5 -> 0 pairs, tool in `docs/recipes/toolkit/intersections.py` |
| V2-04 | Snapping wall ends to the nearest wall line can collapse a short nib to zero length (Revit: "curve length too small") | Snap only when the result keeps a minimum length | handled by hand; add the guard to the snapper |
| V2-05 | A 45 degree wall that is 0.2 degrees off gives "Wall is slightly off axis" | Construct diagonal walls from exact dx == dy | fixed in data |
| V2-06 | `NewProjectDocument` + `Document.Import` of a DWG into a drafting view reads a DWG without touching the project; an uncommitted transaction in the temp document blocks `Close`, and dropping the reference plus `GC.Collect()` rolls it back | Safe DWG-to-geometry route when no converter is installed. A flattened DWG has a single layer: walls must be recovered by parallel-line pairing | used for the villa-2 plans |
| V2-07 | `revit_export_image` (loaded add-in, old build) returns success with `file_exists:false`; the real file is `<requested stem> - <ViewType> - <view name>.png` | `ImageExportOptions` directly inside `revit_execute_python` is reliable; always list the folder | workaround in `views.py` |
| V2-08 | `revit_execute_python` has no persistent scope: objects such as a `Transaction` do not survive between calls | Always roll back/commit inside one call | noted |
| V2-09 | `NewFootPrintRoof` fails with "Value cannot be null" from IronPython (out parameter) and from the add-in when no roof type is passed. The add-in command `revit.create_roof` works with `roof_type` in the payload via `revit_raw_command`; the MCP tool `revit_create_roof` has no `roof_type` argument | Roof creation tool should accept the roof type; slope is then set from IronPython with `FootPrintRoof.GetProfiles()` + `set_DefinesSlope` / `set_SlopeAngle` | worked around; MCP tool schema to extend |
| V2-10 | Creating the primary plan view of an API-created level and setting `VIEW_NAME` **renames the level** | Never rename a level's own plan view; create plan views through `make_plan` | fixed in `views.py` |
| V2-11 | A never-opened isometric 3D view exports blank (model at the project origin) | Crop the view to the projected section box before `ExportImage` | fixed in `views.py` |
| V2-12 | Door/window family editing: (a) setting Width/Height type parameters on a generated family from the project **rescales its geometry** (4.1 m window became 7.3 m); (b) window geometry must start at the family's Sill reference plane or the instance sits 0.9 m low; (c) a family `Opening` or a void form with an arch profile does **not** cut the host wall (rectangular cuts work) | Set Width/Height inside the family before building geometry, start at the sill plane, and cut arches with a void family instance (`InstanceVoidCutUtils.AddInstanceVoidCut`) or Cut Geometry | fixed (a)(b); (c) in progress |
| V2-13 | A `revit_execute_python` call that runs longer than 30 s returns a bridge timeout while Revit keeps working; the result is lost | Split family generation (one family per call) from placement; verify state with a read-only audit afterwards | process rule |
| V2-14 | Measured audit needed: openings were rebuilt several times and the first 3D look showed errors the placement log did not (arch windows uncut, roof pit, missing tower cap) | `docs/recipes/toolkit/audit_villa.py` is a mandatory stage after openings and roofs: host, DWG position, true geometry z/width, cut volume, roof heights and parapet edges | added |
