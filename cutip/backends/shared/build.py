"""Build-time resource staging helper shared by all backends.

Mirrors the podwrap ``ImageBuilder._stage_resources`` pattern: before running
``podman/docker build``, any ``buildtime_resources`` declared on the ImageCard
are copied into a staging directory inside the build context so the Dockerfile
can reference them with ``COPY`` instructions.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger

from cutip.utils.exceptions import CutipError


def stage_buildtime_resources(
    card,                          # ImageCard — avoid circular import at module level
    project_root: Path | None,
) -> Path:
    """Copy buildtime_resources into the staging directory and return it.

    Args:
        card:         An :class:`~cutip.models.cards.image.ImageCard` with
                      ``spec.source == "build"``.
        project_root: Project root used to resolve relative paths.  Defaults
                      to the current working directory when *None*.

    Returns:
        The staging directory path (``card.spec.buildtime_dir`` or the default
        ``{context}/buildtime``).

    Raises:
        CutipError: If ``context`` is missing or a resource path does not exist.
    """
    root = project_root or Path.cwd()

    ctx_path = card.spec.context
    if not ctx_path:
        raise CutipError(
            f"ImageCard '{card.metadata.name}': 'context' is required for source='build'"
        )
    context = Path(ctx_path)
    if not context.is_absolute():
        context = root / context

    # Resolve staging directory
    if card.spec.buildtime_dir:
        staging = Path(card.spec.buildtime_dir)
        if not staging.is_absolute():
            staging = root / staging
    else:
        staging = context / "buildtime"

    if not card.spec.buildtime_resources:
        return staging  # nothing to stage

    staging.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Staging buildtime resources into {staging}")

    for resource in card.spec.buildtime_resources:
        src_path = Path(resource.src)
        if not src_path.is_absolute():
            src_path = root / src_path

        if not src_path.exists():
            raise CutipError(
                f"ImageCard '{card.metadata.name}': buildtime resource not found: {src_path}"
            )

        dest_name = resource.dest or src_path.name
        dest_path = staging / dest_name

        if src_path.is_dir():
            if dest_path.exists():
                shutil.rmtree(dest_path)
            shutil.copytree(src_path, dest_path)
            logger.debug(f"  staged dir  {src_path} -> {dest_path}")
        else:
            shutil.copy2(src_path, dest_path)
            logger.debug(f"  staged file {src_path} -> {dest_path}")

    return staging
