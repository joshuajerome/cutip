"""cutip from-compose — convert a docker-compose.yaml into CUTIP artifacts.

Usage:
    cutip from-compose <compose-file> [--output-dir <path>]

Generates:
    cutip/cards/<service>/<service>.image.yaml
    cutip/cards/<service>/<service>.container.yaml
    cutip/cards/<network>/<network>.network.yaml
    cutip/units/<service>/<service>.unit.yaml
    cutip/units/<service>/startup.py
    cutip/groups/<project>/group.yaml
    cutip/groups/<project>/workflow.py
    cutip/vars.yaml                   (created or left untouched if it exists)
    resources/dockerfiles/            (directory)
    resources/buildtime/              (directory)
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


def _yaml_scalar(value: str) -> str:
    """Return a YAML-safe inline scalar representation of *value*.

    Uses PyYAML to handle quoting of strings that contain special characters
    (double quotes, colons, newlines, etc.). The output is always a single line.
    """
    # width=float('inf') prevents PyYAML from wrapping long strings across lines.
    # yaml.dump produces "value\n...\n" — strip trailing document marker and newline.
    dumped = yaml.dump(
        value,
        default_flow_style=True,
        allow_unicode=True,
        width=float("inf"),
    ).strip()
    # Remove trailing YAML document-end marker if present
    if dumped.endswith("\n..."):
        dumped = dumped[:-4]
    return dumped

from cutip.utils.logging import setup_logging
from cutip.workspace.scaffold import _find_project_root, _write_file

console = Console()

# Env var key substrings that suggest a credential or sensitive path.
# Values matching these patterns are replaced with {{ vars.<key> }} references
# and placed in vars.yaml required: section for the user to fill in.
_SENSITIVE_PATTERNS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "private_key",
        "passphrase",
        "passwd",
        "pwd",
    }
)


def _is_sensitive(key: str) -> bool:
    """Return True if the env var key looks like a credential."""
    lower = key.lower()
    return any(pat in lower for pat in _SENSITIVE_PATTERNS)


def _parse_port(port_spec: Any) -> tuple[str, str] | None:
    """Convert a compose port spec to (host_port/tcp, container_port).

    Handles:
        "8080:3000"           → ("8080/tcp", "3000")
        "127.0.0.1:8080:3000" → ("8080/tcp", "3000")
        "3000"                → ("3000/tcp", "3000")
        3000                  → ("3000/tcp", "3000")
    """
    s = str(port_spec).strip("'\"")
    parts = s.split(":")
    if len(parts) == 1:
        return (f"{parts[0]}/tcp", parts[0])
    elif len(parts) == 2:
        return (f"{parts[0]}/tcp", parts[1])
    elif len(parts) == 3:
        # ip:host:container
        return (f"{parts[1]}/tcp", parts[2])
    return None


def _normalize_env(env: Any) -> dict[str, str]:
    """Normalize compose environment to {key: value} dict."""
    if isinstance(env, dict):
        return {str(k): str(v) if v is not None else "" for k, v in env.items()}
    if isinstance(env, list):
        result: dict[str, str] = {}
        for item in env:
            s = str(item)
            if "=" in s:
                k, v = s.split("=", 1)
                result[k] = v
            else:
                result[s] = ""
        return result
    return {}


def _normalize_labels(labels: Any) -> dict[str, str]:
    """Normalize compose labels to {key: value} dict."""
    if isinstance(labels, dict):
        return {str(k): str(v) for k, v in labels.items()}
    if isinstance(labels, list):
        result: dict[str, str] = {}
        for item in labels:
            s = str(item)
            if "=" in s:
                k, v = s.split("=", 1)
                result[k] = v
            else:
                result[s] = ""
        return result
    return {}


def _get_service_networks(service: dict) -> list[str]:
    """Return the list of network names a service attaches to."""
    nets = service.get("networks", [])
    if isinstance(nets, list):
        return [str(n) for n in nets]
    if isinstance(nets, dict):
        return list(nets.keys())
    return []


# ── Per-service artifact generators ──────────────────────────────────────────


def _image_yaml(service_name: str, service: dict) -> tuple[str, list[str]]:
    """Generate image YAML for a service. Returns (yaml_str, unmapped_items)."""
    unmapped: list[str] = []

    if "image" in service:
        ref = str(service["image"])
        # Split tag from image reference
        if ":" in ref.split("/")[-1]:
            image_name, tag = ref.rsplit(":", 1)
        else:
            image_name, tag = ref, "latest"
        # Normalize short image names to docker.io/library/
        parts = image_name.split("/")
        if len(parts) == 1:
            image_name = f"docker.io/library/{image_name}"
        elif len(parts) == 2 and "." not in parts[0] and ":" not in parts[0]:
            image_name = f"docker.io/{image_name}"

        text = textwrap.dedent(f"""\
            apiVersion: cutip/v1
            kind: ImageCard
            metadata:
              name: {service_name}

            spec:
              source: pull
              image: {image_name}
              tag: "{tag}"
            """)
    elif "build" in service:
        build = service["build"]
        orig_context = (
            build.get("context", ".") if isinstance(build, dict) else str(build)
        )
        orig_dockerfile = (
            build.get("dockerfile", "Dockerfile") if isinstance(build, dict) else "Dockerfile"
        )
        unmapped.append(
            f"services.{service_name}.build: original context='{orig_context}' "
            f"dockerfile='{orig_dockerfile}' — place your Dockerfile at "
            f"resources/dockerfiles/{service_name}.dockerfile"
        )
        text = textwrap.dedent(f"""\
            apiVersion: cutip/v1
            kind: ImageCard
            metadata:
              name: {service_name}

            spec:
              source: build
              tag: "latest"
              context: resources/dockerfiles
              dockerfile: {service_name}.dockerfile
            """)
    else:
        unmapped.append(
            f"services.{service_name}: no 'image' or 'build' key — "
            f"fill in the ImageCard spec manually"
        )
        text = textwrap.dedent(f"""\
            apiVersion: cutip/v1
            kind: ImageCard
            metadata:
              name: {service_name}

            spec:
              source: pull
              image: "# TODO: fill in image name"
              tag: "latest"
            """)

    return text, unmapped


def _container_yaml(
    service_name: str,
    service: dict,
    used_networks: set[str],
) -> tuple[str, list[str], dict[str, str]]:
    """Generate container YAML for a service.

    Returns (yaml_str, unmapped_items, sensitive_vars)
    where sensitive_vars is {var_key: original_value}.
    """
    unmapped: list[str] = []
    sensitive_vars: dict[str, str] = {}
    lines: list[str] = [
        "apiVersion: cutip/v1",
        "kind: ContainerCard",
        "metadata:",
        f"  name: {service_name}",
        "",
        "spec:",
        f"  imageRef:",
        f"    ref: images/{service_name}",
    ]

    # -- Network ---------------------------------------------------------------
    svc_nets = _get_service_networks(service)
    for n in svc_nets:
        used_networks.add(n)

    if svc_nets:
        primary = svc_nets[0]
        lines += [f"  networkRef:", f"    ref: networks/{primary}"]
    else:
        lines.append("  network_mode: bridge")

    # -- Simple scalar fields --------------------------------------------------
    if "command" in service:
        cmd = service["command"]
        if isinstance(cmd, list):
            cmd_str = " ".join(str(c) for c in cmd)
        else:
            cmd_str = str(cmd)
        lines.append(f"  command: {_yaml_scalar(cmd_str)}")

    if "hostname" in service:
        lines.append(f"  hostname: {service['hostname']}")

    if "working_dir" in service:
        lines.append(f"  workdir: {service['working_dir']}")

    if service.get("privileged"):
        lines.append("  privileged: true")

    if "cap_add" in service:
        caps = service["cap_add"]
        if caps:
            lines.append("  cap_add:")
            for c in caps:
                lines.append(f"    - {c}")

    if "restart" in service:
        lines.append(f"  restart_policy: {service['restart']}")

    # -- Environment -----------------------------------------------------------
    env = _normalize_env(service.get("environment", {}))
    if env:
        lines.append("  environment:")
        for k, v in env.items():
            if _is_sensitive(k):
                var_key = k.lower()
                lines.append(f'    {k}: "{{{{ vars.{var_key} }}}}"')
                sensitive_vars[var_key] = v
            else:
                lines.append(f"    {k}: {_yaml_scalar(v)}")

    # -- Labels ----------------------------------------------------------------
    labels = _normalize_labels(service.get("labels", {}))
    if labels:
        lines.append("  labels:")
        for k, v in labels.items():
            lines.append(f"    {k}: {v}")

    # -- Ports -----------------------------------------------------------------
    ports = service.get("ports", [])
    if ports:
        lines.append("  ports:")
        for p in ports:
            parsed = _parse_port(p)
            if parsed:
                host_port, container_port = parsed
                lines.append(f'    "{host_port}": "{container_port}"')

    # -- Volumes and mounts ----------------------------------------------------
    vols = service.get("volumes", [])
    named_vols: dict[str, str] = {}
    bind_mounts: list[dict[str, str]] = []

    for v in vols:
        if isinstance(v, str):
            # Short form: "source:target" or "source:target:ro"
            parts = v.split(":")
            if len(parts) >= 2:
                source, target = parts[0], parts[1]
                is_bind = source.startswith(".") or source.startswith("/")
                if is_bind:
                    bind_mounts.append({"source": source, "target": target})
                else:
                    named_vols[source] = target
        elif isinstance(v, dict):
            # Long form
            vtype = v.get("type", "bind")
            source = str(v.get("source", ""))
            target = str(v.get("target", ""))
            if vtype == "bind":
                bind_mounts.append({"source": source, "target": target})
            elif vtype == "volume":
                if source:
                    named_vols[source] = target
            else:
                bind_mounts.append({"source": source, "target": target})

    if named_vols:
        lines.append("  volumes:")
        for vol_name, target in named_vols.items():
            lines.append(f"    {vol_name}: {target}")

    if bind_mounts:
        lines.append("  mounts:")
        for m in bind_mounts:
            lines.append(f'    - type: bind')
            lines.append(f'      source: "{m["source"]}"')
            lines.append(f'      target: "{m["target"]}"')

    # -- Unmapped fields -------------------------------------------------------
    if "entrypoint" in service:
        unmapped.append(
            f"services.{service_name}.entrypoint: not mapped — "
            f"add to ContainerCard spec.command or use a wrapper script"
        )
    if "depends_on" in service:
        unmapped.append(
            f"services.{service_name}.depends_on: not mapped — "
            f"implement start ordering in groups/<group>/workflow.py"
        )
    if "healthcheck" in service:
        unmapped.append(
            f"services.{service_name}.healthcheck: not mapped — "
            f"implement in cutip/units/{service_name}/startup.py"
        )

    return "\n".join(lines) + "\n", unmapped, sensitive_vars


def _unit_yaml(service_name: str) -> str:
    return textwrap.dedent(f"""\
        apiVersion: cutip/v1
        kind: Unit
        metadata:
          name: {service_name}

        spec:
          containerRef:
            ref: containers/{service_name}
        """)


def _startup_py(service_name: str, service: dict) -> str:
    """Generate startup.py stub, including healthcheck TODO if present."""
    hc_lines: list[str] = []
    if "healthcheck" in service:
        hc = service["healthcheck"]
        test = hc.get("test", [])
        if isinstance(test, list):
            test_str = " ".join(
                str(t) for t in test if t not in ("CMD-SHELL", "CMD")
            )
        else:
            test_str = str(test)
        hc_lines = [
            "",
            f"# TODO: Implement the health check from compose:",
            f"#   Original test: {test_str}",
            "#",
            "# def startup(ctx: CutipContext) -> None:",
            "#     import time",
            "#     for attempt in range(1, 31):",
            f'#         exit_code, _ = ctx.container("{service_name}").exec_run(',
            f'#             ["sh", "-c", "{test_str}"]',
            "#         )",
            "#         if exit_code == 0:",
            f'#             logger.success(f"\'{service_name}\' ready after {{attempt}} attempt(s)")',
            "#             break",
            '#         logger.debug(f"  attempt {attempt}/30 — not ready yet")',
            "#         time.sleep(1)",
            "#     else:",
            f'#         raise RuntimeError("{service_name} did not become ready")',
        ]

    lines = [
        f'"""Unit startup hooks for \'{service_name}\'.',
        "",
        "pre_build(ctx)  -- runs before the image is built.",
        "startup(ctx)    -- runs after workflow.main() starts the container.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from loguru import logger",
        "",
        "from cutip.context.workflow import CutipContext",
    ]
    lines.extend(hc_lines)
    lines += [
        "",
        "",
        "# def pre_build(ctx: CutipContext) -> None:",
        '#     """Stage files into the build context before the image is built."""',
        "#     pass",
        "",
        "",
        "# def startup(ctx: CutipContext) -> None:",
        f'#     """Verify \'{service_name}\' is ready after it starts."""',
        f'#     logger.success("\'{service_name}\' is running")',
    ]
    return "\n".join(lines) + "\n"


