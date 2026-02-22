"""Docker execution backend.

Connects to the local Docker daemon via docker-py (reads DOCKER_HOST env var
automatically, so CI setups that set DOCKER_HOST work without extra flags).

Dependencies (optional extra): uv add docker
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from loguru import logger

from cutip.backends.base import CutipBackend
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.cards.volume import VolumeCard
from cutip.utils.exceptions import CutipError


class DockerBackend(CutipBackend):
    """Docker backend — connects to the local Docker daemon via docker-py."""

    def __init__(self, client) -> None:
        self._client = client

    @classmethod
    def connect(cls) -> "DockerBackend":
        """Connect to the Docker daemon (respects DOCKER_HOST env var)."""
        try:
            import docker
        except ImportError as exc:
            raise CutipError(
                "The 'docker' package is required for the Docker backend. "
                "Run: uv add docker"
            ) from exc

        try:
            client = docker.from_env()
            client.ping()
        except Exception as exc:
            raise CutipError(
                f"Docker connection failed: {exc}. "
                "Is Docker running? Check DOCKER_HOST if using a remote daemon."
            ) from exc

        logger.info("Docker client connected.")
        return cls(client=client)

    # ── CutipBackend interface ───────────────────────────────────────────────

    def pull_image(self, card: ImageCard) -> None:
        # The alias is how the workflow (and create_container) will reference this image:
        # {card.metadata.name}:{card.spec.tag}  (e.g. "hello:3.20").
        # This mirrors how build_image tags images, making pull/build symmetric.
        alias = f"{card.metadata.name}:{card.spec.tag}"
        image_ref = f"{card.spec.image}:{card.spec.tag}"

        # Idempotent: if alias already exists, nothing to do.
        try:
            self._client.images.get(alias)
            logger.info(f"Image already present as {alias}")
            return
        except Exception:
            pass

        logger.info(f"Pulling image: {image_ref}")
        # docker-py's images.pull() does a GET /images/{ref}/json after the
        # pull to return an Image object.  On Windows, Docker stores official
        # Hub images under the short name ("alpine:3.20") rather than the full
        # registry URL ("docker.io/library/alpine:3.20"), so the post-pull
        # inspect of the full URL returns 404.
        #
        # Fix: strip the "docker.io/library/" prefix before calling pull() so
        # that docker-py inspects the same short name that Docker stored — this
        # is cross-platform safe because Docker normalises "alpine" back to the
        # full registry URL when it pulls.
        pull_repo = card.spec.image
        if pull_repo.startswith("docker.io/library/"):
            pull_repo = pull_repo[len("docker.io/library/"):]

        image = self._client.images.pull(pull_repo, tag=card.spec.tag)

        # Tag the pulled image with the card's canonical alias so that
        # create_container can reference it by name regardless of registry path.
        if alias not in (image.tags or []):
            name, tag = alias.rsplit(":", 1)
            image.tag(name, tag)
            logger.info(f"Tagged {image_ref} -> {alias}")

    def build_image(self, card: ImageCard, project_root: Path | None = None) -> None:
        context = Path(card.spec.context)
        if not context.is_absolute() and project_root:
            context = project_root / context

        dockerfile = card.spec.dockerfile
        tag = f"{card.metadata.name}:{card.spec.tag}"

        cmd = ["docker", "build", "--tag", tag, "--file", dockerfile]
        for k, v in card.spec.build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
        cmd.append(str(context))

        logger.info(f"Building image {tag} from {context}/{dockerfile}")
        result = subprocess.run(cmd, cwd=str(context))
        if result.returncode != 0:
            raise CutipError(f"Image build failed for '{tag}'")

    def ensure_network(self, card: NetworkCard) -> None:
        import docker as docker_mod
        name = card.metadata.name
        try:
            self._client.networks.get(name)
            logger.info(f"Network already exists: {name}")
            return
        except docker_mod.errors.NotFound:
            pass

        ipam = docker_mod.types.IPAMConfig(
            driver="default",
            pool_configs=[
                docker_mod.types.IPAMPool(
                    subnet=card.spec.subnet,
                    gateway=card.spec.gateway,
                )
            ],
        )
        self._client.networks.create(name, driver=card.spec.driver, ipam=ipam)
        logger.info(f"Created network: {name}")

    def ensure_volume(self, card: VolumeCard) -> None:
        import docker as docker_mod
        name = card.metadata.name
        try:
            self._client.volumes.get(name)
            logger.info(f"Volume already exists: {name}")
            return
        except docker_mod.errors.NotFound:
            pass
        self._client.volumes.create(name, driver=card.spec.driver, labels=card.spec.labels)
        logger.info(f"Created volume: {name}")

    def create_container(
        self,
        card: ContainerCard,
        image_name: str | None = None,
    ) -> str:
        """Create (but do not start) a container from a ContainerCard."""
        import docker as docker_mod
        name = card.metadata.name
        try:
            self._client.containers.get(name)
            logger.info(f"Container already exists: {name}")
            return name
        except docker_mod.errors.NotFound:
            pass

        if image_name is None:
            image_name = f"{card.spec.imageRef.ref.split('/')[-1]}:latest"

        kwargs: dict = {
            "name": name,
            "image": image_name,
            "privileged": card.spec.privileged,
            "environment": card.spec.environment or {},
            "cap_add": card.spec.cap_add or [],
            "security_opt": card.spec.security_opts or [],
            "detach": True,
        }

        # Ports: docker-py expects {container_port/proto: host_port}
        if card.spec.ports:
            kwargs["ports"] = card.spec.ports

        if card.spec.network_mode:
            kwargs["network_mode"] = card.spec.network_mode
        elif card.spec.networkRef:
            kwargs["network"] = card.spec.networkRef.ref.split("/")[-1]

        if card.spec.command:
            kwargs["command"] = shlex.split(card.spec.command)
        if card.spec.hostname:
            kwargs["hostname"] = card.spec.hostname
        if card.spec.workdir:
            kwargs["working_dir"] = card.spec.workdir
        if card.spec.restart_policy:
            kwargs["restart_policy"] = {"Name": card.spec.restart_policy}

        # Bind mounts
        if card.spec.mounts:
            kwargs["mounts"] = [
                docker_mod.types.Mount(
                    target=m.target,
                    source=m.source,
                    type=m.type,
                    read_only=(m.mode == "ro"),
                )
                for m in card.spec.mounts
            ]

        # Named volumes: {vol_name: container_path}
        if card.spec.volumes:
            kwargs["volumes"] = {
                vol_name: {"bind": container_path, "mode": "rw"}
                for vol_name, container_path in card.spec.volumes.items()
            }

        self._client.containers.create(**kwargs)
        logger.info(f"Created container: {name}")
        return name

    def start_container(self, name: str) -> None:
        container = self._client.containers.get(name)
        container.start()
        logger.info(f"Started container: {name}")

    def stop_container(self, name: str) -> None:
        try:
            container = self._client.containers.get(name)
            container.stop()
            logger.info(f"Stopped container: {name}")
        except Exception:
            logger.debug(f"stop_container: '{name}' not running or not found.")

    def remove_container(self, name: str) -> None:
        container = self._client.containers.get(name)
        container.remove(force=True)
        logger.info(f"Removed container: {name}")

    def container_status(self, name: str) -> str:
        import docker as docker_mod
        try:
            container = self._client.containers.get(name)
            return container.status
        except docker_mod.errors.NotFound:
            return "not_found"
        except Exception:
            return "unknown"

    def container_logs(self, name: str) -> str:
        """Return stdout + stderr logs for a container as a string."""
        container = self._client.containers.get(name)
        raw = container.logs(stdout=True, stderr=True)
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return b"".join(raw).decode("utf-8", errors="replace")
