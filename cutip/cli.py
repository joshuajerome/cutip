"""cutip CLI — Python wrapper over Rust core, formatted with rich."""

import sys
import json
import importlib.util
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import box

from cutip._core import validate as _validate, tree as _tree, show as _show

VERSION = "2.5.0"
console = Console()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _resolve_project(project_arg: str | None) -> Path:
    """Resolve a project YAML file path.

    If project_arg is given, use it directly.
    If not, look for *.yaml files with a 'project:' field in cwd.
    """
    if project_arg:
        path = Path(project_arg)
        if path.is_dir():
            # User passed a directory — look for config.yaml inside (backward compat)
            candidate = path / "config.yaml"
            if candidate.exists():
                return candidate
            console.print(f"[red]Error:[/red] No config.yaml found in {path}")
            sys.exit(1)
        if not path.suffix:
            path = path.with_suffix(".yaml")
        if not path.exists():
            console.print(f"[red]Error:[/red] {path} not found")
            sys.exit(1)
        return path

    # No arg — search cwd and parent directories for project YAML files
    import yaml

    search_dir = Path.cwd()
    while True:
        # Check for config.yaml (backward compat)
        if (search_dir / "config.yaml").exists():
            return search_dir / "config.yaml"

        # Check for *.yaml with project: field
        projects = []
        for f in sorted(search_dir.glob("*.yaml")):
            try:
                with open(f) as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict) and "project" in data:
                    projects.append(f)
            except Exception:
                continue

        if projects:
            break

        # Walk up
        parent = search_dir.parent
        if parent == search_dir:
            break  # reached filesystem root
        search_dir = parent

    if len(projects) == 1:
        return projects[0]

    if len(projects) > 1:
        console.print("[bold]Available projects:[/bold]")
        for p in projects:
            with open(p) as fh:
                data = yaml.safe_load(fh)
            name = data.get("project", p.stem)
            host = data.get("host", "local")
            console.print(f"  {p}  — {name} (host: {host})")
        console.print(f"\nUsage: cutip run <project.yaml>")
        sys.exit(0)

    console.print("[red]Error:[/red] No project YAML found in current directory")
    console.print("  Create one with: cutip init <name>")
    sys.exit(1)


def _resolve_workflow(project_path: Path, config: dict) -> Path:
    """Resolve the workflow file from a project config."""
    workflow_name = config.get("workflow")
    if not workflow_name:
        # Default: <stem>.workflow.py
        workflow_name = f"{project_path.stem}.workflow.py"
        # Fallback: workflow.py (backward compat)
        candidate = project_path.parent / workflow_name
        if not candidate.exists():
            workflow_name = "workflow.py"

    return project_path.parent / workflow_name


def _load_config(project_path: Path) -> dict:
    """Load and return project config as a dict."""
    import yaml
    with open(project_path) as f:
        config = yaml.safe_load(f) or {}
    return config


def _resolve_host(config: dict) -> str:
    """Resolve host from config, with backward compat for 'backend'."""
    host = config.get("host")
    if host:
        return host
    backend = config.get("backend", "local")
    return "container" if backend in ("docker", "podman") else backend


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_validate(args):
    """Validate a project YAML file."""
    project_path = _resolve_project(args.get("project"))

    try:
        result = _validate(path=str(project_path))
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if args.get("json"):
        print(json.dumps(result, indent=2))
        return

    table = Table(title="Validation", box=box.ROUNDED, show_header=False, title_style="bold")
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("Project", result["project"])
    host = result.get("host", result.get("backend", "local"))
    table.add_row("Host", host)
    if host == "container":
        rt = result.get("container_runtime", result.get("container.rt", "auto"))
        table.add_row("Runtime", rt)
    table.add_row("Workflow", result.get("workflow", "workflow.py"))
    table.add_row("Vars", str(result["vars_count"]))

    if result["empty_secrets"]:
        table.add_row("Secrets", f"{result['secrets_count']} ([yellow]{len(result['empty_secrets'])} empty[/yellow])")
    else:
        table.add_row("Secrets", f"{result['secrets_count']}, all set")

    if result["containers_count"]:
        table.add_row("Containers", str(result["containers_count"]))
    if result["networks_count"]:
        table.add_row("Networks", str(result["networks_count"]))

    workflow_path = _resolve_workflow(project_path, _load_config(project_path))
    if workflow_path.exists():
        table.add_row("Workflow", "[green]exists[/green]")
    else:
        table.add_row("Workflow", f"[red]not found:[/red] {workflow_path.name}")

    console.print(table)

    if result["warnings"]:
        console.print()
        for w in result["warnings"]:
            console.print(f"  [yellow]⚠[/yellow] {w}")
        console.print("\n[yellow]⚠ Validation passed with warnings[/yellow]")
    else:
        console.print("\n[green]✓ Validation passed[/green]")


