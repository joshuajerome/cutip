//! Container runtime — Docker/Podman lifecycle via bollard.
//!
//! Handles image build/pull, network creation, container create/start.
//! Only used when backend != "local".

use std::collections::HashMap;
use std::path::Path;

use anyhow::{Context, Result};
use bollard::container::{Config, CreateContainerOptions, RemoveContainerOptions, StartContainerOptions, StopContainerOptions};
use bollard::image::CreateImageOptions;
use bollard::network::CreateNetworkOptions;
use bollard::Docker;
use colored::Colorize;
use futures_util::StreamExt;
use tokio::runtime::Runtime;

use crate::config::model::{ContainerConfig, ImageConfig, NetworkConfig};
use crate::config::resolve;

pub struct ContainerRuntime {
    client: Docker,
    rt: Runtime,
}

impl ContainerRuntime {
    pub fn connect() -> Result<Self> {
        let rt = Runtime::new().context("Failed to create tokio runtime")?;
        let client = Docker::connect_with_local_defaults()
            .context("Failed to connect to Docker/Podman. Is the daemon running?")?;

        // Verify connection
        rt.block_on(async {
            client.ping().await.context("Docker/Podman daemon not reachable")
        })?;

        println!("  {} Connected to container runtime", "✓".green());
        Ok(Self { client, rt })
    }

    pub fn ensure_network(&self, name: &str, config: &NetworkConfig) -> Result<()> {
        let client = self.client.clone();
        let name = name.to_string();
        let subnet = config.subnet.clone();
        let gateway = config.gateway.clone();
        let driver = config.driver.clone();

        self.rt.block_on(async {
            // Check if exists
            match client.inspect_network::<String>(&name, None).await {
                Ok(_) => {
                    println!("  {} Network '{}' already exists", "·".dimmed(), name);
                    return Ok(());
                }
                Err(_) => {}
            }

            let ipam = if subnet.is_some() || gateway.is_some() {
                Some(bollard::models::Ipam {
                    config: Some(vec![bollard::models::IpamConfig {
                        subnet,
                        gateway,
                        ..Default::default()
                    }]),
                    ..Default::default()
                })
            } else {
                None
            };

            let opts = CreateNetworkOptions {
                name: name.as_str(),
                driver: driver.as_str(),
                ipam: ipam.unwrap_or_default(),
                ..Default::default()
            };

            client.create_network(opts).await
                .with_context(|| format!("Failed to create network '{name}'"))?;

            println!("  {} Created network '{}'", "✓".green(), name);
            Ok(())
        })
    }

    pub fn pull_image(&self, image: &str, tag: &str) -> Result<()> {
        let client = self.client.clone();
        let image = image.to_string();
        let tag = tag.to_string();

        println!("  {} Pulling {}:{} ...", "↓".cyan(), image, tag);

        self.rt.block_on(async {
            let opts = CreateImageOptions {
                from_image: image.as_str(),
                tag: tag.as_str(),
                ..Default::default()
            };
            let mut stream = client.create_image(Some(opts), None, None);
            while let Some(result) = stream.next().await {
                result.with_context(|| format!("Pull failed for {image}:{tag}"))?;
            }
            println!("  {} Pulled {}:{}", "✓".green(), image, tag);
            Ok(())
        })
    }

    pub fn remove_container_if_exists(&self, name: &str) -> Result<()> {
        let client = self.client.clone();
        let name = name.to_string();

        self.rt.block_on(async {
            match client.inspect_container(&name, None).await {
                Ok(_) => {
                    client.remove_container(&name, Some(RemoveContainerOptions {
                        force: true,
                        ..Default::default()
                    })).await
                        .with_context(|| format!("Failed to remove stale container '{name}'"))?;
                    println!("  {} Removed stale container '{}'", "·".dimmed(), name);
                }
                Err(_) => {}
            }
            Ok(())
        })
    }

    pub fn create_container(
        &self,
        name: &str,
        container_config: &ContainerConfig,
        image_tag: &str,
        vars: &HashMap<String, String>,
        secrets: &HashMap<String, String>,
    ) -> Result<()> {
        let client = self.client.clone();
        let name = name.to_string();

        // Resolve environment variables
        let env: Vec<String> = container_config.environment.iter()
            .map(|(k, v)| {
                let resolved = resolve::resolve_string(v, vars, secrets);
                format!("{k}={resolved}")
            })
            .collect();

        // Resolve mounts
        let binds: Vec<String> = container_config.mounts.iter()
            .map(|m| {
                let source = resolve::resolve_string(&m.source, vars, secrets);
                let ro = if m.read_only { ":ro" } else { "" };
                format!("{source}:{}{ro}", m.target)
            })
            .collect();

        // Port bindings
        let mut exposed_ports = HashMap::new();
        let mut port_bindings = HashMap::new();
        for (container_port, host_port) in &container_config.ports {
            exposed_ports.insert(container_port.clone(), HashMap::new());
            port_bindings.insert(
                container_port.clone(),
                Some(vec![bollard::models::PortBinding {
                    host_ip: Some("0.0.0.0".to_string()),
                    host_port: Some(host_port.clone()),
                }]),
            );
        }

        let host_config = bollard::models::HostConfig {
            binds: if binds.is_empty() { None } else { Some(binds) },
            network_mode: container_config.network_mode.clone()
                .or(container_config.network.clone()),
            port_bindings: if port_bindings.is_empty() { None } else { Some(port_bindings) },
            privileged: Some(container_config.privileged),
            restart_policy: container_config.restart_policy.as_ref().map(|p| {
                bollard::models::RestartPolicy {
                    name: Some(match p.as_str() {
                        "always" => bollard::models::RestartPolicyNameEnum::ALWAYS,
                        "unless-stopped" => bollard::models::RestartPolicyNameEnum::UNLESS_STOPPED,
                        "on-failure" => bollard::models::RestartPolicyNameEnum::ON_FAILURE,
                        _ => bollard::models::RestartPolicyNameEnum::NO,
                    }),
                    ..Default::default()
                }
            }),
            ..Default::default()
        };

        let config = Config {
            image: Some(image_tag.to_string()),
            cmd: container_config.command.as_ref().map(|c| vec!["/bin/sh".to_string(), "-c".to_string(), c.clone()]),
            env: if env.is_empty() { None } else { Some(env) },
            working_dir: container_config.workdir.clone(),
            exposed_ports: if exposed_ports.is_empty() { None } else { Some(exposed_ports) },
            labels: if container_config.labels.is_empty() { None } else { Some(container_config.labels.clone()) },
            host_config: Some(host_config),
            ..Default::default()
        };

        self.rt.block_on(async {
            client.create_container(
                Some(CreateContainerOptions { name: name.as_str(), ..Default::default() }),
                config,
            ).await
                .with_context(|| format!("Failed to create container '{name}'"))?;

            println!("  {} Created container '{}'", "✓".green(), name);
            Ok(())
        })
    }

    pub fn start_container(&self, name: &str) -> Result<()> {
        let client = self.client.clone();
        let name = name.to_string();

        self.rt.block_on(async {
            client.start_container(&name, None::<StartContainerOptions<String>>).await
                .with_context(|| format!("Failed to start container '{name}'"))?;
            println!("  {} Started container '{}'", "✓".green(), name);
            Ok(())
        })
    }
}
