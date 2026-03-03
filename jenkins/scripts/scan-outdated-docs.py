#!/usr/bin/env python3
"""
scan-outdated-docs.py

Scan docs/ for stale references: removed CLI flags, removed backend names,
renamed classes/paths, and deprecated APIs.

Exit 0 — findings are warnings only; pipeline continues.
Exit 1 — if any HIGH-severity stale references are found.
"""

import re
import sys
from pathlib import Path

DOCS_DIR = Path("docs")

# Each entry: (pattern, severity, reason)
STALE_PATTERNS: list[tuple[str, str, str]] = [
    # Removed Docker backend
    (r"\bdocker\b", "HIGH", "docker support was removed; Podman is the only backend"),
    (r"DockerBackend", "HIGH", "DockerBackend was removed"),
    (r"--backend\s+docker", "HIGH", "docker backend flag no longer valid"),

    # Renamed directories
    (r"\bcontainers/resources\b", "HIGH", "renamed to resources/buildtime/"),
    (r"\bcontainers/\b(?!card)", "MEDIUM", "containers/ directory renamed to resources/"),

    # Renamed group names
    (r"\bgroup:\s*main\b", "MEDIUM", "group 'main' renamed to 'snf-gui' or 'snf-blueprint-manager'"),

    # Old CLI flags or commands that may have changed
    (r"cutip\s+run\s+main\b", "MEDIUM", "group 'main' no longer exists"),

    # Deprecated vars.yaml format (flat, no required:/generated: sections)
    (r"^\s{0,4}\w+:\s+\"\".*#.*required", "LOW", "old flat vars.yaml format; use required:/generated: sections"),
]


def scan_file(md_file: Path) -> list[tuple[str, int, str, str]]:
    """Return list of (file, line_num, severity, reason) for each hit."""
    hits = []
    lines = md_file.read_text(errors="replace").splitlines()
    for lineno, line in enumerate(lines, start=1):
        for pattern, severity, reason in STALE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                hits.append((str(md_file), lineno, severity, reason))
    return hits


def main() -> int:
    if not DOCS_DIR.exists():
        print("[scan-outdated-docs] docs/ directory not found — skipping.")
        return 0

    all_hits: list[tuple[str, int, str, str]] = []
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        all_hits.extend(scan_file(md_file))

    if not all_hits:
        print("[scan-outdated-docs] No stale references found.")
        return 0

    high = [h for h in all_hits if h[2] == "HIGH"]
    medium = [h for h in all_hits if h[2] == "MEDIUM"]
    low = [h for h in all_hits if h[2] == "LOW"]

    print(f"\n[scan-outdated-docs] Found {len(all_hits)} stale reference(s):")
    print(f"  HIGH: {len(high)}  MEDIUM: {len(medium)}  LOW: {len(low)}\n")

    for file, lineno, severity, reason in all_hits:
        print(f"  [{severity}] {file}:{lineno} — {reason}")

    if high:
        print(
            "\nHIGH-severity stale references must be resolved before merging."
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
