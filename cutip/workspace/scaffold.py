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
    "cutip/units",
    "cutip/groups",
]

_RUNTIME_DIRS = [
    ".cutip/logs",
    ".cutip/cache",
    ".cutip/runs",
    ".cutip/locks",
]

# -- Example file contents written by `cutip init` ----------------------------
# All files are idempotent -- they are skipped if they already exist.

_EXAMPLE_IMAGE_YAML = """\
# -----------------------------------------------------------------------------
# ImageCard -- tells CUTIP where to get the container image.
#
# Two sources are supported:
#   source: pull   Pull a pre-built image from a registry (Docker Hub, GHCR, ...)
#   source: build  Build an image locally from a Dockerfile
#
# This card pulls the official Alpine Linux image from Docker Hub.
# For a build example, see the commented block at the bottom.
# -----------------------------------------------------------------------------
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
  # Private registries: registry.example.com/my-org/my-image
  image: docker.io/library/alpine

  # Pin to an explicit tag for reproducible runs.
  tag: "3.20"

# -----------------------------------------------------------------------------
# BUILD EXAMPLE — uncomment and adapt for a locally built image:
#
# spec:
#   source: build
#   tag: "1.0"
#
#   # Directory containing your Dockerfile (relative to project root).
#   context: containers/dockerfiles
#
#   # Dockerfile filename inside context (defaults to "Dockerfile").
#   dockerfile: myapp.dockerfile
#
#   # Build-time arguments passed as --build-arg to podman/docker build.
#   build_args:
#     PYTHON_VERSION: "3.11"
#     APP_ENV: production
#
#   # Files and directories to stage into {context}/buildtime/ before the build.
#   # CUTIP copies these alongside the Dockerfile so COPY instructions can reach
#   # them -- mirrors the podwrap buildtime_resources pattern.
#   # Paths are relative to the project root (where cutip.yaml lives).
#   buildtime_resources:
#     - src: containers/resources/requirements.txt
#     - src: containers/resources/collections.yaml
#     - src: containers/resources/settings.json
#       dest: vscode-settings.json     # optional rename on the way in
#     - src: containers/scripts/       # directories are copied recursively
#
#   # Staging directory (defaults to {context}/buildtime if omitted).
#   # buildtime_dir: containers/dockerfiles/buildtime
# -----------------------------------------------------------------------------
"""

_EXAMPLE_CONTAINER_YAML = """\
# -----------------------------------------------------------------------------
# ContainerCard -- describes a single container: image, network, command,
# environment variables, ports, mounts, volumes, labels, and more.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  # The name given to the container on the daemon (docker ps / podman ps).
  # Must be unique across all running containers on the host.
  name: cutip-hello

spec:
  # -- Image ------------------------------------------------------------------
  # Reference to an ImageCard by its metadata.name.
  imageRef:
    ref: images/alpine

  # -- Network ----------------------------------------------------------------
  # Exactly one of network_mode or networkRef must be provided.
  #
  # network_mode: bridge   -- default bridge network
  # network_mode: host     -- share the host network stack (Linux only)
  # network_mode: none     -- fully isolated
  #
  # To use a named network managed by CUTIP:
  #   networkRef:
  #     ref: networks/<NetworkCard-name>
  network_mode: bridge

  # -- Command ----------------------------------------------------------------
  command: 'sh -c "echo Hello from CUTIP! && echo backend=$CUTIP_BACKEND"'

  # -- Environment variables --------------------------------------------------
  # Static values defined in YAML.  Use descriptive names -- prefer full
  # command strings or meaningful paths, as in the podwrap pattern.
  # workflow.py can inject or override values at runtime via model_copy(update=).
  environment:
    CUTIP_BACKEND: "unknown"       # overwritten at runtime by workflow.py
    LANG: "C.UTF-8"
    LC_ALL: "C.UTF-8"
    # CLEANUP_CMD: "ansible-playbook -i hosts /app/playbooks/cleanup.yaml"

  # -- Labels -----------------------------------------------------------------
  # Arbitrary metadata attached to the container (visible in podman ps / docker ps).
  labels:
    app: cutip-hello
    env: dev

  # -- Ports ------------------------------------------------------------------
  # {container_port[/proto]: host_port}
  # ports:
  #   "8080/tcp": "8080"
  #   "5432/tcp": "5432"

  # -- Bind mounts ------------------------------------------------------------
  # create_host_path: true instructs CUTIP to create the host directory before
  # the workflow runs -- mirrors the podwrap pattern of pre-creating data dirs.
  # mounts:
  #   - type: bind
  #     source: ./data/sheets          # relative to project root
  #     target: /app/sheets
  #     read_only: false
  #     create_host_path: true         # CUTIP creates ./data/sheets if missing
  #
  #   - type: bind
  #     source: ./config/settings.json
  #     target: /app/settings.json
  #     read_only: true

  # -- Named volumes ----------------------------------------------------------
  # Inline volume definitions: {volume_name: container_path}
  # The runtime creates the volume on first use.
  # volumes:
  #   postgres_data: /var/lib/postgresql/data
  #   node_modules:  /app/node_modules

  # -- Privileges -------------------------------------------------------------
  # privileged: false
  # cap_add:
  #   - NET_ADMIN
  # security_opts:
  #   - label=disable
"""

_EXAMPLE_UNIT_YAML = """\
# -----------------------------------------------------------------------------
# Unit -- a named, reusable deployment unit backed by a ContainerCard.
#
# Groups reference Units (not ContainerCards directly).  This indirection lets
# you share a ContainerCard definition across multiple groups or swap
# implementations behind the same unit name for different environments.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: Unit
metadata:
  name: hello

spec:
  # The ContainerCard this unit is backed by.  Format: containers/<name>
  containerRef:
    ref: containers/cutip-hello
"""

