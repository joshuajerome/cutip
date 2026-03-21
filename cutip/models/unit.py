from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from cutip.models.base import CutipBaseModel
from cutip.models.cards.container import Ref


class HookSpec(BaseModel):
    prehook: str | None = None
    posthook: str | None = None


class UnitSpec(BaseModel):
    containerRef: Ref
    hooks: HookSpec = HookSpec()


class Unit(CutipBaseModel):
    kind: Literal["Unit"] = "Unit"
    spec: UnitSpec
