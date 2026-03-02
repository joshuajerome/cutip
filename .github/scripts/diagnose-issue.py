#!/usr/bin/env python3
"""
Diagnose a GitHub issue using the Claude API.

Called by issue-diagnose.yml when the claude-review label is applied to an issue.
Outputs a structured markdown diagnosis to stdout, which the workflow posts as a comment.

Environment variables (set by the workflow):
  ANTHROPIC_API_KEY  - Anthropic API key (from repo secret)
  ISSUE_NUMBER       - GitHub issue number
  ISSUE_TITLE        - Issue title
  ISSUE_BODY         - Issue body (markdown)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Source files included as context for diagnosis (most issue-relevant paths first)
CONTEXT_FILES = [
    "cutip/backends/podman/backend.py",
    "cutip/cli/commands/run.py",
    "cutip/cli/main.py",
    "cutip/models/cards/container.py",
    "cutip/models/cards/image.py",
    "cutip/models/cards/network.py",
    "cutip/models/unit.py",
    "cutip/models/group.py",
    "cutip/context/workflow.py",
    "cutip/context/startup.py",
    "cutip/resolver/refs.py",
    "cutip/validation/graph.py",
    "cutip/utils/exceptions.py",
    "cutip/workspace/discovery.py",
    "cutip/workspace/registry.py",
]


def _env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"ERROR: environment variable {key!r} is not set", file=sys.stderr)
        sys.exit(1)
    return val


def _build_source_context() -> str:
    parts = []
    for rel_path in CONTEXT_FILES:
        path = REPO_ROOT / rel_path
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
            parts.append(f"### {rel_path}\n```python\n{content}\n```")
        except Exception as exc:
            print(f"WARNING: could not read {rel_path}: {exc}", file=sys.stderr)
    return "\n\n".join(parts)


def diagnose(
    issue_number: str,
    issue_title: str,
    issue_body: str,
    source_context: str,
) -> str:
    client = anthropic.Anthropic()

    prompt = f"""You are a senior engineer maintaining CUTIP (Container Unit Templates in Python) — \
a deterministic framework for defining and orchestrating container environments using Podman.

A user has filed a GitHub issue. Diagnose the root cause and describe a concise fix approach.

## Issue #{issue_number}: {issue_title}

{issue_body or "_No description provided._"}

## Relevant Source Code

{source_context}

---

Respond with a structured diagnosis in **exactly** this format (use the exact headings):

## Claude Diagnosis

**Root Cause:** (one sentence describing the fundamental problem)

**Affected Location:** `path/to/file.py:line_number` (one or more locations)

**What's Happening:** (2–4 sentences explaining the bug mechanically — what code path leads to the failure)

**Proposed Fix:** (2–5 sentences describing the minimal code change that will resolve it)

**Confidence:** High / Medium / Low — (one sentence explaining confidence level and any uncertainty)
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main() -> None:
    issue_number = _env("ISSUE_NUMBER")
    issue_title = _env("ISSUE_TITLE")
    issue_body = os.environ.get("ISSUE_BODY", "").strip()

    print(f"Diagnosing issue #{issue_number}: {issue_title}", file=sys.stderr)

    source_context = _build_source_context()
    print(
        f"Loaded context from {source_context.count('###')} source files.",
        file=sys.stderr,
    )

    diagnosis = diagnose(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        source_context=source_context,
    )

    print(diagnosis)


if __name__ == "__main__":
    main()
