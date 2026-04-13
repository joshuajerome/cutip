//! cutip init — scaffold a new project with config.yaml + workflow.py.

use std::path::Path;

use anyhow::{Context, Result};
use colored::Colorize;

pub fn run(name: &str, path: Option<&Path>) -> Result<()> {
    let dir = match path {
        Some(p) => p.to_path_buf(),
        None => std::env::current_dir()?.join(name),
    };

    if dir.join("config.yaml").exists() {
        anyhow::bail!("config.yaml already exists in {}", dir.display());
    }

    std::fs::create_dir_all(&dir)
        .with_context(|| format!("Failed to create {}", dir.display()))?;

    // config.yaml
    let config = format!(r#"project: {name}
backend: local

vars:
  # Add your variables here
  # example_path: "/path/to/something"

secrets:
  # Add sensitive values here (prompted if empty)
  # db_password: ""

# Uncomment for container-based projects:
# backend: docker
#
# image:
#   source: build
#   dockerfile: Dockerfile
#   context: .
#
# container:
#   name: {name}
#   environment:
#     ENV: development
"#);

    std::fs::write(dir.join("config.yaml"), config)
        .context("Failed to write config.yaml")?;

    // workflow.py — build without format! to avoid brace escaping
    let tq = "\"\"\"";  // triple quote
    let workflow = [
        format!("{tq}{name} workflow."),
        String::new(),
        "Usage:".to_string(),
        "    cutip run             # via cutip CLI".to_string(),
        format!("    python workflow.py    # standalone"),
        format!("{tq}"),
        String::new(),
        "from loguru import logger".to_string(),
        String::new(),
        String::new(),
        "def main(config):".to_string(),
        format!("    {tq}Entry point — called by cutip run or standalone.{tq}"),
        format!("    logger.info(\"Starting {name} ...\")"),
        String::new(),
        "    # Access config values".to_string(),
        "    # vars = config.get(\"vars\", {})".to_string(),
        "    # secrets = config.get(\"secrets\", {})".to_string(),
        String::new(),
        "    # Your workflow logic here".to_string(),
        format!("    logger.success(\"{name} complete.\")"),
        String::new(),
        String::new(),
        "def run_standalone(config):".to_string(),
        format!("    {tq}Called by cutip run.{tq}"),
        "    main(config)".to_string(),
        String::new(),
        String::new(),
        "if __name__ == \"__main__\":".to_string(),
        "    import yaml".to_string(),
        "    with open(\"config.yaml\") as f:".to_string(),
        "        config = yaml.safe_load(f) or {}".to_string(),
        "    main(config)".to_string(),
        String::new(),
    ].join("\n");

    std::fs::write(dir.join("workflow.py"), workflow)
        .context("Failed to write workflow.py")?;

    println!("{} Created project '{}' at {}", "✓".green(), name, dir.display());
    println!();
    println!("  {}", "Files:".bold());
    println!("    config.yaml    — project configuration");
    println!("    workflow.py    — workflow logic");
    println!();
    println!("  {}", "Next:".bold());
    println!("    cd {name}");
    println!("    cutip validate");
    println!("    cutip run");

    Ok(())
}
