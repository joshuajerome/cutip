# Feature or Bug Fix — End-to-End Playbook

Follow this playbook **completely** for every `feat/cap{N}` or `bug/cap{N}` deliverable.
Do not stop at PR creation. Do not stop at push. Finish when all completion criteria are met.

---

## Completion Criteria

All of the following must be true before reporting done:

- [ ] Tests pass locally
- [ ] Branch pushed, PR opened with correct body (from `.claude/templates/pr-body.md`)
- [ ] All CI checks green (`gh pr checks --watch`)
- [ ] PR merged to staging (`gh pr merge --merge --delete-branch`)
- [ ] `docs-generate.yml` run confirmed (or reported as queued)
- [ ] Final summary printed to user

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
2. Fix locally, push — CI reruns automatically
3. Never merge a PR with failing checks

---

## Step 9 — Merge

```bash
gh pr merge <PR_NUMBER> --merge --delete-branch
```

---

## Step 10 — Confirm docs-generate fired

```bash
gh run list --workflow docs-generate.yml --limit 3
```

A run should appear within ~30 seconds of the merge. If a `docs/cap{N}-*` PR was opened, note its URL.

---

## Step 11 — Final report

```
✓ cap{N} — {title}
✓ Branch: {feat|bug}/cap{N}-{slug}
✓ PR #{N} merged to staging
✓ docs-generate: {run URL or "queued — run ID {N}"}
  docs PR: {URL or "not yet opened"}
```

---

## Rules

- Never merge with failing CI
- One cap ID per PR — never mix changes
- Always use `[cap{N}]` prefix on commits and PR titles
- Stage specific files — never `git add -A`
- Never skip Step 3 (read before editing)
