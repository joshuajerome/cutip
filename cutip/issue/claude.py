"""Shared Claude API logic for issue diagnosis and fix generation."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _get_api_key() -> str:
    """Resolve Anthropic API key from environment."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print(
            "ERROR: ANTHROPIC_API_KEY not set. "
            "Set it in your environment or install cutip[ai].",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def _build_local_context(project_root: Path) -> str:
    """Build source context from the CUTIP codebase for Claude."""
    context_files = [
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

    # Try CUTIP source root (for development installs)
    cutip_root = Path(__file__).resolve().parent.parent.parent
    parts = []
    for rel_path in context_files:
        path = cutip_root / rel_path
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
            parts.append(f"### {rel_path}\n```python\n{content}\n```")
        except Exception:
            continue
    return "\n\n".join(parts)


def diagnose(title: str, body: str, context: str) -> str:
    """Run Claude diagnosis on an issue. Returns markdown diagnosis."""
    try:
        import anthropic
    except ImportError:
        print(
            "ERROR: anthropic package not installed. Run: uv pip install cutip[ai]",
            file=sys.stderr,
        )
        sys.exit(1)

    _get_api_key()
    client = anthropic.Anthropic()

    prompt = f"""You are a senior engineer maintaining CUTIP (Container Unit Templates in Python) — \
a deterministic framework for defining and orchestrating container environments using Docker/Podman.

A user has filed an issue. Diagnose the root cause and describe a concise fix approach.

## Issue: {title}

{body or "_No description provided._"}

## Relevant Source Code

{context}

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


def generate_fix(
    title: str,
    body: str,
    diagnosis_text: str,
    cap_id: str,
    context: str,
) -> tuple[dict[str, str], str]:
    """Generate a code fix via Claude. Returns (file_changes, summary)."""
    try:
        import anthropic
    except ImportError:
        print(
            "ERROR: anthropic package not installed. Run: uv pip install cutip[ai]",
            file=sys.stderr,
        )
        sys.exit(1)

    import json

    _get_api_key()
    client = anthropic.Anthropic()

    prompt = f"""You are a senior engineer maintaining CUTIP (Container Unit Templates in Python) — \
a deterministic framework for defining and orchestrating container environments using Docker/Podman.

A user filed an issue and you previously diagnosed the root cause. \
Now generate a minimal, correct code fix.

## Issue: {title}

{body or "_No description provided._"}

## Prior Diagnosis

{diagnosis_text}

## Current Source Code

{context}

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

    parts = response_text.split("---SUMMARY---", 1)
    json_part = parts[0].strip()
    summary = parts[1].strip() if len(parts) > 1 else "_No summary provided._"

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
        sys.exit(1)

    return file_changes, summary
