"""Engine-level template substitution for cutip config + hosts files.

Walks any nested dict / list / str structure and substitutes:

  ``{{ vars.key }}``       from vars
  ``{{ paths.key }}``      from paths (raw values, before merge into data)
  ``{{ secrets.key }}``    from secrets
  ``{{ globals.a.b.c }}``  from globals (dotted keys, pre-flattened)

Both spaced (``{{ ns.key }}``) and unspaced (``{{ns.key}}``) forms are
accepted, matching the runtime ``rsty.config.substitute_vars`` and the
Rust resolver in cutip-core.

Resolution order at config load (see ``cutip.cli._load_config``):

  1. Read globals from ``~/.cutip/data.yaml`` (flat dotted keys).
  2. Substitute globals into ``vars``, ``paths``, ``secrets``. These are
     SOURCES for further substitution, so resolving them first means the
     rest of the config sees their final values. Vars/paths/secrets
     cannot reference each other — only globals.
  3. Substitute vars + paths + secrets + globals into the entire config
     (data, container, image, environment, mounts, etc.).
  4. ``cutip.paths.merge_paths_into_data`` runs after substitution so
     paths used by workflows are already expanded.

For hosts.yaml, ``cutip.hosts.resolve()`` returns the dict; the caller
(``cli.py`` / ``daemon.py``) then calls ``substitute_in_obj`` with the
project's substitution context. That keeps ``hosts.resolve()`` pure and
avoids passing context that hosts logic doesn't otherwise need.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


def _substitute_string(
    text: str,
    vars: Mapping[str, str],
    paths: Mapping[str, str],
    secrets: Mapping[str, str],
    globals: Mapping[str, str],
    collection: Mapping[str, str] | None = None,
) -> str:
    """Substitute ``{{ ns.key }}`` placeholders in a single string.

    Whitespace-tolerant: ``{{ns.key}}``, ``{{ ns.key }}``, ``{{ ns.key}}``,
    ``{{ns.key }}``, and any number of internal spaces all match.

    Idempotent: a string with no ``{{`` returns unchanged. Strings whose
    placeholders don't match any key in any namespace are returned with
    the placeholders intact (caller decides whether to flag as an error).
    """
    if "{{" not in text:
        return text
    result = text
    coll = collection or {}
    for ns, mapping in (
        ("vars", vars),
        ("paths", paths),
        ("secrets", secrets),
        ("collection", coll),
        ("globals", globals),
    ):
        for key, value in mapping.items():
            sval = value if isinstance(value, str) else str(value)
            # \{\{\s*ns\.key\s*\}\}  — any (or no) whitespace inside braces.
            pattern = re.compile(r"\{\{\s*" + re.escape(f"{ns}.{key}") + r"\s*\}\}")
            result = pattern.sub(lambda _, v=sval: v, result)
    return result


def substitute_in_obj(
    obj: Any,
    *,
    vars: Mapping[str, str] | None = None,
    paths: Mapping[str, str] | None = None,
    secrets: Mapping[str, str] | None = None,
    globals: Mapping[str, str] | None = None,
    collection: Mapping[str, str] | None = None,
) -> Any:
    """Recursively substitute templates in a dict / list / str structure.

    Returns a new structure (input is not mutated). Values that aren't
    strings, dicts, or lists pass through unchanged (int, bool, None, …).
    """
    v = vars or {}
    p = paths or {}
    s = secrets or {}
    g = globals or {}
    c = collection or {}

    if isinstance(obj, str):
        return _substitute_string(obj, v, p, s, g, c)
    if isinstance(obj, dict):
        return {
            k: substitute_in_obj(
                val, vars=v, paths=p, secrets=s, globals=g, collection=c
            )
            for k, val in obj.items()
        }
    if isinstance(obj, list):
        return [
            substitute_in_obj(item, vars=v, paths=p, secrets=s, globals=g, collection=c)
            for item in obj
        ]
    return obj


# Matches `{{ ns.key }}` / `{{ns.key}}` etc. Captures whatever's between
# the braces, trimmed. Stops at the first ``}}`` to avoid greedy issues
# when multiple placeholders appear on the same line.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def find_unresolved_in_obj(obj: Any, path: str = "") -> list[tuple[str, str]]:
    """Walk a substituted config structure and collect unresolved placeholders.

    Returns a list of ``(yaml_path, placeholder)`` pairs. ``yaml_path`` is
    a dotted/bracketed location like ``"data.password"`` or
    ``"container.mounts[0].source"``. ``placeholder`` is the inner text of
    the placeholder, e.g. ``"globals.sfm.passwords.cli"``.

    Substitution leaves unresolved placeholders untouched (by design — see
    ``_substitute_string``), so calling this after ``substitute_in_obj``
    pinpoints exactly which references didn't bind to a value.
    """
    found: list[tuple[str, str]] = []

    if isinstance(obj, str):
        for match in _PLACEHOLDER_RE.finditer(obj):
            found.append((path or "<root>", match.group(1).strip()))
        return found

    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else str(k)
            found.extend(find_unresolved_in_obj(v, child_path))
        return found

    if isinstance(obj, list):
        for i, item in enumerate(obj):
            child_path = f"{path}[{i}]"
            found.extend(find_unresolved_in_obj(item, child_path))
        return found

    return found


def resolve_substitution_maps(
    config: dict,
    globals_flat: Mapping[str, str],
    collection_flat: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Resolve globals + collection into vars/paths/secrets, returning the final maps.

    These three are the substitution SOURCES; they themselves can only
    reference globals or collection (the two tiers above project). Used
    at the start of config load before walking the rest of the dict.
    """
    raw_vars = config.get("vars") or {}
    raw_paths = config.get("paths") or {}
    raw_secrets = config.get("secrets") or {}
    coll = collection_flat or {}

    def _resolve_one(mapping: Mapping[str, Any]) -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in mapping.items():
            if isinstance(v, str):
                out[k] = _substitute_string(v, {}, {}, {}, globals_flat, coll)
            else:
                # Coerce non-string values (rare; users who put ints/bools
                # in vars: usually mean strings anyway).
                out[k] = str(v)
        return out

    return _resolve_one(raw_vars), _resolve_one(raw_paths), _resolve_one(raw_secrets)
