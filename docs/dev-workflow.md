# Branches and merging

How changes reach `main`, and the habits we keep to a minimum.

## The branches

| Branch | What it is | Who changes it |
| --- | --- | --- |
| `main` | What a release is cut from. Always passes CI. | Only through a pull request, never by a direct push. |
| `dev` | Where finished, green work is combined and tested by the owner before it goes to `main`. | Merge commits from reviewed branches. No force-push. |
| `feat/…`, `fix/…`, `docs/…` | One change each. | Anyone, through a pull request. |

## The path of a change

1. Work on a branch named for the change. One concern per branch.
2. Open one pull request. Describe what changed, how it was tested, and what is **UNVERIFIED** (anything that needs a real Revit).
3. CI (`ci-success`) must pass and review threads must be answered.
4. A green branch is merged into `dev` with a **merge commit**, not a squash. That keeps the commit ids, so GitHub marks the pull request as merged when `dev` later goes to `main`.
5. The owner tests `dev` on a real machine. When they are happy, `dev` goes to `main` in one pull request.

## Protecting `main`

The ruleset in [`.github/rulesets/protect-main.json`](../.github/rulesets/protect-main.json) blocks direct pushes, force-pushes and deletion of `main`, and requires:

- a pull request,
- the `ci-success` check, on a branch that is up to date with `main`,
- every review thread resolved.

No approving review is required, because there is one maintainer today and a person cannot approve their own pull request. Repository admins can bypass the rules **only while merging a pull request**, not by pushing. The second file, [`protect-dev.json`](../.github/rulesets/protect-dev.json), only stops `dev` being deleted or force-pushed.

To apply them (the repository owner, in GitHub): **Settings → Rules → Rulesets → New ruleset → Import a ruleset**, choose each file, then check the preview and save. The import checks the schema and will say if a field is not accepted.

## Releases

Because direct pushes to `main` are blocked, a release is:

1. Open a pull request that bumps the version and changelog (`chore(release): X.Y.Z`).
2. Merge it when `ci-success` is green.
3. Tag the merge commit (`git tag vX.Y.Z && git push origin vX.Y.Z`). Pushing a tag is not blocked.

Nothing is published until the owner confirms a release.

## Habits we skip on purpose

- No direct commits to `main`, and no force-pushes anywhere.
- No squash merges into `dev`, because they hide which pull request a change came from.
- No hand-merging of generated files. `docs/tools-generated.md` is regenerated with `python scripts/generate_tool_docs.py`.
- No new tool, module or screen without a test that fails without it.
- No claim in the docs that has not been checked. Unchecked things are marked UNVERIFIED.
- No second pull request for the same change.
