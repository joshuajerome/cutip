"""``cutip info`` — display CUTIP version, workspace, and backend information."""

from __future__ import annotations

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cutip.utils.version import installed_version, latest_version
from cutip.workspace.scaffold import _find_project_root

console = Console()
app = typer.Typer()


def _version_line(project_root) -> str:
    """Build the version status line: installed vs latest + migration hint."""
    ver = installed_version()
    latest = latest_version(cache_dir=project_root / ".cutip" / "cache")

    if latest and latest != ver:
        return (
            f"[bold]Version[/bold]: {ver} "
            f"([yellow]{latest} available[/yellow] — "
            f"run: [cyan]pip install cutip --upgrade[/cyan])"
        )

    # Up to date — check if workspace has deprecated patterns
    from cutip.upgrade.registry import scan_migrations

    findings = scan_migrations(project_root)
    if findings:
        n = len(findings)
        return (
            f"[bold]Version[/bold]: {ver} [green]up to date[/green] — "
            f"[yellow]{n} file{'s' if n != 1 else ''} use{'s' if n == 1 else ''} "
            f"deprecated patterns[/yellow]. Run: [cyan]cutip upgrade[/cyan]"
        )

    return f"[bold]Version[/bold]: {ver} [green]up to date[/green]"


@app.callback(invoke_without_command=True)
def info() -> None:
    """Show CUTIP version, active workspace, backend info, and discovered artifacts."""
    project_root = _find_project_root()

    lines = [_version_line(project_root)]

    # Active workspace
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
            lines.append("[bold]Workspace[/bold]: [yellow]cutip.yaml found but unreadable[/yellow]")
            lines.append(f"[bold]Project root[/bold]: [cyan]{project_root}[/cyan]")
    else:
        lines.append("[bold]Workspace[/bold]: [dim]none (no cutip.yaml found)[/dim]")

    # Available backends
    available = []
    for be_name, mod in [("docker", "docker"), ("podman", "podman")]:
        try:
            __import__(mod)
            available.append(be_name)
        except ImportError:
            pass

    if available:
        lines.append(f"[bold]Available backends[/bold]: {', '.join(available)}")
    else:
        lines.append("[bold]Available backends[/bold]: [yellow]none installed[/yellow]")

    # Discover artifacts
    cutip_dir = project_root / "cutip"
    if cutip_dir.is_dir():
        try:
            from cutip.workspace.discovery import WorkspaceDiscovery

            registry = WorkspaceDiscovery(project_root).discover()
            lines.append("")
            lines.append(
                f"[bold]Artifacts[/bold]: "
                f"{len(registry.groups)} group(s), "
                f"{len(registry.units)} unit(s), "
                f"{len(registry.cards)} card(s)"
            )
            if registry.groups:
                lines.append(f"[bold]Groups[/bold]: {', '.join(sorted(registry.groups.keys()))}")
        except Exception:
            pass

    console.print(
        Panel.fit(
            "\n".join(lines),
            title="cutip info",
            border_style="blue",
        )
    )

    # Per-unit hook status table
    if cutip_dir.is_dir():
        try:
            from cutip.workspace.discovery import WorkspaceDiscovery

            registry = WorkspaceDiscovery(project_root).discover()
            if registry.units:
                table = Table(title="Unit Hook Status", show_lines=True)
                table.add_column("Unit", style="bold")
                table.add_column("prehook.py")
                table.add_column("workflow.py")
                table.add_column("posthook.py")
                table.add_column("startup.py", style="dim")

                for unit_name in sorted(registry.units):
                    unit_source = registry.source_of(f"units/{unit_name}")
                    if unit_source:
                        unit_dir = unit_source.parent
                    else:
                        unit_dir = cutip_dir / "units" / unit_name

                    row = [unit_name]
                    for hook_file in ("prehook.py", "workflow.py", "posthook.py", "startup.py"):
                        exists = (unit_dir / hook_file).is_file()
                        row.append("[green]yes[/green]" if exists else "[dim]—[/dim]")
                    table.add_row(*row)

                console.print()
                console.print(table)
        except Exception:
            pass
