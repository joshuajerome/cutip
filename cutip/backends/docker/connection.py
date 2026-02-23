"""Docker connection management.

Handles connecting to the Docker daemon via docker-py, respecting the
``DOCKER_HOST`` environment variable for remote daemons.

Run standalone to verify connectivity::

    python -m cutip.backends.docker.connection
"""

from __future__ import annotations

import sys

from loguru import logger

from cutip.utils.exceptions import CutipError


def connect_client():
    """Connect to the Docker daemon and return a :class:`docker.DockerClient`.

    Respects ``DOCKER_HOST`` (and all other docker-py env vars) automatically,
    so CI setups that export ``DOCKER_HOST`` work without extra configuration.

    Returns:
        A connected :class:`docker.DockerClient` instance.

    Raises:
        CutipError: If docker-py is not installed or the daemon is unreachable.
    """
    try:
        import docker
    except ImportError as exc:
        raise CutipError(
            "The 'docker' package is required for the Docker backend. "
            "Run: uv add docker"
        ) from exc

    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:
        raise CutipError(
            f"Docker connection failed: {exc}. "
            "Is Docker running? Check DOCKER_HOST if using a remote daemon."
        ) from exc

    logger.info("Docker client connected.")
    return client


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Verify Docker connectivity without running a full workflow.

    Usage::

        python -m cutip.backends.docker.connection
    """
    from cutip.utils.logging import setup_logging
    setup_logging(level="DEBUG")

    logger.info("Testing Docker connection...")

    try:
        client = connect_client()
    except CutipError as exc:
        logger.error(str(exc))
        sys.exit(1)

    version = client.version()
    logger.info(f"Docker Engine version: {version.get('Version', 'unknown')}")

    images = client.images.list()
    logger.info(f"Images on daemon: {len(images)}")
    for img in images[:5]:
        logger.info(f"  {img.tags}")

    containers = client.containers.list(all=True)
    logger.info(f"Containers (all): {len(containers)}")
    for c in containers[:5]:
        logger.info(f"  {c.name}  [{c.status}]")
