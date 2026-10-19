param(
    [string]$Version = (Get-Content (Join-Path $PSScriptRoot '..\VERSION') -Raw).Trim(),
    [string]$RevitVersion = "All"
)

$ErrorActionPreference = "Stop"

# Path Guard: Prevent Execution in System32 or Windows
if ($PSScriptRoot -like "*C:\Windows*") {
    Write-Error "Dangerous path detected: $PSScriptRoot"
    Write-Error "Please clone the repo to a safe location (e.g., $env:USERPROFILE\src) and run from there."
    exit 1
}

$distDir = "$PSScriptRoot\..\dist\AECModelBridge"
Write-Host "Creating distribution package: $distDir" -ForegroundColor Cyan

# Clean dist directory only if building everything or if it doesn't exist
if (-not (Test-Path $distDir)) {
    New-Item -ItemType Directory -Path $distDir -Force | Out-Null
}

# Define versions to build
$targetFrameworks = @{
    "2024" = "net48"
    "2025" = "net8.0-windows"
    "2026" = "net8.0-windows"
    "2027" = "net10.0-windows"
}
$versionsToBuild = @("2024", "2025", "2026", "2027")
if ($RevitVersion -ne "All") {
    if ($versionsToBuild -notcontains $RevitVersion) {
        Write-Error "Unsupported Revit version: $RevitVersion. Supported: $($versionsToBuild -join ', ')"
        exit 1
    }
    $versionsToBuild = @($RevitVersion)
}

# Build C# add-in
Write-Host "`nBuilding C# add-in for: $($versionsToBuild -join ', ')..." -ForegroundColor Yellow

foreach ($year in $versionsToBuild) {
    Write-Host "  Building for Revit $year..." -ForegroundColor Cyan
    & "$PSScriptRoot\build-addin.ps1" -RevitVersion $year -Configuration Release

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build failed for Revit $year"
        exit $LASTEXITCODE
    }

    $binDir = "$distDir\bin\$year"
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null

    $sourcePath = "$PSScriptRoot\..\packages\revit-bridge-addin\bin\Release\$year"
    $sourcePath = Join-Path $sourcePath $targetFrameworks[$year]

    if (Test-Path $sourcePath) {
        Copy-Item "$sourcePath\*" $binDir -Recurse -Force
        $nonWindowsRuntimes = Join-Path $binDir "runtimes"
        if (Test-Path $nonWindowsRuntimes) {
            Remove-Item -LiteralPath $nonWindowsRuntimes -Recurse -Force
        }
        Write-Host "    Copied binaries for Revit $year" -ForegroundColor Green
    }
    else {
        Write-Warning "    Build output not found at $sourcePath"
    }
}

# Build Python package with PyInstaller (if available)
Write-Host "`nPackaging Python MCP server..." -ForegroundColor Yellow
$serverDir = "$distDir\server"
New-Item -ItemType Directory -Path $serverDir -Force | Out-Null

Push-Location "$PSScriptRoot\..\packages\mcp-server-revit"
try {
    # Try PyInstaller first
    $pyInstallerAvailable = (Get-Command pyinstaller -ErrorAction SilentlyContinue) -ne $null

    if ($pyInstallerAvailable) {
        Write-Host "  Building standalone executable with PyInstaller..." -ForegroundColor Cyan
        pyinstaller --onefile --name revit_mcp_server --distpath $serverDir src/revit_mcp_server/__main__.py
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Created revit_mcp_server.exe" -ForegroundColor Green
        }
        else {
            Write-Warning "PyInstaller build failed, falling back to wheel"
        }
    }

    # Always create wheel as fallback
    Write-Host "  Building Python wheel..." -ForegroundColor Cyan
    python -m build --wheel --outdir $serverDir
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Created Python wheel" -ForegroundColor Green
    }
}
finally {
    Pop-Location
}

# Bundle portable Python runtime
if (Test-Path "$PSScriptRoot\bundle-python.ps1") {
    & "$PSScriptRoot\bundle-python.ps1" -DistPath $distDir
}

# Copy add-in manifests
Write-Host "`nCopying add-in manifests..." -ForegroundColor Yellow
$addinDir = "$distDir\addin"
New-Item -ItemType Directory -Path $addinDir -Force | Out-Null
Copy-Item "$PSScriptRoot\..\packages\revit-bridge-addin\AECModelBridge.addin" $addinDir -Force
Write-Host "  Copied AECModelBridge.addin" -ForegroundColor Green

