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
    CleanupMeta,
    ConfigMeta,
    HealthcheckMeta,
    HookMeta,
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
        return [StageGroup(stage=StageMeta(), actions=[action_funcs[n] for n in all_actions])]

    # Number untitled stages
    stage_counter = 0
    for group in groups:
        stage_counter += 1
        if group.stage.title is None:
            # Replace with numbered stage — need to create new frozen instance
            numbered = StageMeta(title=f"Stage {stage_counter}", description=group.stage.description)
            # Since StageGroup is frozen, rebuild it
            groups[groups.index(group)] = StageGroup(stage=numbered, actions=group.actions)

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
                groups.append(StageGroup(stage=current_stage, actions=list(current_actions)))
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
    return _collect_staged_items(stmts, action_funcs, groups, current_stage, current_actions)


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
    if isinstance(func, ast.Name) and func.id == "stage":
        is_stage = True
    elif isinstance(func, ast.Attribute) and func.attr == "stage":
        is_stage = True

    if not is_stage:
        return None

    # Extract title and description
    title: str | None = None
    description: str | None = None

    # Positional: first arg is title
    if call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            title = first.value

    # Keyword arguments
    for kw in call.keywords:
        if kw.arg == "title" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            title = kw.value.value
        elif kw.arg == "description" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            description = kw.value.value

    return StageMeta(title=title, description=description)


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
    if isinstance(func, ast.Name) and func.id in action_funcs and func.id not in call_order:
        call_order.append(func.id)


# ── Decorator names recognized by extract_hook_order ──────────────────────────

_DECORATOR_NAMES = frozenset(
    {"action", "prehook", "posthook", "healthcheck", "cleanup", "config", "orchestrator"}
)


@dataclass(frozen=True)
class AnnotatedFunc:
    """A function annotated with a CUTIP decorator, as discovered by AST."""

    func_name: str
    decorator: str  # "action", "prehook", "posthook", etc.
    meta: ActionMeta | HookMeta | HealthcheckMeta | CleanupMeta | ConfigMeta | None
    line: int
    source: str  # relative file path


@dataclass
class GroupGraph:
    """Compiled graph for a group — all annotated functions across its files."""

    group_name: str
    prehooks: list[AnnotatedFunc] = field(default_factory=list)
    actions: list[AnnotatedFunc] = field(default_factory=list)
    healthchecks: list[AnnotatedFunc] = field(default_factory=list)
    posthooks: list[AnnotatedFunc] = field(default_factory=list)
    cleanups: list[AnnotatedFunc] = field(default_factory=list)
    configs: list[AnnotatedFunc] = field(default_factory=list)
    orchestrator_source: str | None = None


def extract_hook_order(file_path: Path, rel_source: str = "") -> list[AnnotatedFunc]:
    """Parse a Python file and return all CUTIP-decorated functions in definition order."""
    source_label = rel_source or str(file_path)
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except Exception:
        return []

    results: list[AnnotatedFunc] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            deco_name = _get_decorator_name(deco)
            if deco_name not in _DECORATOR_NAMES:
                continue
            meta = _extract_generic_meta(deco, deco_name)
            results.append(
                AnnotatedFunc(
                    func_name=node.name,
                    decorator=deco_name,
                    meta=meta,
                    line=node.lineno,
                    source=source_label,
                )
            )
            break  # one decorator per function for our purposes
    return results


def compile_group_graph(
    group_name: str,
    workflow_files: list[tuple[Path, str]],
) -> GroupGraph:
    """Compile a GroupGraph from a list of (absolute_path, relative_label) file pairs."""
    graph = GroupGraph(group_name=group_name)

    for abs_path, rel_label in workflow_files:
        if not abs_path.is_file():
            continue
        funcs = extract_hook_order(abs_path, rel_source=rel_label)
        for f in funcs:
            if f.decorator == "prehook":
                graph.prehooks.append(f)
            elif f.decorator == "action":
                graph.actions.append(f)
            elif f.decorator == "healthcheck":
                graph.healthchecks.append(f)
            elif f.decorator == "posthook":
                graph.posthooks.append(f)
            elif f.decorator == "cleanup":
                graph.cleanups.append(f)
            elif f.decorator == "config":
                graph.configs.append(f)
            elif f.decorator == "orchestrator":
                graph.orchestrator_source = rel_label

    return graph


