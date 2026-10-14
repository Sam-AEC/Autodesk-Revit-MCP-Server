# Dev branch test plan (Windows + Revit)

Status: on the dev branch, not yet released.

This is the plan for testing the `dev` branch by hand before a `dev` to `main`
pull request. `dev` is `main` plus a set of pull requests merged together, so
nobody has run this acceptance plan end to end. Everything here is **UNVERIFIED**
unless a line says otherwise. On 14 October 2026 the full automated suite passed
1,752 tests with 17 skips, the Revit 2024 Release build passed, and bounded
read-only checks ran against live Revit 2024 without changing model counts.
The family-probe hotfix subsequently passed 150 focused tests and live shallow/deep
checks. See [the live validation report](revit-addin-live-validation-2026-10-14.md)
and [the upgrade handoff](bridge-upgrade-handoff.md). Mutating acceptance remains pending.

Fill in the results table at the end as you go. Treat every difference from
"working looks like" as a finding, not as something to explain away.

Record before you start: Revit year, `git rev-parse HEAD` of the dev checkout,
date, name of the model you tested on.

## What is on dev

Merged into `dev` on top of `main`, as merge commits, in this order: #95
(CreateTransaction fix), #98 (add-in and hub contract test), #93 (panel shim
Host/Origin/Content-Type checks), #94 (shared client, lazy imports), #96
(community health files), #100 (third-party notices), #97 (distribution
prerequisites), #76 (model bloat), #77 (sheet and view audit), #78 (model
changes), #81 (door and room consistency), #84 (naming checker), #69, #71, #74,
#65 (rule packs), #61 (pyRevit bridge), #64 (preview in model), #60 (panel
first-run check).

Merged since the first version of this plan:

- **#99 approval v2.** Approval is human-only (panel or the
  `aec-model-bridge-approve` command). A `plan_id` is bound to the exact tool
  and arguments, each approved action runs at most once, and approve, reject and
  rollback are hidden from MCP. Report writers are confined to the workspace,
  plan ids with a trailing newline are refused, tool names that are not
  registered are refused when drafting, and the panel shows escaped arguments
  before approval.
- **#105.** `rhino_generate_diagrid_tower`, `navisworks_append_file`,
  `navisworks_refresh`, `navisworks_activate_viewpoint` and `revit_render_3d` now
  go through the approval gate.
- **#106.** Honest undo wording: Ctrl+Z per step; one-step undo for a whole plan
  is **not built**; rollback can skip actions.
- **#107.** Panel step 1: AA contrast, narrow layout, settled plans
  show a badge and no decision buttons (though the list only holds pending
  plans), Approve Selected sends one approve per ticked plan with its plan hash, the active view scrolls inside a bounded row, focus ring and aria labels.
- **#108.** Design tokens doc (docs only, nothing to test by hand).
- **#109.** Approval modes `look_only`, `ask_first` and `auto`, set with
  `MCP_REVIT_APPROVAL_MODE`. Unknown values fail closed to `ask_first`. No MCP
  tool can change the mode.

Also on dev since then: the per-user panel hub token (`X-AMB-Token`) and
instance routing for several open Revits (see [security.md](security.md) and
[ADR 0014](0014-multi-revit-routing.md)). The Revit 2024 build and authenticated
panel backend were verified on 14 October 2026; net8/net10 targets and two-live-Revit
acceptance still need verification. Also implemented: validated panel plan reviews,
explicit audited Dev mode ([ADR 0018](0018-explicit-development-mode.md)), and recovered
QA/documentation tools. See [the upgrade handoff](bridge-upgrade-handoff.md).

[demo-runbook.md](demo-runbook.md) was brought up to date with this list.
Known limits you should expect to hit are collected in section H.

## A. Install from the dev branch

