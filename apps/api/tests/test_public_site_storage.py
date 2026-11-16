"""SF Conditions Search with its motion PDFs in a public Vercel Blob store: build_public_conditions_site.py links the
store and writes the upload manifest (no PDF in the site); tools/conditions-search/upload-pdfs.mjs uploads from that
manifest (its own tests: tools/conditions-search/tests/upload-pdfs.test.mjs). No network, and the PDF copies are not
made (stage_pdfs is replaced)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]
VALIDATION = REPO / "scripts" / "validation"
STORE = "https://example.public.blob.vercel-storage.com"
BASE = f"{STORE}/motions/"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, VALIDATION / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


B = load("build_public_conditions_site")


# ---- the builder -------------------------------------------------------------------------------------------------


def site_data(out: Path) -> dict:
    """The built site's data file, named by its content (assets/conditions.<hash>.json)."""
    (path,) = (out / B.ASSETS).glob("conditions.*.json")
    return json.loads(path.read_text())


@pytest.fixture
def fake_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """stage_pdfs without ghostscript: a small fake copy per record, in tmp_path/cache. Returns {record: bytes}."""
    sizes: dict[str, int] = {}

    def stage(data: dict, sources: dict[str, str]) -> dict[str, dict]:
        assert all(
            sources[c["record"]] == f"pdf/{c['record']}.pdf" for c in data["conditions"]
        )  # the local copies
        cache = tmp_path / "cache"
        cache.mkdir(exist_ok=True)
        metas = {}
        for record in sorted({c["record"] for c in data["conditions"] if c.get("pdf")}):
            path = cache / f"{record}.pdf"
            path.write_bytes(b"%PDF-1.5 " + record.encode())
            sizes[record] = path.stat().st_size
            metas[record] = {"version": B.PDF_CACHE_VERSION, "source_bytes": 1000, "setting": "ebook",
                             "bytes": sizes[record], "rejected": {}, "path": path}  # fmt: skip
        return metas

    monkeypatch.setattr(B, "stage_pdfs", stage)
    return sizes


