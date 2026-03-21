"""Tests for the ref resolver."""

import pytest

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.unit import Unit
from cutip.resolver.refs import RefResolver
from cutip.utils.exceptions import CutipRefError
from cutip.workspace.registry import CutipRegistry


def _make_registry() -> CutipRegistry:
    registry = CutipRegistry()

    image = ImageCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "ImageCard",
            "metadata": {"name": "my-image"},
            "spec": {"source": "pull", "image": "ubuntu", "tag": "22.04"},
        }
    )
    network = NetworkCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "NetworkCard",
            "metadata": {"name": "my-network"},
            "spec": {"subnet": "10.89.0.0/16", "gateway": "10.89.0.1"},
        }
    )
    container = ContainerCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "ContainerCard",
            "metadata": {"name": "my-container"},
            "spec": {
                "imageRef": {"ref": "images/my-image"},
                "networkRef": {"ref": "networks/my-network"},
            },
        }
    )
    unit = Unit.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "Unit",
            "metadata": {"name": "my-unit"},
            "spec": {"containerRef": {"ref": "containers/my-container"}},
        }
    )

    registry.register(image)
    registry.register(network)
    registry.register(container)
    registry.register(unit)
    return registry


def test_resolve_image():
    r = RefResolver(_make_registry())
    card = r.resolve("images/my-image")
    assert isinstance(card, ImageCard)
    assert card.name == "my-image"


def test_resolve_container():
    r = RefResolver(_make_registry())
    card = r.resolve_card("containers/my-container", ContainerCard)
    assert isinstance(card, ContainerCard)


def test_resolve_unit():
    r = RefResolver(_make_registry())
    unit = r.resolve_unit("units/my-unit")
    assert isinstance(unit, Unit)
    assert unit.name == "my-unit"


def test_resolve_missing_raises():
    r = RefResolver(_make_registry())
    with pytest.raises(CutipRefError):
        r.resolve("images/does-not-exist")


def test_resolve_bad_format_raises():
    r = RefResolver(_make_registry())
    with pytest.raises(CutipRefError):
        r.resolve("badformat")


def test_resolve_unknown_prefix_raises():
    r = RefResolver(_make_registry())
    with pytest.raises(CutipRefError):
        r.resolve("foobar/my-thing")
