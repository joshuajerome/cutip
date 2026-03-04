# Guide: Docker Runtime

Docker is an optional container backend. CUTIP also supports [Podman](podman.md) (the default).

---

## Installation

Docker support requires the optional `docker` extra:

```shell
pip install cutip[docker]
```

This installs the `docker` Python SDK (`docker>=6.0`). You also need Docker Desktop or the Docker daemon running.

---

## Usage

Pass `--backend docker` to `cutip run`, or set the environment variable:

```shell
# CLI flag
cutip run dev --backend docker

# Environment variable
CUTIP_BACKEND=docker cutip run dev
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

Docker is pre-installed on `ubuntu-latest` runners. Install CUTIP with the docker extra:

```yaml
- name: Install cutip with docker extra
  run: |
    uv venv .venv
    uv pip install -e ".[docker]"

- name: Run E2E
  run: uv run cutip run dev --path tests/e2e/simple --backend docker --local
```

---

## Differences from Podman

| | Podman | Docker |
|---|---|---|
| **Connection** | SSH tunnel (default) or local socket | Local daemon only |
| **Windows paths** | Translated to WSL2 format (`/mnt/c/...`) | Native — Docker Desktop handles translation |
| **Network creation** | Raw IPAM dict | `docker.types.IPAMConfig` / `IPAMPool` |
| **Image build** | `podman build` CLI | `docker build` CLI |
| **Package** | `podman>=4.0` (core dependency) | `docker>=6.0` (optional extra) |

---

## Troubleshooting

**`The 'docker' package is required`**
→ Install the optional extra: `pip install cutip[docker]`

**`Could not connect to the Docker daemon`**
→ Docker Desktop or the Docker daemon is not running. Start it and retry.

**`Permission denied` on Linux**
→ Add your user to the `docker` group: `sudo usermod -aG docker $USER`
