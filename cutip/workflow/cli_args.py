"""Workflow-declared CLI arguments.

A workflow's project YAML may include a ``cli_args:`` block declaring
typed flags that ``cutip run`` will accept. The declared values are
merged into ``config['vars']`` before template substitution, so any
``{{ vars.X }}`` references in the rest of the YAML pick up the
runtime override.

Schema::

    cli_args:
      sheet_path:                # populates vars.sheet_path
        short: -f                # optional short flag
        long: --sheet            # optional long flag (default: --<var-name-kebabified>)
        type: path               # str | int | float | bool | path (default: str)
        required: true           # default: false
        default: ""              # value if user doesn't pass the flag
        help: "Input xlsx"       # one-line help string

The generic ``--vars k=v [k=v ...]`` mechanism is a separate path
implemented in cli.py — it doesn't go through this module. Declared
cli_args take precedence over ``--vars`` when both name the same key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


VALID_TYPES = ("str", "int", "float", "bool", "path")

# CLI flag names cutip reserves for itself; declared cli_args may not
# claim these. Keeps the parser unambiguous.
RESERVED_FLAGS = frozenset(
    {
        "-h",
        "--help",
        "--bg",
        "--vars",
        "--hosts",
        "--path",
        "--json",
        "--all",
        "--version",
    }
)


class CliArgsError(ValueError):
    """Raised when a cli_args block is malformed or runtime args don't satisfy it."""


def _kebab(name: str) -> str:
    """``sheet_path`` → ``sheet-path`` for default --long flag."""
    return name.replace("_", "-")


def _coerce(value: str, type_: str, *, key: str, flag: str) -> Any:
    """Convert a string CLI value to the declared type."""
    if type_ == "str":
        return value
    if type_ == "int":
        try:
            return int(value)
        except ValueError:
            raise CliArgsError(f"{flag} (vars.{key}): expected int, got {value!r}")
    if type_ == "float":
        try:
            return float(value)
        except ValueError:
            raise CliArgsError(f"{flag} (vars.{key}): expected float, got {value!r}")
    if type_ == "bool":
        v = value.strip().lower()
        if v in ("true", "yes", "y", "1"):
            return True
        if v in ("false", "no", "n", "0"):
            return False
        raise CliArgsError(
            f"{flag} (vars.{key}): expected bool (true/false), got {value!r}"
        )
    if type_ == "path":
        return str(Path(value).expanduser())
    raise CliArgsError(f"unknown cli_args type {type_!r} for {key}")


def normalize_specs(cli_args_block: Any) -> dict[str, dict]:
    """Validate and normalize the raw ``cli_args:`` block from project YAML.

    Returns a dict ``{var_name: spec}`` with every spec containing:
    ``short`` (str|None), ``long`` (str), ``type`` (str), ``required`` (bool),
    ``default`` (anything|None), ``help`` (str).

    Raises CliArgsError on malformed input.
    """
    if cli_args_block is None:
        return {}
    if not isinstance(cli_args_block, dict):
        raise CliArgsError(
            f"cli_args must be a mapping of <var_name>: <spec>, got {type(cli_args_block).__name__}"
        )

    out: dict[str, dict] = {}
    flag_owners: dict[str, str] = {}  # flag → var_name (for collision detection)
    for key, raw in cli_args_block.items():
        spec = raw or {}
        if not isinstance(spec, dict):
            raise CliArgsError(
                f"cli_args.{key}: spec must be a mapping, got {type(spec).__name__}"
            )

        short = spec.get("short")
        long_ = spec.get("long") or f"--{_kebab(key)}"
        type_ = spec.get("type", "str")
        required = bool(spec.get("required", False))
        default = spec.get("default")
        help_ = spec.get("help", "")

        # Validate type
        if type_ not in VALID_TYPES:
            raise CliArgsError(
                f"cli_args.{key}.type: must be one of {VALID_TYPES}, got {type_!r}"
            )

        # Validate flag shapes
        if short is not None:
            if not (
                isinstance(short, str)
                and len(short) == 2
                and short.startswith("-")
                and short[1] != "-"
            ):
                raise CliArgsError(
                    f"cli_args.{key}.short: must be a single-dash 2-char flag like '-f', got {short!r}"
                )
            if short in RESERVED_FLAGS:
                raise CliArgsError(
                    f"cli_args.{key}.short={short!r} clashes with reserved cutip flag"
                )
        if not (isinstance(long_, str) and long_.startswith("--") and len(long_) > 2):
            raise CliArgsError(
                f"cli_args.{key}.long: must look like '--name', got {long_!r}"
            )
        if long_ in RESERVED_FLAGS:
            raise CliArgsError(
                f"cli_args.{key}.long={long_!r} clashes with reserved cutip flag"
            )

        # Detect duplicate flags across declared args
        for flag in (short, long_):
            if flag is None:
                continue
            if flag in flag_owners:
                raise CliArgsError(
                    f"cli_args: flag {flag!r} declared by both {flag_owners[flag]!r} and {key!r}"
                )
            flag_owners[flag] = key

        out[key] = {
            "short": short,
            "long": long_,
            "type": type_,
            "required": required,
            "default": default,
            "help": help_,
        }
    return out


