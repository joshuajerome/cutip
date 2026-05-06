"""Tests for cutip.globals — global data store + dotted-path lookup."""

from __future__ import annotations

import pytest

from cutip import globals as _globals


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect ~/.cutip/ to a tmp dir per-test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    yield tmp_path


# ── lookup ──────────────────────────────────────────────────────────────────


def test_lookup_simple():
    data = {"x": "hello"}
    assert _globals.lookup(data, "x") == "hello"


def test_lookup_nested():
    data = {"passwords": {"v22": "pw"}}
    assert _globals.lookup(data, "passwords.v22") == "pw"


def test_lookup_missing_returns_none():
    data = {"x": "hello"}
    assert _globals.lookup(data, "y") is None
    assert _globals.lookup(data, "x.deeper") is None


def test_lookup_returns_dict_when_path_is_intermediate():
    """Looking up an intermediate node returns the dict; caller decides."""
    data = {"passwords": {"v22": "pw"}}
    assert _globals.lookup(data, "passwords") == {"v22": "pw"}


def test_lookup_empty_path_returns_none():
    assert _globals.lookup({"x": 1}, "") is None


# ── set_dotted ──────────────────────────────────────────────────────────────


def test_set_dotted_creates_nested():
    data: dict = {}
    _globals.set_dotted(data, "passwords.v22", "pw")
    assert data == {"passwords": {"v22": "pw"}}


def test_set_dotted_extends_existing():
    data = {"passwords": {"v22": "old"}}
    _globals.set_dotted(data, "passwords.v23", "new")
    assert data == {"passwords": {"v22": "old", "v23": "new"}}


def test_set_dotted_overwrites_leaf():
    data = {"passwords": {"v22": "old"}}
    _globals.set_dotted(data, "passwords.v22", "new")
    assert data["passwords"]["v22"] == "new"


def test_set_dotted_rejects_traversal_through_scalar():
    data = {"passwords": "scalar-not-a-dict"}
    with pytest.raises(_globals.GlobalsError, match="non-mapping"):
        _globals.set_dotted(data, "passwords.v22", "pw")


def test_set_dotted_rejects_empty_path():
    with pytest.raises(_globals.GlobalsError, match="empty"):
        _globals.set_dotted({}, "", "x")


# ── remove_dotted ───────────────────────────────────────────────────────────


def test_remove_dotted_leaf_returns_value():
    data = {"passwords": {"v22": "pw", "v23": "pw2"}}
    removed = _globals.remove_dotted(data, "passwords.v22")
    assert removed == "pw"
    assert data == {"passwords": {"v23": "pw2"}}


def test_remove_dotted_cleans_up_empty_parents():
    data = {"passwords": {"v22": "pw"}}
    _globals.remove_dotted(data, "passwords.v22")
    assert data == {}


def test_remove_dotted_cleans_up_multiple_levels():
    data = {"a": {"b": {"c": {"leaf": "v"}}}}
    _globals.remove_dotted(data, "a.b.c.leaf")
    assert data == {}


def test_remove_dotted_keeps_siblings_at_parents():
    """Sibling at a higher level — only the immediate empty chain prunes."""
    data = {
        "passwords": {"v22": "pw"},
        "constants": {"url": "x"},
    }
    _globals.remove_dotted(data, "passwords.v22")
    assert data == {"constants": {"url": "x"}}


def test_remove_dotted_returns_subtree_for_intermediate():
    """Removing an intermediate path returns the dict it pointed at."""
    data = {"passwords": {"v22": "pw", "v23": "pw2"}}
    removed = _globals.remove_dotted(data, "passwords")
    assert removed == {"v22": "pw", "v23": "pw2"}
    assert data == {}


def test_remove_dotted_missing_path():
    with pytest.raises(_globals.GlobalsError, match="not found"):
        _globals.remove_dotted({"a": 1}, "b")


def test_remove_dotted_traverse_through_scalar():
    with pytest.raises(_globals.GlobalsError, match="non-mapping"):
        _globals.remove_dotted({"a": "scalar"}, "a.deeper")


