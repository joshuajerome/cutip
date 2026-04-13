use pyo3::prelude::*;

mod config;
mod commands;

/// cutip._core — Rust core for the cutip Python package.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(commands::validate::validate, m)?)?;
    m.add_function(wrap_pyfunction!(commands::tree::tree, m)?)?;
    m.add_function(wrap_pyfunction!(commands::show::show, m)?)?;
    Ok(())
}
