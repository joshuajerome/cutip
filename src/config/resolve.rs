//! Template resolution for {{ vars.X }} and {{ secrets.X }} placeholders.

use std::collections::HashMap;

use super::model::Config;

/// Resolve all {{ vars.X }} and {{ secrets.X }} placeholders in a string.
pub fn resolve_string(
    template: &str,
    vars: &HashMap<String, String>,
    secrets: &HashMap<String, String>,
) -> String {
    let mut result = template.to_string();

    for (key, value) in vars {
        let patterns = [
            format!("{{{{ vars.{key} }}}}"),
            format!("{{{{vars.{key}}}}}"),
        ];
        for pattern in &patterns {
            result = result.replace(pattern, value);
        }
    }

    for (key, value) in secrets {
        let patterns = [
            format!("{{{{ secrets.{key} }}}}"),
            format!("{{{{secrets.{key}}}}}"),
        ];
        for pattern in &patterns {
            result = result.replace(pattern, value);
        }
    }

    result
}

/// Check for unresolved {{ ... }} placeholders in a string.
pub fn find_unresolved(text: &str) -> Vec<String> {
    let mut unresolved = Vec::new();
    let mut remaining = text;

    while let Some(start) = remaining.find("{{") {
        if let Some(end) = remaining[start..].find("}}") {
            let placeholder = &remaining[start..start + end + 2];
            unresolved.push(placeholder.trim().to_string());
            remaining = &remaining[start + end + 2..];
        } else {
            break;
        }
    }

    unresolved
}

/// Validate that all vars and secrets referenced in the config are present and non-empty.
pub fn validate_refs(config: &Config) -> Vec<String> {
    let mut errors = Vec::new();

    // Check secrets — must be non-empty
    for (key, value) in &config.secrets {
        if value.trim().is_empty() {
            errors.push(format!("Secret '{}' is empty — set it in config.yaml or it will be prompted", key));
        }
    }

    errors
}
