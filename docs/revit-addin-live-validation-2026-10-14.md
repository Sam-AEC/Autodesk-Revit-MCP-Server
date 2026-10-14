# Revit 2024 live validation, 14 October 2026

The new add-in was tested in the owner's running Revit 2024 copy through the authenticated panel backend. These were bounded,
read-only smoke checks, not a whole-model audit or mutating acceptance suite. No project transaction was opened.

## Build and runtime

- Add-in and companion server: `1.4.0`; Revit build: `24.3.10.22`.
- Loaded assembly file time matched the verified build, `2026-10-14T08:11:26.2243198Z`; `revit.get_context` is supported.
- Dev mode was on, with no expiry, an idle queue and no context warnings.
- IronPython `2.7.12.0`: `json`, `time` and `collections` executed successfully; the packaged standard library was available.
- Before and after the checks: **202,521 non-type elements and 2,087 Revit warnings**. The read runner reported zero model changes.

## Native read checks

| Check | Measured outcome | Limit |
|---|---|---|
| Wall joins | One wall, two ends; both free by the wall's join setting | Does not establish joins for the project |
| Naming/parameters | One scoped wall inspected, no reported failures | No project-wide naming or parameter acceptance |
| Openings | Door `3730761`: bottom measured 0.06 m below its host wall base | A model finding, not a confirmed tool bug; cut/swing checks were intentionally disabled |
| Roofs | Actual `RoofBase` `4380798` inspected; four open-edge/parapet findings | Coverage remained explicitly unverified without expected footprint data; design intent was not checked |
| Family probe, after fix | `AMB2_HeatPump`: one type, one instance, zero nested instances, seven connectors, zero reported problems | Shallow mode correctly remains unverified for family contents; deep mode passed |
| MEP system report | One scoped pipe: one system, no reported open ends or mismatches | Does not establish whole-project topology or engineering sizing |
| Documentation inventory | 164 views, 13 sheets, 40 schedules, 88 view templates | Listing only; no creation, layout or export acceptance |
| Read-mode guard | A script mentioning `Transaction` was refused before execution | Refusal currently returns HTTP 500, noted below |

## Bugs and quirks found

| ID | Evidence | Status / next action |
|---|---|---|
| LIVE-01: family type-name access | `revit_probe_family` failed with `AttributeError: Name` on a loaded family symbol under IronPython | **Fixed and verified live.** Read `SYMBOL_NAME_PARAM` first, then safe fallbacks. All three symbol-name sites use the helper; unavailable names produce `UNVERIFIED_TYPE_NAME`. Added six behavioral regressions; 150 focused tests passed. Updated the installed server wheel and repeated shallow/deep native probes successfully. |
| LIVE-02: stale chat connection after Revit restart | The existing chat MCP process retained the old endpoint and reported connection refused/server 1.2.1; the fresh panel backend reported the correct loaded build/server 1.4.0 | **Open.** Reconnect the chat MCP process. Future work should refresh stale instance routing and distinguish an unreachable session from an outdated add-in. This did not prevent authenticated panel checks. |
| LIVE-03: refusal status code | Read-mode transaction rejection returned a correct refusal message with HTTP 500 | **Open, minor.** The guard worked and model counts stayed unchanged; classify validation/refusal responses separately from server failures. |
| Roof-category scope | The first element in `OST_Roofs` was a `FamilyInstance`, not a `RoofBase`; the roof audit refused that scope | **Expected scope limitation.** Select actual roof elements; a category name alone is not proof of API element type. The audit subsequently ran on a `RoofBase`. |
| Default roof/opening rules | The sample roof lacked expected coverage data and the opening had a below-host-base offset | **Needs design context.** Findings are measurements under the tool's rules, not a declaration that existing content must be changed. No foreign content was modified. |

## Remaining acceptance

Creation, rollback, modal-failure handling, real view/sheet/schedule layouts, export files, job timeout/recovery and complete MEP
or geometry acceptance still need the explicitly requested scratch-project suite. Read-only smoke success cannot replace that suite.
The initial automated suite passed **1,752 tests, with 17 skips**; after LIVE-01, **150 focused tests** passed, including the new regressions.

Detailed responses are saved locally under `artifacts/bridge-upgrade-verification/`: `live-context.json`, `live-runtime.json`,
`live-read-checks.json`, `live-extra-checks.json` and `live-family-hotfix.json`. See [the upgrade handoff](bridge-upgrade-handoff.md)
and [the preflight prompt](prompts/revit-agent-preflight-and-verify.md) for continuation rules.
