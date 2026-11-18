import { createHash } from "node:crypto";
import { createReadStream, readFileSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { defineConfig, type Plugin } from "vite";
import { readSubset, SOURCE as STORY_SOURCE } from "./tools/story-facts.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../..");
const tool = resolve(repo, "tools/conditions-search");

/** The public site's name: the tab title of its pages (the wordmark on the page stays src/core/brand.ts's). */
const SITE_NAME = "SF Conditions Search";
/** The live site's description, as scripts/validation/build_public_conditions_site.py writes it. */
const SITE_DESCRIPTION =
  "Search the conditions of approval San Francisco's Planning Commission set for restaurants, bars and entertainment venues.";
/** The tag of Vercel Web Analytics, as the current site's pages carry it (the build checks it is there once). */
const ANALYTICS_TAG = '<script defer src="/_vercel/insights/script.js"></script>';

// ---- two builds ---------------------------------------------------------------------------------------------------
// `vite build` (and `vite` in dev): the local pages. / is a short contents page, /c/ the front page ("the living
// grid"), /search/ the search on its own, /coverage/ the coverage page. The data is the local file.
//
// `vite build --mode site`: the front end of the public site, SF Conditions Search. Run by
// scripts/validation/build_public_conditions_site.py (--front c), which prepares the public data and passes it in:
//   SHOWCASE_DATA         the public data file (private contacts withheld, no raw_text, motion links to the store)
//   SHOWCASE_COVERAGE_MD  the public coverage text (public/coverage.md plus the builder's own sections)
//   SHOWCASE_CONTACT      the address of the contact line and of every card's "Wrong or missing? Tell me"
// It writes index.html (the front page) and coverage.html at the top of the output, as the live site has them, and
// every script, style, font and data file under assets/, named by its content. No source maps, nothing inlined
// (the site's Content-Security-Policy allows no data: fonts), no public/ folder copied.

function env(name: string, required: boolean): string | undefined {
  const value = process.env[name];
  if (required && !value) throw new Error(`vite --mode site needs ${name} (scripts/validation/build_public_conditions_site.py sets it)`);
  return value || undefined;
}

/** "assets/<stem>.<first 12 hex of sha256>.<ext>": the public site's own naming of content-named files. */
function hashedName(stem: string, ext: string, bytes: Buffer | string): string {
  return `assets/${stem}.${createHash("sha256").update(bytes).digest("hex").slice(0, 12)}.${ext}`;
}

/** The map's motions as the page reads them: the points, with the fields the page uses, and nothing else (the
 *  file's notes on how the points were found are not for the public). */
function publicMotions(): string {
  const raw = JSON.parse(readFileSync(resolve(here, "public/data/motions.json"), "utf8")) as {
    points: { record: string; year: number; n: number; x: number | null; y: number | null; sx: number | null; sy: number | null }[];
  };
  const points = raw.points.map(({ record, year, n, x, y, sx, sy }) => ({ record, year, n, x, y, sx, sy }));
  return `${JSON.stringify({ points })}\n`;
}

interface SiteFiles {
  conditions: string;
  motions: string;
  streets: string;
  coverage: string;
}
interface SiteConfig {
  name: string;
  contact: string;
  pdfBase: string;
  files: SiteFiles;
  pages: { search: string; coverage: string };
}

