# Installation

## Requirements

| Requirement | Minimum | Notes |
|---|---|---|
| Python | 3.11 | 3.12+ recommended |
| [uv](https://github.com/astral-sh/uv) | latest | Package manager and virtual environment tool |
| Podman or Docker | any recent | Required only for `cutip run` |

---

## Install CUTIP

```shell
git clone <repo-url> cutip
cd cutip

uv venv
uv pip install -e .
```

Verify the CLI is available:

```shell
cutip --help
```

---

## Runtime Backend Extras

CUTIP's core (`cutip init`, `cutip tree`, `cutip validate`, `cutip show`, `cutip plan`) has no runtime dependency. The Podman and Docker SDK clients are optional extras:

```shell
# Podman backend
uv pip install -e ".[podman]"

# Docker backend
uv pip install -e ".[docker]"

# Both
uv pip install -e ".[podman,docker]"
```

---

## Runtime Setup

### Podman

See the full per-platform guide: [guides/runtimes/podman.md](../guides/runtimes/podman.md)

Summary:
- **Ubuntu** — `sudo apt-get install podman`, start the user socket
- **macOS** — `brew install podman && podman machine init --now`
- **Windows** — Download the MSI from the [Podman releases page](https://github.com/containers/podman/releases), then `podman machine init --now`

### Docker

See: [guides/runtimes/docker.md](../guides/runtimes/docker.md)

Summary:
- **Ubuntu** — Docker Engine is available via `apt`; Docker Engine ships pre-installed on GitHub-hosted runners
- **macOS** — Use [Colima](https://github.com/abiosoft/colima): `brew install colima docker && colima start`
- **Windows** — Docker Desktop or the Docker Engine that ships with `windows-latest` GitHub runners

---

## Development Install (with test dependencies)

```shell
uv venv
uv pip install -e ".[podman,docker]"
uv sync   # installs pytest and other dev-group deps from pyproject.toml
```

Run tests:

```shell
uv run pytest tests/ --ignore=tests/e2e
```
