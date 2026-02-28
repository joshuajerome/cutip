# CUTIP

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/latest/)
[![uv](https://img.shields.io/badge/uv-package_manager-6e44ff)](https://github.com/astral-sh/uv)
[![Runtime](https://img.shields.io/badge/runtime-podman-892ca0)](https://podman.io/)

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
pip install cutip
```

Or install from source:

```shell
git clone https://github.com/joshuajerome/cutip && cd cutip
uv pip install -e .
cutip --help
```

> [!NOTE]
> `cutip init`, `cutip tree`, `cutip validate`, `cutip show`, and `cutip plan` run without any container runtime installed. Only `cutip run` requires Podman.

---

## Quick Look

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
    ctx.container("app").start()
```

```shell
cutip validate
cutip plan dev
cutip run dev
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
| `cutip run <group> [--local] [--path]` | Validate → connect → execute workflow |

Full reference: [CLI Reference](reference/cli.md)
