param(
    [string]$RevitYear = "2024",
    [string]$AddinDir = "C:\\ProgramData\\Autodesk\\Revit\\Addins"
)

$target = Join-Path $AddinDir $RevitYear
if (-not (Test-Path $target)) {
    New-Item -ItemType Directory -Path $target | Out-Null
}
Copy-Item packages/revit-bridge-addin/RevitBridge.addin -Destination $target -Force
Write-Host "Installed add-in manifest to $target"
