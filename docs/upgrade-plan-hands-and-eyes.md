# Upgrade and bug-fix plan: AEC Model Bridge as the hands and eyes of an AI inside Revit

Written 2026-10-14, after two villas (a first build and a DWG-driven second build with MEP) were produced through the bridge in a live
Revit 2024.3 session. Companion documents: `docs/revit-mcp-behaviour-and-improvements.md` (what Revit does through the bridge),
`docs/bim-agent-findings.md` (catalogue V2-01..V2-14), `docs/prompts/revit-agent-preflight-and-verify.md` (the agent-side checks this plan turns into tools),
`docs/recipes/` (working scripts that become native tools).

Status: **a plan, not shipped behaviour.** Section 12 holds the root causes verified in source on 2026-10-14 and the build order that follows from them; where it disagrees with sections 2 and 5, section 12 wins. Items marked *(verify)* are suspected from reading the source or from a single observation and must be
reproduced before work starts. Nothing here has been built or compiled yet.

## 1. What "hands and eyes" means here

An AI that builds a model needs four capabilities, each with a bounded cost per step:

| Capability | Question it answers | Today |
|---|---|---|
| **Eyes (state)** | What exists, where, in which frame, joined to what? | 115 add-in commands, mostly per-element getters; whole-scene questions need a hand-written Python script |
| **Eyes (geometry)** | Does it overlap, cut, fit, connect, face the right way? | `revit.check_clashes` is bounding-box only; everything else is a recipe script |
| **Eyes (picture)** | What does it look like? | `revit.export_image` works only after a view is framed; wrong file name/size reported by the loaded build |
| **Hands** | Change the model correctly the first time, and tell me honestly what happened | Plain creators (`create_wall`, `create_roof`, `create_pipe`) with no rule enforcement; `revit_execute_python` for everything else, behind an approval gate that marks every script as mutating |
| **Memory/continuity** | Where was I after a timeout, a restart, a context reset? | Model tags and files the agent invents itself; lost results on timeout |

The measure of success is not the number of commands. It is: **how many calls and how many tokens does an agent need to build a phase, prove it is
right, and recover from a failure?** In the villa 2 session the answer was dominated by hand-written Python (about 20 recipe files), manual
re-verification after timeouts, and image checks that only a human noticed. This plan moves each of those into the tool.

## 2. Where the tool stands (evidence)

Read from the repository on 2026-10-14 unless marked otherwise.

| Layer | Fact | Source |
|---|---|---|
| Transport | The HTTP wait is 30 s; on timeout the pending entry is removed, so the result of a script that Revit is still running is discarded | `packages/revit-bridge-addin/src/Bridge/CommandQueue.cs` (`WaitForResponse(requestId, 30000)`), `BridgeServer.cs` (`HandleExecute`) |
| Transport | The Python client retries 3 times with the same request id, but a "timed out" answer comes back as a normal 200 and becomes `BridgeError`; nothing re-polls the result | `packages/mcp-server-revit/src/revit_mcp_server/bridge/client.py` |
| Execution | One request per ExternalEvent turn, strictly serial; `revit_health` queues behind a long script, so it doubles as an idle probe | `ExternalEventHandler.cs`, observed |
| Commands | 115 `[BridgeCommand]`s in one 4,832-line file | `BridgeCommandFactory.cs` |
| Roofs | `revit.create_roof` has no default `roof_type` and fails with "Value cannot be null"; the MCP tool `revit_create_roof` exposes only points/level/slope, not `roof_type` | `BridgeCommandFactory.cs`, MCP schema |
| Clashes | `revit.check_clashes` compares bounding boxes only | `BridgeCommandFactory.cs` |
| MEP | `create_duct` / `create_pipe` take start and end points only: no connectors, system type, size, fittings | `BridgeCommandFactory.cs` |
| Python | `revit.execute_python` is declared mutating, so even read-only audits need approval; IronPython 2.7 with no `json`/`time` in the deployed build | `BridgeCommandFactory.cs`; observed |
| Jobs | A job manager exists (queued/running/completed/failed/cancelled, artifacts, secret sanitising) but is used only by the legacy server, not for Revit calls | `src/revit_mcp_server/jobs.py`, `legacy/server.py` |
| Deployment | The loaded add-in was older than the repository (image export fixes missing); no way to ask the running add-in which build it is *(observed; verify the exact gap)* | `findings V2-07` |
| Tests | 79 test entries under `packages/mcp-server-revit/tests`, source-guard style (`test_addin_source_guards.py`) and contract tests; nothing drives a live Revit | `tests/` |

