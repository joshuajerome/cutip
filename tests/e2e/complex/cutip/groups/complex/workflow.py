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
from cutip.workflow import action, orchestrator


@action(name="Start Database", description="Start PostgreSQL", container="cutip-db")
def start_database(ctx: CutipContext) -> None:
    ctx.container("cutip-db").start()
    logger.info("Waiting for postgres to accept connections...")


@action(name="Wait for Database", description="Poll until DB accepts connections", container="cutip-db")
def wait_for_database(ctx: CutipContext) -> None:
    db = ctx.container("cutip-db")
    db_password = ctx.secrets["db_password"]
    for attempt in range(1, 31):
        exit_code, _ = db.exec_run(
            ["psql", "-U", "appuser", "-d", "appdb", "-c", "SELECT 1"],
            environment={"PGPASSWORD": db_password},
        )
        if exit_code == 0:
            logger.success(f"Postgres ready after {attempt} attempt(s)")
            return
        logger.debug(f"  attempt {attempt}/30 — postgres not ready yet")
        time.sleep(1)

    db.remove(force=True)
    raise RuntimeError(
        "Postgres did not become ready within 30 seconds. "
        "Check 'podman logs cutip-db' for details."
    )


@action(name="Start Web", description="Start the web container", container="cutip-web")
def start_web(ctx: CutipContext) -> None:
    ctx.container("cutip-web").start()
    logger.info("Web container started")


@orchestrator
def main(ctx: CutipContext) -> None:
    start_database(ctx)
    wait_for_database(ctx)
    start_web(ctx)
