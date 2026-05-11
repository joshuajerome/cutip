"""cutip CLI — Python wrapper over Rust core, formatted with rich."""

import os
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

VERSION = "2.19.0"
console = Console()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _resolve_project(project_arg: str | None) -> Path:
    """Resolve a project YAML file path.

    If project_arg is given, use it directly.
    If not, look for *.yaml files with a 'project:' field in cwd.
    """
    if project_arg:
        path = Path(project_arg)
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
        console.print("\nUsage: cutip run <project.yaml>")
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

    return project_path.parent / workflow_name


def _load_config(project_path: Path, var_overrides: dict | None = None) -> dict:
    """Load and return project config as a dict.

    Resolution stages (in order):
      1. Parse YAML.
      2. Read globals from ``~/.cutip/data.yaml`` (flat dotted keys).
      2b. Apply ``var_overrides`` (from ``--vars k=v`` or workflow-declared
          cli_args, see ``cutip/workflow/cli_args.py``) into ``vars`` so
          downstream substitution sees the runtime values.
      3. Resolve globals into ``vars`` / ``paths`` / ``secrets`` so they
         carry final values before the rest of the config is processed.
      4. Walk the entire config dict and substitute every ``{{ ns.key }}``
         placeholder using the resolved vars/paths/secrets/globals maps.
      5. Expand the ``paths:`` section against the project's directory
         and merge the resolved values into ``config['data']`` so
         workflow code reads them via ``ctx.data["<name>"]``.
    """
    import yaml

    from cutip import globals as _globals
    from cutip.paths import merge_paths_into_data
    from cutip.templating import resolve_substitution_maps, substitute_in_obj

    with open(project_path) as f:
        config = yaml.safe_load(f) or {}

    if var_overrides:
        if "vars" not in config or config["vars"] is None:
            config["vars"] = {}
        for k, v in var_overrides.items():
            config["vars"][k] = v

    globals_flat = _globals.flatten(_globals.read_globals())

    # Stage 3: resolve globals into vars/paths/secrets.
    vars_resolved, paths_resolved, secrets_resolved = resolve_substitution_maps(
        config, globals_flat
    )

    # Stage 4: substitute all four namespaces across the entire config.
    config = substitute_in_obj(
        config,
        vars=vars_resolved,
        paths=paths_resolved,
        secrets=secrets_resolved,
        globals=globals_flat,
    )

    # Stage 5: existing path-section merge into data.
    merge_paths_into_data(config, project_path)
    return config


def _resolve_host(config: dict) -> str:
    """Resolve host from config."""
    return config.get("host", "local")


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

    table = Table(
        title="Validation", box=box.ROUNDED, show_header=False, title_style="bold"
    )
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    table.add_row("Project", result["project"])
    host = result.get("host", "local")
    table.add_row("Host", host)
    if host == "container":
        rt = result.get("container_runtime", "auto")
        table.add_row("Runtime", rt)
    table.add_row("Workflow", result.get("workflow", "workflow.py"))
    table.add_row("Vars", str(result["vars_count"]))
    if result.get("paths_count", 0):
        table.add_row("Paths", str(result["paths_count"]))

    if result["empty_secrets"]:
        table.add_row(
            "Secrets",
            f"{result['secrets_count']} ([yellow]{len(result['empty_secrets'])} empty[/yellow])",
        )
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

    if args.get("all"):
        # --all: also do live SSH probes against the project's hosts
        console.print()
        from cutip import hosts as _hosts_mod

        hosts_path = _resolve_hosts_path(project_path)
        if not hosts_path.exists():
            console.print(
                f"[dim]No hosts file at {hosts_path.name} — skipping probes.[/dim]"
            )
            return
        try:
            to_probe = _hosts_mod.resolve(hosts_path)
        except _hosts_mod.HostsError as e:
            console.print(f"[red]Error resolving hosts:[/red] {e}")
            sys.exit(1)
        if not to_probe:
            return
        failed = _print_probe_results(to_probe, hosts_path.name)
        if failed:
            sys.exit(1)
    else:
        console.print(
            "\n[dim]Network checks skipped. Use 'cutip hosts validate' or 'cutip validate --all' for live probes.[/dim]"
        )


def cmd_projects(args):
    """Discover all cutip projects in the current directory tree.

    Walks cwd recursively, finds every *.yaml with `project:` + `host:`
    keys, prints a table with project name, host, and the first comment
    line as description. Useful for monorepos that host many cutip
    projects scattered across subdirectories.
    """
    import yaml as _yaml

    cwd = Path.cwd()
    skip_dirs = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".cutip",
        "target",
        "dist",
        "site",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
    }

    found = []
    for yaml_path in sorted(cwd.rglob("*.yaml")):
        if any(part in skip_dirs for part in yaml_path.relative_to(cwd).parts):
            continue
        try:
            text = yaml_path.read_text(encoding="utf-8")
            data = _yaml.safe_load(text)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        # Cutip artifact YAMLs (apiVersion: cutip/v1) use a different shape
        # and aren't project files — skip them.
        if isinstance(data.get("apiVersion"), str) and data["apiVersion"].startswith(
            "cutip/"
        ):
            continue
        if "project" not in data or "host" not in data:
            continue

        found.append(
            {
                "path": yaml_path.relative_to(cwd),
                "project": str(data["project"]),
                "host": str(data.get("host", "local")),
                "workflow": data.get("workflow"),
                "description": _first_yaml_comment(text),
            }
        )

    if args.get("json"):
        print(
            json.dumps(
                [
                    {
                        "path": str(p["path"]),
                        "project": p["project"],
                        "host": p["host"],
                        "workflow": p["workflow"],
                        "description": p["description"],
                    }
                    for p in found
                ],
                indent=2,
            )
        )
        return

    if not found:
        console.print(f"[dim]No cutip projects found under {cwd}[/dim]")
        return

    host_color = {"local": "green", "container": "yellow", "remote": "magenta"}

    table = Table(
        title=f"cutip projects under {cwd.name}/",
        box=box.ROUNDED,
        show_lines=False,
    )
    table.add_column("path", style="cyan", no_wrap=False)
    table.add_column("project", style="bold")
    table.add_column("host")
    table.add_column("description", style="dim", no_wrap=False)

    for p in found:
        color = host_color.get(p["host"], "white")
        table.add_row(
            str(p["path"]),
            p["project"],
            f"[{color}]{p['host']}[/{color}]",
            p["description"],
        )

    console.print(table)
    console.print(f"[dim]{len(found)} project{'s' if len(found) != 1 else ''}[/dim]")


