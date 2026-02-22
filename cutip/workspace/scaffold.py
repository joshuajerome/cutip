from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import yaml
from loguru import logger


_CUTIP_DIRS = [
    "cutip/cards/images",
    "cutip/cards/containers",
    "cutip/cards/networks",
    "cutip/cards/volumes",
    "cutip/units",
    "cutip/groups",
]

_RUNTIME_DIRS = [
    ".cutip/logs",
    ".cutip/cache",
    ".cutip/runs",
    ".cutip/locks",
]

# ── Example file contents written by `cutip init` ────────────────────────────
# All files are idempotent — they are skipped if they already exist.

_EXAMPLE_IMAGE_YAML = """\
# ─────────────────────────────────────────────────────────────────────────────
# ImageCard — tells CUTIP where to get the container image.
#
# Two sources are supported:
#   source: pull   Pull a pre-built image from a registry (Docker Hub, GHCR, …)
#   source: build  Build an image locally from a Dockerfile
#
# This card pulls the official Alpine Linux image from Docker Hub.
# ─────────────────────────────────────────────────────────────────────────────
apiVersion: cutip/v1
kind: ImageCard
metadata:
  # Unique name within your workspace.  ContainerCards reference this via
  # imageRef.ref: images/<name>
  name: alpine

spec:
  # Pull an existing image rather than building one locally.
  source: pull

  # Full registry path.  Docker Hub official images use docker.io/library/.
  # For private registries: registry.example.com/my-org/my-image
  image: docker.io/library/alpine

  # Pin to an explicit tag for reproducible runs.
  # Use "latest" during exploration; pin to a digest in production.
  tag: "3.20"
"""

_EXAMPLE_CONTAINER_YAML = """\
# ─────────────────────────────────────────────────────────────────────────────
# ContainerCard — describes a single container: image, network, command,
# environment variables, ports, mounts, volumes, and more.
#
# Cards are immutable definitions. workflow.py can layer runtime values on top
# using Pydantic's model_copy(update=…) before passing them to the backend.
# ─────────────────────────────────────────────────────────────────────────────
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  # The name given to the container on the daemon (docker ps / podman ps).
  # Must be unique across all running containers on the host.
  name: cutip-hello

spec:
  # ── Image ──────────────────────────────────────────────────────────────────
  # Reference to an ImageCard by its metadata.name.
  # CUTIP pulls or builds the image before creating this container.
  imageRef:
    ref: images/alpine

  # ── Network ────────────────────────────────────────────────────────────────
  # Exactly one of `network_mode` or `networkRef` must be provided.
  #
  # network_mode: bridge   — shared bridge (default Docker/Podman behaviour)
  # network_mode: host     — share the host network stack (Linux only)
  # network_mode: none     — fully isolated, no network access
  #
  # To use a named network managed by CUTIP, replace network_mode with:
  #   networkRef:
  #     ref: networks/<NetworkCard-name>
  network_mode: bridge

  # ── Command ────────────────────────────────────────────────────────────────
  # Shell command run inside the container.  Supports quoting (shlex-parsed).
  # This short-lived command prints a greeting and exits immediately, which
  # makes it easy to verify the full CUTIP round-trip end-to-end.
  command: 'sh -c "echo Hello from CUTIP! && echo backend=$CUTIP_BACKEND"'

  # ── Environment variables ──────────────────────────────────────────────────
  # Static values defined here; workflow.py can add or override at runtime.
  environment:
    CUTIP_BACKEND: "unknown"    # overwritten at runtime by workflow.py

  # ── Ports ─────────────────────────────────────────────────────────────────
  # Map container ports to host ports: {container_port: host_port}
  # ports:
  #   "8080": "8080"
  #   "5432": "5432"

  # ── Bind mounts ───────────────────────────────────────────────────────────
  # mounts:
  #   - type: bind
  #     source: ./config        # host path (relative to project root)
  #     target: /app/config     # path inside the container
  #     read_only: true

  # ── Named volumes ─────────────────────────────────────────────────────────
  # Volumes are created by CUTIP if they don't exist (via VolumeCard).
  # volumes:
  #   my-data: /app/data        # {volume-name: container-path}
"""

