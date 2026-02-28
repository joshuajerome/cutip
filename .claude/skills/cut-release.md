# cut-release

Bump the version, update docs, merge to integration, push the release branch, clean up the GitHub Release page, and update the capabilities registry.

---

## Workflow

### Step 1 — Determine the new version

Ask the user: "What version? (current: X.Y.Z)"

If the user doesn't specify, suggest the next patch version (`X.Y.Z+1`).

### Step 2 — Ensure staging and integration are clean

```bash
git checkout staging && git pull
git checkout integration && git pull
git diff integration..staging --name-only
```

If there are unmerged commits on staging, warn the user and ask whether to proceed or merge staging first.

### Step 3 — Bump version in pyproject.toml

```bash
git checkout staging && git pull
git checkout -b feat/bump-vX.Y.Z
```

Edit `pyproject.toml`:
```toml
version = "X.Y.Z"
```

Commit:
```bash
git add pyproject.toml
git commit -m "bump: version A.B.C → X.Y.Z"
git push -u origin feat/bump-vX.Y.Z
```

Open PR:
```bash
gh pr create --base staging \
  --title "bump: version A.B.C → X.Y.Z" \
  --body "Version bump for the X.Y.Z release." \
  --label "enhancement" \
  --assignee joshuajerome
```

Wait for all CI checks to pass:
```bash
gh pr checks <PR_NUMBER> --watch
```

Merge:
```bash
gh pr merge <PR_NUMBER> --merge --delete-branch
```

### Step 4 — Update docs/patch-notes.md

On the same branch (before merging) or a separate `docs/` branch, add a release section to `docs/patch-notes.md`:

```markdown
## vX.Y.Z (YYYY-MM-DD)

### cap{N} — <title> (YYYY-MM-DD)
- <bullet describing what changed from a user perspective>
```

Only include cap IDs that shipped since the last release. Describe changes in terms users care about — not internal refactors or CI fixes.

### Step 5 — Update docs/capabilities.md

Ensure all cap IDs that shipped in this release are registered in `docs/capabilities.md` with `status: merged`.

### Step 6 — Forward staging → integration

```bash
git checkout integration && git pull
git merge origin/staging --no-edit
git push
```

### Step 7 — Cut the release branch

```bash
git checkout -b release/vX.Y.Z integration
git push -u origin release/vX.Y.Z
```

The `release.yml` workflow will fire automatically. Watch it:

```bash
gh run watch $(gh run list --branch release/vX.Y.Z --workflow release.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

### Step 8 — Clean up the GitHub Release page

After `release.yml` completes:

**Remove non-wheel assets** (keep only the `.whl`):
```bash
gh api repos/{owner}/{repo}/releases/tags/vX.Y.Z \
  --jq '.assets[] | select(.name | test("whl") | not) | .id' \
  | while read id; do
      gh api repos/{owner}/{repo}/releases/assets/$id --method DELETE
    done
```

**Update release notes** — replace the auto-generated "What's Changed" with user-facing bullet points:
```bash
gh release edit vX.Y.Z --notes "..."
```

Notes format:
```markdown
Container Unit Templates in Python — deterministic framework for building and orchestrating Podman container workloads.

## What's Changed

- <user-facing bullet for cap{N}>
- <user-facing bullet for cap{M}>

**Full Changelog**: https://github.com/{owner}/{repo}/compare/vA.B.C...vX.Y.Z
```

Focus on what users care about: new commands, behavior changes, bug fixes that caused visible errors. Omit CI fixes, doc cleanups, and internal refactors.

### Step 9 — Clean up local branches

```bash
git checkout integration
git branch -d release/vX.Y.Z feat/bump-vX.Y.Z 2>/dev/null || true
```

### Step 10 — Report

Print a summary:

```
✓ Version bumped: A.B.C → X.Y.Z
✓ release/vX.Y.Z pushed → release.yml passed
✓ GitHub Release: https://github.com/{owner}/{repo}/releases/tag/vX.Y.Z
✓ Assets: cutip-X.Y.Z-py3-none-any.whl (only)
✓ Docs: patch-notes.md and capabilities.md updated
```

---

## Rules

- Never push directly to `integration` for the version bump — always go through a PR on staging
- The release branch is created from `integration` (not staging)
- `release/*` branches are permanent — never delete them
- Do not tag manually — the `release.yml` workflow creates the git tag automatically via `softprops/action-gh-release`
- If `release.yml` fails, investigate the logs before retrying
