param(
    [string]$RevitVersion = "2024",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

# Path Guard: Prevent Execution in System32 or Windows
if ($PSScriptRoot -like "*C:\Windows*") {
    Write-Error "Dangerous path detected: $PSScriptRoot"
    Write-Error "Please clone the repo to a safe location (e.g., $env:USERPROFILE\src) and run from there."
    exit 1
}

$projectPath = "$PSScriptRoot\..\packages\revit-bridge-addin\RevitBridge.csproj"

if (-not (Test-Path $projectPath)) {
    Write-Error "Project not found: $projectPath"
    exit 1
}

# Find msbuild using vswhere
$vsWherePath = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

if (Test-Path $vsWherePath) {
    $msbuild = & $vsWherePath -latest -requires Microsoft.Component.MSBuild -find MSBuild\**\Bin\MSBuild.exe | Select-Object -First 1
}
else {
    # Fallback to dotnet build if vswhere not available
    Write-Host "vswhere not found, using dotnet build..." -ForegroundColor Yellow
    $msbuild = "dotnet"
    $buildCommand = "build"
}

if (-not $msbuild) {
    Write-Error "MSBuild or dotnet not found. Install Visual Studio Build Tools or .NET SDK."
    exit 1
}

Write-Host "Building RevitBridge for Revit $RevitVersion ($Configuration)..." -ForegroundColor Cyan

if ($msbuild -like "*dotnet*") {
    & $msbuild build $projectPath `
        -c $Configuration `
        -p:RevitVersion=$RevitVersion `
        -v:minimal
}
else {
    & $msbuild $projectPath `
        /p:Configuration=$Configuration `
        /p:RevitVersion=$RevitVersion `
        /v:minimal
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$outputPath = "packages\revit-bridge-addin\bin\$Configuration\$RevitVersion\RevitBridge.dll"
Write-Host "Build succeeded: $outputPath" -ForegroundColor Green