# ── Network card generator ────────────────────────────────────────────────────

_SUBNET_POOL = [
    ("172.20.0.0/24", "172.20.0.1"),
    ("172.21.0.0/24", "172.21.0.1"),
    ("172.22.0.0/24", "172.22.0.1"),
    ("172.23.0.0/24", "172.23.0.1"),
]
_subnet_index = 0


def _next_placeholder_subnet() -> tuple[str, str]:
    global _subnet_index
    subnet, gateway = _SUBNET_POOL[_subnet_index % len(_SUBNET_POOL)]
    _subnet_index += 1
    return subnet, gateway


def _network_yaml(network_name: str, network_def: dict | None) -> str:
    """Generate a NetworkCard YAML for a compose network definition."""
    driver = "bridge"
    subnet = None
    gateway = None

    if isinstance(network_def, dict):
        driver = network_def.get("driver", "bridge") or "bridge"
        ipam = network_def.get("ipam", {}) or {}
        config_list = ipam.get("config", []) if isinstance(ipam, dict) else []
        if config_list and isinstance(config_list[0], dict):
            subnet = config_list[0].get("subnet")
            gateway = config_list[0].get("gateway")

    if not subnet:
        subnet, gateway = _next_placeholder_subnet()
        placeholder_comment = "  # TODO: adjust subnet/gateway to your environment\n"
    else:
        placeholder_comment = ""

    gw_line = f'  gateway: "{gateway}"' if gateway else ""

    return (
        "apiVersion: cutip/v1\n"
        "kind: NetworkCard\n"
        "metadata:\n"
        f"  name: {network_name}\n"
        "\n"
        "spec:\n"
        f"  driver: {driver}\n"
        f'{placeholder_comment}'
        f'  subnet: "{subnet}"\n'
        + (f"{gw_line}\n" if gw_line else "")
    )


