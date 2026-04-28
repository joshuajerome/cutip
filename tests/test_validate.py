"""Tests for cutip.workflow.validate — comprehensive project validation."""

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

    def test_remote_ssh_missing_hosts(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "host": "remote"},
            hosts=None,
        )
        assert any("hosts.yaml" in e for e in errors)

    def test_remote_ssh_missing_credentials(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "host": "remote"},
            hosts={"host": "10.0.0.1"},  # missing username, password
        )
        assert any("username" in e for e in errors)
        assert any("password" in e for e in errors)

    def test_remote_ssh_complete_credentials(self, tmp_path):
        errors, warnings = validate_project(
            tmp_path / "test.yaml",
            {"project": "test", "host": "remote"},
            hosts={"host": "10.0.0.1", "username": "root", "password": "pw"},
        )
        cred_errors = [e for e in errors if "missing" in e.lower() and "SSH" in e]
        assert cred_errors == []
