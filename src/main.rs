mod commands;
mod config;
mod runtime;

use std::path::PathBuf;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(
    name = "cutip",
    about = "Workflow automation framework — define infrastructure as YAML, automate with Python, execute in containers",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Validate config.yaml — check schema, refs, secrets, workflow
    Validate {
        #[arg(short, long)]
        path: Option<PathBuf>,
        /// Output as JSON (for cutip-desktop integration)
        #[arg(long)]
        json: bool,
    },

    /// Print config structure as a tree
    Tree {
        #[arg(short, long)]
        path: Option<PathBuf>,
        /// Output as JSON
        #[arg(long)]
        json: bool,
    },

    /// Show a resolved config section
    Show {
        /// Section name: vars, secrets, container, containers, network, or any config key
        section: String,
        #[arg(short, long)]
        path: Option<PathBuf>,
    },

    /// Check system prerequisites
    Doctor,

    /// Run a workflow
    Run {
        #[arg(short, long)]
        path: Option<PathBuf>,
    },

    /// Scaffold a new project
    Init {
        /// Project name
        name: String,
        #[arg(short, long)]
        path: Option<PathBuf>,
    },

    /// Convert a Docker Compose file to config.yaml + workflow.py
    FromCompose {
        /// Path to docker-compose.yml
        file: PathBuf,
        /// Output directory (default: current)
        #[arg(short, long)]
        output: Option<PathBuf>,
    },
}

fn main() {
    let cli = Cli::parse();

    let result = match cli.command {
        Commands::Validate { path, json } => commands::validate::run(path.as_deref(), json),
        Commands::Tree { path, json } => commands::tree::run(path.as_deref(), json),
        Commands::Show { section, path } => commands::show::run(&section, path.as_deref()),
        Commands::Doctor => commands::doctor::run(),
        Commands::Run { path } => commands::run::run(path.as_deref()),
        Commands::Init { name, path } => commands::init::run(&name, path.as_deref()),
        Commands::FromCompose { file, output } => commands::from_compose::run(&file, output.as_deref()),
    };

    if let Err(e) = result {
        eprintln!("Error: {e}");
        std::process::exit(1);
    }
}
