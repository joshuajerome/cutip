from __future__ import annotations

import subprocess
import textwrap
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
# SIMPLE project — single Alpine container, one-shot exec on every `cutip run`
# =============================================================================

_SIMPLE_IMAGE_YAML = """\
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
  name: simple

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
#   context: resources/dockerfiles
#   dockerfile: simple.dockerfile
#   build_args:
#     PYTHON_VERSION: "3.11"
#   buildtime_resources:
#     - src: resources/buildtime/requirements.txt
#     - src: "{{ paths.my_repo }}/src/package.json"
#       dest: package.json
# -----------------------------------------------------------------------------
"""

_SIMPLE_CONTAINER_YAML = """\
# -----------------------------------------------------------------------------
# ContainerCard -- describes a single container: image, network, command,
# environment variables, ports, mounts, volumes, labels, and more.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: cutip-simple

spec:
  imageRef:
    ref: images/simple

  # Use the default bridge network
  network_mode: bridge

  # tail -f /dev/null keeps the container alive indefinitely so you can
  # `podman exec -it cutip-simple /bin/sh` into it at any time.
  # workflow.py execs a one-shot echo on every `cutip run simple`.
  command: "tail -f /dev/null"

  environment:
    LANG: "C.UTF-8"

  labels:
    app: cutip-simple
    env: dev

  # -- Bind mounts (sources resolved from cutip/paths.yaml at run time) ------
  # mounts:
  #   - type: bind
  #     source: "{{ paths.my_repo }}"   # resolved from cutip/paths.yaml
  #     target: /app/repo
  #
  #   - type: bind
  #     source: "{{ secrets.ssh_private_key }}"
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

_SIMPLE_UNIT_YAML = """\
# -----------------------------------------------------------------------------
# Unit -- a named, reusable deployment unit backed by a ContainerCard.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: Unit
metadata:
  name: simple

spec:
  containerRef:
    ref: containers/cutip-simple
"""

_SIMPLE_GROUP_YAML = """\
# -----------------------------------------------------------------------------
# Group -- an ordered set of Units and the workflow that orchestrates them.
#
# Running `cutip run simple` triggers the full CUTIP lifecycle:
#   1. Load cutip/paths.yaml + cutip/secrets.yaml
#   2. Create host directories (create_host_path: true) and named volumes
#   3. Call pre_build(ctx) in each unit's startup.py  [if defined]
#   4. Build / pull images
#   5. Ensure networks
#   6. Remove stale + create fresh containers ({{ paths.key }} mounts resolved)
#   7. Call workflow.main(ctx)  -- starts containers, orchestrates units
#   8. Call startup(ctx) in each unit's startup.py  [if defined]
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: Group
metadata:
  name: simple

spec:
  units:
    - ref: units/simple

  workflow: workflow.py
"""

_SIMPLE_STARTUP_PY = """\
\"\"\"simple unit startup.

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
#         src_dir=Path(ctx.paths[\"my_repo\"]) / \"src\",
#         build_context_dir=ctx.project_root / \"resources/dockerfiles\",
#         clean=True,
#     )


