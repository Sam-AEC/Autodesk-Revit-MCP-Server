# Villa evaluation: bridge and assistant limitations

Date: 2026-10-13. Live host: Revit 2024, build 24.3.10.22. Document: `R24_2026_HWC_B01_HEIJ_BWK_GEV-IND_TAS - Copy`, modified, non-workshared. The user selected 194 villa elements and flagged 23841924 and 23841925. The stated primary purpose is to discover/document bridge and AI limitations and improve the tool or workflow. This report records the initial audit phase. Later live corrections and newly measured unresolved defects are in the [coding-agent handoff](AI-REVIT-MODELING-HANDOFF.md) and [current-state manifest](villa-coding-agent-state-2026-10-13.json). The villa and MEP remain unfinished.

## Findings and implemented improvements

| ID | Evidence | Observation and impact | Action/status |
|---|---|---|---|
| B01 | MEASURED + source | `revit_get_element_parameters` fails on both flagged fixtures with `Parameter is not a shared parameter.` One ordinary parameter aborts the entire read. | Guard `Parameter.GUID` with `IsShared`; ordinary parameters return a null GUID. Fixed in source; add-in builds and behavioral regression passed. Loaded add-in still needs live acceptance. |
| B02 | MEASURED + source | Parameter exceptions, workspace rejections and approval blocks return readable error text with MCP `isError: false`. Automation may accept failure as success. | Error branches now return `CallToolResult(isError=True)` with structured error kind. Explicit top-level provider failures also fail the MCP response and claimed plan outcome. Successful responses retain their previous text shape. Stdio and unit regression coverage added. |
| B03 | MEASURED + source | `revit_export_image` requested width 1800 and a PNG output path but produced a 150-pixel JPEG in the parent directory. It returned `status: success` and `file_exists: false`. | Fix filename prefix, requested pixel sizing, shaded/wireframe image formats and output artifact detection. Missing/stale/empty artifacts report error. Source/build/behavioral verification complete; live export after reload remains pending. |
| B04 | MEASURED + source | A read-only Python inspection is blocked by the approval gate; tool description wrongly implied reads needed no setup. Dedicated per-element reads retrieved the selection, but required 194 geometry tool calls. | Keep Python gated; clarify description. Add `revit_inspect_elements` to orchestrate bounded existing read commands, with strict runtime/schema validation, endpoint document checks and explicit completeness. It reduces assistant round trips, not underlying Revit requests. |
| B05 | MEASURED | The coding repository is outside the configured bridge export workspace. An export there is correctly rejected; relative mapping also resolved outside the bridge workspace. | Record workspace boundaries and export into an allowed workspace. Do not widen permissions. Reusable workflow requires checking actual artifacts. Workspace discovery/clearer diagnostics remains a follow-up. |
| A01 | MEASURED geometry; cause INFERRED | Four basin envelopes are mostly below the 3.200 m first-floor level although their insertion points match it. Both flagged fixtures have `Elevation from Level = 0`. Level/origin-only acceptance can miss bad family placement. | Add semantic, level-relative geometry and visual checks. Correct mounting elevation requires family-origin/host/transform and design height evidence; no move performed. |
| A02 | MEASURED | Some `Bed04` records have nonzero envelopes but zero reported area/volume. AABB overlaps also occur for beds/cabinets versus walls. | Preserve broad-phase candidates and missing geometry; zero quantities are not proof of no geometry. Solids/mesh fallback and exact collision checks remain future capabilities. |
| A03 | MEASURED inventory | Active-document counts are zero for Ducts, Pipes, Mechanical Equipment, Air Terminals and Electrical Equipment. Electrical Fixtures exist elsewhere (195 total), but none are in the villa selection. | MEP absence is substantiated for these categories; connectivity, sizing and electrical circuits are not verified. Require connector/system evidence before accepting MEP work. |
| A04 | MEASURED tool inventory + source | Dedicated geometry reads expose position/box/quantities but not family host/orientation/transform or connector topology. Dedicated creation of ducts/pipes/conduit does not itself connect or size systems. | Document the capability gap. Use an explicitly approved short audit when deeper Revit API evidence is required; future dedicated readers should provide these fields. No approval bypass added. |
| A05 | UNTESTED design assessment | A tiny exterior image is insufficient evidence for detailed façade quality, circulation, furniture clearance or construction detail. No full-resolution plan/section QA was available in this run. | Define design intent and review exterior, plan and section evidence using the repaired exporter. Do not report architectural refinement as completed. |

