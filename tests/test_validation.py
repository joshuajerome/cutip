"""Tests for the graph validator."""

from pathlib import Path
import tempfile

import pytest

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.group import Group
from cutip.models.unit import Unit
from cutip.validation.graph import GraphValidator
from cutip.workspace.registry import CutipRegistry


def _full_registry(include_workflow: bool = True) -> tuple[CutipRegistry, Path]:
    tmpdir = Path(tempfile.mkdtemp())
    workflow = tmpdir / "workflow.py"
    if include_workflow:
        workflow.write_text("def main(ctx): pass\n")

    registry = CutipRegistry()

    image = ImageCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "ImageCard",
            "metadata": {"name": "img"},
            "spec": {"source": "pull", "image": "ubuntu"},
        }
    )
    network = NetworkCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "NetworkCard",
            "metadata": {"name": "net"},
            "spec": {"subnet": "10.0.0.0/16"},
        }
    )
    container = ContainerCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "ContainerCard",
            "metadata": {"name": "ctr"},
            "spec": {
                "imageRef": {"ref": "images/img"},
                "networkRef": {"ref": "networks/net"},
            },
        }
    )
    unit = Unit.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "Unit",
            "metadata": {"name": "u"},
            "spec": {"containerRef": {"ref": "containers/ctr"}},
        }
    )
    group_yaml = tmpdir / "group.yaml"
    group_yaml.write_text("")
    group = Group.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "Group",
            "metadata": {"name": "g"},
            "spec": {"units": [{"ref": "units/u"}], "workflow": "workflow.py"},
        }
    )

    registry.register(image)
    registry.register(network)
    registry.register(container)
    registry.register(unit)
    registry.register(group, source=group_yaml)
    return registry, tmpdir


def test_valid_graph_passes():
    registry, _ = _full_registry()
    result = GraphValidator(registry).validate()
    assert result.ok
    assert result.errors == []


def test_missing_container_ref_fails():
    registry, _ = _full_registry()
    unit = Unit.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "Unit",
            "metadata": {"name": "bad-unit"},
            "spec": {"containerRef": {"ref": "containers/nonexistent"}},
        }
    )
    registry.register(unit)
    result = GraphValidator(registry).validate()
    assert not result.ok
    assert any("bad-unit" in e for e in result.errors)


def test_missing_workflow_fails():
    registry, _ = _full_registry(include_workflow=False)
    result = GraphValidator(registry).validate()
    assert not result.ok
    assert any("WorkflowPath" in e for e in result.errors)


def test_missing_unit_in_group_fails():
    registry, tmpdir = _full_registry()
    group_yaml = tmpdir / "group2.yaml"
    group_yaml.write_text("")
    group2 = Group.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "Group",
            "metadata": {"name": "g2"},
            "spec": {
                "units": [{"ref": "units/nonexistent"}],
                "workflow": "workflow.py",
            },
        }
    )
    registry.register(group2, source=group_yaml)
    result = GraphValidator(registry).validate()
    assert not result.ok
    assert any("g2" in e for e in result.errors)
