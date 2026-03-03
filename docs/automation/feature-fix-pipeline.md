# Feature / Fix Pipeline

Every capability (`feat/cap{N}`) and bug fix (`bug/cap{N}`) runs through the same end-to-end pipeline before landing in `integration`.

---

## Trigger

- Push to `feat/**` or `bug/**` — triggers `ci.yml` (unit-tests, smoke-test, docs-build, build-wheel)
- PR opened targeting `staging` — triggers all of the above plus E2E (Ubuntu, Windows, macOS validate)

---

## GitHub Actions: `ci.yml`

All CI runs through a single consolidated workflow file.

### On push to feature branch

| Job | Command |
|---|---|
| Unit tests | `uv run pytest tests/ -v --ignore=tests/e2e --tb=short` |
| Smoke test | Build wheel → install in isolated venv → `import cutip` + `cutip --help` |
| Docs build | `uv run mkdocs build --strict` |
| Build wheel | `uv build --wheel` → archived as workflow artifact |

### On PR to staging or integration (adds E2E)

| Job | What it runs |
|---|---|
| E2E · Ubuntu | `cutip validate` + `cutip run simple` + `cutip run complex` + from-compose suite |
| E2E · Windows | Same, using PowerShell and Podman Machine |
| Install & Validate · macOS | Install check + schema-only validate (no container runtime) |

E2E jobs carry `if: github.event_name == 'pull_request'` — they skip on push to feature branches and only gate PRs. GitHub treats skipped jobs as passing for branch-protection purposes.

All checks must pass before merge is allowed.

---

## Post-merge: docs-generate

After merge to `staging`, `docs-generate.yml` fires automatically for `feat/*` and `bug/*` merges. If documentation changes are detected, it opens a `docs/cap{N}-*` PR. That PR must also be merged before the task is complete.

---

## Full e2e sequence

```
1. Branch from staging: feat/cap{N}-slug
2. Implement + run tests locally
3. Push → ci.yml runs unit-tests, smoke-test, docs-build, build-wheel
4. Open PR to staging (auto-labeled + assigned by CI)
5. All checks pass (including E2E on PR) → merge --merge --delete-branch
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
