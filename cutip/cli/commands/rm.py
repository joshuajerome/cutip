"""``cutip rm`` — safely remove CUTIP artifacts with archive."""

from __future__ import annotations

import tarfile
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipError
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root

console = Console()
app = typer.Typer(help="Remove CUTIP artifacts (with archive to .cutip/trash/).")


def _archive_files(
    project_root: Path,
    files: list[Path],
    archive_name: str,
) -> Path:
    """Archive files to .cutip/trash/ and return the archive path."""
    trash_dir = project_root / ".cutip" / "trash"
    trash_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_path = trash_dir / f"{archive_name}-{ts}.tar.gz"

    with tarfile.open(archive_path, "w:gz") as tar:
        for f in files:
            if f.is_file():
                arcname = str(f.relative_to(project_root))
                tar.add(f, arcname=arcname)

    return archive_path


def _collect_group_files(
    group_name: str,
    project_root: Path,
    registry,
    resolver: RefResolver,
) -> list[Path]:
    """Collect all files belonging to a group and its units/cards."""
    files: list[Path] = []
    cutip_dir = project_root / "cutip"

    group = registry.get_group(group_name)
    if group is None:
        raise CutipError(f"Group '{group_name}' not found")

    # Group files
    group_source = registry.source_of(f"groups/{group_name}")
    if group_source:
        group_dir = group_source.parent
    else:
        group_dir = cutip_dir / "groups" / group_name

    if group_dir.is_dir():
        files.extend(group_dir.rglob("*"))

    # Unit files
    for unit_ref in group.spec.units:
        try:
            unit = resolver.resolve_unit(unit_ref.ref)
            unit_source = registry.source_of(f"units/{unit.name}")
            unit_dir = unit_source.parent if unit_source else cutip_dir / "units" / unit.name
            if unit_dir.is_dir():
                files.extend(unit_dir.rglob("*"))

            # Card files
            container_ref = unit.spec.containerRef.ref
            card_source = registry.source_of(container_ref)
            if card_source:
                card_dir = card_source.parent
                if card_dir.is_dir():
                    files.extend(card_dir.rglob("*"))
        except CutipError:
            continue

    return [f for f in files if f.is_file()]


def _remove_empty_parents(path: Path, stop_at: Path) -> None:
    """Remove empty parent directories up to stop_at."""
    parent = path.parent
    while parent != stop_at and parent.is_dir():
        try:
            next(parent.iterdir())
            break  # not empty
        except StopIteration:
            parent.rmdir()
            parent = parent.parent


@app.command("group")
def rm_group(
    group_name: str = typer.Argument(..., help="Group name to remove"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Remove a group and all its artifacts (archived to .cutip/trash/)."""
    project_root = path or _find_project_root()
    registry = WorkspaceDiscovery(project_root).discover()
    resolver = RefResolver(registry)

    files = _collect_group_files(group_name, project_root, registry, resolver)
    if not files:
        console.print(f"[yellow]No files found for group '{group_name}'.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Files to remove ({len(files)}):[/bold]")
    for f in files[:20]:
        console.print(f"  {f.relative_to(project_root)}")
    if len(files) > 20:
        console.print(f"  ... and {len(files) - 20} more")

    if not typer.confirm("Archive and remove these files?", default=False):
        raise typer.Exit(0)

    archive = _archive_files(project_root, files, group_name)

    cutip_dir = project_root / "cutip"
    for f in files:
        f.unlink(missing_ok=True)
        _remove_empty_parents(f, cutip_dir)

    console.print(f"[green]Archived to {archive.relative_to(project_root)}[/green]")
    console.print(
        f"[dim]Restore with: tar xzf {archive.relative_to(project_root)} -C {project_root}[/dim]"
    )


@app.command("unit")
def rm_unit(
    unit_name: str = typer.Argument(..., help="Unit name to remove"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Remove a unit and its cards (archived to .cutip/trash/)."""
    project_root = path or _find_project_root()
    registry = WorkspaceDiscovery(project_root).discover()
    cutip_dir = project_root / "cutip"

    unit = registry.get_unit(unit_name)
    if unit is None:
        console.print(f"[red]Unit '{unit_name}' not found.[/red]")
        raise typer.Exit(1)

    # Check if any group references this unit
    for gname, group in registry.groups.items():
        for uref in group.spec.units:
            if uref.ref.endswith(f"/{unit_name}"):
                console.print(
                    f"[red]Cannot remove unit '{unit_name}': referenced by group '{gname}'.[/red]"
                )
                raise typer.Exit(1)

    files: list[Path] = []
    unit_source = registry.source_of(f"units/{unit_name}")
    unit_dir = unit_source.parent if unit_source else cutip_dir / "units" / unit_name
    if unit_dir.is_dir():
        files.extend(f for f in unit_dir.rglob("*") if f.is_file())

    # Card files
    container_ref = unit.spec.containerRef.ref
    card_source = registry.source_of(container_ref)
    if card_source:
        card_dir = card_source.parent
        if card_dir.is_dir():
            files.extend(f for f in card_dir.rglob("*") if f.is_file())

    if not files:
        console.print(f"[yellow]No files found for unit '{unit_name}'.[/yellow]")
        raise typer.Exit(0)

    archive = _archive_files(project_root, files, f"unit-{unit_name}")

    for f in files:
        f.unlink(missing_ok=True)
        _remove_empty_parents(f, cutip_dir)

    console.print(
        f"[green]Removed unit '{unit_name}'. Archived to {archive.relative_to(project_root)}[/green]"
    )


@app.command("card")
def rm_card(
    card_ref: str = typer.Argument(..., help="Card ref to remove (e.g. containers/myapp)"),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Remove a card (archived to .cutip/trash/)."""
    project_root = path or _find_project_root()
    registry = WorkspaceDiscovery(project_root).discover()
    cutip_dir = project_root / "cutip"

    card = registry.get_card(card_ref)
    if card is None:
        console.print(f"[red]Card '{card_ref}' not found.[/red]")
        raise typer.Exit(1)

    # Check if any unit references this card
    for uname, unit in registry.units.items():
        if unit.spec.containerRef.ref == card_ref:
            console.print(
                f"[red]Cannot remove card '{card_ref}': referenced by unit '{uname}'.[/red]"
            )
            raise typer.Exit(1)

    card_source = registry.source_of(card_ref)
    if card_source is None or not card_source.is_file():
        console.print(f"[yellow]No source file found for card '{card_ref}'.[/yellow]")
        raise typer.Exit(0)

    files = [card_source]
    safe_name = card_ref.replace("/", "-")
    archive = _archive_files(project_root, files, f"card-{safe_name}")

    card_source.unlink(missing_ok=True)
    _remove_empty_parents(card_source, cutip_dir)

    console.print(
        f"[green]Removed card '{card_ref}'. Archived to {archive.relative_to(project_root)}[/green]"
    )
