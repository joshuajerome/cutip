"""cutip upgrade — detect and apply workspace migrations."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cutip.upgrade.registry import Finding, apply_findings, scan_migrations
from cutip.workspace.scaffold import _find_project_root

console = Console()

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Detect and apply workspace migrations for newer CUTIP versions.",
)


def _render_findings(findings: list[Finding]) -> None:
    """Print a summary table of detected migration findings."""
    table = Table(title="Migration Report", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Severity", width=10)
    table.add_column("Migration", width=20)
    table.add_column("File", style="cyan")
    table.add_column("Action")

    for i, f in enumerate(findings, 1):
        sev = "[red]breaking[/red]" if f.severity == "breaking" else "[yellow]warning[/yellow]"
        file_str = str(f.file.name) if f.file else "—"
        table.add_row(str(i), sev, f.migration_id, file_str, f.detail or f.message)

    console.print(table)


def _git_stage(files: list[Path], project_root: Path) -> bool:
    """Stage modified files in git. Returns True if git is available and staging succeeded."""
    try:
        # Check if we're in a git repo
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_root,
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

    existing = [str(f) for f in files if f.exists()]
    deleted = [str(f) for f in files if not f.exists()]

    if existing:
        subprocess.run(["git", "add", *existing], cwd=project_root, capture_output=True)
    if deleted:
        subprocess.run(["git", "rm", "--cached", *deleted], cwd=project_root, capture_output=True)

    return True


@app.callback()
def upgrade(
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply all safe migrations and stage changes in git.",
    ),
    backend: str = typer.Option(
        "podman",
        "--backend",
        "-b",
        help="Backend to set when adding missing project.backend to cutip.yaml.",
    ),
) -> None:
    """Scan the workspace for outdated patterns and report needed changes.

    Run without --apply to see a dry-run report.
    Pass --apply to fix automatically and stage changes in git.

    Upgrade workflow:
      1. cutip info          — check version + migration status
      2. pip install cutip --upgrade  — install latest
      3. cutip upgrade       — dry-run: see what needs changing
      4. cutip diff          — preview exact changes
      5. cutip upgrade --apply  — apply and stage
    """
    project_root = path or _find_project_root()

    findings = scan_migrations(project_root)

    if not findings:
        console.print("[green]Workspace is up to date — no migrations needed.[/green]")
        raise typer.Exit(0)

    # Always show the report
    _render_findings(findings)

    breaking = [f for f in findings if f.severity == "breaking"]

    if not apply:
        console.print()
        console.print("Run [bold]cutip diff[/bold] to preview changes.")
        console.print("Run [bold]cutip upgrade --apply[/bold] to fix and stage in git.")
        raise typer.Exit(1 if breaking else 0)

    # Apply migrations
    console.print()
    console.print("[bold]Applying migrations...[/bold]")

    modified = apply_findings(findings, project_root, backend=backend)

    if not modified:
        console.print("[yellow]No changes were applied.[/yellow]")
        raise typer.Exit(0)

    # Stage in git
    staged = _git_stage(modified, project_root)
    if staged:
        console.print(f"\n[green]Done.[/green] {len(modified)} file(s) modified and staged in git.")
        console.print("Run [bold]cutip diff[/bold] to review staged changes.")
    else:
        console.print(f"\n[green]Done.[/green] {len(modified)} file(s) modified.")
        console.print("[dim](Not a git repository — changes were not staged.)[/dim]")

    # Verify
    remaining = scan_migrations(project_root)
    if remaining:
        console.print(
            f"\n[yellow]{len(remaining)} migration(s) still pending "
            f"(may require manual action).[/yellow]"
        )
    else:
        console.print("\n[green]All migrations applied. Workspace is up to date.[/green]")
