# Changelog

## Unreleased

- Fixed from a 1.4.0 user report (Revit 2027.2, Windows on ARM): `revit_set_parameter_value` and every other native write froze Revit because the transaction helper called itself (fixed earlier in 189e25a, first release 1.5.0); `revit.get_sheet_info` failed on sheets that carry two parameters with the same name (for example "Category"), now the second one is listed as "Category (2)"; a force-closed Revit leaves `revit-<pid>.json` behind, the add-in now removes entries of dead processes when it starts; `config\default.json` no longer carries the build machine's profile path (`%USERPROFILE%` is written literally).
- Scripts: `revit_execute_python` in write mode gets `amb_transaction(doc, name)`; it dismisses Revit warnings (no dialog) and returns them in the result, errors roll back. stdout without a trailing newline is now flushed on IronPython 3 (the tail was dropped). UNVERIFIED in Revit. Removed two unreferenced files (`new_checks.txt`, `banner.png`).
- Panel: the dark theme uses the slate colours of Revit's own dark UI (#3B4453 background, #222933 headers, #515C6B lines, measured from Revit 2024) instead of the near-black blue (`docs/design/tokens.md` updated, dialogs match; status colours lightened to keep WCAG AA).

## 1.5.0 - 2026-10-14

Status: on the dev branch, not yet released.

- Recipes: new `revit_recipes` module (`revit_recipe_save`, `_list`, `_get`, `_run`, `_delete`). A recipe is saved IronPython with a typed parameter schema and a code hash. A write run needs a plan bound to the recipe id, version, code hash and parameter values, so editing a recipe voids old approvals. A read recipe runs without approval only if its code passes read mode at run time. A recipe can carry a standing approval, set only by a person with `aec-model-bridge-approve recipe-standing`, tied to id and hash. Parameters reach the script as one JSON string, never spliced into code. UNVERIFIED in Revit.
- Documentation batch: `revit_place_views`, `revit_list_view_templates`, `revit_set_view_templates`, `revit_make_view_template`, `revit_align_crop`, `revit_list_revisions`, `revit_add_revision`, `revit_add_revision_clouds`, `revit_issue_revision`, `revit_sheet_index` and `revit_update_sheets` (collision check, temporary numbers for swaps). Strict schemas, `dry_run` on every write. UNVERIFIED in Revit.
- Sparing: status flow (`revit_sparing_status_get`, `_summary`, `_set` with a transition table, `_setup` for the shared parameter, only through an approved plan) and copy to discipline models (`revit_sparing_export_spec`, `revit_sparing_place_spec`, active document only). UNVERIFIED in Revit.
- MEP hangers: `revit_mep_hanger_plan` (read) and `revit_mep_hanger_place` (gated, `dry_run`, idempotent). The spacing table ships empty; a rule without a named source is never used, and results carry the not-an-engineering-calculation notice. UNVERIFIED in Revit.
- Cleanup: new read-only `revit_cleanup_audit` (11 checks, scope by model, categories or view, time budget, `purge_candidates` as a separate field). It deletes nothing. UNVERIFIED in Revit.
- Tests and reach: a C# xUnit project (`packages/revit-bridge-addin-tests`, 145 tests, runs in CI, no Revit needed); one tool count (302, `scripts/count_tools.py`, checked by a test); `aec-model-bridge --help` no longer starts the server; PyPI classifiers and `__version__`; demo shot list under `scripts/demo/`. Nothing is published.
- Fixed after the first live run (Revit 2024): door and window results returned the host wall as `element_id`; replacing a view or an MEP route failed on the camera, section box, nested fitting parts and centre lines Revit makes itself; a rerun of a route failed with NO_FREE_CONNECTOR because the piping system counted as a connection; a tee split made the system report flag a planned free end; 3D views are now cropped to their scope (before, an export was a speck on a blank page); the door/window fit check measured sill height as distance from the wall.
- Security: read mode could be bypassed by building the name `Transaction` at run time (`getattr(DB, 'Trans' + 'action')`), which changed a wall parameter without approval. Read-mode scripts now run inside a transaction group that is always rolled back, and the result says so. Revit rolling back a committed inner transaction was confirmed live; the runner change itself is UNVERIFIED until the rebuilt add-in is loaded.

