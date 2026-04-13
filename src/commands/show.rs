//! cutip show — return a config section as YAML string.

use std::collections::HashMap;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

use crate::config::loader;

/// Return a config section as a YAML string.
#[pyfunction]
#[pyo3(signature = (section, path = None))]
pub fn show(section: &str, path: Option<&str>) -> PyResult<String> {
    let config_path = match path {
        Some(p) => std::path::PathBuf::from(p),
        None => loader::find_config(&std::env::current_dir().map_err(|e| {
            PyRuntimeError::new_err(format!("{e}"))
        })?)
        .map_err(|e| PyRuntimeError::new_err(format!("{e}")))?,
    };

    let config = loader::load_config(&config_path)
        .map_err(|e| PyRuntimeError::new_err(format!("{e}")))?;

    let yaml = match section {
        "vars" => serde_yaml::to_string(&config.vars),
        "secrets" => {
            let masked: HashMap<_, _> = config
                .secrets
                .iter()
                .map(|(k, v)| (k.as_str(), if v.is_empty() { "(empty)" } else { "****" }))
                .collect();
            serde_yaml::to_string(&masked)
        }
        "container" => match &config.container {
            Some(c) => serde_yaml::to_string(c),
            None => Ok("No single container defined".to_string()),
        },
        "containers" => {
            if config.containers.is_empty() {
                Ok("No containers defined".to_string())
            } else {
                serde_yaml::to_string(&config.containers)
            }
        }
        "network" | "networks" => {
            let mut parts = Vec::new();
            if let Some(ref n) = config.network {
                parts.push(serde_yaml::to_string(n).unwrap_or_default());
            }
            if !config.networks.is_empty() {
                parts.push(serde_yaml::to_string(&config.networks).unwrap_or_default());
            }
            if parts.is_empty() {
                Ok("No networks defined".to_string())
            } else {
                Ok(parts.join("\n"))
            }
        }
        other => {
            if let Some(value) = config.extra.get(other) {
                serde_yaml::to_string(value)
            } else {
                return Err(PyRuntimeError::new_err(format!(
                    "Unknown section: '{other}'. Available: vars, secrets, container, containers, network, networks"
                )));
            }
        }
    }
    .map_err(|e| PyRuntimeError::new_err(format!("YAML error: {e}")))?;

    Ok(yaml)
}