## 3. Principles

1. **A timeout is a status, not a loss.** Every call has a durable result retrievable by id.
2. **A tool that can be wrong must say how it checked.** Mutating tools return what they changed (ids), what they measured afterwards, and any
   warning they swallowed. "success" means Revit committed *and* the post-check passed.
3. **Measure in the tool, not in the prompt.** Anything the agent had to script twice (join check, solid overlap, cut check, nested-instance probe,
   warnings delta, framed render) becomes a native read-only tool with a bounded, structured output.
4. **Rules baked into the hands.** The creators enforce what cost us hours (pre-oriented walls, not-a-foundation floors, openings that fit and cut, roofs with a type,
   views that never rename levels). Raw access stays, behind the gate, for everything else.
5. **Read-only is free.** Approval and Auto-mode apply to mutation. Read-only scripts and tools never prompt. Dev mode is explicit, time-boxed and logged.
6. **Small outputs.** Default output is a summary plus FAIL lines; detail goes to a file whose path is returned. The agent's context is the scarce resource.
7. **One writer.** The add-in stays strictly serial; the server reports queue depth and the running job so the agent can wait instead of guessing.
8. **Verified means live.** A feature is done when the live acceptance suite (section 8) passes against a running Revit, not when unit tests pass.

## 4. Phases

Effort: S <= 1 day, M 2-4 days, L 1-2 weeks, for one developer who can run Revit. Order matters; each phase is shippable on its own.

### Phase 0 - Trust (make results durable and honest). Target: 1 week

| # | Work | Files | Done when | Size |
|---|---|---|---|---|
| 0.1 | **Durable results.** Keep finished results for a TTL (default 15 min) keyed by request id; do not drop `_pending` on timeout, mark it `running`. New `GET /result/{request_id}` returns `queued/running/done/failed` plus payload. The server polls it (backoff) instead of failing at 30 s and returns `status: running, request_id` after a configurable soft wait (default 25 s). | `CommandQueue.cs`, `BridgeServer.cs`, `bridge/client.py` | A 90 s script returns its real output via one follow-up call; no output is ever lost in the timeout test | M |
| 0.2 | **Async job tools.** `revit_run_job(command | script, args, wait_s)` returns `{job_id, state, output?}`; `revit_job_status(job_id)` returns state, elapsed, last progress lines, final output/artifacts; `revit_job_cancel` for queued jobs. Reuse `jobs.py` (`JobManager`) on the Python side; the add-in keeps the single serial queue. Scripts can call `progress("...")` to stream lines. | `jobs.py`, `mcp_server.py`, `tool_metadata.py`, add-in `PythonEngineFactory.cs` (progress hook) | Chunked phases from the villa 2 batch runner become one job each; killing the MCP process does not lose a running job | M |
| 0.3 | **Honest failure.** Detect Revit-side rollback (transaction status `RolledBack`, `FailuresAccessor` errors, element count delta of zero when creates were expected) and return `success:false, kind, failed_element_ids, revit_messages[]`. Classify: `rolled_back`, `warning_swallowed`, `timeout_running`, `invalid_input`, `revit_dialog_blocked`. | `BridgeCommandFactory.cs` (shared failure handler), `errors.py` | A window wider than its wall returns `rolled_back` with the host wall id; "slightly off axis" arrives as a structured warning | M |
| 0.4 | **Context tool.** `revit_get_context`: add-in version + git sha/build timestamp, Revit version, document title/path/guid, active view, workshared state, queue depth, running job and its age, approval mode + expiry, workspace folder, python engine features (json? time?). Add the same stamp to every response header. | add-in `HealthCommand`, `mcp_server.py` | Agent can detect "loaded add-in older than repo" in one call (fixes V2-07 class of problem) | S |
| 0.5 | **Deployment hygiene.** `scripts/build-addin.ps1` writes a build stamp; `install-addin.ps1` verifies the loaded add-in matches after a Revit restart; CI guard compares the stamp to `VERSION`. Fix `revit.export_image` result (real file path, size, exists) in the same release. | scripts, `BridgeCommandFactory.cs` | `revit_get_context` build equals the repo build after install; image export returns the true path | S |
| 0.6 | **Read-only Python without prompts.** Add `mode: read | write` to `revit_execute_python`. `read` runs in a read-only wrapper (no `Transaction.Start` allowed: the engine injects a `doc` proxy or a transaction guard that throws) and is not gated. Mutating scripts keep the gate. | `PythonEngineFactory.cs`, `tool_metadata.py`, approval modules | The audit and intersection scripts run without approval and cannot change the model | M |
| 0.7 | **Dev mode.** `AEC_BRIDGE_DEV_MODE=1` or a signed local switch: time-boxed (<= 8 h), banner in the panel, every script and its before/after element-count delta written to the audit log. Keep ADR 0008/0017 as the default; add ADR 0018. | `config.py`, approval modules, `panel/`, `docs/0018-...` | Dev mode never persists across a server restart; the audit log has an entry per call | M |
| 0.8 | **IronPython runtime.** Ship `json`, `time`, `collections`, `math` equivalents with the engine (or a vetted shim module) and test them with the existing `scripts/test-ironpython-runtime.ps1`. | `PythonEngineFactory.cs`, `scripts/` | A script can `import json` and `import time` in the deployed build | S |