You need a build, because the dev add-in is not in any release. Requirements are
in [install.md](install.md#requirements): Windows, Python 3.11+, Git, the .NET
SDK for your Revit year (.NET 8 for 2025 and 2026, .NET 10 for 2027, .NET 8 SDK
plus the .NET Framework 4.8 developer pack for 2024).

Close Revit first. If you installed a release with the installer, uninstall it
or expect the source install to overwrite the add-in files.

```powershell
git clone https://github.com/Sam-AEC/aec-model-bridge.git
cd aec-model-bridge
git checkout dev
git rev-parse HEAD            # write this down

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e packages/mcp-server-revit

$RevitVersion = "2026"        # your Revit year
.\scripts\package.ps1 -RevitVersion $RevitVersion
.\scripts\install.ps1 -RevitVersion $RevitVersion
```

These commands are copied from [install.md](install.md#install-from-source) and
the parameter blocks of `scripts/package.ps1` and `scripts/install.ps1`. The
Revit 2024 build and deployment were verified on 14 October 2026; this exact
packaging recipe and other Revit-year targets still need acceptance. If `package.ps1` fails, `.\scripts\build-addin.ps1 -RevitVersion $RevitVersion`
builds the add-in only. Note the first error.

Checks:

1. `%APPDATA%\Autodesk\Revit\Addins\<year>\AECModelBridge.addin` exists, and
   `C:\ProgramData\AECModelBridge\bin\<year>\` has fresh files (check the
   timestamps are from now).
2. Start Revit, open a project. The **AEC Bridge** tab shows.
3. Bridge health (from install.md):

   ```powershell
   $registry = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry\revit-*.json" | Select-Object -First 1
   $switch = Get-Content $registry.FullName -Raw | ConvertFrom-Json
   Invoke-RestMethod "$($switch.endpoint)/health"
   ```

   Working looks like: `status` is `healthy` and `revit_version` is your year.
4. Connect your MCP client to the dev checkout, using the `.venv` Python and
   `-m revit_mcp_server.mcp_server`, `MCP_REVIT_MODE=bridge`, and a workspace
   folder that exists (see [install.md](install.md#configure-an-mcp-client)).
   Ask the client to list tools. Working looks like: the new tools in section D
   appear.
5. Optional, no Revit needed: from the checkout, with the venv active,
   `cd packages\mcp-server-revit; $env:PYTHONPATH="src"; python -m pytest tests -q --ignore=tests/e2e --deselect tests/test_wheel_contents.py`.
   On Linux this gave 921 passed, 2 skipped (2 deselected). Record your number.

## B. First: the minimal safe write test

This is the first real write against Revit since the `CreateTransaction` fix
(#95). Builds without that fix called the method recursively, so a write could
have recursed until Revit crashed. Save everything in other Revit sessions first. Do it on a
**scratch copy** of a model, never a project file.

1. Make a copy of a small model and open the copy. Save as a new name if
   needed. Close other Revit documents.
2. Take a snapshot (`revit_extract_snapshot`). Note the `snapshot_id`.
3. Pick **one** element with an editable text parameter, for example one door's
   `Comments`. Note its element id and the current value.
4. Ask the assistant to plan exactly one `revit_set_parameter_value` on that
   element (parameter `Comments`, value `dev-test-1`) using `plan_actions`.
   Do not let it execute. Switch Dev and timed Auto off in Settings; the
   approval mode must be `ask_first` (the default).
5. In the Revit panel, open the plan. Check the arguments shown match what you
   asked for, then press **Approve** on it. (Or approve with the command line,
   section G.)
6. Ask the assistant to execute the plan (`execute_plan`).
7. In Revit, read the parameter in the Properties palette.
   - Working looks like: value is `dev-test-1`, and Revit did not hang or
     crash.
   - Failure signs: Revit freezes or closes (the old recursion), an error
     in the panel, or the value is unchanged.
8. Press Ctrl+Z once in Revit. Read the parameter again.
   - Working looks like: back to the original value. With one action in the
     plan, one step is the best case.
   - If not, note how many undo steps it took. Undo is per step (each action is
     its own Revit transaction); one-step undo for a whole plan is not built.
     That is documented behaviour, not a bug, for plans of several actions.
9. Record: pass or fail for the write, pass or fail for undo, any message text,
   and `%APPDATA%\AECModelBridge\Logs\bridge.jsonl` lines around the time.

Stop here and report if step 6 or 7 fails. Do not continue to the demo.

## C. Demo runbook

Follow [demo-runbook.md](demo-runbook.md) step by step: step 0 (build the
fixture), snapshot, ask, plan, preview, approve, execute, verify, undo, and the
rejected-plan run. Differences on this branch:

- Writes are now possible because of #95. Only do steps 6 to 8 after B passed.
- Preview in the model (#64) is merged. Step 4 can use it: see
  [preview-in-model.md](preview-in-model.md). UNVERIFIED in Revit.
- Approval is now human-only (#99). Step 5 is done by you in the panel or with
  `aec-model-bridge-approve`; the assistant cannot do it.
- Undo (step 8) is Ctrl+Z once per action, so 12 presses for the 12 doors.
  `rollback_plan` may skip the doors that started empty (see the runbook), and
  it has no panel button or command-line command on dev.
- Expected baseline from the manifest: 12 doors without Mark and 3 rooms
  without Number, 15 findings in total. Nobody has recorded this on a live
  model.
- `plan_revert` after executing: the doors started empty, so expect it to
  behave as the runbook describes.

Record the "Record for each run" items from the runbook alongside the table
below.

## D. The new tools, one by one

How to run each: ask the assistant in plain words, or call the tool by its
full name. All of these are read-only unless noted. Tool name is
`<module>_<tool>`. Take a **fresh snapshot of the real model** first and pass
its `snapshot_id`. Many tools can also run on built-in sample data when you
leave the id empty or run in mock mode. Do not count a sample-data result as a
live test.

Tools that go through the approval gate (#105) and so need an approved plan
before they act: `rhino_generate_diagrid_tower`, `navisworks_append_file`,
`navisworks_refresh`, `navisworks_activate_viewpoint`, `revit_render_3d`. They
are tested in section G, not here.

**What "not enough data" means.** The add-in's snapshot does not yet carry
every field these checks would like. When a snapshot lacks a field, the tool is
meant to say so ("Not enough data ...") and skip that check, rather than guess
or report zero problems. That is a correct, honest result today. A wrong result
is: a clean bill of health that hides a skipped check, a crash, or numbers that
do not match the model. Write down any "not enough data" text exactly, so the
snapshot can be extended.

| Tool | Run | Working looks like | Honest "not enough data" looks like |
|---|---|---|---|
| `model_bloat_audit` | Snapshot id; optional `large_type_threshold`, `max_items` | Counts of unused families and types, in-place families, families with very many types, imported CAD, and a cleanliness estimate. Counts match what you see in Revit's Purge Unused / Manage Links (spot check two). Nothing is deleted. | Notes like "Not enough data for '<check>'" and "Model cleanliness: not rated". Check that skipped checks are named. |
| `sheet_view_audit_run_audit` | Snapshot id | Empty sheets, unplaced views, duplicate sheet numbers, missing sheet parameters listed with ids you can find in Revit. | "Not enough data in this snapshot for: <list>" if the snapshot lacks sheets or views. |
| `model_changes_list_snapshots`, then `model_changes_compare_snapshots` | Take a snapshot, change something in Revit (add a door, rename a room, move a wall), take a second one. Compare `previous` and `latest`, or pass ids | The list shows both snapshots. The compare names what was added, removed, changed. Your change appears. | Text that it cannot tell whether anything moved or rotated. With only one snapshot it should say there is nothing to compare, not invent changes. |
| `schedule_consistency_check_doors_and_rooms` | Snapshot id | Duplicate or missing door Marks, missing From/To Room, rooms with missing numbers or zero area. Counts match your door and room schedules. | "Not enough data" for From Room / To Room, or for whether zero-area rooms are placed. The door-to-room checks may be reported as NOT run. |
| `naming_checker_list_example_conventions`, then `naming_checker_check_names` | List the example conventions, pick one, check a snapshot against it | A list of names that break the convention, by element kind (views, sheets, levels, and so on). | "Not enough data for view names" if the snapshot has no or partial views. |
| `warnings_triage_review_warnings` | Live Revit only, a model that has warnings (Manage > Inspect > Review Warnings) | Warnings grouped by type and ranked by element count. The top group matches Revit's own warning dialog. | An empty or short result with a clear reason if the model has no warnings. Zero warnings in a model that has them is a bug. |
| `links_worksets_audit_audit` | Snapshot id, model with a Revit link and worksets | Linked models and worksets listed, with problems like unloaded links or elements on odd worksets. | Notes for fields not in the snapshot. Non-workshared models should say so, not error. |
| `clash_triage_match_clashes`, `clash_triage_list_clash_issues` | Needs a Navisworks clash test export (the `clash_results` input). Without one, skip and mark N/A | Each clash matched to the Revit elements it involves, grouped, recorded as issues you can list. | Clashes that cannot be matched say so. See [clash-triage.md](clash-triage.md). |
| `bcf_exchange_export_bcf`, `bcf_exchange_import_bcf` | Export the recorded issues from the core QA run to a `.bcfzip` in the workspace. Import it back. Open it in a BCF viewer if you have one | A `.bcfzip` appears in the workspace (this writes a file, not the model). Import returns the same titles and status. See [bcf-exchange.md](bcf-exchange.md). | Export with no issues should say it has nothing to write. |
| Review pack: `report_generator_build_review_pack` | After a QA run and a snapshot. Check the tool's inputs with your client first | A review pack file in the workspace that opens, with findings that match the QA list. | Missing sections named, not silently blank. |

Also quickly look for the other merged modules in your client's tool list:
rule packs (`qaqc_checker_list_rule_packs`, `_validate_rule_pack`,
`_import_rule_pack`, `_export_rule_pack`, see [rule-packs.md](rule-packs.md))
and the pyRevit bridge (see [pyrevit-bridge.md](pyrevit-bridge.md)). Run
`qaqc_checker_list_rule_packs` once. The pyRevit bridge runs scripts, so only try
discover, and only run a script through the approval gate on a scratch model.

## E. Panel checks

Open the panel from the **AEC Bridge** tab.

1. **First-run Setup check (#60).** The Setup check card should be at the top
   and run by itself. Working looks like: "Ready" when hub, live mode, Revit
   connection, workspace and AI provider are fine; otherwise "N steps to fix"
   with a "What to do" per failing check
   ([first-check.md](first-check.md)). Break one on purpose (set mock mode) and
   confirm the card says so.
2. **Narrow width (#107).** Dock the panel and drag it to its narrowest, and
   also try 360 px wide if you can (a docked pane, or a browser window at
   360 px if you load the panel page outside Revit). Working looks like: no
   horizontal scroll, buttons and badges readable, rail labels not cut off, and
   a tighter layout below 480 px. Note the width in pixels where it breaks.
   UNVERIFIED in Revit's embedded browser.
3. **Finished plans leave the Plans list (#107).** The Plans list is refreshed
   from `list_pending_plans`, which returns only plans in state `pending`. So
   after you approve or reject a plan, and after it executes, it disappears from
   the panel's Plans view; this is expected, not a failure. After B, confirm the
   executed plan is no longer listed, then check it another way:
   `aec-model-bridge-approve show <plan_id>` (prints the state, who approved it
   and how), the plan file in `<workspace>\plans\`, or the proof bundle under
   `<workspace>\proofs\`. Note that `aec-model-bridge-approve list` also shows
   pending plans only. #107 hides Approve and Reject on a settled plan and shows
   a status badge instead; that rendering is only visible if a settled plan is
   ever listed, which the current refresh does not do. UNVERIFIED; record
   whether you ever see a badge-only plan.
4. **Approve Selected (#107).** Make two pending plans, tick both, press
   Approve Selected. Working looks like: one approve is sent per ticked plan,
   each carrying that plan's hash, and both plans leave the pending list. Then
   tick one plan and confirm only that plan changed. Untick everything and
   confirm the button is disabled. Record any error text. Do not use it on a
   model you care about.
5. **Long plan list scrolls inside the view (#107).** Create enough plans (or
   findings or log lines) that the list is longer than the panel. Working looks
   like: the top bar and the Setup check stay in place and only the active view
   scrolls. If the whole page grows and the top bar scrolls away, record it.
6. **Keyboard and focus (#107).** Tab through the panel. Working looks like: a
   visible focus ring on every button, tick box and rail item, and controls
   announce a name to a screen reader (aria labels) if you have one. Check text
   contrast by eye in light and dark themes. UNVERIFIED.
7. **Arguments shown before approval (#99).** Open a pending plan in the panel.
   Working looks like: each action lists its tool, its arguments and its current
   (before) value, with control characters shown as visible escapes. If you can,
   have the assistant draft a plan with an argument containing `<b>x</b>` or an
   escape sequence and confirm it is shown as text, not rendered.
8. **Panel shim checks (#93).** The panel hub should refuse requests with a
   foreign Host, Origin or Content-Type. From PowerShell,
   `Invoke-RestMethod http://127.0.0.1:8787/health` should work, and
   `curl.exe -i -H "Origin: http://evil.example" http://127.0.0.1:8787/health`
   should be refused. UNVERIFIED which status code; record it. The panel itself
   must still work after this change. That is the main thing to check. Every
   route except `GET /health` also needs the `X-AMB-Token` header: a request with
   a valid Host, no Origin and no token should get 401. The token proves a
   process running as your Windows user, not a person (section H).

### E2. Chat panel, stage 1 (new chat renderer)

The chat view now renders markdown (headings, lists, tables, code with a Copy
button and syntax colours), shows the mode in the header, and shows pending
plans as "Review N changes" cards. Replies still arrive whole (no streaming
yet). Everything below was only tested in headless Chromium with a stubbed
host, so each item is UNVERIFIED in Revit's WebView2.

1. **The panel loads at all (CSP on file://).** The page now carries a
   Content-Security-Policy (`script-src 'self'`, no inline script or style, no
   network). Open the panel from the ribbon. Working looks like: the chat view
   shows "Ask about the active model" with three example prompts, and the
   header shows a mode chip. If the panel is blank, or the chat shows "Chat
   could not load", the CSP or the script loading failed on `file://`; record
   it first, because every other check depends on it.
2. **Mode chip.** Working looks like: the chip reads "Look only", "Ask me
   first" or "Auto: not recommended" to match `approval_mode` in the hub
   config, and "Mode unknown" until the Setup check has run or when the hub is
   down. In Look only the chat also shows a "Look only" banner. The chip only
   displays the mode; "Change in settings" means the hub config, there is no
   switch in the panel yet.
3. **Markdown reply.** Ask for "a table of 3 doors and a python snippet".
   Working looks like: a real table, a code block with a language label, colours
   and a Copy button, and the table or code scrolls sideways inside its own box
   instead of widening the panel. Try a reply with `<b>x</b>` or `[a](javascript:alert(1))`
   in it: it must appear as text or as a struck-through, unclickable link.
4. **Copy buttons (clipboard permission).** Press Copy on a code block and on a
   message, then paste into Notepad. Working looks like: the pasted text is the
   raw code or the message markdown. If nothing pastes, WebView2 blocked the
   clipboard; record whether the button said "Copy failed".
5. **Composer and IME.** Enter sends, Shift+Enter adds a line, and the box
   grows up to about 8 lines. With a Japanese, Chinese or Korean IME, press
   Enter to confirm a candidate: it must confirm the text and NOT send. Also
   try the Windows emoji picker (Win+period). UNVERIFIED.
6. **Links.** Click a link in a reply. The panel posts `link.open` to the host,
   but the add-in has no handler for it yet, so expect nothing to open in your
   browser and expect a small "Link" note above the composer with the URL and a
   Copy button. Record whether anything else happened (a popup, a navigation
   inside the panel). That would be a bug.
7. **Proposal card.** Ask the assistant for a change (for example "set Fire
   Rating to 2h on the selected doors") in Ask me first mode. After the reply
   the panel asks the host for the pending plans. Working looks like: a card
   "N proposed changes" with the tools, how many elements it names, whether
   before values were captured, the Ctrl+Z note, and a "Review N changes"
   button. The card has no Approve button. Press Review: the Plans view opens
   on that plan, which still has Approve and Reject. In Look only the card says
   the changes cannot be approved. Check the numbers on the card against the
   plan's real actions in the Plans view.
8. **Scroll and "Jump to latest".** After a few replies, scroll up. Working
   looks like: a "Jump to latest" pill appears, new replies do not pull you
   down, and the pill returns you to the bottom.
9. **DPI, narrow width, Narrator.** Check 100%, 150% and 200% display scaling
   and the narrowest docked width (no sideways scroll, composer buttons
   reachable), light and dark theme, and with Narrator on that a new reply is
   read out once and the Review button is announced with its name. UNVERIFIED.
10. **Large reply.** A reply over 200 KB is cut with a "Message shortened for
    display" note (Copy still copies all of it). Only try this if you can make
    the assistant produce one; it is not a release blocker.

## F. Multi-Revit check

One hub on fixed port 8787 serves every open Revit. Requests carry the Revit
process id and the hub routes them to that Revit's bridge
([ADR 0014](0014-multi-revit-routing.md), the "Several Revits" section of
[security.md](security.md)). This routing has never run against two live Revits.
Plans do not yet record which Revit created them.

Only do this on scratch models. Open Revit 2024 and 2026 (any two versions) with
a different scratch model in each. Open the panel in both. Ask each panel for
the document name (for example a model summary) and note which model answers.
Working looks like each panel answering for its own Revit. Record which Revit
answers in each panel, and do **not** approve any write plan in this setup.

## G. Approval v2 and modes (#99, #105, #106, #109)

Do these on a scratch model, in order. Where a step says "draft a plan", ask the
assistant to use `plan_actions` for one harmless parameter write (the
`Comments` write from section B is fine) and stop before it executes. List
pending plans with `aec-model-bridge-approve list` or in the panel.

The approval mode is set with the environment variable
`MCP_REVIT_APPROVAL_MODE` for the process that starts the MCP server and the
panel hub (restart Revit and the MCP client after you change it). Leave it
unset for the default, `ask_first`.

**G1. The assistant cannot approve (MCP refusal).** Ask the assistant, in plain
words, to approve its own plan. Also ask it to call `approve_plan`,
`reject_plan` and `rollback_plan` by name.
- Working looks like: the three names are not in the tool list; the assistant
  says it cannot, or gets a plain refusal. The plan stays `pending`.
- Failure sign: the plan changes state without you pressing anything.
- Result: ______

**G2. The approve command line.** From the venv, run
`aec-model-bridge-approve list`, then `show <plan_id>`, then
`approve <plan_id>`.
- Working looks like: `list` shows pending plans only, with their action count
  and tool names. `show` works for a plan in any state. `show` prints the plan in plain language (tool, arguments, current
  value) and a `Plan hash`. `approve` asks you to type the plan id, and only an
  exact match approves it; anything else prints "Cancelled; plan unchanged."
  The plan file then has `approved_via` `cli` and your Windows account as
  `approved_by`.
- Also run `approve` with no terminal (input piped in): expected refusal unless
  you pass `--yes`.
- Also `reject <plan_id>` on a second pending plan, and on an approved plan that
  has not run: both should work. Rejecting an executed plan should be refused.
- Result: ______

**G3. Edit the plan file, expect a hash rejection.** Draft a plan. Before
approving, open `<workspace>\plans\<plan_id>.json`, change one action's
argument (for example the `value`) and save.
- Working looks like: `show` prints a different hash than before the edit.
  Approving with a hash from before the edit (the panel sends the hash of the
  list it rendered) is refused with a message that the plan changed.
- Then draft a second plan, approve it, edit its file, and ask the assistant to
  execute it. Working looks like: execution is refused because the plan no
  longer matches what was approved.
- This only covers editing the actions. Someone who can rewrite the hashes too
  is not stopped (section H).
- Result: ______

**G4. Plan id bound to the exact tool and arguments.** Approve a plan for
`Comments` = `dev-test-1`. Ask the assistant to make the same
`revit_set_parameter_value` call with a different value or element, passing the
approved `plan_id`.
- Working looks like: refused, saying no matching approved action exists. The
  original action can still run unchanged.
- Result: ______

**G5. At most once.** Execute the approved plan from G4 once. Ask the assistant
to execute it again, and to repeat the single action by hand with the `plan_id`.
- Working looks like: the second attempt is refused. The action is consumed
  after the first attempt, including when the first attempt failed. Look in
  `<workspace>\plans\.claims\` for a claim file per action.
- Result: ______

**G6. Bad plan ids and unregistered tool names.** Call a gated tool with a
`plan_id` of `plan_` plus 12 hex characters followed by a newline, then
`../plan_x`, then an id of another shape. Then ask the assistant to draft a plan
containing a tool name that does not exist, for example `revit_not_a_tool`.
- Working looks like: each bad id is refused with a plain error, and the
  drafting call with an unknown tool name is refused.
- Result: ______

**G7. Report writers are confined.** Ask the assistant to export an Excel or
SQLite report with an output file name that leaves the workspace
(`..\..\x.xlsx`), and one aimed at the `plans` or `proofs` folder.
- Working looks like: both refused; nothing written outside the workspace and
  nothing written into `plans` or `proofs`.
- Result: ______

**G8. Newly gated tools (#105).** With no approved plan, ask the assistant to
call `revit_render_3d`, then `navisworks_append_file`, `navisworks_refresh`,
`navisworks_activate_viewpoint` (needs Navisworks; mark N/A without it) and
`rhino_generate_diagrid_tower` (needs the Rhino bridge; N/A without it).
- Working looks like: each is refused with an error naming the missing or
  unapproved `plan_id`. After a plan for that exact call is approved, the call
  runs. UNVERIFIED against the real applications.
- Result: ______

**G9. Look only mode (#109).** Set `MCP_REVIT_APPROVAL_MODE=look_only`, restart,
and open the panel. Ask the assistant to run a read (a model summary), then a
write (set the `Comments` parameter, with and without a plan).
- Working looks like: the read works. Every write is refused with "Look only
  mode: this tool changes the model. Switch to Ask me first in the panel or
  settings." even for an approved plan, including from the panel chat, from
  `execute_plan` and from `rollback_plan`. A plan can still be drafted.
- UNVERIFIED: whether the panel shows or switches the mode. Record what it
  shows.
- Result: ______

**G10. Unknown mode value falls back to Ask me first.** Set
`MCP_REVIT_APPROVAL_MODE` to `lookonly`, then `off`, then an empty string,
restarting each time. Draft a plan and try to run its action without approving
it.
- Working looks like: each behaves as `ask_first`: an unapproved write is
  refused, and the server log shows a warning about the unknown value. None of
  them turns the gate off. Also check `Ask_First` and ` LOOK_ONLY ` (case and
  surrounding spaces are ignored) and `required` (same as `ask_first`).
- Result: ______

**G11. No MCP route can change the mode.** Ask the assistant to change the
approval mode to `auto`, or to turn approvals off.
- Working looks like: there is no tool for it, and the assistant says so. The
  mode is unchanged afterwards.
- Do not set `auto` on a model you care about. If you test `auto` at all, use a
  scratch model and expect writes to run with no plan.
- Result: ______

**G12. Rollback of a plan with a skipped action (#106).** Use the demo's 12-door
plan (the doors started with an empty Mark), or any plan where an action had no
recorded before-value. Run it. `rollback_plan` is not available to the assistant
and has no panel button or `aec-model-bridge-approve` command on dev, so it can
only be reached by posting to the panel hub's `/execute` with the token. If you
cannot do that, mark this step N/A and use Ctrl+Z.
- Working looks like: the result carries warnings such as "Skipped rollback for
  action ...: no before-value recorded", and the doors keep their new Marks. The
  plan is not reported as fully restored. Verify with a new snapshot, then
  restore with Ctrl+Z (one press per action).
- Rollback only restores `revit_set_parameter_value` actions; any other tool in
  the plan gives a "No rollback handler" warning and is skipped.
- Result: ______

**G13. Current panel review and Dev mode.** Use a scratch workspace/model.
- Open a plan carrying a validated review. Check summary, findings, proposed
  changes and before-values against `aec-model-bridge-approve show <plan_id>`.
  Malformed, unsupported and oversized reviews must block approval.
- Switch Dev on yourself in Settings and confirm the warning. Diagnostics should
  return `dev_mode: true` and no expiry; audited writes can proceed without a plan.
  Read-mode guards and file scope still apply. A supplied invalid or unapproved
  plan must still be refused. Switch Dev off and verify Ask me first applies
  across every session using the workspace. No model-facing tool may toggle Dev.
- Test timed Auto separately: it expires; Dev stays on until switched off.
- Automated panel and Dev-mode tests passed; live mutating checks above remain pending.
- Result: ______

## H. Known limits (do not report as new findings)

These are known and accepted for this dev drop. Check they behave as described;
do not spend time trying to prove them wrong.

- **The panel hub token authenticates a process, not a person.** Any program
  running as your Windows user can read `panel-hub.token` and use `/execute`,
  including to approve a plan. The client sends the raw token to whatever
  listens on 127.0.0.1:8787, so another user on a shared machine could bind the
  port first. The Host and Origin checks only stop browser pages.
- **Approvals are not bound to a document or a view, and never expire.** A plan
  approved on one model can in principle be run later after you switch
  documents, if the element ids and arguments still match. Reject plans you no
  longer want.
- **An action can stay `running`** if the submit to Revit fails part-way or the
  process dies. Such an action is consumed and will not rerun. A person can
  abandon it with `aec-model-bridge-approve recover <plan_id> --reason "..."`
  (after checking in Revit what it changed); then ask for a new plan.
- **Some Navisworks and proxy tools are still ungated.** #105 covered five tools,
  not every mutating tool. Treat other Navisworks and proxy tools as able to act
  without an approved plan.
- **The add-in snapshot extractor is not built** for every field, so several
  checks report "not enough data" (section D). That is expected.
- **Mutating live acceptance remains pending** (section B). Bounded read-only
  Revit 2024 checks passed on 14 October 2026; this does not establish creation,
  export, rollback or complete QA/geometry acceptance.
- **No one-step undo for a whole plan.** Undo is Ctrl+Z once per action.
  Rollback can skip actions and only handles parameter writes.
- **Write access to the workspace defeats the hash check.** Software that can
  write the plans folder can replace a plan and its hashes together. Keep AI
  clients' file tools out of the workspace.
- **The command line does not authenticate who is typing.** A program that can
  run shell commands as you can run `aec-model-bridge-approve approve <id> --yes`.
- **One hub serves all Revits.** A plan drafted in one Revit can be executed against another, because plans do not record the Revit that created them (section F).

## I. Results table and where to report

Mark each row PASS, FAIL, or N/A, add the exact message on a failure, and
attach `bridge.jsonl` lines if it is a failure.

| Section | Check | Result | Notes (messages, ids, screenshots) |
|---|---|---|---|
| A | Build and install from dev | | |
| A | `/health` healthy | | |
| A | Tools list shows new tools | | |
| B | One write applied, no crash | | |
| B | Ctrl+Z restored the value | | |
| C | Demo steps 0 to 5 | | |
| C | Demo steps 6 to 8 | | |
| C | Rejected-plan run | | |
| D | model_bloat_audit | | |
| D | sheet_view_audit_run_audit | | |
| D | model_changes (list, compare) | | |
| D | schedule_consistency | | |
| D | naming_checker | | |
| D | warnings_triage | | |
| D | links_worksets_audit | | |
| D | clash_triage | | |
| D | bcf_exchange | | |
| D | review pack | | |
| D | rule packs, pyRevit discover | | |
| E | First-run Setup check | | |
| E | Narrow width, 360 px | | |
| E | Settled plans leave the Plans list | | |
| E | Approve Selected, two plans | | |
| E | Long list scrolls inside the view | | |
| E | Focus ring and aria | | |
| E | Arguments shown, escaped | | |
| E | Panel shim Host/Origin | | |
| F | Two Revits, one hub | | |
| G1 | Approve over MCP refused | | |
| G2 | Approve command line | | |
| G3 | Edited plan file rejected | | |
| G4 | Plan bound to exact arguments | | |
| G5 | Action runs at most once | | |
| G6 | Bad plan ids, unknown tool names | | |
| G7 | Report writers confined | | |
| G8 | Newly gated tools refuse | | |
| G9 | Look only refuses a write | | |
| G10 | Unknown mode falls back to Ask me first | | |
| G11 | Mode cannot be changed over MCP | | |
| G12 | Rollback warns on skipped action | | |

Report results as an issue on
[Sam-AEC/aec-model-bridge](https://github.com/Sam-AEC/aec-model-bridge/issues)
titled "dev test run <date>", with the table, the dev commit, the Revit year and
the failing lines from `%APPDATA%\AECModelBridge\Logs\bridge.jsonl`. File one
issue per failure if you can, and name the PR number it came from (see "What is
on dev").
