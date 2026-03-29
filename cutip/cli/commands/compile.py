"""``cutip graph`` — display the workflow command graph for a group."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipError
from cutip.utils.logging import setup_logging
from cutip.workflow.commands import extract_all_action_commands
from cutip.workflow.introspect import (
    compile_group_graph,
    extract_staged_action_order,
)
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()


def compile_cmd(
    group_name: str = typer.Argument(..., help="Name of the group to compile"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Display the workflow graph for a group with runtime commands."""
    setup_logging()
    project_root = path or _find_project_root()
    registry = WorkspaceDiscovery(project_root).discover()

    group = registry.get_group(group_name)
    if group is None:
        console.print(f"[red]Group '{group_name}' not found.[/red]")
        raise typer.Exit(1)

    resolver = RefResolver(registry)
    cutip_dir = project_root / "cutip"

    # Collect all workflow files for this group
    workflow_files: list[tuple[Path, str]] = []
    workflow_path: Path | None = None

    # Group-level workflow / orchestrator
    group_source = registry.source_of(f"groups/{group_name}")
    group_dir = group_source.parent if group_source else cutip_dir / "groups" / group_name

    for fname in ("orchestrator.py", "workflow.py"):
        candidate = group_dir / fname
        if candidate.is_file():
            rel = str(candidate.relative_to(project_root))
            workflow_files.append((candidate, rel))
            if workflow_path is None:
                workflow_path = candidate

    # Per-unit files
    for unit_ref in group.spec.units:
        try:
            unit = resolver.resolve_unit(unit_ref.ref)
            unit_source = registry.source_of(f"units/{unit.name}")
            unit_dir = unit_source.parent if unit_source else cutip_dir / "units" / unit.name

            for fname in ("prehook.py", "workflow.py", "posthook.py", "startup.py"):
                candidate = unit_dir / fname
                if candidate.is_file():
                    rel = str(candidate.relative_to(project_root))
                    workflow_files.append((candidate, rel))
        except CutipError:
            continue

    if not workflow_files:
        console.print(f"[yellow]No workflow files found for group '{group_name}'.[/yellow]")
        raise typer.Exit(0)

    # Extract commands from all workflow files
    all_commands: dict[str, list[str]] = {}
    for abs_path, _rel in workflow_files:
        try:
            cmds = extract_all_action_commands(abs_path)
            all_commands.update(cmds)
        except Exception:
            pass

    # Try staged output first (shows stage headers)
    staged = None
    if workflow_path:
        try:
            staged = extract_staged_action_order(workflow_path)
        except Exception:
            pass

    console.print()

    if staged and any(sg.actions for sg in staged):
        # Staged tree — each stage is a section
        step = 0
        for sg in staged:
            title = sg.stage.title or "Workflow"
            desc = f" — {sg.stage.description}" if sg.stage.description else ""
            console.print(f"  [bold yellow]━━ {title}{desc} ━━[/bold yellow]")
            console.print()
            for action in sg.actions:
                step += 1
                commands = all_commands.get(action.name, [])
                console.print(f"  [bold]{step}. {action.name}[/bold]")
                if commands:
                    for cmd in commands:
                        console.print(f"     [cyan]→ {cmd}[/cyan]")
                else:
                    console.print("     [dim]→ (no block calls detected)[/dim]")
                console.print()
    else:
        # Flat tree — no stages
        graph = compile_group_graph(group_name, workflow_files)
        all_funcs = (
            graph.configs
            + graph.prehooks
            + graph.actions
            + graph.healthchecks
            + graph.posthooks
            + graph.cleanups
        )
        step = 0
        for f in all_funcs:
            step += 1
            meta_name = f.meta.name if f.meta and hasattr(f.meta, "name") else f.func_name
            commands = all_commands.get(meta_name, [])
            console.print(f"  [bold]{step}. {meta_name}[/bold]")
            if commands:
                for cmd in commands:
                    console.print(f"     [cyan]→ {cmd}[/cyan]")
            else:
                console.print("     [dim]→ (no block calls detected)[/dim]")
            console.print()

    console.print(f"  [dim]Group: {group_name} | Files: {len(workflow_files)}[/dim]")
