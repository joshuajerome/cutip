"""Tests for cutip.workflow.cli_args — workflow-declared CLI argument parsing.

The full ``cutip run`` integration goes through cli.py and gets exercised
by snf-dev workflows in CI; here we cover the pure-logic unit:
spec normalization, runtime parsing, type coercion, and help rendering.
"""

from __future__ import annotations

import pytest

from cutip.workflow import cli_args as ca


# ── normalize_specs ──────────────────────────────────────────────────────────


def test_normalize_minimal():
    specs = ca.normalize_specs({"sheet_path": {}})
    s = specs["sheet_path"]
    assert s["short"] is None
    assert s["long"] == "--sheet-path"
    assert s["type"] == "str"
    assert s["required"] is False
    assert s["default"] is None
    assert s["help"] == ""


def test_normalize_full_spec():
    specs = ca.normalize_specs(
        {
            "sheet_path": {
                "short": "-f",
                "long": "--sheet",
                "type": "path",
                "required": True,
                "help": "Input xlsx",
            }
        }
    )
    s = specs["sheet_path"]
    assert s["short"] == "-f"
    assert s["long"] == "--sheet"
    assert s["type"] == "path"
    assert s["required"] is True
    assert s["help"] == "Input xlsx"


def test_normalize_kebabs_var_name_for_default_long():
    # snake_case var → kebab-case --long
    specs = ca.normalize_specs({"pod_namespace": {}})
    assert specs["pod_namespace"]["long"] == "--pod-namespace"


def test_normalize_none_block_returns_empty():
    assert ca.normalize_specs(None) == {}
    assert ca.normalize_specs({}) == {}


def test_normalize_rejects_non_mapping_block():
    with pytest.raises(ca.CliArgsError):
        ca.normalize_specs([1, 2, 3])


def test_normalize_rejects_invalid_type():
    with pytest.raises(ca.CliArgsError, match="type"):
        ca.normalize_specs({"x": {"type": "frobnicator"}})


def test_normalize_rejects_bad_short_flag():
    with pytest.raises(ca.CliArgsError, match="short"):
        ca.normalize_specs({"x": {"short": "-foo"}})  # >2 chars


def test_normalize_rejects_bad_long_flag():
    with pytest.raises(ca.CliArgsError, match="long"):
        ca.normalize_specs({"x": {"long": "noprefix"}})


def test_normalize_rejects_reserved_flag_collision():
    with pytest.raises(ca.CliArgsError, match="reserved"):
        ca.normalize_specs({"x": {"long": "--bg"}})


def test_normalize_rejects_duplicate_flag_across_args():
    with pytest.raises(ca.CliArgsError, match="declared by both"):
        ca.normalize_specs(
            {
                "first": {"short": "-f"},
                "second": {"short": "-f"},
            }
        )


# ── parse_runtime ────────────────────────────────────────────────────────────


def test_parse_short_flag_with_value():
    specs = ca.normalize_specs({"sheet": {"short": "-f"}})
    values, defaults, leftover = ca.parse_runtime(specs, ["-f", "sheets/foo.xlsx"])
    assert values == {"sheet": "sheets/foo.xlsx"}
    assert leftover == []


def test_parse_long_flag_with_value():
    specs = ca.normalize_specs({"sheet": {"long": "--sheet"}})
    values, defaults, leftover = ca.parse_runtime(specs, ["--sheet", "sheets/foo.xlsx"])
    assert values == {"sheet": "sheets/foo.xlsx"}
    assert leftover == []


def test_parse_long_eq_value():
    specs = ca.normalize_specs({"sheet": {"long": "--sheet"}})
    values, _d, _ = ca.parse_runtime(specs, ["--sheet=sheets/foo.xlsx"])
    assert values == {"sheet": "sheets/foo.xlsx"}


def test_parse_int_coercion():
    specs = ca.normalize_specs({"port": {"type": "int"}})
    values, _d, _ = ca.parse_runtime(specs, ["--port", "8080"])
    assert values == {"port": 8080}


def test_parse_int_coercion_failure():
    specs = ca.normalize_specs({"port": {"type": "int"}})
    with pytest.raises(ca.CliArgsError, match="expected int"):
        ca.parse_runtime(specs, ["--port", "abc"])


def test_parse_bool_with_value():
    specs = ca.normalize_specs({"flag": {"type": "bool"}})
    values, _d, _ = ca.parse_runtime(specs, ["--flag", "true"])
    assert values == {"flag": True}
    values, _d, _ = ca.parse_runtime(specs, ["--flag", "no"])
    assert values == {"flag": False}


def test_parse_bool_bare_flag_implies_true():
    specs = ca.normalize_specs({"flag": {"type": "bool"}})
    values, _d, _ = ca.parse_runtime(specs, ["--flag"])
    assert values == {"flag": True}


def test_parse_path_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    specs = ca.normalize_specs({"out": {"type": "path"}})
    values, _d, _ = ca.parse_runtime(specs, ["--out", "~/data/foo.xlsx"])
    assert values["out"] == str(tmp_path / "data" / "foo.xlsx")


def test_parse_default_returned_separately_when_unset():
    """Defaults aren't mingled with user values — caller chooses precedence."""
    specs = ca.normalize_specs({"namespace": {"default": "sfm-1"}})
    user_values, defaults, _ = ca.parse_runtime(specs, [])
    assert user_values == {}
    assert defaults == {"namespace": "sfm-1"}


def test_parse_user_value_takes_precedence_over_default():
    specs = ca.normalize_specs({"namespace": {"default": "sfm-1"}})
    user_values, defaults, _ = ca.parse_runtime(specs, ["--namespace", "sfm-2"])
    assert user_values == {"namespace": "sfm-2"}
    # No default returned — user provided a value, default doesn't apply.
    assert defaults == {}


def test_parse_required_missing_raises():
    specs = ca.normalize_specs({"sheet": {"short": "-f", "required": True}})
    with pytest.raises(ca.CliArgsError, match="required"):
        ca.parse_runtime(specs, [])


def test_parse_unrecognized_tokens_become_leftover():
    specs = ca.normalize_specs({"sheet": {"short": "-f"}})
    values, defaults, leftover = ca.parse_runtime(
        specs, ["-f", "sheets/foo.xlsx", "--unknown", "blah"]
    )
    assert values == {"sheet": "sheets/foo.xlsx"}
    assert leftover == ["--unknown", "blah"]


def test_parse_value_missing_raises():
    specs = ca.normalize_specs({"sheet": {"long": "--sheet"}})
    with pytest.raises(ca.CliArgsError, match="missing value"):
        ca.parse_runtime(specs, ["--sheet"])  # no value follows


# ── help_text ────────────────────────────────────────────────────────────────


def test_help_text_renders_flags_and_metadata():
    specs = ca.normalize_specs(
        {
            "sheet": {
                "short": "-f",
                "long": "--sheet",
                "type": "path",
                "required": True,
                "help": "Input xlsx",
            },
            "namespace": {
                "long": "--namespace",
                "default": "sfm-1",
                "help": "K8s ns",
            },
        }
    )
    out = ca.help_text(specs)
    assert "-f" in out
    assert "--sheet" in out
    assert "path" in out
    assert "required" in out
    assert "Input xlsx" in out
    assert "default='sfm-1'" in out


def test_help_text_empty_for_no_specs():
    assert ca.help_text({}) == ""
