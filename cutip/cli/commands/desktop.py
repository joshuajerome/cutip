"""cutip desktop — register workspace in cutip-desktop and open graph tab."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import typer
import yaml

from cutip.workspace.scaffold import _find_project_root


def desktop(
    url: str = typer.Option("http://localhost:5173", "--url", help="cutip-desktop server URL."),
    path: Path = typer.Option(None, "--path", "-p", help="Project root (auto-detected if omitted)."),
) -> None:
    """Register this workspace in cutip-desktop and open the graph tab."""
    project_root = path or _find_project_root()
    config_path = project_root / "cutip.yaml"

    if not config_path.is_file():
        typer.echo(f"No cutip.yaml found at {project_root}", err=True)
        raise typer.Exit(1)

    with config_path.open(encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    project_name = config.get("project", {}).get("name", project_root.name)

    payload = json.dumps({"name": project_name, "path": str(project_root)}).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/api/workspaces",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            workspace_id = body.get("id", "unknown")
            typer.echo(f"Workspace registered: {url}/workspace/{workspace_id}/graph")
    except urllib.error.URLError as exc:
        typer.echo(
            f"Could not connect to cutip-desktop at {url}\n"
            f"Start it first: cd cutip-desktop && npm run dev\n"
            f"Error: {exc.reason}",
            err=True,
        )
        raise typer.Exit(1)
