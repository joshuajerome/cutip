# CUTIP — Claude Working Context

## What is CUTIP

Async workflow automation framework. Write orchestration logic in Python, execute I/O in Rust. Targets local machines, containers, or remote hosts. No agents, no YAML gymnastics, no speed tax.

- **cutip** — the framework (CLI, execution engine, decorators)
- **rsty** — Python-typed Rust modules (SSH, kubectl, containers, files, HTTP, packages, services, templates)

## Key Conventions

- **Never auto-commit.** Only commit when explicitly asked.
- **uv** is the Python package manager. Always `uv run`, `uv add`, `uv pip install`.
- **PRs**: Always `--assignee joshuajerome`
- **Read before edit** — never modify a file you haven't read in this session.

## Quick Commands

```bash
# Development
cd ~/dev/cutip-related/cutip
uv run pytest tests/ -v --ignore=tests/e2e          # unit tests
uv run maturin develop                                # build Rust extension

# Consumer project testing
cd <project-dir>
uv run --project ~/dev/cutip-related/cutip --with rsty cutip validate <project>.yaml
uv run --project ~/dev/cutip-related/cutip --with rsty cutip run <project>.yaml
```

## Architecture (v2)

### Project model

A cutip project is a YAML file with a `project:` field + a workflow Python file:

```
myproject/
├── gui.yaml              # project config (committed)
├── gui.workflow.py       # workflow logic (committed)
├── hosts.yaml            # credentials (gitignored)
├── .cutip/logs/          # run logs (gitignored)
└── .gitignore
```

### Config schema

```yaml
# gui.yaml
project: my-app
host: local                  # local | container | remote
container.rt: auto           # auto | podman | docker (only when host: container)

vars:
  greeting: "hello"

secrets:
  api_key: ""                # prompted if empty

connections:                 # auto-initialized, credentials from hosts.yaml
  vm:
    type: ssh
  k8s:
    type: kubectl
    session: vm
    namespace: prod

# Additional config sections (passed through to workflow as ctx.config)
kubernetes:
  deployment: web-app
```

### Hosts file (gitignored)

```yaml
# hosts.yaml — credentials for connections
vm:
  host: 10.0.0.1
  username: root
  password: secret
```

### Workflow model

```python
from cutip.workflow import action, orchestrator, stage

@orchestrator
def main(ctx):
    stage("Setup")
    check_access(ctx)

    stage("Deploy", parallel=True)
    deploy_backend(ctx)
    deploy_frontend(ctx)

@action(name="Check access")
def check_access(ctx):
    ctx.vm.probe()

@action(name="Deploy backend", retry=3, delay=5, on_fail="rollback")
def deploy_backend(ctx):
    ctx.k8s.patch_deployment(...)
```

### Decorator parameters

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `name` | str | required | Action display name |
| `retry` | int | 0 | Retry count on failure |
| `delay` | float | 0 | Seconds between retries |
| `backoff` | float | 1.0 | Multiply delay each retry |
| `timeout` | float | None | Kill after N seconds |
| `on_fail` | str | None | Action name to invoke on failure |
| `continue_on_fail` | bool | False | Continue workflow on failure |
| `when` | callable | None | Skip if returns False |

### Execution engine

The engine runs the `@orchestrator` directly — Python handles `if/else` branching. Each `@action` call is intercepted at runtime to apply orchestration policies. `stage()` emits events for CLI output.

```
@orchestrator main(ctx)
  → stage("Setup") emits stage_started
  → action(ctx) intercepted → retry/timeout/on_fail applied
  → stage("Deploy", parallel=True) → ThreadPoolExecutor
  → _close_connections() on exit
```

Error-type-aware retry: `AuthError`/`ValidationError` stop immediately. `ConnectionError`/`TimeoutError` are retried.

### WorkflowContext (ctx)

| Attribute | Type | Description |
|-----------|------|-------------|
| `ctx.config` | dict | Full parsed YAML |
| `ctx.vars` | dict[str, str] | User variables |
| `ctx.secrets` | dict[str, str] | Sensitive values |
| `ctx.results` | dict[str, Any] | Action return values (keyed by action name) |
| `ctx.host` | str | "local", "container", or "remote" |
| `ctx.container_runtime` | str | "auto", "podman", or "docker" |
| `ctx.{name}` | Connection | Named connections (SSH, kubectl, container) |
| `ctx.connection_host(name)` | str | IP/hostname of a named connection |