### Phase 1 - Eyes (native inspection, geometry checks, pictures). Target: 2-3 weeks

All Phase 1 tools are read-only, never prompt, and return `{summary, fails[], info[], detail_file?}`.

| # | Tool | What it replaces | Returns | Size |
|---|---|---|---|---|
| 1.1 | `revit_inspect_scene(scope, frame)` | hand-made inventory scripts | per category/level: counts, extents in a **local frame** (origin + rotation given, so a villa 3.9 km from the project origin reads as 0..20 m), levels with elevations and plan-view existence, rooms, hosts, tag census (`Comments` prefix) | M |
| 1.2 | `revit_check_joins(ids|tag)` | `get_ElementsAtJoin` loops | per wall end: joined/not, joined-to ids, join type; summary "27 ends, 0 unjoined" | S |
| 1.3 | `revit_check_intersections(set_a, set_b, tolerance, min_volume)` | `toolkit/intersections.py` | solid/solid boolean intersect volumes (Revit `BooleanOperationsUtils`), pairs sorted by volume, categories, element ids and locations; bounding boxes only as a pre-filter. Replaces the bounding-box `check_clashes` (keep it as `mode=bbox`). | M |
| 1.4 | `revit_audit_openings(tag, data?)` | `toolkit/audit_villa.py` openings half | host wall, centre-in-wall-piece, wall volume drop or ray-through-centre test, sill/head heights, width/height vs data, door swing side (symbolic arc centre vs hinge), "opening cuts nothing" warning match | M |
| 1.5 | `revit_audit_roofs(tag, data?)` | audit roofs half | top z vs level, slope, covers footprint, open edges without parapet, stair openings present | M |
| 1.6 | `revit_probe_family(name)` | nested-instance probe, connector census | nested `FamilyInstance`s, nested families, category, parameters, connector list (domain, system, size, direction), geometry extents and sill datum (catches the nested EV charger, 1.8x rescaling, 0.9 m sill offset) | M |
| 1.7 | `revit_system_report(system|tag)` | `m3_route.report()` | per MEP system: members, open ends (with xyz), disconnected fittings, sizes, flow direction mismatches, equipment with unconnected ports | M |
| 1.8 | `revit_warnings_delta(baseline_id?)` | manual counting | `snapshot_warnings()` returns a baseline id; later call returns new/closed warnings with element ids and owner tag | S |
| 1.9 | `revit_check_orientation(tag)` | wall-side probes | probes 0.6 m along each exterior wall's `Orientation`; reports walls whose exterior probe lands inside a room | S |
| 1.10 | `revit_frame_view(view, ids|bbox|tag, direction)` + `revit_render(views[], size, style)` | `views.py` | creates/uses a 3D view, sets crop box to the projected section box, `ShadingWithEdges`, never renames levels; exports PNG; returns the **real path, bytes, and a "looks blank" flag** (histogram-based) so the agent knows before reading the image | M |
| 1.11 | `revit_screenshot_compare(a, b)` | none | optional: pixel diff between two renders of the same framing to confirm a change happened | S |
| 1.12 | Pagination and budgets | n/a | every list tool gets `limit`, `fields`, `count_only`; default <= 50 rows | S |

### Phase 2 - Hands (verified creators). Target: 3-4 weeks

Each creator is idempotent (re-run purges its own tag), runs per-element transactions where it matters, runs its own post-check from Phase 1 and returns the result.

