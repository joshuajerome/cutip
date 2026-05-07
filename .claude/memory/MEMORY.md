# CUTIP Project Memory

## Project Paths

- **CUTIP source**: `~/dev/cutip` (git repo)
- **Run tests**: `cd ~/dev/cutip && uv run pytest tests/ -v --ignore=tests/e2e`
- **Validate a consumer project**: `cd <project> && uv run --project ~/dev/cutip cutip validate`

## Architecture Decisions

- **Podman + Docker** — both backends supported. Selectable via `--backend podman` / `--backend docker` or `CUTIP_BACKEND` env var.
- **No auto-start** — `workflow.main(ctx)` is always responsible for calling `ctx.container(name).start()`. CUTIP only creates containers.
- **vars.yaml** has `required:` (user-supplied, validated non-empty) and `generated:` (CUTIP creates dirs, never validated for emptiness).
- **Logging** uses 4 loguru sinks — subprocess lines (build output) rendered in grey; standard lines with full format. Both console and file.

## Key File Roles

- `cutip/cli.py` — CLI entry point + command handlers (`cmd_run`, `cmd_validate`, `cmd_hosts`, etc.)
- `cutip/workflow/decorators.py` — `@action`, `@orchestrator`, `stage()`
- `cutip/workflow/engine.py` — `WorkflowEngine`, `WorkflowContext`
- `cutip/workflow/cli_args.py` — workflow-declared CLI argument parsing (cutip 2.18+)
- `cutip/hosts.py` — hosts.yaml resolver + `cutip hosts` subcommands
- `cutip/templating.py` — `{{ vars.X }}` / `{{ paths.X }}` / `{{ secrets.X }}` / `{{ globals.X.Y.Z }}` substitution

## pyproject.toml Build Backend

Consumer projects typically use:
```toml
[build-system]
requires = ["setuptools>=42"]
build-backend = "setuptools.build_meta"
```
(NOT `setuptools.backends.legacy:build` which requires setuptools ≥ 70)

## Tab Completion

Install with: `cutip install-completion`
Project name completion is wired via shell-level path completion on `cutip run <project>.yaml`.
