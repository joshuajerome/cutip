# CUTIP

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/latest/)
[![uv](https://img.shields.io/badge/uv-package_manager-6e44ff)](https://github.com/astral-sh/uv)
[![Runtime](https://img.shields.io/badge/runtime-podman%20%7C%20docker-892ca0)](https://joshuajerome.github.io/cutip/getting-started/installation/)
[![CI](https://github.com/joshuajerome/cutip/actions/workflows/pr-checks.yml/badge.svg)](https://github.com/joshuajerome/cutip/actions/workflows/pr-checks.yml)
[![Docs](https://img.shields.io/badge/docs-github%20pages-0969da)](https://joshuajerome.github.io/cutip)

**Container Unit Templates in Python** — a deterministic framework for defining, validating, and orchestrating container environments using structured YAML artifacts and Python workflows.

CUTIP is not a replacement for `docker-compose`. It is designed for a different use case: environments where the startup sequence is imperative, not declarative.

| | docker-compose | CUTIP |
|---|---|---|
| **Startup ordering** | `depends_on` with condition polling | Python loop — exec into container, branch on result |
| **Post-start hooks** | None native | `startup(ctx)` per unit — full container API |
| **Pre-build file staging** | None | `pre_build(ctx)` — generate config, copy deps before build |
| **Config variables** | `.env` flat substitution | `vars.yaml` with required/generated sections + fail-fast validation |
| **Validation** | Runtime only | Static graph validation — no backend required |
| **Orchestration logic** | Shell scripts outside compose | First-class Python in `workflow.py` |
| **Migration from compose** | — | `cutip from-compose` — convert any compose file to a CUTIP workspace |

> **[When to use each →](https://joshuajerome.github.io/cutip/getting-started/why-cutip/)**

---

## The Model

Container infrastructure is organized into four composable layers:

```
ImageCard   ─┐
NetworkCard ─┘──▶  ContainerCard  ──▶  Unit  ──▶  Group  ──▶  workflow.py
```

| Layer | What it represents |
|---|---|
| **Card** | One atomic container resource (image, network, or container configuration) |
| **Unit** | One running container instance — a ContainerCard reference |
| **Group** | A collection of Units + a Python `workflow.py` — the executable artifact |
| **Workflow** | A plain Python function `main(ctx: CutipContext)` — full control, no magic |

Every artifact is a versioned YAML file. Every ref is validated before any backend is contacted.

---

## Install

```shell
pip install cutip
cutip --help
```

> **Contributing?** Clone the repo and use `uv pip install -e .` for an editable install — see the [installation guide](https://joshuajerome.github.io/cutip/getting-started/installation/).

> [!NOTE]
> `cutip init`, `cutip from-compose`, `cutip tree`, `cutip validate`, `cutip show`, and `cutip plan` run without any container runtime installed. Only `cutip run` requires a container backend (Podman or Docker).

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
  context: resources/buildtime
  dockerfile: resources/dockerfiles/app.dockerfile
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
| `cutip from-compose <file> [--output-dir]` | Convert a `docker-compose.yaml` into a CUTIP workspace |
| `cutip tree [--path]` | Print discovered cards, units, and groups |
| `cutip validate [--path]` | Full schema + graph validation (no backend required) |
| `cutip show card <ref>` | Dump a resolved card as YAML |
| `cutip show unit <name>` | Show a unit's resolved card graph |
| `cutip show group <name>` | Show a group's units and workflow status |
| `cutip plan <group> [--path]` | Dry-run: print execution table, start nothing |
| `cutip run <group> [-b backend] [--local] [--path]` | Validate → connect → execute workflow |
| `cutip group ls` | List all groups in the workspace |
| `cutip unit ls` | List all units in the workspace |
| `cutip card ls` | List all cards in the workspace |

`cutip run` uses Podman by default. Pass `--backend docker` (or set `CUTIP_BACKEND=docker`) to use Docker instead. For Docker, install the optional extra: `pip install cutip[docker]`. Pass `--local` for direct socket connection (CI / rootless setups).

---

## vars.yaml

Workspace variables are declared in `cutip/vars.yaml` with two sections:

```yaml
required:
  ssh_private_key: ""   # must be filled in — cutip fails fast if empty

generated:
  data_dir: ".my-data"  # cutip creates this directory automatically
```

CUTIP validates all `{{ vars.key }}` references in cards before any container backend is contacted — missing or empty required values surface as a clear error, not a runtime failure.

---

## Documentation

Full documentation at **[joshuajerome.github.io/cutip](https://joshuajerome.github.io/cutip)**

| Section | Contents |
|---|---|
| [Getting Started](https://joshuajerome.github.io/cutip/getting-started/installation/) | Installation, quickstart, workspace layout |
| [Concepts](https://joshuajerome.github.io/cutip/concepts/overview/) | The 4-layer model, cards, units, groups, graph resolution |
| [Reference](https://joshuajerome.github.io/cutip/reference/cli/) | CLI flags, card schemas, workflow contract, exceptions |
| [Guides](https://joshuajerome.github.io/cutip/guides/runtimes/podman/) | Podman/Docker setup, writing workflows, CI/CD |

---

## License

[MIT](LICENSE)