| # | Tool | Rules baked in (source) | Size |
|---|---|---|---|
| 2.1 | `revit_build_walls(polyline|rects, wall_type, base, top, offsets, tag)` | pre-orient so the exterior is on the left; never `Flip()`; stop at slab underside when a slab level is given; min segment guard; exact-diagonal check; join check on return (V2-02..V2-05) | M |
| 2.2 | `revit_build_floors(boundaries, floor_type, level, tag)` | asserts `IsFoundationSlab == False` (V2-01); slab edges at outer wall faces; reports overlap with walls | S |
| 2.3 | `revit_place_openings(list, tag)` | one transaction per opening; fit check before placing; hosts chosen among walls that reach above the floor; door swing from hinge side + `flipFacing/flipHand` read from the symbolic arc; sill/head set; returns cut-volume per opening; rollback becomes `rolled_back` with host id | L |
| 2.4 | `revit_create_roof(...)` fix + `revit_build_roof(profile, roof_type, slope_per_edge, level, top_offset, openings[])` | `roof_type` default + argument; create the level's plan view if missing; set slopes via profile; apply negative offset so the top sits on the level; cut stair/skylight openings in the same call (user-reported missing roof opening) | L |
| 2.5 | `revit_build_stair(from_level, to_level, run_shape, width, risers, landing, opening_in=[floors|roof])` | stair by component with `TopElevation` raised before the second run; `ActualTreadDepth` / `DesiredRisersNumber` first; `ExtensionBelowRiserBase=0` for upper-level starts; creates the floor/roof opening and the railing; head-clearance check | L |
| 2.6 | `revit_create_level(name, elevation, make_plan=true)` | creates the plan view; never renames the primary view (V2-10) | S |
| 2.7 | `revit_make_view(kind, scope, name)` | never renames a level's own view; applies view template; crop to scope | S |
| 2.8 | `revit_place_content(family, type, host|point, face_to=wall|room, clearance)` | measures the family geometry to find back/head, rotates, touches the wall face (`recipes/villa/p7g_back_to_wall.py`) | L |
| 2.9 | `revit_checkpoint(name)` / `revit_restore(name)` | records ids and tags per phase; restore = purge the tag (and report what else changed). Builds on `docs/proof-and-revert.md` | M |
| 2.10 | Transaction policy | `transaction: per_element | one`, `on_error: skip | abort`, default per-element for placements | S |

### Phase 3 - Families and MEP (specialist hands). Target: 3-4 weeks

| # | Tool | Details | Size |
|---|---|---|---|
| 3.1 | `revit_make_family(spec)` | one call per family; template-less (edit a vetted base family); deletes nested instances; sets Width/Height inside the family; sill datum rule; single type named like the family; saves with `OverwriteExistingFile`; closes the family document in `finally`; returns `revit_probe_family` output. Kinds: door, window, mep equipment, fixture, air terminal, light, void. | L |
| 3.2 | Port spec | port cubes with real connectors in the right domain/system/size/direction; categories for Mechanical, Plumbing, Electrical, Lighting, Air terminals (`m1_mep_families.py`) | M |
| 3.3 | Void/arch strategy | Decision spike (1 day): `InstanceVoidCutUtils.AddInstanceVoidCut` from a void-only family vs. a wall-sketch edit vs. keeping arches as rectangular + decorative frame. Implement the winner, with a measurement that the host volume drops (V2-12, open item in the behaviour doc). | M |
| 3.4 | `revit_route(kind, from_connector, to_connector, via[], size, system, type)` | stub, vertical, horizontal legs; elbows/unions/takeoffs created, not left loose; skips segments below the type's minimum; clear error on pipe sizes below the fitting minimum (32 mm Dyka); returns created ids + open ends (`m3_route.py`) | L |
| 3.5 | `revit_branch(trunk, connector)` / `revit_riser(trunk, x, y, z)` | takeoff fitting onto a straight piece; vertical pieces with correct system id | M |
| 3.6 | `revit_size_check(system)` | **Not sizing.** Reports only mechanical facts (minimum fitting size, connected sizes, velocity if flow is defined). Output carries "not an engineering calculation". | S |
| 3.7 | `revit_make_circuits(panel, items[], system)` | `ElectricalSystem.Create` + `SelectPanel`; reports unassigned fixtures and panel load totals | M |
| 3.8 | `revit_mep_view(systems[])` | MEP-only 3D view with filters/visibility for the chosen systems, framed | S |
| 3.9 | Category guard | refuse to create/place an element in a category that does not match its role (the EV-charger-in-MEP bug) unless `force_category` | S |

