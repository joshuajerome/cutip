//! Load and parse config.yaml.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

use super::model::Config;

/// Find config.yaml in the current directory or parents.
pub fn find_config(start: &Path) -> Result<PathBuf> {
    let mut dir = start.to_path_buf();
    loop {
        let candidate = dir.join("config.yaml");
        if candidate.is_file() {
            return Ok(candidate);
        }
        if !dir.pop() {
            anyhow::bail!(
                "No config.yaml found in {} or any parent directory",
                start.display()
            );
        }
    }
}

/// Load and parse config.yaml from a path.
pub fn load_config(path: &Path) -> Result<Config> {
    let content = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read {}", path.display()))?;

    let config: Config = serde_yaml::from_str(&content)
        .with_context(|| format!("Failed to parse {}", path.display()))?;

    Ok(config)
}
