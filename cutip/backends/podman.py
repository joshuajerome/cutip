"""Podman execution backend.

Communicates with Podman via TCP-over-SSH tunnel, mirroring the approach
established in podwrap/shared/setup.py and podwrap/shared/core/.

Dependencies (optional extra): uv add podman
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from cutip.backends.base import CutipBackend
from cutip.models.cards.container import ContainerCard
from cutip.models.cards.image import ImageCard
from cutip.models.cards.network import NetworkCard
from cutip.models.cards.volume import VolumeCard
from cutip.utils.exceptions import CutipError

if TYPE_CHECKING:
    pass

_PODMAN_TCP_PORT = 8080
_PODMAN_TCP_URL = f"tcp://localhost:{_PODMAN_TCP_PORT}"


def _get_default_podman_connection() -> dict:
    """Run 'podman system connection ls' and return the default connection as a dict."""
    try:
        result = subprocess.run(
            ["podman", "system", "connection", "ls"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise CutipError("Could not list Podman connections. Is Podman installed?") from exc

    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        raise CutipError("No Podman connections found. Run 'podman machine start' first.")

    headers = lines[0].split()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < len(headers):
            continue
        conn = dict(zip(headers, parts))
        if conn.get("Default", "").lower() == "true":
            return conn

    raise CutipError("No default Podman connection found.")


def _open_ssh_tunnel(connection: dict) -> subprocess.Popen:
    """Open a TCP-over-SSH tunnel to the Podman socket. Returns the tunnel process."""
    uri: str = connection.get("URI", "")
    identity: str = connection.get("Identity", "")

    # Parse: ssh://user@host:port/path
    without_scheme = uri.replace("ssh://", "")
    user_host_port, _ = without_scheme.split("/", 1) if "/" in without_scheme else (without_scheme, "")
    if "@" in user_host_port:
        user, host_port = user_host_port.split("@", 1)
    else:
        user, host_port = "root", user_host_port
    if ":" in host_port:
        host, port = host_port.rsplit(":", 1)
    else:
        host, port = host_port, "22"

    ssh_cmd = [
        "ssh", "-n",
        "-i", identity,
        "-p", port,
        f"{user}@{host}",
        "-o", "StrictHostKeyChecking=no",
        "-T",
        f"podman system service --time=0 tcp:127.0.0.1:{_PODMAN_TCP_PORT}",
    ]

    logger.debug(f"Opening SSH tunnel: {' '.join(ssh_cmd)}")
    process = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)

    if process.poll() is not None:
        raise CutipError("SSH tunnel process exited prematurely. Check Podman connection.")

    logger.info(f"Podman SSH tunnel established on {_PODMAN_TCP_URL}")
    return process


class PodmanBackend(CutipBackend):
    """Podman backend — uses PodmanClient over a TCP-over-SSH tunnel."""

    def __init__(self, client, tunnel_process: subprocess.Popen | None = None) -> None:
        self._client = client
        self._tunnel = tunnel_process

    @classmethod
    def connect(cls) -> "PodmanBackend":
        """Establish SSH tunnel and return a connected PodmanBackend."""
        try:
            from podman import PodmanClient
        except ImportError as exc:
            raise CutipError(
                "The 'podman' package is required for the Podman backend. "
                "Run: uv add podman"
            ) from exc

        connection = _get_default_podman_connection()
        tunnel = _open_ssh_tunnel(connection)
        client = PodmanClient(base_url=_PODMAN_TCP_URL)

        if not client.ping():
            tunnel.terminate()
            raise CutipError("Podman client ping failed after opening SSH tunnel.")

        logger.info("Podman client connected.")
        return cls(client=client, tunnel_process=tunnel)

    def disconnect(self) -> None:
        """Close the client and terminate the SSH tunnel."""
        try:
            self._client.close()
        except Exception:
            pass
        if self._tunnel and self._tunnel.poll() is None:
            self._tunnel.terminate()
            logger.debug("SSH tunnel closed.")

    # ------------------------------------------------------------------ #
    # CutipBackend interface                                               #
    # ------------------------------------------------------------------ #

    def pull_image(self, card: ImageCard) -> None:
        image_ref = f"{card.spec.image}:{card.spec.tag}"
        existing = [img for img in self._client.images.list() if image_ref in (img.tags or [])]
        if existing:
            logger.info(f"Image already present: {image_ref}")
            return
        logger.info(f"Pulling image: {image_ref}")
        self._client.images.pull(card.spec.image, tag=card.spec.tag)

    def build_image(self, card: ImageCard, project_root: Path | None = None) -> None:
        # Resolve context relative to project_root when it is a relative path
        context = Path(card.spec.context)
        if not context.is_absolute() and project_root:
            context = project_root / context

        dockerfile = card.spec.dockerfile
        tag = f"{card.metadata.name}:{card.spec.tag}"

        cmd = ["podman", "build", "--tag", tag, "--file", dockerfile]
        for k, v in card.spec.build_args.items():
            cmd += ["--build-arg", f"{k}={v}"]
        cmd.append(str(context))

        logger.info(f"Building image {tag} from {context}/{dockerfile}")
        result = subprocess.run(cmd, cwd=str(context))
        if result.returncode != 0:
            raise CutipError(f"Image build failed for '{tag}'")

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
        ipam = {
            "Driver": "default",
            "Config": [{"Subnet": str(network), "Gateway": card.spec.gateway or str(next(network.hosts()))}],
        }
        self._client.networks.create(name, driver=card.spec.driver, ipam=ipam)
        logger.info(f"Created network: {name}")

    def ensure_volume(self, card: VolumeCard) -> None:
        name = card.metadata.name
        existing = [v for v in self._client.volumes.list() if v.name == name]
        if existing:
            logger.info(f"Volume already exists: {name}")
            return
        self._client.volumes.create(name, driver=card.spec.driver, labels=card.spec.labels)
        logger.info(f"Created volume: {name}")

    def create_container(
        self,
        card: ContainerCard,
        image_name: str | None = None,
    ) -> str:
        """Create a container from a ContainerCard.

        Args:
            card:       The ContainerCard definition.
            image_name: Explicit ``name:tag`` string for the image. When omitted,
                        the image is derived from ``card.spec.imageRef`` as
                        ``<ref-name>:<tag>``. Pass this from the workflow when you
                        have resolved the ImageCard and know its exact tag.
        """
        name = card.metadata.name
        try:
            self._client.containers.get(name)
            logger.info(f"Container already exists: {name}")
            return name
        except Exception:
            pass

        # ── Image ────────────────────────────────────────────────────────────
        if image_name is None:
            # Best-effort fallback: strip the "images/" prefix and assume :latest
            image_name = f"{card.spec.imageRef.ref.split('/')[-1]}:latest"

        # ── Network ──────────────────────────────────────────────────────────
        # network_mode covers special modes (host, none, slirp4netns, …)
        # networkRef names a specific user-defined bridge network.
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
            # Extract the bare network name from "networks/jireh" → "jireh"
            kwargs["network"] = [card.spec.networkRef.ref.split("/")[-1]]

        # ── Optional fields ──────────────────────────────────────────────────
        if card.spec.command:
            kwargs["command"] = card.spec.command.split()
        if card.spec.hostname:
            kwargs["hostname"] = card.spec.hostname
        if card.spec.workdir:
            kwargs["working_dir"] = card.spec.workdir
        if card.spec.restart_policy:
            kwargs["restart_policy"] = {"Name": card.spec.restart_policy}
        if card.spec.mounts:
            kwargs["mounts"] = [m.model_dump() for m in card.spec.mounts]

        # ── Named volumes ─────────────────────────────────────────────────────
        # ContainerCard.spec.volumes: {volume_name: container_path}
        # Podman SDK expects:          {volume_name: {"bind": container_path, "mode": "rw"}}
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
        container = self._client.containers.get(name)
        container.stop()
        logger.info(f"Stopped container: {name}")

    def remove_container(self, name: str) -> None:
        container = self._client.containers.get(name)
        container.remove()
        logger.info(f"Removed container: {name}")

    def container_status(self, name: str) -> str:
        try:
            container = self._client.containers.get(name)
            return container.status
        except Exception:
            return "unknown"
