# Recipe library

A recipe is a saved IronPython 2.7 script that runs through the same path as `revit_execute_python`. Save it once, run it by id with checked parameters. Module: `revit_recipes`. (The older YAML `recipe_runner` is a different thing and is unchanged.)

Status: on the dev branch, not released. Nothing here has run against a live Revit (UNVERIFIED).

## Tools

| Tool | What it does | Approval |
|---|---|---|
| `revit_recipe_save` | Writes `recipes/<id>.py` and `recipes/<id>.json` in the workspace | none (it only writes those files) |
| `revit_recipe_list` / `revit_recipe_get` | Show recipes, code, hash, params | none |
| `revit_recipe_run` | Runs a recipe. `dry_run: true` checks everything and runs nothing | read recipe: none. Write recipe: approved plan |
| `revit_recipe_delete` | Removes a recipe | approved plan |

Ids are `a-z`, `0-9`, `_`, `-`, 1 to 64 characters. Code is at most 64 KiB. Three read-only starters ship with the server: `element_count_by_category`, `level_list`, `warning_summary`. Save a recipe with the same id to replace one.

## What the manifest holds

`id`, `version` (goes up on every save), `title`, `description`, `params`, `mode` (`read` or `write`), `approval`, and `sha256` of the code (line endings normalised to LF). The hash is recomputed from the file on every read. If the manifest and the code disagree, nothing runs.

## Approval

- A write recipe is planned like any other write. The plan action must carry exactly `{id, version, sha256, params}`; `revit_recipe_get` and `dry_run` print it as `plan_arguments`. If the recipe is edited after approval, the version and hash no longer match and the run is refused.
- A read recipe runs with no approval only if the manifest says `read` and its code passes read mode when it is run. The manifest flag alone is never trusted. `mode: read` is also refused at save if the code fails the check.
- A recipe can have a standing approval. Only a person can set it, with `aec-model-bridge-approve recipe-standing <id> --sha256 <hash>`. The command shows the code first. It is tied to the id and the code hash. Saving, editing or deleting the recipe ends it. `recipe-revoke <id>` removes it. Look only mode still blocks it. Standing records live in `plans/standing/`, a folder tools cannot write. The `approval` field in the manifest is always `per_run`; the effective value comes from that record.
- Auto and Dev mode behave as for other write tools.

## Parameters

The manifest declares each one: `name`, `type` (`integer`, `number`, `string`, `boolean`), `unit`, `min`, `max`, `required`, `default`, and for strings `enum` and `max_length`. The server checks them, fills defaults and sends the values as one JSON string, `PARAMS_JSON`, set on a line before your code. The script reads it with `load_params()`. Values are never written into the code, so they cannot change the hash or add code.

## Writing a recipe

The script gets the same prelude as the check tools: `doc`, `summary()`, `row()`, `info()`, `fail()`, `meta()`, `eid()`, `ename()`, `run_main()`. End with `__output__ = run_main(main)`. Results use the usual contract (`summary`, `rows`, `fails`, `limits`). A write recipe opens its own transaction and may call `meta("changed_ids", "1,2")`. No `from __future__` imports. See `modules/revit_recipes/starter/` for examples.

## Not verified live

`load_params()` fallback for IronPython builds without `json`, the starter scripts against a real model, and write-mode behaviour of a saved recipe.
