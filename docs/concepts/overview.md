# Concepts: Overview

## Why CUTIP exists

Most container tooling conflates *definition* and *execution*. A `docker-compose.yml` is both a schema and a runtime instruction — there's no clean separation between "what the container looks like" and "what to do with it."

CUTIP separates these concerns explicitly:

- **Cards** — immutable, validated definitions of container resources
- **Workflow** — arbitrary Python that operates on those definitions at runtime

This means you can validate your entire container graph statically (no daemon, no network) and only contact a runtime when you've verified the graph is correct.

---

## The four layers

```
ImageCard   ─┐
NetworkCard ─┤──▶  ContainerCard  ──▶  Unit  ──▶  Group  ──▶  workflow.py
VolumeCard  ─┘
```

### Layer 1: Cards (atomic definitions)

A **Card** defines one container resource. It has a `kind`, a `name`, and a `spec`. Nothing more.

Cards are stateless — they describe what a resource *is*, not what to do with it. A `ContainerCard` describes ports, environment variables, and mounts. A `NetworkCard` describes a subnet. Neither contains instructions.

Cards are validated on load by Pydantic v2 — type errors, missing required fields, and invalid CIDR ranges are caught before any command runs.

→ [concepts/cards.md](cards.md)

### Layer 2: Units (container instances)

A **Unit** composes exactly one `ContainerCard` into a named, deployable container instance. Units are the bridge between definitions (cards) and execution (groups).

→ [concepts/units.md](units.md)

### Layer 3: Groups (executable artifacts)

A **Group** collects one or more Units and attaches a Python `workflow.py`. A group is the unit of deployment: `cutip run <group>`.

→ [concepts/groups.md](groups.md)

### Layer 4: Workflow (Python orchestration)

The workflow is a plain Python file with a single function: `main(ctx: CutipContext)`. CUTIP injects a `CutipContext` that gives the workflow access to all resolved cards, units, the backend handle, and the project root. There is no DSL — just Python.

→ [reference/workflow-contract.md](../reference/workflow-contract.md)

---

## Validation before execution

Every `cutip run` begins with a full graph validation pass:

1. **Schema validation** — every YAML file is parsed and validated by Pydantic on workspace discovery
2. **Ref resolution** — every `ref:` in every card and unit is verified to exist in the registry
3. **Workflow existence** — every group's `workflow.py` path is checked
4. **Only then** — the backend is connected and the workflow runs

→ [concepts/graph-resolution.md](graph-resolution.md)

---

## Determinism

CUTIP is designed to be deterministic. Given the same YAML artifacts and the same workflow, `cutip run` always performs the same sequence of operations. There is no implicit state, no cached build detection, no magic.

What you define is what runs. What you commit is what you can reproduce.
