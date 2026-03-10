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

app = typer.Typer(
    name="cutip",
    help="CUTIP — Container Unit Templates in Python",
    no_args_is_help=True,
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

app.add_typer(init_app, name="init")
app.add_typer(tree_app, name="tree")
app.add_typer(validate_app, name="validate")
app.add_typer(show_app, name="show")
app.add_typer(group_app, name="group")
app.add_typer(unit_app, name="unit")
app.add_typer(card_app, name="card")
app.add_typer(secrets_app, name="secrets")
app.add_typer(issue_app, name="issue")
app.command("plan")(plan)
app.command("run")(run)
app.command("from-compose")(from_compose)
app.add_typer(upgrade_app, name="upgrade")


if __name__ == "__main__":
    app()
