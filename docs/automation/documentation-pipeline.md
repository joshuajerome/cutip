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

## GitHub Actions: `docs-ai-review.yml`

Fires on every push to `staging`. Performs a deeper AI-driven audit and deploys to GitHub Pages:

```
Checkout (full history)
  └── Install Dependencies (uv + anthropic SDK + docs extras)
        └── Analyze Code Changes       ← Claude: coverage gaps
              └── Scan Outdated Docs   ← Claude: stale references
                    └── Scan for Vulnerabilities  ← Claude: credentials, broken links
                          └── Update README        ← Claude: CLI/version drift
                                └── Post Claude Summary as PR comment
                                      └── Deploy GitHub Pages (mkdocs gh-deploy)
                                            └── Build & Verify MkDocs (strict)
```

### Stage details

#### Analyze Code Changes

Diffs changed `.py` files since the last commit and calls Claude to identify documentation coverage gaps for changed modules.

- Script: `.github/scripts/analyze-doc-coverage.py`
- Prompt: `.github/prompts/analyze-doc-coverage.md`
- Output: `claude-reports/analyze-doc-coverage.md`

#### Scan Documentation for Outdated Content

Claude audits `docs/` against key source files to find stale references — removed CLI flags, renamed classes, deleted backends.

- Script: `.github/scripts/scan-outdated-docs.py`
- Prompt: `.github/prompts/scan-outdated-docs.md`
- Output: `claude-reports/scan-outdated-docs.md`
- Exit: `1` if `VERDICT: FAIL` (HIGH severity stale refs)

#### Scan for Vulnerabilities

Claude scans `docs/` for accidentally included credentials, private paths, and broken external links.

- Script: `.github/scripts/scan-doc-vulnerabilities.py`
- Prompt: `.github/prompts/scan-doc-vulnerabilities.md`
- Output: `claude-reports/scan-doc-vulnerabilities.md`
- Exit: `1` if `VERDICT: FAIL` (HIGH severity findings)

#### Update README

Claude checks whether `cutip --help` output or the version in `pyproject.toml` has drifted from what's documented in `README.md`. If drift is detected, updated sections are written for human review.

- Script: `.github/scripts/update-readme.py`
- Prompt: `.github/prompts/update-readme.md`
- Output: `claude-reports/update-readme.md`

#### Post Claude Summary

All per-script reports are compiled into `claude-reports/summary.md`. If an open PR exists for the triggering branch, the summary is posted as a PR comment via `gh pr comment`. Reports are archived as workflow artifacts.

#### Deploy GitHub Pages

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

## Secrets required

| Secret | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | All Claude API calls |
| `GITHUB_TOKEN` | Posting PR comments and deploying GitHub Pages (automatic) |

---

## Prompt files

All Claude prompts are editable Markdown files — no code changes required:

| Prompt | Path |
|---|---|
| Coverage analysis | `.github/prompts/analyze-doc-coverage.md` |
| Outdated docs scan | `.github/prompts/scan-outdated-docs.md` |
| Vulnerability scan | `.github/prompts/scan-doc-vulnerabilities.md` |
| README update | `.github/prompts/update-readme.md` |
