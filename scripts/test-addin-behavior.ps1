param(
    [string]$ArtifactDirectory,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$factoryPath = Join-Path $repoRoot "packages/revit-bridge-addin/src/Bridge/BridgeCommandFactory.cs"
$fixtureRoot = Join-Path $PSScriptRoot "tests/addin-behavior"
$factorySource = Get-Content -LiteralPath $factoryPath -Raw

function Get-ProductionMethod([string]$name) {
    # The following BridgeCommand attribute bounds the two selected methods.
    $pattern = '(?s)private static object ' + [regex]::Escape($name) +
        '\(.*?(?=\r?\n    \[BridgeCommand)'
    $match = [regex]::Match($factorySource, $pattern)
    if (-not $match.Success) {
        throw "Production method not found: $name"
    }
    return $match.Value.Replace("private static object $name", "public static object $name")
}

$explicitArtifacts = -not [string]::IsNullOrWhiteSpace($ArtifactDirectory)
if ($explicitArtifacts) {
    $taskArtifactRoot = [IO.Path]::GetFullPath($ArtifactDirectory)
} else {
    $taskArtifactRoot = Join-Path ([IO.Path]::GetTempPath()) ("aec-addin-behavior-" + [Guid]::NewGuid().ToString("N"))
}
if (Test-Path -LiteralPath $taskArtifactRoot) {
    throw "Artifact directory must be new: $taskArtifactRoot"
}
New-Item -ItemType Directory -Path $taskArtifactRoot | Out-Null
$expectedArtifactRoot = [IO.Path]::GetFullPath($taskArtifactRoot)

try {
    foreach ($fixture in @(
        @{ File = "ParameterReader.cs"; Method = "ExecuteGetElementParameters" },
        @{ File = "ImageExport.cs"; Method = "ExecuteExportImage" }
    )) {
        $source = Get-Content -LiteralPath (Join-Path $fixtureRoot $fixture.File) -Raw
        $source = $source.Replace("/* PRODUCTION_METHOD */", (Get-ProductionMethod $fixture.Method))
        Set-Content -LiteralPath (Join-Path $taskArtifactRoot $fixture.File) -Value $source -Encoding UTF8
    }

    $project = @'
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
'@
    Set-Content -LiteralPath (Join-Path $taskArtifactRoot "Regression.csproj") -Value $project -Encoding UTF8
    $runner = @'
try
{
    ParameterRegression.Program.Run();
    ExportRegression.Program.Run();
    return 0;
}
catch (Exception error)
{
    Console.WriteLine("FAIL: " + error);
    return 1;
}
'@
    Set-Content -LiteralPath (Join-Path $taskArtifactRoot "Runner.cs") -Value $runner -Encoding UTF8
    $logPath = Join-Path $taskArtifactRoot "test-output.log"
    & dotnet run --project (Join-Path $taskArtifactRoot "Regression.csproj") --configuration Release --verbosity quiet *> $logPath
    $testExitCode = $LASTEXITCODE
    Get-Content -LiteralPath $logPath
    if ($testExitCode -ne 0) {
        throw "Add-in behavioral regression failed (exit $testExitCode)."
    }
} finally {
    if ($explicitArtifacts -or $KeepArtifacts) {
        Write-Output "Artifacts: $taskArtifactRoot"
    } else {
        # Delete only the unique directory created above, under the system temp root.
        $resolvedArtifactRoot = [IO.Path]::GetFullPath($taskArtifactRoot)
        $tempPrefix = Join-Path ([IO.Path]::GetTempPath()) "aec-addin-behavior-"
        if ($resolvedArtifactRoot -ne $expectedArtifactRoot -or
            -not $resolvedArtifactRoot.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing cleanup outside the verified task directory: $resolvedArtifactRoot"
        }
        Remove-Item -LiteralPath $resolvedArtifactRoot -Recurse -Force
    }
}
