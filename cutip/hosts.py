"""Hosts file management for cutip.

Two storage tiers:
  - **local**:  ``<project>/hosts.yaml`` (per-project)
  - **global**: ``~/.cutip/hosts.yaml`` (shared across projects)

The path of the global file can be changed via ``cutip hosts set-path -g``,
which writes to ``~/.cutip/config.yaml``.

Two file formats are recognized:
  - **flat** (legacy): top-level keys are the field names::

        host: 10.0.0.1
        username: root
        password: secret

  - **nested** (current): top-level keys are host *names*, each a dict
    of fields. A host entry can use ``global: true`` to defer to the
    same name in the global file::

        build:
          host: build.example.com
          username: alice
          password: secret
        app:
          global: true        # pulled from ~/.cutip/hosts.yaml

The parser auto-detects format on read. Migration (flat → nested) is
explicit via ``cutip hosts migrate``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ── File layout ─────────────────────────────────────────────────────────────


def cutip_dir() -> Path:
    """Return ``~/.cutip/`` (creating it if missing)."""
    p = Path.home() / ".cutip"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    """Path to ``~/.cutip/config.yaml`` (the cutip global config)."""
    return cutip_dir() / "config.yaml"


def default_global_hosts_path() -> Path:
    """Default path for the global hosts file."""
    return cutip_dir() / "hosts.yaml"


def global_hosts_path() -> Path:
    """Resolve the global hosts file path.

    Reads ``hosts_path`` from ``~/.cutip/config.yaml`` if set, otherwise
    returns the default ``~/.cutip/hosts.yaml``.
    """
    cp = config_path()
    if cp.exists():
        try:
            import yaml

            cfg = yaml.safe_load(cp.read_text()) or {}
            override = cfg.get("hosts_path")
            if override:
                return Path(str(override)).expanduser()
        except Exception:
            pass
    return default_global_hosts_path()


def set_global_hosts_path(path: Path | str) -> None:
    """Persist a custom global hosts file path to ``~/.cutip/config.yaml``."""
    import yaml

    cp = config_path()
    cfg: dict[str, Any] = {}
    if cp.exists():
        try:
            cfg = yaml.safe_load(cp.read_text()) or {}
        except Exception:
            cfg = {}
    cfg["hosts_path"] = str(Path(str(path)).expanduser())
    cp.write_text(yaml.safe_dump(cfg, sort_keys=False))


# ── Format detection ────────────────────────────────────────────────────────


def is_nested(data: dict | None) -> bool:
    """Return True if `data` is in nested format (host names → field dicts).

    Heuristic: a dict is nested if any top-level value is itself a dict.
    Empty dict treated as nested (the new default).
    """
    if not data:
        return True
    return any(isinstance(v, dict) for v in data.values())


# ── Read / write ────────────────────────────────────────────────────────────


def read_hosts_file(path: Path) -> dict[str, Any]:
    """Read a hosts file, returning the raw parsed dict.

    Returns an empty dict if the file does not exist.
    """
    if not path.exists():
        return {}
    import yaml

    return yaml.safe_load(path.read_text()) or {}


def write_hosts_file(path: Path, data: dict[str, Any]) -> None:
    """Write a hosts dict to the given path (creating parent dirs)."""
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


# ── Resolution ──────────────────────────────────────────────────────────────


class HostsError(RuntimeError):
    """Raised when hosts files can't be parsed or resolved."""


def resolve(local_path: Path) -> dict[str, dict]:
    """Read local + global, resolve `global: true` references, return nested dict.

    Output is always nested: ``{"<host_name>": {"host": ..., "username": ...,
    "password": ...}, ...}``.

    For flat-format input files, the entire file becomes a single host
    entry under the key ``"_default"``. Workflows can read it via
    ``ctx.host_for("_default")`` — but typically existing workflows that use
    ``ctx._hosts["host"]`` keep working unchanged because the raw dict
    is also exposed.

    Raises HostsError if a `global: true` reference can't be resolved.
    """
    local = read_hosts_file(local_path)

    if not is_nested(local):
        # Flat file: wrap as single-entry nested
        return {"_default": local} if local else {}

    out: dict[str, dict] = {}
    global_data: dict | None = None  # lazy-load

    for name, entry in local.items():
        if not isinstance(entry, dict):
            raise HostsError(
                f"Host entry '{name}' must be a mapping, got {type(entry).__name__}"
            )

        # Reference to a global entry
        if entry.get("global") is True:
            if global_data is None:
                gp = global_hosts_path()
                if not gp.exists():
                    raise HostsError(
                        f"Host '{name}' is marked 'global: true' but the global "
                        f"hosts file does not exist at {gp}. Run: cutip hosts init -g"
                    )
                global_data = read_hosts_file(gp)
                if not is_nested(global_data):
                    raise HostsError(
                        f"Global hosts file at {gp} must be in nested format "
                        f"(host names as top-level keys)"
                    )
            if name not in global_data:
                raise HostsError(
                    f"Host '{name}' marked 'global: true' but not found in {global_hosts_path()}. "
                    f"Available: {', '.join(sorted(global_data.keys()))}"
                )
            out[name] = dict(global_data[name])
        else:
            out[name] = dict(entry)

    return out


