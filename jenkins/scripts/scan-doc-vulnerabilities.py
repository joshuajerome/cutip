#!/usr/bin/env python3
"""
scan-doc-vulnerabilities.py

Scan docs/ for:
  - Accidental credential / token patterns (HIGH)
  - Internal / private path leakage (MEDIUM)
  - Broken external links (LOW — HTTP GET with timeout)

Exit 0 — low/medium findings only (printed as warnings).
Exit 1 — any HIGH-severity finding detected.
"""

import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

DOCS_DIR = Path("docs")
LINK_TIMEOUT_SECONDS = 5

# Credential patterns: (regex, label)
CREDENTIAL_PATTERNS: list[tuple[str, str]] = [
    (r"password\s*[:=]\s*\S+", "password assignment"),
    (r"secret\s*[:=]\s*\S+", "secret assignment"),
    (r"api[_-]?key\s*[:=]\s*\S+", "API key"),
    (r"token\s*[:=]\s*\S+", "token assignment"),
    (r"ssh-rsa\s+[A-Za-z0-9+/]{20,}", "SSH public key literal"),
    (r"-----BEGIN [A-Z ]+PRIVATE KEY-----", "private key block"),
    (r"ghp_[A-Za-z0-9]{36,}", "GitHub PAT"),
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI / Anthropic API key"),
]

# Private path patterns: (regex, label)
PRIVATE_PATH_PATTERNS: list[tuple[str, str]] = [
    (r"/Users/[a-zA-Z0-9._-]+/", "macOS user home path"),
    (r"/home/[a-zA-Z0-9._-]+/", "Linux user home path"),
    (r"C:\\Users\\[a-zA-Z0-9._-]+\\", "Windows user home path"),
    (r"192\.168\.\d+\.\d+", "private IP address (192.168.x.x)"),
    (r"10\.\d+\.\d+\.\d+", "private IP address (10.x.x.x)"),
]

EXTERNAL_LINK_RE = re.compile(r"https?://[^\s\)\]\"']+")

# Domains to skip for link checking (known slow or auth-gated)
SKIP_LINK_DOMAINS = {"localhost", "127.0.0.1", "example.com"}


def extract_links(text: str) -> list[str]:
    return EXTERNAL_LINK_RE.findall(text)


def check_link(url: str) -> bool:
    """Return True if URL responds with HTTP 2xx/3xx, False otherwise."""
    for domain in SKIP_LINK_DOMAINS:
        if domain in url:
            return True
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "cutip-docs-scanner/1.0"})
        with urllib.request.urlopen(req, timeout=LINK_TIMEOUT_SECONDS) as resp:
            return resp.status < 400
    except Exception:
        return False


def scan_file(md_file: Path, check_links: bool) -> dict:
    text = md_file.read_text(errors="replace")
    lines = text.splitlines()
    hits: dict[str, list] = {"HIGH": [], "MEDIUM": [], "LOW": []}

    for lineno, line in enumerate(lines, start=1):
        # Credential patterns
        for pattern, label in CREDENTIAL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                # Skip lines that look like template placeholders or comments showing format
                if re.search(r"\{[^}]+\}|<[^>]+>|^\s*#", line):
                    continue
                hits["HIGH"].append((lineno, f"Credential leak ({label}): {line.strip()[:120]}"))

        # Private path patterns
        for pattern, label in PRIVATE_PATH_PATTERNS:
            if re.search(pattern, line):
                # Skip if it looks like it's inside a code block showing a variable
                if "vars." in line or "{{" in line:
                    continue
                hits["MEDIUM"].append((lineno, f"Private path ({label}): {line.strip()[:120]}"))

    # Broken links
    if check_links:
        links = extract_links(text)
        for url in links:
            if not check_link(url):
                hits["LOW"].append((0, f"Broken link: {url}"))

    return hits


def main() -> int:
    if not DOCS_DIR.exists():
        print("[scan-doc-vulnerabilities] docs/ directory not found — skipping.")
        return 0

    # Link checking can be slow; skip if there are many docs
    md_files = sorted(DOCS_DIR.rglob("*.md"))
    check_links = len(md_files) <= 20  # Only check links for small doc sets

    total_high = 0
    total_medium = 0
    total_low = 0
    any_hit = False

    for md_file in md_files:
        hits = scan_file(md_file, check_links)
        for severity, entries in hits.items():
            for lineno, message in entries:
                any_hit = True
                loc = f"{md_file}:{lineno}" if lineno else str(md_file)
                print(f"  [{severity}] {loc} — {message}")
                if severity == "HIGH":
                    total_high += 1
                elif severity == "MEDIUM":
                    total_medium += 1
                else:
                    total_low += 1

    if not any_hit:
        print("[scan-doc-vulnerabilities] No vulnerabilities found.")
        return 0

    print(
        f"\n[scan-doc-vulnerabilities] Summary: "
        f"HIGH={total_high} MEDIUM={total_medium} LOW={total_low}"
    )
    if total_high > 0:
        print("HIGH-severity findings must be resolved before merging.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
