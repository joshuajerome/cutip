"""``cutip group ls``, ``cutip unit ls``, ``cutip card ls`` commands.

Each sub-app exposes a single ``ls`` command that lists all artifacts of that
kind discovered in the current CUTIP workspace.
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()

group_app = typer.Typer(help="Group commands.")
unit_app  = typer.Typer(help="Unit commands.")
card_app  = typer.Typer(help="Card commands.")


def _get_registry(path: Path | None):
    project_root = path or _find_project_root()
    return WorkspaceDiscovery(project_root).discover()


# ── group ls ─────────────────────────────────────────────────────────────────

@group_app.command("ls")
def group_ls(
    path: Path = typer.Option(None, "--path", "-p", show_default=False,
                              help="Project root. Defaults to nearest cutip.yaml, git root, or cwd."),
) -> None:
    """List all groups discovered in the workspace."""
    try:
        registry = _get_registry(path)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if not registry.groups:
        console.print("[dim]No groups found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Group", style="magenta")
    table.add_column("Units", style="dim")
    table.add_column("Workflow", style="dim")

    for name, group in sorted(registry.groups.items()):
        unit_names = ", ".join(u.ref.split("/")[-1] for u in group.spec.units)
        table.add_row(name, unit_names, group.spec.workflow)

    console.print(table)


# ── unit ls ──────────────────────────────────────────────────────────────────

@unit_app.command("ls")
def unit_ls(
    path: Path = typer.Option(None, "--path", "-p", show_default=False,
                              help="Project root. Defaults to nearest cutip.yaml, git root, or cwd."),
) -> None:
    """List all units discovered in the workspace."""
    try:
        registry = _get_registry(path)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if not registry.units:
        console.print("[dim]No units found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Unit", style="blue")
    table.add_column("ContainerRef", style="dim")

    for name, unit in sorted(registry.units.items()):
        table.add_row(name, unit.spec.containerRef.ref)

    console.print(table)


# ── card ls ──────────────────────────────────────────────────────────────────

@card_app.command("ls")
def card_ls(
    path: Path = typer.Option(None, "--path", "-p", show_default=False,
                              help="Project root. Defaults to nearest cutip.yaml, git root, or cwd."),
) -> None:
    """List all cards (images, containers, networks) discovered in the workspace."""
    try:
        registry = _get_registry(path)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if not registry.cards:
        console.print("[dim]No cards found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold yellow")
    table.add_column("Ref", style="yellow")
    table.add_column("Kind", style="dim")
    table.add_column("Name", style="dim")

    for ref, card in sorted(registry.cards.items()):
        table.add_row(ref, card.kind, card.metadata.name)

    console.print(table)
