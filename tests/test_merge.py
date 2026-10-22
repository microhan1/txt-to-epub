"""v0.2.0 "one book": several TXT files -> one EPUB, one chapter per file.

Natural order of file names, chapter titles from file names, the default book
title, the merged result, the CLI --merge path, the GUI mode switch, cancel,
and the output-name lock that made
test_two_conversions_of_the_same_file_at_once_produce_two_files flaky.
"""
from __future__ import annotations

import io
import json
import os
import sys
import threading
import time
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import chapters as chap  # noqa: E402
import epub_build as core  # noqa: E402
import i18n  # noqa: E402
import main as cli  # noqa: E402
import prefs as prefs_mod  # noqa: E402
from test_cases import Book, epubcheck_errors  # noqa: E402

BOOK = "나혼자만레벨업"
EPISODES = (  # (file name, text, encoding): the usual web-novel folder, encodings mixed
    (BOOK + "_001화_각성.txt", "001화 각성\n\n첫 회차 본문입니다.\n둘째 줄.\n\n둘째 문단.\n", "utf-8"),
    (BOOK + "_002화_던전.txt", "제2화 던전\n\n둘째 회차 본문.\n", "cp949"),
    (BOOK + "_010화_귀환.txt", "열 번째 회차.\n그냥 본문.\n", "utf-8"),
)


