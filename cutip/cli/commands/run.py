from __future__ import annotations

import os
import re
import sys
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
# Group name helpers — partial matching + tab completion
# ---------------------------------------------------------------------------

def _match_group_name(incomplete: str, group_names: list[str]) -> list[str]:
    """Return group names that match *incomplete* by full prefix or segment prefix.

    Matching rules (in priority order — first match type wins):
      1. Full prefix:    ``snf-bl``      matches ``snf-blueprint-manager``
      2. Segment prefix: ``bl``          matches ``snf-blueprint-manager``
                         ``blueprint``   matches ``snf-blueprint-manager``

    A "segment" is any hyphen-delimited part of the group name.
    """
    # 1. Full prefix matches
    full_prefix = [n for n in group_names if n.startswith(incomplete)]
    if full_prefix:
        return full_prefix

    # 2. Segment prefix matches
    return [
        n for n in group_names
        if any(seg.startswith(incomplete) for seg in n.split("-"))
    ]


def _resolve_group_name(name: str, registry) -> str:
    """Resolve a full or partial group name to an exact registry key.

    Accepts an exact name, a unique full-name prefix, or a unique segment prefix.
    Raises :class:`~cutip.utils.exceptions.CutipError` when the name is
    missing or ambiguous.
    """
    if name in registry.groups:
        return name

    candidates = _match_group_name(name, list(registry.groups))

    if len(candidates) == 1:
        resolved = candidates[0]
        logger.debug(f"Resolved group '{name}' → '{resolved}'")
        return resolved

    if len(candidates) > 1:
        raise CutipError(
            f"Ambiguous group name '{name}': matches {candidates}. "
            f"Be more specific."
        )

    raise CutipError(f"Group '{name}' not found in registry")


def _complete_group_name(incomplete: str) -> list[str]:
    """Return group names that match *incomplete* (used by shell completion)."""
    try:
        project_root = _find_project_root()
        registry = WorkspaceDiscovery(project_root).discover()
        return _match_group_name(incomplete, list(registry.groups))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Paths / secrets helpers
# ---------------------------------------------------------------------------

def _load_paths(project_root: Path) -> tuple[dict, frozenset[str]]:
    """Load ``cutip/paths.yaml`` from the project if it exists.

    Supports two formats:

    **Flat (legacy)** — all keys are treated as ``required``::

        ssh_private_key: "/Users/you/.ssh/id_ed25519"
        my_repo: "/Users/you/dev/my-project"

    **Structured** — explicit ``required`` and ``generated`` sections::

        required:
          my_repo: ""

        generated:
          data_dir: ".my-data"

    *required* keys must be present **and** non-empty at run time.

    *generated* keys are resolved to absolute paths relative to the project
    root and their directories are created automatically by
    :func:`_prepare_generated_dirs`.  They never fail validation.

    Returns ``(flat_paths, generated_keys)`` where *flat_paths* is the merged
    dict of both sections and *generated_keys* is the frozenset of keys whose
    directories CUTIP manages.
    """
    import yaml as _yaml
    p = project_root / "cutip" / "paths.yaml"
    if not p.exists():
        return {}, frozenset()

    data = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CutipError("cutip/paths.yaml must be a YAML mapping (key: value pairs)")

    # ── Structured format (has 'required' or 'generated' top-level keys) ──
    if "required" in data or "generated" in data:
        req = data.get("required") or {}
        gen = data.get("generated") or {}

        if not isinstance(req, dict):
            raise CutipError("cutip/paths.yaml: 'required' must be a mapping")
        if not isinstance(gen, dict):
            raise CutipError("cutip/paths.yaml: 'generated' must be a mapping")

        flat: dict = {}
        flat.update({k: (str(v) if v is not None else "") for k, v in req.items()})

        generated_keys: set[str] = set()
        for key, rel_path in gen.items():
            if rel_path is None or not str(rel_path).strip():
                raise CutipError(
                    f"cutip/paths.yaml: generated key '{key}' must have a non-empty "
                    f"path value (e.g. '.my-data'). Got: {rel_path!r}"
                )
            abs_path = (project_root / str(rel_path)).resolve()
            flat[key] = str(abs_path)
            generated_keys.add(key)

        logger.debug(
            f"Loaded paths: {len(req)} required, {len(gen)} generated "
            f"(from cutip/paths.yaml)"
        )
        return flat, frozenset(generated_keys)

    # ── Flat (legacy) format — every key is required ──────────────────────
    flat = {k: (str(v) if v is not None else "") for k, v in data.items()}
    logger.debug(f"Loaded {len(flat)} path(s) from cutip/paths.yaml")
    return flat, frozenset()


