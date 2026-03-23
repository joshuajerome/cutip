"""cutip status — show backend selection and connectivity."""

from __future__ import annotations

import platform
import shutil

from rich.console import Console

console = Console()

_START_HINTS: dict[str, dict[str, str]] = {
    "podman": {
        "Darwin": "podman machine start",
        "Windows": "podman machine start",
        "Linux": "systemctl --user start podman.socket",
    },
    "docker": {
        "Darwin": "open -a Docker",
        "Windows": "start Docker Desktop",
        "Linux": "sudo systemctl start docker",
    },
}


def _detect_available_backends() -> list[str]:
    available = []
    for name, mod in [("docker", "docker"), ("podman", "podman")]:
        try:
            __import__(mod)
            available.append(name)
        except ImportError:
            pass
    return available


def _check_backend_running(name: str) -> tuple[bool, str]:
    """Check if a backend daemon is reachable. Returns (ok, detail)."""
    try:
        if name == "docker":
            import docker

            client = docker.from_env()
            client.ping()
            info = client.version()
            ver = info.get("Version", "unknown")
            client.close()
            return True, f"Docker Engine {ver}"

        if name == "podman":
            # Try local socket first (works on Linux CI and --local mode)
            from cutip.backends.podman.connection import local_socket_url

            try:
                from podman import PodmanClient

                url = local_socket_url()
                client = PodmanClient(base_url=url)
                client.ping()
                ver = client.version()
                api_ver = ver.get("Version", "unknown")
                client.close()
                return True, f"Podman {api_ver}"
            except Exception:
                pass

            # Check if podman CLI is available and a machine is running
            if shutil.which("podman"):
                import subprocess

                result = subprocess.run(
                    ["podman", "machine", "info"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    # Machine info succeeded — check if any machine is running
                    result2 = subprocess.run(
                        ["podman", "machine", "list", "--format", "{{.Running}}"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if "true" in result2.stdout.lower():
                        return True, "Podman machine running (socket unreachable from Python)"
                return False, "Podman machine not running"
            return False, "Podman not reachable"

    except Exception as exc:
        return False, str(exc)

    return False, f"Unknown backend: {name}"


def status() -> None:
    """Show backend selection, connectivity, and available backends."""
    from cutip.cli.commands.run import _load_project_backend
    from cutip.workspace.scaffold import _find_project_root

    # ── Configured backend ──────────────────────────────────────────────────
    configured = None
    try:
        project_root = _find_project_root()
        configured = _load_project_backend(project_root)
    except Exception:
        pass

    available = _detect_available_backends()
    active = configured or "docker"

    console.print()
    console.print(
        f"[bold]Backend[/bold]:  {active}" + (" (from cutip.yaml)" if configured else " (default)")
    )

    # ── Connectivity check ──────────────────────────────────────────────────
    if active in available:
        ok, detail = _check_backend_running(active)
        if ok:
            console.print(f"[bold]Status[/bold]:   [green]running[/green] — {detail}")
        else:
            console.print(f"[bold]Status[/bold]:   [red]not running[/red] — {detail}")
            hint = _START_HINTS.get(active, {}).get(platform.system())
            if hint:
                console.print(f"[bold]Start[/bold]:    [cyan]{hint}[/cyan]")
    else:
        console.print(
            f"[bold]Status[/bold]:   [red]not installed[/red] — "
            f"install with: [cyan]pip install {active}[/cyan]"
        )

    # ── Other backends ──────────────────────────────────────────────────────
    others = [b for b in available if b != active]
    if others:
        console.print(f"[bold]Also installed[/bold]: {', '.join(others)}")

    console.print()