def get_field(local_path: Path, host_name: str, field: str) -> Any:
    """Get a single field from a host entry. Returns None if missing."""
    resolved = resolve(local_path)
    if host_name not in resolved:
        return None
    return resolved[host_name].get(field)


def set_field(path: Path, host_name: str, field: str, value: str) -> None:
    """Set a host's field in the file, ensuring nested format.

    Reads the existing file (if any). If it's in flat format, raises
    HostsError telling the caller to migrate first. Always writes nested.
    """
    data = read_hosts_file(path)
    if data and not is_nested(data):
        raise HostsError(
            f"{path.name} is in flat (legacy) format. Run 'cutip hosts migrate' "
            f"first, then re-run this command."
        )
    if host_name not in data:
        data[host_name] = {}
    if not isinstance(data[host_name], dict):
        raise HostsError(
            f"Host '{host_name}' has a non-mapping entry: {data[host_name]!r}"
        )
    data[host_name][field] = value
    write_hosts_file(path, data)


# ── Promotion (local → global) ──────────────────────────────────────────────


@dataclass
class PromoteResult:
    """Outcome of a promote_to_global() call."""

    promoted: list[str]  # names successfully copied to global
    conflicts: list[str]  # names that exist in global with different values (skipped)
    skipped_already_global: list[str]  # names already `global: true` in local
    skipped_missing: list[str]  # names requested but not in local file


def promote_to_global(
    local_path: Path,
    names: list[str] | None = None,
    *,
    force: bool = False,
) -> PromoteResult:
    """Copy local hosts entries to ``~/.cutip/hosts.yaml`` and replace each
    promoted local entry with ``{global: true}``.

    Args:
        local_path: Path to the project's hosts.yaml.
        names: Specific host names to promote. ``None`` means every entry
            in the local file.
        force: Overwrite global entries that already exist with different
            values. Without ``force``, conflicts are reported and the
            promotion of those names is skipped.

    Returns:
        ``PromoteResult`` describing what happened. The local file is only
        modified for names that were actually promoted (no partial writes
        on errors).

    Raises:
        HostsError: if the local file is in flat format (run ``migrate``
            first) or if a requested entry isn't a mapping.
    """
    local = read_hosts_file(local_path)
    if local and not is_nested(local):
        raise HostsError(
            f"{local_path.name} is in flat (legacy) format. "
            "Run 'cutip hosts migrate' first, then re-run promote."
        )

    global_path = global_hosts_path()
    global_data = read_hosts_file(global_path) if global_path.exists() else {}
    if global_data and not is_nested(global_data):
        raise HostsError(f"global hosts file at {global_path} is not in nested format")

    targets: list[str] = list(names) if names else list(local.keys())
    promoted: list[str] = []
    conflicts: list[str] = []
    skipped_already_global: list[str] = []
    skipped_missing: list[str] = []

    for name in targets:
        if name not in local:
            skipped_missing.append(name)
            continue
        entry = local[name]
        if not isinstance(entry, dict):
            raise HostsError(
                f"local entry '{name}' is not a mapping (got {type(entry).__name__})"
            )
        if entry.get("global") is True:
            skipped_already_global.append(name)
            continue
        # Conflict: existing global entry with different fields
        existing = global_data.get(name)
        if isinstance(existing, dict) and existing != entry and not force:
            conflicts.append(name)
            continue
        global_data[name] = dict(entry)
        promoted.append(name)

    # Only persist if we actually moved something. Empty promote = no-op.
    if promoted:
        write_hosts_file(global_path, global_data)
        for name in promoted:
            local[name] = {"global": True}
        write_hosts_file(local_path, local)

    return PromoteResult(
        promoted=promoted,
        conflicts=conflicts,
        skipped_already_global=skipped_already_global,
        skipped_missing=skipped_missing,
    )


# ── Migration ───────────────────────────────────────────────────────────────


def migrate(path: Path, default_name: str = "default") -> bool:
    """Convert a flat hosts.yaml to nested in-place.

    Returns True if migrated, False if already nested (no-op) or empty.
    `default_name` is the host name to use for the converted entry.
    """
    data = read_hosts_file(path)
    if not data:
        return False
    if is_nested(data):
        return False
    new_data = {default_name: dict(data)}
    write_hosts_file(path, new_data)
    return True
