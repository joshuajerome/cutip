"""Tests for cutip.collection — collection-tier discovery + data.

Covers the foundation pieces: walking up to find ``cutip.collection.yaml``,
reading manifest / data / hosts files, flattening data for substitution,
and the integration with ``substitute_in_obj``.
"""

from __future__ import annotations


from cutip import collection as _collection
from cutip.templating import _substitute_string, substitute_in_obj


# ── find_collection_root ────────────────────────────────────────────────────


def test_find_root_from_marker_dir(tmp_path):
    (tmp_path / "cutip.collection.yaml").write_text("name: x\n")
    root = _collection.find_collection_root(tmp_path)
    assert root == tmp_path.resolve()


def test_find_root_from_nested_project(tmp_path):
    (tmp_path / "cutip.collection.yaml").write_text("name: x\n")
    nested = tmp_path / "workspaces" / "foo"
    nested.mkdir(parents=True)
    proj = nested / "p.yaml"
    proj.write_text("project: p\nhost: local\n")
    root = _collection.find_collection_root(proj)
    assert root == tmp_path.resolve()


def test_find_root_from_directory_path(tmp_path):
    (tmp_path / "cutip.collection.yaml").write_text("name: x\n")
    nested = tmp_path / "workspaces" / "foo"
    nested.mkdir(parents=True)
    root = _collection.find_collection_root(nested)
    assert root == tmp_path.resolve()


def test_no_collection_returns_none(tmp_path):
    (tmp_path / "p.yaml").write_text("project: p\n")
    assert _collection.find_collection_root(tmp_path / "p.yaml") is None
    assert _collection.find_collection_root(tmp_path) is None


def test_first_ancestor_wins(tmp_path):
    """If outer + inner both have manifests, the inner one wins."""
    (tmp_path / "cutip.collection.yaml").write_text("name: outer\n")
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "cutip.collection.yaml").write_text("name: inner\n")
    proj = inner / "p.yaml"
    proj.write_text("project: p\n")
    root = _collection.find_collection_root(proj)
    assert root == inner.resolve()


# ── Manifest / data / hosts read+write ──────────────────────────────────────


def test_read_manifest_missing(tmp_path):
    assert _collection.read_manifest(tmp_path) == {}


def test_write_then_read_manifest(tmp_path):
    data = {"name": "x", "projects": [{"path": "a/b.yaml"}]}
    _collection.write_manifest(tmp_path, data)
    assert _collection.read_manifest(tmp_path) == data


def test_read_data_missing(tmp_path):
    assert _collection.read_data(tmp_path) == {}


def test_write_then_read_data(tmp_path):
    data = {"sfm": {"passwords": {"cli": "pw"}}}
    _collection.write_data(tmp_path, data)
    assert _collection.read_data(tmp_path) == data


def test_data_path_layout(tmp_path):
    assert _collection.data_path(tmp_path) == tmp_path / ".cutip" / "data.yaml"
    assert _collection.hosts_path(tmp_path) == tmp_path / ".cutip" / "hosts.yaml"


def test_write_data_creates_cutip_dir(tmp_path):
    _collection.write_data(tmp_path, {"k": "v"})
    assert (tmp_path / ".cutip" / "data.yaml").exists()


def test_read_hosts_missing(tmp_path):
    assert _collection.read_hosts(tmp_path) == {}


def test_write_then_read_hosts(tmp_path):
    data = {"vm": {"host": "10.0.0.1", "username": "u"}}
    _collection.write_hosts(tmp_path, data)
    assert _collection.read_hosts(tmp_path) == data


# ── flatten ─────────────────────────────────────────────────────────────────


def test_flatten_flat():
    assert _collection.flatten({"a": "b"}) == {"a": "b"}


def test_flatten_nested():
    flat = _collection.flatten({"sfm": {"passwords": {"cli": "pw"}}})
    assert flat == {"sfm.passwords.cli": "pw"}


def test_flatten_coerces_types():
    flat = _collection.flatten({"port": 22, "enabled": True, "ratio": 0.5})
    assert flat == {"port": "22", "enabled": "true", "ratio": "0.5"}


def test_flatten_skips_lists_and_none():
    flat = _collection.flatten({"a": "b", "lst": [1, 2], "n": None})
    assert flat == {"a": "b"}


# ── load_for_project ────────────────────────────────────────────────────────


def test_load_for_project_no_collection(tmp_path):
    (tmp_path / "p.yaml").write_text("project: p\n")
    root, flat = _collection.load_for_project(tmp_path / "p.yaml")
    assert root is None
    assert flat == {}


def test_load_for_project_with_collection(tmp_path):
    (tmp_path / "cutip.collection.yaml").write_text("name: x\n")
    (tmp_path / ".cutip").mkdir()
    (tmp_path / ".cutip" / "data.yaml").write_text("sfm:\n  passwords:\n    cli: pw\n")
    proj = tmp_path / "p.yaml"
    proj.write_text("project: p\n")
    root, flat = _collection.load_for_project(proj)
    assert root == tmp_path.resolve()
    assert flat == {"sfm.passwords.cli": "pw"}


def test_load_for_project_collection_without_data(tmp_path):
    """Collection marker exists but .cutip/data.yaml doesn't yet."""
    (tmp_path / "cutip.collection.yaml").write_text("name: x\n")
    proj = tmp_path / "p.yaml"
    proj.write_text("project: p\n")
    root, flat = _collection.load_for_project(proj)
    assert root == tmp_path.resolve()
    assert flat == {}


# ── Integration with substitute_in_obj ─────────────────────────────────────


def test_substitute_string_collection_namespace():
    out = _substitute_string(
        "pw={{ collection.sfm.passwords.cli }}",
        {},
        {},
        {},
        {},
        {"sfm.passwords.cli": "Dell@force10"},
    )
    assert out == "pw=Dell@force10"


def test_substitute_in_obj_collection_kwarg():
    obj = {"data": {"password": "{{ collection.sfm.passwords.cli }}"}}
    out = substitute_in_obj(obj, collection={"sfm.passwords.cli": "pw"})
    assert out == {"data": {"password": "pw"}}


def test_substitute_in_obj_collection_and_globals():
    """Both namespaces resolve independently — no precedence cascade."""
    obj = {
        "c": "{{ collection.x }}",
        "g": "{{ globals.y }}",
    }
    out = substitute_in_obj(
        obj,
        collection={"x": "C"},
        globals={"y": "G"},
    )
    assert out == {"c": "C", "g": "G"}


def test_collection_unresolved_left_intact():
    """Unresolved collection refs stay as the placeholder for cmd_validate to flag."""
    out = _substitute_string(
        "{{ collection.missing }}",
        {},
        {},
        {},
        {},
        {},
    )
    assert out == "{{ collection.missing }}"


def test_substitute_in_obj_collection_optional():
    """collection kwarg defaults to empty — pre-2.21 callers still work."""
    out = substitute_in_obj({"x": "{{ vars.a }}"}, vars={"a": "A"})
    assert out == {"x": "A"}
