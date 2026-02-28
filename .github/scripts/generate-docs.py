#!/usr/bin/env python3
"""
Auto-generate patch notes and capability registry entries via Claude API.

Called by docs-generate.yml after a feat/* or bug/* branch merges to staging.

Environment variables (set by the workflow):
  ANTHROPIC_API_KEY  - Anthropic API key (from repo secret)
  CAP_ID             - Capability ID, e.g. "cap001"
  SOURCE_BRANCH      - Source branch name, e.g. "feat/cap001-initial-scaffold"
  COMMIT_MSG         - The merge commit message
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CAPABILITIES_FILE = REPO_ROOT / "docs" / "capabilities.md"
PATCH_NOTES_FILE = REPO_ROOT / "docs" / "patch-notes.md"


def _env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"ERROR: environment variable {key!r} is not set", file=sys.stderr)
        sys.exit(1)
    return val


def _read_or_empty(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def generate_docs(
    cap_id: str,
    source_branch: str,
    commit_msg: str,
    capabilities_content: str,
    patch_notes_content: str,
) -> tuple[str, str]:
    """Call Claude to generate updated capabilities.md and patch-notes entry."""
    client = anthropic.Anthropic()

    branch_type = source_branch.split("/")[0]  # "feat" or "bug"
    # Extract short description from branch name (after cap{N}-)
    slug = re.sub(r"^(feat|bug)/cap\d+-?", "", source_branch)
    today = date.today().isoformat()

    prompt = f"""You are maintaining documentation for the CUTIP project.
A {branch_type} branch just merged into staging.

Branch: {source_branch}
Cap ID: {cap_id}
Merge commit message: {commit_msg}
Date: {today}

## Task 1: Update docs/capabilities.md

Current content:
<capabilities>
{capabilities_content}
</capabilities>

Add a new row for {cap_id} to the capabilities table. Use:
- ID: {cap_id}
- Title: a concise title derived from the branch slug "{slug}" and commit message
- Type: {branch_type}
- Status: merged
- Branch: {source_branch}
- PR: (leave as —)
- Date: {today}

Return the COMPLETE updated capabilities.md content (not a diff).

## Task 2: Generate a patch note entry

Write a short patch note entry (2-5 bullet points) for this change.
Format it as a markdown section:

### {cap_id} — <title> ({today})

- Bullet describing what changed
- ...

Return ONLY the markdown for the patch note section (no surrounding text).

---

Respond with exactly two sections separated by "---SPLIT---":
1. The full updated capabilities.md content
2. The patch note section to prepend to patch-notes.md
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text
    parts = response_text.split("---SPLIT---", 1)
    if len(parts) != 2:
        print(
            "WARNING: Claude response did not contain ---SPLIT--- separator. "
            "Writing raw response to capabilities.md only.",
            file=sys.stderr,
        )
        return response_text, ""

    new_capabilities = parts[0].strip()
    patch_note_entry = parts[1].strip()
    return new_capabilities, patch_note_entry


def update_patch_notes(patch_notes_content: str, new_entry: str) -> str:
    """Prepend new_entry after the first heading in patch-notes.md."""
    if not patch_notes_content:
        return f"# Patch Notes\n\n{new_entry}\n"

    lines = patch_notes_content.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            insert_at = i + 1
            break

    lines.insert(insert_at, f"\n{new_entry}\n")
    return "".join(lines)


def main() -> None:
    cap_id = _env("CAP_ID")
    source_branch = _env("SOURCE_BRANCH")
    commit_msg = _env("COMMIT_MSG")

    capabilities_content = _read_or_empty(CAPABILITIES_FILE)
    patch_notes_content = _read_or_empty(PATCH_NOTES_FILE)

    print(f"Generating docs for {cap_id} from {source_branch}...")

    new_capabilities, patch_note_entry = generate_docs(
        cap_id=cap_id,
        source_branch=source_branch,
        commit_msg=commit_msg,
        capabilities_content=capabilities_content,
        patch_notes_content=patch_notes_content,
    )

    CAPABILITIES_FILE.write_text(new_capabilities + "\n", encoding="utf-8")
    print(f"Updated {CAPABILITIES_FILE.relative_to(REPO_ROOT)}")

    if patch_note_entry:
        updated_patch_notes = update_patch_notes(patch_notes_content, patch_note_entry)
        PATCH_NOTES_FILE.write_text(updated_patch_notes, encoding="utf-8")
        print(f"Updated {PATCH_NOTES_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
