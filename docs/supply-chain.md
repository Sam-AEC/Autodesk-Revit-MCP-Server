# Supply chain: what is signed, what is not

This page says plainly how much you can trust a download from this project, and how to check it yourself.

## What is attested today

Every GitHub release is built by the `Build GitHub Release` workflow on GitHub-hosted runners. The workflow runs `actions/attest-build-provenance` over everything in the release (`dist/release/*`). That produces a signed build provenance attestation, stored by GitHub, that links each file to the exact repository, commit, tag and workflow run that built it.

Each release also carries:

- `SHA256SUMS.txt`: a SHA-256 checksum for every other release file, including the SBOM.
- `aec-model-bridge-<version>.cdx.json`: a CycloneDX software bill of materials (SBOM) for the Python package (see below).

## What is not signed

- The Windows installer (`AECModelBridge-Setup-<version>.exe`) and the add-in DLLs are **not Authenticode code signed**. Windows SmartScreen may warn about the installer. The provenance attestation proves where the file was built, but Windows itself does not check it.
- There is no detached signature (`.sig`) or GPG signature next to the release files.
- Builds are not yet reproducible, so you cannot rebuild a file and compare bytes.
- The SBOM covers the Python package only. It does not list the .NET add-in dependencies or the bundled Python runtime.

## How to verify a download

Download the file and `SHA256SUMS.txt` from the same release page.

Check the checksum (Linux, macOS, Git Bash):

```bash
sha256sum -c --ignore-missing SHA256SUMS.txt
```

On Windows PowerShell:

```powershell
(Get-FileHash .\AECModelBridge-Setup-1.4.0.exe -Algorithm SHA256).Hash.ToLower()
# compare with the matching line in SHA256SUMS.txt
```

Check the build provenance with the GitHub CLI:

```bash
gh attestation verify AECModelBridge-Setup-1.4.0.exe --repo Sam-AEC/aec-model-bridge
```

A checksum only proves the file matches the release page. The attestation is the stronger check, because it proves the file was built by this repository's workflow.

## Where the SBOM is

- **Releases:** `aec-model-bridge-<version>.cdx.json` is a release asset, listed in `SHA256SUMS.txt` and covered by the attestation.
- **Pull requests and `main`:** the `sbom` job in `.github/workflows/ci.yml` uploads it as the `sbom-cyclonedx` workflow artifact (kept 14 days).

It is generated from `packages/mcp-server-revit/uv.lock` (runtime dependencies only, no dev tools) with `cyclonedx-bom` at a pinned version, in CycloneDX 1.6 JSON. To regenerate it locally:

```bash
cd packages/mcp-server-revit
python -m pip install "cyclonedx-bom==7.2.1"
uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt -o /tmp/req.txt
cyclonedx-py requirements /tmp/req.txt --pyproject pyproject.toml --sv 1.6 --of JSON -o aec-model-bridge.cdx.json
```
