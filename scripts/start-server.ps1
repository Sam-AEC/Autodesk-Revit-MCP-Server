param(
    [string]$Mode = "bridge"
)

$ErrorActionPreference = "Stop"

Write-Host "RevitMCP Server Startup" -ForegroundColor Cyan
Write-Host "=====================`n" -ForegroundColor Cyan

# Check if .env exists
$envFile = "$PSScriptRoot\.env"
if (-not (Test-Path $envFile)) {
    Write-Host ".env file not found. Creating from example..." -ForegroundColor Yellow
    if (Test-Path "$PSScriptRoot\.env.example") {
        Copy-Item "$PSScriptRoot\.env.example" $envFile
        Write-Host "Created .env file. Please edit it with your paths!" -ForegroundColor Green
        Write-Host "Opening .env in notepad..." -ForegroundColor Yellow
        Start-Process notepad $envFile
        Write-Host "`nPress Enter after editing .env to continue..." -ForegroundColor Yellow
        Read-Host
    }
    else {
        Write-Error ".env.example not found. Cannot continue."
        exit 1
    }
}

# Check if Python is available
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found. Please install Python 3.11 or later."
    exit 1
}

Write-Host "Python version:" -ForegroundColor Yellow
python --version

# Check if in virtual environment
$inVenv = $env:VIRTUAL_ENV -ne $null
if (-not $inVenv) {
    Write-Host "`nWARNING: Not in a virtual environment." -ForegroundColor Yellow
    Write-Host "It's recommended to use a virtual environment." -ForegroundColor Yellow
    Write-Host "Create one with: python -m venv venv" -ForegroundColor Gray
    Write-Host "Activate with: .\venv\Scripts\Activate.ps1`n" -ForegroundColor Gray
}

# Install/update dependencies
Write-Host "`nInstalling Python MCP server package..." -ForegroundColor Yellow
Push-Location "$PSScriptRoot\packages\mcp-server-revit"
try {
    python -m pip install -e . --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install Python package"
        exit 1
    }
    Write-Host "Package installed successfully" -ForegroundColor Green
}
finally {
    Pop-Location
}

# Display configuration
Write-Host "`nConfiguration:" -ForegroundColor Yellow
Get-Content $envFile | Where-Object { $_ -notmatch "^#" -and $_ -match "\S" } | ForEach-Object {
    Write-Host "  $_" -ForegroundColor Gray
}

# Check if Revit is running (if bridge mode)
if ($Mode -eq "bridge") {
    Write-Host "`nChecking Revit bridge..." -ForegroundColor Yellow
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:3000/health" -Method GET -TimeoutSec 2 -UseBasicParsing
        $health = $response.Content | ConvertFrom-Json
        Write-Host "Bridge status: $($health.status)" -ForegroundColor Green
        Write-Host "Revit version: $($health.revit_version)" -ForegroundColor Green
        if ($health.active_document) {
            Write-Host "Active document: $($health.active_document)" -ForegroundColor Green
        }
    }
    catch {
        Write-Host "WARNING: Cannot connect to Revit bridge!" -ForegroundColor Red
        Write-Host "Make sure Revit is running with a project open." -ForegroundColor Yellow
        Write-Host "The bridge should be available at http://127.0.0.1:3000" -ForegroundColor Yellow
        Write-Host "`nContinuing anyway... (server will fail on first tool call)`n" -ForegroundColor Gray
    }
}

# Start the server
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Starting MCP Server (mode: $Mode)" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Server is now listening for JSON-RPC requests on stdin/stdout" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop the server`n" -ForegroundColor Gray

Push-Location "$PSScriptRoot\packages\mcp-server-revit"
try {
    python -m revit_mcp_server
}
finally {
    Pop-Location
}
