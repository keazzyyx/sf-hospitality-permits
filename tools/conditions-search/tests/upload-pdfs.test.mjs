// Tests for upload-pdfs.mjs (the motion PDFs of the public site, to its Vercel Blob store). No network: put and
// list are fakes, the token is a made-up string, and the PDFs are small files in a temp folder.
// Run: node --test tools/conditions-search/tests/*.test.mjs   (or `make test-conditions`)
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, writeFileSync, readFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run, mask, BASE_URL, PUT_OPTIONS, parseArgs, DEFAULT_MANIFEST } from "../upload-pdfs.mjs";

const TOKEN = "vercel_blob_rw_TestStoreId_madeUpSecretForTestsOnly123";
const ENV = { BLOB_READ_WRITE_TOKEN: TOKEN };
const STORE = BASE_URL.slice(0, -"motions/".length);

function makeManifest(n = 3, extra = {}) {
  const dir = mkdtempSync(join(tmpdir(), "upload-pdfs-"));
  const files = [];
  for (let i = 0; i < n; i++) {
    const record = `2021-00000${i}CUA`;
    const path = join(dir, `${record}.pdf`);
    writeFileSync(path, "%PDF-1.5 " + record.repeat(i + 1));
    files.push({ record, name: `${record}.pdf`, path, bytes: statSync(path).size,
      sha256: createHash("sha256").update(readFileSync(path)).digest("hex"), public_url: `${BASE_URL}${record}.pdf` });
  }
  const manifest = { public_base_url: BASE_URL, bucket: "motions", upload_limit_bytes: 52428800, count: n,
    total_bytes: files.reduce((s, f) => s + f.bytes, 0), files, ...extra };
  const mpath = join(dir, "manifest.json");
  writeFileSync(mpath, JSON.stringify(manifest));
  return { dir, mpath, manifest };
}

/** A fake store: `blobs` {pathname: size}. put/list record their calls; put fails `failures[pathname]` times. */
function fakeStore(blobs = {}, { failures = {}, pageSize = 1000, url = p => STORE + p } = {}) {
  const store = new Map(Object.entries(blobs));
  const calls = { put: [], list: [] };
  let inFlight = 0, maxInFlight = 0;
  const left = { ...failures };
  return {
    store, calls, get maxInFlight() { return maxInFlight; },
    async put(pathname, body, options) {
      calls.put.push({ pathname, bytes: body.length, options });
      inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise(r => setTimeout(r, 5));
      inFlight--;
      if (left[pathname] > 0) {
        left[pathname]--;
        throw new Error(`Vercel Blob: Access denied, token ${TOKEN} rejected`);
      }
      store.set(pathname, body.length);
      return { url: url(pathname), pathname, contentType: options.contentType };
    },
    async list(opts) {
      calls.list.push(opts);
      const all = [...store.entries()].filter(([p]) => p.startsWith(opts.prefix)).sort();
      const start = opts.cursor ? Number(opts.cursor) : 0;
      const page = all.slice(start, start + Math.min(pageSize, opts.limit ?? 1000));
      const hasMore = start + page.length < all.length;
      return { blobs: page.map(([pathname, size]) => ({ pathname, size, url: url(pathname) })), hasMore,
        ...(hasMore ? { cursor: String(start + page.length) } : {}) };
    },
  };
}

function capture() {
  const lines = { out: [], err: [] };
  return { lines, out: l => lines.out.push(l), err: l => lines.err.push(l), get all() { return [...lines.out, ...lines.err].join("\n"); } };
}

const go = (argv, fake, env = ENV) => {
  const c = capture();
  return run(argv, { env, put: fake?.put, list: fake?.list, out: c.out, err: c.err, sleep: async () => {} })
    .then(code => ({ code, ...c, text: c.all }));
};

