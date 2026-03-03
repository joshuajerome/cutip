# GitHub Release Notes Template

Use this when running `gh release edit vX.Y.Z --notes "..."`.

Fill every `{placeholder}`. Write only user-facing changes.
Omit: CI fixes, doc cleanups, internal refactors, test changes.

**Format rules:**
- List capabilities added/fixed — one bullet per cap ID
- Do not list individual PRs, authors, or "What's Changed" auto-generated content
- Replace any GitHub-generated release notes entirely with this template

---

## GitHub Release page body

```
Container Unit Templates in Python — deterministic framework for building
and orchestrating Podman container workloads.

## Features

- **cap{N} — {title}**: {one sentence — what the user can now do}
- **cap{M} — {title}**: {one sentence — what the user can now do}

## Patch Notes

- **cap{P} — {title}**: {one sentence — what error is fixed}
- **cap{Q} — {title}**: {one sentence — what error is fixed}

## Installation

```bash
pip install cutip=={X.Y.Z}
```

Or install the wheel directly from this release:

```bash
pip install cutip-{X.Y.Z}-py3-none-any.whl
```

**Full Changelog**: https://github.com/joshuajerome/cutip/compare/v{A.B.C}...v{X.Y.Z}
```

Omit `## Features` entirely if no `feat/*` caps shipped in this release.
Omit `## Patch Notes` entirely if no `bug/*` caps shipped in this release.

---

## docs/patch-notes.md entry

Prepend this block after the `# Patch Notes` heading in `docs/patch-notes.md`:

```markdown
## v{X.Y.Z} ({YYYY-MM-DD})

### Features

- **cap{N}** — {title}: {what changed from a user perspective}
- **cap{M}** — {title}: {what the user can now do}

### Patch Notes

- **cap{P}** — {title}: {what was broken, what now works}
- **cap{Q}** — {title}: {behavioral impact}
```

Omit `### Features` if no feat caps. Omit `### Patch Notes` if no bug caps.

---

## Checklist before saving

- [ ] Every shipped cap ID appears exactly once
- [ ] feat/* caps are in `## Features`; bug/* caps are in `## Patch Notes`
- [ ] Sections with no caps are omitted entirely
- [ ] No mention of CI, docs, or internal-only changes
- [ ] No PR numbers, authors, or GitHub-generated content
- [ ] Installation commands use the correct version number
- [ ] Full Changelog URL uses the previous tag as the base (`v{A.B.C}`)
- [ ] patch-notes.md entry is prepended (not appended)
