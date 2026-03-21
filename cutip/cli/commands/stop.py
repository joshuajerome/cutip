from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console

from cutip.backends import get_backend
from cutip.cli.commands.run import (
    _complete_group_name,
    _load_project_backend,
    _resolve_group_name,
)
from cutip.models.cards.container import ContainerCard
from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipError
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()


def _resolve_container_names(group_name: str, registry) -> list[str]:
    """Return container names belonging to *group_name*."""
    group = registry.get_group(group_name)
    if group is None:
        raise CutipError(f"Group '{group_name}' not found in registry")

    resolver = RefResolver(registry)
    names: list[str] = []
    for unit_ref in group.spec.units:
        unit = resolver.resolve_unit(unit_ref.ref)
        card = resolver.resolve(unit.spec.containerRef.ref)
        if isinstance(card, ContainerCard):
            names.append(card.metadata.name)
    return names


def stop(
    group_name: str = typer.Argument(
        ...,
        help="Name of the group to stop",
        autocompletion=_complete_group_name,
    ),
    remove: bool = typer.Option(
        False,
        "--rm",
        help="Remove containers after stopping (like docker compose down).",
    ),
    backend: str = typer.Option(
        None,
        "--backend",
        "-b",
        envvar="CUTIP_BACKEND",
        help="Container backend (docker or podman). "
        "Defaults to project.backend in cutip.yaml, then docker.",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Connect to the local Podman socket directly.",
    ),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Stop all containers in a group.

    Gracefully stops every container belonging to GROUP's units.
    Use --rm to also remove the stopped containers (equivalent to
    ``docker compose down``).
    """
    project_root = path or _find_project_root()
    registry = WorkspaceDiscovery(project_root).discover()

    try:
        group_name = _resolve_group_name(group_name, registry)
    except CutipError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    container_names = _resolve_container_names(group_name, registry)
    if not container_names:
        console.print(f"[yellow]No containers found for group '{group_name}'[/yellow]")
        raise typer.Exit(0)

    is_local = local or os.environ.get("CUTIP_LOCAL", "").lower() in ("1", "true", "yes")
    backend_name = backend.lower() if backend else _load_project_backend(project_root) or "docker"

    try:
        _backend = get_backend(backend_name, local=is_local)
    except CutipError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    try:
        for name in container_names:
            status = _backend.container_status(name)
            if status == "not_found":
                console.print(f"  [dim]{name}[/dim] — not found (skipped)")
                continue

            if status == "running":
                _backend.stop_container(name)
                console.print(f"  [green]Stopped[/green] {name}")
            else:
                console.print(f"  [dim]{name}[/dim] — already {status}")

            if remove:
                _backend.remove_container(name)
                console.print(f"  [red]Removed[/red] {name}")

        action = "stopped and removed" if remove else "stopped"
        console.print(f"\n[bold green]Group '{group_name}' {action}.[/bold green]")
    finally:
        _backend.disconnect()