test("the default manifest and the put options are the agreed ones", () => {
  assert.equal(BASE_URL, process.env.PDF_BASE_URL || "https://example.public.blob.vercel-storage.com/motions/");
  assert.match(DEFAULT_MANIFEST, /sf-conditions-search-pdfs\/manifest\.json$/);
  assert.equal(parseArgs([]).manifest, DEFAULT_MANIFEST);
  assert.deepEqual({ ...PUT_OPTIONS }, { access: "public", addRandomSuffix: false, allowOverwrite: true,
    contentType: "application/pdf", cacheControlMaxAge: 31536000 });
});

test("the dry run is the default: no calls, no token needed, prints count, MB, largest and pathnames", async () => {
  const { mpath, manifest } = makeManifest();
  const fake = fakeStore();
  const r = await go([mpath], fake, {});
  assert.equal(r.code, 0);
  assert.deepEqual(fake.calls, { put: [], list: [] });
  assert.match(r.text, /dry run: nothing sent\. 3 files, 0\.0 MB/);
  assert.match(r.text, /largest: 2021-000002CUA\.pdf/);
  for (const f of manifest.files) assert.ok(r.text.includes(`would upload motions/${f.name}`));
  // with a token set, still nothing is sent and the token is not printed
  const again = await go([mpath, "--dry-run"], fake);
  assert.equal(again.code, 0);
  assert.deepEqual(fake.calls, { put: [], list: [] });
  assert.ok(!again.text.includes(TOKEN));
});

test("refused: a manifest for another base URL, even in a dry run", async () => {
  for (const base of ["https://your-project-ref.supabase.co/storage/v1/object/public/motions/",
    "https://otherstore123.public.blob.vercel-storage.com/motions/", BASE_URL.slice(0, -1)]) {
    const { mpath } = makeManifest(2, { public_base_url: base });
    const fake = fakeStore();
    for (const argv of [[mpath], [mpath, "--apply"], [mpath, "check"]]) {
      const r = await go(argv, fake);
      assert.equal(r.code, 2, `${base} ${argv}`);
      assert.match(r.text, /refused: the manifest links/);
    }
    assert.deepEqual(fake.calls, { put: [], list: [] });
  }
  const r = await go([join(mkdtempSync(join(tmpdir(), "none-")), "manifest.json")], null);
  assert.equal(r.code, 2);
  assert.match(r.text, /no manifest at/);
});

test("refused: a file whose size or sha256 differs from the manifest", async () => {
  const { mpath, manifest } = makeManifest();
  const fake = fakeStore();
  writeFileSync(manifest.files[1].path, "%PDF changed");  // another size
  let r = await go([mpath, "--apply"], fake);
  assert.equal(r.code, 2);
  assert.match(r.text, /2021-000001CUA: \d+ bytes on disk, \d+ in the manifest \(changed since the build\)/);
  const { mpath: m2, manifest: man2 } = makeManifest();
  const same = readFileSync(man2.files[2].path, "utf8");
  writeFileSync(man2.files[2].path, same.slice(0, -1) + "B");  // same size, other bytes (it ended in "A")
  r = await go([m2], fake);
  assert.equal(r.code, 2);
  assert.match(r.text, /2021-000002CUA: sha256 differs from the manifest/);
  assert.deepEqual(fake.calls, { put: [], list: [] });
});

test("refused: a file over the manifest's upload limit", async () => {
  const { mpath } = makeManifest(3, { upload_limit_bytes: 30 });
  const fake = fakeStore();
  for (const argv of [[mpath], [mpath, "--apply"]]) {
    const r = await go(argv, fake);
    assert.equal(r.code, 2);
    assert.match(r.text, /2021-000002CUA: \d+ bytes, over the per-file upload limit of 30/);
    assert.ok(!/2021-000000CUA: .*over/.test(r.text));
  }
  assert.deepEqual(fake.calls, { put: [], list: [] });
});

test("refused: check and --apply without a token", async () => {
  const { mpath } = makeManifest();
  const fake = fakeStore();
  for (const env of [{}, { BLOB_READ_WRITE_TOKEN: "" }]) {
    for (const argv of [[mpath, "check"], [mpath, "--apply"]]) {
      const r = await go(argv, fake, env);
      assert.equal(r.code, 2);
      assert.match(r.text, /BLOB_READ_WRITE_TOKEN is not set/);
    }
  }
  assert.deepEqual(fake.calls, { put: [], list: [] });
  assert.equal((await go([mpath, "check", "--apply"], fake)).code, 2);
  assert.equal((await go([mpath, "--bogus"], fake)).code, 2);
});

