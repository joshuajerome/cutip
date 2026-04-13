//! cutip show — dump a resolved config section.

use std::path::Path;

use anyhow::{Context, Result};
use colored::Colorize;

use crate::config::loader;

pub fn run(section: &str, path: Option<&Path>) -> Result<()> {
    let config_path = match path {
        Some(p) => p.to_path_buf(),
        None => loader::find_config(&std::env::current_dir()?)?,
    };

    let config = loader::load_config(&config_path)?;

    match section {
        "vars" => {
            println!("{}", serde_yaml::to_string(&config.vars)?);
        }
        "secrets" => {
            // Mask values
            let masked: std::collections::HashMap<_, _> = config
                .secrets
                .iter()
                .map(|(k, v)| (k.as_str(), if v.is_empty() { "(empty)" } else { "****" }))
                .collect();
            println!("{}", serde_yaml::to_string(&masked)?);
        }
        "container" => {
            if let Some(ref c) = config.container {
                println!("{}", serde_yaml::to_string(c)?);
            } else {
                println!("{}", "No single container defined".yellow());
            }
        }
        "containers" => {
            if config.containers.is_empty() {
                println!("{}", "No containers defined".yellow());
            } else {
                println!("{}", serde_yaml::to_string(&config.containers)?);
            }
        }
        "network" | "networks" => {
            if let Some(ref n) = config.network {
                println!("{}", serde_yaml::to_string(n)?);
            }
            if !config.networks.is_empty() {
                println!("{}", serde_yaml::to_string(&config.networks)?);
            }
            if config.network.is_none() && config.networks.is_empty() {
                println!("{}", "No networks defined".yellow());
            }
        }
        other => {
            // Try extra sections
            if let Some(value) = config.extra.get(other) {
                println!("{}", serde_yaml::to_string(value)?);
            } else {
                anyhow::bail!("Unknown section: '{}'. Available: vars, secrets, container, containers, network, networks, or config section names", other);
            }
        }
    }

    Ok(())
}
