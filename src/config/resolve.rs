//! Template resolution for {{ vars.X }}, {{ paths.X }}, and {{ secrets.X }}
//! placeholders.

use std::collections::HashMap;

use super::model::Config;

/// Resolve all `{{ vars.X }}`, `{{ paths.X }}`, and `{{ secrets.X }}`
/// placeholders in a string against the provided maps.
///
/// Substitution order: vars first, then paths, then secrets. Within each
/// namespace both `{{ ns.key }}` (with spaces) and `{{ns.key}}` (without)
/// are supported.
pub fn resolve_string(
    template: &str,
    vars: &HashMap<String, String>,
    paths: &HashMap<String, String>,
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

    for (key, value) in paths {
        let patterns = [
            format!("{{{{ paths.{key} }}}}"),
            format!("{{{{paths.{key}}}}}"),
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

/// Validate that secrets and paths are present and non-empty.
///
/// Returns a list of warning strings; empty if everything is set.
pub fn validate_refs(config: &Config) -> Vec<String> {
    let mut errors = Vec::new();

    for (key, value) in &config.secrets {
        if value.trim().is_empty() {
            errors.push(format!(
                "Secret '{}' is empty — set it in config.yaml or it will be prompted",
                key
            ));
        }
    }

    for (key, value) in &config.paths {
        if value.trim().is_empty() {
            errors.push(format!("Path '{}' is empty", key));
        }
    }

    errors
}

#[cfg(test)]
mod tests {
    use super::*;

    fn map(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    #[test]
    fn resolve_paths_with_spaces() {
        let result = resolve_string(
            "src: {{ paths.repo }}",
            &map(&[]),
            &map(&[("repo", "/home/u/proj")]),
            &map(&[]),
        );
        assert_eq!(result, "src: /home/u/proj");
    }

    #[test]
    fn resolve_paths_without_spaces() {
        let result = resolve_string(
            "src: {{paths.repo}}",
            &map(&[]),
            &map(&[("repo", "/home/u/proj")]),
            &map(&[]),
        );
        assert_eq!(result, "src: /home/u/proj");
    }

    #[test]
    fn resolve_paths_does_not_collide_with_vars() {
        // Same key in both vars and paths — paths wins for {{ paths.X }},
        // vars wins for {{ vars.X }}. They never overlap by construction.
        let result = resolve_string(
            "v={{ vars.x }} p={{ paths.x }}",
            &map(&[("x", "from-vars")]),
            &map(&[("x", "from-paths")]),
            &map(&[]),
        );
        assert_eq!(result, "v=from-vars p=from-paths");
    }

    #[test]
    fn resolve_all_three_namespaces() {
        let result = resolve_string(
            "{{ vars.a }}|{{ paths.b }}|{{ secrets.c }}",
            &map(&[("a", "VA")]),
            &map(&[("b", "PB")]),
            &map(&[("c", "SC")]),
        );
        assert_eq!(result, "VA|PB|SC");
    }

    #[test]
    fn find_unresolved_picks_up_paths() {
        let unresolved = find_unresolved("src: {{ paths.missing }}");
        assert_eq!(unresolved, vec!["{{ paths.missing }}"]);
    }
}
