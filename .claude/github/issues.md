# GitHub Issue Pipeline

How CUTIP handles automated issue diagnosis and resolution via GitHub Actions.

---

## State Machine

Issues progress through labels that represent pipeline stages:

```
(new issue opened)
    │
    ▼ bot posts welcome message + commands table
    │
    ├── repo owner → auto-triggers diagnosis
    │
    └── external user → reply `@claude continue`
            │
            ▼ bot acknowledges, runs diagnosis
claude-diagnosing  (transient — while Claude is working)
    │
    ▼ diagnosis posted as comment
claude-diagnosed
    │
    ▼ user replies `@claude acknowledge`
claude-acknowledged
    │
    ▼ user or code owner replies `@claude continue`
claude-fixing  (transient — while Claude generates fix)
    │
    ▼ fix branch pushed + TestPyPI published
claude-fixed
    │
    ├─▶ `@claude approve` → waits for `@claude continue`
    │       │
    │       ▼ PR opened to staging
    │   claude-staging
    │
    └─▶ `@claude deny` → resets to claude-diagnosed
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

## Commands

All commands use `@claude <command>` syntax in issue comments.

| Command | Description | Valid when |
|---------|-------------|-----------|
| `@claude continue` | Advance to the next pipeline stage | Any non-transient state |
| `@claude acknowledge` | Accept the diagnosis | `claude-diagnosed` |
| `@claude approve` | Approve the generated fix | `claude-fixed` |
| `@claude deny` | Reject fix, post re-entry template | `claude-fixed` |
| `@claude status` | Show current pipeline state and next action | Any state |
| `@claude retry` | Re-run the current stage (re-diagnose or re-fix) | `claude-diagnosed`, `claude-acknowledged`, `claude-fixed` |

Invalid commands or commands in the wrong state produce a warning with guidance.

## Workflow Triggers

| Event | Job | Effect |
|-------|-----|--------|
| `issues: [opened]` | `welcome` | Post welcome message with commands table. Auto-diagnose for repo owner. |
| `issue_comment: [created]` containing `@claude` | `handle-command` | Parse command and dispatch based on current label state. |

## Repo Owner Fast Path

When the repository owner opens an issue, the bot:
1. Posts the welcome message (noting auto-diagnosis)
2. Immediately posts `@claude continue` on behalf of the owner
3. Diagnosis starts without manual intervention

## Bot Identity

Comments are posted by `cutip-bot` (GitHub App). Falls back to `github-actions[bot]` if the App is not configured. See cap025 for setup.

## Scripts

| Script | Purpose |
|--------|---------|
| `.github/scripts/diagnose-issue.py` | Calls Claude API to diagnose root cause |
| `.github/scripts/fix-issue.py` | Calls Claude API to generate minimal fix |
| `.github/scripts/deny-template.md` | Re-entry template for rejected fixes |

## Self-Service Mode

Users with `ANTHROPIC_API_KEY` can bypass the pipeline and run diagnosis/fixes locally via `cutip issue diagnose` and `cutip issue fix`. See cap027.