def _first_yaml_comment(text: str) -> str:
    """Return the first prose-shaped comment line from a YAML file.

    Scans the first 30 lines (comments may appear before or after the
    leading `project:`/`host:` keys — snf-dev's convention is the
    latter). Skips blank lines and ruler-style separators (e.g.
    `# ─────────`). Used by `cutip projects` to surface a short
    description for each discovered project.
    """
    for i, line in enumerate(text.splitlines()):
        if i >= 30:
            break
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        body = stripped.lstrip("#").strip()
        if not body:
            continue
        # Ruler-style separator (e.g. "─────" or "====="), skip.
        if all(c in "─-=*#~_" for c in body):
            continue
        return body
    return ""


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

    host = config.get("host") or "local"
    tree.add(f"host: [cyan]{host}[/cyan]")
    if host == "container":
        rt = config.get("container.rt", "auto")
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

    excluded = {
        "project",
        "host",
        "container.rt",
        "workflow",
        "vars",
        "secrets",
        "connections",
        "image",
        "container",
        "containers",
        "network",
        "networks",
    }
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
    workflow_path = _resolve_workflow(project_path, config)

    # Print tree
    cmd_tree(args)
    console.print()

    # Steps
    console.print("[bold]Steps:[/bold]")
    console.print(f"  1. Read [cyan]{project_path}[/cyan]")
    console.print("  2. Validate config")

    empty_vars = [k for k, v in (config.get("vars") or {}).items() if not v]
    step = 3
    if empty_vars:
        console.print(
            f"  {step}. Prompt for empty vars: [yellow]{', '.join(empty_vars)}[/yellow]"
        )
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
        console.print("\n  [dim]No @action-decorated functions found[/dim]")
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

    console.print(
        f"  [dim]{action_num} action(s) across {len(groups)} stage(s)[/dim]\n"
    )


def cmd_run(args):
    """Run a workflow."""
    import yaml

    from cutip.workflow import cli_args as _cli_args

    project_path = _resolve_project(args.get("project"))

    # Read the raw yaml to extract any cli_args declarations + decide whether
    # this is a --help request that needs project-specific help.
    with open(project_path) as f:
        raw_config = yaml.safe_load(f) or {}
    try:
        specs = _cli_args.normalize_specs(raw_config.get("cli_args"))
    except _cli_args.CliArgsError as e:
        console.print(f"[red]Invalid cli_args block in {project_path.name}:[/red] {e}")
        sys.exit(1)

    if args.get("help"):
        console.print("[bold]cutip run[/bold] [project.yaml] [--bg] [--vars k=v ...]")
        console.print("  Reads project YAML, runs the workflow")
        console.print("  --bg   Detach: print cu-id and return; track via 'cutip ps'")
        console.print("  --vars Override vars block: --vars greeting=hi port=8080")
        if specs:
            console.print()
            console.print(_cli_args.help_text(specs))
        return

    # Resolve workflow-declared cli_args from any unconsumed tokens.
    cli_arg_user: dict = {}
    cli_arg_defaults: dict = {}
    if specs:
        try:
            cli_arg_user, cli_arg_defaults, leftover = _cli_args.parse_runtime(
                specs, args.get("_unconsumed", [])
            )
        except _cli_args.CliArgsError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)
        if leftover:
            console.print(
                f"[yellow]warning:[/yellow] unrecognized args ignored: {' '.join(leftover)}"
            )
    elif args.get("_unconsumed"):
        # Project doesn't declare cli_args but user passed unknown flags.
        # Don't silently swallow — surface them so the typo is visible.
        console.print(
            f"[yellow]warning:[/yellow] unrecognized args ignored "
            f"(project has no cli_args block): {' '.join(args['_unconsumed'])}"
        )

    # Precedence (lowest → highest):
    #   1. yaml `vars:` block          (handled by _load_config; we don't override)
    #   2. cli_args defaults           — only applied where yaml vars is absent
    #   3. --vars k=v                  — explicit user runtime override
    #   4. cli_args explicit values    — explicit user runtime override (typed)
    yaml_vars = raw_config.get("vars") or {}
    var_overrides: dict = {}
    for k, v in cli_arg_defaults.items():
        if k not in yaml_vars or yaml_vars[k] in (None, ""):
            var_overrides[k] = v
    var_overrides.update(args.get("cli_vars") or {})
    var_overrides.update(cli_arg_user)

    config = _load_config(project_path, var_overrides=var_overrides or None)

    # Background mode: spawn a detached daemon and exit
    if args.get("bg"):
        from cutip import processes as _proc
        from cutip.daemon import spawn_daemon

        workflow_path = _resolve_workflow(project_path, config)
        if not workflow_path.exists():
            console.print(f"[red]Error:[/red] {workflow_path.name} not found")
            sys.exit(1)
        cu_id = _proc.make_cu_id(config.get("project", project_path.stem))
        pid = spawn_daemon(
            cu_id,
            project_path,
            workflow_path,
            hosts_path=args.get("hosts"),
        )
        console.print(f"  [green]✓[/green] Spawned [cyan]{cu_id}[/cyan] (pid {pid})")
        console.print(f"  Tail logs:  cutip ps logs {cu_id}")
        console.print(f"  Stop:       cutip ps stop {cu_id}")
        return

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
    # Two values are produced:
    #   `hosts`           — the raw dict (flat or nested) for backward compat
    #                       with workflows that use ctx._hosts["host"] directly
    #   `resolved_hosts`  — the fully resolved nested dict (with global: true
    #                       references expanded) for ctx.host(name)
    hosts = None
    resolved_hosts = None
    hosts_path_arg = args.get("hosts")
    if hosts_path_arg:
        hosts_path = Path(hosts_path_arg)
    else:
        hosts_path = _resolve_hosts_path(project_path)

    if hosts_path.exists():
        from cutip import globals as _globals
        from cutip import hosts as _hosts_mod
        from cutip.templating import substitute_in_obj

        try:
            resolved_hosts = _hosts_mod.resolve(hosts_path)
        except _hosts_mod.HostsError as e:
            console.print(f"[red]Error resolving hosts:[/red] {e}")
            sys.exit(1)
        # For flat-format files, ctx._hosts retains the original flat shape
        # (existing workflows do ctx._hosts["host"]); for nested, ctx._hosts
        # carries the nested raw dict.
        with open(hosts_path) as f:
            hosts = yaml.safe_load(f) or {}

        # Substitute templates in resolved hosts using project's vars/paths/
        # secrets (already resolved against globals at config-load time).
        globals_flat = _globals.flatten(_globals.read_globals())
        resolved_hosts = substitute_in_obj(
            resolved_hosts,
            vars=config.get("vars") or {},
            paths=config.get("paths") or {},
            secrets=config.get("secrets") or {},
            globals=globals_flat,
        )
        hosts = substitute_in_obj(
            hosts,
            vars=config.get("vars") or {},
            paths=config.get("paths") or {},
            secrets=config.get("secrets") or {},
            globals=globals_flat,
        )

    # Pre-run validation
    workflow_path = _resolve_workflow(project_path, config)
    from cutip.workflow.validate import validate_project

    errors, warnings = validate_project(
        project_path, config, hosts=hosts, workflow_path=workflow_path
    )
    if errors:
        console.print("\n[red]Validation failed:[/red]")
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
    from cutip.workflow.decorators import _ACTION_ATTR

    has_actions = any(
        hasattr(getattr(module, attr, None), _ACTION_ATTR)
        for attr in dir(module)
        if callable(getattr(module, attr, None))
    )

    if has_actions:
        _run_with_engine(module, config, project_path, hosts, resolved_hosts)
    elif hasattr(module, "run_standalone"):
        module.run_standalone(config)
    elif hasattr(module, "main"):
        module.main(config)
    else:
        console.print(
            "[red]Error:[/red] workflow has no @action functions, run_standalone(), or main()"
        )
        sys.exit(1)


