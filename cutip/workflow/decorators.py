"""Workflow decorators for self-describing CUTIP actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps

_ACTION_ATTR = "_cutip_action_meta"
_ORCHESTRATOR_ATTR = "_cutip_is_orchestrator"
_PREHOOK_ATTR = "_cutip_prehook_meta"
_POSTHOOK_ATTR = "_cutip_posthook_meta"
_HEALTHCHECK_ATTR = "_cutip_healthcheck_meta"
_CLEANUP_ATTR = "_cutip_cleanup_meta"
_CONFIG_ATTR = "_cutip_config_meta"


# ---------------------------------------------------------------------------
# Stage separator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageMeta:
    """Metadata for a stage boundary in the orchestrator."""

    title: str | None = None
    description: str | None = None
    parallel: bool = False


def stage(
    title: str | None = None,
    description: str | None = None,
    parallel: bool = False,
) -> None:
    """Workflow stage separator. No-op at runtime.

    Parsed by the AST introspector to group actions into named stages
    for cutip-desktop DAG visualization and the execution engine.

    With no arguments, Desktop labels stages numerically (Stage 1, Stage 2, ...).
    With title/description, Desktop shows the stage header and detail panel.
    With parallel=True, all actions in this stage run concurrently.

    Usage::

        @orchestrator
        def main(ctx):
            stage("Pre-op Validation")
            validate_ssh(ctx)
            check_cluster(ctx)

            stage("Deploy", parallel=True)
            deploy_backend(ctx)
            deploy_frontend(ctx)

            stage("Verify")
            smoke_test(ctx)
    """


@dataclass(frozen=True)
class ActionMeta:
    """Metadata attached to an ``@action``-decorated function."""

    name: str
    description: str = ""
    container: str | None = None
    host: str | None = None
    depends_on: list[str] = field(default_factory=list)

    # Orchestration parameters
    retry: int = 0
    delay: float = 0.0
    backoff: float = 1.0
    timeout: float | None = None
    on_fail: str | None = None
    continue_on_fail: bool = False
    when: Callable | None = field(default=None, compare=False, hash=False)


@dataclass(frozen=True)
class HookMeta:
    """Metadata attached to ``@prehook`` or ``@posthook`` functions."""

    name: str
    description: str = ""


@dataclass(frozen=True)
class HealthcheckMeta:
    """Metadata attached to ``@healthcheck`` functions."""

    name: str
    container: str
    timeout: int = 30
    interval: int = 1
    retries: int = 30


@dataclass(frozen=True)
class CleanupMeta:
    """Metadata attached to ``@cleanup`` functions."""

    name: str
    description: str = ""
    container: str | None = None


@dataclass(frozen=True)
class ConfigMeta:
    """Metadata attached to ``@config`` functions."""

    name: str
    description: str = ""


def action(
    name: str,
    description: str = "",
    container: str | None = None,
    host: str | None = None,
    depends_on: list[str] | None = None,
    retry: int = 0,
    delay: float = 0.0,
    backoff: float = 1.0,
    timeout: float | None = None,
    on_fail: str | None = None,
    continue_on_fail: bool = False,
    when: Callable | None = None,
) -> Callable:
    """Parameterized decorator that attaches :class:`ActionMeta` to a function.

    Orchestration parameters control how the execution engine runs the action:

    - ``retry`` — Number of retry attempts on failure (default 0, no retry).
    - ``delay`` — Seconds between retries (default 0).
    - ``backoff`` — Multiply delay by this after each retry (default 1.0, no backoff).
    - ``timeout`` — Kill the action after this many seconds (default None, no timeout).
    - ``on_fail`` — Name of another @action to invoke if this action fails.
    - ``continue_on_fail`` — If True, the workflow continues even if this action fails.
    - ``when`` — Callable that receives ctx; action is skipped if it returns False.

    Usage::

        @action(name="Wait for API", retry=5, delay=10, backoff=2, timeout=120)
        def wait_for_api(ctx):
            service.poll_until_ready("http://localhost:8080")

        @action(name="Deploy backend", on_fail="rollback_backend")
        def deploy_backend(ctx):
            kubectl.patch_deployment(name="api", image=ctx.vars["api_image"])
    """
    meta = ActionMeta(
        name=name,
        description=description,
        container=container,
        host=host,
        depends_on=depends_on or [],
        retry=retry,
        delay=delay,
        backoff=backoff,
        timeout=timeout,
        on_fail=on_fail,
        continue_on_fail=continue_on_fail,
        when=when,
    )

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        setattr(wrapper, _ACTION_ATTR, meta)
        return wrapper

    return decorator


def orchestrator(fn: Callable) -> Callable:
    """Bare decorator marking the workflow entry point.

    Usage::

        @orchestrator
        def main(ctx):
            start_db(ctx)
            start_web(ctx)
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    setattr(wrapper, _ORCHESTRATOR_ATTR, True)
    return wrapper


def prehook(name: str, description: str = "") -> Callable:
    """Mark a function as a pre-build hook step.

    Usage::

        @prehook(name="Stage configs", description="Copy config files into build context")
        def stage_configs(ctx):
            ...
    """
    meta = HookMeta(name=name, description=description)

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        setattr(wrapper, _PREHOOK_ATTR, meta)
        return wrapper

    return decorator


def posthook(name: str, description: str = "") -> Callable:
    """Mark a function as a post-orchestration hook step.

    Usage::

        @posthook(name="Print info", description="Display connection details")
        def print_info(ctx):
            ...
    """
    meta = HookMeta(name=name, description=description)

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        setattr(wrapper, _POSTHOOK_ATTR, meta)
        return wrapper

    return decorator


def healthcheck(
    name: str,
    container: str,
    timeout: int = 30,
    interval: int = 1,
    retries: int = 30,
) -> Callable:
    """Mark a function as a health check step.

    Usage::

        @healthcheck(name="DB ready", container="cutip-db", timeout=30, retries=30)
        def wait_for_db(ctx):
            ...
    """
    meta = HealthcheckMeta(
        name=name, container=container, timeout=timeout, interval=interval, retries=retries
    )

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        setattr(wrapper, _HEALTHCHECK_ATTR, meta)
        return wrapper

    return decorator


def cleanup(name: str, description: str = "", container: str | None = None) -> Callable:
    """Mark a function as a teardown/cleanup step.

    Usage::

        @cleanup(name="Remove temp", description="Clean up temp files", container="cutip-web")
        def remove_temp(ctx):
            ...
    """
    meta = CleanupMeta(name=name, description=description, container=container)

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        setattr(wrapper, _CLEANUP_ATTR, meta)
        return wrapper

    return decorator


def config(name: str, description: str = "") -> Callable:
    """Mark a function as a configuration generation step.

    Usage::

        @config(name="Generate nginx.conf", description="Template nginx config from paths")
        def gen_nginx(ctx):
            ...
    """
    meta = ConfigMeta(name=name, description=description)

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        setattr(wrapper, _CONFIG_ATTR, meta)
        return wrapper

    return decorator
