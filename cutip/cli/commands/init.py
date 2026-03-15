from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from cutip.utils.logging import setup_logging
from cutip.workspace.scaffold import WorkspaceScaffold

console = Console()
app = typer.Typer()


@app.callback(invoke_without_command=True)
def init(
    path: Path = typer.Option(
        None,
        "--path",
        "-p",
        help="Project root directory. Defaults to git root or cwd.",
        show_default=False,
    ),
) -> None:
    """Initialize a CUTIP workspace in the current project."""
    setup_logging()
    scaffold = WorkspaceScaffold(project_root=path)
    scaffold.init()

    root = scaffold.project_root

    # Detect available backends
    backends = []
    for name, mod in [("docker", "docker"), ("podman", "podman")]:
        try:
            __import__(mod)
            backends.append(name)
        except ImportError:
            pass

    backend_line = ""
    if backends:
        backend_line = (
            f"\n\n  [bold]Backend[/bold]: docker (default in cutip.yaml)"
            f"\n  [dim]Available[/dim]: {', '.join(backends)}"
            f"\n  [dim]Override[/dim]:  cutip run GROUP -b podman"
        )
    else:
        backend_line = (
            "\n\n  [yellow]No backends installed.[/yellow]"
            "\n  Run: pip install docker  (or: pip install podman)"
        )

    console.print(
        Panel.fit(
            f"[bold green]CUTIP workspace initialized[/bold green]\n"
            f"  Project root: [cyan]{root}[/cyan]\n\n"
            f"  [dim]cutip/[/dim]          ← version-controlled artifacts\n"
            f"  [dim].cutip/[/dim]         ← runtime state (add to .gitignore)\n"
            f"  [dim]cutip.yaml[/dim]       ← project config"
            + backend_line,
            title="cutip init",
            border_style="green",
        )
    )