### Phase 4 - Source documents and the build-audit-review loop. Target: 2-3 weeks

| # | Work | Details | Size |
|---|---|---|---|
| 4.1 | `revit_read_dwg(path)` | temporary-document import in a drafting view (nothing touches the project), returns lines/arcs/text per layer into a file; layer-less DWGs: wall pairing at a given thickness; units/scale calibration helper (known dimension -> scale) | L |
| 4.2 | `dwg_overlay(extracted, rendered)` | PNG overlay of extracted walls/openings on the drawing for visual comparison before modelling | M |
| 4.3 | `revit_pdf_scale(path, page)` | rasterise a page and return the image + printed scale if present; no model changes | S |
| 4.4 | Phase runner | `revit_run_phase(recipe, data, tag)`: purge-by-tag, chunking (<= 20 s units), progress, post-check hook, returns the check table. Recipes are the existing `docs/recipes/villa2/*` ported to native tools or kept as scripts. | M |
| 4.5 | `revit_review(tag, views[])` | one call: audits (1.2-1.9), warnings delta, standard renders (1.10), returns FAIL lines and image paths; the `bim-reviewer` agent consumes it so its read-only procedure is a single command | M |
| 4.6 | Skill and prompt update | `revit-bim-builder` skill points to the native tools; `docs/prompts/revit-agent-preflight-and-verify.md` lines "run script X" become tool names | S |

### Phase 5 - Quality, scale, safety. Ongoing

| # | Work | Details |
|---|---|---|
| 5.1 | Split `BridgeCommandFactory.cs` (4,832 lines) into per-domain command classes (walls, openings, roofs, views, MEP, families, inspect) behind the existing `[BridgeCommand]` attribute; no behaviour change, source-guard tests keep passing |
| 5.2 | Contract tests for every new tool (schema, defaults, error kinds) in the same style as `test_mcp_error_results.py`; mock-mode responses must not look like real output (existing `test_mock_fallback_guard.py`) |
| 5.3 | Live acceptance suite (section 8) run before each release, results stored in `docs/` |
| 5.4 | Performance: batch element reads (`FilteredElementCollector` with filters, `ElementId` sets), avoid per-element API round trips; measure on the 1.7 GB project (about 2,080 warnings) |
| 5.5 | Multi-Revit and workshared safety: documents identified by GUID in every call; refuse writes to a central model without an explicit flag (ADR 0014) |
| 5.6 | Observability: structured per-call log (tool, duration, queue wait, ids changed, warnings delta), a panel view of the running job and queue |

## 5. Bug list (fix with the phase named in the last column)

| ID | Bug | Evidence | Fix |
|---|---|---|---|
| B-01 | Result of a script lost when it exceeds 30 s while Revit keeps running it | `CommandQueue.cs`; four occurrences in the villa 2 session | 0.1, 0.2 |
| B-02 | `revit.create_roof` fails "Value cannot be null" without a roof type; MCP tool cannot pass one | `BridgeCommandFactory.cs`, tool schema | 2.4 |
| B-03 | Image export reports wrong file name/`file_exists:false` in the loaded build; blank 3D for never-opened views | V2-07, V2-11 | 0.5, 1.10 |
| B-04 | `check_clashes` is bounding-box only (false positives and negatives) | `BridgeCommandFactory.cs` | 1.3 |
| B-05 | A Revit rollback or swallowed failure can come back as success | behaviour doc §4 item 2 *(verify with the too-wide window case)* | 0.3 |
| B-06 | `execute_python` is always mutating: read-only audits need approval | `BridgeCommandFactory.cs` | 0.6 |
| B-07 | `create_duct` / `create_pipe` create loose segments with no connectors or fittings; MEP routing needed 180 lines of Python | `BridgeCommandFactory.cs`, `m3_route.py` | 3.4, 3.5 |
| B-08 | Python engine lacks `json`/`time` in the deployed build; new scope per call | observed, V2-08 | 0.8 |
| B-09 | Loaded add-in can be older than the repo with no way to tell | V2-07 | 0.4, 0.5 |
| B-10 | Levels created through the API have no plan view; view rename renames the level | V2-10 | 2.6, 2.7 |
| B-11 | Floors can be created with a foundation-slab type | V2-01 | 2.2 *(also check `revit.create_floor` default type selection)* |
| B-12 | Walls: `Flip()` breaks joins; diagonal off-axis; short nibs | V2-02, V2-04, V2-05 | 2.1 *(check whether `revit.create_wall` flips)* |
| B-13 | `place_door` / `place_window`: no fit check, no per-opening transaction, no swing control, no cut verification | villa 2 openings work *(verify the current implementation first)* | 2.3 |
| B-14 | Generated families can inherit nested content and be rescaled by project-side parameter edits | V2-12; EV charger in "Pole" | 1.6, 3.1 |
| B-15 | Non-rectangular openings do not cut the host | V2-12 | 3.3 |
| B-16 | Server-side job manager exists but Revit calls do not use it | `jobs.py`, `legacy/server.py` | 0.2 |
| B-17 | Stair from an upper level to the roof not solved; stairs through floors/roof leave no opening | behaviour doc §6, user report | 2.4, 2.5 |
| B-18 | `revit.export_image` argument set (`view_id`, `output_path`, `format`, `width`) cannot frame; no way to know if the image is empty | `BridgeCommandFactory.cs` | 1.10 |

