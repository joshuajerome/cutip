"""Version utilities — installed version + PyPI latest check."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from importlib.metadata import version as _pkg_version
from pathlib import Path

_PYPI_URL = "https://pypi.org/pypi/cutip/json"
_CACHE_TTL = 3600  # 1 hour


def installed_version() -> str:
    """Return the locally installed cutip version."""
    return _pkg_version("cutip")


def latest_version(cache_dir: Path | None = None) -> str | None:
    """Check PyPI for the latest cutip version (cached for 1 hour).

    Returns the version string, or None if the check fails (offline, timeout, etc.).
    """
    if cache_dir is None:
        cache_dir = Path(".cutip") / "cache"

    cache_file = cache_dir / "version_check.json"

    # Read cache
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if time.time() - data.get("ts", 0) < _CACHE_TTL:
                return data.get("version")
        except Exception:
            pass

    # Fetch from PyPI
    try:
        req = urllib.request.Request(_PYPI_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read())
        ver = payload.get("info", {}).get("version")
    except Exception:
        return None

    # Write cache
    if ver:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({"version": ver, "ts": time.time()}),
                encoding="utf-8",
            )
        except Exception:
            pass

    return ver
