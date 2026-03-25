"""cutip.workflow — self-describing workflow decorators.

Public API::

    from cutip.workflow import action, orchestrator, stage, ActionMeta, StageMeta
"""

from cutip.workflow.decorators import ActionMeta, StageMeta, action, orchestrator, stage
from cutip.workflow.introspect import (
    extract_action_order,
    extract_action_order_from_module,
    extract_staged_action_order,
    get_module_actions,
    get_orchestrator,
)

__all__ = [
    "ActionMeta",
    "StageMeta",
    "action",
    "extract_action_order",
    "extract_action_order_from_module",
    "extract_staged_action_order",
    "get_module_actions",
    "get_orchestrator",
    "orchestrator",
    "stage",
]
