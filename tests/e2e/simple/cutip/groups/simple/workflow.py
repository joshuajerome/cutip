"""E2E smoke-test for the 'simple' scaffold project.

Starts the simple container; startup.py polls for exit, asserts CUTIP_OK,
and removes the container.
"""

from __future__ import annotations

from cutip.context.workflow import CutipContext


def main(ctx: CutipContext) -> None:
    ctx.container("cutip-simple").start()
