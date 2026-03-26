"""cutip validate — static validation of the CUTIP workspace graph + configuration."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console

from cutip.utils.logging import setup_logging
from cutip.validation.graph import GraphValidator
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()
app = typer.Typer()


def _validate_paths_secrets(project_root: Path) -> list[str]:
    """Check that all required paths and secrets are non-empty."""
    errors: list[str] = []

    # paths.yaml
    paths_file = project_root / "cutip" / "paths.yaml"
    if paths_file.exists():
        data = yaml.safe_load(paths_file.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            req = data.get(
                "required", data if "required" not in data and "generated" not in data else {}
            )
            if isinstance(req, dict):
                for key, val in req.items():
                    if val is None or not str(val).strip():
                        errors.append(f"paths.yaml: required key '{key}' is empty")

    # secrets.yaml
    secrets_file = project_root / "cutip" / "secrets.yaml"
    if secrets_file.exists():
        data = yaml.safe_load(secrets_file.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            req = data.get("required", data if "required" not in data else {})
            if isinstance(req, dict):
                for key, val in req.items():
                    if val is None or not str(val).strip():
                        errors.append(f"secrets.yaml: required key '{key}' is empty")

    return errors


def _validate_config(project_root: Path) -> list[str]:
    """Check that config.yaml exists if referenced in cutip.yaml."""
    errors: list[str] = []

    cutip_yaml = project_root / "cutip.yaml"
    if not cutip_yaml.exists():
        return errors

    data = yaml.safe_load(cutip_yaml.read_text(encoding="utf-8")) or {}
    project = data.get("project")
    if not isinstance(project, dict):
        return errors

    config_path_str = project.get("config")
    if not config_path_str:
        return errors

    config_path = project_root / config_path_str
    if not config_path.is_file():
        errors.append(f"config: '{config_path_str}' referenced in cutip.yaml but file not found")

    return errors


@app.callback(invoke_without_command=True)
def validate(
    path: Path = typer.Option(
        None,
        "--path",
        "-p",
        help="Project root. Defaults to nearest cutip.yaml, git root, or cwd.",
        show_default=False,
    ),
    graph_only: bool = typer.Option(
        False,
        "--graph-only",
        help="Only validate the artifact graph (skip paths/secrets/config checks).",
    ),
) -> None:
    """Validate the CUTIP workspace: artifact graph + static configuration.

    Checks:
      1. Artifact graph — all refs resolve (unit → container → image → network)
      2. paths.yaml — all required keys are non-empty
      3. secrets.yaml — all required keys are non-empty
      4. config.yaml — exists if referenced in cutip.yaml
    """
    setup_logging()
    project_root = path or _find_project_root()
    discovery = WorkspaceDiscovery(project_root)

    try:
        registry = discovery.discover()
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    all_errors: list[str] = []

    # 1. Graph validation
    validator = GraphValidator(registry, project_root=project_root)
    result = validator.validate()
    if not result.ok:
        for error in result.errors:
            all_errors.append(f"[graph] {error}")

    # 2-4. Config validation (unless --graph-only)
    if not graph_only:
        path_errors = _validate_paths_secrets(project_root)
        for e in path_errors:
            all_errors.append(f"[config] {e}")

        config_errors = _validate_config(project_root)
        for e in config_errors:
            all_errors.append(f"[config] {e}")

    if all_errors:
        for error in all_errors:
            console.print(f"[red]{error}[/red]")
        console.print(f"\n[bold red]{len(all_errors)} error(s) found.[/bold red]")
        raise typer.Exit(1)

    console.print("[bold green]Validation OK[/bold green]")
