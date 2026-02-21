# Guide: Podman Runtime

CUTIP's Podman backend (`cutip[podman]`) supports two connection modes:

| Mode | Command | Use case |
|---|---|---|
| **SSH tunnel** | `cutip run <group> --backend podman` | Default. Production use over SSH to a remote Podman socket. |
| **Local socket** | `cutip run <group> --backend podman --local` | CI, local dev. Connects directly to the local Podman socket. |

---

## Installation by platform

### Ubuntu

```shell
sudo apt-get update -y
sudo apt-get install -y podman

# Start the rootless user socket
systemctl --user start podman.socket

# Verify
podman version
```

### macOS

```shell
brew install podman

# Initialize and start a Podman machine (QEMU or Apple HV)
podman machine init --cpus 2 --memory 4096 --disk-size 20 --now

# Verify
podman version
```

> [!NOTE]
> `--now` initializes and starts the machine in a single command. On subsequent runs, use `podman machine start`.

### Windows

1. Download the latest installer from [github.com/containers/podman/releases](https://github.com/containers/podman/releases) — look for `podman-<version>-setup.exe`
2. Run the installer (silent: `.\podman-setup.exe /S`)
3. Add `C:\Program Files\RedHat\Podman` to your PATH
4. Initialize and start a machine (requires WSL2):

```powershell
podman machine init --cpus 2 --memory 4096 --now
podman version   # confirm daemon connection
```

---

## SSH tunnel mode (default)

The default mode reads the active Podman connection from `podman system connection ls` and opens a TCP-over-SSH tunnel to the remote socket before connecting `PodmanClient`.

Requirements:
- `podman system connection ls` returns a default connection
- SSH access to the Podman host
- The Podman socket service is running on the remote host

```shell
cutip run dev --backend podman
```

---

## Local socket mode (`--local`)

Connect directly to the local Podman socket without SSH. The socket URL is resolved in priority order:

1. `CONTAINER_HOST` environment variable — standard Podman convention
2. Platform default:
   - **Linux**: `unix:///run/user/<uid>/podman/podman.sock`
   - **macOS**: resolved via `podman machine inspect`
   - **Windows**: `npipe:////./pipe/podman-machine-default`

```shell
cutip run dev --backend podman --local
```

Or via environment variable:

```shell
CUTIP_LOCAL=1 cutip run dev --backend podman
```

Set a custom socket:

```shell
CONTAINER_HOST=unix:///custom/path.sock cutip run dev --backend podman --local
```

---

## CI usage (GitHub Actions)

See the complete workflow: [guides/ci-cd/github-actions.md](../ci-cd/github-actions.md)

Summary per platform:

**Ubuntu:**
```yaml
- run: |
    sudo apt-get install -y podman
    systemctl --user start podman.socket
    echo "CONTAINER_HOST=unix:///run/user/$(id -u)/podman/podman.sock" >> "$GITHUB_ENV"
```

**macOS:**
```yaml
- run: |
    brew install podman
    podman machine init --cpus 2 --memory 2048 --disk-size 10 --now
    SOCK=$(podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}')
    echo "CONTAINER_HOST=unix://${SOCK}" >> "$GITHUB_ENV"
```

**Windows:**
```yaml
- shell: pwsh
  run: |
    # (after installing MSI and adding to PATH)
    podman machine init --cpus 2 --memory 2048 --now
    "CONTAINER_HOST=npipe:////./pipe/podman-machine-default" |
      Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
```

Then run with:
```yaml
- run: uv run cutip run hello --path tests/e2e/hello-world --backend podman --local
```

---

## Troubleshooting

**`podman system connection list` shows no connections**
→ The machine is not running. Run `podman machine start`.

**`dial unix ... no such file or directory`**
→ The socket path doesn't exist. Verify `CONTAINER_HOST` or run `systemctl --user start podman.socket` (Linux).

**`Podman client ping failed`**
→ The socket exists but the service isn't responding. Check `podman machine inspect` or restart the machine.

**Connection works in terminal but not in `cutip run`**
→ The `CONTAINER_HOST` env var isn't set in the process environment. Export it explicitly or set `CUTIP_LOCAL=1`.