def parse_runtime(
    specs: dict[str, dict], tokens: list[str]
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Match a list of unrecognized CLI tokens against declared cli_arg specs.

    Returns ``(user_values, defaults, leftover)``:
    - ``user_values``: ``{var_name: typed_value}`` for flags the user actually passed.
    - ``defaults``: ``{var_name: typed_value}`` for declared specs the user
      did NOT pass that have a non-None ``default`` — kept separate so the
      caller can apply them at lower precedence than ``--vars k=v`` or yaml
      ``vars:`` entries.
    - ``leftover``: tokens that didn't match any declared flag.

    Raises CliArgsError on type-coercion failure or missing required args.
    """
    # Build flag → (key, spec) map
    by_flag: dict[str, tuple[str, dict]] = {}
    for key, spec in specs.items():
        if spec["short"]:
            by_flag[spec["short"]] = (key, spec)
        by_flag[spec["long"]] = (key, spec)

    user_values: dict[str, Any] = {}
    leftover: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]

        # Handle --flag=value form
        if "=" in tok and tok.startswith("--"):
            flag, value = tok.split("=", 1)
            if flag in by_flag:
                key, spec = by_flag[flag]
                user_values[key] = _coerce(value, spec["type"], key=key, flag=flag)
                i += 1
                continue

        if tok in by_flag:
            key, spec = by_flag[tok]
            if spec["type"] == "bool" and (
                i + 1 >= len(tokens) or tokens[i + 1].startswith("-")
            ):
                # bare bool flag (without explicit value) → True
                user_values[key] = True
                i += 1
            else:
                if i + 1 >= len(tokens):
                    raise CliArgsError(f"{tok}: missing value")
                user_values[key] = _coerce(
                    tokens[i + 1], spec["type"], key=key, flag=tok
                )
                i += 2
            continue

        leftover.append(tok)
        i += 1

    # Defaults for args the user didn't pass; check required
    defaults: dict[str, Any] = {}
    for key, spec in specs.items():
        if key in user_values:
            continue
        if spec["default"] is not None:
            defaults[key] = spec["default"]
        elif spec["required"]:
            ident = spec["short"] or spec["long"]
            raise CliArgsError(f"cli_args.{key} is required (pass {ident})")
    return user_values, defaults, leftover


def help_text(specs: dict[str, dict]) -> str:
    """Render a one-screen help block for the declared cli_args. Empty if none."""
    if not specs:
        return ""
    lines = ["Workflow CLI args:"]
    for key, spec in specs.items():
        flags = []
        if spec["short"]:
            flags.append(spec["short"])
        flags.append(spec["long"])
        flag_str = ", ".join(flags)
        meta = []
        if spec["type"] != "str":
            meta.append(spec["type"])
        if spec["required"]:
            meta.append("required")
        elif spec["default"] is not None:
            meta.append(f"default={spec['default']!r}")
        meta_str = f" [{', '.join(meta)}]" if meta else ""
        help_str = f"  {spec['help']}" if spec["help"] else ""
        lines.append(f"  {flag_str:<32}{meta_str}{help_str}")
    return "\n".join(lines)
