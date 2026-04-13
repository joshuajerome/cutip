# Feature or Bug Fix — End-to-End Playbook

Follow this playbook **completely** for every `feat/cap{N}` or `bug/cap{N}` deliverable.
Do not stop at PR creation. Do not stop at push. Finish when all completion criteria are met.

---

## Completion Criteria

All of the following must be true before reporting done:

- [ ] Tests pass locally
- [ ] PR opened with correct body, assignee, and label
- [ ] All CI checks green
- [ ] PR merged to staging
- [ ] docs-generate fired (confirmed or N/A for non-feat/bug branches)
- [ ] docs PR merged (if one was created)
- [ ] staging forwarded to integration
- [ ] Merged branch pruned locally
- [ ] Final summary printed

---

## Step 1 — Assign a Cap ID

1. Read `docs/capabilities.md`
2. Find the highest existing `cap{N}` ID and increment by 1
3. Announce: **"Assigning cap{N}: {title}. Branch: `{feat|bug}/cap{N}-{slug}`."**

Never reuse a cap ID. Never skip this step. Announce before branching.

---

## Step 2 — Branch from staging

```bash
git checkout staging && git pull origin staging
git checkout -b {feat|bug}/cap{N}-{slug}
```

- `feat/` for new capabilities
- `bug/` for fixes

---

## Step 3 — Read before editing

Before touching any file:

- Read every file you will modify
- Read any file whose logic you need to understand (callers, tests, models)

**Never edit a file you haven't read in this session.**

---

## Step 4 — Implement

- Fix the root cause — not the symptom
- Keep the diff minimal — no comments, refactors, or docstrings beyond what the task requires
- Do not add error handling for impossible cases

---

## Step 5 — Run tests

```bash
cd ~/dev/cutip && uv run pytest tests/ -v --ignore=tests/e2e
```

All tests must pass before committing. If a test fails, fix it first.

---

## Step 6 — Commit and push

```bash
git add <specific files — never git add -A or git add .>
git commit -m "[cap{N}] {feat|fix}: {short imperative description}"
git push -u origin {feat|bug}/cap{N}-{slug}
```

Commit message format: `[cap007] fix: handle missing key in _validate_vars`

---

## Step 7 — Open PR

Fill out the PR body using `.claude/templates/pr-body.md` (feat or bug section).
Write the filled body to `/tmp/pr-body.md`, then:

```bash
gh pr create \
  --base staging \
  --head {feat|bug}/cap{N}-{slug} \
  --title "[cap{N}] {description}" \
  --body-file /tmp/pr-body.md \
  --label "{feat|bug}" \
  --assignee joshuajerome
```

`--assignee` and `--label` are **required on every PR** — never omit them.

---

## Step 8 — Watch CI

```bash
gh pr checks <PR_NUMBER> --watch
```

Wait for **all checks to pass**. If a check fails:

1. Read the failure: `gh run view <run-id> --log-failed`
2. Diagnose: is this a code issue or a transient/pre-existing infra issue?
3. **Code issue** — fix locally, push. CI reruns automatically.
4. **Trivial / non-production failure** (pre-existing flake, infra timeout, unrelated scan) —
   if the failure cannot affect users and the PR change is correct, post a PR comment
   defending why the failure is not significant before merging:
   ```bash
   gh pr comment <PR_NUMBER> --body \
     "CI failure on <job-name>: <one sentence root cause>.
   This failure is pre-existing / unrelated to this PR's changes and does not affect
   production: <explain why no user-facing behavior is impacted>.
   Proceeding with merge."
   ```
5. Never merge a PR with a failure that could be a real code issue.

---

## Step 9 — Merge

```bash
gh pr merge <PR_NUMBER> --merge --delete-branch
```

---

## Step 10 — Wait for docs-generate and merge docs PR

```bash
# Wait for docs-generate run (fires within ~30s of merge for feat/* and bug/*)
gh run list --workflow docs-generate.yml --limit 3
```

If a `docs/cap{N}-*` PR was opened, watch its CI and merge it:

```bash
gh pr checks <DOCS_PR_NUMBER> --watch
gh pr merge <DOCS_PR_NUMBER> --merge --delete-branch
```

Note: docs-generate only fires for `feat/*` and `bug/*` merges. If no docs PR is created, mark this step N/A.

---

## Step 11 — Forward staging → integration

```bash
git checkout integration && git pull origin integration
git merge origin/staging --no-edit
git push origin integration
```

---

## Step 12 — Prune merged branches

```bash
git fetch --prune
git branch -d {feat|bug}/cap{N}-{slug} 2>/dev/null || true
```

---

## Step 13 — Final report

```
✓ cap{N} — {title}
✓ Branch: {feat|bug}/cap{N}-{slug}
✓ PR #{N} merged to staging
✓ docs-generate: {run URL or "N/A"}
  docs PR: {URL and merged, or "N/A"}
✓ staging forwarded to integration
✓ Branch pruned locally
```

---

## Rules

- Never merge with failing CI
- One cap ID per PR — never mix changes
- Always use `[cap{N}]` prefix on commits and PR titles
- Stage specific files — never `git add -A`
- Never skip Step 3 (read before editing)
- When asked to raise a PR, complete the entire e2e: PR → GHA → staging → integration → branch prune
