//! cutip tree — print config structure.

use std::path::Path;

use anyhow::Result;
use colored::Colorize;

use crate::config::loader;

pub fn run(path: Option<&Path>, json: bool) -> Result<()> {
    let config_path = match path {
        Some(p) => p.to_path_buf(),
        None => loader::find_config(&std::env::current_dir()?)?,
    };

    let config = loader::load_config(&config_path)?;

    if json {
        println!("{}", serde_json::to_string_pretty(&config)?);
        return Ok(());
    }

    println!("{}", config.project.bold());
    println!("├── backend: {}", config.backend);
    println!("├── workflow: {}", config.workflow);

    if !config.vars.is_empty() {
        println!("├── vars:");
        let vars: Vec<_> = config.vars.keys().collect();
        for (i, key) in vars.iter().enumerate() {
            let prefix = if i == vars.len() - 1 { "│   └──" } else { "│   ├──" };
            println!("{} {}: {:?}", prefix, key, config.vars[*key]);
        }
    }

    if !config.secrets.is_empty() {
        println!("├── secrets:");
        let keys: Vec<_> = config.secrets.keys().collect();
        for (i, key) in keys.iter().enumerate() {
            let prefix = if i == keys.len() - 1 { "│   └──" } else { "│   ├──" };
            let masked = if config.secrets[*key].is_empty() { "(empty)" } else { "****" };
            println!("{} {}: {}", prefix, key, masked);
        }
    }

    if let Some(ref c) = config.container {
        let name = c.name.as_deref().unwrap_or("(unnamed)");
        println!("├── container: {}", name);
    }

    if !config.containers.is_empty() {
        println!("├── containers:");
        let names: Vec<_> = config.containers.keys().collect();
        for (i, name) in names.iter().enumerate() {
            let prefix = if i == names.len() - 1 { "│   └──" } else { "│   ├──" };
            println!("{} {}", prefix, name);
        }
    }

    if let Some(ref n) = config.network {
        let name = n.name.as_deref().unwrap_or("(unnamed)");
        println!("├── network: {}", name);
    }

    if !config.networks.is_empty() {
        println!("├── networks:");
        let names: Vec<_> = config.networks.keys().collect();
        for (i, name) in names.iter().enumerate() {
            let prefix = if i == names.len() - 1 { "│   └──" } else { "│   ├──" };
            println!("{} {}", prefix, name);
        }
    }

    // Extra config sections
    let extra_keys: Vec<_> = config.extra.keys().collect();
    if !extra_keys.is_empty() {
        println!("└── config sections: {}", extra_keys.iter().map(|k| k.as_str()).collect::<Vec<_>>().join(", "));
    }

    Ok(())
}
