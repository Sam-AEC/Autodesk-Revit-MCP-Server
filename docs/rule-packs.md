# Shareable QA/QC rule packs

Status: on the dev branch, not yet released.

A rule pack is a YAML file of QA/QC rules. A firm can keep its naming,
numbering and standards checks in one file, share it, and run it with
`qaqc_checker_run_check`.

## Where packs live

- Built-in packs ship with the server (for example `core`).
- User packs live in `<workspace>/rule_packs/<name>.yaml`. The workspace is the
  first allowed directory of the server.

`run_check(rule_pack="<name>")` and `list_rules(rule_pack="<name>")` resolve a
pack name in this order: built-in first, then the workspace `rule_packs/`
folder. A user pack cannot shadow a built-in. Names may only contain letters,
digits, `_`, `-` and `.`; paths are not accepted, so a pack name can never point
outside those two folders. Packs are re-validated every time they are loaded.

## Tools

| Tool | Reads/writes | What it does |
| --- | --- | --- |
| `qaqc_checker_list_rule_packs` | read-only | Lists built-in and user packs with rule count and validity. |
| `qaqc_checker_validate_rule_pack` | read-only | Schema-checks a YAML file (`path`) or a named pack (`rule_pack`). Returns `errors` and `warnings`, each with `rule_id`, `field` and `message`. Never executes rules. |
| `qaqc_checker_import_rule_pack` | writes a file | Validates `source_path` (inside the workspace) and copies it to `rule_packs/<name>.yaml`. Refuses invalid packs, built-in names, and existing packs unless `overwrite=true`. |
| `qaqc_checker_export_rule_pack` | writes a file | Copies a built-in or user pack to `destination` (a file or folder inside the workspace; default `exports/<name>.yaml`). Refuses to overwrite unless `overwrite=true`. |

All paths are checked with the workspace path-safety helper (symlinks are
resolved), so nothing is read or written outside the workspace.

## Rule format

```yaml
rules:
  - id: door_mark_missing          # required, unique, letters/digits/_-.
    severity: error                # required: error | warning | info
    category: Doors                # optional label
    description: "Door has no Mark."   # required, becomes the issue message
    filter:                        # optional; see operators below
      category: OST_Doors
      parameter: {name: Mark, empty: true}
    assertion: "element_count == 0"    # optional, this is the default
    fix_template: "Set the Mark on '{label}'."   # optional
```

### Operators the engine supports

Filter keys (all must match):

- `category`: a category such as `OST_Doors`, or a list of them.
- `placed`: `true` or `false`.
- `parameter`: `{name: <Parameter>, empty: true}` or `{name: <Parameter>, value: "<text>"}`.
  `value` is an exact text comparison.
- `workset`: exact workset name.
- `family_source`: matches family types by source (for example `inplace`).

Assertions:

- `element_count == 0`: every element that matches the filter is an issue.
- `all elements have <field>`: matched elements missing that top-level element
  field are issues.

The validator rejects anything else, with the list of supported names in the
message. There is no regular-expression operator and no uniqueness operator in
the engine today, so naming-pattern checks (for example "door Mark must match
`D-###`") and duplicate-number checks cannot be expressed yet. They are not
validated as "supported" and are not in the example pack.

## Example pack

[`rule_packs/examples/door-room-basics.yaml`](../rule_packs/examples/door-room-basics.yaml)
covers door Mark, unplaced doors and room Number. To use it:

1. Copy the file into your workspace, for example `<workspace>/door-room-basics.yaml`.
2. `qaqc_checker_validate_rule_pack` with `path` set to that file.
3. `qaqc_checker_import_rule_pack` with `source_path` set to that file.
4. `qaqc_checker_run_check` with `rule_pack="door-room-basics"`.

To share your own pack, call `qaqc_checker_export_rule_pack` and send the
resulting YAML file; the recipient imports it the same way.
