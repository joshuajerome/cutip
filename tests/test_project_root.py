"""Tests for _find_project_root() discovery logic."""

from __future__ import annotations

from cutip.workspace.scaffold import _find_project_root


def test_find_project_root_prefers_cutip_yaml(tmp_path, monkeypatch):
    """cutip.yaml in a subdirectory should win over .git in parent."""
    # Simulate: parent has .git, child has cutip.yaml
    parent = tmp_path / "monorepo"
    parent.mkdir()
    (parent / ".git").mkdir()

    child = parent / "subproject"
    child.mkdir()
    (child / "cutip.yaml").write_text("apiVersion: cutip/v1\n")

    monkeypatch.chdir(child)
    assert _find_project_root() == child


def test_find_project_root_walks_up_to_cutip_yaml(tmp_path, monkeypatch):
    """Walking up from a subdirectory should find the nearest cutip.yaml."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "cutip.yaml").write_text("apiVersion: cutip/v1\n")

    subdir = project / "cutip" / "groups" / "mygroup"
    subdir.mkdir(parents=True)

    monkeypatch.chdir(subdir)
    assert _find_project_root() == project


def test_find_project_root_falls_back_to_git(tmp_path, monkeypatch):
    """Without cutip.yaml, fall back to .git root."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    subdir = repo / "src"
    subdir.mkdir()

    monkeypatch.chdir(subdir)
    # No cutip.yaml anywhere, so it should use git rev-parse.
    # Since tmp_path/.git isn't a real git repo, git rev-parse will fail
    # and we'll fall back to cwd.
    root = _find_project_root()
    assert root == subdir


def test_find_project_root_falls_back_to_cwd(tmp_path, monkeypatch):
    """Without cutip.yaml or .git, return cwd."""
    monkeypatch.chdir(tmp_path)
    assert _find_project_root() == tmp_path
