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

VERSION = "1.0.2"
console = Console()


def cmd_validate(args):
    """Validate config.yaml."""
    path = args.get("path")
    try:
        result = _validate(path=path)
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
    table.add_row("Backend", result["backend"])
    table.add_row("Workflow", result["workflow"])
    table.add_row("Vars", str(result["vars_count"]))

    if result["empty_secrets"]:
        table.add_row("Secrets", f"{result['secrets_count']} ([yellow]{len(result['empty_secrets'])} empty[/yellow])")
    else:
        table.add_row("Secrets", f"{result['secrets_count']}, all set")

    if result["containers_count"]:
        table.add_row("Containers", str(result["containers_count"]))
    if result["networks_count"]:
        table.add_row("Networks", str(result["networks_count"]))

    if result["workflow_exists"]:
        table.add_row("Workflow", "[green]exists[/green]")
    else:
        table.add_row("Workflow", "[red]not found[/red]")

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
    path = args.get("path")
    try:
        config_json = _tree(path=path)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if args.get("json"):
        print(config_json)
        return

    config = json.loads(config_json)
    tree = Tree(f"[bold]{config['project']}[/bold]")
    tree.add(f"backend: [cyan]{config['backend']}[/cyan]")
    tree.add(f"workflow: [cyan]{config.get('workflow', 'workflow.py')}[/cyan]")

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

    extra = {k for k in config
             if k not in ("project", "backend", "workflow", "vars", "secrets",
                          "image", "container", "containers", "network", "networks")}
    if extra:
        tree.add(f"config: [dim]{', '.join(sorted(extra))}[/dim]")

    console.print(tree)


def cmd_show(args):
    """Show a config section."""
    if "--help" in sys.argv or "-h" in sys.argv:
        console.print("[bold]cutip show[/bold] <section>")
        console.print("Sections: vars, secrets, container, containers, network, or any config key")
        return

    section = args.get("section")
    if not section:
        console.print("[bold]cutip show[/bold] <section>")
        console.print("Sections: vars, secrets, container, containers, network, or any config key")
        sys.exit(1)

    try:
        result = _show(section, path=args.get("path"))
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(Panel(result.strip(), title=section, box=box.ROUNDED))


def cmd_run(args):
    """Run workflow.py."""
    import yaml

    if "--help" in sys.argv or "-h" in sys.argv:
        console.print("[bold]cutip run[/bold]")
        console.print("Reads config.yaml in current directory, runs workflow.py")
        return

    path = args.get("path")
    if path:
        config_path = Path(path)
    else:
        config_path = Path("config.yaml")
        if not config_path.exists():
            console.print("[red]Error:[/red] No config.yaml found in current directory")
            sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    # Prompt for empty vars/secrets
    has_prompts = False
    for key, val in config.get("vars", {}).items():
        if not val:
            if not has_prompts:
                console.print()
                has_prompts = True
            config["vars"][key] = console.input(f"  {key}: ")

    for key, val in config.get("secrets", {}).items():
        if not val:
            if not has_prompts:
                console.print()
                has_prompts = True
            config["secrets"][key] = console.input(f"  {key}: ")

    if has_prompts:
        console.print()

    # Find and run workflow
    config_dir = config_path.parent
    workflow_name = config.get("workflow", "workflow.py")
    workflow_path = config_dir / workflow_name

    if not workflow_path.exists():
        console.print(f"[red]Error:[/red] {workflow_name} not found")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("workflow", str(workflow_path))
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(config_dir))
    spec.loader.exec_module(module)

    if hasattr(module, "run_standalone"):
        module.run_standalone(config)
    elif hasattr(module, "main"):
        module.main(config)
    else:
        console.print("[red]Error:[/red] workflow.py has no run_standalone() or main() function")
        sys.exit(1)


def cmd_init(args):
    """Scaffold a new project."""
    if "--help" in sys.argv or "-h" in sys.argv:
        console.print("[bold]cutip init[/bold] <project-name>")
        return

    name = args.get("name")
    if not name:
        console.print("[bold]cutip init[/bold] <project-name>")
        sys.exit(1)

    target = Path(args.get("path") or name)

    if (target / "config.yaml").exists():
        console.print(f"[red]Error:[/red] config.yaml already exists in {target}")
        sys.exit(1)

    target.mkdir(parents=True, exist_ok=True)

    (target / "config.yaml").write_text(f"""project: {name}
backend: local

vars:
  # example_var: ""

secrets:
  # example_secret: ""
""")

    (target / "workflow.py").write_text(f'''"""{name} workflow."""

from loguru import logger


def main(config):
    logger.info("Starting {name} ...")
    logger.success("{name} complete.")


def run_standalone(config):
    main(config)
''')

    console.print(f"[green]✓[/green] Created [bold]{name}[/bold] at {target}")
    console.print(f"  config.yaml + workflow.py")
    console.print(f"  Next: cd {name} && cutip validate && cutip run")


def cmd_verify(args):
    """Check prerequisites and environment."""
    import subprocess
    import platform

    table = Table(title=f"cutip v{VERSION}", box=box.ROUNDED, show_header=False)
    table.add_column("Check", style="bold")
    table.add_column("Status")

    table.add_row("Platform", f"{platform.system()} {platform.machine()}")

    # Python — try both python and python3
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

    # Check cutip-blocks
    try:
        import cutip_blocks
        table.add_row("cutip-blocks", "[green]✓[/green] installed")
    except ImportError:
        table.add_row("cutip-blocks", "[red]✗ not installed[/red] (pip install cutip-blocks)")

    # Check Rust core
    try:
        from cutip._core import validate
        table.add_row("cutip core", "[green]✓[/green] loaded")
    except ImportError:
        table.add_row("cutip core", "[red]✗ not loaded[/red]")

    console.print(table)


COMMANDS = {
    "validate": cmd_validate,
    "tree": cmd_tree,
    "show": cmd_show,
    "run": cmd_run,
    "init": cmd_init,
    "verify": cmd_verify,
}


def main():
    """Entry point for `cutip` and `python -m cutip`."""
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        console.print(Panel(
            "[bold]cutip[/bold] — workflow automation framework\n\n"
            "[bold]Commands:[/bold]\n"
            "  validate   Validate config.yaml\n"
            "  tree       Print config structure\n"
            "  show       Show a config section\n"
            "  run        Run workflow.py\n"
            "  init       Scaffold a new project\n"
            "  verify     Check prerequisites\n\n"
            "[bold]Options:[/bold]\n"
            "  --path     Path to config.yaml\n"
            "  --json     Output as JSON (validate, tree)\n\n"
            "[bold]Usage:[/bold]\n"
            "  cutip validate\n"
            "  python -m cutip validate",
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

    # Parse remaining args into a dict
    parsed = {}
    i = 1
    while i < len(args):
        if args[i] in ("-h", "--help"):
            parsed["help"] = True
            i += 1
        elif args[i] == "--path" and i + 1 < len(args):
            parsed["path"] = args[i + 1]
            i += 2
        elif args[i] == "--json":
            parsed["json"] = True
            i += 1
        elif command == "show" and "section" not in parsed:
            parsed["section"] = args[i]
            i += 1
        elif command == "init" and "name" not in parsed:
            parsed["name"] = args[i]
            i += 1
        else:
            i += 1

    COMMANDS[command](parsed)
