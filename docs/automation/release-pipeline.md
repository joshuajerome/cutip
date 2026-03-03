# Release Pipeline

A CUTIP release produces a versioned Python wheel published to a GitHub Release and tagged with a git tag. Release branches are temporary — the **git tag** is the durable version marker.

---

## Trigger

Push to `release/v{X.Y.Z}` — triggers `release.yml`.

---

## GitHub Actions: `release.yml`

```
Push to release/v{X.Y.Z}
      │
      ▼
  Build wheel (uv build --wheel)
      │
      ▼
  Create GitHub Release
      │   - Tag: v{X.Y.Z}
      │   - Uploads wheel as asset
      │
      ▼
  Release published
```

The git tag (`v{X.Y.Z}`) is created by `softprops/action-gh-release` as part of the release step. Do not tag manually.

---

## Release branch lifecycle

Release branches (`release/v{X.Y.Z}`) are **short-lived**:

1. Created from `integration`
2. Pushed to trigger `release.yml`
3. Deleted after the GitHub Release is published

Versioned code is preserved via the **git tag** (`v{X.Y.Z}`), not via a permanent branch.

---

## Full release sequence

```
1. Bump version in pyproject.toml
2. Update docs/patch-notes.md
3. PR → staging → merge
4. Forward staging → integration
5. git checkout -b release/v{X.Y.Z} origin/integration
6. git push -u origin release/v{X.Y.Z}
7. Watch release.yml until complete
8. Edit GitHub Release notes (Features + Patch Notes)
9. Remove non-wheel assets from release
10. git branch -d release/v{X.Y.Z}  (tag persists)
```

See the complete playbook: [`.claude/workflows/release.md`](https://github.com/joshuajerome/cutip/blob/integration/.claude/workflows/release.md)

---

## GitHub Release structure

Release notes use the format from `.claude/templates/github-release-notes.md`:

```markdown
## Features
- **cap{N} — {title}**: {user-facing description}

## Patch Notes
- **cap{N} — {title}**: {user-facing description}

## Installation
pip install cutip=={X.Y.Z}
```

- `## Features` — `feat/*` caps shipped in this release
- `## Patch Notes` — `bug/*` caps shipped in this release
- No PR numbers, no authors, no GitHub-generated "What's Changed"

---

## Patch notes

`docs/patch-notes.md` is updated as part of every release. Each entry follows the same structure:

```markdown
## v{X.Y.Z} ({YYYY-MM-DD})

### Features
- **cap{N}** — {title}: {description}

### Patch Notes
- **cap{N}** — {title}: {description}
```
