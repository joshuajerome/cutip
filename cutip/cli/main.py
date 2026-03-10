from __future__ import annotations

from importlib.metadata import version as _pkg_version

import typer

from cutip.cli.commands.compose import from_compose
from cutip.cli.commands.init import app as init_app
from cutip.cli.commands.issue import issue_app
from cutip.cli.commands.upgrade import app as upgrade_app
from cutip.cli.commands.ls import card_app, group_app, unit_app
from cutip.cli.commands.plan import plan
from cutip.cli.commands.run import run
from cutip.cli.commands.secrets import secrets_app
from cutip.cli.commands.show import app as show_app
from cutip.cli.commands.tree import app as tree_app
from cutip.cli.commands.validate import app as validate_app

_EPILOG = (
    "[bold]Getting Started[/bold]: "
    "cutip init · cutip from-compose FILE · cutip validate · cutip run GROUP\n\n"
    "[bold]Updating[/bold]: "
    "pip install --upgrade cutip · cutip upgrade --apply\n\n"
    "[bold]AI Issues[/bold] (requires cutip\\[ai]): "
    "pip install cutip\\[ai] · export ANTHROPIC_API_KEY=... · cutip issue diagnose\n\n"
    "[bold]GitHub[/bold]: "
    "gh auth login (required for cutip issue push)\n\n"
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
    version: bool = typer.Option(  # noqa: ARG001
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    pass


# ── Workflow ─────────────────────────────────────────────────────────────────
_WF = "Workflow"
app.add_typer(init_app, name="init", rich_help_panel=_WF)
app.command("run", rich_help_panel=_WF)(run)
app.command("plan", rich_help_panel=_WF)(plan)
app.command("from-compose", rich_help_panel=_WF)(from_compose)

# ── Inspect ──────────────────────────────────────────────────────────────────
_IN = "Inspect"
app.add_typer(tree_app, name="tree", rich_help_panel=_IN)
app.add_typer(validate_app, name="validate", rich_help_panel=_IN)
app.add_typer(show_app, name="show", rich_help_panel=_IN)
app.add_typer(group_app, name="group", rich_help_panel=_IN)
app.add_typer(unit_app, name="unit", rich_help_panel=_IN)
app.add_typer(card_app, name="card", rich_help_panel=_IN)

# ── Configuration ────────────────────────────────────────────────────────────
_CF = "Configuration"
app.add_typer(secrets_app, name="secrets", rich_help_panel=_CF)
app.add_typer(upgrade_app, name="upgrade", rich_help_panel=_CF)

# ── AI & Issues ──────────────────────────────────────────────────────────────
_AI = "AI & Issues"
app.add_typer(issue_app, name="issue", rich_help_panel=_AI)


if __name__ == "__main__":
    app()