def startup(ctx: CutipContext) -> None:
    \"\"\"Called by CUTIP after workflow.main() has started the 'simple' container.\"\"\"
    cc = next(c for c in ctx.resolved_cards.values() if isinstance(c, ContainerCard))
    cname = cc.metadata.name

    logger.success(f\"Container '{cname}' is running (tail -f /dev/null).\")
    logger.info(f\"  Connect:  podman exec -it {cname} /bin/sh\")
    logger.info(f\"  Stop:     podman stop {cname}\")
"""

_SIMPLE_WORKFLOW_PY = """\
\"\"\"simple group workflow.

Demonstrates CUTIP's @action/@orchestrator decorators for self-describing
workflows.  Each action carries a name, description, and optional container
hint — enabling static analysis and visualization by external tools.

Unit-specific logic (pre_build, post-start tasks) lives in each unit's
startup.py, not here.
\"\"\"

from __future__ import annotations

import time

from loguru import logger

from cutip.context.workflow import CutipContext
from cutip.workflow import action, orchestrator


@action(name="Start Container", description="Start the simple container", container="cutip-simple")
def start_container(ctx: CutipContext) -> None:
    ctx.container(\"cutip-simple\").start()
    logger.info(\"Container cutip-simple started\")


@action(name="Health Check", description="Verify the container is responding")
def health_check(ctx: CutipContext) -> None:
    container = ctx.container(\"cutip-simple\")
    for attempt in range(1, 11):
        exit_code, _ = container.exec_run([\"sh\", \"-c\", \"echo ok\"])
        if exit_code == 0:
            logger.success(f\"Health check passed after {attempt} attempt(s)\")
            return
        logger.debug(f\"  attempt {attempt}/10 — not ready yet\")
        time.sleep(1)
    raise RuntimeError(\"Container did not become ready within 10 seconds\")


@action(name="Run Greeting", description="Execute a one-shot greeting in the container")
def run_greeting(ctx: CutipContext) -> None:
    _, output = ctx.container(\"cutip-simple\").exec_run(
        [\"sh\", \"-c\", \"echo 'hello from container'\"]
    )
    logger.info(output.decode(\"utf-8\", errors=\"replace\").strip())


@orchestrator
def main(ctx: CutipContext) -> None:
    start_container(ctx)
    health_check(ctx)
    run_greeting(ctx)
"""

# =============================================================================
# COMPLEX project — PostgreSQL + Python web app
#
# Demonstrates:
#   - pre_build(ctx): generates config.yaml into build context before podman build
#   - workflow.py health-check loop: exec psql to confirm postgres is ready
#   - NetworkCard: isolated bridge network shared by db and web containers
#   - startup(ctx): exec-based post-start verification for the web container
#   - secrets.yaml: required db_password; paths.yaml: generated db_data_dir
# =============================================================================

_COMPLEX_VARS_YAML_COMMENT = """\
# Add these entries for the complex project:
#
# cutip/secrets.yaml:
#   required:
#     db_password: ""        # must be filled in before cutip run complex
#
# cutip/paths.yaml:
#   generated:
#     db_data_dir: ".cutip-complex-data"   # CUTIP creates this automatically
"""

_COMPLEX_NETWORK_YAML = """\
# -----------------------------------------------------------------------------
# NetworkCard -- defines an isolated bridge network for the complex project.
#
# Both the database (cutip-db) and web (cutip-web) containers attach to this
# network so they can communicate by container name.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: NetworkCard
metadata:
  name: app-net

spec:
  driver: bridge
  subnet: "172.20.0.0/24"
  gateway: "172.20.0.1"
"""

_COMPLEX_DB_IMAGE_YAML = """\
# -----------------------------------------------------------------------------
# ImageCard -- PostgreSQL 16 pulled from Docker Hub.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: db

spec:
  source: pull
  image: docker.io/library/postgres
  tag: "16"
"""

_COMPLEX_DB_CONTAINER_YAML = """\
# -----------------------------------------------------------------------------
# ContainerCard -- PostgreSQL database container.
#
# The password is read from cutip/secrets.yaml at run time.  CUTIP validates
# that {{ secrets.db_password }} is non-empty before creating any container.
#
# The data volume (db_data) is auto-created by CUTIP as a named Podman volume.
# The generated db_data_dir var creates a host-side directory that you can use
# for pg_dump backups or direct inspection.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: cutip-db

spec:
  imageRef:
    ref: images/db

  networkRef:
    ref: networks/app-net

  environment:
    POSTGRES_DB: appdb
    POSTGRES_USER: appuser
    POSTGRES_PASSWORD: "{{ secrets.db_password }}"

  # Named volume — auto-created by CUTIP.
  volumes:
    db_data: /var/lib/postgresql/data

  labels:
    app: cutip-complex
    role: database
"""

_COMPLEX_WEB_IMAGE_YAML = """\
# -----------------------------------------------------------------------------
# ImageCard -- Python web app built locally.
#
# The Dockerfile lives in resources/dockerfiles/.
# pre_build(ctx) in cutip/units/web/startup.py generates config.yaml into
# resources/buildtime/ before podman build runs.  CUTIP's buildtime_resources
# stages it into the build context so the Dockerfile can COPY it.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: ImageCard
metadata:
  name: web

spec:
  source: build
  tag: "latest"
  context: resources/dockerfiles
  dockerfile: web.dockerfile
  buildtime_resources:
    - src: resources/buildtime/config.yaml   # generated by pre_build(ctx)
      dest: config.yaml                       # available as COPY config.yaml ... in Dockerfile
"""

_COMPLEX_WEB_CONTAINER_YAML = """\
# -----------------------------------------------------------------------------
# ContainerCard -- Python web application container.
#
# Shares the app-net network with the database so it can reach cutip-db by
# container name (e.g. host=cutip-db in the database URL).
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: ContainerCard
metadata:
  name: cutip-web

spec:
  imageRef:
    ref: images/web

  networkRef:
    ref: networks/app-net

  # Expose the app on host port 8080 → container port 8080
  ports:
    "8080/tcp": "8080"

  labels:
    app: cutip-complex
    role: web
"""

_COMPLEX_DB_UNIT_YAML = """\
apiVersion: cutip/v1
kind: Unit
metadata:
  name: db

spec:
  containerRef:
    ref: containers/cutip-db
"""

_COMPLEX_DB_STARTUP_PY = """\
\"\"\"complex/db unit startup.

Optional hooks — uncomment and implement as needed.

  pre_build(ctx)  -- runs before the db image is built (not needed for a pull
                     image, but available if you switch to a custom postgres image)

  startup(ctx)    -- runs after workflow.main() confirms the database is ready.
                     Useful for running migrations, seeding data, etc.
\"\"\"

from __future__ import annotations

# from loguru import logger
# from cutip.context.workflow import CutipContext


# def pre_build(ctx: CutipContext) -> None:
#     \"\"\"Optional: stage files before the db image is built.\"\"\"
#     pass


# def startup(ctx: CutipContext) -> None:
#     \"\"\"Optional: run after the database is confirmed ready.\"\"\"
#     logger.info(\"Running database migrations...\")
#     ctx.container(\"cutip-db\").exec_run([\"psql\", \"-U\", \"appuser\", \"-d\", \"appdb\", \"-f\", \"/migrations/001_init.sql\"])
"""

_COMPLEX_WEB_UNIT_YAML = """\
apiVersion: cutip/v1
kind: Unit
metadata:
  name: web

spec:
  containerRef:
    ref: containers/cutip-web
"""

_COMPLEX_WEB_STARTUP_PY = """\
\"\"\"complex/web unit startup.

  pre_build(ctx)  -- generates config.yaml into resources/buildtime/ before
                     the web image is built.  CUTIP's buildtime_resources in
                     web.image.yaml stages it into the build context.

  startup(ctx)    -- verifies the web app is serving after the container starts.
\"\"\"

from __future__ import annotations

import yaml
from loguru import logger

from cutip.context.workflow import CutipContext


def pre_build(ctx: CutipContext) -> None:
    \"\"\"Generate config.yaml into resources/buildtime/ before podman build runs.\"\"\"
    config = {
        \"database\": {
            \"host\": \"cutip-db\",          # container name — reachable on app-net
            \"port\": 5432,
            \"name\": \"appdb\",
            \"user\": \"appuser\",
        },
        \"app\": {
            \"debug\": False,
            \"port\": 8080,
        },
    }

    config_path = ctx.project_root / \"resources\" / \"buildtime\" / \"config.yaml\"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.dump(config))
    logger.info(\"Generated resources/buildtime/config.yaml\")


def startup(ctx: CutipContext) -> None:
    \"\"\"Verify the web app is serving after it starts.\"\"\"
    exit_code, output = ctx.container(\"cutip-web\").exec_run(
        [\"curl\", \"-sf\", \"http://localhost:8080/health\"]
    )
    if exit_code == 0:
        logger.success(\"Web app is serving at http://localhost:8080\")
    else:
        logger.warning(f\"Health endpoint returned non-zero exit code: {exit_code}\")

    logger.info(\"  DB shell:   podman exec -it cutip-db psql -U appuser -d appdb\")
    logger.info(\"  Web shell:  podman exec -it cutip-web /bin/sh\")
    logger.info(\"  Stop all:   podman stop cutip-db cutip-web\")
"""

_COMPLEX_GROUP_YAML = """\
# -----------------------------------------------------------------------------
# Group -- PostgreSQL + web app.
#
# The workflow starts the database, waits for it to be ready (health-check loop
# via exec_run), then starts the web app.  See workflow.py for the full logic.
# -----------------------------------------------------------------------------
apiVersion: cutip/v1
kind: Group
metadata:
  name: complex

spec:
  units:
    - ref: units/db
    - ref: units/web

  workflow: workflow.py
"""

_COMPLEX_WORKFLOW_PY = """\
\"\"\"complex group workflow.

Demonstrates multi-container orchestration with @action/@orchestrator decorators.
Each action is self-describing — external tools can extract the execution graph
without importing this module.

This is the key demonstration of CUTIP vs docker-compose: startup ordering
is expressed as Python, not as a healthcheck declaration.  You can log
progress, branch on failure, or take corrective action — all in decorated
action functions.
\"\"\"

from __future__ import annotations

import time

from loguru import logger

from cutip.context.workflow import CutipContext
from cutip.workflow import action, orchestrator


@action(name="Start Database", description="Start PostgreSQL container", container="cutip-db")
def start_database(ctx: CutipContext) -> None:
    ctx.container(\"cutip-db\").start()
    logger.info(\"PostgreSQL container started\")


@action(name="Wait for Database", description="Poll until PostgreSQL accepts connections", container="cutip-db")
def wait_for_database(ctx: CutipContext) -> None:
    db = ctx.container(\"cutip-db\")
    db_password = ctx.secrets[\"db_password\"]

    for attempt in range(1, 31):
        exit_code, _ = db.exec_run(
            [\"psql\", \"-U\", \"appuser\", \"-d\", \"appdb\", \"-c\", \"SELECT 1\"],
            environment={\"PGPASSWORD\": db_password},
        )
        if exit_code == 0:
            logger.success(f\"Postgres ready after {attempt} attempt(s)\")
            return
        logger.debug(f\"  attempt {attempt}/30 — postgres not ready yet\")
        time.sleep(1)

    raise RuntimeError(
        \"Postgres did not become ready within 30 seconds. \"
        \"Check 'podman logs cutip-db' for details.\"
    )


@action(name="Run Migrations", description="Apply database schema migrations", container="cutip-db")
def run_migrations(ctx: CutipContext) -> None:
    db = ctx.container(\"cutip-db\")
    db_password = ctx.secrets[\"db_password\"]

    exit_code, output = db.exec_run(
        [
            \"psql\", \"-U\", \"appuser\", \"-d\", \"appdb\", \"-c\",
            \"CREATE TABLE IF NOT EXISTS app_migrations (id SERIAL PRIMARY KEY, applied_at TIMESTAMP DEFAULT NOW())\",
        ],
        environment={\"PGPASSWORD\": db_password},
    )
    if exit_code == 0:
        logger.success(\"Database migrations applied\")
    else:
        logger.warning(f\"Migration returned exit code {exit_code}\")


@action(name="Start Web App", description="Start the web application container", container="cutip-web")
def start_web(ctx: CutipContext) -> None:
    ctx.container(\"cutip-web\").start()
    logger.info(\"Web app container started\")


@action(name="Verify Web App", description="Confirm web app is serving", container="cutip-web")
def verify_web(ctx: CutipContext) -> None:
    web = ctx.container(\"cutip-web\")

    for attempt in range(1, 11):
        exit_code, _ = web.exec_run(
            [\"curl\", \"-sf\", \"http://localhost:8080/health\"]
        )
        if exit_code == 0:
            logger.success(f\"Web app healthy after {attempt} attempt(s)\")
            return
        logger.debug(f\"  attempt {attempt}/10 — web app not ready yet\")
        time.sleep(1)

    logger.warning(\"Web app health check did not pass — container may still be starting\")


@orchestrator
def main(ctx: CutipContext) -> None:
    start_database(ctx)
    wait_for_database(ctx)
    run_migrations(ctx)
    start_web(ctx)
    verify_web(ctx)
"""

_COMPLEX_WEB_DOCKERFILE = """\
# resources/dockerfiles/web.dockerfile
# Minimal Python web app stub for the CUTIP complex example.
#
# config.yaml is generated by pre_build(ctx) in cutip/units/web/startup.py
# and staged here by CUTIP's buildtime_resources before the build runs.

FROM python:3.11-slim

WORKDIR /app

# Install dependencies — replace with your actual requirements
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# config.yaml generated by pre_build and staged by buildtime_resources
COPY config.yaml /app/config.yaml

# Add your application source files here, e.g.:
# COPY app.py /app/app.py

# Placeholder entrypoint — replace with your actual server command
CMD ["python", "-c", "import time; print('cutip-web started'); time.sleep(86400)"]
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

        # -- Simple project (single Alpine container) --------------------------
        _write_file(
            root / "cutip/cards/simple/simple.image.yaml",
            _SIMPLE_IMAGE_YAML,
            "cutip/cards/simple/simple.image.yaml",
        )
        _write_file(
            root / "cutip/cards/simple/simple.container.yaml",
            _SIMPLE_CONTAINER_YAML,
            "cutip/cards/simple/simple.container.yaml",
        )
        _write_file(
            root / "cutip/units/simple/simple.unit.yaml",
            _SIMPLE_UNIT_YAML,
            "cutip/units/simple/simple.unit.yaml",
        )
        _write_file(
            root / "cutip/units/simple/startup.py",
            _SIMPLE_STARTUP_PY,
            "cutip/units/simple/startup.py",
        )
        _write_file(
            root / "cutip/groups/simple/group.yaml",
            _SIMPLE_GROUP_YAML,
            "cutip/groups/simple/group.yaml",
        )
        _write_file(
            root / "cutip/groups/simple/workflow.py",
            _SIMPLE_WORKFLOW_PY,
            "cutip/groups/simple/workflow.py",
        )

        # -- Complex project (PostgreSQL + Python web app) ---------------------
        _write_file(
            root / "cutip/cards/app-net/app-net.network.yaml",
            _COMPLEX_NETWORK_YAML,
            "cutip/cards/app-net/app-net.network.yaml",
        )
        _write_file(
            root / "cutip/cards/db/db.image.yaml",
            _COMPLEX_DB_IMAGE_YAML,
            "cutip/cards/db/db.image.yaml",
        )
        _write_file(
            root / "cutip/cards/db/db.container.yaml",
            _COMPLEX_DB_CONTAINER_YAML,
            "cutip/cards/db/db.container.yaml",
        )
        _write_file(
            root / "cutip/cards/web/web.image.yaml",
            _COMPLEX_WEB_IMAGE_YAML,
            "cutip/cards/web/web.image.yaml",
        )
        _write_file(
            root / "cutip/cards/web/web.container.yaml",
            _COMPLEX_WEB_CONTAINER_YAML,
            "cutip/cards/web/web.container.yaml",
        )
        _write_file(
            root / "cutip/units/db/db.unit.yaml",
            _COMPLEX_DB_UNIT_YAML,
            "cutip/units/db/db.unit.yaml",
        )
        _write_file(
            root / "cutip/units/db/startup.py",
            _COMPLEX_DB_STARTUP_PY,
            "cutip/units/db/startup.py",
        )
        _write_file(
            root / "cutip/units/web/web.unit.yaml",
            _COMPLEX_WEB_UNIT_YAML,
            "cutip/units/web/web.unit.yaml",
        )
        _write_file(
            root / "cutip/units/web/startup.py",
            _COMPLEX_WEB_STARTUP_PY,
            "cutip/units/web/startup.py",
        )
        _write_file(
            root / "cutip/groups/complex/group.yaml",
            _COMPLEX_GROUP_YAML,
            "cutip/groups/complex/group.yaml",
        )
        _write_file(
            root / "cutip/groups/complex/workflow.py",
            _COMPLEX_WORKFLOW_PY,
            "cutip/groups/complex/workflow.py",
        )
        _write_file(
            root / "resources/dockerfiles/web.dockerfile",
            _COMPLEX_WEB_DOCKERFILE,
            "resources/dockerfiles/web.dockerfile",
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
