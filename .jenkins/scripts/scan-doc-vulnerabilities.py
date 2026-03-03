#!/usr/bin/env python3
"""
scan-doc-vulnerabilities.py

Uses Claude to scan docs/ for accidentally included credentials, sensitive
paths, and broken external links.
Prompt is loaded from .jenkins/prompts/scan-doc-vulnerabilities.md.

Environment variables:
  ANTHROPIC_API_KEY  - Anthropic API key

Exit 0 — no HIGH findings.
Exit 1 — one or more HIGH-severity findings.
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
PROMPT_FILE = REPO_ROOT / ".jenkins" / "prompts" / "scan-doc-vulnerabilities.md"
DOCS_DIR = REPO_ROOT / "docs"

MAX_DOCS_BYTES = 24_000


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


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    prompt = PROMPT_FILE.read_text().replace("{{docs}}", _docs_block())

    client = anthropic.Anthropic(api_key=api_key)
    print("[scan-doc-vulnerabilities] Calling Claude to scan for sensitive content...")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response = message.content[0].text
    print("\n" + response)

    out = REPO_ROOT / "claude-reports" / "scan-doc-vulnerabilities.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(response)

    if "VERDICT: FAIL" in response:
        print("\n[scan-doc-vulnerabilities] HIGH-severity findings — resolve before merging.")
        return 1

    print("\n[scan-doc-vulnerabilities] No HIGH-severity issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
