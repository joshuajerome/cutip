"""``cutip create`` — scaffold individual CUTIP artifacts."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from cutip.workspace.scaffold import _find_project_root

console = Console()
app = typer.Typer(help="Create CUTIP artifacts (cards, units, groups).")


@app.command("card")
def create_card(
    name: str = typer.Argument(..., help="Card name"),
    kind: str = typer.Option(
        "container", "--kind", "-k", help="Card kind: image, container, or network"
    ),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Create a new card YAML stub."""
    project_root = path or _find_project_root()
    card_dir = project_root / "cutip" / "cards" / name
    card_dir.mkdir(parents=True, exist_ok=True)

    if kind == "image":
        out = card_dir / f"{name}.image.yaml"
        out.write_text(
            f'apiVersion: cutip/v1\nkind: ImageCard\nname: {name}\nspec:\n  source: pull\n  image: "alpine:3.20"\n',
            encoding="utf-8",
        )
    elif kind == "network":
        out = card_dir / f"{name}.network.yaml"
        out.write_text(
            f"apiVersion: cutip/v1\nkind: NetworkCard\nname: {name}\nspec:\n  subnet: 172.20.0.0/16\n",
            encoding="utf-8",
        )
    else:
        # container (default) — also create image card
        img_out = card_dir / f"{name}.image.yaml"
        if not img_out.exists():
            img_out.write_text(
                f'apiVersion: cutip/v1\nkind: ImageCard\nname: {name}\nspec:\n  source: pull\n  image: "alpine:3.20"\n',
                encoding="utf-8",
            )
        out = card_dir / f"{name}.container.yaml"
        out.write_text(
            f"apiVersion: cutip/v1\nkind: ContainerCard\nname: {name}\nspec:\n"
            f"  imageRef:\n    ref: images/{name}\n  command:\n    - tail\n    - -f\n    - /dev/null\n",
            encoding="utf-8",
        )

    console.print(f"[green]Created {kind} card:[/green] {out.relative_to(project_root)}")


@app.command("unit")
def create_unit(
    name: str = typer.Argument(..., help="Unit name"),
    container: str = typer.Option(
        None, "--container", "-c", help="Container ref (e.g. containers/myapp)"
    ),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Create a new unit with YAML stub and optional hook files."""
    project_root = path or _find_project_root()
    unit_dir = project_root / "cutip" / "units" / name
    unit_dir.mkdir(parents=True, exist_ok=True)

    container_ref = container or f"containers/{name}"

    yaml_out = unit_dir / f"{name}.unit.yaml"
    yaml_out.write_text(
        f"apiVersion: cutip/v1\nkind: Unit\nname: {name}\nspec:\n  containerRef:\n    ref: {container_ref}\n",
        encoding="utf-8",
    )

    # Create empty hook stubs
    for hook_file in ("prehook.py", "workflow.py", "posthook.py"):
        hook_path = unit_dir / hook_file
        if not hook_path.exists():
            hook_path.write_text(
                f'"""CUTIP {hook_file.replace(".py", "")} for unit: {name}."""\n',
                encoding="utf-8",
            )

    console.print(f"[green]Created unit:[/green] {unit_dir.relative_to(project_root)}/")
    console.print(f"  {name}.unit.yaml, prehook.py, workflow.py, posthook.py")


@app.command("group")
def create_group(
    name: str = typer.Argument(..., help="Group name"),
    units: str = typer.Option(None, "--units", "-u", help="Comma-separated unit names"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Create a new group with YAML stub and orchestrator."""
    project_root = path or _find_project_root()
    group_dir = project_root / "cutip" / "groups" / name
    group_dir.mkdir(parents=True, exist_ok=True)

    unit_list = [u.strip() for u in units.split(",")] if units else []
    unit_yaml = (
        "\n".join(f"    - ref: units/{u}" for u in unit_list)
        if unit_list
        else "    - ref: units/example"
    )

    yaml_out = group_dir / "group.yaml"
    yaml_out.write_text(
        f"apiVersion: cutip/v1\nkind: Group\nname: {name}\nspec:\n  units:\n{unit_yaml}\n  workflow: workflow.py\n",
        encoding="utf-8",
    )

    # Create orchestrator stub
    orch_out = group_dir / "orchestrator.py"
    if not orch_out.exists():
        orch_out.write_text(
            f'"""CUTIP orchestrator for group: {name}."""\n\n'
            "from cutip.workflow.decorators import orchestrator\n\n\n"
            "@orchestrator\ndef main(ctx):\n"
            '    """Sequence unit workflows."""\n'
            "    pass\n",
            encoding="utf-8",
        )

    # Create workflow.py stub
    wf_out = group_dir / "workflow.py"
    if not wf_out.exists():
        wf_out.write_text(
            f'"""CUTIP workflow for group: {name}."""\n\n\n'
            "def main(ctx):\n"
            '    """Start containers and orchestrate."""\n'
            "    pass\n",
            encoding="utf-8",
        )

    console.print(f"[green]Created group:[/green] {group_dir.relative_to(project_root)}/")
    console.print("  group.yaml, orchestrator.py, workflow.py")
