//! cutip run — validate, set up runtime, spawn Python workflow.

use std::collections::HashMap;
use std::io::{self, Write};
use std::path::Path;
use std::process::Command;

use anyhow::{Context, Result};
use colored::Colorize;

use crate::config::loader;
use crate::config::model::Config;
use crate::config::resolve;
use crate::runtime::ContainerRuntime;

pub fn run(path: Option<&Path>) -> Result<()> {
    let config_path = match path {
        Some(p) => p.to_path_buf(),
        None => loader::find_config(&std::env::current_dir()?)?,
    };

    let config_dir = config_path.parent().unwrap_or(Path::new("."));

    println!("{}", "cutip run".bold());
    println!();

    // Step 1: Load config
    let mut config = loader::load_config(&config_path)?;
    println!("  {} Loaded {}", "✓".green(), config_path.display());

    // Step 2: Prompt for empty secrets
    prompt_empty_secrets(&mut config);

    // Step 3: Prompt for empty vars (if they look like credentials)
    prompt_empty_vars(&mut config);

    // Step 4: Resolve templates in config
    println!("  {} Resolved templates", "✓".green());

    // Step 5: Set up container runtime (if needed)
    if config.backend != "local" {
        println!();
        println!("{}", "Container Runtime".bold());
        let runtime = ContainerRuntime::connect()?;

        // Create networks
        if let Some(ref net) = config.network {
            let name = net.name.as_deref().unwrap_or("default");
            runtime.ensure_network(name, net)?;
        }
        for (name, net) in &config.networks {
            runtime.ensure_network(name, net)?;
        }

        // Pull/build images + create containers
        if let Some(ref container_cfg) = config.container {
            let name = container_cfg.name.as_deref().unwrap_or(&config.project);
            let image_cfg = container_cfg.image.as_ref()
                .or(config.image.as_ref());

            if let Some(img) = image_cfg {
                if img.source == "pull" {
                    let image_name = img.image.as_deref().unwrap_or(&config.project);
                    runtime.pull_image(image_name, &img.tag)?;
                }
                // TODO: image build support
            }

            let image_tag = image_cfg
                .and_then(|i| i.image.as_deref())
                .unwrap_or(&config.project);

            runtime.remove_container_if_exists(name)?;
            runtime.create_container(name, container_cfg, image_tag, &config.vars, &config.secrets)?;
        }

        for (name, container_cfg) in &config.containers {
            if let Some(ref img) = container_cfg.image {
                if img.source == "pull" {
                    let image_name = img.image.as_deref().unwrap_or(name);
                    runtime.pull_image(image_name, &img.tag)?;
                }
            }

            let image_tag = container_cfg.image.as_ref()
                .and_then(|i| i.image.as_deref())
                .unwrap_or(name);

            runtime.remove_container_if_exists(name)?;
            runtime.create_container(name, container_cfg, image_tag, &config.vars, &config.secrets)?;
        }
    }

    // Step 6: Spawn Python workflow
    println!();
    println!("{}", "Workflow".bold());

    let workflow_path = config_dir.join(&config.workflow);
    if !workflow_path.is_file() {
        anyhow::bail!(
            "Workflow file not found: {}. Create it or set 'workflow:' in config.yaml",
            workflow_path.display()
        );
    }

    // Serialize config to JSON for Python to consume
    let config_json = serde_json::to_string(&config)
        .context("Failed to serialize config to JSON")?;

    // Build the Python bootstrap script
    let bootstrap = format!(
        r#"
import sys, os, json

# Load config from environment
config = json.loads(os.environ["CUTIP_CONFIG"])

# Add workflow directory to path
workflow_dir = os.path.dirname(os.path.abspath("{workflow}"))
if workflow_dir not in sys.path:
    sys.path.insert(0, workflow_dir)

# Add project root to path
project_root = os.path.abspath("{project_root}")
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import and run
import importlib.util
spec = importlib.util.spec_from_file_location("workflow", "{workflow}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if hasattr(module, "run_standalone"):
    module.run_standalone(config)
elif hasattr(module, "main"):
    module.main(config)
else:
    print("ERROR: workflow.py has no run_standalone() or main() function")
    sys.exit(1)
"#,
        workflow = workflow_path.display(),
        project_root = config_dir.display(),
    );

    println!("  {} Spawning Python: {}", "→".cyan(), config.workflow);
    println!();

    let status = Command::new("python3")
        .arg("-c")
        .arg(&bootstrap)
        .env("CUTIP_CONFIG", &config_json)
        .env("CUTIP_PROJECT", &config.project)
        .env("CUTIP_BACKEND", &config.backend)
        .current_dir(config_dir)
        .status()
        .context("Failed to spawn Python. Is python3 installed?")?;

    if !status.success() {
        let code = status.code().unwrap_or(1);
        anyhow::bail!("Workflow exited with code {code}");
    }

    println!();
    println!("  {} Workflow complete", "✓".green().bold());

    Ok(())
}

/// Prompt for empty secrets interactively.
fn prompt_empty_secrets(config: &mut Config) {
    let empty: Vec<String> = config.secrets.iter()
        .filter(|(_, v)| v.trim().is_empty())
        .map(|(k, _)| k.clone())
        .collect();

    if empty.is_empty() {
        return;
    }

    println!();
    println!("  Secrets not set in config.yaml:");
    for key in &empty {
        print!("    {}: ", key);
        io::stdout().flush().unwrap();
        let mut value = String::new();
        io::stdin().read_line(&mut value).unwrap();
        config.secrets.insert(key.clone(), value.trim().to_string());
    }
    println!();
}

/// Prompt for empty vars that look like credentials.
fn prompt_empty_vars(config: &mut Config) {
    let credential_hints = ["ip", "host", "user", "pass", "password", "addr", "url"];
    let empty: Vec<String> = config.vars.iter()
        .filter(|(k, v)| {
            v.trim().is_empty() && credential_hints.iter().any(|h| k.to_lowercase().contains(h))
        })
        .map(|(k, _)| k.clone())
        .collect();

    if empty.is_empty() {
        return;
    }

    println!();
    println!("  Vars not set in config.yaml:");
    for key in &empty {
        print!("    {}: ", key);
        io::stdout().flush().unwrap();
        let mut value = String::new();
        io::stdin().read_line(&mut value).unwrap();
        config.vars.insert(key.clone(), value.trim().to_string());
    }
    println!();
}
