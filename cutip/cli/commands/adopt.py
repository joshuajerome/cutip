"""cutip adopt — generate CUTIP artifacts from an existing container.

Inspects a running or stopped container via the Docker/Podman API,
reverse-engineers its configuration, and generates CUTIP YAML artifacts
(ImageCard, ContainerCard, Unit, Group, workflow.py).

Usage:
    cutip adopt <container-name-or-id>
    cutip adopt <container-name-or-id> --group my-group
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import typer
import yaml
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from cutip.utils.logging import setup_logging
from cutip.workspace.scaffold import _find_project_root, _write_file

console = Console()


def _inspect_container(name: str, backend: str) -> dict[str, Any]:
    """Inspect a container by name or ID. Returns the full inspection dict."""
    if backend == "podman":
        from podman import PodmanClient

        from cutip.backends.podman.connection import local_socket_url

        url = local_socket_url()
        client = PodmanClient(base_url=url)
    else:
        import docker

        client = docker.from_env()

    container = client.containers.get(name)
    data = container.attrs
    client.close()
    return data


def _extract_name(attrs: dict) -> str:
    """Extract the container name from inspection data."""
    name = attrs.get("Name", "")
    # Docker prefixes with /
    return name.lstrip("/")


def _extract_image(attrs: dict) -> tuple[str, str]:
    """Extract image name and tag from inspection data."""
    config = attrs.get("Config", {})
    image = config.get("Image", "")
    if ":" in image.split("/")[-1]:
        name, tag = image.rsplit(":", 1)
    else:
        name, tag = image, "latest"
    return name, tag


def _extract_env(attrs: dict) -> dict[str, str]:
    """Extract environment variables from inspection data."""
    config = attrs.get("Config", {})
    env_list = config.get("Env", []) or []
    result: dict[str, str] = {}
    for item in env_list:
        if "=" in item:
            k, v = item.split("=", 1)
            # Skip common runtime-injected vars
            if k in ("PATH", "HOME", "HOSTNAME", "TERM"):
                continue
            result[k] = v
    return result


def _extract_ports(attrs: dict) -> dict[str, str]:
    """Extract port mappings from inspection data."""
    config = attrs.get("Config", {})
    exposed = config.get("ExposedPorts", {}) or {}
    host_config = attrs.get("HostConfig", {})
    port_bindings = host_config.get("PortBindings", {}) or {}

    ports: dict[str, str] = {}
    for port_proto in exposed:
        container_port = port_proto.split("/")[0]
        bindings = port_bindings.get(port_proto, [])
        if bindings and isinstance(bindings, list):
            host_port = bindings[0].get("HostPort", container_port)
            ports[f"{host_port}/tcp"] = container_port
        else:
            ports[f"{container_port}/tcp"] = container_port

    return ports


def _extract_mounts(attrs: dict) -> list[dict[str, str]]:
    """Extract bind mounts from inspection data."""
    mounts_raw = attrs.get("Mounts", []) or []
    mounts: list[dict[str, str]] = []
    for m in mounts_raw:
        mtype = m.get("Type", "bind")
        source = m.get("Source", "")
        target = m.get("Destination", "")
        if source and target:
            mounts.append({"type": mtype, "source": source, "target": target})
    return mounts


def _extract_network(attrs: dict) -> str | None:
    """Extract the primary network name from inspection data."""
    settings = attrs.get("NetworkSettings", {})
    networks = settings.get("Networks", {})
    if networks:
        # Return first non-default network, or first network
        for name in networks:
            if name not in ("bridge", "host", "none"):
                return name
        return next(iter(networks))
    return None


def _extract_command(attrs: dict) -> str | None:
    """Extract the container command from inspection data."""
    config = attrs.get("Config", {})
    cmd = config.get("Cmd")
    if cmd and isinstance(cmd, list):
        return " ".join(cmd)
    return None


def _extract_labels(attrs: dict) -> dict[str, str]:
    """Extract user labels (excluding runtime labels)."""
    config = attrs.get("Config", {})
    labels = config.get("Labels", {}) or {}
    # Filter out common runtime labels
    skip_prefixes = ("com.docker.", "org.opencontainers.", "desktop.", "io.podman.")
    return {k: v for k, v in labels.items() if not any(k.startswith(p) for p in skip_prefixes)}


def _yaml_scalar(value: str) -> str:
    """Return a YAML-safe inline scalar."""
    dumped = yaml.dump(
        value, default_flow_style=True, allow_unicode=True, width=float("inf")
    ).strip()
    if dumped.endswith("\n..."):
        dumped = dumped[:-4]
    return dumped


# ── Artifact generators ──────────────────────────────────────────────────────


def _gen_image_yaml(name: str, image: str, tag: str) -> str:
    return textwrap.dedent(f"""\
        apiVersion: cutip/v1
        kind: ImageCard
        metadata:
          name: {name}

        spec:
          source: pull
          image: {image}
          tag: "{tag}"
        """)


def _gen_container_yaml(
    name: str,
    *,
    network: str | None,
    command: str | None,
    env: dict[str, str],
    ports: dict[str, str],
    mounts: list[dict[str, str]],
    labels: dict[str, str],
) -> str:
    lines = [
        "apiVersion: cutip/v1",
        "kind: ContainerCard",
        "metadata:",
        f"  name: {name}",
        "",
        "spec:",
        "  imageRef:",
        f"    ref: images/{name}",
    ]

    if network and network not in ("bridge", "host", "none"):
        lines += ["  networkRef:", f"    ref: networks/{network}"]
    elif network in ("host", "none"):
        lines.append(f"  network_mode: {network}")
    else:
        lines.append("  network_mode: bridge")

    if command:
        lines.append(f"  command: {_yaml_scalar(command)}")

    if env:
        lines.append("  environment:")
        for k, v in env.items():
            lines.append(f"    {k}: {_yaml_scalar(v)}")

    if labels:
        lines.append("  labels:")
        for k, v in labels.items():
            lines.append(f"    {k}: {_yaml_scalar(v)}")

    if ports:
        lines.append("  ports:")
        for host_port, container_port in ports.items():
            lines.append(f'    "{host_port}": "{container_port}"')

    if mounts:
        lines.append("  mounts:")
        for m in mounts:
            lines.append(f"    - type: {m['type']}")
            lines.append(f'      source: "{m["source"]}"')
            lines.append(f'      target: "{m["target"]}"')

    return "\n".join(lines) + "\n"


def _gen_unit_yaml(name: str) -> str:
    return textwrap.dedent(f"""\
        apiVersion: cutip/v1
        kind: Unit
        metadata:
          name: {name}

        spec:
          containerRef:
            ref: containers/{name}
        """)


def _gen_group_yaml(group_name: str, unit_name: str) -> str:
    return textwrap.dedent(f"""\
        apiVersion: cutip/v1
        kind: Group
        metadata:
          name: {group_name}

        spec:
          units:
            - ref: units/{unit_name}

          workflow: workflow.py
        """)


def _gen_workflow_py(group_name: str, container_name: str) -> str:
    return textwrap.dedent(f"""\
        \"\"\"Group workflow for '{group_name}'.

        Generated by cutip adopt from an existing container.
        Customize this workflow to automate tasks through the container.
        \"\"\"

        from cutip.workflow import action, orchestrator, stage
        from cutip_blocks.blocks import container


        @action(name="Start {container_name}", container="{container_name}")
        def start(ctx):
            container.start(ctx, container="{container_name}")


        @orchestrator
        def main(ctx):
            stage("Start")
            start(ctx)
        """)


def _gen_network_yaml(name: str, attrs: dict) -> str:
    """Generate a NetworkCard from container network inspection data."""
    settings = attrs.get("NetworkSettings", {})
    networks = settings.get("Networks", {})
    net_info = networks.get(name, {})

    gateway = net_info.get("Gateway", "")
    subnet = ""
    # Try to derive subnet from IP + prefix length
    ip = net_info.get("IPAddress", "")
    prefix = net_info.get("IPPrefixLen", 0)
    if ip and prefix:
        # Build approximate subnet from IP
        parts = ip.split(".")
        if len(parts) == 4 and prefix <= 24:
            parts[3] = "0"
            subnet = f"{'.'.join(parts)}/{prefix}"

    if not subnet:
        subnet = "172.20.0.0/24"

    lines = [
        "apiVersion: cutip/v1",
        "kind: NetworkCard",
        "metadata:",
        f"  name: {name}",
        "",
        "spec:",
        "  driver: bridge",
        f'  subnet: "{subnet}"',
    ]
    if gateway:
        lines.append(f'  gateway: "{gateway}"')

    return "\n".join(lines) + "\n"


# ── CLI command ──────────────────────────────────────────────────────────────


def adopt(
    container_name: str = typer.Argument(
        ...,
        help="Name or ID of the container to adopt.",
    ),
    group: str = typer.Option(
        None,
        "--group",
        "-g",
        help="Group name for the adopted container. Defaults to the container name.",
    ),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory. Defaults to nearest cutip.yaml, git root, or cwd.",
        show_default=False,
    ),
    backend: str = typer.Option(
        None,
        "--backend",
        "-b",
        help="Container runtime (docker or podman). Auto-detected if omitted.",
    ),
) -> None:
    """Adopt an existing container into a CUTIP workspace.

    Inspects a running or stopped container, extracts its configuration,
    and generates CUTIP artifacts (ImageCard, ContainerCard, Unit, Group,
    and a workflow.py scaffold).

    Adopt workflow:
      1. cutip adopt <container>    — generate artifacts from live container
      2. cutip validate             — verify the generated graph
      3. cutip compile <group>      — preview the workflow
      4. cutip run <group>          — execute
    """
    setup_logging()

    project_root = output_dir or _find_project_root()

    # Detect backend
    if backend is None:
        try:
            from cutip.cli.commands.run import _load_project_backend

            backend = _load_project_backend(project_root)
        except Exception:
            backend = "docker"

    # Inspect the container
    logger.info(f"Inspecting container '{container_name}' via {backend}...")
    try:
        attrs = _inspect_container(container_name, backend)
    except Exception as e:
        console.print(f"[red]Failed to inspect container '{container_name}': {e}[/red]")
        raise typer.Exit(1)

    # Extract container details
    cname = _extract_name(attrs) or container_name
    image_name, image_tag = _extract_image(attrs)
    env = _extract_env(attrs)
    ports = _extract_ports(attrs)
    mounts = _extract_mounts(attrs)
    network = _extract_network(attrs)
    command = _extract_command(attrs)
    labels = _extract_labels(attrs)

    # Sanitize names
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in cname).strip("-_")
    group_name = group or safe_name

    logger.info(f"  Container: {cname}")
    logger.info(f"  Image: {image_name}:{image_tag}")
    logger.info(f"  Network: {network or 'bridge'}")
    logger.info(f"  Ports: {ports or 'none'}")
    logger.info(f"  Mounts: {len(mounts)}")
    logger.info(f"  Env vars: {len(env)}")
    logger.info(f"  Group: {group_name}")

    # Create output directories
    for rel in ["cutip/cards", "cutip/units", "cutip/groups"]:
        (project_root / rel).mkdir(parents=True, exist_ok=True)

    generated: list[str] = []

    # ImageCard
    img_yaml = _gen_image_yaml(safe_name, image_name, image_tag)
    img_path = project_root / f"cutip/cards/{safe_name}/{safe_name}.image.yaml"
    _write_file(img_path, img_yaml, f"cutip/cards/{safe_name}/{safe_name}.image.yaml")
    generated.append(str(img_path.relative_to(project_root)))

    # ContainerCard
    ctr_yaml = _gen_container_yaml(
        safe_name,
        network=network,
        command=command,
        env=env,
        ports=ports,
        mounts=mounts,
        labels=labels,
    )
    ctr_path = project_root / f"cutip/cards/{safe_name}/{safe_name}.container.yaml"
    _write_file(ctr_path, ctr_yaml, f"cutip/cards/{safe_name}/{safe_name}.container.yaml")
    generated.append(str(ctr_path.relative_to(project_root)))

    # NetworkCard (if custom network)
    if network and network not in ("bridge", "host", "none"):
        net_yaml = _gen_network_yaml(network, attrs)
        net_path = project_root / f"cutip/cards/{network}/{network}.network.yaml"
        _write_file(net_path, net_yaml, f"cutip/cards/{network}/{network}.network.yaml")
        generated.append(str(net_path.relative_to(project_root)))

    # Unit
    unit_yaml = _gen_unit_yaml(safe_name)
    unit_path = project_root / f"cutip/units/{safe_name}/{safe_name}.unit.yaml"
    _write_file(unit_path, unit_yaml, f"cutip/units/{safe_name}/{safe_name}.unit.yaml")
    generated.append(str(unit_path.relative_to(project_root)))

    # Group
    group_yaml = _gen_group_yaml(group_name, safe_name)
    group_path = project_root / f"cutip/groups/{group_name}/group.yaml"
    _write_file(group_path, group_yaml, f"cutip/groups/{group_name}/group.yaml")
    generated.append(str(group_path.relative_to(project_root)))

    # Workflow
    workflow = _gen_workflow_py(group_name, safe_name)
    workflow_path = project_root / f"cutip/groups/{group_name}/workflow.py"
    _write_file(workflow_path, workflow, f"cutip/groups/{group_name}/workflow.py")
    generated.append(str(workflow_path.relative_to(project_root)))

    # paths.yaml + secrets.yaml (if missing)
    paths_path = project_root / "cutip" / "paths.yaml"
    if not paths_path.exists():
        paths_path.parent.mkdir(parents=True, exist_ok=True)
        paths_path.write_text("required: {}\n\ngenerated: {}\n", encoding="utf-8")
        generated.append("cutip/paths.yaml")

    secrets_path = project_root / "cutip" / "secrets.yaml"
    if not secrets_path.exists():
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.write_text("required: {}\n", encoding="utf-8")
        generated.append("cutip/secrets.yaml")

    # cutip.yaml (if missing)
    cutip_yaml_path = project_root / "cutip.yaml"
    if not cutip_yaml_path.exists():
        doc = {
            "apiVersion": "cutip/v1",
            "project": {
                "name": project_root.name,
                "version": "0.1.0",
                "backend": backend,
            },
        }
        cutip_yaml_path.write_text(
            yaml.dump(doc, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        generated.append("cutip.yaml")

    # Report
    console.print(
        Panel.fit(
            f"[bold green]Adopted '{cname}' into group '{group_name}'[/bold green]\n"
            + "\n".join(f"  [dim]{f}[/dim]" for f in generated),
            title="cutip adopt",
            border_style="green",
        )
    )

    console.print(
        f"\nNext steps:\n"
        f"  [cyan]cutip validate[/cyan]                — verify the generated graph\n"
        f"  [cyan]cutip compile {group_name}[/cyan]    — preview the workflow\n"
        f"  [cyan]cutip run {group_name}[/cyan]        — execute\n"
        f"\nCustomize the workflow at [bold]cutip/groups/{group_name}/workflow.py[/bold]"
    )