- Dry run: every write tool of the docs, family and MEP modules takes `dry_run`. It does the work and the checks, then always rolls the group back and reports `would_change`; it writes no file and loads nothing. Still approval-gated like a real write.
- Parameters: new `revit_get_parameters` (read-only) and `revit_set_parameters` (approval-gated, up to 500 elements, explicit units, never creates parameters, refuses read-only and critical ones with a reason per element, reads every value back and returns a `revert` list). UNVERIFIED in Revit.

- API lookup: new read-only `revit_api_lookup` answers whether a Revit API type or member exists, with its signature and the nearest real names when it does not, from the documentation XML that ships with Revit (2024 to 2027) or the NuGet cache. No Revit needed. Agents should check unfamiliar members with it before writing a script.
- IFC: new read-only `revit_ifc_check` compares an exported IFC with the live model per category (counts, missing elements, classification, materials, storeys, expected parameters, origin offset). It is never PASS when the Revit side was truncated or the IFC could not be read; `ifc_only` checks the file alone. UNVERIFIED in Revit.
- Openings: new `revit_sparing_find` (read-only: where MEP crosses walls and floors, in linked models too, with a suggested size and any existing opening) and `revit_sparing_place` (approval-gated: places a loaded sparing family or a native opening, tagged and idempotent, with `dry_run`). UNVERIFIED in Revit.

- **Breaking:** the old creators were hardened in place. `revit_create_wall` takes `wall_type` and `reverse` (flip the exterior side) and uses the default basic wall type when none is given. `revit_create_floor` forwards `floor_type` and no longer defaults to a foundation slab. `revit_create_roof` forwards `roof_type` (it used to pass none, so Revit refused) and `slope` (rise over run; omitted means flat; the old hidden default of 0.5 was never applied and is gone). `revit_create_level` also creates the floor plan view unless `create_plan_view` is false. An unknown type name now fails instead of falling back. Not yet run in Revit.
- Transactions: native add-in commands commit through a checked transaction. Revit warnings are dismissed and listed; an error rolls the call back and returns `ok: false` with Revit's message, the failing element ids and the transaction status, instead of an opaque error or a stuck dialog. Live repro on the old build (2400 mm window in a 1 m wall) showed the dialog and a message-less error.
- Doors and windows: placement checks that the opening fits the host wall before any transaction starts and refuses with the wall id and the numbers; picks the first loaded door or window type when none is named and says which; `hand_flipped` and `facing_flipped` control the swing; the result carries `host_wall_id` and `fit_check`. `revit_check_clashes` gets `max_pairs` and `time_budget_s` and reports `truncated` instead of freezing Revit. Not yet run in Revit.
- MEP: new `revit_mep` module with `revit_mep_route` (pipe or duct with fittings, branches, risers), `revit_mep_connect`, `revit_mep_circuit` and the read-only `revit_mep_check_elements`. A category guard refuses a family whose category, connectors or system domain do not match. Write tools are approval-gated, roll back by default (`on_error=skip` keeps what worked) and finish with a system report. UNVERIFIED in Revit.
- Families: new `revit_make_family` builds loadable families from data specs (the `docs/recipes/villa2/m1_specs.json` format), checks the category against the port kinds, saves and loads them, and runs the family probe. Approval-gated, UNVERIFIED in Revit.