### CLI commands

| Command | Description |
|---------|-------------|
| `cutip init <name>` | Scaffold `<name>.yaml` + `<name>.workflow.py` |
| `cutip validate <project>.yaml` | Validate config, workflow syntax, connections |
| `cutip show <project>.yaml` | Project summary with execution steps |
| `cutip show <project>.yaml workflow` | List workflow actions in order |
| `cutip plan <project>.yaml` | Execution plan (dry run) |
| `cutip run <project>.yaml` | Execute workflow |
| `cutip run` | Auto-discover `*.yaml` projects in cwd |
| `cutip tree <project>.yaml` | Config structure as tree |
| `cutip verify` | Check prerequisites (Python, Docker, Podman, rsty) |

## Source layout

```
cutip/
├── Cargo.toml                    # Rust core (PyO3 config parser)
├── src/
│   ├── lib.rs                    # 3 PyO3 functions: validate, tree, show
│   ├── config/
│   │   ├── model.rs              # Config struct (host, container.rt, vars, etc.)
│   │   ├── loader.rs             # find_config, load_config
│   │   └── resolve.rs            # template resolution
│   └── commands/
│       ├── validate.rs           # returns validation dict
│       ├── tree.rs               # returns config as JSON
│       └── show.rs               # returns config section as YAML
├── cutip/
│   ├── cli.py                    # CLI entry point (rich formatted output)
│   ├── __main__.py               # python -m cutip
│   └── workflow/
│       ├── decorators.py         # @action, @orchestrator, stage(), ActionMeta, StageMeta
│       ├── engine.py             # WorkflowEngine, WorkflowContext, ActionFailed
│       ├── introspect.py         # AST extraction of actions/stages
│       ├── commands.py           # AST extraction of action commands
│       └── validate.py           # Comprehensive project validation
└── tests/
    ├── test_workflow_decorators.py
    └── test_stage_parsing.py
```

## rsty modules (Python-typed Rust)

| Module | Functions | Rust crate |
|--------|-----------|-----------|
| ssh | connect, SSHSession.exec/probe/close | russh |
| kubectl | connect, KubectlSession (10 methods) | russh + serde |
| container | connect, ContainerRuntime.build/create/start/stop/remove/exec/pull/exists | bollard |
| file | copy, copy_tree, read/write_json, read/write_yaml, replace, mkdir, is_empty | std::fs + serde |
| shell | run (cmd, cwd, env, check, stream) | std::process |
| http | get, post, put, delete → HttpResponse | reqwest |
| pkg | install, remove, update (auto-detects apt/dnf/yum/apk) | std::process |
| svc | start, stop, restart, enable, disable, is_active, status | std::process |
| template | render, render_string, check | std string ops |
| network | create, remove, exists | bollard |
| service | poll_until_ready, wait_for_exit | reqwest + bollard |
| validate | path_exists, env_var_set, ip_valid | std |
| config | render_template, substitute_vars | string ops |
| errors | CutipBlocksError, ConnectionError, TimeoutError, AuthError, CommandFailed, ValidationError | pyo3 |

## Versioning

Semantic versioning:
- **Major** — breaking changes to project model, CLI, or public API
- **Minor** — new features, new CLI commands, new config fields
- **Patch** — bug fixes, CI, docs, tooling

## Branch conventions

```
integration  ← release branches merge here, triggers release CI
  └── release/v{X}.{Y}.{Z}  (short-lived, triggers wheel builds + PyPI publish)
```

For features/fixes during active development, commit directly to integration or use short-lived branches. The cap ID system is optional for rapid iteration.

## Consumer projects

A cutip "consumer project" is any directory containing a `<name>.yaml`
+ `<name>.workflow.py` pair (plus optional `hosts.yaml` for SSH creds).
Cutip discovers and runs them via `cutip run <name>.yaml`. There's no
required directory structure beyond that — projects can sit at the repo
root, under `workspaces/`, or anywhere else convenient for the user.

## Current versions

| Package | Version | PyPI |
|---------|---------|------|
| cutip | 2.0.0 | published |
| rsty | 0.1.0 | published |
