"""Window layout (v0.2.3 tidy-up): the window fits the screen, nothing is cut, panel 3 lines up.

What was wrong before: the preview and the log used Tk's fixed font (굴림체 10 on Korean
Windows, 13 px lines), so Hangul lines touched; the order buttons made the file panel, and
with it the least window height, 870 px, more than a 1920x1080 screen has at 125% or 150%;
the window always opened at 1320x860, so the Convert button could sit under the taskbar;
the Japanese line-spacing box was cut ("リーダーの設定に従う"); the style rows did not
start where the book-info rows start.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import detect  # noqa: E402
import gui  # noqa: E402
import i18n  # noqa: E402
from test_merge import app, wait_loaded, write  # noqa: E402,F401  (app is a fixture)

FRAME = (8, 31, 8, 8)               # border and title bar of a Windows 11 window
SCREENS = {                         # work areas in this program's pixels (it is not DPI aware)
    "100% 1920x1080": (0, 0, 1920, 1032),
    "125% 1920x1080": (0, 0, 1536, 816),
    "150% 1920x1200": (0, 0, 1280, 752),
    "150% 1920x1080": (0, 0, 1280, 672),
}


def switch(a, lang: str) -> None:
    a.cmb_lang.current(i18n.LANGS.index(lang))
    a._on_lang()
    a.root.update()


def shown(a, geometry: str | None = None) -> None:
    if geometry:
        a.root.geometry(geometry)
    a.root.deiconify()
    a.root.update()


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def cut_texts(a) -> list[str]:
    """Labels, buttons, checkboxes and radio buttons narrower than their text, and
    read-only boxes narrower than the choice they show."""
    from tkinter import font as tkfont

    out = []
    box_font = tkfont.nametofont("TkDefaultFont")
    for w in walk(a.root):
        if not w.winfo_ismapped():
            continue
        cls = w.winfo_class()
        if cls in ("TLabel", "TButton", "TCheckbutton", "TRadiobutton") and str(w.cget("text")):
            wraps = cls == "TLabel" and str(w.cget("wraplength")) not in ("", "0")
            if not wraps and w.winfo_width() + 1 < w.winfo_reqwidth():
                out.append(f"{w.cget('text')} {w.winfo_width()}<{w.winfo_reqwidth()}")
        elif cls == "TCombobox" and str(w.cget("state")) == "readonly" and w.get():
            if w.winfo_width() < box_font.measure(w.get()) + 26:  # 26: the arrow and the inner margins
                out.append(f"{w.get()} {w.winfo_width()}")
    return out


# ---------------------------------------------------------------- fit_window
@pytest.mark.parametrize("screen", list(SCREENS))
def test_window_lies_inside_the_work_area(screen):
    work = SCREENS[screen]
    w, h, x, y, min_w, min_h = gui.fit_window(work, FRAME, (1320, 820), (1274, 772))
    left, top, right, bottom = work
    assert left <= x and x + w + FRAME[0] + FRAME[2] <= right, screen
    assert top <= y and y + h + FRAME[1] + FRAME[3] <= bottom, screen
    assert min_w <= w and min_h <= h


def test_big_screen_keeps_the_wanted_size_and_centres_it():
    w, h, x, y, min_w, min_h = gui.fit_window((0, 0, 1920, 1032), FRAME, (1320, 820), (1274, 772))
    assert (w, h, min_w, min_h) == (1320, 820, 1274, 772)
    assert (x, y) == ((1920 - 1336) // 2, (1032 - 859) // 2)


def test_least_height_fits_125_percent_on_a_1080p_screen(app):
    """The least window height used to be 870; a 1920x1080 screen at 125% has 777 inside."""
    for lang in i18n.LANGS:
        switch(app, lang)
        app._place_window(work=(0, 0, 3000, 2000))
        assert app._min_size[1] <= 777, (lang, app._min_size)


@pytest.mark.parametrize("screen", ["150% 1920x1080", "150% 1920x1200"])
def test_convert_button_stays_on_a_small_screen(app, screen):
    """Smaller than the panels ask for: the window still fits and Convert is inside it."""
    app._place_window(work=SCREENS[screen])
    shown(app)
    try:
        root = app.root
        assert root.winfo_height() + FRAME[1] + FRAME[3] <= SCREENS[screen][3]
        bottom = app.btn_run.winfo_rooty() + app.btn_run.winfo_height() - root.winfo_rooty()
        assert 0 < bottom <= root.winfo_height()
    finally:
        app.root.withdraw()


# ---------------------------------------------------------------- texts
def test_preview_and_log_use_the_ui_font_not_the_fixed_one(app):
    for box in (app.txt_preview, app.txt_log):
        assert str(box.cget("font")) == gui.TEXT_FONT == "TkTextFont"


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_nothing_is_cut_at_the_least_size(app, tmp_path, lang):
    app.add_paths([write(tmp_path, "a.txt", "제1장 시작\n\n본문입니다.\n")])
    wait_loaded(app)
    app.var_epub_version.set("3")
    switch(app, lang)
    w, h = app._min_size
    shown(app, f"{w}x{h}+0+0")
    try:
        assert cut_texts(app) == [], lang
        app.var_merge.set("one")
        app._on_merge_mode()
        app.root.update()
        assert cut_texts(app) == [], (lang, "one book")
    finally:
        app.root.withdraw()


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_style_rows_start_where_the_book_info_rows_start(app, lang):
    switch(app, lang)
    shown(app)
    try:
        x = app.ent_title.winfo_rootx()
        assert app.cmb_epub.winfo_rootx() == x
        assert app.cmb_line_height.winfo_rootx() == x, lang
        right = x + app.ent_title.winfo_width()
        assert app.cmb_epub.winfo_rootx() + app.cmb_epub.winfo_width() == right
    finally:
        app.root.withdraw()


# ---------------------------------------------------------------- panels
def test_order_buttons_sit_on_the_mode_line(app):
    assert app.btn_up.master is app.rad_one.master is app.btn_down.master
    assert app.btn_up.winfo_manager() == "pack"


def test_encoding_warning_takes_room_only_when_it_says_something(app, tmp_path, monkeypatch):
    app.add_paths([write(tmp_path, "a.txt", "제1장 시작\n\n본문입니다.\n")])
    wait_loaded(app)
    assert app.lbl_enc_warn.winfo_manager() == "" and app.lbl_enc_warn.cget("text") == ""
    monkeypatch.setattr(detect, "LOW_CONFIDENCE", 101)
    app._refresh_preview()
    assert app.lbl_enc_warn.winfo_manager() == "grid" and app.lbl_enc_warn.cget("text")
    assert app.lbl_enc_warn.grid_info()["row"] == 2  # back where it was, above the preview
    monkeypatch.setattr(detect, "LOW_CONFIDENCE", 0)
    app._refresh_preview()
    assert app.lbl_enc_warn.winfo_manager() == ""