def render_mermaid(graph: GroupGraph) -> str:
    """Render a GroupGraph as a Mermaid flowchart TD string."""
    lines = ["graph TD"]
    node_id = 0

    def _add_node(label: str, source: str) -> str:
        nonlocal node_id
        nid = f"n{node_id}"
        node_id += 1
        safe_label = label.replace('"', "'")
        lines.append(f'    {nid}["{safe_label}"]')
        return nid

    prev_ids: list[str] = []

    # Config subgraph
    if graph.configs:
        lines.append("    subgraph Config")
        for f in graph.configs:
            label = f.meta.name if f.meta and hasattr(f.meta, "name") else f.func_name
            nid = _add_node(label, f.source)
            prev_ids.append(nid)
        lines.append("    end")

    # Prehook subgraph
    if graph.prehooks:
        lines.append("    subgraph Prehook")
        new_ids = []
        for f in graph.prehooks:
            label = f.meta.name if f.meta and hasattr(f.meta, "name") else f.func_name
            nid = _add_node(label, f.source)
            for pid in prev_ids:
                lines.append(f"    {pid} --> {nid}")
            new_ids.append(nid)
        lines.append("    end")
        prev_ids = new_ids

    # Workflow subgraph (actions + healthchecks)
    workflow_funcs = graph.actions + graph.healthchecks
    if workflow_funcs:
        lines.append("    subgraph Workflow")
        new_ids = []
        for f in workflow_funcs:
            label = f.meta.name if f.meta and hasattr(f.meta, "name") else f.func_name
            nid = _add_node(label, f.source)
            for pid in prev_ids:
                lines.append(f"    {pid} --> {nid}")
            new_ids.append(nid)
            prev_ids = [nid]
        lines.append("    end")
        prev_ids = new_ids if new_ids else prev_ids

    # Posthook subgraph
    if graph.posthooks:
        lines.append("    subgraph Posthook")
        new_ids = []
        for f in graph.posthooks:
            label = f.meta.name if f.meta and hasattr(f.meta, "name") else f.func_name
            nid = _add_node(label, f.source)
            for pid in prev_ids:
                lines.append(f"    {pid} --> {nid}")
            new_ids.append(nid)
        lines.append("    end")
        prev_ids = new_ids

    # Cleanup subgraph
    if graph.cleanups:
        lines.append("    subgraph Cleanup")
        for f in graph.cleanups:
            label = f.meta.name if f.meta and hasattr(f.meta, "name") else f.func_name
            nid = _add_node(label, f.source)
            for pid in prev_ids:
                lines.append(f"    {pid} --> {nid}")
        lines.append("    end")

    return "\n".join(lines)


def _get_decorator_name(deco: ast.expr) -> str:
    """Extract the decorator function name from an AST node."""
    if isinstance(deco, ast.Call):
        func = deco.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    elif isinstance(deco, ast.Name):
        return deco.id
    elif isinstance(deco, ast.Attribute):
        return deco.attr
    return ""


def _extract_generic_meta(
    deco: ast.expr, deco_name: str
) -> ActionMeta | HookMeta | HealthcheckMeta | CleanupMeta | ConfigMeta | None:
    """Extract metadata from any CUTIP decorator AST node."""
    if deco_name == "orchestrator":
        return None
    if not isinstance(deco, ast.Call):
        return None

    if deco_name == "action":
        return _extract_meta_from_decorator(deco)

    kwargs = _extract_kwargs(deco)
    name = kwargs.get("name", "")
    if not isinstance(name, str):
        return None

    if deco_name in ("prehook", "posthook"):
        return HookMeta(name=name, description=kwargs.get("description", "") or "")
    elif deco_name == "healthcheck":
        return HealthcheckMeta(
            name=name,
            container=kwargs.get("container", "") or "",
            timeout=_int_kwarg(kwargs, "timeout", 30),
            interval=_int_kwarg(kwargs, "interval", 1),
            retries=_int_kwarg(kwargs, "retries", 30),
        )
    elif deco_name == "cleanup":
        return CleanupMeta(
            name=name,
            description=kwargs.get("description", "") or "",
            container=kwargs.get("container"),
        )
    elif deco_name == "config":
        return ConfigMeta(name=name, description=kwargs.get("description", "") or "")
    return None


def _extract_kwargs(deco: ast.Call) -> dict[str, str | int | list[str] | None]:
    """Extract keyword arguments from an AST Call node."""
    kwargs: dict[str, str | int | list[str] | None] = {}
    # Positional: first arg is name
    if deco.args:
        first = deco.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            kwargs["name"] = first.value
    for kw in deco.keywords:
        if kw.arg is None:
            continue
        if isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, (str, int)):
                kwargs[kw.arg] = kw.value.value
        elif isinstance(kw.value, ast.List):
            items = []
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    items.append(elt.value)
            kwargs[kw.arg] = items
    return kwargs


def _int_kwarg(kwargs: dict, key: str, default: int) -> int:
    val = kwargs.get(key, default)
    return val if isinstance(val, int) else default
