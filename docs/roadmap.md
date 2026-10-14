# Roadmap: adoption priorities for BIM coordinators

Prepared 2026-10-09. These are proposed priorities. They are not claims about shipped features or users. The first audience is BIM coordinators who need to find missing model data and approve parameter fixes.

The first goal is a repeatable workflow on a synthetic model in a real Revit session: **find missing parameters → preview the exact changes → approve → verify**. Missing door Marks are the smallest first case. Inconsistent values come later, once coordinators set the rules and expected values. The existing QA rules, parameter planning and approval gate are the base. Effort labels are relative estimates, not delivery dates.

| Priority | Deliverable and rationale | Effort | Verification criteria |
| --- | --- | --- | --- |
| 0 | Require a real snapshot in the live QA and parameter workflow, and fail with a clear message when none is given. **Partly done:** in bridge mode, the QA checker and parameter manager now reject an empty `snapshot_id` (`require_snapshot_or_mock`) instead of using generated mock data. Still open: check that the snapshot belongs to the open document, and show its source and time in findings and previews. | Small | The live path rejects a missing snapshot with a clear instruction (done). It also checks the snapshot's document identity and shows its source and time in findings and previews (open). Mock mode stays labelled. The after check uses a newly captured snapshot of the same document, so sample data cannot pass as a live result. |
| 1 | A short real Revit demo and repeatable runbook. Show missing door Marks, select affected elements, review proposed values, approve once and rerun the check. This makes the existing product understandable and provides evidence of a complete coordinator task. | Small, with live Revit access | Rebuild the fixture and obtain the same rule counts on two runs. Before the door fix, the intended baseline is 12 missing Marks and 3 missing room Numbers; after it, 0 missing Marks and 3 unchanged room findings. Capture actual counts, Revit version, commit and before/after evidence. A rejected plan must leave parameters unchanged. Publish a recording only after the live result is verified. |
| 2 | Make the parameter fix review dependable. Use explicit element IDs, parameter names, old/new values, warnings and skipped elements; use user-confirmed numbering rules. Coordinators need to know exactly which model data will change and why. | Medium | Only selected missing values change. Existing populated Marks remain intact. Read-only or owned elements surface actionable failures/skips. A fresh read checks final values and reruns QA; failed or partial execution cannot appear as a completed fix. Cover stale-document/changed-value handling and document the supported rollback path. |
| 3 | An install-to-first-check diagnostic path. Explain the Revit version, add-in connection, active document, hub/client state and next action in one place. The source/install instructions currently require several components, so reducing setup failures helps new users reach the demo. | Small to medium | A fresh Windows account installs one supported Revit package and completes the read-only check without source editing. Missing Python, wrong Revit package, stopped bridge and no open document each produce a specific recovery step. Test each advertised Revit version before claiming equivalent live support. |
| 4 | A compact QA and change report that coordinators can hand over. Include document identity, rule pack, affected elements, before/after values, approval outcome and verification result. This makes the workflow useful in project reviews after the chat closes. | Small to medium | Report links every fix to its plan and element identity, distinguishes unresolved findings/skips/failures, and uses fresh model data for the after state. Reopening the report must not require an AI account. Measure time saved against the same manual check with actual pilot users. |

## First demo scope

Fix the snapshot contract first. The add-in used to write
`snapshots/snapshot-{GUID}.json` but return a bare GUID. The Python modules load
`snapshots/{snapshot_id}.json`. The add-in now writes `snapshots/{GUID}.json`.
The add-in now resolves its workspace with the same rule as the Python server
(`MCP_REVIT_WORKSPACE_DIR`, else `~/Documents/AEC Model Bridge`), and the server
reads snapshots from the workspace when it is on the allowed list. The C# side is
UNVERIFIED: it has not been compiled or run against live Revit. Compile it and
test it against live Revit before you rely on it, and check that both sides use
the same folder. Check that the snapshot covers the categories the QA rules
need. Never replace a failed live extraction with generated mock data.

Use a disposable copy of the [canonical model](../fixtures/canonical-model/README.md).
The [seeded defect manifest](../fixtures/canonical-model/seeded-defects.json)
specifies 12 doors without Mark and 3 rooms without Number. These are expected
fixture counts, not a claim that a live run has already passed. The first
recording fixes only the door Marks, using an explicit unique numbering pattern
reviewed by the coordinator. Preserve the room findings to show the scope of
the approved change.

Capture a real snapshot from that open synthetic Revit document and pass its
explicit `snapshot_id` to every QA and parameter call. Record document identity
and source/time. Capture a new snapshot after execution for verification. In
mock mode, an omitted snapshot still falls back to generated mock data. In
bridge mode it is now rejected. A connection to Revit alone does not show that
findings describe the open model, so finish the open part of priority 0 before
you treat the default workflow as live.

Record the check result, affected element selection, parameter preview, human
approval, execution result and a fresh check. Include a rejected-plan run and
the unchanged before/after values in the verification record. Exercise the
same commands through a real MCP client; a UI mockup or canned mock-mode
response cannot establish live Revit behavior.

Capture a short clip after that sequence works and store a text runbook beside
it with the commit, Revit version, fixture generation command, prompts/tool
calls and expected counts. Use small targeted tests for any newly fixed
behavior, then the existing live e2e path where applicable:

```powershell
# Requires Revit with the add-in loaded; use a disposable fixture project.
python scripts\revit\generate_canonical_test_model.py
$env:AEC_MODEL_BRIDGE_E2E = '1'
python -m pytest packages\mcp-server-revit\tests\e2e -m e2e
```

Do not assume this existing e2e suite alone covers the full review/approve/fix
demo; record missing coverage and verify the full sequence in the live client.

## Evidence and sequencing

- [Core QA rule pack](../packages/mcp-server-revit/src/revit_mcp_server/modules/qaqc_checker/rules/core.yaml) already contains `door_missing_mark` and `room_missing_number`; [the checker](../packages/mcp-server-revit/src/revit_mcp_server/modules/qaqc_checker/module.py) tracks findings in a workspace SQLite store.
- The checker's `_get_data` and the [parameter manager's](../packages/mcp-server-revit/src/revit_mcp_server/modules/parameter_manager/module.py) `_get_elements` call `require_snapshot_or_mock()` when `snapshot_id` is empty. In bridge mode this raises an error. In mock mode they still call `generate_mock_snapshot()`. This covers the first part of priority 0. Document identity checks are not implemented.
- [Parameter manager](../packages/mcp-server-revit/src/revit_mcp_server/modules/parameter_manager/module.py) already produces planned changes with before values, validation errors and worksharing warnings. Validate those warnings against real Revit ownership before promising batch safety.
- [Approval lifecycle](0008-approval-gate-lifecycle.md) and [native chat trust model](0012-native-agent-chat-backend.md) describe the human approval boundary. Acceptance criteria must verify the concrete client path used in the demo.
- [Installation](install.md) documents the Python server and native add-in requirements; [audit logging](logging-and-audit.md) explains the two log layers needed to correlate a requested change with actual Revit execution.

Finish the first demo before adding more integrations. Pick the next workflow from the setup failures and repeated QA tasks that coordinators actually hit. Keep Navisworks, Power BI and other provider work behind this until a real pilot shows one of them blocks users.

No pilot with BIM coordinators has been run yet.
