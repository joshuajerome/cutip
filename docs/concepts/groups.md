# Concepts: Groups

A **Group** is CUTIP's top-level executable artifact. It collects one or more Units and attaches a Python `workflow.py`. Running `cutip run <group>` deploys a Group.

---

## Schema

```yaml
apiVersion: cutip/v1
kind: Group
metadata:
  name: <string>          # unique — used with cutip run / plan / show group
spec:
  units:
    - ref: units/<name>   # one or more unit refs
    - ref: units/<name>
  workflow: workflow.py   # path to Python workflow, relative to this file's directory
```

---

## Directory layout

A Group lives in a subdirectory under `cutip/groups/`:

```
cutip/groups/
└── dev/
    ├── group.yaml       ← Group artifact
    └── workflow.py      ← Python orchestration entry point
```

The `workflow` field is always relative to the group's directory, so `workflow.py` resolves to `cutip/groups/dev/workflow.py`. Additional Python modules (e.g. helpers, shared utilities) can be placed in the same directory and imported normally.

---

## Multiple groups in one workspace

A project may contain multiple independent groups, each with its own workflow and unit composition. All groups share the same card and unit registry.

```
cutip/groups/
├── dev/         ← local development environment
├── staging/     ← staging environment
└── tools/       ← one-off tooling (migrations, seed data, etc.)
```

Run them independently:

```shell
cutip plan dev
cutip run staging
```

---

## The workflow contract

The attached `workflow.py` must export an entry point function:

```python
def main(ctx: CutipContext) -> None:
    ...
```

CUTIP dynamically imports the file, calls `main(ctx)`, and propagates any exception as a `CutipWorkflowError`. Workflows can use `@action` and `@orchestrator` decorators for self-describing steps --- see [Annotations](annotations.md).

The workflow runs as Phase 2 of the unit lifecycle (pre-build -> orchestration -> post-start). See [Lifecycle](lifecycle.md) for the full execution model.

Full reference: [Workflow Contract](../reference/workflow-contract.md)

---

## Validation

`GraphValidator` checks each Group by:

1. Resolving every `units[].ref` to a registered Unit
2. Walking each Unit's card chain (ContainerCard → ImageCard → NetworkCard)
3. Checking that `workflow.py` exists on disk at the resolved path

All errors are collected and reported in a single pass.
