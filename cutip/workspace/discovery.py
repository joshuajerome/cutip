from __future__ import annotations

from pathlib import Path

from loguru import logger

from cutip.utils.exceptions import CutipError, CutipParseError
from cutip.utils.yaml_loader import load_yaml_file, parse_artifact
from cutip.workspace.registry import CutipRegistry


class WorkspaceDiscovery:
    """Scans a CUTIP workspace and populates a CutipRegistry."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def discover(self) -> CutipRegistry:
        """Walk cutip/ recursively, parse every YAML file, return a populated registry."""
        cutip_dir = self.project_root / "cutip"
        if not cutip_dir.is_dir():
            raise CutipError(
                f"No 'cutip/' directory found at {self.project_root}. "
                "Run 'cutip init' first."
            )

        registry = CutipRegistry()
        # Exclude vars.yaml — it holds user-specific values, not CUTIP artifacts.
        yaml_files = [
            f for f in sorted(cutip_dir.rglob("*.yaml")) + sorted(cutip_dir.rglob("*.yml"))
            if f.name != "vars.yaml"
        ]

        for path in yaml_files:
            self._load_file(path, registry)

        logger.debug(
            f"Discovered {len(registry.cards)} card(s), "
            f"{len(registry.units)} unit(s), "
            f"{len(registry.groups)} group(s)."
        )
        return registry

    def _load_file(self, path: Path, registry: CutipRegistry) -> None:
        try:
            raw = load_yaml_file(path)
            artifact = parse_artifact(raw, source_path=str(path))
            registry.register(artifact, source=path)
        except CutipParseError as exc:
            logger.warning(f"Skipping {path.relative_to(self.project_root)}: {exc.detail}")
        except CutipError as exc:
            logger.warning(f"Skipping {path.relative_to(self.project_root)}: {exc}")
