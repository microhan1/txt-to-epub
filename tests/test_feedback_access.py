"""The "Send feedback" link, series follow-up of 2026-10-27: it is a Tab stop that Enter
and Space open, it shows a small note while the mouse is over it, and every language code
picks its page by one rule (ko... -> Korean page, anything else -> English page). The
browser is faked, settings live in a temporary folder and nothing may leave the machine.

Key presses: a generated key event only reaches a widget when the window has the
system's keyboard focus, and taking that focus would steal it from whoever is typing.
So the tests run the very script Tk binds to the key (what Tk runs when the key comes
in), and check the Tab order with tk_focusNext/tk_focusPrev, which is what Tk's <Tab>
and <Shift-Tab> bindings use (same approach as scan-pdf-split).
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.parse
import webbrowser

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import conftest  # noqa: E402
import i18n  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402

SLUG = version.UPDATE_SLUG
KO_PAGE = "https://chaekgalpi.co.kr/tools/txttoepub"
EN_PAGE = "https://chaekgalpi.co.kr/en/tools/txttoepub"
TIPS = {"ko": "안 되는 것·불편한 것·바라는 기능을 알려 주세요(브라우저가 열립니다)",
        "en": "Tell us what's broken or missing (opens your browser)",
        "ja": "不具合・ご要望をお知らせください（ブラウザが開きます）",
        "zh-CN": "告诉我们问题或建议（将打开浏览器）"}


# ---------------------------------------------------------------- f. no network at all
_sockets: list[str] = []


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    """Every socket connect/lookup is refused and counted; the test fails if any happened."""
    _sockets.clear()

    def refuse(name):
        def fake(*a, **k):
            _sockets.append(name)
            raise OSError(f"network blocked in tests: {name}")
        return fake

    monkeypatch.setattr(socket.socket, "connect", refuse("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", refuse("connect_ex"))
    monkeypatch.setattr(socket, "create_connection", refuse("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", refuse("getaddrinfo"))
    yield
    assert _sockets == [], f"socket calls: {_sockets}"
    assert conftest._attempts == [], f"urlopen calls: {conftest._attempts}"


def page_of(url: str) -> str:
    s = urllib.parse.urlsplit(url)
    return f"{s.scheme}://{s.netloc}{s.path}"


def url_for(lang):
    return uc.feedback_url(SLUG, version.APP_VERSION, lang)


# ---------------------------------------------------------------- c. one language rule
KOREAN = ["ko", "ko-KR", "ko_KR", "KO", "Ko-kr", "ko-kr", " ko ", "KO_kr"]
ENGLISH = ["en", "ja", "zh", "zh-CN", "zh_CN", "zh-TW", "zh-Hant", "fr", "de", "EN", "en-US", "en_GB",
           "ja-JP", "pt-BR", "xx", "english", "korean", "kor", "kr", "k", "-ko", "o-ko"]
EMPTY = [None, "", "   ", "\t", 5, 0, ["ko"], b"ko"]


@pytest.mark.parametrize("lang", KOREAN)
def test_korean_codes_get_the_korean_page(lang):
    assert uc.is_korean(lang)
    assert page_of(url_for(lang)) == KO_PAGE


@pytest.mark.parametrize("lang", ENGLISH)
def test_every_other_code_gets_the_english_page(lang):
    assert not uc.is_korean(lang)
    assert page_of(url_for(lang)) == EN_PAGE


@pytest.mark.parametrize("lang", EMPTY)
def test_no_language_follows_the_default_screen_language(lang, monkeypatch):
    assert i18n.DEFAULT_LANG == "en"  # this tool opens in English when it cannot tell
    assert not uc.is_korean(lang) and page_of(url_for(lang)) == EN_PAGE
    monkeypatch.setattr(i18n, "DEFAULT_LANG", "ko")  # and the rule really reads the default
    assert uc.is_korean(lang) and page_of(url_for(lang)) == KO_PAGE


@pytest.mark.parametrize("lang", KOREAN + ENGLISH + EMPTY)
@pytest.mark.parametrize("ver", [version.APP_VERSION, "", None])
def test_every_address_has_the_same_shape(lang, ver):
    url = uc.feedback_url(SLUG, ver, lang)
    assert url.startswith("https://chaekgalpi.co.kr/") and url.endswith("#feedback") and url.count("#") == 1
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert q["utm_source"] == ["app"] and q["utm_medium"] == ["feedback"]
    assert q.get("v") == ([ver] if ver else None)
    assert set(q) <= {"utm_source", "utm_medium", "v"}


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_the_four_screen_languages(lang):
    assert page_of(url_for(lang)) == (KO_PAGE if lang == "ko" else EN_PAGE)


URL_KO = "https://chaekgalpi.co.kr/tools/txttoepub?utm_source=app&utm_medium=update"
URL_EN = "https://chaekgalpi.co.kr/en/tools/txttoepub?utm_source=app&utm_medium=update"


@pytest.mark.parametrize("lang", KOREAN + ENGLISH + EMPTY)
def test_update_page_uses_the_same_rule(lang):
    info = uc.UpdateInfo("9.9.9", version.APP_VERSION, URL_KO, URL_EN)
    assert uc.page_url(info, lang) == (URL_KO if uc.is_korean(lang) else URL_EN)
    assert (uc.page_url(info, lang) == URL_KO) == (page_of(url_for(lang)) == KO_PAGE)
    assert uc.page_url(uc.UpdateInfo("9.9.9", version.APP_VERSION, URL_KO), lang) == URL_KO  # no English page offered


def test_one_rule_only():
    """The old list of English codes is gone: nothing else in update_check decides the page."""
    assert not hasattr(uc, "FEEDBACK_EN_LANGS")
    src = open(os.path.join(ROOT, "update_check.py"), encoding="utf-8").read()
    assert src.count("def is_korean(") == 1
    assert "is_korean(ui_lang)" in src and 'page = "ko" if is_korean(lang) else "en"' in src


# ---------------------------------------------------------------- d. the READMEs
FEEDBACK_LINK = re.compile(r"https://chaekgalpi\.co\.kr/[^\s)\]>]*#feedback")


@pytest.mark.parametrize("name, expected", [
    ("README.md", KO_PAGE + "#feedback"),
    ("README.en.md", EN_PAGE + "#feedback"),
    ("README.ja.md", EN_PAGE + "#feedback"),
    ("README.zh-CN.md", EN_PAGE + "#feedback"),
])
def test_readme_feedback_links(name, expected):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        text = f.read()
    links = FEEDBACK_LINK.findall(text)
    assert links and all(link == expected for link in links), links
    # written as [text](address): the address never runs into a bracket, particle or full-width comma
    for m in re.finditer(re.escape(expected), text):
        assert text[m.start() - 1] in "[(", text[m.start() - 5:m.end() + 5]
        assert text[m.end()] in "])", text[m.start() - 5:m.end() + 5]


@pytest.mark.parametrize("name, page", [("README.md", KO_PAGE), ("README.en.md", EN_PAGE), ("README.ja.md", EN_PAGE), ("README.zh-CN.md", EN_PAGE)])
def test_readme_tools_page_link(name, page):
    """The tools-page link (utm_source=github): Korean README -> Korean page, the others -> English page, query kept."""
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        links = re.findall(r"\]\((https://chaekgalpi\.co\.kr/[^\s)]*utm_source=github[^\s)]*)\)", f.read())
    assert links == [page + "?utm_source=github&utm_medium=referral&utm_campaign=tool_cta&utm_content=txttoepub"], links


# ---------------------------------------------------------------- the window
@pytest.fixture
def app(tmp_path, monkeypatch):
    """A real window, withdrawn; a fake browser; nothing written to the user's settings.json."""
    import gui

    monkeypatch.setattr(i18n, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(i18n, "save_settings", lambda data: None)
    monkeypatch.setattr(gui.Tooltip, "DELAY_MS", 50)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda title, msg, **k: warnings.append((title, msg)))
    monkeypatch.setattr(gui.update_check, "check_async", lambda *a, **k: None)
    opened: list[str] = []
    browser = {"result": True}

    def fake_open(url, *a, **k):
        opened.append(url)
        return browser["result"]

    monkeypatch.setattr(webbrowser, "open", fake_open)
    before = i18n.current_lang()
    i18n.set_lang("en", persist=False)
    a = gui.App()
    a.root.withdraw()
    a.root.update()
    a.opened, a.warnings, a.browser = opened, warnings, browser
    try:
        yield a
    finally:
        a.tip_feedback.hide()
        a._closing = True
        a.root.destroy()
        i18n.set_lang(before, persist=False)


