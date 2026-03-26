from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path

import typer

from cutip.cli.commands.adopt import adopt
from cutip.cli.commands.compile import compile_cmd
from cutip.cli.commands.compose import from_compose
from cutip.cli.commands.create import app as create_app
from cutip.cli.commands.desktop import desktop
from cutip.cli.commands.diff import diff
from cutip.cli.commands.export_cmd import export_group
from cutip.cli.commands.import_cmd import import_group
from cutip.cli.commands.info import app as info_app
from cutip.cli.commands.init import app as init_app
from cutip.cli.commands.issue import issue_app
from cutip.cli.commands.ls import card_app, group_app, unit_app
from cutip.cli.commands.plan import preview
from cutip.cli.commands.rm import app as rm_app
from cutip.cli.commands.run import run
from cutip.cli.commands.secrets import secrets_app
from cutip.cli.commands.show import app as show_app
from cutip.cli.commands.status import status
from cutip.cli.commands.stop import stop
from cutip.cli.commands.tree import app as tree_app
from cutip.cli.commands.upgrade import app as upgrade_app
from cutip.cli.commands.validate import app as validate_app


def _backend_status() -> str:
    """Detect available backends and the current default."""
    available = []
    for name, mod in [("docker", "docker"), ("podman", "podman")]:
        try:
            __import__(mod)
            available.append(name)
        except ImportError:
            pass

    if not available:
        return "[bold]Backends[/bold]: none installed (pip install docker / podman)"

    # Try to read configured default from cutip.yaml in cwd
    default = None
    try:
        from cutip.cli.commands.run import _load_project_backend
        from cutip.workspace.scaffold import _find_project_root

        default = _load_project_backend(_find_project_root())
    except Exception:
        pass

    default = default or "docker"
    parts = []
    for name in available:
        label = f"[bold green]{name}[/bold green] (default)" if name == default else name
        parts.append(label)
    return "[bold]Backends[/bold]: " + ", ".join(parts)


_EPILOG = (
    "[bold]Common Workflows[/bold]\n\n"
    "  [bold]New project[/bold]:   cutip init → cutip validate → cutip run GROUP\n"
    "  [bold]Adopt[/bold]:         cutip adopt CONTAINER → cutip validate → cutip run GROUP\n"
    "  [bold]Upgrade[/bold]:       cutip info → pip install cutip --upgrade → cutip upgrade → cutip diff → cutip upgrade --apply\n"
    "  [bold]Inspect[/bold]:       cutip info → cutip group ls → cutip tree → cutip show group GROUP\n"
    "  [bold]Run[/bold]:           cutip status → cutip validate → cutip run GROUP\n"
    "  [bold]AI Issues[/bold]:     cutip issue diagnose → cutip issue fix → cutip issue push\n\n"
    "[bold]Docs[/bold]: https://joshuajerome.github.io/cutip"
)

