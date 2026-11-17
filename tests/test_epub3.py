"""EPUB 3 as a second output format; EPUB 2 stays the default and stays byte-for-byte the same shape.

Every EPUB written here goes through epubcheck when EPUBCHECK_JAR points at it
(5.4.0 is what the hub asked for), for EPUB 2 and EPUB 3 alike.
"""
from __future__ import annotations

import io
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import chapters as chap  # noqa: E402
import epub_build as core  # noqa: E402
import i18n  # noqa: E402
import main as cli  # noqa: E402
from test_cases import EPUBCHECK, epubcheck_errors  # noqa: E402
from test_merge import app, wait_loaded, wait_worker, write  # noqa: E402,F401  (app is a fixture)

X = "{http://www.w3.org/1999/xhtml}"
EPUB_NS = "{http://www.idpf.org/2007/ops}"
OPF = "{http://www.idpf.org/2007/opf}"
DC = "{http://purl.org/dc/elements/1.1/}"
NCX = "{http://www.daisy.org/z3986/2005/ncx/}"

TITLE3 = '제3장 & <끝> "따옴표"'
BOOK_TEXT = f"머리말입니다.\n\n제1장 시작\n\n첫째 문단.\n둘째 줄.\n\n제2장 이어서\n\n또 다른 문단.\n\n{TITLE3}\n\n마지막.\n"


def make(tmp_path, name: str = "책.txt", text: str = BOOK_TEXT, enc: str = "cp949", **opts):
    p = write(tmp_path, name, text, enc)
    r = core.convert_file(p, core.Options(**opts))
    return r.output_path, r


def check(path: str) -> None:
    assert epubcheck_errors(path) == [], path


