# Workflow Contract

A CUTIP workflow is a plain Python file (`workflow.py`) containing exactly one function: `main(ctx: CutipContext)`. CUTIP discovers and imports this file dynamically at runtime and calls `main(ctx)`.

There is no base class to inherit, no decorator to apply, no registration step. If the file exists and exports `main`, it runs.

---

## CutipContext

```python
@dataclass
class CutipContext:
    group:          Group                               # the Group being executed
    resolved_units: dict[str, Unit]                    # unit name → Unit
    resolved_cards: dict[str, CutipBaseModel]          # card ref → Card
    registry:       CutipRegistry                      # full workspace registry
    project_root:   Path                               # absolute path to project root
    runtime:        CutipBackend | None                # None in cutip plan (dry-run)
```

### `ctx.resolved_cards`

Keyed by the card's registry ref (`"images/app"`, `"containers/db"`, etc.). Only cards that are reachable from the group's unit chain are included.

```python
img_card = ctx.resolved_cards["images/app"]         # ImageCard
cc        = ctx.resolved_cards["containers/app"]    # ContainerCard
net       = ctx.resolved_cards["networks/dev"]      # NetworkCard
```

### `ctx.runtime`

A `CutipBackend` instance connected to the configured runtime. It is `None` when the workflow is invoked via `cutip plan`. Always guard against this if you want a plan-safe workflow.

---

## CutipBackend methods

The backend handle (`ctx.runtime`) exposes the following interface:

```python
# Images
runtime.pull_image(card: ImageCard) -> None
runtime.build_image(card: ImageCard, project_root: Path | None = None) -> None

# Networks
runtime.ensure_network(card: NetworkCard) -> None

# Containers
runtime.create_container(card: ContainerCard, image_name: str | None = None) -> str
runtime.start_container(name: str) -> None
runtime.stop_container(name: str) -> None
runtime.remove_container(name: str) -> None

# Inspection
runtime.container_status(name: str) -> str   # "running" | "exited" | "not_found" | ...
runtime.container_logs(name: str) -> str     # stdout + stderr as a string
```

### `create_container` image_name

If `image_name` is omitted, CUTIP infers `<card.metadata.name>:latest`. Pass it explicitly when using a build tag:

```python
image_name = f"{img_card.name}:{img_card.spec.tag}"
runtime.create_container(cc, image_name=image_name)
```

---

## Runtime injection pattern

Cards are immutable Pydantic models. To inject runtime values (paths from `.env`, dynamic mount sources), use `model_copy`:

```python
from dotenv import load_dotenv
import os

load_dotenv()

runtime_mounts = [
    {"type": "bind", "source": os.environ["DATA_DIR"], "target": "/data"}
]

cc = ctx.resolved_cards["containers/app"]
cc = cc.model_copy(update={
    "spec": cc.spec.model_copy(update={"mounts": runtime_mounts})
})

runtime.create_container(cc, image_name="app:latest")
```

---

## Plan-safe guard

`ctx.runtime` is `None` when invoked via `cutip plan`. If your workflow contains side effects beyond container operations (file writes, HTTP calls, etc.), guard them:

```python
def main(ctx):
    if ctx.runtime is None:
        print("Dry-run — skipping execution")
        return

    # ... actual deployment logic
```

---

## Example: full lifecycle workflow

```python
from cutip.models.cards.image import ImageCard
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.network import NetworkCard


def main(ctx):
    if ctx.runtime is None:
        return

    img = next(c for c in ctx.resolved_cards.values() if isinstance(c, ImageCard))
    cc  = next(c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard))
    net = next(c for c in ctx.resolved_cards.values() if isinstance(c, NetworkCard))

    ctx.runtime.build_image(img, project_root=ctx.project_root)
    ctx.runtime.ensure_network(net)
    ctx.runtime.create_container(cc, image_name=f"{img.name}:{img.spec.tag}")
    ctx.runtime.start_container(cc.name)
```
