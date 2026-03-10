# Repository Setup Guide

How the CUTIP GitHub repository is configured. Follow this guide to replicate the repository structure for a new project.

---

## GitHub "About" Section

Configure at **Settings → General → About** (or the gear icon on the repo page):

| Field | Value |
|-------|-------|
| **Description** | `A deterministic framework for building and orchestrating container workloads.` |
| **Website** | `https://joshuajerome.github.io/cutip/` |
| **Topics** | `automation`, `cli`, `containers`, `podman`, `python`, `workflow`, `yaml` |
| **Include in home page** | Releases ✓, Packages ✗, Deployments ✓ |

---

## README Badges

```markdown
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/latest/)
[![uv](https://img.shields.io/badge/uv-package_manager-6e44ff)](https://github.com/astral-sh/uv)
[![Runtime](https://img.shields.io/badge/runtime-podman%20%7C%20docker-892ca0)](https://joshuajerome.github.io/cutip/getting-started/installation/)
[![CI](https://github.com/joshuajerome/cutip/actions/workflows/ci.yml/badge.svg)](https://github.com/joshuajerome/cutip/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-github%20pages-0969da)](https://joshuajerome.github.io/cutip)
```

Pattern: static shields.io badges for tech stack, dynamic badge for CI status, link badge for docs.

---

## Default Branch

The default branch is **`integration`** (not `main`). Set at **Settings → Branches → Default branch**.

---

## Branch Protection Rules

Three permanent protected branches. Apply via **Settings → Branches → Add rule** or use the automation script:

```bash
bash .github/scripts/apply-branch-protections.sh joshuajerome/cutip
```

### `integration` (trunk)

| Setting | Value |
|---------|-------|
| Require pull request before merging | Yes |
| Required approvals | 0 (bot-driven merges) |
| Require status checks to pass | Yes |
| Required checks | `Unit Tests`, `Smoke Test`, `Docs Build`, `MkDocs · Build` |
| Require branches to be up to date | Yes |
| Restrict who can push | Admins only |

### `staging` (integration gate)

| Setting | Value |
|---------|-------|
| Require pull request before merging | Yes |
| Required approvals | 0 |
| Require status checks to pass | Yes |
| Required checks | `Unit Tests`, `Smoke Test` |
| Allow force pushes | No |

### `gh-pages` (docs deployment)

| Setting | Value |
|---------|-------|
| Restrict who can push | Deploy keys / Actions only |

---

## Ephemeral Branch Naming

| Pattern | Purpose | Base | Deleted after |
|---------|---------|------|---------------|
| `feat/cap{N}-<desc>` | New feature | `staging` | Merge to staging |
| `bug/cap{N}-<desc>` | Bug fix | `staging` | Merge to staging |
| `docs/cap{N}-<desc>` | Auto-generated docs | `staging` | Merge to staging |
| `gh/<desc>` | CI/CD changes | `staging` | Merge to staging |
| `claude/<desc>` | .claude/ changes | `staging` | Merge to staging |
| `release/v{X}.{Y}.{Z}` | Release cut | `integration` | After tag confirmed |

---

## GitHub Labels

Create these labels (the issue workflow auto-creates the `claude-*` labels):

| Label | Color | Purpose |
|-------|-------|---------|
| `feature` | `#0e8a16` | Feature PRs (NOT "feat") |
| `bugfix` | `#d73a4a` | Bug fix PRs |
| `documentation` | `#0075ca` | Docs-only PRs |
| `automation` | `#e4e669` | CI/CD changes |
| `claude-review` | `#0075ca` | Issue needs Claude diagnosis |
| `claude-diagnosing` | `#e4e669` | Claude is diagnosing (transient) |
| `claude-diagnosed` | `#cfd3d7` | Diagnosis posted |
| `claude-acknowledged` | `#c2e0c6` | User acknowledged diagnosis |
| `claude-fixing` | `#e4e669` | Claude generating fix (transient) |
| `claude-fixed` | `#0e8a16` | Fix ready for review |
| `claude-staging` | `#1d76db` | PR opened to staging |

---

## Repository Secrets

