"""Live SSH probing for ``cutip hosts validate``.

Takes a resolved hosts dict (the kind ``cutip.hosts.resolve()`` returns)
and probes each entry in parallel. Returns structured results so the CLI
can render a table and the exit code can reflect failures.

The probe function is injected so tests don't need a real SSH endpoint.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import perf_counter
from typing import Callable


@dataclass
class ProbeResult:
    """Outcome of one host probe."""

    name: str
    host: str
    ok: bool
    elapsed: float  # seconds
    error: str | None = None  # populated when ok=False


def _default_probe(host: str, username: str, password: str, port: int) -> None:
    """Open an SSH session and call ``probe()``. Raises on any failure."""
    from rsty import ssh

    with ssh.connect(host=host, username=username, password=password, port=port) as s:
        s.probe()


def _probe_one(
    name: str,
    fields: dict,
    probe: Callable[[str, str, str, int], None],
    timeout_s: float,
) -> ProbeResult:
    host = fields.get("host", "")
    if not host:
        return ProbeResult(name, "", False, 0.0, "missing 'host' field")
    username = fields.get("username", "")
    password = fields.get("password", "")
    if not username or not password:
        missing = [
            f for f, v in (("username", username), ("password", password)) if not v
        ]
        return ProbeResult(
            name, host, False, 0.0, f"missing field(s): {', '.join(missing)}"
        )
    try:
        port = int(fields.get("port", 22))
    except (TypeError, ValueError):
        return ProbeResult(name, host, False, 0.0, "port must be an integer")

    started = perf_counter()
    try:
        # NOTE: the probe function itself is responsible for honoring timeout
        # if the underlying SSH library supports it. We measure wall time and
        # surface it; we do not interrupt — russh handles its own timeouts.
        del timeout_s  # reserved for future use; unused today
        probe(host, username, password, port)
        return ProbeResult(name, host, True, perf_counter() - started)
    except Exception as e:
        # Keep the error short — full traceback isn't useful in a table cell.
        msg = str(e) or type(e).__name__
        return ProbeResult(
            name, host, False, perf_counter() - started, _shorten(msg, 80)
        )


def _shorten(s: str, n: int) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def probe_hosts(
    hosts_dict: dict[str, dict],
    *,
    max_workers: int = 8,
    timeout_s: float = 30.0,
    probe: Callable[[str, str, str, int], None] | None = None,
) -> list[ProbeResult]:
    """Probe every entry in ``hosts_dict`` concurrently.

    Args:
        hosts_dict: Resolved nested dict — ``{name: {"host": ..., "username":
            ..., "password": ..., "port": ...}}``.
        max_workers: Concurrency cap. Default 8.
        timeout_s: Per-probe wall-clock budget (informational; not enforced).
        probe: Override the SSH probe function (used in tests).

    Returns:
        One ``ProbeResult`` per entry, in the same order as ``hosts_dict``.
    """
    fn = probe if probe is not None else _default_probe
    if not hosts_dict:
        return []

    items = list(hosts_dict.items())
    results: dict[str, ProbeResult] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        futures = {
            pool.submit(_probe_one, name, fields or {}, fn, timeout_s): name
            for name, fields in items
        }
        for fut in as_completed(futures):
            res = fut.result()
            results[res.name] = res
    return [results[name] for name, _ in items]
