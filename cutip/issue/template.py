"""Issue YAML template generation and loading."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ISSUE_TEMPLATE = {
    "apiVersion": "cutip/v1",
    "kind": "Issue",
    "metadata": {
        "title": "",
        "slug": "",
        "github_number": None,
        "status": "draft",
    },
    "spec": {
        "description": ("## What happened\n\n## Steps to reproduce\n\n## Expected behavior\n"),
        "labels": ["bug"],
    },
}

ISSUES_DIR = ".cutip/issues"


def slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:40]


def issues_dir(project_root: Path) -> Path:
    """Return the issues directory, creating it if needed."""
    d = project_root / ISSUES_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_issue(project_root: Path, title: str) -> Path:
    """Create a new issue YAML file from template. Returns the file path."""
    slug = slugify(title)
    d = issues_dir(project_root)
    path = d / f"{slug}.issue.yaml"

    data = _deep_copy_template()
    data["metadata"]["title"] = title
    data["metadata"]["slug"] = slug

    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return path


def load_issue(path: Path) -> dict:
    """Load an issue YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("kind") != "Issue":
        raise ValueError(f"Not a valid issue file: {path}")
    return data


def save_issue(path: Path, data: dict) -> None:
    """Save an issue YAML file."""
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def list_issues(project_root: Path) -> list[tuple[Path, dict]]:
    """List all issue files with their data."""
    d = project_root / ISSUES_DIR
    if not d.exists():
        return []
    results = []
    for p in sorted(d.glob("*.issue.yaml")):
        try:
            results.append((p, load_issue(p)))
        except (ValueError, yaml.YAMLError):
            continue
    return results


def _deep_copy_template() -> dict:
    """Return a deep copy of the issue template."""
    import copy

    return copy.deepcopy(ISSUE_TEMPLATE)
