"""Tests for the cutip desktop command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from cutip.cli.main import app

runner = CliRunner()


def test_desktop_no_cutip_yaml_exits(tmp_path):
    result = runner.invoke(app, ["desktop", "--path", str(tmp_path)])
    assert result.exit_code != 0
    assert "No cutip.yaml found" in result.output


def test_desktop_connection_refused(tmp_path):
    config = {"apiVersion": "cutip/v1", "project": {"name": "test-proj"}}
    (tmp_path / "cutip.yaml").write_text(yaml.dump(config))

    result = runner.invoke(app, ["desktop", "--path", str(tmp_path), "--url", "http://localhost:19999"])
    assert result.exit_code != 0
    assert "Could not connect" in result.output


def test_desktop_success(tmp_path):
    config = {"apiVersion": "cutip/v1", "project": {"name": "test-proj"}}
    (tmp_path / "cutip.yaml").write_text(yaml.dump(config))

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"id": "abc123"}).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("cutip.cli.commands.desktop.urllib.request.urlopen", return_value=mock_resp):
        result = runner.invoke(app, ["desktop", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "abc123" in result.output
        assert "/graph" in result.output
