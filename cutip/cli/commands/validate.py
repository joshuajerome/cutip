from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from cutip.utils.logging import setup_logging
from cutip.validation.graph import GraphValidator
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()
app = typer.Typer()


@app.callback(invoke_without_command=True)
def validate(
    path: Path = typer.Option(
        None,
        "--path",
        "-p",
        help="Project root. Defaults to nearest cutip.yaml, git root, or cwd.",
        show_default=False,
    ),
) -> None:
    """Validate the CUTIP configuration graph."""
    setup_logging()
    project_root = path or _find_project_root()
    discovery = WorkspaceDiscovery(project_root)

    try:
        registry = discovery.discover()
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    validator = GraphValidator(registry, project_root=project_root)
    result = validator.validate()

    if result.ok:
        console.print("[bold green]Validation OK[/bold green]")
    else:
        for error in result.errors:
            console.print(f"[red]{error}[/red]")
        console.print(f"\n[bold red]{len(result.errors)} error(s) found.[/bold red]")
        raise typer.Exit(1)
