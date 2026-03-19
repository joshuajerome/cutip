"""``cutip info`` — display CUTIP version, workspace, and backend information."""
from __future__ import annotations

from importlib.metadata import version as _pkg_version
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel

from cutip.workspace.scaffold import _find_project_root

console = Console()
app = typer.Typer()


@app.callback(invoke_without_command=True)
def info() -> None:
    """Show CUTIP version, active workspace, and backend info."""
    ver = _pkg_version("cutip")
    lines = [f"[bold]Version[/bold]: {ver}"]

    # Active workspace
    project_root = _find_project_root()
    config_path = project_root / "cutip.yaml"
    if config_path.is_file():
        try:
            with config_path.open(encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
            project = doc.get("project", {})
            name = project.get("name", project_root.name)
            proj_ver = project.get("version", "—")
            backend = project.get("backend", "docker")
            lines.append(f"[bold]Workspace[/bold]: {name} (v{proj_ver})")
            lines.append(f"[bold]Project root[/bold]: [cyan]{project_root}[/cyan]")
            lines.append(f"[bold]Backend[/bold]: {backend}")
        except Exception:
            lines.append(f"[bold]Workspace[/bold]: [yellow]cutip.yaml found but unreadable[/yellow]")
            lines.append(f"[bold]Project root[/bold]: [cyan]{project_root}[/cyan]")
    else:
        lines.append("[bold]Workspace[/bold]: [dim]none (no cutip.yaml found)[/dim]")

    # Available backends
    available = []
    for name, mod in [("docker", "docker"), ("podman", "podman")]:
        try:
            __import__(mod)
            available.append(name)
        except ImportError:
            pass

    if available:
        lines.append(f"[bold]Available backends[/bold]: {', '.join(available)}")
    else:
        lines.append("[bold]Available backends[/bold]: [yellow]none installed[/yellow]")

    console.print(Panel.fit(
        "\n".join(lines),
        title="cutip info",
        border_style="blue",
    ))