_EXAMPLE_UNIT_YAML = """\
# ─────────────────────────────────────────────────────────────────────────────
# Unit — a named, reusable deployment unit backed by a ContainerCard.
#
# Groups reference Units (not ContainerCards directly).  This indirection lets
# you share a ContainerCard definition across multiple groups, or substitute a
# different container behind the same unit name for different environments.
# ─────────────────────────────────────────────────────────────────────────────
apiVersion: cutip/v1
kind: Unit
metadata:
  # Unit name referenced from GroupCard spec.units[].ref
  name: hello

spec:
  # The ContainerCard this unit is backed by.
  # Format: containers/<ContainerCard-name>
  containerRef:
    ref: containers/cutip-hello
"""

_EXAMPLE_GROUP_YAML = """\
# ─────────────────────────────────────────────────────────────────────────────
# Group — an ordered set of Units and the workflow that orchestrates them.
#
# Running `cutip run hello` will:
#   1. Discover and resolve all cards referenced by the units listed below.
#   2. Inject everything into a CutipContext.
#   3. Connect to the container backend (Podman or Docker).
#   4. Call main(ctx) in workflow.py.
#
# Use `cutip plan hello` to preview what CUTIP would do without running it.
# ─────────────────────────────────────────────────────────────────────────────
apiVersion: cutip/v1
kind: Group
metadata:
  # Group name — passed to `cutip run <name>` and `cutip plan <name>`.
  name: hello

spec:
  # ── Units ──────────────────────────────────────────────────────────────────
  # Ordered list of Units included in this group.
  # CUTIP resolves each Unit's ContainerCard (and its transitive dependencies:
  # ImageCard, NetworkCard, VolumeCard, …) before workflow.py is invoked.
  # The resolved objects are available via ctx.resolved_cards.
  units:
    - ref: units/hello

  # ── Workflow ───────────────────────────────────────────────────────────────
  # Path to the workflow module, relative to this group's directory.
  # The file must export `def main(ctx: CutipContext) -> None`.
  workflow: workflow.py
"""

_EXAMPLE_WORKFLOW_PY = """\
\"\"\"Hello-world CUTIP workflow.

Demonstrates the full container lifecycle managed by CUTIP:
  1. Pull the image        (idempotent — skipped if already cached locally)
  2. Clean up stale runs   (removes any leftover container from a previous run)
  3. Create the container  (allocates the container, does not start it)
  4. Start the container   (kicks off the process)
  5. Wait for it to exit   (polls status; this command is short-lived)
  6. Read its logs         (capture stdout / stderr via the backend)
  7. Remove the container  (clean up after ourselves)

Run with:
    cutip run hello --backend podman --local   # local Podman socket
    cutip run hello --backend docker           # local Docker daemon
\"\"\"

from __future__ import annotations

import os
import time

from cutip.backends.base import CutipBackend
from cutip.context.workflow import CutipContext
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard


def main(ctx: CutipContext) -> None:
    \"\"\"Entry point called by `cutip run hello`.

    Args:
        ctx: Fully resolved runtime context.  Key attributes:
             - ctx.runtime        CutipBackend handle (Podman or Docker)
             - ctx.resolved_cards dict[ref_str, CutipBaseModel] of every card
                                  transitively resolved for this group
             - ctx.group          the Group artifact itself
             - ctx.project_root   absolute Path to the project root
    \"\"\"
    runtime: CutipBackend = ctx.runtime

    # ── 1. Resolve cards ───────────────────────────────────────────────────
    # ctx.resolved_cards is keyed by ref string (e.g. "images/alpine").
    # Filter by type to get strongly-typed card objects.
    img_card: ImageCard = next(
        c for c in ctx.resolved_cards.values() if isinstance(c, ImageCard)
    )
    cc: ContainerCard = next(
        c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard)
    )

    # ── 2. Inject runtime values ───────────────────────────────────────────
    # Cards are immutable Pydantic models — never mutate them in place.
    # Use model_copy(update=…) to create a modified copy for this run only;
    # the registry copy is left unchanged for future re-use.
    backend_name: str = os.environ.get("CUTIP_BACKEND_NAME", "unknown")
    cc = cc.model_copy(
        update={
            "spec": cc.spec.model_copy(
                update={
                    "environment": {
                        **cc.spec.environment,
                        "CUTIP_BACKEND": backend_name,
                    }
                }
            )
        }
    )

    # image_name must match the local alias that pull_image tags the image
    # with: {card.metadata.name}:{card.spec.tag}  (e.g. "alpine:3.20")
    image_name: str = f"{img_card.metadata.name}:{img_card.spec.tag}"
    container_name: str = cc.metadata.name

    print(f"[hello] backend={backend_name}  image={image_name}")

    # ── 3. Pull image ──────────────────────────────────────────────────────
    # Idempotent: if the image is already present locally this is a no-op.
    print("[hello] pulling image ...")
    runtime.pull_image(img_card)

    # ── 4. Remove any stale container from a previous run ──────────────────
    status: str = runtime.container_status(container_name)
    if status != "not_found":
        print(f"[hello] removing stale container (status={status})")
        runtime.remove_container(container_name)

    # ── 5. Create & start ──────────────────────────────────────────────────
    print("[hello] creating container ...")
    runtime.create_container(cc, image_name=image_name)

    print("[hello] starting container ...")
    runtime.start_container(container_name)

    # ── 6. Wait for the container to exit ─────────────────────────────────
    # The hello command is short-lived; poll until it exits or we time out.
    timeout_seconds: int = 30
    deadline: float = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = runtime.container_status(container_name)
        if status in ("exited", "stopped"):
            break
        time.sleep(0.5)
    else:
        runtime.remove_container(container_name)
        raise RuntimeError(
            f"Container '{container_name}' did not exit within {timeout_seconds}s "
            f"(last status: {status})"
        )

    # ── 7. Read logs ───────────────────────────────────────────────────────
    logs: str = runtime.container_logs(container_name)
    print(f"[hello] output:\\n{logs}")

    # ── 8. Cleanup ─────────────────────────────────────────────────────────
    runtime.remove_container(container_name)
    print("[hello] done - workflow complete")
"""


