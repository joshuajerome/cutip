# resolve-issues

Fetch all open GitHub issues, group them by root cause, fix each group on a dedicated branch, open PRs, and comment on every issue with the resolution and a downloadable wheel.

---

## Workflow

### Step 1 — Fetch and parse open issues

```bash
gh issue list --state open --json number,title,body,labels --limit 100
```

Read each issue body carefully. Look at attached logs, stack traces, and reproduction steps.

### Step 2 — Group by root cause

Group issues where a single code change will resolve multiple issues (shared root cause, related components, same error path). List ungrouped issues individually.

Print a summary:

```
Group A (issues #3, #7): Empty generated vars silently map to project root
Group B (issue #5): Missing required var not caught until container start
Standalone (issue #9): Tab completion broken on zsh
```

Then immediately begin fixing all groups without waiting for approval.

### Step 3 — Assign cap IDs

For each group or standalone issue:
1. Read `docs/capabilities.md` to find the next unused ID
2. State: "Assigning **cap{N}**: {title}. Branch: `bug/cap{N}-<short-desc>`."
3. Do this for all groups before branching — assign IDs sequentially

### Step 4 — Branch, fix, and commit (per group)

For each cap ID:

```bash
git checkout staging && git pull
git checkout -b bug/cap{N}-<short-desc>
```

- Read the relevant source files before making any change
- Fix the root cause — do not patch symptoms or add workarounds
- Commit with prefix: `[cap{N}] fix: <description>`
- Push the branch

### Step 5 — Build a wheel for this fix

```bash
uv build --wheel
```

This produces `dist/cutip-X.Y.Z-py3-none-any.whl`. Note the path — it will be attached to the PR and referenced in issue comments.

### Step 6 — Open a PR

```bash
gh pr create --base staging \
  --title "[cap{N}] fix: <description>" \
  --body "..." \
  --label "bug" \
  --assignee joshuajerome
```

PR body must include:
- **Root cause**: one sentence explaining what was wrong
- **Fix**: what changed and why
- **Issues resolved**: `Closes #N, Closes #M`
- **Test plan**: checklist

### Step 7 — Upload wheel and comment on every resolved issue

For each issue resolved by this group:

```bash
gh issue comment {number} --body "..."
```

Comment body:
```
**Resolved in PR #<N> — [cap{X}]**

**Root cause:** <one sentence>

**Fix:** <what changed>

**Wheel with fix:** download `cutip-X.Y.Z-py3-none-any.whl` from the PR's wheel-build artifact, or wait for it to ship in the next release.

This issue will be closed automatically when the PR merges to staging.
```

### Step 8 — Repeat for all groups

Work through all groups and standalone issues. After all PRs are open, print a summary table:

```
| Cap ID | Branch                        | PR  | Issues Closed |
|--------|-------------------------------|-----|---------------|
| cap007 | bug/cap007-empty-generated-var | #17 | #3, #7        |
| cap008 | bug/cap008-zsh-completion      | #18 | #9            |
```

---

## Rules

- Never auto-commit. Only commit when a fix is complete and tested locally (`uv run pytest tests/ --ignore=tests/e2e`)
- One branch per cap ID — never mix fixes
- Always read source files before editing
- Do not close issues manually — they close via `Closes #N` in the PR body when merged
- If a fix requires more investigation, open a draft PR and note what is unclear in the issue comment
