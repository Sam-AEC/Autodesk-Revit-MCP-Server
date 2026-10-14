# Demo runbook: missing door Marks

Status: on the dev branch, not yet released.

This is the script for the core demo: ask, plan, preview, approve in Revit,
verify, undo. It runs on a synthetic fixture with 12 doors that have no Mark
and 3 rooms that have no Number. It also covers a run where the plan is
rejected and nothing changes.

**Writes are untested in a real Revit.** An architecture review found that
`BridgeCommandFactory.CreateTransaction(Document, string)` in the add-in called
itself, so builds without hotfix PR #95 could recurse on every model write
(including `revit_set_parameter_value`) until Revit crashes. The fix is merged
into `dev`; the current build passed read-only smoke checks, but its mutating
path has not passed live acceptance. Build the add-in from `dev` (or a release that
contains #95), do not run Step 6 or the undo steps against anything you care
about, and treat the first real write on a throwaway copy as a test in its own
right. Steps 1 to 5 and the rejected-plan run do not write to the model.

This runbook matches `dev`, not the last release. The pre-release checks and
known limits are in [release-checklist.md](release-checklist.md).

Bounded read-only Revit 2024 checks passed on 14 October 2026; see
[the live validation report](revit-addin-live-validation-2026-10-14.md).
Nobody has run this demo end to end against live Revit yet. The expected counts come
from the [seeded defect manifest](../fixtures/canonical-model/seeded-defects.json)
and the rule pack, not from a recorded session. Record what you actually see
and treat any difference as a finding. Background on why the demo looks like
this is in the [roadmap](roadmap.md).

## How to read the status tags

- **Checked in code**: the tool or panel feature exists on `dev` and I read
  how it behaves. That does not mean it has been seen working in Revit.
- **UNVERIFIED (live Revit)**: it needs a running Revit session with the
  add-in. Nothing in this runbook has been confirmed that way.
- **UNVERIFIED (not in a release)**: it is merged into `dev` but not yet in a
  release. This describes the current dev checkout; presence on `main` alone
  does not establish release or live acceptance. Preview in the model (#64), the write-path crash fix
  (#95) and approval v2 (#99, #105, #109) are in this group. They are tagged
  "checked in code" or "UNVERIFIED (live Revit)" below, as appropriate. Proof
  bundles, `plan_revert` (#62) and the draft-plan gate fix (#63) are merged.

## What you need

- Windows with a supported Revit version (2024 to 2027) and the add-in
  installed. See the [install guide](install.md).
- The MCP server connected to an MCP client, and the Revit side panel open.
- A throwaway copy of the fixture. Never run this on a project model.
- In Settings, switch Dev off and leave timed Auto off for this approval demo.
  Approval mode is its default, `ask_first` (the older name `required`
  means the same). Do not set `MCP_REVIT_APPROVAL_MODE=auto`; that turns the
  human check off. `look_only` refuses every model change; use it only to show
  that writes are blocked. An unknown value falls back to `ask_first`.
- The person running the demo approves. The assistant cannot approve, reject or
  roll back a plan, and the approval tools are not listed to MCP clients.

Write down before you start: Revit version, git commit, date, and the document
name. The roadmap asks for these with every recorded run.

## Step 0: build the fixture

From the repository root, with Revit open and the add-in loaded:

```powershell
python scripts\revit\generate_canonical_test_model.py
```

The script saves to `fixtures/canonical-model/generated/canonical_test_model.rvt`.
If Revit does not activate the new document, open a clean project template
yourself and rerun with `--use-active-document`. Details are in the
[fixture README](../fixtures/canonical-model/README.md).

Expected: per the manifest, the last 12 generated doors have no Mark and the
last 3 generated rooms have no Number. The manifest also expects the core rule
pack to report 15 findings in total on this model (12 + 3). UNVERIFIED (live
Revit): the generator itself.

If it fails: confirm the add-in is loaded and a document is open. The script
looks for the bridge under `%LOCALAPPDATA%\AECModelBridge\registry\` and falls
back to `http://127.0.0.1:3000`. Save the generated model under a new name so
you can reopen a clean copy for the rejected-plan run.

## Step 1: capture a snapshot

Ask the assistant: "Take a snapshot of the active model." The tool is
`revit_extract_snapshot`. Keep the `snapshot_id` it returns; every check and
parameter call below needs it.

Why: on `dev`, the QA checker and the parameter manager refuse to run in live
mode without a `snapshot_id` and tell you to capture one (change #59). They only
fall back to generated sample data when `MCP_REVIT_MODE=mock`. Sample data is not
your model, so do not run the demo in mock mode and call it live.

What to look for: a snapshot id comes back, with no error. I have not seen the
exact output, so I will not quote it. Note the id and the time.

If it fails:

- "requires a snapshot_id" means you skipped this step or the id was not passed.
- A connection error means the add-in is not running or the server cannot find
  it. Check the panel's status area, then see the install guide.
- The snapshot file must be readable by the Python server. The add-in and the
  server each have a workspace setting. If the server says the snapshot is not
  found, confirm both point at the same workspace folder. The roadmap flags this
  as something to verify, so treat it as a likely first failure.

UNVERIFIED (live Revit).

## Step 2: ask (find the problems)

Ask: "Run the core QA check on that snapshot and list the issues."

Tools: `qaqc_checker_run_check` (with `snapshot_id` and rule pack `core`), then
`qaqc_checker_list_issues`. Note the `doc_guid` that `run_check` returns and
pass it to `list_issues` together with `status` set to `open`. The issue store
is persistent and `list_issues` defaults to every document and every status, so
an unscoped call on a repeated demo, or after the doors are fixed, also returns
old and resolved findings and will not match the counts below.

Expected counts, from the manifest:

| Rule | Expected findings |
| --- | --- |
| `door_missing_mark` | 12 |
| `room_missing_number` | 3 |
| Total | 15 |

Other core rules may report findings on this model. The manifest lists several
rules the fixture cannot seed, so do not be alarmed by extra or absent lines for
other rules. Only the two rows above are the demo baseline.

If the counts differ: do not adjust the story to fit. Check that the snapshot
came from the fixture document, rebuild the fixture, and retake the snapshot. The
roadmap's bar is the same counts on two runs. If a run gives different numbers,
write down both.

Panel note: the panel's "Run Health Check" button on the Findings tab calls the
same check, but as written it sends no `snapshot_id`. In live mode that will be
rejected. Use the MCP client for this step. UNVERIFIED (live Revit) whether the
panel path works in your build.

## Step 3: plan

Ask: "Propose a unique Mark for each of the 12 doors without one, using the
pattern D-101 to D-112. Show me the exact values before anything is changed."

Agree the numbering pattern yourself first. The demo only works if the
coordinator chooses the rule; the assistant should not guess one.

Before building actions, get the numeric element ids. The QA findings carry
only `element_uid`, but `revit_set_parameter_value` needs the integer
`element_id`, and `plan_actions` does not convert one to the other. Look them up
in the snapshot: `parameter_manager_filter_params` (pass the snapshot id,
`param_name` `Mark`, and a filter for doors with an empty Mark) returns each
match with both `uid` and `element_id`; `model_inspector_ask` also returns
`element_id`. Match them to the 12 `element_uid` values from Step 2 and do not
guess ids. The add-in's snapshot writer includes `element_id`; that it comes
through correctly is UNVERIFIED (live Revit).

Tool: `plan_actions`, with one `revit_set_parameter_value` action per door
(`element_id`, `parameter_name` = `Mark`, `value`). `plan_actions` reads each
door's current Mark and stores it as the plan's before-state. It refuses a tool
name that is not a registered tool, and it stores a content hash of the plan
(its actions, arguments and before values) that the approval is bound to.
`parameter_manager_plan_set_params` can also build a draft, but it sets one
value for every matched element, so it does not fit unique Marks. Use it only
if you want to show a shared value.

Expected: a plan with 12 actions, state `pending`, 12 distinct values, and an
empty before-state for each door.

Things to check before going further:

- Exactly 12 element ids, none of them rooms, and each one matches a finding's
  `element_uid` from Step 2.
- No duplicate values within the plan, and none that clash with the 48 doors that
  already have a Mark. The code does not check uniqueness of the proposed values
  for you. This is on the human.
- If a before-value shows as missing for an element, say so. Rollback in Step 8
  depends on it.

If it fails: an assistant that tries to change a parameter directly, without a
plan, should get an authorization error naming the missing `plan_id`. That is the
gate working. Go back and create the plan. If the assistant lists
`list_pending_plans` and your plan is not there, plan creation failed; ask it to
report the error text.

## Step 4: preview

Two previews, different status:

- **In the panel (checked in code)**: open the Plans tab and press Refresh. The
  plan appears with its state and, for each action, its tool, its arguments
  (escaped, so odd characters show as text) and the current value. Read these
  before you approve and compare the count yourself. For long arguments,
  `aec-model-bridge-approve show <plan_id>` prints the same in a terminal, with
  the plan hash.
- **In the model (UNVERIFIED (live Revit), PR #64, merged into `dev`)**: see
  [preview-in-model.md](preview-in-model.md). If it does not work in your
  build, select the 12 doors and eyeball them. Use `revit_select_by_unique_ids` with the 12
  `element_uid` values; it selects and zooms in the active view. Do not use
  `selection_tools_select_by_query` for this: it only writes the matching UIDs to
  `pending_selection.json` in the workspace, and nothing in the add-in reads that
  file, so nothing would be selected in Revit. Selecting is a Revit UI action.
  UNVERIFIED (live Revit).

Expected: 1 pending plan, 12 actions.

## Step 5: approve in Revit

Approve as the person, in one of two ways.

- **Panel.** In the Plans tab, read the arguments shown, then press Approve on
  the plan. The panel sends `approve_plan` through the hub together with the
  plan's hash. To approve several, tick them and press Approve Selected; it
  sends one approve per ticked plan, each with its own hash.
- **Command line.** `aec-model-bridge-approve list`, `show <plan_id>`, then
  `approve <plan_id>` and type the plan id when asked. Without a terminal it
  refuses unless you add `--yes`.

The assistant cannot approve its own plan: `approve_plan`, `reject_plan` and
`rollback_plan` are not listed to MCP clients, are denied to the panel chat, and
are refused on every other path a model can reach. The approval is bound to a
content hash of the plan. If the plan file changed after you looked at it, the
approval is refused. The dev panel shows tools, arguments, before-values and
validated review text when you open the plan review. Malformed, unsupported or
oversized reviews block approval. Compare with
`aec-model-bridge-approve show <plan_id>` if anything is unclear. The plan records `approved_via` (`panel` or `cli`) and
`approved_by` (your account name).

Expected: the plan leaves the Plans list. The panel lists pending plans only, so
an approved, rejected or executed plan is no longer shown there. Check its
state with `aec-model-bridge-approve show <plan_id>`, the plan file, or (after
execution) the proof bundle. The Run Log gets a `Plan approve`
entry as soon as you click, and a `Plans updated` entry after the refresh; both
are normal and neither proves the hub accepted the call. Nothing in the model has changed yet; approval only unlocks execution.

An approval is not tied to a document or a view and does not expire. If you
switch models before executing, reject the plan and draft a new one.

If it fails: an `Error: plan.approve` entry in the Run Log (or an error toast)
means the hub rejected the call. Any other Run Log entry is not a failure.
Press Refresh and check the plan's state. Check the plan's
state each time. A plan that was approved but not yet run can still be
rejected; an executed or rolled-back one cannot.

UNVERIFIED (live Revit).

## Step 6: execute

Ask the assistant: "The plan is approved. Run it." Tool: `execute_plan`.

Each approved action runs at most once and only with the arguments you
approved. A repeat of the same action, or a call that differs in any argument,
is refused. If an action fails, it is not reopened: ask for a new plan.

Expected: the result lists 12 actions, each executed. In the add-in each
`revit_set_parameter_value` call runs in its own transaction, which Revit's
Undo list should show as `AMB: Set Parameter Value`, one entry per door, not one
entry for the whole plan. The add-in only appends ` #<action id>` to the name
when the call carries an `action_id`, and `execute_plan` does not pass one, so
expect no suffix and 12 identical-looking entries. This is only reachable with the #95 fix in the add-in build (see the top of
this page). UNVERIFIED (live Revit).

If some actions fail: execution reports and continues. The plan is marked
`partial`, not `executed`, and the proof bundle's outcome is `partial` or
`failed`. Do not tell the audience it worked. Read which actions failed
(read-only or owned elements are the usual suspects), then go to Step 7 and look
at what changed. An action can also be left marked `running` if the submit to
Revit failed part-way; treat the plan as not finished and check the model.

## Step 7: verify

Take a new snapshot (Step 1 again, new id) and rerun the check on it. Never
verify with the old snapshot; it still shows the old values.

Expected after a clean run:

| Rule | Before | After |
| --- | --- | --- |
| `door_missing_mark` | 12 | 0 |
| `room_missing_number` | 3 | 3 (unchanged on purpose) |

The 3 room findings staying put is the point: the approval covered doors only,
and nothing else moved. Also read back two or three of the new Marks with
`revit_get_parameter_value` and compare with the plan.

If the door count is not 0: list the remaining issues and match them to the
plan's failed actions. Say what happened plainly. If the room count changed,
stop. Something outside the plan wrote to the model; check the
[audit logs](logging-and-audit.md) to match requested changes against what Revit
executed.

## Step 8: undo

There are two ways back. Use whichever you can show honestly.

1. **Revit Undo (checked in code that transactions are named, behavior
   UNVERIFIED)**. Immediately after execution, in the same Revit session, press
   Ctrl+Z. Because each parameter write is its own named transaction, you
   need to press it 12 times, once per door. Take a fresh snapshot afterwards and
   expect the baseline of 12 and 3 again. One-step undo for a whole plan is not
   built. ADR 0008 describes a single named transaction per plan; the code names
   one per action. Do not promise one-click undo.
2. **`rollback_plan` (checked in code)**. It only works on a plan in state
   `executed`, and it writes each recorded before-value back, only for
   `revit_set_parameter_value` actions. One catch: it skips an action when no
   before-value was recorded, and reports that as a warning. It skips any other
   tool with a "No rollback handler" warning. Rollback is for a person, not the
   assistant, and on `dev` it has no panel button or `aec-model-bridge-approve`
   command, so there is no everyday way to run it. These doors started empty. If the before-state is stored as empty,
   rollback may skip all 12 and leave the Marks in place. Read the warnings in
   the result and verify with a new snapshot. If it skipped them, use Ctrl+Z
   instead. UNVERIFIED (live Revit). The model-facing chat cannot call rollback.
3. **`plan_revert` (checked in code, merged in #62)**. It drafts a new pending
   plan from the proof bundle; you still approve and execute it. It refuses when
   an element has no recorded before-value, and an empty value counts as not
   recorded. These doors started with an empty Mark, so expect `plan_revert` to
   refuse here. Treat that as the documented behaviour, not a bug, and fall back
   to Ctrl+Z. It would work for a parameter that had a value before. Its
   write-back is UNVERIFIED (live Revit) and subject to #95 like every write.

Proof of the change: `get_proof_bundle(plan_id)` returns the proof file written
after `execute_plan` (see [proof and revert](proof-and-revert.md)). Pass
`snapshot_id` to `plan_actions` if you want the document identity in it. The
bundle is a server-side record, not an observation of the model, so the evidence
that the model really changed or reverted is still the two snapshots and the
check counts. UNVERIFIED (live Revit).

## Rejected-plan run

This proves a rejected plan leaves the model alone. Start from a clean copy of
the fixture (the baseline of 12 and 3) and a new snapshot.

1. Steps 1 to 4 as above. Note the snapshot id and the 12 before-values.
2. In the panel's Plans tab, press Reject (or run `aec-model-bridge-approve reject <plan_id>`). This sends `reject_plan`. The plan is
   closed and archived.
3. Ask the assistant to run it anyway. Expected: `execute_plan` refuses, saying
   the plan is `rejected`, not `approved`. A direct parameter write with that
   plan id is blocked the same way.
4. Take a new snapshot and rerun the check. Expected: 12 missing door Marks and 3
   missing room Numbers, exactly as in Step 2. Read two doors' Marks back: still
   empty.
5. Compare the new snapshot with the first one. Nothing should differ.
   `parameter_manager_diff_params` compares two snapshots and lists differences.
   Expected: no parameter differences.

If anything is different, that is a bug in the gate. Stop and capture the plan
file, the audit log and both snapshot ids.

## Quick reference: when it goes wrong

| What you see | What to say | What to do |
| --- | --- | --- |
| "requires a snapshot_id" | The tool is protecting us from sample data. | Take a snapshot, pass its id. |
| Counts are not 12 and 3 | The baseline is off; I am not going to hide that. | Rebuild the fixture, retake the snapshot, record both runs. |
| Error naming a missing or unapproved `plan_id` | The gate is blocking an unapproved write. | Create or approve the plan. |
| Approve does nothing in the panel | I will confirm the plan state before going on. | Refresh, look for an `Error:` entry in the Run Log, check the plan state. |
| Revit crashes or hangs on the first write | Mutating acceptance is pending; confirm the installed build contains the #95 recursion fix. | Stop. Check the add-in was built from `dev`, record the log, report it. |
| "Look only mode: this tool changes the model..." | The mode is Look only on purpose; nothing can change the model. | Set `MCP_REVIT_APPROVAL_MODE` to `ask_first` and restart, if you meant to write. |
| Approval refused, plan changed | The plan on disk no longer matches what you were shown. | Run `show` again, check the hash, reject or redraft the plan. |
| Assistant says it cannot approve | Correct: only a person approves. | Approve in the panel or with `aec-model-bridge-approve`. |
| An action stays `running` | Submit to Revit may have failed; it will not rerun. | Check in Revit what it changed, mark it with `aec-model-bridge-approve recover <plan_id> --reason "..."`, then ask for a new plan. |
| Some actions failed on execute | This is a partial result, not a finished fix. | Read the per-action errors, verify with a new snapshot. |
| Door count after is not 0 | Not everything was fixed. | List the remaining issues, match them to failed actions. |
| Rollback skipped actions | Rollback could not restore empty values. | Use Revit Undo, then verify with a new snapshot. |
| Anything touching rooms changed | Stop the demo. | Check the audit logs. |

## Known limits

- The panel hub (port 8787) needs a per-user token, but the token only proves a
  process running as your Windows user. Any such program can read it and call
  the hub, including to approve a plan. Treat the machine as trusted-local.
- Approvals are not bound to a document or view and never expire.
- Actions can stay `running` after a failed submit or a crash. A person can abandon them with `aec-model-bridge-approve recover`; nothing recovers automatically.
- Some Navisworks and proxy tools are still outside the approval gate.
- The add-in's snapshot extractor does not carry every field, so some checks say
  "not enough data".
- The demo and mutating acceptance remain unverified in live Revit. The separate
  14 October 2026 read-only smoke checks do not establish this workflow.
- Undo is Ctrl+Z once per action. There is no one-step undo for a plan.

The fuller list is in
[release-checklist.md](release-checklist.md#6-known-limits-of-the-dev-drop).

## Record for each run

Date, commit, Revit version, fixture generation command, snapshot ids (before
and after), prompts used, the actual counts at each step, plan ids, and
what failed. The roadmap asks for the same list. Publish a recording only after a
run matches the expected counts twice.
