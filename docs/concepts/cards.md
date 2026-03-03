# Concepts: Cards

Cards are CUTIP's smallest unit of definition. Each card describes exactly one container resource — an image, a network, a volume, or a container's runtime configuration.

---

## What makes a card

Every card shares the same envelope:

```yaml
apiVersion: cutip/v1      # must be exactly "cutip/v1"
kind: <CardKind>          # ImageCard | ContainerCard | NetworkCard
metadata:
  name: <string>          # unique within its kind — used as the registry key
  labels: {}              # optional key-value metadata
spec:
  ...                     # kind-specific fields
```

Cards are:

- **Immutable** — Pydantic models, validated on load, not modified after parse
- **Stateless** — they describe what a resource *is*, not what to do with it
- **Versioned** — committed to source control alongside your application code
- **Composable** — `ContainerCard` references `ImageCard` and `NetworkCard` by ref

---

## The four card kinds

### ImageCard

Describes how to obtain a container image — either by pulling from a registry or building from a local Dockerfile.

```yaml
kind: ImageCard
spec:
  source: pull | build
  image: docker.io/library/ubuntu   # required for source: pull
  tag: "22.04"
  context: containers/dockerfiles   # required for source: build
  dockerfile: app.dockerfile
  build_args:
    MY_ARG: value
```

Full reference: [reference/cards/image-card.md](../reference/cards/image-card.md)

### ContainerCard

Defines the complete runtime configuration for one container. References an `ImageCard` and either a `NetworkCard` (via `networkRef`) or a raw network mode string.

```yaml
kind: ContainerCard
spec:
  imageRef:
    ref: images/my-app
  networkRef:
    ref: networks/dev     # managed bridge
  # network_mode: host    # OR: raw mode — not both
  command: "tail -f /dev/null"
  environment:
    ENV: production
  ports:
    "8080/tcp": "8080"
```

Full reference: [reference/cards/container-card.md](../reference/cards/container-card.md)

### NetworkCard

Defines a managed bridge network with a predictable subnet and gateway.

```yaml
kind: NetworkCard
spec:
  driver: bridge
  subnet: "10.89.0.0/16"
  gateway: "10.89.0.1"
```

Full reference: [reference/cards/network-card.md](../reference/cards/network-card.md)

---

## Registry keys

When CUTIP discovers cards during workspace loading, each card is registered under a key of the form `<prefix>/<name>`:

| Kind | Prefix | Example key |
|---|---|---|
| `ImageCard` | `images/` | `images/my-app` |
| `ContainerCard` | `containers/` | `containers/my-app` |
| `NetworkCard` | `networks/` | `networks/dev` |

These keys are the ref strings used in `imageRef`, `networkRef`, `containerRef`, etc.
