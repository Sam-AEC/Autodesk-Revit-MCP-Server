# Brand

There are two things to keep apart. The product is **AEC Model Bridge** and it has one mark, the Pier. **Cerberus** is a planned feature inside the product and has its own sub-mark, the Ember mesh. The Ember mesh is never the logo of the product or the repository.

## 1. Product brand: AEC Model Bridge, the Pier mark

The Pier is an isometric model cube with a bridge arch cut through each side face, on a rounded `#111923` tile (96 px viewBox, 20 px corner radius). The top face is `#1CB5CA`, the left face `#FFFFFF`, the right face `#AEBCCB`, with a 2.5 px `#111923` stroke between faces. `assets/logo-mark.svg` is the source of truth for the geometry. See [tokens.md](tokens.md) for the palette and the surfaces that copy it, and [../../TRADEMARKS.md](../../TRADEMARKS.md) for the name and logo policy.

| File | Purpose |
| --- | --- |
| `assets/logo-mark.svg`, `assets/logo.svg` | Pier mark |
| `assets/logo-mark-512.png` | 512 px raster |
| `assets/icon.ico` | Installer and shortcuts (16, 24, 32, 48, 64, 128, 256 px) |
| `assets/installer/wizard-large.bmp` | 164x314, 24-bit, Inno Setup side panel |
| `assets/installer/wizard-small.bmp` | 55x58, 24-bit, Inno Setup header |
| `extensions/vscode/media/icon.png` | VS Code extension icon (512x512) |
| `scripts/make_brand_assets.py` | Regenerates `icon.ico`, `logo-mark-512.png` and the two installer bitmaps from the Pier geometry |

The README artwork includes [the social preview image](../images/readme/social-preview.png). GitHub takes the link-card image from repository settings; a maintainer must upload this file there. There is no `assets/social-preview.png`.

## 2. Cerberus: feature name and sub-mark

Cerberus is the name of a planned feature inside AEC Model Bridge ([ADR 0016](../0016-cerberus-multi-agent-review.md), Proposed, not built). The artwork exists; the feature does not. Its mark is the "Ember mesh": three jackal heads inside an ouroboros ring, built from flat triangular facets with ember-orange eyes. All files are in `assets/cerberus/`.

### Usage

- Use it only inside the product, to mark the Cerberus feature.
- Never use it as the repository logo, the product logo, an installer image or an extension icon.
- No text inside the mark. No mark file contains `<text>`; set the name as live text beside it.

### Minimum sizes

| Size | Use this file |
| --- | --- |
| 16 px | `mark-16.svg` (solid shapes; the three heads merge into one masked head) |
| 24 to 48 px | `mark-32.svg` (coarse mesh, no glow, no edge lines) |
| 64 px and up | `mark.svg` (full mesh) |

### Files

| File | Purpose |
| --- | --- |
| [`mark.svg`](../../assets/cerberus/mark.svg) | Full-colour master |
| [`mark-512.png`](../../assets/cerberus/mark-512.png), [`mark-1024.png`](../../assets/cerberus/mark-1024.png) | Rasters, transparent |
| [`mark-16.svg`](../../assets/cerberus/mark-16.svg), [`mark-32.svg`](../../assets/cerberus/mark-32.svg) | Small-size variants |
| [`mark-mono.svg`](../../assets/cerberus/mark-mono.svg) | One colour (`fill="currentColor"`) |
| [`mark-mono-badge.svg`](../../assets/cerberus/mark-mono-badge.svg) | Near-black disc with a white mark; works on any background |
| [`mark-dark-disc.svg`](../../assets/cerberus/mark-dark-disc.svg) | Full mark on its own dark disc, for dark UIs |
| [`cerberus.ico`](../../assets/cerberus/cerberus.ico) | 16, 24, 32, 48, 64, 128, 256 px |
| [`cerberus-hero.png`](../../assets/cerberus/cerberus-hero.png) | 1280x640 feature artwork. It is not the repository social preview |

### Do not

- Recolour the eyes.
- Add glow below 64 px.
- Stretch, rotate, crop or re-draw the mark.
- Use the full mesh below 64 px.

### Provenance

The mark is original vector artwork. No AI-generated raster image was traced. Its lineage is cited, not copied:

- the ouroboros motif, as in the Chrysopoeia of Cleopatra (Marcian MS gr. Z. 299);
- the low-poly faceted emblem style;
- the Greek myth of Kerberos, the many-headed guardian of the threshold (Hesiod, Theogony 310 to 312).
