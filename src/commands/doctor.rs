//! cutip doctor — check system prerequisites.

use std::process::Command;

use anyhow::Result;
use colored::Colorize;

pub fn run() -> Result<()> {
    println!("{}", "cutip doctor".bold());
    println!();

    // Python
    check_command("Python", "python3", &["--version"]);

    // Container runtimes
    check_command("Docker", "docker", &["--version"]);
    check_command("Podman", "podman", &["--version"]);

    // Docker daemon
    check_daemon("Docker daemon", "docker", &["info", "--format", "{{.ServerVersion}}"]);
    check_daemon("Podman daemon", "podman", &["info", "--format", "{{.version.Version}}"]);

    // cutip-blocks
    check_python_import("cutip-blocks", "cutip_blocks");

    // Rust
    check_command("Rust", "rustc", &["--version"]);

    println!();
    Ok(())
}

fn check_command(name: &str, cmd: &str, args: &[&str]) {
    match Command::new(cmd).args(args).output() {
        Ok(output) if output.status.success() => {
            let version = String::from_utf8_lossy(&output.stdout);
            println!("  {} {} — {}", "✓".green(), name, version.trim());
        }
        _ => {
            println!("  {} {} — not found", "✗".red(), name);
        }
    }
}

fn check_daemon(name: &str, cmd: &str, args: &[&str]) {
    match Command::new(cmd).args(args).output() {
        Ok(output) if output.status.success() => {
            let version = String::from_utf8_lossy(&output.stdout);
            println!("  {} {} — v{}", "✓".green(), name, version.trim());
        }
        Ok(_) => {
            println!("  {} {} — installed but not running", "⚠".yellow(), name);
        }
        _ => {
            println!("  {} {} — not available", "·".dimmed(), name);
        }
    }
}

fn check_python_import(name: &str, module: &str) {
    let result = Command::new("python3")
        .args(["-c", &format!("import {module}; print('ok')")])
        .output();

    match result {
        Ok(output) if output.status.success() => {
            println!("  {} {} — installed", "✓".green(), name);
        }
        _ => {
            println!("  {} {} — not installed (pip install {})", "✗".red(), name, name);
        }
    }
}