def test_stage_pdfs_reads_the_local_pdfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The public data links the store, so the copies are made from the local paths (`sources`), not from c["pdf"]."""
    monkeypatch.setattr(B, "SRC", tmp_path)
    (tmp_path / "pdf").mkdir()
    (tmp_path / "pdf" / "2021-000001CUA.pdf").write_bytes(b"%PDF original")
    seen = []

    def compress(record: str, original: Path, conditions: list[dict], decided: str | None = None):  # type: ignore[no-untyped-def]
        seen.append((record, original, decided))
        return original, {"bytes": 13}

    monkeypatch.setattr(B, "compress_pdf", compress)
    data = {
        "conditions": [
            {"record": "2021-000001CUA", "pdf": BASE + "2021-000001CUA.pdf", "decided": "2021-05-06"}
        ]
    }
    metas = B.stage_pdfs(data, {"2021-000001CUA": "pdf/2021-000001CUA.pdf"})
    assert seen == [("2021-000001CUA", (tmp_path / "pdf" / "2021-000001CUA.pdf").resolve(), "2021-05-06")]
    assert metas["2021-000001CUA"]["path"] == (tmp_path / "pdf" / "2021-000001CUA.pdf").resolve()


def test_defaults_point_at_the_blob_store() -> None:
    assert B.PDF_BASE_URL == BASE
    assert B.pdf_url(BASE, "2011.0097CUA-02") == BASE + "2011.0097CUA-02.pdf"
    assert B.UPLOAD_LIMIT_BYTES == 50 * 1024 * 1024
    # the upload script refuses any other base URL, so it must agree with the builder's
    upload = (REPO / "tools" / "conditions-search" / "upload-pdfs.mjs").read_text()
    assert f'"{BASE}"' in upload  # its default when PDF_BASE_URL is not set


def test_bucket_of_reads_the_folder_of_a_blob_base_url() -> None:
    assert B.bucket_of(B.PDF_BASE_URL) == "motions"
    assert B.bucket_of("https://abc123.public.blob.vercel-storage.com/other/") == "other"
    for other in (
        "https://example.org/pdfs/",
        "https://your-project-ref.supabase.co/storage/v1/object/public/motions/",
        f"{STORE}/motions",  # no closing slash
        f"{STORE}/motions/older/",  # a nested folder
        "http://example.public.blob.vercel-storage.com/motions/",
        "https://example.blob.vercel-storage.com/motions/",  # not the public host
        "https://evil.example.org/x.public.blob.vercel-storage.com/motions/",
    ):
        assert B.bucket_of(other) is None, other


def test_guard_allows_the_blob_url_but_not_the_product_name() -> None:
    assert not B.FORBIDDEN.search(B.pdf_url(BASE, "2018-010482CUA"))
    assert not B.FORBIDDEN.search(BASE)
    for bad in (
        "Permit Memo",
        "permit memo",
        "permit-memo",
        "permit_memo",
        "https://permit-memo.public.blob.vercel-storage.com/motions/x.pdf",
    ):
        assert B.FORBIDDEN.search(bad), bad


def test_build_links_the_blob_store_and_keeps_pdfs_out_of_the_site(tmp_path: Path, fake_stage: dict) -> None:
    out = tmp_path / "site"
    (out / "pdf").mkdir(parents=True)
    (out / "pdf" / "old.pdf").write_bytes(b"%PDF old")  # a site built before: its pdf/ folder goes
    counts = B.build(out)

    assert not (out / "pdf").exists()
    assert sorted(p.name for p in out.iterdir()) == ["assets", "coverage.html", "index.html", "vercel.json"]
    assert sorted(p.name.split(".")[0] for p in (out / B.ASSETS).iterdir()) == [
        "conditions",
        "coverage",
        "coverage",
        "search",
    ]
    assert not [p for p in out.rglob("*") if p.suffix == ".pdf"]
    assert counts["files"] == 7  # with the data file

    data = site_data(out)
    source = json.loads((B.SRC / "data" / "conditions.json").read_text())
    assert len(data["conditions"]) == len(source["conditions"])
    for c, s in zip(data["conditions"], source["conditions"], strict=True):
        assert c["pdf"] == BASE + c["record"] + ".pdf"
        # nothing else about the condition changes: same text, page and page_exact, so the same #page link
        assert {k: v for k, v in c.items() if k not in ("pdf", "motion_url")} == {
            k: v for k, v in s.items() if k not in ("pdf", "motion_url", *B.DROP_CONDITION_FIELDS)
        }

    index = (out / "index.html").read_text()
    assert "stored with this site's files" in index and "kept on this site" not in index
    assert 'c.page_exact ? " at page " : " near page "' in index  # the page wording is kept
    assert "Planning's copy" in index

    vercel = json.loads((out / "vercel.json").read_text())
    assert [h["source"] for h in vercel["headers"]] == [
        *B.PAGES,
        f"/{B.ASSETS}/(.*)",
        "/(.*)",
    ]
    assert "pdf" not in json.dumps(vercel)

    manifest = json.loads((tmp_path / "sf-conditions-search-pdfs" / "manifest.json").read_text())
    assert counts["manifest"] == str((tmp_path / "sf-conditions-search-pdfs" / "manifest.json").resolve())
    assert (manifest["bucket"], manifest["public_base_url"]) == ("motions", BASE)
    assert manifest["upload_limit_bytes"] == B.UPLOAD_LIMIT_BYTES
    assert manifest["count"] == len(fake_stage) == len({c["record"] for c in data["conditions"]})
    assert manifest["total_bytes"] == sum(fake_stage.values())
    first = manifest["files"][0]
    path = Path(first["path"])
    assert first["name"] == first["record"] + ".pdf" and first["public_url"] == BASE + first["name"]
    assert (first["bytes"], first["sha256"]) == (
        path.stat().st_size,
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    linked = {c["pdf"] for c in data["conditions"]}
    assert linked == {f["public_url"] for f in manifest["files"]}


def test_build_with_another_base_url(tmp_path: Path, fake_stage: dict) -> None:
    other = "https://files.example.org/motions/"
    B.build(tmp_path / "site", other, tmp_path / "m" / "manifest.json")
    data = site_data(tmp_path / "site")
    assert all(c["pdf"].startswith(other) for c in data["conditions"])
    manifest = json.loads((tmp_path / "m" / "manifest.json").read_text())
    assert manifest["bucket"] is None and manifest["public_base_url"] == other  # the upload script refuses it


def test_build_refusals(tmp_path: Path, fake_stage: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "site"
    with pytest.raises(SystemExit, match="internal names"):
        B.build(out, "https://permit-memo.example.org/pdf/")
    with pytest.raises(SystemExit, match="https URL"):
        B.build(out, "http://files.example.org/motions/")
    with pytest.raises(SystemExit, match="https URL"):
        B.build(out, "https://files.example.org/motions")
    with pytest.raises(SystemExit, match="outside the site folder"):
        B.build(out, BASE, out / "manifest.json")
    monkeypatch.setattr(B, "UPLOAD_LIMIT_BYTES", 5)
    with pytest.raises(SystemExit, match="upload limit"):
        B.build(out)


def test_the_pages_load_their_scripts_and_data_by_content_name_and_are_revalidated(
    tmp_path: Path, fake_stage: dict
) -> None:
    """A returning visitor must get the latest deploy on a normal reload: the scripts, data and coverage text are
    named by their content (assets/<name>.<sha256[:12]>.<ext>) and the pages that load them are served no-cache."""
    out = tmp_path / "site"
    B.build(out, BASE, tmp_path / "pdfs" / "manifest.json")
    assets = sorted(p.relative_to(out).as_posix() for p in (out / B.ASSETS).iterdir())
    assert [a.split("/")[1].split(".")[0] for a in assets] == ["conditions", "coverage", "coverage", "search"]
    for rel in assets:
        name = rel.split("/")[1]
        digest = name.split(".")[-2]
        assert digest == hashlib.sha256((out / rel).read_bytes()).hexdigest()[:12], rel
    # the plain names are gone from the site and from what the pages load
    for plain in B.FINGERPRINTED:
        assert not (out / plain).exists(), plain
    index, coverage = (out / "index.html").read_text(), (out / "coverage.html").read_text()
    by_stem = {a.split("/")[1].rsplit(".", 2)[0] + "." + a.rsplit(".", 1)[1]: a for a in assets}
    assert f'from "./{by_stem["search.js"]}"' in index and f'from "./{by_stem["coverage.js"]}"' in index
    assert f'fetch("{by_stem["conditions.json"]}")' in index
    assert (
        f'fetch("{by_stem["conditions.json"]}")' in coverage
        and f'fetch("{by_stem["coverage.md"]}")' in coverage
    )
    for page in (index, coverage):
        for plain in B.FINGERPRINTED:
            assert f'"./{plain}"' not in page and f'"{plain}"' not in page, plain
    # headers: pages no-cache, assets immutable for a year
    rules = {
        r["source"]: {h["key"]: h["value"] for h in r["headers"]}
        for r in json.loads((out / "vercel.json").read_text())["headers"]
    }
    for page in ("/", "/index.html", "/coverage.html"):
        assert rules[page]["Cache-Control"] == "no-cache", page
    assert rules[f"/{B.ASSETS}/(.*)"]["Cache-Control"] == "public, max-age=31536000, immutable"
    # a change of content is a change of name
    assert B.fingerprinted_name("search.js", "a") != B.fingerprinted_name("search.js", "b")
    assert B.fingerprinted_name("data/conditions.json", "x").startswith("assets/conditions.")


# ---- analytics and the card feedback link ----------------------------------------------------------------------

ANALYTICS_QUEUE = "window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };"


def test_the_built_pages_keep_vercel_web_analytics_and_the_csp_allows_it(
    tmp_path: Path, fake_stage: dict
) -> None:
    """Both built pages load /_vercel/insights/script.js once, with the window.va queue before it, as the source
    pages do: the content-hashing step does not rename or rewrite it, no file is made for it, and the
    Content-Security-Policy lets the same-origin script, its same-origin requests and the inline queue run."""
    out = tmp_path / "site"
    B.build(out, BASE, tmp_path / "pdfs" / "manifest.json")
    assert B.ANALYTICS_SCRIPT == '<script defer src="/_vercel/insights/script.js"></script>'
    for page in ("index.html", "coverage.html"):
        built, source = (out / page).read_text(), (B.SRC / page).read_text()
        assert built.count(B.ANALYTICS_SCRIPT) == 1, page
        assert built.count(ANALYTICS_QUEUE) == 1, page
        # the head snippet (queue, beforeSend, script tag) is the source's, unchanged
        snippet = source[source.index("<script>\n  window.va") : source.index(B.ANALYTICS_SCRIPT)]
        assert snippet and snippet + B.ANALYTICS_SCRIPT in built, page
        assert built.index(ANALYTICS_QUEUE) < built.index(B.ANALYTICS_SCRIPT) < built.index("</head>"), page
        assert f"{B.ASSETS}/script." not in built, page
    assert not (out / "_vercel").exists()
    assert not [p for p in out.rglob("*") if "insights" in p.name or p.name.startswith("script.")]
    rules = {
        r["source"]: {h["key"]: h["value"] for h in r["headers"]}
        for r in json.loads((out / "vercel.json").read_text())["headers"]
    }
    csp = {d.split()[0]: d.split()[1:] for d in rules["/(.*)"]["Content-Security-Policy"].split("; ")}
    assert "'self'" in csp["script-src"] and "'unsafe-inline'" in csp["script-src"]
    assert csp["connect-src"] == ["'self'"]  # the page views go to the site itself, nowhere else
    assert csp["default-src"] == ["'self'"]
    # the public page says so
    assert (
        "Page views are counted by Vercel Web Analytics, without cookies." in (out / "index.html").read_text()
    )


def test_the_build_stops_when_a_page_lost_the_analytics_script(
    tmp_path: Path, fake_stage: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(B, "ANALYTICS_SCRIPT", '<script defer src="/_vercel/insights/other.js"></script>')
    with pytest.raises(SystemExit, match="analytics script once"):
        B.build(tmp_path / "site", BASE, tmp_path / "pdfs" / "manifest.json")


def test_the_built_cards_email_the_contact_address_written_once_in_the_builder(
    tmp_path: Path, fake_stage: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The "Wrong or missing? Tell me" link on every card emails CONTACT: the build fills the page's FEEDBACK_TO
    with it (the source page leaves it empty), and the address is in no source page or script."""
    monkeypatch.setattr(B, "CONTACT", "feedback@example.org")  # CONTACT_EMAIL when the site is built
    for name in ("index.html", "coverage.html", "search.js", "coverage.js"):
        assert B.CONTACT not in (B.SRC / name).read_text(), name
    assert (B.SRC / "index.html").read_text().count(B.FEEDBACK_TO) == 1
    out = tmp_path / "site"
    B.build(out, BASE, tmp_path / "pdfs" / "manifest.json")
    index = (out / "index.html").read_text()
    assert index.count(f'const FEEDBACK_TO = "{B.CONTACT}";') == 1
    assert B.FEEDBACK_TO not in index
    assert "feedbackLink(c, { to: FEEDBACK_TO, base: location.origin + location.pathname }, esc)" in index
    assert index.count(B.CONTACT) == 3  # the contact line's mailto: href and text, and FEEDBACK_TO
    (search_js,) = (out / B.ASSETS).glob("search.*.js")
    assert "export function feedbackLink" in search_js.read_text()
    assert "Wrong or missing? Tell me" in search_js.read_text()


