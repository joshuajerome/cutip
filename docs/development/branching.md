# Branching Guide

## Branch Architecture

```
integration  (permanent protected — the stable trunk)
    └── ← staging merges here after all checks pass
    └── release/v{major}.{minor}.{patch}  ← targeted releases

staging  (permanent protected — integration gate)
    ← feat/cap{N}-<desc>    (code feature branches)
    ← bug/cap{N}-<desc>     (bug fix branches)
    ← docs/cap{N}-<desc>    (auto-generated after feat/bug merge)
    ← gh/<desc>             (GitHub Actions workflow changes)
    ← claude/<desc>         (.claude/, skills, memory changes)
```

Local development happens directly — no shared sandbox branch.
New work starts from a fresh branch off `staging` (or `integration` for hotfixes).

## Branch Types

| Prefix | Purpose | Triggers |
|--------|---------|----------|
| `feat/cap{N}-<desc>` | New feature | `wheel-build.yml` on push |
| `bug/cap{N}-<desc>` | Bug fix | `wheel-build.yml` on push |
| `docs/cap{N}-<desc>` | Auto-generated or manual docs | `docs-check.yml` on push |
| `gh/<desc>` | CI/GitHub Actions changes | `wheel-build.yml` on push |
| `claude/<desc>` | Claude Code config changes | `wheel-build.yml` on push |
| `release/v{ver}` | Release pipeline | `release.yml` on push |

## Capability ID System

Every feature or bug fix is assigned a **capability ID** (`cap001`, `cap002`, ...).

### Assigning a Cap ID

1. Read `docs/capabilities.md` to find the next unused ID
2. Create branch: `feat/cap{N}-<short-desc>` or `bug/cap{N}-<short-desc>`
3. Prefix all commits: `[cap{N}] short message`
4. Title PRs: `[cap{N}] Description of capability`

### Format Rules

- IDs are zero-padded to 3 digits: `cap001`, `cap010`, `cap999`
- Extensible beyond 3 digits: `cap1000`
- IDs are never reused or skipped

## Branch Protection

| Branch | Requires PR | Status Checks | Force Push |
|--------|-------------|---------------|------------|
| `integration` | Yes | all `pr-checks` jobs | Blocked |
| `staging` | Yes | all `pr-checks` jobs | Blocked |
| `release/*` | Yes | all `pr-checks` jobs | Blocked |

**Required status checks** (must all pass before merge):
- `pr-checks / unit-tests`
- `pr-checks / smoke-test`
- `pr-checks / e2e-podman-ubuntu`
- `pr-checks / e2e-podman-windows`
- `pr-checks / docs-build`

## Workflow: Feature Development

```
1. git checkout staging && git pull
2. git checkout -b feat/cap{N}-<desc>
3. ... develop, commit with [cap{N}] prefix ...
4. git push -u origin feat/cap{N}-<desc>
5. Open PR → staging
6. All pr-checks pass → merge
7. docs-generate.yml auto-creates docs/cap{N}-<desc> PR
8. When staging is stable: open PR → integration
```

## Workflow: Release

```
1. git checkout integration && git pull
2. git checkout -b release/v{X}.{Y}.{Z}
3. git push -u origin release/v{X}.{Y}.{Z}
4. release.yml runs all checks, builds wheel, creates GitHub Release
```

## Automated Docs Generation

After a `feat/*` or `bug/*` branch merges to `staging`, the `docs-generate.yml`
workflow:

1. Detects the source branch type and cap ID from the merge commit
2. Calls the Anthropic API (`claude-sonnet-4-6`) to generate:
   - A patch note entry for `docs/patch-notes.md`
   - A capability registry row for `docs/capabilities.md`
3. Creates a `docs/cap{N}-<desc>` branch with the changes
4. Opens a PR to `staging` with the `docs-auto` label

> **Prerequisite**: The `ANTHROPIC_API_KEY` secret must be set in the GitHub repo
> (Settings → Secrets → Actions). This requires an Anthropic API key from
> `console.anthropic.com` — not a Claude.ai Pro subscription.
