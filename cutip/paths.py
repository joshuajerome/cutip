"""Path expansion + merge for the project YAML ``paths:`` section.

The ``paths:`` section is a typed sibling of ``data:``. Values are filesystem
paths; cutip expands ``~`` / ``$VAR`` and resolves relatives against the
project YAML's directory, then merges the result into ``ctx.data`` so workflow
code reads them like any other data entry.

This module is the single source of truth for that expansion. Both the
runtime (``cli.py``, ``daemon.py``) and the validator call into it so they
agree on what each path means.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _looks_absolute(raw: str) -> bool:
    """True if `raw` should be treated as already-absolute before expansion.

    Covers Unix absolute (``/...``), home-relative (``~/...``), and Windows
    drive-letter paths (``C:\\`` or ``C:/``). Pure relatives (``./x``,
    ``foo/bar``) return False — they get resolved against the project dir.
    """
    if not raw:
        return False
    if raw.startswith(("/", "~")):
        return True
    if len(raw) >= 3 and raw[1] == ":" and raw[2] in ("/", "\\"):
        return True
    return False


def expand_path(value: str, base_dir: Path) -> str:
    """Expand ``~`` and ``$VAR``; resolve relatives against ``base_dir``.

    Always returns an absolute path string. Empty input returns "" unchanged
    so the validator can flag it.
    """
    if not isinstance(value, str) or not value:
        return value
    expanded = os.path.expandvars(os.path.expanduser(value))
    p = Path(expanded)
    if not p.is_absolute():
        p = (base_dir / p).resolve(strict=False)
    return str(p)


def merge_paths_into_data(config: dict[str, Any], project_path: Path) -> None:
    """Expand each entry under ``paths:`` and merge into ``config['data']``.

    Mutates ``config`` in place. ``paths`` keys that collide with existing
    ``data`` keys overwrite them — paths are typed and validated, so they win.
    No-op if ``paths`` is missing or not a mapping.
    """
    paths = config.get("paths")
    if not isinstance(paths, dict):
        return
    base = project_path.parent
    data = config.get("data")
    if data is None:
        data = {}
        config["data"] = data
    if not isinstance(data, dict):
        return
    for k, v in paths.items():
        if isinstance(v, str):
            data[k] = expand_path(v, base)
        else:
            # Non-string value: pass through; validator will flag.
            data[k] = v
