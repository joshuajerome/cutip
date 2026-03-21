"""cutip.workflow — self-describing workflow decorators.

Public API::

    from cutip.workflow import action, orchestrator, ActionMeta, extract_action_order
"""

from cutip.workflow.decorators import ActionMeta, action, orchestrator
from cutip.workflow.introspect import (
    extract_action_order,
    extract_action_order_from_module,
    get_module_actions,
    get_orchestrator,
)

__all__ = [
    "ActionMeta",
    "action",
    "extract_action_order",
    "extract_action_order_from_module",
    "get_module_actions",
    "get_orchestrator",
    "orchestrator",
]
