from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from cutip.models.unit import Unit
from cutip.utils.exceptions import CutipWorkflowError
from cutip.workspace.registry import CutipRegistry


class UnitStartupLoader:
    """Dynamically imports a unit's ``startup.py`` and calls its hooks.

    ``startup.py`` lives alongside the unit's YAML file::

        cutip/units/<project-name>/startup.py

    Two optional hooks are supported:

    ``pre_build(ctx)``
        Called *before* that unit's image is built or pulled.  Use this to
        stage files into the build context — e.g. resolving local npm
        ``file:`` dependencies that must be present when ``podman build`` runs.
        CUTIP calls this per-unit in declaration order before any images are
        built.

    ``startup(ctx)``
        Called *after* the group's ``workflow.main(ctx)`` returns.  Use this
        for post-start tasks: health checks, printing connection instructions,
        running initialization commands via exec, etc.

    Either hook is silently skipped when ``startup.py`` is absent or when the
    file does not define the corresponding function.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._module_cache: dict[str, tuple[ModuleType, Path]] = {}

    def _startup_path(self, unit: Unit, registry: CutipRegistry) -> Path | None:
        """Return the path to startup.py for *unit*, or None if it doesn't exist.

        The loader first tries the path registered in the registry (next to the
        unit YAML), then falls back to the conventional location::

            <project_root>/cutip/units/<unit-name>/startup.py
        """
        unit_source = registry.source_of(f"units/{unit.name}")
        if unit_source is not None:
            candidate = unit_source.parent / "startup.py"
        else:
            candidate = self.project_root / "cutip" / "units" / unit.name / "startup.py"

        return candidate if candidate.is_file() else None

    def _load_module(self, unit: Unit, startup_path: Path) -> ModuleType:
        """Import startup.py (cached per unit name)."""
        if unit.name in self._module_cache:
            return self._module_cache[unit.name][0]

        module_name = f"cutip._startup_{unit.name}"
        spec = importlib.util.spec_from_file_location(module_name, startup_path)
        if spec is None or spec.loader is None:
            raise CutipWorkflowError(
                f"Could not create module spec from '{startup_path}'"
            )

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            raise CutipWorkflowError(
                f"Error loading startup '{startup_path}': {exc}"
            ) from exc

        self._module_cache[unit.name] = (module, startup_path)
        return module

    def run_pre_build(self, unit: Unit, ctx, registry: CutipRegistry) -> None:
        """Call ``pre_build(ctx)`` for *unit* if ``startup.py`` defines it.

        Silently returns when:
        - ``startup.py`` is not found next to the unit YAML
        - the file exists but does not define a ``pre_build()`` function

        Raises :class:`~cutip.utils.exceptions.CutipWorkflowError` on any
        exception raised inside ``pre_build()``.
        """
        from loguru import logger

        startup_path = self._startup_path(unit, registry)
        if startup_path is None:
            return

        module = self._load_module(unit, startup_path)

        if not hasattr(module, "pre_build"):
            return

        logger.info(f"Running pre_build for unit '{unit.name}' ...")
        try:
            module.pre_build(ctx)
        except Exception as exc:
            raise CutipWorkflowError(
                f"Error in pre_build '{startup_path}': {exc}"
            ) from exc

    def run(self, unit: Unit, ctx, registry: CutipRegistry) -> None:
        """Call ``startup(ctx)`` for *unit* if ``startup.py`` exists and defines it.

        Silently returns when:
        - ``startup.py`` is not found next to the unit YAML
        - the file exists but does not define a ``startup()`` function

        Raises :class:`~cutip.utils.exceptions.CutipWorkflowError` on any
        exception raised inside ``startup()``.
        """
        from loguru import logger

        startup_path = self._startup_path(unit, registry)
        if startup_path is None:
            logger.debug(f"No startup.py for unit '{unit.name}' — skipping.")
            return

        module = self._load_module(unit, startup_path)

        if not hasattr(module, "startup"):
            logger.debug(
                f"startup.py for unit '{unit.name}' has no startup() — skipping."
            )
            return

        logger.info(f"Running startup for unit '{unit.name}' ...")
        try:
            module.startup(ctx)
        except Exception as exc:
            raise CutipWorkflowError(
                f"Error in startup '{startup_path}': {exc}"
            ) from exc