- Live verification: exercised the new Revit 2024 add-in's read-only runtime and QA/documentation tools. Fixed the family probe's IronPython `FamilySymbol.Name` failure with parameter-first name access and explicit unverified fallbacks; added six regressions and verified shallow/deep native probes after installing the corrected wheel. See `docs/revit-addin-live-validation-2026-10-14.md` for measured results, the stale-chat-routing issue and remaining scratch-model acceptance.
- Panel: add explicit Dev mode, confirmed in Settings and visible in the mode chip and chat banner. A signed workspace switch keeps it on until the person switches it off, including across restarts; an owner-only nonce authority prevents a revoked signed record from re-enabling it. Ask first clears it and timed Auto replaces it. Look only remains enforced, supplied plan ids retain hash/single-use checks, and Dev calls and toggles are audited. Workspace sandbox and secret/path redaction remain enforced. See ADR 0018. Revit 2024 read-only smoke checks observed Dev active; mutating scratch-model acceptance remains pending.
- QA/QC: recover the unfinished opening/roof audits, family probe, MEP system report, naming/parameter and level/grid checks, plus `revit_review`. Generated scripts now load their shared helpers. Missing scopes, empty checks, unreadable geometry and budget limits cannot produce a verified PASS. Added behavioral tests using a Revit API stub; bounded native read checks are recorded in `docs/revit-addin-live-validation-2026-10-14.md`; complete geometry acceptance remains pending.
- Documentation: recover view/sheet/schedule creation and listing, PNG content checks, and PDF/DWG/IFC/NWC export. Generated writes use one outer approved action through an execution capability bound to that exact call; stale executors are refused. Replacement checks the complete deletion cascade and rolls back foreign dependencies. Exports stage actual filenames before publishing and guard split outputs/sidecars against overwrite. Corrupt or unsupported PNGs remain unverified, and decompression is bounded. The corrected server wheel is installed; live creation, layout and export acceptance are pending.
- Plans: `execute_plan` now honors provider-reported failures and retains running receipts instead of marking them complete. Pending actions remain consumed and have no success proof; repeated execution cannot turn them into completed actions.
- Security: a mutating call that comes back `running` (Revit still working, `{status: "running", request_id}`) is no longer booked as done. The approval claim stays consumed (no replay), the action stays `running` and is recorded as in flight under `plans/.inflight/<request_id>.json`, which survives a server restart, and the reply says "still running, resume with revit_get_result". `revit_get_result` (or `revit_job_status` for `revit_run_job`) closes it: a final result marks it `executed`, Revit's own failure marks it `failed` with Revit's message; a lost connection or an expired id leaves it `running` for `aec-model-bridge-approve recover`. Applies to MCP calls, `run_async` jobs, the panel route and module steps. A `revit_run_job` that is still queued or running is held open the same way (before, it was booked done at once).
- `revit_get_context` now reports the approval mode in force right now, including the signed temporary Auto window from the panel (`server.approval_mode`, `configured_approval_mode`, `auto_expires_at`), not only the mode the server started with.
- Deploy: new `scripts/deploy-addin.ps1` mirrors the whole add-in output folder, including `Lib\`, to `C:\ProgramData\AECModelBridge\bin\<year>\`, refuses to run while Revit.exe is running (unless `-Force`), backs up the previous folder, and verifies the DLL size and file time afterwards (restoring the backup on a mismatch). Python scripts: a missing `Lib\` no longer disables `revit_execute_python`; the engine starts without the standard library and the result says so. The engine runtime is shut down after every script, and a script that leaves a transaction started is rolled back and reported (`transaction_left_open`). The complete Revit 2024 deployment and packaged IronPython standard library were verified live; open-transaction and missing-library acceptance remain pending.
- Docs: add `docs/upgrade-plan-hands-and-eyes.md` (phased upgrade and bug-fix plan with a bug list B-01..B-18, owner priorities, source implementation status and a live acceptance suite) and `docs/prompts/revit-agent-preflight-and-verify.md` (copy-paste pre-flight and verification prompt for AI building in live Revit).
- Security: the panel now shows a plan's hashed review block (summary, reasoning, citations, assumptions, excluded elements, warnings, conflicts, reverted plan id) in the Plans view, built on demand, and says which parts the approval hash covers. Review text is untrusted and shown as plain text only. The panel hub adds a validated `review_view` to `list_pending_plans` results on the panel route only, sorts plans newest first and sends at most 50. Every card shows the plan id and a copyable `aec-model-bridge-approve show <plan id>` command. Approve is disabled, with a pointer to that command, for a hash_version 2 plan whose review is missing, malformed or not yet opened, for legacy revert plans with content outside the hash, for numbers above 2^53, for lists over 100 entries, and for plans holding a real credential (password, API key, bearer value, high-entropy token), which the panel masks. Paths, `code` arguments, parameter names such as `Assembly Code` and ordinary prose are shown as they are on the approval card; other routes keep their full redaction. NaN and Infinity are refused at drafting. Reject still works. Not verified in a live Revit panel.
- Security: a person can now recover a plan stuck by a crashed process. `aec-model-bridge-approve recover <plan_id> --reason ...` marks actions left in `running` as `abandoned` (never re-run, the approved plan becomes `partial`, remaining actions need a new plan); `show` lists running actions with their age. It is not an MCP tool and nothing recovers automatically. Plan writes retry `os.replace` up to 5 times on a Windows `PermissionError` before failing with a clear error (UNVERIFIED on Windows). `docs/security.md` lists the remaining gaps and ADR 0017 (Proposed) covers document binding and expiry; no behaviour change for those.
- Brand: add the Cerberus sub-mark artwork (Ember mesh: three jackal heads in an ouroboros ring) under `assets/cerberus/` for the Cerberus feature, and rewrite `docs/design/brand.md` to separate the product brand (AEC Model Bridge, Pier mark) from the feature sub-mark. The product mark, installer images, icons and READMEs keep the Pier mark. Setting the repository social preview in Settings remains a manual step.
- Security: log and error redaction now also covers UNC network paths (`\\server\share\model.rvt`, the usual way central models are shared) and backslash paths without a drive letter. Before, a server or share name could appear in audit logs and error messages. This also fixes `test_redaction_in_server` on Linux.


## 1.4.0 - 2026-10-09

- Release: every stable release now also attaches a double-click Windows installer, `AECModelBridge-Setup-<version>.exe` (listed in `SHA256SUMS.txt`). It picks the installed Revit years, needs no admin rights, can set up Claude Desktop and VS Code (with a backup first) and uninstalls cleanly. The release workflow builds it with Inno Setup, smoke-tests a silent install, upgrade, failure and uninstall, and has a new `dry_run` input that builds everything without publishing. The old `AECModelBridge.iss` copied the package onto itself, always installed every year and ran the client setup without asking; it was reworked. `configure-mcp-clients.ps1` now backs up each config, writes UTF-8 and leaves a commented VS Code `settings.json` alone.
- VS Code: add the local MCP extension, connection status, mock mode and Revit year selection. Correct local-host execution, settings overrides and auto-approval warnings; add provider/command regression tests. Marketplace publishing and live app verification remain pending.
- Release: build and test the VS Code package before attaching its `.vsix` to future GitHub releases, include it in checksums, and synchronize extension manifest and lockfile versions.
- README: lead with BIM coordinator workflows, simplify badges and licensing text, remove endorsement boilerplate and ecosystem artwork, and use local paths for technical diagrams. Document the snapshot handoff limitation and coordinator adoption priorities.
- Design: add a Claude Design brief for README artwork, workflow images, a social preview and a synthetic-model demo cover.
- Release audit: the MIT-licensed 0.1.x and 1.0.x releases and v1.1.0 (whose LICENSE file was PolyForm Small Business, contradicting the docs) were withdrawn from GitHub releases together with their tags. `docs/release-retirement.md` records the inventory of the releases that remain (all GPL-3.0-or-later) and the procedure for future retirements.
- Dependabot: security updates are grouped into one pull request per ecosystem instead of one per package. The pinned lock-file versions of `ujson`, `anyio`, `starlette`, `cryptography`, `pydantic-settings` and `mcp` were refreshed after testing them together.
- Dependabot: routine updates are now monthly and grouped into one pull request for Python and one for GitHub Actions; routine .NET package PRs are off (the add-in dependencies are pinned on purpose). Security updates are unaffected.
- Security: update `System.Text.Json` from 8.0.0 to the patched 8.0.5 in the Rhino, Navisworks and Power BI projects (clears the NU1903 advisories).
- Dependabot: leave `mcp` and `specklepy` majors, IronPython majors and the pinned WebView2 alone, so it cannot propose changes that would break installs or Revit scripting.


## 1.3.3 - 2026-10-09

- Repo: add issue forms, a pull request template, a Code of Conduct, Dependabot config, `CITATION.cff` and `docs/README.md` (a one-line index of every doc); move the Hermes Desktop example to `docs/examples/hermes-desktop.json`; extend `.gitignore` and `.gitattributes`.
- Docs: the README diagrams are now images (light and dark, absolute URLs) so they show on directory sites that mirror the README but do not run Mermaid. The Mermaid sources live in `docs/diagrams/` and `scripts/render_diagrams.py` regenerates the PNGs.
- Fix upgrade: `install.ps1` now removes the previous server package before copying the bundled Python, so old `aec_model_bridge-<version>.dist-info` folders no longer make the installed server report an old version.


## 1.3.2 - 2026-10-09

- Release: the MCP Registry publish now starts automatically after each stable release and reads the version from `VERSION`, so the bundle hash is no longer left stale.
- Fix install: `mcp` is now pinned `>=1.10,<2`. An unpinned install on Python 3.12+ resolved mcp 2.x, which removed the `Server.list_tools()` decorators this server uses, so the server crashed at import. `uv.lock` was also stale (missing `anthropic`) and is refreshed.
- Fix packaging: module manifests, QA/QC rules and recipes were missing from the wheel, so a pip or uvx install lacked the 34 module tools. They are now package data.
- Tools: every tool now lists a full description, a described input schema, a title and MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`), derived from the existing approval-gate flags. The server reports its own version and usage instructions at initialize. No tool behaviour changed.
- Mock mode: tools backed by a legacy handler (for example `revit_health`) no longer fail with a missing `request_id`, so directories can call them without Revit.
- Directories: add a root `Dockerfile` (mock mode), `glama.json` and `smithery.yaml` so listing sites can build and introspect the server without Revit. README gains a quick start, a tool table and a demo placeholder; `server.json` and `manifest.json` document more environment variables and keywords.


