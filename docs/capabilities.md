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
| cap006 | Translate Windows bind-mount paths to WSL2 format      | bug  | merged | bug/cap006-win-path-wsl-translation | #23 | 2026-03-02 |
| cap007 | Improve init scaffold, validate logs, group name match | feat | merged | feat/cap007-scaffold-validate-completion | #36 | 2026-03-03 |
| cap008 | Add docker-compose vs CUTIP comparison to docs and README | feat | merged | feat/cap008-compose-comparison-docs      | #37 | 2026-03-03 |
| cap009 | Rename scaffold hello→simple, add complex project, e2e tests | feat | merged | feat/cap009-scaffold-simple-complex      | #38 | 2026-03-03 |
| cap010 | cutip from-compose — convert compose.yaml to CUTIP artifacts  | feat | merged  | feat/cap010-from-compose                | #45 | 2026-03-03 |
| cap011 | cutip push/pull — git-based artifact registry                 | feat | planned | —                                       | —   | —          |
| cap012 | Docker backend support                                        | feat | merged  | feat/cap012-docker-backend              | —   | 2026-03-04 |
| cap013 | Mac/Apple Silicon Podman CI + docs                           | feat | merged | feat/cap013-mac-podman-ci-docs          | #40 | 2026-03-03 |
| cap014 | Remove Jenkins, migrate AI doc scripts to GHA               | feat | merged | feat/cap014-remove-jenkins-migrate-gha  | #41 | 2026-03-03 |
| cap015 | Consolidate GHA workflows + PR auto-label/assign            | feat | merged | feat/cap015-consolidate-workflows       | #42 | 2026-03-03 |
| cap016 | Add Windows E2E + complex workspace to release gate         | feat | merged | feat/cap016-release-full-matrix         | #43 | 2026-03-03 |
| cap017 | Fix doc language: imperative/declarative, remove overhead   | feat | merged | feat/cap017-doc-language-fixes          | #44 | 2026-03-03 |
| cap018 | Document from-compose interoperability in compose comparison | feat | merged  | feat/cap018-from-compose-docs           | #46 | 2026-03-03 |
| cap019 | Revise CI workflow matrix, Test PyPI continuity, and retry policy | feat | merged | feat/cap019-ci-matrix-testpypi-retry | #47 | 2026-03-03 |
| cap020 | Add from-compose E2E tests for 5 awesome-compose projects         | feat | merged | feat/cap020-e2e-from-compose-matrix  | #48 | 2026-03-03 |
| cap021 | Rename vars.yaml → paths.yaml + add cutip/secrets.yaml            | feat | merged | feat/cap021-paths-secrets-split      | #53 | 2026-03-04 |
| cap022 | Read backend from cutip.yaml project config                       | feat | merged | feat/cap022-yaml-backend             | #55 | 2026-03-04 |
| cap023 | Add cutip upgrade command for workspace migration                 | bug  | merged | bug/cap023-upgrade-command           | #59 | 2026-03-09 |
| cap024 | Reorganize .claude/ with github/ subdirectory                     | feat | merged | claude/cap024-claude-dir-reorg       | #60 | 2026-03-09 |
| cap025 | Bot identity for GitHub issue comments                            | feat | merged | gh/cap025-bot-identity               | #61 | 2026-03-09 |
| cap026 | Issue pipeline with approval gates                                | feat | merged | feat/cap026-issue-pipeline-gates     | #61 | 2026-03-09 |
| cap027 | Self-service issue CLI with local Claude API                      | feat | merged | feat/cap027-self-service-issues      | #62 | 2026-03-09 |
| cap028 | CLI help grouping + repo setup documentation                     | feat | merged | feat/cap028-cli-help-repo-docs       | #64 | 2026-03-09 |
| cap029 | Backend default prompt + status display                           | feat | merged | feat/cap029-backend-default-prompt   | #70 | 2026-03-14 |
| cap030 | cutip stop command for graceful group teardown                    | feat | merged | feat/cap030-stop-command             | #71 | 2026-03-15 |
| cap031 | @claude commands, welcome message, auto-diagnose for owner        | feat | merged | feat/cap031-claude-commands          | #73 | 2026-03-15 |
| cap032 | @action/@orchestrator workflow decorators + introspection         | feat | merged | feat/cap032-workflow-decorators      | #74 | 2026-03-17 |
| cap033 | cutip desktop command for workspace registration                  | feat | merged | feat/cap033-desktop-command           | #75 | 2026-03-17 |
| cap034 | Scaffold rewrite with @action/@orchestrator decorators            | feat | merged | feat/cap034-scaffold-decorators      | #76 | 2026-03-17 |
| cap035 | Fix project root discovery to anchor on cutip.yaml               | bug  | merged | bug/cap035-project-root-discovery    | #79 | 2026-03-18 |
| cap036 | cutip info command for version and workspace status              | feat | merged | feat/cap036-info-command             | #81 | 2026-03-18 |
| cap037 | Dynamic SSH tunnel port for concurrent Podman workspaces        | bug  | merged | bug/cap037-dynamic-tunnel-port       | #83 | 2026-03-18 |
| cap038 | cutip run --no-cache for clean rebuild                          | feat | merged | feat/cap038-no-cache-fresh           | #84 | 2026-03-19 |
| cap039 | Backend reconciliation prompt when project.backend is unset    | feat | merged | feat/cap039-backend-prompt           | #85 | 2026-03-19 |
| cap040 | Timestamped log files with retention                            | feat | merged | feat/cap040-timestamped-logs          | #86 | 2026-03-19 |
| cap041 | Default bridge network when no networkRef or network_mode set  | feat | merged | feat/cap041-default-bridge-network    | #87 | 2026-03-19 |
| cap042 | Build-time network mode for image builds                       | feat | merged | feat/cap042-build-network-mode        | #89 | 2026-03-19 |
| cap043 | Semantic versioning convention                                 | feat | merged | feat/cap043-semver-convention          | #92 | 2026-03-21 |
| cap044 | ruff linter/formatter + ty type checker                        | feat | merged | feat/cap044-ruff-ty                   | #91 | 2026-03-21 |
| cap045 | MkDocs dark theme + design tokens                              | feat | merged | feat/cap045-mkdocs-theme              | #96 | 2026-03-21 |
| cap046 | Trim README to essential content                               | feat | merged | feat/cap046-readme-trim               | #95 | 2026-03-21 |
| cap047 | Documentation rewrite: lifecycle, annotations, compile         | docs | merged | docs/cap047-docs-rewrite              | #97 | 2026-03-21 |
| cap048 | CLI command renames + new commands                              | feat | merged | feat/cap048-cli-commands              | #102 | 2026-03-21 |
| cap049 | CLI performance + tab completion cache                          | feat | merged | feat/cap049-cli-perf                  | #100 | 2026-03-21 |
| cap050 | Annotation system + cutip compile                               | feat | merged | feat/cap050-annotations-compile       | #101 | 2026-03-21 |
| cap051 | Unit lifecycle: prehook.py + posthook.py + HookSpec             | feat | merged | feat/cap051-unit-lifecycle             | #105 | 2026-03-21 |
| cap052 | Group orchestrator.py + ctx.run_unit()                          | feat | merged | feat/cap052-orchestrator              | #106 | 2026-03-21 |
| cap053 | cutip rm with safe archive to .cutip/trash/                     | feat | merged | feat/cap053-cutip-rm                  | #107 | 2026-03-21 |
| cap054 | cutip export/import for portable group archives                 | feat | merged | feat/cap054-import-export             | #108 | 2026-03-21 |
| cap055 | Hello-world scaffold rewrite + --blank flag                     | feat | merged | feat/cap055-hello-world-scaffold      | #109 | 2026-03-21 |
| cap056 | Optional config.yaml support in CutipContext                    | feat | merged | feat/cap056-project-config            | #110 | 2026-03-21 |
| cap057 | Validate orchestrator.py alongside workflow.py                  | bug  | merged | bug/cap057-validate-orchestrator      | #113 | 2026-03-21 |
| cap058 | Fix prehook ctx=None for explicit hook declarations            | bug  | open   | bug/cap058-prehook-ctx-none           | —   | 2026-03-21 |

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
