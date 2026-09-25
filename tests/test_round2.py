"""Second verification round for txt-to-epub: real-world file shapes, random
input invariants, code-vs-language-file placeholder agreement, concurrency,
settings round trip, CLI encoding names and console output.

    python -m unittest tests.test_round2 -v
"""
from __future__ import annotations

import ast
import json
import os
import random
import re
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
import detect  # noqa: E402
import epub_build as core  # noqa: E402
import i18n  # noqa: E402

NS = {"x": "http://www.w3.org/1999/xhtml", "ncx": "http://www.daisy.org/z3986/2005/ncx/",
      "opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
WS = re.compile(r"\s+")


def book_sequence(epub: str) -> list[tuple[str, str]]:
    """(tag, text) for every h1/h2/p in spine order."""
    z = zipfile.ZipFile(epub)
    opf = ET.fromstring(z.read("OEBPS/content.opf"))
    ids = {i.get("id"): i.get("href") for i in opf.findall("opf:manifest/opf:item", NS)}
    seq = []
    for r in opf.findall("opf:spine/opf:itemref", NS):
        href = ids[r.get("idref")]
        if href == "cover.xhtml":
            continue
        for el in ET.fromstring(z.read("OEBPS/" + href)).iter():
            tag = el.tag.split("}")[-1]
            if tag in ("h1", "h2", "p"):
                seq.append((tag, "".join(el.itertext())))
    return seq


def book_text(epub: str) -> tuple[list[str], list[str]]:
    """(headings, paragraphs) in spine order."""
    seq = book_sequence(epub)
    return [t for k, t in seq if k in ("h1", "h2")], [t for k, t in seq if k == "p"]


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="t2e_r2_")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name: str, data, encoding="utf-8") -> str:
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode(encoding))
        return p


# ---------------------------------------------------------------- real-world shapes

class RealWorldShapes(Base):
    def titles(self, text: str, **opt) -> list[str]:
        p = self.write("shape.txt", text)
        r = core.convert_file(p, core.Options(**opt))
        return [t for t in book_text(r.output_path)[0]]

    def test_table_of_contents_at_top_is_not_chapters(self):
        toc = "소설 제목\n\n목차\n" + "".join(f"제{i}장 이야기 {i}\n" for i in range(1, 21)) + "\n"
        body = "".join(f"제{i}장 이야기 {i}\n\n본문 {i}.\n\n" for i in range(1, 21))
        for sep in ("", "\n", "머리말이 여기에.\n\n"):
            with self.subTest(sep=repr(sep)):
                heads = self.titles(toc + sep + body)
                self.assertEqual(heads[-20:], [f"제{i}장 이야기 {i}" for i in range(1, 21)])
                self.assertLessEqual(len(heads), 21)  # at most the front section extra

    def test_numbered_list_inside_a_chapter_stays_in_the_body(self):
        text = "제1장 준비물\n\n가져올 것:\n1. 사과\n2. 배\n3. 감\n4. 귤\n\n계속되는 본문.\n\n제2장 출발\n\n본문.\n"
        heads = self.titles(text)
        self.assertEqual(heads, ["제1장 준비물", "제2장 출발"])
        p = self.write("list.txt", text)
        _, paras = book_text(core.convert_file(p, core.Options()).output_path)
        self.assertIn("1. 사과", paras)
        self.assertIn("4. 귤", paras)

    def test_prologue_followed_directly_by_chapter_one_is_kept(self):
        self.assertEqual(self.titles("프롤로그\n제1장 시작\n\n본문.\n"), ["프롤로그", "제1장 시작"])

    def test_gutenberg_layout(self):
        text = ("The Project Gutenberg eBook of Example, by Nobody\n\nThis eBook is for the use of anyone anywhere.\n\n"
                "Title: Example\nAuthor: Nobody\n\n*** START OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***\n\n\n\n"
                "CONTENTS\n\n CHAPTER I. One\n CHAPTER II. Two\n CHAPTER III. Three\n\n\n\n"
                "CHAPTER I. One\n\nIt was a bright cold day in April,\nand the clocks were striking thirteen.\n\n"
                "CHAPTER II. Two\n\nSecond chapter text\nwrapped here.\n\n"
                "CHAPTER III. Three\n\nThird.\n\n*** END OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***\n")
        p = self.write("gutenberg.txt", text)
        r = core.convert_file(p, core.Options())
        heads, paras = book_text(r.output_path)
        self.assertEqual(heads[-3:], ["CHAPTER I. One", "CHAPTER II. Two", "CHAPTER III. Three"])
        self.assertIn("It was a bright cold day in April, and the clocks were striking thirteen.", paras)
        self.assertEqual(r.text_lang, "en")

    def test_korean_web_novel_layout(self):
        eps = "".join(f"{i}화\n\n{'그는 말했다. ' * 5}\n\n다음 화에 계속\n\n\n" for i in range(1, 51))
        heads = self.titles("웹소설 제목\n작가: 아무개\n\n" + eps)
        self.assertEqual(heads[-50:], [f"{i}화" for i in range(1, 51)])

    def test_dialogue_heavy_text_keeps_every_line(self):
        lines = ['"안녕?"', '"응, 안녕."', "그가 물었다.", '"어디 가?"', '"집에."']
        p = self.write("dialogue.txt", "제1장\n" + "\n".join(lines) + "\n")
        _, paras = book_text(core.convert_file(p, core.Options()).output_path)
        self.assertEqual(paras, lines)  # no blank lines -> one paragraph per line


