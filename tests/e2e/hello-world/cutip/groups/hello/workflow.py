"""E2E smoke-test workflow.

Steps:
  1. Pull alpine image
  2. Create + start a short-lived container that prints 'CUTIP_OK'
  3. Wait for it to exit, then read its logs
  4. Assert the sentinel string is present  ← proves the backend round-trip works
  5. Clean up (remove container)

Exits non-zero (via assert) on any failure, causing `cutip run` to surface the
error and the GitHub Actions step to fail.
"""

from __future__ import annotations

import os
import time

from cutip.backends.base import CutipBackend
from cutip.context.workflow import CutipContext
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard


def main(ctx: CutipContext) -> None:
    runtime: CutipBackend = ctx.runtime
    backend_name = os.environ.get("CUTIP_BACKEND_NAME", "unknown")

    # ── Resolve cards ──────────────────────────────────────────────────────
    img_card = next(
        c for c in ctx.resolved_cards.values() if isinstance(c, ImageCard)
    )
    cc = next(
        c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard)
    )

    # Stamp the backend name into the container environment at runtime
    cc = cc.model_copy(
        update={
            "spec": cc.spec.model_copy(
                update={"environment": {**cc.spec.environment, "CUTIP_BACKEND": backend_name}}
            )
        }
    )

    image_name = f"{img_card.metadata.name}:{img_card.spec.tag}"
    container_name = cc.metadata.name

    print(f"[hello-world] backend={backend_name}  image={image_name}")

    # ── Pull ───────────────────────────────────────────────────────────────
    print("[hello-world] pulling image ...")
    runtime.pull_image(img_card)

    # ── Clean up any leftover from a previous run ──────────────────────────
    status = runtime.container_status(container_name)
    if status != "not_found":
        print(f"[hello-world] removing stale container (status={status})")
        runtime.remove_container(container_name)

    # ── Create & start ─────────────────────────────────────────────────────
    print("[hello-world] creating container ...")
    runtime.create_container(cc, image_name=image_name)

    print("[hello-world] starting container ...")
    runtime.start_container(container_name)

    # ── Wait for exit (up to 15 s) ─────────────────────────────────────────
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        status = runtime.container_status(container_name)
        if status in ("exited", "stopped"):
            break
        time.sleep(0.5)
    else:
        runtime.remove_container(container_name)
        raise RuntimeError(
            f"Container '{container_name}' did not exit within 15 seconds "
            f"(last status: {status})"
        )

    # ── Verify logs ────────────────────────────────────────────────────────
    logs = runtime.container_logs(container_name)
    print(f"[hello-world] container logs:\n{logs}")

    assert "CUTIP_OK" in logs, (
        f"Sentinel 'CUTIP_OK' not found in container logs.\n"
        f"Got:\n{logs}"
    )
    print("[hello-world] [OK] CUTIP_OK confirmed in logs")

    # ── Cleanup ────────────────────────────────────────────────────────────
    runtime.remove_container(container_name)
    print("[hello-world] container removed - E2E test PASSED [OK]")
