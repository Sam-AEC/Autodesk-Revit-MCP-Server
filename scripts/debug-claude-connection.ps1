Write-Host "`nRevitMCP - Claude Desktop Connection Debugger`n" -ForegroundColor Cyan

# 1. Check config file
Write-Host "[1] Checking Claude Desktop config..." -ForegroundColor Yellow
$configPath = "$env:APPDATA\Claude\claude_desktop_config.json"
if (Test-Path $configPath) {
    Write-Host "  Config file: EXISTS" -ForegroundColor Green
    Write-Host "  Location: $configPath" -ForegroundColor Gray

    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json

        if ($config.mcpServers.revit) {
            Write-Host "  Revit server: CONFIGURED" -ForegroundColor Green
            Write-Host "  Command: $($config.mcpServers.revit.command)" -ForegroundColor Gray

            # Test Python path
            $pythonPath = $config.mcpServers.revit.command
            if (Test-Path $pythonPath) {
                Write-Host "  Python executable: EXISTS" -ForegroundColor Green
            } else {
                Write-Host "  Python executable: NOT FOUND!" -ForegroundColor Red
                Write-Host "  Path: $pythonPath" -ForegroundColor Red
            }
        } else {
            Write-Host "  Revit server: NOT CONFIGURED" -ForegroundColor Red
        }

        # Show full config
        Write-Host "`n  Current config:" -ForegroundColor Gray
        Write-Host ($config | ConvertTo-Json -Depth 10) -ForegroundColor DarkGray

    } catch {
        Write-Host "  ERROR: Invalid JSON in config file" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "  Config file: NOT FOUND" -ForegroundColor Red
    Write-Host "  Expected at: $configPath" -ForegroundColor Red
}

# 2. Test MCP server manually
Write-Host "`n[2] Testing MCP server startup..." -ForegroundColor Yellow
Write-Host "  Starting server (will timeout after 3 seconds)..." -ForegroundColor Gray

try {
    $job = Start-Job -ScriptBlock {
        param($repoPath)
        Set-Location $repoPath
        python -m revit_mcp_server.mcp_server 2>&1
    } -ArgumentList "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"

    Start-Sleep -Seconds 3
    $output = Receive-Job $job -ErrorAction SilentlyContinue
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -ErrorAction SilentlyContinue

    if ($output -match "error" -and $output -notmatch "Bridge") {
        Write-Host "  Status: FAILED" -ForegroundColor Red
        Write-Host "  Output:" -ForegroundColor Red
        Write-Host $output -ForegroundColor Red
    } elseif ($output -match "Traceback") {
        Write-Host "  Status: ERROR" -ForegroundColor Red
        Write-Host "  Output:" -ForegroundColor Red
        Write-Host $output -ForegroundColor Red
    } else {
        Write-Host "  Status: OK (server starts)" -ForegroundColor Green
    }
} catch {
    Write-Host "  Status: ERROR" -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 3. Test module import
Write-Host "`n[3] Testing Python module..." -ForegroundColor Yellow
try {
    $result = python -c "import sys; sys.path.insert(0, 'packages/mcp-server-revit/src'); from revit_mcp_server.mcp_server import app; print('OK')" 2>&1
    if ($result -match "OK") {
        Write-Host "  Module import: OK" -ForegroundColor Green
    } else {
        Write-Host "  Module import: FAILED" -ForegroundColor Red
        Write-Host "  Output: $result" -ForegroundColor Red
    }
} catch {
    Write-Host "  Module import: ERROR" -ForegroundColor Red
    Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Check MCP package
Write-Host "`n[4] Checking MCP SDK..." -ForegroundColor Yellow
try {
    $result = python -c "import mcp; print(mcp.__version__)" 2>&1
    if ($result -match "^\d") {
        Write-Host "  MCP SDK: Installed (v$result)" -ForegroundColor Green
    } else {
        Write-Host "  MCP SDK: NOT INSTALLED" -ForegroundColor Red
        Write-Host "  Output: $result" -ForegroundColor Red
    }
} catch {
    Write-Host "  MCP SDK: ERROR" -ForegroundColor Red
}

# 5. Suggest fixes
Write-Host "`n[5] Diagnosis & Fixes`n" -ForegroundColor Yellow

$allGood = $true

# Check if config exists
if (-not (Test-Path $configPath)) {
    Write-Host "FIX: Config file missing" -ForegroundColor Red
    Write-Host "Run: .\setup-claude-desktop.ps1" -ForegroundColor White
    $allGood = $false
}

# Check Python path
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    $pythonPath = $config.mcpServers.revit.command
    if (-not (Test-Path $pythonPath)) {
        Write-Host "FIX: Python path is wrong" -ForegroundColor Red
        Write-Host "Current: $pythonPath" -ForegroundColor Gray
        $actualPython = (Get-Command python).Source
        Write-Host "Should be: $actualPython" -ForegroundColor Green
        Write-Host "Edit: $configPath" -ForegroundColor White
        $allGood = $false
    }
}

if ($allGood) {
    Write-Host "All checks passed!" -ForegroundColor Green
    Write-Host "`nNext steps:" -ForegroundColor Yellow
    Write-Host "1. RESTART Claude Desktop (completely close and reopen)" -ForegroundColor White
    Write-Host "2. Look for 'revit' in the MCP servers list" -ForegroundColor White
    Write-Host "3. If still not visible, check Claude Developer Tools:" -ForegroundColor White
    Write-Host "   View > Toggle Developer Tools > Console tab" -ForegroundColor Gray
    Write-Host "   Look for errors related to 'revit' or MCP" -ForegroundColor Gray
}

Write-Host ""