Add at **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Required by | Purpose |
|--------|-------------|---------|
| `ANTHROPIC_API_KEY` | `issues.yml`, `docs.yml` | Claude API calls for issue diagnosis, fix generation, doc generation |
| `APP_ID` | `issues.yml` | GitHub App numeric ID for bot identity |
| `APP_PRIVATE_KEY` | `issues.yml` | GitHub App `.pem` private key for bot identity |
| `TEST_PYPI_TOKEN` | `integration.yml`, `issues.yml` | Publish dev builds to Test PyPI |

> [!NOTE]
> `GITHUB_TOKEN` is automatic — no setup needed. If `APP_ID`/`APP_PRIVATE_KEY` are missing, workflows fall back to `github-actions[bot]`.

---

## GitHub App (Bot Identity)

Create at **github.com/settings/apps/new**:

| Field | Value |
|-------|-------|
| Name | `cutip-bot` |
| Description | Bot identity for CUTIP automated issue pipeline |
| Homepage URL | `https://github.com/joshuajerome/cutip` |
| Webhook | Unchecked (not needed) |

**Repository permissions:**

| Permission | Access |
|------------|--------|
| Contents | Read and write |
| Issues | Read and write |
| Pull requests | Read and write |
| Metadata | Read-only (auto) |

After creation:
1. Note the **App ID** on the settings page
2. **Generate a private key** → save the `.pem` file
3. **Install App** → select `joshuajerome/cutip`
4. Add `APP_ID` and `APP_PRIVATE_KEY` as repo secrets

---

## GitHub Actions Workflows

Five workflow files in `.github/workflows/`:

| Workflow | Triggers | Purpose |
|----------|----------|---------|
| `ci.yml` | Push to `feat/**`, `bug/**`, `claude/**`; PRs to `staging`/`integration` | Unit tests, smoke test, E2E (Ubuntu/Windows/macOS), docs build, wheel build |
| `release.yml` | Push to `release/**` | Full test matrix + GitHub Release with wheel + optional PyPI publish |
| `docs.yml` | Push to `staging`/`integration`/`docs/**`; PRs with docs changes | MkDocs build, GitHub Pages deploy, auto-generate cap entries + patch notes |
| `integration.yml` | Push to `integration` | Publish dev build to Test PyPI, prune merged branches |
| `issues.yml` | Issue labeled, issue comment | Automated diagnosis/fix pipeline via Claude API |

### CI Matrix (`ci.yml`)

| Job | OS | What it tests |
|-----|-----|--------------|
| Unit Tests | Ubuntu | `pytest tests/ --ignore=tests/e2e` |
| Smoke Test | Ubuntu | Build wheel, install, `import cutip` |
| E2E Podman Ubuntu | Ubuntu | `cutip validate` + `cutip run` with Podman |
| E2E Docker Ubuntu | Ubuntu | `cutip validate` + `cutip run` with Docker |
| E2E Podman Windows | Windows | Full E2E with `podman machine` |
| Install + Validate macOS | macOS 14 | Install + schema validation (no runtime) |
| Docs Build | Ubuntu | `mkdocs build --strict` |
| Build Wheel | Ubuntu | `uv build` + artifact upload |

---

## GitHub Pages (Documentation)

Deployed from the `gh-pages` branch via MkDocs Material.

**Setup:**

1. **Settings → Pages → Source**: Deploy from branch `gh-pages` / root
2. Docs auto-deploy on push to `integration` via `docs.yml` (`mkdocs gh-deploy --force`)
3. Theme: [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)

**MkDocs configuration:** `mkdocs.yml` at repo root.

**Key features:**
- Dark/light mode toggle
- Search with autocomplete
- Code copy buttons
- GitHub callout → admonition conversion (via `mkdocs-callouts` plugin)
- "Edit this page" links pointing to `integration` branch

---

## Release Process

1. Create `release/v{X}.{Y}.{Z}` branch from `integration`
2. `release.yml` runs full test matrix
3. On all-green: creates GitHub Release with tag `v{X.Y.Z}`, uploads wheel
4. Optional: publishes to PyPI if `PUBLISH_TO_PYPI` variable is `'true'`
5. Delete release branch (tag is the durable marker)