def nav_entries(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    doc = ET.fromstring(z.read("OEBPS/nav.xhtml"))
    toc = next(n for n in doc.iter(X + "nav") if n.get(EPUB_NS + "type") == "toc")
    return [(a.get("href"), "".join(a.itertext())) for a in toc.iter(X + "a")]


def ncx_entries(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    root = ET.fromstring(z.read("OEBPS/toc.ncx"))
    return [(np.find(NCX + "content").get("src"), np.find(NCX + "navLabel/" + NCX + "text").text)
            for np in root.iter(NCX + "navPoint")]


def spine_hrefs(opf: ET.Element) -> list[str]:
    items = {i.get("id"): i.get("href") for i in opf.iter(OPF + "item")}
    return [items[r.get("idref")] for r in opf.iter(OPF + "itemref")]


def test_epubcheck_is_configured_for_these_tests():
    if not EPUBCHECK or not os.path.isfile(EPUBCHECK):
        pytest.skip("EPUBCHECK_JAR is not set: the EPUBs below are checked structurally only")


# ---------------------------------------------------------------- EPUB 2 stays as it was

def test_default_output_is_still_epub2(tmp_path):
    out, _ = make(tmp_path)
    check(out)
    z = zipfile.ZipFile(out)
    opf_text = z.read("OEBPS/content.opf").decode("utf-8")
    assert 'version="2.0"' in opf_text and "<guide>" not in opf_text   # no cover, so no guide, as before
    assert "OEBPS/nav.xhtml" not in z.namelist()
    ch = z.read("OEBPS/ch0001.xhtml").decode("utf-8")
    assert "XHTML 1.1" in ch
    assert core.Options().epub_version == "2" and core.Options().validated().epub_version == "2"
    with_cover, _ = make(tmp_path, name="표지.txt", cover_mode="auto")  # the EPUB 2 cover path is untouched too
    check(with_cover)
    z2 = zipfile.ZipFile(with_cover)
    text = z2.read("OEBPS/content.opf").decode("utf-8")
    assert "<guide>" in text and '<meta name="cover" content="cover-image"/>' in text and "properties=" not in text


# ---------------------------------------------------------------- EPUB 3 package

def test_epub3_package_nav_and_documents(tmp_path):
    out, r = make(tmp_path, epub_version="3", author="김소월", publisher="출판사")
    check(out)
    z = zipfile.ZipFile(out)
    first = z.infolist()[0]
    assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
    opf = ET.fromstring(z.read("OEBPS/content.opf"))
    assert opf.get("version") == "3.0"
    items = {i.get("id"): i for i in opf.iter(OPF + "item")}
    assert items["nav"].get("properties") == "nav" and items["nav"].get("href") == "nav.xhtml"
    assert items["ncx"].get("href") == "toc.ncx" and opf.find(OPF + "spine").get("toc") == "ncx"
    entries = nav_entries(z)
    assert [t for _, t in entries] == ["책", "제1장 시작", "제2장 이어서", TITLE3]  # Hangul and & < > " intact
    assert len(entries) == r.nav == 4 and r.chapters == 3
    assert [h for h, _ in entries] == spine_hrefs(opf)   # nav order == reading order
    assert entries == ncx_entries(z)                      # the kept NCX says exactly the same
    ident = opf.find(f"{OPF}metadata/{DC}identifier").text
    assert ident.startswith("urn:uuid:")
    ncx = ET.fromstring(z.read("OEBPS/toc.ncx"))
    uid = next(m.get("content") for m in ncx.iter(NCX + "meta") if m.get("name") == "dtb:uid")
    assert uid == ident                                   # epubcheck NCX-001
    stamp = next(m.text for m in opf.iter(OPF + "meta") if m.get("property") == "dcterms:modified")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamp)
    assert opf.find(f"{OPF}metadata/{DC}creator").text == "김소월"
    assert any(m.get("refines") == "#creator" and m.text == "aut" for m in opf.iter(OPF + "meta"))
    assert opf.find(f"{OPF}metadata/{DC}publisher").text == "출판사"
    assert opf.find(OPF + "guide") is None                # landmarks live in nav.xhtml
    for name in ("OEBPS/ch0001.xhtml", "OEBPS/nav.xhtml"):
        text = z.read(name).decode("utf-8")
        assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'), name
        assert "XHTML 1.1" not in text
        ET.fromstring(text.encode("utf-8"))               # well-formed
    # ch0001 is the front section, so chapter 2 is ch0003
    assert z.read("OEBPS/ch0003.xhtml").decode("utf-8").count("또 다른 문단.") == 1
    assert "<h1>책</h1>" in z.read("OEBPS/ch0001.xhtml").decode("utf-8")


def test_epub3_cover_landmarks_and_cover_image_property(tmp_path):
    out, _ = make(tmp_path, epub_version="3", cover_mode="auto", author="저자")
    check(out)
    z = zipfile.ZipFile(out)
    opf = ET.fromstring(z.read("OEBPS/content.opf"))
    cover = next(i for i in opf.iter(OPF + "item") if i.get("id") == "cover-image")
    assert cover.get("properties") == "cover-image" and cover.get("media-type") == "image/jpeg"
    assert spine_hrefs(opf)[0] == "cover.xhtml"
    nav = ET.fromstring(z.read("OEBPS/nav.xhtml"))
    marks = next(n for n in nav.iter(X + "nav") if n.get(EPUB_NS + "type") == "landmarks")
    kinds = {a.get(EPUB_NS + "type"): a.get("href") for a in marks.iter(X + "a")}
    assert kinds == {"cover": "cover.xhtml", "bodymatter": "ch0001.xhtml"}
    toc_targets = [h for h, _ in nav_entries(z)]
    assert "cover.xhtml" not in toc_targets               # the cover is not a chapter


def test_epub3_without_author_writes_no_empty_creator(tmp_path):
    out, _ = make(tmp_path, epub_version="3")
    check(out)
    assert b"<dc:creator" not in zipfile.ZipFile(out).read("OEBPS/content.opf")


def test_epub3_text_without_chapters_is_one_nav_entry(tmp_path):
    out, r = make(tmp_path, name="그냥 글.txt", text="제목 없는 글입니다.\n\n둘째 문단.\n", epub_version="3")
    check(out)
    z = zipfile.ZipFile(out)
    assert nav_entries(z) == [("ch0001.xhtml", "그냥 글")] and r.no_chapters


def test_epub3_nav_has_one_entry_per_chapter_even_when_a_chapter_is_split(tmp_path):
    sections = [chap.Section("긴 장", ["가" * 300] * 20), chap.Section("짧은 장", ["나"])]
    path, nav_count, files = core.build_epub(str(tmp_path / "split.epub"), "책", "", "ko", sections,
                                             split_bytes=1500, epub_version="3")
    check(path)
    z = zipfile.ZipFile(path)
    assert nav_count == 2 and files > 2
    entries = nav_entries(z)
    assert entries[0] == ("ch0001.xhtml", "긴 장") and [t for _, t in entries] == ["긴 장", "짧은 장"]
    hrefs = spine_hrefs(ET.fromstring(z.read("OEBPS/content.opf")))
    assert "ch0001-2.xhtml" in hrefs and len(hrefs) == files
    assert entries == ncx_entries(z)


def test_epub3_one_book_from_several_files(tmp_path):
    files = [write(tmp_path, f"책_00{i}화.txt", f"{i}화 제목\n\n본문 {i}.\n") for i in (1, 2, 3)]
    parts = core.merge_parts([core.load_text(f) for f in files], "책")
    r = core.convert_many(parts, core.Options(epub_version="3"), "합본", output_path=str(tmp_path / "합본.epub"))
    check(r.output_path)
    z = zipfile.ZipFile(r.output_path)
    assert len(nav_entries(z)) == r.nav == 3 and nav_entries(z) == ncx_entries(z)


@pytest.mark.parametrize("version", ["2", "3"])
def test_both_formats_handle_mixed_encodings_and_markup_characters(tmp_path, version):
    text = '제1장 <b>"&"</b>\n\n]]> & 이모지 🙂 와 한글 — ① 전각　공백\n'
    out, _ = make(tmp_path, name=f"특수{version}.txt", text=text, enc="utf-8", epub_version=version)
    check(out)
    z = zipfile.ZipFile(out)
    body = z.read("OEBPS/ch0001.xhtml").decode("utf-8")
    assert "&lt;b&gt;" in body and "&amp;" in body and "🙂" in body


# ---------------------------------------------------------------- the option itself

@pytest.mark.parametrize("given,expected", [("2", "2"), ("3", "3"), (3, "3"), (2, "2"), ("3.0", "3"), (" 3 ", "3"),
                                            ("x", "2"), ("", "2"), (None, "2"), ("03", "2"), ("4", "2")])
def test_options_validated_maps_every_value_to_2_or_3(given, expected):
    assert core.Options(epub_version=given).validated().epub_version == expected


def run_cli(argv: list[str]) -> tuple[int, str]:
    before = i18n.current_lang()
    buf, old_out, old_err = io.StringIO(), sys.stdout, sys.stderr
    sys.stdout = sys.stderr = buf
    try:
        try:
            code = cli.main(argv + ["--ui-lang", "en", "-y"])
        except SystemExit as exc:
            code = int(exc.code or 0)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        i18n.set_lang(before, persist=False)
    return code, buf.getvalue()


@pytest.mark.parametrize("flags,expected", [([], "2"), (["--epub3"], "3"), (["--epub-version", "3"], "3"),
                                            (["--epub-version", "2"], "2")])
def test_cli_chooses_the_format(tmp_path, flags, expected):
    p = write(tmp_path, "c.txt", BOOK_TEXT, "cp949")
    code, out = run_cli([p, *flags])
    assert code == 0, out
    z = zipfile.ZipFile(tmp_path / "c.epub")
    assert ("OEBPS/nav.xhtml" in z.namelist()) == (expected == "3")
    assert ('version="3.0"' in z.read("OEBPS/content.opf").decode("utf-8")) == (expected == "3")
    assert ("EPUB 3" in out and "upaper" in out) == (expected == "3")  # the upaper note shows only for EPUB 3
    check(str(tmp_path / "c.epub"))


def test_cli_rejects_an_unknown_format_and_merges_as_epub3(tmp_path):
    p = write(tmp_path, "c.txt", BOOK_TEXT, "cp949")
    code, out = run_cli([p, "--epub-version", "4"])
    assert code == 2 and not (tmp_path / "c.epub").exists()
    folder = tmp_path / "연재"
    for i in (1, 2):
        write(folder, f"연재_00{i}.txt", f"본문 {i}.\n")
    code, out = run_cli([str(folder), "--merge", "--epub3", "--output", str(tmp_path / "합본.epub")])
    assert code == 0, out
    z = zipfile.ZipFile(tmp_path / "합본.epub")
    assert len(nav_entries(z)) == 2
    check(str(tmp_path / "합본.epub"))


def test_help_describes_both_flags_in_every_language():
    before = i18n.current_lang()
    try:
        for lang in i18n.LANGS:
            buf, old = io.StringIO(), sys.stdout
            sys.stdout = buf
            try:
                with pytest.raises(SystemExit):
                    cli.main(["--help", "--ui-lang", lang])
            finally:
                sys.stdout = old
            text = buf.getvalue()
            assert "--epub-version" in text and "--epub3" in text and "EPUB 3" in text, lang
    finally:
        i18n.set_lang(before, persist=False)


# ---------------------------------------------------------------- settings and GUI

def test_saved_options_trust_nothing_about_the_format():
    import gui

    assert gui._saved_options({"options": {"epub_version": "3"}}).epub_version == "3"
    for bad in (3, None, ["3"], {"v": 3}, "x", "", True):
        assert gui._saved_options({"options": {"epub_version": bad}}).epub_version == "2", bad
    assert gui._saved_options({}).epub_version == "2" and gui._saved_options({"options": 5}).epub_version == "2"


def test_gui_format_choice_is_used_remembered_and_translated(app, tmp_path):
    import gui

    assert app.var_epub_version.get() == "2" and app.cmb_epub.current() == 0
    assert list(app.cmb_epub["values"]) == ["EPUB 2 (default)", "EPUB 3 (latest)"]
    assert app.options().epub_version == "2"
    app.cmb_epub.current(1)
    app._on_epub_version()
    assert app.var_epub_version.get() == "3" and app.options().epub_version == "3"
    assert "upaper" in app.txt_log.get("1.0", "end")       # the note is read where the choice is made
    app._save_options()
    assert app.saved["options"]["epub_version"] == "3"
    assert gui._saved_options(app.saved).epub_version == "3"
    for i, lang in enumerate(i18n.LANGS):                   # the labels follow the screen language, the choice stays
        app.cmb_lang.current(i)
        app._on_lang()
        assert app.cmb_epub.current() == 1 and app.options().epub_version == "3"
        assert list(app.cmb_epub["values"]) == [i18n.t("format_epub2"), i18n.t("format_epub3")], lang
    app.cmb_epub.current(0)
    app._on_epub_version()
    assert app.options().epub_version == "2"


def test_gui_converts_to_epub3_and_check_passes(app, tmp_path):
    p = write(tmp_path, "화면.txt", BOOK_TEXT, "cp949")
    app.add_paths([p])
    wait_loaded(app)
    app.cmb_epub.current(1)
    app._on_epub_version()
    app.run()
    wait_worker(app)
    assert len(app.outputs) == 1
    out = app.outputs[0]
    z = zipfile.ZipFile(out)
    assert 'version="3.0"' in z.read("OEBPS/content.opf").decode("utf-8")
    assert [t for _, t in nav_entries(z)] == ["화면", "제1장 시작", "제2장 이어서", TITLE3]
    check(out)