# ── Group artifacts ───────────────────────────────────────────────────────────


def _group_yaml(group_name: str, service_names: list[str]) -> str:
    unit_refs = "\n".join(f"    - ref: units/{s}" for s in service_names)
    lines = [
        "apiVersion: cutip/v1",
        "kind: Group",
        "metadata:",
        f"  name: {group_name}",
        "",
        "spec:",
        "  units:",
        unit_refs,
        "",
        "  workflow: workflow.py",
    ]
    return "\n".join(lines) + "\n"


def _workflow_py(group_name: str, services: dict[str, dict]) -> str:
    """Generate workflow.py stub with start calls ordered by depends_on."""
    order = _topo_sort(services)

    body_lines: list[str] = []
    for svc in order:
        deps = services[svc].get("depends_on", [])
        if isinstance(deps, dict):
            deps = list(deps.keys())
        elif isinstance(deps, str):
            deps = [deps]
        if deps:
            body_lines.append(f"    # depends_on: {', '.join(deps)} — start after them")
        body_lines.append(f'    ctx.container("{svc}").start()')
        body_lines.append(f'    logger.info("Started {svc}")')
        body_lines.append("")

    body = "\n".join(body_lines).rstrip()

    lines = [
        f'"""Group workflow for \'{group_name}\'.',
        "",
        "This workflow was generated from a docker-compose.yaml.",
        "Review the start order and add health-check loops where needed.",
        "",
        "Containers with depends_on relationships are annotated with comments",
        "— implement the actual health checks in each unit's startup.py.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from loguru import logger",
        "",
        "from cutip.context.workflow import CutipContext",
        "",
        "",
        f"def main(ctx: CutipContext) -> None:",
        f'    """Start all containers for group \'{group_name}\'."""',
        body,
    ]
    return "\n".join(lines) + "\n"