def _load_secrets(project_root: Path) -> dict:
    """Load ``cutip/secrets.yaml`` from the project if it exists.

    Returns a flat dict of secret key → value pairs.
    """
    import yaml as _yaml
    p = project_root / "cutip" / "secrets.yaml"
    if not p.exists():
        return {}

    data = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise CutipError("cutip/secrets.yaml must be a YAML mapping (key: value pairs)")

    if "required" in data:
        req = data.get("required") or {}
        if not isinstance(req, dict):
            raise CutipError("cutip/secrets.yaml: 'required' must be a mapping")
        flat = {k: (str(v) if v is not None else "") for k, v in req.items()}
        logger.debug(f"Loaded {len(flat)} secret(s) from cutip/secrets.yaml")
        return flat

    # Flat format — every key is a secret
    flat = {k: (str(v) if v is not None else "") for k, v in data.items()}
    logger.debug(f"Loaded {len(flat)} secret(s) from cutip/secrets.yaml")
    return flat


def _resolve_refs_in_str(text: str, paths: dict, secrets: dict) -> str:
    """Resolve ``{{ paths.key }}`` and ``{{ secrets.key }}`` placeholders in *text*.

    Raises :class:`~cutip.utils.exceptions.CutipError` when a referenced key
    is absent from the corresponding dict.
    """
    def _replace(match: re.Match) -> str:
        namespace = match.group(1)
        key = match.group(2).strip()
        if namespace == "paths":
            if key not in paths:
                raise CutipError(
                    f"'{{{{ paths.{key} }}}}' not found in cutip/paths.yaml"
                )
            return str(paths[key])
        else:  # secrets
            if key not in secrets:
                raise CutipError(
                    f"'{{{{ secrets.{key} }}}}' not found in cutip/secrets.yaml"
                )
            return str(secrets[key])

    return re.sub(r"\{\{\s*(paths|secrets)\.(\w+)\s*\}\}", _replace, text)