### Dev builds (Test PyPI)

Every push to `integration` triggers `integration.yml`:
- Computes version: `{major}.{minor}.{patch+1}.dev{run_number}`
- Publishes wheel to `https://test.pypi.org/`

Install dev build:
```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "cutip>=0.1.5.dev0"
```

---

## Python Package Configuration

`pyproject.toml` key sections:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "cutip"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "loguru>=0.7",
    "rich>=13.0",
    "podman>=4.0",
    "docker>=6.0",
]

[project.scripts]
cutip = "cutip.cli.main:app"

[project.optional-dependencies]
docs = ["mkdocs-material>=9.5", "mkdocs<2.0", "mkdocs-callouts>=1.14"]
dev = ["pytest>=8.0", "pytest-cov"]
ai = ["anthropic>=0.40"]
```

---

## License

MIT License — `LICENSE` file at repo root.

---

## File Tree (repo root)

```
.
├── .claude/                     # Claude Code context
│   ├── github/                  # GitHub orchestration docs
│   │   ├── issues.md            # Issue pipeline state machine
│   │   ├── prs.md               # PR conventions
│   │   └── releases.md          # Release pipeline
│   ├── skills/                  # Reusable skills
│   ├── templates/               # PR body + release notes templates
│   └── workflows/               # End-to-end playbooks
├── .github/
│   ├── scripts/                 # Python/bash scripts called by workflows
│   └── workflows/               # 5 workflow YAML files
├── cutip/                       # Python package source
│   ├── backends/                # Podman + Docker backends
│   ├── cli/commands/            # Typer CLI commands
│   ├── context/                 # CutipContext + startup loader
│   ├── issue/                   # Issue template + Claude API logic
│   ├── models/                  # Pydantic models (cards, units, groups)
│   ├── resolver/                # Ref resolution
│   ├── utils/                   # Logging, exceptions
│   ├── validation/              # Graph validator
│   └── workspace/               # Discovery, registry, scaffold
├── docs/                        # MkDocs source pages
├── tests/                       # pytest test suite
├── CLAUDE.md                    # Claude Code working context
├── LICENSE                      # MIT
├── README.md                    # Project README (this file's source)
├── mkdocs.yml                   # Documentation site config
└── pyproject.toml               # Package metadata + dependencies
```

---

## Capability ID System

Every feature/bugfix gets a sequential ID: `cap001`, `cap002`, ...

- Registry: `docs/capabilities.md`
- Branch: `feat/cap{N}-desc` or `bug/cap{N}-desc`
- Commit prefix: `[cap{N}] short message`
- PR title: `[cap{N}] Description`

Read the highest ID in `docs/capabilities.md` and increment by 1.

---

## Checklist: New Repo from Scratch

1. [ ] Create GitHub repo with `integration` as default branch
2. [ ] Add `staging` branch, protect both with rules above
3. [ ] Add `LICENSE` (MIT)
4. [ ] Add `pyproject.toml` with hatchling build, entry points, optional deps
5. [ ] Add `README.md` with badges, model diagram, install, quick look, CLI table, docs link
6. [ ] Add `mkdocs.yml` with Material theme, plugins, nav structure
7. [ ] Add `.github/workflows/` — ci.yml, release.yml, docs.yml, integration.yml, issues.yml
8. [ ] Add `.github/scripts/` — diagnose-issue.py, fix-issue.py, generate-docs.py, etc.
9. [ ] Add repo secrets: `ANTHROPIC_API_KEY`, `TEST_PYPI_TOKEN`
10. [ ] Create GitHub App for bot identity, add `APP_ID` + `APP_PRIVATE_KEY`
11. [ ] Configure GitHub Pages: deploy from `gh-pages` branch
12. [ ] Set repo About: description, website, topics
13. [ ] Add `.claude/` directory with workflows, skills, templates, github docs
14. [ ] Add `docs/capabilities.md` to track feature IDs
15. [ ] Run `mkdocs gh-deploy` to initialize GitHub Pages
