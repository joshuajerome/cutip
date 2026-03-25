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


def stage(title: str | None = None, description: str | None = None) -> None:
    """Workflow stage separator. No-op at runtime.

    Parsed by the AST introspector to group actions into named stages
    for cutip-desktop DAG visualization.

    With no arguments, Desktop labels stages numerically (Stage 1, Stage 2, ...).
    With title/description, Desktop shows the stage header and detail panel.

    Usage::

        @orchestrator
        def main(ctx):
            stage("Pre-op Validation", description="Verify SSH, K8s resources, and file integrity")
            validate_ssh(ctx, sesh)
            check_deploy(ctx, sesh, ns, deploy)

            stage("Operations")
            enable_keycloak(ctx, sesh, script)
            patch_handler(ctx, sesh, ns, deploy, patch)

            stage()  # Desktop shows "Stage 3"
            verify_pod(ctx, sesh, ns, deploy)
    """


@dataclass(frozen=True)
class ActionMeta:
    """Metadata attached to an ``@action``-decorated function."""

    name: str
    description: str = ""
    container: str | None = None
    depends_on: list[str] = field(default_factory=list)


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
    depends_on: list[str] | None = None,
) -> Callable:
    """Parameterized decorator that attaches :class:`ActionMeta` to a function.

    Usage::

        @action(name="Start DB", description="Start the database", container="cutip-db")
        def start_db(ctx):
            ctx.container("cutip-db").start()
    """
    meta = ActionMeta(
        name=name,
        description=description,
        container=container,
        depends_on=depends_on or [],
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
