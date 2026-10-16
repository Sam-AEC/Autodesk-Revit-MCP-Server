# Demo GIF shot list

For the README GIF of the missing-Mark demo. The steps, expected counts and
failure notes are in [docs/demo-runbook.md](../../docs/demo-runbook.md); this
file only says what to put on screen. Nobody has recorded this against a live
Revit yet, so every shot is UNVERIFIED until a run matches the runbook counts
twice.

Run `scripts/demo/demo-commands.ps1` for the exact commands and prompts. It
records nothing and changes nothing.

## Setup

- Throwaway copy of the synthetic fixture (runbook Step 0), never a project.
- 1280x720 window, Revit on the left, MCP client on the right, panel open.
- Hide your user name, project names and file paths in title bars and trays.
- Recorder: ScreenToGif, 10 fps, crop to the two windows. Target 25 s or less
  and 5 MB or less, so GitHub shows it inline.
- Approval mode `ask_first`, Dev off, timed Auto off.

## Shots

| # | Seconds | On screen | Caption |
| --- | --- | --- | --- |
| 1 | 3 | Client prompt: "Run the core QA check on that snapshot and list the issues." Result shows 12 doors without a Mark, 3 rooms without a Number. | Ask |
| 2 | 3 | Client prompt: propose Marks D-101 to D-112. Plan comes back as pending, 12 actions. | Plan |
| 3 | 4 | Panel, Plans tab: the plan with its 12 actions and the before-values. | Review |
| 4 | 3 | Assistant tries to run it. Refused: plan is not approved. | Blocked until you approve |
| 5 | 3 | Person clicks Approve in the panel. | You approve |
| 6 | 4 | Assistant runs the plan. Revit shows the Marks filling in. | Execute |
| 7 | 3 | New snapshot and check: doors 0, rooms still 3. | Verify |
| 8 | 2 | Optional: Ctrl+Z in Revit, or the rejected-plan run instead. | Undo |

Shot 4 is the one that matters. Do not cut it.

Do not record shot 6 until a write has passed on a throwaway model (runbook,
top of page). Until then record shots 1 to 5 and the rejected-plan run only,
which do not write to the model.

## Check before publishing

- The counts on screen match the runbook (12 and 3, then 0 and 3).
- No real names or paths are visible.
- The GIF does not claim more than was shown. Put the Revit version and the
  commit in the caption of the post that carries it.
