#!/usr/bin/env node
// Upload the motion PDFs of "SF Conditions Search" to its file storage: a public Vercel Blob store kept apart
// from the app. Set PDF_BASE_URL to the store's https://<store>.public.blob.vercel-storage.com/motions/ (the
// builder reads the same variable); the default is a placeholder.
//
// scripts/validation/build_public_conditions_site.py links every condition to PDF_BASE_URL<record>.pdf#page=N and
// writes a manifest of the copies (record, object name, local file, bytes, sha256, public URL), by default
// $LOCAL_DATA_DIR/sf-conditions-search-pdfs/manifest.json. This script puts each copy in the store at the
// pathname motions/<name>, with the @vercel/blob SDK (the CLI's `vercel blob put` adds a random suffix, which would
// break the links).
//
//   node tools/conditions-search/upload-pdfs.mjs [manifest.json]                dry run: no network, no token
//   node tools/conditions-search/upload-pdfs.mjs [manifest.json] check          what the store holds
//   node tools/conditions-search/upload-pdfs.mjs [manifest.json] --apply        upload missing / changed files
//   ... --only <record,...>   ... --skip <record,...>                           a subset of the records
//
// Before anything, the manifest must point at this store (public_base_url === BASE_URL) and every file must match
// the manifest (bytes and sha256 of the file on disk) and be under its upload_limit_bytes. "check" and "--apply"
// need BLOB_READ_WRITE_TOKEN in the environment (the SDK reads it there); it is never printed, and any
// "vercel_blob_rw_..." string in an error message is masked. Exit 0 when everything went through, 1 when an upload
// failed (or "check" found a file missing or of a different size), 2 when the run was refused.

import { createHash } from "node:crypto";
import { readFile, realpath, stat } from "node:fs/promises";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const BASE_URL = process.env.PDF_BASE_URL || "https://example.public.blob.vercel-storage.com/motions/";
export const PREFIX = "motions/";
export const DEFAULT_MANIFEST = join(process.env.LOCAL_DATA_DIR || join(homedir(), "sfhp-local"), "sf-conditions-search-pdfs", "manifest.json");
export const PUT_OPTIONS = Object.freeze({
  access: "public",
  addRandomSuffix: false,
  allowOverwrite: true,
  contentType: "application/pdf",
  cacheControlMaxAge: 31536000,
});
export const IN_FLIGHT = 4;
export const RETRIES = 2; // a failed upload is tried again at most twice
const USAGE = "usage: node upload-pdfs.mjs [manifest.json] [check | --apply] [--only <record,...>] [--skip <record,...>]";

export class Refused extends Error {}

/** Hide any Blob read-write token (and the token in `env`, whatever its form) in a message. */
export function mask(text, env = {}) {
  let s = String(text).replace(/vercel_blob_rw_[A-Za-z0-9_-]*/g, "vercel_blob_rw_***");
  const token = env.BLOB_READ_WRITE_TOKEN;
  if (token && token.length >= 8) s = s.split(token).join("***");
  return s;
}

export const mb = bytes => (bytes / 1e6).toFixed(1);

export function parseArgs(argv) {
  const opts = { manifest: DEFAULT_MANIFEST, mode: "dry-run", only: null, skip: null };
  let manifestSet = false;
  const records = v => {
    if (!v || v.startsWith("--")) throw new Refused(`a comma-separated list of records is needed. ${USAGE}`);
    return v.split(",").map(s => s.trim()).filter(Boolean);
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "check") opts.mode = opts.mode === "apply" ? "conflict" : "check";
    else if (a === "--apply") opts.mode = opts.mode === "check" ? "conflict" : "apply";
    else if (a === "--dry-run") { if (opts.mode !== "dry-run") opts.mode = "conflict"; }
    else if (a === "--only") opts.only = records(argv[++i]);
    else if (a === "--skip") opts.skip = records(argv[++i]);
    else if (a.startsWith("--only=")) opts.only = records(a.slice(7));
    else if (a.startsWith("--skip=")) opts.skip = records(a.slice(7));
    else if (!a.startsWith("-") && !manifestSet) { opts.manifest = resolve(a); manifestSet = true; }
    else throw new Refused(`unknown argument ${JSON.stringify(a)}. ${USAGE}`);
  }
  if (opts.mode === "conflict") throw new Refused(`choose one of check and --apply. ${USAGE}`);
  return opts;
}

