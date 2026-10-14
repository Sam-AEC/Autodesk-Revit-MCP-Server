# Changelog

## Unreleased

- Docs: add `docs/upgrade-plan-hands-and-eyes.md` (phased upgrade and bug-fix plan with a bug list B-01..B-18 and a live acceptance suite; plan only, nothing implemented) and `docs/prompts/revit-agent-preflight-and-verify.md` (copy-paste pre-flight and verification prompt for AI building in live Revit).
- Security: the panel now shows a plan's hashed review block (summary, reasoning, citations, assumptions, excluded elements, warnings, conflicts, reverted plan id) in the Plans view, built on demand, and says which parts the approval hash covers. Review text is untrusted and shown as plain text only. The panel hub adds a validated `review_view` to `list_pending_plans` results on the panel route only, sorts plans newest first and sends at most 50. Every card shows the plan id and a copyable `aec-model-bridge-approve show <plan id>` command. Approve is disabled, with a pointer to that command, for a hash_version 2 plan whose review is missing, malformed or not yet opened, for legacy revert plans with content outside the hash, for numbers above 2^53, for lists over 100 entries, and for plans holding a real credential (password, API key, bearer value, high-entropy token), which the panel masks. Paths, `code` arguments, parameter names such as `Assembly Code` and ordinary prose are shown as they are on the approval card; other routes keep their full redaction. NaN and Infinity are refused at drafting. Reject still works. Not verified in a live Revit panel.
- Security: a person can now recover a plan stuck by a crashed process. `aec-model-bridge-approve recover <plan_id> --reason ...` marks actions left in `running` as `abandoned` (never re-run, the approved plan becomes `partial`, remaining actions need a new plan); `show` lists running actions with their age. It is not an MCP tool and nothing recovers automatically. Plan writes retry `os.replace` up to 5 times on a Windows `PermissionError` before failing with a clear error (UNVERIFIED on Windows). `docs/security.md` lists the remaining gaps and ADR 0017 (Proposed) covers document binding and expiry; no behaviour change for those.
- Brand: adopt the text-free Ember mesh mark (three jackal heads in an ouroboros ring) in `assets/`, the installer wizard images, `icon.ico`, the VS Code extension icon and all READMEs; add `assets/social-preview.png` and `docs/design/brand.md`. The social preview image must still be set by hand in repository Settings.
- Brand: add the Cerberus sub-mark artwork (Ember mesh: three jackal heads in an ouroboros ring) under `assets/cerberus/` for the Cerberus feature, and rewrite `docs/design/brand.md` to separate the product brand (AEC Model Bridge, Pier mark) from the feature sub-mark. The product mark, installer images, icons and READMEs keep the Pier mark.
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