# Copy installer entrypoints and helper scripts into the distribution package
Copy-Item "$PSScriptRoot\install.ps1" "$distDir\install.ps1" -Force
$distScripts = Join-Path $distDir "scripts"
New-Item -ItemType Directory -Path $distScripts -Force | Out-Null
Copy-Item "$PSScriptRoot\*" $distScripts -Recurse -Force
Write-Host "  Copied install.ps1 and helper scripts" -ForegroundColor Green

# Include license terms and required notices in every distribution.
Copy-Item "$PSScriptRoot\..\LICENSE" "$distDir\LICENSE" -Force
Copy-Item "$PSScriptRoot\..\NOTICE" "$distDir\NOTICE" -Force
Copy-Item "$PSScriptRoot\..\LICENSING.md" "$distDir\LICENSING.md" -Force
$distLicenses = Join-Path $distDir "LICENSES"
New-Item -ItemType Directory -Path $distLicenses -Force | Out-Null
Copy-Item "$PSScriptRoot\..\LICENSES\*" $distLicenses -Recurse -Force
Write-Host "  Copied licensing documents" -ForegroundColor Green

# Create default config
Write-Host "`nCreating default configuration..." -ForegroundColor Yellow
$configDir = "$distDir\config"
New-Item -ItemType Directory -Path $configDir -Force | Out-Null

$defaultConfig = @{
    version = $Version
    bridge  = @{
        host      = "127.0.0.1"
        port      = 3000
        use_https = $false
    }
    server  = @{
        mode      = "bridge"
        # Literal %USERPROFILE%: expanding it here baked the build machine's profile path into the release.
        workspace = @('C:\RevitProjects', '%USERPROFILE%\Documents')
    }
}

$defaultConfig | ConvertTo-Json -Depth 10 | Set-Content "$configDir\default.json"
Write-Host "  Created default.json" -ForegroundColor Green

# Create README for distribution
$distReadme = @"
# AEC Model Bridge Distribution Package v$Version

This package contains AEC Model Bridge for Revit software and its MCP server.

## Installation

This archive contains these Revit binaries:

``````
bin\$($versionsToBuild -join "`nbin\")
``````

Check the available version folders and install the one matching Revit:

``````powershell
Get-ChildItem .\bin -Directory
$RevitVersion = Read-Host "Choose one of the listed Revit years"
.\install.ps1 -RevitVersion $RevitVersion
``````

The installer writes binaries to
``C:\ProgramData\AECModelBridge\bin\{year}\`` and creates the matching manifest.

## Verify Installation
1. Start Revit
2. In PowerShell, read ``%LOCALAPPDATA%\AECModelBridge\registry\revit-*.json`` and call the listed ``/health`` endpoint.
3. The response should report ``healthy`` and the running Revit version.

## Run MCP Server
``````powershell
# If using standalone exe:
.\server\revit_mcp_server.exe

# If using Python wheel:
pip install server\aec_model_bridge-*.whl
python -m revit_mcp_server
``````

## Documentation
- README: ../README.md
- Security: ../docs/security.md
- MCP clients: ../docs/marketplaces.md

## Support
https://github.com/Sam-AEC/aec-model-bridge/issues

## License
Version 1.1.0 and later is available under your choice of GPL-3.0-or-later with
the AEC Model Bridge Revit Linking Exception, or a separate commercial license.
Commercial terms are available for proprietary distribution and negotiated
requirements. See LICENSING.md.

## Trademark Notice
AEC Model Bridge is independent and is not affiliated with Autodesk.
Autodesk and Revit are trademarks of the Autodesk group of companies.
"@

$distReadme | Set-Content "$distDir\README.txt"

Write-Host "`nPackage created successfully!" -ForegroundColor Green
Write-Host "Location: $distDir" -ForegroundColor Cyan
Write-Host "`nContents:" -ForegroundColor Yellow
Get-ChildItem $distDir -Recurse -File | ForEach-Object {
    $relativePath = $_.FullName.Replace($distDir, "").TrimStart("\")
    Write-Host "  $relativePath" -ForegroundColor Gray
}

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "  1. Test installation: .\scripts\install.ps1 -RevitVersion $RevitVersion" -ForegroundColor White
Write-Host "  2. Create MSI: Build WiX installer from dist\ folder" -ForegroundColor White
Write-Host "  3. Create release: Compress to aec-model-bridge-$Version.zip" -ForegroundColor White
exit 0
