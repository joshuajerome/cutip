# ImageCard Reference

An `ImageCard` describes how to obtain a container image — either by pulling from a registry or building from a local Dockerfile context.

---

## Schema

```yaml
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: <string>              # required
  labels: {}                  # optional
spec:
  source: pull | build        # required

  # ── Pull mode ──────────────────────────────────────────────────────
  image: <string>             # required if source: pull — registry image name
  tag: <string>               # default: "latest"

  # ── Build mode ─────────────────────────────────────────────────────
  context: <path>             # required if source: build — path to Dockerfile dir
  dockerfile: <string>        # default: "Dockerfile"
  build_args: {}              # optional key-value pairs passed to --build-arg
```

---

## Pull example

```yaml
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: alpine
spec:
  source: pull
  image: docker.io/library/alpine
  tag: "3.20"
```

CUTIP calls `runtime.pull_image(card)` in your workflow. The image ref used is `<image>:<tag>`.

---

## Build example

```yaml
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: my-app
spec:
  source: build
  context: containers/dockerfiles
  dockerfile: app.dockerfile
  tag: latest
  build_args:
    REQUIREMENTS: requirements.txt
    VERSION: "1.2.3"
```

CUTIP calls `runtime.build_image(card, project_root=ctx.project_root)` in your workflow. The `context` path is resolved relative to `project_root`.

---

## Validation rules

- `source` must be `"pull"` or `"build"`
- If `source: pull`, `image` is required
- If `source: build`, `context` is required
- `build_args` keys and values must both be strings
