# Guide: GitHub Actions

CUTIP's CI pipeline lives entirely in `.github/workflows/ci.yml`. A single file handles every stage: unit tests, smoke test, E2E, docs build, and wheel archive.

| File | Trigger | What it does |
|---|---|---|
| `ci.yml` | Push to `feat/**`, `bug/**`, `claude/**`; PR → `staging` or `integration` | Unit tests, smoke test, E2E (PR-only), docs build, wheel archive |
| `docs.yml` | Push to `staging` or `docs/**`; PR touching docs | Docs build check, AI audit, GitHub Pages deploy |
| `integration.yml` | Push to `integration` | Test PyPI dev publish, merged-branch pruning |
| `release.yml` | Push to `release/**` | Full test matrix + GitHub Release creation |

---

## Workflow trigger matrix

| Event | Jobs that run |
|---|---|
| Push to `feat/**`, `bug/**`, `claude/**` | unit-tests, smoke-test, docs-build, build-wheel |
| PR → `staging` or `integration` | auto-label, unit-tests, smoke-test, **e2e-ubuntu**, **e2e-windows**, **install-macos**, docs-build |

E2E jobs carry `if: github.event_name == 'pull_request'` — they only run on PRs, not on every iterative push to a feature branch. This keeps per-push CI fast while still requiring E2E to pass before any merge.

---

## Unit tests and smoke test

These run on every push and every PR:

```yaml
- name: Run unit tests
  run: uv run pytest tests/ --ignore=tests/e2e -v --tb=short

- name: Smoke-test wheel install
  run: |
    uv venv .wheel-test
    uv pip install --python .wheel-test/bin/python dist/cutip-*.whl
    .wheel-test/bin/python -c "import cutip; print('cutip import OK')"
    .wheel-test/bin/cutip --help
```

Unit tests live in `tests/`. The E2E directory (`tests/e2e/`) is excluded from the unit test job — it requires a live Podman runtime.

---

## E2E — Podman (PR-only)

E2E runs against two workspaces plus a from-compose validation suite, on Ubuntu and Windows.

### How each platform gets a working Podman socket

| Platform | Approach | `CONTAINER_HOST` value |
|---|---|---|
| Ubuntu | `apt install podman` + `systemctl --user start podman.socket` | `unix:///run/user/<uid>/podman/podman.sock` |
| Windows | Download MSI, install, `podman machine init --now` | `npipe:////./pipe/podman-machine-default` |

### E2E workspaces

Two permanent workspaces live under `tests/e2e/`:

| Workspace | Group | What it tests |
|---|---|---|
| `tests/e2e/simple/` | `simple` | Single container (alpine), basic lifecycle |
| `tests/e2e/complex/` | `complex` | Multi-container (postgres + Python app), health-check loop, pre-build hooks |

Both are validated (schema + ref check) before being run:

```yaml
- name: Validate simple workspace
  run: uv run cutip validate --path tests/e2e/simple

- name: Run E2E group simple (Podman · Ubuntu)
  run: uv run cutip run simple --path tests/e2e/simple --local

- name: Validate complex workspace
  run: uv run cutip validate --path tests/e2e/complex

- name: Run E2E group complex (Podman · Ubuntu)
  run: uv run cutip run complex --path tests/e2e/complex --local
```

### from-compose validation suite

Five projects from [docker/awesome-compose](https://github.com/docker/awesome-compose) are fetched and converted via `cutip from-compose`, then validated with `cutip validate`. This confirms the converter produces valid CUTIP artifacts across a range of real-world compose files:

| Project | Services | What it exercises |
|---|---|---|
| `react-nginx` | frontend, proxy | multi-stage build, nginx proxy |
| `fastapi` | api | single-service with restart policy |
| `nginx-flask-mongo` | nginx, flask, mongo | 3-service stack, depends_on |
| `prometheus-grafana` | prometheus, grafana | named volumes, env vars, port bindings |
| `angular` | frontend | Angular SPA build |

Each step fetches the compose file, converts it, and validates the output (schema + ref check). Container runtime is not invoked — `cutip validate` only checks the artifact graph.

Ubuntu example:

```yaml
- name: "from-compose · react-nginx"
  run: |
    curl -fsSL https://raw.githubusercontent.com/docker/awesome-compose/master/react-nginx/compose.yaml \
      -o /tmp/react-nginx.yaml
    mkdir -p /tmp/fc-react-nginx
    uv run cutip from-compose /tmp/react-nginx.yaml --output-dir /tmp/fc-react-nginx
    uv run cutip validate --path /tmp/fc-react-nginx
```

Windows uses `Invoke-WebRequest` and `$env:TEMP` paths via PowerShell.

---

## Install & Validate — macOS (PR-only)

Free macOS runners (`macos-14`) do not expose the Apple Hypervisor Framework, so `podman machine` cannot start. The macOS job validates install and schema only — no containers:

```yaml
- name: Smoke-test CLI (no runtime needed)
  run: |
    uv run cutip --help
    uv run cutip --version

- name: Validate simple workspace (schema only, no containers)
  run: uv run cutip validate --path tests/e2e/simple

- name: Validate complex workspace (schema only, no containers)
  run: uv run cutip validate --path tests/e2e/complex
```

---

## Why `uv venv .venv` instead of `--system`

System Python on Ubuntu and macOS is marked as "externally managed" (PEP 668), which blocks `uv pip install --system`. The workflows create a project-local `.venv` first:

```yaml
- name: Install cutip
  run: |
    uv venv .venv
    uv pip install -e .
```

`uv run cutip ...` then automatically discovers and activates `.venv` without any PATH manipulation, working identically on all three platforms.

---

## Adding more E2E workspaces

To test additional CUTIP workspaces in CI, add steps that run `uv run cutip validate --path <path>` and `uv run cutip run <group> --path <path>`. The workspaces live under `tests/e2e/`.

For `from-compose` tests, add steps that fetch a compose file, run `cutip from-compose`, and then `cutip validate` — no container runtime needed.
