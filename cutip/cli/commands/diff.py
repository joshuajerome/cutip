"""cutip diff — show what migrations would change, or review staged changes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from cutip.upgrade.registry import scan_migrations
from cutip.workspace.scaffold import _find_project_root

console = Console()


def diff(
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Show pending migration changes or review already-staged changes.

    Before --apply: shows what each migration would change.
    After --apply: shows the git-staged diff for cutip/ files.
    """
    project_root = path or _find_project_root()

    # Check if there are staged cutip/ changes (post-apply review)
    staged_diff = _get_staged_diff(project_root)
    if staged_diff:
        console.print(
            Panel("[bold]Staged changes[/bold] (after cutip upgrade --apply)", border_style="green")
        )
        console.print(Syntax(staged_diff, "diff", theme="monokai"))
        return

    # Pre-apply: show what migrations would change
    findings = scan_migrations(project_root)
    if not findings:
        console.print("[green]No pending migrations — nothing to diff.[/green]")
        raise typer.Exit(0)

    lines: list[str] = []
    for f in findings:
        rel = f.file.relative_to(project_root) if f.file else "—"
        sev = "✗" if f.severity == "breaking" else "!"
        lines.append(f"[{'red' if f.severity == 'breaking' else 'yellow'}]{sev}[/] [{f.migration_id}] {rel}")
        if f.detail:
            lines.append(f"    → {f.detail}")
        lines.append("")

    console.print(Panel.fit("\n".join(lines), title="cutip diff (dry-run preview)"))
    console.print("Run [bold]cutip upgrade --apply[/bold] to apply these changes.")


def _get_staged_diff(project_root: Path) -> str | None:
    """Get git staged diff for cutip/ files. Returns None if no staged changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--", "cutip/", "cutip.yaml"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None
