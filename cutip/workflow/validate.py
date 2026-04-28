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
    host = config.get("host", "local")
    valid_hosts = ("local", "container", "remote")
    if host not in valid_hosts:
        errors.append(f"Invalid host: '{host}' (must be one of: {', '.join(valid_hosts)})")

    # 3. Container runtime
    if host == "container":
        rt = config.get("container.rt", "auto")
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

    # 7. Hosts file — check existence and empty values
    data = config.get("data") or {}
    hosts_ref = data.get("hosts")
    if hosts_ref:
        # Project declares a hosts file in data.hosts
        hosts_path = project_path.parent / hosts_ref
        if not hosts_path.exists():
            errors.append(f"{hosts_ref} not found")
            errors.append(f"  Create with: cutip hosts set <key>=<value>")
        else:
            import yaml
            with open(hosts_path) as f:
                h = yaml.safe_load(f) or {}
            empty_keys = [k for k, v in h.items() if not v and v != 0]
            if empty_keys:
                warnings.append(f"Empty values in {hosts_ref}: {', '.join(empty_keys)}")
                warnings.append(f"  Set with: cutip hosts set {' '.join(f'{k}=<value>' for k in empty_keys)}")
    elif host == "remote":
        # Fallback: host: remote without data.hosts
        hosts_path = project_path.parent / "hosts.yaml"
        if not hosts_path.exists() and not hosts:
            errors.append("hosts.yaml not found (required for host: remote)")
            errors.append("  Create with: cutip hosts set host=<ip> username=<user> password=<pw>")
        else:
            h = hosts or {}
            missing = [f for f in ("host", "username", "password") if not h.get(f)]
            if missing:
                errors.append(f"Missing SSH credentials in hosts.yaml: {', '.join(missing)}")
                errors.append(f"  Set with: cutip hosts set {' '.join(f'{f}=<value>' for f in missing)}")

    # 8. Container runtime reachable
    if host == "container":
        try:
            from rsty._core import container_connect
            container_connect()
        except ImportError:
            errors.append("rsty not installed (pip install rsty)")
        except Exception as e:
            errors.append(f"Container runtime not reachable: {e}")

    # 9. Data section type check
    raw_data = config.get("data")
    if raw_data is not None and not isinstance(raw_data, dict):
        errors.append(f"'data' section must be a mapping, got {type(data).__name__}")

    return errors, warnings
