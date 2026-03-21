"""Tests for the Docker backend (all mocked — no real Docker daemon needed)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cutip.utils.exceptions import CutipError

# ── Connection tests ─────────────────────────────────────────────────────────


def test_connect_success():
    mock_client = MagicMock()
    mock_client.ping.return_value = True

    with patch(
        "cutip.backends.docker.backend.connect_docker_client",
        return_value=mock_client,
    ):
        from cutip.backends.docker.backend import DockerBackend

        backend = DockerBackend.connect()
        assert backend.client is mock_client


def test_connect_import_error():
    with patch(
        "cutip.backends.docker.backend.connect_docker_client",
        side_effect=CutipError("The 'docker' package is required"),
    ):
        from cutip.backends.docker.backend import DockerBackend

        with pytest.raises(CutipError, match=r"docker.*package"):
            DockerBackend.connect()


def test_connect_daemon_error():
    with patch(
        "cutip.backends.docker.backend.connect_docker_client",
        side_effect=CutipError("Could not connect to the Docker daemon"),
    ):
        from cutip.backends.docker.backend import DockerBackend

        with pytest.raises(CutipError, match="Could not connect"):
            DockerBackend.connect()


# ── Image tests ──────────────────────────────────────────────────────────────


def _make_backend(mock_client=None):
    from cutip.backends.docker.backend import DockerBackend

    client = mock_client or MagicMock()
    backend = DockerBackend.__new__(DockerBackend)
    backend._client = client
    return backend


def _make_image_card(name="hello", image="docker.io/library/alpine", tag="3.20", source="pull"):
    from cutip.models.cards.image import ImageCard

    return ImageCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "ImageCard",
            "metadata": {"name": name},
            "spec": {
                "source": source,
                "image": image,
                "tag": tag,
            },
        }
    )


def test_pull_image_skip_existing():
    mock_img = MagicMock()
    mock_img.tags = ["hello:3.20"]
    client = MagicMock()
    client.images.list.return_value = [mock_img]

    backend = _make_backend(client)
    card = _make_image_card()
    backend.pull_image(card)

    client.images.pull.assert_not_called()


def test_pull_image_new():
    client = MagicMock()
    client.images.list.return_value = []
    pulled_img = MagicMock()
    client.images.pull.return_value = pulled_img

    backend = _make_backend(client)
    card = _make_image_card()
    backend.pull_image(card)

    client.images.pull.assert_called_once_with("docker.io/library/alpine", tag="3.20")
    pulled_img.tag.assert_called_once_with("hello:3.20")


# ── Network tests ────────────────────────────────────────────────────────────


def _make_network_card(name="test-net", subnet="10.89.0.0/16", gateway="10.89.0.1"):
    from cutip.models.cards.network import NetworkCard

    return NetworkCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "NetworkCard",
            "metadata": {"name": name},
            "spec": {"subnet": subnet, "gateway": gateway},
        }
    )


def test_ensure_network_exists():
    client = MagicMock()
    client.networks.get.return_value = MagicMock()

    backend = _make_backend(client)
    card = _make_network_card()
    backend.ensure_network(card)

    client.networks.create.assert_not_called()


def test_ensure_network_create():
    client = MagicMock()
    client.networks.get.side_effect = Exception("not found")

    backend = _make_backend(client)
    card = _make_network_card()

    # Mock docker.types inside the ensure_network method
    mock_types = MagicMock()
    with patch.dict("sys.modules", {"docker": MagicMock(), "docker.types": mock_types}):
        backend.ensure_network(card)

    client.networks.create.assert_called_once()
    call_args = client.networks.create.call_args
    assert call_args[0][0] == "test-net"


# ── Container tests ──────────────────────────────────────────────────────────


def test_create_container_no_wsl_translation():
    """Docker backend should NOT translate Windows paths (Docker Desktop handles them)."""
    from cutip.models.cards.container import ContainerCard

    card = ContainerCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "ContainerCard",
            "metadata": {"name": "test-ctr"},
            "spec": {
                "imageRef": {"ref": "images/hello"},
                "network_mode": "bridge",
                "mounts": [
                    {
                        "type": "bind",
                        "source": "C:/Users/foo/data",
                        "target": "/data",
                    }
                ],
            },
        }
    )

    client = MagicMock()
    client.containers.get.side_effect = Exception("not found")

    backend = _make_backend(client)
    backend.create_container(card, image_name="hello:3.20")

    call_kwargs = client.containers.create.call_args[1]
    mounts = call_kwargs["mounts"]
    # Source must remain as-is — no /mnt/c/ translation
    assert mounts[0]["source"] == "C:/Users/foo/data"


def test_build_image_uses_docker_cli():
    from cutip.models.cards.image import ImageCard

    card = ImageCard.model_validate(
        {
            "apiVersion": "cutip/v1",
            "kind": "ImageCard",
            "metadata": {"name": "myimg"},
            "spec": {
                "source": "build",
                "image": "myimg",
                "tag": "latest",
                "context": "/tmp/ctx",
                "dockerfile": "Dockerfile",
            },
        }
    )

    backend = _make_backend()

    with patch("cutip.backends.docker.backend.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        with patch("cutip.backends.docker.backend.stage_buildtime_resources") as mock_stage:
            mock_stage.return_value = "/tmp/ctx"
            backend.build_image(card)

        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "docker"
        assert cmd[1] == "build"


def test_disconnect():
    client = MagicMock()
    backend = _make_backend(client)
    backend.disconnect()
    client.close.assert_called_once()