## 6. Output contract for every new tool

```json
{
  "ok": true,
  "tool": "revit_check_intersections",
  "build": "1.4.1+abc1234",
  "document": {"title": "...", "guid": "..."},
  "elapsed_ms": 1840,
  "summary": "412 pairs checked, 0 overlaps above 0.0005 m3",
  "fails": [],
  "info": [],
  "changed_ids": [],
  "warnings_delta": {"new": 0, "closed": 0},
  "detail_file": null,
  "limits": {"truncated": false}
}
```

- Failures use `ok:false` with `kind` (see 0.3), `message`, `element_ids`, and `hint` (the rule that applies, e.g. "walls stop at the slab underside").
- Mutating tools always list `changed_ids` and a `post_check` section; a creator never returns `ok:true` if its post-check failed.
- Mock mode must set `mock:true` at the top level; the agent prompt treats mock output as UNVERIFIED.

## 7. Safety and governance

- Read-only tools and read-mode scripts never open a transaction (enforced in the engine, not by convention).
- The approval gate stays the default for mutation. Dev mode is explicit, time-boxed, logged and visible in the panel (0.7).
- Every mutating call carries a phase tag so `revit_restore` can undo it; nothing deletes elements it did not create unless the call lists their ids.
- Workshared/central models: writes refused without `allow_workshared`.
- No claim of engineering correctness: sizing, load and code checks are reported as mechanical facts with a disclaimer (3.6).
- Security: new file arguments (DWG, PDF, output paths) go through the existing `ValidatePayloadPaths` workspace sandbox.

## 8. Verification: the live acceptance suite

Tests against source prove nothing about the loaded add-in (V2-07). Build a repeatable suite in `scripts/revit/acceptance/` that runs against a **disposable
copy** of a small test project (use the canonical model fixture where possible) in a live Revit:

| Test | Passes when |
|---|---|
| T1 Timeout durability | a 90 s sleep script returns its output via `revit_job_status`; killing the MCP client mid-run loses nothing |
| T2 Honest failure | a 4 m window in a 1 m wall piece returns `rolled_back` with the host id and leaves the model unchanged |
| T3 Walls and joins | a 6-wall house plan: 0 unjoined ends, exterior side correct on all walls, no `Flip` calls in the log |
| T4 Floors and levels | floors not foundation slabs; level created with a plan view; renaming a view does not rename the level |
| T5 Openings | 20 openings: each cuts its host, correct swing, no uncut walls, one transaction each |
| T6 Roof | hip + flat roof with stair opening; tops on the level; parapet edges reported |
| T7 Stair | ground->first and first->roof stairs with openings and head clearance reported |
| T8 Family probe | generated MEP family has 0 nested instances, correct category and connector list |
| T9 MEP | route from equipment A to B: all ends connected, fittings present, `system_report` 0 open ends |
| T10 Render | framed 3D from 4 sides: files exist, not blank, correct size |
| T11 Read-only | audit scripts run without approval and cannot start a transaction |
| T12 Recovery | after a forced Revit restart the agent can read context and find its phase tags |
| T13 Villa 2 replay | the DWG-driven villa 2 recipes rebuild with 0 audit FAIL in under N chunks (target set after the first run) |

Record the result of every run with date, Revit version, add-in build and the failures; do not edit a failing test to make it pass.

