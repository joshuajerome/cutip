from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console

from cutip.context.workflow import CutipContext, WorkflowLoader
from cutip.models.cards.container import ContainerCard
from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipError, CutipWorkflowError
from cutip.utils.logging import setup_logging
from cutip.utils.runs import iso_now, run_lock, write_run_record
from cutip.validation.graph import GraphValidator
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root
from loguru import logger

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


def _prepare_host_dirs(ctx: CutipContext, project_root: Path) -> None:
    """Create host-side directories for any mount with create_host_path: true.

    This mirrors the podwrap pattern of pre-creating bind-mount source dirs
    (e.g. data volumes, sheet dirs) before the container starts, but declared
    in YAML rather than in Python.  Relative paths are resolved against the
    project root.
    """
    for card in ctx.resolved_cards.values():
        if not isinstance(card, ContainerCard):
            continue
        for mount in card.spec.mounts:
            if not mount.create_host_path:
                continue
            host_path = Path(mount.source)
            if not host_path.is_absolute():
                host_path = project_root / host_path
            host_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Prepared host directory: {host_path}")


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
    project_root = path or _find_project_root()
    cutip_dir   = project_root / ".cutip"
    setup_logging(log_dir=cutip_dir / "logs")

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

    # Connect backend — manages connection lifecycle (SSH tunnel, cleanup).
    # The raw client it wraps (PodmanClient / DockerClient) is passed into
    # ctx.runtime so workflow.py can call the native API directly.
    try:
        if backend == BackendChoice.podman:
            from cutip.backends.podman import PodmanBackend
            _backend = PodmanBackend.connect_local() if is_local else PodmanBackend.connect()
        else:
            from cutip.backends.docker import DockerBackend
            _backend = DockerBackend.connect()
    except CutipError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    started_at = iso_now()
    status = "failure"
    run_error: str | None = None

    try:
        with run_lock(cutip_dir / "locks", group_name):
            ctx = _build_context(group_name, project_root, registry, runtime=_backend.client)
            _prepare_host_dirs(ctx, project_root)
            WorkflowLoader(project_root).run(ctx.group, ctx, registry)
            status = "success"
    except CutipError as exc:
        run_error = str(exc)
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except CutipWorkflowError as exc:
        run_error = str(exc)
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    finally:
        write_run_record(
            cutip_dir / "runs",
            group=group_name,
            backend=backend.value,
            started_at=started_at,
            status=status,
            error=run_error,
        )
        _backend.disconnect()
