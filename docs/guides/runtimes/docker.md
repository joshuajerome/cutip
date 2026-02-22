# Guide: Docker Runtime

CUTIP's Docker backend (`cutip[docker]`) connects to the local Docker daemon via `docker-py`. It respects the `DOCKER_HOST` environment variable, so any standard Docker connection setup works without additional flags.

---

## Installation by platform

### Ubuntu

Docker Engine is pre-installed on GitHub-hosted `ubuntu-latest` runners. For a local install:

```shell
sudo apt-get update -y
sudo apt-get install -y docker.io
sudo systemctl start docker

# Add your user to the docker group (rootless access)
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker version
```

### macOS

Docker Desktop requires a license for commercial use. The recommended open-source alternative for macOS is [Colima](https://github.com/abiosoft/colima):

```shell
brew install colima docker

# Start the Colima VM
colima start --cpu 2 --memory 4 --disk 20

# Verify
docker version
```

Colima sets `DOCKER_HOST` automatically in your shell session. If it doesn't, export it:

```shell
export DOCKER_HOST="unix://${HOME}/.colima/default/docker.sock"
```

### Windows

Docker Engine ships pre-installed on GitHub-hosted `windows-latest` runners. For local development, install [Docker Desktop](https://www.docker.com/products/docker-desktop/).

---

## Running with Docker

```shell
cutip run dev --backend docker
```

Docker always uses the local daemon. The `--local` flag has no effect for Docker.

`docker-py` reads `DOCKER_HOST` automatically. To target a remote Docker host:

```shell
DOCKER_HOST=tcp://remote-host:2376 cutip run dev --backend docker
```

---

## CI usage (GitHub Actions)

**Ubuntu:** Docker is pre-installed. No setup step needed.
```yaml
- run: uv run cutip run hello --path tests/e2e/hello-world --backend docker
```

**macOS:**
```yaml
- run: |
    brew install colima docker
    colima start --cpu 2 --memory 4 --disk 20
    docker version
- run: uv run cutip run hello --path tests/e2e/hello-world --backend docker
```

**Windows:** Docker Engine is pre-installed on `windows-latest` runners.
```yaml
- run: uv run cutip run hello --path tests/e2e/hello-world --backend docker
```

See the full workflow: [guides/ci-cd/github-actions.md](../ci-cd/github-actions.md)

---

## Troubleshooting

**`Docker connection failed`**
→ The Docker daemon is not running. Start it with `sudo systemctl start docker` (Linux) or open Docker Desktop / Colima (macOS/Windows).

**Permission denied on socket**
→ Your user isn't in the `docker` group. Run `sudo usermod -aG docker $USER && newgrp docker`.

**`DOCKER_HOST` not picked up**
→ Ensure the variable is exported in the same shell session that runs `cutip run`. Colima sets it automatically; other setups may require manual export.
