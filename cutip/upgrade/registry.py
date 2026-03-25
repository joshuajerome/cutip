"""Migration registry — extensible scan/detect/apply framework for workspace upgrades.

Each migration is a class with:
  - id:          unique identifier (e.g. "vars-to-paths")
  - introduced:  version that introduced the breaking change (e.g. "0.1.8")
  - severity:    "breaking" or "warning"
  - detect():    returns list of Finding dicts if the migration applies
  - apply():     applies the fix for a single finding
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml
from loguru import logger


# ---------------------------------------------------------------------------
# Finding — a single detected issue
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single migration finding."""

    migration_id: str
    severity: str  # "breaking" or "warning"
    message: str
    file: Path | None = None
    detail: str = ""  # human-readable description of what --apply would do


# ---------------------------------------------------------------------------
# Migration protocol
# ---------------------------------------------------------------------------


class Migration(Protocol):
    id: str
    introduced: str
    severity: str
    description: str

    def detect(self, project_root: Path) -> list[Finding]: ...

    def apply(self, finding: Finding, project_root: Path, **kwargs: object) -> Path | list[Path]:
        """Apply fix for a single finding. Return list of modified file paths."""
        ...


# ---------------------------------------------------------------------------
# Concrete migrations
# ---------------------------------------------------------------------------


class VarsToPathsMigration:
    """vars.yaml → paths.yaml + secrets.yaml split (v0.1.8)."""

    id = "vars-to-paths"
    introduced = "0.1.8"
    severity = "breaking"
    description = "cutip/vars.yaml was renamed to cutip/paths.yaml; secrets go in cutip/secrets.yaml"

    def detect(self, project_root: Path) -> list[Finding]:
        old = project_root / "cutip" / "vars.yaml"
        new_paths = project_root / "cutip" / "paths.yaml"
        if old.exists() and not new_paths.exists():
            return [
                Finding(
                    migration_id=self.id,
                    severity=self.severity,
                    message=(
                        f"cutip/vars.yaml should be renamed to cutip/paths.yaml.\n"
                        f"  Sensitive values should be moved to cutip/secrets.yaml."
                    ),
                    file=old,
                    detail="Rename cutip/vars.yaml → cutip/paths.yaml",
                )
            ]
        return []

    def apply(self, finding: Finding, project_root: Path, **kwargs: object) -> list[Path]:
        old = project_root / "cutip" / "vars.yaml"
        new = project_root / "cutip" / "paths.yaml"
        old.rename(new)
        logger.info("Renamed: cutip/vars.yaml → cutip/paths.yaml")
        return [new]


class MissingBackendMigration:
    """cutip.yaml missing project.backend field (v0.1.9)."""

    id = "missing-backend"
    introduced = "0.1.9"
    severity = "warning"
    description = "cutip.yaml project.backend field required (default changed from podman to docker)"

    def detect(self, project_root: Path) -> list[Finding]:
        config = project_root / "cutip.yaml"
        if not config.exists():
            return []
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        project = data.get("project")
        if project is None:
            return [
                Finding(
                    migration_id="cutip-yaml-project",
                    severity="breaking",
                    message=(
                        "cutip.yaml is missing the 'project' section.\n"
                        "  Expected: apiVersion: cutip/v1 / project: / name: ... / backend: docker"
                    ),
                    file=config,
                    detail="Add project section to cutip.yaml (requires manual restructuring)",
                )
            ]
        if not isinstance(project, dict):
            return []
        if "backend" not in project:
            return [
                Finding(
                    migration_id=self.id,
                    severity=self.severity,
                    message=(
                        "cutip.yaml is missing project.backend.\n"
                        "  Default is now 'docker' (changed from 'podman' in v0.1.9)."
                    ),
                    file=config,
                    detail="Add project.backend to cutip.yaml",
                )
            ]
        return []

    def apply(self, finding: Finding, project_root: Path, **kwargs: object) -> list[Path]:
        if finding.migration_id == "cutip-yaml-project":
            logger.warning("Skipped: cutip-yaml-project requires manual restructuring of cutip.yaml")
            return []
        backend = kwargs.get("backend", "podman")
        config = project_root / "cutip.yaml"
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        project = data.get("project", {})
        project["backend"] = backend
        data["project"] = project
        config.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        logger.info(f"Added project.backend: {backend} to cutip.yaml")
        return [config]