def _run_with_engine(module, config, project_path, hosts=None, resolved_hosts=None):
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
            _log(
                f"  [start] {event.action}"
                + (f" (attempt {event.attempt})" if event.attempt > 1 else "")
            )
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
    if resolved_hosts is not None:
        engine.ctx._resolved_hosts = resolved_hosts

    try:
        engine.run()
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
    console.print("  [bold]Next:[/bold]")
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
        import rsty  # noqa: F401  (importability probe)

        table.add_row("rsty", "[green]✓[/green] installed")
    except ImportError:
        table.add_row("rsty", "[red]✗ not installed[/red] (pip install rsty)")

    try:
        from cutip._core import validate  # noqa: F401  (importability probe)

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
        yaml.dump(
            data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )


def cmd_vars(args):
    """Manage project variables."""
    subcmd = args.get("subcmd")
    if not subcmd or subcmd == "help":
        console.print(
            "[bold]cutip vars[/bold] <list|get|set|rm> [project.yaml] [key=value ...]"
        )
        console.print("  list   Show all vars and their values")
        console.print("  get    Get a single var value")
        console.print("  set    Set one or more vars")
        console.print("  rm     Remove a var; prints the removed value")
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
            console.print(
                "[red]Usage:[/red] cutip vars set [project.yaml] key=value ..."
            )
            sys.exit(1)
        if "vars" not in config or config["vars"] is None:
            config["vars"] = {}
        for pair in pairs:
            if "=" not in pair:
                console.print(
                    f"[red]Error:[/red] invalid format '{pair}', expected key=value"
                )
                sys.exit(1)
            k, v = pair.split("=", 1)
            config["vars"][k] = v
            console.print(f"  [green]✓[/green] {k} = {v}")
        _yaml_write(project_path, config)

    elif subcmd == "rm":
        key = args.get("key")
        if not key:
            console.print("[red]Usage:[/red] cutip vars rm [project.yaml] <key>")
            sys.exit(1)
        vars_dict = config.get("vars") or {}
        if key not in vars_dict:
            console.print(f"[red]Error:[/red] var '{key}' not found")
            sys.exit(1)
        removed = vars_dict.pop(key)
        if not vars_dict:
            # Drop the empty section so re-loading doesn't carry an empty dict.
            config.pop("vars", None)
        _yaml_write(project_path, config)
        console.print(f"  [green]✓[/green] removed {key} = {removed!r}")


def cmd_secrets(args):
    """Manage project secrets."""
    subcmd = args.get("subcmd")
    if not subcmd or subcmd == "help":
        console.print(
            "[bold]cutip secrets[/bold] <list|get|set|rm> [project.yaml] [key=value ...]"
        )
        console.print("  list   Show all secret keys (values masked)")
        console.print("  get    Get a single secret value")
        console.print("  set    Set one or more secrets")
        console.print("  rm     Remove a secret; prints (masked) confirmation")
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
            console.print(
                "[red]Usage:[/red] cutip secrets set [project.yaml] key=value ..."
            )
            sys.exit(1)
        if "secrets" not in config or config["secrets"] is None:
            config["secrets"] = {}
        for pair in pairs:
            if "=" not in pair:
                console.print(
                    f"[red]Error:[/red] invalid format '{pair}', expected key=value"
                )
                sys.exit(1)
            k, v = pair.split("=", 1)
            config["secrets"][k] = v
            console.print(f"  [green]✓[/green] {k} = ****")
        _yaml_write(project_path, config)

    elif subcmd == "rm":
        key = args.get("key")
        if not key:
            console.print("[red]Usage:[/red] cutip secrets rm [project.yaml] <key>")
            sys.exit(1)
        secrets_dict = config.get("secrets") or {}
        if key not in secrets_dict:
            console.print(f"[red]Error:[/red] secret '{key}' not found")
            sys.exit(1)
        removed = secrets_dict.pop(key)
        if not secrets_dict:
            config.pop("secrets", None)
        _yaml_write(project_path, config)
        # Always mask removed secret values; user just needs to know it's gone.
        disp = "****" if removed else "(empty)"
        console.print(f"  [green]✓[/green] removed {key} = {disp}")


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


def _resolved_hosts_with_substitution(
    project_path: Path, hosts_path: Path
) -> dict[str, dict]:
    """Resolve hosts.yaml + apply template substitution against the project's
    vars / paths / secrets / globals context.

    Mirrors what ``cmd_run`` does when loading hosts before passing them to
    the workflow engine. Used by ``cutip hosts get / list / validate`` so
    those subcommands return resolved values, not raw ``{{ ... }}`` template
    strings.
    """
    from cutip import globals as _globals
    from cutip import hosts as _hosts_mod
    from cutip.templating import substitute_in_obj

    config = _load_config(project_path)
    resolved = _hosts_mod.resolve(hosts_path)
    globals_flat = _globals.flatten(_globals.read_globals())
    return substitute_in_obj(
        resolved,
        vars=config.get("vars") or {},
        paths=config.get("paths") or {},
        secrets=config.get("secrets") or {},
        globals=globals_flat,
    )


def _print_hosts_dict(data: dict, label: str | None = None) -> None:
    """Render a hosts dict (nested or flat) with sensitive values masked."""
    from cutip import hosts as _hosts

    if not data:
        console.print(f"[dim]No hosts defined{f' in {label}' if label else ''}.[/dim]")
        return

    if _hosts.is_nested(data):
        for name, entry in data.items():
            if isinstance(entry, dict) and entry.get("global") is True:
                console.print(f"  [cyan]{name}[/cyan]  [dim](→ global)[/dim]")
                continue
            console.print(f"  [cyan]{name}[/cyan]")
            if not isinstance(entry, dict):
                console.print(f"    [red]invalid entry: {entry!r}[/red]")
                continue
            for k, v in entry.items():
                if not v and v != 0:
                    console.print(f"    {k} = [yellow](empty)[/yellow]")
                elif _is_sensitive(k):
                    console.print(f"    {k} = [dim]****[/dim]")
                else:
                    console.print(f"    {k} = [dim]{v}[/dim]")
    else:
        # Flat (legacy) — render at top level
        for k, v in data.items():
            if not v and v != 0:
                console.print(f"  {k} = [yellow](empty)[/yellow]")
            elif _is_sensitive(k):
                console.print(f"  {k} = [dim]****[/dim]")
            else:
                console.print(f"  {k} = [dim]{v}[/dim]")


