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

    def run_unit(self, unit_name: str) -> None:
        """Execute a unit's workflow.py (if it exists).

        Called from an orchestrator to run a specific unit's workflow::

            @orchestrator
            def main(ctx):
                ctx.run_unit("db")
                ctx.run_unit("web")

        If the unit has no workflow.py, just starts the container.
        """
        from loguru import logger

        unit = self.resolved_units.get(unit_name)
        if unit is None:
            raise CutipWorkflowError(f"Unit '{unit_name}' not found in resolved units")

        unit_source = self.registry.source_of(f"units/{unit_name}")
        if unit_source is not None:
            unit_dir = unit_source.parent
        else:
            unit_dir = self.project_root / "cutip" / "units" / unit_name

        workflow_path = unit_dir / "workflow.py"
        if workflow_path.is_file():
            logger.info(f"Running workflow for unit '{unit_name}' ...")
            module = _load_module_from_path(f"cutip._unit_workflow_{unit_name}", workflow_path)
            fn = getattr(module, "main", None)
            if fn is not None:
                try:
                    fn(self)
                except Exception as exc:
                    raise CutipWorkflowError(
                        f"Error in unit workflow '{workflow_path}': {exc}"
                    ) from exc
                return

        # No workflow.py — just start the container
        from cutip.models.cards.container import ContainerCard

        container_ref = unit.spec.containerRef.ref
        card = self.resolved_cards.get(container_ref)
        if isinstance(card, ContainerCard) and self.runtime is not None:
            logger.info(f"Starting container '{card.metadata.name}' (no unit workflow)")
            self.runtime.containers.get(card.metadata.name).start()


def _load_module_from_path(module_name: str, file_path: Path) -> ModuleType:
    """Import a Python file by path, returning the loaded module."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise CutipWorkflowError(f"Could not create module spec from '{file_path}'")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        raise CutipWorkflowError(f"Error loading '{file_path}': {exc}") from exc

    return module


class WorkflowLoader:
    """Loads and executes a group's orchestrator or workflow.

    Resolution order:
    1. ``orchestrator.py`` in the group directory (new convention)
    2. ``workflow.py`` in the group directory (backward compatible)
    3. If neither has a ``main()`` or ``@orchestrator``, run unit workflows
       in group.yaml declaration order (zero-config default)
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._module_cache: dict[str, tuple[ModuleType, Path]] = {}

    def _group_dir(self, group: Group, registry: CutipRegistry) -> Path:
        group_source = registry.source_of(f"groups/{group.name}")
        if group_source is not None:
            return group_source.parent
        return self.project_root / "cutip" / "groups" / group.name

    def _load_module(self, group: Group, registry: CutipRegistry) -> tuple[ModuleType, Path] | None:
        """Import orchestrator.py or workflow.py (cached per group name)."""
        if group.name in self._module_cache:
            return self._module_cache[group.name]

        group_dir = self._group_dir(group, registry)

        # Try orchestrator.py first, then workflow.py
        for filename in (group.spec.orchestrator, group.spec.workflow):
            candidate = group_dir / filename
            if candidate.is_file():
                module_name = f"cutip._workflow_{group.name}"
                module = _load_module_from_path(module_name, candidate)
                self._module_cache[group.name] = (module, candidate)
                return module, candidate

        return None

    def run(self, group: Group, ctx: CutipContext, registry: CutipRegistry) -> None:
        """Import the orchestrator/workflow module and call main(ctx)."""
        result = self._load_module(group, registry)

        if result is None:
            # No orchestrator or workflow — run unit workflows in declaration order
            self._run_units_default(group, ctx)
            return

        module, workflow_path = result

        if hasattr(module, "main"):
            try:
                module.main(ctx)
            except Exception as exc:
                raise CutipWorkflowError(
                    f"Error executing workflow '{workflow_path}': {exc}"
                ) from exc
            return

        # Check for @orchestrator-decorated function
        from cutip.workflow.decorators import _ORCHESTRATOR_ATTR

        orch = next(
            (
                fn
                for fn in vars(module).values()
                if callable(fn) and getattr(fn, _ORCHESTRATOR_ATTR, False)
            ),
            None,
        )
        if orch is not None:
            try:
                orch(ctx)
            except Exception as exc:
                raise CutipWorkflowError(
                    f"Error executing workflow '{workflow_path}': {exc}"
                ) from exc
            return

        # File exists but has no entry point — fall back to default unit execution
        self._run_units_default(group, ctx)

    def _run_units_default(self, group: Group, ctx: CutipContext) -> None:
        """Run unit workflows in group.yaml declaration order (zero-config default)."""
        from loguru import logger as _logger

        _logger.debug(f"No orchestrator found for group '{group.name}' — running units in order.")
        for unit_ref in group.spec.units:
            unit_name = unit_ref.ref.split("/")[-1]
            ctx.run_unit(unit_name)
