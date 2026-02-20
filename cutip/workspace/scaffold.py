from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from loguru import logger


_CUTIP_DIRS = [
    "cutip/cards/images",
    "cutip/cards/containers",
    "cutip/cards/networks",
    "cutip/cards/volumes",
    "cutip/units",
    "cutip/groups",
]

_RUNTIME_DIRS = [
    ".cutip/logs",
    ".cutip/cache",
    ".cutip/runs",
    ".cutip/locks",
]


def _find_project_root() -> Path:
    """Return the git root if inside a repo, otherwise cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


class WorkspaceScaffold:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or _find_project_root()

    def init(self) -> None:
        """Create the CUTIP workspace structure. Idempotent."""
        logger.info(f"Initializing CUTIP workspace at {self.project_root}")

        for rel in _CUTIP_DIRS + _RUNTIME_DIRS:
            target = self.project_root / rel
            if target.exists():
                logger.debug(f"  exists: {rel}")
            else:
                target.mkdir(parents=True, exist_ok=True)
                logger.debug(f"  created: {rel}")

        self._write_cutip_yaml()
        logger.info("Workspace ready.")

    def _write_cutip_yaml(self) -> None:
        config_path = self.project_root / "cutip.yaml"
        if config_path.exists():
            logger.debug("  exists: cutip.yaml")
            return

        project_name = self.project_root.name
        doc = {
            "apiVersion": "cutip/v1",
            "project": {
                "name": project_name,
                "version": "0.1.0",
            },
        }
        with config_path.open("w", encoding="utf-8") as fh:
            yaml.dump(doc, fh, default_flow_style=False, sort_keys=False)
        logger.debug("  created: cutip.yaml")
