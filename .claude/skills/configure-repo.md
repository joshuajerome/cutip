# configure-repo

Configure a repository with the deterministic multi-branch workflow used by CUTIP.

## What This Skill Does

When the user runs `/configure-repo`, you will:

1. **Inspect** the current repository
2. **Ask** the user for project-specific details
3. **Apply** the multi-branch workflow configuration
4. **Report** a summary of what was applied

This skill is **idempotent**: running it twice on the same repo produces the same result.

---

## Step 1: Inspect the Repo

Run these commands to understand the current state:

```bash
git remote -v
git branch -a
ls .github/workflows/ 2>/dev/null || echo "no workflows"
ls docs/ 2>/dev/null || echo "no docs dir"
cat pyproject.toml 2>/dev/null | head -20 || cat package.json 2>/dev/null | head -10 || echo "no manifest"
cat mkdocs.yml 2>/dev/null | head -5 || echo "no mkdocs"
gh auth status 2>/dev/null || echo "gh not authenticated"
```

Note:
- Current default branch (usually `main`)
- Existing workflow files
- Package manager (`uv`, `npm`, `cargo`, `pip`, etc.)
- Docs tool (`mkdocs`, `sphinx`, `storybook`, none)
- Whether `gh` CLI is authenticated

---

## Step 2: Ask the User

Ask ALL of the following questions before doing anything:

1. **Project name** — used in workflow names and CLAUDE.md
2. **Tech stack** — language, package manager, test runner command
3. **Docs tool** — mkdocs / sphinx / none
4. **Starting cap ID** — default: `cap001`
5. **GitHub owner/repo** — e.g. `joshuajerome/cutip` (for `gh api` calls)
6. **Default branch name** — the branch currently named `main` or equivalent

---

## Step 3: Apply Configuration

Apply each step only if not already done (idempotency check before each).

### 3a. Rename default branch → `integration`

```bash
# Check if integration already exists
if git show-ref --verify --quiet refs/heads/integration; then
  echo "integration branch already exists, skipping rename"
else
  git branch -m <current-default> integration
  git push origin integration
  echo "Pushed integration branch. You must now set the default branch on GitHub:"
  echo "  https://github.com/<owner>/<repo>/settings → Branches → Default branch"
fi
```

### 3b. Create `staging` branch

```bash
if git show-ref --verify --quiet refs/heads/staging; then
  echo "staging already exists, skipping"
else
  git checkout integration
  git checkout -b staging
  git push -u origin staging
fi
```

### 3c. Create workflow files

Check which files exist. Only create missing ones.

**wheel-build.yml** — triggered on push to feat/**, bug/**, claude/**:
```yaml
name: Wheel Build
on:
  push:
    branches: ["feat/**", "bug/**", "claude/**"]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { version: "latest" }
      - run: uv build --wheel
      - uses: actions/upload-artifact@v4
        with: { name: <project>-wheel, path: dist/*.whl, retention-days: 7 }
```

**pr-checks.yml** — triggered on PR to staging or integration. Jobs:
- `unit-tests`: run the test suite
- `smoke-test`: build wheel, install in clean venv, verify import
- `e2e-*`: platform-specific E2E tests (skip if not applicable)
- `docs-build`: `mkdocs build --strict` (or equivalent)

**docs-check.yml** — triggered on push to docs/** or PR touching docs/:
- Builds docs in strict mode

**docs-generate.yml** — triggered on push to staging:
- Detects if merged from feat/* or bug/*
- Calls `ANTHROPIC_API_KEY` via anthropic SDK
- Creates docs/* branch + opens PR

**release.yml** — triggered on push to release/**:
- Runs all checks
- Extracts version from branch name
- Builds artifacts + creates GitHub Release

### 3d. Create `docs/capabilities.md`

Only create if it doesn't exist:

```markdown
# Capabilities

| ID     | Title | Type | Status | Branch | PR | Date |
|--------|-------|------|--------|--------|----|------|
| <start-cap-id> | Initial scaffold | feat | merged | — | — | <today> |
```

### 3e. Create/update `CLAUDE.md`

Add these sections if not already present (check for "Branch Conventions" heading):

```markdown
## Branch Conventions

[branch diagram]

## Capability ID System

[cap ID assignment instructions]

## Commit Message Format

[cap{N}] short imperative description

## Workflow Stages

[stages: feat branch → staging → integration → release]
```

### 3f. Create `.github/scripts/generate-docs.py`

Copy the template from the CUTIP repo or generate inline. This script:
- Reads `ANTHROPIC_API_KEY`, `CAP_ID`, `SOURCE_BRANCH`, `COMMIT_MSG` from env
- Calls `claude-sonnet-4-6` to generate patch notes + capability entry
- Writes to `docs/capabilities.md` and `docs/patch-notes.md`

### 3g. Apply branch protections

Requires `gh auth login`. If authenticated:

```bash
REPO="<owner>/<repo>"
CHECKS='["pr-checks / unit-tests","pr-checks / smoke-test","pr-checks / docs-build"]'

for branch in integration staging; do
  gh api repos/${REPO}/branches/${branch}/protection \
    --method PUT \
    --field required_status_checks="{\"strict\":true,\"contexts\":${CHECKS}}" \
    --field enforce_admins=false \
    --field required_pull_request_reviews=null \
    --field restrictions=null \
    --field allow_force_pushes=false
done
```

If not authenticated, print instructions and create the script at
`.github/scripts/apply-branch-protections.sh`.

---

## Step 4: Report Summary

Print a checklist of what was applied vs. skipped:

```
✓ Renamed main → integration (pushed to origin)
✓ Created staging branch (pushed to origin)
✓ Created .github/workflows/wheel-build.yml
✓ Created .github/workflows/pr-checks.yml
✓ Created .github/workflows/docs-check.yml
✓ Created .github/workflows/docs-generate.yml
✓ Created .github/workflows/release.yml
✓ Created docs/capabilities.md
✓ Created docs/patch-notes.md
✓ Created .github/scripts/generate-docs.py
✓ Updated CLAUDE.md with branch conventions
⚠ Branch protections: gh not authenticated
    Run: gh auth login
    Then: bash .github/scripts/apply-branch-protections.sh <owner>/<repo>

Manual steps remaining:
  1. Set default branch to 'integration' on GitHub:
     https://github.com/<owner>/<repo>/settings → Branches
  2. Delete old 'main' branch from remote (after changing default):
     git push origin --delete main
  3. Add ANTHROPIC_API_KEY secret in repo settings:
     https://github.com/<owner>/<repo>/settings/secrets/actions
```

---

## Tech-Stack Substitution Table

When generating workflow files for non-uv projects, substitute:

| uv (Python) | npm (Node) | cargo (Rust) |
|-------------|------------|--------------|
| `astral-sh/setup-uv@v5` | `actions/setup-node@v4` | `dtolnay/rust-toolchain@stable` |
| `uv build --wheel` | `npm run build` | `cargo build --release` |
| `uv run pytest` | `npm test` | `cargo test` |
| `uv pip install -e .` | `npm ci` | (N/A) |
| `uv run mkdocs build` | (docs tool varies) | `cargo doc` |
