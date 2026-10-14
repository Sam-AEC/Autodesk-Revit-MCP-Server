# pyRevit Bridge module

Status: on the dev branch, not yet released.

The built-in `pyrevit_bridge` module lets existing pyRevit pushbutton scripts be discovered and run as tools behind the [approval gate](0008-approval-gate-lifecycle.md), without rewriting them.

> **Status: Python side only.** Running a script inside Revit needs a provider tool `revit_run_pyrevit_script` and an add-in handler for the bridge call `revit.run_pyrevit_script`. Neither exists, and the add-in side is **NOT implemented and UNVERIFIED**. Nothing here has been tested against a live Revit or pyRevit install. Until the runner exists, `run_pyrevit_script` performs every check and then returns `status: "bridge_unavailable"` with `executed: false`.

## Configuration

Set `MCP_REVIT_PYREVIT_EXTENSION_DIRS` to one or more directories, separated by `os.pathsep` (`;` on Windows, `:` elsewhere). Only `*.extension/**/*.pushbutton/script.py` files under those directories are visible. Paths are resolved (symlinks included) and must stay inside the configured directory; `..`, absolute paths and backslashes in a script id are rejected.

## Tools

| Tool | Gate | What it does |
| --- | --- | --- |
| `pyrevit_bridge_list_pyrevit_scripts` | read-only | Returns `id`, `title` (pushbutton folder name), `tab`, `panel`, `description` (module docstring if present) and `has_write_calls`. |
| `pyrevit_bridge_plan_run_pyrevit_script` | read-only | Returns an ActionPlan draft with script path, SHA-256 and the detected write-call lines. Never executes. |
| `pyrevit_bridge_run_pyrevit_script` | mutating, needs approved `plan_id` | Re-reads the script, checks its SHA-256 against the approved plan, then calls the bridge. |

Script ids look like `0:Tools.extension/Arch.tab/Rooms.panel/Renumber.pushbutton/script.py`; the number is the index of the directory in the env var.

The plan tool is deliberately not flagged mutating: it writes nothing, and a mutating flag would make the gate demand an approved plan before a plan could be created.

## Flow

1. `list_pyrevit_scripts` to find a script.
2. `plan_run_pyrevit_script` and review the preview.
3. Pass the draft's `actions` to `plan_actions`, then approve the plan.
4. `run_pyrevit_script` with `script_id`, `script_sha256` (from the preview) and `plan_id`. It refuses if the plan is not approved, does not contain that id and hash, or the file's current hash differs. The same bytes that were hashed are the ones sent to the bridge.

## Write-call detection

A line-based heuristic flags `Transaction`/`TransactionGroup`, `.Start(`, `.Commit(`, `.Delete(` and `ElementTransformUtils` (comment lines are skipped). A script with no hits is **not** guaranteed read-only; every run is gated regardless.

## Bridge contract (proposed, not implemented)

Provider tool `revit_run_pyrevit_script` mapping to bridge call `revit.run_pyrevit_script` with `{script_id, script_sha256, script_source, plan_id}`. The add-in should verify `script_sha256` against `script_source` before executing and return the script output. Registering that provider tool and writing the add-in handler are follow-up work.
