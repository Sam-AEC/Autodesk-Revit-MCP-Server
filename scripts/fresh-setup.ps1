$ErrorActionPreference = "Stop"

Write-Host "== RevitMCP Local Setup ==" -ForegroundColor Cyan
$RepoDir = (Get-Item -Path $PSScriptRoot\..).FullName
Write-Host "Target: $RepoDir" -ForegroundColor Gray

# 1) Stop common processes
$procNames = @("Revit", "dotnet", "msbuild", "vbcscompiler", "devenv")
foreach ($p in $procNames) {
  Get-Process -Name $p -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

# 2) Clean artifacts
# Explicitly remove known build folders first (sometimes git clean fails on locked/permissioned build files)
Write-Host "Removing dist/bin/obj folders..." -ForegroundColor Yellow
$foldersToClean = Get-ChildItem -Path $RepoDir -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -in "bin","obj","dist" }
foreach ($folder in $foldersToClean) {
    Remove-Item $folder.FullName -Recurse -Force -ErrorAction SilentlyContinue 
}

# Then git clean for anything else
Write-Host "Cleaning remaining artifacts (git clean -fdx)..." -ForegroundColor Yellow
Set-Location $RepoDir
# Exclude .env, .vscode, AND this script itself (fresh-setup.ps1)
git clean -fdx -e .env -e .vscode -e scripts/fresh-setup.ps1

# 3) Submodules
Write-Host "Updating submodules..." -ForegroundColor Yellow
git submodule update --init --recursive

# 4) Build Add-in
Write-Host "Building Add-in..." -ForegroundColor Yellow
& "$PSScriptRoot\build-addin.ps1" -RevitVersion 2024

# 5) Package
Write-Host "Packaging..." -ForegroundColor Yellow
$version = "1.0.0"
# Try to get version from git tag if available
try {
    $gitTag = git describe --tags --abbrev=0
    if ($gitTag) { $version = $gitTag -replace "^[vV]", "" }
} catch {}

& "$PSScriptRoot\package.ps1" -Version $version

Write-Host "`n✅ Setup Complete!" -ForegroundColor Green
