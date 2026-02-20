"""CUTIP custom exceptions."""

from __future__ import annotations


class CutipError(Exception):
    """Base class for all CUTIP errors."""


class CutipParseError(CutipError):
    """Raised when a YAML artifact cannot be parsed or fails schema validation."""

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"[ParseError] {path}: {detail}")


class CutipRefError(CutipError):
    """Raised when a ref string cannot be resolved in the registry."""

    def __init__(self, ref: str, reason: str) -> None:
        self.ref = ref
        self.reason = reason
        super().__init__(f"[RefError] '{ref}': {reason}")


class CutipValidationError(CutipError):
    """Raised when graph validation fails."""


class CutipWorkflowError(CutipError):
    """Raised when a workflow module cannot be loaded or executed."""
