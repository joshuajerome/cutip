# Concepts: Units

A **Unit** is the bridge between a card definition and a running container. It composes exactly one `ContainerCard` into a named, deployable container instance.

---

## Schema

```yaml
apiVersion: cutip/v1
kind: Unit
metadata:
  name: <string>          # unique — used as the unit name in groups and CLI
spec:
  containerRef:
    ref: containers/<name>  # must resolve to a ContainerCard
```

---

## Why units exist

You might wonder why there's a Unit layer between `ContainerCard` and `Group`. The reason is **reusability and naming**.

A `ContainerCard` is a reusable definition. A `Unit` gives that definition a deployment identity. This means:

- The same `ContainerCard` can be reused across multiple groups (different environments, different configurations) by creating multiple Units that reference it
- Units carry semantic names (`web-server`, `db`, `worker`) that are meaningful in the context of a group

In practice, for most projects, there's a 1:1:1 relationship between `ImageCard → ContainerCard → Unit`. The layering becomes valuable in multi-environment setups where a single image card is referenced by staging and production container cards with different configurations.

---

## Resolved graph

When CUTIP resolves a Unit, it walks the full card chain:

```
Unit
└── ContainerCard  (containerRef)
    ├── ImageCard  (imageRef)
    └── NetworkCard  (networkRef) — or network_mode (no NetworkCard needed)
```

This entire chain is validated by `GraphValidator` before any backend is contacted.

---

## Accessing units in a workflow

Units are available in the workflow via `ctx.resolved_units`:

```python
def main(ctx):
    for unit_name, unit in ctx.resolved_units.items():
        cc = ctx.resolved_cards[unit.spec.containerRef.ref]
        print(f"Unit {unit_name} → container {cc.name}")
```
