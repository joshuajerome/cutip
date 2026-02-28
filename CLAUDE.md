# CUTIP — Claude Working Context

## What is CUTIP

**Container Unit Templates in Python** — a deterministic framework for defining, validating, and orchestrating container environments with structured YAML artifacts and Python workflows. **Podman is the only supported backend** (docker support was removed).

## Key Conventions

- **Never auto-commit.** Only commit when explicitly asked.
- **uv is the package manager.** Always use `uv run`, `uv add`, `uv pip install`.
- **Run tests** with: `cd ~/dev/cutip && uv run pytest tests/ -v --ignore=tests/e2e`
- **Validate a consumer project**: `cd <project> && uv run --project ~/dev/cutip cutip validate`
- **List workspace artifacts**: `cutip group ls` / `cutip unit ls` / `cutip card ls`

## Architecture

```
ImageCard ──┐
NetworkCard─┤──▶  ContainerCard  ──▶  Unit  ──▶  Group  ──▶  workflow.py
```

Every artifact is a versioned YAML file. Every ref is validated before any backend is contacted. The lifecycle is:

1. Load `cutip/vars.yaml` → flat vars dict (required + generated sections)
2. Create generated directories (`_prepare_generated_dirs`)
3. Validate all `{{ vars.X }}` refs are present and non-empty (skip generated keys)
4. Create host dirs (`create_host_path: true`) + named volumes
5. Run `pre_build(ctx)` in each unit's `startup.py`
6. Build/pull images, ensure networks, create containers
7. Call `workflow.main(ctx)` — starts containers, orchestrates
8. Run `startup(ctx)` in each unit's `startup.py`

## Directory Layout

```
cutip/
├── cutip/
│   ├── backends/podman/      # PodmanBackend — build_image uses Popen streaming
│   ├── cli/
│   │   ├── main.py           # Typer app root — add_typer + commands
│   │   └── commands/
│   │       ├── run.py        # _load_vars, _validate_vars, run()
│   │       ├── ls.py         # group/unit/card ls sub-apps
│   │       ├── show.py       # show card/unit/group
│   │       ├── plan.py       # dry-run
│   │       ├── tree.py       # workspace tree
│   │       ├── validate.py   # graph validation
│   │       └── init.py       # workspace scaffold
│   ├── context/
│   │   ├── workflow.py       # CutipContext — ctx.container(), ctx.vars, etc.
│   │   └── startup.py        # UnitStartupLoader — runs startup.py hooks
│   ├── models/
│   │   ├── cards/container.py  # ContainerCard, Mount, Ref, VolumeMount
│   │   ├── cards/image.py      # ImageCard (pull or build)
│   │   ├── cards/network.py    # NetworkCard
│   │   ├── group.py            # Group, GroupSpec
│   │   └── unit.py             # Unit, UnitSpec
│   ├── resolver/refs.py      # RefResolver — resolves "containers/name" refs
│   ├── utils/
│   │   ├── logging.py        # setup_logging() — 4 sinks (subprocess + standard × console/file)
│   │   └── exceptions.py     # CutipError, CutipWorkflowError, CutipRefError
│   ├── validation/graph.py   # GraphValidator
│   └── workspace/
│       ├── discovery.py      # WorkspaceDiscovery — scans cutip/ dir
│       ├── registry.py       # CutipRegistry — groups/units/cards dicts
│       └── scaffold.py       # WorkspaceScaffold — cutip init
└── tests/
    ├── test_models.py
    ├── test_resolver.py
    └── test_validation.py
```

## Per-Project Structure (consumer projects)

```
<project>/
├── cutip.yaml                  # project name/version
├── cutip/
│   ├── vars.yaml               # gitignored — user fills required:, generated: auto-created
│   ├── cards/<name>/
│   │   ├── <name>.image.yaml
│   │   └── <name>.container.yaml
│   ├── units/<name>/
│   │   ├── <name>.unit.yaml
│   │   └── startup.py          # pre_build(ctx) and startup(ctx) hooks
│   └── groups/<name>/
│       ├── group.yaml
│       └── workflow.py         # workflow.main(ctx) starts containers
└── resources/
    ├── buildtime/              # files staged into image build context
    └── dockerfiles/
        └── <name>.dockerfile
```

## vars.yaml Format

```yaml
required:
  my_repo: ""          # user must fill in — CUTIP fails fast if empty
  ssh_private_key: ""

generated:
  data_dir: ".my-data" # CUTIP creates <project_root>/.my-data/ automatically
                       # sub-dirs created by create_host_path: true mounts
```

## Logging Architecture

`setup_logging()` in `utils/logging.py` installs 4 sinks:

| Sink | Filter | Format | Level |
|---|---|---|---|
| Console | `subprocess=True` | Grey `<light-black>{message}</light-black>` | DEBUG |
| Console | standard | Full loguru format | INFO |
| File (`cutip.log`) | `subprocess=True` | `{message}` (plain) | DEBUG |
| File (`cutip.log`) | standard | Full loguru format | DEBUG |

Build output goes through `logger.bind(subprocess=True).debug(raw_line)`.

## Shell Tab Completion

`cutip --install-completion` installs shell completion. Group names in `cutip run` auto-complete via the `_complete_group_name()` callback.

## Consumer Projects

Both are at `~/dev/cutip-projects/`:

### snf-gui-dev
- Group: `snf-gui`
- Container: `snf-gui`
- `sfm_vm_support/` package — uses `config.yaml` (not `.env`); kubectl exec for keycloak patch
- `vars.yaml` required: `snf_repo`, `ssh_private_key`, `ssh_public_key`

### snf-blueprint-dev
- Group: `snf-blueprint-manager`
- Container: `snf-blueprint-manager` (Ansible/blueprint tooling)
- `vars.yaml` required: `ssh_private_key`, `ssh_public_key`, `blueprint_manager`
- `vars.yaml` generated: `blueprint_manager_data: ".snf-blueprint-manager-data"`
  - Mounts: `{{ vars.blueprint_manager_data }}/sheets` and `.../infrastructures` with `create_host_path: true`

## Recent Work (this development cycle)

- Renamed `containers/` → `resources/`, `containers/resources/` → `resources/buildtime/`
- Moved `podman>=4.0` to core deps (docker removed as supported backend)
- Renamed groups: `main` → `snf-gui` / `snf-blueprint-manager`
- Added `_validate_vars()` — checks `{{ vars.X }}` refs are present + non-empty (skips generated keys)
- Added `_prepare_generated_dirs()` — creates generated var directories before lifecycle
- Build output: `subprocess.Popen` streaming → `logger.bind(subprocess=True).debug()`
- Added `cutip group ls`, `cutip unit ls`, `cutip card ls` commands
- Added tab-completion for group names in `cutip run`
- New `vars.yaml` schema: `required:` / `generated:` sections
