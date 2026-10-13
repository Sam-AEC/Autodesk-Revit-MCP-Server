# Villa 2 recipes (DWG to Revit)

Builds the villa drawn in `630ef8009fd4b.dwg` (ground plan, first-floor plan, four elevations) 30 m to the left and 30 m above villa 1.
Each phase is a small IronPython file run through `revit_execute_python` after `prelude.py` (`# prelude2` marker in the helper client).

Scale: 1 DWG unit = 0.125 m. All DWG coordinates are in the ground-plan frame (first-floor drawing minus (214.0, 2.4)).

Order and what each phase proves:

| Phase | File | Verification it prints |
|---|---|---|
| 1 levels and layered types | `p1_types.py` | type thickness equals the sum of layers |
| 3 walls (ground, first, parapets, tower) | `p3_walls.py` | every wall end joined; no wall flipped after creation (`preorient`); heights |
| 4 floors | `p4_floors.py` | category Floors, not foundation slabs; z range |
| 5 openings | `p5_openings.py` (+ `p8_arch_families.py`) | host, DWG position, wall volume removed, door hinge/swing match the DWG arcs |
| 6 stair | `p6_stair.py` | 20 risers, 171 mm / 280 mm, top at the first-floor level |
| 7 roofs | `p7_roofs.py` + `revit_raw_command revit.create_roof` | top heights, slope edges |
| audit | `../toolkit/audit_villa.py` | openings and roofs, FAIL lines; **must be 0 FAIL** |
| clashes | `../toolkit/intersections.py` | wall/floor/roof solid overlaps in m3 |
| views | `views.py` | 3D (cropped), plans; PNGs exported to `villa2-review` |

Lessons (also in `docs/bim-agent-findings.md`, section F): draw exterior walls with the exterior on the LEFT of the direction instead of calling `Flip`;
walls stop at slab undersides; a single `revit_execute_python` call must stay under 30 s (families one per call);
arch openings are cut with void-family instances, not with a family Opening.
