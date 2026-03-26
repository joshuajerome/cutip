"""cutip ping — test backend connectivity."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()


def ping(
    backend: str = typer.Option(
        None,
        "--backend",
        "-b",
        help="Backend to test (docker or podman). Auto-detected if omitted.",
    ),
) -> None:
    """Test connection to the container runtime engine.

    Pings the Docker or Podman API and prints the runtime version.
    Use this as a quick pre-flight check before cutip run.

    Pre-run workflow:
      cutip ping → cutip validate → cutip run GROUP
    """
    if backend is None:
        try:
            from cutip.cli.commands.run import _load_project_backend
            from cutip.workspace.scaffold import _find_project_root

            backend = _load_project_backend(_find_project_root())
        except Exception:
            backend = "docker"

    console.print(f"Pinging [bold]{backend}[/bold]...")

    try:
        if backend == "podman":
            from podman import PodmanClient

            from cutip.backends.podman.connection import local_socket_url

            url = local_socket_url()
            client = PodmanClient(base_url=url)
            client.ping()
            ver = client.version()
            version_str = ver.get("Version", "unknown")
            client.close()
            console.print(f"[green]Podman {version_str} — running[/green]")

        else:
            import docker

            client = docker.from_env()
            client.ping()
            info = client.version()
            version_str = info.get("Version", "unknown")
            client.close()
            console.print(f"[green]Docker {version_str} — running[/green]")

    except Exception as e:
        console.print(f"[red]{backend} is not reachable: {e}[/red]")
        console.print()

        # Platform-specific start hints
        import platform

        hints = {
            "podman": {
                "Darwin": "podman machine start",
                "Windows": "podman machine start",
                "Linux": "systemctl --user start podman.socket",
            },
            "docker": {
                "Darwin": "open -a Docker",
                "Windows": "Start Docker Desktop",
                "Linux": "sudo systemctl start docker",
            },
        }
        hint = hints.get(backend, {}).get(platform.system())
        if hint:
            console.print(f"Try: [cyan]{hint}[/cyan]")

        raise typer.Exit(1)