test("--apply uploads missing and different-size files with the exact put options and skips same-size ones", async () => {
  const { mpath, manifest } = makeManifest(4);
  const [a, b, c, d] = manifest.files;
  const fake = fakeStore({ [`motions/${a.name}`]: a.bytes, [`motions/${b.name}`]: b.bytes + 7, "motions/other.pdf": 100 });
  const r = await go([mpath, "--apply"], fake);
  assert.equal(r.code, 0, r.text);
  assert.deepEqual(fake.calls.list, [{ prefix: "motions/", limit: 1000 }]);
  assert.deepEqual(fake.calls.put.map(p => p.pathname).sort(), [b, c, d].map(f => `motions/${f.name}`).sort());
  for (const p of fake.calls.put) {
    assert.deepEqual(p.options, { access: "public", addRandomSuffix: false, allowOverwrite: true,
      contentType: "application/pdf", cacheControlMaxAge: 31536000 });
    assert.equal(p.bytes, manifest.files.find(f => `motions/${f.name}` === p.pathname).bytes);
    assert.ok(!("token" in p.options));
  }
  assert.match(r.text, /summary: 3 uploaded, 1 skipped \(same size\), 0 failed, 0\.0 MB uploaded/);
  assert.ok(!r.text.includes(TOKEN));
  // a second run: everything is there with the same size, nothing is sent
  fake.calls.put.length = 0;
  const again = await go([mpath, "--apply"], fake);
  assert.equal(again.code, 0);
  assert.equal(fake.calls.put.length, 0);
  assert.match(again.text, /summary: 0 uploaded, 4 skipped/);
});

test("--apply keeps at most 4 uploads in flight and follows the list's pages", async () => {
  const { mpath, manifest } = makeManifest(9);
  const stored = Object.fromEntries(manifest.files.slice(0, 3).map(f => [`motions/${f.name}`, f.bytes]));
  const fake = fakeStore(stored, { pageSize: 2 });
  const r = await go([mpath, "--apply"], fake);
  assert.equal(r.code, 0, r.text);
  assert.equal(fake.calls.list.length, 2);  // 3 blobs, pages of 2
  assert.equal(fake.calls.list[1].cursor, "2");
  assert.equal(fake.calls.put.length, 6);
  assert.ok(fake.maxInFlight <= 4 && fake.maxInFlight > 1, String(fake.maxInFlight));
  assert.deepEqual(fake.calls.put.map(p => p.pathname).sort(), manifest.files.slice(3).map(f => `motions/${f.name}`));
});

test("check reports present, missing, different size and stored bytes, and exits 1 unless all are present", async () => {
  const { mpath, manifest } = makeManifest(3);
  const [a, b] = manifest.files;
  const fake = fakeStore({ [`motions/${a.name}`]: a.bytes, [`motions/${b.name}`]: 5 });
  let r = await go([mpath, "check"], fake);
  assert.equal(r.code, 1);
  assert.equal(fake.calls.put.length, 0);
  assert.match(r.text, /2 files under motions\/, 0\.0 MB stored/);
  assert.match(r.text, /1 present with the same size, 1 missing, 1 of a different size/);
  assert.match(r.text, /missing {3}motions\/2021-000002CUA\.pdf/);
  assert.match(r.text, new RegExp(`different motions/2021-000001CUA\\.pdf  stored 5 bytes, manifest ${b.bytes}`));
  const full = fakeStore(Object.fromEntries(manifest.files.map(f => [`motions/${f.name}`, f.bytes])));
  r = await go(["check", mpath], full);
  assert.equal(r.code, 0);
  assert.match(r.text, /3 present with the same size, 0 missing, 0 of a different size/);
});

