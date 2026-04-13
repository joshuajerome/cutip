# CUTIP

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/latest/)
[![uv](https://img.shields.io/badge/uv-package_manager-6e44ff)](https://github.com/astral-sh/uv)
[![Runtime](https://img.shields.io/badge/runtime-podman%20%7C%20docker-892ca0)](https://joshuajerome.github.io/cutip/getting-started/installation/)
[![CI](https://github.com/joshuajerome/cutip/actions/workflows/ci.yml/badge.svg)](https://github.com/joshuajerome/cutip/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-github%20pages-0969da)](https://joshuajerome.github.io/cutip)

Automate multi-step operations using containers as reproducible execution environments.

CUTIP is a workflow automation framework. You define container infrastructure as typed YAML artifacts, write orchestration logic in Python, and CUTIP handles the lifecycle: pre-build file generation, container startup ordering, health-check loops, and post-deployment verification. Every artifact is validated statically before any container runtime is contacted.

**Containers are the medium, not the goal.** The task is the goal — SSH into a VM, configure a service, patch a deployment, start a dev environment. CUTIP makes that operation structured, validated, and reproducible.

## What cutip is NOT

- **Not a Docker replacement.** cutip uses Docker or Podman as backends. It does not build images differently or replace `docker run`.
- **Not a Kubernetes orchestrator.** cutip manages local container workloads. For K8s operations, use [cutip-blocks](https://github.com/joshuajerome/cutip-blocks) which provides kubectl blocks over SSH.
- **Not a CI/CD system.** cutip runs workflows locally or in containers. It complements CI — it doesn't replace GitHub Actions or Jenkins.
- **Not a Docker Compose replacement for simple stacks.** If you're running postgres + redis + your app with no custom startup logic, use Compose. cutip solves a different class of problems.

## Who is this for

- DevOps engineers automating VM or Kubernetes operations that span multiple tools (SSH, kubectl, REST APIs)
- Teams that outgrew bash scripts but don't need the weight of Ansible
- Developers who want reproducible multi-step procedures with validation, hooks, and visual inspection
- Anyone who needs to generate config files, exec into containers during startup, or branch on health state

## The model

```
ImageCard   ─┐
NetworkCard ─┘──>  ContainerCard  ──>  Unit  ──>  Group  ──>  workflow.py
```

| Layer | What it is |
|---|---|
| **Card** | A YAML file defining one container resource (image, network, or container config). Validated by Pydantic v2. |
| **Unit** | A named container instance — references one ContainerCard + optional pre/post hooks. |
| **Group** | A collection of Units + a `workflow.py`. The executable artifact: `cutip run <group>`. |
| **Workflow** | A Python function `main(ctx)` that starts containers, runs health checks, and orchestrates. Full Python — no DSL. |

Every artifact is a versioned YAML file (`apiVersion: cutip/v1`). Every ref is resolved and validated before any backend is contacted.

## Install

```shell
pip install cutip
```

## Quick start

```shell
cutip init              # scaffold a workspace with example projects
cutip validate          # static validation — no container runtime needed
cutip plan hello-world  # dry-run — print what would happen
cutip run hello-world   # validate → connect → execute workflow
```

## Before and after

**Before (bash script):**
```bash
#!/bin/bash
ssh root@$VM_IP "kubectl exec -n prod deploy/web -- cat /opt/config/handler.py > /root/patches/handler.py"
ssh root@$VM_IP "sed -i 's|get_host(req)|localhost:4000|g' /root/patches/handler.py"
ssh root@$VM_IP "chmod 777 /root/patches/handler.py"
ssh root@$VM_IP "kubectl get deployment -n prod web -o yaml | python3 -c 'import sys,yaml; ...' | kubectl apply -f -"
ssh root@$VM_IP "kubectl rollout status deployment -n prod web --timeout=120s"
# Hope nothing went wrong. No validation. No rollback. No visibility.
```

**After (cutip workflow):**
```python
@orchestrator
def main(ctx):
    container.start(ctx, container="ops-runner")

    with ssh.session(ctx, container="ops-runner",
                     host=vm["ip"], username="root", password=pw) as sesh:

        stage("Pre-op Validation")
        ssh.probe(ctx, sesh)
        k8s.get_deployment(ctx, sesh, namespace="prod", deployment="web")

        stage("Operations")
        patch_handler(ctx, sesh)
        apply_deploy(ctx, sesh)

        stage("Post-op Validation")
        k8s.rollout_status(ctx, sesh, namespace="prod", deployment="web")

    container.stop(ctx, container="ops-runner")
```

Every step is a named `@action`. The workflow is validated before execution. Failed steps report which action and stage broke. The entire pipeline is visible as a DAG in [CUTIP Desktop](https://github.com/joshuajerome/cutip-desktop).

## How it compares

| | Bash script | Docker Compose | Ansible | CUTIP |
|---|---|---|---|---|
| **Validation** | None | Runtime only | YAML lint | Static graph validation — no runtime needed |
| **Reproducibility** | Hope-based | Image tags | Playbook idempotency | Deterministic: same YAML + same workflow = same result |
| **Startup ordering** | Sequential commands | `depends_on` with health poll | Task ordering | Python: exec into container, branch on result |
| **Pre-build hooks** | Makefile target | None | None | `pre_build(ctx)` per unit |
| **Post-start hooks** | None | None | Handlers (limited) | `startup(ctx)` per unit |
| **Secrets** | `.env` or hardcoded | `.env` flat substitution | Vault / vars | `secrets.yaml` with fail-fast validation |
| **Visual inspection** | `set -x` | None | `--verbose` | DAG visualization in [CUTIP Desktop](https://github.com/joshuajerome/cutip-desktop) |
| **Migration** | Manual | — | Manual | `cutip from-compose` converts any compose file |

## Ecosystem

| Project | Description |
|---|---|
| [cutip](https://github.com/joshuajerome/cutip) | Core framework — YAML artifacts, Python workflows, CLI |
| [cutip-blocks](https://github.com/joshuajerome/cutip-blocks) | Reusable workflow blocks — SSH, kubectl, file ops, container lifecycle (34 blocks, 9 categories) |
| [cutip-desktop](https://github.com/joshuajerome/cutip-desktop) | Visual companion — DAG visualization, artifact inspection, container management, observability |

## CLI

| Command | Description |
|---|---|
| `cutip init` | Scaffold workspace with example projects |
| `cutip validate` | Static graph validation (no runtime needed) |
| `cutip plan <group>` | Dry-run: print execution table |
| `cutip run <group>` | Validate, connect, execute workflow |
| `cutip tree` | Print workspace artifact tree |
| `cutip show <type> <name>` | Dump a resolved artifact |
| `cutip from-compose <file>` | Convert a Docker Compose file to cutip artifacts |
| `cutip secrets set/list/check` | Manage secrets.yaml |

## Documentation

**[joshuajerome.github.io/cutip](https://joshuajerome.github.io/cutip)**

- [Why CUTIP?](https://joshuajerome.github.io/cutip/getting-started/why-cutip/) — detailed comparison with Docker Compose
- [Concepts](https://joshuajerome.github.io/cutip/concepts/overview/) — cards, units, groups, lifecycle, graph resolution
- [Quickstart](https://joshuajerome.github.io/cutip/getting-started/quickstart/) — end-to-end walkthrough
- [Use Cases](https://joshuajerome.github.io/cutip/guides/use-cases/) — real-world examples

## License

[MIT](LICENSE)