def cmd_tree(args):
    """Print config as tree."""
    project_path = _resolve_project(args.get("project"))

    try:
        config_json = _tree(path=str(project_path))
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if args.get("json"):
        print(config_json)
        return

    config = json.loads(config_json)
    tree = Tree(f"[bold]{config['project']}[/bold]")

    host = config.get("host") or ("container" if config.get("backend") in ("docker", "podman") else config.get("backend", "local"))
    tree.add(f"host: [cyan]{host}[/cyan]")
    if host == "container":
        rt = config.get("container.rt", config.get("container_runtime", "auto"))
        tree.add(f"container.rt: [cyan]{rt}[/cyan]")

    workflow = config.get("workflow", f"{project_path.stem}.workflow.py")
    tree.add(f"workflow: [cyan]{workflow}[/cyan]")

    if config.get("vars"):
        vars_branch = tree.add("vars")
        for k, v in config["vars"].items():
            display = f"[dim]{v!r}[/dim]" if v else "[yellow](empty)[/yellow]"
            vars_branch.add(f"{k}: {display}")

    if config.get("secrets"):
        secrets_branch = tree.add("secrets")
        for k, v in config["secrets"].items():
            masked = "[yellow](empty)[/yellow]" if not v else "[dim]****[/dim]"
            secrets_branch.add(f"{k}: {masked}")

    if config.get("connections"):
        conn_branch = tree.add("connections")
        for name, conn in config["connections"].items():
            conn_type = conn.get("type", "unknown")
            conn_branch.add(f"{name}: [cyan]{conn_type}[/cyan]")

    if config.get("container"):
        name = config["container"].get("name", "(unnamed)")
        tree.add(f"container: [cyan]{name}[/cyan]")

    if config.get("containers"):
        containers_branch = tree.add("containers")
        for name in config["containers"]:
            containers_branch.add(f"[cyan]{name}[/cyan]")

    if config.get("network"):
        name = config["network"].get("name", "(unnamed)")
        tree.add(f"network: [cyan]{name}[/cyan]")

    if config.get("networks"):
        networks_branch = tree.add("networks")
        for name in config["networks"]:
            networks_branch.add(f"[cyan]{name}[/cyan]")

    excluded = {"project", "host", "container.rt", "container_runtime", "backend",
                "workflow", "vars", "secrets", "connections",
                "image", "container", "containers", "network", "networks"}
    extra = {k for k in config if k not in excluded}
    if extra:
        tree.add(f"config: [dim]{', '.join(sorted(extra))}[/dim]")

    console.print(tree)


def cmd_show(args):
    """Show project summary, a config section, or workflow actions."""
    if "--help" in sys.argv or "-h" in sys.argv:
        console.print("[bold]cutip show[/bold] <project.yaml> [section]")
        console.print("  (no section)  Project summary with execution steps")
        console.print("  workflow      List workflow actions in execution order")
        console.print("  vars, secrets, container, connections, or any config key")
        return

    section = args.get("section")

    if not section:
        _show_summary(args)
        return

    if section == "workflow":
        _show_workflow(args)
        return

    project_path = _resolve_project(args.get("project"))
    try:
        result = _show(section, path=str(project_path))
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(Panel(result.strip(), title=section, box=box.ROUNDED))


def _show_summary(args):
    """Show project overview with what cutip run will do."""
    project_path = _resolve_project(args.get("project"))
    config = _load_config(project_path)
    host = _resolve_host(config)
    project = config.get("project", project_path.stem)
    workflow_path = _resolve_workflow(project_path, config)

    # Print tree
    cmd_tree(args)
    console.print()

    # Steps
    console.print("[bold]Steps:[/bold]")
    console.print(f"  1. Read [cyan]{project_path}[/cyan]")
    console.print(f"  2. Validate config")

    empty_vars = [k for k, v in (config.get("vars") or {}).items() if not v]
    step = 3
    if empty_vars:
        console.print(f"  {step}. Prompt for empty vars: [yellow]{', '.join(empty_vars)}[/yellow]")
        step += 1

    if host == "local":
        console.print(f"  {step}. Prepare environment: [cyan]local[/cyan]")
    elif host == "container":
        rt = config.get("container.rt", "auto")
        console.print(f"  {step}. Prepare environment: [cyan]container[/cyan] ({rt})")
    elif host == "remote":
        console.print(f"  {step}. Prepare environment: [cyan]remote[/cyan]")

    console.print(f"  {step + 1}. Run [cyan]{workflow_path.name}[/cyan]")

    # Workflow actions
    if workflow_path.exists():
        from cutip.workflow.introspect import extract_staged_action_order
        groups = extract_staged_action_order(workflow_path)
        if groups:
            console.print()
            console.print("[bold]Workflow:[/bold]")
            for group in groups:
                title = group.stage.title or "Stage"
                parallel = " [dim](parallel)[/dim]" if group.stage.parallel else ""
                console.print(f"  [bold]{title}[/bold]{parallel}")
                for a in group.actions:
                    extras = []
                    if a.retry:
                        extras.append(f"retry={a.retry}")
                    if a.timeout:
                        extras.append(f"timeout={a.timeout}s")
                    if a.on_fail:
                        extras.append(f"on_fail={a.on_fail}")
                    suffix = f" [dim]({', '.join(extras)})[/dim]" if extras else ""
                    console.print(f"    {a.name}{suffix}")


