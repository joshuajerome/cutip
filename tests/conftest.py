"""Shared test fixtures for cutip tests."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary cutip project directory with config + workflow."""

    def _create(
        name="test-project",
        host="local",
        vars=None,
        secrets=None,
        workflow_code=None,
        config_extra="",
    ):
        project_file = tmp_path / f"{name}.yaml"
        workflow_file = tmp_path / f"{name}.workflow.py"

        vars_block = ""
        if vars:
            vars_block = "vars:\n" + "".join(f"  {k}: \"{v}\"\n" for k, v in vars.items())

        secrets_block = ""
        if secrets:
            secrets_block = "secrets:\n" + "".join(f"  {k}: \"{v}\"\n" for k, v in secrets.items())

        project_file.write_text(
            f"project: {name}\n"
            f"host: {host}\n"
            f"{vars_block}"
            f"{secrets_block}"
            f"{config_extra}"
        )

        if workflow_code is None:
            workflow_code = '''
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("Test")
    hello(ctx)

@action(name="Hello")
def hello(ctx):
    return "hello"
'''

        workflow_file.write_text(workflow_code)

        return project_file, workflow_file

    return _create


@pytest.fixture
def simple_project(tmp_project):
    """A minimal working project."""
    project_file, workflow_file = tmp_project()
    return project_file, workflow_file
