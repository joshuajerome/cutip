"""E2E smoke-test workflow — uses the native Podman/Docker API via ctx.runtime.

Steps:
  1. Pull alpine image
  2. Create + start a short-lived container that prints 'CUTIP_OK'
  3. Wait for it to exit, then read its logs
  4. Assert the sentinel string is present  <- proves the backend round-trip works
  5. Clean up (remove container)

Exits non-zero (via assert) on any failure, causing `cutip run` to surface the
error and the GitHub Actions step to fail.
"""

from __future__ import annotations

import os
import shlex
import time

from cutip.context.workflow import CutipContext
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard


def main(ctx: CutipContext) -> None:
    # ctx.runtime is the raw PodmanClient or DockerClient
    client = ctx.runtime
    backend_name = os.environ.get("CUTIP_BACKEND_NAME", "unknown")

    # -- Resolve cards from context -------------------------------------------
    img_card: ImageCard = next(
        c for c in ctx.resolved_cards.values() if isinstance(c, ImageCard)
    )
    cc: ContainerCard = next(
        c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard)
    )

    # Strip docker.io/library/ prefix so the pull ref matches the local name.
    pull_ref = img_card.spec.image
    if pull_ref.startswith("docker.io/library/"):
        pull_ref = pull_ref[len("docker.io/library/"):]

    image_alias = f"{img_card.metadata.name}:{img_card.spec.tag}"
    container_name = cc.metadata.name

    print(f"[hello-world] backend={backend_name}  image={image_alias}")

    # -- 1. Pull image ---------------------------------------------------------
    print("[hello-world] pulling image ...")
    client.images.pull(pull_ref, tag=img_card.spec.tag)

    # Tag with the card's canonical alias so we can reference it by name.
    try:
        img_obj = client.images.get(f"{pull_ref}:{img_card.spec.tag}")
    except Exception:
        img_obj = client.images.get(f"{img_card.spec.image}:{img_card.spec.tag}")

    if image_alias not in (img_obj.tags or []):
        alias_name, alias_tag = image_alias.rsplit(":", 1)
        img_obj.tag(alias_name, alias_tag)

    # -- 2. Remove stale container from a previous run -------------------------
    try:
        old = client.containers.get(container_name)
        print(f"[hello-world] removing stale container (status={old.status})")
        old.remove(force=True)
    except Exception:
        pass  # not found -- nothing to clean up

    # -- 3. Create container ---------------------------------------------------
    print("[hello-world] creating container ...")
    env = {**cc.spec.environment, "CUTIP_BACKEND": backend_name}
    kwargs = {
        "name": container_name,
        "image": image_alias,
        "command": shlex.split(cc.spec.command) if cc.spec.command else None,
        "environment": env,
        "detach": True,
    }
    if cc.spec.network_mode:
        kwargs["network_mode"] = cc.spec.network_mode
    container = client.containers.create(**{k: v for k, v in kwargs.items() if v is not None})

    # -- 4. Start & wait -------------------------------------------------------
    print("[hello-world] starting container ...")
    container.start()

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

    # -- 5. Verify logs --------------------------------------------------------
    raw_logs = container.logs(stdout=True, stderr=True)
    logs = (
        raw_logs.decode("utf-8", errors="replace")
        if isinstance(raw_logs, bytes)
        else b"".join(raw_logs).decode("utf-8", errors="replace")
    )
    print(f"[hello-world] container logs:\n{logs}")

    assert "CUTIP_OK" in logs, (
        f"Sentinel 'CUTIP_OK' not found in container logs.\nGot:\n{logs}"
    )
    print("[hello-world] [OK] CUTIP_OK confirmed in logs")

    # -- 6. Cleanup ------------------------------------------------------------
    container.remove(force=True)
    print("[hello-world] container removed - E2E test PASSED [OK]")
