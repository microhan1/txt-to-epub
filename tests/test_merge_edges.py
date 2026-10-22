"""Second, careful pass over "one book" (v0.2.0): odd file names, odd first lines,
odd titles, output-name corner cases, many files, the GUI in states the first
pass did not cover (startup in one-book mode, language switch, tree/list sync,
remove, inline title entry, confirmations), and the fixed output-name race run
through the original flaky test many times.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk
import unittest
from tkinter import ttk

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import chapters as chap  # noqa: E402
import epub_build as core  # noqa: E402
import i18n  # noqa: E402
import prefs as prefs_mod  # noqa: E402
from test_cases import Book  # noqa: E402
from test_merge import (BOOK, EPISODES, app, checked, episodes, load_all, run_cli, run_until,  # noqa: E402,F401
                        wait_loaded, wait_worker, write)

CHECK = chr(0x2714)


def names(paths):
    return [os.path.basename(p) for p in paths]


# ---------------------------------------------------------------- file names

def test_odd_file_names_still_order_by_number():
    paths = [os.path.join("x", n) for n in ("ch10.txt", "Ch2.txt", "1.10x.txt", "1.5x.txt", "1x.txt", "001x.txt",
                                            chr(0xFF11) + chr(0xFF10) + "x.txt", " 3x.txt", "-2.txt", "a.txt")]
    order = names(core.sort_natural(paths))
    pos = {n: i for i, n in enumerate(order)}
    assert pos["1.5x.txt"] < pos["1.10x.txt"]                      # 5 < 10 inside a dotted number
    assert pos["Ch2.txt"] < pos["ch10.txt"]                        # case does not matter
    assert pos["1x.txt"] < pos[" 3x.txt"] < pos[chr(0xFF11) + chr(0xFF10) + "x.txt"]  # 1 < 3 < full-width 10
    assert abs(pos["001x.txt"] - pos["1x.txt"]) == 1               # same number: side by side, stable
    assert pos["-2.txt"] < pos["a.txt"]
    assert core.sort_natural(paths) == core.sort_natural(list(reversed(paths)))  # input order never matters


def test_huge_numbers_and_numbers_only_names():
    paths = [os.path.join("x", n) for n in ("99999999999999999999.txt", "100000000000000000000.txt", "7.txt")]
    assert names(core.sort_natural(paths)) == ["7.txt", "99999999999999999999.txt", "100000000000000000000.txt"]


def test_subfolders_order_by_folder_number_then_file(tmp_path):
    paths = [write(tmp_path / f"{v}권", f"{n}화.txt", "x") for v in (10, 2, 1) for n in (10, 2, 1)]
    ordered = core.sort_natural(paths)
    assert [os.path.relpath(p, tmp_path) for p in ordered] == [
        os.path.join(f"{v}권", f"{n}화.txt") for v in (1, 2, 10) for n in (1, 2, 10)]
    assert core.book_title_for([str(tmp_path)], ordered) == tmp_path.name
    parts = core.merge_parts(load_all(ordered), tmp_path.name, lambda n: f"{n}화")
    # the names share nothing, the folder name is not a prefix: the file names are the titles
    assert [p.title for p in parts][:3] == ["1화", "2화", "10화"]


# ---------------------------------------------------------------- chapter titles

@pytest.mark.parametrize("stem,prefix,expected", [
    ("Book_001", "Book", "001"),
    ("book_001", "Book", "001"),                     # case-insensitive prefix
    ("Book - 001 - Intro", "Book", "001 - Intro"),
    ("Book__001__a", "Book", "001 a"),               # doubled separators collapse
    ("Book.001.a", "Book", "001.a"),                 # dots inside stay (they may be part of a title)
    ("Bookworm_001", "Book", "worm 001"),            # a prefix that stops inside a word still comes off
    ("Book", "Book", "FALLBACK"),
    ("Book___", "Book", "FALLBACK"),
    ("_ _ . -", "Book", "FALLBACK"),
    ("Book_001", "", "Book 001"),                    # no prefix at all
    ("제1-2화", "", "제1-2화"),
])
def test_title_from_name(stem, prefix, expected):
    assert core.chapter_title_for(f"x/{stem}.txt", prefix, ["body"], "FALLBACK") == (expected, 0)


@pytest.mark.parametrize("first,expected", [
    ("001 Intro", ("001 Intro", 3)),                 # equal: the body starts after it (two blank lines before it)
    ("  001   Intro  ", ("001   Intro", 3)),         # equal ignoring spaces; the line is kept as typed, trimmed
    ("001-Intro", ("001-Intro", 3)),                 # equal ignoring separators
    ("001 intro", ("001 intro", 3)),                 # equal ignoring case
    ("Chapter 1", ("Chapter 1", 3)),                 # a heading by the default pattern
    ("1.", ("1.", 3)),
    ("프롤로그", ("프롤로그", 3)),
    ("Book 001 Intro", ("001 Intro", 3)),            # the whole file name: dropped, short title kept
    ("book_001_intro", ("001 Intro", 3)),
    ("001 Intro and more words", ("001 Intro", 0)),  # neither equal nor a heading: body
    ("He read chapter 1 twice.", ("001 Intro", 0)),
    ("Chapter 1 " + "x" * chap.MAX_HEADING_CHARS, ("001 Intro", 0)),  # too long for a heading
    ("<b>001 & Intro</b>", ("001 Intro", 0)),
])
def test_first_line_rules(first, expected):
    lines = ["", "   ", first, "", "body"]
    assert core.chapter_title_for("x/Book_001_Intro.txt", "Book", lines, "F") == expected


def test_special_characters_in_titles_survive_into_the_epub(tmp_path):
    a = write(tmp_path, "A&B_001 'x'.txt", "A&B 001 'x'\n\n\"quoted\" & <single>\n")
    b = write(tmp_path, "A&B_002.txt", "plain\n")
    parts = core.merge_parts(load_all([a, b]), 'T & "Q"')
    assert [(p.title, p.body_start) for p in parts] == [("001 'x'", 1), ("002", 0)]  # line = whole file name: dropped
    r = core.convert_many(parts, core.Options(), 'T & "Q" <br/>')
    book = checked(r.output_path)
    assert book.meta("title") == 'T & "Q" <br/>'
    assert book.nav_labels() == ["001 'x'", "002"]
    assert book.paragraphs("ch0001.xhtml") == ["\"quoted\" & <single>"]
    assert os.path.basename(r.output_path) == "T & Q br.epub"


def test_heading_only_file_and_blank_lines_around(tmp_path):
    a = write(tmp_path, "s_1.txt", "\n\n제1화 제목만\n\n\n")
    b = write(tmp_path, "s_2.txt", "\n본문만 있고 제목 줄은 없음\n")
    parts = core.merge_parts(load_all([a, b]), "s", lambda n: f"{n}화")
    assert [(p.title, p.body_start) for p in parts] == [("제1화 제목만", 3), ("2", 0)]  # "s_2" minus "s"
    r = core.convert_many(parts, core.Options(), "s")
    book = checked(r.output_path)
    assert book.nav_labels() == ["제1화 제목만", "2"]
    assert book.paragraphs("ch0001.xhtml") == []
    assert book.paragraphs("ch0002.xhtml") == ["본문만 있고 제목 줄은 없음"]


def test_bom_crlf_and_old_dos_eof_do_not_disturb_the_first_line(tmp_path):
    a = write(tmp_path, "s_1.txt", "﻿제1화 시작\r\n\r\n본문\r\n\x1a", "utf-8")
    parts = core.merge_parts(load_all([a]), "s")
    assert (parts[0].title, parts[0].body_start) == ("제1화 시작", 1)
    assert parts[0].loaded.lines[-1] == "" and "\x1a" not in "".join(parts[0].loaded.lines)


def test_user_titles_are_kept_even_when_empty_strings_are_avoided(tmp_path):
    parts = core.merge_parts(load_all(episodes(tmp_path)), BOOK)
    parts[1].title = "   "  # blank title: the book title stands in, the EPUB stays valid
    r = core.convert_many(parts, core.Options(), BOOK)
    assert Book(r.output_path).nav_labels()[1] == BOOK


# ---------------------------------------------------------------- book title and output name

def test_book_title_edge_inputs(tmp_path):
    files = episodes(tmp_path / "f")
    assert core.book_title_for([str(tmp_path / "f") + "/"], files) == "f"       # trailing slash
    assert core.book_title_for([str(tmp_path / "f"), files[0]], files) == BOOK  # folder plus a file: not "one folder"
    assert core.book_title_for([files[0]], files[:1]) == BOOK + "_001화_각성"
    long_dir = tmp_path / ("가" * 200)  # near the longest name Windows allows
    long_files = episodes(long_dir)
    assert core.book_title_for([str(long_dir)], long_files) == "가" * 200


@pytest.mark.parametrize("title,expected", [
    ("CON", "CON_"), ("com1", "com1_"), ("nul.", "nul_"), ("Console", "Console"),
    ("  spaced   out  ", "spaced out"), ("tab\there", "tab here"), ("a" * 300, "a" * 120),
    ("제목: 부제?", "제목 부제"), ("\\\\server\\share", "server share"),
])
def test_safe_file_name_edges(title, expected):
    assert core.safe_file_name(title) == expected


def test_output_name_when_a_folder_or_a_numbered_file_holds_the_name(tmp_path):
    parts = core.merge_parts(load_all(episodes(tmp_path)), BOOK)
    os.mkdir(os.path.join(tmp_path, "t.epub"))
    write(tmp_path, "t(2).epub", "x")
    r = core.convert_many(parts, core.Options(), "t")
    assert os.path.basename(r.output_path) == "t(3).epub"
    assert os.path.isdir(os.path.join(tmp_path, "t.epub"))
    assert open(os.path.join(tmp_path, "t(2).epub")).read() == "x"


def test_explicit_output_is_never_overwritten_and_gets_its_extension(tmp_path):
    files = episodes(tmp_path)
    out = os.path.join(str(tmp_path), "mine")
    code, text = run_cli(*files, "--merge", "--output", out, "-y")
    assert code == 0, text
    assert os.path.exists(out + ".epub")
    before = open(out + ".epub", "rb").read()
    code, text = run_cli(*files, "--merge", "--output", out + ".epub", "-y")
    assert code == 0, text
    assert open(out + ".epub", "rb").read() == before
    assert os.path.exists(os.path.join(str(tmp_path), "mine(2).epub"))
    assert "mine(2).epub" in text


def test_output_in_a_missing_folder_fails_cleanly(tmp_path):
    files = episodes(tmp_path)
    code, text = run_cli(*files, "--merge", "--output", os.path.join(str(tmp_path), "nope", "x.epub"), "-y")
    assert code == 1
    assert "Failed, skipping" in text
    assert [n for n in os.listdir(tmp_path) if n.endswith((".epub", ".part"))] == []


def test_cli_many_files_need_a_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "MANY_FILES", 2)
    folder = tmp_path / "many"
    episodes(folder)
    code, text = run_cli(str(folder), "--merge")
    assert code == 1
    assert "3 chapters" in text and "Run again with -y" in text
    assert [n for n in os.listdir(folder) if n.endswith(".epub")] == []
    code, text = run_cli(str(folder), "--merge", "-y")
    assert code == 0, text
    assert Book(os.path.join(str(folder), "many.epub")).nav_labels() == ["001화 각성", "제2화 던전", "010화 귀환"]


def test_cli_merge_with_forced_encoding_cover_and_missing_input(tmp_path):
    from PIL import Image

    files = episodes(tmp_path)
    small = os.path.join(str(tmp_path), "small.png")
    Image.new("RGB", (200, 300), (9, 9, 9)).save(small)
    code, text = run_cli(files[1], files[0], os.path.join(str(tmp_path), "gone.txt"), "--merge", "--encoding", "cp949",
                         "--cover", small, "--lang", "en", "-y")
    assert code == 0, text
    assert "Cannot open file: " in text and "cover image is small" in text
    book = checked(os.path.join(str(tmp_path), BOOK + ".epub"))
    assert book.meta("language") == "en"
    assert "OEBPS/images/cover.png" in book.z.namelist()
    assert book.nav_labels()[1] == "제2화 던전"           # cp949 forced: the EUC-KR file reads right
    assert "undecodable" in text                           # ... and the UTF-8 files report replaced characters


def test_big_chapters_split_but_toc_stays_one_per_file(tmp_path):
    para = "가" * 5000 + "\n\n"
    big = write(tmp_path, "b_1.txt", "제1화 큰 장\n\n" + para * 120)
    small = write(tmp_path, "b_2.txt", "제2화\n\n짧음\n")
    r = core.convert_many(core.merge_parts(load_all([big, small]), "b"), core.Options(), "b")
    assert r.chapters == 2 and r.nav == 2 and r.files > 2
    book = checked(r.output_path)
    assert book.nav_labels() == ["제1화 큰 장", "제2화"]
    assert book.spine_hrefs()[0] == "ch0001.xhtml" and book.spine_hrefs()[-1] == "ch0002.xhtml"
    for n in book.z.namelist():
        if n.startswith("OEBPS/ch"):
            assert len(book.z.read(n)) <= chap.CHAPTER_SPLIT_BYTES + 4096


def test_progress_reports_every_part_then_the_write(tmp_path):
    parts = core.merge_parts(load_all(episodes(tmp_path)), BOOK)
    seen = []
    core.convert_many(parts, core.Options(), BOOK, progress=lambda *a: seen.append(a))
    assert seen == [("read", 1, 3, EPISODES[0][0]), ("read", 2, 3, EPISODES[1][0]), ("read", 3, 3, EPISODES[2][0]),
                    ("write", 3, 3, "")]


def test_options_are_validated_inside_convert_many(tmp_path):
    parts = core.merge_parts(load_all(episodes(tmp_path)), BOOK)
    r = core.convert_many(parts, core.Options(text_lang="xx", line_height="7", paragraph_mode="?", merge="yes"), BOOK)
    book = checked(r.output_path)
    assert book.meta("language") == "ko"
    assert "line-height" not in book.z.read("OEBPS/style.css").decode()


# ---------------------------------------------------------------- GUI, second pass

def test_gui_starts_in_one_book_mode_when_the_settings_say_so(tmp_path, monkeypatch):
    import gui

    monkeypatch.setattr(i18n, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    open(i18n.SETTINGS_PATH, "w", encoding="utf-8").write('{"merge_mode": "one", "lang": "en"}')
    monkeypatch.setattr(i18n, "save_settings", lambda data: None)
    monkeypatch.setattr(gui.update_check, "check_async", lambda *a, **k: None)
    before = i18n.current_lang()
    i18n.set_lang("en", persist=False)
    a = gui.App()
    try:
        a.root.withdraw()
        assert a.merging() and a.var_merge.get() == "one"
        assert a.chk_split.instate(["disabled"]) and a.btn_up.instate(["!disabled"])
        assert a.tree.cget("displaycolumns") == ("on", "no", "title", "line")
        assert a.var_title.get() == ""
    finally:
        a._closing = True
        a.root.destroy()
        i18n.set_lang(before, persist=False)


def test_gui_one_book_with_no_files_and_with_nothing_ticked(app, tmp_path, monkeypatch):
    import gui

    shown = []
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, msg, **k: shown.append(msg))
    app.var_merge.set("one")
    app._on_merge_mode()
    assert app.tree.get_children() == () and app.lbl_chapter_count.cget("text") == ""
    app.run()
    assert shown == ["Add TXT files first"]
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    for iid in app.tree.get_children():
        app._toggle(iid)
    assert [app.tree.set(r, "on") for r in app.tree.get_children()] == ["", "", ""]
    assert "0 files" in app.lbl_chapter_count.cget("text")
    app.run()
    assert shown[-1] == "None of the files could be read"
    assert app.worker is None and app.btn_run.instate(["!disabled"])


def test_gui_many_files_confirmation_declined_runs_nothing(app, tmp_path, monkeypatch):
    import gui

    asked = []
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda title, msg, **k: asked.append(msg) or False)
    monkeypatch.setattr(core, "MANY_FILES", 2)
    app.var_merge.set("one")
    app._on_merge_mode()
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    app.run()
    assert len(asked) == 1 and "3 chapters" in asked[0]
    assert app.worker is None and app.btn_run.instate(["!disabled"]) and app.btn_up.instate(["!disabled"])
    assert [n for n in os.listdir(tmp_path) if n.endswith(".epub")] == []


def test_gui_tree_selection_follows_to_the_file_list_and_preview(app, tmp_path):
    app.var_merge.set("one")
    app._on_merge_mode()
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    app._select_index(0)
    assert app.tree.selection() == ("F0",)
    app.tree.selection_set("F2")
    run_until(app, lambda: app.current is app.files[2])
    assert app.lst_files.curselection() == (2,)
    assert app.txt_preview.get("1.0", "end").startswith("열 번째 회차.")
    assert app.tree.selection() == ("F2",)
    app._jump_preview()  # "preview chapter" on a file row shows that file from its first line
    assert app.txt_preview.get("1.0", "end").startswith("열 번째 회차.")


def test_gui_remove_and_clear_in_one_book_mode(app, tmp_path):
    app.var_merge.set("one")
    app._on_merge_mode()
    folder = tmp_path / "series"
    episodes(folder)
    app.add_paths([str(folder)])
    wait_loaded(app)
    app.set_chapter_title(2, "Last")
    app._toggle("F1")
    app._select_index(0)
    app.remove_selected()
    rows = app.tree.get_children()
    assert rows == ("F0", "F1")
    assert [app.tree.set(r, "title") for r in rows] == ["제2화 던전", "Last"]  # the edits stay with their files
    assert [app.tree.set(r, "on") for r in rows] == ["", CHECK]
    assert app.var_title.get() == "series"
    app.var_title.set("Mine")
    assert app.merge_title_user == "Mine"
    app.clear_files()
    assert app.tree.get_children() == () and app.var_title.get() == "" and app.merge_title_user is None
    assert app.inputs == []


def test_gui_book_title_survives_a_mode_round_trip_and_encoding_change(app, tmp_path):
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    app.var_merge.set("one")
    app._on_merge_mode()
    app.var_title.set("My Title")
    app.var_merge.set("each")
    app._on_merge_mode()
    assert app.var_title.get() == BOOK + "_010화_귀환"
    app.var_title.set("per-file title")
    assert app.files[2].title == "per-file title" and app.merge_title_user == "My Title"
    app.var_merge.set("one")
    app._on_merge_mode()
    assert app.var_title.get() == "My Title"
    # the encoding box re-reads the selected file; the row comes back with the same title and tick
    app._select_index(1)
    app._toggle("F1")
    app.cmb_enc.current(3)  # cp949
    app._on_encoding()
    run_until(app, lambda: not app.files[1].loading)
    assert app.files[1].loaded.encoding == "cp949"
    assert app.tree.set("F1", "on") == "" and app.tree.set("F1", "title") == "제2화 던전"


def test_gui_language_switch_keeps_one_book_headings(app, tmp_path):
    app.var_merge.set("one")
    app._on_merge_mode()
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    app.cmb_lang.current(i18n.LANGS.index("ko"))
    app._on_lang()
    assert i18n.current_lang() == "ko"
    assert app.tree.heading("line")["text"] == "파일"
    assert app.rad_one.cget("text") == "한 권으로" and app.btn_up.cget("text").endswith("위로")
    assert "한 권" in app.lbl_chapter_count.cget("text")
    assert len(app.tree.get_children()) == 3
    app.cmb_lang.current(i18n.LANGS.index("en"))
    app._on_lang()
    assert app.tree.heading("line")["text"] == "File"


def test_gui_inline_title_entry_return_keeps_escape_drops(app, tmp_path):
    app.var_merge.set("one")
    app._on_merge_mode()
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    app.root.deiconify()  # bbox() needs a mapped, drawn tree: give the window a moment on screen
    end = time.time() + 1.0
    run_until(app, lambda: time.time() > end)
    assert app.tree.bbox("F0", "title")

    def entry() -> ttk.Entry:
        ents = [w for w in app.tree.winfo_children() if isinstance(w, ttk.Entry)]
        assert len(ents) == 1
        # a test window is not the active application, so focus_set() in _edit_title does not
        # take the keyboard; the key event goes to the focus window, so take it by force here
        ents[0].focus_force()
        pause = time.time() + 0.3
        run_until(app, lambda: time.time() > pause)
        assert app.root.focus_get() is ents[0]
        return ents[0]

    app._edit_title("F0")
    e = entry()
    assert e.get() == "001화 각성"
    e.delete(0, "end")
    e.insert(0, "Awake")
    e.event_generate("<Return>")
    run_until(app, lambda: not app.tree.winfo_children())
    assert app.tree.set("F0", "title") == "Awake" and app.files[0].merge_title == "Awake"
    app._edit_title("F1")
    e = entry()
    e.delete(0, "end")
    e.insert(0, "dropped")
    e.event_generate("<Escape>")
    run_until(app, lambda: not app.tree.winfo_children())
    assert app.tree.set("F1", "title") == "제2화 던전" and app.files[1].merge_title is None
    app._edit_title("F0")
    e = entry()
    e.delete(0, "end")
    e.event_generate("<Return>")  # emptied: back to the name-derived title
    run_until(app, lambda: not app.tree.winfo_children())
    assert app.tree.set("F0", "title") == "001화 각성" and app.files[0].merge_title is None
    app.root.withdraw()


def test_gui_controls_are_locked_while_the_book_is_written(app, tmp_path, monkeypatch):
    app.var_merge.set("one")
    app._on_merge_mode()
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    gate = threading.Event()
    real = core.convert_many
    states = {}

    def slow(parts, opts, title, output_path=None, progress=None, cancel=None):
        gate.wait(10)
        return real(parts, opts, title, output_path, progress, cancel)

    monkeypatch.setattr(core, "convert_many", slow)
    app.run()
    for name in ("btn_run", "btn_up", "btn_down", "rad_one", "rad_each", "btn_add"):
        states[name] = getattr(app, name).instate(["disabled"])
    assert all(states.values()), states
    assert app.btn_cancel.instate(["!disabled"])
    app.move_selected(1)  # ignored while running
    assert [f.name for f in app.files] == [n for n, _, _ in EPISODES]
    gate.set()
    wait_worker(app)
    assert app.btn_run.instate(["!disabled"]) and app.btn_up.instate(["!disabled"]) and app.btn_cancel.instate(["disabled"])
    assert app.btn_open.instate(["!disabled"]) and len(app.outputs) == 1
    assert app.progress["value"] == app.progress["maximum"]


def test_gui_failure_inside_the_build_is_logged_not_raised(app, tmp_path, monkeypatch):
    app.var_merge.set("one")
    app._on_merge_mode()
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(core, "convert_many", boom)
    app.run()
    wait_worker(app)
    log = app.txt_log.get("1.0", "end")
    assert "Failed, skipping: " in log and "disk full" in log
    assert app.outputs == [] and app.btn_open.instate(["disabled"]) and app.btn_run.instate(["!disabled"])


def test_gui_merge_pref_is_saved_with_the_options_on_run(app, tmp_path):
    app.var_merge.set("one")
    app._on_merge_mode()
    episodes(tmp_path)
    app.add_paths([str(tmp_path)])
    wait_loaded(app)
    app.run()
    wait_worker(app)
    assert app.saved["merge_mode"] == "one" and app.saved["options"]["merge"] is True
    loaded = prefs_mod.load.__wrapped__ if hasattr(prefs_mod.load, "__wrapped__") else None
    assert loaded is None  # (no decorator games: plain function)


# ---------------------------------------------------------------- the formerly flaky test, many times

def test_original_flaky_test_passes_fifty_times_in_a_row():
    from test_round2 import ConcurrencyAndSettings

    for _ in range(50):
        case = ConcurrencyAndSettings("test_two_conversions_of_the_same_file_at_once_produce_two_files")
        result = unittest.TestResult()
        case.run(result)
        assert not result.errors and not result.failures, (result.errors, result.failures)
