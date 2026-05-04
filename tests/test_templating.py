"""Tests for cutip.templating — engine-level substitution helpers."""

from __future__ import annotations


from cutip.templating import (
    _substitute_string,
    resolve_substitution_maps,
    substitute_in_obj,
)


# ── _substitute_string ──────────────────────────────────────────────────────


def test_substitute_string_no_template_passthrough():
    assert _substitute_string("plain text", {}, {}, {}, {}) == "plain text"


def test_substitute_string_vars():
    assert (
        _substitute_string("hi {{ vars.name }}", {"name": "alice"}, {}, {}, {})
        == "hi alice"
    )


def test_substitute_string_paths():
    assert (
        _substitute_string("src: {{ paths.repo }}", {}, {"repo": "/x"}, {}, {})
        == "src: /x"
    )


def test_substitute_string_secrets():
    assert (
        _substitute_string("token={{ secrets.t }}", {}, {}, {"t": "abc"}, {})
        == "token=abc"
    )


def test_substitute_string_globals_dotted():
    assert (
        _substitute_string(
            "pw={{ globals.passwords.v22 }}", {}, {}, {}, {"passwords.v22": "P!"}
        )
        == "pw=P!"
    )


def test_substitute_string_unspaced_form():
    assert _substitute_string("{{vars.x}}", {"x": "Y"}, {}, {}, {}) == "Y"


def test_substitute_string_idempotent_after_resolve():
    """Re-running on already-resolved text is a no-op."""
    once = _substitute_string("{{ vars.x }}", {"x": "alice"}, {}, {}, {})
    twice = _substitute_string(once, {"x": "alice"}, {}, {}, {})
    assert once == twice == "alice"


def test_substitute_string_unknown_placeholder_left_alone():
    assert (
        _substitute_string("{{ vars.unknown }}", {"x": "y"}, {}, {}, {})
        == "{{ vars.unknown }}"
    )


def test_substitute_string_all_four_namespaces():
    out = _substitute_string(
        "{{ vars.a }}|{{ paths.b }}|{{ secrets.c }}|{{ globals.d.e }}",
        {"a": "A"},
        {"b": "B"},
        {"c": "C"},
        {"d.e": "D"},
    )
    assert out == "A|B|C|D"


# ── substitute_in_obj ───────────────────────────────────────────────────────


def test_substitute_in_obj_string():
    assert substitute_in_obj("{{ vars.x }}", vars={"x": "v"}) == "v"


def test_substitute_in_obj_passthrough_non_strings():
    assert substitute_in_obj(42, vars={"x": "v"}) == 42
    assert substitute_in_obj(True, vars={"x": "v"}) is True
    assert substitute_in_obj(None, vars={"x": "v"}) is None


def test_substitute_in_obj_dict_recurses():
    obj = {"name": "{{ vars.name }}", "extra": {"deeper": "{{ vars.x }}"}}
    out = substitute_in_obj(obj, vars={"name": "alice", "x": "Y"})
    assert out == {"name": "alice", "extra": {"deeper": "Y"}}


def test_substitute_in_obj_list_recurses():
    obj = ["{{ vars.a }}", {"k": "{{ vars.b }}"}, 42]
    out = substitute_in_obj(obj, vars={"a": "A", "b": "B"})
    assert out == ["A", {"k": "B"}, 42]


def test_substitute_in_obj_does_not_mutate_input():
    original = {"a": "{{ vars.x }}"}
    substitute_in_obj(original, vars={"x": "Y"})
    assert original == {"a": "{{ vars.x }}"}


def test_substitute_in_obj_no_kwargs_passes_through():
    obj = {"a": "{{ vars.x }}", "b": 1}
    out = substitute_in_obj(obj)
    assert out == obj


# ── resolve_substitution_maps ───────────────────────────────────────────────


def test_resolve_substitution_maps_resolves_globals_in_vars():
    config = {"vars": {"greeting": "hi {{ globals.user }}"}}
    v, p, s = resolve_substitution_maps(config, {"user": "alice"})
    assert v == {"greeting": "hi alice"}
    assert p == {}
    assert s == {}


def test_resolve_substitution_maps_resolves_globals_in_paths():
    config = {"paths": {"repo": "{{ globals.home }}/proj"}}
    _, p, _ = resolve_substitution_maps(config, {"home": "/home/u"})
    assert p == {"repo": "/home/u/proj"}


def test_resolve_substitution_maps_resolves_globals_in_secrets():
    config = {"secrets": {"db_pw": "{{ globals.passwords.db }}"}}
    _, _, s = resolve_substitution_maps(config, {"passwords.db": "secret"})
    assert s == {"db_pw": "secret"}


def test_resolve_substitution_maps_coerces_non_strings():
    """A var like `port: 22` (int) becomes string '22'."""
    config = {"vars": {"port": 22}}
    v, _, _ = resolve_substitution_maps(config, {})
    assert v == {"port": "22"}


def test_resolve_substitution_maps_empty_config():
    v, p, s = resolve_substitution_maps({}, {})
    assert v == {} and p == {} and s == {}


# ── Integration: end-to-end shape ──────────────────────────────────────────


def test_end_to_end_globals_then_config():
    """Globals → vars/paths/secrets → rest of config."""
    config = {
        "vars": {"name": "{{ globals.user }}"},
        "paths": {"repo": "{{ globals.home }}/code"},
        "data": {
            "greeting": "hello {{ vars.name }} at {{ paths.repo }}",
            "list": ["{{ globals.user }}", "{{ vars.name }}"],
        },
    }
    globals_flat = {"user": "alice", "home": "/home/alice"}

    v, p, s = resolve_substitution_maps(config, globals_flat)
    out = substitute_in_obj(config, vars=v, paths=p, secrets=s, globals=globals_flat)

    assert out["vars"]["name"] == "alice"
    assert out["paths"]["repo"] == "/home/alice/code"
    assert out["data"]["greeting"] == "hello alice at /home/alice/code"
    assert out["data"]["list"] == ["alice", "alice"]


def test_end_to_end_hosts_yaml_shape():
    """Hosts entries can pull credentials from globals while keeping a
    per-project IP."""
    resolved_hosts = {
        "sfm": {
            "host": "100.94.115.88",
            "username": "{{ globals.sfm.cred.username }}",
            "password": "{{ globals.sfm.cred.password }}",
        }
    }
    globals_flat = {"sfm.cred.username": "root", "sfm.cred.password": "Dell@force10"}
    out = substitute_in_obj(resolved_hosts, globals=globals_flat)
    assert out == {
        "sfm": {
            "host": "100.94.115.88",
            "username": "root",
            "password": "Dell@force10",
        }
    }
