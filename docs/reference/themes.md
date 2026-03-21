# Design Tokens

CUTIP's documentation site uses a custom color palette built on
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).
The same tokens are intended for reuse by cutip-desktop and any future
CUTIP-branded UI.

## Color Palette

### Dark (default)

| Token | Value | Usage |
|-------|-------|-------|
| Background | `#1f1f1f` | Page body (`--md-default-bg-color`) |
| Sidebar / Header | `#181818` | Side navigation, top bar, code blocks |
| Accent | `#0078d4` | Links, active nav items, buttons |
| Text | `#cccccc` | Body text (`--md-default-fg-color`) |
| Footer | `#181818` | Footer background |
| Footer (dark) | `#141414` | Footer bottom strip |

### Light

| Token | Value | Usage |
|-------|-------|-------|
| Accent | `#0078d4` | Links, active nav items, buttons |
| Header | `#005a9e` | Top bar background (accent-dark) |

## CSS Variables

All tokens live in `docs/stylesheets/cutip.css` and are scoped to the
Material theme's `data-md-color-scheme` attribute:

```css
/* Dark */
[data-md-color-scheme="slate"] {
  --md-default-bg-color: #1f1f1f;
  --md-default-fg-color: #cccccc;
  --md-primary-fg-color: #0078d4;
  --md-accent-fg-color: #0078d4;
  --md-code-bg-color: #181818;
}

/* Light */
[data-md-color-scheme="default"] {
  --md-primary-fg-color: #0078d4;
  --md-accent-fg-color: #0078d4;
}
```

## Reuse in cutip-desktop

Desktop or any downstream project should read these tokens from
`docs/stylesheets/cutip.css` as the single source of truth. The CSS
variable names follow Material for MkDocs conventions, but the hex
values are portable to any framework (Qt, Electron, GTK).

## Toggling Themes

The site ships dark by default. Users toggle between dark and light
with the sun/moon icon in the header. The first palette entry in
`mkdocs.yml` is the default.
