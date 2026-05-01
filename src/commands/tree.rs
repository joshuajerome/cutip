//! cutip tree — returns full config as a Python dict.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

use crate::config::loader;

/// Load config.yaml and return the full config as a JSON string.
/// Python side parses it into a dict.
#[pyfunction]
#[pyo3(signature = (path = None))]
pub fn tree(path: Option<&str>) -> PyResult<String> {
    let config_path = match path {
        Some(p) => std::path::PathBuf::from(p),
        None => loader::find_config(
            &std::env::current_dir().map_err(|e| PyRuntimeError::new_err(format!("{e}")))?,
        )
        .map_err(|e| PyRuntimeError::new_err(format!("{e}")))?,
    };

    let config =
        loader::load_config(&config_path).map_err(|e| PyRuntimeError::new_err(format!("{e}")))?;

    serde_json::to_string_pretty(&config).map_err(|e| PyRuntimeError::new_err(format!("{e}")))
}
