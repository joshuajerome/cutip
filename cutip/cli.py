"""cutip CLI — thin Python wrapper over Rust core."""

import sys
import json
import importlib.util
from pathlib import Path

from cutip._core import validate as _validate, tree as _tree, show as _show

VERSION = "1.0.1"


def cmd_validate(args):
    """Validate config.yaml."""
    path = args.get("path")
    result = _validate(path=path)

    if args.get("json"):
        print(json.dumps(result, indent=2))
        return

    print(f"Project: {result['project']}")
    print(f"Backend: {result['backend']}")
    print(f"Workflow: {result['workflow']}")
    print(f"Vars: {result['vars_count']}")

    if result["empty_secrets"]:
        print(f"Secrets: {result['secrets_count']} ({len(result['empty_secrets'])} empty: {', '.join(result['empty_secrets'])})")
    else:
        print(f"Secrets: {result['secrets_count']}, all set")

    if result["containers_count"]:
        print(f"Containers: {result['containers_count']}")
    if result["networks_count"]:
        print(f"Networks: {result['networks_count']}")

    if result["workflow_exists"]:
        print(f"Workflow: {result['workflow']} exists")
    else:
        print(f"Workflow: {result['workflow']} not found")

    if result["warnings"]:
        print()
        for w in result["warnings"]:
            print(f"  ⚠ {w}")
        print("\n⚠ Validation passed with warnings")
    else:
        print("\n✓ Validation passed")


def cmd_tree(args):
    """Print config as tree."""
    path = args.get("path")
    config_json = _tree(path=path)

    if args.get("json"):
        print(config_json)
        return

    config = json.loads(config_json)
    print(config["project"])
    print(f"├── backend: {config['backend']}")
    print(f"├── workflow: {config.get('workflow', 'workflow.py')}")

    if config.get("vars"):
        print("├── vars:")
        items = list(config["vars"].items())
        for i, (k, v) in enumerate(items):
            prefix = "│   └──" if i == len(items) - 1 else "│   ├──"
            print(f"{prefix} {k}: {v!r}")

    if config.get("secrets"):
        print("├── secrets:")
        items = list(config["secrets"].items())
        for i, (k, v) in enumerate(items):
            prefix = "│   └──" if i == len(items) - 1 else "│   ├──"
            masked = "(empty)" if not v else "****"
            print(f"{prefix} {k}: {masked}")

    if config.get("containers"):
        print("├── containers:")
        items = list(config["containers"].keys())
        for i, name in enumerate(items):
            prefix = "│   └──" if i == len(items) - 1 else "│   ├──"
            print(f"{prefix} {name}")

    extra = {k: v for k, v in config.items()
             if k not in ("project", "backend", "workflow", "vars", "secrets",
                          "image", "container", "containers", "network", "networks")}
    if extra:
        print(f"└── config: {', '.join(extra.keys())}")


def cmd_show(args):
    """Show a config section."""
    section = args.get("section")
    if not section:
        print("Usage: cutip show <section>")
        print("Sections: vars, secrets, container, containers, network, or any config key")
        sys.exit(1)
    print(_show(section, path=args.get("path")))


def cmd_run(args):
    """Run workflow.py."""
    import yaml

    path = args.get("path")
    if path:
        config_path = Path(path)
    else:
        config_path = Path("config.yaml")
        if not config_path.exists():
            print("Error: No config.yaml found in current directory")
            sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    # Prompt for empty vars/secrets
    for key, val in config.get("vars", {}).items():
        if not val:
            config["vars"][key] = input(f"  {key}: ").strip()

    for key, val in config.get("secrets", {}).items():
        if not val:
            config["secrets"][key] = input(f"  {key} (secret): ").strip()

    # Find and run workflow
    config_dir = config_path.parent
    workflow_name = config.get("workflow", "workflow.py")
    workflow_path = config_dir / workflow_name

    if not workflow_path.exists():
        print(f"Error: {workflow_name} not found")
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
        print("Error: workflow.py has no run_standalone() or main() function")
        sys.exit(1)


def cmd_init(args):
    """Scaffold a new project."""
    name = args.get("name")
    if not name:
        print("Usage: cutip init <project-name>")
        sys.exit(1)

    target = Path(args.get("path") or name)

    if (target / "config.yaml").exists():
        print(f"Error: config.yaml already exists in {target}")
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

    print(f"✓ Created {name} at {target}")
    print(f"  config.yaml + workflow.py")
    print(f"  Next: cd {name} && cutip validate && cutip run")


def cmd_verify(args):
    """Check prerequisites and environment."""
    import subprocess
    import platform

    print(f"cutip v{VERSION}")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print()

    # Python — try both python and python3
    python_found = False
    for cmd in (["python", "--version"], ["python3", "--version"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                print(f"  ✓ Python — {r.stdout.strip()}")
                python_found = True
                break
        except Exception:
            continue
    if not python_found:
        print("  ✗ Python — not found")

    checks = [
        ("Docker", ["docker", "--version"]),
        ("Podman", ["podman", "--version"]),
    ]
    for name, cmd in checks:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                print(f"  ✓ {name} — {r.stdout.strip()}")
            else:
                print(f"  · {name} — not found")
        except Exception:
            print(f"  · {name} — not found")

    # Check cutip-blocks
    try:
        import cutip_blocks
        print("  ✓ cutip-blocks — installed")
    except ImportError:
        print("  ✗ cutip-blocks — not installed (pip install cutip-blocks)")

    # Check Rust core
    try:
        from cutip._core import validate
        print("  ✓ cutip core — loaded")
    except ImportError:
        print("  ✗ cutip core — not loaded")


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
        print(f"cutip v{VERSION} — workflow automation framework")
        print()
        print("Commands:")
        print("  validate   Validate config.yaml")
        print("  tree       Print config structure")
        print("  show       Show a config section")
        print("  run        Run workflow.py")
        print("  init       Scaffold a new project")
        print("  verify     Check prerequisites")
        print()
        print("Options:")
        print("  --path     Path to config.yaml")
        print("  --json     Output as JSON (validate, tree)")
        print()
        print("Usage:")
        print("  cutip validate")
        print("  python -m cutip validate")
        return

    if args[0] in ("--version", "version"):
        print(f"cutip v{VERSION}")
        return

    command = args[0]
    if command not in COMMANDS:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)

    # Parse remaining args into a dict
    parsed = {}
    i = 1
    while i < len(args):
        if args[i] == "--path" and i + 1 < len(args):
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
