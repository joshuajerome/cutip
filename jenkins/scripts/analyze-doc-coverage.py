#!/usr/bin/env python3
"""
analyze-doc-coverage.py

Cross-reference changed Python source files (from /tmp/changed_files.txt)
against docs/ to identify undocumented modules.

Exit 0 — report printed; pipeline continues regardless (informational stage).
"""

import os
import re
import sys
from pathlib import Path

CHANGED_FILES_PATH = "/tmp/changed_files.txt"
DOCS_DIR = Path("docs")
REPO_ROOT = Path(".")


def load_changed_files() -> list[str]:
    if not os.path.exists(CHANGED_FILES_PATH):
        print("[analyze-doc-coverage] No changed files list found — skipping.")
        return []
    with open(CHANGED_FILES_PATH) as f:
        return [line.strip() for line in f if line.strip().endswith(".py")]


def load_docs_content() -> str:
    """Return concatenated text of all markdown files under docs/."""
    if not DOCS_DIR.exists():
        return ""
    parts = []
    for md_file in DOCS_DIR.rglob("*.md"):
        parts.append(md_file.read_text(errors="replace"))
    return "\n".join(parts)


def module_name_from_path(py_path: str) -> str:
    """Convert a file path like cutip/models/group.py → cutip.models.group."""
    return py_path.replace("/", ".").removesuffix(".py")


def main() -> None:
    changed = load_changed_files()
    if not changed:
        print("[analyze-doc-coverage] No Python files changed — nothing to check.")
        return

    docs_text = load_docs_content()
    gaps: list[str] = []

    for py_file in changed:
        module = module_name_from_path(py_file)
        # Check for any mention of the module path or leaf name in docs
        leaf = py_file.split("/")[-1].removesuffix(".py")
        mentioned = (
            py_file in docs_text
            or module in docs_text
            or leaf in docs_text
        )
        if not mentioned:
            gaps.append(py_file)

    print(f"\n[analyze-doc-coverage] Changed Python files: {len(changed)}")
    print(f"[analyze-doc-coverage] Undocumented in docs/: {len(gaps)}")

    if gaps:
        print("\nThe following changed modules have no reference in docs/:")
        for g in gaps:
            print(f"  - {g}")
        print(
            "\nAction: Consider adding or updating documentation for these modules."
        )
    else:
        print("All changed modules are referenced in docs/. No gaps found.")


if __name__ == "__main__":
    main()
