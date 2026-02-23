from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from cutip.models.base import CutipBaseModel
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.group import Group
from cutip.models.unit import Unit
from cutip.utils.exceptions import CutipParseError

_KIND_MAP: dict[str, type[CutipBaseModel]] = {
    "ImageCard": ImageCard,
    "ContainerCard": ContainerCard,
    "NetworkCard": NetworkCard,
    "Unit": Unit,
    "Group": Group,
}

_KIND_PREFIX: dict[str, str] = {
    "ImageCard": "images",
    "ContainerCard": "containers",
    "NetworkCard": "networks",
    "Unit": "units",
    "Group": "groups",
}


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Read a YAML file and return its contents as a dict."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise CutipParseError(str(path), f"YAML syntax error: {exc}") from exc

    if not isinstance(data, dict):
        raise CutipParseError(str(path), "Expected a YAML mapping at the top level")
    return data


def parse_artifact(raw: dict[str, Any], source_path: str = "<unknown>") -> CutipBaseModel:
    """Dispatch a raw YAML dict to the correct Pydantic model by 'kind'."""
    kind = raw.get("kind")
    if not kind:
        raise CutipParseError(source_path, "Missing required field 'kind'")

    model_cls = _KIND_MAP.get(kind)
    if model_cls is None:
        known = ", ".join(_KIND_MAP)
        raise CutipParseError(source_path, f"Unknown kind '{kind}'. Known kinds: {known}")

    try:
        return model_cls.model_validate(raw)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise CutipParseError(source_path, errors) from exc


def kind_prefix(kind: str) -> str:
    """Return the registry prefix for a given kind string (e.g. 'ContainerCard' → 'containers')."""
    return _KIND_PREFIX.get(kind, kind.lower() + "s")
