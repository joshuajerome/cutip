# Automation Overview

CUTIP enforces a consistent end-to-end lifecycle for every change — from a local branch to a deployed GitHub Release. This section documents each pipeline, what triggers it, and the playbooks that drive it.

---

## The three pipelines

| Pipeline | Trigger | Purpose |
|---|---|---|
| [Feature / Fix](feature-fix-pipeline.md) | Push to `feat/**` or `bug/**` | Code changes: test, validate, and ship a capability |
| [Documentation](documentation-pipeline.md) | Push to `staging` or `docs/**` | AI-driven docs audit, README sync, and GitHub Pages deploy |
| [Release](release-pipeline.md) | Push to `release/**` | Build wheel, publish GitHub Release, tag version |

---

## Full e2e flow

```
feat/cap{N} branch
      │
      ▼
  local tests pass
      │
      ▼
  PR → staging
      │
      ├── GHA: pr-checks.yml  (unit tests, smoke test, e2e, wheel build)
      │
      ▼
  merge to staging
      │
      ├── GHA: docs-generate.yml  (auto-generates docs PR if feat/* or bug/*)
      │   └── docs/cap{N}-* PR → CI → merge
      │
      ├── Jenkins: docs.Jenkinsfile  (AI audit, README sync, gh-pages deploy)
      │
      ▼
  staging → integration (fast-forward merge)
      │
      ▼
  release/v{X.Y.Z} branch pushed
      │
      ├── GHA: release.yml  (wheel build → GitHub Release + git tag)
      │
      ▼
  v{X.Y.Z} released
```

---

## Playbooks (Claude uses these)

When Claude Code runs any of these pipelines end-to-end, it follows the corresponding playbook:

| Playbook | Path |
|---|---|
| Feature / fix | [`.claude/workflows/feature-fix.md`](https://github.com/joshuajerome/cutip/blob/integration/.claude/workflows/feature-fix.md) |
| Release | [`.claude/workflows/release.md`](https://github.com/joshuajerome/cutip/blob/integration/.claude/workflows/release.md) |

---

## Branch conventions

```
integration   permanent protected trunk
staging       permanent protected gate — all PRs merge here first
gh-pages      auto-managed by MkDocs gh-deploy (never commit manually)
```

Feature and fix branches (`feat/cap{N}-*`, `bug/cap{N}-*`) are short-lived — deleted after merge. Release versions are preserved as **git tags** (`v{X.Y.Z}`), not as permanent branches.
