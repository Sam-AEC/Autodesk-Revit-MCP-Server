param(
    [ValidateSet("2024", "2025", "2026", "2027")]
    [string[]]$RevitVersion = @("2024", "2026"),
    [string]$ArtifactDirectory,
    [switch]$SkipBuild,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$addinProject = Join-Path $repoRoot "packages/revit-bridge-addin/RevitBridge.csproj"
$helperPath = Join-Path $repoRoot "packages/revit-bridge-addin/src/Bridge/PythonEngineFactory.cs"
$fixturePath = Join-Path $PSScriptRoot "tests/ironpython-runtime/Program.cs"
$explicitArtifacts = -not [string]::IsNullOrWhiteSpace($ArtifactDirectory)
$taskArtifactRoot = if ($explicitArtifacts) {
    [IO.Path]::GetFullPath($ArtifactDirectory)
} else {
    Join-Path ([IO.Path]::GetTempPath()) ("aec-ironpython-runtime-" + [Guid]::NewGuid().ToString("N"))
}
if (Test-Path -LiteralPath $taskArtifactRoot) {
    throw "Artifact directory must be new: $taskArtifactRoot"
}
New-Item -ItemType Directory -Path $taskArtifactRoot | Out-Null
$expectedArtifactRoot = [IO.Path]::GetFullPath($taskArtifactRoot)

try {
    foreach ($year in $RevitVersion) {
        $framework = switch ($year) {
            "2024" { "net48" }
            "2027" { "net10.0-windows" }
            default { "net8.0-windows" }
        }
        $yearArtifacts = Join-Path $taskArtifactRoot $year
        New-Item -ItemType Directory -Path $yearArtifacts | Out-Null
        if (-not $SkipBuild) {
            $buildLog = Join-Path $yearArtifacts "addin-build.log"
            & dotnet build $addinProject -c Release "-p:RevitVersion=$year" -clp:ErrorsOnly -v:q *> $buildLog
            $buildExitCode = $LASTEXITCODE
            Get-Content -LiteralPath $buildLog
            if ($buildExitCode -ne 0) { throw "Revit $year add-in build failed." }
        }

        $addinOutput = Join-Path $repoRoot "packages/revit-bridge-addin/bin/Release/$year/$framework"
        if (-not (Test-Path -LiteralPath (Join-Path $addinOutput "Lib/json/__init__.py"))) {
            throw "Revit $year build output is missing the packaged standard library."
        }
        if (-not (Test-Path -LiteralPath (Join-Path $addinOutput "IronPython.StdLib.LICENSE.txt"))) {
            throw "Revit $year build output is missing the standard-library license."
        }
        Copy-Item -LiteralPath $helperPath -Destination $yearArtifacts
        Copy-Item -LiteralPath $fixturePath -Destination $yearArtifacts
        $escapedOutput = [Security.SecurityElement]::Escape($addinOutput)
        # Reference shipped System.* packages where present, while UseWPF below
        # matches the add-in's Windows Desktop framework dependencies.
        $systemReferences = (Get-ChildItem -LiteralPath $addinOutput -Filter "System*.dll" -File | ForEach-Object {
            $escapedPath = [Security.SecurityElement]::Escape($_.FullName)
            '<Reference Include="' + $_.BaseName + '"><HintPath>' + $escapedPath + '</HintPath></Reference>'
        }) -join [Environment]::NewLine
        $project = @"
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>$framework</TargetFramework>
    <UseWPF>true</UseWPF>
    <LangVersion>latest</LangVersion>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="IronPython"><HintPath>$escapedOutput/IronPython.dll</HintPath></Reference>
    <Reference Include="IronPython.Modules"><HintPath>$escapedOutput/IronPython.Modules.dll</HintPath></Reference>
    <Reference Include="Microsoft.Dynamic"><HintPath>$escapedOutput/Microsoft.Dynamic.dll</HintPath></Reference>
    <Reference Include="Microsoft.Scripting"><HintPath>$escapedOutput/Microsoft.Scripting.dll</HintPath></Reference>
    $systemReferences
    <Content Include="$escapedOutput/Lib/**/*">
      <Link>Lib/%(RecursiveDir)%(Filename)%(Extension)</Link>
      <CopyToOutputDirectory>PreserveNewest</CopyToOutputDirectory>
    </Content>
  </ItemGroup>
</Project>
"@
        $projectPath = Join-Path $yearArtifacts "RuntimeRegression.csproj"
        Set-Content -LiteralPath $projectPath -Value $project -Encoding UTF8
        $major = if ($year -eq "2024") { "2" } else { "3" }
        $minor = if ($year -eq "2024") { "7" } else { "4" }
        $testLog = Join-Path $yearArtifacts "test-output.log"
        & dotnet run --project $projectPath -c Release -v:q -- $major $minor *> $testLog
        $testExitCode = $LASTEXITCODE
        Get-Content -LiteralPath $testLog
        if ($testExitCode -ne 0) { throw "Revit $year IronPython runtime regression failed." }
    }
} finally {
    if ($explicitArtifacts -or $KeepArtifacts) {
        Write-Output "Artifacts: $taskArtifactRoot"
    } else {
        $resolvedArtifactRoot = [IO.Path]::GetFullPath($taskArtifactRoot)
        $tempPrefix = Join-Path ([IO.Path]::GetTempPath()) "aec-ironpython-runtime-"
        if ($resolvedArtifactRoot -ne $expectedArtifactRoot -or
            -not $resolvedArtifactRoot.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing cleanup outside the verified task directory: $resolvedArtifactRoot"
        }
        Remove-Item -LiteralPath $resolvedArtifactRoot -Recurse -Force
    }
}
