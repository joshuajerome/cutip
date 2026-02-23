"""Podman execution backend — container operations.

Connection setup lives in :mod:`cutip.backends.podman.connection`.
This module contains only the :class:`PodmanBackend` class and its
container/image/network/volume operations.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from loguru import logger

from cutip.backends.base import CutipBackend
from cutip.backends.podman.connection import (
    PODMAN_TCP_URL,
    close_ssh_tunnel,
    get_default_connection,
    local_socket_url,
    open_ssh_tunnel,
)
from cutip.backends.shared.build import stage_buildtime_resources
from cutip.backends.shared.image import image_alias, image_ref
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.utils.exceptions import CutipError


class PodmanBackend(CutipBackend):
    """Podman backend — communicates via PodmanClient (SSH tunnel or local socket)."""

    def __init__(self, client, tunnel_process: subprocess.Popen | None = None) -> None:
        self._client = client
        self._tunnel = tunnel_process

    @property
    def client(self):
        """The raw PodmanClient instance. Injected into ctx.runtime for workflows."""
        return self._client

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def connect(cls) -> "PodmanBackend":
        """Open an SSH port-forward tunnel and return a connected backend.

        Reads the default Podman connection from ``podman system connection ls``
        and forwards ``localhost:{PODMAN_TCP_PORT}`` to the Podman socket inside
        the VM.  No daemon service is started inside the guest.
        """
        try:
            from podman import PodmanClient
        except ImportError as exc:
            raise CutipError(
                "The 'podman' package is required. Run: uv add podman"
            ) from exc

        conn = get_default_connection()
        tunnel = open_ssh_tunnel(conn)

        client = PodmanClient(base_url=PODMAN_TCP_URL)
        if not client.ping():
            close_ssh_tunnel(tunnel)
            raise CutipError("Podman ping failed after opening SSH tunnel.")

        logger.info("Podman connected (SSH tunnel).")
        return cls(client=client, tunnel_process=tunnel)

    @classmethod
    def connect_local(cls) -> "PodmanBackend":
        """Connect directly to the local Podman socket (CI / ``--local`` mode)."""
        try:
            from podman import PodmanClient
        except ImportError as exc:
            raise CutipError(
                "The 'podman' package is required. Run: uv add podman"
            ) from exc

        url = local_socket_url()
        client = PodmanClient(base_url=url)

        if not client.ping():
            raise CutipError(
                f"Podman local socket ping failed at {url}. "
                "Is the Podman socket/service running?"
            )

        logger.info(f"Podman connected (local socket: {url}).")
        return cls(client=client, tunnel_process=None)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def disconnect(self) -> None:
        """Close the Podman client and terminate the SSH tunnel (if any)."""
        try:
            self._client.close()
        except Exception:
            pass
        close_ssh_tunnel(self._tunnel)

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
            name, tag = alias.rsplit(":", 1)
            image.tag(name, tag)
            logger.info(f"Tagged {ref} -> {alias}")

    def build_image(self, card: ImageCard, project_root: Path | None = None) -> None:
        context = Path(card.spec.context or "")
        if not context.is_absolute() and project_root:
            context = project_root / context

        # Stage any extra files into {context}/buildtime (or buildtime_dir) before
        # building -- mirrors the podwrap buildtime_resources pattern.
        staging = stage_buildtime_resources(card, project_root)
        build_ctx = staging if card.spec.buildtime_resources else context

        tag = image_alias(card)
        cmd = [
            "podman", "build",
            "--tag", tag,
            "--file", str(context / card.spec.dockerfile),
        ]
        for k, v in card.spec.build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
        cmd.append(str(build_ctx))

        logger.info(f"Building image {tag} from {build_ctx}/{card.spec.dockerfile}")
        result = subprocess.run(cmd, cwd=str(context))
        if result.returncode != 0:
            raise CutipError(f"Image build failed for '{tag}'")

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
        network = ipaddress.IPv4Network(card.spec.subnet, strict=False)
        gateway = card.spec.gateway or str(next(network.hosts()))
        ipam = {
            "Driver": "default",
            "Config": [{"Subnet": str(network), "Gateway": gateway}],
        }
        self._client.networks.create(name, driver=card.spec.driver, ipam=ipam)
        logger.info(f"Created network: {name}")

    # ── Container operations ──────────────────────────────────────────────────

    def create_container(
        self,
        card: ContainerCard,
        image_name: str | None = None,
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
            kwargs["network"] = [card.spec.networkRef.ref.split("/")[-1]]

        if card.spec.command:
            kwargs["command"] = shlex.split(card.spec.command)
        if card.spec.hostname:
            kwargs["hostname"] = card.spec.hostname
        if card.spec.workdir:
            kwargs["working_dir"] = card.spec.workdir
        if card.spec.restart_policy:
            kwargs["restart_policy"] = {"Name": card.spec.restart_policy}
        if card.spec.mounts:
            kwargs["mounts"] = [m.model_dump() for m in card.spec.mounts]
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
