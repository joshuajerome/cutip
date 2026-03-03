# Workspace Layout

`cutip init` creates the following structure inside your project root:

```
cutip.yaml                   ← project metadata (name, description)
│
cutip/                       ← version-controlled artifacts (commit this)
│
├── cards/
│   ├── images/              ← ImageCard YAMLs
│   ├── containers/          ← ContainerCard YAMLs
│   └── networks/            ← NetworkCard YAMLs
│
├── units/                   ← Unit YAMLs
│
└── groups/
    └── <group-name>/
        ├── group.yaml       ← Group artifact
        └── workflow.py      ← Python orchestration entry point

.cutip/                      ← runtime state (add to .gitignore)
├── logs/
├── cache/
├── runs/
└── locks/
```

---

## Discovery rules

CUTIP's workspace discovery (`WorkspaceDiscovery`) walks the `cutip/` directory and parses every `*.yaml` / `*.yml` file it finds. Files are registered by their `kind` and `metadata.name`:

| File path | Registry key |
|---|---|
| `cutip/cards/images/app.yaml` | `images/app` |
| `cutip/cards/containers/db.yaml` | `containers/db` |
| `cutip/cards/networks/prod.yaml` | `networks/prod` |
| `cutip/units/app.yaml` | `units/app` (unit registry) |
| `cutip/groups/infra/group.yaml` | `groups/infra` (group registry) |

Card refs in YAML always use the `<prefix>/<name>` format:

```yaml
imageRef:
  ref: images/app       # resolves cutip/cards/images/app.yaml
networkRef:
  ref: networks/prod    # resolves cutip/cards/networks/prod.yaml
```

---

## Project root detection

CUTIP resolves the project root by running `git rev-parse --show-toplevel`. If not in a git repo, it falls back to the current working directory. All relative paths in cards and workflows are resolved from this root.

Override at any time with `--path /absolute/path/to/project`.

---

## What to commit vs. what to ignore

```gitignore
# Always ignore — runtime only
.cutip/

# Ignore .env (contains secrets and machine-local paths)
.env

# Commit everything else
cutip/
cutip.yaml
```

---

## Multiple groups in one project

A project may contain multiple groups, each with its own workflow:

```
cutip/groups/
├── dev/
│   ├── group.yaml
│   └── workflow.py
├── staging/
│   ├── group.yaml
│   └── workflow.py
└── tools/
    ├── group.yaml
    └── workflow.py
```

All groups share the same card and unit registry. Run them independently:

```shell
cutip run dev
cutip run staging
cutip run tools
```
