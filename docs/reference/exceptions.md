# Exceptions Reference

All CUTIP exceptions inherit from `CutipError` and live in `cutip.utils.exceptions`.

---

## Hierarchy

```
CutipError
├── CutipParseError       # YAML file failed Pydantic validation on load
├── CutipRefError         # A ref string points to a non-existent artifact
├── CutipValidationError  # Graph validation failed (schema or semantic)
└── CutipWorkflowError    # workflow.py raised an exception during execution
```

---

## `CutipError`

Base class. All CUTIP-originated errors are instances of this class. Catching `CutipError` is safe — it will never catch unexpected Python errors.

```python
from cutip.utils.exceptions import CutipError

try:
    runtime.pull_image(card)
except CutipError as exc:
    print(f"CUTIP error: {exc}")
```

---

## `CutipParseError`

Raised by `WorkspaceDiscovery` when a YAML file fails Pydantic schema validation.

Attributes:
- `path: Path` — the file that failed to parse
- `detail: str` — the validation error message

`WorkspaceDiscovery` treats parse errors as **non-fatal warnings** — the malformed file is skipped and a warning is logged. The error is only surfaced if the skipped artifact is referenced by a unit or group (which `GraphValidator` will then report as an unresolved ref).

---

## `CutipRefError`

Raised by `RefResolver` when a ref string cannot be resolved.

Attributes:
- `ref: str` — the ref string that could not be resolved (e.g. `"images/missing"`)
- `reason: str` — explanation (not found, unknown prefix, wrong type)

```python
from cutip.utils.exceptions import CutipRefError

try:
    card = resolver.resolve_card("images/missing", ImageCard)
except CutipRefError as exc:
    print(f"Ref error: {exc.ref} — {exc.reason}")
```

---

## `CutipValidationError`

Raised when `GraphValidator` detects validation errors. Contains the collected error list as its message string.

---

## `CutipWorkflowError`

Raised when `WorkflowLoader` catches an exception from `workflow.py`. The original exception is chained (`__cause__`) so the full traceback is preserved.

---

## In workflow code

Workflow code can raise any exception — CUTIP will catch it and wrap it in `CutipWorkflowError`. For cleaner error messages in `cutip run` output, raise `CutipError` directly from your workflow:

```python
from cutip.utils.exceptions import CutipError

def main(ctx):
    if not ctx.project_root.joinpath(".env").exists():
        raise CutipError(".env file not found — copy .template.env and fill it in")
```
