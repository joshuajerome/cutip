"""cutip upgrade — detect and apply workspace migrations."""

from __future__ import annotations

import re
from pathlib import Path

import typer
import yaml
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from cutip.workspace.scaffold import _find_project_root

console = Console()

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Detect and apply workspace migrations for newer CUTIP versions.",
)


# ---------------------------------------------------------------------------
# Migration checks
# ---------------------------------------------------------------------------


def _check_vars_yaml(project_root: Path) -> dict | None:
    """Detect cutip/vars.yaml that should be split into paths.yaml + secrets.yaml."""
    old = project_root / "cutip" / "vars.yaml"
    new_paths = project_root / "cutip" / "paths.yaml"
    if old.exists() and not new_paths.exists():
        return {
            "id": "vars-to-paths",
            "severity": "breaking",
            "message": (
                "cutip/vars.yaml was renamed to cutip/paths.yaml in v0.1.8.\n"
                "  Sensitive values should be moved to cutip/secrets.yaml."
            ),
            "old_file": old,
        }
    return None


def _check_cutip_yaml_backend(project_root: Path) -> dict | None:
    """Detect cutip.yaml missing the project.backend field."""
    config = project_root / "cutip.yaml"
    if not config.exists():
        return None
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    project = data.get("project")
    if project is None:
        return {
            "id": "cutip-yaml-project",
            "severity": "breaking",
            "message": (
                "cutip.yaml is missing the 'project' section.\n"
                "  Expected format:\n"
                "    apiVersion: cutip/v1\n"
                "    project:\n"
                "      name: my-project\n"
                "      version: 0.1.0\n"
                "      backend: docker"
            ),
        }
    if not isinstance(project, dict):
        return None
    if "backend" not in project:
        return {
            "id": "missing-backend",
            "severity": "warning",
            "message": (
                "cutip.yaml is missing project.backend.\n"
                "  Default is now 'docker' (changed from 'podman' in v0.1.9).\n"
                "  Add 'backend: podman' if your system only supports Podman."
            ),
        }
    return None


def _check_startup_ctx_vars(project_root: Path) -> list[dict]:
    """Detect startup.py files still using ctx.vars (renamed to ctx.paths)."""
    findings = []
    units_dir = project_root / "cutip" / "units"
    if not units_dir.exists():
        return findings

    for startup in units_dir.rglob("startup.py"):
        text = startup.read_text(encoding="utf-8")
        if "ctx.vars" in text:
            findings.append(
                {
                    "id": "ctx-vars-renamed",
                    "severity": "breaking",
                    "message": (
                        f"{startup.relative_to(project_root)}: "
                        f"ctx.vars was renamed to ctx.paths in v0.1.8.\n"
                        f"  Replace ctx.vars with ctx.paths."
                    ),
                    "file": startup,
                }
            )
    return findings


def _check_card_vars_refs(project_root: Path) -> list[dict]:
    """Detect YAML cards still using {{ vars.X }} (renamed to {{ paths.X }})."""
    findings = []
    cards_dir = project_root / "cutip" / "cards"
    if not cards_dir.exists():
        return findings

    pattern = re.compile(r"\{\{\s*vars\.\w+\s*\}\}")
    for yaml_file in cards_dir.rglob("*.yaml"):
        text = yaml_file.read_text(encoding="utf-8")
        if pattern.search(text):
            findings.append(
                {
                    "id": "vars-ref-renamed",
                    "severity": "breaking",
                    "message": (
                        f"{yaml_file.relative_to(project_root)}: "
                        f"{{{{ vars.X }}}} was renamed to {{{{ paths.X }}}} in v0.1.8.\n"
                        f"  Update all {{{{ vars.X }}}} references to {{{{ paths.X }}}}."
                    ),
                    "file": yaml_file,
                }
            )
    return findings


# ---------------------------------------------------------------------------
# Apply logic
# ---------------------------------------------------------------------------


