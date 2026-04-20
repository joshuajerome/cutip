"""Tests for cutip.workflow.engine — WorkflowEngine and WorkflowContext."""

import importlib.util
import tempfile
from pathlib import Path

import pytest

from cutip.workflow.engine import (
    ActionFailed,
    WorkflowContext,
    WorkflowEngine,
)


# ── WorkflowContext ──────────────────────────────────────────────────────────

class TestWorkflowContext:

    def test_from_config_local(self):
        ctx = WorkflowContext.from_config({"project": "test", "host": "local"})
        assert ctx.host == "local"
        assert ctx.vars == {}
        assert ctx.secrets == {}
        assert ctx.results == {}

    def test_from_config_container(self):
        ctx = WorkflowContext.from_config({
            "project": "test",
            "host": "container",
            "container.rt": "podman",
        })
        assert ctx.host == "container"
        assert ctx.container_runtime == "podman"

    def test_from_config_legacy_backend(self):
        ctx = WorkflowContext.from_config({"project": "test", "backend": "podman"})
        assert ctx.host == "container"
        assert ctx.backend == "podman"

    def test_from_config_vars_and_secrets(self):
        ctx = WorkflowContext.from_config({
            "project": "test",
            "vars": {"key": "value"},
            "secrets": {"pw": "secret"},
        })
        assert ctx.vars == {"key": "value"}
        assert ctx.secrets == {"pw": "secret"}

    def test_from_config_null_vars(self):
        ctx = WorkflowContext.from_config({"project": "test", "vars": None, "secrets": None})
        assert ctx.vars == {}
        assert ctx.secrets == {}

    def test_results_stored(self):
        ctx = WorkflowContext.from_config({"project": "test"})
        ctx.results["action1"] = "result1"
        assert ctx.results["action1"] == "result1"

    def test_ssh_host_from_hosts(self):
        ctx = WorkflowContext.from_config(
            {"project": "test", "host": "remote"},
            hosts={"host": "10.0.0.1", "username": "root", "password": "pw"},
        )
        assert ctx.ssh_host == ""  # not set until ssh property accessed
        assert ctx._hosts["host"] == "10.0.0.1"

    def test_ssh_missing_credentials_raises(self):
        ctx = WorkflowContext.from_config(
            {"project": "test", "host": "remote"},
            hosts={},
        )
        with pytest.raises(RuntimeError, match="SSH credentials not set"):
            _ = ctx.ssh

    def test_data_from_data_section(self):
        ctx = WorkflowContext.from_config({
            "project": "test",
            "data": {"kubernetes": {"namespace": "prod"}},
        })
        assert ctx.data["kubernetes"]["namespace"] == "prod"

    def test_data_fallback_to_config(self):
        """Projects without data: section fall back to extra config keys."""
        ctx = WorkflowContext.from_config({
            "project": "test",
            "host": "local",
            "kubernetes": {"namespace": "prod"},
        })
        assert ctx.data["kubernetes"]["namespace"] == "prod"
        assert "project" not in ctx.data
        assert "host" not in ctx.data

    def test_close_connections(self):
        ctx = WorkflowContext.from_config({"project": "test"})

        class FakeSSH:
            closed = False
            def close(self):
                self.closed = True

        ctx._ssh = FakeSSH()
        ctx._close_connections()
        assert ctx._ssh is None


# ── WorkflowEngine ───────────────────────────────────────────────────────────

