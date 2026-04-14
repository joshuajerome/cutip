"""cutip.workflow — self-describing workflow decorators and execution engine.

Public API::

    from cutip.workflow import action, orchestrator, stage, ActionMeta, StageMeta
"""

from cutip.workflow.decorators import ActionMeta, StageMeta, action, orchestrator, stage
from cutip.workflow.engine import ActionFailed, WorkflowContext, WorkflowEngine
from cutip.workflow.introspect import (
    extract_action_order,
    extract_action_order_from_module,
    extract_staged_action_order,
    get_module_actions,
    get_orchestrator,
    StageGroup,
)

__all__ = [
    "ActionFailed",
    "ActionMeta",
    "StageMeta",
    "StageGroup",
    "WorkflowContext",
    "WorkflowEngine",
    "action",
    "extract_action_order",
    "extract_action_order_from_module",
    "extract_staged_action_order",
    "get_module_actions",
    "get_orchestrator",
    "orchestrator",
    "stage",
]
