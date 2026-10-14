# Proof bundles and revert plans

Status: on the dev branch, not yet released.

Every plan that finishes executing leaves a proof file, and an executed parameter fix can be undone through the same approval gate.

## Proof bundle

When `execute_plan` finishes (or a mutating tool marks a plan executed), the server writes `proofs/<plan_id>.json` in the workspace. Read it with the read-only tool `get_proof_bundle(plan_id)`.

| Field | Meaning |
| --- | --- |
| `plan_id`, `tool`, `tools` | The plan and the tool(s) it called. |
| `created_at`, `approved_at`, `executed_at` | Lifecycle timestamps (UTC). |
| `approved_by` | The operating-system account that ran the approval (set by the server; an `approver` argument is ignored). It is a local account name, not a verified person. `approver_note` names the channel (`panel` or `cli`), or says the identity was not recorded. |
| `document` | `snapshot_id`, `doc_guid`, `doc_title` of the snapshot the plan was drafted from. `null` if the plan has no `snapshot_id`. |
| `plan_hash` | SHA-256 of the plan content (actions, arguments, before values, skipped list). |
| `elements` | Applied changes: `element_id`, `uid` (when a snapshot is known), `parameter`, `before`, `before_storage_type` (Revit storage type reported when `before` was captured; `null` if unknown), `new`. |
| `skipped` | Elements left out, each with a `reason` (blocked at planning time, or failed at execution). Entries from `parameter_manager_plan_set_params` carry `uid`, `element_id` and `param`. |
| `outcome` | `success`, `partial` or `failed`. Only `success` means every action ran. |

To get the document identity and the skipped list, pass `snapshot_id` (and `skipped`, which `parameter_manager_plan_set_params` returns as its blocked list) to `plan_actions`.

## Reverting

`plan_revert(plan_id)` reads the proof bundle and drafts a new pending plan that sets each parameter back to its recorded `before` value. It never executes anything: the draft still needs a person to approve it (in the panel or with `aec-model-bridge-approve`) and then `execute_plan`, and its own execution gets its own proof (`reverts_plan_id` links them).

It refuses, with a message, when:

- the plan has no proof bundle, or its outcome is not `success` (partial and failed runs are not reverted);
- the plan state is not `executed`;
- an element has no recorded `before` value (an empty value counts as not recorded);
- the current model value differs from the value the plan wrote. With `allow_conflicts=true` the draft is created anyway and lists those elements in the plan's hashed `review` block (`review.conflicts`, with element, parameter, expected, actual and revert-to values clipped for display, plus a warning; conflicts beyond the detailed list are named in an "Also changed" warning), so editing them after drafting invalidates the approval. `aec-model-bridge-approve show` and the panel review card display them.

Values are compared and drafted by type. The live read returns every value as text, so the staleness check compares numerically when both sides are numbers (`"60"` equals `60`, `"61"` does not) and as text otherwise. The drafted `value` is rebuilt from `before_storage_type`: integer for Integer and ElementId, float for Double, text for String. When the storage type was not recorded (proofs written before this field existed), a numeric-looking `before` becomes a number only if the value the plan wrote was numeric; the draft's `review.assumptions` list each such guess. The proof bundle also records the plan's `hash_version` and `review`.

Like `plan_actions`, drafting a revert is not itself gated; changing the model is.

## Limitations

- UNVERIFIED: write-back to Revit. The tests use an in-memory fake parameter store. The `outcome` reflects what the provider reported; the server does not re-read values after writing. Confirm against a live Revit session before relying on it.
- UNVERIFIED: revert's staleness check and the `before` capture read values through `revit_get_parameter_value`, so their correctness in a real model (units, type vs instance parameters, worksharing ownership) depends on that live tool.
- When a mutating tool is called directly with a `plan_id` (not through `execute_plan`), no per-action results exist. The proof is still written, but its outcome is never `success`, so such plans cannot be reverted. Direct calls that raise before the plan is marked executed leave no proof.
- Only `revit_set_parameter_value` actions are recorded per element and reverted. Other actions in the same plan appear under `other_actions` and are not reverted.
- `approved_by` is the local operating-system account name; it is not an authenticated identity.
