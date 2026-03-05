"""cutip secrets — manage secrets.yaml entries.

Commands:
    cutip secrets set <key> <value>   Set a secret in cutip/secrets.yaml
    cutip secrets list                List secret keys (values masked)
    cutip secrets check               Validate all {{ secrets.key }} refs are defined + non-empty
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console

from cutip.utils.exceptions import CutipError
from cutip.workspace.scaffold import _find_project_root

secrets_app = typer.Typer(
    help="Manage cutip/secrets.yaml entries.",
    no_args_is_help=True,
)

console = Console()


def _secrets_path(project_root: Path) -> Path:
    return project_root / "cutip" / "secrets.yaml"


def _load_secrets_file(path: Path) -> dict:
    """Load secrets.yaml and return the raw dict."""
    if not path.exists():
        return {"required": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CutipError("cutip/secrets.yaml must be a YAML mapping")
    if "required" not in data:
        data = {"required": data}
    return data


def _write_secrets_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


@secrets_app.command("set")
def set_secret(
    key: str = typer.Argument(..., help="Secret key name"),
    value: str = typer.Argument(..., help="Secret value"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Set a secret in cutip/secrets.yaml."""
    project_root = path or _find_project_root()
    sp = _secrets_path(project_root)
    data = _load_secrets_file(sp)
    data.setdefault("required", {})[key] = value
    _write_secrets_file(sp, data)
    console.print(f"[green]Set secret '{key}' in cutip/secrets.yaml[/green]")


@secrets_app.command("list")
def list_secrets(
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """List secret keys (values masked)."""
    project_root = path or _find_project_root()
    sp = _secrets_path(project_root)

    if not sp.exists():
        console.print("[yellow]No cutip/secrets.yaml found.[/yellow]")
        raise typer.Exit(0)

    data = _load_secrets_file(sp)
    required = data.get("required", {})
    if not required:
        console.print("[dim]No secrets defined.[/dim]")
        return

    for key, val in required.items():
        masked = "****" if val else "[empty]"
        console.print(f"  {key}: {masked}")


@secrets_app.command("check")
def check_secrets(
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Validate all {{ secrets.key }} refs are defined and non-empty."""
    import re

    from cutip.models.cards.container import ContainerCard
    from cutip.workspace.discovery import WorkspaceDiscovery

    project_root = path or _find_project_root()
    sp = _secrets_path(project_root)

    secrets = {}
    if sp.exists():
        data = _load_secrets_file(sp)
        req = data.get("required", {})
        secrets = {k: (str(v) if v is not None else "") for k, v in req.items()}

    registry = WorkspaceDiscovery(project_root).discover()
    pattern = re.compile(r"\{\{\s*secrets\.(\w+)\s*\}\}")
    errors: list[str] = []

    for card in registry.cards.values():
        if not isinstance(card, ContainerCard):
            continue
        name = card.metadata.name
        for mount in card.spec.mounts:
            for key in pattern.findall(mount.source):
                if key not in secrets:
                    errors.append(f"  [{name}] mounts.source: secrets.{key} not defined")
                elif not secrets[key].strip():
                    errors.append(f"  [{name}] mounts.source: secrets.{key} is empty")
            for key in pattern.findall(mount.target):
                if key not in secrets:
                    errors.append(f"  [{name}] mounts.target: secrets.{key} not defined")
                elif not secrets[key].strip():
                    errors.append(f"  [{name}] mounts.target: secrets.{key} is empty")
        for env_key, env_val in card.spec.environment.items():
            for key in pattern.findall(env_val):
                if key not in secrets:
                    errors.append(f"  [{name}] environment[{env_key!r}]: secrets.{key} not defined")
                elif not secrets[key].strip():
                    errors.append(f"  [{name}] environment[{env_key!r}]: secrets.{key} is empty")

    if errors:
        console.print("[red]Secrets check failed:[/red]")
        for e in errors:
            console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print("[green]All secrets refs are defined and non-empty.[/green]")
