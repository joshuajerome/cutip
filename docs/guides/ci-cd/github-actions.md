# Guide: GitHub Actions

CUTIP's CI pipeline uses the following workflows under `.github/workflows/`:

| File | Trigger | What it does |
|---|---|---|
| `wheel-build.yml` | push to `feat/**`, `bug/**`, `claude/**` | Build wheel and upload as artifact |
| `pr-checks.yml` | PR to `staging` or `integration` | Unit tests, smoke test, E2E (Ubuntu + Windows), docs build |
| `docs-check.yml` | push to `docs/**`, `integration`; PR touching docs | Build docs (strict); deploy to GitHub Pages on `integration` push |
| `release.yml` | push to `release/**` | Run all checks, build wheel + sdist, create GitHub Release |

---

## PR Checks (`pr-checks.yml`)

Every PR to `staging` or `integration` must pass all five jobs before merge:

```
unit-tests → smoke-test → e2e-podman-ubuntu → e2e-podman-windows → docs-build
```

Key steps:

```yaml
- name: Run unit tests
  run: uv run pytest tests/ --ignore=tests/e2e -v --tb=short

- name: Smoke-test wheel install
  run: |
    uv venv .wheel-test
    uv pip install --python .wheel-test/bin/python dist/cutip-*.whl
    .wheel-test/bin/cutip --help
```

Unit tests live in `tests/`. The E2E fixture (`tests/e2e/`) is excluded from the unit test job — it requires a live Podman runtime.

---

## E2E — Podman

Runs `tests/e2e/hello-world` against the Podman backend on Ubuntu and Windows.

### How each platform gets a working Podman socket

| Platform | Approach | `CONTAINER_HOST` value |
|---|---|---|
| Ubuntu | `apt install podman` + `systemctl --user start podman.socket` | `unix:///run/user/<uid>/podman/podman.sock` |
| Windows | Download MSI, install, `podman machine init --now` | `npipe:////./pipe/podman-machine-default` |

### Connection mode

Both platforms use `--local` to connect via the socket set in `CONTAINER_HOST`:

```yaml
- run: uv run cutip run hello --path tests/e2e/hello-world --local
```

---

## The E2E fixture (`tests/e2e/hello-world/`)

A minimal CUTIP workspace:

```
cutip.yaml
cutip/
  cards/images/hello.yaml         # pull alpine:3.20
  cards/containers/hello.yaml     # network_mode: bridge, command: echo CUTIP_OK
  units/hello.yaml
  groups/hello/
    group.yaml
    workflow.py
```

The workflow:
1. Pulls `alpine:3.20`
2. Creates and starts `cutip-hello` container
3. Waits up to 15 s for the container to exit
4. Reads container logs
5. Asserts `"CUTIP_OK"` is present in the output
6. Removes the container

A failed assertion propagates as a non-zero exit, turning the GitHub Actions step red.

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

## Adding more E2E groups

To test additional CUTIP workspaces in CI, add steps that run `uv run cutip run <group> --path <path>`. The fixtures live under `tests/e2e/`.
