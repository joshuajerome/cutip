"""``cutip export`` — package a group and its dependencies into a portable archive."""

from __future__ import annotations

import tarfile
from pathlib import Path

import typer
from rich.console import Console

from cutip.cli.commands.rm import _collect_group_files
from cutip.resolver.refs import RefResolver
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()


def export_group(
    group_name: str = typer.Argument(..., help="Group name to export"),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output archive path (default: ./<group>.cutip.tar.gz)",
    ),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Export a group and all its artifacts into a portable .tar.gz archive."""
    project_root = path or _find_project_root()
    registry = WorkspaceDiscovery(project_root).discover()
    resolver = RefResolver(registry)

    files = _collect_group_files(group_name, project_root, registry, resolver)
    if not files:
        console.print(f"[yellow]No files found for group '{group_name}'.[/yellow]")
        raise typer.Exit(0)

    archive_path = output or Path(f"{group_name}.cutip.tar.gz")

    with tarfile.open(archive_path, "w:gz") as tar:
        for f in files:
            arcname = str(f.relative_to(project_root))
            tar.add(f, arcname=arcname)

    console.print(f"[green]Exported {len(files)} files to {archive_path}[/green]")
    console.print("[dim]Import with: cutip import <archive>[/dim]")
