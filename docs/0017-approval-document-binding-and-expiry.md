# ADR 0017: Binding approvals to a Revit document, and expiring them

Status: on the dev branch, not yet released.

## Status
Proposed. Nothing in this record is implemented.

## Context
A person approves a plan after reading its actions. Today the approval records the plan hash, who approved, when and through which channel (see [security](security.md)). It does not record which Revit document, view or instance the person had in mind, and it never expires. An approved plan stays executable until it runs, is rejected, or its running actions are abandoned.

Consequences, read from the code:

- A plan drafted and approved against model A can be executed after the person switched to model B, or in a different Revit when several are open ([ADR 0014](0014-multi-revit-routing.md)). Element ids are only meaningful inside one document, so the actions may touch unrelated elements.
- An approval given on Monday can be spent on Friday, after the model changed. The before-values captured at drafting are then stale.
- Plans do not record the Revit instance that created them (listed in security.md, "Before any release").

## Decision (proposed)
1. **Document binding.** At drafting, store a `binding` object inside the hashed plan: document GUID or central path hash, document title, Revit process id and start time, Revit version, and the active view id for view-scoped actions. The CLI and panel show it. `claim_action` compares it with the live document and refuses on a mismatch, with a message naming both. Fail closed: if the live document cannot be read, the claim is refused. Plans without a binding cannot be approved after the change (same rule as plans without `plan_hash`).
2. **Expiry.** `approved_at` already exists. Add a configurable `approval_ttl` (default proposed: 8 hours, 0 disables). `verify_approved` refuses a plan whose approval is older than the TTL, and the plan moves to `expired`, which needs a new plan. Expiry is checked at claim time, not by a timer, so a clock jump cannot reopen anything; a clock set backwards is treated as expired.
3. **No silent renewal.** Neither check can be waived by a tool call. Only a new approval by a person renews anything.

## Alternatives considered
- Binding only on the document title: titles repeat and can be renamed.
- Expiry without binding: does not stop use in the wrong document within the window.
- Re-reading before-values at claim time and refusing on drift: complementary, tracked separately (the revert path already does this).

## Consequences
- Changes the hashed plan content, so `hash_version` must be bumped and the proof bundle format extended; this overlaps with the proof and review work and must follow it.
- Needs a Revit run to verify document identity on workshared, detached and linked models (UNVERIFIED).
- Plans drafted before the change must be drafted again.
