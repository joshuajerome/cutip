//! cutip from-compose — convert a Docker Compose file to config.yaml + workflow.py.

use std::collections::HashMap;
use std::path::Path;

use anyhow::{Context, Result};
use colored::Colorize;

use crate::config::model::{Config, ContainerConfig, ImageConfig, MountConfig, NetworkConfig};

pub fn run(compose_path: &Path, output_dir: Option<&Path>) -> Result<()> {
    let content = std::fs::read_to_string(compose_path)
        .with_context(|| format!("Failed to read {}", compose_path.display()))?;

    let doc: serde_yaml::Value = serde_yaml::from_str(&content)
        .with_context(|| format!("Failed to parse {}", compose_path.display()))?;

    let services = doc.get("services")
        .and_then(|s| s.as_mapping())
        .context("No 'services' key in compose file")?;

    let out = output_dir.map(|p| p.to_path_buf())
        .unwrap_or_else(|| std::env::current_dir().unwrap());

    let project_name = compose_path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("my-project")
        .replace("docker-compose", "project")
        .replace("compose", "project");

    let mut containers = HashMap::new();
    let mut secrets = HashMap::new();
    let mut workflow_lines = vec![
        format!("\"\"\"Converted from {}\"\"\"", compose_path.display()),
        String::new(),
        "from loguru import logger".to_string(),
        String::new(),
        String::new(),
        "def main(config):".to_string(),
    ];

    for (name, service) in services {
        let name = name.as_str().unwrap_or("unknown").to_string();
        let empty_mapping = serde_yaml::Mapping::new();
        let service = service.as_mapping().unwrap_or(&empty_mapping);

        let mut container = ContainerConfig {
            name: Some(name.clone()),
            ..Default::default()
        };

        // Image
        if let Some(img) = service.get(&serde_yaml::Value::String("image".to_string())) {
            let img_str = img.as_str().unwrap_or("").to_string();
            container.image = Some(ImageConfig {
                source: "pull".to_string(),
                image: Some(img_str),
                tag: "latest".to_string(),
                dockerfile: None,
                context: None,
                build_args: HashMap::new(),
            });
        } else if let Some(build) = service.get(&serde_yaml::Value::String("build".to_string())) {
            let (context, dockerfile) = match build {
                serde_yaml::Value::String(s) => (Some(s.clone()), None),
                serde_yaml::Value::Mapping(m) => {
                    let ctx = m.get(&serde_yaml::Value::String("context".to_string()))
                        .and_then(|v| v.as_str()).map(String::from);
                    let df = m.get(&serde_yaml::Value::String("dockerfile".to_string()))
                        .and_then(|v| v.as_str()).map(String::from);
                    (ctx, df)
                }
                _ => (None, None),
            };
            container.image = Some(ImageConfig {
                source: "build".to_string(),
                image: None,
                tag: "latest".to_string(),
                dockerfile,
                context,
                build_args: HashMap::new(),
            });
        }

        // Environment
        if let Some(env) = service.get(&serde_yaml::Value::String("environment".to_string())) {
            match env {
                serde_yaml::Value::Mapping(m) => {
                    for (k, v) in m {
                        let key = k.as_str().unwrap_or("").to_string();
                        let val = v.as_str().unwrap_or("").to_string();
                        // Detect secrets
                        if key.to_lowercase().contains("password") || key.to_lowercase().contains("secret") || key.to_lowercase().contains("token") {
                            secrets.insert(key.to_lowercase(), String::new());
                            container.environment.insert(key.clone(), format!("{{{{ secrets.{} }}}}", key.to_lowercase()));
                        } else {
                            container.environment.insert(key, val);
                        }
                    }
                }
                serde_yaml::Value::Sequence(seq) => {
                    for item in seq {
                        if let Some(s) = item.as_str() {
                            if let Some((k, v)) = s.split_once('=') {
                                container.environment.insert(k.to_string(), v.to_string());
                            }
                        }
                    }
                }
                _ => {}
            }
        }

        // Ports
        if let Some(ports) = service.get(&serde_yaml::Value::String("ports".to_string())) {
            if let Some(seq) = ports.as_sequence() {
                for port in seq {
                    if let Some(s) = port.as_str() {
                        if let Some((host, container_port)) = s.split_once(':') {
                            container.ports.insert(format!("{container_port}/tcp"), host.to_string());
                        }
                    }
                }
            }
        }

        // Volumes
        if let Some(volumes) = service.get(&serde_yaml::Value::String("volumes".to_string())) {
            if let Some(seq) = volumes.as_sequence() {
                for vol in seq {
                    if let Some(s) = vol.as_str() {
                        if let Some((src, target)) = s.split_once(':') {
                            let ro = target.ends_with(":ro");
                            let target_clean = target.trim_end_matches(":ro").to_string();
                            container.mounts.push(MountConfig {
                                source: src.to_string(),
                                target: target_clean,
                                mount_type: "bind".to_string(),
                                read_only: ro,
                            });
                        }
                    }
                }
            }
        }

        workflow_lines.push(format!("    logger.info(\"Starting {name}...\")"));
        workflow_lines.push(format!("    # TODO: start {name}, add health checks"));
        workflow_lines.push(String::new());

        containers.insert(name, container);
    }

    workflow_lines.push("    logger.success(\"All services started.\")".to_string());
    workflow_lines.push(String::new());
    workflow_lines.push(String::new());
    workflow_lines.push("def run_standalone(config):".to_string());
    workflow_lines.push("    main(config)".to_string());

    // Write config.yaml
    let config = Config {
        project: project_name.clone(),
        backend: "docker".to_string(),
        containers,
        secrets,
        ..Default::default()
    };

    let config_yaml = serde_yaml::to_string(&config).context("Failed to serialize config")?;
    std::fs::write(out.join("config.yaml"), config_yaml).context("Failed to write config.yaml")?;

    // Write workflow.py
    let workflow_content = workflow_lines.join("\n");
    std::fs::write(out.join("workflow.py"), workflow_content).context("Failed to write workflow.py")?;

    println!("{} Converted {} → config.yaml + workflow.py", "✓".green(), compose_path.display());
    println!("  {} container(s) converted", config.containers.len());
    if !config.secrets.is_empty() {
        println!("  {} secret(s) extracted (fill in config.yaml)", config.secrets.len());
    }

    Ok(())
}

impl Default for ContainerConfig {
    fn default() -> Self {
        Self {
            name: None,
            image: None,
            network_mode: None,
            network: None,
            command: None,
            workdir: None,
            environment: HashMap::new(),
            ports: HashMap::new(),
            mounts: Vec::new(),
            labels: HashMap::new(),
            restart_policy: None,
            privileged: false,
        }
    }
}
