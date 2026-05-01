"""Cutip workflow execution engine.

Reads the action/stage graph from decorators and executes actions with
retry, timeout, on_fail, continue_on_fail, when, and parallel stage support.

Usage::

    from cutip.workflow.engine import WorkflowEngine

    engine = WorkflowEngine(module, config)
    engine.run()
"""

from __future__ import annotations

import os
import signal
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

from cutip.workflow.decorators import ActionMeta, _ACTION_ATTR
from cutip.workflow import decorators as _decorators_module
from cutip.workflow.introspect import (
    StageGroup,
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
    """Context passed to workflow actions.

    Attributes:
        config: Full parsed project YAML as a dict.
        data: Workflow data section — freeform key-value pairs from data: in YAML.
        vars: User-defined variables from vars: section.
        secrets: Sensitive values from secrets: section.
        results: Action return values, keyed by action name.
        host: Execution target — "local", "container", or "remote".
        container_runtime: Container engine — "auto", "podman", or "docker".
        ssh_host: SSH host IP (from hosts.yaml, for HTTP URL construction).

    Typed connections (lazy, created on first access):
        ctx.ssh       → SSHSession (host: remote only, from hosts.yaml)
        ctx.kubectl   → KubectlSession (bound to ctx.ssh, namespace from config)
        ctx.container → ContainerRuntime (auto-detected)
    """

    config: dict[str, Any]
    vars: dict[str, str] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    host: str = "local"
    container_runtime: str = "auto"
    ssh_host: str = ""
    _hosts: dict[str, str] = field(default_factory=dict, repr=False)
    _ssh: Any = field(default=None, repr=False)
    _kubectl: Any = field(default=None, repr=False)
    _container: Any = field(default=None, repr=False)

    @property
    def data(self) -> dict[str, Any]:
        """Workflow data — freeform config from data: section."""
        return self.config.get("data", {})

    @property
    def globals(self) -> dict[str, str]:
        """Flattened global data from ~/.cutip/data.yaml.

        Returns dotted-path keys mapped to scalar string values, suitable
        for passing as the ``globals`` argument to
        ``rsty.config.substitute_vars``. The underlying file is loaded
        once per workflow run.
        """
        cached = getattr(self, "_globals_cache", None)
        if cached is not None:
            return cached
        from cutip import globals as _globals

        flat = _globals.flatten(_globals.read_globals())
        self._globals_cache = flat
        return flat

    @property
    def ssh(self) -> Any:
        """SSH session — created on first access from hosts.yaml credentials.

        Returns:
            SSHSession with .exec(cmd), .probe(), .close() methods.
        """
        if self._ssh is not None:
            return self._ssh

        # Backward-compat resolution order:
        # 1. Flat top-level fields on _hosts (legacy: host: …, username: …)
        # 2. Single-entry nested hosts file (the named entry's fields)
        # 3. Error — multiple entries means workflow must use ctx.host_for(name).
        creds = {
            "host": self._hosts.get("host", ""),
            "username": self._hosts.get("username", ""),
            "password": self._hosts.get("password", ""),
            "port": self._hosts.get("port", "22"),
        }
        if not creds["host"] or not creds["username"] or not creds["password"]:
            resolved = getattr(self, "_resolved_hosts", None) or {}
            named = {k: v for k, v in resolved.items() if k != "_default"}
            if len(named) == 1:
                only = next(iter(named.values()))
                creds = {
                    "host": only.get("host", ""),
                    "username": only.get("username", ""),
                    "password": only.get("password", ""),
                    "port": only.get("port", "22"),
                }
            elif len(named) > 1:
                raise RuntimeError(
                    "ctx.ssh is ambiguous: hosts.yaml has multiple named entries "
                    f"({', '.join(sorted(named.keys()))}). Use ctx.host_for('<name>') "
                    "to pick one explicitly."
                )

        host = creds["host"]
        username = creds["username"]
        password = creds["password"]
        port = int(creds["port"])

        if not host or not username or not password:
            raise RuntimeError(
                "SSH credentials not set. Run: cutip hosts set <name>.host=<ip> <name>.username=<user> <name>.password=<pw>"
            )

        from rsty._core import ssh_connect

        self._ssh = ssh_connect(
            host=host, username=username, password=password, port=port
        )
        self.ssh_host = host
        return self._ssh

    @property
    def kubectl(self) -> Any:
        """Kubectl session — bound to ctx.ssh, namespace from config.

        Reads namespace from config["kubernetes"]["namespace"] or
        data["kubernetes"]["namespace"].

        Returns:
            KubectlSession with get/exec/patch/rollout methods.
        """
        if self._kubectl is not None:
            return self._kubectl

        # Find namespace from config
        ns = "default"
        k8s_config = (self.config.get("data") or self.config).get("kubernetes", {})
        if isinstance(k8s_config, dict):
            ns = k8s_config.get("namespace", "default")

        ssh_session = self.ssh  # triggers SSH connection if not already established

        from rsty._core import kubectl_connect

        self._kubectl = kubectl_connect(ssh_session, namespace=ns)
        return self._kubectl

    @property
    def container(self) -> Any:
        """Container runtime — auto-detected on first access.

        Returns:
            ContainerRuntime with build/create/start/stop/exec methods.
        """
        if self._container is not None:
            return self._container

        from rsty._core import container_connect

        self._container = container_connect()
        return self._container

    def _close_connections(self) -> None:
        """Close all connections. Called by the engine on workflow exit."""
        if self._ssh is not None:
            try:
                self._ssh.close()
            except Exception:
                pass
            self._ssh = None
        self._kubectl = None
        self._container = None

    def host_for(self, name: str) -> dict[str, str]:
        """Return the resolved host config for the given name.

        Works regardless of the hosts file format:
          - **Nested** (current): returns ``{"host": ..., "username": ...,
            "password": ...}`` for the named entry. Resolves
            ``global: true`` references against ``~/.cutip/hosts.yaml``
            transparently.
          - **Flat** (legacy): the entire flat dict is treated as a single
            unnamed host. ``ctx.host_for("default")`` (or any name) returns it.

        Raises:
            KeyError: if ``name`` isn't found in the resolved hosts.

        Example::

            ub20 = ctx.host_for("ub20")
            sesh = ssh.open(host=ub20["host"], username=ub20["username"],
                           password=ub20["password"])
        """
        # If we already have resolved nested data, look it up
        resolved = getattr(self, "_resolved_hosts", None)
        if resolved is not None:
            if name in resolved:
                return dict(resolved[name])
            # For flat-file backward compat: any name returns the flat dict
            if "_default" in resolved:
                return dict(resolved["_default"])
            raise KeyError(
                f"host '{name}' not found in hosts file. "
                f"Available: {', '.join(sorted(resolved.keys()))}"
            )

        # Fall back to the raw _hosts dict (flat, legacy path)
        if self._hosts:
            return dict(self._hosts)
        raise KeyError(
            f"host '{name}' requested but no hosts file is loaded for this project"
        )

    def exec_tracked(
        self,
        sesh: Any,
        cmd: str,
        *,
        label: str = "",
        timeout: int = 3600,
        line_timeout: int = 900,
        on_line: Any = None,
    ) -> Any:
        """Run a remote command via streaming exec, tracking the remote PID.

        When this workflow is running under ``cutip run --bg``, the remote PID
        is appended to ``~/.cutip/processes/<cu-id>/remote.json`` so
        ``cutip ps stop`` can cascade-kill it on the actual remote host.

        For foreground runs (no cu-id env var), behaves identically to
        ``ssh.exec_stream`` — no tracking overhead.

        Args:
            sesh: An open SSHSession (rsty.ssh.SSHSession).
            cmd: Shell command to run on the remote host.
            label: Human-readable label for `cutip ps inspect` (e.g. 'make-blueprint').
            timeout: Total wall-clock timeout in seconds.
            line_timeout: Per-line read timeout — bump for commands that go
                silent for long stretches (docker pulls, big downloads).
            on_line: Optional callback invoked per output line.

        Returns:
            The StreamResult from rsty.ssh.exec_stream (exit_code + lines).
        """
        from rsty import ssh

        cu_id = os.environ.get("CUTIP_BG_CU_ID")
        if not cu_id:
            # Foreground run — no tracking, just stream
            return ssh.exec_stream(
                sesh, cmd, on_line=on_line, timeout=timeout, line_timeout=line_timeout
            )

        # Background run — wrap to capture remote PID, register, then run
        from cutip import processes as _proc

        # Use shell_with_pid to launch the cmd in the background and capture
        # the remote PID. Then we read until completion.
        pid, shell = ssh.shell_with_pid(sesh, cmd)

        # Determine host + username from the session's host attribute
        # (rsty exposes them as the first arg of ssh.open). We approximate
        # via ctx._hosts since the session doesn't currently expose them.
        host = self.ssh_host or self._hosts.get("host", "")
        username = self._hosts.get("username", "")

        _proc.append_remote_pid(
            cu_id,
            _proc.RemoteProc(
                host=host, username=username, pid=pid, label=label or cmd[:40]
            ),
        )

        # Drain output until the EXIT sentinel from shell_with_pid wrapper
        try:
            from rsty.ssh import _EXIT_RE  # type: ignore

            lines: list[str] = []
            import time as _time

            deadline = _time.monotonic() + timeout
            while True:
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"exec_tracked timed out after {timeout}s")
                line = shell.read_line(timeout=min(line_timeout, int(remaining) + 1))
                line = line.rstrip("\r\n")
                m = _EXIT_RE.search(line)
                if m:
                    pre = line[: m.start()].rstrip()
                    if pre:
                        lines.append(pre)
                        if on_line is not None:
                            on_line(pre)
                    return ssh.StreamResult(exit_code=int(m.group(1)), lines=lines)
                lines.append(line)
                if on_line is not None:
                    on_line(line)
        finally:
            try:
                shell.close()
            except Exception:
                pass

    @classmethod
    def from_config(cls, config: dict, hosts: dict | None = None) -> WorkflowContext:
        host = config.get("host", "local")
        runtime = config.get("container.rt", "auto")

        return cls(
            config=config,
            vars=config.get("vars") or {},
            secrets=config.get("secrets") or {},
            host=host,
            container_runtime=runtime,
            _hosts=hosts or {},
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
        hosts: dict | None = None,
    ):
        self.module = module
        self.config = config
        self.ctx = WorkflowContext.from_config(config, hosts)
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
        """Execute the workflow and return the context with results.

        Runs the @orchestrator function directly, intercepting @action calls
        at runtime to apply orchestration policies (retry, timeout, on_fail, etc.).

        The orchestrator controls flow — if/else, loops, conditionals all work
        naturally because Python executes them. The engine wraps each @action
        call with the orchestration layer.
        """
        # Patch all @action functions in the module to go through the engine
        self._patch_actions()

        try:
            orch = get_orchestrator(self.module)
            if orch:
                orch(self.ctx)
            elif hasattr(self.module, "main"):
                self.module.main(self.ctx)
        finally:
            self._unpatch_actions()
            self.ctx._close_connections()

        return self.ctx

    def _patch_actions(self) -> None:
        """Replace @action-decorated functions and stage() with engine-wrapped versions."""
        self._originals: dict[str, Callable] = {}
        self._current_stage: str | None = None

        for func_name, (func, meta) in self._actions.items():
            self._originals[func_name] = getattr(self.module, func_name)

            def make_wrapper(fn_name: str, fn: Callable, m: ActionMeta):
                def wrapper(*args, **kwargs):
                    return self._execute_action(m)

                return wrapper

            setattr(self.module, func_name, make_wrapper(func_name, func, meta))

        # Patch stage() to emit events at runtime
        self._original_stage = _decorators_module.stage

        def _runtime_stage(title=None, description=None, parallel=False):
            if self._current_stage is not None:
                self.on_event(
                    ActionEvent(
                        event="stage_completed",
                        action=self._current_stage,
                    )
                )
            stage_title = title or "Stage"
            self._current_stage = stage_title
            self.on_event(
                ActionEvent(
                    event="stage_started",
                    action=stage_title,
                    detail=description or "",
                )
            )

        _decorators_module.stage = _runtime_stage

        # Also patch in the module's namespace if it imported stage directly
        if hasattr(self.module, "stage"):
            self._originals["stage"] = getattr(self.module, "stage")
            setattr(self.module, "stage", _runtime_stage)

    def _unpatch_actions(self) -> None:
        """Restore original @action functions and stage()."""
        # Emit final stage_completed
        if self._current_stage is not None:
            self.on_event(
                ActionEvent(
                    event="stage_completed",
                    action=self._current_stage,
                )
            )

        for func_name, original in self._originals.items():
            setattr(self.module, func_name, original)

        _decorators_module.stage = self._original_stage

    def _run_staged(self, stage_groups: list[StageGroup]) -> None:
        """Execute stage groups with orchestration policies."""
        for group in stage_groups:
            stage = group.stage
            stage_title = stage.title or "Stage"

            self.on_event(
                ActionEvent(
                    event="stage_started",
                    action=stage_title,
                    detail=stage.description or "",
                )
            )

            if stage.parallel:
                self._run_parallel(group.actions, stage_title)
            else:
                self._run_sequential(group.actions, stage_title)

            self.on_event(
                ActionEvent(
                    event="stage_completed",
                    action=stage_title,
                )
            )

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
            raise ActionFailed(
                meta.name, RuntimeError(f"Action '{meta.name}' not found")
            )
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
                self.on_event(
                    ActionEvent(
                        event="action_skipped",
                        action=meta.name,
                        detail="when condition returned False",
                    )
                )
                return None

        # Execute with retry/timeout
        max_attempts = meta.retry + 1
        current_delay = meta.delay

        for attempt in range(1, max_attempts + 1):
            self.on_event(
                ActionEvent(
                    event="action_started",
                    action=meta.name,
                    attempt=attempt,
                )
            )

            try:
                if meta.timeout is not None:
                    result = self._run_with_timeout(func, meta.timeout)
                else:
                    result = func(self.ctx)

                # Success
                self.ctx.results[meta.name] = result
                self.on_event(
                    ActionEvent(
                        event="action_completed",
                        action=meta.name,
                        attempt=attempt,
                        result=result,
                    )
                )
                return result

            except Exception as e:
                # Check if this error type should stop retries immediately
                if attempt < max_attempts and not self._is_fatal(e):
                    self.on_event(
                        ActionEvent(
                            event="action_retrying",
                            action=meta.name,
                            attempt=attempt,
                            detail=f"Retrying in {current_delay}s ({attempt}/{max_attempts}): {e}",
                            error=e,
                        )
                    )
                    if current_delay > 0:
                        time.sleep(current_delay)
                    current_delay *= meta.backoff
                    continue

                # All retries exhausted
                self.on_event(
                    ActionEvent(
                        event="action_failed",
                        action=meta.name,
                        attempt=attempt,
                        error=e,
                    )
                )

                # Try on_fail action
                if meta.on_fail:
                    self._run_on_fail(meta.on_fail, e)

                if meta.continue_on_fail:
                    self.ctx.results[meta.name] = None
                    return None

                raise ActionFailed(meta.name, e) from e

    @staticmethod
    def _is_fatal(error: Exception) -> bool:
        """Check if an error should stop retries immediately.

        AuthError and ValidationError are fatal — retrying won't help.
        All other errors (ConnectionError, TimeoutError, CommandFailed,
        generic Exception) are considered transient and retryable.
        """
        try:
            from rsty.errors import AuthError, ValidationError

            return isinstance(error, (AuthError, ValidationError))
        except ImportError:
            pass

        # Fallback: check class name for environments without rsty
        name = type(error).__name__
        return name in ("AuthError", "ValidationError")

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
            from concurrent.futures import (
                ThreadPoolExecutor,
                TimeoutError as FutureTimeout,
            )

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
        self.on_event(
            ActionEvent(
                event="action_started",
                action=on_fail_name,
                detail=f"on_fail triggered by: {original_error}",
            )
        )

        try:
            result = func(self.ctx)
            self.ctx.results[on_fail_name] = result
            self.on_event(
                ActionEvent(
                    event="action_completed",
                    action=on_fail_name,
                    result=result,
                )
            )
        except Exception as e:
            self.on_event(
                ActionEvent(
                    event="action_failed",
                    action=on_fail_name,
                    error=e,
                )
            )
