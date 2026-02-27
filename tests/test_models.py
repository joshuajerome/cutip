"""Tests for CUTIP Pydantic models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.group import Group
from cutip.models.unit import Unit
from cutip.utils.yaml_loader import load_yaml_file, parse_artifact

FIXTURES = Path(__file__).parent / "fixtures"


def test_image_card_pull():
    raw = load_yaml_file(FIXTURES / "image_card.yaml")
    card = parse_artifact(raw)
    assert isinstance(card, ImageCard)
    assert card.name == "test-image"
    assert card.spec.source == "pull"
    assert card.spec.image == "ubuntu"


def test_network_card():
    raw = load_yaml_file(FIXTURES / "network_card.yaml")
    card = parse_artifact(raw)
    assert isinstance(card, NetworkCard)
    assert card.name == "test-network"
    assert card.spec.subnet == "10.89.0.0/16"
    assert card.spec.gateway == "10.89.0.1"


def test_container_card():
    raw = load_yaml_file(FIXTURES / "container_card.yaml")
    card = parse_artifact(raw)
    assert isinstance(card, ContainerCard)
    assert card.name == "test-container"
    assert card.spec.imageRef.ref == "images/test-image"
    assert card.spec.networkRef.ref == "networks/test-network"


def test_wrong_api_version_raises():
    with pytest.raises(ValidationError):
        ImageCard.model_validate(
            {
                "apiVersion": "v1",  # wrong
                "kind": "ImageCard",
                "metadata": {"name": "bad"},
                "spec": {"source": "pull", "image": "ubuntu"},
            }
        )


def test_image_card_pull_requires_image():
    with pytest.raises(ValidationError):
        ImageCard.model_validate(
            {
                "apiVersion": "cutip/v1",
                "kind": "ImageCard",
                "metadata": {"name": "bad"},
                "spec": {"source": "pull"},  # missing image
            }
        )


def test_image_card_build_requires_context():
    with pytest.raises(ValidationError):
        ImageCard.model_validate(
            {
                "apiVersion": "cutip/v1",
                "kind": "ImageCard",
                "metadata": {"name": "bad"},
                "spec": {"source": "build"},  # missing context
            }
        )


def test_network_card_invalid_subnet():
    with pytest.raises(ValidationError):
        NetworkCard.model_validate(
            {
                "apiVersion": "cutip/v1",
                "kind": "NetworkCard",
                "metadata": {"name": "bad"},
                "spec": {"subnet": "not-a-cidr"},
            }
        )


def test_network_card_gateway_outside_subnet():
    with pytest.raises(ValidationError):
        NetworkCard.model_validate(
            {
                "apiVersion": "cutip/v1",
                "kind": "NetworkCard",
                "metadata": {"name": "bad"},
                "spec": {"subnet": "10.89.0.0/16", "gateway": "192.168.1.1"},
            }
        )


def test_unit_model():
    unit = Unit.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "Unit",
            "metadata": {"name": "my-unit"},
            "spec": {"containerRef": {"ref": "containers/my-container"}},
        }
    )
    assert unit.name == "my-unit"
    assert unit.spec.containerRef.ref == "containers/my-container"


def test_group_model():
    group = Group.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "Group",
            "metadata": {"name": "my-group"},
            "spec": {
                "units": [{"ref": "units/my-unit"}],
                "workflow": "workflow.py",
            },
        }
    )
    assert group.name == "my-group"
    assert group.spec.units[0].ref == "units/my-unit"
    assert group.spec.workflow == "workflow.py"
