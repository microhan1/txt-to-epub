"""Fixture-driven cases for txt-to-epub: encodings, chapter forms, paragraphs,
file names, metadata, covers and batch behaviour. Every EPUB produced is
checked structurally and, when EPUBCHECK_JAR is set, with epubcheck.

    python -m unittest tests.test_cases -v
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import chapters as chap  # noqa: E402
import detect  # noqa: E402
import epub_build as core  # noqa: E402
import i18n  # noqa: E402
import main as cli  # noqa: E402

EPUBCHECK = os.environ.get("EPUBCHECK_JAR")
NS = {"x": "http://www.w3.org/1999/xhtml", "ncx": "http://www.daisy.org/z3986/2005/ncx/",
      "opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}


def epubcheck_errors(path: str) -> list[str]:
    if not EPUBCHECK or not os.path.isfile(EPUBCHECK) or shutil.which("java") is None:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "r.json")
        subprocess.run(["java", "-jar", EPUBCHECK, path, "--json", out], capture_output=True, timeout=300)
        data = json.load(open(out, encoding="utf-8"))
    return [f"{m.get('ID')}: {m.get('message')}" for m in data.get("messages", [])
            if m.get("severity") in ("ERROR", "FATAL", "WARNING")]


class Book:
    """Read-back helper for a produced EPUB."""

    def __init__(self, path: str):
        self.path = path
        self.z = zipfile.ZipFile(path)
        self.opf = ET.fromstring(self.z.read("OEBPS/content.opf"))
        self.ncx = ET.fromstring(self.z.read("OEBPS/toc.ncx"))

    def meta(self, tag: str) -> str:
        el = self.opf.find(f"opf:metadata/dc:{tag}", NS)
        return el.text or "" if el is not None else ""

    def nav_labels(self) -> list[str]:
        return [e.text or "" for e in self.ncx.findall(".//ncx:navLabel/ncx:text", NS)]

    def spine_hrefs(self) -> list[str]:
        ids = {i.get("id"): i.get("href") for i in self.opf.findall("opf:manifest/opf:item", NS)}
        return [ids[r.get("idref")] for r in self.opf.findall("opf:spine/opf:itemref", NS)]

    def doc(self, href: str) -> ET.Element:
        return ET.fromstring(self.z.read("OEBPS/" + href))

    def paragraphs(self, href: str) -> list[str]:
        return [("".join(p.itertext())) for p in self.doc(href).findall(".//x:p", NS)]

    def heading(self, href: str) -> str:
        for tag in ("h1", "h2"):
            h = self.doc(href).find(f".//x:{tag}", NS)
            if h is not None:
                return "".join(h.itertext())
        return ""

    def all_paragraphs(self) -> list[str]:
        out = []
        for href in self.spine_hrefs():
            if href != "cover.xhtml":
                out += self.paragraphs(href)
        return out


class CaseBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="t2e_cases_")

    def tearDown(self) -> None:
        for root, dirs, files in os.walk(self.tmp):
            for n in files:
                try:
                    os.chmod(os.path.join(root, n), stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name: str, data: bytes | str, encoding: str = "utf-8") -> str:
        p = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode(encoding))
        return p

    def convert(self, path: str, **opt) -> Book:
        before = hashlib.sha256(open(path, "rb").read()).hexdigest()
        r = core.convert_file(path, core.Options(**opt))
        self.assertEqual(hashlib.sha256(open(path, "rb").read()).hexdigest(), before, "original modified")
        self.result = r
        return self.check(r.output_path)

    def check(self, epub: str) -> Book:
        z = zipfile.ZipFile(epub)
        info = z.infolist()
        self.assertEqual(info[0].filename, "mimetype")
        self.assertEqual(info[0].compress_type, zipfile.ZIP_STORED)
        for n in z.namelist():
            if n.endswith((".xhtml", ".opf", ".ncx", ".xml")):
                ET.fromstring(z.read(n))
        self.assertEqual(z.testzip(), None)
        self.assertEqual(epubcheck_errors(epub), [], epub)
        return Book(epub)


KO_BODY = "머리말입니다.\n\n제1장 시작\n\n첫째 문단.\n둘째 줄.\n\n제2장 끝\n\n마지막 문단.\n"


class EncodingCases(CaseBase):
    def test_every_supported_code_page_round_trips(self):
        cases = {
            "cp949": ("제1장 똠방각하\n\n펲시콜라와 한글.\n", "펲시콜라와 한글."),
            "euc_kr": ("제1장 시작\n\n한글 본문입니다.\n", "한글 본문입니다."),
            "utf-8": ("제1장 시작\n\n한글 본문 🙂 이모지.\n", "한글 본문 🙂 이모지."),
            "utf-8-sig": ("제1장 시작\n\nBOM 파일.\n", "BOM 파일."),
            "utf-16": ("제1장 시작\n\nUTF-16 BOM.\n", "UTF-16 BOM."),
            "utf-16-le": ("제1장 시작\n\nUTF-16 LE 본문.\n", "UTF-16 LE 본문."),
            "utf-16-be": ("제1장 시작\n\nUTF-16 BE 본문.\n", "UTF-16 BE 본문."),
            "shift_jis": ("第1章 始まり\n\n日本語の本文です。\n", "日本語の本文です。"),
            "euc-jp": ("第1章 始まり\n\n日本語の本文です。\n", "日本語の本文です。"),
            "gb18030": ("第1章 开始\n\n这是中文正文。\n", "这是中文正文。"),
            "gb2312-short": ("第1章 开始\n\n这是中文正文\n", "这是中文正文"),  # bytes that are also valid CP949
            "big5": ("第1章 開始\n\n這是中文正文。\n", "這是中文正文。"),
            "ascii": ("Chapter 1\n\nPlain ASCII text.\n", "Plain ASCII text."),
        }
        for enc, (text, expect) in cases.items():
            with self.subTest(enc=enc):
                p = self.write(f"{enc}.txt", (text * 20), enc.split("-short")[0].replace("gb2312", "gb18030"))
                book = self.convert(p)
                self.assertEqual(self.result.replaced, 0, enc)
                self.assertIn(expect, book.all_paragraphs(), enc)

    def test_forced_encoding_beats_detection(self):
        p = self.write("forced.txt", "제1장\n\n강제 지정.\n", "cp949")
        book = self.convert(p, encoding="cp949")
        self.assertIn("강제 지정.", book.all_paragraphs())
        # wrong forced encoding: replacements are counted, nothing crashes, XML stays valid
        book = self.convert(p, encoding="utf-8")
        self.assertGreater(self.result.replaced, 0)

    def test_line_endings_and_dos_eof(self):
        for name, text in (("crlf", "제1장\r\n\r\n본문 한 줄.\r\n둘째 줄.\r\n"),
                           ("cr", "제1장\r\r본문 한 줄.\r둘째 줄.\r"),
                           ("mixed", "제1장\n\r\n본문 한 줄.\r둘째 줄.\r\n"),
                           ("dos_eof", "제1장\n\n본문 한 줄.\n\x1a")):
            with self.subTest(name=name):
                book = self.convert(self.write(f"{name}.txt", text, "cp949"))
                paras = book.all_paragraphs()
                self.assertEqual(paras[0].split()[0], "본문", paras)
                self.assertNotIn("\x1a", "".join(paras))

    def test_control_and_special_characters_are_xml_safe(self):
        text = "제1장 <시작> & \"인용\" 'holder'\n\n탭\t문자 \x07벨 \x0c폼피드 nbsp 끝 전각　공백 ]]> 끝.\n"
        book = self.convert(self.write("special.txt", text))
        self.assertEqual(book.nav_labels()[-1], "제1장 <시작> & \"인용\" 'holder'")
        para = book.all_paragraphs()[0]
        self.assertIn("탭 문자 벨 폼피드 nbsp 끝 전각 공백 ]]> 끝.", para)

    def test_only_whitespace_or_bom_is_empty(self):
        for name, data in (("spaces", b"   \r\n\r\n  "), ("bom", b"\xef\xbb\xbf"), ("zero", b""),
                           ("utf16", "  \n".encode("utf-16"))):
            with self.subTest(name=name):
                with self.assertRaises(detect.EmptyFile):
                    core.convert_file(self.write(f"{name}.txt", data), core.Options())

    def test_damaged_bytes_in_korean_file(self):
        good = ("제1장 시작\n\n한글 소설 본문입니다. 그는 천천히 걸었다.\n" * 50).encode("cp949")
        data = good[:200] + b"\xff\xfe" + good[200:]
        book = self.convert(self.write("damaged.txt", data))
        self.assertEqual(self.result.replaced, 2)  # two stray bytes -> two U+FFFD
        self.assertIn("한글 소설 본문입니다. 그는 천천히 걸었다.", book.all_paragraphs())
        det = detect.detect(data)
        self.assertEqual(det.encoding, "cp949")
        self.assertGreaterEqual(det.confidence, detect.LOW_CONFIDENCE)

    def test_short_file_and_single_line(self):
        book = self.convert(self.write("one.txt", "한 줄뿐인 파일", "cp949"))
        self.assertEqual(book.all_paragraphs(), ["한 줄뿐인 파일"])
        self.assertTrue(self.result.no_chapters)
        self.assertEqual(book.heading("ch0001.xhtml"), "one")


class ChapterCases(CaseBase):
    def test_heading_forms(self):
        forms = ["제1장 시작", "제 2 장 띄어쓰기", "제3화", "4화", "5.", "6. 제목", "Chapter 7", "CHAPTER VIII. Roman",
                 "Part 9", "第10章", "第十一話 帰郷", "第12话", "第13回", "프롤로그", "에필로그", "Epilogue",
                 "序章", "プロローグ", "１４화", "제15편", "제16부"]
        text = "\n\n".join(f"{h}\n\n본문 {i}." for i, h in enumerate(forms, 1)) + "\n"
        book = self.convert(self.write("forms.txt", text))
        self.assertEqual(book.nav_labels(), forms)
        self.assertEqual(self.result.chapters, len(forms))

    def test_lines_that_must_not_be_headings(self):
        body = ["그는 제1장을 읽었다", "1990년의 일이었다", "3.5kg", "12시 정각", "제일 좋아하는 계절",
                "Chapter 없는 문장 chapter", "장 하나", "1.2.3 버전", "12345678화", "제" + "1" * 5 + "장", "x" * 81]
        text = "제1장 진짜\n\n" + "\n\n".join(body) + "\n"
        book = self.convert(self.write("nofalse.txt", text))
        self.assertEqual(book.nav_labels(), ["제1장 진짜"])
        self.assertEqual(len(book.all_paragraphs()), len(body))

    def test_edge_positions(self):
        # heading on the first line, two headings back to back, heading as the very last line
        text = "제1장 첫 줄\n본문 A.\n제2장 빈 장\n제3장 셋째\n본문 C.\n제4장 마지막 줄"
        book = self.convert(self.write("edges.txt", text))
        self.assertEqual(book.nav_labels(), ["제1장 첫 줄", "제2장 빈 장", "제3장 셋째", "제4장 마지막 줄"])
        self.assertEqual(book.paragraphs("ch0002.xhtml"), [])
        self.assertEqual(book.paragraphs("ch0004.xhtml"), [])
        self.assertEqual(book.spine_hrefs()[0], "ch0001.xhtml")  # no front section

    def test_duplicate_titles_and_indented_headings(self):
        text = "   제1장\n\n가.\n\n\t제1장\n\n나.\n\n　제1장\n\n다.\n"
        book = self.convert(self.write("dups.txt", text))
        self.assertEqual(book.nav_labels(), ["제1장"] * 3)
        self.assertEqual([book.paragraphs(h) for h in book.spine_hrefs()], [["가."], ["나."], ["다."]])

    def test_custom_pattern_and_no_chapters(self):
        text = "*** 하나 ***\n\n가.\n\n*** 둘 ***\n\n나.\n\n제1장 무시\n\n다.\n"
        p = self.write("custom.txt", text)
        book = self.convert(p, pattern=r"^\*\*\* .+ \*\*\*$")
        self.assertEqual(book.nav_labels(), ["*** 하나 ***", "*** 둘 ***"])
        self.assertIn("제1장 무시", book.paragraphs("ch0002.xhtml"))
        book = self.convert(p, split_chapters=False)
        self.assertEqual(book.nav_labels(), ["custom"])
        self.assertEqual(len(book.all_paragraphs()), 6)
        # an invalid pattern in Options falls back to the default instead of failing
        self.assertEqual(core.Options(pattern="(").validated().pattern, chap.DEFAULT_PATTERN)

    def test_many_chapters_exact_boundaries(self):
        for n in (500, 501, 1000):
            with self.subTest(n=n):
                text = "".join(f"제{i}장\n본문 {i}.\n" for i in range(1, n + 1))
                book = self.convert(self.write(f"n{n}.txt", text))
                self.assertEqual(len(book.nav_labels()), n)
                self.assertEqual(book.nav_labels()[-1], f"제{n}장")
                plays = [int(e.get("playOrder")) for e in book.ncx.findall(".//ncx:navPoint", NS)]
                self.assertEqual(plays, list(range(1, n + 1)))
                self.assertEqual(book.all_paragraphs()[-1], f"본문 {n}.")

    def test_huge_single_paragraph_and_split_continuity(self):
        paras = [f"{i}:" + "가" * 3000 for i in range(1, 600)]  # ~5.4 MB of XHTML in one chapter
        text = "제1장\n\n" + "\n\n".join(paras) + "\n"
        book = self.convert(self.write("split.txt", text))
        hrefs = book.spine_hrefs()
        self.assertGreater(len(hrefs), 4)
        self.assertEqual(hrefs[0], "ch0001.xhtml")
        self.assertTrue(all(h.startswith("ch0001-") for h in hrefs[1:]))
        self.assertEqual(book.nav_labels(), ["제1장"])
        self.assertEqual(book.all_paragraphs(), paras)  # nothing lost or reordered
        self.assertEqual(book.heading("ch0001.xhtml"), "제1장")
        self.assertEqual(book.heading(hrefs[1]), "")  # continuation parts carry no heading
        one = "제1장\n\n" + "나" * 3_000_000 + "\n"   # one paragraph bigger than the limit stays whole
        book = self.convert(self.write("onepara.txt", one))
        self.assertEqual(len(book.spine_hrefs()), 1)


class ParagraphCases(CaseBase):
    def test_wrapped_text_per_language(self):
        cases = {
            "en": ("It was the best\nof times, it was\nthe worst of times.\n", "It was the best of times, it was the worst of times."),
            "ko": ("바람이 불었다\n그는 천천히\n걸었다.\n", "바람이 불었다 그는 천천히 걸었다."),
            "ja": ("風が吹いた。\n彼はゆっくり\n歩いた。\n", "風が吹いた。彼はゆっくり歩いた。"),
            "zh": ("风吹过。\n他慢慢地\n走着。\n", "风吹过。他慢慢地走着。"),
            "mixed": ("한글 다음에\nEnglish comes\n그리고 한글\n", "한글 다음에 English comes 그리고 한글"),
        }
        for name, (text, expect) in cases.items():
            with self.subTest(name=name):
                book = self.convert(self.write(f"wrap_{name}.txt", "Chapter 1\n\n" + text))
                self.assertEqual(book.all_paragraphs(), [expect])

    def test_web_novel_style_one_paragraph_per_line(self):
        lines = [f"{i}번째 문장입니다." for i in range(1, 101)]
        book = self.convert(self.write("lines.txt", "제1장\n" + "\n".join(lines) + "\n"))
        self.assertEqual(book.all_paragraphs(), lines)  # auto picked "line" mode

    def test_blank_line_variants_and_indentation(self):
        text = "제1장\n\n   \n　\n첫 문단\n\n\n\n\n둘째 문단\n  들여쓴 셋째 줄\n\n　　전각 들여쓰기\n"
        book = self.convert(self.write("blanks.txt", text))
        self.assertEqual(book.all_paragraphs(), ["첫 문단", "둘째 문단 들여쓴 셋째 줄", "전각 들여쓰기"])

    def test_forced_modes(self):
        p = self.write("modes.txt", "제1장\n\n가\n나\n\n다\n")
        self.assertEqual(self.convert(p, paragraph_mode="blank").all_paragraphs(), ["가 나", "다"])
        self.assertEqual(self.convert(p, paragraph_mode="line").all_paragraphs(), ["가", "나", "다"])

    def test_multiple_spaces_collapse_but_text_is_kept(self):
        book = self.convert(self.write("spaces.txt", "제1장\n\n가     나  다   .\n"))
        self.assertEqual(book.all_paragraphs(), ["가 나 다 ."])


class NamingCases(CaseBase):
    def test_awkward_file_names(self):
        names = ["한글 이름.txt", "日本語 名前.TXT", "name with #hash & amp %percent.txt", "deep/nested/folder/x.txt",
                 "dots.in.name.v2.txt", " leading space.txt"]
        for name in names:
            with self.subTest(name=name):
                p = self.write(name, "제1장\n\n본문.\n")
                book = self.convert(p)
                self.assertEqual(os.path.dirname(book.path), os.path.dirname(p))
                self.assertEqual(book.meta("title"), os.path.splitext(os.path.basename(name))[0].strip())
                self.assertEqual(book.all_paragraphs(), ["본문."])

    def test_collisions_and_readonly_original(self):
        p = self.write("book.txt", "제1장\n\n본문.\n")
        os.chmod(p, stat.S_IREAD)
        a = core.convert_file(p, core.Options()).output_path
        b = core.convert_file(p, core.Options()).output_path
        os.mkdir(os.path.join(self.tmp, "book(3).epub"))
        c = core.convert_file(p, core.Options()).output_path
        self.assertEqual([os.path.basename(x) for x in (a, b, c)], ["book.epub", "book(2).epub", "book(4).epub"])
        self.assertFalse(os.stat(p).st_mode & stat.S_IWRITE)
        self.assertEqual([n for n in os.listdir(self.tmp) if n.endswith(".part")], [])

    def test_collect_recurses_and_dedups(self):
        a = self.write("a.txt", "x")
        self.write("sub/b.TXT", "x")
        self.write("sub/deep/c.txt", "x")
        self.write("sub/skip.md", "x")
        self.write("sub/skip.epub", "x")
        found = core.collect_txts([self.tmp, a, a.upper(), os.path.join(self.tmp, "sub")])
        self.assertEqual([os.path.relpath(f, self.tmp).replace(os.sep, "/") for f in found],
                         ["a.txt", "sub/b.TXT", "sub/deep/c.txt"])


class MetadataCoverCases(CaseBase):
    def test_metadata_escaping_and_language(self):
        p = self.write("meta.txt", "제1장\n\n본문.\n")
        title = 'A & B <C> "D" \'E\''
        r = core.convert_file(p, core.Options(author="저자 & Co", publisher="<출판사>", text_lang="ja",
                                              cover_mode="auto"), title=title)
        book = self.check(r.output_path)
        self.assertEqual(book.meta("title"), title)
        self.assertEqual(book.meta("creator"), "저자 & Co")
        self.assertEqual(book.meta("publisher"), "<출판사>")
        self.assertEqual(book.meta("language"), "ja")
        self.assertEqual(book.doc("cover.xhtml").find(".//x:img", NS).get("alt"), title)
        self.assertEqual(book.ncx.find("ncx:docTitle/ncx:text", NS).text, title)

    def test_language_auto_detection(self):
        cases = {"ko": "제1장\n\n한국어 본문입니다. He said hello.\n", "en": "Chapter 1\n\nEnglish only text.\n",
                 "ja": "第1章\n\nこれは日本語の文です。\n", "zh": "第1章\n\n这是中文正文。\n"}
        for lang, text in cases.items():
            with self.subTest(lang=lang):
                book = self.convert(self.write(f"lang_{lang}.txt", text))
                self.assertEqual(book.meta("language"), lang)
                self.assertEqual(book.doc("ch0001.xhtml").get("{http://www.w3.org/XML/1998/namespace}lang"), lang)

    def test_cover_formats(self):
        from PIL import Image

        p = self.write("cov.txt", "제1장\n\n본문.\n")
        for fmt, ext, expect_ext, expect_type in (("JPEG", "jpg", "jpg", "image/jpeg"), ("PNG", "png", "png", "image/png"),
                                                  ("WEBP", "webp", "jpg", "image/jpeg"), ("BMP", "bmp", "jpg", "image/jpeg"),
                                                  ("GIF", "gif", "jpg", "image/jpeg")):
            with self.subTest(fmt=fmt):
                img = os.path.join(self.tmp, f"cover.{ext}")
                Image.new("RGB", (700, 1000), (10, 60, 120)).save(img, fmt)
                book = self.convert(p, cover_mode="file", cover_path=img)
                self.assertFalse(self.result.cover_small)
                self.assertIn(f"OEBPS/images/cover.{expect_ext}", book.z.namelist())
                item = [i for i in book.opf.findall("opf:manifest/opf:item", NS) if i.get("id") == "cover-image"][0]
                self.assertEqual(item.get("media-type"), expect_type)
                self.assertEqual(book.spine_hrefs()[0], "cover.xhtml")
                ref = book.opf.find("opf:guide/opf:reference[@type='cover']", NS)
                self.assertEqual(ref.get("href"), "cover.xhtml")
        with self.assertRaises(Exception):
            core.convert_file(p, core.Options(cover_mode="file", cover_path=p))  # a text file is not an image
        with self.assertRaises(Exception):
            core.convert_file(p, core.Options(cover_mode="file", cover_path=os.path.join(self.tmp, "missing.jpg")))

    def test_auto_cover_with_long_and_odd_titles(self):
        import cover

        for title in ("", "아주 " * 40 + "긴 제목", "Emoji 🙂 title", "日本語のタイトル", "A"):
            with self.subTest(title=title[:10]):
                img = cover.make_cover(title, "저자 이름이 아주 길어서 줄바꿈이 필요한 경우입니다 " * 3, "ko")
                self.assertEqual((img.width, img.height), (800, 1200))
                self.assertGreater(len(img.data), 1000)

    def test_style_options(self):
        p = self.write("style.txt", "제1장\n\n본문.\n")
        for indent, lh, want in ((True, "", "text-indent: 1em;"), (False, "1.8", "text-indent: 0; line-height: 1.8;")):
            book = self.convert(p, indent=indent, line_height=lh)
            css = book.z.read("OEBPS/style.css").decode("utf-8")
            self.assertIn(want, css)
            self.assertNotIn("font-family", css)


class BatchCliCases(CaseBase):
    def run_cli(self, *argv) -> tuple[int, str]:
        buf = io.StringIO()
        old_out, old_err, old_in = sys.stdout, sys.stderr, sys.stdin
        sys.stdout = sys.stderr = buf
        sys.stdin = io.StringIO()  # not a tty
        try:
            code = cli.main(list(argv) + ["--ui-lang", "en"])
        finally:
            sys.stdout, sys.stderr, sys.stdin = old_out, old_err, old_in
        return code, buf.getvalue()

    def test_mixed_batch_continues_and_reports(self):
        good1 = self.write("batch/a.txt", "제1장\n\n가.\n", "cp949")
        self.write("batch/empty.txt", b"")
        good2 = self.write("batch/sub/b.txt", "Chapter 1\n\nb.\n")
        self.write("batch/sub/c.md", "ignored")
        code, out = self.run_cli(os.path.join(self.tmp, "batch"), os.path.join(self.tmp, "nope.txt"), good1)
        self.assertEqual(code, 1, out)
        self.assertIn("Cannot open file", out)
        self.assertIn("The file is empty", out)
        self.assertIn("Done: 2 EPUB files created", out)
        self.assertTrue(os.path.exists(good1[:-4] + ".epub"))
        self.assertTrue(os.path.exists(good2[:-4] + ".epub"))
        self.assertEqual(out.count("[1/3]") + out.count("[2/3]") + out.count("[3/3]"), 3)  # duplicates removed
        for p in (good1, good2):
            self.check(p[:-4] + ".epub")

    def test_title_only_for_single_input(self):
        a = self.write("t1.txt", "x\n")
        b = self.write("t2.txt", "y\n")
        code, out = self.run_cli(a, b, "--title", "Shared")
        self.assertEqual(code, 0, out)
        self.assertEqual(Book(a[:-4] + ".epub").meta("title"), "t1")
        code, out = self.run_cli(a, "--title", "Single")
        self.assertEqual(Book(a[:-4] + "(2).epub").meta("title"), "Single")

    def test_confirmations_without_a_terminal(self):
        many = self.write("many.txt", "".join(f"제{i}장\n본문\n" for i in range(1, 502)))
        code, out = self.run_cli(many)
        self.assertEqual(code, 1)
        self.assertIn("Run again with -y", out)
        self.assertFalse(os.path.exists(many[:-4] + ".epub"))
        code, out = self.run_cli(many, "-y")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(Book(many[:-4] + ".epub").nav_labels()), 501)

    def test_cli_option_matrix(self):
        p = self.write("opts.txt", "第1章 始まり\n\n本文。\n", "shift_jis")
        code, out = self.run_cli(p, "--encoding", "shift_jis", "--lang", "ja", "--author", "作者", "--publisher", "版元",
                                 "--paragraph", "line", "--no-indent", "--line-height", "1.4", "--cover", "auto",
                                 "--chapter-pattern", "^第\\d+章")
        self.assertEqual(code, 0, out)
        book = self.check(p[:-4] + ".epub")
        self.assertEqual((book.meta("language"), book.meta("creator"), book.meta("publisher")), ("ja", "作者", "版元"))
        self.assertEqual(book.nav_labels(), ["第1章 始まり"])
        self.assertIn("line-height: 1.4;", book.z.read("OEBPS/style.css").decode())
        self.assertIn("OEBPS/images/cover.jpg", book.z.namelist())
        for bad in (["--line-height", "9"], ["--paragraph", "x"], ["--lang", "fr"], ["--cover", "missing.png"],
                    ["--encoding", "nope"], ["--chapter-pattern", "("]):
            with self.subTest(bad=bad):
                try:
                    code, out = self.run_cli(p, *bad)
                except SystemExit as exc:  # argparse rejects a bad choice with exit code 2
                    code = exc.code
                self.assertEqual(code, 2, bad)


class SettingsCases(CaseBase):
    def test_broken_settings_file_does_not_break_startup(self):
        real = i18n.SETTINGS_PATH
        p = os.path.join(self.tmp, "settings.json")
        i18n.SETTINGS_PATH = p
        try:
            for raw in (b"{ not json", b"[]", b'{"lang": 5}', b'{"lang": "xx", "options": 3}', b""):
                with self.subTest(raw=raw):
                    open(p, "wb").write(raw)
                    self.assertIn(i18n.init(), i18n.LANGS)
                    self.assertIsInstance(i18n.load_settings(), dict)
                    import gui

                    gui._saved_options(i18n.load_settings())
            i18n.set_lang("ja")
            self.assertEqual(json.load(open(p, encoding="utf-8"))["lang"], "ja")
            self.assertEqual(i18n.init(), "ja")
        finally:
            i18n.SETTINGS_PATH = real
            i18n.init("ko")


if __name__ == "__main__":
    unittest.main()
