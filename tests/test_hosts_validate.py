"""Tests for cutip.hosts_validate — parallel SSH probe orchestrator."""

from __future__ import annotations

from cutip.hosts_validate import probe_hosts


def _ok_probe(*_args, **_kwargs):
    return None


def _fail_probe(*_args, **_kwargs):
    raise RuntimeError("auth failed")


def _slow_probe(*_args, **_kwargs):
    import time

    time.sleep(0.05)


def test_probe_hosts_empty():
    assert probe_hosts({}) == []


def test_probe_hosts_all_ok():
    hosts = {
        "ub20": {"host": "h1", "username": "u", "password": "p"},
        "sfm": {"host": "h2", "username": "u", "password": "p"},
    }
    results = probe_hosts(hosts, probe=_ok_probe)
    assert len(results) == 2
    assert {r.name for r in results} == {"ub20", "sfm"}
    assert all(r.ok for r in results)
    assert all(r.error is None for r in results)


def test_probe_hosts_failure_captured():
    hosts = {"ub20": {"host": "h1", "username": "u", "password": "p"}}
    results = probe_hosts(hosts, probe=_fail_probe)
    assert results[0].ok is False
    assert "auth failed" in results[0].error


def test_probe_hosts_missing_host_field():
    hosts = {"bad": {"username": "u", "password": "p"}}
    results = probe_hosts(hosts, probe=_ok_probe)
    assert results[0].ok is False
    assert "host" in results[0].error


def test_probe_hosts_missing_credentials():
    hosts = {"bad": {"host": "h1"}}
    results = probe_hosts(hosts, probe=_ok_probe)
    assert results[0].ok is False
    assert "username" in results[0].error
    assert "password" in results[0].error


def test_probe_hosts_invalid_port():
    hosts = {"bad": {"host": "h1", "username": "u", "password": "p", "port": "abc"}}
    results = probe_hosts(hosts, probe=_ok_probe)
    assert results[0].ok is False
    assert "port" in results[0].error


def test_probe_hosts_preserves_input_order():
    hosts = {
        "z": {"host": "h", "username": "u", "password": "p"},
        "a": {"host": "h", "username": "u", "password": "p"},
        "m": {"host": "h", "username": "u", "password": "p"},
    }
    results = probe_hosts(hosts, probe=_ok_probe)
    assert [r.name for r in results] == ["z", "a", "m"]


def test_probe_hosts_runs_in_parallel():
    """5 hosts × 50ms each should complete in <250ms with parallel pool."""
    import time

    hosts = {
        f"h{i}": {"host": f"h{i}", "username": "u", "password": "p"} for i in range(5)
    }
    started = time.perf_counter()
    results = probe_hosts(hosts, max_workers=8, probe=_slow_probe)
    elapsed = time.perf_counter() - started
    assert all(r.ok for r in results)
    # Sequential would be 250ms+; parallel should clock well under 200ms
    assert elapsed < 0.2, f"expected parallel run, took {elapsed:.3f}s"


def test_probe_hosts_records_elapsed():
    hosts = {"ub20": {"host": "h", "username": "u", "password": "p"}}
    results = probe_hosts(hosts, probe=_slow_probe)
    assert results[0].ok
    assert results[0].elapsed >= 0.04  # was sleep 0.05


def test_probe_hosts_default_port_22():
    """If no port is given, the probe should still run with port=22."""
    captured: dict = {}

    def capturing_probe(host, username, password, port):
        captured["port"] = port

    hosts = {"ub20": {"host": "h", "username": "u", "password": "p"}}
    probe_hosts(hosts, probe=capturing_probe)
    assert captured["port"] == 22


def test_probe_hosts_custom_port():
    captured: dict = {}

    def capturing_probe(host, username, password, port):
        captured["port"] = port

    hosts = {"ub20": {"host": "h", "username": "u", "password": "p", "port": 2222}}
    probe_hosts(hosts, probe=capturing_probe)
    assert captured["port"] == 2222
