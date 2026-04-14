"""Cutip workflow execution engine.

Reads the action/stage graph from decorators and executes actions with
retry, timeout, on_fail, continue_on_fail, when, and parallel stage support.

Usage::

    from cutip.workflow.engine import WorkflowEngine

    engine = WorkflowEngine(module, config)
    engine.run()
"""

from __future__ import annotations

import signal
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

from cutip.workflow.decorators import ActionMeta, StageMeta, _ACTION_ATTR
from cutip.workflow.introspect import (
    StageGroup,
    extract_staged_action_order,
    get_module_actions,
    get_orchestrator,
)


# ── Events ──────────────────────────────────────────────────────────────────

@dataclass
class ActionEvent:
    """Event emitted during action execution."""

    event: str  # stage_started, stage_completed, action_started, action_completed, action_failed, action_retrying, action_skipped
    action: str  # action name or stage title
    detail: str = ""
    attempt: int = 0
    result: Any = None
    error: Exception | None = None


EventCallback = Callable[[ActionEvent], None]


# ── Context ─────────────────────────────────────────────────────────────────

@dataclass
class WorkflowContext:
    """Lightweight context passed to workflow actions.

    Carries config, vars, secrets, and action results.
    """

    config: dict
    vars: dict = field(default_factory=dict)
    secrets: dict = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    backend: str = "local"

    @classmethod
    def from_config(cls, config: dict) -> WorkflowContext:
        return cls(
            config=config,
            vars=config.get("vars", {}),
            secrets=config.get("secrets", {}),
            backend=config.get("backend", "local"),
        )


# ── Engine ──────────────────────────────────────────────────────────────────

class ActionFailed(Exception):
    """Raised when an action fails after all retries."""

    def __init__(self, action_name: str, original: Exception):
        self.action_name = action_name
        self.original = original
        super().__init__(f"Action '{action_name}' failed: {original}")


