# Copy this task to the coding agent

Take over the Revit villa and the AEC Model Bridge improvements in this repository.

Read `docs/AI-REVIT-MODELING-HANDOFF.md` and `docs/villa-coding-agent-state-2026-10-13.json` first. Inspect the current worktree and live Revit state; don't assume old evidence is current. Revit was 2024 with document `R24_2026_HWC_B01_HEIJ_BWK_GEV-IND_TAS - Copy`; the connection port is ephemeral. The model is modified and has not been saved by the previous agent.

The objective is to finish the villa's geometry, spatial placement, architecture/facade/details and coordinated native MEP, while building reliable reusable AI modeling tools and workflows. The user still sees overlaps. Start by inspecting floor overlaps 23841023/23843041 and 23841030/23843041, the incorrect foundation-slab classification of ordinary floors, and window/partition conflict 23840036/23839620. Expand inspection beyond the initial selection. Resolve purposes/dependencies before deleting or replacing elements.

Implement the handoff's P0 native scene inspection, solid/mesh collision checking, verified placement/type semantics and reliable visual evidence. Integrate and test the uncommitted parameter-reader, image-export, error-reporting, inspection and IronPython-runtime fixes. Reuse existing work; preserve the user's dirty BIM review files. Never claim a mesh has no clash just because there are no solids.

Then complete the architectural detailing and genuine connector-bearing MEP systems. Create a permanent, nonempty `AMB_MEP_Only_3D` view showing only the villa MEP so the user can review it separately. Verify geometry, clearances, native system/circuit connectivity, warning deltas and readable before/after plan/section/3D views. Record design and engineering assumptions honestly.

Use narrow independent subagents where useful, with one live Revit writer. The user has authorized supported Auto mode; respect its effective state/expiry and never bypass or forge approval. Do not stop for repeated confirmation when existing authorization covers the action. Keep Revit calls bounded and mutations guarded, transactional and idempotent. Do not overwrite user work, close a modified document without handling unsaved changes, or add co-author/tool-credit lines to commits/PRs.

Continue until the full villa and tool/workflow acceptance contract is satisfied, not merely until a small test suite passes. Deliver model/view evidence, tool changes, tests, unresolved limitations and live deployment status.
