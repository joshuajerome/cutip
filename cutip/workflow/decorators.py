"""Workflow decorators for self-describing CUTIP actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps

_ACTION_ATTR = "_cutip_action_meta"
_ORCHESTRATOR_ATTR = "_cutip_is_orchestrator"


@dataclass(frozen=True)
class ActionMeta:
    """Metadata attached to an ``@action``-decorated function."""

    name: str
    description: str = ""
    container: str | None = None
    depends_on: list[str] = field(default_factory=list)


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
