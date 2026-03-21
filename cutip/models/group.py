from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from cutip.models.base import CutipBaseModel
from cutip.models.cards.container import Ref


class GroupSpec(BaseModel):
    units: list[Ref]
    workflow: str = "workflow.py"
    orchestrator: str = "orchestrator.py"


class Group(CutipBaseModel):
    kind: Literal["Group"] = "Group"
    spec: GroupSpec
