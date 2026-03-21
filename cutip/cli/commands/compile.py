"""``cutip compile`` — compile group graph with Mermaid output."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipError
from cutip.utils.logging import setup_logging
from cutip.workflow.introspect import compile_group_graph, render_mermaid
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()


def compile_cmd(
    group_name: str = typer.Argument(..., help="Name of the group to compile"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Compile a group's workflow graph to Mermaid and a summary table."""
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

    # Group-level workflow / orchestrator
    group_source = registry.source_of(f"groups/{group_name}")
    if group_source:
        group_dir = group_source.parent
    else:
        group_dir = cutip_dir / "groups" / group_name

    for fname in ("orchestrator.py", "workflow.py"):
        candidate = group_dir / fname
        if candidate.is_file():
            rel = str(candidate.relative_to(project_root))
            workflow_files.append((candidate, rel))

    # Per-unit files
    for unit_ref in group.spec.units:
        try:
            unit = resolver.resolve_unit(unit_ref.ref)
            unit_source = registry.source_of(f"units/{unit.name}")
            if unit_source:
                unit_dir = unit_source.parent
            else:
                unit_dir = cutip_dir / "units" / unit.name

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

    # Compile the graph
    graph = compile_group_graph(group_name, workflow_files)

    # Render Mermaid
    mermaid = render_mermaid(graph)

    # Write compiled output
    compiled_dir = project_root / ".cutip" / "compiled"
    compiled_dir.mkdir(parents=True, exist_ok=True)
    out_file = compiled_dir / f"{group_name}.md"

    all_funcs = (
        graph.configs
        + graph.prehooks
        + graph.actions
        + graph.healthchecks
        + graph.posthooks
        + graph.cleanups
    )

    md_lines = [
        f"# {group_name} — Compiled Graph",
        "",
        "## Flowchart",
        "",
        "```mermaid",
        mermaid,
        "```",
        "",
        "## Annotated Functions",
        "",
        "| Function | Decorator | Name | Source | Line |",
        "|----------|-----------|------|--------|------|",
    ]
    for f in all_funcs:
        meta_name = f.meta.name if f.meta and hasattr(f.meta, "name") else "—"
        md_lines.append(
            f"| `{f.func_name}` | @{f.decorator} | {meta_name} | `{f.source}` | {f.line} |"
        )

    md_lines.append("")
    out_file.write_text("\n".join(md_lines), encoding="utf-8")

    # Print summary
    console.print(f"\n[bold]Compiled graph for:[/bold] [magenta]{group_name}[/magenta]\n")

    if all_funcs:
        table = Table(title="Annotated Functions", show_lines=True)
        table.add_column("Function", style="bold")
        table.add_column("Decorator", style="cyan")
        table.add_column("Name")
        table.add_column("Source", style="dim")
        table.add_column("Line", style="dim", justify="right")

        for f in all_funcs:
            meta_name = f.meta.name if f.meta and hasattr(f.meta, "name") else "—"
            table.add_row(f.func_name, f"@{f.decorator}", meta_name, f.source, str(f.line))
        console.print(table)

    console.print(f"\n[dim]Mermaid graph written to: {out_file.relative_to(project_root)}[/dim]")
    console.print(f"[dim]Files scanned: {len(workflow_files)}[/dim]")
