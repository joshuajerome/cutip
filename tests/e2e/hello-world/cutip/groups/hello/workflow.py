"""E2E smoke-test group workflow.

CUTIP pulls the image and creates the container.
main() starts it; units/hello/startup.py polls for exit, asserts CUTIP_OK,
and removes the container.
"""

from __future__ import annotations

from cutip.context.workflow import CutipContext


def main(ctx: CutipContext) -> None:
    """Start the hello container."""
    ctx.container("cutip-hello").start()
