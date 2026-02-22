# VolumeCard Reference

A `VolumeCard` defines a named container volume. CUTIP calls `runtime.ensure_volume(card)` before creating any container that references it. If the volume already exists, the call is a no-op.

---

## Schema

```yaml
apiVersion: cutip/v1
kind: VolumeCard
metadata:
  name: <string>          # required — used as the volume name
  labels: {}              # optional
spec:
  driver: local           # default: "local"
  labels: {}              # labels applied to the volume
  options: {}             # driver-specific options
```

---

## Example

```yaml
apiVersion: cutip/v1
kind: VolumeCard
metadata:
  name: node_modules
spec:
  driver: local
```

Reference it in a `ContainerCard`:

```yaml
spec:
  volumes:
    node_modules: /app/node_modules   # volume name → container mount path
```

---

## Volume vs bind mount

| Use case | How |
|---|---|
| Named volume managed by the runtime | `VolumeCard` + `volumes:` in `ContainerCard` |
| Host directory mounted into container | `mounts:` in `ContainerCard` with `type: bind` |

Use `VolumeCard` when the data belongs to the container lifecycle (e.g. `node_modules`, build cache). Use bind mounts when the data is on the host machine and must be shared in (e.g. source code, SSH keys, config files injected at runtime).