def _validate_refs(
    ctx: CutipContext,
    paths: dict,
    secrets: dict,
    generated_keys: frozenset[str] = frozenset(),
) -> None:
    """Validate that every ``{{ paths.key }}`` and ``{{ secrets.key }}``
    referenced in resolved cards is present *and* non-empty.

    *generated_keys* are skipped for paths — their values are resolved and
    created automatically by CUTIP, so they are always valid.

    Called before any lifecycle step so that missing or unfilled entries
    surface as a clear error instead of cryptic backend failures.

    Raises :class:`~cutip.utils.exceptions.CutipError` listing all problems.
    """
    pattern = re.compile(r"\{\{\s*(paths|secrets)\.(\w+)\s*\}\}")
    errors: list[str] = []

    def _check_field(card_name: str, field_name: str, text: str) -> None:
        for namespace, key in pattern.findall(text):
            if namespace == "paths":
                if key in generated_keys:
                    continue  # auto-managed by CUTIP — always valid
                if key not in paths:
                    errors.append(
                        f"  [{card_name}] {field_name}: "
                        f"'{{{{ paths.{key} }}}}' is not defined in cutip/paths.yaml"
                    )
                elif not str(paths[key]).strip():
                    errors.append(
                        f"  [{card_name}] {field_name}: "
                        f"'{{{{ paths.{key} }}}}' is defined but empty in cutip/paths.yaml"
                    )
            else:  # secrets
                if key not in secrets:
                    errors.append(
                        f"  [{card_name}] {field_name}: "
                        f"'{{{{ secrets.{key} }}}}' is not defined in cutip/secrets.yaml"
                    )
                elif not str(secrets[key]).strip():
                    errors.append(
                        f"  [{card_name}] {field_name}: "
                        f"'{{{{ secrets.{key} }}}}' is defined but empty in cutip/secrets.yaml"
                    )

    for card in ctx.resolved_cards.values():
        if not isinstance(card, ContainerCard):
            continue
        name = card.metadata.name
        for mount in card.spec.mounts:
            _check_field(name, "mounts.source", mount.source)
            _check_field(name, "mounts.target", mount.target)
        for env_key, env_val in card.spec.environment.items():
            _check_field(name, f"environment[{env_key!r}]", env_val)

    if errors:
        raise CutipError(
            "Missing or empty values required by your cards:\n"
            + "\n".join(errors)
            + "\n\nFill in the values in cutip/paths.yaml / cutip/secrets.yaml and re-run."
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


def _resolve_refs_in_card(
    card: ContainerCard, paths: dict, secrets: dict,
) -> ContainerCard:
    """Return a copy of *card* with ``{{ paths.key }}`` / ``{{ secrets.key }}``
    resolved in mount paths.

    Only mount ``source`` and ``target`` fields are interpolated.  Other
    string fields (command, workdir, etc.) are not touched.
    """
    if (not paths and not secrets) or not card.spec.mounts:
        return card

    resolved_mounts = []
    for mount in card.spec.mounts:
        resolved_mounts.append(
            mount.model_copy(update={
                "source": _resolve_refs_in_str(mount.source, paths, secrets),
                "target": _resolve_refs_in_str(mount.target, paths, secrets),
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
    paths: dict | None = None,
    secrets: dict | None = None,
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
        paths=paths or {},
        secrets=secrets or {},
    )


# ---------------------------------------------------------------------------
# Lifecycle helpers — called by run() in order
# ---------------------------------------------------------------------------

def _prepare_host_dirs(
    ctx: CutipContext,
    project_root: Path,
    paths: dict | None = None,
    secrets: dict | None = None,
) -> None:
    """Create host-side directories for any mount with ``create_host_path: true``.

    ``{{ paths.key }}`` / ``{{ secrets.key }}`` placeholders in mount sources
    are resolved before the path is created, so declarative YAML mounts with
    user-specific sources work correctly without any Python in the workflow.
    """
    for card in ctx.resolved_cards.values():
        if not isinstance(card, ContainerCard):
            continue
        for mount in card.spec.mounts:
            if not mount.create_host_path:
                continue
            source = mount.source
            if (paths or secrets) and "{{" in source:
                source = _resolve_refs_in_str(source, paths or {}, secrets or {})
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
    ctx: CutipContext, backend, project_root: Path, paths: dict, secrets: dict,
) -> None:
    """Build or pull every ImageCard resolved in the context."""
    # Merge paths + secrets for build-time interpolation ({{ paths.key }} / {{ secrets.key }})
    merged = {**paths, **secrets}
    for card in ctx.resolved_cards.values():
        if not isinstance(card, ImageCard):
            continue
        if card.spec.source == "build":
            logger.info(f"Building image: {card.metadata.name}")
            backend.build_image(card, project_root=project_root, vars=merged)
        elif card.spec.source == "pull":
            logger.info(f"Pulling image: {card.metadata.name}")
            backend.pull_image(card)


def _ensure_networks(ctx: CutipContext, backend) -> None:
    """Create any NetworkCard-backed networks that do not already exist."""
    for card in ctx.resolved_cards.values():
        if isinstance(card, NetworkCard):
            backend.ensure_network(card)


def _provision_containers(
    ctx: CutipContext, backend, paths: dict, secrets: dict,
) -> None:
    """Remove stale containers and create fresh ones with refs resolved."""
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

        # Resolve {{ paths.key }} / {{ secrets.key }} in mount sources / targets
        resolved_card = _resolve_refs_in_card(card, paths, secrets)

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
# Project config helpers
# ---------------------------------------------------------------------------

def _load_project_backend(project_root: Path) -> str | None:
    """Read ``project.backend`` from ``cutip.yaml`` if it exists.

    Returns the backend name (e.g. ``"podman"``, ``"docker"``) or ``None``
    when the file is missing or the field is absent.
    """
    import yaml as _yaml

    config_path = project_root / "cutip.yaml"
    if not config_path.exists():
        return None

    data = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    project = data.get("project") or {}
    backend_val = project.get("backend")
    if backend_val is not None:
        return str(backend_val).lower()
    return None


def _save_project_backend(project_root: Path, backend_name: str) -> None:
    """Write ``project.backend`` to ``cutip.yaml``."""
    import yaml as _yaml

    config_path = project_root / "cutip.yaml"
    if not config_path.exists():
        return

    data = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if "project" not in data:
        data["project"] = {}
    data["project"]["backend"] = backend_name

    with config_path.open("w", encoding="utf-8") as fh:
        _yaml.dump(data, fh, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------

def run(
    group_name: str = typer.Argument(
        ...,
        help="Name of the group to run",
        autocompletion=_complete_group_name,
    ),
    backend: str = typer.Option(
        None,
        "--backend",
        "-b",
        envvar="CUTIP_BACKEND",
        help="Container backend to use (docker or podman). "
             "Defaults to project.backend in cutip.yaml, then docker.",
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
    """Run a group's workflow.

    CUTIP handles the container lifecycle up to creation; workflow.main(ctx)
    is responsible for starting containers and orchestrating across units.

    \b
      1. Load cutip/paths.yaml + cutip/secrets.yaml
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

    try:
        group_name = _resolve_group_name(group_name, registry)
    except CutipError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    # Validate first
    result = GraphValidator(registry, project_root=project_root).validate()
    if not result.ok:
        for err in result.errors:
            console.print(f"[red]{err}[/red]")
        console.print("[bold red]Validation failed. Fix errors before running.[/bold red]")
        raise typer.Exit(1)

    # Honour env-var shortcut in addition to the CLI flag
    is_local = local or os.environ.get("CUTIP_LOCAL", "").lower() in ("1", "true", "yes")

    # Resolve backend: -b / CUTIP_BACKEND → cutip.yaml → docker
    backend_name = (
        backend.lower() if backend
        else _load_project_backend(project_root)
        or "docker"
    )
    logger.debug(f"Using backend: {backend_name}")

    # Connect backend
    try:
        from cutip.backends import get_backend
        _backend = get_backend(backend_name, local=is_local)
    except CutipError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    started_at = iso_now()
    status = "failure"
    run_error: str | None = None

    project_paths, generated_keys = _load_paths(project_root)
    project_secrets = _load_secrets(project_root)

    # Create generated directories before any lifecycle step so they exist
    # when create_host_path mounts try to create sub-directories inside them.
    _prepare_generated_dirs(project_paths, generated_keys)

    try:
        with run_lock(cutip_dir / "locks", group_name):
            ctx = _build_context(
                group_name, project_root, registry,
                runtime=_backend.client,
                paths=project_paths,
                secrets=project_secrets,
            )

            # Validate all {{ paths.X }} / {{ secrets.X }} references
            # (generated keys are auto-managed and always valid — skip them)
            _validate_refs(ctx, project_paths, project_secrets, generated_keys)

            # Steps 1–2: host dirs + named volumes
            _prepare_host_dirs(ctx, project_root, paths=project_paths, secrets=project_secrets)
            _prepare_volumes(ctx, _backend.client)

            # Step 3: per-unit pre_build hooks (stage build-context files)
            _run_unit_pre_builds(ctx, registry, project_root)

            # Steps 4–6: images → networks → create containers (no auto-start)
            _build_and_pull_images(ctx, _backend, project_root, project_paths, project_secrets)
            _ensure_networks(ctx, _backend)
            _provision_containers(ctx, _backend, project_paths, project_secrets)

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
    else:
        # Prompt to save backend as default if user explicitly passed -b
        # and it differs from the currently configured default.
        # Skip when stdin is not a TTY (CI, pipes, etc.).
        if backend and status == "success" and sys.stdin.isatty():
            configured = _load_project_backend(project_root)
            if configured != backend_name:
                save = typer.confirm(
                    f"Use '{backend_name}' as the default backend in cutip.yaml?",
                    default=False,
                )
                if save:
                    _save_project_backend(project_root, backend_name)
                    console.print(
                        f"[green]Default backend set to '{backend_name}' in cutip.yaml[/green]"
                    )
    finally:
        write_run_record(
            cutip_dir / "runs",
            group=group_name,
            backend=backend_name,
            started_at=started_at,
            status=status,
            error=run_error,
        )
        _backend.disconnect()
