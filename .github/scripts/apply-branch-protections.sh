#!/usr/bin/env bash
# apply-branch-protections.sh
#
# Applies branch protection rules to integration, staging, and release/* branches.
# Requires: gh auth login (GitHub CLI authenticated with repo admin scope)
#
# Usage: bash .github/scripts/apply-branch-protections.sh joshuajerome/cutip

set -euo pipefail

REPO="${1:-joshuajerome/cutip}"

REQUIRED_CHECKS='[
  "pr-checks / unit-tests",
  "pr-checks / smoke-test",
  "pr-checks / e2e-podman-ubuntu",
  "pr-checks / e2e-podman-windows",
  "pr-checks / docs-build"
]'

PROTECTION_PAYLOAD=$(cat <<EOF
{
  "required_status_checks": {
    "strict": true,
    "contexts": $(echo "$REQUIRED_CHECKS")
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false
}
EOF
)

apply_protection() {
  local branch="$1"
  echo "Applying protection to branch: $branch"
  gh api "repos/${REPO}/branches/${branch}/protection" \
    --method PUT \
    --input - <<< "$PROTECTION_PAYLOAD"
  echo "  Done."
}

apply_protection "integration"
apply_protection "staging"

echo ""
echo "Branch protections applied successfully."
echo ""
echo "Next steps (if not already done):"
echo "  1. Go to https://github.com/${REPO}/settings → Branches"
echo "     → Change default branch to 'integration'"
echo "  2. Delete the old 'main' branch from remote:"
echo "     git push origin --delete main"
echo "  3. Add ANTHROPIC_API_KEY secret:"
echo "     https://github.com/${REPO}/settings/secrets/actions"
