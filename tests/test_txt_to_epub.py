"""Tests for txt-to-epub. Run with:  python -m unittest discover -s tests -v

Set EPUBCHECK_JAR to a path to epubcheck.jar to also validate the EPUBs.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import chapters as chap  # noqa: E402
import cover  # noqa: E402
import detect  # noqa: E402
import epub_build as core  # noqa: E402
import main as cli  # noqa: E402

SAMPLES = os.path.join(REPO, "samples")
EPUBCHECK = os.environ.get("EPUBCHECK_JAR")


def sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def epubcheck(path: str) -> list[dict]:
    """Messages of severity ERROR/FATAL from epubcheck, or [] when unavailable."""
    if not EPUBCHECK or not os.path.isfile(EPUBCHECK) or shutil.which("java") is None:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "r.json")
        subprocess.run(["java", "-jar", EPUBCHECK, path, "--json", out], capture_output=True, timeout=300)
        data = json.load(open(out, encoding="utf-8"))
    return [m for m in data.get("messages", []) if m.get("severity") in ("ERROR", "FATAL")]


class TempDirMixin:
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="t2e_")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name: str, data: bytes) -> str:
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p


KO_TEXT = "머리말\n\n제1장 시작\n\n첫째 문단입니다.\n둘째 줄도 같은 문단.\n\n제2장 이어서\n\n또 다른 문단.\n"


class DetectTests(unittest.TestCase):
    def test_bom_and_utf8(self):
        self.assertEqual(detect.detect(b"\xef\xbb\xbfabc").encoding, "utf-8-sig")
        self.assertEqual(detect.detect("한글".encode("utf-8")).encoding, "utf-8")
        self.assertEqual(detect.detect("한글".encode("utf-8")).confidence, 100)

    def test_utf16(self):
        d = detect.detect("한글 텍스트 파일입니다".encode("utf-16"))
        self.assertEqual(d.encoding, "utf-16")
        d = detect.detect(("한글 텍스트 파일입니다 " * 50).encode("utf-16-le"))
        self.assertEqual(d.encoding, "utf-16-le")

    def test_cp949_detected_without_settings(self):
        data = (KO_TEXT * 5).encode("cp949")
        d = detect.detect(data)
        self.assertEqual(d.encoding, "cp949")
        self.assertGreaterEqual(d.confidence, detect.LOW_CONFIDENCE)
        text, bad = detect.decode(data, d.encoding)
        self.assertEqual(bad, 0)
        self.assertIn("첫째 문단입니다", text)

    def test_extended_hangul_needs_cp949(self):
        # '똠' is not in EUC-KR; decoding as cp949 keeps it.
        data = "똠방각하 이야기 제1장".encode("cp949")
        text, bad = detect.decode(data, detect.detect(data).encoding)
        self.assertEqual(bad, 0)
        self.assertIn("똠", text)

    def test_replacement_count(self):
        data = "가나다".encode("cp949") + b"\xff\xff" + "라".encode("cp949")
        text, bad = detect.decode(data, "cp949")
        self.assertEqual(bad, 2)
        self.assertEqual(text.count("�"), 2)

    def test_empty_file(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "e.txt")
            open(p, "wb").close()
            with self.assertRaises(detect.EmptyFile):
                detect.read_file(p)
            with open(p, "wb") as f:
                f.write(b"\xef\xbb\xbf \r\n\x1a")
            with self.assertRaises(detect.EmptyFile):
                detect.read_file(p)
        finally:
            shutil.rmtree(tmp)


class ChapterTests(unittest.TestCase):
    def heads(self, *lines):
        rx = chap.compile_pattern(chap.DEFAULT_PATTERN)
        return [chap.is_heading(l, rx) for l in lines]

    def test_default_pattern_matches_prd_forms(self):
        self.assertTrue(all(self.heads("제1장", "제 12 화 제목", "3.", "1. 시작", "12화", "Chapter 7",
                                       "CHAPTER XII. The Pool", "第3章", "第十二話 帰郷", "第3话", "프롤로그", "エピローグ")))

    def test_default_pattern_rejects_body_text(self):
        self.assertFalse(any(self.heads("그는 제1장을 읽었다", "1990년의 일이었다", "3.5kg", "x" * 90,
                                        "제일 좋아하는 계절", "제11111장", "", "   ")))

    def test_detect_and_front_section(self):
        lines = chap.normalize(KO_TEXT)
        ch = chap.detect_chapters(lines, chap.DEFAULT_PATTERN, "책")
        self.assertEqual([c.title for c in ch], ["책", "제1장 시작", "제2장 이어서"])
        self.assertFalse(ch[0].heading)
        self.assertEqual(ch[1].start, 2)

    def test_no_chapters_is_one_section(self):
        ch = chap.detect_chapters(["그냥 글", "계속"], chap.DEFAULT_PATTERN, "책")
        self.assertEqual(len(ch), 1)
        self.assertFalse(ch[0].heading)
        self.assertEqual(chap.heading_count(ch), 0)

    def test_toggle_and_manual(self):
        lines = chap.normalize(KO_TEXT)
        ch = chap.detect_chapters(lines, chap.DEFAULT_PATTERN, "책")
        ch[2].enabled = False
        merged = chap.apply_selection(lines, ch, "책")
        self.assertEqual([c.title for c in merged], ["책", "제1장 시작"])
        self.assertEqual(merged[1].end, len(lines))
        manual = chap.build_chapters(lines, [2, 4], "책", manual={4})
        self.assertTrue(manual[2].manual)
        self.assertEqual(manual[2].title, "첫째 문단입니다.")

    def test_bad_pattern(self):
        with self.assertRaises(chap.BadPattern):
            chap.compile_pattern("(")

    def test_paragraph_modes(self):
        lines = chap.normalize("가나\n다라\n\nEnglish\nwrapped\n\n日本語の\n文章です\n")
        self.assertEqual(chap.choose_paragraph_mode(lines, "auto"), "blank")
        self.assertEqual(chap.paragraphs_of(lines, "blank"),
                         ["가나 다라", "English wrapped", "日本語の文章です"])
        self.assertEqual(len(chap.paragraphs_of(lines, "line")), 6)
        self.assertEqual(chap.choose_paragraph_mode(["a"] * 100, "auto"), "line")

    def test_normalize_strips_xml_forbidden(self):
        lines = chap.normalize("a\x1a\x00b\r\nc\t d　")
        self.assertEqual(lines, ["ab", "c     d"])


class BuildTests(TempDirMixin, unittest.TestCase):
    def convert(self, name: str, data: bytes, **opt) -> tuple[str, core.FileResult]:
        p = self.write(name, data)
        before = sha(p)
        r = core.convert_file(p, core.Options(**opt))
        self.assertEqual(sha(p), before, "input must not be modified")
        return p, r

    def check_structure(self, epub: str) -> zipfile.ZipFile:
        z = zipfile.ZipFile(epub)
        first = z.infolist()[0]
        self.assertEqual(first.filename, "mimetype")
        self.assertEqual(first.compress_type, zipfile.ZIP_STORED)
        self.assertEqual(z.read("mimetype"), b"application/epub+zip")
        names = z.namelist()
        self.assertIn("META-INF/container.xml", names)
        self.assertIn("OEBPS/content.opf", names)
        self.assertIn("OEBPS/toc.ncx", names)
        for n in names:
            if n.endswith((".xhtml", ".opf", ".ncx", ".xml")):
                ET.fromstring(z.read(n))  # well-formed XML
        opf = z.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn('version="2.0"', opf)
        self.assertEqual(epubcheck(epub), [])
        return z

    def test_euc_kr_sample_converts_without_settings(self):
        src = os.path.join(SAMPLES, "euc-kr.txt")
        dst = shutil.copy(src, os.path.join(self.tmp, "euc-kr.txt"))
        r = core.convert_file(dst, core.Options())
        self.assertEqual(r.replaced, 0)
        z = self.check_structure(r.output_path)
        ncx = z.read("OEBPS/toc.ncx").decode("utf-8")
        self.assertIn("제1장 진달래꽃", ncx)
        self.assertIn("제4장 먼 후일", ncx)
        self.assertEqual(r.chapters, 4)  # the 4 poems
        self.assertEqual(r.nav, 5)       # plus the front section
        body = z.read("OEBPS/ch0002.xhtml").decode("utf-8")
        self.assertIn("영변에 약산", body)
        self.assertNotIn("�", body)
        self.assertIn("<dc:language>ko</dc:language>", z.read("OEBPS/content.opf").decode("utf-8"))

    def test_utf8_sample(self):
        dst = shutil.copy(os.path.join(SAMPLES, "utf8.txt"), os.path.join(self.tmp, "utf8.txt"))
        r = core.convert_file(dst, core.Options(author="Lewis Carroll", cover_mode="auto"))
        z = self.check_structure(r.output_path)
        self.assertIn("OEBPS/cover.xhtml", z.namelist())
        self.assertIn("OEBPS/images/cover.jpg", z.namelist())
        opf = z.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn('<meta name="cover" content="cover-image"/>', opf)
        self.assertIn("<dc:language>en</dc:language>", opf)
        self.assertIn("<dc:creator opf:role=\"aut\">Lewis Carroll</dc:creator>", opf)
        # wrapped lines were joined into one paragraph
        body = z.read("OEBPS/ch0002.xhtml").decode("utf-8")
        self.assertIn("sitting by her sister on the bank, and of having", body)

    def test_300_chapters_in_ncx(self):
        text = "\n".join(f"제{n}장 이야기\n\n본문 {n}.\n" for n in range(1, 301))
        p, r = self.convert("many.txt", text.encode("utf-8"))
        self.assertEqual(r.chapters, 300)
        z = self.check_structure(r.output_path)
        ncx = z.read("OEBPS/toc.ncx").decode("utf-8")
        self.assertEqual(ncx.count("<navPoint "), 300)
        self.assertIn('playOrder="300"', ncx)
        self.assertIn("제300장 이야기", ncx)

    def test_no_chapters_one_section(self):
        p, r = self.convert("plain.txt", "그냥 글입니다.\n\n둘째 문단.\n".encode("cp949"))
        self.assertTrue(r.no_chapters)
        z = self.check_structure(r.output_path)
        self.assertEqual(z.read("OEBPS/toc.ncx").decode("utf-8").count("<navPoint "), 1)
        self.assertIn("<h1>plain</h1>", z.read("OEBPS/ch0001.xhtml").decode("utf-8"))

    def test_huge_chapter_is_split(self):
        para = "가" * 5000 + "\n\n"
        text = "제1장 큰 장\n\n" + para * 120  # ~1.8 MB of XHTML in one chapter
        p, r = self.convert("huge.txt", text.encode("utf-8"))
        self.assertEqual(r.chapters, 1)
        self.assertGreater(r.files, 1)
        z = self.check_structure(r.output_path)
        for n in z.namelist():
            if n.startswith("OEBPS/ch"):
                self.assertLessEqual(len(z.read(n)), chap.CHAPTER_SPLIT_BYTES + 4096)
        self.assertEqual(z.read("OEBPS/toc.ncx").decode("utf-8").count("<navPoint "), 1)

    def test_output_name_collision_including_folder(self):
        p = self.write("book.txt", "제1장\n\n본문\n".encode("utf-8"))
        os.mkdir(os.path.join(self.tmp, "book.epub"))  # a folder holds the name
        self.write("book(2).epub", b"x")
        r = core.convert_file(p, core.Options())
        self.assertEqual(os.path.basename(r.output_path), "book(3).epub")
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "book.epub")))
        self.assertEqual(open(os.path.join(self.tmp, "book(2).epub"), "rb").read(), b"x")

    def test_replaced_characters_are_counted_and_xml_safe(self):
        data = "제1장 시작\n\n가나".encode("cp949") + b"\xff" + "다 <태그> & 앰퍼샌드\n".encode("cp949")
        p, r = self.convert("bad.txt", data)
        self.assertEqual(r.replaced, 1)
        z = self.check_structure(r.output_path)
        body = z.read("OEBPS/ch0001.xhtml").decode("utf-8")
        self.assertIn("&lt;태그&gt; &amp; 앰퍼샌드", body)

    def test_forced_encoding_and_lang_and_style(self):
        p = self.write("jp.txt", "第1章 始まり\n\n日本語の本文。\n".encode("shift_jis"))
        r = core.convert_file(p, core.Options(encoding="shift_jis", text_lang="ja", indent=False,
                                              line_height="1.6", publisher="Pub"))
        z = self.check_structure(r.output_path)
        opf = z.read("OEBPS/content.opf").decode("utf-8")
        self.assertIn("<dc:language>ja</dc:language>", opf)
        self.assertIn("<dc:publisher>Pub</dc:publisher>", opf)
        css = z.read("OEBPS/style.css").decode("utf-8")
        self.assertIn("text-indent: 0;", css)
        self.assertIn("line-height: 1.6;", css)
        self.assertNotIn("font-family", css)

    def test_guess_text_lang(self):
        self.assertEqual(core.guess_text_lang("한국어 문장입니다"), "ko")
        self.assertEqual(core.guess_text_lang("これは日本語の文です"), "ja")
        self.assertEqual(core.guess_text_lang("这是中文句子"), "zh")
        self.assertEqual(core.guess_text_lang("Plain English"), "en")

    def test_cover_file_and_small_warning(self):
        from PIL import Image

        small = os.path.join(self.tmp, "small.png")
        Image.new("RGB", (300, 450), (200, 10, 10)).save(small)
        p = self.write("c.txt", "제1장\n\n본문\n".encode("utf-8"))
        r = core.convert_file(p, core.Options(cover_mode="file", cover_path=small))
        self.assertTrue(r.cover_small)
        z = self.check_structure(r.output_path)
        self.assertIn("OEBPS/images/cover.png", z.namelist())
        big = cover.make_cover("제목", "저자", "ko")
        self.assertFalse(big.too_small)
        self.assertEqual(big.media_type, "image/jpeg")

    def test_cancel_leaves_no_file(self):
        p = self.write("cancel.txt", "제1장\n\n본문\n".encode("utf-8"))
        ev = threading.Event()
        ev.set()
        loaded = core.load_text(p)
        with self.assertRaises(core.Cancelled):
            core.convert(loaded, core.Options(), cancel=ev)
        self.assertEqual([f for f in os.listdir(self.tmp) if f.endswith((".epub", ".part"))], [])

    def test_options_validated(self):
        o = core.Options(encoding="nope", pattern="(", paragraph_mode="x", text_lang="fr", cover_mode="y",
                         line_height="9").validated()
        self.assertEqual((o.encoding, o.pattern, o.paragraph_mode, o.text_lang, o.cover_mode, o.line_height),
                         (detect.AUTO, chap.DEFAULT_PATTERN, "auto", core.LANG_AUTO, "none", ""))

    def test_collect_txts(self):
        os.mkdir(os.path.join(self.tmp, "sub"))
        a = self.write("A.TXT", b"x")
        b = self.write(os.path.join("sub", "b.txt"), b"y")
        self.write("c.md", b"z")
        found = core.collect_txts([self.tmp, a])
        self.assertEqual(sorted(os.path.basename(f) for f in found), ["A.TXT", "b.txt"])


class CliTests(TempDirMixin, unittest.TestCase):
    def run_cli(self, *argv) -> tuple[int, str]:
        buf = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = buf
        try:
            code = cli.main(list(argv) + ["--ui-lang", "en"])
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        return code, buf.getvalue()

    def test_cli_success_and_title(self):
        p = self.write("n.txt", KO_TEXT.encode("cp949"))
        code, out = self.run_cli(p, "--title", "My Book", "--author", "Me", "--lang", "ko", "--cover", "auto")
        self.assertEqual(code, 0, out)
        z = zipfile.ZipFile(os.path.join(self.tmp, "n.epub"))
        self.assertIn("<dc:title>My Book</dc:title>", z.read("OEBPS/content.opf").decode("utf-8"))
        self.assertIn("2 chapters detected", out)

    def test_cli_batch_continues_after_empty_file(self):
        self.write("empty.txt", b"")
        p2 = self.write("ok.txt", "Chapter 1\n\nText\n".encode("utf-8"))
        code, out = self.run_cli(os.path.join(self.tmp, "empty.txt"), p2, "-y")
        self.assertEqual(code, 1)
        self.assertIn("The file is empty", out)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "ok.epub")))

    def test_cli_no_input_and_bad_args(self):
        self.assertEqual(self.run_cli(os.path.join(self.tmp, "missing.txt"))[0], 2)
        p = self.write("x.txt", b"abc")
        self.assertEqual(self.run_cli(p, "--chapter-pattern", "(")[0], 2)
        self.assertEqual(self.run_cli(p, "--encoding", "nope")[0], 2)

    def test_cli_help_is_translated(self):
        for lang, word in (("ko", "사용법"), ("en", "usage"), ("zh-CN", "用法"), ("ja", "使い方")):
            buf = io.StringIO()
            old = sys.stdout
            sys.stdout = buf
            try:
                with self.assertRaises(SystemExit):
                    cli.main(["--help", "--ui-lang", lang])
            finally:
                sys.stdout = old
            self.assertIn(word, buf.getvalue())


class SettingsTests(TempDirMixin, unittest.TestCase):
    def test_broken_settings_use_defaults(self):
        import gui

        for raw in ({"options": {"pattern": 5, "indent": "yes", "line_height": 1.6, "cover_mode": None}},
                    {"options": "garbage"}, {}):
            o = gui._saved_options(raw)
            self.assertEqual(o.pattern, chap.DEFAULT_PATTERN)
            self.assertTrue(o.indent)
            self.assertEqual(o.line_height, "")
            self.assertEqual(o.cover_mode, "none")


if __name__ == "__main__":
    unittest.main()