def _apply_vars_to_paths(project_root: Path) -> None:
    """Rename cutip/vars.yaml → cutip/paths.yaml."""
    old = project_root / "cutip" / "vars.yaml"
    new = project_root / "cutip" / "paths.yaml"
    old.rename(new)
    logger.info("Renamed: cutip/vars.yaml → cutip/paths.yaml")


def _apply_missing_backend(project_root: Path, backend: str) -> None:
    """Add project.backend to cutip.yaml."""
    config = project_root / "cutip.yaml"
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    project = data.get("project", {})
    project["backend"] = backend
    data["project"] = project
    config.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info(f"Added project.backend: {backend} to cutip.yaml")


def _apply_ctx_vars_rename(file_path: Path) -> None:
    """Replace ctx.vars with ctx.paths in a startup.py file."""
    text = file_path.read_text(encoding="utf-8")
    updated = text.replace("ctx.vars", "ctx.paths")
    file_path.write_text(updated, encoding="utf-8")
    logger.info(f"Updated: {file_path} (ctx.vars → ctx.paths)")


def _apply_vars_ref_rename(file_path: Path) -> None:
    """Replace {{ vars.X }} with {{ paths.X }} in a YAML card."""
    text = file_path.read_text(encoding="utf-8")
    updated = re.sub(
        r"\{\{\s*vars\.(\w+)\s*\}\}",
        r"{{ paths.\1 }}",
        text,
    )
    file_path.write_text(updated, encoding="utf-8")
    logger.info(f"Updated: {file_path} ({{ vars.X }} → {{ paths.X }})")


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


@app.callback()
def upgrade(
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply all safe migrations automatically.",
    ),
    backend: str = typer.Option(
        "podman",
        "--backend",
        "-b",
        help="Backend to set when adding missing project.backend to cutip.yaml.",
    ),
) -> None:
    """Scan the workspace for outdated patterns and report needed changes.

    Run without --apply to see a dry-run report. Pass --apply to fix automatically.
    """
    project_root = path or _find_project_root()

    findings: list[dict] = []

    # Run all checks
    v = _check_vars_yaml(project_root)
    if v:
        findings.append(v)

    b = _check_cutip_yaml_backend(project_root)
    if b:
        findings.append(b)

    findings.extend(_check_startup_ctx_vars(project_root))
    findings.extend(_check_card_vars_refs(project_root))

    if not findings:
        console.print("[green]Workspace is up to date — no migrations needed.[/green]")
        raise typer.Exit(0)

    # Report
    breaking = [f for f in findings if f["severity"] == "breaking"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    lines = []
    if breaking:
        lines.append("[bold red]Breaking changes:[/bold red]")
        for f in breaking:
            lines.append(f"  [red]✗[/red] {f['message']}")
    if warnings:
        lines.append("[bold yellow]Warnings:[/bold yellow]")
        for f in warnings:
            lines.append(f"  [yellow]![/yellow] {f['message']}")

    console.print(Panel.fit("\n".join(lines), title="cutip upgrade"))

    if not apply:
        console.print("\nRun [bold]cutip upgrade --apply[/bold] to fix automatically.")
        raise typer.Exit(1 if breaking else 0)

    # Apply migrations
    console.print("\n[bold]Applying migrations...[/bold]")
    for f in findings:
        fid = f["id"]
        if fid == "vars-to-paths":
            _apply_vars_to_paths(project_root)
        elif fid == "missing-backend":
            _apply_missing_backend(project_root, backend)
        elif fid == "ctx-vars-renamed":
            _apply_ctx_vars_rename(f["file"])
        elif fid == "vars-ref-renamed":
            _apply_vars_ref_rename(f["file"])
        elif fid == "cutip-yaml-project":
            console.print(
                f"  [yellow]Skipped:[/yellow] {fid} — requires manual restructuring of cutip.yaml"
            )

    console.print("[green]Done. Re-run cutip upgrade to verify.[/green]")
