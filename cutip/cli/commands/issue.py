"""cutip issue — local issue management and self-service diagnosis/fix.

Commands:
    cutip issue create -t "title"   Create a local issue template
    cutip issue list                List local issues with status
    cutip issue push <slug>         Push issue to GitHub via gh CLI
    cutip issue diagnose <slug>     Run Claude diagnosis locally (requires ANTHROPIC_API_KEY)
    cutip issue fix <slug>          Generate fix locally (requires ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cutip.workspace.scaffold import _find_project_root

issue_app = typer.Typer(
    help="Manage local issues and run self-service diagnosis/fix.",
    no_args_is_help=True,
)

console = Console()


@issue_app.command("create")
def create_issue(
    title: str = typer.Option(..., "--title", "-t", help="Issue title"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Create a local issue YAML from template."""
    from cutip.issue.template import create_issue as _create

    project_root = path or _find_project_root()
    issue_path = _create(project_root, title)
    console.print(f"[green]Created issue:[/green] {issue_path}")
    console.print(
        "[dim]Edit the file to fill in description, then use 'cutip issue push' to create on GitHub.[/dim]"
    )


@issue_app.command("list")
def list_issues(
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """List local issues with status."""
    from cutip.issue.template import list_issues as _list

    project_root = path or _find_project_root()
    issues = _list(project_root)

    if not issues:
        console.print("[dim]No local issues found.[/dim]")
        return

    table = Table(title="Local Issues")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Status", style="green")
    table.add_column("GitHub #", style="yellow")

    for _, data in issues:
        meta = data.get("metadata", {})
        table.add_row(
            meta.get("slug", "?"),
            meta.get("title", "?"),
            meta.get("status", "?"),
            str(meta.get("github_number") or "—"),
        )

    console.print(table)


@issue_app.command("push")
def push_issue(
    slug: str = typer.Argument(..., help="Issue slug to push to GitHub"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Create a GitHub issue from a local issue file."""
    from cutip.issue.template import issues_dir, load_issue, save_issue

    project_root = path or _find_project_root()
    issue_path = issues_dir(project_root) / f"{slug}.issue.yaml"

    if not issue_path.exists():
        console.print(f"[red]Issue not found: {issue_path}[/red]")
        raise typer.Exit(1)

    data = load_issue(issue_path)
    meta = data["metadata"]
    spec = data.get("spec", {})

    if meta.get("github_number"):
        console.print(f"[yellow]Already pushed as #{meta['github_number']}[/yellow]")
        raise typer.Exit(0)

    title = meta["title"]
    body = spec.get("description", "")
    labels = spec.get("labels", [])

    cmd = [
        "gh",
        "issue",
        "create",
        "--title",
        title,
        "--body",
        body,
    ]
    for label in labels:
        cmd.extend(["--label", label])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        console.print("[red]gh CLI not found. Install it: https://cli.github.com[/red]")
        raise typer.Exit(1)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Failed to create issue: {exc.stderr}[/red]")
        raise typer.Exit(1)

    # Parse issue URL to get number
    url = result.stdout.strip()
    try:
        issue_number = int(url.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        issue_number = None

    meta["github_number"] = issue_number
    meta["status"] = "pushed"
    save_issue(issue_path, data)

    console.print(f"[green]Issue created:[/green] {url}")


@issue_app.command("diagnose")
def diagnose_issue(
    slug: str = typer.Argument(..., help="Issue slug to diagnose"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Run Claude diagnosis locally. Requires ANTHROPIC_API_KEY."""
    from cutip.issue.claude import _build_local_context, diagnose
    from cutip.issue.template import issues_dir, load_issue, save_issue

    project_root = path or _find_project_root()
    issue_path = issues_dir(project_root) / f"{slug}.issue.yaml"

    if not issue_path.exists():
        console.print(f"[red]Issue not found: {issue_path}[/red]")
        raise typer.Exit(1)

    data = load_issue(issue_path)
    meta = data["metadata"]
    spec = data.get("spec", {})

    console.print(f"[cyan]Diagnosing:[/cyan] {meta['title']}")
    context = _build_local_context(project_root)

    diagnosis_text = diagnose(
        title=meta["title"],
        body=spec.get("description", ""),
        context=context,
    )

    console.print()
    console.print(diagnosis_text)

    # Save diagnosis alongside the issue
    diag_path = issue_path.with_suffix(".diagnosis.md")
    diag_path.write_text(diagnosis_text, encoding="utf-8")

    meta["status"] = "diagnosed"
    save_issue(issue_path, data)
    console.print(f"\n[green]Diagnosis saved to:[/green] {diag_path}")


@issue_app.command("fix")
def fix_issue(
    slug: str = typer.Argument(..., help="Issue slug to fix"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Generate a fix locally. Requires ANTHROPIC_API_KEY and prior diagnosis."""
    from cutip.issue.claude import _build_local_context, generate_fix
    from cutip.issue.template import issues_dir, load_issue, save_issue

    project_root = path or _find_project_root()
    issue_path = issues_dir(project_root) / f"{slug}.issue.yaml"

    if not issue_path.exists():
        console.print(f"[red]Issue not found: {issue_path}[/red]")
        raise typer.Exit(1)

    data = load_issue(issue_path)
    meta = data["metadata"]
    spec = data.get("spec", {})

    # Load diagnosis
    diag_path = issue_path.with_suffix(".diagnosis.md")
    if not diag_path.exists():
        console.print("[red]No diagnosis found. Run 'cutip issue diagnose' first.[/red]")
        raise typer.Exit(1)

    diagnosis_text = diag_path.read_text(encoding="utf-8").strip()

    # Determine cap ID from capabilities.md
    cap_id = _next_cap_id(project_root)
    console.print(f"[cyan]Generating fix ({cap_id}):[/cyan] {meta['title']}")

    context = _build_local_context(project_root)
    file_changes, summary = generate_fix(
        title=meta["title"],
        body=spec.get("description", ""),
        diagnosis_text=diagnosis_text,
        cap_id=cap_id,
        context=context,
    )

    if not file_changes:
        console.print("[red]Claude returned no file changes.[/red]")
        raise typer.Exit(1)

    # Write changed files
    cutip_root = Path(__file__).resolve().parent.parent.parent
    for rel_path, content in file_changes.items():
        target = cutip_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        console.print(f"  [dim]Wrote {rel_path}[/dim]")

    console.print(f"\n[green]Fix applied ({len(file_changes)} file(s)).[/green]")
    console.print(f"\n{summary}")

    # Create branch
    branch = f"bug/{cap_id}-issue-{meta.get('github_number', slug)}-{meta['slug']}"[:60]
    console.print(f"\n[yellow]Suggested branch:[/yellow] {branch}")
    console.print(
        f"[dim]Run: git checkout -b {branch} && git add -p && git commit -m '[{cap_id}] fix: {meta['title']}'[/dim]"
    )

    meta["status"] = "fixed"
    save_issue(issue_path, data)


def _next_cap_id(project_root: Path) -> str:
    """Read docs/capabilities.md and return the next cap ID."""
    import re

    # Try CUTIP source root
    cutip_root = Path(__file__).resolve().parent.parent.parent
    caps_path = cutip_root / "docs" / "capabilities.md"

    if not caps_path.exists():
        caps_path = project_root / "docs" / "capabilities.md"

    if not caps_path.exists():
        return "cap001"

    content = caps_path.read_text(encoding="utf-8")
    ids = re.findall(r"cap(\d+)", content)
    if not ids:
        return "cap001"

    max_num = max(int(n) for n in ids)
    return f"cap{max_num + 1:03d}"
