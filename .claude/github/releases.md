# GitHub Release Pipeline

How CUTIP versions are cut and published.

---

## Release Flow

```
integration (stable) → release/v{X}.{Y}.{Z} branch
    → release.yml creates git tag v{X.Y.Z}
    → GitHub Release page created
    → Wheel asset attached
    → Branch deleted (tag is the durable marker)
```

## Steps (automated by `.claude/workflows/release.md`)

1. Determine version: read `pyproject.toml`, increment per semver
2. Identify shipped caps: all `merged` caps since last release tag
3. Draft release notes using `.claude/templates/github-release-notes.md`
4. Version bump PR to `staging` (updates `pyproject.toml` + `docs/patch-notes.md`)
5. Update `docs/capabilities.md` status for shipped caps
6. Forward `staging` → `integration` via PR
7. Cut `release/v{X}.{Y}.{Z}` branch from `integration`
8. Edit GitHub Release: remove non-wheel assets (source archives)
9. Clean up: delete release branch (tag persists)
10. Print final report

## Release Notes Format

Use `.claude/templates/github-release-notes.md` template. Sections:

- **What's New** — user-facing features
- **Bug Fixes** — resolved issues
- **Internal** — CI, docs, refactoring (if any)
- **Install** — pip/uv install command with version

## Asset Cleanup

GitHub auto-attaches source archives (`.tar.gz`, `.zip`) to releases. The `release.yml` workflow builds and attaches the wheel (`.whl`). After release:
- Keep: `.whl` file
- Remove: source archives (users should install from PyPI, not source)

## Test PyPI

Every push to `staging` or `integration` publishes a dev build to Test PyPI. Users can test pre-release:

```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "cutip>=0.1.5.dev0"
```

## Version Convention

- `{major}.{minor}.{patch}` — semver
- Tags: `v{major}.{minor}.{patch}` (e.g., `v0.1.9`)
- Dev builds on Test PyPI: `{version}.dev{N}`
