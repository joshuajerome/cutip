from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from cutip.models.base import CutipBaseModel


class ImageSpec(BaseModel):
    source: Literal["pull", "build"]
    image: str | None = None
    tag: str = "latest"
    context: str | None = None
    dockerfile: str = "Dockerfile"
    build_args: dict[str, str] = {}

    @model_validator(mode="after")
    def _validate_source_fields(self) -> "ImageSpec":
        if self.source == "pull" and not self.image:
            raise ValueError("'image' is required when source is 'pull'")
        if self.source == "build" and not self.context:
            raise ValueError("'context' is required when source is 'build'")
        return self


class ImageCard(CutipBaseModel):
    kind: Literal["ImageCard"] = "ImageCard"
    spec: ImageSpec
