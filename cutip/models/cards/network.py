from __future__ import annotations

import ipaddress
from typing import Literal

from pydantic import BaseModel, model_validator

from cutip.models.base import CutipBaseModel


class NetworkSpec(BaseModel):
    driver: str = "bridge"
    subnet: str
    gateway: str | None = None

    @model_validator(mode="after")
    def _validate_network(self) -> NetworkSpec:
        try:
            network = ipaddress.IPv4Network(self.subnet, strict=False)
        except ValueError as exc:
            raise ValueError(f"'subnet' is not a valid CIDR: {self.subnet}") from exc

        if self.gateway is not None:
            try:
                gw = ipaddress.IPv4Address(self.gateway)
            except ValueError as exc:
                raise ValueError(f"'gateway' is not a valid IPv4 address: {self.gateway}") from exc
            if gw not in network:
                raise ValueError(f"'gateway' {self.gateway} is not within subnet {self.subnet}")
        return self


class NetworkCard(CutipBaseModel):
    kind: Literal["NetworkCard"] = "NetworkCard"
    spec: NetworkSpec
