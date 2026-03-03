# ContainerCard Reference

A `ContainerCard` defines the complete runtime configuration for one container. It references an `ImageCard` (what to run) and declares how networking, environment, mounts, and privileges are configured.

---

## Schema

```yaml
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: <string>          # required — used as the container name and registry key
  labels: {}              # optional key-value metadata
spec:
  # ── Image (required) ──────────────────────────────────────────────────
  imageRef:
    ref: images/<name>    # required — must resolve to an ImageCard

  # ── Networking (exactly one of the following is required) ─────────────
  networkRef:
    ref: networks/<name>  # use a managed NetworkCard (bridge with defined subnet)
  network_mode: <string>  # use a raw network mode: "host", "bridge", "none", etc.

  # ── Container config ──────────────────────────────────────────────────
  command: <string>       # optional — shell command string (parsed with shlex)
  hostname: <string>      # optional
  workdir: <string>       # optional working directory inside the container
  privileged: false       # default: false
  restart_policy: <string> # optional — e.g. "always", "on-failure"

  # ── Networking extras ─────────────────────────────────────────────────
  ports:                  # host → container port mapping
    "8080/tcp": "8080"

  # ── Environment ───────────────────────────────────────────────────────
  environment:
    MY_VAR: "value"

  # ── Mounts ────────────────────────────────────────────────────────────
  mounts:
    - type: bind          # "bind" or "volume"
      source: /host/path
      target: /container/path
      mode: rw            # "rw" or "ro"

  # ── Capabilities and security ─────────────────────────────────────────
  cap_add:
    - SYS_ADMIN
  security_opts:
    - label=disable
```

---

## Network: `networkRef` vs `network_mode`

Exactly one of these must be set. They are mutually exclusive.

| Field | When to use |
|---|---|
| `networkRef` | You need a managed bridge with a defined subnet and gateway (defined via `NetworkCard`). CUTIP will call `ensure_network` before creating the container. |
| `network_mode` | You need a raw network mode (`host`, `bridge`, `none`) that doesn't require a managed network definition. No `NetworkCard` is needed. |

```yaml
# Managed network (bridge with defined subnet)
spec:
  networkRef:
    ref: networks/dev

# Raw host network
spec:
  network_mode: host

# Default bridge (no subnet management)
spec:
  network_mode: bridge
```

---

## Command parsing

The `command` field is a string parsed with `shlex.split`. This means quoted arguments are handled correctly:

```yaml
command: 'sh -c "echo hello && sleep 5"'
# Parsed as: ["sh", "-c", "echo hello && sleep 5"]
```

---

## Runtime injection

`ContainerCard` is a Pydantic model and is immutable by default. To inject runtime values (paths from `.env`, dynamic mount sources) without modifying the YAML, use `model_copy` in your workflow:

```python
cc = ctx.resolved_cards["containers/app"]
cc = cc.model_copy(update={
    "spec": cc.spec.model_copy(update={
        "mounts": [
            {"type": "bind", "source": "/runtime/path", "target": "/data", "mode": "rw"}
        ]
    })
})
ctx.runtime.create_container(cc, image_name="app:latest")
```

---

## Validation rules

- `imageRef` is always required
- Exactly one of `networkRef` or `network_mode` must be set (Pydantic `model_validator`)
- `networkRef.ref` must resolve to a registered `NetworkCard` (checked by `GraphValidator`)
- `imageRef.ref` must resolve to a registered `ImageCard` (checked by `GraphValidator`)