## 1.3.1 - 2026-10-09

- Release: every GitHub release now ships one ready-to-install package per supported Revit year (`aec-model-bridge-revit-2024-X.Y.Z.zip` through `-2027-`). 1.3.0 only shipped the Revit 2027 package. `build-release.ps1` defaults to all years, and the release workflow installs the .NET 8 SDK that the 2024-2026 builds need.
- Build scripts: `install.ps1` read a stale `1.1.0` default and now takes its version from `VERSION`.

## 1.3.0 - 2026-10-09

- Versioning: the root `VERSION` file is now the single source of truth (SemVer). `scripts/version.py` checks and sets the version across every manifest, CI fails on drift, and pushing a `vX.Y.Z` tag builds the GitHub release with notes taken from this changelog. See `docs/versioning.md`.
- Docs: README rewritten for readers and search (plain-language intro, install and connect guides, FAQ, release pointers). Architecture, approval and ADR 0008 diagrams redrawn with a colour scheme that stays legible in light and dark mode.
- Fix CI: the IFC provider could not find elements whose `GlobalId` is malformed (for example 24 characters instead of 22) once `ifcopenshell` 0.9 started resolving GUIDs through a validated index, which failed `test_ifc_provider_tools` on Python 3.11. Lookup now falls back to scanning `IfcRoot` and no longer crashes on an unknown Express ID.
- Ribbon: Workflows and Tools now use one large button plus stacked 16 px buttons, every button gets the brand tooltip image and F1 help, and icons redraw live when Revit's theme changes.
- Dialogs: semantic vector status glyphs replace emoji, link/panel errors use the branded dialog instead of native MessageBox/TaskDialog, and the dialog window carries the app icon.
- Panel: empty states and assistant messages carry icons, nav exposes `aria-current`.
- Add `assets/icon.ico`, `assets/logo-mark-512.png`, Inno Setup wizard images and `scripts/make_brand_assets.py`; the MCP registry icon now points at the square mark.