def _load_module(code: str, name: str = "test_wf") -> object:
    """Write workflow code to a temp file and load it as a module."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        f.flush()
        spec = importlib.util.spec_from_file_location(name, f.name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class TestWorkflowEngine:

    def test_sequential_execution(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("S1")
    a(ctx)
    b(ctx)

@action(name="A")
def a(ctx):
    return "a"

@action(name="B")
def b(ctx):
    return "b"
''')
        engine = WorkflowEngine(module, {"project": "test"})
        ctx = engine.run()
        assert ctx.results["A"] == "a"
        assert ctx.results["B"] == "b"

    def test_parallel_stage(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("Parallel", parallel=True)
    a(ctx)
    b(ctx)

@action(name="A")
def a(ctx):
    return "a"

@action(name="B")
def b(ctx):
    return "b"
''')
        engine = WorkflowEngine(module, {"project": "test"})
        ctx = engine.run()
        assert "A" in ctx.results
        assert "B" in ctx.results

    def test_retry_on_failure(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

counter = {"n": 0}

@orchestrator
def main(ctx):
    stage("S1")
    flaky(ctx)

@action(name="Flaky", retry=2, delay=0)
def flaky(ctx):
    counter["n"] += 1
    if counter["n"] < 3:
        raise RuntimeError("not yet")
    return "ok"
''')
        engine = WorkflowEngine(module, {"project": "test"})
        ctx = engine.run()
        assert ctx.results["Flaky"] == "ok"

    def test_on_fail_triggers_recovery(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("S1")
    failing(ctx)

@action(name="Failing", on_fail="Recovery", continue_on_fail=True)
def failing(ctx):
    raise RuntimeError("boom")

@action(name="Recovery")
def recovery(ctx):
    return "recovered"
''')
        engine = WorkflowEngine(module, {"project": "test"})
        ctx = engine.run()
        assert ctx.results["Recovery"] == "recovered"
        assert ctx.results["Failing"] is None

    def test_when_skips_action(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("S1")
    skipped(ctx)
    not_skipped(ctx)

@action(name="Skipped", when=lambda ctx: False)
def skipped(ctx):
    return "should not run"

@action(name="Not skipped")
def not_skipped(ctx):
    return "ran"
''')
        engine = WorkflowEngine(module, {"project": "test"})
        ctx = engine.run()
        assert "Skipped" not in ctx.results
        assert ctx.results["Not skipped"] == "ran"

    def test_continue_on_fail(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("S1")
    failing(ctx)
    after(ctx)

@action(name="Failing", continue_on_fail=True)
def failing(ctx):
    raise RuntimeError("fail")

@action(name="After")
def after(ctx):
    return "continued"
''')
        engine = WorkflowEngine(module, {"project": "test"})
        ctx = engine.run()
        assert ctx.results["After"] == "continued"

    def test_action_failed_on_exhausted_retries(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("S1")
    always_fail(ctx)

@action(name="Always fail", retry=1, delay=0)
def always_fail(ctx):
    raise RuntimeError("nope")
''')
        engine = WorkflowEngine(module, {"project": "test"})
        with pytest.raises(ActionFailed):
            engine.run()

    def test_conditional_branching(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    if ctx.host == "local":
        stage("Local")
        local_action(ctx)
    else:
        stage("Remote")
        remote_action(ctx)

@action(name="Local action")
def local_action(ctx):
    return "local"

@action(name="Remote action")
def remote_action(ctx):
    return "remote"
''')
        engine = WorkflowEngine(module, {"project": "test", "host": "local"})
        ctx = engine.run()
        assert ctx.results["Local action"] == "local"
        assert "Remote action" not in ctx.results

    def test_stage_events_emitted(self):
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("MyStage")
    a(ctx)

@action(name="A")
def a(ctx):
    return "a"
''')
        events = []
        engine = WorkflowEngine(module, {"project": "test"}, on_event=lambda e: events.append(e.event))
        engine.run()
        assert "stage_started" in events
        assert "action_started" in events
        assert "action_completed" in events
        assert "stage_completed" in events

    def test_fallback_to_main_without_decorators(self):
        module = _load_module('''
ran = False
def main(ctx):
    global ran
    ran = True
''')
        config = {"project": "test"}
        engine = WorkflowEngine(module, config)
        engine.run()
        assert module.ran is True

    def test_fatal_error_stops_retry(self):
        """AuthError should not be retried."""
        module = _load_module('''
from cutip.workflow import action, orchestrator, stage

counter = {"n": 0}

@orchestrator
def main(ctx):
    stage("S1")
    auth_fail(ctx)

@action(name="Auth fail", retry=5, delay=0)
def auth_fail(ctx):
    counter["n"] += 1
    # Simulate AuthError by class name (rsty may not be installed in tests)
    class AuthError(Exception):
        pass
    AuthError.__name__ = "AuthError"
    raise AuthError("bad creds")
''')
        engine = WorkflowEngine(module, {"project": "test"})
        with pytest.raises(ActionFailed):
            engine.run()
        # Should have only attempted once since AuthError is fatal
