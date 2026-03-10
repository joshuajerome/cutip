# GitHub PR Conventions

Pull request standards for the CUTIP project.

---

## Branch → PR Mapping

| Branch pattern | Base branch | Label | Assignee |
|----------------|-------------|-------|----------|
| `feat/cap{N}-*` | `staging` | `feature` | `joshuajerome` |
| `bug/cap{N}-*` | `staging` | `bugfix` | `joshuajerome` |
| `docs/cap{N}-*` | `staging` | `documentation` | `joshuajerome` |
| `gh/*` | `staging` | `automation` | `joshuajerome` |
| `claude/*` | `staging` | — | `joshuajerome` |
| `release/v*` | — | — | — (handled by release.yml) |

## PR Title Format

```
[cap{N}] Short imperative description
```

For non-cap branches (gh/*, claude/*): use a descriptive title without cap prefix.

## PR Body Template

Use `.claude/templates/pr-body.md` — pick the section matching your branch type.

## CI Expectations

All PRs to `staging` and `integration` run `.github/workflows/pr-checks.yml`:
- Wheel build
- Unit tests (`pytest tests/ -v --ignore=tests/e2e`)
- Lint / type checks (if configured)

PRs must pass all checks before merge. For transient CI failures:
```bash
gh run rerun <run-id> --failed
```

## Label Rules

- **`feature`** — NOT "feat". Use `--label "feature"` for feature PRs.
- **`bugfix`** — for bug fix PRs
- **`documentation`** — for docs-only PRs
- **`automation`** — for CI/CD and workflow changes

## Merge Strategy

- Squash merge for feature/bug branches → staging
- Merge commit for staging → integration (preserves history)
- Never force-push to `staging` or `integration`

## Auto-generated PRs

After a PR merges to `staging`, `.github/workflows/docs-generate.yml` auto-creates a `docs/cap{N}-*` PR with updated patch notes and capability registry entries.
