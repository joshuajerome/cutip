from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cutip.models.base import CutipBaseModel
from cutip.models.group import Group
from cutip.models.unit import Unit
from cutip.utils.exceptions import CutipWorkflowError
from cutip.workspace.registry import CutipRegistry


@dataclass
class CutipContext:
    """Runtime context injected into a group's workflow.

    Attributes:
        group:          The Group artifact being executed.
        resolved_units: Mapping of unit name → Unit for all units in the group.
        resolved_cards: Mapping of card ref → Card for all transitively resolved cards.
        registry:       The full workspace registry (read-only access).
        project_root:   Absolute path to the project root.
        runtime:        Backend handle (populated in Phase 3). None in dry-run / plan mode.
    """

    group: Group
    resolved_units: dict[str, Unit] = field(default_factory=dict)
    resolved_cards: dict[str, CutipBaseModel] = field(default_factory=dict)
    registry: CutipRegistry = field(default_factory=CutipRegistry)
    project_root: Path = field(default_factory=Path.cwd)
    runtime: Any = None


class WorkflowLoader:
    """Dynamically imports a group's workflow.py and calls main(ctx)."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def run(self, group: Group, ctx: CutipContext, registry: CutipRegistry) -> None:
        """Resolve workflow path, import the module, call main(ctx)."""
        group_source = registry.source_of(f"groups/{group.name}")
        if group_source is not None:
            group_dir = group_source.parent
        else:
            group_dir = self.project_root / "cutip" / "groups" / group.name

        workflow_path = group_dir / group.spec.workflow
        if not workflow_path.is_file():
            raise CutipWorkflowError(
                f"Workflow file not found: '{workflow_path}'"
            )

        module_name = f"cutip._workflow_{group.name}"
        spec = importlib.util.spec_from_file_location(module_name, workflow_path)
        if spec is None or spec.loader is None:
            raise CutipWorkflowError(
                f"Could not create module spec from '{workflow_path}'"
            )

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            raise CutipWorkflowError(
                f"Error loading workflow '{workflow_path}': {exc}"
            ) from exc

        if not hasattr(module, "main"):
            raise CutipWorkflowError(
                f"Workflow '{workflow_path}' must define a 'main(ctx)' function"
            )

        try:
            module.main(ctx)
        except Exception as exc:
            raise CutipWorkflowError(
                f"Error executing workflow '{workflow_path}': {exc}"
            ) from exc
