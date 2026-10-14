# Preview in model

Status: on the dev branch, not yet released.

Lets a coordinator who does not script see which elements a proposed change
affects before approving it. Two read-only tools:

| Tool | Add-in command | What it does |
|---|---|---|
| `revit_preview_elements` | `revit.preview_elements` | Selects the given elements, zooms to them, and (by default) puts the active view into Revit's temporary isolate mode. |
| `revit_clear_preview` | `revit.clear_preview` | Ends temporary isolate in the active view and clears the selection. |

Arguments for `revit_preview_elements`: `element_uids` (UniqueId strings),
`element_ids` (integers), both optional and combined, and `isolate`
(boolean, default `true`; `false` selects and zooms only). Ids that do not
resolve are counted in `not_found_count` and skipped.

## Design

- Neither command is flagged mutating, so no approved plan is required.
- Persistent view graphic overrides (`View.SetElementOverrides`, colour) are
  deliberately not used: they are stored in the document and would change
  persistent model content. Highlighting is selection plus Revit's
  temporary hide/isolate view mode, which Revit does not save.
- `IsolateElementsTemporary` and `DisableTemporaryViewMode` must run inside a
  transaction. The add-in opens and commits one around each call. Revit may
  list it on the undo stack, but the temporary mode itself is not saved.
- `revit_clear_preview` is exempted by name in the contract test that flags
  "clear" as a mutating verb, because it only affects view and selection state.

## UNVERIFIED

- The Revit 2024 Release build passed on 14 October 2026 (zero errors); see
  [the upgrade handoff](bridge-upgrade-handoff.md). Other target builds still need release verification.
- Not run in a live Revit session. Actual on-screen behaviour is unobserved.
- Workshared models: whether the small transactions behave well (no
  checkout/ownership side effects, no sync prompts) is unknown.
- Linked models: elements living in a link are not resolved by the host
  document's `GetElement`; they will be reported as not found.
- Views that cannot take temporary isolate (`CanUseTemporaryVisibilityModes`
  false, such as some schedules or sheets) get select and zoom only;
  `ShowElements` behaviour in such views is untested.
- There is no colour highlight, only isolate; by design, see above.
- Python tests use mock mode and only cover argument mapping and metadata.