def _topo_sort(services: dict[str, dict]) -> list[str]:
    """Return service names in a valid start order (respecting depends_on)."""
    remaining = list(services.keys())
    ordered: list[str] = []
    resolved: set[str] = set()

    # Simple repeated-pass topo sort (handles small graphs without cycle detection)
    max_passes = len(remaining) + 1
    for _ in range(max_passes):
        if not remaining:
            break
        for svc in list(remaining):
            deps = services[svc].get("depends_on", [])
            if isinstance(deps, dict):
                deps = list(deps.keys())
            elif isinstance(deps, str):
                deps = [deps]
            deps = [d for d in deps if d in services]  # only internal deps
            if all(d in resolved for d in deps):
                ordered.append(svc)
                resolved.add(svc)
                remaining.remove(svc)

    # Any remaining services (circular deps) — append at end
    ordered.extend(remaining)
    return ordered


# ── vars.yaml handling ────────────────────────────────────────────────────────


def _vars_yaml_content(sensitive_vars: dict[str, str]) -> str:
    if not sensitive_vars:
        return textwrap.dedent("""\
            required: {}

            generated: {}
            """)

    required_lines = "\n".join(
        f'  {k}: ""  # was: {v}' if v else f'  {k}: ""'
        for k, v in sensitive_vars.items()
    )
    return textwrap.dedent(f"""\
        # Fill in the required values before running cutip run <group>.
        # These were detected as sensitive environment variables in compose.
        required:
        {required_lines}

        generated: {{}}
        """)


