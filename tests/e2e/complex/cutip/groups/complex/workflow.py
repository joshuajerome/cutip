"""E2E complex test workflow.

Starts PostgreSQL, waits for it to accept connections (health-check loop
via exec_run), then starts the web container.

This verifies CUTIP's multi-container orchestration: startup ordering
is determined by actual container behavior, not a static declaration.
"""

from __future__ import annotations

import time

from loguru import logger

from cutip.context.workflow import CutipContext


def main(ctx: CutipContext) -> None:
    db = ctx.container("cutip-db")
    web = ctx.container("cutip-web")

    # Start the database
    db.start()
    logger.info("Waiting for postgres to accept connections...")

    db_password = ctx.vars["db_password"]
    for attempt in range(1, 31):
        exit_code, _ = db.exec_run(
            ["psql", "-U", "appuser", "-d", "appdb", "-c", "SELECT 1"],
            environment={"PGPASSWORD": db_password},
        )
        if exit_code == 0:
            logger.success(f"Postgres ready after {attempt} attempt(s)")
            break
        logger.debug(f"  attempt {attempt}/30 — postgres not ready yet")
        time.sleep(1)
    else:
        db.remove(force=True)
        raise RuntimeError(
            "Postgres did not become ready within 30 seconds. "
            "Check 'podman logs cutip-db' for details."
        )

    # Database confirmed ready — start the web container
    web.start()
    logger.info("Web container started")
