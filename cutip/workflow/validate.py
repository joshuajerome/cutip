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
) -> tuple[list[str], list[str]]:
    """Validate a project config and return (errors, warnings).

    Errors block execution. Warnings are informational.
    """
    errors: list[str] = []
    warnings: list[str] = []

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

    # 5. Empty vars
    vars_dict = config.get("vars") or {}
    empty_vars = [k for k, v in vars_dict.items() if not v]
    if empty_vars:
        warnings.append(f"Empty vars (use 'cutip vars set' or will be prompted): {', '.join(empty_vars)}")

    # 6. Empty secrets
    secrets_dict = config.get("secrets") or {}
    empty_secrets = [k for k, v in secrets_dict.items() if not v]
    if empty_secrets:
        warnings.append(f"Empty secrets (use 'cutip secrets set' or will be prompted): {', '.join(empty_secrets)}")

    # 7. Connections — check required fields
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

    # 8. Remote connections — hosts.yaml
    if host == "remote" and connections:
        ssh_connections = [n for n, c in connections.items() if c.get("type") == "ssh"]
        if ssh_connections and not hosts:
            hosts_path = project_path.parent / "hosts.yaml"
            if hosts_path.exists():
                pass  # hosts file exists but might be empty — check below
            else:
                errors.append(f"hosts.yaml not found (required for remote SSH connections: {', '.join(ssh_connections)})")
                errors.append(f"  Create with: cutip hosts set {project_path.name} {ssh_connections[0]}.host=<ip> {ssh_connections[0]}.username=<user> {ssh_connections[0]}.password=<pw>")

        hosts_data = hosts or {}
        for name in ssh_connections:
            host_creds = hosts_data.get(name, {})
            missing_fields = []
            for field in ("host", "username", "password"):
                conn_val = connections[name].get(field, "")
                host_val = host_creds.get(field, "")
                if not conn_val and not host_val:
                    missing_fields.append(field)
            if missing_fields:
                errors.append(f"Connection '{name}' missing: {', '.join(missing_fields)} (set in hosts.yaml)")

    # 9. Container runtime reachable
    if host == "container":
        try:
            from rsty._core import container_connect
            container_connect()
        except ImportError:
            errors.append("rsty not installed (pip install rsty)")
        except Exception as e:
            errors.append(f"Container runtime not reachable: {e}")

    return errors, warnings
