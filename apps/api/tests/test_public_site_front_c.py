"""SF Conditions Search with the C front end (apps/showcase, "the living grid"): build_public_conditions_site.py
--front c runs the Vite site build against the public data and checks every file of the output before writing it
(check_site). No network; the motion PDFs are not made (stage_pdfs is replaced). The tests that run the Vite build
need pnpm and the repository's node_modules, and skip without them."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from urllib.parse import quote

import pytest

REPO = Path(__file__).resolve().parents[3]
VALIDATION = REPO / "scripts" / "validation"
BASE = "https://example.public.blob.vercel-storage.com/motions/"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, VALIDATION / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


B = load("build_public_conditions_site")
P = sys.modules["private_contacts"]

QUEUE = (
    "<script>\n  window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };\n"
    '  window.va("beforeSend", event => ({ ...event, url: String(event.url).split("#")[0] }));\n</script>\n'
)


def can_build_c() -> bool:
    return bool(shutil.which("pnpm")) and (REPO / "apps" / "showcase" / "node_modules" / "vite").exists()


needs_vite = pytest.mark.skipif(
    not can_build_c(), reason="needs pnpm and `pnpm install` (the Vite site build)"
)


@pytest.fixture(autouse=True)
def contact(monkeypatch: pytest.MonkeyPatch) -> None:
    """The contact address the site is built with (CONTACT_EMAIL when the site is built; empty by default)."""
    monkeypatch.setattr(B, "CONTACT", "feedback@example.org")


@pytest.fixture
def fake_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """stage_pdfs without ghostscript: a small fake copy per record."""

    def stage(data: dict, sources: dict[str, str]) -> dict[str, dict]:
        cache = tmp_path / "cache"
        cache.mkdir(exist_ok=True)
        metas = {}
        for record in sorted({c["record"] for c in data["conditions"] if c.get("pdf")}):
            path = cache / f"{record}.pdf"
            path.write_bytes(b"%PDF-1.5 " + record.encode())
            metas[record] = {"version": B.PDF_CACHE_VERSION, "source_bytes": 1000, "setting": "ebook",
                             "bytes": path.stat().st_size, "rejected": {}, "path": path}  # fmt: skip
        return metas

    monkeypatch.setattr(B, "stage_pdfs", stage)


# ---- the guards, on a small made-up site ----------------------------------------------------------------------------


def page(title: str) -> str:
    return f"<!doctype html><html><head><title>{title}</title>\n{QUEUE}{B.ANALYTICS_SCRIPT}\n</head><body></body></html>"


def small_site() -> tuple[dict[str, bytes], dict]:
    data = {"conditions": [{"record": "2021-000001CUA", "number": "1", "text": "Hours: 9 am to 10 pm.", "page": 4,
                            "pdf": BASE + "2021-000001CUA.pdf"}]}  # fmt: skip
    text = B.data_text(data)
    files = {
        "index.html": page("SF Conditions Search").encode(),
        "coverage.html": page("Coverage · SF Conditions Search").encode(),
        "vercel.json": B.vercel_json().encode(),
        "assets/index-AbCd1234.js": b'export const x = "Wrong or missing? Tell me";',
        "assets/index-AbCd1234.css": b"body{color:red}",
        "assets/public-sans-latin-wght-normal-DdeTHZLK.woff2": b"wOF2",
        B.fingerprinted_name("data/conditions.json", text): text.encode(),
        B.fingerprinted_name("coverage.md", "# Coverage\n"): b"# Coverage\n",
    }
    for stem, ext in (("motions", "json"), ("sf-streets", "bin")):
        body = b'{"points":[]}' if ext == "json" else b"SFG1"
        files[f"assets/{stem}.{hashlib.sha256(body).hexdigest()[:12]}.{ext}"] = body
    return files, data


def problems(files: dict[str, bytes], data: dict, withheld: list[str] | None = None) -> list[str]:
    return B.check_site(files, data, BASE, "c", withheld or [])


def test_a_good_small_site_passes() -> None:
    files, data = small_site()
    assert problems(files, data) == []


@pytest.mark.parametrize(
    ("change", "why"),
    [
        (lambda f: f.update({"assets/index-AbCd1234.js.map": b"{}"}), "source map"),
        (lambda f: f.update({"pdf/x.pdf": b"%PDF"}), "not a file the site is made of"),
        (lambda f: f.update({"README.md": b"# notes"}), "not a file the site is made of"),
        (
            lambda f: f.update({"assets/index-AbCd1234.js": b'fetch("http://localhost:55433")'}),
            "internal names",
        ),
        (lambda f: f.update({"assets/three-AbCd1234.js": b"// Permit Memo"}), "internal names"),
        (lambda f: f.update({"assets/index-AbCd1234.js": b'{"raw_text":"x"}'}), "raw_text"),
        (lambda f: f.update({"assets/index-AbCd1234.js": b'a.href=u+"#page=1"'}), "page 1"),
        (lambda f: f.update({"assets/index-AbCd1234.js": b'"call (415) 555-0100"'}), "phone number"),
        (lambda f: f.update({"assets/index-AbCd1234.js": b'"alex@example.com"'}), "e-mail address"),
        (lambda f: f.update({"index.html": page("x").replace(B.ANALYTICS_SCRIPT, "").encode()}), "analytics"),
        (lambda f: f.update({"coverage.html": (page("x") + B.ANALYTICS_SCRIPT).encode()}), "analytics"),
        (lambda f: f.update({"assets/motions.000000000000.json": b"{}"}), "not its content"),
    ],
)
def test_the_guards_stop_the_build(change, why: str) -> None:  # type: ignore[no-untyped-def]
    files, data = small_site()
    change(files)
    found = problems(files, data)
    assert any(why in p for p in found), found


def test_the_guards_ask_for_every_data_file() -> None:
    files, data = small_site()
    for rel in [r for r in files if r.startswith("assets/sf-streets.")]:
        del files[rel]
    assert any("no assets/sf-streets" in p for p in problems(files, data))


def test_city_numbers_and_the_contact_address_pass() -> None:
    files, data = small_site()
    files["assets/index-AbCd1234.js"] = f'"(415) 558-6378 {B.CONTACT} planning@sfgov.org"'.encode()
    assert problems(files, data) == []


def test_a_withheld_contact_is_found_in_any_file_in_any_case() -> None:
    files, data = small_site()
    files["assets/gate-AbCd1234.js"] = b'"the liaison is ALEX EXAMPLE"'
    found = problems(files, data, ["Alex Example"])
    assert any("withheld private contact" in p for p in found)
    # the message does not repeat the contact
    assert not any("Alex" in p or "ALEX" in p for p in found)


def test_a_condition_the_withholding_would_still_change_stops_the_build() -> None:
    files, data = small_site()
    data["conditions"][0]["text"] = "Community Liaison: the liaison will be Alex Example, at (415) 555-0100."
    assert any("private contact in the published text" in p for p in problems(files, data))


def test_a_condition_with_no_page_needs_where_its_conditions_begin() -> None:
    """A condition with no page would open its motion at page 1 (the sponsor's name and address): the C build stops
    unless src/core/search/section-pages.json says where that motion's conditions begin."""
    files, data = small_site()
    data["conditions"][0]["page"] = None
    assert any("would open page 1" in p for p in problems(files, data))
    data["conditions"][0]["record"] = "2011.0186C"
    data["conditions"][0]["pdf"] = BASE + "2011.0186C.pdf"
    assert not any("page 1" in p for p in problems(files, data))
    # (the classic front end is the live page as it was, byte for byte: it is not held to this)
    data["conditions"][0]["record"] = "2021-000001CUA"
    assert not any("would open page 1" in p for p in B.check_site(files, data, BASE, "classic", []))


def can_check_links() -> bool:
    """node, Playwright and its Chromium: what the C build's browser check (check_links) needs."""
    node = shutil.which("node")
    if not node or not (REPO / "apps" / "showcase" / "node_modules" / "@playwright" / "test").exists():
        return False
    res = subprocess.run([node, "-e", "import('@playwright/test').then(m => console.log(m.chromium.executablePath()))"],
                         cwd=REPO / "apps" / "showcase", capture_output=True, text=True, check=False)  # fmt: skip
    return res.returncode == 0 and Path(res.stdout.strip()).exists()


needs_browser = pytest.mark.skipif(
    not can_check_links(), reason="needs node, `pnpm install` and Playwright's Chromium"
)
PAGELESS = "#q=2011.0186C&kind=all"


def card_site(mail_pdf: str, button_pdf: str | None = None) -> tuple[dict[str, bytes], dict]:
    """The small site with a front page that shows one card of 2011.0186C (read with no page): its motion link at
    `button_pdf` and its feedback e-mail naming `mail_pdf`, encoded as the page writes it."""
    files, data = small_site()
    data["conditions"][0].update({"record": "2011.0186C", "pdf": BASE + "2011.0186C.pdf", "page": None})
    body = quote(
        f"About this condition:\r\nMotion page: {mail_pdf}\r\n\r\nWhat is wrong or missing:\r\n", safe=""
    )
    card = (
        '<div class="cs" data-cs-state="ready"><article data-cs-card>'
        f'<a class="cs-pdf" href="{button_pdf or BASE + "2011.0186C.pdf#page=11"}">open the motion</a>'
        f'<a class="feedback" href="mailto:{B.CONTACT}?subject=Wrong&amp;body={body}">Wrong or missing? Tell me</a>'
        "</article></div>"
    )
    files["index.html"] = files["index.html"].replace(b"<body></body>", f"<body>{card}</body>".encode())
    return files, data


@needs_browser
def test_the_browser_check_reads_the_feedback_mail_of_every_card() -> None:
    """A card's feedback e-mail is written as the page runs: the C build opens the site in a browser and stops on a
    motion link in it (or on the card) with no page, or at page 1, which prints the sponsor's name and address."""
    files, _ = card_site(BASE + "2011.0186C.pdf")
    found = B.check_links(files, [PAGELESS])
    assert len(found) == 1 and "a feedback e-mail" in found[0] and "2011.0186C.pdf" in found[0]
    files, _ = card_site(BASE + "2011.0186C.pdf#page=1")
    assert any("a feedback e-mail" in p for p in B.check_links(files, [PAGELESS]))
    files, _ = card_site(BASE + "2011.0186C.pdf#page=11", button_pdf=BASE + "2011.0186C.pdf")
    assert [p for p in B.check_links(files, [PAGELESS]) if "a link" in p]
    files, _ = card_site(BASE + "2011.0186C.pdf#page=11")
    assert B.check_links(files, [PAGELESS]) == []


@needs_browser
def test_the_c_build_reads_its_links_in_a_browser() -> None:
    """check_site with `browse` (as build() runs it for the C front end) opens every motion read with no page."""
    files, data = card_site(BASE + "2011.0186C.pdf")
    assert any("a feedback e-mail" in p for p in B.check_site(files, data, BASE, "c", [], browse=True))
    assert not any("feedback e-mail" in p for p in B.check_site(files, data, BASE, "c", []))
    files, data = card_site(BASE + "2011.0186C.pdf#page=11")
    assert not any(
        "browser" in p or "e-mail" in p or ".pdf" in p
        for p in B.check_site(files, data, BASE, "c", [], browse=True)
    )


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_a_browser_check_that_cannot_run_stops_the_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The check is never skipped: one that cannot run is a problem, and the site is not written."""
    monkeypatch.setattr(B, "CHECK_LINKS", tmp_path / "missing.mjs")
    files, _ = card_site(BASE + "2011.0186C.pdf#page=11")
    found = B.check_links(files, [PAGELESS])
    assert len(found) == 1 and "could not be checked in a browser" in found[0]


def test_a_condition_linked_to_page_1_stops_the_build() -> None:
    files, data = small_site()
    data["conditions"][0]["page"] = 1
    assert any("linked to page 1" in p for p in problems(files, data))


def test_private_contact_strings_are_what_the_withholding_takes_out() -> None:
    text = (
        "Community Liaison: The community liaison officer will be Alex Example, who can be contacted at "
        "(415) 555-0100, or via email at alex@example.com, or at the business address of 1 Main St, San Francisco, "
        "CA 94110. For information about compliance, contact Code Enforcement, Planning Department at 415-575-6863."
    )
    found = P.private_contact_strings(text)
    assert set(found) == {
        "Alex Example",
        "(415) 555-0100",
        "alex@example.com",
        "1 Main St, San Francisco, CA 94110",
    }
    out = P.withhold_private_contacts(text)
    assert not any(s in out for s in found)
    assert P.private_contact_strings(out) == []
    assert (
        P.private_contact_strings("Hours: 9 am to 10 pm. Call (415) 555-0100.") == []
    )  # no liaison: left alone


def test_the_withheld_strings_include_the_four_liaisons_when_git_has_the_history() -> None:
    found, note = B.withheld_strings(json.loads((B.SRC / "data" / "conditions.json").read_text()))
    if "before the withholding" not in note or "not read" in note:
        pytest.skip(f"no git history of the data here: {note}")
    assert len(found) >= 8  # names, numbers, an e-mail and an address of four liaisons
    data = (B.SRC / "data" / "conditions.json").read_text().lower()
    assert not [s for s in found if s.lower() in data]


def test_the_command_defaults_to_the_c_front_end() -> None:
    assert B.DEFAULT_FRONT == "c" and B.FRONTS == ("c", "classic")
    out = subprocess.run([sys.executable, str(VALIDATION / "build_public_conditions_site.py"), "--help"],
                         capture_output=True, text=True, check=True).stdout  # fmt: skip
    assert "--front {c,classic}" in out
    with pytest.raises(SystemExit, match="--front"):
        B.build(Path("/nonexistent/site"), BASE, None, "b")


# ---- the C build itself --------------------------------------------------------------------------------------------


@needs_vite
def test_the_c_build(tmp_path: Path, fake_stage: None) -> None:
    out, classic = tmp_path / "site", tmp_path / "classic"
    counts = B.build(out, BASE, tmp_path / "pdfs" / "manifest.json", "c")
    B.build(classic, BASE, tmp_path / "pdfs-classic" / "manifest.json", "classic")
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert counts["files"] == len(files)
    assert [f for f in files if "/" not in f] == ["coverage.html", "index.html", "vercel.json"]
    assert all(B.C_ASSET.fullmatch(f) for f in files if f.startswith("assets/"))
    assert not [f for f in files if f.endswith(".map")]

    # the same data, coverage text and headers as the classic front end, byte for byte, under the same names
    same = [
        "vercel.json",
        counts["data_file"],
        *(p.relative_to(classic).as_posix() for p in (classic / "assets").glob("coverage.*.md")),
    ]
    assert len(same) == 3
    for name in same:
        assert (out / name).read_bytes() == (classic / name).read_bytes(), name
    assert counts["data_sha256"] == hashlib.sha256((out / counts["data_file"]).read_bytes()).hexdigest()

    index, coverage = (out / "index.html").read_text(), (out / "coverage.html").read_text()
    assert "<title>SF Conditions Search</title>" in index
    assert "<title>Coverage · SF Conditions Search</title>" in coverage
    assert '<meta name="description" content="Search the conditions of approval' in index
    for html in (index, coverage):
        assert html.count(B.ANALYTICS_SCRIPT) == 1 and html.count(B.ANALYTICS_QUEUE) == 1
        assert 'name="robots"' not in html and "Prototype" not in html
        # every file the page loads is the site's own, by its content name (plain <a> links, such as the noscript
        # text's source code and licence, load nothing)
        loaded = re.findall(r'<(?:script|link|img)\b[^>]*?\b(?:src|href)="([^"#]+)"', html)
        assert loaded and all(
            u.startswith("/assets/") or u == "/_vercel/insights/script.js" for u in loaded
        ), loaded
        # the notices of every package in it, named in the head
        (license_name,) = re.findall(
            r'<link rel="license" href="/(assets/third-party-licenses\.[0-9a-f]{12}\.md)">', html
        )
        assert "## three " in (out / license_name).read_text()
        # without scripts the page still says who to write to
        assert f'<a href="mailto:{B.CONTACT}">' in html.split("<noscript>")[1].split("</noscript>")[0]

    bundles = "\n".join(p.read_text() for p in (out / "assets").glob("*.js"))
    # the contact address reaches the page (the contact line, every card's feedback link), the wordmark stays
    assert B.CONTACT in bundles and "Questions or corrections: " in bundles and "Working Title" in bundles
    # the story ships only the facts it shows: none of story.json's notes on how the facts were checked
    story = json.loads((REPO / "apps" / "showcase" / "src" / "data" / "story.json").read_text())
    for note in (*story["open_questions"], *story["pdf"]["notes"]):
        assert note[:60] not in bundles
    assert "suggested_page_to_show" in bundles  # (the subset itself is there)
    # the map's motions: the points only
    (motions,) = (out / "assets").glob("motions.*.json")
    assert list(json.loads(motions.read_text())) == ["points"]
    # the story's own motion links point at the store this build was given
    assert BASE in bundles


@needs_vite
def test_the_c_build_without_a_contact_address(
    tmp_path: Path, fake_stage: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A copy of the site built with no contact address (CONTACT empty, as the builder has it when CONTACT_EMAIL is
    not set) builds: no contact line, no card link, no mailto anywhere."""
    monkeypatch.setattr(B, "CONTACT", "")
    out = tmp_path / "site"
    B.build(out, BASE, tmp_path / "pdfs" / "manifest.json", "c")
    texts = "\n".join(p.read_text() for p in out.rglob("*") if p.suffix in (".html", ".js"))
    assert "mailto:" not in (out / "index.html").read_text()
    # (the minifier writes the empty string as `` or "")
    assert re.search(r'"?contact"?:\s*(""|``)', texts)


@needs_vite
def test_the_c_build_stops_on_a_forbidden_name_in_a_bundle(
    tmp_path: Path, fake_stage: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard reads Vite's bundles too: a name that is only in a script stops the build, and nothing is written."""
    monkeypatch.setattr(B, "FORBIDDEN", re.compile(r"Working Title"))
    out = tmp_path / "site"
    with pytest.raises(SystemExit, match=r"assets/.*\.js: internal names"):
        B.build(out, BASE, tmp_path / "pdfs" / "manifest.json", "c")
    assert not out.exists()
