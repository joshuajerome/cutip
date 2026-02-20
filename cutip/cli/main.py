from __future__ import annotations

import typer

from cutip.cli.commands.init import app as init_app
from cutip.cli.commands.plan import plan
from cutip.cli.commands.run import run
from cutip.cli.commands.show import app as show_app
from cutip.cli.commands.tree import app as tree_app
from cutip.cli.commands.validate import app as validate_app

app = typer.Typer(
    name="cutip",
    help="CUTIP — Container Unit Templates in Python",
    no_args_is_help=True,
)

app.add_typer(init_app, name="init")
app.add_typer(tree_app, name="tree")
app.add_typer(validate_app, name="validate")
app.add_typer(show_app, name="show")
app.command("plan")(plan)
app.command("run")(run)


if __name__ == "__main__":
    app()
