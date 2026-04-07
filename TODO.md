# CUTIP Documentation & Positioning TODO

Driven by external analysis showing cutip is perceived as a vague Docker competitor. The actual value (workflow automation using containers as execution environments) is not communicated.

---

## PyPI (`pyproject.toml`)

- [x] Rewrite `description` — "Workflow automation framework — define infrastructure as YAML, automate with Python, execute in containers"
- [x] `long_description` via README.md — already configured (`readme = "README.md"`)
- [x] Fix classifiers — added Systems Administration, AsyncIO
- [x] `project.urls` — already had Homepage, Documentation, Repository, Bug Tracker

## GitHub README

- [x] Lead with the problem, not the acronym
- [x] Add "What cutip is NOT" section
- [x] Add comparison table — cutip vs Bash vs Docker Compose vs Ansible
- [x] Add concrete before/after example (bash script vs cutip workflow)
- [x] Add "Who is this for?" section
- [x] Add quick start section
- [x] Link to cutip-desktop and cutip-blocks (Ecosystem table)
- [ ] Screenshot of cutip-desktop DAG — need actual screenshot file

## MkDocs Site (`docs/`)

- [x] "Concepts" page — already existed (concepts/overview.md + cards/units/groups/lifecycle)
- [x] "Use Cases" page — added with 3 real examples (VM ops, dev environment, infrastructure provisioning)
- [x] "Why CUTIP?" page — already existed with detailed Docker Compose comparison
- [ ] Add "Blocks" page — document cutip-blocks as the standard library with examples per category
- [ ] Add "cutip vs X" page — extend beyond Docker Compose (vs Ansible, Bash, Dagger)
- [ ] Improve API reference — auto-generate from docstrings with usage examples for key classes

## CLI Improvements (documentation-adjacent)

- [ ] Add `cutip doctor` — check runtime availability, validate workspace, report health
- [ ] Add `cutip block ls` — list available blocks from cutip-blocks with descriptions

## General

- [ ] Write announcement / blog post explaining the origin story and positioning
