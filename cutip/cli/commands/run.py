from __future__ import annotations

import os
import re
from pathlib import Path

import typer
from rich.console import Console

from cutip.backends.shared.image import image_alias
from cutip.context.startup import UnitStartupLoader
from cutip.context.workflow import CutipContext, WorkflowLoader
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipError, CutipWorkflowError
from cutip.utils.logging import setup_logging
from cutip.utils.runs import iso_now, run_lock, write_run_record
from cutip.validation.graph import GraphValidator
from cutip.workspace.discovery import WorkspaceDiscovery
from cutip.workspace.scaffold import _find_project_root
from loguru import logger

console = Console()


# ---------------------------------------------------------------------------
# Tab-completion helper
# ---------------------------------------------------------------------------

def _complete_group_name(incomplete: str) -> list[str]:
    """Return group names that start with *incomplete* (used by shell completion)."""
    try:
        project_root = _find_project_root()
        registry = WorkspaceDiscovery(project_root).discover()
        return [name for name in registry.groups if name.startswith(incomplete)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Vars helpers
# ---------------------------------------------------------------------------

def _load_vars(project_root: Path) -> tuple[dict, frozenset[str]]:
    """Load ``cutip/vars.yaml`` from the project if it exists.

    Supports two formats:

    **Flat (legacy)** — all keys are treated as ``required``::

        ssh_private_key: "/Users/you/.ssh/id_ed25519"
        my_repo: "/Users/you/dev/my-project"

    **Structured** — explicit ``required`` and ``generated`` sections::

        required:
          ssh_private_key: ""
          blueprint_manager: ""

        generated:
          blueprint_manager_data: ".snf-blueprint-manager"

    *required* keys must be present **and** non-empty at run time.

    *generated* keys are resolved to absolute paths relative to the project
    root and their directories are created automatically by
    :func:`_prepare_generated_dirs`.  They never fail validation.

    Returns ``(flat_vars, generated_keys)`` where *flat_vars* is the merged
    dict of both sections and *generated_keys* is the frozenset of keys whose
    directories CUTIP manages.
    """
    import yaml as _yaml
    p = project_root / "cutip" / "vars.yaml"
    if not p.exists():
        return {}, frozenset()

    data = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CutipError("cutip/vars.yaml must be a YAML mapping (key: value pairs)")

    # ── Structured format (has 'required' or 'generated' top-level keys) ──
    if "required" in data or "generated" in data:
        req = data.get("required") or {}
        gen = data.get("generated") or {}

        if not isinstance(req, dict):
            raise CutipError("cutip/vars.yaml: 'required' must be a mapping")
        if not isinstance(gen, dict):
            raise CutipError("cutip/vars.yaml: 'generated' must be a mapping")

        flat: dict = {}
        flat.update({k: (str(v) if v is not None else "") for k, v in req.items()})

        generated_keys: set[str] = set()
        for key, rel_path in gen.items():
            if rel_path is None:
                raise CutipError(
                    f"cutip/vars.yaml: generated key '{key}' has no path value"
                )
            abs_path = (project_root / str(rel_path)).resolve()
            flat[key] = str(abs_path)
            generated_keys.add(key)

        logger.debug(
            f"Loaded vars: {len(req)} required, {len(gen)} generated "
            f"(from cutip/vars.yaml)"
        )
        return flat, frozenset(generated_keys)

    # ── Flat (legacy) format — every key is required ──────────────────────
    flat = {k: (str(v) if v is not None else "") for k, v in data.items()}
    logger.debug(f"Loaded {len(flat)} var(s) from cutip/vars.yaml")
    return flat, frozenset()


def _resolve_vars_in_str(text: str, vars: dict) -> str:
    """Resolve ``{{ vars.key }}`` placeholders in *text*.

    Raises :class:`~cutip.utils.exceptions.CutipError` when a referenced key
    is absent from *vars*.
    """
    def _replace(match: re.Match) -> str:
        key = match.group(1).strip()
        if key not in vars:
            raise CutipError(
                f"'{{{{ vars.{key} }}}}' not found in cutip/vars.yaml"
            )
        return str(vars[key])

    return re.sub(r"\{\{\s*vars\.(\w+)\s*\}\}", _replace, text)


def _validate_vars(
    ctx: CutipContext,
    vars: dict,
    generated_keys: frozenset[str] = frozenset(),
) -> None:
    """Validate that every ``{{ vars.key }}`` referenced in resolved cards is
    present *and* non-empty in *vars*.

    *generated_keys* are skipped — their values are resolved and created
    automatically by CUTIP, so they are always valid.

    Called before any lifecycle step so that missing or unfilled vars.yaml
    entries surface as a clear error instead of cryptic backend failures
    (e.g. ``statfs /sheets: no such file or directory`` when a path prefix
    resolves to an empty string).

    Raises :class:`~cutip.utils.exceptions.CutipError` listing all problems.
    """
    pattern = re.compile(r"\{\{\s*vars\.(\w+)\s*\}\}")
    errors: list[str] = []

    for card in ctx.resolved_cards.values():
        if not isinstance(card, ContainerCard):
            continue
        for mount in card.spec.mounts:
            for field_name, text in (("source", mount.source), ("target", mount.target)):
                for key in pattern.findall(text):
                    if key in generated_keys:
                        continue  # auto-managed by CUTIP — always valid
                    if key not in vars:
                        errors.append(
                            f"  [{card.metadata.name}] {field_name}: "
                            f"'{{{{ vars.{key} }}}}' is not defined in cutip/vars.yaml"
                        )
                    elif not str(vars[key]).strip():
                        errors.append(
                            f"  [{card.metadata.name}] {field_name}: "
                            f"'{{{{ vars.{key} }}}}' is defined but empty in cutip/vars.yaml"
                        )

    if errors:
        raise CutipError(
            "cutip/vars.yaml has missing or empty values required by your cards:\n"
            + "\n".join(errors)
            + "\n\nFill in the values in cutip/vars.yaml and re-run."
        )


def _prepare_generated_dirs(
    vars: dict,
    generated_keys: frozenset[str],
) -> None:
    """Create directories for all ``generated`` vars.

    Generated vars hold paths that CUTIP owns (e.g. data directories relative
    to the project root).  The directory is created with ``mkdir -p`` before
    any workflow step runs so that subsequent ``create_host_path: true`` mounts
    can safely create sub-directories inside it.
    """
    for key in generated_keys:
        path = Path(vars[key])
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Prepared generated directory [{key}]: {path}")


def _resolve_vars_in_card(card: ContainerCard, vars: dict) -> ContainerCard:
    """Return a copy of *card* with ``{{ vars.key }}`` resolved in mount paths.

    Only mount ``source`` and ``target`` fields are interpolated.  Other
    string fields (command, workdir, etc.) are not touched.
    """
    if not vars or not card.spec.mounts:
        return card

    resolved_mounts = []
    for mount in card.spec.mounts:
        resolved_mounts.append(
            mount.model_copy(update={
                "source": _resolve_vars_in_str(mount.source, vars),
                "target": _resolve_vars_in_str(mount.target, vars),
            })
        )

    resolved_spec = card.spec.model_copy(update={"mounts": resolved_mounts})
    return card.model_copy(update={"spec": resolved_spec})


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context(
    group_name: str,
    project_root: Path,
    registry,
    runtime=None,
    vars: dict | None = None,
) -> CutipContext:
    """Assemble a CutipContext for the given group."""
    group = registry.get_group(group_name)
    if group is None:
        raise CutipError(f"Group '{group_name}' not found in registry")

    resolver = RefResolver(registry)
    resolved_units: dict = {}
    resolved_cards: dict = {}

    for unit_ref in group.spec.units:
        unit = resolver.resolve_unit(unit_ref.ref)
        resolved_units[unit.name] = unit

        container_ref = unit.spec.containerRef.ref
        cc = resolver.resolve(container_ref)
        resolved_cards[container_ref] = cc

        if isinstance(cc, ContainerCard):
            img = resolver.resolve(cc.spec.imageRef.ref)
            resolved_cards[cc.spec.imageRef.ref] = img

            # networkRef is optional when network_mode is set
            if cc.spec.networkRef is not None:
                net = resolver.resolve(cc.spec.networkRef.ref)
                resolved_cards[cc.spec.networkRef.ref] = net

    return CutipContext(
        group=group,
        resolved_units=resolved_units,
        resolved_cards=resolved_cards,
        registry=registry,
        project_root=project_root,
        runtime=runtime,
        vars=vars or {},
    )


# ---------------------------------------------------------------------------
# Lifecycle helpers — called by run() in order
# ---------------------------------------------------------------------------

def _prepare_host_dirs(ctx: CutipContext, project_root: Path, vars: dict | None = None) -> None:
    """Create host-side directories for any mount with ``create_host_path: true``.

    ``{{ vars.key }}`` placeholders in mount sources are resolved before the
    path is created, so declarative YAML mounts with user-specific sources
    work correctly without any Python in the workflow.
    """
    for card in ctx.resolved_cards.values():
        if not isinstance(card, ContainerCard):
            continue
        for mount in card.spec.mounts:
            if not mount.create_host_path:
                continue
            source = mount.source
            if vars and "{{" in source:
                source = _resolve_vars_in_str(source, vars)
            host_path = Path(source)
            if not host_path.is_absolute():
                host_path = project_root / host_path
            host_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Prepared host directory: {host_path}")


def _prepare_volumes(ctx: CutipContext, client) -> None:
    """Create named volumes declared in ContainerCard.spec.volumes if missing.

    Runs before images are built so the volume exists when the container is
    created.  Mirrors ``_prepare_host_dirs`` but for named (non-bind) volumes.
    """
    for card in ctx.resolved_cards.values():
        if not isinstance(card, ContainerCard):
            continue
        for vol_name in card.spec.volumes:
            try:
                client.volumes.get(vol_name)
                logger.debug(f"Volume already exists: {vol_name}")
            except Exception:
                client.volumes.create(vol_name)
                logger.debug(f"Created volume: {vol_name}")


def _build_and_pull_images(
    ctx: CutipContext, backend, project_root: Path, vars: dict
) -> None:
    """Build or pull every ImageCard resolved in the context."""
    for card in ctx.resolved_cards.values():
        if not isinstance(card, ImageCard):
            continue
        if card.spec.source == "build":
            logger.info(f"Building image: {card.metadata.name}")
            backend.build_image(card, project_root=project_root, vars=vars)
        elif card.spec.source == "pull":
            logger.info(f"Pulling image: {card.metadata.name}")
            backend.pull_image(card)


def _ensure_networks(ctx: CutipContext, backend) -> None:
    """Create any NetworkCard-backed networks that do not already exist."""
    for card in ctx.resolved_cards.values():
        if isinstance(card, NetworkCard):
            backend.ensure_network(card)


def _provision_containers(ctx: CutipContext, backend, vars: dict) -> None:
    """Remove stale containers and create fresh ones with vars resolved."""
    for card in ctx.resolved_cards.values():
        if not isinstance(card, ContainerCard):
            continue

        name = card.metadata.name

        # Remove stale container from a previous run (if any)
        try:
            backend.remove_container(name)
            logger.info(f"Removed stale container: {name}")
        except Exception:
            pass  # not found — nothing to clean up

        # Resolve {{ vars.key }} in mount sources / targets
        resolved_card = _resolve_vars_in_card(card, vars)

        # Derive the image alias from the resolved ImageCard
        img_ref = resolved_card.spec.imageRef.ref
        img_card = ctx.resolved_cards.get(img_ref)
        img_name = image_alias(img_card) if isinstance(img_card, ImageCard) else None

        backend.create_container(resolved_card, image_name=img_name)


def _run_unit_pre_builds(
    ctx: CutipContext, registry, project_root: Path
) -> None:
    """Call ``pre_build(ctx)`` in each unit's ``startup.py`` (if it exists).

    Runs *before* any images are built so that units can stage build-context
    files (e.g. resolving local npm ``file:`` dependencies) that must be
    present when ``podman build`` runs.
    """
    loader = UnitStartupLoader(project_root)
    for unit in ctx.resolved_units.values():
        loader.run_pre_build(unit, ctx, registry)


def _run_unit_startups(
    ctx: CutipContext, registry, project_root: Path
) -> None:
    """Call ``startup(ctx)`` in each unit's ``startup.py`` (if it exists).

    Runs after all containers have started, before the group-level
    ``workflow.main(ctx)``.  Per-unit startup files live at::

        cutip/units/<unit-name>/startup.py
    """
    loader = UnitStartupLoader(project_root)
    for unit in ctx.resolved_units.values():
        loader.run(unit, ctx, registry)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

def run(
    group_name: str = typer.Argument(
        ...,
        help="Name of the group to run",
        autocompletion=_complete_group_name,
    ),
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Connect to the local Podman socket directly (no SSH tunnel). "
             "Uses CONTAINER_HOST env var when set. "
             "Required for CI / Linux environments.",
    ),
    path: Path = typer.Option(None, "--path", "-p", show_default=False),
) -> None:
    """Run a group's workflow against the Podman backend.

    CUTIP handles the container lifecycle up to creation; workflow.main(ctx)
    is responsible for starting containers and orchestrating across units.

    \b
      1. Load cutip/vars.yaml (user-specific paths & credentials)
      2. Create host directories for mounts with create_host_path: true
      3. Create named volumes declared in ContainerCard.spec.volumes
      4. Call pre_build(ctx) in each unit's startup.py (if defined)
      5. Build / pull images declared in ImageCards
      6. Ensure networks declared in NetworkCards
      7. Remove stale containers and create fresh ones (no auto-start)
      8. Call workflow.main(ctx) — start containers, orchestrate units
      9. Call startup(ctx) in each unit's startup.py (post-start hooks)
    """
    project_root = path or _find_project_root()
    cutip_dir   = project_root / ".cutip"
    setup_logging(log_dir=cutip_dir / "logs")

    registry = WorkspaceDiscovery(project_root).discover()

    # Validate first
    result = GraphValidator(registry, project_root=project_root).validate()
    if not result.ok:
        for err in result.errors:
            console.print(f"[red]{err}[/red]")
        console.print("[bold red]Validation failed. Fix errors before running.[/bold red]")
        raise typer.Exit(1)

    # Honour env-var shortcut in addition to the CLI flag
    is_local = local or os.environ.get("CUTIP_LOCAL", "").lower() in ("1", "true", "yes")

    # Connect Podman backend
    try:
        from cutip.backends.podman import PodmanBackend
        _backend = PodmanBackend.connect_local() if is_local else PodmanBackend.connect()
    except CutipError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    started_at = iso_now()
    status = "failure"
    run_error: str | None = None

    project_vars, generated_keys = _load_vars(project_root)

    # Create generated directories before any lifecycle step so they exist
    # when create_host_path mounts try to create sub-directories inside them.
    _prepare_generated_dirs(project_vars, generated_keys)

    try:
        with run_lock(cutip_dir / "locks", group_name):
            ctx = _build_context(
                group_name, project_root, registry,
                runtime=_backend.client,
                vars=project_vars,
            )

            # Validate all {{ vars.X }} references are present and non-empty
            # (generated keys are auto-managed and always valid — skip them)
            _validate_vars(ctx, project_vars, generated_keys)

            # Steps 1–2: host dirs + named volumes
            _prepare_host_dirs(ctx, project_root, vars=project_vars)
            _prepare_volumes(ctx, _backend.client)

            # Step 3: per-unit pre_build hooks (stage build-context files)
            _run_unit_pre_builds(ctx, registry, project_root)

            # Steps 4–6: images → networks → create containers (no auto-start)
            _build_and_pull_images(ctx, _backend, project_root, project_vars)
            _ensure_networks(ctx, _backend)
            _provision_containers(ctx, _backend, project_vars)

            # Step 7: group-level workflow main() — starts containers, orchestrates
            workflow_loader = WorkflowLoader(project_root)
            workflow_loader.run(ctx.group, ctx, registry)

            # Step 8: per-unit startup.py post-start hooks
            _run_unit_startups(ctx, registry, project_root)
            status = "success"
    except CutipError as exc:
        run_error = str(exc)
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except CutipWorkflowError as exc:
        run_error = str(exc)
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    finally:
        write_run_record(
            cutip_dir / "runs",
            group=group_name,
            backend="podman",
            started_at=started_at,
            status=status,
            error=run_error,
        )
        _backend.disconnect()
