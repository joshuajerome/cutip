"""Docker connection management.

Handles connecting to the local Docker daemon via ``docker.from_env()``.

Run standalone to verify connectivity::

    python -m cutip.backends.docker.connection
"""

from __future__ import annotations

import sys

from loguru import logger

from cutip.utils.exceptions import CutipError


def connect_docker_client():
    """Connect to the local Docker daemon and return a ``DockerClient``.

    Raises:
        CutipError: If the ``docker`` package is missing or the daemon is unreachable.
    """
    try:
        import docker
    except ImportError as exc:
        raise CutipError(
            "The 'docker' package is required for the Docker backend. "
            "Run: uv pip install 'cutip[docker]'"
        ) from exc

    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:
        raise CutipError(
            f"Could not connect to the Docker daemon: {exc}\n"
            "Is Docker Desktop or the Docker daemon running?"
        ) from exc

    logger.info("Docker daemon connected.")
    return client


# ── Standalone test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Verify Docker connectivity without running a full workflow.

    Usage::

        python -m cutip.backends.docker.connection
    """
    from cutip.utils.logging import setup_logging
    setup_logging(level="DEBUG")

    try:
        client = connect_docker_client()
    except CutipError as exc:
        logger.error(str(exc))
        sys.exit(1)

    logger.info("Ping OK")
    images = client.images.list()
    logger.info(f"Images on daemon: {len(images)}")
    for img in images[:5]:
        logger.info(f"  {img.tags}")
