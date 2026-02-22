# CUTIP

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/latest/)
[![uv](https://img.shields.io/badge/uv-package_manager-6e44ff)](https://github.com/astral-sh/uv)
[![Runtime](https://img.shields.io/badge/runtime-podman%20%7C%20docker-e44c11)](https://podman.io/)
[![CI](https://github.com/your-org/cutip/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/cutip/actions/workflows/ci.yml)

**Container Unit Templates in Python** — a deterministic framework for defining, validating, and orchestrating container environments using structured YAML artifacts and Python workflows.

CUTIP is not a wrapper around `docker-compose`. It is an opinionated engineering layer: every container resource is a versioned, validated artifact; every deployment is a reproducible Python function.

---

## The Model

Container infrastructure is organized into four composable layers:

```
ImageCard   ─┐
NetworkCard ─┤──▶  ContainerCard  ──▶  Unit  ──▶  Group  ──▶  workflow.py
VolumeCard  ─┘
```

| Layer | What it represents |
|---|---|
| **Card** | One atomic container resource (image, network, volume, or container config) |
| **Unit** | One running container instance — a ContainerCard reference |
| **Group** | A collection of Units + a Python `workflow.py` — the executable artifact |
| **Workflow** | A plain Python function `main(ctx: CutipContext)` — full control, no magic |

Every artifact is a versioned YAML file. Every ref is validated before any backend is contacted.

---

## Install

```shell
git clone <repo-url> cutip && cd cutip
uv venv && uv pip install -e .

# Runtime backend (choose one or both)
uv pip install -e ".[podman]"
uv pip install -e ".[docker]"

cutip --help
```

> [!NOTE]
> `cutip init`, `cutip tree`, `cutip validate`, `cutip show`, and `cutip plan` run without any container runtime installed. Only `cutip run` requires a backend.

---

## Quick Look

```yaml
# cutip/cards/images/app.yaml
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: app
spec:
  source: build
  context: containers/dockerfiles
  dockerfile: app.dockerfile
  tag: latest
```

```yaml
# cutip/cards/containers/app.yaml
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: app
spec:
  imageRef:
    ref: images/app
  networkRef:
    ref: networks/dev
  environment:
    ENV: production
  workdir: /app
```

```python
# cutip/groups/dev/workflow.py
def main(ctx):
    img  = ctx.resolved_cards["images/app"]
    cc   = ctx.resolved_cards["containers/app"]
    net  = ctx.resolved_cards["networks/dev"]

    ctx.runtime.build_image(img, project_root=ctx.project_root)
    ctx.runtime.ensure_network(net)
    ctx.runtime.create_container(cc, image_name=f"{img.name}:{img.spec.tag}")
    ctx.runtime.start_container(cc.name)
```

```shell
cutip validate
cutip plan dev
cutip run dev --backend podman
```

---

## CLI

| Command | Description |
|---|---|
| `cutip init [--path]` | Scaffold workspace directories and `cutip.yaml` |
| `cutip tree [--path]` | Print discovered cards, units, and groups |
| `cutip validate [--path]` | Full schema + graph validation (no backend required) |
| `cutip show card <ref>` | Dump a resolved card as YAML |
| `cutip show unit <name>` | Show a unit's resolved card graph |
| `cutip show group <name>` | Show a group's units and workflow status |
| `cutip plan <group> [--path]` | Dry-run: print execution table, start nothing |
| `cutip run <group> [--backend podman\|docker] [--local]` | Validate → connect → execute workflow |

Full flag reference: [`docs/reference/cli.md`](docs/reference/cli.md)

---

## Documentation

| Section | Contents |
|---|---|
| [Getting Started](docs/getting-started/installation.md) | Installation, quickstart, workspace layout |
| [Concepts](docs/concepts/overview.md) | The 4-layer model, cards, units, groups, graph resolution |
| [Reference](docs/reference/cli.md) | CLI flags, card schemas, workflow contract, exceptions |
| [Guides — Runtimes](docs/guides/runtimes/podman.md) | Podman (SSH tunnel + local), Docker, per-platform setup |
| [Guides — Workflows](docs/guides/workflows/writing-workflows.md) | Patterns, runtime injection, plan-safe guards |
| [Guides — CI/CD](docs/guides/ci-cd/github-actions.md) | GitHub Actions (build, Podman E2E, Docker E2E) |
| [Architecture](docs/architecture/design-decisions.md) | Design decisions, backend interface, registry internals |

---

## Project Status

| Backend | Status |
|---|---|
| Podman | ✅ Fully implemented (SSH tunnel + local socket) |
| Docker | ✅ Implemented (local daemon via docker-py) |

---

## License

[MIT](LICENSE)
