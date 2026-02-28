# CUTIP Project Memory

## Project Paths

- **CUTIP source**: `~/dev/cutip` (git repo)
- **Consumer projects**: `~/dev/cutip-projects/snf-gui-dev` and `~/dev/cutip-projects/snf-blueprint-dev`
- **Run tests**: `cd ~/dev/cutip && uv run pytest tests/ -v --ignore=tests/e2e`
- **Validate project**: `cd <project> && uv run --project ~/dev/cutip cutip validate`

## Architecture Decisions

- **Podman only** — docker backend was removed. `podman>=4.0` is a core dependency (not optional).
- **No auto-start** — `workflow.main(ctx)` is always responsible for calling `ctx.container(name).start()`. CUTIP only creates containers.
- **vars.yaml** has `required:` (user-supplied, validated non-empty) and `generated:` (CUTIP creates dirs, never validated for emptiness).
- **Logging** uses 4 loguru sinks — subprocess lines (build output) rendered in grey; standard lines with full format. Both console and file.

## Key File Roles

- `cutip/cli/commands/run.py` — `_load_vars()`, `_validate_vars()`, `_prepare_generated_dirs()`, `_complete_group_name()`, `run()`
- `cutip/cli/commands/ls.py` — `group ls`, `unit ls`, `card ls` commands
- `cutip/utils/logging.py` — `setup_logging()` with 4 sinks; `SUBPROCESS_FMT`
- `cutip/backends/podman/backend.py` — `build_image()` with Popen streaming
- `cutip/workspace/scaffold.py` — `_find_project_root()`, `_CUTIP_VARS_YAML` template

## Consumer Project Conventions

### snf-gui-dev
- Group name: `snf-gui` (was `main`)
- Folder layout: `resources/buildtime/` (was `containers/resources/`), `resources/dockerfiles/`
- Has `sfm_vm_support/` package: `config.yaml` replaces `.env`; no GHE token; uses `kubectl exec` to copy keycloak handler file from pod to VM
- `sfm_vm_support/environment.py` uses `cutip.workspace.scaffold._find_project_root()`

### snf-blueprint-dev
- Group name: `snf-blueprint-manager` (was `main`)
- `vars.yaml` generated key: `blueprint_manager_data: ".snf-blueprint-manager-data"` → auto-creates `<project>/.snf-blueprint-manager-data/`
- Mounts use `{{ vars.blueprint_manager_data }}/sheets` and `.../infrastructures` with `create_host_path: true` to auto-create subdirs

## pyproject.toml Build Backend Fix

Both consumer projects use:
```toml
[build-system]
requires = ["setuptools>=42"]
build-backend = "setuptools.build_meta"
```
(NOT `setuptools.backends.legacy:build` which requires setuptools ≥ 70)

## Per-Unit startup.py Pattern

Every startup.py uses `from loguru import logger` (not `print()`). File logging goes through loguru automatically.

## Tab Completion

Install with: `cutip --install-completion`
Group name completion is wired via `autocompletion=_complete_group_name` on `cutip run GROUP_NAME`.
