"""``cutip import`` — import a group archive into the current workspace."""

from __future__ import annotations

import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import typer
from rich.console import Console

from cutip.utils.exceptions import CutipError
from cutip.workspace.scaffold import _find_project_root

console = Console()


def _is_url(value: str) -> bool:
    """Check if a string looks like a URL."""
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https")


def _download(url: str, dest: Path) -> None:
    """Download a URL to a local path."""
    from urllib.request import urlretrieve

    try:
        urlretrieve(url, dest)
    except Exception as exc:
        raise CutipError(f"Failed to download '{url}': {exc}") from exc


def import_group(
    source: str = typer.Argument(..., help="Path or URL to a .cutip.tar.gz archive"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Import a group archive into the current workspace."""
    project_root = path or _find_project_root()

    if _is_url(source):
        console.print(f"[dim]Downloading {source}...[/dim]")
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        _download(source, tmp_path)
        archive_path = tmp_path
    else:
        archive_path = Path(source)

    if not archive_path.is_file():
        console.print(f"[red]Archive not found: {archive_path}[/red]")
        raise typer.Exit(1)

    if not tarfile.is_tarfile(archive_path):
        console.print(f"[red]Not a valid tar archive: {archive_path}[/red]")
        raise typer.Exit(1)

    imported: list[str] = []
    with tarfile.open(archive_path, "r:gz") as tar:
        # Security: reject absolute paths and path traversal
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in member.name:
                console.print(f"[red]Refusing to extract unsafe path: {member.name}[/red]")
                raise typer.Exit(1)

        for member in tar.getmembers():
            if member.isfile():
                tar.extract(member, path=project_root)
                imported.append(member.name)

    console.print(f"[green]Imported {len(imported)} files into {project_root}[/green]")
    for name in imported[:20]:
        console.print(f"  {name}")
    if len(imported) > 20:
        console.print(f"  ... and {len(imported) - 20} more")

    # Run validation
    try:
        from cutip.workspace.discovery import WorkspaceDiscovery

        WorkspaceDiscovery(project_root).discover()
        console.print("[green]Workspace validation passed.[/green]")
    except Exception as exc:
        console.print(f"[yellow]Warning: validation issue after import: {exc}[/yellow]")