class CtxVarsRenamedMigration:
    """ctx.vars → ctx.paths in startup.py files (v0.1.8)."""

    id = "ctx-vars-renamed"
    introduced = "0.1.8"
    severity = "breaking"
    description = "ctx.vars was renamed to ctx.paths in startup.py files"

    def detect(self, project_root: Path) -> list[Finding]:
        findings: list[Finding] = []
        units_dir = project_root / "cutip" / "units"
        if not units_dir.exists():
            return findings
        for startup in units_dir.rglob("startup.py"):
            text = startup.read_text(encoding="utf-8")
            if "ctx.vars" in text:
                findings.append(
                    Finding(
                        migration_id=self.id,
                        severity=self.severity,
                        message=(
                            f"{startup.relative_to(project_root)}: "
                            f"ctx.vars was renamed to ctx.paths in v0.1.8."
                        ),
                        file=startup,
                        detail="Replace ctx.vars → ctx.paths",
                    )
                )
        return findings

    def apply(self, finding: Finding, project_root: Path, **kwargs: object) -> list[Path]:
        if finding.file is None:
            return []
        text = finding.file.read_text(encoding="utf-8")
        updated = text.replace("ctx.vars", "ctx.paths")
        finding.file.write_text(updated, encoding="utf-8")
        logger.info(f"Updated: {finding.file} (ctx.vars → ctx.paths)")
        return [finding.file]


class CardVarsRefsMigration:
    """{{ vars.X }} → {{ paths.X }} in YAML cards (v0.1.8)."""

    id = "card-vars-refs"
    introduced = "0.1.8"
    severity = "breaking"
    description = "{{ vars.X }} template refs renamed to {{ paths.X }}"

    _pattern = re.compile(r"\{\{\s*vars\.\w+\s*\}\}")

    def detect(self, project_root: Path) -> list[Finding]:
        findings: list[Finding] = []
        cards_dir = project_root / "cutip" / "cards"
        if not cards_dir.exists():
            return findings
        for yaml_file in cards_dir.rglob("*.yaml"):
            text = yaml_file.read_text(encoding="utf-8")
            if self._pattern.search(text):
                findings.append(
                    Finding(
                        migration_id=self.id,
                        severity=self.severity,
                        message=(
                            f"{yaml_file.relative_to(project_root)}: "
                            f"{{{{ vars.X }}}} should be {{{{ paths.X }}}}."
                        ),
                        file=yaml_file,
                        detail="Replace {{ vars.X }} → {{ paths.X }}",
                    )
                )
        return findings

    def apply(self, finding: Finding, project_root: Path, **kwargs: object) -> list[Path]:
        if finding.file is None:
            return []
        text = finding.file.read_text(encoding="utf-8")
        updated = re.sub(r"\{\{\s*vars\.(\w+)\s*\}\}", r"{{ paths.\1 }}", text)
        finding.file.write_text(updated, encoding="utf-8")
        logger.info(f"Updated: {finding.file} ({{{{ vars.X }}}} → {{{{ paths.X }}}})")
        return [finding.file]


