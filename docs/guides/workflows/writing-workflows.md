# Guide: Writing Workflows

A CUTIP workflow is a Python file with a single entry point. There is no DSL, no base class --- just:

```python
def main(ctx):
    ...
```

CUTIP injects a fully-populated `CutipContext` and calls your function. What happens next is entirely up to you.

For larger workflows, you can use `@action` and `@orchestrator` decorators to make steps self-describing --- see [Annotations](../../concepts/annotations.md). For the lifecycle context (pre-build, orchestration, post-start), see [Lifecycle](../../concepts/lifecycle.md).

---

## Accessing cards

Cards are pre-resolved in `ctx.resolved_cards`, keyed by their registry ref:

```python
def main(ctx):
    img = ctx.resolved_cards["images/my-app"]        # ImageCard
    cc  = ctx.resolved_cards["containers/my-app"]    # ContainerCard
    net = ctx.resolved_cards["networks/dev"]          # NetworkCard
```

If you don't want to hardcode ref strings, iterate by type:

```python
from cutip.models.cards.image import ImageCard
from cutip.models.cards.container import ContainerCard

def main(ctx):
    img = next(c for c in ctx.resolved_cards.values() if isinstance(c, ImageCard))
    cc  = next(c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard))
```

---

## Standard deployment pattern

```python
def main(ctx):
    img = ctx.resolved_cards["images/app"]
    cc  = ctx.resolved_cards["containers/app"]
    net = ctx.resolved_cards["networks/dev"]

    image_name = f"{img.name}:{img.spec.tag}"

    ctx.runtime.build_image(img, project_root=ctx.project_root)
    ctx.runtime.ensure_network(net)
    ctx.runtime.create_container(cc, image_name=image_name)
    ctx.runtime.start_container(cc.name)
```

---

## Injecting runtime values

Cards are Pydantic models. Environment-specific values (host paths from `.env`, dynamic mount sources) should not be hardcoded in YAML — inject them at runtime using `model_copy`:

```python
import os
from dotenv import load_dotenv

def main(ctx):
    load_dotenv(ctx.project_root / ".env")

    cc = ctx.resolved_cards["containers/app"]

    runtime_mounts = [
        {"type": "bind", "source": os.environ["DATA_DIR"], "target": "/data", "mode": "rw"},
        {"type": "bind", "source": os.environ["SSH_KEY"],  "target": "/root/.ssh/id_ed25519", "mode": "ro"},
    ]

    # model_copy is non-destructive — returns a new instance
    cc = cc.model_copy(update={
        "spec": cc.spec.model_copy(update={"mounts": runtime_mounts})
    })

    ctx.runtime.create_container(cc, image_name="app:latest")
    ctx.runtime.start_container(cc.name)
```

This pattern keeps secrets and machine-local paths out of version control while preserving the declarative YAML as the source of truth for static configuration.

---

## Staging buildtime resources

Some images need files copied into the Dockerfile build context before `build_image` is called. Do this explicitly in the workflow:

```python
import shutil
from pathlib import Path

def main(ctx):
    img = ctx.resolved_cards["images/app"]

    # Stage resources into build context
    build_ctx = ctx.project_root / img.spec.context
    resources  = ctx.project_root / "resources"

    shutil.copy(resources / "requirements.txt", build_ctx / "requirements.txt")
    shutil.copy(resources / "config.yaml",      build_ctx / "config.yaml")

    ctx.runtime.build_image(img, project_root=ctx.project_root)
```

Staged files should be listed in `.gitignore` (they're generated artifacts, not source).

---

## Handling existing containers

By default, `create_container` is a no-op if the container already exists. To enforce a clean state, remove it first:

```python
def main(ctx):
    cc = ctx.resolved_cards["containers/app"]
    name = cc.name

    status = ctx.runtime.container_status(name)
    if status != "not_found":
        ctx.runtime.stop_container(name)
        ctx.runtime.remove_container(name)

    ctx.runtime.create_container(cc, image_name="app:latest")
    ctx.runtime.start_container(name)
```

---

## Plan-safe guard

`ctx.runtime` is `None` when invoked via `cutip plan`. If your workflow does anything beyond container operations (file I/O, HTTP calls, subprocess), guard against this:

```python
def main(ctx):
    if ctx.runtime is None:
        print("Dry-run — nothing will be executed")
        return

    # ... deployment logic
```

See [plan-safe.md](plan-safe.md) for patterns.

---

## Multi-unit workflows

Groups can contain multiple units. Iterate them in order:

```python
def main(ctx):
    for unit_name, unit in ctx.resolved_units.items():
        cc  = ctx.resolved_cards[unit.spec.containerRef.ref]
        img = ctx.resolved_cards[cc.spec.imageRef.ref]

        ctx.runtime.pull_image(img)
        ctx.runtime.create_container(cc, image_name=f"{img.name}:{img.spec.tag}")
        ctx.runtime.start_container(cc.name)
```

---

## Accessing the registry

The full workspace registry is available at `ctx.registry` for advanced use cases:

```python
# Get any card by ref
card = ctx.registry.get_card("images/other-image")

# Check where an artifact was loaded from
source_path = ctx.registry.source_of("images/app")
```
