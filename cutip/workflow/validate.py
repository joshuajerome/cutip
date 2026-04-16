"""Comprehensive project validation.

Validates all user-facing config fields before workflow execution.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def validate_project(
    project_path: Path,
    config: dict[str, Any],
    hosts: dict[str, Any] | None = None,
    workflow_path: Path | None = None,
) -> list[str]:
    """Validate a project config and return a list of errors.

    Returns an empty list if everything is valid.
    """
    errors: list[str] = []

    # 1. Project name
    if not config.get("project"):
        errors.append("Missing 'project' field")

    # 2. Host type
    host = config.get("host", config.get("backend", "local"))
    if host in ("docker", "podman"):
        host = "container"
    valid_hosts = ("local", "container", "remote")
    if host not in valid_hosts:
        errors.append(f"Invalid host: '{host}' (must be one of: {', '.join(valid_hosts)})")

    # 3. Container runtime
    if host == "container":
        rt = config.get("container.rt", config.get("container_runtime", "auto"))
        valid_rts = ("auto", "podman", "docker")
        if rt not in valid_rts:
            errors.append(f"Invalid container.rt: '{rt}' (must be one of: {', '.join(valid_rts)})")

    # 4. Workflow file exists and parses
    if workflow_path:
        if not workflow_path.exists():
            errors.append(f"Workflow not found: {workflow_path.name}")
        else:
            try:
                source = workflow_path.read_text(encoding="utf-8")
                ast.parse(source, filename=str(workflow_path))
            except SyntaxError as e:
                errors.append(f"Workflow syntax error: {workflow_path.name} line {e.lineno}: {e.msg}")

    # 5. Connections — check required fields
    connections = config.get("connections") or {}
    for name, conn in connections.items():
        conn_type = conn.get("type")
        if not conn_type:
            errors.append(f"Connection '{name}' missing 'type' field")
            continue

        valid_types = ("ssh", "kubectl", "container")
        if conn_type not in valid_types:
            errors.append(f"Connection '{name}' invalid type: '{conn_type}' (must be one of: {', '.join(valid_types)})")

        if conn_type == "kubectl":
            if not conn.get("session"):
                errors.append(f"Connection '{name}' (kubectl) missing 'session' field")
            elif conn["session"] not in connections:
                errors.append(f"Connection '{name}' references session '{conn['session']}' which is not defined")

    # 6. Remote connections need hosts file
    if host == "remote" and connections:
        ssh_connections = [n for n, c in connections.items() if c.get("type") == "ssh"]
        if ssh_connections and not hosts:
            errors.append(f"host: remote with SSH connections requires hosts.yaml (missing credentials for: {', '.join(ssh_connections)})")
        elif hosts:
            for name in ssh_connections:
                host_creds = hosts.get(name, {})
                for field in ("host", "username", "password"):
                    conn_val = connections[name].get(field, "")
                    host_val = host_creds.get(field, "")
                    if not conn_val and not host_val:
                        errors.append(f"Connection '{name}' missing '{field}' (set in hosts.yaml)")

    # 7. Container runtime reachable
    if host == "container":
        try:
            from rsty._core import container_connect
            rt = container_connect()
            # If we get here, runtime is reachable
        except ImportError:
            errors.append("rsty not installed (pip install rsty)")
        except Exception as e:
            errors.append(f"Container runtime not reachable: {e}")

    # 8. Var/secret refs
    # Already handled by Rust _validate, so skip here

    return errors
