# CLI Reference

All commands accept `--path / -p <dir>` to override project root detection. By default, CUTIP resolves the project root via `git rev-parse --show-toplevel`, falling back to `cwd`.

---

## `cutip init`

Initialize a CUTIP workspace in the current project.

```shell
cutip init [--path PATH]
```

Creates (idempotently):

```
cutip.yaml
cutip/cards/{images,containers,networks,volumes}/
cutip/units/
cutip/groups/
.cutip/{logs,cache,runs,locks}/
```

Running `cutip init` on an existing workspace is safe — no existing files are modified.

---

## `cutip tree`

Print all discovered cards, units, and groups.

```shell
cutip tree [--path PATH]
```

Example output:

```
Project: /my/project
├── Cards
│   ├── containers/app
│   ├── images/app
│   └── networks/dev
├── Units
│   └── app
└── Groups
    └── dev
```

---

## `cutip validate`

Validate the full artifact graph — schema, ref resolution, and workflow file existence. No backend connection is made.

```shell
cutip validate [--path PATH]
```

On success:

```
Validation OK
```

On failure (all errors reported in one pass):

```
[UnitResolve] app: Card 'containers/missing' not found in registry
[WorkflowPath] dev: workflow file not found: '.../workflow.py'

2 error(s) found.
```

Exit code is `1` on validation failure.

---

## `cutip show card`

Dump a resolved card as YAML.

```shell
cutip show card <ref> [--path PATH]
```

`<ref>` uses the `<prefix>/<name>` format, e.g. `images/app`, `containers/db`.

---

## `cutip show unit`

Show a unit and its fully resolved card graph.

```shell
cutip show unit <name> [--path PATH]
```

Example output:

```
Unit: app
└── ContainerCard: app
    ├── ImageCard:   app
    └── NetworkCard: dev
```

For a container using `network_mode`:

```
Unit: frontend
└── ContainerCard: frontend
    ├── ImageCard:   frontend
    └── Network:     mode=host
```

---

## `cutip show group`

Show a group, its units, and workflow resolution status.

```shell
cutip show group <name> [--path PATH]
```

---

## `cutip plan`

Dry-run: compute the execution plan for a group and print it as a table. No containers are created.

```shell
cutip plan <group> [--path PATH]
```

Example output:

```
Plan for group: dev

┌────────┬──────────────────┬────────┬──────────────┐
│ Step   │ Action           │ Target │ Detail       │
├────────┼──────────────────┼────────┼──────────────┤
│ 1      │ pull_image       │ app    │ alpine:3.20  │
│ 2      │ ensure_network   │ dev    │ 10.89.0.0/16 │
│ 3      │ create_container │ app    │ app          │
│ 4      │ start_container  │ app    │              │
│ 5      │ run_workflow     │ ...    │              │
└────────┴──────────────────┴────────┴──────────────┘
```

`cutip plan` runs full graph validation before printing. It exits `1` if validation fails.

---

## `cutip run`

Validate, connect to the backend, and execute the group's workflow.

```shell
cutip run <group> [--backend podman|docker] [--local] [--path PATH]
```

| Flag | Default | Description |
|---|---|---|
| `--backend / -b` | `podman` | Which container runtime to use |
| `--local / -l` | `false` | Connect to local daemon directly (no SSH tunnel). Reads `CONTAINER_HOST` / `DOCKER_HOST` env vars. Required for CI. |
| `--path / -p` | git root / cwd | Override project root |

### Backend connection modes

**Podman — SSH tunnel (default):**

```shell
cutip run dev --backend podman
```

Reads the default connection from `podman system connection ls` and opens a TCP-over-SSH tunnel. Requires Podman to be installed and a machine to be running.

**Podman — local socket:**

```shell
cutip run dev --backend podman --local
```

Connects to the local Podman socket. Socket URL is resolved in priority order:
1. `CONTAINER_HOST` env var
2. Platform default (Linux: `unix:///run/user/<uid>/podman/podman.sock`, macOS: machine inspect, Windows: `npipe:////./pipe/podman-machine-default`)

**Docker:**

```shell
cutip run dev --backend docker
```

Docker always connects to the local daemon (`docker.from_env()`), which respects `DOCKER_HOST`.

### Environment variables

| Variable | Effect |
|---|---|
| `CUTIP_LOCAL=1` | Equivalent to passing `--local` |
| `CONTAINER_HOST` | Podman socket URL (used by `--local`) |
| `DOCKER_HOST` | Docker daemon socket URL (standard docker-py convention) |
| `CUTIP_BACKEND_NAME` | Informational — passed to `workflow.py` via `os.environ` |

---

## Global options

| Option | Description |
|---|---|
| `--help` | Show help for any command |
| `--version` | Show CUTIP version |
