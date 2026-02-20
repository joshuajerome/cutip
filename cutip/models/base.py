from __future__ import annotations

from pydantic import BaseModel, field_validator


class CutipMetadata(BaseModel):
    name: str
    labels: dict[str, str] = {}


class CutipBaseModel(BaseModel):
    apiVersion: str
    kind: str
    metadata: CutipMetadata

    @field_validator("apiVersion")
    @classmethod
    def _check_api_version(cls, v: str) -> str:
        if v != "cutip/v1":
            raise ValueError(f"apiVersion must be 'cutip/v1', got '{v}'")
        return v

    @property
    def name(self) -> str:
        return self.metadata.name
