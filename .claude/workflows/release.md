# Release — End-to-End Playbook

Follow this playbook **completely** when cutting a release.
Do not stop until the GitHub Release page is edited, assets are cleaned, and the final report is printed.

---

## Completion Criteria

- [ ] Version bumped in `pyproject.toml`, PR merged to staging
- [ ] `docs/patch-notes.md` updated with release section
- [ ] `docs/capabilities.md` — all shipped caps marked `merged`
- [ ] staging forwarded to integration (`git merge`)
- [ ] `release/vX.Y.Z` branch pushed, `release.yml` passed
- [ ] GitHub Release notes edited (using `.claude/templates/github-release-notes.md`)
- [ ] Non-wheel assets removed from GitHub Release
- [ ] Local release branch cleaned up
- [ ] Final report printed

---

## Step 1 — Determine version

Read current version from `pyproject.toml`.
Ask: "What version? (current: {X.Y.Z})"
If not specified, suggest next patch: `X.Y.{Z+1}`.

---

## Step 2 — Identify what's shipping

Read `docs/capabilities.md`. List every cap with `status: open` or merged since the last `release/*` tag.
These are the changes that will appear in the release notes.

```bash
git log $(git describe --tags --abbrev=0)..HEAD --oneline
```

---

## Step 3 — Draft release notes

Fill the template at `.claude/templates/github-release-notes.md`.
Save the GitHub Release section to `/tmp/release-notes.md`.
Save the patch-notes section to `/tmp/patch-note-entry.md`.

Write only user-facing changes. Omit CI fixes, doc cleanups, internal refactors.

---

## Step 4 — Version bump PR

```bash
git checkout staging && git pull origin staging
git checkout -b feat/bump-v{X.Y.Z}
```

Edit `pyproject.toml`:
```toml
version = "{X.Y.Z}"
```

Prepend `/tmp/patch-note-entry.md` content into `docs/patch-notes.md` (after the `# Patch Notes` heading).

```bash
git add pyproject.toml docs/patch-notes.md
git commit -m "bump: version {A.B.C} → {X.Y.Z}"
git push -u origin feat/bump-v{X.Y.Z}

gh pr create \
  --base staging \
  --title "bump: version {A.B.C} → {X.Y.Z}" \
  --body "Version bump for the {X.Y.Z} release." \
  --assignee joshuajerome
```

Watch CI, then merge:
```bash
gh pr checks <PR_NUMBER> --watch
gh pr merge <PR_NUMBER> --merge --delete-branch
```

---

## Step 5 — Update capabilities.md

Ensure all shipped caps have `status: merged` and the correct PR number.
If any are still `open`, update them now on a `docs/*` branch or inline with the bump commit.

---

## Step 6 — Forward staging → integration

```bash
git checkout integration && git pull origin integration
git merge origin/staging --no-edit
git push origin integration
```

---

## Step 7 — Cut the release branch

```bash
git checkout -b release/v{X.Y.Z} origin/integration
git push -u origin release/v{X.Y.Z}
```

Watch the release workflow until it completes:
```bash
gh run watch $(gh run list --branch release/v{X.Y.Z} --workflow release.yml \
  --limit 1 --json databaseId --jq '.[0].databaseId')
```

If `release.yml` fails, read the logs before retrying:
```bash
gh run view <run-id> --log-failed
```

---

## Step 8 — Edit the GitHub Release page

After `release.yml` completes, update the release notes using the template at
`.claude/templates/github-release-notes.md`. The release description must list
capabilities added/fixed — do not list individual PRs, authors, or retain the
GitHub-generated "What's Changed" content.

```bash
gh release edit v{X.Y.Z} --notes "$(cat /tmp/release-notes.md)"
```

Remove non-wheel assets (keep only `.whl`):
```bash
gh api repos/joshuajerome/cutip/releases/tags/v{X.Y.Z} \
  --jq '.assets[] | select(.name | test("whl") | not) | .id' \
  | while read id; do
      gh api repos/joshuajerome/cutip/releases/assets/$id --method DELETE
    done
```

Verify the release page looks correct:
```bash
gh release view v{X.Y.Z}
```

---

## Step 9 — Clean up branches

```bash
git checkout integration
git branch -d feat/bump-v{X.Y.Z} 2>/dev/null || true
git push origin --delete release/v{X.Y.Z} 2>/dev/null || true
git branch -d release/v{X.Y.Z} 2>/dev/null || true
```

The git tag (`v{X.Y.Z}`) is the durable version marker — the release branch is deleted after the tag is confirmed.

---

## Step 10 — Final report

```
✓ Version bumped: {A.B.C} → {X.Y.Z}
✓ docs/patch-notes.md updated
✓ docs/capabilities.md — all shipped caps marked merged
✓ staging → integration forwarded
✓ release/v{X.Y.Z} pushed — release.yml passed
✓ GitHub Release: https://github.com/joshuajerome/cutip/releases/tag/v{X.Y.Z}
✓ Assets: cutip-{X.Y.Z}-py3-none-any.whl (only)
```

---

## Rules

- Never push directly to `integration` — always merge staging in
- The release branch is created from `integration`, not staging
- Delete release branches after the GitHub Release is confirmed — git tags preserve versioned code
- Do not tag manually — `release.yml` creates the git tag via `softprops/action-gh-release`
- If `release.yml` fails, investigate logs before retrying
