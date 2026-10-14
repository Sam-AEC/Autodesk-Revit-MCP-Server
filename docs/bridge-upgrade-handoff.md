# Bridge upgrade checkpoint, 14 October 2026

Continue from the owner decisions in [upgrade plan section 13](upgrade-plan-hands-and-eyes.md#13-owner-decisions-2026-10-14-and-resulting-priorities), using [the preflight and verification prompt](prompts/revit-agent-preflight-and-verify.md) for live work. DWG/PDF modelling and the Villa 2 stair/roof work are parked. The current priority is bridge software.

## Starting point

The takeover began on clean branch `dev` at `8ebf005`, after the jobs and trust ports. Those commits cover durable results, context, asynchronous jobs, Python read mode, geometry checks, complete-folder deployment and in-flight approval handling. They do not prove the installed add-in supports those changes.

Claude also left unfinished implementations in `C:/tmp/wt-qa` and `C:/tmp/wt-docs`. Their QA and documentation files were copied into the active checkout and hardened; both original worktrees were preserved. `C:/tmp/wt-dev` was clean at the starting commit.

## Current source changes

- Explicit person-operated Dev mode in Settings, mode chip and chat banner, with shared persistent state, signed records, trusted revocation, audit logging and strict supplied-plan checks. See [ADR 0018](0018-explicit-development-mode.md). Optional extra-folder access and path-masking relaxation remain unimplemented.
- Recovered read-only opening/roof audits, family probe, MEP system report, naming/parameter checks, level/grid checks and `revit_review`. Fixed missing helper injection, missing scopes, silent limits and false PASS results for empty or incomplete checks. Added generated-script and behavioral regressions using a Revit API stub.
- Recovered documentation tools for listing views/sheets/schedules, rendering checks, creating views/sheets/schedules and PDF/DWG/IFC/NWC export. Replacements check the complete deletion cascade; generated writes use the outer approved action through a scoped execution capability. Export and image-analysis failures must remain explicit.
- Plan execution now records provider-reported failure without requiring an exception, retains running receipts and single-use claims, and withholds a success proof while results remain pending. Repeated execution cannot turn a pending action into a completed one.

These are source changes, not a release or a verified live BIM workflow. `revit_review` does not inspect rendered pictures; the prompt's visual review remains a separate requirement. Stub tests verify control flow and arithmetic, not actual Revit geometry or engineering sizing.

## Verification

The full suite passed: **1,752 passed, 17 skipped, zero failures**, in 584.63 seconds, with Edge enabled for the panel browser checks.
The skips cover live Revit acceptance, platform-specific permission/symlink cases and disconnected providers.
The Revit 2024 Release build passed with zero errors and 111 compiler warnings. Ruff, version consistency and diff checks passed.
The separate Edge panel suite passed 204 tests. Independent source review found no remaining blockers after fixing stale nested
capabilities, Dev authorization races and test-fixture isolation. Logs, JUnit results and the DLL fingerprint are saved under
`artifacts/bridge-upgrade-verification/` (`pytest.log`, `pytest.xml`, `build.json`). Live-model acceptance remains pending.

## Revit 2024 installation

After the owner closed Revit, the complete build was installed to `C:/ProgramData/AECModelBridge/bin/2024`.
All 557 deployed files were checked by SHA-256 against the build, and the per-user Revit 2024 manifest points to its DLL.
The bundled Python companion server was updated from the new wheel to include Dev mode and the documentation module;
`pip check` reports no broken requirements. The development environment retains its editable checkout and now reports version 1.4.0.
The previous add-in and server package were backed up under `C:/ProgramData/AECModelBridge/backup`.
After Revit reopened, the authenticated panel backend's `revit_get_context` verified process `49464` (bridge port `53712`):
Revit 2024 build `24.3.10.22`, add-in and companion server version `1.4.0`, matching assembly file time,
`addin_supports_context: true`, `dev_mode: true`, an idle queue and no context warnings.
The live response is saved in `artifacts/bridge-upgrade-verification/live-context.json`.
The chat's older MCP process still targets the previous session and needs reconnection; the installed panel backend routes correctly.
No model content was changed. Mutating acceptance remains pending on a requested scratch-model run.

<<<<<<< HEAD
Read-only native checks then exercised the runtime, joins, naming, openings, roofs, family probing, MEP and documentation inventory.
They found an IronPython family-symbol name bug, which was fixed, regression-tested, installed and verified with shallow/deep family
probes. Element/warning counts stayed unchanged. See [the live validation report](revit-addin-live-validation-2026-10-14.md) for measured
results, actual quirks and the distinction between model findings and tool bugs.

=======
>>>>>>> 111456fed602efdfa73cca934189fba8bd3f019f
## Development scope

The villa recipes are integration-test evidence, not the bridge development roadmap. Keep future villa-specific work in test
fixtures and verification records; group related test changes with the reusable tool feature they validate. Do not add standalone
villa-refinement commits by default. Historical villa commits also contain reusable review/runtime changes, so shared history remains intact.

## Live state observed at takeover

`revit_health` answered for Revit 2024, build `24.3.10.22`, document `R24_2026_HWC_B01_HEIJ_BWK_GEV-IND_TAS - Copy`, with unsaved model changes. `revit_get_context` reported `addin_supports_context: false`: the loaded add-in lacks `revit.get_context` and is older than the repository. The live server reported `1.2.1`; the add-in reported `1.4.0.0`. No live settings or model content were changed during this takeover.

## Next steps

1. Reconnect the chat's old MCP process before using its Revit tools. The installed panel backend and loaded Revit 2024 build are verified; [deploy-addin.ps1](../scripts/deploy-addin.ps1) can repeat the add-in deployment after Revit is closed.
2. Run mutating acceptance only when requested, on an owner-opened scratch project. Upgrade plan section 13 excludes the open Heijmans copy.
3. Continue shared transaction failure handling (`CommitChecked`, structured Revit messages and `on_error`), creator argument forwarding/defaults and plan-view creation. These remain outstanding.
4. Validate the recovered QA/documentation tools against live Revit, then continue MEP/family creation and routing. Native connector topology checks do not replace design or sizing checks.

Before saying a live phase is complete, require measured checks, independently reviewed evidence and inspected images as prescribed by the prompt. Report an old add-in or unavailable check as UNVERIFIED.
