"""E2E smoke-test for the 'simple' scaffold project.

Starts the simple container; startup.py polls for exit, asserts CUTIP_OK,
and removes the container.
"""

from __future__ import annotations

from cutip.context.workflow import CutipContext
from cutip.workflow import action, orchestrator


@action(name="Start Container", description="Start the simple container", container="cutip-simple")
def start_container(ctx: CutipContext) -> None:
    ctx.container("cutip-simple").start()


@orchestrator
def main(ctx: CutipContext) -> None:
    start_container(ctx)