class WorkflowEngine:
    """Execute a workflow module with orchestration policies.

    The engine:
    1. Discovers @action-decorated functions and the @orchestrator entry point
    2. Extracts the stage/action graph (via AST or runtime introspection)
    3. Executes each stage sequentially (or in parallel if stage.parallel=True)
    4. Applies retry/timeout/on_fail/continue_on_fail/when per action
    5. Stores action return values on ctx.results
    6. Emits events for each lifecycle transition
    """

    def __init__(
        self,
        module: ModuleType,
        config: dict,
        on_event: EventCallback | None = None,
    ):
        self.module = module
        self.config = config
        self.ctx = WorkflowContext.from_config(config)
        self.on_event = on_event or (lambda e: None)

        # Build function lookup: func_name → (callable, ActionMeta)
        self._actions: dict[str, tuple[Callable, ActionMeta]] = {}
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if callable(obj):
                meta = getattr(obj, _ACTION_ATTR, None)
                if isinstance(meta, ActionMeta):
                    self._actions[attr_name] = (obj, meta)

        # Build name → func_name reverse lookup (for on_fail references)
        self._name_to_func: dict[str, str] = {}
        for func_name, (_, meta) in self._actions.items():
            self._name_to_func[meta.name] = func_name

    def run(self) -> WorkflowContext:
        """Execute the workflow and return the context with results."""
        # Try AST-based staged extraction first
        mod_file = getattr(self.module, "__file__", None)
        if mod_file:
            from pathlib import Path
            stage_groups = extract_staged_action_order(Path(mod_file))
        else:
            stage_groups = []

        if stage_groups:
            self._run_staged(stage_groups)
        else:
            # Fallback: run orchestrator directly (no stage awareness)
            orch = get_orchestrator(self.module)
            if orch:
                orch(self.ctx)
            elif hasattr(self.module, "main"):
                self.module.main(self.ctx)

        return self.ctx

    def _run_staged(self, stage_groups: list[StageGroup]) -> None:
        """Execute stage groups with orchestration policies."""
        for group in stage_groups:
            stage = group.stage
            stage_title = stage.title or "Stage"

            self.on_event(ActionEvent(
                event="stage_started",
                action=stage_title,
                detail=stage.description or "",
            ))

            if stage.parallel:
                self._run_parallel(group.actions, stage_title)
            else:
                self._run_sequential(group.actions, stage_title)

            self.on_event(ActionEvent(
                event="stage_completed",
                action=stage_title,
            ))

    def _run_sequential(self, actions: list[ActionMeta], stage_title: str) -> None:
        """Execute actions one at a time, in order."""
        for meta in actions:
            self._execute_action(meta)

    def _run_parallel(self, actions: list[ActionMeta], stage_title: str) -> None:
        """Execute all actions in a stage concurrently."""
        if not actions:
            return

        errors: list[ActionFailed] = []

        with ThreadPoolExecutor(max_workers=len(actions)) as executor:
            futures = {}
            for meta in actions:
                future = executor.submit(self._execute_action, meta)
                futures[future] = meta

            for future in as_completed(futures):
                meta = futures[future]
                try:
                    future.result()
                except ActionFailed as e:
                    if not meta.continue_on_fail:
                        errors.append(e)

        if errors:
            raise errors[0]

    def _execute_action(self, meta: ActionMeta) -> Any:
        """Execute a single action with all orchestration policies applied."""
        # Find the callable
        func_name = self._name_to_func.get(meta.name)
        if func_name is None or func_name not in self._actions:
            raise ActionFailed(meta.name, RuntimeError(f"Action '{meta.name}' not found"))
        func, runtime_meta = self._actions[func_name]

        # Runtime meta is authoritative — it has the actual decorator params
        # including `when` callables that AST can't capture.
        meta = runtime_meta

        # Check `when` condition
        if meta.when is not None:
            try:
                should_run = meta.when(self.ctx)
            except Exception:
                should_run = False
            if not should_run:
                self.on_event(ActionEvent(
                    event="action_skipped",
                    action=meta.name,
                    detail="when condition returned False",
                ))
                return None

        # Execute with retry/timeout
        last_error: Exception | None = None
        max_attempts = meta.retry + 1
        current_delay = meta.delay

        for attempt in range(1, max_attempts + 1):
            self.on_event(ActionEvent(
                event="action_started",
                action=meta.name,
                attempt=attempt,
            ))

            try:
                if meta.timeout is not None:
                    result = self._run_with_timeout(func, meta.timeout)
                else:
                    result = func(self.ctx)

                # Success
                self.ctx.results[meta.name] = result
                self.on_event(ActionEvent(
                    event="action_completed",
                    action=meta.name,
                    attempt=attempt,
                    result=result,
                ))
                return result

            except Exception as e:
                last_error = e

                if attempt < max_attempts:
                    self.on_event(ActionEvent(
                        event="action_retrying",
                        action=meta.name,
                        attempt=attempt,
                        detail=f"Retrying in {current_delay}s ({attempt}/{max_attempts})",
                        error=e,
                    ))
                    if current_delay > 0:
                        time.sleep(current_delay)
                    current_delay *= meta.backoff
                    continue

                # All retries exhausted
                self.on_event(ActionEvent(
                    event="action_failed",
                    action=meta.name,
                    attempt=attempt,
                    error=e,
                ))

                # Try on_fail action
                if meta.on_fail:
                    self._run_on_fail(meta.on_fail, e)

                if meta.continue_on_fail:
                    self.ctx.results[meta.name] = None
                    return None

                raise ActionFailed(meta.name, e) from e

    def _run_with_timeout(self, func: Callable, timeout: float) -> Any:
        """Execute a function with a timeout.

        Uses SIGALRM on Unix main thread for clean cancellation,
        falls back to thread-based timeout otherwise (Windows, or
        when called from a non-main thread like parallel stages).
        """
        import threading

        use_signal = (
            sys.platform != "win32"
            and threading.current_thread() is threading.main_thread()
        )

        if use_signal:
            def _alarm_handler(signum, frame):
                raise TimeoutError(f"Action timed out after {timeout}s")

            old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.alarm(int(timeout))
            try:
                return func(self.ctx)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        else:
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, self.ctx)
                try:
                    return future.result(timeout=timeout)
                except FutureTimeout:
                    raise TimeoutError(f"Action timed out after {timeout}s")

    def _run_on_fail(self, on_fail_name: str, original_error: Exception) -> None:
        """Execute the on_fail action."""
        func_name = self._name_to_func.get(on_fail_name)
        if func_name is None or func_name not in self._actions:
            return

        func, meta = self._actions[func_name]
        self.on_event(ActionEvent(
            event="action_started",
            action=on_fail_name,
            detail=f"on_fail triggered by: {original_error}",
        ))

        try:
            result = func(self.ctx)
            self.ctx.results[on_fail_name] = result
            self.on_event(ActionEvent(
                event="action_completed",
                action=on_fail_name,
                result=result,
            ))
        except Exception as e:
            self.on_event(ActionEvent(
                event="action_failed",
                action=on_fail_name,
                error=e,
            ))