def _show_workflow(args):
    """Show workflow actions in execution order."""
    project_path = _resolve_project(args.get("project"))
    config = _load_config(project_path)
    workflow_path = _resolve_workflow(project_path, config)

    if not workflow_path.exists():
        console.print(f"[red]Error:[/red] {workflow_path.name} not found")
        sys.exit(1)

    from cutip.workflow.introspect import extract_staged_action_order
    groups = extract_staged_action_order(workflow_path)

    if not groups:
        console.print("[dim]No @action-decorated functions found in workflow[/dim]")
        return

    project = config.get("project", project_path.stem)
    console.print(f"[bold]{project}[/bold] — {workflow_path.name}\n")

    action_num = 0
    for group in groups:
        title = group.stage.title or "Stage"
        parallel = " [dim](parallel)[/dim]" if group.stage.parallel else ""
        console.print(f"[bold]  {title}[/bold]{parallel}")
        for a in group.actions:
            action_num += 1
            extras = []
            if a.retry:
                extras.append(f"retry={a.retry}")
            if a.delay:
                extras.append(f"delay={a.delay}s")
            if a.timeout:
                extras.append(f"timeout={a.timeout}s")
            if a.on_fail:
                extras.append(f"on_fail={a.on_fail}")
            if a.continue_on_fail:
                extras.append("continue_on_fail")
            suffix = f"  [dim]{', '.join(extras)}[/dim]" if extras else ""
            console.print(f"    {action_num}. {a.name}{suffix}")
        console.print()


def cmd_plan(args):
    """Show execution plan without running."""
    project_path = _resolve_project(args.get("project"))
    config = _load_config(project_path)
    host = _resolve_host(config)
    project = config.get("project", project_path.stem)
    workflow_path = _resolve_workflow(project_path, config)

    console.print(f"\n[bold]{project}[/bold] — execution plan\n")

    console.print(f"  Host:     [cyan]{host}[/cyan]")
    if host == "container":
        rt = config.get("container.rt", "auto")
        console.print(f"  Runtime:  [cyan]{rt}[/cyan]")
    console.print(f"  Workflow: [cyan]{workflow_path.name}[/cyan]")

    vars_dict = config.get("vars") or {}
    secrets_dict = config.get("secrets") or {}
    empty_vars = [k for k, v in vars_dict.items() if not v]
    empty_secrets = [k for k, v in secrets_dict.items() if not v]

    if vars_dict:
        console.print(f"  Vars:     {len(vars_dict)}", end="")
        if empty_vars:
            console.print(f" [yellow]({len(empty_vars)} will be prompted)[/yellow]")
        else:
            console.print()
    if secrets_dict:
        console.print(f"  Secrets:  {len(secrets_dict)}", end="")
        if empty_secrets:
            console.print(f" [yellow]({len(empty_secrets)} will be prompted)[/yellow]")
        else:
            console.print()

    if config.get("connections"):
        console.print(f"  Connections: {len(config['connections'])}")

    if not workflow_path.exists():
        console.print(f"\n  [red]Workflow not found:[/red] {workflow_path.name}")
        sys.exit(1)

    from cutip.workflow.introspect import extract_staged_action_order
    groups = extract_staged_action_order(workflow_path)

    if not groups:
        console.print(f"\n  [dim]No @action-decorated functions found[/dim]")
        return

    console.print()
    action_num = 0
    for group in groups:
        title = group.stage.title or "Stage"
        parallel = " [dim](parallel)[/dim]" if group.stage.parallel else ""
        console.print(f"  [bold]── {title} ──[/bold]{parallel}")
        for a in group.actions:
            action_num += 1
            extras = []
            if a.retry:
                extras.append(f"retry={a.retry}")
            if a.delay:
                extras.append(f"delay={a.delay}s")
            if a.backoff and a.backoff != 1.0:
                extras.append(f"backoff={a.backoff}x")
            if a.timeout:
                extras.append(f"timeout={a.timeout}s")
            if a.on_fail:
                extras.append(f"on_fail={a.on_fail}")
            if a.continue_on_fail:
                extras.append("continue_on_fail")
            suffix = f"  [dim]{', '.join(extras)}[/dim]" if extras else ""
            console.print(f"    {action_num}. {a.name}{suffix}")
        console.print()

    console.print(f"  [dim]{action_num} action(s) across {len(groups)} stage(s)[/dim]\n")


