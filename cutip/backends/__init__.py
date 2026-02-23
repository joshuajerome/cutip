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
