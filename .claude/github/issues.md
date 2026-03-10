# GitHub Issue Pipeline

How CUTIP handles automated issue diagnosis and resolution via GitHub Actions.

---

## State Machine

Issues progress through labels that represent pipeline stages:

```
(new issue)
    │
    ▼ code owner adds `claude-review` label
claude-review
    │
    ▼ workflow runs diagnosis
claude-diagnosing  (transient — while Claude is working)
    │
    ▼ diagnosis posted as comment
claude-diagnosed
    │
    ▼ user comments `/acknowledge`
claude-acknowledged
    │
    ▼ code owner comments `/continue`
claude-fixing  (transient — while Claude generates fix)
    │
    ▼ fix branch pushed + TestPyPI published
claude-fixed
    │
    ├─▶ user comments `/approve` → waits for code owner `/continue`
    │       │
    │       ▼ PR opened to staging
    │   claude-staging
    │
    └─▶ user comments `/deny` → resets to claude-diagnosed
            (re-entry template posted)
```

## Labels

| Label | Color | Description | Transient? |
|-------|-------|-------------|------------|
| `claude-review` | `#0075ca` | Needs Claude diagnosis | No |
| `claude-diagnosing` | `#e4e669` | Claude is diagnosing | Yes |
| `claude-diagnosed` | `#cfd3d7` | Claude diagnosis posted | No |
| `claude-acknowledged` | `#c2e0c6` | User acknowledged diagnosis | No |
| `claude-fixing` | `#e4e669` | Claude is generating fix | Yes |
| `claude-fixed` | `#0e8a16` | Claude fix ready for review | No |
| `claude-staging` | `#1d76db` | Fix PR opened to staging | No |

## Slash Commands

| Command | Who | When (required label) | Effect |
|---------|-----|-----------------------|--------|
| `/continue` | Code owner | `claude-review` (no label) | Start diagnosis |
| `/continue` | Code owner | `claude-acknowledged` | Start fix generation |
| `/continue` | Code owner | `claude-fixed` + `/approve` | Open PR to staging |
| `/acknowledge` | User | `claude-diagnosed` | Accept diagnosis, wait for code owner |
| `/approve` | User | `claude-fixed` | Approve the fix (needs code owner `/continue`) |
| `/deny` | User | `claude-fixed` | Reject fix, post re-entry template |

## Workflow File

`.github/workflows/issues.yml` — triggered by `issues: [labeled]` and `issue_comment: [created]`.

## Scripts

| Script | Purpose |
|--------|---------|
| `.github/scripts/diagnose-issue.py` | Calls Claude API to diagnose root cause |
| `.github/scripts/fix-issue.py` | Calls Claude API to generate minimal fix |
| `.github/scripts/deny-template.md` | Re-entry template for rejected fixes |

## Bot Identity

Comments are posted by `cutip-bot` (GitHub App). Falls back to `github-actions[bot]` if the App is not configured. See cap025 for setup.

## Self-Service Mode

Users with `ANTHROPIC_API_KEY` can bypass the pipeline and run diagnosis/fixes locally via `cutip issue diagnose` and `cutip issue fix`. See cap027.
