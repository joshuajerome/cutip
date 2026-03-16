"""AST-based introspection for workflow action ordering."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

from cutip.workflow.decorators import _ACTION_ATTR, _ORCHESTRATOR_ATTR, ActionMeta


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
    kwargs: dict[str, str | list[str] | None] = {}

    # Positional: first arg is name
    if deco.args:
        name_node = deco.args[0]
        if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
            kwargs["name"] = name_node.value

    # Keyword arguments
    for kw in deco.keywords:
        if kw.arg is None:
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            kwargs[kw.arg] = kw.value.value
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
    depends_on = kwargs.get("depends_on", [])

    return ActionMeta(
        name=name,
        description=description if isinstance(description, str) else "",
        container=container if isinstance(container, str) else None,
        depends_on=depends_on if isinstance(depends_on, list) else [],
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
            value = stmt.value if isinstance(stmt, ast.Assign) else stmt.value
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
    if isinstance(func, ast.Name) and func.id in action_funcs:
        if func.id not in call_order:
            call_order.append(func.id)
