"""Docker execution backend (stub).

Full implementation is future work. Install the optional extra:
    uv add docker
"""

from __future__ import annotations

from cutip.backends.base import CutipBackend
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.cards.volume import VolumeCard
from cutip.utils.exceptions import CutipError


class DockerBackend(CutipBackend):
    """Docker backend stub — satisfies the CutipBackend interface."""

    def __init__(self) -> None:
        try:
            import docker
            self._client = docker.from_env()
        except ImportError as exc:
            raise CutipError(
                "The 'docker' package is required for the Docker backend. "
                "Run: uv add docker"
            ) from exc

    @classmethod
    def connect(cls) -> "DockerBackend":
        return cls()

    def pull_image(self, card: ImageCard) -> None:
        raise NotImplementedError("DockerBackend.pull_image is not yet implemented")

    def build_image(self, card: ImageCard) -> None:
        raise NotImplementedError("DockerBackend.build_image is not yet implemented")

    def ensure_network(self, card: NetworkCard) -> None:
        raise NotImplementedError("DockerBackend.ensure_network is not yet implemented")

    def ensure_volume(self, card: VolumeCard) -> None:
        raise NotImplementedError("DockerBackend.ensure_volume is not yet implemented")

    def create_container(self, card: ContainerCard) -> str:
        raise NotImplementedError("DockerBackend.create_container is not yet implemented")

    def start_container(self, name: str) -> None:
        raise NotImplementedError("DockerBackend.start_container is not yet implemented")

    def stop_container(self, name: str) -> None:
        raise NotImplementedError("DockerBackend.stop_container is not yet implemented")

    def remove_container(self, name: str) -> None:
        raise NotImplementedError("DockerBackend.remove_container is not yet implemented")

    def container_status(self, name: str) -> str:
        raise NotImplementedError("DockerBackend.container_status is not yet implemented")
