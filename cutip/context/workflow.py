from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
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
        runtime:        Raw backend client (PodmanClient or DockerClient). None in dry-run / plan mode.
        paths:          Filesystem paths loaded from ``cutip/paths.yaml``.
                        Safe to sync via ``cutip push``.  Empty dict if absent.
        secrets:        Sensitive values loaded from ``cutip/secrets.yaml``.
                        Never synced, always gitignored.  Empty dict if absent.
    """

    group: Group
    resolved_units: dict[str, Unit] = field(default_factory=dict)
    resolved_cards: dict[str, CutipBaseModel] = field(default_factory=dict)
    registry: CutipRegistry = field(default_factory=CutipRegistry)
    project_root: Path = field(default_factory=Path.cwd)
    runtime: Any = None
    paths: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)

    def container(self, name: str):
        """Return the live container object for the given container name.

        Use in ``workflow.main()`` to start or inspect a container that CUTIP
        has already created::

            def main(ctx):
                ctx.container("my-app").start()

        The name must match the ``metadata.name`` of the ContainerCard.

        Raises ``NotFound`` (from the active backend SDK) if no container with
        that name exists (i.e. CUTIP has not yet created it).
        """
        if self.runtime is None:
            raise RuntimeError(
                "ctx.container() requires an active backend connection "
                "(runtime is None — are you in dry-run / plan mode?)"
            )
        return self.runtime.containers.get(name)


class WorkflowLoader:
    """Dynamically imports a group's workflow.py and calls main(ctx).

    ``main(ctx)`` is the group-level orchestration hook — it is responsible
    for starting containers (via ``ctx.container(name).start()``) and
    coordinating across units.  It is optional; if absent, CUTIP logs a
    debug message and continues.

    Unit-specific pre-build and post-start logic belongs in each unit's
    ``startup.py``, not here.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._module_cache: dict[str, tuple[ModuleType, Path]] = {}

    def _load_module(
        self, group: Group, registry: CutipRegistry
    ) -> tuple[ModuleType, Path]:
        """Import the workflow module (cached per group name)."""
        if group.name in self._module_cache:
            return self._module_cache[group.name]

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

        self._module_cache[group.name] = (module, workflow_path)
        return module, workflow_path

    def run(self, group: Group, ctx: CutipContext, registry: CutipRegistry) -> None:
        """Import the workflow module and call main(ctx)."""
        module, workflow_path = self._load_module(group, registry)

        if not hasattr(module, "main"):
            from loguru import logger as _logger
            _logger.debug(
                f"Workflow '{workflow_path}' has no main() — skipping group-level execution."
            )
            return

        try:
            module.main(ctx)
        except Exception as exc:
            raise CutipWorkflowError(
                f"Error executing workflow '{workflow_path}': {exc}"
            ) from exc