test("a token for another store is refused before anything is uploaded", async () => {
  const { mpath } = makeManifest(2);
  const other = p => `https://otherstore999.public.blob.vercel-storage.com/${p}`;
  const fake = fakeStore({ "motions/x.pdf": 3 }, { url: other });
  const r = await go([mpath, "--apply"], fake);
  assert.equal(r.code, 2);
  assert.match(r.text, /the token's store is not/);
  assert.equal(fake.calls.put.length, 0);
  // an empty store of another account: the first answer stops the run
  const empty = fakeStore({}, { url: other });
  const r2 = await go([mpath, "--apply"], empty);
  assert.equal(r2.code, 1);
  assert.match(r2.text, /wrong store, stopped/);
  assert.ok(empty.calls.put.length <= 2);
});

test("--only and --skip upload a subset; an unknown record is refused", async () => {
  const { mpath, manifest } = makeManifest(4);
  const names = manifest.files.map(f => f.record);
  let fake = fakeStore();
  let r = await go([mpath, "--apply", "--only", `${names[1]},${names[3]}`], fake);
  assert.equal(r.code, 0, r.text);
  assert.deepEqual(fake.calls.put.map(p => p.pathname).sort(), [names[1], names[3]].map(n => `motions/${n}.pdf`));
  fake = fakeStore();
  r = await go([mpath, "--apply", `--skip=${names[0]}`], fake);
  assert.deepEqual(fake.calls.put.map(p => p.pathname).sort(), names.slice(1).map(n => `motions/${n}.pdf`));
  fake = fakeStore();
  r = await go([mpath, "--only", names[2]], fake);
  assert.equal(r.code, 0);
  assert.match(r.text, /1 files \(of 4 in the manifest\)/);
  assert.ok(r.text.includes(`would upload motions/${names[2]}.pdf`) && !r.text.includes(`motions/${names[0]}.pdf`));
  r = await go([mpath, "--apply", "--only", "2099-999999CUA"], fake);
  assert.equal(r.code, 2);
  assert.match(r.text, /not in the manifest: 2099-999999CUA/);
  assert.equal(fake.calls.put.length, 0);
  assert.equal((await go([mpath, "--only"], fake)).code, 2);
});

test("a failed upload is retried at most twice; a third failure counts as failed and exits non-zero", async () => {
  const { mpath, manifest } = makeManifest(3);
  const [a, b, c] = manifest.files.map(f => `motions/${f.name}`);
  const fake = fakeStore({}, { failures: { [a]: 2, [b]: 3 } });
  const r = await go([mpath, "--apply"], fake);
  assert.equal(r.code, 1);
  const tries = p => fake.calls.put.filter(x => x.pathname === p).length;
  assert.deepEqual([tries(a), tries(b), tries(c)], [3, 3, 1]);
  assert.ok(fake.store.has(a) && !fake.store.has(b) && fake.store.has(c));
  assert.match(r.text, /summary: 2 uploaded, 0 skipped \(same size\), 1 failed/);
  assert.match(r.text, new RegExp(`FAILED ${b.replace(".", "\\.")}`));
  assert.match(r.text, /\(try 3\)/);
});

test("the token never shows: errors are masked", async () => {
  assert.equal(mask(`bad ${TOKEN} here`), "bad vercel_blob_rw_*** here");
  assert.equal(mask("token abcdefghijk", { BLOB_READ_WRITE_TOKEN: "abcdefghijk" }), "token ***");
  const { mpath } = makeManifest(2);
  const fake = fakeStore({}, { failures: { "motions/2021-000000CUA.pdf": 9 } });
  const r = await go([mpath, "--apply"], fake);
  assert.equal(r.code, 1);
  assert.ok(r.text.includes("vercel_blob_rw_***"));
  assert.ok(!r.text.includes(TOKEN) && !r.text.includes("madeUpSecret"));
  const listFails = { put: fake.put, list: async () => { throw new Error(`list failed for ${TOKEN}`); } };
  const r2 = await go([mpath, "check"], listFails);
  assert.equal(r2.code, 1);
  assert.ok(!r2.text.includes(TOKEN) && r2.text.includes("vercel_blob_rw_***"));
});
