"""Tests for cutip.workflow.validate — comprehensive project validation."""

import tempfile
from pathlib import Path

import pytest

from cutip.workflow.validate import validate_project


class TestValidateProject:

    def test_valid_local_project(self, tmp_path):
        wf = tmp_path / "test.workflow.py"
        wf.write_text("from cutip.workflow import action, orchestrator\n")
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "host": "local"},
            workflow_path=wf,
        )
        assert errors == []

    def test_missing_project_name(self, tmp_path):
        errors, warnings = validate_project(tmp_path / "test.yaml", {})
        assert any("project" in e.lower() for e in errors)

    def test_invalid_host(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "host": "invalid"},
        )
        assert any("host" in e.lower() for e in errors)

    def test_valid_hosts(self, tmp_path):
        for host in ("local", "container", "remote"):
            errors, warnings = validate_project(
                tmp_path / "test.yaml",
                {"project": "test", "host": host},
            )
            host_errors = [e for e in errors if "host" in e.lower() and "Invalid" in e]
            assert host_errors == [], f"host={host} should be valid"

    def test_invalid_container_rt(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "host": "container", "container.rt": "orbstack"},
        )
        assert any("container.rt" in e for e in errors)

    def test_valid_container_rt(self, tmp_path):
        for rt in ("auto", "podman", "docker"):
            errors, warnings = validate_project(
                tmp_path / "test.yaml",
                {"project": "test", "host": "container", "container.rt": rt},
            )
            rt_errors = [e for e in errors if "container.rt" in e]
            assert rt_errors == [], f"container.rt={rt} should be valid"

    def test_missing_workflow(self, tmp_path):
        wf = tmp_path / "nonexistent.py"
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test"},
            workflow_path=wf,
        )
        assert any("workflow" in e.lower() for e in errors)

    def test_workflow_syntax_error(self, tmp_path):
        wf = tmp_path / "bad.py"
        wf.write_text("def foo(\n")  # syntax error
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test"},
            workflow_path=wf,
        )
        assert any("syntax" in e.lower() for e in errors)

    def test_valid_workflow_syntax(self, tmp_path):
        wf = tmp_path / "good.py"
        wf.write_text("def foo(): pass\n")
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test"},
            workflow_path=wf,
        )
        assert not any("syntax" in e.lower() for e in errors)

    def test_connection_missing_type(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "connections": {"vm": {}}},
        )
        assert any("type" in e for e in errors)

    def test_connection_invalid_type(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "connections": {"vm": {"type": "ftp"}}},
        )
        assert any("invalid type" in e.lower() for e in errors)

    def test_kubectl_missing_session(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "connections": {
                "k8s": {"type": "kubectl"},
            }},
        )
        assert any("session" in e for e in errors)

    def test_kubectl_session_not_defined(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "connections": {
                "k8s": {"type": "kubectl", "session": "vm"},
            }},
        )
        assert any("not defined" in e for e in errors)

    def test_kubectl_valid_session_reference(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "connections": {
                "vm": {"type": "ssh"},
                "k8s": {"type": "kubectl", "session": "vm", "namespace": "default"},
            }},
        )
        kubectl_errors = [e for e in errors if "kubectl" in e.lower() or "session" in e.lower()]
        assert kubectl_errors == []

    def test_remote_ssh_missing_hosts(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {
                "project": "test",
                "host": "remote",
                "connections": {"vm": {"type": "ssh"}},
            },
            hosts=None,
        )
        assert any("hosts.yaml" in e for e in errors)

    def test_remote_ssh_missing_credentials(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {
                "project": "test",
                "host": "remote",
                "connections": {"vm": {"type": "ssh"}},
            },
            hosts={"vm": {"host": "10.0.0.1"}},  # missing username, password
        )
        assert any("username" in e for e in errors)
        assert any("password" in e for e in errors)

    def test_remote_ssh_complete_credentials(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {
                "project": "test",
                "host": "remote",
                "connections": {"vm": {"type": "ssh"}},
            },
            hosts={"vm": {"host": "10.0.0.1", "username": "root", "password": "pw"}},
        )
        cred_errors = [e for e in errors if "username" in e or "password" in e or "host" in e.lower()]
        # Filter out the "Invalid host" type errors
        cred_errors = [e for e in cred_errors if "missing" in e.lower()]
        assert cred_errors == []

    def test_legacy_backend_mapped(self, tmp_path):
        """backend: podman should be treated as host: container."""
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "backend": "podman"},
        )
        host_errors = [e for e in errors if "Invalid host" in e]
        assert host_errors == []
