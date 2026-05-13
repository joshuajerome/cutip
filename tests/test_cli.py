"""Tests for cutip.cli — CLI command execution."""

import json
import subprocess
import sys


def _run_cutip(*args, cwd=None):
    """Run cutip CLI via python -m and return result."""
    result = subprocess.run(
        [sys.executable, "-m", "cutip", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result


class TestCLIHelp:
    def test_help(self):
        r = _run_cutip("--help")
        assert r.returncode == 0
        assert "cutip" in r.stdout
        assert "Commands" in r.stdout

    def test_version(self):
        r = _run_cutip("--version")
        assert r.returncode == 0
        assert "cutip v" in r.stdout

    def test_unknown_command(self):
        r = _run_cutip("nonexistent")
        assert r.returncode == 1
        assert "Unknown command" in r.stdout


class TestCLIInit:
    def test_init_creates_files(self, tmp_path):
        r = _run_cutip("init", "myapp", cwd=str(tmp_path))
        assert r.returncode == 0
        assert (tmp_path / "myapp.yaml").exists()
        assert (tmp_path / "myapp.workflow.py").exists()
        assert (tmp_path / ".gitignore").exists()

    def test_init_yaml_has_project_field(self, tmp_path):
        _run_cutip("init", "myapp", cwd=str(tmp_path))
        content = (tmp_path / "myapp.yaml").read_text()
        assert "project: myapp" in content
        assert "host: local" in content

    def test_init_workflow_has_decorators(self, tmp_path):
        _run_cutip("init", "myapp", cwd=str(tmp_path))
        content = (tmp_path / "myapp.workflow.py").read_text()
        assert "@orchestrator" in content
        assert "@action" in content
        assert "stage(" in content

    def test_init_duplicate_fails(self, tmp_path):
        _run_cutip("init", "myapp", cwd=str(tmp_path))
        r = _run_cutip("init", "myapp", cwd=str(tmp_path))
        assert r.returncode == 1
        assert "already exists" in r.stdout

    def test_init_gitignore_entries(self, tmp_path):
        _run_cutip("init", "myapp", cwd=str(tmp_path))
        content = (tmp_path / ".gitignore").read_text()
        assert "hosts.yaml" in content
        assert ".cutip/" in content


class TestCLIValidate:
    def test_validate_good_project(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("validate", str(project_file))
        assert r.returncode == 0
        assert "Validation passed" in r.stdout

    def test_validate_json(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("validate", str(project_file), "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["project"] == "test-project"

    def test_validate_missing_file(self):
        r = _run_cutip("validate", "nonexistent.yaml")
        assert r.returncode == 1


class TestCLIPlan:
    def test_plan_shows_actions(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("plan", str(project_file))
        assert r.returncode == 0
        assert "execution plan" in r.stdout
        assert "Hello" in r.stdout

    def test_plan_shows_stage(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("plan", str(project_file))
        assert "Test" in r.stdout


class TestCLIRun:
    def test_run_executes_workflow(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("run", str(project_file))
        assert r.returncode == 0
        assert "complete" in r.stdout

    def test_run_creates_log(self, simple_project):
        project_file, _ = simple_project
        _run_cutip("run", str(project_file))
        log_dir = project_file.parent / ".cutip" / "logs"
        assert log_dir.exists()
        logs = list(log_dir.glob("*.log"))
        assert len(logs) >= 1

    def test_run_validation_failure(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("project: bad\nhost: invalid\n")
        r = _run_cutip("run", str(bad))
        assert r.returncode == 1
        assert "Validation failed" in r.stdout

    def test_run_auto_discover(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("run", cwd=str(project_file.parent))
        # Should find the single *.yaml project
        assert r.returncode == 0 or "Available projects" in r.stdout


class TestCLITree:
    def test_tree_output(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("tree", str(project_file))
        assert r.returncode == 0
        assert "test-project" in r.stdout

    def test_tree_json(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("tree", str(project_file), "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["project"] == "test-project"


class TestCLIProjects:
    def _make_project(self, dirpath, name, host="local", description=None):
        dirpath.mkdir(parents=True, exist_ok=True)
        yaml_path = dirpath / f"{name}.yaml"
        body = ""
        if description:
            body += f"# {description}\n"
        body += f"project: {name}\nhost: {host}\nworkflow: {name}.workflow.py\n"
        yaml_path.write_text(body)
        return yaml_path

    def test_projects_discovers_single(self, tmp_path):
        self._make_project(tmp_path / "alpha", "alpha", description="Alpha project")
        r = _run_cutip("projects", cwd=str(tmp_path))
        assert r.returncode == 0
        assert "alpha" in r.stdout
        assert "Alpha project" in r.stdout

    def test_projects_discovers_nested(self, tmp_path):
        self._make_project(tmp_path / "workspaces" / "a", "a-proj", host="local")
        self._make_project(tmp_path / "workspaces" / "b", "b-proj", host="container")
        self._make_project(tmp_path / "misc" / "c", "c-proj", host="remote")
        r = _run_cutip("projects", cwd=str(tmp_path))
        assert r.returncode == 0
        assert "a-proj" in r.stdout
        assert "b-proj" in r.stdout
        assert "c-proj" in r.stdout

    def test_projects_skips_non_project_yamls(self, tmp_path):
        self._make_project(tmp_path, "real-proj")
        # hosts.yaml shape — no project key
        (tmp_path / "hosts.yaml").write_text("vm:\n  host: 1.2.3.4\n  username: root\n")
        # arbitrary non-project yaml
        (tmp_path / "data.yaml").write_text("some_key: some_value\n")
        r = _run_cutip("projects", cwd=str(tmp_path))
        assert r.returncode == 0
        assert "real-proj" in r.stdout
        assert "hosts.yaml" not in r.stdout
        assert "data.yaml" not in r.stdout

    def test_projects_empty_dir(self, tmp_path):
        r = _run_cutip("projects", cwd=str(tmp_path))
        assert r.returncode == 0
        assert "No cutip projects" in r.stdout

    def test_projects_json(self, tmp_path):
        self._make_project(tmp_path / "x", "xproj", host="remote", description="X desc")
        r = _run_cutip("projects", "--json", cwd=str(tmp_path))
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert len(data) == 1
        assert data[0]["project"] == "xproj"
        assert data[0]["host"] == "remote"
        assert data[0]["description"] == "X desc"

    def test_projects_skips_build_dirs(self, tmp_path):
        # Hidden / build dirs should be skipped even with valid project yaml.
        self._make_project(tmp_path / ".venv" / "foo", "venv-proj")
        self._make_project(tmp_path / "node_modules" / "bar", "node-proj")
        self._make_project(tmp_path / "real", "real-proj")
        r = _run_cutip("projects", cwd=str(tmp_path))
        assert r.returncode == 0
        assert "real-proj" in r.stdout
        assert "venv-proj" not in r.stdout
        assert "node-proj" not in r.stdout


class TestCLIValidateUnresolvedGlobals:
    """`cutip validate` should fail when {{ globals.X.Y.Z }} doesn't bind."""

    def _make_project(self, dirpath, body, workflow="pass\n"):
        dirpath.mkdir(parents=True, exist_ok=True)
        (dirpath / "p.yaml").write_text(body)
        (dirpath / "p.workflow.py").write_text(workflow)
        return dirpath / "p.yaml"

    def test_validate_fails_on_unresolved_global(self, tmp_path):
        # Point HOME at tmp so the global ~/.cutip/data.yaml is empty.
        import os

        env_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp_path)
        try:
            self._make_project(
                tmp_path / "proj",
                "project: p\nhost: local\n"
                'data:\n  password: "{{ globals.sfm.passwords.cli }}"\n',
            )
            r = _run_cutip(
                "validate",
                str(tmp_path / "proj" / "p.yaml"),
                cwd=str(tmp_path / "proj"),
            )
        finally:
            if env_home:
                os.environ["HOME"] = env_home
        assert r.returncode != 0
        assert "unresolved" in r.stdout.lower() or "unresolved" in r.stderr.lower()
        assert "sfm.passwords.cli" in r.stdout or "sfm.passwords.cli" in r.stderr

    def test_validate_passes_when_globals_resolve(self, tmp_path):
        import os

        # Plant a populated global data file in HOME/.cutip/
        cutip_dir = tmp_path / ".cutip"
        cutip_dir.mkdir()
        (cutip_dir / "data.yaml").write_text(
            "sfm:\n  passwords:\n    cli: Dell@force10\n"
        )
        env_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp_path)
        try:
            self._make_project(
                tmp_path / "proj",
                "project: p\nhost: local\n"
                'data:\n  password: "{{ globals.sfm.passwords.cli }}"\n',
            )
            r = _run_cutip(
                "validate",
                str(tmp_path / "proj" / "p.yaml"),
                cwd=str(tmp_path / "proj"),
            )
        finally:
            if env_home:
                os.environ["HOME"] = env_home
        assert r.returncode == 0
        assert "unresolved" not in r.stdout.lower()


class TestCLIDataUsages:
    """Test `cutip data usages <key>` and `cutip data unused`.

    Both walk the cwd tree and grep yaml files; they don't touch
    ~/.cutip/data.yaml read state beyond `unused` checking which keys
    are defined there. We don't mutate the user's real ~/.cutip/data.yaml
    in tests — instead, point CUTIP_DATA_PATH-equivalent at tmp via the
    `cutip data set-path` CLI (which writes ~/.cutip/config.yaml).
    """

    def _make_project(self, dirpath, name, body):
        dirpath.mkdir(parents=True, exist_ok=True)
        yaml_path = dirpath / f"{name}.yaml"
        yaml_path.write_text(body)
        return yaml_path

    def test_usages_finds_references(self, tmp_path):
        self._make_project(
            tmp_path / "a",
            "a-proj",
            "project: a-proj\nhost: local\n"
            'data:\n  pw: "{{ globals.sfm.passwords.cli }}"\n',
        )
        self._make_project(
            tmp_path / "b",
            "b-proj",
            'project: b-proj\nhost: local\ndata:\n  ip: "{{ globals.sfm.ips.gui }}"\n',
        )
        r = _run_cutip("data", "usages", "sfm.passwords.cli", cwd=str(tmp_path))
        assert r.returncode == 0
        assert "a-proj.yaml" in r.stdout or "a/a-proj.yaml" in r.stdout
        # b-proj references a different key — must not appear
        assert "b-proj.yaml" not in r.stdout

    def test_usages_whitespace_tolerant(self, tmp_path):
        self._make_project(
            tmp_path / "p",
            "p",
            "project: p\nhost: local\n"
            "data:\n"
            '  a: "{{globals.foo.bar}}"\n'  # no spaces
            '  b: "{{ globals.foo.bar }}"\n'  # spaces
            '  c: "{{  globals.foo.bar  }}"\n',  # extra spaces
        )
        r = _run_cutip("data", "usages", "foo.bar", cwd=str(tmp_path))
        assert r.returncode == 0
        # all three lines should be picked up
        assert r.stdout.count("globals.foo.bar") >= 3

    def test_usages_no_matches(self, tmp_path):
        self._make_project(
            tmp_path / "p",
            "p",
            "project: p\nhost: local\ndata: {}\n",
        )
        r = _run_cutip("data", "usages", "nothing.here", cwd=str(tmp_path))
        assert r.returncode == 0
        assert "No references" in r.stdout

    def test_usages_skips_build_dirs(self, tmp_path):
        # Reference inside a skip-dir must NOT be matched
        self._make_project(
            tmp_path / "node_modules" / "pkg",
            "noise",
            'project: noise\nhost: local\ndata:\n  x: "{{ globals.foo.bar }}"\n',
        )
        # Reference outside should be picked up
        self._make_project(
            tmp_path / "real",
            "real",
            'project: real\nhost: local\ndata:\n  x: "{{ globals.foo.bar }}"\n',
        )
        r = _run_cutip("data", "usages", "foo.bar", cwd=str(tmp_path))
        assert r.returncode == 0
        assert "real.yaml" in r.stdout
        assert "noise.yaml" not in r.stdout

    def test_usages_requires_key(self, tmp_path):
        r = _run_cutip("data", "usages", cwd=str(tmp_path))
        assert r.returncode != 0


class TestCLIShow:
    def test_show_summary(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("show", str(project_file))
        assert r.returncode == 0
        assert "Steps" in r.stdout

    def test_show_workflow(self, simple_project):
        project_file, _ = simple_project
        r = _run_cutip("show", str(project_file), "workflow")
        assert r.returncode == 0
        assert "Hello" in r.stdout


class TestCLIVerify:
    def test_verify(self):
        r = _run_cutip("verify")
        assert r.returncode == 0
        assert "Python" in r.stdout
        assert "cutip core" in r.stdout