def test_the_built_search_script_makes_the_mailto_link(
    tmp_path: Path, fake_stage: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The built (comment-stripped, content-named) search script, run by node on a condition of the built data:
    the link goes to CONTACT with the case and condition number, the address and the store's motion page."""
    monkeypatch.setattr(B, "CONTACT", "feedback@example.org")  # CONTACT_EMAIL when the site is built
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = tmp_path / "site"
    B.build(out, BASE, tmp_path / "pdfs" / "manifest.json")
    (search_js,) = (out / B.ASSETS).glob("search.*.js")
    c = site_data(out)["conditions"][0]
    script = (
        f"const m = await import({json.dumps(search_js.as_uri())});"
        f"const c = {json.dumps(c)};"
        f"const href = m.feedbackHref(c, {{ to: {json.dumps(B.CONTACT)}, base: 'https://example.org/' }});"
        "const [to, q] = href.slice('mailto:'.length).split('?');"
        "const h = Object.fromEntries(q.split('&').map(kv => [kv.split('=')[0], decodeURIComponent(kv.split('=')[1])]));"
        "console.log(JSON.stringify({ to, ...h }));"
    )
    res = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True
    )
    mail = json.loads(res.stdout)
    assert mail["to"] == B.CONTACT
    assert mail["subject"] == f"Wrong or missing: {c['record']}, condition {c['number']}"
    lines = mail["body"].split("\r\n")
    assert f"Case number: {c['record']}" in lines and f"Condition number: {c['number']}" in lines
    assert f"Address: {c['address']}" in lines
    page = f"#page={c['page']}" if c.get("page") else ""
    assert f"Motion page: {BASE}{c['record']}.pdf{page}" in lines


def test_without_contact_email_the_built_page_has_no_contact_address_and_no_feedback_link(
    tmp_path: Path, fake_stage: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CONTACT_EMAIL unset: no address under the page and FEEDBACK_TO stays empty, so no card has the link."""
    monkeypatch.setattr(B, "CONTACT", "")
    out = tmp_path / "site"
    B.build(out, BASE, tmp_path / "pdfs" / "manifest.json")
    index = (out / "index.html").read_text()
    assert index.count(B.FEEDBACK_TO) == 1
    assert "mailto:" not in index
    assert "Questions or corrections" not in index
    assert "Page views are counted by Vercel Web Analytics, without cookies." in index
