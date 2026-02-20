from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax
from rich.tree import Tree

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.cards.volume import VolumeCard
from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipRefError
from cutip.utils.logging import setup_logging
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()
app = typer.Typer()


def _get_registry_and_resolver(path: Path | None):
    project_root = path or _find_project_root()
    discovery = WorkspaceDiscovery(project_root)
    registry = discovery.discover()
    resolver = RefResolver(registry)
    return registry, resolver, project_root


def _print_yaml(obj) -> None:
    raw = yaml.dump(obj.model_dump(mode="json"), default_flow_style=False, sort_keys=False)
    console.print(Syntax(raw, "yaml", theme="monokai"))


@app.command("card")
def show_card(
    ref: str = typer.Argument(..., help="Card ref, e.g. 'containers/my-app'"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Show a resolved card definition."""
    setup_logging()
    try:
        registry, resolver, _ = _get_registry_and_resolver(path)
        card = resolver.resolve(ref)
        _print_yaml(card)
    except (CutipRefError, Exception) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@app.command("unit")
def show_unit(
    name: str = typer.Argument(..., help="Unit name"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Show a unit and its fully resolved card graph."""
    setup_logging()
    try:
        registry, resolver, _ = _get_registry_and_resolver(path)
        unit = registry.get_unit(name)
        if unit is None:
            console.print(f"[red]Unit '{name}' not found.[/red]")
            raise typer.Exit(1)

        tree = Tree(f"[bold]Unit:[/bold] [blue]{name}[/blue]")

        container_ref = unit.spec.containerRef.ref
        try:
            container_card: ContainerCard = resolver.resolve_card(container_ref, ContainerCard)
            c_branch = tree.add(
                f"[bold]ContainerCard:[/bold] [yellow]{container_card.name}[/yellow]"
            )

            image_ref = container_card.spec.imageRef.ref
            try:
                image_card: ImageCard = resolver.resolve_card(image_ref, ImageCard)
                c_branch.add(f"[bold]ImageCard:[/bold]   [green]{image_card.name}[/green]")
            except CutipRefError:
                c_branch.add(f"[bold]ImageCard:[/bold]   [red]UNRESOLVED ({image_ref})[/red]")

            network_ref = container_card.spec.networkRef.ref
            try:
                network_card: NetworkCard = resolver.resolve_card(network_ref, NetworkCard)
                c_branch.add(
                    f"[bold]NetworkCard:[/bold] [green]{network_card.name}[/green]"
                )
            except CutipRefError:
                c_branch.add(
                    f"[bold]NetworkCard:[/bold] [red]UNRESOLVED ({network_ref})[/red]"
                )

        except CutipRefError:
            tree.add(f"[bold]ContainerCard:[/bold] [red]UNRESOLVED ({container_ref})[/red]")

        console.print(tree)

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@app.command("group")
def show_group(
    name: str = typer.Argument(..., help="Group name"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Show a group, its units, and workflow resolution status."""
    setup_logging()
    try:
        registry, resolver, project_root = _get_registry_and_resolver(path)
        group = registry.get_group(name)
        if group is None:
            console.print(f"[red]Group '{name}' not found.[/red]")
            raise typer.Exit(1)

        tree = Tree(f"[bold]Group:[/bold] [magenta]{name}[/magenta]")

        # Workflow path
        group_source = registry.source_of(f"groups/{name}")
        group_dir = group_source.parent if group_source else project_root / "cutip" / "groups" / name
        workflow_path = group_dir / group.spec.workflow
        status = "[green]OK[/green]" if workflow_path.is_file() else "[red]MISSING[/red]"
        tree.add(f"[bold]Workflow:[/bold] {group.spec.workflow} {status}")

        # Units
        units_branch = tree.add("[bold]Units[/bold]")
        for unit_ref in group.spec.units:
            ref = unit_ref.ref
            try:
                unit = resolver.resolve_unit(ref)
                u_branch = units_branch.add(f"[blue]{unit.name}[/blue]")

                container_ref = unit.spec.containerRef.ref
                try:
                    cc: ContainerCard = resolver.resolve_card(container_ref, ContainerCard)
                    cc_branch = u_branch.add(
                        f"[bold]ContainerCard:[/bold] [yellow]{cc.name}[/yellow]"
                    )
                    # image
                    try:
                        img: ImageCard = resolver.resolve_card(cc.spec.imageRef.ref, ImageCard)
                        cc_branch.add(f"[bold]ImageCard:[/bold]   [green]{img.name}[/green]")
                    except CutipRefError:
                        cc_branch.add(
                            f"[bold]ImageCard:[/bold]   [red]UNRESOLVED ({cc.spec.imageRef.ref})[/red]"
                        )
                    # network
                    try:
                        net: NetworkCard = resolver.resolve_card(
                            cc.spec.networkRef.ref, NetworkCard
                        )
                        cc_branch.add(
                            f"[bold]NetworkCard:[/bold] [green]{net.name}[/green]"
                        )
                    except CutipRefError:
                        cc_branch.add(
                            f"[bold]NetworkCard:[/bold] [red]UNRESOLVED ({cc.spec.networkRef.ref})[/red]"
                        )
                except CutipRefError:
                    u_branch.add(
                        f"[bold]ContainerCard:[/bold] [red]UNRESOLVED ({container_ref})[/red]"
                    )
            except CutipRefError:
                units_branch.add(f"[red]UNRESOLVED ({ref})[/red]")

        console.print(tree)

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
