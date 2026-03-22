from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from cutip.models.unit import Unit
from cutip.utils.exceptions import CutipWorkflowError
from cutip.workspace.registry import CutipRegistry


class UnitHookLoader:
    """Dynamically imports a unit's hook files and calls their entry points.

    Hook resolution order per unit:

    **Prehook** (before image build):
        1. ``unit.spec.hooks.prehook`` (explicit filename from YAML)
        2. ``prehook.py`` in the unit directory
        3. ``startup.py`` with ``pre_build(ctx)`` (legacy fallback, deprecation warning)

    **Posthook** (after orchestration):
        1. ``unit.spec.hooks.posthook`` (explicit filename from YAML)
        2. ``posthook.py`` in the unit directory
        3. ``startup.py`` with ``startup(ctx)`` (legacy fallback, deprecation warning)

    All hooks are silently skipped when the file or function does not exist.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._module_cache: dict[str, tuple[ModuleType, Path]] = {}

    def _unit_dir(self, unit: Unit, registry: CutipRegistry) -> Path:
        """Return the directory containing the unit's YAML and hook files."""
        unit_source = registry.source_of(f"units/{unit.name}")
        if unit_source is not None:
            return unit_source.parent
        return self.project_root / "cutip" / "units" / unit.name

    def _load_module(self, name: str, file_path: Path) -> ModuleType:
        """Import a Python file (cached by name)."""
        if name in self._module_cache:
            return self._module_cache[name][0]

        module_name = f"cutip._hook_{name}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise CutipWorkflowError(f"Could not create module spec from '{file_path}'")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            raise CutipWorkflowError(f"Error loading hook '{file_path}': {exc}") from exc

        self._module_cache[name] = (module, file_path)
        return module

    def run_prehook(self, unit: Unit, ctx, registry: CutipRegistry) -> None:
        """Run the prehook for a unit (before image build).

        Resolution order:
        1. unit.spec.hooks.prehook → explicit file
        2. prehook.py → main(ctx)
        3. startup.py → pre_build(ctx) (legacy)
        """
        from loguru import logger

        unit_dir = self._unit_dir(unit, registry)

        # 1. Explicit hook from YAML
        if unit.spec.hooks.prehook:
            hook_path = unit_dir / unit.spec.hooks.prehook
            if hook_path.is_file():
                module = self._load_module(f"{unit.name}_prehook", hook_path)
                self._call(module, "main", unit.name, "prehook", hook_path, ctx=ctx)
                return

        # 2. Convention: prehook.py
        prehook_path = unit_dir / "prehook.py"
        if prehook_path.is_file():
            module = self._load_module(f"{unit.name}_prehook", prehook_path)
            self._call(module, "main", unit.name, "prehook", prehook_path, ctx=ctx)
            return

        # 3. Legacy: startup.py → pre_build(ctx)
        startup_path = unit_dir / "startup.py"
        if startup_path.is_file():
            module = self._load_module(f"{unit.name}_startup", startup_path)
            if hasattr(module, "pre_build"):
                logger.warning(
                    f"Unit '{unit.name}': startup.py pre_build() is deprecated. "
                    f"Use prehook.py with main(ctx) instead."
                )
                self._call(
                    module, "pre_build", unit.name, "pre_build (legacy)", startup_path, ctx=ctx
                )

    def run_posthook(self, unit: Unit, ctx, registry: CutipRegistry) -> None:
        """Run the posthook for a unit (after orchestration).

        Resolution order:
        1. unit.spec.hooks.posthook → explicit file
        2. posthook.py → main(ctx)
        3. startup.py → startup(ctx) (legacy)
        """
        from loguru import logger

        unit_dir = self._unit_dir(unit, registry)

        # 1. Explicit hook from YAML
        if unit.spec.hooks.posthook:
            hook_path = unit_dir / unit.spec.hooks.posthook
            if hook_path.is_file():
                module = self._load_module(f"{unit.name}_posthook", hook_path)
                self._call(module, "main", unit.name, "posthook", hook_path, ctx=ctx)
                return

        # 2. Convention: posthook.py
        posthook_path = unit_dir / "posthook.py"
        if posthook_path.is_file():
            module = self._load_module(f"{unit.name}_posthook", posthook_path)
            self._call(module, "main", unit.name, "posthook", posthook_path, ctx=ctx)
            return

        # 3. Legacy: startup.py → startup(ctx)
        startup_path = unit_dir / "startup.py"
        if startup_path.is_file():
            module = self._load_module(f"{unit.name}_startup", startup_path)
            if hasattr(module, "startup"):
                logger.warning(
                    f"Unit '{unit.name}': startup.py startup() is deprecated. "
                    f"Use posthook.py with main(ctx) instead."
                )
                self._call(module, "startup", unit.name, "startup (legacy)", startup_path, ctx=ctx)

    def _call(
        self,
        module: ModuleType,
        func_name: str,
        unit_name: str,
        label: str,
        file_path: Path,
        ctx=None,
    ) -> None:
        """Call a function on a module, passing ctx if accepted."""
        from loguru import logger

        fn = getattr(module, func_name, None)
        if fn is None:
            return

        logger.info(f"Running {label} for unit '{unit_name}' ...")
        try:
            fn(ctx)
        except Exception as exc:
            raise CutipWorkflowError(f"Error in {label} '{file_path}': {exc}") from exc


# Backward-compatible alias
UnitStartupLoader = UnitHookLoader