/** Read the manifest and check it, and every file in it, against this store and the files on disk. */
export async function loadManifest(path) {
  let manifest;
  try {
    manifest = JSON.parse(await readFile(path, "utf8"));
  } catch (e) {
    throw new Refused(e.code === "ENOENT" ? `no manifest at ${path}: build the site first` : `cannot read ${path}: ${e.message}`);
  }
  if (manifest.public_base_url !== BASE_URL) {
    throw new Refused(`the manifest links ${JSON.stringify(manifest.public_base_url)}, not this store (${BASE_URL}): build the site with the default --pdf-base-url`);
  }
  const limit = manifest.upload_limit_bytes;
  if (!Number.isInteger(limit) || limit <= 0) throw new Refused("the manifest has no upload_limit_bytes");
  if (!Array.isArray(manifest.files) || manifest.files.length === 0) throw new Refused("the manifest lists no files");
  if (manifest.count !== manifest.files.length) throw new Refused(`the manifest says ${manifest.count} files but lists ${manifest.files.length}`);
  const problems = [];
  const names = new Set();
  for (const f of manifest.files) {
    const label = f.record ?? f.name;
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*\.pdf$/.test(f.name ?? "") || f.name !== `${f.record}.pdf`) {
      problems.push(`${label}: bad object name ${JSON.stringify(f.name)}`);
      continue;
    }
    if (names.has(f.name)) problems.push(`${label}: listed twice`);
    names.add(f.name);
    if (f.public_url !== BASE_URL + f.name) problems.push(`${label}: public_url ${f.public_url} is not ${BASE_URL + f.name}`);
    if (f.bytes > limit) problems.push(`${label}: ${f.bytes} bytes, over the per-file upload limit of ${limit}`);
    let size;
    try {
      size = (await stat(f.path)).size;
    } catch {
      problems.push(`${label}: no file at ${f.path}`);
      continue;
    }
    if (size !== f.bytes) { problems.push(`${label}: ${size} bytes on disk, ${f.bytes} in the manifest (changed since the build)`); continue; }
    if (size > limit) { problems.push(`${label}: ${size} bytes, over the per-file upload limit of ${limit}`); continue; }
    const sha = createHash("sha256").update(await readFile(f.path)).digest("hex");
    if (sha !== f.sha256) problems.push(`${label}: sha256 differs from the manifest (changed since the build)`);
  }
  if (problems.length) throw new Refused(`the manifest does not match the files:\n  ${problems.join("\n  ")}`);
  return manifest;
}

/** The manifest's files, narrowed by --only / --skip (an unknown record is refused: a typo would upload nothing). */
export function selectFiles(files, { only, skip }) {
  const known = new Set(files.map(f => f.record));
  const unknown = [...(only ?? []), ...(skip ?? [])].filter(r => !known.has(r));
  if (unknown.length) throw new Refused(`not in the manifest: ${unknown.join(", ")}`);
  return files.filter(f => (!only || only.includes(f.record)) && !(skip ?? []).includes(f.record));
}

/** Every blob under PREFIX: {pathname: {size, url}}. */
export async function listStore(list) {
  const blobs = new Map();
  let cursor;
  do {
    const page = await list({ prefix: PREFIX, limit: 1000, ...(cursor ? { cursor } : {}) });
    for (const b of page.blobs ?? []) blobs.set(b.pathname, { size: b.size, url: b.url });
    cursor = page.hasMore ? page.cursor : undefined;
  } while (cursor);
  for (const [pathname, b] of blobs) {
    if (b.url && b.url !== BASE_URL.slice(0, -PREFIX.length) + pathname) {
      throw new Refused(`the token's store is not ${BASE_URL} (it lists ${b.url})`);
    }
  }
  return blobs;
}

export function compare(files, blobs) {
  const same = [], missing = [], different = [];
  for (const f of files) {
    const b = blobs.get(PREFIX + f.name);
    if (!b) missing.push(f);
    else if (b.size !== f.bytes) different.push({ ...f, stored: b.size });
    else same.push(f);
  }
  return { same, missing, different };
}

/** Run `work` over `items` in order with at most `n` in flight; stops taking new items once `stop()` is true. */
async function pool(items, n, work, stop = () => false) {
  let next = 0;
  const worker = async () => {
    while (next < items.length && !stop()) await work(items[next++]);
  };
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, worker));
}

/**
 * The script. `deps`: { env, put, list, out, err, sleep, readFile } (put and list as in @vercel/blob; out/err take a
 * line). Returns the exit code.
 */
