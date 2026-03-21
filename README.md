# CUTIP

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/latest/)
[![uv](https://img.shields.io/badge/uv-package_manager-6e44ff)](https://github.com/astral-sh/uv)
[![Runtime](https://img.shields.io/badge/runtime-podman%20%7C%20docker-892ca0)](https://joshuajerome.github.io/cutip/getting-started/installation/)
[![CI](https://github.com/joshuajerome/cutip/actions/workflows/ci.yml/badge.svg)](https://github.com/joshuajerome/cutip/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-github%20pages-0969da)](https://joshuajerome.github.io/cutip)

An automation tool for containerized workflows with deterministic Python hooks
at every stage of a container's lifecycle. Define infrastructure as structured
YAML cards, wire them into units and groups, then orchestrate with plain Python.

| | docker-compose | CUTIP |
|---|---|---|
| **Startup ordering** | `depends_on` with condition polling | Python loop -- exec into container, branch on result |
| **Post-start hooks** | None native | `startup(ctx)` per unit -- full container API |
| **Pre-build file staging** | None | `pre_build(ctx)` -- generate config, copy deps before build |
| **Config variables** | `.env` flat substitution | `paths.yaml` + `secrets.yaml` with fail-fast validation |
| **Validation** | Runtime only | Static graph validation -- no backend required |
| **Orchestration logic** | Shell scripts outside compose | First-class Python in `workflow.py` |
| **Migration from compose** | -- | `cutip from-compose` converts any compose file |

## Install

```shell
pip install cutip
```

## Getting Started

```shell
cutip init
cutip validate
cutip run hello-world
```

## Documentation

**[joshuajerome.github.io/cutip](https://joshuajerome.github.io/cutip)**

## License

[MIT](LICENSE)
