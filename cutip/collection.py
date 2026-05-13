"""Collection tier for cutip — multiple projects sharing config.

A *collection* is a directory tree containing multiple cutip projects
plus shared `.cutip/{data,hosts}.yaml` and a `cutip.collection.yaml`
manifest at the root. Projects under that root resolve
`{{ collection.X }}` template references against the collection's
`.cutip/data.yaml` (in addition to `{{ globals.X }}` from
`~/.cutip/data.yaml`).

Discovery is filesystem-based: walk up from the project's yaml location
looking for ``cutip.collection.yaml``. The first match wins. No
``collection:`` field in the project yaml — the filesystem layout IS
the authoritative answer.

The manifest schema (illustrative — kept loose; cutip reads only what
it needs)::

    name: snf-dev
    version: 1.0.0
    projects:
      - path: workspaces/snf-gui/container.yaml
        description: |
          Multi-line free-form description for cutip projects / show.
        status: working
      - path: sfm/gui/setup.yaml
        description: Patch Keycloak + REST deployment.
        status: working

Why a separate namespace (not precedence-cascade on ``globals``):
explicit beats implicit. With ``{{ collection.X }}`` vs ``{{ globals.X }}``
the writer (and reader) knows immediately which tier supplies the value.
Same shape as git's ``--local`` / ``--global`` / ``--system``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ── Constants ───────────────────────────────────────────────────────────────


MANIFEST_FILENAME = "cutip.collection.yaml"
DATA_FILENAME = "data.yaml"
HOSTS_FILENAME = "hosts.yaml"


# ── Discovery ───────────────────────────────────────────────────────────────


def find_collection_root(start: Path) -> Path | None:
    """Walk up from ``start`` looking for ``cutip.collection.yaml``.

    Returns the directory containing the manifest, or ``None`` if no
    ancestor has one (i.e. ``start`` is not inside a collection).

    ``start`` may be a file or a directory; files are resolved to their
    parent directory before walking.
    """
    p = Path(start).resolve()
    if p.is_file():
        p = p.parent
    for ancestor in (p, *p.parents):
        if (ancestor / MANIFEST_FILENAME).is_file():
            return ancestor
    return None


# ── File layout helpers ─────────────────────────────────────────────────────


def manifest_path(collection_root: Path) -> Path:
    return Path(collection_root) / MANIFEST_FILENAME


def data_path(collection_root: Path) -> Path:
    return Path(collection_root) / ".cutip" / DATA_FILENAME


def hosts_path(collection_root: Path) -> Path:
    return Path(collection_root) / ".cutip" / HOSTS_FILENAME


# ── Read / write ────────────────────────────────────────────────────────────


def read_manifest(collection_root: Path) -> dict[str, Any]:
    """Parse ``cutip.collection.yaml``. Empty dict if missing/empty."""
    p = manifest_path(collection_root)
    if not p.is_file():
        return {}
    import yaml

    return yaml.safe_load(p.read_text()) or {}


def write_manifest(collection_root: Path, data: dict[str, Any]) -> None:
    """Write the manifest. Creates the file if it doesn't exist."""
    import yaml

    p = manifest_path(collection_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def read_data(collection_root: Path) -> dict[str, Any]:
    """Parse ``<root>/.cutip/data.yaml``. Empty dict if missing/empty."""
    p = data_path(collection_root)
    if not p.is_file():
        return {}
    import yaml

    return yaml.safe_load(p.read_text()) or {}


def write_data(collection_root: Path, data: dict[str, Any]) -> None:
    """Write ``<root>/.cutip/data.yaml`` (creating dirs)."""
    import yaml

    p = data_path(collection_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def read_hosts(collection_root: Path) -> dict[str, Any]:
    """Parse ``<root>/.cutip/hosts.yaml``. Empty dict if missing/empty."""
    p = hosts_path(collection_root)
    if not p.is_file():
        return {}
    import yaml

    return yaml.safe_load(p.read_text()) or {}


def write_hosts(collection_root: Path, data: dict[str, Any]) -> None:
    """Write ``<root>/.cutip/hosts.yaml`` (creating dirs)."""
    import yaml

    p = hosts_path(collection_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


# ── Flatten (for substitution) ──────────────────────────────────────────────


def flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten a nested dict to {dotted.path: str_value} for substitution.

    Mirrors ``cutip.globals.flatten``. Only leaf scalars (str/int/float/bool)
    are included; dict-typed values recurse, lists/None are skipped (they
    can't be substituted into a string template).
    """
    out: dict[str, str] = {}
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, bool):
            out[key] = "true" if v else "false"
        elif isinstance(v, (str, int, float)):
            out[key] = str(v)
    return out


def load_for_project(project_path: Path) -> tuple[Path | None, dict[str, str]]:
    """Resolve collection context for a project at ``project_path``.

    Returns ``(collection_root, collection_flat)``. If the project isn't
    inside a collection, ``(None, {})``. ``collection_flat`` is the
    flattened-dotted-key form of ``<root>/.cutip/data.yaml`` ready to
    pass into ``substitute_in_obj``.
    """
    root = find_collection_root(Path(project_path))
    if root is None:
        return None, {}
    return root, flatten(read_data(root))