def write(folder, name: str, text: str, encoding: str = "utf-8") -> str:
    p = os.path.join(str(folder), name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(text.encode(encoding))
    return p


def episodes(folder) -> list[str]:
    return [write(folder, name, text, enc) for name, text, enc in EPISODES]


def load_all(paths: list[str]) -> list[core.Loaded]:
    return [core.load_text(p) for p in paths]


def checked(path: str) -> Book:
    assert epubcheck_errors(path) == []
    return Book(path)


# ---------------------------------------------------------------- 4-3 natural order

def test_numbers_in_names_compare_as_numbers():
    names = [os.path.join("x", n) for n in ("10화.txt", "2화.txt", "1화.txt")]
    assert [os.path.basename(p) for p in core.sort_natural(names)] == ["1화.txt", "2화.txt", "10화.txt"]


def test_nested_numbers_compare_part_by_part():
    names = [os.path.join("x", n) for n in ("제1-10화.txt", "제1-2화.txt", "제2-1화.txt")]
    assert [os.path.basename(p) for p in core.sort_natural(names)] == ["제1-2화.txt", "제1-10화.txt", "제2-1화.txt"]


def test_names_without_numbers_sort_by_name_ignoring_case():
    names = [os.path.join("x", n) for n in ("b.txt", "C.txt", "a.txt")]
    assert [os.path.basename(p) for p in core.sort_natural(names)] == ["a.txt", "b.txt", "C.txt"]


def test_same_name_in_two_folders_is_kept_twice_in_folder_order(tmp_path):
    a = write(tmp_path / "2권", "1화.txt", "a")
    b = write(tmp_path / "10권", "1화.txt", "b")
    c = write(tmp_path / "2권", "2화.txt", "c")
    assert core.sort_natural([b, c, a]) == [a, c, b]
    assert core.sort_natural(core.collect_txts([str(tmp_path)])) == [a, c, b]


# ---------------------------------------------------------------- 4-4 chapter titles

def test_chapter_title_drops_the_book_title_and_separators():
    title, start = core.chapter_title_for("x/" + BOOK + "_001화_각성.txt", BOOK, ["그냥 본문 문장입니다.", "본문"], "1화")
    assert (title, start) == ("001화 각성", 0)
    assert core.chapter_title_for("x/" + BOOK + " - 03.txt", BOOK, ["본문"], "3화") == ("03", 0)
    assert core.chapter_title_for("x/Book.ch4.txt", "Book", ["body"], "Chapter 4") == ("ch4", 0)


def test_first_line_equal_to_the_title_is_used_once():
    lines = ["", "001화 각성", "", "본문"]
    assert core.chapter_title_for("x/" + BOOK + "_001화_각성.txt", BOOK, lines, "1화") == ("001화 각성", 2)
    lines = ["001화_각성", "본문"]  # same ignoring separators
    assert core.chapter_title_for("x/" + BOOK + "_001화_각성.txt", BOOK, lines, "1화") == ("001화_각성", 1)


def test_first_line_matching_the_default_pattern_becomes_the_title():
    assert core.chapter_title_for("x/" + BOOK + "_001화_각성.txt", BOOK, ["제1화 각성", "본문"], "1화") == ("제1화 각성", 1)
    assert core.chapter_title_for("x/Book_7.txt", "Book", ["Chapter 7. Home", "text"], "x") == ("Chapter 7. Home", 1)


def test_long_or_plain_first_line_stays_in_the_body():
    long_heading = "제1화 " + "가" * chap.MAX_HEADING_CHARS
    assert core.chapter_title_for("x/" + BOOK + "_001화.txt", BOOK, [long_heading, "본문"], "1화") == ("001화", 0)
    assert core.chapter_title_for("x/" + BOOK + "_001화.txt", BOOK, ["그는 제1장을 읽었다", "본문"], "1화") == ("001화", 0)


def test_nothing_left_after_the_book_title_uses_the_fallback():
    assert core.chapter_title_for("x/" + BOOK + ".txt", BOOK, ["본문"], "1화") == ("1화", 0)
    assert core.chapter_title_for("x/" + BOOK + "_.txt", BOOK, ["본문"], "2화") == ("2화", 0)
    assert core.chapter_title_for("x/" + BOOK + ".txt", "", ["본문"], "1화") == (BOOK, 0)  # no book title: the name


def test_merge_parts_numbers_the_fallback_by_position(tmp_path):
    paths = [write(tmp_path, f"{BOOK}.txt", "a"), write(tmp_path, f"{BOOK}_.txt", "b")]
    parts = core.merge_parts(load_all(paths), BOOK, lambda n: f"Chapter {n}")
    assert [p.title for p in parts] == ["Chapter 1", "Chapter 2"]
    assert [p.title for p in core.merge_parts(load_all(paths), BOOK)] == ["1", "2"]


# ---------------------------------------------------------------- 4-5 book title default

def test_book_title_is_the_folder_name_for_one_folder(tmp_path):
    folder = tmp_path / "전지적 독자 시점"
    files = episodes(folder)
    assert core.book_title_for([str(folder)], files) == "전지적 독자 시점"
    assert core.book_title_for([str(folder) + os.sep], files) == "전지적 독자 시점"


def test_book_title_is_the_shared_prefix_of_dropped_files(tmp_path):
    files = episodes(tmp_path)
    assert core.book_title_for(files, files) == BOOK
    assert core.common_title_prefix(["Book 01", "Book 02"]) == "Book"
    assert core.common_title_prefix(["Book2_1", "Book2_2"]) == "Book2"
    assert core.common_title_prefix(["abc-def-1", "abc-deg-1"]) == "abc"
    assert core.common_title_prefix(["소설 9화", "소설 10화"]) == "소설"


def test_book_title_falls_back_to_the_first_file(tmp_path):
    files = [write(tmp_path, "1화.txt", "a"), write(tmp_path, "2화.txt", "b")]
    assert core.common_title_prefix(["1화", "2화"]) == ""
    assert core.book_title_for(files, files) == "1화"
    only = [write(tmp_path, "solo.txt", "a")]
    assert core.book_title_for(only, only) == "solo"
    assert core.book_title_for([], []) == ""


def test_safe_file_name():
    assert core.safe_file_name('A: B? <c>/d.. ') == "A B c d"
    assert core.safe_file_name("...") == "book"
    assert core.safe_file_name("x" * 200).endswith("x") and len(core.safe_file_name("x" * 200)) == 120


# ---------------------------------------------------------------- merged result

def test_three_files_with_mixed_encodings_become_one_book(tmp_path):
    folder = tmp_path / BOOK
    files = core.sort_natural(episodes(folder))
    parts = core.merge_parts(load_all(files), BOOK, lambda n: f"{n}화")
    r = core.convert_many(parts, core.Options(), BOOK)
    assert r.output_path == os.path.join(str(folder), BOOK + ".epub")
    assert (r.chapters, r.nav, r.replaced, r.no_chapters, r.text_lang) == (3, 3, 0, False, "ko")
    book = checked(r.output_path)
    assert book.meta("title") == BOOK
    assert book.meta("language") == "ko"
    assert book.nav_labels() == ["001화 각성", "제2화 던전", "010화 귀환"]
    hrefs = book.spine_hrefs()
    assert hrefs == ["ch0001.xhtml", "ch0002.xhtml", "ch0003.xhtml"]
    # the heading used as the title is not printed again; everything else is there, in order
    assert book.paragraphs(hrefs[0]) == ["첫 회차 본문입니다. 둘째 줄.", "둘째 문단."]
    assert book.paragraphs(hrefs[1]) == ["둘째 회차 본문."]
    assert book.paragraphs(hrefs[2]) == ["열 번째 회차.", "그냥 본문."]  # no blank lines: one paragraph per line
    assert [book.heading(h) for h in hrefs] == book.nav_labels()
    assert all(book.doc(h).find(".//{http://www.w3.org/1999/xhtml}h2") is not None for h in hrefs)


def test_parts_can_be_left_out_and_renamed(tmp_path):
    files = core.sort_natural(episodes(tmp_path))
    parts = core.merge_parts(load_all(files), BOOK)
    parts[0].title = "Awakening"
    r = core.convert_many([parts[0], parts[2]], core.Options(), BOOK)
    assert Book(r.output_path).nav_labels() == ["Awakening", "010화 귀환"]


def test_one_file_alone_is_still_one_book(tmp_path):
    p = write(tmp_path, BOOK + ".txt", "제1장 시작\n\n본문.\n\n제2장 끝\n\n본문 2.\n")
    parts = core.merge_parts(load_all([p]), BOOK, lambda n: f"{n}화")
    r = core.convert_many(parts, core.Options(), BOOK)
    book = checked(r.output_path)
    # one file = one chapter: the pattern is not applied inside the file; its first
    # line is a heading, so it is the chapter title and not printed twice
    assert book.nav_labels() == ["제1장 시작"]
    assert book.all_paragraphs() == ["본문.", "제2장 끝", "본문 2."]
    p2 = write(tmp_path, "plain.txt", "그냥 본문.\n")
    r2 = core.convert_many(core.merge_parts(load_all([p2]), "plain", lambda n: f"{n}화"), core.Options(), "plain")
    assert Book(r2.output_path).nav_labels() == ["1화"]


def test_paragraph_mode_auto_is_decided_per_file_and_language_once(tmp_path):
    blank = write(tmp_path, "b_1.txt", "첫 문단\n이어서\n\n둘째 문단\n")
    lines = write(tmp_path, "b_2.txt", "\n".join(f"대사 {i}" for i in range(60)) + "\n")
    english = write(tmp_path, "b_3.txt", "Just English here.\n")
    parts = core.merge_parts(load_all([blank, lines, english]), "b")
    r = core.convert_many(parts, core.Options(), "b")
    book = Book(r.output_path)
    assert len(book.paragraphs("ch0001.xhtml")) == 2
    assert len(book.paragraphs("ch0002.xhtml")) == 60
    assert book.meta("language") == "ko"
    r2 = core.convert_many(parts, core.Options(text_lang="en", paragraph_mode="line"), "b")
    book2 = Book(r2.output_path)
    assert book2.meta("language") == "en"
    assert len(book2.paragraphs("ch0001.xhtml")) == 3


def test_replaced_characters_are_summed_and_the_title_shapes_the_file_name(tmp_path):
    a = write(tmp_path, "t_1.txt", "가나".encode("cp949").decode("latin-1") + "\n", "latin-1")
    b = write(tmp_path, "t_2.txt", "다라\n", "cp949")
    loadeds = [core.load_text(a, "utf-8"), core.load_text(b, "utf-8")]
    assert loadeds[0].replaced and loadeds[1].replaced
    r = core.convert_many(core.merge_parts(loadeds, "t"), core.Options(), 'Q: "A/B"')
    assert r.replaced == loadeds[0].replaced + loadeds[1].replaced
    assert os.path.basename(r.output_path) == "Q A B.epub"
    assert Book(r.output_path).meta("title") == 'Q: "A/B"'


def test_output_name_counts_up_and_output_path_wins(tmp_path):
    files = episodes(tmp_path)
    parts = core.merge_parts(load_all(files), BOOK)
    first = core.convert_many(parts, core.Options(), "book").output_path
    second = core.convert_many(parts, core.Options(), "book").output_path
    assert [os.path.basename(p) for p in (first, second)] == ["book.epub", "book(2).epub"]
    out = os.path.join(str(tmp_path), "sub", "x.epub")
    os.mkdir(os.path.dirname(out))
    assert core.convert_many(parts, core.Options(), "book", out).output_path == out


def test_cover_and_style_apply_once_to_the_book(tmp_path):
    parts = core.merge_parts(load_all(episodes(tmp_path)), BOOK)
    r = core.convert_many(parts, core.Options(cover_mode="auto", author="작가", publisher="출판사", line_height="1.6"), BOOK)
    book = checked(r.output_path)
    assert "OEBPS/images/cover.jpg" in book.z.namelist()
    assert book.z.namelist().count("OEBPS/cover.xhtml") == 1
    assert (book.meta("creator"), book.meta("publisher")) == ("작가", "출판사")
    assert "line-height: 1.6;" in book.z.read("OEBPS/style.css").decode()


def test_empty_parts_is_an_error():
    with pytest.raises(ValueError):
        core.convert_many([], core.Options(), "x")


# ---------------------------------------------------------------- 4-7 cancel

def test_cancel_while_reading_the_second_file_leaves_no_output(tmp_path):
    parts = core.merge_parts(load_all(episodes(tmp_path)), BOOK)
    ev = threading.Event()
    seen = []

    def progress(phase, i, n, name):
        seen.append((phase, i))
        if phase == "read" and i == 2:
            ev.set()

    with pytest.raises(core.Cancelled):
        core.convert_many(parts, core.Options(), BOOK, progress=progress, cancel=ev)
    assert seen == [("read", 1), ("read", 2)]
    assert [n for n in os.listdir(tmp_path) if n.endswith((".epub", ".part"))] == []


def test_cancel_before_writing_leaves_no_output(tmp_path):
    parts = core.merge_parts(load_all(episodes(tmp_path)), BOOK)
    ev = threading.Event()

    def progress(phase, i, n, name):
        if phase == "write":
            ev.set()

    with pytest.raises(core.Cancelled):
        core.convert_many(parts, core.Options(), BOOK, progress=progress, cancel=ev)
    assert [n for n in os.listdir(tmp_path) if n.endswith((".epub", ".part"))] == []


# ---------------------------------------------------------------- CLI

def run_cli(*argv) -> tuple[int, str]:
    buf = io.StringIO()
    old_out, old_err, old_in = sys.stdout, sys.stderr, sys.stdin
    sys.stdout = sys.stderr = buf
    sys.stdin = io.StringIO()
    try:
        code = cli.main(list(argv) + ["--ui-lang", "en"])
    finally:
        sys.stdout, sys.stderr, sys.stdin = old_out, old_err, old_in
    return code, buf.getvalue()


def test_cli_merge_folder_makes_one_epub_named_after_the_folder(tmp_path):
    folder = tmp_path / BOOK
    episodes(folder)
    code, out = run_cli(str(folder), "--merge", "-y")
    assert code == 0, out
    assert "Title: " + BOOK in out
    assert "3 files → 1 book, 3 chapters" in out
    assert "Done: 1 EPUB" in out
    book = checked(os.path.join(str(folder), BOOK + ".epub"))
    assert book.nav_labels() == ["001화 각성", "제2화 던전", "010화 귀환"]
    assert [n for n in os.listdir(folder) if n.endswith(".epub")] == [BOOK + ".epub"]


def test_cli_merge_output_title_and_ignored_pattern_options(tmp_path):
    files = episodes(tmp_path)
    out_path = os.path.join(str(tmp_path), "book.epub")
    code, out = run_cli(*files, "--merge", "--output", out_path, "--title", "My Book", "--chapter-pattern", "^x",
                        "--no-chapters", "--author", "Me", "-y")
    assert code == 0, out
    assert "--chapter-pattern and --no-chapters are ignored with --merge" in out
    assert "Title: My Book" in out
    book = checked(out_path)
    assert (book.meta("title"), book.meta("creator")) == ("My Book", "Me")
    assert book.nav_labels() == ["001화 각성", "제2화 던전", "010화 귀환"]
    code, out = run_cli(*files, "--merge", "-y")
    assert code == 0 and "ignored" not in out
    assert os.path.exists(os.path.join(str(tmp_path), BOOK + ".epub"))  # shared prefix of dropped files


def test_cli_merge_skips_an_empty_file_and_fails_when_nothing_is_left(tmp_path):
    folder = tmp_path / "series"
    episodes(folder)
    write(folder, BOOK + "_003화.txt", "")
    code, out = run_cli(str(folder), "--merge", "-y")
    assert code == 1, out
    assert "The file is empty" in out
    assert "3 files → 1 book, 3 chapters" in out
    assert Book(os.path.join(str(folder), "series.epub")).nav_labels() == ["001화 각성", "제2화 던전", "010화 귀환"]
    only = tmp_path / "empty"
    write(only, "a.txt", "")
    write(only, "b.txt", " \n")
    code, out = run_cli(str(only), "--merge", "-y")
    assert code == 2
    assert "None of the files could be read" in out
    assert [n for n in os.listdir(only) if n.endswith(".epub")] == []


def test_cli_merge_option_is_in_every_help_text():
    for lang in i18n.LANGS:
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            with pytest.raises(SystemExit):
                cli.main(["--help", "--ui-lang", lang])
        finally:
            sys.stdout = old
        assert "--merge" in buf.getvalue() and "--output FILE" in buf.getvalue()


def test_language_files_all_carry_the_new_keys():
    en = json.load(open(os.path.join(ROOT, "lang", "en.json"), encoding="utf-8"))
    new = ("merge_each", "merge_one", "btn_up", "btn_down", "lbl_order", "col_file", "merge_count", "merge_hint",
           "merge_chapter_n", "log_merged", "status_reading", "status_writing", "cli_merge", "cli_output",
           "cli_merge_title", "warn_merge_ignores_pattern", "err_merge_none")
    for lang in i18n.LANGS:
        strings = json.load(open(os.path.join(ROOT, "lang", f"{lang}.json"), encoding="utf-8"))
        assert set(strings) == set(en), lang
        for key in new:
            assert strings[key].strip(), (lang, key)


# ---------------------------------------------------------------- prefs

def test_merge_mode_pref_is_type_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    for raw, expected in (('{"merge_mode": "one"}', "one"), ('{"merge_mode": "each"}', "each"),
                          ('{"merge_mode": "both"}', "each"), ('{"merge_mode": 1}', "each"), ("{}", "each")):
        open(i18n.SETTINGS_PATH, "w", encoding="utf-8").write(raw)
        assert prefs_mod.load().merge_mode == expected, raw
    prefs_mod.save(prefs_mod.Prefs(merge_mode="one"))
    assert json.load(open(i18n.SETTINGS_PATH, encoding="utf-8"))["merge_mode"] == "one"


# ---------------------------------------------------------------- GUI

@pytest.fixture
def app(tmp_path, monkeypatch):
    """A real window, withdrawn; nothing is written to the user's settings.json."""
    import gui

    monkeypatch.setattr(i18n, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    saved: dict = {}
    monkeypatch.setattr(i18n, "save_settings", lambda data: saved.update(data))
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(gui.update_check, "check_async", lambda *a, **k: None)
    before = i18n.current_lang()
    i18n.set_lang("en", persist=False)
    a = gui.App()
    a.saved = saved
    a.root.withdraw()
    try:
        yield a
    finally:
        a._closing = True
        a.cancel_event.set()
        wait_worker(a)
        a.root.destroy()
        i18n.set_lang(before, persist=False)


def run_until(a, cond, timeout: float = 30) -> None:
    """Run the real event loop until cond() holds. The worker threads hand their
    results over with root.after(), which Tk only accepts while the main thread
    is inside mainloop(); a root.update() loop is not enough."""
    deadline = time.time() + timeout

    def poll() -> None:
        if cond() or time.time() > deadline:
            a.root.quit()
        else:
            a.root.after(20, poll)

    a.root.after(0, poll)
    a.root.mainloop()
    a.root.after(30, a.root.quit)  # one more turn for the callbacks the condition left queued
    a.root.mainloop()
    assert cond(), "timed out"


def pump(a, times: int = 1) -> None:
    run_until(a, lambda: True)


def wait_loaded(a, timeout: float = 15) -> None:
    run_until(a, lambda: bool(a.files) and not any(f.loading for f in a.files), timeout)


def wait_worker(a, timeout: float = 30) -> None:
    run_until(a, lambda: not (a.worker and a.worker.is_alive()), timeout)


def test_gui_mode_switch_changes_the_panels_and_is_remembered(app, tmp_path):
    folder = tmp_path / "전지적 독자 시점"
    episodes(folder)
    app.add_paths([str(folder)])
    wait_loaded(app)
    assert not app.merging()
    assert app.btn_up.instate(["disabled"]) and app.chk_split.instate(["!disabled"])
    assert app.var_title.get() == BOOK + "_010화_귀환"  # per file: the last added file's own title
    app.var_merge.set("one")
    app._on_merge_mode()
    assert app.saved["merge_mode"] == "one" and app.options().merge
    assert app.btn_up.instate(["!disabled"]) and app.chk_split.instate(["disabled"])
    assert str(app.cmb_pattern["state"]) == "disabled"
    assert app.var_title.get() == "전지적 독자 시점"
    rows = app.tree.get_children()
    assert [app.tree.set(r, "title") for r in rows] == ["001화 각성", "제2화 던전", "010화 귀환"]
    assert [app.tree.set(r, "line") for r in rows] == [n for n, _, _ in EPISODES]
    assert [app.tree.set(r, "on") for r in rows] == [gui_check()] * 3
    assert app.tree.heading("line")["text"] == "File"
    assert "one book" in app.lbl_chapter_count.cget("text")
    app.var_merge.set("each")
    app._on_merge_mode()
    assert app.saved["merge_mode"] == "each" and not app.options().merge
    assert app.chk_split.instate(["!disabled"]) and app.btn_up.instate(["disabled"])
    assert app.tree.heading("line")["text"] == "Start line"
    assert app.var_title.get() == BOOK + "_010화_귀환"


def gui_check() -> str:
    import gui

    return gui.CHECK


def test_gui_order_titles_ticks_and_one_epub(app, tmp_path):
    folder = tmp_path / BOOK
    episodes(folder)
    app.var_merge.set("one")
    app._on_merge_mode()
    app.add_paths([str(folder)])
    wait_loaded(app)
    assert [f.name for f in app.files] == [n for n, _, _ in EPISODES]  # natural order: 001, 002, 010
    app._select_index(2)
    app.move_selected(-1)  # 010 before 002
    assert [f.name for f in app.files][1] == EPISODES[2][0]
    assert app.lst_files.get(1) == EPISODES[2][0] and app.lst_files.curselection() == (1,)
    app.set_chapter_title(0, "Awakening")
    app._toggle("F2")  # leave 002 out
    rows = app.tree.get_children()
    assert [app.tree.set(r, "title") for r in rows] == ["Awakening", "010화 귀환", "제2화 던전"]
    assert [app.tree.set(r, "on") for r in rows] == [gui_check(), gui_check(), ""]
    app.var_title.set("My Book")
    app.run()
    wait_worker(app)
    assert len(app.outputs) == 1
    book = checked(app.outputs[0])
    assert os.path.basename(app.outputs[0]) == "My Book.epub"
    assert os.path.dirname(app.outputs[0]) == str(folder)
    assert book.meta("title") == "My Book"
    assert book.nav_labels() == ["Awakening", "010화 귀환"]
    log = app.txt_log.get("1.0", "end")
    assert "2 files → 1 book, 2 chapters" in log and "Saved:" in log
    assert app.lbl_status.cget("text") == "Done"
    assert app.saved["options"]["merge"] is True
    # back to one EPUB per file: the three files, each on its own
    app.var_merge.set("each")
    app._on_merge_mode()
    app.run()
    wait_worker(app)
    assert len(app.outputs) == 3


def test_gui_one_book_skips_a_file_that_failed_to_load(app, tmp_path):
    episodes(tmp_path)
    app.var_merge.set("one")
    app._on_merge_mode()
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    app.files[1].loaded = None
    app.files[1].error = "err_decode_failed"
    app._refresh_tree()
    assert len(app.tree.get_children()) == 2
    app.run()
    wait_worker(app)
    assert len(app.outputs) == 1
    assert Book(app.outputs[0]).nav_labels() == ["001화 각성", "010화 귀환"]
    assert "Skipped: " + EPISODES[1][0] in app.txt_log.get("1.0", "end")


def test_gui_cancel_during_one_book_leaves_no_file(app, tmp_path, monkeypatch):
    episodes(tmp_path)
    app.var_merge.set("one")
    app._on_merge_mode()
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    real = core.convert_many

    def slow(parts, opts, title, output_path=None, progress=None, cancel=None):
        def spy(phase, i, n, name):
            if progress:
                progress(phase, i, n, name)
            if phase == "read" and i == 2:
                app.cancel_event.set()
        return real(parts, opts, title, output_path, spy, cancel)

    monkeypatch.setattr(core, "convert_many", slow)
    app.run()
    wait_worker(app)
    assert app.outputs == []
    assert [n for n in os.listdir(tmp_path) if n.endswith((".epub", ".part"))] == []
    assert app.lbl_status.cget("text") == "Cancelled"
    assert "Cancelled: " in app.txt_log.get("1.0", "end")


# ---------------------------------------------------------------- the output-name race, now serialized

def test_parallel_conversions_into_one_folder_never_collide(tmp_path):
    """Before the lock, os.replace onto the reserved name failed with WinError 5
    about once in a hundred runs (another thread's lexists held the file).
    Many short rounds make that window show up in one test run."""
    p = write(tmp_path, "same.txt", "제1장\n\n" + "본문 " * 200 + "\n")
    for _ in range(12):
        results, errors = [], []

        def work():
            try:
                results.append(core.convert_file(p, core.Options()).output_path)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=work) for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert errors == []
        assert len(set(results)) == 6
        for out in results:
            os.remove(out)
    assert [n for n in os.listdir(tmp_path) if ".part" in n] == []


def test_reserve_and_replace_run_under_the_lock(tmp_path, monkeypatch):
    seen = []
    real = core._reserve_output

    def spying(path):
        seen.append(core._output_lock.locked())
        return real(path)

    monkeypatch.setattr(core, "_reserve_output", spying)
    core.convert_file(write(tmp_path, "l.txt", "x\n"), core.Options())
    assert seen == [True]
