"""Tests for cutip.processes — background-run state directory."""

from __future__ import annotations

import json

import pytest

from cutip import processes


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    """Redirect ~/.cutip/processes/ to a tmp dir for each test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Re-resolve home in case any path was cached
    yield tmp_path


def _make_meta(cu_id: str, **overrides) -> processes.Meta:
    defaults = dict(
        cu_id=cu_id,
        project="test-project",
        project_path="/tmp/test.yaml",
        workflow_path="/tmp/test.workflow.py",
        cwd="/tmp",
        started_at=processes.now_iso(),
    )
    defaults.update(overrides)
    return processes.Meta(**defaults)


def test_make_cu_id_format():
    cu_id = processes.make_cu_id("my-project")
    parts = cu_id.split("-")
    assert parts[0] == "my"
    assert parts[1] == "project"
    # Last part is 4 hex chars
    assert len(parts[-1]) == 4
    assert all(c in "0123456789abcdef" for c in parts[-1])


def test_make_cu_id_collision_handling():
    """Two cu-ids for the same project should differ."""
    a = processes.make_cu_id("dup")
    # Force collision by writing a meta first
    processes.write_meta(_make_meta(a))
    b = processes.make_cu_id("dup")
    assert a != b


def test_write_read_meta_roundtrip():
    cu_id = "test-1234"
    m = _make_meta(cu_id, host_pid=999, status="running")
    processes.write_meta(m)
    m2 = processes.read_meta(cu_id)
    assert m2.cu_id == cu_id
    assert m2.host_pid == 999
    assert m2.status == "running"
    # Verify on-disk JSON shape
    raw = json.loads(processes.meta_path(cu_id).read_text())
    assert raw["cu_id"] == cu_id
    assert raw["host_pid"] == 999


def test_update_meta():
    cu_id = "test-update"
    processes.write_meta(_make_meta(cu_id))
    processes.update_meta(cu_id, status="succeeded", exit_code=0)
    m = processes.read_meta(cu_id)
    assert m.status == "succeeded"
    assert m.exit_code == 0


def test_list_processes_newest_first():
    a = _make_meta("test-alpha")
    b = _make_meta("test-beta")
    a.started_at = "2026-04-28T10:00:00+00:00"
    b.started_at = "2026-04-28T11:00:00+00:00"  # 1 hour newer
    processes.write_meta(a)
    processes.write_meta(b)
    listed = list(processes.list_processes())
    ids = [m.cu_id for m in listed]
    assert ids[0] == "test-beta"  # newest first
    assert "test-alpha" in ids


def test_resolve_cu_id_exact():
    processes.write_meta(_make_meta("exact-match-abcd"))
    assert processes.resolve_cu_id("exact-match-abcd") == "exact-match-abcd"


def test_resolve_cu_id_prefix():
    processes.write_meta(_make_meta("prefix-test-xxxx"))
    assert processes.resolve_cu_id("prefix-test") == "prefix-test-xxxx"


def test_resolve_cu_id_suffix():
    processes.write_meta(_make_meta("project-aaaa"))
    assert processes.resolve_cu_id("aaaa") == "project-aaaa"


def test_resolve_cu_id_ambiguous_prefix():
    processes.write_meta(_make_meta("amb-1111"))
    processes.write_meta(_make_meta("amb-2222"))
    with pytest.raises(ValueError, match="Ambiguous"):
        processes.resolve_cu_id("amb")


def test_resolve_cu_id_not_found():
    with pytest.raises(ValueError, match="No cutip process"):
        processes.resolve_cu_id("nonexistent-xxxx")


def test_remote_pid_tracking():
    cu_id = "remote-test-abcd"
    processes.write_meta(_make_meta(cu_id))

    p1 = processes.RemoteProc(host="h1", username="u1", pid=100, label="make-A")
    p2 = processes.RemoteProc(host="h2", username="u1", pid=200, label="make-B")
    processes.append_remote_pid(cu_id, p1)
    processes.append_remote_pid(cu_id, p2)

    listed = processes.list_remote_pids(cu_id)
    assert len(listed) == 2
    assert listed[0].host == "h1"
    assert listed[1].pid == 200


def test_list_remote_pids_empty():
    cu_id = "no-remote-abcd"
    processes.write_meta(_make_meta(cu_id))
    assert processes.list_remote_pids(cu_id) == []


def test_stop_signaling():
    cu_id = "stop-test-abcd"
    processes.write_meta(_make_meta(cu_id))
    assert processes.is_stop_requested(cu_id) is False
    processes.request_stop(cu_id)
    assert processes.is_stop_requested(cu_id) is True
    processes.clear_stop(cu_id)
    assert processes.is_stop_requested(cu_id) is False


def test_is_terminal():
    assert processes.is_terminal("succeeded") is True
    assert processes.is_terminal("failed") is True
    assert processes.is_terminal("stopped") is True
    assert processes.is_terminal("running") is False
    assert processes.is_terminal("starting") is False


def test_prune_keeps_running():
    """Running processes should never be pruned regardless of age."""
    cu_id = "running-old-abcd"
    # Old started_at, but status running
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(
        timespec="seconds"
    )
    m = _make_meta(cu_id, status="running")
    m.started_at = old
    processes.write_meta(m)

    pruned = processes.prune(older_than_days=7)
    assert cu_id not in pruned
    assert processes.process_dir(cu_id).exists()


def test_prune_removes_old_completed():
    cu_id = "old-completed-abcd"
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(
        timespec="seconds"
    )
    m = _make_meta(cu_id, status="succeeded")
    m.started_at = old
    m.finished_at = old
    processes.write_meta(m)

    pruned = processes.prune(older_than_days=7)
    assert cu_id in pruned
    assert not processes.process_dir(cu_id).exists()


def test_prune_keeps_recent_completed():
    cu_id = "recent-ok-abcd"
    m = _make_meta(cu_id, status="succeeded")
    m.finished_at = processes.now_iso()
    processes.write_meta(m)

    pruned = processes.prune(older_than_days=7)
    assert cu_id not in pruned


def test_path_helpers():
    cu_id = "paths-test-abcd"
    assert processes.process_dir(cu_id).name == cu_id
    assert processes.meta_path(cu_id).name == "meta.json"
    assert processes.stdout_path(cu_id).name == "stdout.log"
    assert processes.stderr_path(cu_id).name == "stderr.log"
    assert processes.remote_path(cu_id).name == "remote.json"
    assert processes.stop_lock_path(cu_id).name == "stop.lock"