def wait(a, cond, timeout=3.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        a.root.update()
        if cond():
            return True
        time.sleep(0.01)
    return False


def press(widget, sequence: str) -> str:
    """Run the script Tk binds to `sequence` on this widget, as Tk does when the key
    arrives; return what it returned ("break" stops the class bindings)."""
    script = widget.bind(sequence)
    assert script, f"nothing bound to {sequence}"
    fields = dict.fromkeys("#bhkstwxyEXYD", "0")  # the numbers Tk would fill in
    fields["W"] = str(widget)
    script = re.sub(r"%([#a-zA-Z])", lambda m: fields.get(m.group(1), "??"), script)
    code = widget.tk.eval(f"catch {{{script}}} ::press_result")  # 3 is Tcl's code for break
    assert code in ("0", "3"), widget.tk.eval("set ::press_result")
    return "break" if code == "3" else ""


def shown(a) -> None:
    """Tk's Tab walk skips widgets that are not viewable, so these tests map the window
    (not focused: nothing here takes the keyboard)."""
    a.root.deiconify()
    assert wait(a, lambda: a.lnk_feedback.winfo_viewable() and a.chk_update.winfo_viewable())


def switch(a, lang):
    a.cmb_lang.current(i18n.LANGS.index(lang))
    a._on_lang()
    a.root.update()


# ---------------------------------------------------------------- a. keyboard
def test_link_is_a_tab_stop_right_before_the_update_checkbox(app):
    shown(app)
    link = app.lnk_feedback
    assert str(link.cget("takefocus")) in ("1", "true", "True")
    assert link.tk_focusNext() is app.chk_update  # Tab from the link lands on the checkbox
    assert app.chk_update.tk_focusPrev() is link  # and Shift+Tab comes back to it
    before = link.tk_focusPrev()
    assert before is not link and before.tk_focusNext() is link  # the widget before it -> Tab -> link


def test_tab_and_shift_tab_walk_the_same_ring_in_opposite_orders(app):
    shown(app)
    link = app.lnk_feedback
    ring, w = [link], link.tk_focusNext()
    while w is not link and len(ring) < 500:
        ring.append(w)
        w = w.tk_focusNext()
    assert w is link and ring.count(link) == 1 and len(ring) > 3
    back, w = [link], link.tk_focusPrev()
    while w is not link and len(back) < 500:
        back.append(w)
        w = w.tk_focusPrev()
    assert back == [link] + ring[:0:-1]
    i = ring.index(app.chk_update)
    assert ring[i - 1] is link and ring[i + 1] is app.cmb_lang  # header: link, checkbox, language


@pytest.mark.parametrize("key", ["<Return>", "<KP_Enter>", "<space>"])
def test_enter_and_space_open_the_page_exactly_once(app, key):
    assert press(app.lnk_feedback, key) == "break"
    assert app.opened == [url_for("en")]
    assert app.warnings == []


def test_each_key_opens_once_and_mouse_still_works(app):
    link = app.lnk_feedback
    for key in ("<Return>", "<space>", "<KP_Enter>"):
        press(link, key)
    link.event_generate("<Button-1>", x=2, y=2)
    app.root.update()
    assert app.opened == [url_for("en")] * 4


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_keyboard_uses_the_current_language(app, lang):
    switch(app, lang)
    press(app.lnk_feedback, "<Return>")
    press(app.lnk_feedback, "<space>")
    assert app.opened == [url_for(lang)] * 2


def test_keyboard_with_no_browser_shows_the_address(app):
    app.browser["result"] = False
    press(app.lnk_feedback, "<space>")
    assert len(app.warnings) == 1 and url_for("en") in app.warnings[0][1]


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_focus_shows_a_frame_that_does_not_change_the_size(app, lang):
    switch(app, lang)
    link = app.lnk_feedback
    head = link.master
    app.root.update_idletasks()
    size = (link.winfo_reqwidth(), link.winfo_reqheight())
    head_size = (head.winfo_reqwidth(), head.winfo_reqheight())
    assert str(link.cget("relief")) == "flat" and int(str(link.cget("borderwidth"))) >= 1
    press(link, "<FocusIn>")
    app.root.update_idletasks()
    assert str(link.cget("relief")) == "solid"
    assert (link.winfo_reqwidth(), link.winfo_reqheight()) == size
    assert (head.winfo_reqwidth(), head.winfo_reqheight()) == head_size
    press(link, "<FocusOut>")
    app.root.update_idletasks()
    assert str(link.cget("relief")) == "flat"
    assert (link.winfo_reqwidth(), link.winfo_reqheight()) == size
    assert app.opened == []  # focus alone opens nothing


def test_other_keys_do_nothing(app):
    link = app.lnk_feedback
    for seq in ("<Key>", "<Key-a>", "<Escape>", "<Tab>", "<Shift-Tab>", "<BackSpace>", "<Up>", "<Down>"):
        assert not link.bind(seq), seq
    assert set(link.bind()) == {"<Button-1>", "<Key-Return>", "<Key-KP_Enter>", "<Key-space>", "<FocusIn>",
                                "<FocusOut>", "<Enter>", "<Leave>", "<Button>", "<Destroy>"}
    assert app.opened == []


# ---------------------------------------------------------------- b. the note under the link
def hover(a) -> bool:
    a.lnk_feedback.event_generate("<Enter>", x=2, y=2)
    # mapped is not enough: the label inside can still be width 1 for a moment
    return wait(a, lambda: a.tip_feedback.tip is not None and a.tip_feedback.tip.winfo_ismapped()
                and a.tip_feedback.tip.winfo_width() > 1 and a.tip_feedback.label.winfo_width() > 1)


def leave(a) -> None:
    a.lnk_feedback.event_generate("<Leave>", x=2, y=2)
    a.root.update()


def test_real_delay_is_between_four_and_five_tenths():
    import gui

    assert 400 <= gui.Tooltip.DELAY_MS <= 500


def test_note_appears_on_hover_and_goes_on_leave(app):
    tip = app.tip_feedback
    assert tip.tip is None
    assert hover(app)
    assert tip.label.cget("text") == TIPS["en"]
    leave(app)
    assert tip.tip is None
    assert hover(app)  # and again
    leave(app)
    assert tip.tip is None and app.opened == []  # hovering opens nothing


def test_leaving_before_the_delay_shows_nothing(app):
    app.lnk_feedback.event_generate("<Enter>", x=2, y=2)
    leave(app)
    wait(app, lambda: False, timeout=0.3)
    assert app.tip_feedback.tip is None


def test_no_note_before_the_delay(app, monkeypatch):
    import gui

    monkeypatch.setattr(gui.Tooltip, "DELAY_MS", 400)
    app.lnk_feedback.event_generate("<Enter>", x=2, y=2)
    start = time.time()
    wait(app, lambda: time.time() - start > 0.2, timeout=0.3)
    assert app.tip_feedback.tip is None
    assert wait(app, lambda: app.tip_feedback.tip is not None, timeout=2)
    assert time.time() - start >= 0.35


def test_clicking_or_pressing_hides_the_note_and_opens_once(app):
    assert hover(app)
    app.lnk_feedback.event_generate("<Button-1>", x=2, y=2)
    app.root.update()
    assert app.tip_feedback.tip is None and app.opened == [url_for("en")]
    assert hover(app)
    press(app.lnk_feedback, "<Return>")
    assert app.tip_feedback.tip is None and len(app.opened) == 2
    assert hover(app)
    press(app.lnk_feedback, "<space>")
    assert app.tip_feedback.tip is None and len(app.opened) == 3


def test_note_is_a_borderless_window_below_the_link(app):
    app.root.deiconify()
    try:
        assert hover(app)
        tip = app.tip_feedback.tip
        assert tip.wm_overrideredirect() and tip.winfo_toplevel() is tip
        assert tip.winfo_rooty() >= app.lnk_feedback.winfo_rooty() + app.lnk_feedback.winfo_height()
    finally:
        app.root.withdraw()


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_note_words_per_language(app, lang):
    switch(app, lang)
    assert app.tip_feedback.text == TIPS[lang]
    assert hover(app)
    assert app.tip_feedback.label.cget("text") == TIPS[lang]


def test_language_files_carry_distinct_non_empty_notes():
    notes = {}
    for lang in i18n.LANGS:
        with open(os.path.join(ROOT, "lang", f"{lang}.json"), encoding="utf-8") as f:
            notes[lang] = json.load(f)["tip_feedback"]
    assert notes == TIPS
    assert all(n.strip() for n in notes.values()) and len(set(notes.values())) == len(notes)
    assert all("http" not in n for n in notes.values())


def test_switching_language_while_the_note_shows_changes_its_words(app):
    assert hover(app)
    for lang in ("ko", "ja", "zh-CN", "en", "ko"):
        switch(app, lang)
        assert app.tip_feedback.tip is not None
        assert app.tip_feedback.label.cget("text") == TIPS[lang]


def test_closing_the_link_takes_the_note_with_it(app):
    assert hover(app)
    tip = app.tip_feedback.tip
    app.lnk_feedback.destroy()
    app.root.update()
    assert app.tip_feedback.tip is None and not tip.winfo_exists()


@pytest.mark.parametrize("edge", ["left", "right"])
@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_note_stays_inside_the_window_and_the_screen(app, lang, edge):
    """At the smallest window size, with the window pushed against either screen edge."""
    switch(app, lang)
    root = app.root
    w, h = app._min_size
    sw = root.winfo_screenwidth()
    x = 0 if edge == "left" else max(sw - w - 16, 0)  # 16: the window frame around the client area
    root.geometry(f"{w}x{h}+{x}+0")
    root.deiconify()
    try:
        wait(app, lambda: root.winfo_ismapped() and root.winfo_width() >= w - 1, timeout=2)
        assert hover(app)
        tip, label = app.tip_feedback.tip, app.tip_feedback.label
        tip.update_idletasks()
        tx, ty, tw, th = tip.winfo_rootx(), tip.winfo_rooty(), tip.winfo_width(), tip.winfo_height()
        assert label.cget("text") == TIPS[lang] and label.winfo_reqwidth() <= label.winfo_width() + 1
        assert root.winfo_rootx() <= tx and tx + tw <= root.winfo_rootx() + root.winfo_width(), (lang, edge)
        assert root.winfo_rooty() <= ty and ty + th <= root.winfo_rooty() + root.winfo_height(), (lang, edge)
        assert 0 <= tx and tx + tw <= sw and 0 <= ty and ty + th <= root.winfo_screenheight()
        leave(app)
        assert app.tip_feedback.tip is None
    finally:
        root.withdraw()


def test_note_is_pulled_inside_the_screen_when_the_link_is_at_its_edge(app):
    """place() itself: a link reported at the very left or right screen edge."""
    assert hover(app)
    tooltip, link = app.tip_feedback, app.lnk_feedback
    sw, sh = link.winfo_screenwidth(), link.winfo_screenheight()
    for fake_x, fake_y in ((-500, 10), (sw + 500, 10), (10, sh + 50)):
        link.winfo_rootx, link.winfo_rooty = (lambda v=fake_x: v), (lambda v=fake_y: v)
        try:
            tooltip.place()
            app.root.update()
        finally:
            del link.winfo_rootx, link.winfo_rooty
        tip = tooltip.tip
        tx, ty, tw, th = tip.winfo_x(), tip.winfo_y(), tip.winfo_reqwidth(), tip.winfo_reqheight()
        assert 0 <= tx and tx + tw <= sw and 0 <= ty and ty + th <= sh, (fake_x, fake_y, tx, ty)


# ---------------------------------------------------------------- e. what was there stays
def test_update_notice_and_its_page_untouched(app):
    info = uc.UpdateInfo("9.9.9", version.APP_VERSION, URL_KO, URL_EN)
    app._on_update_result(info, answered=False)
    assert app.frm_update.winfo_manager()
    assert hover(app)
    press(app.lnk_feedback, "<Return>")
    app._update_open()
    assert app.opened == [url_for("en"), URL_EN]
    switch(app, "ko")
    app._on_update_result(info, answered=False)
    app._update_open()
    assert app.opened[-1] == URL_KO
