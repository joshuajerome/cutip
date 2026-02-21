# Guide: Plan-Safe Workflows

`ctx.runtime` is `None` when a workflow is invoked via `cutip plan`. This is intentional — `cutip plan` is a dry-run that shows what *would* happen without contacting any backend.

A **plan-safe workflow** handles `ctx.runtime is None` gracefully instead of crashing with `AttributeError`.

---

## The basic guard

The simplest pattern — return immediately in dry-run mode:

```python
def main(ctx):
    if ctx.runtime is None:
        print("Dry-run — skipping execution")
        return

    # ... all deployment logic below
```

This makes `cutip plan` safe to run on any machine (no Podman, no Docker needed) and fast to execute in CI pre-checks.

---

## When to guard

You need a guard whenever your workflow calls any method on `ctx.runtime`. Container operations (`create_container`, `start_container`, etc.) will raise `AttributeError` in plan mode if unchecked.

You do **not** need a guard for:

- Reading `ctx.resolved_cards` or `ctx.resolved_units`
- Reading `ctx.project_root` or `ctx.registry`
- Pure Python logic (env var reads, path construction, logging)

---

## Partial dry-run — print the plan instead

A more informative pattern: show what the workflow *would* do, rather than silently returning:

```python
def main(ctx):
    img = ctx.resolved_cards["images/app"]
    cc  = ctx.resolved_cards["containers/app"]
    net = ctx.resolved_cards["networks/dev"]

    if ctx.runtime is None:
        print(f"[plan] would build:            {img.name}:{img.spec.tag}")
        print(f"[plan] would ensure network:   {net.name} ({net.spec.subnet})")
        print(f"[plan] would create container: {cc.name}")
        return

    ctx.runtime.build_image(img, project_root=ctx.project_root)
    ctx.runtime.ensure_network(net)
    ctx.runtime.create_container(cc, image_name=f"{img.name}:{img.spec.tag}")
    ctx.runtime.start_container(cc.name)
```

---

## Helper function pattern

For workflows with significant side-effect logic, extract the deployment into a separate function to keep the plan guard clean:

```python
def _deploy(ctx):
    img = ctx.resolved_cards["images/app"]
    cc  = ctx.resolved_cards["containers/app"]

    ctx.runtime.pull_image(img)
    ctx.runtime.create_container(cc, image_name=f"{img.name}:{img.spec.tag}")
    ctx.runtime.start_container(cc.name)


def main(ctx):
    if ctx.runtime is None:
        print("Dry-run — use `cutip run` to execute")
        return

    _deploy(ctx)
```

---

## Testing plan-safe workflows

Because plan-safe workflows can run without a backend, you can test them in unit tests without mocking the runtime:

```python
from unittest.mock import MagicMock
from cutip.context.workflow import CutipContext
from my_group.workflow import main

def test_workflow_plan_safe():
    ctx = MagicMock(spec=CutipContext)
    ctx.runtime = None   # simulate cutip plan

    # Should not raise
    main(ctx)
```
