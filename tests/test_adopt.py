"""Tests for cutip adopt — artifact generation from container inspection data."""

import yaml

from cutip.cli.commands.adopt import (
    _extract_command,
    _extract_env,
    _extract_image,
    _extract_labels,
    _extract_mounts,
    _extract_name,
    _extract_network,
    _extract_ports,
    _gen_container_yaml,
    _gen_group_yaml,
    _gen_image_yaml,
    _gen_network_yaml,
    _gen_unit_yaml,
    _gen_workflow_py,
)

# ── Mock inspection data (mimics docker/podman inspect output) ──────────────

MOCK_ATTRS = {
    "Name": "/my-redis",
    "Config": {
        "Image": "redis:7-alpine",
        "Cmd": ["redis-server", "--save", "60", "1"],
        "Env": [
            "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "REDIS_VERSION=7.2.4",
            "REDIS_PASSWORD=secret123",
            "HOME=/root",
        ],
        "ExposedPorts": {"6379/tcp": {}},
        "Labels": {
            "com.docker.compose.project": "myapp",
            "app.tier": "cache",
        },
    },
    "HostConfig": {
        "PortBindings": {
            "6379/tcp": [{"HostIp": "", "HostPort": "6379"}],
        },
    },
    "Mounts": [
        {
            "Type": "bind",
            "Source": "/data/redis",
            "Destination": "/data",
        },
        {
            "Type": "volume",
            "Source": "redis-vol",
            "Destination": "/var/lib/redis",
        },
    ],
    "NetworkSettings": {
        "Networks": {
            "myapp-network": {
                "Gateway": "172.20.0.1",
                "IPAddress": "172.20.0.5",
                "IPPrefixLen": 24,
            },
        },
    },
}


# ── Extraction tests ────────────────────────────────────────────────────────


def test_extract_name():
    assert _extract_name(MOCK_ATTRS) == "my-redis"


def test_extract_name_no_slash():
    assert _extract_name({"Name": "plain-name"}) == "plain-name"


def test_extract_image():
    name, tag = _extract_image(MOCK_ATTRS)
    assert name == "redis"
    assert tag == "7-alpine"


def test_extract_image_no_tag():
    attrs = {"Config": {"Image": "nginx"}}
    name, tag = _extract_image(attrs)
    assert name == "nginx"
    assert tag == "latest"


def test_extract_env():
    env = _extract_env(MOCK_ATTRS)
    assert "REDIS_VERSION" in env
    assert "REDIS_PASSWORD" in env
    assert env["REDIS_PASSWORD"] == "secret123"
    # Runtime vars should be filtered
    assert "PATH" not in env
    assert "HOME" not in env


def test_extract_ports():
    ports = _extract_ports(MOCK_ATTRS)
    assert ports == {"6379/tcp": "6379"}


def test_extract_mounts():
    mounts = _extract_mounts(MOCK_ATTRS)
    assert len(mounts) == 2
    assert mounts[0]["source"] == "/data/redis"
    assert mounts[0]["target"] == "/data"
    assert mounts[1]["type"] == "volume"


def test_extract_network():
    net = _extract_network(MOCK_ATTRS)
    assert net == "myapp-network"


def test_extract_network_bridge_only():
    attrs = {"NetworkSettings": {"Networks": {"bridge": {}}}}
    assert _extract_network(attrs) == "bridge"


def test_extract_command():
    cmd = _extract_command(MOCK_ATTRS)
    assert cmd == "redis-server --save 60 1"


def test_extract_command_none():
    assert _extract_command({"Config": {}}) is None


def test_extract_labels():
    labels = _extract_labels(MOCK_ATTRS)
    assert "app.tier" in labels
    assert labels["app.tier"] == "cache"
    # Docker-internal labels should be filtered
    assert "com.docker.compose.project" not in labels


# ── Generator tests ─────────────────────────────────────────────────────────


def test_gen_image_yaml():
    result = _gen_image_yaml("my-redis", "redis", "7-alpine")
    doc = yaml.safe_load(result)
    assert doc["kind"] == "ImageCard"
    assert doc["metadata"]["name"] == "my-redis"
    assert doc["spec"]["source"] == "pull"
    assert doc["spec"]["image"] == "redis"
    assert doc["spec"]["tag"] == "7-alpine"


def test_gen_container_yaml_with_network():
    result = _gen_container_yaml(
        "my-redis",
        network="myapp-network",
        command="redis-server",
        env={"REDIS_VERSION": "7.2.4"},
        ports={"6379/tcp": "6379"},
        mounts=[{"type": "bind", "source": "/data", "target": "/data"}],
        labels={"app.tier": "cache"},
    )
    doc = yaml.safe_load(result)
    assert doc["kind"] == "ContainerCard"
    assert doc["spec"]["imageRef"]["ref"] == "images/my-redis"
    assert doc["spec"]["networkRef"]["ref"] == "networks/myapp-network"
    assert doc["spec"]["command"] == "redis-server"
    assert doc["spec"]["environment"]["REDIS_VERSION"] == "7.2.4"
    assert doc["spec"]["ports"]["6379/tcp"] == "6379"


def test_gen_container_yaml_host_network():
    result = _gen_container_yaml(
        "test",
        network="host",
        command=None,
        env={},
        ports={},
        mounts=[],
        labels={},
    )
    doc = yaml.safe_load(result)
    assert doc["spec"]["network_mode"] == "host"
    assert "networkRef" not in doc["spec"]


def test_gen_unit_yaml():
    result = _gen_unit_yaml("my-redis")
    doc = yaml.safe_load(result)
    assert doc["kind"] == "Unit"
    assert doc["spec"]["containerRef"]["ref"] == "containers/my-redis"


def test_gen_group_yaml():
    result = _gen_group_yaml("redis-group", "my-redis")
    doc = yaml.safe_load(result)
    assert doc["kind"] == "Group"
    assert doc["metadata"]["name"] == "redis-group"
    assert len(doc["spec"]["units"]) == 1
    assert doc["spec"]["units"][0]["ref"] == "units/my-redis"


def test_gen_workflow_py():
    result = _gen_workflow_py("redis-group", "my-redis")
    assert "def start(ctx):" in result
    assert "def main(ctx):" in result
    assert 'container="my-redis"' in result
    assert 'stage("Start")' in result


def test_gen_network_yaml():
    result = _gen_network_yaml("myapp-network", MOCK_ATTRS)
    doc = yaml.safe_load(result)
    assert doc["kind"] == "NetworkCard"
    assert doc["metadata"]["name"] == "myapp-network"
    assert doc["spec"]["gateway"] == "172.20.0.1"
    assert "172.20.0" in doc["spec"]["subnet"]