app = typer.Typer(
    name="cutip",
    help=(
        "CUTIP — Container Unit Templates in Python.\n\n"
        "Define container environments with YAML artifacts, "
        "validate statically, and orchestrate with Python workflows. "
        "Supports Docker (default) and Podman backends."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
    epilog=_EPILOG,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cutip {_pkg_version('cutip')}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    # Inject live backend status into the epilog
    app.info.epilog = _EPILOG + "\n\n" + _backend_status()


_SHELLS = {"bash", "zsh", "fish", "powershell", "pwsh"}

_RC_FILES = {
    "bash": "~/.bashrc",
    "zsh": "~/.zshrc",
    "fish": "~/.config/fish/completions/cutip.fish",
}


@app.command("install-completion", rich_help_panel="Configuration")
def install_completion(
    shell: str = typer.Argument(
        None,
        help="Shell to install completion for (bash, zsh, fish). Auto-detected if omitted.",
    ),
) -> None:
    """Install shell tab-completion for cutip."""
    if shell is None:
        shell = _detect_shell()
    shell = shell.lower()
    if shell not in _SHELLS:
        typer.echo(f"Unsupported shell: {shell}. Supported: {', '.join(sorted(_SHELLS))}", err=True)
        raise typer.Exit(1)

    env_var = "_CUTIP_COMPLETE"
    script = _get_completion_script(shell, env_var)

    if shell == "fish":
        comp_dir = Path("~/.config/fish/completions").expanduser()
        comp_dir.mkdir(parents=True, exist_ok=True)
        comp_path = comp_dir / "cutip.fish"
        comp_path.write_text(script, encoding="utf-8")
        typer.echo(f"Completion installed: {comp_path}")
        typer.echo(f"Restart your shell or run: source {comp_path}")
    else:
        rc_file = Path(_RC_FILES.get(shell, f"~/.{shell}rc")).expanduser()
        marker = "# cutip shell completion"
        block = f"\n{marker}\n{script}\n"

        if rc_file.exists():
            content = rc_file.read_text(encoding="utf-8")
            if marker in content:
                typer.echo(f"Completion already installed in {rc_file}")
                raise typer.Exit(0)
        else:
            content = ""

        rc_file.write_text(content + block, encoding="utf-8")
        typer.echo(f"Completion installed in {rc_file}")
        typer.echo(f"Restart your shell or run: source {rc_file}")


def _detect_shell() -> str:
    """Detect the current shell, with fallbacks."""
    try:
        import shellingham

        name, _ = shellingham.detect_shell()
        return name
    except Exception:
        pass

    shell_env = os.environ.get("SHELL", "")
    if shell_env:
        return Path(shell_env).name

    typer.echo(
        "Could not detect your shell. Please specify it explicitly:\n"
        "  cutip install-completion bash\n"
        "  cutip install-completion zsh\n"
        "  cutip install-completion fish",
        err=True,
    )
    raise typer.Exit(1)


def _get_completion_script(shell: str, env_var: str) -> str:
    """Generate the completion script for the given shell."""
    source_key = f"source_{shell}"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"""
import os
os.environ["{env_var}"] = "{source_key}"
import sys
sys.argv = ["cutip"]
from cutip.cli.main import app
try:
    app(standalone_mode=False)
except SystemExit:
    pass
""",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, env_var: source_key},
    )
    if result.stdout.strip():
        return result.stdout.strip()
    # Fallback: generate script directly via Click's env var mechanism
    if shell == "zsh":
        return f"""#compdef cutip

_cutip_completion() {{
  eval $(env _TYPER_COMPLETE_ARGS="${{words[1,$CURRENT]}}" {env_var}=complete_zsh cutip)
}}

compdef _cutip_completion cutip"""
    elif shell == "bash":
        return f"""_cutip_completion() {{
  local IFS=$'\\n'
  COMPREPLY=( $(env _TYPER_COMPLETE_ARGS="${{COMP_WORDS[*]}}" {env_var}=complete_bash cutip) )
  return 0
}}

complete -o default -F _cutip_completion cutip"""
    elif shell == "fish":
        return f'''complete -c cutip -f -a "(env _TYPER_COMPLETE_ARGS=(commandline -cp) {env_var}=complete_fish cutip)"'''
    return ""


# ── Workflow ─────────────────────────────────────────────────────────────────
_WF = "Workflow"
app.add_typer(init_app, name="init", rich_help_panel=_WF)
app.command("run", rich_help_panel=_WF)(run)
app.command("stop", rich_help_panel=_WF)(stop)
app.command("preview", rich_help_panel=_WF)(preview)
app.command("plan", hidden=True)(preview)  # backward-compat alias
app.command("from-compose", rich_help_panel=_WF)(from_compose)
app.command("adopt", rich_help_panel=_WF)(adopt)
app.command("desktop", rich_help_panel=_WF)(desktop)

app.add_typer(info_app, name="info", rich_help_panel=_WF)
app.add_typer(create_app, name="create", rich_help_panel=_WF)

app.command("compile", rich_help_panel=_WF)(compile_cmd)
app.command("status", rich_help_panel=_WF)(status)

# ── Inspect ──────────────────────────────────────────────────────────────────
_IN = "Inspect"
app.add_typer(tree_app, name="tree", rich_help_panel=_IN)
app.add_typer(validate_app, name="validate", rich_help_panel=_IN)
app.add_typer(show_app, name="show", rich_help_panel=_IN)
app.add_typer(group_app, name="group", rich_help_panel=_IN)
app.add_typer(unit_app, name="unit", rich_help_panel=_IN)
app.add_typer(card_app, name="card", rich_help_panel=_IN)

# ── Manage ────────────────────────────────────────────────────────────────────
_MG = "Manage"
app.add_typer(rm_app, name="rm", rich_help_panel=_MG)
app.command("export", rich_help_panel=_MG)(export_group)
app.command("import", rich_help_panel=_MG)(import_group)

# ── Configuration ────────────────────────────────────────────────────────────
_CF = "Configuration"
app.add_typer(secrets_app, name="secrets", rich_help_panel=_CF)
app.add_typer(upgrade_app, name="upgrade", rich_help_panel=_CF)
app.command("diff", rich_help_panel=_CF)(diff)

# ── AI & Issues ──────────────────────────────────────────────────────────────
_AI = "AI & Issues"
app.add_typer(issue_app, name="issue", rich_help_panel=_AI)


if __name__ == "__main__":
    app()
