#!/usr/bin/env python3
"""
Generate an automated code fix for a GitHub issue using the Claude API.

Called by issue-resolve.yml after a /approve comment is received.
Reads relevant source files, generates a minimal fix, writes changed files to disk,
and outputs a markdown summary to stdout (posted as an issue comment by the workflow).

Environment variables (set by the workflow):
  ANTHROPIC_API_KEY  - Anthropic API key (from repo secret)
  ISSUE_NUMBER       - GitHub issue number
  ISSUE_TITLE        - Issue title
  ISSUE_BODY         - Issue body (markdown)
  DIAGNOSIS_FILE     - Path to file containing Claude's prior diagnosis
  CAP_ID             - Capability ID for this fix (e.g., cap007)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# All source files that could potentially need a change
ALL_SOURCE_FILES = [
    "cutip/backends/podman/backend.py",
    "cutip/cli/commands/run.py",
    "cutip/cli/commands/validate.py",
    "cutip/cli/commands/ls.py",
    "cutip/cli/commands/show.py",
    "cutip/cli/commands/plan.py",
    "cutip/cli/commands/init.py",
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
    "cutip/utils/logging.py",
    "cutip/workspace/discovery.py",
    "cutip/workspace/registry.py",
    "cutip/workspace/scaffold.py",
]


def _env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"ERROR: environment variable {key!r} is not set", file=sys.stderr)
        sys.exit(1)
    return val


def _build_source_context() -> str:
    parts = []
    for rel_path in ALL_SOURCE_FILES:
        path = REPO_ROOT / rel_path
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
            parts.append(f"### {rel_path}\n```python\n{content}\n```")
        except Exception as exc:
            print(f"WARNING: could not read {rel_path}: {exc}", file=sys.stderr)
    return "\n\n".join(parts)


def generate_fix(
    issue_number: str,
    issue_title: str,
    issue_body: str,
    diagnosis: str,
    cap_id: str,
    source_context: str,
) -> tuple[dict[str, str], str]:
    """
    Call Claude to generate a minimal code fix.

    Returns:
        file_changes: dict mapping relative file path → complete new file content
        summary: markdown summary of changes (for the issue comment)
    """
    client = anthropic.Anthropic()

    prompt = f"""You are a senior engineer maintaining CUTIP (Container Unit Templates in Python) — \
a deterministic framework for defining and orchestrating container environments using Podman.

A user filed issue #{issue_number} and you previously diagnosed the root cause. \
Now generate a minimal, correct code fix.

## Issue #{issue_number}: {issue_title}

{issue_body or "_No description provided._"}

## Prior Diagnosis

{diagnosis}

## Current Source Code

{source_context}

---

Generate the minimal fix. Respond in exactly two parts separated by `---SUMMARY---` on its own line:

**Part 1:** A JSON object where:
- Keys are relative file paths (e.g., `"cutip/cli/commands/run.py"`)
- Values are the **complete** new file contents (not diffs, not excerpts — full file text)
- Only include files that actually need to change

Wrap the JSON in a ```json code block.

**Part 2:** A concise markdown summary (3–8 bullet points) of:
- What changed and in which file(s)
- Why the change fixes the issue
- Any caveats or limitations of the automated fix

Example response structure:

```json
{{
  "cutip/some/file.py": "#!/usr/bin/env python3\\n..."
}}
```
---SUMMARY---
- Fixed null-check in `cutip/some/file.py:42` to handle missing key
- Added `KeyError` guard in the `_validate_vars` path
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text

    # Split on ---SUMMARY---
    parts = response_text.split("---SUMMARY---", 1)
    json_part = parts[0].strip()
    summary = parts[1].strip() if len(parts) > 1 else "_No summary provided._"

    # Strip code fences from the JSON part
    if "```json" in json_part:
        json_part = json_part.split("```json", 1)[1]
        if "```" in json_part:
            json_part = json_part.rsplit("```", 1)[0]
    elif "```" in json_part:
        json_part = json_part.split("```", 1)[1]
        if "```" in json_part:
            json_part = json_part.rsplit("```", 1)[0]

    try:
        file_changes: dict[str, str] = json.loads(json_part.strip())
    except json.JSONDecodeError as exc:
        print(f"ERROR: Could not parse Claude's response as JSON: {exc}", file=sys.stderr)
        print(f"--- Raw response ---\n{response_text}\n---", file=sys.stderr)
        sys.exit(1)

    return file_changes, summary


def apply_fix(file_changes: dict[str, str]) -> list[str]:
    """Write changed files to disk. Returns list of relative paths written."""
    written = []
    for rel_path, content in file_changes.items():
        path = REPO_ROOT / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(rel_path)
        print(f"  Wrote {rel_path}", file=sys.stderr)
    return written


def main() -> None:
    issue_number = _env("ISSUE_NUMBER")
    issue_title = _env("ISSUE_TITLE")
    issue_body = os.environ.get("ISSUE_BODY", "").strip()
    diagnosis_file = _env("DIAGNOSIS_FILE")
    cap_id = _env("CAP_ID")

    diagnosis_path = Path(diagnosis_file)
    if not diagnosis_path.exists():
        print(f"ERROR: diagnosis file not found: {diagnosis_file}", file=sys.stderr)
        sys.exit(1)
    diagnosis = diagnosis_path.read_text(encoding="utf-8").strip()
    if not diagnosis:
        print("ERROR: diagnosis file is empty", file=sys.stderr)
        sys.exit(1)

    print(
        f"Generating fix for issue #{issue_number} ({cap_id}): {issue_title}",
        file=sys.stderr,
    )

    source_context = _build_source_context()
    print(
        f"Loaded context from {source_context.count('###')} source files.",
        file=sys.stderr,
    )

    file_changes, summary = generate_fix(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        diagnosis=diagnosis,
        cap_id=cap_id,
        source_context=source_context,
    )

    if not file_changes:
        print("ERROR: Claude returned no file changes.", file=sys.stderr)
        sys.exit(1)

    written = apply_fix(file_changes)
    print(f"Applied fix to {len(written)} file(s).", file=sys.stderr)

    # Stdout output is captured by the workflow and posted as a GitHub comment
    print(summary)
    print()
    print("**Files changed:**")
    for path in written:
        print(f"- `{path}`")


if __name__ == "__main__":
    main()