class StartupToHooksMigration:
    """startup.py with pre_build/startup → prehook.py/posthook.py (v0.2.0)."""

    id = "startup-to-hooks"
    introduced = "0.2.0"
    severity = "warning"
    description = "startup.py pre_build()/startup() should migrate to prehook.py/posthook.py"

    def detect(self, project_root: Path) -> list[Finding]:
        findings: list[Finding] = []
        units_dir = project_root / "cutip" / "units"
        if not units_dir.exists():
            return findings

        for startup in units_dir.rglob("startup.py"):
            unit_dir = startup.parent
            text = startup.read_text(encoding="utf-8")

            has_pre_build = "def pre_build(" in text
            has_startup = "def startup(" in text
            has_prehook = (unit_dir / "prehook.py").is_file()
            has_posthook = (unit_dir / "posthook.py").is_file()

            if has_pre_build and not has_prehook:
                findings.append(
                    Finding(
                        migration_id=self.id,
                        severity=self.severity,
                        message=(
                            f"{startup.relative_to(project_root)}: "
                            f"pre_build() should move to prehook.py (startup.py is deprecated)."
                        ),
                        file=startup,
                        detail="Extract pre_build() → prehook.py with main(ctx) entry point",
                    )
                )

            if has_startup and not has_posthook:
                findings.append(
                    Finding(
                        migration_id=self.id,
                        severity=self.severity,
                        message=(
                            f"{startup.relative_to(project_root)}: "
                            f"startup() should move to posthook.py (startup.py is deprecated)."
                        ),
                        file=startup,
                        detail="Extract startup() → posthook.py with main(ctx) entry point",
                    )
                )

        return findings

    def apply(self, finding: Finding, project_root: Path, **kwargs: object) -> list[Path]:
        """Extract pre_build/startup from startup.py into prehook.py/posthook.py.

        Preserves imports and helper functions. The new file gets main(ctx) as entry point.
        """
        if finding.file is None:
            return []

        import ast
        import textwrap

        text = finding.file.read_text(encoding="utf-8")
        tree = ast.parse(text)

        # Determine which function to extract
        if "pre_build() should move" in finding.message:
            old_name = "pre_build"
            new_file = finding.file.parent / "prehook.py"
        else:
            old_name = "startup"
            new_file = finding.file.parent / "posthook.py"

        if new_file.exists():
            logger.warning(f"Skipped: {new_file} already exists")
            return []

        # Collect imports (all lines before first function def)
        imports: list[str] = []
        func_body: str | None = None

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.get_source_segment(text, node) or "")
            elif isinstance(node, ast.FunctionDef) and node.name == old_name:
                func_body = ast.get_source_segment(text, node)

        if func_body is None:
            logger.warning(f"Could not extract {old_name}() from {finding.file}")
            return []

        # Build the new file: imports + renamed function
        new_func = func_body.replace(f"def {old_name}(", "def main(", 1)

        parts = []
        if imports:
            parts.append("\n".join(imports))
            parts.append("")
        parts.append("")
        parts.append(new_func)
        parts.append("")

        new_file.write_text("\n".join(parts), encoding="utf-8")
        logger.info(f"Created: {new_file.relative_to(project_root)} (from {old_name}())")

        modified = [new_file]

        # Remove the extracted function from startup.py if the other function still exists
        other_name = "startup" if old_name == "pre_build" else "pre_build"
        has_other = any(
            isinstance(n, ast.FunctionDef) and n.name == other_name
            for n in ast.iter_child_nodes(tree)
        )

        if not has_other:
            # startup.py only had this one function — it can be deleted
            finding.file.unlink()
            logger.info(f"Removed: {finding.file.relative_to(project_root)} (fully migrated)")
            modified.append(finding.file)
        else:
            # Remove the extracted function from startup.py, keep the rest
            lines = text.split("\n")
            func_start = None
            func_end = None
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef) and node.name == old_name:
                    func_start = node.lineno - 1  # 0-indexed
                    func_end = node.end_lineno  # exclusive
                    break

            if func_start is not None and func_end is not None:
                remaining = lines[:func_start] + lines[func_end:]
                # Remove trailing blank lines from the cut
                while remaining and remaining[-1].strip() == "":
                    remaining.pop()
                remaining.append("")
                finding.file.write_text("\n".join(remaining), encoding="utf-8")
                logger.info(
                    f"Updated: {finding.file.relative_to(project_root)} "
                    f"(removed {old_name}())"
                )
                modified.append(finding.file)

        return modified


# ---------------------------------------------------------------------------
# Registry — ordered list of all migrations
# ---------------------------------------------------------------------------


_MIGRATIONS: list[Migration] = [
    VarsToPathsMigration(),
    MissingBackendMigration(),
    CtxVarsRenamedMigration(),
    CardVarsRefsMigration(),
    StartupToHooksMigration(),
]


def scan_migrations(project_root: Path) -> list[Finding]:
    """Run all migration detectors against a workspace. Returns all findings."""
    findings: list[Finding] = []
    for migration in _MIGRATIONS:
        findings.extend(migration.detect(project_root))
    return findings


def get_migration(migration_id: str) -> Migration | None:
    """Look up a migration by ID."""
    for m in _MIGRATIONS:
        if m.id == migration_id:
            return m
    return None


def apply_findings(
    findings: list[Finding],
    project_root: Path,
    **kwargs: object,
) -> list[Path]:
    """Apply all findings. Returns list of all modified file paths."""
    modified: list[Path] = []
    for finding in findings:
        migration = get_migration(finding.migration_id)
        if migration is None:
            # Sub-findings like "cutip-yaml-project" are handled by their parent migration
            parent_id = finding.migration_id.rsplit("-", 1)[0] if "-" in finding.migration_id else None
            if parent_id:
                migration = get_migration(parent_id)
        if migration:
            result = migration.apply(finding, project_root, **kwargs)
            if isinstance(result, list):
                modified.extend(result)
            elif isinstance(result, Path):
                modified.append(result)
    return modified
