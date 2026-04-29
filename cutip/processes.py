"""Process state management for cutip background runs.

Each `cutip run --bg` invocation writes its state to a directory under
``~/.cutip/processes/<cu-id>/``. State is plain files so any of these
work without a daemon: `cutip ps`, `cutip ps logs`, `cutip ps stop`,
`cutip ps inspect` — they all just read/write files in this directory.

Layout::

    ~/.cutip/processes/snf-build-7f3a/
    ├── meta.json       # project, started_at, status, host_pid, exit_code, ...
    ├── stdout.log      # streamed during run; tail -f-able
    ├── stderr.log      # streamed
    ├── remote.json     # remote PIDs the daemon spawned (for cascade-kill)
    └── stop.lock       # presence = stop requested; daemon polls + acts

Status values: ``starting``, ``running``, ``succeeded``, ``failed``, ``stopped``.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


# ── Layout ──────────────────────────────────────────────────────────────────


def root_dir() -> Path:
    """Return ``~/.cutip/processes/`` (creating it if missing)."""
    p = Path.home() / ".cutip" / "processes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def process_dir(cu_id: str) -> Path:
    return root_dir() / cu_id


def meta_path(cu_id: str) -> Path:
    return process_dir(cu_id) / "meta.json"


def stdout_path(cu_id: str) -> Path:
    return process_dir(cu_id) / "stdout.log"


def stderr_path(cu_id: str) -> Path:
    return process_dir(cu_id) / "stderr.log"


def remote_path(cu_id: str) -> Path:
    return process_dir(cu_id) / "remote.json"


def stop_lock_path(cu_id: str) -> Path:
    return process_dir(cu_id) / "stop.lock"


# ── cu-id generation ────────────────────────────────────────────────────────


def make_cu_id(project: str) -> str:
    """Return ``<project>-<4hex>`` slug, unique within the processes dir."""
    base = project.lower().replace("/", "-").replace(" ", "-")
    salt = f"{project}-{time.time_ns()}-{os.getpid()}"
    short = hashlib.sha256(salt.encode()).hexdigest()[:4]
    cu_id = f"{base}-{short}"
    # Collision is essentially impossible given time_ns, but be safe.
    n = 1
    while process_dir(cu_id).exists():
        n += 1
        cu_id = f"{base}-{short}-{n}"
    return cu_id


def resolve_cu_id(prefix_or_id: str) -> str:
    """Resolve a (possibly partial) cu-id to a full one.

    Accepts an exact match, a unique prefix, or a unique 4-hex suffix.
    Raises ValueError if ambiguous or not found.
    """
    candidates = [d.name for d in root_dir().iterdir() if d.is_dir()]

    # Exact match
    if prefix_or_id in candidates:
        return prefix_or_id

    # Prefix match
    prefixed = [c for c in candidates if c.startswith(prefix_or_id)]
    if len(prefixed) == 1:
        return prefixed[0]
    if len(prefixed) > 1:
        raise ValueError(
            f"Ambiguous cu-id prefix '{prefix_or_id}': matches {', '.join(sorted(prefixed))}"
        )

    # Suffix match (e.g., user typed just '7f3a')
    suffixed = [c for c in candidates if c.endswith(f"-{prefix_or_id}")]
    if len(suffixed) == 1:
        return suffixed[0]
    if len(suffixed) > 1:
        raise ValueError(
            f"Ambiguous cu-id suffix '{prefix_or_id}': matches {', '.join(sorted(suffixed))}"
        )

    raise ValueError(f"No cutip process found matching '{prefix_or_id}'")


# ── Meta ────────────────────────────────────────────────────────────────────


@dataclass
class Meta:
    """Process metadata stored at ~/.cutip/processes/<cu-id>/meta.json."""

    cu_id: str
    project: str
    project_path: str  # absolute path to the project YAML
    workflow_path: str  # absolute path to the workflow file
    cwd: str  # working directory at spawn time
    started_at: str  # ISO 8601
    status: str = "starting"
    host_pid: int | None = None  # the daemon's PID on this machine
    exit_code: int | None = None
    finished_at: str | None = None
    error: str | None = None  # short error message if status == "failed"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_meta(meta: Meta) -> None:
    process_dir(meta.cu_id).mkdir(parents=True, exist_ok=True)
    meta_path(meta.cu_id).write_text(json.dumps(asdict(meta), indent=2))


def read_meta(cu_id: str) -> Meta:
    raw = meta_path(cu_id).read_text()
    return Meta(**json.loads(raw))


def update_meta(cu_id: str, **fields) -> Meta:
    """Read meta, update given fields, write back. Returns the new Meta."""
    meta = read_meta(cu_id)
    for k, v in fields.items():
        setattr(meta, k, v)
    write_meta(meta)
    return meta


def list_processes() -> Iterator[Meta]:
    """Yield Meta for every process in the state dir, newest first."""
    items: list[Meta] = []
    for d in root_dir().iterdir():
        if not d.is_dir():
            continue
        try:
            items.append(read_meta(d.name))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    items.sort(key=lambda m: m.started_at, reverse=True)
    yield from items


# ── Remote PID tracking ─────────────────────────────────────────────────────


@dataclass
class RemoteProc:
    host: str
    username: str  # may be redacted before display, kept for cascade-kill SSH
    pid: int
    label: str  # human-readable label for `cutip ps inspect`
    started_at: str = field(default_factory=now_iso)


def append_remote_pid(cu_id: str, proc: RemoteProc) -> None:
    """Append a remote process record to remote.json (creates file if missing)."""
    path = remote_path(cu_id)
    procs: list[dict] = []
    if path.exists():
        try:
            procs = json.loads(path.read_text())
        except json.JSONDecodeError:
            procs = []
    procs.append(asdict(proc))
    path.write_text(json.dumps(procs, indent=2))


def list_remote_pids(cu_id: str) -> list[RemoteProc]:
    path = remote_path(cu_id)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        return []
    return [RemoteProc(**r) for r in raw]


# ── Stop signaling ──────────────────────────────────────────────────────────


def request_stop(cu_id: str) -> None:
    """Write stop.lock so the daemon knows to terminate."""
    stop_lock_path(cu_id).touch()


def is_stop_requested(cu_id: str) -> bool:
    return stop_lock_path(cu_id).exists()


def clear_stop(cu_id: str) -> None:
    p = stop_lock_path(cu_id)
    if p.exists():
        p.unlink()


# ── Cleanup ─────────────────────────────────────────────────────────────────


def is_terminal(status: str) -> bool:
    return status in ("succeeded", "failed", "stopped")


def prune(older_than_days: int = 7) -> list[str]:
    """Delete process dirs whose status is terminal and older than N days.

    Returns the list of cu-ids that were pruned.
    """
    import shutil

    cutoff = time.time() - older_than_days * 86400
    pruned: list[str] = []
    for meta in list_processes():
        if not is_terminal(meta.status):
            continue
        finished = meta.finished_at or meta.started_at
        try:
            ts = datetime.fromisoformat(finished).timestamp()
        except ValueError:
            continue
        if ts < cutoff:
            shutil.rmtree(process_dir(meta.cu_id), ignore_errors=True)
            pruned.append(meta.cu_id)
    return pruned
