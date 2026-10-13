# Add-in behavioral regressions

Run from the repository root with a .NET 8-compatible SDK:

```powershell
./scripts/test-addin-behavior.ps1
```

The runner extracts the current production parameter-reader and image-export methods,
compiles them with small Revit API stubs, and executes behavior assertions. It uses
only local filesystem artifacts and never connects to Revit. No NuGet test packages
or Autodesk runtime are required.

The parameter cases cover shared and ordinary parameters together, all ordinary
parameters, preserved metadata, skipped empty parameters, and a GUID getter that
throws when called on an ordinary parameter. The export cases cover real suffix
paths, width/height fitting, shaded-view format, unchanged old files, overwritten
files, missing images, empty images, and unrelated files.

Default generated sources, binaries, image fixtures, and logs are removed after
execution. To retain evidence, provide a new artifact directory:

```powershell
./scripts/test-addin-behavior.ps1 -ArtifactDirectory "$env:TEMP/aec-addin-behavior-evidence"
```

That directory contains the extracted methods, compiled harness, and
`test-output.log`. `-KeepArtifacts` retains an automatically named temp directory.

These checks exercise production C# logic with API stubs. They do not verify
Autodesk's filename behavior, transaction requirements, actual image pixels, or
the loaded add-in. Live proof still requires rebuilding/loading the add-in and
repeating the parameter reads and image export in Revit.
