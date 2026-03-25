"""Tests for stage() boundary detection in AST parser."""

import textwrap
from pathlib import Path

from cutip.workflow.decorators import StageMeta
from cutip.workflow.introspect import extract_staged_action_order


def _write_workflow(tmp_path: Path, code: str) -> Path:
    p = tmp_path / "workflow.py"
    p.write_text(textwrap.dedent(code), encoding="utf-8")
    return p


def test_no_stages_returns_single_group(tmp_path):
    path = _write_workflow(tmp_path, """\
        from cutip.workflow import action, orchestrator

        @action(name="A")
        def a(ctx): pass

        @action(name="B")
        def b(ctx): pass

        @orchestrator
        def main(ctx):
            a(ctx)
            b(ctx)
    """)
    groups = extract_staged_action_order(path)
    assert len(groups) == 1
    assert len(groups[0].actions) == 2
    assert groups[0].actions[0].name == "A"
    assert groups[0].actions[1].name == "B"


def test_titled_stages_group_actions(tmp_path):
    path = _write_workflow(tmp_path, """\
        from cutip.workflow import action, orchestrator, stage

        @action(name="Check SSH")
        def check_ssh(ctx): pass

        @action(name="Check DB")
        def check_db(ctx): pass

        @action(name="Deploy")
        def deploy(ctx): pass

        @action(name="Verify")
        def verify(ctx): pass

        @orchestrator
        def main(ctx):
            stage("Validation")
            check_ssh(ctx)
            check_db(ctx)

            stage("Operations")
            deploy(ctx)

            stage("Post-check")
            verify(ctx)
    """)
    groups = extract_staged_action_order(path)
    assert len(groups) == 3

    assert groups[0].stage.title == "Validation"
    assert len(groups[0].actions) == 2
    assert groups[0].actions[0].name == "Check SSH"
    assert groups[0].actions[1].name == "Check DB"

    assert groups[1].stage.title == "Operations"
    assert len(groups[1].actions) == 1
    assert groups[1].actions[0].name == "Deploy"

    assert groups[2].stage.title == "Post-check"
    assert len(groups[2].actions) == 1
    assert groups[2].actions[0].name == "Verify"


def test_untitled_stages_get_numbered(tmp_path):
    path = _write_workflow(tmp_path, """\
        from cutip.workflow import action, orchestrator, stage

        @action(name="A")
        def a(ctx): pass

        @action(name="B")
        def b(ctx): pass

        @orchestrator
        def main(ctx):
            stage()
            a(ctx)

            stage()
            b(ctx)
    """)
    groups = extract_staged_action_order(path)
    assert len(groups) == 2
    assert groups[0].stage.title == "Stage 1"
    assert groups[1].stage.title == "Stage 2"


def test_mixed_titled_and_untitled(tmp_path):
    path = _write_workflow(tmp_path, """\
        from cutip.workflow import action, orchestrator, stage

        @action(name="A")
        def a(ctx): pass

        @action(name="B")
        def b(ctx): pass

        @action(name="C")
        def c(ctx): pass

        @orchestrator
        def main(ctx):
            stage()
            a(ctx)

            stage("Operations")
            b(ctx)

            stage()
            c(ctx)
    """)
    groups = extract_staged_action_order(path)
    assert len(groups) == 3
    assert groups[0].stage.title == "Stage 1"
    assert groups[1].stage.title == "Operations"
    assert groups[2].stage.title == "Stage 3"


def test_stage_with_description(tmp_path):
    path = _write_workflow(tmp_path, """\
        from cutip.workflow import action, orchestrator, stage

        @action(name="A")
        def a(ctx): pass

        @orchestrator
        def main(ctx):
            stage("Setup", description="Initialize all resources")
            a(ctx)
    """)
    groups = extract_staged_action_order(path)
    assert len(groups) == 1
    assert groups[0].stage.title == "Setup"
    assert groups[0].stage.description == "Initialize all resources"


def test_stages_inside_with_block(tmp_path):
    """Stages inside a `with` block (like ssh.session) should be detected."""
    path = _write_workflow(tmp_path, """\
        from cutip.workflow import action, orchestrator, stage

        @action(name="Check")
        def check(ctx): pass

        @action(name="Deploy")
        def deploy(ctx): pass

        @orchestrator
        def main(ctx):
            with some_context() as conn:
                stage("Validate")
                check(ctx)

                stage("Execute")
                deploy(ctx)
    """)
    groups = extract_staged_action_order(path)
    assert len(groups) == 2
    assert groups[0].stage.title == "Validate"
    assert groups[0].actions[0].name == "Check"
    assert groups[1].stage.title == "Execute"
    assert groups[1].actions[0].name == "Deploy"


def test_actions_before_first_stage(tmp_path):
    """Actions before the first stage() go into an implicit group."""
    path = _write_workflow(tmp_path, """\
        from cutip.workflow import action, orchestrator, stage

        @action(name="Init")
        def init(ctx): pass

        @action(name="Work")
        def work(ctx): pass

        @orchestrator
        def main(ctx):
            init(ctx)

            stage("Main Work")
            work(ctx)
    """)
    groups = extract_staged_action_order(path)
    assert len(groups) == 2
    # First group has the pre-stage action, numbered
    assert groups[0].actions[0].name == "Init"
    assert groups[1].stage.title == "Main Work"
    assert groups[1].actions[0].name == "Work"


def test_no_actions_returns_empty(tmp_path):
    path = _write_workflow(tmp_path, """\
        from cutip.workflow import orchestrator

        @orchestrator
        def main(ctx):
            pass
    """)
    groups = extract_staged_action_order(path)
    assert len(groups) == 0
