from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.cards.volume import VolumeCard
from cutip.models.unit import Unit
from cutip.utils.exceptions import CutipRefError

if TYPE_CHECKING:
    from cutip.models.base import CutipBaseModel
    from cutip.workspace.registry import CutipRegistry

T = TypeVar("T", bound="CutipBaseModel")

# Maps ref prefix → expected model class
_PREFIX_TO_KIND: dict[str, type] = {
    "images": ImageCard,
    "containers": ContainerCard,
    "networks": NetworkCard,
    "volumes": VolumeCard,
    "units": Unit,
}


def _parse_ref(ref: str) -> tuple[str, str]:
    """Split 'prefix/name' into (prefix, name). Raises CutipRefError on bad format."""
    parts = ref.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise CutipRefError(ref, "ref must be in the format '<kind>/<name>'")
    return parts[0], parts[1]


class RefResolver:
    """Resolves ref strings against a CutipRegistry."""

    def __init__(self, registry: "CutipRegistry") -> None:
        self.registry = registry

    def resolve(self, ref: str) -> "CutipBaseModel":
        """Resolve any ref string to its artifact. Raises CutipRefError if not found."""
        prefix, name = _parse_ref(ref)

        if prefix == "units":
            artifact = self.registry.get_unit(name)
            if artifact is None:
                raise CutipRefError(ref, f"Unit '{name}' not found in registry")
            return artifact

        expected_cls = _PREFIX_TO_KIND.get(prefix)
        if expected_cls is None:
            known = ", ".join(_PREFIX_TO_KIND)
            raise CutipRefError(ref, f"Unknown ref prefix '{prefix}'. Known: {known}")

        artifact = self.registry.get_card(ref)
        if artifact is None:
            raise CutipRefError(ref, f"Card '{ref}' not found in registry")

        if not isinstance(artifact, expected_cls):
            raise CutipRefError(
                ref,
                f"Expected {expected_cls.__name__} but found {type(artifact).__name__}",
            )
        return artifact

    def resolve_card(self, ref: str, expected_cls: type[T]) -> T:
        """Resolve a card ref, enforcing a specific model type."""
        artifact = self.resolve(ref)
        if not isinstance(artifact, expected_cls):
            raise CutipRefError(
                ref,
                f"Expected {expected_cls.__name__} but found {type(artifact).__name__}",
            )
        return artifact  # type: ignore[return-value]

    def resolve_unit(self, ref: str) -> Unit:
        """Resolve a unit ref string."""
        prefix, name = _parse_ref(ref)
        if prefix != "units":
            raise CutipRefError(ref, f"Expected a 'units/' ref, got prefix '{prefix}'")
        unit = self.registry.get_unit(name)
        if unit is None:
            raise CutipRefError(ref, f"Unit '{name}' not found in registry")
        return unit
