from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipError
from cutip.utils.logging import setup_logging
from cutip.validation.graph import GraphValidator
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()


def preview(
    group_name: str = typer.Argument(..., help="Name of the group to preview"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Dry-run: show what cutip run would execute for a group."""
    setup_logging()
    project_root = path or _find_project_root()
    registry = WorkspaceDiscovery(project_root).discover()

    result = GraphValidator(registry, project_root=project_root).validate()
    if not result.ok:
        for err in result.errors:
            console.print(f"[red]{err}[/red]")
        console.print("[bold red]Validation failed. Fix errors before planning.[/bold red]")
        raise typer.Exit(1)

    group = registry.get_group(group_name)
    if group is None:
        console.print(f"[red]Group '{group_name}' not found.[/red]")
        raise typer.Exit(1)

    resolver = RefResolver(registry)
    console.print(f"\n[bold]Plan for group:[/bold] [magenta]{group_name}[/magenta]\n")

    table = Table(title="Execution Plan", show_lines=True)
    table.add_column("Step", style="dim", width=6)
    table.add_column("Action", style="bold")
    table.add_column("Target")
    table.add_column("Detail", style="dim")

    step = 1
    seen_images: set[str] = set()
    seen_networks: set[str] = set()

    for unit_ref in group.spec.units:
        try:
            unit = resolver.resolve_unit(unit_ref.ref)
            cc = resolver.resolve(unit.spec.containerRef.ref)

            if isinstance(cc, ContainerCard):
                # Image
                img_ref = cc.spec.imageRef.ref
                if img_ref not in seen_images:
                    img = resolver.resolve(img_ref)
                    if isinstance(img, ImageCard):
                        action = "build_image" if img.spec.source == "build" else "pull_image"
                        detail = img.spec.context or img.spec.image or ""
                        table.add_row(str(step), action, img.name, detail)
                        step += 1
                    seen_images.add(img_ref)

                # Network
                if cc.spec.network_mode:
                    # host/none/etc — no managed network card to ensure
                    net_key = f"__mode__{cc.spec.network_mode}"
                    if net_key not in seen_networks:
                        table.add_row(
                            str(step), "network_mode", cc.spec.network_mode, "pre-existing"
                        )
                        step += 1
                        seen_networks.add(net_key)
                elif cc.spec.networkRef is not None:
                    net_ref = cc.spec.networkRef.ref
                    if net_ref not in seen_networks:
                        net = resolver.resolve(net_ref)
                        if isinstance(net, NetworkCard):
                            table.add_row(str(step), "ensure_network", net.name, net.spec.subnet)
                            step += 1
                        seen_networks.add(net_ref)

                # Container
                table.add_row(str(step), "create_container", cc.name, unit.name)
                step += 1
                table.add_row(str(step), "start_container", cc.name, "")
                step += 1

        except CutipError as exc:
            table.add_row(str(step), "[red]ERROR[/red]", unit_ref.ref, str(exc))
            step += 1

    # Workflow
    table.add_row(str(step), "run_workflow", group.spec.workflow, "")

    console.print(table)
    console.print(
        f"\n[dim]No containers will be created. "
        f"Run [bold]cutip run {group_name}[/bold] to execute.[/dim]"
    )