def cmd_run(args):
    """Run a workflow."""
    import yaml

    if "--help" in sys.argv or "-h" in sys.argv:
        console.print("[bold]cutip run[/bold] [project.yaml]")
        console.print("  Reads project YAML, runs the workflow")
        return

    project_path = _resolve_project(args.get("project"))
    config = _load_config(project_path)

    # Prompt for empty vars/secrets
    has_prompts = False
    for key, val in (config.get("vars") or {}).items():
        if not val:
            if not has_prompts:
                console.print()
                has_prompts = True
            config.setdefault("vars", {})[key] = console.input(f"  {key}: ")

    for key, val in (config.get("secrets") or {}).items():
        if not val:
            if not has_prompts:
                console.print()
                has_prompts = True
            config.setdefault("secrets", {})[key] = console.input(f"  {key}: ")

    if has_prompts:
        console.print()

    # Load hosts file (for remote connections)
    import yaml
    hosts = None
    hosts_path_arg = args.get("hosts")
    if hosts_path_arg:
        hosts_path = Path(hosts_path_arg)
    else:
        hosts_path = project_path.parent / "hosts.yaml"

    if hosts_path.exists():
        with open(hosts_path) as f:
            hosts = yaml.safe_load(f) or {}

    # Pre-run validation
    workflow_path = _resolve_workflow(project_path, config)
    from cutip.workflow.validate import validate_project
    errors, warnings = validate_project(project_path, config, hosts=hosts, workflow_path=workflow_path)
    if errors:
        console.print(f"\n[red]Validation failed:[/red]")
        for err in errors:
            console.print(f"  [red]✗[/red] {err}")
        sys.exit(1)
    if warnings:
        for w in warnings:
            console.print(f"  [yellow]⚠[/yellow] {w}")

    # Find and load workflow
    workflow_path = _resolve_workflow(project_path, config)

    if not workflow_path.exists():
        console.print(f"[red]Error:[/red] {workflow_path.name} not found")
        sys.exit(1)

    config_dir = project_path.parent
    spec = importlib.util.spec_from_file_location("workflow", str(workflow_path))
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(config_dir))
    spec.loader.exec_module(module)

    # Check if workflow uses @action/@orchestrator decorators → use engine
    from cutip.workflow.engine import WorkflowEngine, ActionFailed
    from cutip.workflow.decorators import _ACTION_ATTR

    has_actions = any(
        hasattr(getattr(module, attr, None), _ACTION_ATTR)
        for attr in dir(module)
        if callable(getattr(module, attr, None))
    )

    if has_actions:
        _run_with_engine(module, config, project_path, hosts)
    elif hasattr(module, "run_standalone"):
        module.run_standalone(config)
    elif hasattr(module, "main"):
        module.main(config)
    else:
        console.print("[red]Error:[/red] workflow has no @action functions, run_standalone(), or main()")
        sys.exit(1)


def _run_with_engine(module, config, project_path, hosts=None):
    """Execute a workflow using the cutip execution engine."""
    from datetime import datetime
    from cutip.workflow.engine import WorkflowEngine, ActionFailed, ActionEvent

    project = config.get("project", "workflow")

    # Set up .cutip/logs/ relative to project YAML
    log_dir = project_path.parent / ".cutip" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = log_dir / f"{timestamp}.log"
    log_lines = []

    def _log(line: str):
        log_lines.append(line)

    def on_event(event: ActionEvent):
        if event.event == "stage_started":
            console.print(f"\n[bold]── {event.action} ──[/bold]")
            _log(f"[stage] {event.action}")
            if event.detail:
                console.print(f"  [dim]{event.detail}[/dim]")
        elif event.event == "action_started":
            label = f"  [cyan]▶[/cyan] {event.action}"
            if event.attempt > 1:
                label += f" [dim](attempt {event.attempt})[/dim]"
            console.print(label)
            _log(f"  [start] {event.action}" + (f" (attempt {event.attempt})" if event.attempt > 1 else ""))
        elif event.event == "action_completed":
            console.print(f"  [green]✓[/green] {event.action}")
            _log(f"  [done] {event.action}")
        elif event.event == "action_failed":
            console.print(f"  [red]✗[/red] {event.action}: {event.error}")
            _log(f"  [FAIL] {event.action}: {event.error}")
        elif event.event == "action_retrying":
            console.print(f"  [yellow]↻[/yellow] {event.action} — {event.detail}")
            _log(f"  [retry] {event.action} — {event.detail}")
        elif event.event == "action_skipped":
            console.print(f"  [dim]○[/dim] {event.action} [dim](skipped)[/dim]")
            _log(f"  [skip] {event.action}")
        elif event.event == "stage_completed":
            pass

    engine = WorkflowEngine(module, config, on_event=on_event, hosts=hosts)

    try:
        ctx = engine.run()
        console.print(f"\n[green]✓ {project} complete[/green]")
        _log(f"\n[OK] {project} complete")
    except ActionFailed as e:
        console.print(f"\n[red]✗ {project} failed:[/red] {e}")
        _log(f"\n[FAIL] {project}: {e}")
        log_file.write_text("\n".join(log_lines) + "\n")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print(f"\n[yellow]⚠ {project} interrupted[/yellow]")
        _log(f"\n[INTERRUPTED] {project}")
        log_file.write_text("\n".join(log_lines) + "\n")
        sys.exit(130)

    log_file.write_text("\n".join(log_lines) + "\n")
    console.print(f"  [dim]log: {log_file}[/dim]")