def cmd_hosts(args):
    """Manage project hosts file (per-project + optional global tier).

    Subcommands:
      cutip hosts list                  List local entries
      cutip hosts list -g               List global (~/.cutip/hosts.yaml) entries
      cutip hosts get <host>.<field>    Get a value (or `<field>` for flat files)
      cutip hosts get -g <host>.<field> Get from global
      cutip hosts set <host>.<field>=<value> [...]
      cutip hosts set -g <host>.<field>=<value> [...]
      cutip hosts rm <host>[.<field>]   Remove an entry or one of its fields
      cutip hosts rm -g <host>[.<field>] Remove from global hosts file
      cutip hosts path                  Print local hosts file path
      cutip hosts path -g               Print global hosts file path
      cutip hosts set-path -g <path>    Change global hosts file location
      cutip hosts init -g               Create the global hosts file
      cutip hosts migrate               Convert flat → nested in this project
      cutip hosts validate              Probe each host via SSH (project's hosts)
      cutip hosts validate -g           Probe every entry in the global file
      cutip hosts promote [<name>...]   Move local entries to ~/.cutip/hosts.yaml
                                        and replace each with `{global: true}`.
                                        Without name, promotes ALL entries.
                                        Use -f / --force to overwrite conflicting
                                        global values; otherwise conflicts abort.
    """
    from cutip import hosts as _hosts

    subcmd = args.get("subcmd")
    use_global = bool(args.get("global"))

    if not subcmd or subcmd == "help":
        console.print(cmd_hosts.__doc__ or "cutip hosts")
        return

    # Global-only subcommands
    if subcmd == "init":
        if not use_global:
            console.print(
                "[red]Error:[/red] 'cutip hosts init' is global-only. Use: cutip hosts init -g"
            )
            console.print(
                "  (local hosts.yaml is auto-created on first 'cutip hosts set <host>.<field>=<value>')"
            )
            sys.exit(1)
        gp = _hosts.global_hosts_path()
        if gp.exists():
            console.print(f"[dim]Global hosts file already exists: {gp}[/dim]")
            return
        _hosts.write_hosts_file(gp, {})
        console.print(f"  [green]✓[/green] Created [cyan]{gp}[/cyan]")
        console.print("  Add entries with: cutip hosts set -g <host>.<field>=<value>")
        return

    if subcmd == "set-path":
        if not use_global:
            console.print(
                "[red]Error:[/red] 'cutip hosts set-path' is global-only. Use: cutip hosts set-path -g <path>"
            )
            sys.exit(1)
        new_path = args.get("key")  # parser puts the bare-positional arg in 'key'
        if not new_path:
            console.print("[red]Usage:[/red] cutip hosts set-path -g <path>")
            sys.exit(1)
        _hosts.set_global_hosts_path(new_path)
        console.print(f"  [green]✓[/green] Global hosts path → [cyan]{new_path}[/cyan]")
        console.print(f"  (stored in {_hosts.config_path()})")
        return

    if subcmd == "path":
        if use_global:
            console.print(_hosts.global_hosts_path())
        else:
            project_path = _resolve_project(args.get("project"))
            console.print(_resolve_hosts_path(project_path))
        return

    # Resolve target file (global or project-local) for list/get/set/migrate
    if use_global:
        target_path = _hosts.global_hosts_path()
        target_label = str(target_path)
    else:
        project_path = _resolve_project(args.get("project"))
        target_path = _resolve_hosts_path(project_path)
        target_label = target_path.name

    if subcmd == "list":
        if not target_path.exists():
            console.print(f"[dim]{target_label} does not exist.[/dim]")
            if use_global:
                console.print("  Create with: cutip hosts init -g")
            return
        if use_global:
            data = _hosts.read_hosts_file(target_path)
        else:
            # Apply project-context template substitution so list shows
            # resolved values instead of raw {{ globals.X }} strings.
            try:
                data = _resolved_hosts_with_substitution(project_path, target_path)
            except _hosts.HostsError as e:
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)
        _print_hosts_dict(data, label=target_label)
        return

    if subcmd == "get":
        key = args.get("key")
        if not key:
            console.print(
                "[red]Usage:[/red] cutip hosts get [-g] <host>.<field>  (or <field> for flat files)"
            )
            sys.exit(1)
        data = _hosts.read_hosts_file(target_path)
        if "." in key:
            host_name, field = key.split(".", 1)
            try:
                if use_global:
                    resolved = data
                else:
                    resolved = _resolved_hosts_with_substitution(
                        project_path, target_path
                    )
            except _hosts.HostsError as e:
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)
            if host_name not in resolved or not isinstance(
                resolved.get(host_name), dict
            ):
                console.print(
                    f"[red]Error:[/red] host '{host_name}' not found in {target_label}"
                )
                sys.exit(1)
            value = resolved[host_name].get(field)
            console.print(value if value is not None else "")
            return
        # No dot — treat as flat-file lookup
        if not _hosts.is_nested(data) and key in data:
            console.print(data[key] if data[key] is not None else "")
            return
        console.print(
            f"[red]Error:[/red] '{key}' not found in {target_label}. "
            f"For nested files use '<host>.<field>' syntax."
        )
        sys.exit(1)

    if subcmd == "set":
        pairs = args.get("pairs", [])
        if not pairs:
            console.print(
                "[red]Usage:[/red] cutip hosts set [-g] <host>.<field>=<value> ..."
            )
            sys.exit(1)
        existing = _hosts.read_hosts_file(target_path)
        for pair in pairs:
            if "=" not in pair:
                console.print(
                    f"[red]Error:[/red] invalid format '{pair}', expected <host>.<field>=<value>"
                )
                sys.exit(1)
            k, v = pair.split("=", 1)
            if "." in k:
                host_name, field = k.split(".", 1)
                try:
                    _hosts.set_field(target_path, host_name, field, v)
                except _hosts.HostsError as e:
                    console.print(f"[red]Error:[/red] {e}")
                    sys.exit(1)
                disp = "****" if _is_sensitive(field) else v
                console.print(f"  [green]✓[/green] {host_name}.{field} = {disp}")
            else:
                # Flat-file backward compat: only allowed if file is flat or empty
                if existing and _hosts.is_nested(existing):
                    console.print(
                        f"[red]Error:[/red] {target_label} is in nested format. "
                        f"Use '<host>.{k}=<value>' instead of '{k}=<value>'."
                    )
                    sys.exit(1)
                existing[k] = v
                _hosts.write_hosts_file(target_path, existing)
                disp = "****" if _is_sensitive(k) else v
                console.print(f"  [green]✓[/green] {k} = {disp}")
        return

    if subcmd == "rm":
        key = args.get("key")
        if not key:
            console.print("[red]Usage:[/red] cutip hosts rm [-g] <host>[.<field>]")
            sys.exit(1)
        if not target_path.exists():
            console.print(f"[red]Error:[/red] {target_label} not found")
            sys.exit(1)
        existing = _hosts.read_hosts_file(target_path)
        if "." in key:
            # Field-level remove: <host>.<field>
            host_name, field = key.split(".", 1)
            entry = existing.get(host_name)
            if not isinstance(entry, dict):
                console.print(
                    f"[red]Error:[/red] host '{host_name}' not found in {target_label}"
                )
                sys.exit(1)
            if field not in entry:
                console.print(
                    f"[red]Error:[/red] field '{field}' not on host '{host_name}'"
                )
                sys.exit(1)
            removed = entry.pop(field)
            _hosts.write_hosts_file(target_path, existing)
            disp = "****" if _is_sensitive(field) else repr(removed)
            console.print(f"  [green]✓[/green] removed {host_name}.{field} = {disp}")
        else:
            # Entry-level remove
            if key not in existing:
                console.print(f"[red]Error:[/red] '{key}' not found in {target_label}")
                sys.exit(1)
            removed = existing.pop(key)
            _hosts.write_hosts_file(target_path, existing)
            if isinstance(removed, dict):
                disp = f"<entry: {len(removed)} field(s)>"
            else:
                disp = "****" if _is_sensitive(key) else repr(removed)
            console.print(f"  [green]✓[/green] removed {key} = {disp}")
        return

    if subcmd == "migrate":
        if use_global:
            console.print("[red]Error:[/red] migrate is project-local only (no -g).")
            sys.exit(1)
        if not target_path.exists():
            console.print(
                f"[dim]{target_label} does not exist — nothing to migrate.[/dim]"
            )
            return
        existing = _hosts.read_hosts_file(target_path)
        if _hosts.is_nested(existing):
            console.print(f"[dim]{target_label} is already in nested format.[/dim]")
            return
        # Pick a default name. If the project YAML has a hint, use it; else 'default'.
        default_name = "default"
        try:
            project_path = _resolve_project(args.get("project"))
            cfg = _load_config(project_path)
            default_name = cfg.get("project", "default")
        except SystemExit:
            pass
        migrated = _hosts.migrate(target_path, default_name=default_name)
        if migrated:
            console.print(
                f"  [green]✓[/green] Migrated {target_label}: flat → nested under [cyan]{default_name}[/cyan]"
            )
            console.print(
                f"  Workflows should now use ctx.host_for('{default_name}') or update field references."
            )
        return

    if subcmd == "promote":
        if use_global:
            console.print(
                "[red]Error:[/red] promote moves entries FROM local TO global; -g doesn't apply."
            )
            sys.exit(1)
        project_path = _resolve_project(args.get("project"))
        local_path = _resolve_hosts_path(project_path)
        if not local_path.exists():
            console.print(f"[red]Error:[/red] {local_path.name} not found")
            sys.exit(1)
        names = args.get("names")  # None = promote all
        force = bool(args.get("force"))
        try:
            result = _hosts.promote_to_global(local_path, names=names, force=force)
        except _hosts.HostsError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

        gp = _hosts.global_hosts_path()
        for name in result.promoted:
            console.print(f"  [green]✓[/green] Promoted [cyan]{name}[/cyan] → {gp}")
        for name in result.skipped_already_global:
            console.print(f"  [dim]○ {name} is already 'global: true' (skipped)[/dim]")
        for name in result.skipped_missing:
            console.print(
                f"  [yellow]⚠[/yellow] '{name}' not found in {local_path.name}"
            )
        if result.conflicts:
            console.print(
                f"\n[red]✗[/red] {len(result.conflicts)} conflict(s) — "
                f"global already has different values for:"
            )
            for name in result.conflicts:
                console.print(f"    [red]•[/red] {name}")
            console.print(
                "\n  Use [cyan]-f[/cyan] (or [cyan]--force[/cyan]) to overwrite the global entries."
            )
            sys.exit(1)
        if result.promoted:
            console.print(
                f"\n  Local {local_path.name} now references global creds. "
                f"Run [cyan]cutip hosts list[/cyan] to confirm."
            )
        elif not (result.skipped_already_global or result.skipped_missing):
            console.print("[dim]Nothing to promote.[/dim]")
        return

    if subcmd == "validate":
        # Build the dict to probe.
        # -g: probe everything in the global file.
        # otherwise: probe everything referenced by the project's hosts file
        #            (with `global: true` references resolved against global).
        if use_global:
            if not target_path.exists():
                console.print(f"[red]Error:[/red] {target_path} does not exist")
                console.print("  Create with: cutip hosts init -g")
                sys.exit(1)
            data = _hosts.read_hosts_file(target_path)
            if not _hosts.is_nested(data):
                console.print(
                    f"[red]Error:[/red] global hosts file at {target_path} is not in nested format"
                )
                sys.exit(1)
            to_probe = data
            label = str(target_path)
        else:
            if not target_path.exists():
                console.print(f"[red]Error:[/red] {target_label} not found")
                sys.exit(1)
            try:
                # Substitute templates so the probe gets real credentials,
                # not raw {{ globals.X }} strings.
                to_probe = _resolved_hosts_with_substitution(project_path, target_path)
            except _hosts.HostsError as e:
                console.print(f"[red]Error resolving hosts:[/red] {e}")
                sys.exit(1)
            label = target_label

        if not to_probe:
            console.print(f"[dim]No hosts to probe in {label}.[/dim]")
            return

        failed = _print_probe_results(to_probe, label)
        if failed:
            sys.exit(1)
        return

    console.print(f"[red]Unknown hosts subcommand:[/red] {subcmd}")
    sys.exit(1)


