"""Docker execution backend — container operations.

Connection setup lives in :mod:`cutip.backends.docker.connection`.
This module contains only the :class:`DockerBackend` class and its
container/image/network/volume operations.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from loguru import logger

from cutip.backends.base import CutipBackend
from cutip.backends.docker.connection import connect_client
from cutip.backends.shared.image import image_alias, image_ref
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.cards.volume import VolumeCard
from cutip.utils.exceptions import CutipError


class DockerBackend(CutipBackend):
    """Docker backend — connects to the local Docker daemon via docker-py."""

    def __init__(self, client) -> None:
        self._client = client

    # ── Constructor ───────────────────────────────────────────────────────────

    @classmethod
    def connect(cls) -> "DockerBackend":
        """Connect to the Docker daemon and return a connected backend.

        Respects ``DOCKER_HOST`` automatically via docker-py.
        """
        client = connect_client()
        return cls(client=client)

    # ── Image operations ──────────────────────────────────────────────────────

    def pull_image(self, card: ImageCard) -> None:
        alias = image_alias(card)
        ref   = image_ref(card)

        # Idempotent: skip if the alias already exists locally.
        try:
            self._client.images.get(alias)
            logger.info(f"Image already present: {alias}")
            return
        except Exception:
            pass

        logger.info(f"Pulling image: {ref}")

        # Use the low-level streaming API to:
        #   (a) surface real error messages embedded in the response stream, and
        #   (b) avoid the unreliable post-pull inspect that docker-py's high-level
        #       images.pull() performs (causes 404s on Windows with normalised names).
        #
        # Strip "docker.io/library/" so the pull ref matches the local short name
        # across all platforms.
        pull_repo = card.spec.image
        if pull_repo.startswith("docker.io/library/"):
            pull_repo = pull_repo[len("docker.io/library/"):]

        for line in self._client.api.pull(
            pull_repo, tag=card.spec.tag, stream=True, decode=True
        ):
            if isinstance(line, dict) and "error" in line:
                raise CutipError(f"Pull failed for {ref}: {line['error']}")

        # Locate the image — short name first (Windows), then full ref.
        image = None
        for lookup in (f"{pull_repo}:{card.spec.tag}", ref):
            try:
                image = self._client.images.get(lookup)
                break
            except Exception:
                continue

        if image is None:
            raise CutipError(
                f"Pulled {ref} but could not find it locally "
                f"(tried: {pull_repo}:{card.spec.tag}, {ref})."
            )

        # Tag with the canonical alias so create_container can reference
        # the image by card name regardless of how Docker stored it.
        if alias not in (image.tags or []):
            name, tag = alias.rsplit(":", 1)
            image.tag(name, tag)
            logger.info(f"Tagged {ref} -> {alias}")

    def build_image(self, card: ImageCard, project_root: Path | None = None) -> None:
        context = Path(card.spec.context)
        if not context.is_absolute() and project_root:
            context = project_root / context

        tag = image_alias(card)
        cmd = ["docker", "build", "--tag", tag, "--file", card.spec.dockerfile]
        for k, v in card.spec.build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
        cmd.append(str(context))

        logger.info(f"Building image {tag} from {context}/{card.spec.dockerfile}")
        result = subprocess.run(cmd, cwd=str(context))
        if result.returncode != 0:
            raise CutipError(f"Image build failed for '{tag}'")

    # ── Network / volume operations ───────────────────────────────────────────

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

    # ── Container operations ──────────────────────────────────────────────────

    def create_container(
        self,
        card: ContainerCard,
        image_name: str | None = None,
    ) -> str:
        """Create (but do not start) a container. Returns the container name."""
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
        if card.spec.volumes:
            kwargs["volumes"] = {
                vol: {"bind": path, "mode": "rw"}
                for vol, path in card.spec.volumes.items()
            }

        self._client.containers.create(**kwargs)
        logger.info(f"Created container: {name}")
        return name

    def start_container(self, name: str) -> None:
        self._client.containers.get(name).start()
        logger.info(f"Started container: {name}")

    def stop_container(self, name: str) -> None:
        try:
            self._client.containers.get(name).stop()
            logger.info(f"Stopped container: {name}")
        except Exception:
            logger.debug(f"stop_container: '{name}' not running or not found.")

    def remove_container(self, name: str) -> None:
        self._client.containers.get(name).remove(force=True)
        logger.info(f"Removed container: {name}")

    def container_status(self, name: str) -> str:
        import docker as docker_mod
        try:
            return self._client.containers.get(name).status
        except docker_mod.errors.NotFound:
            return "not_found"
        except Exception:
            return "unknown"

    def container_logs(self, name: str) -> str:
        raw = self._client.containers.get(name).logs(stdout=True, stderr=True)
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return b"".join(raw).decode("utf-8", errors="replace")
