# Architecture: Design Decisions

This document explains the non-obvious design choices in CUTIP and the reasoning behind them.

---

## Why YAML artifacts instead of a Python DSL

Several container orchestration tools (Pulumi, CDK for Terraform) use a Python DSL to define infrastructure. CUTIP deliberately uses YAML.

**Reasons:**

1. **Validation at parse time.** Pydantic v2 validates every card the moment it is loaded from disk — before any command runs. A Python DSL defers validation to execution time.

2. **Diffs are readable.** YAML diffs in pull requests are unambiguous. A change to a subnet or an environment variable is visually obvious.

3. **The workflow is already Python.** CUTIP splits the concern cleanly: declarative structure in YAML, imperative orchestration in Python. Neither side bleeds into the other.

4. **Tooling.** YAML is natively supported by every CI system, code review tool, and secret manager.

---

## Why Pydantic v2

- **Speed.** Pydantic v2's Rust core is significantly faster than v1 at parse time, which matters when a workspace has dozens of cards.
- **`model_copy`.** The `model_copy(update=...)` pattern for runtime injection is clean and explicit — no mutation, no hidden state.
- **`model_validator`.** The `network_mode` / `networkRef` mutual exclusion is enforced at the model level, not scattered across validation logic.

---

## Why `main(ctx)` with optional decorators

A simple function contract is harder to break than a framework interface. It has one entry point, one argument, and returns nothing. This makes workflows trivially testable:

```python
# Testing a workflow in isolation
from unittest.mock import MagicMock
from my_group.workflow import main

ctx = MagicMock()
main(ctx)

ctx.runtime.create_container.assert_called_once()
```

Compare this to a base class that requires `super().__init__()`, registering methods, or implementing abstract properties.

The `@action` and `@orchestrator` decorators layer metadata on top of this contract without changing it. A decorated function executes identically to an undecorated one --- the decorators exist purely for introspection, planning output, and tooling. This means you can adopt them incrementally: start with a plain `main(ctx)`, add `@action` when your workflow grows complex enough to benefit from named steps.

---

## Why separation of `plan` and `run`

`cutip plan` performs full graph validation and prints the execution table without connecting to any backend. This means:

- Validation is fast (no network, no socket)
- CI can catch broken refs on every PR without needing Podman or Docker installed
- Engineers can review what will happen before approving a deployment

`ctx.runtime` being `None` in plan mode enforces this contract at the Python level — a workflow that accidentally calls `ctx.runtime.create_container()` in plan mode will raise `AttributeError`, making the bug immediately visible.

---

## Why SSH tunnel + local socket as separate modes (Podman)

The SSH tunnel mode (`PodmanBackend.connect()`) mirrors how Podman Desktop and the Podman CLI communicate with machines on macOS and Windows — they proxy a Unix socket over SSH. This is the safe, production default for the Podman backend.

The local socket mode (`--local`) exists for CI environments where the daemon is already local. Forcing CI to configure SSH keys and connections would be impractical. `CONTAINER_HOST` is the standard Podman convention for this, so CUTIP adopts it rather than inventing its own variable.

The Docker backend always connects locally via `docker.from_env()` — Docker Desktop handles all socket/pipe management internally, so no SSH tunnel or `--local` distinction is needed.

---

## Why `GraphValidator` collects all errors before reporting

Most validation frameworks stop at the first error. CUTIP's `GraphValidator` walks the entire graph and collects every error before reporting. The rationale: in a project with 10 units, stopping at the first broken ref forces the engineer to run `cutip validate` 10 times to discover all problems. Reporting all errors at once is a strict quality-of-life requirement for production tooling.

---

## Why `WorkspaceDiscovery` is non-fatal on parse errors

If a YAML file is malformed or contains an unknown `kind`, `WorkspaceDiscovery` emits a warning and continues. This allows work-in-progress artifacts to exist in the workspace without breaking `cutip tree` or `cutip validate` for the rest of the project.

`cutip validate` will still report unresolved refs if those WIP artifacts are referenced by units or groups.
