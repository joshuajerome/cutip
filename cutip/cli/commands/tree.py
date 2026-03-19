from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.tree import Tree

from cutip.utils.logging import setup_logging
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()
app = typer.Typer()


@app.callback(invoke_without_command=True)
def tree(
    path: Path = typer.Option(
        None,
        "--path",
        "-p",
        help="Project root. Defaults to nearest cutip.yaml, git root, or cwd.",
        show_default=False,
    ),
) -> None:
    """Show discovered cards, units, and groups in the workspace."""
    setup_logging()
    project_root = path or _find_project_root()
    discovery = WorkspaceDiscovery(project_root)

    try:
        registry = discovery.discover()
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    root_tree = Tree(f"[bold]Project:[/bold] [cyan]{project_root}[/cyan]")

    cards_branch = root_tree.add("[bold]Cards[/bold]")
    if registry.cards:
        for ref in sorted(registry.cards):
            cards_branch.add(f"[yellow]{ref}[/yellow]")
    else:
        cards_branch.add("[dim]none[/dim]")

    units_branch = root_tree.add("[bold]Units[/bold]")
    if registry.units:
        for name in sorted(registry.units):
            units_branch.add(f"[blue]{name}[/blue]")
    else:
        units_branch.add("[dim]none[/dim]")

    groups_branch = root_tree.add("[bold]Groups[/bold]")
    if registry.groups:
        for name in sorted(registry.groups):
            groups_branch.add(f"[magenta]{name}[/magenta]")
    else:
        groups_branch.add("[dim]none[/dim]")

    console.print(root_tree)
