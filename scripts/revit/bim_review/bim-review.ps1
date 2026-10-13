<#
.SYNOPSIS  Read-only BIM quality review of the AMB villa in the open Revit session, plus rendered images to look at.
.PARAMETER OutDir  Where the PNGs go (default: .\review-images next to the caller).
.PARAMETER NoImages  Skip the image export (the checks alone take about 3 seconds).
Exit code 1 when any check FAILs. It opens no transaction and changes nothing in the model.
#>
param([string]$OutDir = (Join-Path (Get-Location) 'review-images'), [switch]$NoImages)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Get-Process Revit -ErrorAction SilentlyContinue)) { Write-Error 'Revit is not running.'; exit 2 }

function Invoke-Bridge([string]$Script, [int]$TimeoutSec = 90) {
    $reg = Get-ChildItem "$env:LOCALAPPDATA\AECModelBridge\registry" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object { Get-Content $_.FullName -Raw | ConvertFrom-Json }
    $body = @{ tool = 'revit.execute_python'; payload = @{ script = $Script }; request_id = [guid]::NewGuid().ToString() } | ConvertTo-Json -Depth 6
    $r = Invoke-WebRequest "$($reg.endpoint)/execute" -Method Post -Body $body -ContentType 'application/json' -Headers @{ Authorization = "Bearer $($reg.session_token)" } -UseBasicParsing -TimeoutSec $TimeoutSec
    $j = ($r.Content | ConvertFrom-Json)
    if ($j.Status -ne 'ok') { throw "Bridge error: $($j.Message)" }
    return $j.Result
}

$prelude = Get-Content (Join-Path $here 'prelude.py') -Raw
$report = Invoke-Bridge ($prelude + "`n" + (Get-Content (Join-Path $here 'review_checks.py') -Raw))
if (-not $report.success) { Write-Error "Review script failed: $($report.error)"; exit 2 }
$report.output
$failed = ($report.output -split "`n" | Where-Object { $_ -match '^FAIL' }).Count

if (-not $NoImages) {
    New-Item -ItemType Directory -Force $OutDir | Out-Null
    foreach ($view in 'AMB_3D Villa', 'AMB_Plan_00 Ground', 'AMB_Plan_01 First Floor', 'AMB_Section A-A stair') {
        $png = ($OutDir -replace '\', '\') + '\review'
        $py = @"
def vname(v): return v.get_Parameter(BuiltInParameter.VIEW_NAME).AsString()
vs = [v for v in FilteredElementCollector(doc).OfClass(View) if not v.IsTemplate and vname(v) == "$view"]
if vs:
    o = ImageExportOptions(); o.ZoomType = ZoomFitType.FitToPage; o.PixelSize = 1800; o.ImageResolution = ImageResolution.DPI_150
    o.FitDirection = FitDirectionType.Horizontal; o.ExportRange = ExportRange.SetOfViews
    o.SetViewsAndSheets(List[ElementId]([vs[0].Id])); o.FilePath = r"$png"
    o.HLRandWFViewsFileType = ImageFileType.PNG; o.ShadowViewsFileType = ImageFileType.PNG
    doc.ExportImage(o); __output__ = "exported $view"
else:
    __output__ = "view not found: $view"
"@
        try { (Invoke-Bridge ($prelude + "`n" + $py) 60).output } catch { "image export failed for ${view}: $($_.Exception.Message)" }
    }
    "Images in $OutDir"
}
if ($failed -gt 0) { exit 1 }
