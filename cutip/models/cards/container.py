from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from cutip.models.base import CutipBaseModel


class Ref(BaseModel):
    ref: str


class MountSpec(BaseModel):
    type: Literal["bind", "volume"]
    source: str
    target: str
    read_only: bool = False


class ContainerSpec(BaseModel):
    imageRef: Ref
    # Network: exactly one of networkRef (bridge to a named NetworkCard) or
    # network_mode (e.g. "host", "none", "slirp4netns") must be provided.
    networkRef: Ref | None = None
    network_mode: str | None = None
    command: str | None = None
    hostname: str | None = None
    workdir: str | None = None
    privileged: bool = False
    ports: dict[str, str] = {}
    environment: dict[str, str] = {}
    mounts: list[MountSpec] = []
    # Named volumes: {volume_name: container_path}  e.g. {"node_modules": "/app/node_modules"}
    volumes: dict[str, str] = {}
    cap_add: list[str] = []
    security_opts: list[str] = []
    restart_policy: str | None = None

    @model_validator(mode="after")
    def _validate_network(self) -> "ContainerSpec":
        if self.networkRef is None and self.network_mode is None:
            raise ValueError(
                "Either 'networkRef' (bridge to a named NetworkCard) "
                "or 'network_mode' (e.g. 'host') must be provided"
            )
        if self.networkRef is not None and self.network_mode is not None:
            raise ValueError(
                "Only one of 'networkRef' or 'network_mode' may be provided, not both"
            )
        return self


class ContainerCard(CutipBaseModel):
    kind: Literal["ContainerCard"] = "ContainerCard"
    spec: ContainerSpec
