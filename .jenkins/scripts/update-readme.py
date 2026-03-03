#!/usr/bin/env python3
"""
update-readme.py

Uses Claude to detect drift between README.md and the live CLI / pyproject.toml
version, then write corrected sections.
Prompt is loaded from .jenkins/prompts/update-readme.md.

Environment variables:
  ANTHROPIC_API_KEY  - Anthropic API key

Exit 0 always — informational; a human or follow-up automation applies the diff.
Exit 1 if README.md is missing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPT_FILE = REPO_ROOT / ".jenkins" / "prompts" / "update-readme.md"
README_PATH = REPO_ROOT / "README.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _cli_help() -> str:
    try:
        return subprocess.check_output(
            ["uv", "run", "cutip", "--help"],
            text=True,
            cwd=REPO_ROOT,
            timeout=30,
        ).strip()
    except Exception as exc:
        return f"(could not run cutip --help: {exc})"


def _version() -> str:
    if not PYPROJECT_PATH.exists():
        return "(unknown)"
    match = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT_PATH.read_text(), re.MULTILINE)
    return match.group(1) if match else "(unknown)"


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    if not README_PATH.exists():
        print("[update-readme] README.md not found.", file=sys.stderr)
        return 1

    prompt = (
        PROMPT_FILE.read_text()
        .replace("{{readme}}", README_PATH.read_text())
        .replace("{{cli_help}}", _cli_help())
        .replace("{{version}}", _version())
    )

    client = anthropic.Anthropic(api_key=api_key)
    print("[update-readme] Calling Claude to check README for drift...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response = message.content[0].text
    parts = response.split("---SPLIT---", 1)

    drift_report = parts[0].strip()
    updated_sections = parts[1].strip() if len(parts) == 2 else ""

    print("\n## Drift Report\n")
    print(drift_report)

    if updated_sections and "No updates required" not in updated_sections:
        out = Path("/tmp/readme-updated-sections.md")
        out.write_text(updated_sections)
        print(f"\n## Updated Sections\n\n{updated_sections}")
        print(f"\n[update-readme] Updated sections saved to {out}")
        print("[update-readme] Apply them manually or via a docs/readme-update branch.")
    else:
        print("\n[update-readme] README is up to date — no changes needed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
