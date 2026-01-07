param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$distDir = "$PSScriptRoot\..\dist\RevitMCP"
Write-Host "Creating distribution package: $distDir" -ForegroundColor Cyan

# Clean and create dist directory
Remove-Item $distDir -Recurse -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $distDir | Out-Null

# Build C# for both 2024 and 2025
Write-Host "`nBuilding C# add-in for Revit 2024 and 2025..." -ForegroundColor Yellow
foreach ($year in @("2024", "2025")) {
    & "$PSScriptRoot\build-addin.ps1" -RevitVersion $year -Configuration Release

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build failed for Revit $year"
        exit $LASTEXITCODE
    }

    $binDir = "$distDir\bin\$year"
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null

    $sourcePath = "$PSScriptRoot\..\packages\revit-bridge-addin\bin\Release\$year"
    if (Test-Path $sourcePath) {
        Copy-Item "$sourcePath\*" $binDir -Recurse -Force
        Write-Host "  Copied binaries for Revit $year" -ForegroundColor Green
    } else {
        Write-Warning "Build output not found at $sourcePath"
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
        } else {
            Write-Warning "PyInstaller build failed, falling back to wheel"
        }
    }

    # Always create wheel as fallback
    Write-Host "  Building Python wheel..." -ForegroundColor Cyan
    python -m build --wheel --outdir $serverDir
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Created Python wheel" -ForegroundColor Green
    }
} finally {
    Pop-Location
}

# Copy add-in manifests
Write-Host "`nCopying add-in manifests..." -ForegroundColor Yellow
$addinDir = "$distDir\addin"
New-Item -ItemType Directory -Path $addinDir -Force | Out-Null
Copy-Item "$PSScriptRoot\..\packages\revit-bridge-addin\RevitBridge.addin" $addinDir -Force
Write-Host "  Copied RevitBridge.addin" -ForegroundColor Green

# Create default config
Write-Host "`nCreating default configuration..." -ForegroundColor Yellow
$configDir = "$distDir\config"
New-Item -ItemType Directory -Path $configDir -Force | Out-Null

$defaultConfig = @{
    version = $Version
    bridge = @{
        host = "127.0.0.1"
        port = 3000
        use_https = $false
    }
    server = @{
        mode = "bridge"
        workspace = @("C:\RevitProjects", "$env:USERPROFILE\Documents")
    }
}

$defaultConfig | ConvertTo-Json -Depth 10 | Set-Content "$configDir\default.json"
Write-Host "  Created default.json" -ForegroundColor Green

# Create README for distribution
$distReadme = @"
# RevitMCP Distribution Package v$Version

This package contains the RevitMCP Bridge add-in and MCP server.

## Installation

### Quick Install (Revit 2024)
``````powershell
.\install.ps1 -RevitVersion 2024
``````

### Manual Install
1. Copy bin\{year}\* to C:\ProgramData\RevitMCP\bin\
2. Copy addin\RevitBridge.addin to C:\ProgramData\Autodesk\Revit\Addins\{year}\
3. Restart Revit

## Verify Installation
1. Start Revit
2. In PowerShell: ``curl http://localhost:3000/health``
3. Should return: ``{"status":"healthy","revit_version":"2024",...}``

## Run MCP Server
``````powershell
# If using standalone exe:
.\server\revit_mcp_server.exe

# If using Python wheel:
pip install server\revit_mcp_server-*.whl
python -m revit_mcp_server
``````

## Documentation
- README: ../README.md
- Security: ../docs/security.md
- Copilot Integration: ../docs/copilot-integration.md

## Support
https://github.com/Sam-AEC/Autodesk-Revit-MCP-Server/issues
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
Write-Host "  1. Test installation: .\scripts\install.ps1 -RevitVersion 2024" -ForegroundColor White
Write-Host "  2. Create MSI: Build WiX installer from dist\ folder" -ForegroundColor White
Write-Host "  3. Create release: Compress to RevitMCP-$Version.zip" -ForegroundColor White