def cmd_init(args):
    """Scaffold a new project."""
    if "--help" in sys.argv or "-h" in sys.argv:
        console.print("[bold]cutip init[/bold] <name>")
        console.print("  Creates <name>.yaml + <name>.workflow.py in current directory")
        return

    name = args.get("name")
    if not name:
        console.print("[bold]cutip init[/bold] <name>")
        sys.exit(1)

    yaml_path = Path(f"{name}.yaml")
    workflow_path = Path(f"{name}.workflow.py")

    if yaml_path.exists():
        console.print(f"[red]Error:[/red] {yaml_path} already exists")
        sys.exit(1)

    yaml_path.write_text(f"""project: {name}
host: local                  # local | container | remote
# container.rt: auto        # auto | podman | docker (only when host: container)

vars:
  greeting: "hello from {name}"

secrets:
  # api_key: ""              # prompted if empty at runtime
""")

    workflow_path.write_text(f'''"""{name} workflow."""

from cutip.workflow import action, orchestrator, stage


@orchestrator
def main(ctx):
    stage("Setup")
    check_environment(ctx)

    stage("Run")
    greet(ctx)


@action(name="Check environment")
def check_environment(ctx):
    from rsty import shell
    result = shell.run("echo ready", check=False)
    return result.stdout.strip()


@action(name="Greet")
def greet(ctx):
    print(f"  {{ctx.vars['greeting']}}")
''')

    # Create .gitignore if it doesn't exist
    gitignore = Path(".gitignore")
    if not gitignore.exists():
        gitignore.write_text("hosts.yaml\n.cutip/\n")
    else:
        content = gitignore.read_text()
        additions = []
        if "hosts.yaml" not in content:
            additions.append("hosts.yaml")
        if ".cutip/" not in content:
            additions.append(".cutip/")
        if additions:
            with open(gitignore, "a") as f:
                f.write("\n" + "\n".join(additions) + "\n")

    console.print(f"[green]✓[/green] Created [bold]{name}[/bold]")
    console.print(f"  {yaml_path}")
    console.print(f"  {workflow_path}")
    console.print()
    console.print(f"  [bold]Next:[/bold]")
    console.print(f"    cutip show {yaml_path}")
    console.print(f"    cutip run {yaml_path}")