# ---------------------------------------------------------------- invariants on random input

class RandomInvariants(Base):
    ALPHABET = ("가나다라마바사아자차카타파하 " * 3 + "abc def ghi " + "日本語の文 " + "中文字 " + "\"'<>&;:.,!?()" + "12345")

    def random_text(self, rng: random.Random) -> str:
        out = []
        for _ in range(rng.randint(5, 120)):
            kind = rng.random()
            if kind < 0.12:
                tail = "".join(rng.choice(self.ALPHABET) for _ in range(rng.randint(0, 8))).strip()
                out.append(rng.choice([f"제{rng.randint(1, 30)}장 {tail}", f"{rng.randint(1, 30)}화",
                                       f"Chapter {rng.randint(1, 30)}", f"第{rng.randint(1, 30)}章 {tail}"]).rstrip())
            elif kind < 0.3:
                out.append("")
            else:
                out.append("".join(rng.choice(self.ALPHABET) for _ in range(rng.randint(1, 70))))
        return "\n".join(out) + rng.choice(["", "\n", "\r\n", "\n\n\n"])

    def test_no_text_is_lost_or_reordered(self):
        for seed in range(40):
            rng = random.Random(seed)
            text = self.random_text(rng)
            enc = rng.choice(["utf-8", "cp949", "utf-16"])
            try:
                data = text.encode(enc)
            except UnicodeEncodeError:
                data = text.encode("utf-8")
                enc = "utf-8"
            mode = rng.choice(chap.PARAGRAPH_MODES)
            with self.subTest(seed=seed, enc=enc, mode=mode):
                p = self.write(f"rand{seed}.txt", data)
                r = core.convert_file(p, core.Options(paragraph_mode=mode))
                # h1 is the book title (front section or whole book), not source text
                got = WS.sub("", "".join(t for k, t in book_sequence(r.output_path) if k != "h1"))
                want = WS.sub("", text)
                self.assertEqual(got, want)
                self.assertEqual(r.replaced, 0)

    def test_detector_never_raises_and_always_returns_a_usable_codec(self):
        rng = random.Random(7)
        for i in range(300):
            n = rng.choice([0, 1, 2, 3, 7, 16, 100, 1000, 5000])
            data = bytes(rng.getrandbits(8) for _ in range(n))
            with self.subTest(i=i):
                d = detect.detect(data)
                self.assertTrue(0 <= d.confidence <= 100)
                text, bad = detect.decode(data, d.encoding)  # must not raise
                self.assertIsInstance(text, str)

    def test_random_valid_text_round_trips_in_every_code_page(self):
        rng = random.Random(3)
        pools = {"cp949": "가나다라마바사아자차카타파하는을이에서하다. ", "shift_jis": "日本語の文章ですかなカナ。 ",
                 "euc-jp": "日本語の文章ですかなカナ。 ", "gb18030": "这是中文的句子和文字。 ", "big5": "這是中文的句子和文字。 ",
                 "utf-16": "혼합 mixed 日本語 中文 text ", "utf-8": "혼합 mixed 日本語 中文 🙂 "}
        for enc, pool in pools.items():
            for k in range(5):
                text = "".join(rng.choice(pool) for _ in range(rng.randint(30, 400)))
                data = text.encode(enc)
                with self.subTest(enc=enc, k=k):
                    d = detect.detect(data)
                    decoded, bad = detect.decode(data, d.encoding)
                    self.assertEqual(bad, 0, (enc, d))
                    self.assertEqual(decoded, text, (enc, d))


# ---------------------------------------------------------------- code vs language files

