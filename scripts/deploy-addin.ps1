<#
.SYNOPSIS
    Deploys the WHOLE add-in output folder (DLLs, IronPython.Modules.dll, Lib\, panel\, runtimes\) to
    C:\ProgramData\AECModelBridge\bin\<year>\, the folder the Revit manifest and the installer use.

.DESCRIPTION
    Copying only AECModelBridge.dll leaves a stale or incomplete add-in: Lib\ (the IronPython standard
    library) stays missing and the next Revit start runs old helper DLLs. This script:

      1. builds the add-in (or takes an existing build folder with -BuildDir);
      2. refuses to run while Revit.exe is running, unless -Force;
      3. backs up the previous folder to <InstallRoot>\..\backup\<year>-<timestamp> (last 5 kept);
      4. mirrors the build output into the target (same exclusions as the installer: the Revit API DLLs
         that Revit supplies itself);
      5. verifies that AECModelBridge.dll in the target has the build's file time and size, that Lib\ is
         present, and that every built file arrived; on a mismatch it restores the backup and exits 1.

    It does not touch the Revit manifest unless -InstallManifest is given (then scripts\install-addin.ps1
    runs afterwards). Restart Revit after deploying; call revit_get_context to confirm the loaded build.

.EXAMPLE
    .\scripts\deploy-addin.ps1 -RevitYear 2024
    .\scripts\deploy-addin.ps1 -RevitYear 2024 -BuildDir C:\tmp\build-trust\2024
    .\scripts\deploy-addin.ps1 -RevitYear 2024 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("2024", "2025", "2026", "2027")]
    [string]$RevitYear = "2024",
    # An existing add-in output folder (for example the -o folder of a dotnet build). Default: build here.
    [string]$BuildDir,
    # Parent of the per-year folders. The installer and manifest use C:\ProgramData\AECModelBridge\bin.
    [string]$InstallRoot = "C:\ProgramData\AECModelBridge\bin",
    [switch]$Force,
    [switch]$InstallManifest
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$project = Join-Path $repoRoot "packages\revit-bridge-addin\RevitBridge.csproj"
$framework = switch ($RevitYear) {
    "2024" { "net48" }
    "2027" { "net10.0-windows" }
    default { "net8.0-windows" }
}
# What the installer leaves out of {app}\bin\<year>: Revit loads these from its own folder.
$excludedFiles = @("RevitAPI.dll", "RevitAPIUI.dll", "AdWindows.dll", "AdskLicensingSDK_*.dll")

# 1. The build folder -------------------------------------------------------------------------
if (-not $BuildDir) {
    Write-Host "Building the Revit $RevitYear add-in (Release)..."
    & dotnet build $project -c Release "-p:RevitVersion=$RevitYear" -clp:ErrorsOnly -v:q
    if ($LASTEXITCODE -ne 0) { throw "Revit $RevitYear add-in build failed." }
    $BuildDir = Join-Path $repoRoot "packages\revit-bridge-addin\bin\Release\$RevitYear\$framework"
}
$BuildDir = [System.IO.Path]::GetFullPath($BuildDir)
$buildDll = Join-Path $BuildDir "AECModelBridge.dll"
foreach ($required in @("AECModelBridge.dll", "IronPython.dll", "IronPython.Modules.dll", "Lib\json\__init__.py")) {
    if (-not (Test-Path -LiteralPath (Join-Path $BuildDir $required))) {
        throw "Build folder $BuildDir is incomplete: $required is missing. Build the whole add-in (dotnet build ... -p:RevitVersion=$RevitYear) and pass its output folder."
    }
}
$built = Get-Item -LiteralPath $buildDll
Write-Host ("Build:   {0}  {1:N0} bytes  {2:u}" -f $buildDll, $built.Length, $built.LastWriteTimeUtc)

# 2. Revit must not hold the DLLs ---------------------------------------------------------------
$revit = @(Get-Process -Name "Revit" -ErrorAction SilentlyContinue)
if ($revit.Count -gt 0) {
    if (-not $Force) {
        throw "Revit.exe is running (PID $($revit.Id -join ', ')). Close Revit and run this again, or pass -Force to try anyway (locked files will fail the copy)."
    }
    Write-Warning "Revit.exe is running; -Force given. Files Revit has loaded cannot be replaced, and Revit keeps the old build until it restarts."
}