- Unify the side panel and popup dialogs on one design: the panel gets an icon rail (same icon language as the ribbon) with labels, a view-icon header and primary/secondary buttons; dialogs now use the panel's colour tokens, a dark header with a teal rule and the Pier mark, vector status glyphs instead of emoji, and the same card and button shapes.
- Replace the Span brand mark with the Pier mark: an isometric model cube with a bridge arch through each face, on a dark app tile. Applied to `assets/logo.svg` (new `assets/logo-mark.svg`), the panel rail, the dialog header, the About/status brand card, the ribbon brand icon and the Power BI tool icon.
- Redraw all ribbon icons in the Autodesk-style flat grammar: 32 px grid, charcoal outline, light teal fill, one teal accent and a state badge (green run/pass, red stop, amber waiting). Adds an About icon.


## 1.2.1 - 2026-09-23

- Add the Plugin Module Registry with discovery, I/O verification, and validate/on_result hooks.
- Add the Semantic BIM Data Layer: snapshot/delta models, a DSL query engine, a diff engine, and three-way conflict reconciliation.
- Add the Model Inspector, Selection Tools, Parameter Manager, FamilyType Mapper, QA/QC Checker (13-rule engine), Report Generator, and Recipe Runner modules.
- Add ApprovalGate middleware and ActionPlan tools across all providers, and named transactions with action_id, DocumentDirtyTracker, and snapshot delta commands.
- Rewrite the dockable WebView2 panel to run on real hub tools instead of fixture data, and migrate its CSS/HTML/JS to the amb-* design token system with live Revit theme sync.
- Add a native Anthropic tool-calling chat loop in the panel, alongside the existing Codex CLI path.
- Add multi-Revit-version host switching support.
- Introduce the Span brand mark, palette, and icon grammar across the Revit ribbon and panel.
- Add a double-click Windows installer with bundled Python, MCP client configuration, and a WebView2 preflight check.
- Build rhino-bridge-addin in CI for the first time, and stop letting Navisworks' unbuildable-in-CI status fail the whole addin matrix.
- Close approval-gate coverage gaps across all providers, fix a silent rollback no-op, and stop swallowing workspace-sandbox violations.
- Catch prefixed secret keys/values in data redaction, and fix a codex CLI argument-injection issue via dash-prefixed chat messages.
- Fix a WebView2 Access-Denied panel issue and downgrade WebView2 to resolve DLL conflicts on Revit 2027.
- Remove internal planning docs, AI-agent instruction files, personal-machine paths, orphaned scratch scripts, and stale build artifacts from the public repo.