def _print_probe_results(hosts_dict: dict, label: str) -> int:
    """Run live probes and render a result table.

    Returns the number of failed hosts (0 = all ok).
    """
    from cutip.hosts_validate import probe_hosts

    console.print(f"  Probing {len(hosts_dict)} host(s) from [cyan]{label}[/cyan]…")
    results = probe_hosts(hosts_dict)

    table = Table(box=box.ROUNDED, title_style="bold")
    table.add_column("host", style="cyan")
    table.add_column("address")
    table.add_column("time", justify="right")
    table.add_column("status")
    for r in results:
        time_cell = f"{r.elapsed:.2f}s" if r.elapsed > 0 else "—"
        if r.ok:
            status = "[green]✓ ok[/green]"
        else:
            status = f"[red]✗[/red] {r.error or 'failed'}"
        table.add_row(r.name, r.host or "—", time_cell, status)
    console.print(table)

    failed = sum(1 for r in results if not r.ok)
    if failed:
        console.print(f"  [red]✗[/red] {failed} of {len(results)} host(s) failed")
    else:
        console.print(f"  [green]✓[/green] All {len(results)} host(s) reachable")
    return failed


def cmd_data(args):
    """Manage the global data store at ~/.cutip/data.yaml.

    Subcommands:
      cutip data list                 List entries (flattened, dotted paths)
      cutip data get <dotted.path>    Print one value
      cutip data set <dotted.path>=<value> [...]
                                      Set one or more values
      cutip data rm <dotted.path>     Remove an entry; cleans up emptied parents
      cutip data path                 Print the data file path
      cutip data set-path -g <path>   Change the global data file location
      cutip data init                 Create an empty data file
    """
    from cutip import globals as _globals

    subcmd = args.get("subcmd")
    use_global = bool(args.get("global"))

    if not subcmd or subcmd == "help":
        console.print(cmd_data.__doc__ or "cutip data")
        return

    if subcmd == "set-path":
        # The data store is inherently global, but the -g flag is required
        # for parity with `cutip hosts set-path` so the two surfaces stay
        # symmetrical.
        if not use_global:
            console.print(
                "[red]Error:[/red] 'cutip data set-path' is global-only. "
                "Use: cutip data set-path -g <path>"
            )
            sys.exit(1)
        new_path = args.get("key")  # parser puts the bare-positional arg in 'key'
        if not new_path:
            console.print("[red]Usage:[/red] cutip data set-path -g <path>")
            sys.exit(1)
        _globals.set_globals_path(new_path)
        from cutip.hosts import config_path

        console.print(f"  [green]✓[/green] Global data path → [cyan]{new_path}[/cyan]")
        console.print(f"  (stored in {config_path()})")
        return

    gp = _globals.globals_path()

    if subcmd == "path":
        console.print(gp)
        return

    if subcmd == "init":
        if gp.exists():
            console.print(f"[dim]Global data file already exists: {gp}[/dim]")
            return
        _globals.write_globals({}, gp)
        console.print(f"  [green]✓[/green] Created [cyan]{gp}[/cyan]")
        console.print("  Add entries with: cutip data set <dotted.path>=<value>")
        return

    if subcmd == "list":
        if not gp.exists():
            console.print(f"[dim]{gp} does not exist.[/dim]")
            console.print("  Create with: cutip data init")
            return
        data = _globals.read_globals(gp)
        if not data:
            console.print("[dim]No entries.[/dim]")
            return
        flat = _globals.flatten(data)
        for k in sorted(flat):
            # Mask if any segment of the dotted path looks sensitive —
            # 'passwords.v22' should hide its value even though 'v22' alone
            # doesn't match the sensitive list.
            disp = (
                "****" if any(_is_sensitive(seg) for seg in k.split(".")) else flat[k]
            )
            console.print(f"  [cyan]{k}[/cyan] = {disp}")
        return

    if subcmd == "get":
        key = args.get("key")
        if not key:
            console.print("[red]Usage:[/red] cutip data get <dotted.path>")
            sys.exit(1)
        data = _globals.read_globals(gp)
        value = _globals.lookup(data, key)
        if value is None:
            console.print(f"[red]Error:[/red] '{key}' not found in {gp.name}")
            sys.exit(1)
        if isinstance(value, dict):
            console.print(
                f"[red]Error:[/red] '{key}' is a mapping, not a scalar. "
                f"Drill deeper or use 'cutip data list'."
            )
            sys.exit(1)
        console.print(value)
        return

    if subcmd == "set":
        pairs = args.get("pairs", [])
        if not pairs:
            console.print(
                "[red]Usage:[/red] cutip data set <dotted.path>=<value> [...]"
            )
            sys.exit(1)
        data = _globals.read_globals(gp)
        for pair in pairs:
            if "=" not in pair:
                console.print(
                    f"[red]Error:[/red] invalid format '{pair}', "
                    f"expected <dotted.path>=<value>"
                )
                sys.exit(1)
            k, v = pair.split("=", 1)
            try:
                _globals.set_dotted(data, k, v)
            except _globals.GlobalsError as e:
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(1)
            disp = "****" if any(_is_sensitive(seg) for seg in k.split(".")) else v
            console.print(f"  [green]✓[/green] {k} = {disp}")
        _globals.write_globals(data, gp)
        return

    if subcmd == "rm":
        key = args.get("key")
        if not key:
            console.print("[red]Usage:[/red] cutip data rm <dotted.path>")
            sys.exit(1)
        if not gp.exists():
            console.print(f"[red]Error:[/red] {gp} does not exist")
            sys.exit(1)
        data = _globals.read_globals(gp)
        try:
            removed = _globals.remove_dotted(data, key)
        except _globals.GlobalsError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)
        _globals.write_globals(data, gp)
        # Mask sensitive leaves; show full path so the user can confirm.
        if any(_is_sensitive(seg) for seg in key.split(".")):
            disp = "****"
        elif isinstance(removed, dict):
            # Non-leaf removal — show child count rather than the dict body
            # (could be large, could contain sensitive descendants).
            disp = f"<subtree: {len(removed)} child key(s)>"
        else:
            disp = repr(removed)
        console.print(f"  [green]✓[/green] removed {key} = {disp}")
        return

    console.print(f"[red]Unknown data subcommand:[/red] {subcmd}")
    sys.exit(1)


