param(
    [string]$RevitSdkPath = $env:REVIT_SDK
)

if (-not $RevitSdkPath) {
    Write-Error "Set REVIT_SDK to the SDK root before building."
    exit 1
}

Write-Host "Building Revit bridge add-in using SDK at $RevitSdkPath"
# Placeholder: call msbuild on packages/revit-bridge-addin/RevitBridge.csproj
