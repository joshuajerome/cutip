# Guide: Docker Runtime

Docker is the default container backend. CUTIP also supports [Podman](podman.md).

---

## Installation

Docker is included as a core dependency — no extras needed:

```shell
pip install cutip
```

You also need Docker Desktop or the Docker daemon running.

---

## Usage

Docker is used by default. To be explicit, or to persist the choice per-project:

```shell
# Default — just works
cutip run dev

# Explicit CLI flag
cutip run dev --backend docker

# Environment variable
CUTIP_BACKEND=docker cutip run dev
```

Or set `backend: docker` in `cutip.yaml`:

```yaml
apiVersion: cutip/v1
project:
  name: my-project
  version: 0.1.0
  backend: docker
```

Docker always connects to the local daemon via `docker.from_env()`. The `--local` flag is accepted but has no effect (Docker does not use SSH tunnels).

---

## Platform setup

### Ubuntu / Linux

Docker is pre-installed on most CI environments (including GitHub Actions `ubuntu-latest`). For local development:

```shell
# Install Docker Engine (official docs: https://docs.docker.com/engine/install/)
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# Add your user to the docker group (avoids sudo)
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker version
```

### macOS

Install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/):

```shell
# Or via Homebrew
brew install --cask docker

# Start Docker Desktop, then verify
docker version
```

### Windows

Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/). Docker Desktop handles Windows path translation natively — no WSL path conversion is needed (unlike Podman).

```powershell
docker version
```

---

## CI usage (GitHub Actions)

Docker is pre-installed on `ubuntu-latest` runners:

```yaml
- name: Install cutip
  run: |
    uv venv .venv
    uv pip install -e .

- name: Run E2E
  run: uv run cutip run dev --path tests/e2e/simple --local
```

---

## Differences from Podman

| | Docker (default) | Podman |
|---|---|---|
| **Connection** | Local daemon only | SSH tunnel (default) or local socket |
| **Windows paths** | Native — Docker Desktop handles translation | Translated to WSL2 format (`/mnt/c/...`) |
| **Network creation** | `docker.types.IPAMConfig` / `IPAMPool` | Raw IPAM dict |
| **Image build** | `docker build` CLI | `podman build` CLI |
| **Package** | `docker>=6.0` (core dependency) | `podman>=4.0` (core dependency) |

---

## Troubleshooting

**`Could not connect to the Docker daemon`**
→ Docker Desktop or the Docker daemon is not running. Start it and retry.

**`Permission denied` on Linux**
→ Add your user to the `docker` group: `sudo usermod -aG docker $USER`
