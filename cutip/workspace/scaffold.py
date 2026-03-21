from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from loguru import logger

_CUTIP_PATHS_YAML = """\
# cutip/paths.yaml — filesystem paths specific to your machine.
#
# This file is gitignored.  It is safe to sync via `cutip push` because it
# contains only filesystem paths, never credentials.
#
# Two sections are supported:
#
#   required:   Values YOU must supply.  CUTIP fails fast if any are empty.
#   generated:  Paths that CUTIP creates automatically relative to the project
#               root.  No manual action needed — just name the directory.
#
# Reference values in ContainerCard YAML mount sources using {{ paths.key }}:
#
#   mounts:
#     - type: bind
#       source: "{{ paths.my_repo }}"
#       target: /app/repo
#
# Access values in workflow.py / startup.py via ctx.paths["key"].
#
# -----------------------------------------------------------------------------

required:
  # Path to a locally cloned source repository
  # my_repo: ""           # e.g. /Users/you/dev/my-project

generated:
  # data_dir: ".cutip-data"   # → created at <project_root>/.cutip-data/
"""

_CUTIP_SECRETS_YAML = """\
# cutip/secrets.yaml — sensitive values. NEVER commit this file.
#
# Passwords, tokens, API keys, and SSH credentials go here.
# This file is gitignored and is never synced via `cutip push`.
#
# Reference values in ContainerCard YAML using {{ secrets.key }}:
#
#   environment:
#     DB_PASSWORD: "{{ secrets.db_password }}"
#
# Access values in workflow.py / startup.py via ctx.secrets["key"].
#
# -----------------------------------------------------------------------------

required:
  # ssh_private_key: ""   # e.g. /Users/you/.ssh/id_ed25519
  # ssh_public_key: ""    # e.g. /Users/you/.ssh/id_ed25519.pub
  # db_password: ""
"""

# Directories created by `cutip init` (project-specific subdirs are added per unit)
_CUTIP_DIRS = [
    "cutip/cards",
    "cutip/units",
    "cutip/groups",
    "resources/dockerfiles",
    "resources/buildtime",
]

_RUNTIME_DIRS = [
    ".cutip/logs",
    ".cutip/cache",
    ".cutip/runs",
    ".cutip/locks",
]

# =============================================================================
# HELLO-WORLD project — single Alpine container demonstrating the full lifecycle
#
# Demonstrates:
#   - prehook.py:       generates build-info.txt before image build
#   - workflow.py:      @action-decorated start + health check + greeting
#   - posthook.py:      prints connection info, verifies container running
#   - orchestrator.py:  minimal ctx.run_unit("hello")
# =============================================================================

_HW_IMAGE_YAML = """\
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: hello

spec:
  source: pull
  image: docker.io/library/alpine
  tag: "3.20"
"""

_HW_CONTAINER_YAML = """\
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: cutip-hello

spec:
  imageRef:
    ref: images/hello

  network_mode: bridge
  command: "tail -f /dev/null"

  environment:
    LANG: "C.UTF-8"

  labels:
    app: cutip-hello
    env: dev
"""

_HW_UNIT_YAML = """\
apiVersion: cutip/v1
kind: Unit
metadata:
  name: hello

spec:
  containerRef:
    ref: containers/cutip-hello
  hooks:
    prehook: prehook.py
    posthook: posthook.py
"""

_HW_GROUP_YAML = """\
apiVersion: cutip/v1
kind: Group
metadata:
  name: hello-world

spec:
  units:
    - ref: units/hello

  orchestrator: orchestrator.py
  workflow: workflow.py
"""

_HW_PREHOOK_PY = """\
\"\"\"hello unit prehook — runs BEFORE the image is built.

Use this to stage files, generate configs, or prepare the build context.
\"\"\"

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from cutip.context.workflow import CutipContext


def main(ctx: CutipContext) -> None:
    \"\"\"Generate build-info.txt with a timestamp.\"\"\"
    info_path = ctx.project_root / "resources" / "buildtime" / "build-info.txt"
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(
        f"Built at: {datetime.now(timezone.utc).isoformat()}\\n",
        encoding="utf-8",
    )
    logger.info("Generated resources/buildtime/build-info.txt")
"""

