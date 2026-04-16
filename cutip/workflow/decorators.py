"""Workflow decorators for self-describing CUTIP actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps

_ACTION_ATTR = "_cutip_action_meta"
_ORCHESTRATOR_ATTR = "_cutip_is_orchestrator"


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

    Parsed by the AST introspector to group actions into named stages.
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
            stage("Setup")
            check_env(ctx)

            stage("Deploy")
            deploy(ctx)
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    setattr(wrapper, _ORCHESTRATOR_ATTR, True)
    return wrapper
