"""Podman connection management.

Handles listing Podman connections, opening/closing the SSH port-forward
tunnel, and resolving the local socket URL for direct connections.

Run standalone to verify connectivity::

    # Test SSH tunnel (default — mirrors what `cutip run` uses):
    python -m cutip.backends.podman.connection

    # Test local socket (mirrors what `cutip run --local` uses):
    python -m cutip.backends.podman.connection --local
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger

from cutip.utils.exceptions import CutipError

# ── Constants ──────────────────────────────────────────────────────────────────

PODMAN_TCP_PORT: int = 8080
PODMAN_TCP_URL: str = f"tcp://localhost:{PODMAN_TCP_PORT}"


# ── Connection enumeration ─────────────────────────────────────────────────────

def get_connections() -> list[dict[str, str]]:
    """Return all Podman connections as a list of dicts (one per connection).

    Runs ``podman system connection ls`` and parses the tabular output.

    Raises:
        CutipError: If Podman is not installed or the command fails.
    """
    try:
        result = subprocess.run(
            ["podman", "system", "connection", "ls"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise CutipError(
            "Could not list Podman connections. Is Podman installed?"
        ) from exc

    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        raise CutipError(
            "No Podman connections found. Run 'podman machine start' first."
        )

    headers = lines[0].split()
    connections: list[dict[str, str]] = []
    for line in lines[1:]:
        parts = line.split(maxsplit=len(headers) - 1)
        if len(parts) < len(headers):
            continue
        connections.append(dict(zip(headers, parts)))
    return connections


def get_default_connection(connections: list[dict[str, str]] | None = None) -> dict[str, str]:
    """Return the default Podman connection dict.

    Args:
        connections: Pre-fetched list from :func:`get_connections`.
                     If *None*, :func:`get_connections` is called automatically.

    Raises:
        CutipError: If no default connection is found.
    """
    if connections is None:
        connections = get_connections()

    for conn in connections:
        if conn.get("Default", "").lower() == "true":
            return conn

    raise CutipError(
        "No default Podman connection found. "
        "Run 'podman machine start' and ensure a connection is marked as default."
    )


# ── SSH tunnel (used by PodmanBackend.connect()) ───────────────────────────────

def open_ssh_tunnel(connection: dict[str, str]) -> subprocess.Popen:
    """Forward ``localhost:{PODMAN_TCP_PORT}`` → the Podman Unix socket inside the VM.

    Uses SSH local port forwarding (``-L``), so no ``podman system service``
    process needs to run inside the guest — SSH holds the port open and
    transparently proxies HTTP requests to the Podman socket.

    Requires OpenSSH ≥ 6.7 (ships with macOS 10.12+ and modern Linux distros).

    Args:
        connection: A connection dict as returned by :func:`get_default_connection`.

    Returns:
        The running SSH :class:`subprocess.Popen` object.
        Keep this alive for the lifetime of the session; close with
        :func:`close_ssh_tunnel` when done.

    Raises:
        CutipError: If the tunnel exits immediately (bad key, wrong host, etc.).
    """
    uri: str = connection.get("URI", "")
    identity: str = connection.get("Identity", "")

    # Parse ssh://user@host:port/path/to/podman.sock
    without_scheme = uri.replace("ssh://", "")
    if "/" in without_scheme:
        user_host_port, socket_tail = without_scheme.split("/", 1)
        socket_path = "/" + socket_tail        # restore leading slash
    else:
        user_host_port, socket_path = without_scheme, ""

    user, host_port = (
        user_host_port.split("@", 1) if "@" in user_host_port
        else ("root", user_host_port)
    )
    host, port = (
        host_port.rsplit(":", 1) if ":" in host_port
        else (host_port, "22")
    )

    # -L local_port:remote_unix_socket  →  maps tcp://localhost:8080 on the
    # host to the Podman REST API socket inside the VM.
    ssh_cmd = [
        "ssh",
        "-N",                                       # port-forward only, no shell
        "-L", f"{PODMAN_TCP_PORT}:{socket_path}",
        "-i", identity,
        "-p", port,
        f"{user}@{host}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ExitOnForwardFailure=yes",            # fail fast on bind error
    ]

    logger.debug(f"Opening SSH tunnel: {shlex.join(ssh_cmd)}")
    process = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(1)

    if process.poll() is not None:
        stderr = process.stderr.read().decode(errors="replace").strip()
        raise CutipError(
            "SSH tunnel exited prematurely.\n"
            f"  URI:     {uri}\n"
            f"  Socket:  {socket_path}\n"
            f"  Command: {shlex.join(ssh_cmd)}\n"
            f"  stderr:  {stderr or '(none)'}\n"
            "Ensure 'podman machine start' has been run and the machine is healthy."
        )

    logger.info(f"SSH tunnel established: {PODMAN_TCP_URL} -> {socket_path}")
    return process


def close_ssh_tunnel(process: subprocess.Popen, timeout: int = 5) -> None:
    """Terminate the SSH tunnel process gracefully.

    Args:
        process: The :class:`subprocess.Popen` returned by :func:`open_ssh_tunnel`.
        timeout: Seconds to wait for graceful termination before force-killing.
    """
    if process is None or process.poll() is not None:
        return
    logger.debug("Closing SSH tunnel...")
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("SSH tunnel did not exit cleanly — force-killing.")
        process.kill()
    logger.debug("SSH tunnel closed.")


# ── Local socket (used by PodmanBackend.connect_local()) ──────────────────────

def local_socket_url() -> str:
    """Resolve the local Podman socket URL for the current platform.

    Priority order:
    1. ``CONTAINER_HOST`` env var (standard Podman convention)
    2. macOS: socket path reported by ``podman machine inspect``
    3. Linux: ``$XDG_RUNTIME_DIR/podman/podman.sock``
    4. Windows: raises :class:`CutipError` (named pipes unsupported by podman-py)

    Raises:
        CutipError: On Windows or if the macOS socket cannot be located.
    """
    env = os.environ.get("CONTAINER_HOST")
    if env:
        return env

    if sys.platform == "win32":
        raise CutipError(
            "connect_local() (--local) is not supported on Windows because "
            "podman-py does not support the Windows named-pipe protocol.\n"
            "Use SSH-tunnel mode instead (no --local flag) after running "
            "'podman machine start'."
        )

    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["podman", "machine", "inspect",
                 "--format", "{{.ConnectionInfo.PodmanSocket.Path}}"],
                capture_output=True, text=True, check=True,
            )
            sock = result.stdout.strip()
            if sock:
                return f"unix://{sock}"
        except Exception:
            pass
        # Fallback: well-known socket locations for each VM provider
        home = Path.home()
        for candidate in [
            home / ".local/share/containers/podman/machine/applehv/podman.sock",
            home / ".local/share/containers/podman/machine/qemu/podman.sock",
        ]:
            if candidate.exists():
                return f"unix://{candidate}"
        raise CutipError(
            "Could not locate the macOS Podman machine socket. "
            "Set CONTAINER_HOST or run 'podman machine start'."
        )

    # Linux — rootless user socket
    uid = os.getuid()
    xdg = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    return f"unix://{xdg}/podman/podman.sock"


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Verify Podman connectivity without running a full workflow.

    Usage::

        python -m cutip.backends.podman.connection           # SSH tunnel
        python -m cutip.backends.podman.connection --local   # local socket
    """
    from cutip.utils.logging import setup_logging
    setup_logging(level="DEBUG")

    use_local = "--local" in sys.argv

    if use_local:
        # ── Local socket mode ──────────────────────────────────────────────
        logger.info("Mode: local socket")
        url = local_socket_url()
        logger.info(f"Socket URL: {url}")

        try:
            from podman import PodmanClient
        except ImportError:
            logger.error("podman-py not installed. Run: uv add podman")
            sys.exit(1)

        client = PodmanClient(base_url=url)
        ok = client.ping()
        if not ok:
            logger.error(f"Ping failed at {url}. Is 'podman machine start' running?")
            sys.exit(1)

        logger.info(f"Ping OK")
        images = client.images.list()
        logger.info(f"Images on daemon: {len(images)}")
        for img in images[:5]:
            logger.info(f"  {img.tags}")

    else:
        # ── SSH tunnel mode ────────────────────────────────────────────────
        logger.info("Mode: SSH tunnel")
        connections = get_connections()
        conn = get_default_connection(connections)
        logger.info(f"Default connection: {conn['Name']}")
        logger.info(f"  URI:      {conn['URI']}")
        logger.info(f"  Identity: {conn['Identity']}")

        try:
            from podman import PodmanClient
        except ImportError:
            logger.error("podman-py not installed. Run: uv add podman")
            sys.exit(1)

        process = open_ssh_tunnel(conn)
        try:
            client = PodmanClient(base_url=PODMAN_TCP_URL)
            ok = client.ping()
            if not ok:
                logger.error("Ping failed — tunnel is up but Podman is not responding.")
                sys.exit(1)

            logger.info("Ping OK")
            images = client.images.list()
            logger.info(f"Images on daemon: {len(images)}")
            for img in images[:5]:
                logger.info(f"  {img.tags}")
        finally:
            close_ssh_tunnel(process)
