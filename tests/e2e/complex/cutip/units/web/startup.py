"""E2E complex test — web unit startup.

Polls until the web container exits, asserts CUTIP_WEB_OK in its logs,
then removes both containers and the db_data volume.
"""

from __future__ import annotations

import time

from loguru import logger

from cutip.context.workflow import CutipContext


def startup(ctx: CutipContext) -> None:
    client = ctx.runtime

    logger.info("Waiting for cutip-web to exit ...")
    web = client.containers.get("cutip-web")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        web.reload()
        if web.status in ("exited", "stopped"):
            break
        time.sleep(0.5)
    else:
        _cleanup(client)
        raise RuntimeError(f"cutip-web did not exit within 15 seconds (last status: {web.status})")

    # Verify web container output
    raw_logs = web.logs(stdout=True, stderr=True)
    logs = (
        raw_logs.decode("utf-8", errors="replace")
        if isinstance(raw_logs, bytes)
        else b"".join(raw_logs).decode("utf-8", errors="replace")
    )
    logger.info(f"cutip-web logs:\n{logs}")

    assert "CUTIP_WEB_OK" in logs, (
        f"Sentinel 'CUTIP_WEB_OK' not found in web container logs.\nGot:\n{logs}"
    )
    logger.success("CUTIP_WEB_OK confirmed — multi-container orchestration PASSED.")

    _cleanup(client)
    logger.success("Containers removed — E2E complex test PASSED.")


def _cleanup(client) -> None:
    for name in ("cutip-web", "cutip-db"):
        try:
            client.containers.get(name).remove(force=True)
            logger.debug(f"Removed container {name}")
        except Exception:
            pass
    try:
        client.volumes.get("db_data").remove(force=True)
        logger.debug("Removed volume db_data")
    except Exception:
        pass