_EXAMPLE_GROUP_YAML = """\
# -----------------------------------------------------------------------------
# Group -- an ordered set of Units and the workflow that orchestrates them.
#
# Running `cutip run hello` will:
#   1. Discover and resolve all cards referenced by the units listed below.
#   2. Create host directories for mounts with create_host_path: true.
#   3. Connect to the container runtime (Podman or Docker).
#   4. Inject the raw client into ctx.runtime and call main(ctx) in workflow.py.
#
# Use `cutip plan hello` to preview what CUTIP would do without running it.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: Group
metadata:
  name: hello

spec:
  # Ordered list of Units included in this group.
  # CUTIP resolves each Unit's ContainerCard (and its transitive dependencies:
  # ImageCard, NetworkCard, ...) before workflow.py is invoked.
  units:
    - ref: units/hello

  # Path to the workflow module, relative to this group's directory.
  # The file must export `def main(ctx: CutipContext) -> None`.
  workflow: workflow.py
"""

_EXAMPLE_WORKFLOW_PY = """\
\"\"\"Hello-world CUTIP workflow -- uses the native Podman API via ctx.runtime.

ctx.runtime is the raw PodmanClient (or DockerClient) injected by CUTIP.
You have the full podman-py / docker-py API surface available; CUTIP only
provides the resolved card data and manages the connection lifecycle.

Run with:
    cutip run hello                    # Podman via SSH tunnel (default)
    cutip run hello --local            # Podman via local socket
    cutip run hello --backend docker   # Docker daemon
\"\"\"

from __future__ import annotations

import os
import time

from cutip.context.workflow import CutipContext
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard


def main(ctx: CutipContext) -> None:
    \"\"\"Entry point called by `cutip run hello`.

    Args:
        ctx: Fully resolved runtime context:
             ctx.runtime        -- raw PodmanClient or DockerClient
             ctx.resolved_cards -- dict[ref_str, card] of every resolved card
             ctx.project_root   -- absolute Path to the project root
    \"\"\"
    # ctx.runtime is the native client -- import the type for IDE completion.
    # For Podman:  from podman import PodmanClient; client: PodmanClient = ctx.runtime
    # For Docker:  import docker; client: docker.DockerClient = ctx.runtime
    client = ctx.runtime

    # -- 1. Resolve cards from context ----------------------------------------
    # ctx.resolved_cards is keyed by ref string (e.g. "images/alpine").
    img_card: ImageCard = next(
        c for c in ctx.resolved_cards.values() if isinstance(c, ImageCard)
    )
    cc: ContainerCard = next(
        c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard)
    )

    image_ref  = f"{img_card.metadata.name}:{img_card.spec.tag}"
    cname      = cc.metadata.name
    backend    = os.environ.get("CUTIP_BACKEND_NAME", "unknown")

    print(f"[hello] backend={backend}  image={image_ref}")

    # -- 2. Pull image ---------------------------------------------------------
    # Using the native API directly -- full podman-py / docker-py interface.
    print("[hello] pulling image ...")
    client.images.pull(img_card.spec.image, tag=img_card.spec.tag)

    # Tag with the card's canonical alias so we can reference it by name.
    local_alias, alias_tag = image_ref.rsplit(":", 1)
    try:
        img_obj = client.images.get(image_ref)
    except Exception:
        img_obj = client.images.get(f"{img_card.spec.image}:{img_card.spec.tag}")
    if image_ref not in (img_obj.tags or []):
        img_obj.tag(local_alias, alias_tag)

    # -- 3. Remove stale container from a previous run ------------------------
    try:
        old = client.containers.get(cname)
        print(f"[hello] removing stale container (status={old.status})")
        old.remove(force=True)
    except Exception:
        pass   # not found -- nothing to clean up

    # -- 4. Create container ---------------------------------------------------
    print("[hello] creating container ...")
    import shlex
    kwargs = {
        "name":        cname,
        "image":       image_ref,
        "command":     shlex.split(cc.spec.command) if cc.spec.command else None,
        "environment": {**cc.spec.environment, "CUTIP_BACKEND": backend},
        "labels":      cc.spec.labels or {},
        "detach":      True,
    }
    if cc.spec.network_mode:
        kwargs["network_mode"] = cc.spec.network_mode
    container = client.containers.create(**{k: v for k, v in kwargs.items() if v is not None})

    # -- 5. Start & wait -------------------------------------------------------
    print("[hello] starting container ...")
    container.start()

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        container.reload()
        if container.status in ("exited", "stopped"):
            break
        time.sleep(0.5)
    else:
        container.remove(force=True)
        raise RuntimeError(f"Container did not exit within 30s (status={container.status})")

    # -- 6. Logs ---------------------------------------------------------------
    raw_logs = container.logs(stdout=True, stderr=True)
    logs = raw_logs.decode("utf-8", errors="replace") if isinstance(raw_logs, bytes) else b"".join(raw_logs).decode()
    print(f"[hello] output:\\n{logs}")

    # -- 7. Cleanup ------------------------------------------------------------
    container.remove(force=True)
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

        # -- Directories -------------------------------------------------------
        for rel in _CUTIP_DIRS + _RUNTIME_DIRS:
            target = self.project_root / rel
            if target.exists():
                logger.debug(f"  exists: {rel}")
            else:
                target.mkdir(parents=True, exist_ok=True)
                logger.debug(f"  created: {rel}")

        # -- Project config ----------------------------------------------------
        self._write_cutip_yaml()

        # -- Example project ---------------------------------------------------
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
