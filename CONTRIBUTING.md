# Contributing

Status: on the dev branch, not yet released.

Thanks for improving AEC Model Bridge.

## Licensing

Open an issue before you write code. The project is licensed under
GPL-3.0-or-later with the Revit Linking Exception, and it also has a commercial
licence. To keep both options, the maintainer needs the right to license each
contribution under both.

There is no contributor agreement in force yet. Until there is one, code pull
requests cannot be merged. We are not asking anyone to sign anything now.
[docs/legal/CLA-DRAFT.md](docs/legal/CLA-DRAFT.md) is a draft of what it might
look like. It is not reviewed by a lawyer and not in force. If you plan a larger
code contribution, say so in your issue and we will settle the terms first.

Issue reports, design proposals and documentation corrections are welcome
without any agreement.

## Dependencies and licences

- Do not vendor or copy GPL-only code into this repository. This includes
  pyRevit, Bonsai (BlenderBIM) and Dynamo samples unless their licence allows
  it. Calling such a tool from outside, without copying its code, is fine, but
  ask in an issue first.
- Do not add proprietary dependencies without discussing them in an issue
  first. Autodesk Revit and Navisworks assemblies are referenced from the
  user's own installation and are never committed or packaged (see
  [TRADEMARKS.md](TRADEMARKS.md)).
- A new dependency needs a licence that is compatible with GPL-3.0-or-later
  and that does not stop a commercial licence of this project. MIT, BSD, ISC,
  Apache-2.0 and PSF are fine. LGPL needs a discussion. Do not add AGPL, SSPL
  or GPL-only libraries.
- After you change a dependency, regenerate the notices with
  `python scripts/generate_third_party_notices.py` in an environment synced
  from `uv.lock` (`uv sync --frozen`), and commit the result.

## Focus Areas

Contributions help most in these areas:
- Revit command coverage
- MCP tool reliability and error handling
- installation and configuration documentation
- developer ergonomics for local debugging and testing

## Guidelines

- Keep each pull request to one feature, fix or documentation update.
- Name the Revit versions you tested in the PR description.
- Remove local paths, machine names and credentials from config examples.
- If a change affects the UI or commands, give the steps to reproduce it and say what should happen.
- Update examples and docs when behaviour changes.

## Building and testing

Build the add-in for one Revit version and run the Python tests:

```powershell
.\scripts\build-addin.ps1 -RevitVersion 2026 -Configuration Release
python -m pytest packages/mcp-server-revit/tests
```

Supported Revit versions are 2024 (net48), 2025 and 2026 (net8.0-windows), and
2027 (net10.0-windows). See
[docs/target-frameworks-and-dependencies.md](docs/target-frameworks-and-dependencies.md).

## Good first issues

You do not need Revit or Windows for these. The Python tests run in mock mode.

### Run the tests

Install the package with its dev extra (`pip install -e "packages/mcp-server-revit[dev]"`), then run:

```bash
cd packages/mcp-server-revit
PYTHONPATH=src python -m pytest tests/test_tools.py tests/test_config.py   # one or two files
PYTHONPATH=src python -m pytest tests                                      # everything
```

On Windows PowerShell, set the variable first: `$env:PYTHONPATH = "src"`.

The full run takes about half a minute. A few tests are skipped on purpose: the end-to-end test needs a live Revit, and the proxy tests need a bridge. `test_wheel_contents.py` builds the wheel, so it needs an up-to-date `build` and `setuptools`. If it fails with a licence-metadata error on an old setuptools, upgrade setuptools before you report it.

### Starter tasks

Pick one, say so in an issue, and keep the pull request small.

1. **Review a translation.** The 16 READMEs in [docs/i18n/](docs/i18n/) are AI-assisted drafts. A native speaker can fix wording. See [Translations](#translations).
2. **Add a language.** Dutch, Swedish and Czech are not there yet. The steps are in [Translations](#translations), and `test_i18n_readmes.py` checks your work.
3. **Add a test for the Power BI provider.** `providers/powerbi.py` has no test that mentions it. A small mock-mode test is a good start.
4. **Try an untested MCP client.** [docs/compatibility.md](docs/compatibility.md) lists clients marked "not tested". Set one up in mock mode and send a pull request that updates its row, with the steps you used.
5. **Try the server on Linux.** The Linux CI job is experimental because the Windows-only parts (bridge discovery, path mapping) have not been exercised there. Run the tests on Linux and open an issue for each failure you find.
6. **Check the docs for stale statements.** Pick one page from [docs/README.md](docs/README.md), follow it on a clean machine, and fix what is wrong or unclear.
7. **Tidy formatting.** CI reports how many files `ruff format` would change, and does not enforce it. Format a few files in one pull request, with no other changes.
8. **Improve an error message.** Find a tool that returns a vague error in `packages/mcp-server-revit/src/revit_mcp_server/` and make it say what went wrong and what to do. Add a test for it.

## Translations

Translated READMEs live in `docs/i18n/` as `README.<language>.md` and are
linked from the language bar at the top of `README.md`. The English
`README.md` is canonical. If a translation differs from it, the English text
wins, and README changes are made in English first. The current translations
are AI-assisted drafts, so corrections from native speakers are especially
welcome.

To improve a translation, edit the file in `docs/i18n/` and open a pull
request. Keep code blocks, commands, tool names, environment variable names,
file paths, product names, counts and licence text exactly as in the English
README. Use the standard AEC term in your language (for example parameter,
sheet, view, family, worksharing).

To add a language, copy an existing translation and translate the prose. Then
add the language to the bar in `README.md` and in every file in `docs/i18n/`,
and to the list in `packages/mcp-server-revit/tests/test_i18n_readmes.py`.
That test checks that code blocks match the English README, headings line up,
the language bar is present and relative links resolve. Run it with
`python -m pytest packages/mcp-server-revit/tests/test_i18n_readmes.py`.

## Releases and versions

The project uses Semantic Versioning, and the root `VERSION` file is the
single source of truth. Tags look like `vX.Y.Z`. Do not change version numbers
by hand in other files. [docs/versioning.md](docs/versioning.md) describes the
release process, and [CHANGELOG.md](CHANGELOG.md) lists what changed.

## Repository Hygiene & Build Artifacts

- **Build artifacts (`dist/`, `build/`)**: Do not commit compiled files, zip packages or binary builds. We attach them to GitHub Releases.
- **Virtual environments**: Run tests and scripts inside a local `.venv`. Git ignores it.

## Pull Request Checklist

Before opening a PR, confirm that:
- the change has clear steps to reproduce and to check it
- config examples still work with placeholder values
- README or docs are updated when setup or behaviour changes
- any limits or known gaps are stated

Accepted contributions are credited in [CONTRIBUTORS.md](CONTRIBUTORS.md).
