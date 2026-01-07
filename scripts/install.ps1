param(
    [string]$RevitVersion = "2024",
    [switch]$AllUsers,
    [string]$DistPath = "$PSScriptRoot\..\dist\RevitMCP"
)

$ErrorActionPreference = "Stop"

Write-Host "RevitMCP Installer" -ForegroundColor Cyan
Write-Host "==================`n" -ForegroundColor Cyan

# Verify dist package exists
if (-not (Test-Path $DistPath)) {
    Write-Error "Distribution package not found at: $DistPath`nRun .\scripts\package.ps1 first"
    exit 1
}

# Install binaries to ProgramData
Write-Host "Installing binaries..." -ForegroundColor Yellow
$targetBin = "C:\ProgramData\RevitMCP\bin"
New-Item -ItemType Directory -Path $targetBin -Force | Out-Null

$sourceBin = "$DistPath\bin\$RevitVersion"
if (-not (Test-Path $sourceBin)) {
    Write-Error "Binaries for Revit $RevitVersion not found in distribution package.`nAvailable versions: $((Get-ChildItem "$DistPath\bin" -Directory).Name -join ', ')"
    exit 1
}

Copy-Item "$sourceBin\*" $targetBin -Recurse -Force
Write-Host "  Installed to: $targetBin" -ForegroundColor Green

# Install add-in manifest
Write-Host "`nInstalling add-in manifest..." -ForegroundColor Yellow
$addinDir = if ($AllUsers) {
    "C:\ProgramData\Autodesk\Revit\Addins\$RevitVersion"
} else {
    "$env:APPDATA\Autodesk\Revit\Addins\$RevitVersion"
}

New-Item -ItemType Directory -Path $addinDir -Force | Out-Null
Copy-Item "$DistPath\addin\RevitBridge.addin" $addinDir -Force
Write-Host "  Installed to: $addinDir" -ForegroundColor Green

# Copy config (optional)
Write-Host "`nCopying default configuration..." -ForegroundColor Yellow
$configTarget = "C:\ProgramData\RevitMCP\config"
New-Item -ItemType Directory -Path $configTarget -Force | Out-Null
Copy-Item "$DistPath\config\default.json" $configTarget -Force
Write-Host "  Installed to: $configTarget\default.json" -ForegroundColor Green

# Installation summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "`nInstalled components:" -ForegroundColor Yellow
Write-Host "  Bridge DLL:    $targetBin\RevitBridge.dll"
Write-Host "  Add-in:        $addinDir\RevitBridge.addin"
Write-Host "  Config:        $configTarget\default.json"

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "  1. Restart Revit $RevitVersion" -ForegroundColor White
Write-Host "  2. Open a project in Revit" -ForegroundColor White
Write-Host "  3. Verify bridge: curl http://localhost:3000/health" -ForegroundColor White
Write-Host "  4. Expected response: {`"status`":`"healthy`",`"revit_version`":`"$RevitVersion`",...}" -ForegroundColor Gray

Write-Host "`nTo install MCP server:" -ForegroundColor Yellow
if (Test-Path "$DistPath\server\revit_mcp_server.exe") {
    Write-Host "  Run: $DistPath\server\revit_mcp_server.exe" -ForegroundColor White
} else {
    $wheel = Get-ChildItem "$DistPath\server\*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($wheel) {
        Write-Host "  pip install $($wheel.FullName)" -ForegroundColor White
        Write-Host "  python -m revit_mcp_server" -ForegroundColor White
    }
}

Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
Write-Host "  - Check Revit journal: %LOCALAPPDATA%\Autodesk\Revit\Autodesk Revit $RevitVersion\Journals\" -ForegroundColor Gray
Write-Host "  - Check bridge logs: %APPDATA%\RevitMCP\Logs\bridge.jsonl" -ForegroundColor Gray
Write-Host "  - Uninstall: Remove files from paths above" -ForegroundColor Gray
