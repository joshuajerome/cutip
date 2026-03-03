# Feature / Fix Pipeline

Every capability (`feat/cap{N}`) and bug fix (`bug/cap{N}`) runs through the same end-to-end pipeline before landing in `integration`.

---

## Trigger

- Push to `feat/**` or `bug/**` — triggers GHA `pr-checks.yml` and `wheel-build.yml`
- PR opened targeting `staging` — triggers the same checks

---

## GitHub Actions stages

### `pr-checks.yml`

| Step | Command |
|---|---|
| Unit tests | `uv run pytest tests/ -v --ignore=tests/e2e --tb=short` |
| Smoke test | Build wheel → install in isolated venv → `import cutip` |
| E2E | `cutip validate` + `cutip run hello --local` |

All checks must pass before merge is allowed.

### `wheel-build.yml`

Builds the distributable `.whl` and archives it as a workflow artifact. Runs on every push to `feat/**`, `bug/**`, and `claude/**`.

---

## Jenkins stages (`build.Jenkinsfile`)

The Jenkins build pipeline mirrors GHA but runs on the Jenkins agent (which has Podman available unconditionally):

```
Checkout → Install Dependencies → Unit Tests → Smoke Test → E2E → Build Wheel
```

| Stage | Notes |
|---|---|
| Unit Tests | JUnit XML archived |
| Smoke Test | Wheel installed in isolated `.wheel-test` venv |
| E2E | `cutip run hello --local` — Podman always available |
| Build Wheel | `.whl` archived as Jenkins artifact |

---

## Post-merge: docs-generate

After merge to `staging`, `docs-generate.yml` fires automatically for `feat/*` and `bug/*` merges. If documentation changes are detected, it opens a `docs/cap{N}-*` PR. That PR must also be merged before the task is complete.

---

## Full e2e sequence

```
1. Branch from staging: feat/cap{N}-slug
2. Implement + run tests locally
3. Push → GHA pr-checks.yml runs
4. Open PR to staging (with assignee + label)
5. All checks pass → merge --merge --delete-branch
6. docs-generate fires → merge docs PR if created
7. Forward staging → integration
8. Prune local branch
```

See the complete playbook: [`.claude/workflows/feature-fix.md`](https://github.com/joshuajerome/cutip/blob/integration/.claude/workflows/feature-fix.md)

---

## Capability ID system

Every feature or fix is assigned a cap ID (`cap001`, `cap002`, ...) tracked in [`docs/capabilities.md`](../capabilities.md). The cap ID appears in:

- Branch name: `feat/cap{N}-slug`
- Commit prefix: `[cap{N}] message`
- PR title: `[cap{N}] Description`