The shared-parameter API distinction is documented by [Autodesk's parameter reference](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/333ff41b-e6a7-d959-60bf-c3bfae495581.htm); the live Revit 2024 failure and source inspection identify the bug here. [Autodesk's ExportImage reference](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/b98a3e71-39fa-bf7a-cb3d-591d8b1fcd93.htm) describes the export operation; actual filenames, resolution and file detection were checked separately.

## Spatial evidence

All values below are converted from captured feet with exactly 0.3048 m/ft. First-floor level 23833306 is 3.200 m. Floor 23843041 has an AABB from 2.920 to 3.200 m. AABB intersections do not prove a solid clash or resolve openings.

| Element | Family | Insertion Z, m | Envelope Z, m | Envelope below level, mm |
|---|---|---:|---:|---:|
| 23841924 | `53_BZ_Fontein` | 3.200 | 3.062000–3.210000 | 138.000 |
| 23841925 | `52_BZ_wastafel_60` | 3.200 | 3.018305–3.216276 | 181.695 |
| 23841919 | `52_BZ_wastafel_60` | 3.200 | 3.018305–3.216276 | 181.695 |
| 23841920 | `52_BZ_wastafel_60` | 3.200 | 3.018305–3.216276 | 181.695 |

The below-level fractions are 93.24% and 91.78% of AABB height, respectively; these are not solid-volume percentages. A proposed fix needs the intended mounting/rim height and host/orientation, not a guessed blanket offset. Other candidate pairs include Bed04 23842041 / wall 23839621, Bed04 23842047 and 23842050 / wall 23839861, Bed04 23842053 / wall 23839855, and cabinet 23841903 / exterior wall 23839613. Intentional host overlaps and downward-extending fins were excluded from automatic defect conclusions.

## Local evidence and reproduction

Detailed captures remain in the ignored local directory `artifacts/villa-bridge-audit/`: `baseline.json`, `bridge-observations.json`, `spatial-findings.md`, `analyze_spatial.py` and `villa-before-low-resolution.jpg`. This tracked report preserves the critical measurements; those local artifacts are not included in a checkout. Run the spatial script against the captured baseline to reproduce the screening.

The measured export command was `revit_export_image({view_id:23840425, output_path:"C:/Users/samo3/Documents/AEC Model Bridge/villa-before.png", width:1800})`. The resulting file was `C:/Users/samo3/Documents/AEC Model Bridge - 3D View - AMB_3D Villa.jpg`, 3820 bytes. The response instead named an absent `AMB_3D Villa.png` inside the requested directory. That small artifact was opened and copied into the local evidence folder.

Source changes are in `packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs`, `packages/mcp-server-revit/src/revit_mcp_server/mcp_server.py`, and the Revit provider/inspection helper. Regression coverage is in the MCP tests and add-in behavioral harness. Builds/behavioral tests are OFFLINE evidence, not proof that the running Revit process uses these changes.

Verification: Revit 2024 and 2026 Release builds passed (0 errors; existing warnings remain). The approval/state/stdio suite passed 133 tests, and the integrated inspection/error/metadata/stdio suite passed 87 tests before the additional queued-failure regression. Ruff and diff checks passed. Run the persisted add-in behavior tests with `./scripts/test-addin-behavior.ps1`; they extract the actual production methods and execute them against API stubs. Both groups passed and fail against the original methods with the reproduced defects. They do not replace a live Revit run.

## Live acceptance and next capability priorities

After the rebuilt Revit 2024 add-in is loaded and the MCP server reconnected:

1. Read parameters for both flagged fixtures. Require non-shared `guid: null`, valid shared GUIDs and no aborted read.
2. Export view 23840425 at width 1800 to an allowed PNG filename. Require an existing, nonempty image; inspect its dimensions/format and view contents. Revit may append a view suffix; use the returned actual artifact path.
3. Inspect the four basins in one bounded request with the expected document title and elevation parameter. Require complete requested evidence. Test an absent ID and missing parameter; require an explicit partial result, preserving successful sections.
4. Exercise a blocked Python call and a missing-element read. Require MCP error status; do not relax the gate.
5. Gather family host/transform/connectors and readable sections before preparing a villa repair plan. Model edits still need a person-approved plan.

Highest-value follow-ups are native bounded inspection with stable document identity and raw parameter IDs/values; family host/transform and connectors; selection-scoped rooms/system extraction; mesh-aware exact collision diagnostics; and MEP connection/circuit acceptance. These need dedicated capability work and live regression fixtures rather than adding prompt instructions alone.

The reusable [villa review workflow](workflows/villa-refinement-review.md) establishes the evidence and acceptance steps. No villa model changes, save, restart, approval-mode changes or add-in deployment were performed during this initial audit phase. Subsequent Auto-enabled corrections are documented in the coding-agent handoff; this initial table is not the current model status.
