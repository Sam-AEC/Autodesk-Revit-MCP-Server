# Villa recipes (IronPython for revit_execute_python)

Proven, measured recipes that built a two-storey villa in a live Revit 2024 session on 2026-10-13. Each file is run
as `prelude.py` followed by the phase file, sent as one `revit_execute_python` script. Phases tag what they create
(`Comments = AMB_VILLA:<phase>`) so they can be re-run; floors need the fallback tagging in the prelude.

Order: p1_types, p2_openings, p3a_ground, p3b_upper, (roof via the add-in command `revit.create_roof`, then
p3b2_roof_tag.py with its `ROOF_ID` set), p3x_orient, p3c_openings, p3d_rooms, p3e_stair, p5_luxury, p5b_garage,
p5c_dedupe, p4_views / p4b_3d.

Hard-won facts these encode:
- Layered types: duplicate an existing type's own compound structure (`SetLayers`), keep Revit's layer order
  (substrate < insulation < membrane < finish outside the core); membrane layers must be 0 mm thick.
- Walls drawn counter-clockwise face inwards: measure `Wall.Orientation` and `Flip()`.
- Host openings only in walls that reach above the floor, not the underground foundation walls.
- `NewFootPrintRoof` cannot be called from IronPython (out parameter); use the add-in command.
- Copying families between documents needs an `IDuplicateTypeNamesHandler`, or Revit shows a blocking dialog.
- Failure handler: collect warnings, remove only a failing door/window, roll back anything else; never show a dialog.
- Verify by measurement: type thickness, element z-ranges, wall volume drops for each opening, room areas, stair
  risers, warning count before and after.

These are prototypes ("recipes first, promote later"): coordinates are hard-coded around one anchor element.
