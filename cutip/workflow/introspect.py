"""AST-based introspection for workflow action ordering."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from cutip.workflow.decorators import (
    _ACTION_ATTR,
    _ORCHESTRATOR_ATTR,
    ActionMeta,
    StageMeta,
)


def get_module_actions(module: ModuleType) -> dict[str, ActionMeta]:
    """Return a mapping of function-name → ActionMeta for all @action functions."""
    actions: dict[str, ActionMeta] = {}
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if callable(obj):
            meta = getattr(obj, _ACTION_ATTR, None)
            if isinstance(meta, ActionMeta):
                actions[attr_name] = meta
    return actions


def get_orchestrator(module: ModuleType) -> Callable | None:
    """Return the @orchestrator-decorated function, or None."""
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        if callable(obj) and getattr(obj, _ORCHESTRATOR_ATTR, False):
            return obj
    return None


def extract_action_order(workflow_path: Path) -> list[ActionMeta]:
    """Extract the ordered list of actions from a workflow file using AST analysis.

    Strategy:
    1. Parse file with ast.parse
    2. Find @action-decorated functions and their ActionMeta kwargs
    3. Find @orchestrator function (or ``main``)
    4. Walk orchestrator body for call nodes matching action function names
    5. Return ActionMeta list in call order
    6. Fallback to definition order if orchestrator not found
    """
    source = workflow_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(workflow_path))

    # Step 1: Find all @action-decorated functions and extract their metadata
    action_funcs: dict[str, ActionMeta] = {}  # func_name → ActionMeta
    action_order: list[str] = []  # definition order

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if _is_action_decorator(deco):
                meta = _extract_meta_from_decorator(deco)
                if meta is not None:
                    action_funcs[node.name] = meta
                    action_order.append(node.name)
                break

    if not action_funcs:
        return []

    # Step 2: Find orchestrator body and extract call order
    orch_body = _find_orchestrator_body(tree)
    if orch_body is None:
        # Fallback: definition order
        return [action_funcs[name] for name in action_order]

    # Step 3: Walk orchestrator body for calls to action functions
    call_order: list[str] = []
    _collect_action_calls(orch_body, action_funcs, call_order)

    if not call_order:
        # No recognized calls found (dynamic dispatch?) → definition order
        return [action_funcs[name] for name in action_order]

    return [action_funcs[name] for name in call_order]


def extract_action_order_from_module(module: ModuleType) -> list[ActionMeta]:
    """Extract action order from an already-loaded module.

    Uses the module's __file__ for AST analysis, falling back to runtime
    introspection in definition order.
    """
    mod_file = getattr(module, "__file__", None)
    if mod_file is not None:
        return extract_action_order(Path(mod_file))

    # No file available — fall back to runtime introspection
    actions = get_module_actions(module)
    return list(actions.values())


@dataclass(frozen=True)
class StageGroup:
    """A group of actions belonging to a named stage."""

    stage: StageMeta
    actions: list[ActionMeta] = field(default_factory=list)


def extract_staged_action_order(workflow_path: Path) -> list[StageGroup]:
    """Extract actions grouped by stage() separators from a workflow file.

    Returns a list of StageGroup objects. Each group contains a StageMeta
    (with optional title/description) and the actions that follow that stage()
    call until the next stage() or end of orchestrator body.

    Actions before any stage() call are placed in an implicit first group
    with no title (Desktop may render these outside any stage lane, or as
    setup/teardown).

    If no stage() calls are found, returns a single StageGroup containing
    all actions.
    """
    source = workflow_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(workflow_path))

    # Find action-decorated functions
    action_funcs: dict[str, ActionMeta] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if _is_action_decorator(deco):
                meta = _extract_meta_from_decorator(deco)
                if meta is not None:
                    action_funcs[node.name] = meta
                break

    if not action_funcs:
        return []

    # Find orchestrator body
    orch_body = _find_orchestrator_body(tree)
    if orch_body is None:
        return [StageGroup(stage=StageMeta(), actions=list(action_funcs.values()))]

    # Walk body collecting stage boundaries and action calls
    groups: list[StageGroup] = []
    current_stage = StageMeta()
    current_actions: list[ActionMeta] = []

    current_stage, current_actions = _collect_staged_items(
        orch_body, action_funcs, groups, current_stage, current_actions
    )

    # Flush remaining actions
    if current_actions:
        groups.append(StageGroup(stage=current_stage, actions=list(current_actions)))

    # If no stages were found, return single group with all actions
    if not groups:
        all_actions: list[str] = []
        _collect_action_calls(orch_body, action_funcs, all_actions)
        return [
            StageGroup(
                stage=StageMeta(), actions=[action_funcs[n] for n in all_actions]
            )
        ]

    # Number untitled stages
    for i, group in enumerate(groups):
        if group.stage.title is None:
            numbered = StageMeta(
                title=f"Stage {i + 1}", description=group.stage.description
            )
            groups[i] = StageGroup(stage=numbered, actions=group.actions)

    return groups


def _collect_staged_items(
    stmts: list[ast.stmt],
    action_funcs: dict[str, ActionMeta],
    groups: list[StageGroup],
    current_stage: StageMeta,
    current_actions: list[ActionMeta],
) -> tuple[StageMeta, list[ActionMeta]]:
    """Walk statements collecting stage() boundaries and action calls."""
    for stmt in stmts:
        # Check for stage() call
        stage_meta = _extract_stage_call(stmt)
        if stage_meta is not None:
            # Flush current group if it has actions
            if current_actions:
                groups.append(
                    StageGroup(stage=current_stage, actions=list(current_actions))
                )
                current_actions.clear()
            current_stage = stage_meta
            continue

        # Check for action call
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if isinstance(func, ast.Name) and func.id in action_funcs:
                current_actions.append(action_funcs[func.id])
                continue

        # Assignment with action call
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            value = stmt.value
            if isinstance(value, ast.Call):
                func = value.func
                if isinstance(func, ast.Name) and func.id in action_funcs:
                    current_actions.append(action_funcs[func.id])
                    continue

        # Recurse into with blocks (ssh.session, etc.)
        if isinstance(stmt, ast.With):
            current_stage, current_actions = _collect_staged_items_with_state(
                stmt.body, action_funcs, groups, current_stage, current_actions
            )
            continue

        # Recurse into if/for/while/try
        if isinstance(stmt, ast.If):
            current_stage, current_actions = _collect_staged_items_with_state(
                stmt.body, action_funcs, groups, current_stage, current_actions
            )
            current_stage, current_actions = _collect_staged_items_with_state(
                stmt.orelse, action_funcs, groups, current_stage, current_actions
            )
        elif isinstance(stmt, (ast.For, ast.While)):
            current_stage, current_actions = _collect_staged_items_with_state(
                stmt.body, action_funcs, groups, current_stage, current_actions
            )
        elif isinstance(stmt, ast.Try):
            current_stage, current_actions = _collect_staged_items_with_state(
                stmt.body, action_funcs, groups, current_stage, current_actions
            )
            for handler in stmt.handlers:
                current_stage, current_actions = _collect_staged_items_with_state(
                    handler.body, action_funcs, groups, current_stage, current_actions
                )

    return current_stage, current_actions


def _collect_staged_items_with_state(
    stmts: list[ast.stmt],
    action_funcs: dict[str, ActionMeta],
    groups: list[StageGroup],
    current_stage: StageMeta,
    current_actions: list[ActionMeta],
) -> tuple[StageMeta, list[ActionMeta]]:
    """Wrapper that threads mutable state through recursive calls."""
    return _collect_staged_items(
        stmts, action_funcs, groups, current_stage, current_actions
    )


def _extract_stage_call(stmt: ast.stmt) -> StageMeta | None:
    """Check if a statement is a stage() call and extract its metadata."""
    if not isinstance(stmt, ast.Expr):
        return None
    if not isinstance(stmt.value, ast.Call):
        return None

    call = stmt.value
    func = call.func

    # Match stage(...) or workflow.stage(...)
    is_stage = False
    if (isinstance(func, ast.Name) and func.id == "stage") or (
        isinstance(func, ast.Attribute) and func.attr == "stage"
    ):
        is_stage = True

    if not is_stage:
        return None

    # Extract title, description, parallel
    title: str | None = None
    description: str | None = None
    parallel: bool = False

    # Positional: first arg is title
    if call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            title = first.value

    # Keyword arguments
    for kw in call.keywords:
        if (
            kw.arg == "title"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            title = kw.value.value
        elif (
            kw.arg == "description"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            description = kw.value.value
        elif (
            kw.arg == "parallel"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, bool)
        ):
            parallel = kw.value.value

    return StageMeta(title=title, description=description, parallel=parallel)


def _is_action_decorator(deco: ast.expr) -> bool:
    """Check if a decorator node is an @action(...) call."""
    if isinstance(deco, ast.Call):
        func = deco.func
        if isinstance(func, ast.Name) and func.id == "action":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "action":
            return True
    return False


def _extract_meta_from_decorator(deco: ast.Call) -> ActionMeta | None:
    """Parse ActionMeta fields from an @action(...) AST call node."""
    kwargs: dict[str, str | int | float | bool | list[str] | None] = {}

    # Positional: first arg is name
    if deco.args:
        name_node = deco.args[0]
        if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
            kwargs["name"] = name_node.value

    # Keyword arguments
    for kw in deco.keywords:
        if kw.arg is None:
            continue
        if isinstance(kw.value, ast.Constant):
            val = kw.value.value
            if isinstance(val, (str, int, float, bool)):
                kwargs[kw.arg] = val
        elif isinstance(kw.value, ast.List):
            items = []
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    items.append(elt.value)
            kwargs[kw.arg] = items

    name = kwargs.get("name")
    if not isinstance(name, str):
        return None

    description = kwargs.get("description", "")
    container = kwargs.get("container")
    host = kwargs.get("host")
    depends_on = kwargs.get("depends_on", [])

    return ActionMeta(
        name=name,
        description=description if isinstance(description, str) else "",
        container=container if isinstance(container, str) else None,
        host=host if isinstance(host, str) else None,
        depends_on=depends_on if isinstance(depends_on, list) else [],
        retry=_int_kwarg(kwargs, "retry", 0),
        delay=_float_kwarg(kwargs, "delay", 0.0),
        backoff=_float_kwarg(kwargs, "backoff", 1.0),
        timeout=_float_kwarg_optional(kwargs, "timeout"),
        on_fail=kwargs.get("on_fail")
        if isinstance(kwargs.get("on_fail"), str)
        else None,
        continue_on_fail=bool(kwargs.get("continue_on_fail", False)),
        # `when` is a callable — can't be parsed from AST, only available at runtime
    )


def _find_orchestrator_body(tree: ast.Module) -> list[ast.stmt] | None:
    """Find the body of the @orchestrator or main() function."""
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        # Check for @orchestrator decorator
        for deco in node.decorator_list:
            if isinstance(deco, ast.Name) and deco.id == "orchestrator":
                return node.body
            if isinstance(deco, ast.Attribute) and deco.attr == "orchestrator":
                return node.body
        # Fallback: look for main()
        if node.name == "main":
            return node.body
    return None


def _collect_action_calls(
    stmts: list[ast.stmt],
    action_funcs: dict[str, ActionMeta],
    call_order: list[str],
) -> None:
    """Recursively walk statements collecting calls to action functions in order."""
    for stmt in stmts:
        # Direct call: action_func(ctx) as expression
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            _check_call(stmt.value, action_funcs, call_order)
        # Assignment: result = action_func(ctx)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            value = stmt.value
            if isinstance(value, ast.Call):
                _check_call(value, action_funcs, call_order)
        # If/else blocks
        elif isinstance(stmt, ast.If):
            _collect_action_calls(stmt.body, action_funcs, call_order)
            _collect_action_calls(stmt.orelse, action_funcs, call_order)
        # For/while loops
        elif isinstance(stmt, (ast.For, ast.While)):
            _collect_action_calls(stmt.body, action_funcs, call_order)
        # Try blocks
        elif isinstance(stmt, ast.Try):
            _collect_action_calls(stmt.body, action_funcs, call_order)
            for handler in stmt.handlers:
                _collect_action_calls(handler.body, action_funcs, call_order)


def _check_call(
    call: ast.Call,
    action_funcs: dict[str, ActionMeta],
    call_order: list[str],
) -> None:
    """If *call* targets a known action function, append to *call_order*."""
    func = call.func
    if (
        isinstance(func, ast.Name)
        and func.id in action_funcs
        and func.id not in call_order
    ):
        call_order.append(func.id)


def _int_kwarg(kwargs: dict, key: str, default: int) -> int:
    val = kwargs.get(key, default)
    return val if isinstance(val, int) else default


def _float_kwarg(kwargs: dict, key: str, default: float) -> float:
    val = kwargs.get(key, default)
    if isinstance(val, (int, float)):
        return float(val)
    return default


def _float_kwarg_optional(kwargs: dict, key: str) -> float | None:
    val = kwargs.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return None
