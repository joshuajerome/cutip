"""Run recording and per-group lock-file utilities."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from cutip.utils.exceptions import CutipError

# ── Helpers ────────────────────────────────────────────────────────────────────


def iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _pid_alive(pid: int) -> bool:
    """Return True if a process with *pid* is currently running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False  # No such process
    except PermissionError:
        return True  # Process exists but we lack permission to signal it
    except OSError:
        return False  # Catch-all (e.g. Windows quirks)
    else:
        return True


# ── Lock ───────────────────────────────────────────────────────────────────────


@contextmanager
def run_lock(locks_dir: Path, group_name: str) -> Generator[None, None, None]:
    """Acquire an exclusive per-group lock for the duration of a run.

    Writes the current PID to ``<locks_dir>/<group_name>.lock``.
    If the lock file already exists and the recorded PID is still alive, raises
    ``CutipError`` to prevent concurrent runs of the same group.
    Stale locks (dead PID) are silently removed and re-acquired.
    The lock file is always cleaned up in the ``finally`` block.
    """
    locks_dir.mkdir(parents=True, exist_ok=True)
    lock_path = locks_dir / f"{group_name}.lock"

    if lock_path.exists():
        try:
            pid = int(lock_path.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = -1

        if pid > 0 and _pid_alive(pid):
            raise CutipError(
                f"Group '{group_name}' is already running (PID {pid}).\n"
                f"If the previous run crashed, delete '{lock_path}' and retry."
            )
        # Stale lock — remove and continue
        lock_path.unlink(missing_ok=True)

    lock_path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


# ── Run records ────────────────────────────────────────────────────────────────


def write_run_record(
    runs_dir: Path,
    *,
    group: str,
    backend: str,
    started_at: str,
    status: str,  # "success" | "failure"
    finished_at: str | None = None,
    error: str | None = None,
) -> Path:
    """Write a JSON run record to *runs_dir* and return the file path.

    Filename format: ``<group>_<YYYYMMDD_HHMMSS>.json``
    """
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Build a filesystem-safe timestamp from the ISO string
    # e.g. "2026-02-21T19:11:04+00:00" → "20260221_191104"
    ts = started_at.replace("-", "").replace(":", "").replace("+", "")
    ts_clean = ts[:15].replace("T", "_")  # "YYYYMMDD_HHMMSS"

    record_path = runs_dir / f"{group}_{ts_clean}.json"
    record: dict = {
        "group": group,
        "backend": backend,
        "started_at": started_at,
        "finished_at": finished_at or iso_now(),
        "status": status,
        "error": error,
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record_path
