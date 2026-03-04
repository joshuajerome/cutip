"""CUTIP execution backends.

Available backends:

- :class:`~cutip.backends.podman.PodmanBackend` — Podman via SSH tunnel or local socket
- :class:`~cutip.backends.docker.DockerBackend` — Docker via local daemon

Connection utilities (runnable standalone to verify connectivity):

    python -m cutip.backends.podman.connection           # SSH tunnel
    python -m cutip.backends.podman.connection --local   # local socket
    python -m cutip.backends.docker.connection           # Docker daemon

Shared utilities:

- :mod:`cutip.backends.shared.image` — ``image_alias`` / ``image_ref`` helpers
"""

from __future__ import annotations

from cutip.backends.base import CutipBackend
from cutip.utils.exceptions import CutipError


def get_backend(name: str, local: bool = False) -> CutipBackend:
    """Return a connected backend instance by name.

    Args:
        name:  ``"podman"`` or ``"docker"``.
        local: For Podman, connect to the local socket instead of SSH tunnel.
               Ignored for Docker (always uses local daemon).

    Raises:
        CutipError: If the backend name is unknown or connection fails.
    """
    if name == "podman":
        from cutip.backends.podman import PodmanBackend
        return PodmanBackend.connect_local() if local else PodmanBackend.connect()

    if name == "docker":
        from cutip.backends.docker import DockerBackend
        return DockerBackend.connect()

    raise CutipError(
        f"Unknown backend '{name}'. Supported backends: podman, docker"
    )
