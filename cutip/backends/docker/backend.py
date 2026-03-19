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
from cutip.backends.docker.connection import connect_docker_client
from cutip.backends.shared.build import stage_buildtime_resources
from cutip.backends.shared.image import image_alias, image_ref
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.utils.exceptions import CutipError


class DockerBackend(CutipBackend):
    """Docker backend — communicates via DockerClient (local daemon)."""

    def __init__(self, client) -> None:
        self._client = client

    @property
    def client(self):
        """The raw DockerClient instance. Injected into ctx.runtime for workflows."""
        return self._client

    # ── Constructor ───────────────────────────────────────────────────────────

    @classmethod
    def connect(cls) -> "DockerBackend":
        """Connect to the local Docker daemon and return a backend instance."""
        client = connect_docker_client()
        return cls(client=client)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def disconnect(self) -> None:
        """Close the Docker client."""
        try:
            self._client.close()
        except Exception:
            pass

    # ── Image operations ──────────────────────────────────────────────────────

    def pull_image(self, card: ImageCard) -> None:
        alias = image_alias(card)
        ref   = image_ref(card)

        # Idempotent: skip if the alias already exists locally.
        all_tags = {t for img in self._client.images.list() for t in (img.tags or [])}
        if alias in all_tags:
            logger.info(f"Image already present: {alias}")
            return

        logger.info(f"Pulling image: {ref}")
        image = self._client.images.pull(card.spec.image, tag=card.spec.tag)

        # Tag with the card's canonical alias so create_container can reference
        # the image by card name regardless of registry path.
        if alias != ref:
            image.tag(alias)
            logger.info(f"Tagged {ref} -> {alias}")

    def build_image(
        self,
        card: ImageCard,
        project_root: Path | None = None,
        vars: dict | None = None,
        no_cache: bool = False,
    ) -> None:
        context = Path(card.spec.context or "")
        if not context.is_absolute() and project_root:
            context = project_root / context

        # Stage any extra files into {context}/buildtime before building.
        staging = stage_buildtime_resources(card, project_root, vars=vars)
        build_ctx = staging if card.spec.buildtime_resources else context

        tag = image_alias(card)
        cmd = [
            "docker", "build",
            "--tag", tag,
            "--file", str(context / card.spec.dockerfile),
        ]
        if no_cache:
            cmd.append("--no-cache")
        for k, v in card.spec.build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
        cmd.append(str(build_ctx))

        logger.info(f"Building image {tag} from {build_ctx}/{card.spec.dockerfile}")

        process = subprocess.Popen(
            cmd,
            cwd=str(context),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        for raw in process.stdout:
            logger.bind(subprocess=True).debug(raw.rstrip("\n"))
        rc = process.wait()
        if rc != 0:
            raise CutipError(f"Image build failed for '{tag}'")

    def remove_image(self, name: str) -> None:
        try:
            self._client.images.remove(name, force=True)
            logger.info(f"Removed image: {name}")
        except Exception:
            logger.debug(f"remove_image: '{name}' not found.")

    # ── Network / volume operations ───────────────────────────────────────────

    def ensure_network(self, card: NetworkCard) -> None:
        name = card.metadata.name
        try:
            self._client.networks.get(name)
            logger.info(f"Network already exists: {name}")
            return
        except Exception:
            pass

        import ipaddress
        import docker.types

        network = ipaddress.IPv4Network(card.spec.subnet, strict=False)
        gateway = card.spec.gateway or str(next(network.hosts()))
        ipam_pool = docker.types.IPAMPool(subnet=str(network), gateway=gateway)
        ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])
        self._client.networks.create(name, driver=card.spec.driver, ipam=ipam_config)
        logger.info(f"Created network: {name}")

    def ensure_default_network(self, name: str) -> None:
        """Create a default bridge network by name if it does not exist."""
        try:
            self._client.networks.get(name)
            logger.info(f"Default network already exists: {name}")
            return
        except Exception:
            pass
        self._client.networks.create(name, driver="bridge")
        logger.info(f"Created default bridge network: {name}")

    # ── Container operations ──────────────────────────────────────────────────

    def create_container(
        self,
        card: ContainerCard,
        image_name: str | None = None,
        default_network: str | None = None,
    ) -> str:
        """Create (but do not start) a container. Returns the container name."""
        name = card.metadata.name
        try:
            self._client.containers.get(name)
            logger.info(f"Container already exists: {name}")
            return name
        except Exception:
            pass

        if image_name is None:
            image_name = f"{card.spec.imageRef.ref.split('/')[-1]}:latest"

        kwargs: dict = {
            "name": name,
            "image": image_name,
            "privileged": card.spec.privileged,
            "ports": card.spec.ports or {},
            "environment": card.spec.environment or {},
            "cap_add": card.spec.cap_add or [],
            "security_opt": card.spec.security_opts or [],
            "detach": True,
        }

        if card.spec.network_mode:
            kwargs["network_mode"] = card.spec.network_mode
        elif card.spec.networkRef:
            kwargs["network"] = card.spec.networkRef.ref.split("/")[-1]
        elif default_network:
            kwargs["network"] = default_network

        if card.spec.command:
            kwargs["command"] = shlex.split(card.spec.command)
        if card.spec.hostname:
            kwargs["hostname"] = card.spec.hostname
        if card.spec.workdir:
            kwargs["working_dir"] = card.spec.workdir
        if card.spec.restart_policy:
            kwargs["restart_policy"] = {"Name": card.spec.restart_policy}
        if card.spec.mounts:
            # Docker Desktop handles Windows paths natively — no WSL translation needed.
            _DOCKER_MOUNT_KEYS = {"type", "source", "target", "read_only"}
            mounts = []
            for m in card.spec.mounts:
                d = {k: v for k, v in m.model_dump().items() if k in _DOCKER_MOUNT_KEYS}
                mounts.append(d)
            kwargs["mounts"] = mounts
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
        try:
            return self._client.containers.get(name).status
        except Exception:
            return "not_found"

    def container_logs(self, name: str) -> str:
        raw = self._client.containers.get(name).logs(stdout=True, stderr=True)
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return b"".join(raw).decode("utf-8", errors="replace")
