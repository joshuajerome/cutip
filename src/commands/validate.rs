//! cutip validate — returns config validation as a Python dict.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::config::loader;
use crate::config::resolve;

/// Validate config.yaml and return results as a dict.
///
/// Returns: {
///   "project", "backend", "workflow",
///   "vars_count", "secrets_count", "containers_count", "networks_count",
///   "empty_secrets": [...], "warnings": [...],
///   "workflow_exists": bool, "valid": bool
/// }
#[pyfunction]
#[pyo3(signature = (path = None))]
pub fn validate(py: Python<'_>, path: Option<&str>) -> PyResult<PyObject> {
    let config_path = match path {
        Some(p) => std::path::PathBuf::from(p),
        None => loader::find_config(&std::env::current_dir().map_err(|e| {
            PyRuntimeError::new_err(format!("Failed to get current dir: {e}"))
        })?)
        .map_err(|e| PyRuntimeError::new_err(format!("{e}")))?,
    };

    let config = loader::load_config(&config_path)
        .map_err(|e| PyRuntimeError::new_err(format!("{e}")))?;

    let ref_errors = resolve::validate_refs(&config);

    let empty_secrets: Vec<&str> = config
        .secrets
        .iter()
        .filter(|(_, v)| v.trim().is_empty())
        .map(|(k, _)| k.as_str())
        .collect();

    let config_dir = config_path.parent().unwrap_or(std::path::Path::new("."));
    let workflow_exists = config_dir.join(&config.workflow).is_file();

    let dict = PyDict::new(py);
    dict.set_item("path", config_path.to_string_lossy().to_string())?;
    dict.set_item("project", &config.project)?;
    dict.set_item("host", config.resolved_host())?;
    dict.set_item("container_runtime", config.resolved_runtime())?;
    // backward compat
    dict.set_item("backend", config.resolved_host())?;
    dict.set_item("workflow", &config.workflow)?;
    dict.set_item("vars_count", config.vars.len())?;
    dict.set_item("secrets_count", config.secrets.len())?;
    dict.set_item(
        "containers_count",
        config.containers.len() + if config.container.is_some() { 1 } else { 0 },
    )?;
    dict.set_item(
        "networks_count",
        config.networks.len() + if config.network.is_some() { 1 } else { 0 },
    )?;
    dict.set_item("empty_secrets", empty_secrets)?;
    dict.set_item("warnings", &ref_errors)?;
    dict.set_item("workflow_exists", workflow_exists)?;
    dict.set_item("valid", true)?;

    Ok(dict.into_any().unbind())
}