export async function run(argv, deps) {
  const { env = {}, out = console.log, err = console.error, sleep = ms => new Promise(r => setTimeout(r, ms)) } = deps;
  const say = line => out(mask(line, env));
  const warn = line => err(mask(line, env));
  try {
    const opts = parseArgs(argv);
    const manifest = await loadManifest(opts.manifest);
    const files = selectFiles(manifest.files, opts);
    const total = files.reduce((s, f) => s + f.bytes, 0);
    const subset = files.length === manifest.files.length ? "" : ` (of ${manifest.files.length} in the manifest)`;

    if (opts.mode === "dry-run") {
      say(`dry run: nothing sent. ${files.length} files${subset}, ${mb(total)} MB, manifest ${opts.manifest}`);
      if (files.length) {
        const largest = files.reduce((a, b) => (b.bytes > a.bytes ? b : a));
        say(`largest: ${largest.name} ${mb(largest.bytes)} MB (limit ${mb(manifest.upload_limit_bytes)} MB per file)`);
      }
      for (const f of files) say(`would upload ${PREFIX}${f.name}  ${mb(f.bytes)} MB`);
      say("run with 'check' to compare with the store, or '--apply' to upload what is missing or of another size");
      return 0;
    }

    if (!env.BLOB_READ_WRITE_TOKEN) {
      throw new Refused("BLOB_READ_WRITE_TOKEN is not set: load the store's token into the environment first");
    }
    const blobs = await listStore(deps.list);
    const { same, missing, different } = compare(files, blobs);
    const storedBytes = [...blobs.values()].reduce((s, b) => s + (b.size ?? 0), 0);

    if (opts.mode === "check") {
      say(`store ${BASE_URL}: ${blobs.size} files under ${PREFIX}, ${mb(storedBytes)} MB stored`);
      say(`${files.length} manifest files${subset}: ${same.length} present with the same size, ${missing.length} missing, ${different.length} of a different size`);
      for (const f of missing) say(`missing   ${PREFIX}${f.name}  ${mb(f.bytes)} MB`);
      for (const f of different) say(`different ${PREFIX}${f.name}  stored ${f.stored} bytes, manifest ${f.bytes}`);
      return missing.length || different.length ? 1 : 0;
    }

    // --apply
    const todo = [...missing, ...different];
    const order = new Map(files.map((f, i) => [f.record, i]));
    todo.sort((a, b) => order.get(a.record) - order.get(b.record));
    say(`apply: ${todo.length} to upload (${missing.length} missing, ${different.length} of a different size), ${same.length} already there with the same size`);
    const uploaded = [], failed = [];
    let fatal = null;
    await pool(todo, IN_FLIGHT, async f => {
      const pathname = PREFIX + f.name;
      const body = await (deps.readFile ?? readFile)(f.path);
      for (let attempt = 0; attempt <= RETRIES; attempt++) {
        try {
          const res = await deps.put(pathname, body, { ...PUT_OPTIONS });
          if (res?.url && res.url !== f.public_url) {
            fatal = `the store answered ${res.url} for ${pathname}, not ${f.public_url}: wrong store, stopped`;
            failed.push(f);
            return;
          }
          uploaded.push(f);
          say(`uploaded ${pathname}  ${mb(f.bytes)} MB${attempt ? ` (try ${attempt + 1})` : ""}`);
          return;
        } catch (e) {
          if (attempt < RETRIES && !fatal) {
            warn(`retry ${pathname}: ${e?.message ?? e}`);
            await sleep(1000 * (attempt + 1));
          } else {
            warn(`FAILED ${pathname}: ${e?.message ?? e}`);
            failed.push(f);
            return;
          }
        }
      }
    }, () => fatal !== null);
    if (fatal) warn(fatal);
    const notTried = todo.length - uploaded.length - failed.length;
    const sent = uploaded.reduce((s, f) => s + f.bytes, 0);
    say(`summary: ${uploaded.length} uploaded, ${same.length} skipped (same size), ${failed.length} failed` +
        `${notTried ? `, ${notTried} not tried` : ""}, ${mb(sent)} MB uploaded`);
    return failed.length || notTried || fatal ? 1 : 0;
  } catch (e) {
    if (e instanceof Refused) {
      warn(`refused: ${e.message}`);
      return 2;
    }
    warn(`error: ${e?.message ?? e}`);
    return 1;
  }
}

async function main() {
  const argv = process.argv.slice(2);
  const needsSdk = argv.includes("check") || argv.includes("--apply");
  let put, list;
  if (needsSdk) {
    try {
      ({ put, list } = await import("@vercel/blob"));
    } catch {
      console.error("error: @vercel/blob is not installed: cd tools/conditions-search && npm install --ignore-scripts");
      process.exitCode = 1;
      return;
    }
  }
  process.exitCode = await run(argv, { env: process.env, put, list });
}

const invoked = process.argv[1] && (await realpath(process.argv[1]).catch(() => null));
if (invoked && invoked === (await realpath(fileURLToPath(import.meta.url)))) await main();
