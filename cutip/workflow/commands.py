"""Extract runtime commands from @action function bodies via AST.

Walks an action function's AST body to find calls to known block functions
(k8s.*, ssh.*, container.*) and generates human-readable command descriptions.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Maps module.function → command template
# {ns} {deploy} {secret} {cmd} {src} {dest} are replaced with arg values or placeholders
_COMMAND_MAP: dict[str, str] = {
    # New bound session API (kube.*, sesh.*)
    "kube.get": "kubectl get {resource} -n <ns> {name}",
    "kube.get_secret_value": "kubectl get secret -n <ns> {secret} -o jsonpath | base64 -d",
    "kube.find_pod": "kubectl get pod -n <ns> -o json | find {name_prefix}",
    "kube.exec": "kubectl exec -n <ns> {target} -- {cmd}",
    "kube.cat_file": "kubectl exec -n <ns> {target} -- cat {path}",
    "kube.cp": "kubectl cp <ns>/{pod}:{src} {dest}",
    "kube.apply": "kubectl apply -f {file}",
    "kube.rollout_status": "kubectl rollout status {resource} -n <ns>",
    "sesh.exec": "ssh :: {cmd}",
    "sesh.probe": "ssh :: whoami",
    # Legacy module.function API (k8s.*, ssh.*)
    "k8s.get_deployment": "kubectl get deployment -n {namespace} {deployment}",
    "k8s.get_secret": "kubectl get secret -n {namespace} {secret}",
    "k8s.get_pod": "kubectl get pod -n {namespace} | grep {deployment}",
    "k8s.exec": "kubectl exec -n {namespace} deploy/{deployment} -- {cmd}",
    "k8s.cp": "kubectl cp {namespace}/{deployment}:{src} {dest}",
    "k8s.apply": "kubectl apply -f {file}",
    "k8s.patch_deployment": "kubectl apply -f (patched {deployment} YAML)",
    "k8s.rollout_status": "kubectl rollout status deployment -n {namespace} {deployment}",
    "ssh.exec": "ssh :: {cmd}",
    "ssh.probe": "ssh :: whoami",
    # Container + file blocks
    "container.start": "container start {container}",
    "container.stop": "container stop {container}",
    "container.remove": "container remove {container}",
    "container.exec": "container exec {container} :: {cmd}",
    "is_empty": "(check output not empty)",
}


def _resolve_kwarg(node: ast.expr) -> str:
    """Try to extract a static string from an AST expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # f-string — extract what we can
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("<...>")
        return "".join(parts)
    if isinstance(node, ast.Name):
        return f"<{node.id}>"
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and isinstance(node.slice, ast.Constant)
    ):
        return f"<{node.value.id}[{node.slice.value}]>"
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"<{node.value.id}.{node.attr}>"
    return "<...>"


def _get_call_name(call: ast.Call) -> str | None:
    """Extract 'module.func' from a call node like k8s.get_deployment(...)."""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def extract_commands_from_action(func_node: ast.FunctionDef) -> list[str]:
    """Walk an action function body and extract human-readable command strings."""
    commands: list[str] = []

    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue

        call_name = _get_call_name(node)
        if call_name is None or call_name not in _COMMAND_MAP:
            continue

        template = _COMMAND_MAP[call_name]

        # Extract keyword arguments
        kwargs: dict[str, str] = {}
        for kw in node.keywords:
            if kw.arg:
                kwargs[kw.arg] = _resolve_kwarg(kw.value)

        # Extract positional args (e.g., kube.get("deployment", name=...))
        # Map first positional to 'resource' for kube.get
        if call_name == "kube.get" and node.args and len(node.args) >= 1:
            kwargs.setdefault("resource", _resolve_kwarg(node.args[0]))

        # Substitute into template
        cmd = template
        for key, val in kwargs.items():
            cmd = cmd.replace(f"{{{key}}}", val)

        # Clean up unreplaced placeholders
        import re

        cmd = re.sub(r"\{[a-z_]+\}", "<...>", cmd)

        commands.append(cmd)

    return commands


def extract_all_action_commands(workflow_path: Path) -> dict[str, list[str]]:
    """Extract commands for every @action function in a workflow file.

    Returns: {action_name: [command1, command2, ...]}
    """
    source = workflow_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(workflow_path))

    result: dict[str, list[str]] = {}

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        # Check for @action decorator
        action_name = None
        for deco in node.decorator_list:
            if isinstance(deco, ast.Call):
                func = deco.func
                if isinstance(func, ast.Name) and func.id == "action":
                    # Extract name from first arg or keyword
                    if deco.args and isinstance(deco.args[0], ast.Constant):
                        action_name = deco.args[0].value
                    for kw in deco.keywords:
                        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                            action_name = kw.value.value

        if action_name is None:
            continue

        commands = extract_commands_from_action(node)
        result[action_name] = commands

    return result
