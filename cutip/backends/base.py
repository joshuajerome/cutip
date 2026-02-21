from __future__ import annotations

from abc import ABC, abstractmethod

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.cards.volume import VolumeCard


class CutipBackend(ABC):
    """Abstract interface for CUTIP execution backends (Podman, Docker, etc.)."""

    @abstractmethod
    def pull_image(self, card: ImageCard) -> None:
        """Pull an image from a registry."""

    @abstractmethod
    def build_image(self, card: ImageCard) -> None:
        """Build an image from a local Dockerfile context."""

    @abstractmethod
    def ensure_network(self, card: NetworkCard) -> None:
        """Create a network if it does not already exist."""

    @abstractmethod
    def ensure_volume(self, card: VolumeCard) -> None:
        """Create a named volume if it does not already exist."""

    @abstractmethod
    def create_container(self, card: ContainerCard) -> str:
        """Create (but do not start) a container. Returns the container name/ID."""

    @abstractmethod
    def start_container(self, name: str) -> None:
        """Start a previously created container."""

    @abstractmethod
    def stop_container(self, name: str) -> None:
        """Stop a running container."""

    @abstractmethod
    def remove_container(self, name: str) -> None:
        """Remove a stopped container."""

    @abstractmethod
    def container_status(self, name: str) -> str:
        """Return the container's current status string (e.g. 'running', 'exited')."""

    @abstractmethod
    def container_logs(self, name: str) -> str:
        """Return the stdout/stderr logs of a container as a string."""

    def prepare_unit(self, container_card: ContainerCard) -> None:
        """Convenience: ensure image + network exist, then create the container."""
        from cutip.resolver.refs import RefResolver  # avoid circular at module level

        image_card = self._resolve_image(container_card)
        network_card = self._resolve_network(container_card)

        if image_card.spec.source == "pull":
            self.pull_image(image_card)
        else:
            self.build_image(image_card)

        self.ensure_network(network_card)
        self.create_container(container_card)

    # --- helpers for subclasses ---

    def _resolve_image(self, container_card: ContainerCard) -> ImageCard:
        raise NotImplementedError("Subclass must inject _resolver before calling _resolve_image")

    def _resolve_network(self, container_card: ContainerCard) -> NetworkCard:
        raise NotImplementedError("Subclass must inject _resolver before calling _resolve_network")
