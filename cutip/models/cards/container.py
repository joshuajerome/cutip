from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from cutip.models.base import CutipBaseModel


class Ref(BaseModel):
    ref: str


class MountSpec(BaseModel):
    """A bind-mount inside the container.

    Attributes:
        type:              Mount type -- "bind" (host path) or "volume" (named volume).
        source:            Host filesystem path (bind) or volume name (volume).
                           Relative paths are resolved against the project root at runtime.
        target:            Absolute path inside the container.
        read_only:         Mount as read-only (default False).
        create_host_path:  When True, CUTIP creates the host directory before the
                           workflow runs -- mirroring the podwrap pattern of pre-creating
                           bind-mount source dirs (e.g. data dirs, sheet dirs) so the
                           container starts without a missing-source error.
                           Only meaningful for type "bind".
    """

    type: Literal["bind", "volume"]
    source: str
    target: str
    read_only: bool = False
    create_host_path: bool = False


class ContainerSpec(BaseModel):
    # -- Image -----------------------------------------------------------------
    imageRef: Ref

    # -- Network ---------------------------------------------------------------
    # Exactly one of networkRef (bridge to a named NetworkCard) or
    # network_mode (e.g. "host", "none", "bridge", "slirp4netns") must be given.
    networkRef: Ref | None = None
    network_mode: str | None = None

    # -- Process ---------------------------------------------------------------
    command: str | None = None
    hostname: str | None = None
    workdir: str | None = None

    # -- Privileges ------------------------------------------------------------
    privileged: bool = False
    cap_add: list[str] = []
    security_opts: list[str] = []

    # -- Ports -----------------------------------------------------------------
    ports: dict[str, str] = {}

    # -- Environment variables -------------------------------------------------
    environment: dict[str, str] = {}

    # -- Bind mounts -----------------------------------------------------------
    mounts: list[MountSpec] = []

    # -- Named volumes ---------------------------------------------------------
    volumes: dict[str, str] = {}

    # -- Labels ----------------------------------------------------------------
    labels: dict[str, str] = {}

    # -- Restart policy --------------------------------------------------------
    restart_policy: str | None = None

    @model_validator(mode="after")
    def _validate_network(self) -> "ContainerSpec":
        if self.networkRef is None and self.network_mode is None:
            raise ValueError(
                "Either 'networkRef' (bridge to a named NetworkCard) "
                "or 'network_mode' (e.g. 'bridge', 'host') must be provided"
            )
        if self.networkRef is not None and self.network_mode is not None:
            raise ValueError(
                "Only one of 'networkRef' or 'network_mode' may be provided, not both"
            )
        return self


class ContainerCard(CutipBaseModel):
    kind: Literal["ContainerCard"] = "ContainerCard"
    spec: ContainerSpec
