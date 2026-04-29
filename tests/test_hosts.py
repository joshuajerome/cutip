"""Tests for cutip.hosts — local + global hosts file management."""

from __future__ import annotations

import pytest

from cutip import hosts


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect ~/.cutip/ to a tmp dir per-test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    yield tmp_path


# ── Format detection ────────────────────────────────────────────────────────


def test_is_nested_with_nested_dict():
    assert hosts.is_nested({"ub20": {"host": "h", "username": "u"}}) is True


def test_is_nested_with_flat_dict():
    assert hosts.is_nested({"host": "h", "username": "u"}) is False


def test_is_nested_with_empty_dict():
    """Empty defaults to nested (the new default format)."""
    assert hosts.is_nested({}) is True
    assert hosts.is_nested(None) is True


def test_is_nested_mixed_returns_true():
    """If any value is a dict, treat as nested."""
    assert hosts.is_nested({"ub20": {"host": "h"}, "extra": "scalar"}) is True


# ── Read / write ────────────────────────────────────────────────────────────


def test_write_then_read(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.write_hosts_file(p, {"ub20": {"host": "h", "username": "u"}})
    data = hosts.read_hosts_file(p)
    assert data == {"ub20": {"host": "h", "username": "u"}}


def test_read_missing_returns_empty(tmp_path):
    assert hosts.read_hosts_file(tmp_path / "nope.yaml") == {}


# ── Resolution ──────────────────────────────────────────────────────────────


def test_resolve_flat_wraps_as_default(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.write_hosts_file(p, {"host": "10.0.0.1", "username": "root"})
    assert hosts.resolve(p) == {
        "_default": {"host": "10.0.0.1", "username": "root"}
    }


def test_resolve_nested_passes_through(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.write_hosts_file(
        p,
        {"ub20": {"host": "h1", "username": "u1"}, "sfm": {"host": "h2"}},
    )
    resolved = hosts.resolve(p)
    assert resolved["ub20"]["host"] == "h1"
    assert resolved["sfm"]["host"] == "h2"


def test_resolve_global_reference(tmp_path, isolated_home):
    # Set up global file with a "sfm" entry
    gp = hosts.global_hosts_path()
    hosts.write_hosts_file(gp, {"sfm": {"host": "1.2.3.4", "username": "root"}})

    # Local file with global: true reference
    local = tmp_path / "local.yaml"
    hosts.write_hosts_file(local, {"sfm": {"global": True}})

    resolved = hosts.resolve(local)
    assert resolved["sfm"] == {"host": "1.2.3.4", "username": "root"}


def test_resolve_global_missing_file_errors(tmp_path):
    local = tmp_path / "local.yaml"
    hosts.write_hosts_file(local, {"sfm": {"global": True}})
    with pytest.raises(hosts.HostsError, match="global hosts file does not exist"):
        hosts.resolve(local)


def test_resolve_global_missing_entry_errors(tmp_path, isolated_home):
    gp = hosts.global_hosts_path()
    hosts.write_hosts_file(gp, {"other": {"host": "x"}})
    local = tmp_path / "local.yaml"
    hosts.write_hosts_file(local, {"sfm": {"global": True}})
    with pytest.raises(hosts.HostsError, match="not found in"):
        hosts.resolve(local)


def test_resolve_invalid_entry_errors(tmp_path):
    """Mixed file (one valid nested entry + one scalar) is detected as nested
    and the scalar entry should error."""
    local = tmp_path / "local.yaml"
    hosts.write_hosts_file(
        local,
        {"valid": {"host": "h"}, "ub20": "this should be a dict"},
    )
    with pytest.raises(hosts.HostsError, match="must be a mapping"):
        hosts.resolve(local)


# ── set_field ───────────────────────────────────────────────────────────────


def test_set_field_creates_file(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.set_field(p, "ub20", "host", "1.2.3.4")
    assert hosts.read_hosts_file(p) == {"ub20": {"host": "1.2.3.4"}}


def test_set_field_appends_to_existing_host(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.write_hosts_file(p, {"ub20": {"host": "h"}})
    hosts.set_field(p, "ub20", "username", "u")
    data = hosts.read_hosts_file(p)
    assert data == {"ub20": {"host": "h", "username": "u"}}


def test_set_field_rejects_flat_file(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.write_hosts_file(p, {"host": "h", "username": "u"})  # flat
    with pytest.raises(hosts.HostsError, match="flat \\(legacy\\) format"):
        hosts.set_field(p, "ub20", "host", "x")


# ── Migration ───────────────────────────────────────────────────────────────


def test_migrate_flat_to_nested(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.write_hosts_file(p, {"host": "h", "username": "u"})
    assert hosts.migrate(p, default_name="myhost") is True
    assert hosts.read_hosts_file(p) == {"myhost": {"host": "h", "username": "u"}}


def test_migrate_already_nested_noop(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.write_hosts_file(p, {"ub20": {"host": "h"}})
    assert hosts.migrate(p) is False


def test_migrate_empty_noop(tmp_path):
    p = tmp_path / "h.yaml"
    p.write_text("")
    assert hosts.migrate(p) is False


# ── Global path ─────────────────────────────────────────────────────────────


def test_default_global_path(isolated_home):
    expected = isolated_home / ".cutip" / "hosts.yaml"
    assert hosts.global_hosts_path() == expected


def test_set_and_get_global_path(isolated_home, tmp_path):
    custom = tmp_path / "custom-hosts.yaml"
    hosts.set_global_hosts_path(custom)
    assert hosts.global_hosts_path() == custom


def test_get_field_returns_none_for_missing(tmp_path):
    p = tmp_path / "h.yaml"
    hosts.write_hosts_file(p, {"ub20": {"host": "h"}})
    assert hosts.get_field(p, "ub20", "host") == "h"
    assert hosts.get_field(p, "ub20", "username") is None
    assert hosts.get_field(p, "nonexistent", "host") is None
