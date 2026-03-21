# Concepts: Annotations

CUTIP provides two workflow decorators --- `@action` and `@orchestrator` --- that add structured metadata to workflow functions. These decorators are optional: a plain `def main(ctx)` works without them. They exist for introspection, planning, and tooling.

---

## `@action`

Marks a function as a discrete, named step in the workflow. Each action represents one logical operation (start a container, run a health check, seed a database).

```python
from cutip.workflow.decorators import action

@action(
    name="Start DB",
    description="Start postgres and wait for readiness",
    container="cutip-db",
    depends_on=["pull_images"],
)
def start_db(ctx):
    ctx.container("cutip-db").start()
    # ... health check loop
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | yes | Human-readable name for this action (used in plan output and introspection) |
| `description` | `str` | no | Longer description of what this action does |
| `container` | `str` | no | Container name this action operates on (hint for tooling) |
| `depends_on` | `list[str]` | no | List of action function names that must run before this one |

### What `@action` does at runtime

Nothing. The decorator attaches an `ActionMeta` dataclass to the function and returns a transparent wrapper. The function executes identically whether decorated or not. The metadata is available for introspection:

```python
from cutip.workflow.decorators import _ACTION_ATTR

meta = getattr(start_db, _ACTION_ATTR)
# ActionMeta(name="Start DB", description="...", container="cutip-db", depends_on=["pull_images"])
```

---

## `@orchestrator`

Marks the workflow entry point. This is the function CUTIP calls to run the workflow.

```python
from cutip.workflow.decorators import orchestrator

@orchestrator
def main(ctx):
    start_db(ctx)
    start_web(ctx)
```

`@orchestrator` takes no parameters. It marks the function so that introspection tools can identify the entry point without relying on the function being named `main`.

If no `@orchestrator` is present, CUTIP falls back to calling `main(ctx)` by name --- the decorator is not required for execution.

---

## Introspection

CUTIP includes an AST-based introspection module (`cutip.workflow.introspect`) that can extract action metadata and execution order from a workflow file without importing it.

### `get_module_actions(module)`

Returns all `@action`-decorated functions from an imported module:

```python
from cutip.workflow.introspect import get_module_actions

actions = get_module_actions(workflow_module)
# {"start_db": ActionMeta(...), "start_web": ActionMeta(...)}
```

### `get_orchestrator(module)`

Returns the `@orchestrator`-decorated function, or `None`:

```python
from cutip.workflow.introspect import get_orchestrator

orch = get_orchestrator(workflow_module)
```

### `extract_action_order(workflow_path)`

Parses the workflow file with Python's `ast` module and returns actions in the order they are called inside the orchestrator body:

```python
from cutip.workflow.introspect import extract_action_order

order = extract_action_order(Path("cutip/groups/dev/workflow.py"))
# [ActionMeta(name="Start DB", ...), ActionMeta(name="Start Web", ...)]
```

This works without importing the module --- it analyzes the source code statically. The introspection walks if/else branches, for/while loops, and try blocks to find all action calls.

---

## When to use decorators

**Use `@action` when:**

- You want `cutip plan` to show named steps with descriptions
- You are building a multi-step workflow and want the execution graph to be self-documenting
- You want tooling to understand which container each function operates on

**Use `@orchestrator` when:**

- Your entry point is not named `main`
- You want introspection to identify the entry point without naming conventions

**Skip decorators when:**

- You have a simple single-container workflow
- You prefer minimal boilerplate
- The workflow is straightforward enough that the code is its own documentation

---

## Example: annotated workflow

```python
from cutip.workflow.decorators import action, orchestrator

@action(name="Pull images", description="Pull all container images")
def pull_images(ctx):
    for card in ctx.resolved_cards.values():
        if hasattr(card, "spec") and hasattr(card.spec, "source"):
            ctx.runtime.pull_image(card)

@action(
    name="Start DB",
    description="Start postgres and wait for readiness",
    container="cutip-db",
    depends_on=["pull_images"],
)
def start_db(ctx):
    ctx.container("cutip-db").start()
    # health check ...

@action(
    name="Start Web",
    description="Start the web application",
    container="cutip-web",
    depends_on=["start_db"],
)
def start_web(ctx):
    ctx.container("cutip-web").start()

@orchestrator
def main(ctx):
    if ctx.runtime is None:
        return  # plan-safe
    pull_images(ctx)
    start_db(ctx)
    start_web(ctx)
```

This workflow is functionally identical to one without decorators. The difference is that `cutip plan` and introspection tools can extract the step names, descriptions, container hints, and dependency graph without executing the code.
