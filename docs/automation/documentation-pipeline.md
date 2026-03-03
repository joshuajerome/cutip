# Documentation Pipeline

The documentation pipeline runs automatically after any merge to `staging` (for `feat/*` or `bug/*`) or any push to `docs/**`. It is AI-driven — Claude audits documentation for drift, vulnerabilities, and coverage gaps, then posts a summary as a PR comment.

---

## Trigger

- Push to `staging` (after feat/bug merge)
- Push to `docs/**`

---

## GitHub Actions: `docs-check.yml`

Runs on every push to `docs/**` and every PR touching `docs/`. Validates that `mkdocs build --strict` passes with no warnings.

## GitHub Actions: `docs-generate.yml`

Fires after a `feat/*` or `bug/*` branch merges to `staging`. Uses Claude to generate documentation for changed Python modules and opens a `docs/cap{N}-*` PR.

---

## Jenkins: `docs.Jenkinsfile`

The Jenkins docs pipeline performs a deeper AI-driven audit and deploys to GitHub Pages:

```
Checkout
  └── Install Dependencies (uv + anthropic SDK)
        └── Analyze Code Changes       ← Claude: coverage gaps
              └── Scan Outdated Docs   ← Claude: stale references
                    └── Scan for Vulnerabilities  ← Claude: credentials, broken links
                          └── Update README        ← Claude: CLI/version drift
                                └── Claude AI Summary  ← posts PR comment
                                      └── Update GitHub Pages (mkdocs gh-deploy)
                                            └── Build & Verify MkDocs
```

### Stage details

#### Analyze Code Changes

Diffs changed `.py` files since the last commit and calls Claude to identify documentation coverage gaps for changed modules.

- Script: `.jenkins/scripts/analyze-doc-coverage.py`
- Prompt: `.jenkins/prompts/analyze-doc-coverage.md`
- Output: `claude-reports/analyze-doc-coverage.md`

#### Scan Documentation for Outdated Content

Claude audits `docs/` against key source files to find stale references — removed CLI flags, renamed classes, deleted backends.

- Script: `.jenkins/scripts/scan-outdated-docs.py`
- Prompt: `.jenkins/prompts/scan-outdated-docs.md`
- Output: `claude-reports/scan-outdated-docs.md`
- Exit: `1` if `VERDICT: FAIL` (HIGH severity stale refs)

#### Scan for Vulnerabilities

Claude scans `docs/` for accidentally included credentials, private paths, and broken external links.

- Script: `.jenkins/scripts/scan-doc-vulnerabilities.py`
- Prompt: `.jenkins/prompts/scan-doc-vulnerabilities.md`
- Output: `claude-reports/scan-doc-vulnerabilities.md`
- Exit: `1` if `VERDICT: FAIL` (HIGH severity findings)

#### Update README

Claude checks whether `cutip --help` output or the version in `pyproject.toml` has drifted from what's documented in `README.md`. If drift is detected, updated sections are written for human review.

- Script: `.jenkins/scripts/update-readme.py`
- Prompt: `.jenkins/prompts/update-readme.md`
- Output: `claude-reports/update-readme.md`

#### Claude AI Summary

All per-script reports are compiled into `claude-reports/summary.md`. If an open PR exists for the triggering branch, the summary is posted as a PR comment via `gh pr comment`. Reports are always archived as Jenkins build artifacts.

#### Update GitHub Pages

```bash
uv run mkdocs gh-deploy --force
```

Deploys the current `docs/` to the `gh-pages` branch → live at [joshuajerome.github.io/cutip](https://joshuajerome.github.io/cutip).

#### Build & Verify MkDocs

```bash
uv run mkdocs build --strict
```

Builds the static site and spins up a local server to verify key pages return HTTP 200.

---

## Credentials required (Jenkins)

| Credential ID | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | All Claude API calls |
| `GITHUB_TOKEN` | Posting PR comments via `gh` |

---

## Prompt files

All Claude prompts are editable Markdown files — no code changes required:

| Prompt | Path |
|---|---|
| Coverage analysis | `.jenkins/prompts/analyze-doc-coverage.md` |
| Outdated docs scan | `.jenkins/prompts/scan-outdated-docs.md` |
| Vulnerability scan | `.jenkins/prompts/scan-doc-vulnerabilities.md` |
| README update | `.jenkins/prompts/update-readme.md` |
