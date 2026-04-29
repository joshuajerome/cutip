"""Tests for cutip.paths — typed paths section expansion + merge."""

from __future__ import annotations

from cutip.paths import _looks_absolute, expand_path, merge_paths_into_data


# ── _looks_absolute ─────────────────────────────────────────────────────────


def test_looks_absolute_unix():
    assert _looks_absolute("/usr/local") is True


def test_looks_absolute_home():
    assert _looks_absolute("~/dev") is True


def test_looks_absolute_windows_drive():
    assert _looks_absolute("C:/Users") is True
    assert _looks_absolute("C:\\Users") is True


def test_looks_absolute_relative():
    assert _looks_absolute("./foo") is False
    assert _looks_absolute("foo/bar") is False
    assert _looks_absolute("") is False


# ── expand_path ─────────────────────────────────────────────────────────────


def test_expand_path_absolute_passthrough(tmp_path):
    abs_path = "/tmp/cutip-x"
    assert expand_path(abs_path, tmp_path) == abs_path


def test_expand_path_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert expand_path("~/proj", tmp_path) == str(tmp_path / "proj")


def test_expand_path_envvar(monkeypatch, tmp_path):
    monkeypatch.setenv("CUTIP_TEST_DIR", "/opt/cutip-test")
    assert expand_path("$CUTIP_TEST_DIR/sub", tmp_path) == "/opt/cutip-test/sub"


def test_expand_path_relative(tmp_path):
    base = tmp_path / "proj"
    base.mkdir()
    result = expand_path("./build", base)
    assert result == str((base / "build").resolve())


def test_expand_path_empty(tmp_path):
    assert expand_path("", tmp_path) == ""


def test_expand_path_non_string(tmp_path):
    assert expand_path(None, tmp_path) is None  # type: ignore[arg-type]


# ── merge_paths_into_data ───────────────────────────────────────────────────


def test_merge_paths_creates_data(tmp_path):
    project = tmp_path / "p.yaml"
    project.write_text("")
    config = {"paths": {"build": "/tmp/build"}}
    merge_paths_into_data(config, project)
    assert config["data"] == {"build": "/tmp/build"}


def test_merge_paths_extends_existing_data(tmp_path):
    project = tmp_path / "p.yaml"
    project.write_text("")
    config = {
        "data": {"force_clean": False},
        "paths": {"build": "/tmp/build"},
    }
    merge_paths_into_data(config, project)
    assert config["data"] == {"force_clean": False, "build": "/tmp/build"}


def test_merge_paths_resolves_relative(tmp_path):
    project = tmp_path / "proj.yaml"
    project.write_text("")
    config = {"paths": {"work": "./build"}}
    merge_paths_into_data(config, project)
    assert config["data"]["work"] == str((tmp_path / "build").resolve())


def test_merge_paths_no_paths_section(tmp_path):
    project = tmp_path / "p.yaml"
    project.write_text("")
    config = {"data": {"x": 1}}
    merge_paths_into_data(config, project)
    assert config["data"] == {"x": 1}


def test_merge_paths_paths_overrides_data(tmp_path):
    """paths win over data on key collision (paths are typed + validated)."""
    project = tmp_path / "p.yaml"
    project.write_text("")
    config = {
        "data": {"build": "/old"},
        "paths": {"build": "/new"},
    }
    merge_paths_into_data(config, project)
    assert config["data"]["build"] == "/new"


def test_merge_paths_non_mapping_paths(tmp_path):
    """Garbage paths section is ignored (validator catches the type error)."""
    project = tmp_path / "p.yaml"
    project.write_text("")
    config = {"paths": "not a dict", "data": {"x": 1}}
    merge_paths_into_data(config, project)
    assert config["data"] == {"x": 1}


def test_merge_paths_non_string_value_passthrough(tmp_path):
    """Non-string values pass through; validator flags them."""
    project = tmp_path / "p.yaml"
    project.write_text("")
    config = {"paths": {"build": 42}}
    merge_paths_into_data(config, project)
    assert config["data"]["build"] == 42
