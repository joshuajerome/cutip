# Concepts: Graph Resolution

Understanding how CUTIP resolves and validates the artifact graph is useful when debugging ref errors or building complex multi-group workspaces.

---

## The pipeline

```
cutip/              WorkspaceDiscovery       CutipRegistry
*.yaml files   ──▶  parse + dispatch    ──▶  in-memory store
                    (by kind)                keyed by prefix/name

CutipRegistry       RefResolver              GraphValidator
                ──▶ resolve refs         ──▶ full graph walk
                    on demand                non-failing error collection
```

---

## WorkspaceDiscovery

`WorkspaceDiscovery` walks the `cutip/` directory, reads every `.yaml` / `.yml` file, and dispatches to the right model based on the `kind` field:

| `kind` | Model | Registry prefix |
|---|---|---|
| `ImageCard` | `ImageCard` | `images/` |
| `ContainerCard` | `ContainerCard` | `containers/` |
| `NetworkCard` | `NetworkCard` | `networks/` |
| `VolumeCard` | `VolumeCard` | `volumes/` |
| `Unit` | `Unit` | unit registry |
| `Group` | `Group` | group registry |

Parse errors are non-fatal warnings — a malformed file is skipped and logged, not a hard crash. This lets you add work-in-progress YAMLs without breaking `cutip tree`.

---

## CutipRegistry

The registry is an in-memory store with three namespaces:

- `cards` — keyed by `<prefix>/<name>`, e.g. `images/app`, `containers/db`
- `units` — keyed by unit name
- `groups` — keyed by group name

The registry also stores `_sources` — a mapping from registry key to the source file path, used by `cutip show` and `cutip tree` to display file locations.

---

## RefResolver

`RefResolver` is a thin lookup layer on top of `CutipRegistry`. It parses ref strings (`"images/app"`, `"containers/db"`), maps the prefix to an expected model class, and returns the registered artifact or raises `CutipRefError`.

```python
resolver.resolve("images/app")                # → ImageCard
resolver.resolve_card("containers/db", ContainerCard)   # → ContainerCard (type-checked)
resolver.resolve_unit("my-unit")              # → Unit
```

---

## GraphValidator

`GraphValidator` performs a full semantic walk of the graph and collects all errors before reporting:

```
For each Unit:
  resolve containerRef → ContainerCard
    resolve imageRef   → ImageCard
    resolve networkRef → NetworkCard    (skipped when network_mode is set)

For each Group:
  resolve each unit ref → Unit
  check workflow.py exists on disk
```

Errors are collected into a `ValidationResult(ok: bool, errors: list[str])`. All errors are reported in one pass — you never fix one error only to discover the next.

---

## Error types

| Exception | When raised |
|---|---|
| `CutipParseError` | YAML file fails Pydantic validation |
| `CutipRefError` | A `ref:` string points to a non-existent artifact |
| `CutipValidationError` | Graph validation fails |
| `CutipWorkflowError` | `workflow.py` raises an exception during execution |

Full exception hierarchy: [`reference/exceptions.md`](../reference/exceptions.md)
