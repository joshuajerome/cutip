//! cutip validate — static validation of config.yaml.

use std::path::Path;

use anyhow::Result;
use colored::Colorize;

use crate::config::loader;
use crate::config::resolve;

pub fn run(path: Option<&Path>, json: bool) -> Result<()> {
    let config_path = match path {
        Some(p) => p.to_path_buf(),
        None => loader::find_config(&std::env::current_dir()?)?,
    };

    let config = loader::load_config(&config_path)?;

    if json {
        // JSON output for cutip-desktop
        let ref_errors = resolve::validate_refs(&config);
        let output = serde_json::json!({
            "project": config.project,
            "backend": config.backend,
            "workflow": config.workflow,
            "vars_count": config.vars.len(),
            "secrets_count": config.secrets.len(),
            "containers_count": config.containers.len() + if config.container.is_some() { 1 } else { 0 },
            "networks_count": config.networks.len() + if config.network.is_some() { 1 } else { 0 },
            "warnings": ref_errors,
            "valid": true,
        });
        println!("{}", serde_json::to_string_pretty(&output)?);
        return Ok(());
    }

    println!("{} {}", "Loading".cyan(), config_path.display());
    println!("{} {}", "Project".cyan(), config.project);
    println!("{} {}", "Backend".cyan(), config.backend);
    println!("{} {}", "Workflow".cyan(), config.workflow);

    // Check vars
    let var_count = config.vars.len();
    println!("{} {} var(s)", "Vars".cyan(), var_count);

    // Check secrets
    let secret_count = config.secrets.len();
    let empty_secrets: Vec<_> = config
        .secrets
        .iter()
        .filter(|(_, v)| v.trim().is_empty())
        .map(|(k, _)| k.as_str())
        .collect();
    if empty_secrets.is_empty() {
        println!("{} {} secret(s), all set", "Secrets".cyan(), secret_count);
    } else {
        println!(
            "{} {} secret(s), {} empty: {}",
            "Secrets".yellow(),
            secret_count,
            empty_secrets.len(),
            empty_secrets.join(", ")
        );
    }

    // Check containers
    if let Some(ref c) = config.container {
        let name = c.name.as_deref().unwrap_or("(unnamed)");
        println!("{} single container: {}", "Container".cyan(), name);
    }
    if !config.containers.is_empty() {
        println!("{} {} container(s):", "Containers".cyan(), config.containers.len());
        for (name, c) in &config.containers {
            let img = c.image.as_ref()
                .map(|i| {
                    if i.source == "pull" {
                        i.image.as_deref().unwrap_or("?").to_string()
                    } else {
                        i.dockerfile.as_deref().unwrap_or("Dockerfile").to_string()
                    }
                })
                .unwrap_or_else(|| "no image".to_string());
            println!("  {} → {}", name, img);
        }
    }

    // Check networks
    if let Some(ref n) = config.network {
        let name = n.name.as_deref().unwrap_or("(unnamed)");
        let subnet = n.subnet.as_deref().unwrap_or("auto");
        println!("{} single network: {} ({})", "Network".cyan(), name, subnet);
    }
    if !config.networks.is_empty() {
        println!("{} {} network(s):", "Networks".cyan(), config.networks.len());
        for (name, n) in &config.networks {
            let subnet = n.subnet.as_deref().unwrap_or("auto");
            println!("  {} ({})", name, subnet);
        }
    }

    // Check workflow exists
    let config_dir = config_path.parent().unwrap_or(Path::new("."));
    let workflow_path = config_dir.join(&config.workflow);
    if workflow_path.is_file() {
        println!("{} {} exists", "Workflow".green(), config.workflow);
    } else if config.backend == "local" {
        // Local backend might have workflow elsewhere
        println!("{} {} not found (backend=local, may be OK)", "Workflow".yellow(), config.workflow);
    } else {
        println!("{} {} not found", "Workflow".red(), config.workflow);
    }

    // Validate refs
    let ref_errors = resolve::validate_refs(&config);
    if ref_errors.is_empty() {
        println!("\n{}", "✓ Validation passed".green().bold());
    } else {
        println!();
        for err in &ref_errors {
            println!("{} {}", "⚠".yellow(), err);
        }
        println!("\n{}", "⚠ Validation passed with warnings".yellow().bold());
    }

    Ok(())
}
