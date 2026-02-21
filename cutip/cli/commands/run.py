from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console

from cutip.context.workflow import CutipContext, WorkflowLoader
from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipError, CutipWorkflowError
from cutip.utils.logging import setup_logging
from cutip.validation.graph import GraphValidator
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()


class BackendChoice(str, Enum):
    podman = "podman"
    docker = "docker"


def _build_context(group_name: str, project_root: Path, registry, runtime=None) -> CutipContext:
    """Assemble a CutipContext for the given group."""
    group = registry.get_group(group_name)
    if group is None:
        raise CutipError(f"Group '{group_name}' not found in registry")

    resolver = RefResolver(registry)
    resolved_units: dict = {}
    resolved_cards: dict = {}

    for unit_ref in group.spec.units:
        unit = resolver.resolve_unit(unit_ref.ref)
        resolved_units[unit.name] = unit

        container_ref = unit.spec.containerRef.ref
        cc = resolver.resolve(container_ref)
        resolved_cards[container_ref] = cc

        from cutip.models.cards.container import ContainerCard
        if isinstance(cc, ContainerCard):
            img = resolver.resolve(cc.spec.imageRef.ref)
            resolved_cards[cc.spec.imageRef.ref] = img

            # networkRef is optional when network_mode is set
            if cc.spec.networkRef is not None:
                net = resolver.resolve(cc.spec.networkRef.ref)
                resolved_cards[cc.spec.networkRef.ref] = net

    return CutipContext(
        group=group,
        resolved_units=resolved_units,
        resolved_cards=resolved_cards,
        registry=registry,
        project_root=project_root,
        runtime=runtime,
    )


def run(
    group_name: str = typer.Argument(..., help="Name of the group to run"),
    backend: BackendChoice = typer.Option(
        BackendChoice.podman, "--backend", "-b", help="Execution backend"
    ),
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Connect to the local daemon directly (no SSH tunnel). "
             "Uses CONTAINER_HOST / DOCKER_HOST env vars when set. "
             "Required for CI environments.",
    ),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Run a group's workflow against the selected backend."""
    setup_logging()
    project_root = path or _find_project_root()
    registry = WorkspaceDiscovery(project_root).discover()

    # Validate first
    result = GraphValidator(registry, project_root=project_root).validate()
    if not result.ok:
        for err in result.errors:
            console.print(f"[red]{err}[/red]")
        console.print("[bold red]Validation failed. Fix errors before running.[/bold red]")
        raise typer.Exit(1)

    # Honour env-var shortcut in addition to the CLI flag
    is_local = local or os.environ.get("CUTIP_LOCAL", "").lower() in ("1", "true", "yes")

    # Connect backend
    try:
        if backend == BackendChoice.podman:
            from cutip.backends.podman import PodmanBackend
            runtime = PodmanBackend.connect_local() if is_local else PodmanBackend.connect()
        else:
            from cutip.backends.docker import DockerBackend
            runtime = DockerBackend.connect()   # Docker always uses local daemon
    except CutipError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    try:
        ctx = _build_context(group_name, project_root, registry, runtime=runtime)
        WorkflowLoader(project_root).run(ctx.group, ctx, registry)
    except (CutipError, CutipWorkflowError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    finally:
        if hasattr(runtime, "disconnect"):
            runtime.disconnect()
