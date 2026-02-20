from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

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
    networkRef: Ref
    command: str | None = None
    hostname: str | None = None
    privileged: bool = False
    ports: dict[str, str] = {}
    environment: dict[str, str] = {}
    mounts: list[MountSpec] = []
    volumes: dict[str, str] = {}
    cap_add: list[str] = []
    security_opts: list[str] = []
    restart_policy: str | None = None


class ContainerCard(CutipBaseModel):
    kind: Literal["ContainerCard"] = "ContainerCard"
    spec: ContainerSpec
