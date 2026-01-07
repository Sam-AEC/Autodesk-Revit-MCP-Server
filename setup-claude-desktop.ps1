param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "`n" -NoNewline
Write-Host "="*70 -ForegroundColor Cyan
Write-Host "RevitMCP - Claude Desktop Setup" -ForegroundColor Cyan
Write-Host "="*70 -ForegroundColor Cyan
Write-Host ""

# Check if Claude Desktop is installed
$claudeConfigDir = "$env:APPDATA\Claude"
$claudeConfigFile = "$claudeConfigDir\claude_desktop_config.json"

if (-not (Test-Path $claudeConfigDir)) {
    Write-Host "ERROR: Claude Desktop not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Claude Desktop first:" -ForegroundColor Yellow
    Write-Host "  https://claude.ai/download" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "[1/5] Checking prerequisites..." -ForegroundColor Yellow

# Check Python
Write-Host "  - Checking Python installation..."
try {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    $pythonVersion = python --version 2>&1
    Write-Host "    Found: $pythonVersion at $pythonPath" -ForegroundColor Green
} catch {
    Write-Host "    ERROR: Python not found!" -ForegroundColor Red
    exit 1
}

# Check Revit bridge
Write-Host "  - Checking Revit bridge add-in..."
$addinFile = "$env:APPDATA\Autodesk\Revit\Addins\2024\RevitBridge.addin"
if (Test-Path $addinFile) {
    Write-Host "    Found: RevitBridge add-in installed" -ForegroundColor Green
} else {
    Write-Host "    WARNING: RevitBridge add-in not found at $addinFile" -ForegroundColor Yellow
    Write-Host "    Make sure the Revit add-in is installed first!" -ForegroundColor Yellow
}

# Install Python package
Write-Host "`n[2/5] Installing RevitMCP Python package..." -ForegroundColor Yellow
Push-Location "$PSScriptRoot\packages\mcp-server-revit"
try {
    pip install -e . --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Package installed successfully" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Failed to install package" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

# Create config
Write-Host "`n[3/5] Creating Claude Desktop configuration..." -ForegroundColor Yellow

$config = @{
    mcpServers = @{
        revit = @{
            command = $pythonPath
            args = @(
                "-m",
                "revit_mcp_server.mcp_server"
            )
            env = @{
                MCP_REVIT_WORKSPACE_DIR = "$env:USERPROFILE\Documents"
                MCP_REVIT_ALLOWED_DIRECTORIES = "$env:USERPROFILE\Documents"
                MCP_REVIT_BRIDGE_URL = "http://127.0.0.1:3000"
                MCP_REVIT_MODE = "bridge"
            }
        }
    }
}

# Check if config already exists
$configExists = Test-Path $claudeConfigFile
if ($configExists) {
    Write-Host "  Existing config found at: $claudeConfigFile" -ForegroundColor Yellow

    if (-not $Force) {
        Write-Host ""
        Write-Host "  Options:" -ForegroundColor Cyan
        Write-Host "    [B] Backup existing and create new config" -ForegroundColor White
        Write-Host "    [M] Merge with existing config (add 'revit' server)" -ForegroundColor White
        Write-Host "    [O] Overwrite existing config" -ForegroundColor White
        Write-Host "    [C] Cancel" -ForegroundColor White
        Write-Host ""
        $choice = Read-Host "  Choose an option [B/M/O/C]"

        switch ($choice.ToUpper()) {
            "B" {
                $backupFile = "$claudeConfigFile.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
                Copy-Item $claudeConfigFile $backupFile
                Write-Host "  Backed up to: $backupFile" -ForegroundColor Green
                $config | ConvertTo-Json -Depth 10 | Set-Content $claudeConfigFile
            }
            "M" {
                $existing = Get-Content $claudeConfigFile | ConvertFrom-Json
                if (-not $existing.mcpServers) {
                    $existing | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value @{}
                }
                $existing.mcpServers | Add-Member -MemberType NoteProperty -Name "revit" -Value $config.mcpServers.revit -Force
                $existing | ConvertTo-Json -Depth 10 | Set-Content $claudeConfigFile
                Write-Host "  Merged 'revit' server into existing config" -ForegroundColor Green
            }
            "O" {
                $config | ConvertTo-Json -Depth 10 | Set-Content $claudeConfigFile
                Write-Host "  Overwritten with new config" -ForegroundColor Green
            }
            "C" {
                Write-Host "  Cancelled" -ForegroundColor Yellow
                exit 0
            }
            default {
                Write-Host "  Invalid choice. Cancelled." -ForegroundColor Red
                exit 1
            }
        }
    } else {
        # Force mode: backup and overwrite
        $backupFile = "$claudeConfigFile.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item $claudeConfigFile $backupFile
        Write-Host "  Backed up to: $backupFile" -ForegroundColor Green
        $config | ConvertTo-Json -Depth 10 | Set-Content $claudeConfigFile
    }
} else {
    # No existing config, create new
    New-Item -ItemType Directory -Path $claudeConfigDir -Force | Out-Null
    $config | ConvertTo-Json -Depth 10 | Set-Content $claudeConfigFile
    Write-Host "  Created new config at: $claudeConfigFile" -ForegroundColor Green
}

# Test MCP server
Write-Host "`n[4/5] Testing MCP server..." -ForegroundColor Yellow
Write-Host "  Starting server (will timeout after 3 seconds - this is expected)..."

$testResult = $false
try {
    $job = Start-Job -ScriptBlock {
        param($pythonPath, $repoRoot)
        Set-Location $repoRoot
        & $pythonPath -m revit_mcp_server.mcp_server 2>&1
    } -ArgumentList $pythonPath, $PSScriptRoot

    Start-Sleep -Seconds 3
    $job | Stop-Job
    $output = Receive-Job $job
    Remove-Job $job

    if ($output -match "error" -and $output -notmatch "Bridge") {
        Write-Host "  ERROR: Server failed to start" -ForegroundColor Red
        Write-Host "  Output: $output" -ForegroundColor Red
    } else {
        Write-Host "  Server started successfully (will connect to Revit when needed)" -ForegroundColor Green
        $testResult = $true
    }
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

# Final instructions
Write-Host "`n[5/5] Setup complete!" -ForegroundColor Green

Write-Host ""
Write-Host "="*70 -ForegroundColor Cyan
Write-Host "NEXT STEPS" -ForegroundColor Cyan
Write-Host "="*70 -ForegroundColor Cyan
Write-Host ""

Write-Host "1. RESTART Claude Desktop" -ForegroundColor Yellow
Write-Host "   - Completely close Claude Desktop" -ForegroundColor White
Write-Host "   - Reopen it" -ForegroundColor White
Write-Host ""

Write-Host "2. START REVIT" -ForegroundColor Yellow
Write-Host "   - Open Revit 2024" -ForegroundColor White
Write-Host "   - Open or create a project" -ForegroundColor White
Write-Host "   - The RevitMCP Bridge will start automatically" -ForegroundColor White
Write-Host ""

Write-Host "3. VERIFY IN CLAUDE DESKTOP" -ForegroundColor Yellow
Write-Host "   - Look for the plug icon in Claude Desktop" -ForegroundColor White
Write-Host "   - You should see 'revit' server connected" -ForegroundColor White
Write-Host "   - Tools like 'revit_health', 'revit_create_wall', etc. should be available" -ForegroundColor White
Write-Host ""

Write-Host "4. TEST IT OUT" -ForegroundColor Yellow
Write-Host "   Try asking Claude:" -ForegroundColor White
Write-Host "   > 'Is Revit running? What project is open?'" -ForegroundColor Cyan
Write-Host "   > 'Create a 30ft by 25ft house with 10ft tall walls'" -ForegroundColor Cyan
Write-Host ""

Write-Host "="*70 -ForegroundColor Cyan
Write-Host ""

Write-Host "Configuration file: $claudeConfigFile" -ForegroundColor Gray
Write-Host "Full guide: $PSScriptRoot\CLAUDE_DESKTOP_SETUP.md" -ForegroundColor Gray
Write-Host ""

Write-Host "Happy building with Claude + Revit!" -ForegroundColor Green
Write-Host ""
