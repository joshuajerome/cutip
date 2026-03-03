# Capabilities

This registry tracks every discrete capability (feature or bug fix) merged into CUTIP.
Each capability is assigned a unique ID (`cap001`, `cap002`, ...) used in branch names,
commit messages, and PR titles.

## Registry

| ID     | Title                                                  | Type | Status | Branch                              | PR  | Date       |
|--------|--------------------------------------------------------|------|--------|-------------------------------------|-----|------------|
| cap001 | Initial scaffold                                       | feat | merged | —                                   | —   | 2024-01-01 |
| cap002 | Validate generated vars + extend _validate_vars to env | bug  | merged | bug/cap002-validate-vars-coverage   | #7  | 2026-02-28 |
| cap003 | Remove non-existent [podman] extra from CI             | bug  | merged | bug/cap003-fix-podman-extra         | #8  | 2026-02-28 |
| cap004 | Add MIT license                                        | feat | merged | feat/cap004-mit-license             | #9  | 2026-02-28 |
| cap005 | Remove deprecated --backend flag from e2e steps        | bug  | merged | bug/cap005-fix-e2e-backend-flag     | #10 | 2026-02-28 |
| cap006 | Translate Windows bind-mount paths to WSL2 format      | bug  | open   | bug/cap006-win-path-wsl-translation | —   | 2026-03-02 |
| cap007 | Improve init scaffold, validate logs, group name match | feat | merged | feat/cap007-scaffold-validate-completion | #36 | 2026-03-03 |
| cap008 | Add docker-compose vs CUTIP comparison to docs and README | feat | merged | feat/cap008-compose-comparison-docs      | #37 | 2026-03-03 |
| cap009 | Rename scaffold hello→simple, add complex project, e2e tests | feat | merged | feat/cap009-scaffold-simple-complex      | #38 | 2026-03-03 |
| cap010 | cutip from-compose — convert compose.yaml to CUTIP artifacts  | feat | planned | —                                       | —   | —          |
| cap011 | cutip push/pull — git-based artifact registry                 | feat | planned | —                                       | —   | —          |
| cap012 | Docker backend support                                        | feat | planned | —                                       | —   | —          |
| cap013 | Mac/Apple Silicon Podman CI + docs                           | feat | merged | feat/cap013-mac-podman-ci-docs          | #40 | 2026-03-03 |
| cap014 | Remove Jenkins, migrate AI doc scripts to GHA               | feat | merged | feat/cap014-remove-jenkins-migrate-gha  | #41 | 2026-03-03 |
| cap015 | Consolidate GHA workflows + PR auto-label/assign            | feat | merged | feat/cap015-consolidate-workflows       | #42 | 2026-03-03 |

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
