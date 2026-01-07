Write-Host "`n"
Write-Host "="*70 -ForegroundColor Cyan
Write-Host "RevitMCP - Setup Verification" -ForegroundColor Cyan
Write-Host "="*70 -ForegroundColor Cyan
Write-Host ""

# 1. Check Revit Bridge
Write-Host "[1/4] Checking Revit Bridge..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:3000/health" -Method GET -TimeoutSec 5
    Write-Host "  Status: $($response.status)" -ForegroundColor Green
    Write-Host "  Revit Version: $($response.revit_version)" -ForegroundColor Green
    Write-Host "  Active Document: $($response.active_document)" -ForegroundColor Green
    $bridgeOk = $true
} catch {
    Write-Host "  ERROR: Cannot connect to Revit bridge" -ForegroundColor Red
    Write-Host "  Make sure Revit is running with a project open!" -ForegroundColor Yellow
    $bridgeOk = $false
}

# 2. Check Claude Desktop Config
Write-Host "`n[2/4] Checking Claude Desktop Configuration..." -ForegroundColor Yellow
$configFile = "$env:APPDATA\Claude\claude_desktop_config.json"
if (Test-Path $configFile) {
    $config = Get-Content $configFile | ConvertFrom-Json
    if ($config.mcpServers.revit) {
        Write-Host "  Config file: Found" -ForegroundColor Green
        Write-Host "  Revit server: Configured" -ForegroundColor Green
        Write-Host "  Python path: $($config.mcpServers.revit.command)" -ForegroundColor Gray
    } else {
        Write-Host "  WARNING: Revit server not found in config" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ERROR: Config file not found" -ForegroundColor Red
}

# 3. Test MCP Server
Write-Host "`n[3/4] Testing MCP Server..." -ForegroundColor Yellow
try {
    $job = Start-Job -ScriptBlock {
        param($pythonPath)
        cd "C:\Users\samo3\OneDrive - Heijmans N.V\Documenten\GitHub\Autodesk-Revit-MCP-Server"
        & $pythonPath -m revit_mcp_server.mcp_server 2>&1
    } -ArgumentList "C:\Users\samo3\AppData\Local\Programs\Python\Python313\python.exe"

    Start-Sleep -Seconds 2
    $output = Receive-Job $job
    Stop-Job $job
    Remove-Job $job

    if ($output -match "error" -and $output -notmatch "Bridge") {
        Write-Host "  ERROR: Server failed" -ForegroundColor Red
    } else {
        Write-Host "  MCP Server: OK (starts correctly)" -ForegroundColor Green
    }
} catch {
    Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Check Python Package
Write-Host "`n[4/4] Checking Python Package..." -ForegroundColor Yellow
try {
    $result = python -c "import revit_mcp_server; print('OK')" 2>&1
    if ($result -match "OK") {
        Write-Host "  Package: Installed" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Package not installed" -ForegroundColor Red
    }
} catch {
    Write-Host "  ERROR: Cannot verify package" -ForegroundColor Red
}

# Summary
Write-Host "`n"
Write-Host "="*70 -ForegroundColor Cyan
Write-Host "SUMMARY" -ForegroundColor Cyan
Write-Host "="*70 -ForegroundColor Cyan
Write-Host ""

if ($bridgeOk) {
    Write-Host "Status: READY TO USE!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "  1. Open Claude Desktop (or restart if already open)" -ForegroundColor White
    Write-Host "  2. Look for the 'revit' server in MCP tools section" -ForegroundColor White
    Write-Host "  3. Start chatting!" -ForegroundColor White
    Write-Host ""
    Write-Host "Try saying:" -ForegroundColor Cyan
    Write-Host '  "Is Revit running? What project is open?"' -ForegroundColor White
    Write-Host '  "Create a 30ft by 25ft house with 10ft tall walls"' -ForegroundColor White
} else {
    Write-Host "Status: Revit Bridge Not Running" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To Fix:" -ForegroundColor Yellow
    Write-Host "  1. Open Revit 2024" -ForegroundColor White
    Write-Host "  2. Open or create a project" -ForegroundColor White
    Write-Host "  3. Run this script again to verify" -ForegroundColor White
}

Write-Host ""
Write-Host "="*70 -ForegroundColor Cyan
Write-Host ""
