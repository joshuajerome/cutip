# Quickstart

This guide walks you from an empty directory to a running container group in under 10 minutes. It assumes CUTIP is installed and a container backend (Podman or Docker) is available.

For installation, see [installation.md](installation.md).

---

## 1. Initialize a workspace

```shell
mkdir my-project && cd my-project
git init
cutip init
```

This creates:

```
cutip.yaml
cutip/
  cards/{images,containers,networks,volumes}/
  units/
  groups/
.cutip/
```

---

## 2. Define your image

`cutip/cards/images/app.yaml`:

```yaml
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: app
spec:
  source: pull
  image: docker.io/library/alpine
  tag: "3.20"
```

---

## 3. Define a network

`cutip/cards/networks/dev.yaml`:

```yaml
apiVersion: cutip/v1
kind: NetworkCard
metadata:
  name: dev
spec:
  driver: bridge
  subnet: "10.89.0.0/16"
  gateway: "10.89.0.1"
```

---

## 4. Define a container

`cutip/cards/containers/app.yaml`:

```yaml
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: app
spec:
  imageRef:
    ref: images/app
  networkRef:
    ref: networks/dev
  command: "tail -f /dev/null"
```

> [!TIP]
> If you don't need a managed bridge network, use `network_mode: bridge` (or `host`) instead of `networkRef`. Only one of `networkRef` or `network_mode` may be set.

---

## 5. Define a unit

`cutip/units/app.yaml`:

```yaml
apiVersion: cutip/v1
kind: Unit
metadata:
  name: app
spec:
  containerRef:
    ref: containers/app
```

---

## 6. Define a group

`cutip/groups/dev/group.yaml`:

```yaml
apiVersion: cutip/v1
kind: Group
metadata:
  name: dev
spec:
  units:
    - ref: units/app
  workflow: workflow.py
```

---

## 7. Write a workflow

`cutip/groups/dev/workflow.py`:

```python
def main(ctx):
    img = ctx.resolved_cards["images/app"]
    cc  = ctx.resolved_cards["containers/app"]
    net = ctx.resolved_cards["networks/dev"]

    ctx.runtime.pull_image(img)
    ctx.runtime.ensure_network(net)
    ctx.runtime.create_container(cc, image_name=f"{img.name}:{img.spec.tag}")
    ctx.runtime.start_container(cc.name)
```

---

## 8. Validate, inspect, and run

```shell
# Confirm graph is valid — no backend required
cutip validate

# Preview what will happen — no containers started
cutip plan dev

# Deploy
cutip run dev
```

Expected output from `cutip plan dev`:

```
Plan for group: dev

┌────────┬──────────────────┬────────┬──────────────┐
│ Step   │ Action           │ Target │ Detail       │
├────────┼──────────────────┼────────┼──────────────┤
│ 1      │ pull_image       │ app    │ alpine:3.20  │
│ 2      │ ensure_network   │ dev    │ 10.89.0.0/16 │
│ 3      │ create_container │ app    │ app          │
│ 4      │ start_container  │ app    │              │
│ 5      │ run_workflow     │ ...    │              │
└────────┴──────────────────┴────────┴──────────────┘
```

---

## Next steps

- [Workspace layout](workspace-layout.md) — understand the full directory structure
- [Concepts: Cards](../concepts/cards.md) — the full card type system
- [Reference: CLI](../reference/cli.md) — all commands and flags
- [Guides: Writing workflows](../guides/workflows/writing-workflows.md) — patterns and best practices