# 3. Target and backup --------------------------------------------------------------------------
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$target = Join-Path $InstallRoot $RevitYear
if ((Split-Path -Leaf $target) -ne $RevitYear -or $target.Length -lt 12) {
    throw "Refusing to deploy to an unexpected folder: $target"
}
if ($target.TrimEnd("\") -eq $BuildDir.TrimEnd("\")) { throw "The build folder and the target are the same folder." }
Write-Host "Target:  $target"

$backup = $null
if (Test-Path -LiteralPath $target) {
    $backupRoot = Join-Path (Split-Path -Parent $InstallRoot) "backup"
    $backup = Join-Path $backupRoot ("{0}-{1:yyyyMMdd-HHmmss}" -f $RevitYear, (Get-Date))
    if ($PSCmdlet.ShouldProcess($target, "Back up to $backup")) {
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        & robocopy $target $backup /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Backup of $target failed (robocopy exit $LASTEXITCODE). Nothing was changed." }
        Write-Host "Backup:  $backup"
        Get-ChildItem -LiteralPath $backupRoot -Directory -Filter "$RevitYear-*" |
            Sort-Object Name -Descending | Select-Object -Skip 5 |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    }
}

# 4. Mirror the whole folder ----------------------------------------------------------------------
function Restore-Backup {
    if ($backup -and (Test-Path -LiteralPath $backup)) {
        Write-Warning "Restoring the previous folder from $backup"
        & robocopy $backup $target /MIR /R:2 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    }
}

if ($PSCmdlet.ShouldProcess($target, "Mirror $BuildDir (including Lib\)")) {
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $arguments = @($BuildDir, $target, "/MIR", "/R:2", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XF") + $excludedFiles
    & robocopy @arguments | Out-Null
    $copyExit = $LASTEXITCODE
    if ($copyExit -ge 8) {
        Restore-Backup
        throw "Copy to $target failed (robocopy exit $copyExit); a file is probably locked by Revit. The previous folder was restored."
    }

    # 5. Verify ---------------------------------------------------------------------------------------
    $problems = @()
    $deployedDll = Join-Path $target "AECModelBridge.dll"
    if (-not (Test-Path -LiteralPath $deployedDll)) {
        $problems += "AECModelBridge.dll is missing in the target."
    }
    else {
        $deployed = Get-Item -LiteralPath $deployedDll
        if ($deployed.Length -ne $built.Length) { $problems += "DLL size differs: built $($built.Length), deployed $($deployed.Length)." }
        if ([math]::Abs(($deployed.LastWriteTimeUtc - $built.LastWriteTimeUtc).TotalSeconds) -gt 2) {
            $problems += "DLL file time differs: built $($built.LastWriteTimeUtc.ToString('u')), deployed $($deployed.LastWriteTimeUtc.ToString('u'))."
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $target "Lib\json\__init__.py"))) { $problems += "Lib\ was not deployed (IronPython standard library is missing)." }
    $excludeFilter = { param($name) foreach ($pattern in $excludedFiles) { if ($name -like $pattern) { return $true } } return $false }
    $missing = @(Get-ChildItem -LiteralPath $BuildDir -Recurse -File | Where-Object { -not (& $excludeFilter $_.Name) } | ForEach-Object {
            $relative = $_.FullName.Substring($BuildDir.TrimEnd("\").Length + 1)
            if (-not (Test-Path -LiteralPath (Join-Path $target $relative))) { $relative }
        })
    if ($missing.Count -gt 0) { $problems += "$($missing.Count) built file(s) did not arrive, for example: $(($missing | Select-Object -First 3) -join ', ')" }

    if ($problems.Count -gt 0) {
        Restore-Backup
        throw ("Verification failed, the previous folder was restored:`n  " + ($problems -join "`n  "))
    }
    $fileCount = @(Get-ChildItem -LiteralPath $target -Recurse -File).Count
    Write-Host ("Verified: AECModelBridge.dll {0:N0} bytes, {1:u}; Lib\ present; {2} files in {3}" -f $deployed.Length, $deployed.LastWriteTimeUtc, $fileCount, $target)

    if ($InstallManifest) {
        & (Join-Path $PSScriptRoot "install-addin.ps1") -RevitYear $RevitYear -AssemblyPath (Join-Path $target "AECModelBridge.dll")
    }
    Write-Host "Done. Restart Revit, then call revit_get_context and check that the add-in build matches the file time above."
}