def cmd_cmd(args):
    """Execute a project-defined command."""
    import subprocess

    project_path = _resolve_project(args.get("project"))
    config = _load_config(project_path)
    commands = config.get("commands") or {}

    cmd_name = args.get("cmd_name")

    # Normalize: a command can be either a string shorthand or a dict.
    #   commands:
    #     git_branch: "git branch"                    # string shorthand
    #     deploy:                                      # dict form
    #       run: "ansible-playbook deploy.yml"
    #       args: "<env>"
    #       help: "Deploy to <env>"
    def _normalize(cmd_def):
        if isinstance(cmd_def, str):
            return {"run": cmd_def, "args": "", "help": ""}
        return cmd_def

    # No command name — list all available commands
    if not cmd_name:
        if not commands:
            console.print("[dim]No commands defined in project[/dim]")
            return
        console.print("[bold]Available commands:[/bold]\n")
        for name, cmd_def in commands.items():
            cd = _normalize(cmd_def)
            cmd_args = cd.get("args", "")
            cmd_help = cd.get("help", "")
            console.print(f"  [cyan]{name}[/cyan]  {cmd_args}  [dim]{cmd_help}[/dim]")
        console.print("\n  Usage: cutip cmd [project.yaml] <command> [args...]")
        return

    # Command name given but not defined
    if cmd_name not in commands:
        console.print(f"[red]Unknown command:[/red] {cmd_name}")
        if commands:
            console.print(f"Available: {', '.join(commands)}")
        sys.exit(1)

    cmd_def = _normalize(commands[cmd_name])
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


# ── Background processes ────────────────────────────────────────────────────


