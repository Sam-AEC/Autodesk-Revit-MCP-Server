# Documentation index

Status: on the dev branch, not yet released.

Start with the [installation guide](install.md). The main [README](../README.md) covers what the project is and how to connect a client.

## Guides and reference

- [install.md](install.md): install the Revit add-in and the MCP server.
- [first-check.md](first-check.md): from install to ready, using the panel's Setup check card.
- [VS Code extension](../extensions/vscode/README.md): build and install the extension locally.
- [configuration-reference.md](configuration-reference.md): environment variables, package metadata and runtime settings.
- [tools-generated.md](tools-generated.md): the tool catalog, generated from the server (do not edit by hand).
- [rule-packs.md](rule-packs.md): write, validate, import and share QA/QC rule packs.
- [security.md](security.md): trust boundaries, workspace sandboxing and enterprise hardening.
- [logging-and-audit.md](logging-and-audit.md): Python-side audit log and add-in logging.
- [marketplaces.md](marketplaces.md): MCP Registry, Claude Code plugin, extension stores and client distribution.
- [privacy.md](privacy.md): what stays on your computer, what leaves it, and how to delete it (draft, awaiting owner sign-off).
- Client setup guides (snippets not yet tested on live installs): [Visual Studio](clients/visual-studio.md), [JetBrains](clients/jetbrains.md), [Codex](clients/codex.md), [Gemini CLI](clients/gemini-cli.md), [Windsurf](clients/windsurf.md), [Cline](clients/cline.md).
- [versioning.md](versioning.md): version numbers, release tags and release assets.
- [clash-triage.md](clash-triage.md): read-only matching of Navisworks clashes to Revit elements, with a confidence label (unverified on live projects).
- [roadmap.md](roadmap.md): coordinator workflows, demo scope and the next fixes.
- [revit-mcp-behaviour-and-improvements.md](revit-mcp-behaviour-and-improvements.md): measured bridge behaviour, Revit traps and ranked improvements.
- [upgrade-plan-hands-and-eyes.md](upgrade-plan-hands-and-eyes.md): phased bridge upgrade and remaining acceptance work.
- [prompts/revit-agent-preflight-and-verify.md](prompts/revit-agent-preflight-and-verify.md): preflight and verification checks for live Revit work.
- [bridge-upgrade-handoff.md](bridge-upgrade-handoff.md): implemented Dev mode, QA and documentation changes with build and test evidence.
- [revit-addin-live-validation-2026-10-14.md](revit-addin-live-validation-2026-10-14.md): bounded Revit 2024 read-only checks; mutating acceptance remains pending.
- [demo-runbook.md](demo-runbook.md): step-by-step script for the missing-door-Mark demo, with expected counts and a rejected-plan run.

## For contributors

- [module-authoring.md](module-authoring.md): write a plugin module (commands, schemas, QA rules).
- [build-and-install-scripts.md](build-and-install-scripts.md): what each script in `scripts/` does.
- [target-frameworks-and-dependencies.md](target-frameworks-and-dependencies.md): Python and .NET targets per component.
- [revit-addin-lifecycle.md](revit-addin-lifecycle.md): how the Revit add-in starts up and runs commands.
- [design/tokens.md](design/tokens.md): design tokens for the add-in and panel UI ([design/review.html](design/review.html) is the visual review page).
- [design/readme-visuals/README.md](design/readme-visuals/README.md): README artwork sources, rendering and demo assets.
- [release-checklist.md](release-checklist.md): ordered ship-ready checklist, what CI proves and what still needs a live Revit.
- [release-retirement.md](release-retirement.md): reviewed release inventory and future cleanup procedure.
- [examples/hermes-desktop.json](examples/hermes-desktop.json): sample client config for Hermes Desktop.

## Architecture decision records

- [0001](0001-multi-provider-architecture.md): multi-provider automation architecture.
- [0002](0002-switch-contract-v2.md): switch contract v2.
- [0007](0007-hub-performance-posture.md): hub performance posture.
- [0008](0008-approval-gate-lifecycle.md): approval gate and action plan lifecycle.
- [0009](0009-plugin-module-system.md): plugin module system.
- [0010](0010-snapshot-schema.md): semantic BIM snapshot and delta schema.
- [0011](0011-panel-architecture.md): WebView2 dockable panel and hub message bridge.
- [0012](0012-native-agent-chat-backend.md): native tool-calling loop for chat.
- [0013](0013-automation-engines.md): proposal for running Dynamo, pyRevit and Python automation behind the approval gate.
- [0014](0014-multi-revit-routing.md): proposal for routing to the right Revit when several are open.
- [0015](0015-navisworks-bcf-loop.md): proposal (scoping only) for the Navisworks clash to Revit fix loop, and BCF.
- [0016](0016-cerberus-multi-agent-review.md): Proposed, not built. Cerberus, a multi-head read-only model review with cross-checking and one approved plan.
- [0017](0017-approval-document-binding-and-expiry.md): proposal to bind approvals to a Revit document and expire them.
- [0018](0018-explicit-development-mode.md): implemented explicit panel Dev mode, trusted revocation, audit logging and its remaining limits.

Numbers 0003 to 0006 are not in this repository.

## Diagrams

- [diagrams/](diagrams/): Mermaid sources for the architecture and approval-flow diagrams in the README. [images/](images/) holds the rendered light and dark PNGs; regenerate them with `scripts/render_diagrams.py`.
