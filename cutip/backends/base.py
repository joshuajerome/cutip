from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard


class CutipBackend(ABC):
    """Abstract interface for CUTIP execution backends (Podman, Docker, etc.).

    Backends manage the connection lifecycle (SSH tunnel, daemon socket) and
    expose a ``client`` property that returns the raw runtime client
    (PodmanClient or DockerClient).  ``ctx.runtime`` in workflows receives
    this raw client so that workflow.py can use the native podman-py /
    docker-py API directly.
    """

    @property
    @abstractmethod
    def client(self):
        """The raw runtime client (PodmanClient or DockerClient)."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the backend connection (close tunnel, socket, etc.)."""

    # ── Image operations ──────────────────────────────────────────────────────

    @abstractmethod
    def pull_image(self, card: ImageCard) -> None:
        """Pull an image from a registry."""

    @abstractmethod
    def build_image(
        self,
        card: ImageCard,
        project_root: Path | None = None,
        vars: dict | None = None,
        no_cache: bool = False,
    ) -> None:
        """Build an image from a local Dockerfile context."""

    def remove_image(self, name: str) -> None:
        """Remove an image by name/tag. No-op if not found."""

    # ── Network operations ────────────────────────────────────────────────────

    @abstractmethod
    def ensure_network(self, card: NetworkCard) -> None:
        """Create a network if it does not already exist."""

    @abstractmethod
    def ensure_default_network(self, name: str) -> None:
        """Create a default bridge network by name if it does not exist."""

    # ── Container operations ──────────────────────────────────────────────────

    @abstractmethod
    def create_container(
        self,
        card: ContainerCard,
        image_name: str | None = None,
        default_network: str | None = None,
    ) -> str:
        """Create (but do not start) a container. Returns the container name."""

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