export default defineConfig(({ mode }) => {
  const site = mode === "site";

  // The search data stays where the current site keeps it. SHOWCASE_DATA points the pages at another copy (the site
  // build always passes the public build's own).
  const dataFile = resolve(env("SHOWCASE_DATA", site) ?? resolve(tool, "data/conditions.json"));
  const DATA_PATH = "data/conditions.json";

  /** The counts the pages show before the data has loaded ("Reading 352 motions…"), and the file's size, which is
   *  the progress total when the transfer is compressed and Content-Length cannot be used. */
  function dataFacts(): { conditions: number; motions: number; bytes: number } {
    const raw = readFileSync(dataFile);
    const d = JSON.parse(raw.toString("utf8")) as { count: number; motions_with_conditions: number };
    return { conditions: d.count, motions: d.motions_with_conditions, bytes: raw.byteLength };
  }

  // ---- the site build's files: read once, named by their content --------------------------------------------------
  let siteConfig: SiteConfig | null = null;
  const siteSources: { fileName: string; source: Buffer | string }[] = [];
  if (site) {
    const conditions = readFileSync(dataFile);
    const coverage = readFileSync(resolve(env("SHOWCASE_COVERAGE_MD", true)!));
    const streets = readFileSync(resolve(here, "public/data/sf-streets.bin"));
    const motions = publicMotions();
    const files: SiteFiles = {
      conditions: hashedName("conditions", "json", conditions),
      motions: hashedName("motions", "json", motions),
      streets: hashedName("sf-streets", "bin", streets),
      coverage: hashedName("coverage", "md", coverage),
    };
    siteSources.push(
      { fileName: files.conditions, source: conditions },
      { fileName: files.motions, source: motions },
      { fileName: files.streets, source: streets },
      { fileName: files.coverage, source: coverage },
    );
    siteConfig = {
      name: SITE_NAME,
      // (optional: a copy built without an address has no contact line and no card link)
      contact: env("SHOWCASE_CONTACT", false) ?? "",
      pdfBase: env("SHOWCASE_PDF_BASE", false) ?? "",
      // root-relative: the pages sit at the top of the site
      files: Object.fromEntries(Object.entries(files).map(([k, v]) => [k, `/${v}`])) as unknown as SiteFiles,
      pages: { search: "/", coverage: "/coverage.html" },
    };
  }

  /** Serves the data file at /data/conditions.json in dev and writes it to dist/data/ on build. No copy is kept in
   *  this app's folders. (The site build writes its own content-named copy instead.) */
  function conditionsData(): Plugin {
    return {
      name: "showcase:conditions-data",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const path = (req.url ?? "").split("?")[0];
          if (path !== `/${DATA_PATH}`) return next();
          const size = statSync(dataFile).size;
          res.statusCode = 200;
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.setHeader("Content-Length", String(size));
          res.setHeader("Cache-Control", "no-cache");
          if (req.method === "HEAD") return void res.end();
          createReadStream(dataFile).pipe(res);
        });
      },
      generateBundle() {
        if (site) {
          for (const file of siteSources) this.emitFile({ type: "asset", fileName: file.fileName, source: file.source });
        } else this.emitFile({ type: "asset", fileName: DATA_PATH, source: readFileSync(dataFile) });
      },
    };
  }

  /** The sections of the current site's README that its coverage.html shows, in its order. */
  const README_SECTIONS = ["Coverage", "Text quality", "Motions left out: not food or drink", "Motion PDFs on the public site"];

  /** "virtual:coverage-sections": those sections of tools/conditions-search/README.md, cut out when the dev server
   *  or the build starts by the current site's own markdownSection() (coverage.js), so the coverage page carries
   *  them and not the whole README. No copy is kept in this app's folders. The site build carries none: its
   *  coverage page reads the public coverage text, as the live coverage.html does. */
  function coverageSections(): Plugin {
    const id = "virtual:coverage-sections";
    const resolved = `\0${id}`;
    const readme = resolve(tool, "README.md");
    return {
      name: "showcase:coverage-sections",
      resolveId(source) {
        return source === id ? resolved : undefined;
      },
      async load(which) {
        if (which !== resolved) return undefined;
        if (site) return "export default [];";
        this.addWatchFile(readme);
        const { markdownSection } = (await import(pathToFileURL(resolve(tool, "coverage.js")).href)) as {
          markdownSection(md: string, heading: string): string;
        };
        const md = readFileSync(readme, "utf8");
        const sections = README_SECTIONS.map(heading => ({ heading, body: markdownSection(md, heading) })).filter(x => x.body);
        return `export default ${JSON.stringify(sections)};`;
      },
    };
  }

  /** "virtual:story-facts": the part of src/data/story.json the story shows (tools/story-facts.mjs). */
  function storyFacts(): Plugin {
    const id = "virtual:story-facts";
    const resolved = `\0${id}`;
    return {
      name: "showcase:story-facts",
      resolveId(source) {
        return source === id ? resolved : undefined;
      },
      load(which) {
        if (which !== resolved) return undefined;
        this.addWatchFile(STORY_SOURCE);
        return `export default ${JSON.stringify(readSubset())};`;
      },
    };
  }

  /** The site build's pages: the live site's titles and description, no "noindex", Vercel Web Analytics exactly as
   *  the current site loads it (its snippet, read from tools/conditions-search/index.html), and the two pages moved
   *  to the top of the output as index.html and coverage.html. */
  function sitePages(): Plugin {
    const source = readFileSync(resolve(tool, "index.html"), "utf8");
    const start = source.indexOf("<script>\n  window.va");
    const end = source.indexOf(ANALYTICS_TAG);
    if (start < 0 || end < start) throw new Error("tools/conditions-search/index.html no longer carries the analytics snippet");
    const analytics = source.slice(start, end + ANALYTICS_TAG.length);
    const RENAME: Record<string, string> = { "c/index.html": "index.html", "coverage/index.html": "coverage.html" };
    return {
      name: "showcase:site-pages",
      apply: "build",
      transformIndexHtml: {
        order: "post",
        handler(html, ctx) {
          const coverage = ctx.path.startsWith("/coverage/");
          const title = coverage ? `Coverage · ${SITE_NAME}` : SITE_NAME;
          let out = html
            .replace(/<title>[^<]*<\/title>/, `<title>${title}</title>`)
            .replace(/<meta name="robots" content="noindex">\n?/, "")
            .replace(/ data-root="[^"]*"/, ' data-root="/"')
            // the notes in the inline script are for this repository, not for the public
            .replace(/^[ \t]*\/\/[^\n]*\n/gm, "");
          if (!coverage) out = out.replace(/<meta name="description" content="[^"]*">/, `<meta name="description" content="${SITE_DESCRIPTION}">`);
          // without scripts the page still says who to write to (the contact line's own words)
          const contact = siteConfig?.contact;
          if (contact) {
            out = out.replace(
              "</noscript>",
              `  <p style="max-width: 40rem; margin: 1rem auto; padding: 0 1rem">Questions or corrections: <a href="mailto:${contact}">${contact}</a>.</p>\n</noscript>`,
            );
          }
          // the snippet goes right after the title and description, as on the current site
          out = out.replace(/(<meta name="description" content="[^"]*">)/, `$1\n${analytics}`);
          if (out.split(ANALYTICS_TAG).length !== 2) throw new Error(`${ctx.path}: the analytics tag must be in the page once`);
          return out;
        },
      },
      generateBundle: {
        order: "post",
        handler(_options, bundle) {
          for (const [from, to] of Object.entries(RENAME)) {
            const page = bundle[from];
            if (!page || page.type !== "asset") throw new Error(`the site build made no ${from}`);
            const source = page.source;
            delete bundle[from];
            this.emitFile({ type: "asset", fileName: to, source });
          }
        },
      },
    };
  }

  /** The site build's notices: every package from node_modules that is in the output (three.js, Lenis, the font
   *  packages), with its version, licence and its own licence text, as assets/third-party-licenses.<sha256-12>.md,
   *  named in each page's head (<link rel="license">). The minified bundles keep no comments of their own. */
  function licenses(): Plugin {
    const LICENSE_FILES = ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "license", "license.md", "OFL.txt"];
    return {
      name: "showcase:licenses",
      apply: "build",
      generateBundle: {
        order: "post",
        handler(_options, bundle) {
          const roots = new Set<string>();
          for (const id of this.getModuleIds()) {
            const path = id.replace(/^\0/, "").split("?")[0] ?? "";
            const at = path.lastIndexOf("/node_modules/");
            if (at < 0) continue;
            const rest = path.slice(at + "/node_modules/".length).split("/");
            const name = rest[0]?.startsWith("@") ? `${rest[0]}/${rest[1]}` : rest[0];
            if (name) roots.add(`${path.slice(0, at)}/node_modules/${name}`);
          }
          // (the fonts are files a stylesheet points at, not modules: their packages are read off fonts.css)
          const fontsCss = readFileSync(resolve(here, "src/core/fonts.css"), "utf8");
          for (const m of fontsCss.matchAll(/node_modules\/(@fontsource(?:-variable)?\/[\w-]+)\//g)) roots.add(resolve(here, "node_modules", m[1]!));
          const parts = [...roots].sort((a, b) => a.split("/node_modules/").pop()!.localeCompare(b.split("/node_modules/").pop()!)).map(root => {
            const pkg = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8")) as { name: string; version: string; license?: string };
            const file = LICENSE_FILES.map(n => resolve(root, n)).find(p => {
              try {
                return statSync(p).isFile();
              } catch {
                return false;
              }
            });
            const text = file ? readFileSync(file, "utf8").trim() : `(no licence file in the package; its package.json says ${pkg.license ?? "nothing"})`;
            return `## ${pkg.name} ${pkg.version} (${pkg.license ?? "see below"})\n\n${text}\n`;
          });
          const body = `# Third-party software and fonts in this site\n\nEach package below is part of this site's scripts, styles or fonts, as built. Its licence follows it.\n\n${parts.join("\n")}`;
          const fileName = hashedName("third-party-licenses", "md", body);
          this.emitFile({ type: "asset", fileName, source: body });
          // each page names it in its head
          for (const page of ["index.html", "coverage.html"]) {
            const html = bundle[page];
            if (html?.type === "asset" && typeof html.source === "string") {
              html.source = html.source.replace("</head>", `  <link rel="license" href="/${fileName}">\n</head>`);
            }
          }
        },
      },
    };
  }

  const page = (p: string) => resolve(here, p);

  // Several builders work in this tree at once. Each sets its own ports and build folder so they never collide:
  // SHOWCASE_PORT is the dev server's port (the preview server takes the next one up), SHOWCASE_OUT the build folder.
  const devPort = Number(process.env.SHOWCASE_PORT ?? 4310);
  const outDir = process.env.SHOWCASE_OUT ?? (site ? "dist-site" : "dist");

  return {
    root: here,
    base: site ? "/" : "./",
    appType: "mpa",
    publicDir: site ? false : "public",
    plugins: [conditionsData(), coverageSections(), storyFacts(), ...(site ? [sitePages(), licenses()] : [])],
    define: {
      __DATA_FACTS__: JSON.stringify(dataFacts()),
      __SITE__: JSON.stringify(siteConfig),
    },
    resolve: {
      alias: [
        // the search logic and the coverage note, imported unchanged from the current site (no copy, no fork)
        { find: "@conditions/search", replacement: resolve(tool, "search.js") },
        { find: "@conditions/coverage", replacement: resolve(tool, "coverage.js") },
      ],
    },
    server: {
      port: devPort,
      strictPort: true,
      fs: { allow: [repo] },
    },
    preview: {
      port: devPort + 1,
      strictPort: true,
    },
    build: {
      outDir,
      emptyOutDir: true,
      target: "es2022",
      sourcemap: false,
      // three.js is its own chunk (about 140 kB gzipped), loaded after the first paint
      chunkSizeWarningLimit: 600,
      // the site: every file by its own content-named URL (a data: font would need a looser CSP)
      assetsInlineLimit: site ? 0 : undefined,
      rolldownOptions: {
        input: (site
          ? { index: page("c/index.html"), coverage: page("coverage/index.html") }
          : {
              hub: page("index.html"),
              c: page("c/index.html"),
              search: page("search/index.html"),
              coverage: page("coverage/index.html"),
            }) as Record<string, string>,
        output: site
          ? {
              entryFileNames: "assets/[name]-[hash].js",
              chunkFileNames: "assets/[name]-[hash].js",
              assetFileNames: "assets/[name]-[hash][extname]",
            }
          : undefined,
      },
    },
  };
});
