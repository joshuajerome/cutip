"""Global data store for cutip — shared values across projects.

Storage: ``~/.cutip/data.yaml`` (sibling of ``~/.cutip/hosts.yaml``).

Free-form nested YAML — typically used for shared constants like
default passwords keyed by product version, IPs by environment, or
URLs to internal services::

    passwords:
      v22: "DefaultPw123!"
      v23: "OtherPw456!"
    constants:
      artifactory_url: "http://artifactory.internal/"

Templates in workflow YAML (or any string passed through
``rsty.config.substitute_vars``) reference values via dotted paths::

    auth: "admin:{{ globals.passwords.v22 }}"

Resolution rules:

- Only leaf scalars (str/int/float/bool) are substitutable. Dict/list
  values can't render into a string and stay as the unresolved
  placeholder.
- Missing keys leave the placeholder untouched (caller's job to detect
  via the resolver's ``find_unresolved`` helper).

The CLI surface is ``cutip data list/get/set/path/init`` (parallel to
``cutip hosts``, but no per-project tier — globals are by definition
global).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ── File layout ─────────────────────────────────────────────────────────────


def globals_path() -> Path:
    """Return the path to the global data file (~/.cutip/data.yaml).

    Honors the same ``data_path`` override mechanism as
    ``cutip.hosts.global_hosts_path`` if it's ever needed; for now,
    returns the default unless a future ``cutip data set-path`` is added.
    """
    from cutip.hosts import cutip_dir

    return cutip_dir() / "data.yaml"


# ── Read / write ────────────────────────────────────────────────────────────


def read_globals(path: Path | None = None) -> dict[str, Any]:
    """Read the globals file, returning the raw nested dict.

    Returns an empty dict if the file does not exist.
    """
    p = path or globals_path()
    if not p.exists():
        return {}
    import yaml

    return yaml.safe_load(p.read_text()) or {}


def write_globals(data: dict[str, Any], path: Path | None = None) -> None:
    """Write a globals dict to the given path (creating parent dirs)."""
    import yaml

    p = path or globals_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


# ── Dotted-path lookup + flatten ────────────────────────────────────────────


class GlobalsError(RuntimeError):
    """Raised when a globals operation fails."""


def lookup(data: dict[str, Any], dotted: str) -> Any:
    """Walk ``data`` along the dotted path, returning the leaf value.

    Returns ``None`` if any segment is missing or the path traverses a
    non-mapping. Does NOT coerce the result to a string — callers can
    decide how to handle non-scalar leaves.
    """
    if not dotted:
        return None
    cur: Any = data
    for segment in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        if segment not in cur:
            return None
        cur = cur[segment]
    return cur


def set_dotted(data: dict[str, Any], dotted: str, value: Any) -> None:
    """Set a nested value at the dotted path, creating intermediate dicts.

    Raises GlobalsError if any intermediate path traverses a non-mapping
    leaf.
    """
    if not dotted:
        raise GlobalsError("dotted path cannot be empty")
    segments = dotted.split(".")
    cur: dict[str, Any] = data
    for segment in segments[:-1]:
        existing = cur.get(segment)
        if existing is None:
            cur[segment] = {}
        elif not isinstance(existing, dict):
            raise GlobalsError(
                f"path '{dotted}' traverses non-mapping at '{segment}' "
                f"(value: {existing!r})"
            )
        cur = cur[segment]
    cur[segments[-1]] = value


def remove_dotted(data: dict[str, Any], dotted: str) -> Any:
    """Remove the entry at the dotted path, returning what was removed.

    Cleans up emptied parent dicts (so removing the only key under
    ``passwords.v22`` also removes ``passwords`` if it becomes empty).
    Returns the removed leaf value.

    Raises:
        GlobalsError: if the path is empty, doesn't exist, or traverses
            through a non-mapping value.
    """
    if not dotted:
        raise GlobalsError("dotted path cannot be empty")
    segments = dotted.split(".")
    # Walk down, capturing each parent + key so we can clean up empties.
    parents: list[tuple[dict[str, Any], str]] = []
    cur: Any = data
    for segment in segments[:-1]:
        if not isinstance(cur, dict):
            raise GlobalsError(f"path '{dotted}' traverses non-mapping at '{segment}'")
        if segment not in cur:
            raise GlobalsError(f"path '{dotted}' not found")
        parents.append((cur, segment))
        cur = cur[segment]

    leaf_key = segments[-1]
    if not isinstance(cur, dict):
        raise GlobalsError(f"path '{dotted}' traverses non-mapping")
    if leaf_key not in cur:
        raise GlobalsError(f"path '{dotted}' not found")
    removed = cur.pop(leaf_key)

    # Walk parents in reverse, removing any that became empty.
    for parent, key in reversed(parents):
        if isinstance(parent[key], dict) and len(parent[key]) == 0:
            del parent[key]
        else:
            break
    return removed


def flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten a nested dict to {dotted.path: str_value} for substitution.

    Only leaf scalars (str/int/float/bool) are included. Dicts recurse;
    lists, ``None``, and other types are skipped — they can't be
    substituted into a string template.
    """
    out: dict[str, str] = {}
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, bool):
            # Order matters: bool is a subclass of int.
            out[key] = "true" if v else "false"
        elif isinstance(v, (str, int, float)):
            out[key] = str(v)
    return out
