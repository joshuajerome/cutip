"""Tests for cutip.workflow decorators and introspection."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

from cutip.workflow import ActionMeta, action, orchestrator
from cutip.workflow.decorators import _ACTION_ATTR, _ORCHESTRATOR_ATTR
from cutip.workflow.introspect import (
    extract_action_order,
    extract_action_order_from_module,
    get_module_actions,
    get_orchestrator,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Decorator unit tests ─────────────────────────────────────────────────────


def test_action_decorator_attaches_meta():
    @action(name="Test Action", description="A test", container="my-ctr")
    def my_action(ctx):
        pass

    meta = getattr(my_action, _ACTION_ATTR)
    assert isinstance(meta, ActionMeta)
    assert meta.name == "Test Action"
    assert meta.description == "A test"
    assert meta.container == "my-ctr"
    assert meta.depends_on == []


def test_orchestrator_decorator_marks_function():
    @orchestrator
    def main(ctx):
        pass

    assert getattr(main, _ORCHESTRATOR_ATTR) is True


def test_action_preserves_function_behavior():
    @action(name="Add One")
    def add_one(x):
        return x + 1

    assert add_one(5) == 6


def test_action_with_depends_on():
    @action(name="Step 2", depends_on=["Step 1"])
    def step_two(ctx):
        pass

    meta = getattr(step_two, _ACTION_ATTR)
    assert meta.depends_on == ["Step 1"]


def test_action_with_container_hint():
    @action(name="Deploy", container="deploy-ctr")
    def deploy(ctx):
        pass

    meta = getattr(deploy, _ACTION_ATTR)
    assert meta.container == "deploy-ctr"


# ── Runtime introspection tests ──────────────────────────────────────────────


def _load_fixture_module():
    """Load the decorated workflow fixture as a module."""
    fixture_path = FIXTURES / "workflow_decorated.py"
    spec = importlib.util.spec_from_file_location("test_fixture_wf", fixture_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["test_fixture_wf"] = module
    spec.loader.exec_module(module)
    return module


def test_get_module_actions_returns_all_actions():
    module = _load_fixture_module()
    actions = get_module_actions(module)
    assert len(actions) == 3
    assert "start_db" in actions
    assert "wait_for_db" in actions
    assert "start_web" in actions
    assert actions["start_db"].name == "Start DB"
    assert actions["wait_for_db"].container == "cutip-db"


def test_get_orchestrator_finds_decorated():
    module = _load_fixture_module()
    orch = get_orchestrator(module)
    assert orch is not None
    assert getattr(orch, _ORCHESTRATOR_ATTR) is True


# ── AST-based action order extraction ────────────────────────────────────────


def test_extract_action_order_simple():
    actions = extract_action_order(FIXTURES / "workflow_decorated.py")
    assert len(actions) == 3
    assert actions[0].name == "Start DB"
    assert actions[1].name == "Wait for DB"
    assert actions[2].name == "Start Web"


def test_extract_action_order_no_decorators_returns_empty(tmp_path):
    wf = tmp_path / "workflow.py"
    wf.write_text(
        textwrap.dedent("""\
        def main(ctx):
            ctx.container("foo").start()
        """)
    )
    actions = extract_action_order(wf)
    assert actions == []


def test_extract_action_order_fallback_to_definition_order(tmp_path):
    """When orchestrator body has no recognized action calls, fall back to definition order."""
    wf = tmp_path / "workflow.py"
    wf.write_text(
        textwrap.dedent("""\
        from cutip.workflow import action, orchestrator

        @action(name="Alpha")
        def alpha(ctx):
            pass

        @action(name="Beta")
        def beta(ctx):
            pass

        @orchestrator
        def main(ctx):
            # Dynamic dispatch — no direct calls to alpha/beta
            for fn in [alpha, beta]:
                fn(ctx)
        """)
    )
    actions = extract_action_order(wf)
    assert len(actions) == 2
    # Falls back to definition order since the for-loop iteration
    # doesn't produce direct ast.Call nodes matching function names
    assert actions[0].name == "Alpha"
    assert actions[1].name == "Beta"


def test_extract_action_order_from_module():
    module = _load_fixture_module()
    actions = extract_action_order_from_module(module)
    assert len(actions) == 3
    assert actions[0].name == "Start DB"
