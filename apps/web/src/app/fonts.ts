import localFont from "next/font/local";

// The site's three typefaces, stored in the repo so a build never fetches anything from Google.
//
// The files in ./fonts are the woff2 files Google Fonts serves (fonts.googleapis.com/css2, fetched 2026-11-13)
// for exactly what this app used to request through next/font/google:
//   Sora           wght 500, 600, 700   (one variable file per subset)
//   IBM Plex Sans  wght 400, 500, 600   (one variable file per subset)
//   IBM Plex Mono  wght 400, 500        (one static file per weight and subset)
// Each family keeps every subset Google's stylesheet declared, each with Google's unicode-range, so a character
// outside basic Latin (a Vietnamese or Polish name, a box-drawing glyph in mono) renders in the same face as before,
// and the browser only downloads a subset file when the page uses one of its characters. As before, only the latin
// files are preloaded, the family names are 'Sora', 'IBM Plex Sans' and 'IBM Plex Mono', and each has a metric-matched
// Arial fallback ('<family> Fallback'). Licence: SIL Open Font License 1.1 (./fonts/OFL-*.txt).
//
// The latin call of each family sets the CSS variable globals.css reads (--font-display, --font-body, --font-mono).
// The other subsets carry a variable of their own only so their @font-face rules are part of the page's CSS;
// nothing reads those variables. Calls are listed in Google's order (latin last), which decides overlapping ranges.
// next/font needs literal arguments, so each call is written out in full.
// e2e/fonts.spec.ts checks that every file named here exists and that nothing imports next/font/google.

const soraLatinExt = localFont({
  src: [
    { path: "./fonts/sora-latin-ext.woff2", weight: "500", style: "normal" },
    { path: "./fonts/sora-latin-ext.woff2", weight: "600", style: "normal" },
    { path: "./fonts/sora-latin-ext.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-display-latin-ext",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'Sora'" },
    { prop: "unicode-range", value: "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF" },
  ],
});

const soraLatin = localFont({
  src: [
    { path: "./fonts/sora-latin.woff2", weight: "500", style: "normal" },
    { path: "./fonts/sora-latin.woff2", weight: "600", style: "normal" },
    { path: "./fonts/sora-latin.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-display",
  display: "swap",
  adjustFontFallback: "Arial",
  declarations: [
    { prop: "font-family", value: "'Sora'" },
    { prop: "unicode-range", value: "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD" },
  ],
});

const ibmPlexSansCyrillicExt = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-cyrillic-ext.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-cyrillic-ext.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-cyrillic-ext.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-body-cyrillic-ext",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Sans'" },
    { prop: "unicode-range", value: "U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F" },
  ],
});

const ibmPlexSansCyrillic = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-cyrillic.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-cyrillic.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-cyrillic.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-body-cyrillic",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Sans'" },
    { prop: "unicode-range", value: "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116" },
  ],
});

const ibmPlexSansGreek = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-greek.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-greek.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-greek.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-body-greek",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Sans'" },
    { prop: "unicode-range", value: "U+0370-0377, U+037A-037F, U+0384-038A, U+038C, U+038E-03A1, U+03A3-03FF" },
  ],
});

const ibmPlexSansVietnamese = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-vietnamese.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-vietnamese.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-vietnamese.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-body-vietnamese",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Sans'" },
    { prop: "unicode-range", value: "U+0102-0103, U+0110-0111, U+0128-0129, U+0168-0169, U+01A0-01A1, U+01AF-01B0, U+0300-0301, U+0303-0304, U+0308-0309, U+0323, U+0329, U+1EA0-1EF9, U+20AB" },
  ],
});

const ibmPlexSansLatinExt = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-latin-ext.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-latin-ext.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-latin-ext.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-body-latin-ext",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Sans'" },
    { prop: "unicode-range", value: "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF" },
  ],
});

const ibmPlexSansLatin = localFont({
  src: [
    { path: "./fonts/ibm-plex-sans-latin.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-sans-latin.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-sans-latin.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-body",
  display: "swap",
  adjustFontFallback: "Arial",
  declarations: [
    { prop: "font-family", value: "'IBM Plex Sans'" },
    { prop: "unicode-range", value: "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD" },
  ],
});

const ibmPlexMonoCyrillicExt = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-cyrillic-ext-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-cyrillic-ext-500.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-mono-cyrillic-ext",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Mono'" },
    { prop: "unicode-range", value: "U+0460-052F, U+1C80-1C8A, U+20B4, U+2DE0-2DFF, U+A640-A69F, U+FE2E-FE2F" },
  ],
});

const ibmPlexMonoCyrillic = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-cyrillic-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-cyrillic-500.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-mono-cyrillic",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Mono'" },
    { prop: "unicode-range", value: "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116" },
  ],
});

const ibmPlexMonoSymbols2 = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-symbols2-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-symbols2-500.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-mono-symbols2",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Mono'" },
    { prop: "unicode-range", value: "U+2000-2001, U+2004-2008, U+200A, U+23B8-23BD, U+2500-259F" },
  ],
});

const ibmPlexMonoVietnamese = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-vietnamese-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-vietnamese-500.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-mono-vietnamese",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Mono'" },
    { prop: "unicode-range", value: "U+0102-0103, U+0110-0111, U+0128-0129, U+0168-0169, U+01A0-01A1, U+01AF-01B0, U+0300-0301, U+0303-0304, U+0308-0309, U+0323, U+0329, U+1EA0-1EF9, U+20AB" },
  ],
});

const ibmPlexMonoLatinExt = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-latin-ext-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-latin-ext-500.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-mono-latin-ext",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    { prop: "font-family", value: "'IBM Plex Mono'" },
    { prop: "unicode-range", value: "U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF" },
  ],
});

const ibmPlexMonoLatin = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-latin-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-latin-500.woff2", weight: "500", style: "normal" },
  ],
  variable: "--font-mono",
  display: "swap",
  adjustFontFallback: "Arial",
  declarations: [
    { prop: "font-family", value: "'IBM Plex Mono'" },
    { prop: "unicode-range", value: "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD" },
  ],
});

/** Every font's variable class, for the root <html> element. */
export const fontVariables = [
  soraLatinExt.variable,
  soraLatin.variable,
  ibmPlexSansCyrillicExt.variable,
  ibmPlexSansCyrillic.variable,
  ibmPlexSansGreek.variable,
  ibmPlexSansVietnamese.variable,
  ibmPlexSansLatinExt.variable,
  ibmPlexSansLatin.variable,
  ibmPlexMonoCyrillicExt.variable,
  ibmPlexMonoCyrillic.variable,
  ibmPlexMonoSymbols2.variable,
  ibmPlexMonoVietnamese.variable,
  ibmPlexMonoLatinExt.variable,
  ibmPlexMonoLatin.variable,
].join(" ");
