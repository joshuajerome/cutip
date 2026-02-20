# CUTIP

[![Static Badge](https://img.shields.io/badge/python-3.11%2B-3776ab)](https://www.python.org/downloads/)
[![Static Badge](https://img.shields.io/badge/pydantic-v2-e92063)](https://docs.pydantic.dev/latest/)
[![Static Badge](https://img.shields.io/badge/uv-package_manager-6e44ff)](https://github.com/astral-sh/uv)
[![Static Badge](https://img.shields.io/badge/runtime-podman%20%7C%20docker-e44c11)](https://podman.io/)

<!-- TOC -->
- [CUTIP](#cutip)
  - [📚 About](#-about)
  - [🧱 Core Concepts](#-core-concepts)
    - [Cards](#cards)
    - [Units](#units)
    - [Groups](#groups)
  - [✅ Prerequisites](#-prerequisites)
  - [📦 Installation](#-installation)
  - [🗂️ Workspace Layout](#️-workspace-layout)
  - [🚀 Quick Start](#-quick-start)
  - [🖥️ CLI Reference](#️-cli-reference)
  - [📄 Card Reference](#-card-reference)
    - [ImageCard](#imagecard)
    - [ContainerCard](#containercard)
    - [NetworkCard](#networkcard)
    - [VolumeCard](#volumecard)
  - [🔗 Unit & Group Reference](#-unit--group-reference)
    - [Unit](#unit)
    - [Group](#group)
  - [🐍 Workflow Contract](#-workflow-contract)
  - [🧪 Testing](#-testing)
<!-- /TOC -->

## 📚 About

**CUTIP** (Container Unit Templates in Python) is a deterministic Python framework for defining and orchestrating container environments using structured YAML artifacts and Python workflows.

Container infrastructure is organized into three composable levels:

```
ImageCard   ─┐
NetworkCard ─┤─▶  ContainerCard  ─▶  Unit  ─▶  Group  ─▶  workflow.py
VolumeCard  ─┘
```

CUTIP provides:

* A **declarative layer** — Cards, Units, and Groups defined as versioned YAML
* A **validation layer** — Pydantic v2 schema enforcement + semantic graph checking
* A **workflow layer** — Python orchestration via `main(ctx: CutipContext)`
* An **execution layer** — Podman and Docker backends (Docker is a stub; Podman is fully implemented)

## 🧱 Core Concepts

### Cards

Cards are the smallest building blocks. Each card represents one atomic container component.

| Kind | What it defines |
|---|---|
| `ImageCard` | How an image is pulled or built |
| `ContainerCard` | Runtime configuration (refs to an image and a network) |
| `NetworkCard` | Network driver, subnet, and gateway |
| `VolumeCard` | Named volume with driver and options |

Cards live under `cutip/cards/<kind>/`.

### Units

A **Unit** composes the cards needed for one running container instance. It holds a single `containerRef` that points to a `ContainerCard`, which transitively references an `ImageCard` and a `NetworkCard`.

Units live under `cutip/units/`.

### Groups

A **Group** is a collection of Units plus a Python `workflow.py`. Groups are the top-level executable artifact — `cutip run` operates on a group.

Groups live under `cutip/groups/<group-name>/`.

## ✅ Prerequisites

* **Python 3.11+**
* **[uv](https://github.com/astral-sh/uv)** — package manager
* **[Podman](https://podman.io/)** _(required for `cutip run` with the Podman backend)_
  * Podman machine must be initialized and running (`podman machine start`)
  * A default connection must be present (`podman system connection ls`)

> [!NOTE]
> CUTIP itself installs without Podman. The `podman` SDK is an optional extra (`uv add "cutip[podman]"`). You can use `cutip init`, `cutip tree`, `cutip validate`, `cutip show`, and `cutip plan` without any container runtime installed.

## 📦 Installation

1. Clone the repository and navigate into it:

    ```shell
    git clone <repo-url> cutip
    cd cutip
    ```

2. Create a virtual environment and install dependencies:

    ```shell
    uv venv
    uv pip install -e .
    ```

3. _(Optional)_ Install the Podman backend extra:

    ```shell
    uv add "cutip[podman]"
    ```

4. Verify the CLI is available:

    ```shell
    cutip --help
    ```

## 🗂️ Workspace Layout

After running `cutip init` inside a project, the following structure is created:

```
cutip.yaml              ← project metadata (name, version)
cutip/                  ← version-controlled artifacts
│
├── cards/
│   ├── images/         ← ImageCard YAMLs
│   ├── containers/     ← ContainerCard YAMLs
│   ├── networks/       ← NetworkCard YAMLs
│   └── volumes/        ← VolumeCard YAMLs
│
├── units/              ← Unit YAMLs
│
└── groups/
    └── <group-name>/
        ├── group.yaml  ← Group YAML
        └── workflow.py ← Python workflow

.cutip/                 ← runtime state (add to .gitignore)
├── logs/
├── cache/
├── runs/
└── locks/
```

> [!IMPORTANT]
> Add `.cutip/` to your `.gitignore`. It contains runtime-only state (logs, locks, run artifacts) and should not be committed.

## 🚀 Quick Start

**1. Initialize CUTIP in your project:**

```shell
cutip init
```

**2. Define an image card** (`cutip/cards/images/my-image.yaml`):

```yaml
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: my-image
spec:
  source: pull
  image: ubuntu
  tag: "22.04"
```

**3. Define a network card** (`cutip/cards/networks/my-network.yaml`):

```yaml
apiVersion: cutip/v1
kind: NetworkCard
metadata:
  name: my-network
spec:
  driver: bridge
  subnet: "10.89.0.0/16"
  gateway: "10.89.0.1"
```

**4. Define a container card** (`cutip/cards/containers/my-container.yaml`):

```yaml
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: my-container
spec:
  imageRef:
    ref: images/my-image
  networkRef:
    ref: networks/my-network
  command: "tail -f /dev/null"
```

**5. Define a unit** (`cutip/units/my-unit.yaml`):

```yaml
apiVersion: cutip/v1
kind: Unit
metadata:
  name: my-unit
spec:
  containerRef:
    ref: containers/my-container
```

**6. Define a group** (`cutip/groups/infra/group.yaml`):

```yaml
apiVersion: cutip/v1
kind: Group
metadata:
  name: infra
spec:
  units:
    - ref: units/my-unit
  workflow: workflow.py
```

**7. Write a workflow** (`cutip/groups/infra/workflow.py`):

```python
def main(ctx):
    print(f"Deploying: {ctx.group.name}")
    for name, unit in ctx.resolved_units.items():
        ctx.runtime.prepare_unit(ctx.resolved_cards[unit.spec.containerRef.ref])
```

**8. Validate, inspect, and run:**

```shell
cutip validate
cutip plan infra
cutip run infra
```

## 🖥️ CLI Reference

| Command | Description |
|---|---|
| `cutip init [--path]` | Initialize a CUTIP workspace (creates `cutip/`, `.cutip/`, `cutip.yaml`) |
| `cutip tree [--path]` | Print a tree of all discovered cards, units, and groups |
| `cutip validate [--path]` | Validate the full artifact graph (schema + ref resolution) |
| `cutip show card <ref>` | Inspect a card (e.g. `cutip show card containers/my-container`) |
| `cutip show unit <name>` | Show a unit and its fully resolved card graph |
| `cutip show group <name>` | Show a group, its units, and workflow resolution status |
| `cutip plan <group>` | Dry-run: print the execution table without starting anything |
| `cutip run <group> [--backend podman\|docker]` | Validate → connect backend → execute workflow |

### Example: `cutip tree`

```
Project: /my/project
├── Cards
│   ├── containers/my-container
│   ├── images/my-image
│   └── networks/my-network
├── Units
│   └── my-unit
└── Groups
    └── infra
```

### Example: `cutip show unit my-unit`

```
Unit: my-unit
└── ContainerCard: my-container
    ├── ImageCard:   my-image
    └── NetworkCard: my-network
```

### Example: `cutip validate`

```
Validation OK
```

Or, on failure:

```
[UnitResolve] my-unit: Card 'containers/bad-ref' not found in registry
[WorkflowPath] infra: workflow file not found: '.../workflow.py'

2 error(s) found.
```

## 📄 Card Reference

All cards share the same envelope:

```yaml
apiVersion: cutip/v1      # required, must be exactly "cutip/v1"
kind: <CardKind>          # required
metadata:
  name: <string>          # required, used as the registry key
  labels: {}              # optional
spec:
  ...
```

### ImageCard

```yaml
spec:
  source: pull | build    # required
  image: <str>            # required if source: pull  (e.g. "ubuntu")
  tag: <str>              # default: "latest"
  context: <path>         # required if source: build (path to Dockerfile dir)
  dockerfile: <str>       # default: "Dockerfile"
  build_args: {}          # key-value pairs passed to docker/podman build
```

### ContainerCard

```yaml
spec:
  imageRef:
    ref: images/<name>      # required
  networkRef:
    ref: networks/<name>    # required
  command: <str>            # optional shell command
  hostname: <str>           # optional
  privileged: false
  ports: {}                 # { "8080/tcp": "8080" }
  environment: {}           # { "MY_VAR": "value" }
  mounts:
    - type: bind | volume
      source: <path>
      target: <path>
      read_only: false
  cap_add: []
  security_opts: []
  restart_policy: <str>     # e.g. "always"
```

### NetworkCard

```yaml
spec:
  driver: bridge            # default: "bridge"
  subnet: "10.89.0.0/16"   # required, must be valid CIDR
  gateway: "10.89.0.1"     # optional, must be within subnet
```

### VolumeCard

```yaml
spec:
  driver: local             # default: "local"
  labels: {}
  options: {}
```

## 🔗 Unit & Group Reference

### Unit

```yaml
apiVersion: cutip/v1
kind: Unit
metadata:
  name: <name>
spec:
  containerRef:
    ref: containers/<name>    # must resolve to a ContainerCard
```

### Group

```yaml
apiVersion: cutip/v1
kind: Group
metadata:
  name: <name>
spec:
  units:
    - ref: units/<name>       # one or more unit refs
  workflow: workflow.py       # relative path to workflow, from this file's directory
```

## 🐍 Workflow Contract

CUTIP dynamically imports a group's `workflow.py` and calls `main(ctx)`. The `ctx` argument is a `CutipContext` dataclass:

```python
@dataclass
class CutipContext:
    group: Group                              # the Group being executed
    resolved_units: dict[str, Unit]           # unit name → Unit
    resolved_cards: dict[str, CutipBaseModel] # card ref → Card
    registry: CutipRegistry                   # full workspace registry
    project_root: Path                        # absolute path to project root
    runtime: CutipBackend | None              # backend handle (None in plan/dry-run)
```

A minimal workflow:

```python
def main(ctx):
    for name, unit in ctx.resolved_units.items():
        container_ref = unit.spec.containerRef.ref
        container_card = ctx.resolved_cards[container_ref]
        ctx.runtime.create_container(container_card)
        ctx.runtime.start_container(container_card.name)
```

> [!TIP]
> `ctx.runtime` is `None` when invoked via `cutip plan`. Guard against this if you want your workflow to be plan-safe:
> ```python
> def main(ctx):
>     if ctx.runtime is None:
>         print("Dry-run mode — skipping container operations")
>         return
>     ...
> ```

## 🧪 Testing

Run the test suite with `uv`:

```shell
uv run pytest
```

Tests live under `tests/` and cover model validation, ref resolution, and graph validation. Fixture YAML files are under `tests/fixtures/`.