def cmd_ps(args):
    """List/inspect/stop background cutip runs.

    Subcommands:
      cutip ps              List all background processes
      cutip ps logs <id>    Tail stdout of a process
      cutip ps stop <id>    SIGTERM the process + cascade-kill remote PIDs
      cutip ps inspect <id> Show full meta + remote PID list
      cutip ps clean        Prune completed processes older than N days
    """
    from cutip import processes as _proc

    subcmd = args.get("subcmd") or "list"
    target = args.get("key")  # cu-id (or prefix)

    if subcmd in ("help", "--help"):
        console.print("[bold]cutip ps[/bold] [list|logs|stop|inspect|clean] [<cu-id>]")
        console.print("  list      List background processes (default)")
        console.print("  logs      Tail stdout of a process")
        console.print("  stop      Request stop + cascade-kill remote PIDs")
        console.print("  inspect   Show meta + tracked remote PIDs")
        console.print("  clean     Delete completed processes older than 7 days")
        return

    if subcmd == "list":
        rows = list(_proc.list_processes())
        if not rows:
            console.print("[dim]No background processes.[/dim]")
            return
        table = Table(box=box.ROUNDED, title_style="bold")
        table.add_column("cu-id", style="cyan")
        table.add_column("project")
        table.add_column("status")
        table.add_column("started")
        table.add_column("pid")
        for m in rows:
            color = {
                "running": "green",
                "starting": "yellow",
                "succeeded": "green",
                "failed": "red",
                "stopped": "yellow",
            }.get(m.status, "dim")
            table.add_row(
                m.cu_id,
                m.project,
                f"[{color}]{m.status}[/{color}]",
                m.started_at,
                str(m.host_pid or ""),
            )
        console.print(table)
        return

    if subcmd == "clean":
        pruned = _proc.prune(older_than_days=7)
        if pruned:
            console.print(f"Pruned {len(pruned)} process(es):")
            for cu in pruned:
                console.print(f"  {cu}")
        else:
            console.print("[dim]Nothing to prune.[/dim]")
        return

    # All other subcommands need a target cu-id
    if not target:
        console.print(f"[red]Usage:[/red] cutip ps {subcmd} <cu-id>")
        sys.exit(1)

    try:
        cu_id = _proc.resolve_cu_id(target)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if subcmd == "logs":
        stdout_p = _proc.stdout_path(cu_id)
        if not stdout_p.exists():
            console.print(f"[dim]No log yet for {cu_id}.[/dim]")
            return
        # Tail-follow the stdout file. Stops on Ctrl-C.
        # Binary mode + chunked reads — Python text-mode readline() on
        # Windows can stop detecting new content after EOF without an
        # explicit seek invalidation, so the live tail visibly pauses
        # until the writing daemon finishes. Reading bytes through
        # sys.stdout.buffer sidesteps both layers (no text decode, no
        # line-buffer cache).
        import time

        try:
            with open(stdout_p, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if chunk:
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                        continue
                    # No new bytes — check if the producer is done
                    meta = _proc.read_meta(cu_id)
                    if _proc.is_terminal(meta.status):
                        # One last drain in case bytes landed between the
                        # read and the meta check
                        tail = f.read()
                        if tail:
                            sys.stdout.buffer.write(tail)
                            sys.stdout.buffer.flush()
                        return
                    # Force the OS to re-check the file for new content.
                    # On Windows specifically, just re-calling read() at
                    # the same position can return stale EOF — seeking to
                    # the current offset invalidates any cached state.
                    f.seek(f.tell())
                    time.sleep(0.3)
        except KeyboardInterrupt:
            return

    if subcmd == "stop":
        meta = _proc.read_meta(cu_id)
        if _proc.is_terminal(meta.status):
            console.print(f"[dim]{cu_id} is already {meta.status}.[/dim]")
            return
        _proc.request_stop(cu_id)
        console.print(f"  Stop requested for [cyan]{cu_id}[/cyan]")

        # Cascade-kill: SIGTERM remote PIDs immediately so the daemon's
        # shell session unwinds without having to wait for it to poll.
        remote = _proc.list_remote_pids(cu_id)
        if remote:
            console.print(f"  Killing {len(remote)} remote process(es)...")
            from rsty import ssh
            from collections import defaultdict

            by_host: dict[tuple[str, str], list[int]] = defaultdict(list)
            for r in remote:
                by_host[(r.host, r.username)].append(r.pid)
            for (host, user), pids in by_host.items():
                # We need the host's password — read from the cu-id's hosts cache
                # if we cached it, otherwise fall back to user's hosts.yaml. For
                # now keep it simple: we ONLY know the cu-id's project root.
                # Best-effort: skip if we can't auth. The local SIGTERM (next)
                # will at minimum kill the daemon and close SSH, which usually
                # unwinds remote processes.
                try:
                    project_path = Path(meta.project_path)
                    hp = project_path.parent / "hosts.yaml"
                    if hp.exists():
                        import yaml as _yaml

                        with open(hp) as fh:
                            h = _yaml.safe_load(fh) or {}
                        password = h.get("password", "")
                        if not password:
                            console.print(
                                f"  [yellow]⚠[/yellow] No password for {host} — "
                                f"local SIGTERM only"
                            )
                            continue
                        sesh = ssh.open(host=host, username=user, password=password)
                        for pid in pids:
                            try:
                                ssh.signal(sesh, pid, "TERM")
                                console.print(f"    SIGTERM → {host}:{pid}")
                            except Exception as e:
                                console.print(
                                    f"    [yellow]⚠[/yellow] {host}:{pid} — {e}"
                                )
                        sesh.close()
                except Exception as e:
                    console.print(f"  [yellow]⚠[/yellow] {host}: {e}")

        # Local stop the daemon
        # Windows: CTRL_BREAK_EVENT can't reach a DETACHED_PROCESS daemon
        # (no shared console), and the daemon's SIGTERM handler is Unix-only
        # anyway. Use taskkill /T to cascade-kill the whole process tree;
        # the safety net below will mark meta as stopped.
        if meta.host_pid:
            try:
                if sys.platform == "win32":
                    import subprocess

                    result = subprocess.run(
                        ["taskkill", "/PID", str(meta.host_pid), "/T", "/F"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        console.print(f"  Killed daemon tree (pid {meta.host_pid})")
                    elif result.returncode == 128:
                        # 128 = process not found (already exited)
                        pass
                    else:
                        console.print(
                            f"  [yellow]⚠[/yellow] taskkill rc={result.returncode}: "
                            f"{(result.stderr or result.stdout).strip()}"
                        )
                else:
                    import signal

                    os.kill(meta.host_pid, signal.SIGTERM)
                    console.print(f"  SIGTERM → daemon pid {meta.host_pid}")
            except ProcessLookupError:
                pass
            except PermissionError:
                console.print(
                    f"  [yellow]⚠[/yellow] No permission to signal {meta.host_pid}"
                )

        # Safety net: if the daemon doesn't update its own meta within 2s
        # (e.g., it died before its SIGTERM handler ran), force the meta
        # to "stopped" so `cutip ps` doesn't show a phantom "running" entry.
        import time as _time

        for _ in range(20):
            _time.sleep(0.1)
            if _proc.is_terminal(_proc.read_meta(cu_id).status):
                return
        _proc.update_meta(
            cu_id,
            status="stopped",
            finished_at=_proc.now_iso(),
            error="forced stop (daemon did not update meta)",
        )
        _proc.clear_stop(cu_id)
        return

    if subcmd == "inspect":
        meta = _proc.read_meta(cu_id)
        from dataclasses import asdict

        console.print(
            Panel(
                json.dumps(asdict(meta), indent=2),
                title=f"cutip ps inspect {cu_id}",
                box=box.ROUNDED,
            )
        )
        remote = _proc.list_remote_pids(cu_id)
        if remote:
            t = Table(title="Tracked remote processes", box=box.ROUNDED)
            t.add_column("host", style="cyan")
            t.add_column("user")
            t.add_column("pid")
            t.add_column("label")
            t.add_column("started")
            for r in remote:
                t.add_row(r.host, r.username, str(r.pid), r.label, r.started_at)
            console.print(t)
        return

    console.print(f"[red]Unknown ps subcommand:[/red] {subcmd}")
    sys.exit(1)


COMMANDS = {
    "init": cmd_init,
    "validate": cmd_validate,
    "show": cmd_show,
    "plan": cmd_plan,
    "run": cmd_run,
    "cmd": cmd_cmd,
    "tree": cmd_tree,
    "projects": cmd_projects,
    "vars": cmd_vars,
    "secrets": cmd_secrets,
    "hosts": cmd_hosts,
    "data": cmd_data,
    "verify": cmd_verify,
    "ps": cmd_ps,
}


def main():
    """Entry point for `cutip` and `python -m cutip`."""
    args = sys.argv[1:]

    # Internal: daemon stage of `cutip run --bg`. The parent process spawns
    # us with `cutip --bg-daemon <cu-id> [--hosts <path>]` and we run the
    # workflow with stdout/stderr already redirected by the parent.
    if args and args[0] == "--bg-daemon":
        if len(args) < 2:
            print("usage: cutip --bg-daemon <cu-id> [--hosts <path>]", file=sys.stderr)
            sys.exit(2)
        cu_id = args[1]
        hosts_path = None
        if len(args) >= 4 and args[2] == "--hosts":
            hosts_path = args[3]
        from cutip.daemon import run_daemon

        sys.exit(run_daemon(cu_id, hosts_path))

    if not args or args[0] in ("-h", "--help", "help"):
        console.print(
            Panel(
                "[bold]cutip[/bold] — workflow automation framework\n\n"
                "[bold]Commands:[/bold]\n"
                "  init       Scaffold a new project\n"
                "  validate   Validate project config\n"
                "  show       Project summary or config section\n"
                "  plan       Show execution plan (dry run)\n"
                "  run        Execute workflow\n"
                "  cmd        Run a project-defined command\n"
                "  tree       Print config structure\n"
                "  projects   Discover all cutip projects under cwd\n"
                "  vars       Manage project variables (list/get/set)\n"
                "  secrets    Manage project secrets (list/get/set)\n"
                "  hosts      Manage connection credentials (list/get/set)\n"
                "  data       Manage global data store (~/.cutip/data.yaml)\n"
                "  verify     Check prerequisites\n"
                "  ps         List/inspect/stop background runs (cutip run --bg)\n\n"
                "[bold]Usage:[/bold]\n"
                "  cutip init myproject\n"
                "  cutip run myproject.yaml\n"
                "  cutip vars set gui.yaml greeting=hello\n"
                "  cutip hosts set gui.yaml vm.host=10.0.0.1\n"
                "  cutip cmd gui.yaml generate sheets/my.xlsx\n"
                "  cutip validate myproject.yaml",
                title=f"cutip v{VERSION}",
                box=box.ROUNDED,
            )
        )
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
            elif arg.endswith(".yaml") or (
                not cmd_name and Path(arg).exists() and arg.endswith(".yaml")
            ):
                parsed["project"] = arg
            elif cmd_name is None and not arg.startswith("-"):
                cmd_name = arg
            else:
                cmd_args.append(arg)
        parsed["cmd_name"] = cmd_name
        parsed["cmd_args"] = cmd_args
        COMMANDS[command](parsed)
        return

    # Handle subcommand groups (vars, secrets)
    if command in ("vars", "secrets"):
        if remaining and remaining[0] in ("list", "get", "set", "rm", "help"):
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
            elif parsed.get("subcmd") in ("get", "rm") and "key" not in parsed:
                parsed["key"] = arg
            elif not parsed.get("project"):
                parsed["project"] = arg
        if pairs:
            parsed["pairs"] = pairs
        COMMANDS[command](parsed)
        return

    # `hosts` has its own richer subcommand surface (list/get/set/path/
    # set-path/init/migrate, plus the -g flag for global tier).
    if command == "hosts":
        valid_subs = {
            "list",
            "get",
            "set",
            "rm",
            "path",
            "set-path",
            "init",
            "migrate",
            "validate",
            "promote",
            "help",
        }
        if remaining and remaining[0] in valid_subs:
            parsed["subcmd"] = remaining[0]
            remaining = remaining[1:]
        pairs = []
        names: list[str] = []
        for arg in remaining:
            if arg in ("-h", "--help"):
                parsed["subcmd"] = "help"
            elif arg in ("-g", "--global"):
                parsed["global"] = True
            elif arg in ("-f", "--force"):
                parsed["force"] = True
            elif "=" in arg:
                pairs.append(arg)
            elif arg.endswith(".yaml") or Path(arg).exists():
                parsed["project"] = arg
            elif (
                parsed.get("subcmd") in ("get", "set-path", "rm")
                and "key" not in parsed
            ):
                parsed["key"] = arg
            elif parsed.get("subcmd") == "promote":
                names.append(arg)
            elif not parsed.get("project"):
                parsed["project"] = arg
        if pairs:
            parsed["pairs"] = pairs
        if names:
            parsed["names"] = names
        COMMANDS[command](parsed)
        return

    if command == "data":
        valid_subs = {"list", "get", "set", "rm", "path", "set-path", "init", "help"}
        if remaining and remaining[0] in valid_subs:
            parsed["subcmd"] = remaining[0]
            remaining = remaining[1:]
        pairs = []
        for arg in remaining:
            if arg in ("-h", "--help"):
                parsed["subcmd"] = "help"
            elif arg in ("-g", "--global"):
                parsed["global"] = True
            elif "=" in arg:
                pairs.append(arg)
            elif (
                parsed.get("subcmd") in ("get", "rm", "set-path")
                and "key" not in parsed
            ):
                parsed["key"] = arg
        if pairs:
            parsed["pairs"] = pairs
        COMMANDS[command](parsed)
        return

    if command == "ps":
        # cutip ps [list|logs|stop|inspect|clean] [<cu-id>]
        if remaining and remaining[0] in (
            "list",
            "logs",
            "stop",
            "inspect",
            "clean",
            "help",
        ):
            parsed["subcmd"] = remaining[0]
            remaining = remaining[1:]
        if remaining:
            parsed["key"] = remaining[0]
        COMMANDS[command](parsed)
        return

    i = 0
    positional_consumed = False
    cli_vars: dict = {}
    unconsumed: list = []  # for run command — collected and matched against workflow-declared cli_args
    while i < len(remaining):
        arg = remaining[i]
        if arg in ("-h", "--help"):
            parsed["help"] = True
            i += 1
        elif arg == "--json":
            parsed["json"] = True
            i += 1
        elif arg == "--bg":
            parsed["bg"] = True
            i += 1
        elif arg == "--all":
            parsed["all"] = True
            i += 1
        elif arg == "--hosts" and i + 1 < len(remaining):
            parsed["hosts"] = remaining[i + 1]
            i += 2
        elif arg == "--path" and i + 1 < len(remaining):
            parsed["project"] = remaining[i + 1]
            i += 2
        elif arg == "--vars":
            # Greedy consume k=v tokens until next flag or end-of-args.
            # Lets the user write: cutip run x.yaml --vars a=1 b=2 --bg
            i += 1
            while i < len(remaining):
                tok = remaining[i]
                if tok.startswith("-") or "=" not in tok:
                    break
                k, v = tok.split("=", 1)
                cli_vars[k] = v
                i += 1
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
            else:
                # run command may have declared cli_args that take values
                # at unflagged-positional positions if the parser routed
                # there; defer to cmd_run.
                unconsumed.append(arg)
            i += 1
        else:
            # Unknown flag — could be a workflow-declared cli_arg for `run`.
            # Tentatively grab it + a value if the next token looks like one.
            unconsumed.append(arg)
            i += 1
            if (
                command == "run"
                and i < len(remaining)
                and not remaining[i].startswith("-")
                and "=" not in remaining[i]
            ):
                unconsumed.append(remaining[i])
                i += 1

    if cli_vars:
        parsed["cli_vars"] = cli_vars
    if unconsumed:
        parsed["_unconsumed"] = unconsumed

    COMMANDS[command](parsed)
