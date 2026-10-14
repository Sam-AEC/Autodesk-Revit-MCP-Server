# Release checklist

Status: on the dev branch, not yet released.

An ordered list for shipping from `dev` to `main`. It reflects the dev branch as it is today. Bounded read-only Revit 2024 checks passed on 14 October 2026; see [the live validation report](revit-addin-live-validation-2026-10-14.md). Mutating acceptance and other Revit-year targets remain UNVERIFIED until checked. Known limits are in section 3 and in [security.md](security.md).

## 1. What CI proves

The workflow in `.github/workflows/ci.yml` runs on every push and pull request. It proves:

- Python lint (`ruff check`), the Python test suite with coverage, version consistency (`scripts/version.py check`), `uv.lock` freshness and tool catalog generation.
- Repository metadata validation, wheel and sdist build, `twine check --strict`, and a smoke test of the built wheel in a clean venv.
- The Revit add-in and the Rhino bridge add-in compile (`dotnet build`).
- Workflow files pass `actionlint`.
- The doc tests, including the translated READMEs and install links, pass.

CI does not start Revit. Tests that touch Revit use mock providers.

## 2. Needs a live Revit

Run on a Windows machine with Revit, starting with the write test in section 5. Mark each PASS or FAIL.

1. First real write (for example `revit_set_parameter_value` through an approved plan). A crash here is the most important finding.
2. Undo behaviour. The add-in names one transaction per action, so undoing a plan takes one Ctrl+Z per action. Check this, and check `rollback_plan`, which can skip actions that have no recorded before-value.
3. Two Revits open at once: requests reach the Revit the person means ([ADR 0014](0014-multi-revit-routing.md), the "Several Revits" section of security.md).
4. The WebView2 panel loads, lists pending plans and approves one. Run `aec-model-bridge-approve show <plan_id>` for the same plan and compare it with what the panel showed.
5. Windows ACL on `%LOCALAPPDATA%\AECModelBridge\panel-hub.token`: only the current user has access. Windows does not re-verify the ACL on read.
6. The Revit 2024 Release build and authenticated panel backend passed on 14 October 2026. Build and run the net8 and net10 targets as well, and repeat the release checks on each supported year.
7. Verify the panel review card and explicit Dev mode (Settings, Dev mode). Dev must stay visibly enabled until switched off, audit its writes, and preserve read-mode guards, filesystem scope and supplied-plan checks.

## 3. Known limits (from security.md)

- Plans do not record the Revit that created them. Until fixed, a plan drafted in Revit A can run against Revit B.
- The client sends the raw token to whatever listens on 127.0.0.1:8787. On a shared machine another user could bind the port first.
- No socket timeout or thread cap on the hub handler, so a slow unauthenticated body can hold a thread.
- The routed-bridge lock is held during a network initialise, and cached clients for dead Revits are not evicted.
- The dev panel displays validated plan reviews and blocks approval when a review is malformed, unsupported or too large. These browser checks passed; live plan approval acceptance remains pending. Compare the card with `aec-model-bridge-approve show <plan_id>` before approving.
- The panel Plans view lists pending plans only. `aec-model-bridge-approve show <plan_id>` works for a plan in any state; `proofs/` bundles exist only for plans that were executed or attempted.
- There is no one-step undo for a whole plan. Undo is Ctrl+Z once per action, or a revert plan (`plan_revert`) that is approved like any other plan. `rollback_plan` is for people only and has no panel button or command-line command yet.
- Executing a plan costs O(n^2) in its action count; keep plans to a few hundred actions.
- Environment Auto, timed panel Auto and explicit panel Dev skip per-change approval. Dev has no expiry until switched off and applies across sessions sharing the workspace; it does not relax filesystem scope or read-mode guards. An explicitly supplied plan must still be valid and approved.
- The panel's `/execute` endpoint and the approval command line authenticate a local process, not a person. Do not give an AI client a shell on the same account if you rely on the gate.
- Write access to the workspace defeats the hash check.
- `plan_actions` captures a before-value only for `revit_set_parameter_value`.
- Some Navisworks and proxy tools may still be ungated; `revit_calculate_material_quantities` is ungated although the add-in marks it mutating (UNVERIFIED).
- Reject any pending revert plan drafted before upgrading.
- Cerberus is a planned feature inside AEC Model Bridge. It is not built.

## 4. Steps only the maintainer can do

1. Open the pull request from `dev` to `main` and review it. Do not merge until sections 1 and 2 are done or their gaps are accepted in writing.
2. Import the repository rulesets in GitHub settings.
3. Upload `docs/images/readme/social-preview.png` under repository Settings, General, Social preview. Only an admin can set it.
4. Have counsel review the licences and the rule packs ([rule-packs.md](rule-packs.md), [LICENSING.md](../LICENSING.md)).
5. Have native speakers review the 16 translated READMEs in `docs/i18n/`, including the Plans view note, approval and undo wording, and the current screenshot alt text. Source corrections do not establish native-language review.
6. Run a pilot with BIM coordinators. None has been run yet.
7. Tag and publish the release ([versioning.md](versioning.md)).

## 5. Minimal safe write test

The first real write against Revit since the `CreateTransaction` fix (#95). Builds without that fix could recurse until Revit crashed. Save other Revit sessions first. Use a scratch copy of a small model, never a project file.

1. Open the copy, close other Revit documents, and take a snapshot (`revit_extract_snapshot`).
2. Pick one element with an editable text parameter, for example a door's `Comments`. Note its element id and value.
3. Ask the assistant to plan exactly one `revit_set_parameter_value` (parameter `Comments`, value `dev-test-1`) with `plan_actions`. Do not let it execute. Dev and timed Auto must be off; approval mode must be `ask_first`.
4. In the Revit panel, check the arguments match what you asked for, then Approve. (Or `aec-model-bridge-approve`.)
5. Ask the assistant to run `execute_plan`.
6. Read the parameter in the Properties palette. Pass: value is `dev-test-1` and Revit did not hang or crash. Fail: freeze, close, a panel error, or an unchanged value.
7. Press Ctrl+Z once and read it again. Pass: the original value is back. If it took more steps, note how many. Undo is per action, so one step for a whole plan is not built.
8. Record pass or fail for the write and for undo, any message text, and the lines in `%APPDATA%\AECModelBridge\Logs\bridge.jsonl` around that time.

Stop and report if step 5 or 6 fails.

## 6. Known limits of the dev drop

Accepted for now. Check they behave as described; do not report them as new findings. Limits already in section 3 are not repeated.

- The panel hub token authenticates a process, not a person. Any program running as your Windows user can read `panel-hub.token` and call `/execute`, including to approve a plan. The Host and Origin checks only stop browser pages.
- Approvals are not bound to a document or a view and never expire. A plan approved on one model can run after you switch documents if the element ids and arguments still match. Reject plans you no longer want.
- An action can stay `running` if the submit to Revit fails part-way or the process dies. It is consumed and will not rerun. After checking in Revit what it changed, abandon it with `aec-model-bridge-approve recover <plan_id> --reason "..."` and ask for a new plan.
- Navisworks and proxy tools: #105 gated five tools, not every mutating one.
- The add-in snapshot extractor does not fill every field, so several checks report "not enough data".
- The command line does not authenticate who is typing. A program that can run shell commands as you can run `aec-model-bridge-approve approve <id> --yes`.
- One hub serves all Revits. A plan drafted in one can be executed against another.
- Rollback can skip actions and only handles parameter writes.
