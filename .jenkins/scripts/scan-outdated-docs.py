#!/usr/bin/env python3
"""
scan-outdated-docs.py

Uses Claude to audit docs/ for stale references against the live source code.
Prompt is loaded from .jenkins/prompts/scan-outdated-docs.md.

Environment variables:
  ANTHROPIC_API_KEY  - Anthropic API key

Exit 0 — no HIGH findings.
Exit 1 — one or more HIGH-severity stale references found.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPT_FILE = REPO_ROOT / ".jenkins" / "prompts" / "scan-outdated-docs.md"
DOCS_DIR = REPO_ROOT / "docs"

SOURCE_KEY_FILES = [
    "cutip/cli/main.py",
    "cutip/cli/commands/run.py",
    "cutip/cli/commands/ls.py",
    "cutip/models/cards/container.py",
    "cutip/models/cards/image.py",
    "cutip/models/group.py",
    "cutip/models/unit.py",
    "CLAUDE.md",
    "README.md",
]
MAX_DOCS_BYTES = 20_000
MAX_SOURCE_BYTES = 12_000


def _docs_block() -> str:
    if not DOCS_DIR.exists():
        return "(docs/ not found)"
    parts = []
    total = 0
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        text = md_file.read_text(errors="replace")
        parts.append(f"=== {md_file.relative_to(REPO_ROOT)} ===\n{text}")
        total += len(text)
        if total >= MAX_DOCS_BYTES:
            parts.append("...[truncated]...")
            break
    return "\n\n".join(parts)


def _source_block() -> str:
    parts = []
    total = 0
    for p in SOURCE_KEY_FILES:
        path = REPO_ROOT / p
        if not path.exists():
            continue
        text = path.read_text(errors="replace")
        parts.append(f"=== {p} ===\n{text}")
        total += len(text)
        if total >= MAX_SOURCE_BYTES:
            parts.append("...[truncated]...")
            break
    return "\n\n".join(parts)


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    prompt = (
        PROMPT_FILE.read_text()
        .replace("{{docs}}", _docs_block())
        .replace("{{source}}", _source_block())
    )

    client = anthropic.Anthropic(api_key=api_key)
    print("[scan-outdated-docs] Calling Claude to audit documentation for stale content...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response = message.content[0].text
    print("\n" + response)

    if "VERDICT: FAIL" in response:
        print("\n[scan-outdated-docs] HIGH-severity stale references found — resolve before merging.")
        return 1

    print("\n[scan-outdated-docs] No HIGH-severity issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
