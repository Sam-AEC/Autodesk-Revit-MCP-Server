# Clash triage (read-only)

## Decision: Navisworks clash to Revit fix loop, and BCF

Status: proposed, scoping only. Only the read-only triage slice below and the BCF tools exist. Nothing here has run against a real Navisworks or Revit session, so claims about those programs are UNVERIFIED. The approval gate ([ADR 0008](0008-approval-gate-lifecycle.md)) stays in charge: the assistant may propose a fix, never apply one without an approved plan.

The loop: Navisworks clash report, then an issue, then a proposed Revit fix, then the approval gate, then a change in Revit.

**Order of work:** triage first, then BCF, then gated fixes. Skip parsing exported Navisworks reports unless a pilot user only has files. The cloud issue tool (`autodesk_data_create_topic`) is an optional output, not the foundation.

1. **Read-only triage (this page).** Map clash items to Revit elements and measure how often the mapping is right on a real project. If the rate is poor, the loop is not worth building yet.
2. **BCF 2.1 export and import.** Built as separate tools ([bcf-exchange.md](bcf-exchange.md)) with zip and XML hardening, but not yet checked in other BCF tools or against clash-triage issues.
3. **Gated fix proposals.** Only fix types with a tested inverse. Today `rollback_plan` undoes only `revit_set_parameter_value`; for other tools, including `revit_move_element`, it skips the action and can still report `rolled_back`. Until a move has a tested inverse, clash plans may change parameters only, and a plan with a skipped action must not be reported as fully rolled back.

**The main risk is the mapping.** A wrong match means proposing to move the wrong wall. Use the Revit `UniqueId` or the IFC GUID as the key, never `ElementId` (not stable across files) or the Navisworks `InstanceGuid` (not a Revit identifier). Label every mapping with its confidence, re-read the element from the live document before proposing anything, and never fall back to a silent guess.

**Known gap on the read side.** `navis.get_clash_results` reads only `ClashResult` children of the test. Clashes inside groups are dropped while `totalClashes` still counts the groups, so a grouped test can return a short or empty list with a normal-looking total. Fix it first (walk groups, return every clash with its group name, report a true total), or the mapping rate is measured on an incomplete set.

**Open questions:** which model sources a pilot uses (RVT, NWC, IFC) and what `ifcGuid` holds for each; whether the QA/QC issue store fits a two-element clash (the triage module uses its own store); which BCF version and tools to match first; how worksharing ownership affects a move; whether the cloud `issues_endpoint` is real for any user.

## Read-only triage

First slice of the Navisworks to Revit loop (decision summary above). It answers one question for a BIM coordinator: "for each clash in my Navisworks test, which Revit elements are involved, and how sure are we?"

It never changes the Revit model and it proposes no fixes.

## How to use it

1. Run a clash test in Navisworks and fetch the results with `navisworks_get_clash_results`.
2. Capture a Revit snapshot and note its `snapshot_id`.
3. Call `clash_triage_match_clashes` with the clash results and the `snapshot_id`.
4. Read the answer per clash. Later, `clash_triage_list_clash_issues` lists what was recorded.

In mock mode (`MCP_REVIT_MODE=mock`) the snapshot is optional and generated sample data is used. When connected to Revit a real `snapshot_id` is required; the tool refuses to guess.

## What the confidence labels mean

| Label | Meaning |
| --- | --- |
| exact | The clash item's GUID matches exactly one Revit element, by its UniqueId or by its IFC GUID parameter. |
| ambiguous | The GUID matches more than one element. None is picked for you. |
| unmatched | No GUID was supplied, or no element in the snapshot has it (the model may have changed since the test). |

A clash is only "exact" when both of its items are exact. Otherwise it takes the weaker of the two labels.

## What it will not do

- It does not use the Revit ElementId or the Navisworks InstanceGuid to find elements. Those are not reliable across tools.
- It does not match by name or category, and it does not fall back to a guess.
- It does not write to the Revit model. Results are saved as issues in the workspace file `clash_triage.db`. This is kept apart from the QA/QC issue store so a QA/QC re-run cannot close clash issues by accident.

## UNVERIFIED

Everything above was tested with fixture data only. Not yet checked on a real project with Revit and Navisworks:

- What Navisworks puts in the GUID field for items that came from Revit, IFC or NWC sources.
- Whether the Revit snapshot carries an IFC GUID parameter (the module looks for a parameter named `IfcGUID`) in your models.
- How many clashes map to the right element on both sides. A person should check a sample on one real project.
- Clashes inside linked models or groups.