_HW_WORKFLOW_PY = """\
\"\"\"hello unit workflow — runtime actions for the container.

Each @action carries a name, description, and optional container hint,
enabling static analysis and visualization via `cutip compile`.
\"\"\"

from __future__ import annotations

import time

from loguru import logger

from cutip.context.workflow import CutipContext
from cutip.workflow import action


@action(name="Start Container", description="Start the hello container", container="cutip-hello")
def start_container(ctx: CutipContext) -> None:
    ctx.container("cutip-hello").start()
    logger.info("Container cutip-hello started")


@action(name="Health Check", description="Verify the container is responding")
def health_check(ctx: CutipContext) -> None:
    container = ctx.container("cutip-hello")
    for attempt in range(1, 11):
        exit_code, _ = container.exec_run(["sh", "-c", "echo ok"])
        if exit_code == 0:
            logger.success(f"Health check passed after {attempt} attempt(s)")
            return
        logger.debug(f"  attempt {attempt}/10 — not ready yet")
        time.sleep(1)
    raise RuntimeError("Container did not become ready within 10 seconds")


@action(name="Run Greeting", description="Execute a one-shot greeting in the container")
def run_greeting(ctx: CutipContext) -> None:
    _, output = ctx.container("cutip-hello").exec_run(
        ["sh", "-c", "echo 'hello from cutip'"]
    )
    logger.info(output.decode("utf-8", errors="replace").strip())


def main(ctx: CutipContext) -> None:
    start_container(ctx)
    health_check(ctx)
    run_greeting(ctx)
"""

_HW_POSTHOOK_PY = """\
\"\"\"hello unit posthook — runs AFTER the orchestrator completes.

Use this for verification, printing connection info, or cleanup.
\"\"\"

from __future__ import annotations

from loguru import logger

from cutip.context.workflow import CutipContext


def main(ctx: CutipContext) -> None:
    \"\"\"Print connection info and verify the container is running.\"\"\"
    container = ctx.container("cutip-hello")
    if container.status == "running":
        logger.success("Container cutip-hello is running.")
    else:
        logger.warning(f"Container cutip-hello status: {container.status}")

    logger.info("  Connect:  docker exec -it cutip-hello /bin/sh")
    logger.info("  Stop:     cutip stop hello-world")
"""

_HW_ORCHESTRATOR_PY = """\
\"\"\"hello-world group orchestrator — sequences unit workflows.

The orchestrator runs unit workflows in the order you specify.
For a single-unit group this is trivial; for multi-unit groups
you control the exact startup sequence here.
\"\"\"

from __future__ import annotations

from cutip.context.workflow import CutipContext


def main(ctx: CutipContext) -> None:
    ctx.run_unit("hello")
"""


def _find_project_root() -> Path:
    """Find the CUTIP project root.

    Strategy (first match wins):
    1. Walk up from cwd looking for ``cutip.yaml`` — supports multiple
       CUTIP projects inside a single git repo.
    2. Fall back to the git root (``git rev-parse --show-toplevel``).
    3. Fall back to cwd.
    """
    # 1. Walk up looking for cutip.yaml
    current = Path.cwd().resolve()
    for parent in [current, *current.parents]:
        if (parent / "cutip.yaml").is_file():
            return parent

    # 2. Fall back to git root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 3. Fall back to cwd
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

    def init(self, *, blank: bool = False) -> None:
        """Create the CUTIP workspace structure and example files. Idempotent.

        If *blank* is True, create only the directory structure + cutip.yaml
        without any example artifacts.
        """
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

        # -- User paths + secrets files (gitignored, filled in by the user) -----
        _write_file(
            root / "cutip" / "paths.yaml",
            _CUTIP_PATHS_YAML,
            "cutip/paths.yaml",
        )
        _write_file(
            root / "cutip" / "secrets.yaml",
            _CUTIP_SECRETS_YAML,
            "cutip/secrets.yaml",
        )

        if blank:
            logger.info("Blank workspace ready (no example artifacts).")
            return

        # -- Hello-world project -----------------------------------------------
        _write_file(
            root / "cutip/cards/hello/hello.image.yaml",
            _HW_IMAGE_YAML,
            "cutip/cards/hello/hello.image.yaml",
        )
        _write_file(
            root / "cutip/cards/hello/hello.container.yaml",
            _HW_CONTAINER_YAML,
            "cutip/cards/hello/hello.container.yaml",
        )
        _write_file(
            root / "cutip/units/hello/hello.unit.yaml",
            _HW_UNIT_YAML,
            "cutip/units/hello/hello.unit.yaml",
        )
        _write_file(
            root / "cutip/units/hello/prehook.py",
            _HW_PREHOOK_PY,
            "cutip/units/hello/prehook.py",
        )
        _write_file(
            root / "cutip/units/hello/workflow.py",
            _HW_WORKFLOW_PY,
            "cutip/units/hello/workflow.py",
        )
        _write_file(
            root / "cutip/units/hello/posthook.py",
            _HW_POSTHOOK_PY,
            "cutip/units/hello/posthook.py",
        )
        _write_file(
            root / "cutip/groups/hello-world/group.yaml",
            _HW_GROUP_YAML,
            "cutip/groups/hello-world/group.yaml",
        )
        _write_file(
            root / "cutip/groups/hello-world/orchestrator.py",
            _HW_ORCHESTRATOR_PY,
            "cutip/groups/hello-world/orchestrator.py",
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
                "backend": "docker",
            },
        }
        with config_path.open("w", encoding="utf-8") as fh:
            yaml.dump(doc, fh, default_flow_style=False, sort_keys=False)
        logger.debug("  created: cutip.yaml")
