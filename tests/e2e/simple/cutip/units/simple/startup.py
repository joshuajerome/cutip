"""E2E smoke-test unit startup for 'simple'.

CUTIP has pulled the image, created the container; workflow.main() started it.
The container runs `echo CUTIP_OK && echo backend=podman` then exits.

startup(ctx) polls until the container finishes, asserts CUTIP_OK in the
logs, then removes the container.
"""

from __future__ import annotations

import time

from loguru import logger

from cutip.context.workflow import CutipContext
from cutip.models.cards.container import ContainerCard


def startup(ctx: CutipContext) -> None:
    client = ctx.runtime

    cc = next(c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard))
    container_name = cc.metadata.name

    logger.info(f"Waiting for container '{container_name}' to exit ...")

    container = client.containers.get(container_name)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        container.reload()
        if container.status in ("exited", "stopped"):
            break
        time.sleep(0.5)
    else:
        container.remove(force=True)
        raise RuntimeError(
            f"Container '{container_name}' did not exit within 15 seconds "
            f"(last status: {container.status})"
        )

    # Verify logs
    raw_logs = container.logs(stdout=True, stderr=True)
    logs = (
        raw_logs.decode("utf-8", errors="replace")
        if isinstance(raw_logs, bytes)
        else b"".join(raw_logs).decode("utf-8", errors="replace")
    )
    logger.info(f"Container logs:\n{logs}")

    assert "CUTIP_OK" in logs, f"Sentinel 'CUTIP_OK' not found in container logs.\nGot:\n{logs}"
    logger.success("CUTIP_OK confirmed in logs.")

    # Cleanup
    container.remove(force=True)
    logger.success("Container removed — E2E simple test PASSED.")
