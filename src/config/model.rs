//! Data model for config.yaml.
//!
//! ```yaml
//! project: my-app
//! host: container          # local | container | remote
//! container_runtime: podman  # docker | podman (only when host: container)
//!
//! vars:
//!   repo_path: "/home/user/dev/my-app"
//!   node_env: development
//!
//! secrets:
//!   db_password: ""        # prompted if empty
//!   ssh_key: ""
//!
//! image:                   # container projects
//!   source: build
//!   dockerfile: Dockerfile
//!   context: .
//!
//! container:               # single container projects
//!   name: my-app
//!   network_mode: host
//!   environment:
//!     NODE_ENV: "{{ vars.node_env }}"
//!   mounts:
//!     - source: "{{ vars.repo_path }}"
//!       target: /app
//!
//! # Multi-container projects use containers: instead
//! containers:
//!   web:
//!     image: { source: build, dockerfile: web.dockerfile }
//!     ports: { "3000/tcp": "3000" }
//!   db:
//!     image: { source: pull, image: "postgres:16" }
//!     environment:
//!       POSTGRES_PASSWORD: "{{ secrets.db_password }}"
//!
//! network:                 # single network
//!   name: app-net
//!   driver: bridge
//!   subnet: "172.20.0.0/24"
//!
//! networks:                # multiple networks
//!   frontend: { driver: bridge, subnet: "172.20.0.0/24" }
//!   backend: { driver: bridge, subnet: "172.21.0.0/24" }
//! ```

use std::collections::HashMap;
use serde::{Deserialize, Serialize};

/// Root config.yaml structure.
#[derive(Debug, Deserialize, Serialize, Default)]
pub struct Config {
    /// Project name.
    pub project: String,

    /// Host type: "local", "container", or "remote".
    #[serde(default)]
    pub host: Option<String>,

    /// Container runtime: "auto", "docker", or "podman" (only when host: container).
    #[serde(default, rename = "container.rt")]
    pub container_rt: Option<String>,

    /// Workflow file path (default: "workflow.py").
    #[serde(default = "default_workflow")]
    pub workflow: String,

    /// User-defined variables. Referenced as {{ vars.key }} in YAML values.
    #[serde(default)]
    pub vars: HashMap<String, String>,

    /// Sensitive values. Referenced as {{ secrets.key }}. Prompted if empty.
    #[serde(default)]
    pub secrets: HashMap<String, String>,

    /// Single image definition (mutually exclusive with containers).
    #[serde(default)]
    pub image: Option<ImageConfig>,

    /// Single container definition (mutually exclusive with containers).
    #[serde(default)]
    pub container: Option<ContainerConfig>,

    /// Multiple container definitions keyed by name.
    #[serde(default)]
    pub containers: HashMap<String, ContainerConfig>,

    /// Single network definition.
    #[serde(default)]
    pub network: Option<NetworkConfig>,

    /// Multiple network definitions keyed by name.
    #[serde(default)]
    pub networks: HashMap<String, NetworkConfig>,

    /// Workflow data — freeform key-value pairs accessed as ctx.data in workflows.
    #[serde(default)]
    pub data: HashMap<String, serde_yaml::Value>,
}

/// Image build/pull configuration.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct ImageConfig {
    /// "build" or "pull".
    pub source: String,

    /// Image tag (default: "latest").
    #[serde(default = "default_tag")]
    pub tag: String,

    /// For source: pull — image name (e.g. "postgres:16").
    #[serde(default)]
    pub image: Option<String>,

    /// For source: build — Dockerfile path.
    #[serde(default)]
    pub dockerfile: Option<String>,

    /// For source: build — build context directory.
    #[serde(default)]
    pub context: Option<String>,

    /// Build arguments.
    #[serde(default)]
    pub build_args: HashMap<String, String>,
}

/// Container configuration.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct ContainerConfig {
    /// Container name.
    #[serde(default)]
    pub name: Option<String>,

    /// Inline image config, or will use top-level image.
    #[serde(default)]
    pub image: Option<ImageConfig>,

    /// Network mode ("host", "bridge", "none") or network name reference.
    #[serde(default)]
    pub network_mode: Option<String>,

    /// Network name to attach to.
    #[serde(default)]
    pub network: Option<String>,

    /// Command override.
    #[serde(default)]
    pub command: Option<String>,

    /// Working directory inside container.
    #[serde(default)]
    pub workdir: Option<String>,

    /// Environment variables.
    #[serde(default)]
    pub environment: HashMap<String, String>,

    /// Port mappings: "container_port/proto" → "host_port".
    #[serde(default)]
    pub ports: HashMap<String, String>,

    /// Bind mounts.
    #[serde(default)]
    pub mounts: Vec<MountConfig>,

    /// Labels.
    #[serde(default)]
    pub labels: HashMap<String, String>,

    /// Restart policy.
    #[serde(default)]
    pub restart_policy: Option<String>,

    /// Privileged mode.
    #[serde(default)]
    pub privileged: bool,
}

/// Mount/volume configuration.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct MountConfig {
    /// Source path on host (supports {{ vars.X }}).
    pub source: String,

    /// Target path in container.
    pub target: String,

    /// Mount type: "bind" (default) or "volume".
    #[serde(default = "default_mount_type")]
    #[serde(rename = "type")]
    pub mount_type: String,

    /// Read-only mount.
    #[serde(default)]
    pub read_only: bool,
}

/// Network configuration.
#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct NetworkConfig {
    /// Network name.
    #[serde(default)]
    pub name: Option<String>,

    /// Driver (default: "bridge").
    #[serde(default = "default_driver")]
    pub driver: String,

    /// Subnet CIDR.
    #[serde(default)]
    pub subnet: Option<String>,

    /// Gateway IP.
    #[serde(default)]
    pub gateway: Option<String>,
}

fn default_workflow() -> String { "workflow.py".to_string() }
fn default_tag() -> String { "latest".to_string() }
fn default_mount_type() -> String { "bind".to_string() }
fn default_driver() -> String { "bridge".to_string() }