def cmd_verify(args):
    """Check prerequisites and environment."""
    import subprocess
    import platform

    table = Table(title=f"cutip v{VERSION}", box=box.ROUNDED, show_header=False)
    table.add_column("Check", style="bold")
    table.add_column("Status")

    table.add_row("Platform", f"{platform.system()} {platform.machine()}")

    python_found = False
    for cmd in (["python", "--version"], ["python3", "--version"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                table.add_row("Python", f"[green]✓[/green] {r.stdout.strip()}")
                python_found = True
                break
        except Exception:
            continue
    if not python_found:
        table.add_row("Python", "[red]✗ not found[/red]")

    checks = [
        ("Docker", ["docker", "--version"]),
        ("Podman", ["podman", "--version"]),
    ]
    for name, cmd in checks:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                table.add_row(name, f"[green]✓[/green] {r.stdout.strip()}")
            else:
                table.add_row(name, "[dim]· not found[/dim]")
        except Exception:
            table.add_row(name, "[dim]· not found[/dim]")

    try:
        import rsty
        table.add_row("rsty", "[green]✓[/green] installed")
    except ImportError:
        table.add_row("rsty", "[red]✗ not installed[/red] (pip install rsty)")

    try:
        from cutip._core import validate
        table.add_row("cutip core", "[green]✓[/green] loaded")
    except ImportError:
        table.add_row("cutip core", "[red]✗ not loaded[/red]")

    console.print(table)


def _yaml_read(path: Path) -> dict:
    """Read a YAML file, return dict (empty dict if missing or null)."""
    import yaml
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _yaml_write(path: Path, data: dict) -> None:
    """Write a dict to a YAML file, preserving key order."""
    import yaml
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def cmd_vars(args):
    """Manage project variables."""
    subcmd = args.get("subcmd")
    if not subcmd or subcmd == "help":
        console.print("[bold]cutip vars[/bold] <list|get|set> [project.yaml] [key=value ...]")
        console.print("  list   Show all vars and their values")
        console.print("  get    Get a single var value")
        console.print("  set    Set one or more vars")
        return

    project_path = _resolve_project(args.get("project"))
    config = _load_config(project_path)

    if subcmd == "list":
        vars_dict = config.get("vars") or {}
        if not vars_dict:
            console.print("[dim]No vars defined[/dim]")
            return
        for k, v in vars_dict.items():
            if v:
                console.print(f"  {k} = [dim]{v}[/dim]")
            else:
                console.print(f"  {k} = [yellow](empty)[/yellow]")

    elif subcmd == "get":
        key = args.get("key")
        if not key:
            console.print("[red]Usage:[/red] cutip vars get [project.yaml] <key>")
            sys.exit(1)
        vars_dict = config.get("vars") or {}
        if key in vars_dict:
            console.print(vars_dict[key] or "")
        else:
            console.print(f"[red]Error:[/red] var '{key}' not found")
            sys.exit(1)

    elif subcmd == "set":
        pairs = args.get("pairs", [])
        if not pairs:
            console.print("[red]Usage:[/red] cutip vars set [project.yaml] key=value ...")
            sys.exit(1)
        if "vars" not in config or config["vars"] is None:
            config["vars"] = {}
        for pair in pairs:
            if "=" not in pair:
                console.print(f"[red]Error:[/red] invalid format '{pair}', expected key=value")
                sys.exit(1)
            k, v = pair.split("=", 1)
            config["vars"][k] = v
            console.print(f"  [green]✓[/green] {k} = {v}")
        _yaml_write(project_path, config)


def cmd_secrets(args):
    """Manage project secrets."""
    subcmd = args.get("subcmd")
    if not subcmd or subcmd == "help":
        console.print("[bold]cutip secrets[/bold] <list|get|set> [project.yaml] [key=value ...]")
        console.print("  list   Show all secret keys (values masked)")
        console.print("  get    Get a single secret value")
        console.print("  set    Set one or more secrets")
        return

    project_path = _resolve_project(args.get("project"))
    config = _load_config(project_path)

    if subcmd == "list":
        secrets_dict = config.get("secrets") or {}
        if not secrets_dict:
            console.print("[dim]No secrets defined[/dim]")
            return
        for k, v in secrets_dict.items():
            if v:
                console.print(f"  {k} = [dim]****[/dim]")
            else:
                console.print(f"  {k} = [yellow](empty)[/yellow]")

    elif subcmd == "get":
        key = args.get("key")
        if not key:
            console.print("[red]Usage:[/red] cutip secrets get [project.yaml] <key>")
            sys.exit(1)
        secrets_dict = config.get("secrets") or {}
        if key in secrets_dict:
            console.print(secrets_dict[key] or "")
        else:
            console.print(f"[red]Error:[/red] secret '{key}' not found")
            sys.exit(1)

    elif subcmd == "set":
        pairs = args.get("pairs", [])
        if not pairs:
            console.print("[red]Usage:[/red] cutip secrets set [project.yaml] key=value ...")
            sys.exit(1)
        if "secrets" not in config or config["secrets"] is None:
            config["secrets"] = {}
        for pair in pairs:
            if "=" not in pair:
                console.print(f"[red]Error:[/red] invalid format '{pair}', expected key=value")
                sys.exit(1)
            k, v = pair.split("=", 1)
            config["secrets"][k] = v
            console.print(f"  [green]✓[/green] {k} = ****")
        _yaml_write(project_path, config)


def _is_sensitive(key: str) -> bool:
    """Check if a key name suggests a sensitive value."""
    return any(s in key.lower() for s in ("password", "secret", "token", "key"))


def _resolve_hosts_path(project_path: Path) -> Path:
    """Resolve hosts file path from data.hosts or default to hosts.yaml."""
    config = _load_config(project_path)
    data = config.get("data") or {}
    hosts_ref = data.get("hosts", "hosts.yaml")
    hosts_path = project_path.parent / hosts_ref
    return hosts_path


def cmd_hosts(args):
    """Manage project hosts file."""
    subcmd = args.get("subcmd")
    if not subcmd or subcmd == "help":
        console.print("[bold]cutip hosts[/bold] <list|get|set> [project.yaml] [key=value ...]")
        console.print("  list   Show all host entries (passwords masked)")
        console.print("  get    Get a single host value")
        console.print("  set    Set one or more host values")
        return

    project_path = _resolve_project(args.get("project"))
    hosts_path = _resolve_hosts_path(project_path)
    hosts = _yaml_read(hosts_path)

    if subcmd == "list":
        if not hosts:
            console.print(f"[dim]No hosts defined in {hosts_path.name}[/dim]")
            return
        for k, v in hosts.items():
            if not v and v != 0:
                console.print(f"  {k} = [yellow](empty)[/yellow]")
            elif _is_sensitive(k):
                console.print(f"  {k} = [dim]****[/dim]")
            else:
                console.print(f"  {k} = [dim]{v}[/dim]")

    elif subcmd == "get":
        key = args.get("key")
        if not key:
            console.print("[red]Usage:[/red] cutip hosts get [project.yaml] <key>")
            sys.exit(1)
        if key in hosts:
            console.print(hosts[key] or "")
        else:
            console.print(f"[red]Error:[/red] key '{key}' not found in {hosts_path.name}")
            sys.exit(1)

    elif subcmd == "set":
        pairs = args.get("pairs", [])
        if not pairs:
            console.print("[red]Usage:[/red] cutip hosts set [project.yaml] key=value ...")
            sys.exit(1)
        for pair in pairs:
            if "=" not in pair:
                console.print(f"[red]Error:[/red] invalid format '{pair}', expected key=value")
                sys.exit(1)
            k, v = pair.split("=", 1)
            hosts[k] = v
            if _is_sensitive(k):
                console.print(f"  [green]✓[/green] {k} = ****")
            else:
                console.print(f"  [green]✓[/green] {k} = {v}")
        _yaml_write(hosts_path, hosts)


def cmd_cmd(args):
    """Execute a project-defined command."""
    import subprocess

    project_path = _resolve_project(args.get("project"))
    config = _load_config(project_path)
    commands = config.get("commands") or {}

    cmd_name = args.get("cmd_name")

    # No command name — list all available commands
    if not cmd_name:
        if not commands:
            console.print("[dim]No commands defined in project[/dim]")
            return
        console.print(f"[bold]Available commands:[/bold]\n")
        for name, cmd_def in commands.items():
            cmd_args = cmd_def.get("args", "")
            cmd_help = cmd_def.get("help", "")
            console.print(f"  [cyan]{name}[/cyan]  {cmd_args}  [dim]{cmd_help}[/dim]")
        console.print(f"\n  Usage: cutip cmd [project.yaml] <command> [args...]")
        return

    # Command name given but not defined
    if cmd_name not in commands:
        console.print(f"[red]Unknown command:[/red] {cmd_name}")
        if commands:
            console.print(f"Available: {', '.join(commands)}")
        sys.exit(1)

    cmd_def = commands[cmd_name]
    run_template = cmd_def.get("run", "")
    cmd_args_desc = cmd_def.get("args", "")
    cmd_help = cmd_def.get("help", "")
    user_args = args.get("cmd_args", [])

    # No args provided but command expects them — show help
    if cmd_args_desc and not user_args:
        console.print(f"  [bold]{cmd_name}[/bold] — {cmd_help}")
        console.print(f"  Usage: cutip cmd {cmd_name} {cmd_args_desc}")
        return

    import shlex

    def _quote(arg):
        """Quote an arg if it contains spaces."""
        return shlex.quote(arg) if " " in arg else arg

    # Substitute {0}, {1}, etc. with positional args (quoted if spaces)
    cmd_str = run_template
    for i, arg in enumerate(user_args):
        cmd_str = cmd_str.replace(f"{{{i}}}", _quote(arg))

    # Append remaining args that weren't substituted
    placeholder_count = run_template.count("{")
    if len(user_args) > placeholder_count:
        extra = " ".join(_quote(a) for a in user_args[placeholder_count:])
        cmd_str = f"{cmd_str} {extra}"
    elif placeholder_count == 0 and user_args:
        # No placeholders — append all args
        cmd_str = f"{cmd_str} {' '.join(_quote(a) for a in user_args)}"

    # Run from project directory
    cwd = str(project_path.parent)
    console.print(f"  [dim]{cmd_str}[/dim]")
    result = subprocess.run(cmd_str, shell=True, cwd=cwd)
    sys.exit(result.returncode)


COMMANDS = {
    "init": cmd_init,
    "validate": cmd_validate,
    "show": cmd_show,
    "plan": cmd_plan,
    "run": cmd_run,
    "cmd": cmd_cmd,
    "tree": cmd_tree,
    "vars": cmd_vars,
    "secrets": cmd_secrets,
    "hosts": cmd_hosts,
    "verify": cmd_verify,
}


def main():
    """Entry point for `cutip` and `python -m cutip`."""
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        console.print(Panel(
            "[bold]cutip[/bold] — workflow automation framework\n\n"
            "[bold]Commands:[/bold]\n"
            "  init       Scaffold a new project\n"
            "  validate   Validate project config\n"
            "  show       Project summary or config section\n"
            "  plan       Show execution plan (dry run)\n"
            "  run        Execute workflow\n"
            "  cmd        Run a project-defined command\n"
            "  tree       Print config structure\n"
            "  vars       Manage project variables (list/get/set)\n"
            "  secrets    Manage project secrets (list/get/set)\n"
            "  hosts      Manage connection credentials (list/get/set)\n"
            "  verify     Check prerequisites\n\n"
            "[bold]Usage:[/bold]\n"
            "  cutip init myproject\n"
            "  cutip run myproject.yaml\n"
            "  cutip vars set gui.yaml greeting=hello\n"
            "  cutip hosts set gui.yaml vm.host=10.0.0.1\n"
            "  cutip cmd gui.yaml generate sheets/my.xlsx\n"
            "  cutip validate myproject.yaml",
            title=f"cutip v{VERSION}",
            box=box.ROUNDED,
        ))
        return

    if args[0] in ("--version", "version"):
        console.print(f"cutip v{VERSION}")
        return

    command = args[0]
    if command not in COMMANDS:
        console.print(f"[red]Unknown command:[/red] {command}")
        console.print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)

    # Parse remaining args
    parsed = {}
    remaining = args[1:]

    # Handle cmd command
    if command == "cmd":
        # Parse: cutip cmd [project.yaml] <command_name> [args...]
        cmd_name = None
        cmd_args = []
        for arg in remaining:
            if arg in ("-h", "--help"):
                parsed["cmd_name"] = None
                COMMANDS[command](parsed)
                return
            elif arg.endswith(".yaml") or (not cmd_name and Path(arg).exists() and arg.endswith(".yaml")):
                parsed["project"] = arg
            elif cmd_name is None and not arg.startswith("-"):
                cmd_name = arg
            else:
                cmd_args.append(arg)
        parsed["cmd_name"] = cmd_name
        parsed["cmd_args"] = cmd_args
        COMMANDS[command](parsed)
        return

    # Handle subcommand groups (vars, secrets, hosts)
    if command in ("vars", "secrets", "hosts"):
        if remaining and remaining[0] in ("list", "get", "set", "help"):
            parsed["subcmd"] = remaining[0]
            remaining = remaining[1:]
        # Parse project file and key=value pairs
        pairs = []
        for arg in remaining:
            if arg in ("-h", "--help"):
                parsed["subcmd"] = "help"
            elif "=" in arg:
                pairs.append(arg)
            elif arg.endswith(".yaml") or Path(arg).exists():
                parsed["project"] = arg
            elif parsed.get("subcmd") == "get" and "key" not in parsed:
                parsed["key"] = arg
            elif not parsed.get("project"):
                parsed["project"] = arg
        if pairs:
            parsed["pairs"] = pairs
        COMMANDS[command](parsed)
        return

    i = 0
    positional_consumed = False
    while i < len(remaining):
        arg = remaining[i]
        if arg in ("-h", "--help"):
            parsed["help"] = True
            i += 1
        elif arg == "--json":
            parsed["json"] = True
            i += 1
        elif arg == "--hosts" and i + 1 < len(remaining):
            parsed["hosts"] = remaining[i + 1]
            i += 2
        elif arg == "--path" and i + 1 < len(remaining):
            parsed["project"] = remaining[i + 1]
            i += 2
        elif not arg.startswith("-") and not positional_consumed:
            if command == "init":
                parsed["name"] = arg
            elif command == "show" and "project" in parsed:
                parsed["section"] = arg
            elif command == "show" and arg.endswith(".yaml"):
                parsed["project"] = arg
            elif command == "show":
                if Path(arg).exists() or arg.endswith(".yaml"):
                    parsed["project"] = arg
                else:
                    parsed["section"] = arg
            else:
                parsed["project"] = arg
            positional_consumed = True
            i += 1
        elif not arg.startswith("-") and positional_consumed:
            if command == "show" and "section" not in parsed:
                parsed["section"] = arg
            i += 1
        else:
            i += 1

    COMMANDS[command](parsed)
