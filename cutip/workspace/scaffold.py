from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import yaml
from loguru import logger


_CUTIP_VARS_YAML = """\
# cutip/vars.yaml — fill in your machine-specific values.
#
# This file is gitignored and MUST NOT be committed — it contains paths and
# credentials that are specific to your machine.
#
# All paths should be absolute.
#
# Access these values in workflow.py or startup.py via ctx.vars, or reference
# them in ContainerCard YAML mount sources using {{ vars.key }} syntax:
#
#   mounts:
#     - type: bind
#       source: "{{ vars.my_repo }}"
#       target: /app/repo
#
# Example variables (rename / add as needed for your project):
# -----------------------------------------------------------------------------

# SSH credentials (mounted read-only into containers for git/remote access)
# ssh_private_key: "/Users/you/.ssh/id_ed25519"
# ssh_public_key:  "/Users/you/.ssh/id_ed25519.pub"

# Path to a locally cloned source repository
# my_repo: "/Users/you/dev/my-project"
"""

# Directories created by `cutip init` (project-specific subdirs are added per unit)
_CUTIP_DIRS = [
    "cutip/cards",
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
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: ImageCard
metadata:
  # Unique name within your workspace.  ContainerCards reference this via
  # imageRef.ref: images/<name>
  name: hello

spec:
  source: pull
  image: docker.io/library/alpine
  tag: "3.20"

# -----------------------------------------------------------------------------
# BUILD EXAMPLE — uncomment and adapt for a locally built image:
#
# spec:
#   source: build
#   tag: "1.0"
#   context: containers/dockerfiles
#   dockerfile: hello.dockerfile
#   build_args:
#     PYTHON_VERSION: "3.11"
#   buildtime_resources:
#     - src: containers/resources/requirements.txt
#     - src: "{{ vars.my_repo }}/src/package.json"
#       dest: package.json
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
  name: cutip-hello

spec:
  imageRef:
    ref: images/hello

  # Use the default bridge network
  network_mode: bridge

  command: 'sh -c "echo Hello from CUTIP!"'

  environment:
    LANG: "C.UTF-8"

  labels:
    app: cutip-hello
    env: dev

  # -- Bind mounts (sources resolved from cutip/vars.yaml at run time) -------
  # mounts:
  #   - type: bind
  #     source: "{{ vars.my_repo }}"   # resolved from cutip/vars.yaml
  #     target: /app/repo
  #
  #   - type: bind
  #     source: "{{ vars.ssh_private_key }}"
  #     target: /root/.ssh/id_ed25519
  #     read_only: true
  #
  #   - type: bind
  #     source: ./data/sheets          # relative paths resolve against project root
  #     target: /app/sheets
  #     create_host_path: true         # CUTIP creates ./data/sheets if missing

  # -- Named volumes ----------------------------------------------------------
  # volumes:
  #   node_modules_vol: /app/node_modules   # auto-created by CUTIP
"""

_EXAMPLE_UNIT_YAML = """\
# -----------------------------------------------------------------------------
# Unit -- a named, reusable deployment unit backed by a ContainerCard.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: Unit
metadata:
  name: hello

spec:
  containerRef:
    ref: containers/cutip-hello
"""

_EXAMPLE_GROUP_YAML = """\
# -----------------------------------------------------------------------------
# Group -- an ordered set of Units and the workflow that orchestrates them.
#
# Running `cutip run hello` triggers the full CUTIP lifecycle:
#   1. Load cutip/vars.yaml
#   2. Create host directories (create_host_path: true) and named volumes
#   3. Call pre_build(ctx) in each unit's startup.py  [if defined]
#   4. Build / pull images
#   5. Ensure networks
#   6. Remove stale + create fresh containers ({{ vars.key }} mounts resolved)
#   7. Call workflow.main(ctx)  -- starts containers, orchestrates units
#   8. Call startup(ctx) in each unit's startup.py  [if defined]
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: Group
metadata:
  name: hello

spec:
  units:
    - ref: units/hello

  workflow: workflow.py
"""

_EXAMPLE_STARTUP_PY = """\
\"\"\"hello unit startup.

Two optional hooks called by CUTIP:

  pre_build(ctx)  -- BEFORE the image is built.
                     Stage files into the build context (e.g. copy local deps)
                     that must be present when ``podman build`` runs.

  startup(ctx)    -- AFTER workflow.main() starts the container.
                     Health checks, connection instructions, exec commands, etc.

ctx.runtime is the raw PodmanClient -- the full podman-py API is available.
\"\"\"

from __future__ import annotations

from loguru import logger

from cutip.context.workflow import CutipContext
from cutip.models.cards.container import ContainerCard


# Optional: uncomment and implement if you need to stage files before build.
# def pre_build(ctx: CutipContext) -> None:
#     \"\"\"Stage files into the build context before the image is built.\"\"\"
#     import sys
#     from pathlib import Path
#     sys.path.insert(0, str(ctx.project_root / \"scripts\"))
#     from local_deps import stage_local_deps
#     stage_local_deps(
#         src_dir=Path(ctx.vars[\"my_repo\"]) / \"src\",
#         build_context_dir=ctx.project_root / \"containers/dockerfiles/buildtime\",
#         clean=True,
#     )


def startup(ctx: CutipContext) -> None:
    \"\"\"Called by CUTIP after workflow.main() has started the 'hello' container.\"\"\"
    cc = next(c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard))
    cname = cc.metadata.name

    logger.success(f\"Container '{cname}' is running.\")
    logger.info(f\"  Connect:  podman exec -it {cname} /bin/sh\")
"""

_EXAMPLE_WORKFLOW_PY = """\
\"\"\"hello group workflow.

workflow.main() is responsible for starting containers and any cross-unit
orchestration.  For most single-unit projects, it simply starts the container
and lets startup.py handle the rest.

Unit-specific logic (pre_build, post-start tasks, health checks) lives in
each unit's startup.py, not here.
\"\"\"

from __future__ import annotations

from cutip.context.workflow import CutipContext


def main(ctx: CutipContext) -> None:
    \"\"\"Start the hello container.

    CUTIP has already built the image, created the container, and ensured
    the network.  Call .start() here to bring it up, then startup.py
    handles any post-start logic.
    \"\"\"
    ctx.container(\"cutip-hello\").start()
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
        root = self.project_root

        # -- Directories -------------------------------------------------------
        for rel in _CUTIP_DIRS + _RUNTIME_DIRS:
            target = root / rel
            if target.exists():
                logger.debug(f"  exists: {rel}")
            else:
                target.mkdir(parents=True, exist_ok=True)
                logger.debug(f"  created: {rel}")

        # -- Project config ----------------------------------------------------
        self._write_cutip_yaml()

        # -- User vars file (gitignored, filled in by the user) ----------------
        _write_file(
            root / "cutip" / "vars.yaml",
            _CUTIP_VARS_YAML,
            "cutip/vars.yaml",
        )

        # -- Example project (organized by unit name: "hello") -----------------
        _write_file(
            root / "cutip/cards/hello/hello.image.yaml",
            _EXAMPLE_IMAGE_YAML,
            "cutip/cards/hello/hello.image.yaml",
        )
        _write_file(
            root / "cutip/cards/hello/hello.container.yaml",
            _EXAMPLE_CONTAINER_YAML,
            "cutip/cards/hello/hello.container.yaml",
        )
        _write_file(
            root / "cutip/units/hello/hello.unit.yaml",
            _EXAMPLE_UNIT_YAML,
            "cutip/units/hello/hello.unit.yaml",
        )
        _write_file(
            root / "cutip/units/hello/startup.py",
            _EXAMPLE_STARTUP_PY,
            "cutip/units/hello/startup.py",
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