def test_remove_dotted_empty_path_rejected():
    with pytest.raises(_globals.GlobalsError, match="empty"):
        _globals.remove_dotted({"x": 1}, "")


# ── flatten ─────────────────────────────────────────────────────────────────


def test_flatten_empty():
    assert _globals.flatten({}) == {}


def test_flatten_simple_scalars():
    data = {"a": "1", "b": "2"}
    assert _globals.flatten(data) == {"a": "1", "b": "2"}


def test_flatten_nested():
    data = {"passwords": {"v22": "pw1", "v23": "pw2"}}
    assert _globals.flatten(data) == {
        "passwords.v22": "pw1",
        "passwords.v23": "pw2",
    }


def test_flatten_coerces_int_float_bool():
    data = {"port": 22, "ratio": 1.5, "active": True, "off": False}
    flat = _globals.flatten(data)
    assert flat == {"port": "22", "ratio": "1.5", "active": "true", "off": "false"}


def test_flatten_skips_lists_and_none():
    data = {"a": "ok", "list": [1, 2, 3], "missing": None, "nested": {"b": "c"}}
    assert _globals.flatten(data) == {"a": "ok", "nested.b": "c"}


def test_flatten_deep_nesting():
    data = {"a": {"b": {"c": {"d": "deep"}}}}
    assert _globals.flatten(data) == {"a.b.c.d": "deep"}


# ── read / write ────────────────────────────────────────────────────────────


def test_read_missing_returns_empty(tmp_path):
    assert _globals.read_globals(tmp_path / "nope.yaml") == {}


def test_write_then_read_roundtrip(tmp_path):
    p = tmp_path / "data.yaml"
    payload = {"passwords": {"v22": "pw"}, "url": "http://x"}
    _globals.write_globals(payload, p)
    assert _globals.read_globals(p) == payload


def test_globals_path_default(isolated_home):
    expected = isolated_home / ".cutip" / "data.yaml"
    assert _globals.globals_path() == expected


def test_default_globals_path_ignores_override(isolated_home, tmp_path):
    # default_globals_path() is the unconfigurable default and must not
    # be affected by a config-yaml override.
    _globals.set_globals_path(tmp_path / "elsewhere.yaml")
    assert _globals.default_globals_path() == isolated_home / ".cutip" / "data.yaml"


def test_set_globals_path_overrides_default(isolated_home, tmp_path):
    custom = tmp_path / "custom-data.yaml"
    _globals.set_globals_path(custom)
    assert _globals.globals_path() == custom


def test_set_globals_path_persists_in_config_yaml(isolated_home, tmp_path):
    import yaml

    from cutip.hosts import config_path

    custom = tmp_path / "team-data.yaml"
    _globals.set_globals_path(custom)
    cfg = yaml.safe_load(config_path().read_text()) or {}
    assert cfg.get("data_path") == str(custom)


def test_set_globals_path_preserves_other_config_keys(isolated_home, tmp_path):
    import yaml

    from cutip.hosts import config_path, set_global_hosts_path

    set_global_hosts_path(tmp_path / "h.yaml")
    _globals.set_globals_path(tmp_path / "d.yaml")
    cfg = yaml.safe_load(config_path().read_text()) or {}
    assert cfg.get("hosts_path") == str(tmp_path / "h.yaml")
    assert cfg.get("data_path") == str(tmp_path / "d.yaml")


def test_globals_path_falls_back_when_config_unreadable(isolated_home, tmp_path):
    # A malformed config.yaml shouldn't break globals_path() resolution.
    from cutip.hosts import config_path

    config_path().write_text("not: valid: yaml: at: all: : :")
    # Resolution falls back silently to the default location.
    assert _globals.globals_path() == isolated_home / ".cutip" / "data.yaml"


def test_globals_path_expands_user_in_override(isolated_home):
    _globals.set_globals_path("~/custom/data.yaml")
    assert _globals.globals_path() == isolated_home / "custom" / "data.yaml"
