# Third-party software and fonts

Everything the public site (SF Conditions Search, built from this app's front end C) and the local pages ship or
build with, and its licence. Nothing else is loaded: no font CDN, no images, no stock or generated assets; every
visual is code (CSS, SVG, canvas, WebGL). The one tracker is **Vercel Web Analytics** (page views, no cookies), loaded
from the site's own address (`/_vercel/insights/script.js`, served by Vercel), on the public site only.

The site build carries the notices itself: `assets/third-party-licenses.<sha256-12>.md` (written by the `licenses`
plugin in `vite.config.ts`, named in each page's head as `<link rel="license">`) holds, for every package in the
output, its name, version, licence and its own licence text. The minified bundles keep no comments of their own.

Versions are the ones installed on 2026-11-17 (`pnpm-lock.yaml` at the repo root is the record).

## Fonts (self-hosted through the @fontsource packages)

All five families are under the **SIL Open Font License 1.1** (OFL-1.1). Each package carries the licence text
in its `LICENSE` file (checked: the text "SIL OPEN FONT LICENSE Version 1.1" is in all five). Only the latin
subset is used, as woff2, with `font-display: swap` (`src/core/fonts.css`).

| Family | Used for | Package | Package version | Font version | Licence | Copyright |
| --- | --- | --- | --- | --- | --- | --- |
| Instrument Serif (400, 400 italic) | Display: headlines, the search field's typed text | `@fontsource/instrument-serif` | 5.3.0 | v5 | OFL-1.1 | 2022 The Instrument Serif Project Authors |
| Public Sans (variable weight, roman and italic) | UI and body | `@fontsource-variable/public-sans` | 5.3.0 | v21 | OFL-1.1 | 2015 The Public Sans Project Authors |
| IBM Plex Mono (400, 500) | Data: case numbers, dates, counts, page references | `@fontsource/ibm-plex-mono` | 5.3.0 | v20 | OFL-1.1 | 2017 IBM Corp. |
| Big Shoulders Display (800, 900) | The stamp and the wordmark | `@fontsource/big-shoulders-display` | 5.3.0 | v21 | OFL-1.1 | The package's LICENSE names Google Inc. |
| Architects Daughter (400) | Hand lettering for margin notes | `@fontsource/architects-daughter` | 5.3.0 | v20 | OFL-1.1 | 2010 Kimberly Geswein |

"Font version" is the Google Fonts release the package was built from (`metadata.json` in each package).

Files shipped (latin subset, woff2): Instrument Serif 21.0 kB + 22.1 kB, Public Sans 26.8 kB + 28.3 kB,
IBM Plex Mono 14.7 kB + 14.9 kB, Big Shoulders Display 14.6 kB + 14.0 kB, Architects Daughter 13.2 kB.
A page preloads only the faces its first paint needs (five on the front page, whose gate shows all five; four on the coverage page).

## Libraries shipped to the browser

| Library | Version | Licence | Used for |
| --- | --- | --- | --- |
| three | 0.187.0 | MIT | The 3D map (`src/c/scene.ts`, `src/core/world`) and the 3D stamp (`src/core/stamp/stamp3d.ts`); its own chunk, loaded after the first paint |
| lenis | 1.3.27 | MIT | Smooth scrolling for the scroll story (`src/core/story/engine.ts`) |
| motion | 14.14.0 | MIT | The spring and the small animations of the crack at the gate (`src/core/stamp/crack.ts`); it brings `framer-motion` 14.14.0, `motion-dom` 14.14.0 and `motion-utils` 14.7.0 (all MIT) |

No GSAP and no other animation library.

## Build and test tools (not shipped)

| Tool | Version | Licence |
| --- | --- | --- |
| vite | 8.3.8 | MIT |
| typescript | 5.9.3 | Apache-2.0 |
| @playwright/test | 1.64.1 | Apache-2.0 |
| @types/three | 0.187.0 | MIT |
| @types/node | 20.19.43 | MIT |

## From this repository

The search rules and the coverage note are imported, unchanged, from `tools/conditions-search/search.js` and
`tools/conditions-search/coverage.js`. The data is `tools/conditions-search/data/conditions.json`, built from
public San Francisco Planning records. The motion PDFs are linked, not copied: the public site's build points them at its file store
(`<store>/motions/<record>.pdf`, see `scripts/validation/build_public_conditions_site.py`).