## 1.2.0 - 2026-06-13

- Implement Phase B Switch Contract v2 with ADR 0002 specification.
- Add hub discovery registry reader and bearer-token client with legacy fallback.
- Enhance Revit add-in with Contract v2 runtime, token generation, and capability manifest generation via reflection.
- Introduce Navisworks command routing infrastructure with attribute-based registry.
- Establish baseline hub performance posture with ADR 0007.
- Add parameterized provider contract tests and automated tool catalog generation.
- Implement SQLiteExporterProvider for local database exports and graph mapping.
- Add multi-provider integration, persistent background event loop, and data redaction.
- Perform repository hygiene by removing obsolete agent task files and temporary branches.

## 1.1.0 - 2026-06-11

- Rewrite the README as a shorter product and installation guide.
- Standardize public badges on the Shields.io `flat-square` style.
- Remove the custom download dashboard and repository-owned metric assets.
- Clarify installation for Revit 2024, 2025, 2026, and 2027.
- Adopt a GPL-3.0-or-later and commercial dual-licensing model for version
  1.1.0 and later, with a narrow Revit linking exception.
- Add 16x16 and 32x32 theme-aware ribbon icons and maintainer profile links
  to the Revit Help and About dialogs.
- Preserve the MIT terms and notices for version 1.0.2 and earlier.

## 1.0.2 - 2026-06-11

- Replace the external star-history chart with repository-owned release-download tracking.
- Add daily total, 7-day, and 30-day download badges with a generated download chart.
- Upgrade the MCPB manifest to the portable `uv` runtime format with guided workspace configuration.
- Add verified repository, GitHub profile, issue tracker, and LinkedIn links to the Revit UI.
- Replace unsupported UI claims with the actual 100 MCP tools and 103 active bridge routes.
- Add an About ribbon command and refine the theme-aware status, help, and configuration dialogs.
- Add continuous Python tests and Revit 2024-2027 add-in builds.
- Correct installer paths, runtime environment names, packaged wheel instructions, and stale documentation links.
- Install add-in binaries by Revit year and remove duplicate legacy manifests so supported versions can coexist.

## 1.0.1 - 2026-06-11

- Add Autodesk Revit 2027 support targeting .NET 10.
- Fix Revit startup failure when ribbon icon files are missing.
- Package all runtime dependencies required by the Revit add-in.
- Align MCP and bridge tool discovery with active implementations.
- Add live download and repository-growth metrics to the README.
- Add reproducible GitHub release packaging and publication automation.
- Rename the public product to AEC Model Bridge and add trademark/API compliance notices.
- Remove Autodesk product artwork and verify release packages exclude Autodesk API assemblies.

## 1.0.0 - 2026-05-27

- Initial 1.0 release.
