# NetworkCard Reference

A `NetworkCard` defines a managed container network with a driver, subnet, and gateway. It is used when you need a named bridge network with a predictable IP range. For raw `host`, `bridge`, or `none` modes, use `network_mode` in `ContainerCard` instead.

---

## Schema

```yaml
apiVersion: cutip/v1
kind: NetworkCard
metadata:
  name: <string>            # required — used as the network name
  labels: {}                # optional
spec:
  driver: bridge            # default: "bridge"
  subnet: "10.89.0.0/16"   # required — must be a valid CIDR block
  gateway: "10.89.0.1"     # optional — must be within the subnet
```

---

## Example

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

CUTIP calls `runtime.ensure_network(card)` before creating any container that references this network. If the network already exists, `ensure_network` is a no-op.

---

## Validation rules

- `subnet` must be a valid IPv4 CIDR (e.g. `"10.89.0.0/16"`)
- If `gateway` is provided, it must be an address within `subnet`

---

## When to use `networkRef` vs `network_mode`

Use `NetworkCard` + `networkRef` when:
- You need multiple containers on the same defined subnet
- You need a predictable gateway address
- You want CUTIP to own the network lifecycle (`ensure_network`)

Use `network_mode: host` or `network_mode: bridge` in `ContainerCard` when:
- You only need one container and don't care about subnet definition
- You need host networking (e.g. for port-free localhost access)
- The network already exists outside of CUTIP