def _find_project_root() -> Path:
    """Return the git root if inside a repo, otherwise cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _write_file(path: Path, content: str, label: str) -> None:
    """Write *content* to *path* unless it already exists (idempotent)."""
    if path.exists():
        logger.debug(f"  exists: {label}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.debug(f"  created: {label}")


class WorkspaceScaffold:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or _find_project_root()

    def init(self) -> None:
        """Create the CUTIP workspace structure and example files. Idempotent."""
        logger.info(f"Initializing CUTIP workspace at {self.project_root}")

        # ── Directories ───────────────────────────────────────────────────
        for rel in _CUTIP_DIRS + _RUNTIME_DIRS:
            target = self.project_root / rel
            if target.exists():
                logger.debug(f"  exists: {rel}")
            else:
                target.mkdir(parents=True, exist_ok=True)
                logger.debug(f"  created: {rel}")

        # ── Project config ────────────────────────────────────────────────
        self._write_cutip_yaml()

        # ── Example project ───────────────────────────────────────────────
        # A complete, runnable "hello" group so users can immediately do:
        #   cutip run hello --backend podman --local
        #   cutip run hello --backend docker
        root = self.project_root
        _write_file(
            root / "cutip/cards/images/alpine.yaml",
            _EXAMPLE_IMAGE_YAML,
            "cutip/cards/images/alpine.yaml",
        )
        _write_file(
            root / "cutip/cards/containers/hello.yaml",
            _EXAMPLE_CONTAINER_YAML,
            "cutip/cards/containers/hello.yaml",
        )
        _write_file(
            root / "cutip/units/hello.yaml",
            _EXAMPLE_UNIT_YAML,
            "cutip/units/hello.yaml",
        )
        _write_file(
            root / "cutip/groups/hello/group.yaml",
            _EXAMPLE_GROUP_YAML,
            "cutip/groups/hello/group.yaml",
        )
        _write_file(
            root / "cutip/groups/hello/workflow.py",
            _EXAMPLE_WORKFLOW_PY,
            "cutip/groups/hello/workflow.py",
        )

        logger.info("Workspace ready.")

    def _write_cutip_yaml(self) -> None:
        config_path = self.project_root / "cutip.yaml"
        if config_path.exists():
            logger.debug("  exists: cutip.yaml")
            return

        project_name = self.project_root.name
        doc = {
            "apiVersion": "cutip/v1",
            "project": {
                "name": project_name,
                "version": "0.1.0",
            },
        }
        with config_path.open("w", encoding="utf-8") as fh:
            yaml.dump(doc, fh, default_flow_style=False, sort_keys=False)
        logger.debug("  created: cutip.yaml")