### Metrics to track

| Metric | Baseline (villa 2 session, estimated) | Target |
|---|---|---|
| Lost results per 100 calls | about 4 timeouts in a session | 0 |
| Hand-written Python lines per phase | 100-400 | < 30 (data only) |
| Calls to verify a phase | 10-20 | <= 3 (`revit_review`) |
| Defects first seen by a human in a render | 3+ | 0 |
| Agent tokens per phase for checks | large (full audits printed) | summaries + FAIL lines only |

## 9. Sequencing and risks

Recommended order: 0.1 + 0.2 + 0.4 + 0.5 (transport and truth) -> 0.3 + 0.6 + 0.8 -> 1.2 + 1.3 + 1.8 + 1.10 (the checks the agent runs every phase) -> 2.1-2.3 -> 2.4-2.5 -> 3.x -> 4.x. Dev mode (0.7) can ship whenever requested; it is independent.

| Risk | Mitigation |
|---|---|
| Revit API behaviour differs between 2024 and other years the add-in targets | acceptance suite per supported year; feature flags for year-specific calls |
| Boolean intersections are slow on large models | pre-filter with bounding boxes and category sets; cap pairs; run as a job |
| Making creators strict breaks existing users of `create_wall` etc. | new tools get new names (`revit_build_*`); old commands stay and are marked "basic" in `tools-generated.md` |
| Read-only guard in IronPython is bypassable | guard at the API level (refuse `Transaction.Start` and `SubTransaction`), document it as a safety rail, not a security boundary |
| Scope creep into engineering calculations | 3.6 wording and a review gate: no sizing outputs without a named source standard |
| Single UI thread blocks Revit for the user during long jobs | job chunking, progress, cancel for queued work, warning in the panel while a job runs |

## 10. Open questions for the owner

1. Soft-wait default (25 s) and result TTL (15 min): acceptable, or should long jobs persist across add-in restarts?
2. Is dev mode a local switch only, or should it be a signed policy file for team installs?
3. New `revit_build_*` names alongside the old creators (recommended), or replace the old creators in 2.0?
4. Which Revit years must pass the acceptance suite for the next release (2024 only, or 2023-2025)?
5. Where should the DWG/PDF readers live: add-in (needs Revit) or a Python tool (DWG parsing without Revit, e.g. ezdxf after conversion)? The Revit-side import is proven; a Python reader would work offline.

## 11. Definition of done for "hands and eyes"

An agent given a DWG, a PDF and the pre-flight prompt can build a two-storey house with MEP, and without human help: never loses a result, never
builds in the wrong document, proves each phase with at most three calls, sees its own renders, and reports `0 FAIL` that the independent
reviewer confirms. Until the acceptance suite says so against a live Revit, none of that is claimed.

## 12. Root causes verified in source (2026-10-14) and the resulting build order

Read from the repository, nothing run against Revit. `BCF` = `packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs`.

