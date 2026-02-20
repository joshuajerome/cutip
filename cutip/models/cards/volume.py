from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from cutip.models.base import CutipBaseModel


class VolumeSpec(BaseModel):
    driver: str = "local"
    labels: dict[str, str] = {}
    options: dict[str, str] = {}


class VolumeCard(CutipBaseModel):
    kind: Literal["VolumeCard"] = "VolumeCard"
    spec: VolumeSpec
