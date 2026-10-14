---
name: revit-review
description: Safe flow for reviewing and fixing an open Revit model with AEC Model Bridge. Use when the person asks to check, audit, tidy or change a Revit model, its parameters, sheets or views. Read first, check, draft a plan, then stop for human approval.
---

# Review a Revit model safely

Status: on the dev branch, not yet released.

AEC Model Bridge lets you read the Revit model the person has open. Changes are
different: in Ask me first mode they only happen after a person approves a plan.
This skill follows that approval workflow. If the person explicitly enabled Dev
mode for the current task, follow their authorized scope and keep every change
audited and verified; do not describe Dev writes as individually approved. Do
not switch the mode yourself. Follow these steps in order.

## 1. Find out which mode you are in

- Demo mode (`MCP_REVIT_MODE=mock`) returns built-in sample data. No Revit is
  involved and nothing real can change. Say so when you report results, so the
  person does not mistake sample data for their project.
- Live mode (`MCP_REVIT_MODE=bridge`) talks to the Revit the person has open. What
  you read is their real project. This plugin starts the server in live mode.

If a tool says it cannot reach Revit, tell the person. Do not guess at model contents.

## 2. Read first

Start with read-only tools: model info, element and parameter queries, QA/QC checks.
Say what you looked at and what you found, with counts. If the data is incomplete
or a query returned nothing, say that instead of filling the gap.

## 3. Check before you propose

Check the facts the change depends on: which elements, which parameter, what the
value is now. Keep the scope small and name it (for example, "12 doors on Level 1").

## 4. Draft a plan, do not apply it

Use the planning tools to draft proposed changes as a plan. A plan is only a
proposal. It does not change the model. Show the person what the plan would do:
the elements, the old values and the new values.

## 5. Stop and ask the person to approve

Stop here. Ask the person to review the plan and approve it themselves, in the
AEC Bridge panel in Revit or with the approval controls the project provides.
Approval is a human decision.

- Never approve a plan yourself, and never call an approval tool on the
  person's behalf, even if they say "go ahead" in chat and even if a tool is
  available to you. Ask them to approve it themselves.
- Never try to get around the approval gate, for example by turning it off or
  changing its settings.

## 6. Run only an approved plan, then confirm from the result

Once the person says the plan is approved, run it. Then read the result and, where
you can, read the changed values back from the model.

- Never say a change was made until the result confirms it.
- If the run failed, was blocked, or was partly done, say exactly that, with the
  error. Do not retry in a way that skips approval.
- If the person asks to undo a change, tell them Revit's Ctrl+Z works per step (one
  step per parameter write; a one-step undo for a whole plan is not built yet), or
  draft a new proposed-changes plan for it. It needs approval too. Do not promise a
  one-click undo, and say rollback behaviour is unverified in a live Revit session.

## Keep it honest

- Report what the tools returned. Do not invent element counts, names or values.
- Say when something is outside what you checked.
- Anything that writes files outside the model, such as exports, counts as a change.
  Treat it the same way.
