<#
.SYNOPSIS
  Prints the commands and prompts for the missing-Mark demo, step by step.

.DESCRIPTION
  This script records nothing and does not talk to Revit. It checks that the
  local tools are there and prints what to type, in order, so the screen
  recording follows docs/demo-runbook.md exactly. Run it in a second window
  while you record the first. Shot numbers match scripts/demo/shot-list.md.

  Everything here is UNVERIFIED against a live Revit until a run matches the
  runbook counts twice.

.PARAMETER Step
  Print one step (0 to 8, or R for the rejected-plan run). Default: all.

.EXAMPLE
  powershell -File scripts\demo\demo-commands.ps1 -Step 3
#>
param([string]$Step = "all")

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")

function Show-Step([string]$Id, [string]$Title, [string[]]$Lines) {
    if ($Step -ne "all" -and $Step -ne $Id) { return }
    Write-Host ""
    Write-Host "== Step $Id : $Title" -ForegroundColor Cyan
    $Lines | ForEach-Object { Write-Host "   $_" }
}

# Preflight: report only, change nothing.
Write-Host "Preflight (nothing is changed)" -ForegroundColor Yellow
foreach ($cmd in "python", "aec-model-bridge-approve") {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    Write-Host ("   {0,-26} {1}" -f $cmd, $(if ($found) { "found" } else { "NOT FOUND" }))
}
$fixture = Join-Path $repo "fixtures\canonical-model\generated\canonical_test_model.rvt"
Write-Host ("   {0,-26} {1}" -f "fixture model", $(if (Test-Path $fixture) { "found" } else { "not generated yet (Step 0)" }))
Write-Host ("   {0,-26} {1}" -f "approval mode", $(if ($env:MCP_REVIT_APPROVAL_MODE) { $env:MCP_REVIT_APPROVAL_MODE } else { "default (ask_first)" }))
if ($env:MCP_REVIT_APPROVAL_MODE -eq "auto") {
    Write-Warning "MCP_REVIT_APPROVAL_MODE=auto turns the human check off. Do not record the demo like this."
}
Write-Host "   Write down: Revit version, git commit ($(git -C $repo rev-parse --short HEAD)), date, document name."

Show-Step "0" "Build the fixture (Revit open, add-in loaded, throwaway copy)" @(
    "python scripts\revit\generate_canonical_test_model.py",
    "Expect: last 12 doors have no Mark, last 3 rooms have no Number."
)
Show-Step "1" "Snapshot (not recorded)" @(
    'Prompt: "Take a snapshot of the active model."   Tool: revit_extract_snapshot',
    "Keep the snapshot_id."
)
Show-Step "2" "Ask   [shot 1]" @(
    'Prompt: "Run the core QA check on that snapshot and list the issues."',
    "Tools: qaqc_checker_run_check (rule pack core), then qaqc_checker_list_issues with doc_guid and status=open",
    "Expect: door_missing_mark 12, room_missing_number 3."
)
Show-Step "3" "Plan   [shot 2]" @(
    'Prompt: "Propose a unique Mark for each of the 12 doors without one, using the pattern D-101 to D-112. Show me the exact values before anything is changed."',
    "Tool: plan_actions, one revit_set_parameter_value per door.",
    "Expect: state pending, 12 actions, 12 distinct values."
)
Show-Step "4" "Preview and review   [shot 3]" @(
    "Panel: Plans tab, Refresh. Read the 12 actions.",
    "Terminal: aec-model-bridge-approve list",
    "Terminal: aec-model-bridge-approve show <plan_id>"
)
Show-Step "4b" "Blocked until approved   [shot 4]" @(
    'Prompt: "Run the plan."',
    "Expect: execute_plan refused, plan not approved. Nothing changes."
)
Show-Step "5" "Approve   [shot 5]" @(
    "Panel: Plans tab, Approve.   Or: aec-model-bridge-approve approve <plan_id>",
    "Only the person approves. The assistant cannot."
)
Show-Step "6" "Execute   [shot 6]  WRITES: throwaway copy only" @(
    'Prompt: "The plan is approved. Run it."   Tool: execute_plan',
    "Expect: 12 actions executed."
)
Show-Step "7" "Verify   [shot 7]" @(
    "New snapshot (Step 1 again), rerun the check on the NEW id.",
    "Expect: door_missing_mark 0, room_missing_number 3."
)
Show-Step "8" "Undo   [shot 8, optional]" @(
    "Revit: Ctrl+Z once per door (12 times), then a fresh snapshot: 12 and 3 again.",
    "plan_revert is expected to refuse here (the doors had no Mark before)."
)
Show-Step "R" "Rejected-plan run (no model writes)" @(
    "Steps 1 to 4, then: aec-model-bridge-approve reject <plan_id>",
    'Prompt: "Run it anyway."   Expect: execute_plan refuses, plan is rejected.',
    "New snapshot and check: still 12 and 3."
)

Write-Host ""
Write-Host "Done. Nothing was recorded or changed." -ForegroundColor Green
