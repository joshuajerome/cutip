#!/usr/bin/env python3
"""
analyze-doc-coverage.py

Uses Claude to analyze changed Python source files and identify documentation
gaps. Prompt is loaded from .jenkins/prompts/analyze-doc-coverage.md.

Environment variables:
  ANTHROPIC_API_KEY  - Anthropic API key

Exit 0 always — informational stage.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import anthropic

REPO_ROOT = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)
PROMPT_FILE = REPO_ROOT / ".jenkins" / "prompts" / "analyze-doc-coverage.md"
CHANGED_FILES_PATH = "/tmp/changed_files.txt"
DOCS_DIR = REPO_ROOT / "docs"

MAX_FILE_BYTES = 8_000
MAX_DOCS_BYTES = 20_000


def _changed_files_block() -> str:
    if not Path(CHANGED_FILES_PATH).exists():
        return "(no changed files list found)"
    paths = [
        line.strip()
        for line in Path(CHANGED_FILES_PATH).read_text().splitlines()
        if line.strip().endswith(".py")
    ]
    if not paths:
        return "(no Python files changed)"
    parts = []
    for p in paths:
        try:
            content = (REPO_ROOT / p).read_text(errors="replace")[:MAX_FILE_BYTES]
        except FileNotFoundError:
            try:
                content = subprocess.check_output(
                    ["git", "show", f"HEAD~1:{p}"], text=True, cwd=REPO_ROOT
                )[:MAX_FILE_BYTES]
                content = f"[DELETED]\n{content}"
            except subprocess.CalledProcessError:
                content = "[FILE NOT FOUND]"
        parts.append(f"### {p}\n```python\n{content}\n```")
    return "\n\n".join(parts)


def _docs_block() -> str:
    if not DOCS_DIR.exists():
        return "(docs/ directory not found)"
    parts = []
    total = 0
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        text = md_file.read_text(errors="replace")
        parts.append(f"=== {md_file.relative_to(REPO_ROOT)} ===\n{text}")
        total += len(text)
        if total >= MAX_DOCS_BYTES:
            parts.append("...[docs truncated]...")
            break
    return "\n\n".join(parts)


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    changed_block = _changed_files_block()
    if "no Python files changed" in changed_block or "no changed files list" in changed_block:
        print("[analyze-doc-coverage] No Python files changed — skipping.")
        return

    prompt = (
        PROMPT_FILE.read_text()
        .replace("{{changed_files}}", changed_block)
        .replace("{{docs}}", _docs_block())
    )

    client = anthropic.Anthropic(api_key=api_key)
    print("[analyze-doc-coverage] Calling Claude to review documentation coverage...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    report = message.content[0].text
    print("\n" + report)

    out = Path("/tmp/doc-coverage-report.md")
    out.write_text(report)
    print(f"\n[analyze-doc-coverage] Full report saved to {out}")


if __name__ == "__main__":
    main()