# ── Main command ──────────────────────────────────────────────────────────────


def from_compose(
    compose_file: Path = typer.Argument(
        ...,
        help="Path to the compose.yaml / docker-compose.yaml to convert.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    output_dir: Path = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory. Defaults to git root or cwd.",
        show_default=False,
    ),
) -> None:
    """Convert a docker-compose.yaml into a CUTIP workspace.

    Generates ImageCards, ContainerCards, NetworkCards, Units, and a Group
    with a workflow.py stub for each service in the compose file.

    Fields that cannot be automatically mapped (entrypoint, depends_on,
    healthcheck) are listed in the end-of-run report with instructions.
    """
    setup_logging()
    global _subnet_index
    _subnet_index = 0  # Reset for deterministic output

    project_root = output_dir or _find_project_root()

    # -- Load compose file -----------------------------------------------------
    try:
        raw = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        console.print(f"[red]Failed to parse compose file: {exc}[/red]")
        raise typer.Exit(1)

    if not isinstance(raw, dict):
        console.print("[red]Compose file is empty or not a mapping.[/red]")
        raise typer.Exit(1)

    services: dict[str, dict] = raw.get("services", {}) or {}
    compose_networks: dict[str, Any] = raw.get("networks", {}) or {}

    if not services:
        console.print("[yellow]No services found in compose file.[/yellow]")
        raise typer.Exit(0)

    # Derive group name from compose project name or compose file stem
    group_name = (
        raw.get("name")
        or raw.get("x-project-name")
        or compose_file.stem.replace("docker-compose", "app").replace("-", "_")
        or "app"
    )
    # Sanitize: only alphanumeric + underscore + hyphen
    group_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in group_name)
    group_name = group_name.strip("-_") or "app"

    logger.info(f"Converting '{compose_file.name}' → group '{group_name}'")
    logger.info(f"  Output directory: {project_root}")
    logger.info(f"  Services: {', '.join(services)}")

    # -- Create output directories ---------------------------------------------
    for rel in [
        "cutip/cards",
        "cutip/units",
        "cutip/groups",
        "resources/dockerfiles",
        "resources/buildtime",
    ]:
        (project_root / rel).mkdir(parents=True, exist_ok=True)

    # -- Collect outputs -------------------------------------------------------
    all_unmapped: list[str] = []
    all_sensitive: dict[str, str] = {}
    used_networks: set[str] = set()
    generated_files: list[str] = []

    # -- Services --------------------------------------------------------------
    for svc_name, svc_def in services.items():
        if not isinstance(svc_def, dict):
            svc_def = {}

        # ImageCard
        img_yaml, img_unmapped = _image_yaml(svc_name, svc_def)
        img_path = project_root / f"cutip/cards/{svc_name}/{svc_name}.image.yaml"
        _write_file(img_path, img_yaml, f"cutip/cards/{svc_name}/{svc_name}.image.yaml")
        generated_files.append(str(img_path.relative_to(project_root)))
        all_unmapped.extend(img_unmapped)

        # ContainerCard
        ctr_yaml, ctr_unmapped, sensitive = _container_yaml(
            svc_name, svc_def, used_networks
        )
        ctr_path = project_root / f"cutip/cards/{svc_name}/{svc_name}.container.yaml"
        _write_file(ctr_path, ctr_yaml, f"cutip/cards/{svc_name}/{svc_name}.container.yaml")
        generated_files.append(str(ctr_path.relative_to(project_root)))
        all_unmapped.extend(ctr_unmapped)
        all_sensitive.update(sensitive)

        # Unit
        unit_path = project_root / f"cutip/units/{svc_name}/{svc_name}.unit.yaml"
        _write_file(
            unit_path, _unit_yaml(svc_name), f"cutip/units/{svc_name}/{svc_name}.unit.yaml"
        )
        generated_files.append(str(unit_path.relative_to(project_root)))

        # startup.py
        startup_path = project_root / f"cutip/units/{svc_name}/startup.py"
        _write_file(
            startup_path,
            _startup_py(svc_name, svc_def),
            f"cutip/units/{svc_name}/startup.py",
        )
        generated_files.append(str(startup_path.relative_to(project_root)))

    # -- Networks --------------------------------------------------------------
    # Generate cards for every network that was referenced or declared
    all_networks = set(compose_networks.keys()) | used_networks
    for net_name in sorted(all_networks):
        net_def = compose_networks.get(net_name)
        net_yaml = _network_yaml(net_name, net_def)
        net_path = project_root / f"cutip/cards/{net_name}/{net_name}.network.yaml"
        _write_file(
            net_path, net_yaml, f"cutip/cards/{net_name}/{net_name}.network.yaml"
        )
        generated_files.append(str(net_path.relative_to(project_root)))
        if not (isinstance(net_def, dict) and net_def.get("ipam")):
            all_unmapped.append(
                f"networks.{net_name}: no IPAM config in compose — "
                f"review subnet/gateway in cutip/cards/{net_name}/{net_name}.network.yaml"
            )

    # -- Group -----------------------------------------------------------------
    service_order = _topo_sort(services)

    group_yaml_str = _group_yaml(group_name, service_order)
    group_yaml_path = project_root / f"cutip/groups/{group_name}/group.yaml"
    _write_file(
        group_yaml_path, group_yaml_str, f"cutip/groups/{group_name}/group.yaml"
    )
    generated_files.append(str(group_yaml_path.relative_to(project_root)))

    workflow_py_str = _workflow_py(group_name, services)
    workflow_py_path = project_root / f"cutip/groups/{group_name}/workflow.py"
    _write_file(
        workflow_py_path, workflow_py_str, f"cutip/groups/{group_name}/workflow.py"
    )
    generated_files.append(str(workflow_py_path.relative_to(project_root)))

    # -- vars.yaml -------------------------------------------------------------
    vars_path = project_root / "cutip" / "vars.yaml"
    if vars_path.exists():
        if all_sensitive:
            console.print(
                f"\n[yellow]cutip/vars.yaml already exists.[/yellow] "
                f"Add these entries to the [bold]required:[/bold] section manually:"
            )
            for k in all_sensitive:
                console.print(f"  [cyan]{k}[/cyan]: \"\"")
    else:
        vars_path.parent.mkdir(parents=True, exist_ok=True)
        vars_path.write_text(_vars_yaml_content(all_sensitive), encoding="utf-8")
        generated_files.append("cutip/vars.yaml")
        logger.debug("  created: cutip/vars.yaml")

    # -- cutip.yaml (project config) -------------------------------------------
    cutip_yaml_path = project_root / "cutip.yaml"
    if not cutip_yaml_path.exists():
        import yaml as _yaml

        doc = {
            "apiVersion": "cutip/v1",
            "project": {"name": project_root.name, "version": "0.1.0"},
        }
        cutip_yaml_path.write_text(
            _yaml.dump(doc, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        generated_files.append("cutip.yaml")
        logger.debug("  created: cutip.yaml")

    # -- End-of-run report -----------------------------------------------------
    file_count = len(generated_files)
    console.print(
        Panel.fit(
            f"[bold green]✓ Generated {file_count} file(s) for group '{group_name}'[/bold green]\n"
            + "\n".join(f"  [dim]{f}[/dim]" for f in generated_files),
            title="cutip from-compose",
            border_style="green",
        )
    )

    if all_unmapped:
        console.print("\n[bold yellow]⚠  Requires manual action:[/bold yellow]")
        for item in all_unmapped:
            console.print(f"  [yellow]·[/yellow] {item}")

    console.print(
        f"\nRun [bold cyan]cutip validate --path {project_root}[/bold cyan] "
        f"to check the generated graph."
    )
