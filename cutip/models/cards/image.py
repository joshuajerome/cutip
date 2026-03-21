from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from cutip.models.base import CutipBaseModel


class BuildtimeResource(BaseModel):
    """A file or directory to stage into the build context before `podman/docker build`.

    Mirrors podwrap's ``buildtime_resources`` pattern: extra files are copied
    into a staging directory (``buildtime_dir``) alongside the Dockerfile so the
    build context includes them without polluting the source tree.

    Attributes:
        src:  Path to the source file or directory (relative to project root, or absolute).
        dest: Destination name inside the staging directory.
              Defaults to the basename of ``src`` if omitted.
    """

    src: str
    dest: str | None = None

    @model_validator(mode="after")
    def _default_dest(self) -> BuildtimeResource:
        if not self.dest:
            # Use the last path component as the destination name
            from pathlib import Path

            object.__setattr__(self, "dest", Path(self.src).name)
        return self


class ImageSpec(BaseModel):
    # ── Common ────────────────────────────────────────────────────────────────
    source: Literal["pull", "build"]
    tag: str = "latest"

    # ── Pull-mode fields ──────────────────────────────────────────────────────
    # Full registry path, e.g. "docker.io/library/alpine" or
    # "ghcr.io/my-org/my-image".  Required when source is "pull".
    image: str | None = None

    # ── Build-mode fields ─────────────────────────────────────────────────────
    # Directory containing the Dockerfile (relative to project root, or absolute).
    # Required when source is "build".
    context: str | None = None

    # Dockerfile filename relative to context (defaults to "Dockerfile").
    dockerfile: str = "Dockerfile"

    # Build-time --build-arg values.
    build_args: dict[str, str] = {}

    # Extra files/directories to copy into the staging dir before building.
    # Mirrors podwrap's buildtime_resources: files listed here are copied into
    # buildtime_dir so the Dockerfile can reference them via COPY instructions.
    #
    # Example:
    #   buildtime_resources:
    #     - src: containers/resources/requirements.txt
    #     - src: containers/resources/settings.json
    #       dest: vscode-settings.json          # rename on the way in
    #     - src: containers/scripts/             # directories are copied recursively
    buildtime_resources: list[BuildtimeResource] = []

    # Directory where buildtime_resources are staged before the build.
    # Defaults to "{context}/buildtime" if not set.
    buildtime_dir: str | None = None

    # Network mode for the build (e.g. "host", "none", "default").
    # Maps to --network flag on docker/podman build.
    # If not set, the builder's default network is used.
    network_mode: str | None = None

    @model_validator(mode="after")
    def _validate_source_fields(self) -> ImageSpec:
        if self.source == "pull":
            if not self.image:
                raise ValueError("'image' is required when source is 'pull'")
            if self.buildtime_resources:
                raise ValueError("'buildtime_resources' is only valid when source is 'build'")
        if self.source == "build" and not self.context:
            raise ValueError("'context' is required when source is 'build'")
        return self


class ImageCard(CutipBaseModel):
    kind: Literal["ImageCard"] = "ImageCard"
    spec: ImageSpec
