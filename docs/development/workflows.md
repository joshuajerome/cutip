# CI/CD Workflows Reference

Complete reference for CUTIP's GitHub Actions workflows — what triggers what, how Test PyPI dev builds work, and the correct procedure when CI fails.

---

## Workflow Trigger Matrix

| Event | Workflow | Jobs |
|-------|----------|------|
| Push to `feat/**`, `bug/**`, `claude/**` | `ci.yml` | unit-tests, smoke-test, docs-build, build-wheel |
| PR → `staging` or `integration` | `ci.yml` | auto-label, unit-tests, smoke-test, e2e-ubuntu, e2e-windows, install-macos, docs-build |
| Push to `staging` | `docs.yml` | build, generate, ai-review |
| Push to `integration` | `docs.yml` + `integration.yml` | build, deploy (gh-pages), **Test PyPI publish**, prune |
| Push to `docs/**` or PR touching docs / `mkdocs.yml` | `docs.yml` | build |
| Push to `release/**` | `release.yml` | unit-tests, smoke-test, e2e-ubuntu, e2e-windows, install-macos, build-and-release |

### E2E is PR-only

`e2e-podman-ubuntu`, `e2e-podman-windows`, and `install-validate-macos` carry `if: github.event_name == 'pull_request'`.

On a **push to a feature branch**, only unit-tests, smoke-test, docs-build, and build-wheel run. This prevents expensive E2E from running on every iterative commit during development.

On a **PR to staging or integration**, all jobs run — E2E is still a required merge gate. GitHub treats skipped jobs as passing for branch-protection purposes, so the protection rules are unchanged.

---

## Test PyPI Dev Artifact Flow

Every push to `integration` triggers `integration.yml → publish-dev`.

### Version computation

1. `pyproject.toml` is read for the current version (e.g., `0.1.5`)
2. Dev version is computed: `{major}.{minor}.{patch+1}.dev{GITHUB_RUN_NUMBER}` → `0.1.6.dev42`
3. `pyproject.toml` is patched in-place (not committed)
4. Wheel is built and published to `https://test.pypi.org/legacy/`

### Installing a dev build

```shell
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "cutip>=0.1.6.dev0"
```

Replace `0.1.6.dev0` with the specific dev version shown in the `integration.yml` run logs.

### Prerequisite

The `TEST_PYPI_TOKEN` secret must be set in the GitHub repository:

**Settings → Secrets and variables → Actions → New repository secret**

- Name: `TEST_PYPI_TOKEN`
- Value: API token from [test.pypi.org](https://test.pypi.org) (account settings → API tokens)

Without this secret, `publish-dev` fails silently on every integration push.

---

## CI Failure: Retry Before Force-Merging

### Step 1 — Read the failure

```shell
gh run view <run-id> --log-failed
```

This shows only the failed steps, not the full log.

### Step 2 — Diagnose

- **Code issue** (test failure, lint error, import error): fix locally and push. CI reruns automatically.
- **Transient infra issue** (GitHub 500, checkout timeout, rate limit): retry the run.

### Step 3 — Retry failed jobs only

```shell
gh run rerun <run-id> --failed
```

`--failed` retries only the jobs that failed — it does not re-run the entire suite. This is faster and cheaper than a full rerun.

To get the run ID:

```shell
gh run list --limit 5
```

Or from a PR:

```shell
gh pr checks <PR_NUMBER>
```

### Step 4 — If retries fail consistently

If the same job fails three times with the same transient error and the failure is clearly not a code issue, `--admin` force merge may be used as a last resort.

**`--admin` is not a convenience tool.** It bypasses all branch protections, including required status checks. It must only be used when:

- The failure is a confirmed persistent infrastructure issue (not a code issue)
- At least two retry attempts (`gh run rerun --failed`) have been made
- The PR has been reviewed and the code is correct

```shell
gh pr merge <PR_NUMBER> --merge --admin --delete-branch
```

> [!WARNING]
> Force-merging with `--admin` during a transient GitHub error can allow broken code to reach staging or integration if the failure turns out to be a real test failure. Retry first. Always.

---

## Workflow Files

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Unit tests, smoke, E2E (PR-only), docs build, wheel archive |
| `.github/workflows/docs.yml` | Docs build check, staging doc generation, gh-pages deploy |
| `.github/workflows/integration.yml` | Test PyPI publish, merged-branch pruning |
| `.github/workflows/release.yml` | Full test matrix + GitHub Release creation |

See [Branching Guide](branching.md) for branch types and the full feature development workflow.
