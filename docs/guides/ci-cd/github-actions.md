# Guide: GitHub Actions

CUTIP ships three workflows under `.github/workflows/`:

| File | Trigger | What it does |
|---|---|---|
| `ci.yml` | push / PR (any branch) | Build wheel, smoke-test install, run unit tests |
| `e2e-podman.yml` | push / PR → `main` | Podman E2E matrix: ubuntu, macos, windows |
| `e2e-docker.yml` | push / PR → `main` | Docker E2E matrix: ubuntu, macos, windows |

---

## CI — Build & Test (`ci.yml`)

```
checkout → setup uv → build wheel → smoke-test wheel → run unit tests → upload artifact
```

Key steps:

```yaml
- name: Build wheel
  run: uv build --wheel

- name: Smoke-test wheel install
  run: |
    uv venv .wheel-test
    uv pip install --python .wheel-test/bin/python dist/cutip-*.whl
    .wheel-test/bin/cutip --help

- name: Run unit tests
  run: uv run pytest tests/ --ignore=tests/e2e -v --tb=short
```

Unit tests live in `tests/`. The E2E fixture (`tests/e2e/`) is excluded from this job — it requires a live container runtime.

---

## E2E — Podman (`e2e-podman.yml`)

Runs `tests/e2e/hello-world` against the Podman backend on all three platforms.

### How each platform gets a working Podman socket

| Platform | Approach | `CONTAINER_HOST` value |
|---|---|---|
| Ubuntu | `apt install podman` + `systemctl --user start podman.socket` | `unix:///run/user/<uid>/podman/podman.sock` |
| macOS | `brew install podman` + `podman machine init --now` | Resolved from `podman machine inspect` |
| Windows | Download MSI, install, `podman machine init --now` | `npipe:////./pipe/podman-machine-default` |

### Windows: why `podman version --client` in the install step

After installing the Podman binary on Windows but before initializing the machine, `podman version` (without `--client`) attempts a socket connection that doesn't exist yet. The install step uses `--client` to print only the binary version. The full daemon check happens in the separate "Start Podman machine" step, after `machine init --now` has started the WSL2 VM.

### Connection mode

All platforms use `--local` to connect via the socket set in `CONTAINER_HOST`:

```yaml
- run: uv run cutip run hello --path tests/e2e/hello-world --backend podman --local
```

---

## E2E — Docker (`e2e-docker.yml`)

Runs `tests/e2e/hello-world` against the Docker backend on all three platforms.

| Platform | Approach |
|---|---|
| Ubuntu | Docker Engine is pre-installed on `ubuntu-latest` runners |
| macOS | Colima — `brew install colima docker && colima start` |
| Windows | Docker Engine is pre-installed on `windows-latest` runners |

Docker always uses the local daemon. No `--local` flag is needed:

```yaml
- run: uv run cutip run hello --path tests/e2e/hello-world --backend docker
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
- name: Install cutip with Podman extra
  run: |
    uv venv .venv
    uv pip install -e ".[podman]"
```

`uv run cutip ...` then automatically discovers and activates `.venv` without any PATH manipulation, working identically on all three platforms.

---

## Adding more E2E groups

To test additional CUTIP workspaces in CI, add steps that run `uv run cutip run <group> --path <path>`. The fixtures live under `tests/e2e/`.