class I18nAgreement(unittest.TestCase):
    def test_every_t_call_passes_exactly_the_placeholders_the_text_uses(self):
        strings = json.load(open(os.path.join(REPO, "lang", "en.json"), encoding="utf-8"))
        problems = []
        for name in ("gui.py", "main.py"):
            tree = ast.parse(open(os.path.join(REPO, name), encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                fname = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                if fname not in ("t", "log", "_set_status") or not node.args:
                    continue
                key = node.args[0]
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    continue
                if key.value not in strings:
                    problems.append(f"{name}:{node.lineno} unknown key {key.value}")
                    continue
                wanted = set(re.findall(r"\{(\w+)\}", strings[key.value]))
                passed = {kw.arg for kw in node.keywords if kw.arg}
                if any(kw.arg is None for kw in node.keywords):
                    continue  # **kwargs forwarding
                if wanted - passed:
                    problems.append(f"{name}:{node.lineno} {key.value} misses {sorted(wanted - passed)}")
        self.assertEqual(problems, [])

    def test_language_files_have_no_stray_braces(self):
        for lang in i18n.LANGS:
            strings = json.load(open(os.path.join(REPO, "lang", f"{lang}.json"), encoding="utf-8"))
            for key, text in strings.items():
                with self.subTest(lang=lang, key=key):
                    text.format(**{p: "" for p in re.findall(r"\{(\w+)\}", text)})


# ---------------------------------------------------------------- concurrency, settings, CLI

class ConcurrencyAndSettings(Base):
    def test_two_conversions_of_the_same_file_at_once_produce_two_files(self):
        text = "제1장\n\n" + ("본문 " * 2000 + "\n\n") * 200
        p = self.write("same.txt", text)
        results, errors = [], []

        def work():
            try:
                results.append(core.convert_file(p, core.Options()).output_path)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=work) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 4, results)
        for out in results:
            self.assertIsNone(zipfile.ZipFile(out).testzip())
        self.assertEqual([n for n in os.listdir(self.tmp) if ".part" in n], [])

    def test_gui_options_round_trip_through_settings_json(self):
        import gui

        opts = core.Options(pattern=r"^\s*제\s*\d+\s*화\b|^\*\*\* .+ \*\*\*$", paragraph_mode="line",
                            text_lang="ja", author="저자 \"이름\"", publisher="출판사 & Co", cover_mode="file",
                            cover_path=os.path.join(self.tmp, "표지.png"), indent=False, line_height="1.8",
                            split_chapters=False)
        saved = json.loads(json.dumps({"options": opts.__dict__}, ensure_ascii=False))
        back = gui._saved_options(saved)
        self.assertEqual(back, opts)

    def run_cli(self, *args, **kw) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, os.path.join(REPO, "main.py"), *args, "--ui-lang", "en", "-y"],
                              capture_output=True, stdin=subprocess.DEVNULL, cwd=self.tmp, **kw)

    def test_encoding_names_are_accepted_case_insensitively(self):
        p = self.write("enc.txt", "제1장\n\n본문.\n", "cp949")
        for name in ("EUC-KR", "euc_kr", "CP949", "ms949", "UHC"):
            with self.subTest(name=name):
                for old in os.listdir(self.tmp):
                    if old.endswith(".epub"):
                        os.remove(os.path.join(self.tmp, old))
                r = self.run_cli(p, "--encoding", name)
                self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
                self.assertIn("본문.", book_text(p[:-4] + ".epub")[1])

    def test_console_output_survives_cjk_file_names_on_cp949_console(self):
        p = self.write("日本語 ファイル 中文.txt", "第1章\n\n本文。\n", "utf-8")
        env = dict(os.environ, PYTHONIOENCODING="cp949", PYTHONLEGACYWINDOWSSTDIO="1")
        r = self.run_cli(p, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"Done: 1 EPUB", r.stdout)
        self.assertTrue(os.path.exists(p[:-4] + ".epub"))

    def test_folder_without_txt_and_unwritable_output(self):
        os.mkdir(os.path.join(self.tmp, "nothing"))
        r = self.run_cli(os.path.join(self.tmp, "nothing"))
        self.assertEqual(r.returncode, 2)
        if sys.platform != "win32":
            return
        locked = os.path.join(self.tmp, "locked")
        os.mkdir(locked)
        p = os.path.join(locked, "in.txt")
        open(p, "w", encoding="utf-8").write("제1장\n\n본문.\n")
        user = os.environ.get("USERNAME", "")
        deny = subprocess.run(["icacls", locked, "/deny", f"{user}:(W)"], capture_output=True)
        if deny.returncode != 0:
            self.skipTest("icacls unavailable")
        try:
            r = self.run_cli(p)
        finally:
            subprocess.run(["icacls", locked, "/remove:d", user], capture_output=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(b"Failed, skipping: in.txt", r.stdout + r.stderr)
        self.assertEqual([n for n in os.listdir(locked) if n != "in.txt"], [])


if __name__ == "__main__":
    unittest.main()
