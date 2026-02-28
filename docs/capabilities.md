# Capabilities

This registry tracks every discrete capability (feature or bug fix) merged into CUTIP.
Each capability is assigned a unique ID (`cap001`, `cap002`, ...) used in branch names,
commit messages, and PR titles.

## Registry

| ID     | Title                     | Type | Status | Branch | PR | Date       |
|--------|---------------------------|------|--------|--------|----|------------|
| cap001 | Initial scaffold          | feat | merged | —      | —  | 2024-01-01 |

## ID Assignment

- Format: `cap001` → `cap002` → ... (zero-padded, 3 digits minimum)
- Next ID: read the highest existing ID above and increment by 1
- IDs are assigned at branch creation time and never reused

## How Cap IDs Are Used

| Artifact | Format |
|----------|--------|
| Branch   | `feat/cap001-short-desc` or `bug/cap001-short-desc` |
| Commits  | `[cap001] short message` |
| PR title | `[cap001] Description of capability` |
