param(
    [string]$RevitVersion = "2024",
    [switch]$Install,
    [switch]$AllUsers
)

$ErrorActionPreference = "Stop"

# == Path Guard ==
if ($PSScriptRoot -like "*C:\Windows*") {
    Write-Host "CRITICAL ERROR: Dangerous execution path detected." -ForegroundColor Red
    Write-Host "You are running this script from: $PSScriptRoot" -ForegroundColor Red
    Write-Host "Please clone the repo to a safe user directory (e.g. $env:USERPROFILE\src) and run it from there." -ForegroundColor Gray
    exit 1
}

Write-Host "== RevitMCP Setup Master Script ==" -ForegroundColor Cyan
Write-Host "Target Revit Version: $RevitVersion" -ForegroundColor Gray

# == Config Loader ==
$configFile = "$PSScriptRoot\..\revitmcp.config.json"
if (Test-Path $configFile) {
    Write-Host "Loading config from: revitmcp.config.json" -ForegroundColor Green
    try {
        $config = Get-Content $configFile | ConvertFrom-Json
        if ($config.revitVersion) { $RevitVersion = $config.revitVersion }
    }
    catch {
        Write-Warning "Failed to parse config file. Using defaults."
    }
}

# == Step 1: Build ==
Write-Host "`n[Step 1/3] Building Add-in..." -ForegroundColor Yellow
$buildArgs = @{
    RevitVersion = $RevitVersion
}
& "$PSScriptRoot\build-addin.ps1" @buildArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed. Aborting."
    exit $LASTEXITCODE
}

# == Step 2: Package ==
Write-Host "`n[Step 2/3] Creating Distribution Package..." -ForegroundColor Yellow
$packageArgs = @{
    RevitVersion = $RevitVersion
}
& "$PSScriptRoot\package.ps1" @packageArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "Packaging failed. Aborting."
    exit $LASTEXITCODE
}

# == Step 3: Install (Optional) ==
if ($Install) {
    Write-Host "`n[Step 3/3] Installing..." -ForegroundColor Yellow
    $installArgs = @{
        RevitVersion = $RevitVersion
    }
    if ($AllUsers) { $installArgs.Add("AllUsers", $true) }
    
    & "$PSScriptRoot\install.ps1" @installArgs
}
else {
    Write-Host "`n[Step 3/3] Install skipped (use -Install to run)" -ForegroundColor Gray
    Write-Host "To install manually later:" -ForegroundColor Green
    Write-Host "  .\scripts\install.ps1 -RevitVersion $RevitVersion" -ForegroundColor White
}

Write-Host "`n✅ Setup Complete!" -ForegroundColor Green