| ID | Verdict | Root cause (evidence) | Fix | Size |
|---|---|---|---|---|
| B-01 | partial | `CommandQueue.cs:78` drops the pending entry on timeout; `BridgeServer.cs:237` returns the timeout as HTTP 200 `Status=error`; `client.py:49-92` retries only on transport errors. The result is recoverable only inside a ~90 s window and only if the client times out first | TTL result cache, `GET /result/{id}`, client polls on "timed out" | M |
| B-02 | confirmed | `NewFootPrintRoof` gets a null roof type (BCF:495-531); the MCP lambda (`providers/revit.py:344-353`) never sends `roof_type`, and `slope` is never read | default to first `RoofType`; forward both | S |
| B-03 | partial | export naming fix is in source (BCF:2321-2423) but missing from the installed DLL (see B-09) | redeploy | S |
| B-04 | confirmed | bbox O(n*m) loop with `Name` lookups inside, no budget (BCF:3382-3430), can hang the UI thread | budget + `truncated`; solid mode later | M |
| B-05 | confirmed | all 60 `Commit()` calls ignore `TransactionStatus`; no `IFailuresPreprocessor`/`DialogBoxShowing` anywhere; `execute_python` reports success whenever IronPython does not throw (BCF:4143-4208). Live repro of the too-wide window still needed | failure handling in `CreateTransaction` (BCF:32-37) plus `CommitChecked` returning failed ids and messages | M |
| B-06 | confirmed, by design | `execute_python` is `IsMutating` (BCF:4143), gated by tool name alone (`dispatch.py:35`) | `mode=read`: run inside a `TransactionGroup` that always rolls back, as a separate non-mutating tool | M |
| B-07 | confirmed | `Duct.Create`/`Pipe.Create` with end points only (BCF:2756-2830) | routing tools (3.4) | L |
| B-08 | refuted in source, confirmed in the installed build | the csproj ships `IronPython.StdLib` and `bin/Release/2024/net48/Lib/json/` exists; the installed folder `C:/ProgramData/AECModelBridge/bin/2024/` has no `Lib/` because only the DLL was copied by hand | deploy the whole output folder (B-09) | S |
| B-09 | confirmed | `/health` returns the static assembly version only; no sha, timestamp or path (`BridgeServer.cs:277-284`); `install-addin.ps1` writes the manifest only; installed DLL is 420,352 B vs 432,640 B in the repo build | build stamp in both health endpoints, `scripts/deploy-addin.ps1` mirroring the whole folder and verifying the stamp | S |
| B-10 | confirmed | `create_level` never calls `ViewPlan.Create` (BCF:540-562) | create the plan view in the same transaction | S |
| B-11 | confirmed | `FloorType.FirstOrDefault()` with no `IsFoundationSlab` filter (BCF:468-473); `floor_type` never forwarded | filter and forward | S |
| B-12 | refuted for the add-in | no `Flip` under `src/Bridge`; `Flip` came from the recipes. Real gap: `create_wall` does not orient walls and `wall_type` is dropped by the MCP lambda | `reverse`/`exterior_side` parameter, forward `wall_type` | S |
| B-13 | partial | one transaction per call already; missing fit check, swing control, cut verification; commit unchecked; defaults ("Single-Flush", "0915 x 2134mm") do not exist in most projects | fit check, `CommitChecked`, return volume delta | M |
| B-16 | partial | the plan was wrong: `run_async` and `JobManager` exist (`mcp_server.py:104-130`). The job calls the synchronous `send_tool` inside an async function, blocking the event loop, with the same 30 s x 3 window | `asyncio.to_thread`; poll `/result/{id}` | S |
| B-18 | partial | the lambda forwards 4 args (`revit.py:620-628`); `ZoomType` is always `FitToPage`; no crop, no blank check; a transaction is opened for a "read-only" command | framing, blank flag, `format`/`resolution`, no transaction | M |

B-14, B-15 and B-17 are Revit family/API behaviours and cannot be verified from the add-in source.

**Root causes the plan missed**

1. No failure handling at all: a modal Revit dialog freezes the UI thread and surfaces as a 30 s timeout. One hook in `CreateTransaction` covers 58 call sites.
2. `execute_python` leaks: the engine is shut down only on failure (BCF:4160-4165), so a script that throws mid-transaction can leave it open and break the next call.
3. A DLL-only deploy now disables Python entirely, because `PythonEngineFactory.cs:19-21` throws when `Lib/` is missing instead of degrading.
4. MCP wrappers drop parameters (`wall_type`, `floor_type`, `roof_type`, `slope`, `format`): the same bug repeated five times.
5. Read mode (0.6) must restrict imports and IO, not only roll back: with the StdLib present a no-approval script could import `os` or `subprocess`.
6. Minor: `GetInt32` used for element ids (BCF:750, 2326); `revit.health` carries no add-in build.

**Build order (impact x frequency / effort)**

1. Build stamp in `/health` and `revit.health`, `deploy-addin.ps1`, verification after restart (B-09, B-08). Most sessions were bitten by a stale add-in.
2. `PythonEngineFactory` degrades when `Lib` is missing; engine shut down after every script.
3. Creator defaults and forwarded arguments: roof type, non-foundation floor type, `wall_type`, `floor_type`, `roof_type`, `slope` (B-02, B-11, B-12).
4. `CreateTransaction` failure handling, `CommitChecked`, stranded-transaction cleanup (B-05).
5. Durable results, `GET /result/{id}`, client polling, `asyncio.to_thread` (B-01, B-16).
6. Read mode for `execute_python` with import restrictions (B-06).
7. `create_level` makes a plan view; `export_image` framing, blank flag, args (B-10, B-18, B-03).
8. Door and window fit and cut checks (B-13).
9. `check_clashes` budget; solid mode (B-04).
10. Live acceptance T1, T2, T11 against a scratch document; this also settles the B-05 too-wide-window behaviour.
