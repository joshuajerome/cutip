# Installation

## Requirements

| Requirement | Minimum | Notes |
|---|---|---|
| Python | 3.11 | 3.12+ recommended |
| [uv](https://github.com/astral-sh/uv) | latest | Package manager and virtual environment tool |
| Podman **or** Docker | any recent | Required only for `cutip run` — Podman is the default backend |

---

## Install CUTIP

```shell
pip install cutip
cutip --help
```

---

## Runtime Setup

### Podman (default)

See the full per-platform guide: [guides/runtimes/podman.md](../guides/runtimes/podman.md)

Summary:
- **Ubuntu** — `sudo apt-get install podman`, start the user socket
- **macOS** — `brew install podman && podman machine init --now`
- **Windows** — Download the MSI from the [Podman releases page](https://github.com/containers/podman/releases), then `podman machine init --now`

### Docker (default)

Docker is included by default. Have Docker Desktop or the Docker daemon running:

```shell
pip install cutip
cutip run dev
```

See the full guide: [guides/runtimes/docker.md](../guides/runtimes/docker.md)

---

## Contributing to CUTIP

To work on CUTIP itself, clone the repo and install in editable mode with test dependencies:

```shell
git clone https://github.com/joshuajerome/cutip && cd cutip
uv venv
uv pip install -e .
uv sync   # installs pytest and other dev-group deps from pyproject.toml
```

Run tests:

```shell
uv run pytest tests/ --ignore=tests/e2e
```
