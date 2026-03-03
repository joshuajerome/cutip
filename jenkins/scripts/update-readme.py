#!/usr/bin/env python3
"""
update-readme.py

Detect README drift from the live CLI output.

Checks:
  1. Whether `cutip --help` output matches what's embedded in README.md.
  2. Whether install instructions in README.md reference an outdated version.

If drift is found:
  - Prints a diff of what changed.
  - Writes the updated CLI help block to /tmp/readme-help-updated.txt for manual review.
  - Exits 0 (informational — does not fail the pipeline; a human or follow-up
    automation creates the docs/readme-update branch).

Exit 1 only if README.md is missing entirely.
"""

import re
import subprocess
import sys
import difflib
from pathlib import Path

README_PATH = Path("README.md")

# Marker comments that delimit the CLI help block in README.md
HELP_BLOCK_START = "<!-- cutip-help-start -->"
HELP_BLOCK_END = "<!-- cutip-help-end -->"


def get_live_help() -> str:
    """Run `cutip --help` and return its stdout."""
    try:
        result = subprocess.run(
            ["uv", "run", "cutip", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except Exception as exc:
        print(f"[update-readme] Could not run `cutip --help`: {exc}")
        return ""


def extract_help_block(readme_text: str) -> str | None:
    """Extract the CLI help block delimited by marker comments, if present."""
    start_idx = readme_text.find(HELP_BLOCK_START)
    end_idx = readme_text.find(HELP_BLOCK_END)
    if start_idx == -1 or end_idx == -1:
        return None
    inner = readme_text[start_idx + len(HELP_BLOCK_START): end_idx]
    # Strip surrounding code fences if present
    inner = inner.strip()
    if inner.startswith("```"):
        inner = re.sub(r"^```[a-z]*\n?", "", inner)
        inner = re.sub(r"\n?```$", "", inner)
    return inner.strip()


def main() -> int:
    if not README_PATH.exists():
        print("[update-readme] README.md not found — skipping.")
        return 1

    readme_text = README_PATH.read_text()

    # --- Check 1: CLI help block ---
    embedded_help = extract_help_block(readme_text)
    if embedded_help is None:
        print(
            f"[update-readme] No CLI help block found in README.md "
            f"(add {HELP_BLOCK_START} / {HELP_BLOCK_END} markers to enable drift detection)."
        )
    else:
        live_help = get_live_help()
        if live_help and live_help != embedded_help:
            diff = list(
                difflib.unified_diff(
                    embedded_help.splitlines(keepends=True),
                    live_help.splitlines(keepends=True),
                    fromfile="README.md (embedded)",
                    tofile="cutip --help (live)",
                )
            )
            print("[update-readme] CLI help drift detected:\n")
            print("".join(diff[:80]))  # Cap output to first 80 diff lines
            Path("/tmp/readme-help-updated.txt").write_text(live_help)
            print(
                "\n[update-readme] Updated help written to /tmp/readme-help-updated.txt. "
                "Create a docs/readme-update branch and replace the block manually."
            )
        else:
            print("[update-readme] CLI help block is up to date.")

    # --- Check 2: Install version ---
    version_match = re.search(
        r"pip install cutip==([0-9]+\.[0-9]+\.[0-9]+)", readme_text
    )
    if version_match:
        readme_version = version_match.group(1)
        # Read version from pyproject.toml
        pyproject = Path("pyproject.toml")
        if pyproject.exists():
            pyproject_text = pyproject.read_text()
            pkg_version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
            if pkg_version_match:
                pkg_version = pkg_version_match.group(1)
                if readme_version != pkg_version:
                    print(
                        f"[update-readme] Install version drift: "
                        f"README says {readme_version}, pyproject.toml says {pkg_version}. "
                        f"Update README.md install instructions."
                    )
                else:
                    print(f"[update-readme] Install version ({readme_version}) matches pyproject.toml.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
