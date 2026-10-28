"""v0.2.1 "Send feedback": a link that opens the feedback box on the tool's page.

The program only opens a browser; it sends nothing. These tests never open a real
browser (webbrowser.open is a fake) and never touch the network: conftest.py blocks
urlopen, and this module also refuses and counts every socket call.
"""
from __future__ import annotations

import io
import json
import os
import socket
import sys
import urllib.parse
import webbrowser

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import conftest  # noqa: E402
import i18n  # noqa: E402
import main as cli  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402

SLUG = "txttoepub"
KO = "https://chaekgalpi.co.kr/tools/txttoepub?utm_source=app&utm_medium=feedback&v={v}#feedback"
EN = "https://chaekgalpi.co.kr/en/tools/txttoepub?utm_source=app&utm_medium=feedback&v={v}#feedback"
LINK_TEXT = {"ko": "의견 보내기", "en": "Send feedback", "ja": "ご意見を送る", "zh-CN": "发送反馈"}


# ---------------------------------------------------------------- g. no network at all
_sockets: list[str] = []


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    """Every socket connect/lookup is refused and counted; the test fails if any happened."""
    _sockets.clear()

    def refuse(name):
        def fake(*a, **k):
            _sockets.append(f"{name}{a[1:] if name == 'connect' else a}")
            raise OSError(f"network blocked in tests: {name}")
        return fake

    monkeypatch.setattr(socket.socket, "connect", refuse("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", refuse("connect"))
    monkeypatch.setattr(socket, "create_connection", refuse("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", refuse("getaddrinfo"))
    yield
    assert _sockets == [], f"socket calls: {_sockets}"
    assert conftest._attempts == [], f"urlopen calls: {conftest._attempts}"


def parts(url: str):
    s = urllib.parse.urlsplit(url)
    return s, urllib.parse.parse_qs(s.query, keep_blank_values=True)


# ---------------------------------------------------------------- a. the address
@pytest.mark.parametrize("lang, expected", [("ko", KO), ("en", EN), ("ja", EN), ("zh-CN", EN)])
def test_exact_address_per_ui_language(lang, expected):
    assert uc.feedback_url(SLUG, "0.2.1", lang) == expected.format(v="0.2.1")


@pytest.mark.parametrize("lang", [None, "", "  ", "fr", "de", "zh-TW", "zh", "kr", "korean", "english", 5])
def test_unknown_language_gets_the_english_page(lang):
    """Series rule of 2026-10-27: only ko... is Korean; no language means the default (en)."""
    assert uc.feedback_url(SLUG, "0.2.1", lang) == EN.format(v="0.2.1")


@pytest.mark.parametrize("lang, expected", [("EN", EN), ("En", EN), ("JA", EN), ("zh-cn", EN), ("ZH-CN", EN),
                                            ("zh_CN", EN), (" en ", EN), ("KO", KO), ("Ko", KO)])
def test_language_code_case_does_not_matter(lang, expected):
    assert uc.feedback_url(SLUG, "0.2.1", lang) == expected.format(v="0.2.1")


@pytest.mark.parametrize("lang", list(i18n.LANGS) + [None, "xx"])
@pytest.mark.parametrize("ver", ["0.2.1", "", None, "a b&c#d"])
def test_every_address_is_on_the_site_with_the_fragment_and_utm(lang, ver):
    url = uc.feedback_url(SLUG, ver, lang)
    assert url.startswith("https://chaekgalpi.co.kr/") and url.startswith(uc.SITE)
    assert url.endswith("#feedback") and url.count("#") == 1
    s, q = parts(url)
    assert (s.scheme, s.netloc, s.fragment) == ("https", "chaekgalpi.co.kr", "feedback")
    assert s.path in ("/tools/txttoepub", "/en/tools/txttoepub")
    assert q["utm_source"] == ["app"] and q["utm_medium"] == ["feedback"]
    assert set(q) <= {"utm_source", "utm_medium", "v"}
    assert " " not in url


# ---------------------------------------------------------------- b. the version
@pytest.mark.parametrize("ver", ["0.2.1", "v0.2.1", "1.0.0-beta+3", " 0.2.1 ", "a b", "x&y=z", "1#2", "a&utm_source=web",
                                 "한글 버전", "100%", "../..", "?q", "+", "v=1;2", "탭\t줄\n바꿈"])
@pytest.mark.parametrize("lang", ["ko", "en"])
def test_odd_versions_are_encoded_and_read_back_unchanged(ver, lang):
    url = uc.feedback_url(SLUG, ver, lang)
    s, q = parts(url)
    assert q["v"] == [ver]                      # read back exactly as given
    assert q["utm_source"] == ["app"]           # "&utm_source=web" in the version did not win
    assert s.fragment == "feedback" and url.endswith("#feedback")
    assert url.isascii() and not any(c in url for c in " \t\n")


def test_plain_and_prefixed_versions_are_kept_as_they_are():
    assert uc.feedback_url(SLUG, "v0.2.1", "ko") == KO.format(v="v0.2.1")
    assert uc.feedback_url(SLUG, "1.0.0-beta+3", "en") == EN.format(v="1.0.0-beta%2B3")


@pytest.mark.parametrize("ver", ["", None, "   ", "\t"])
def test_empty_version_leaves_v_out(ver):
    assert uc.feedback_url(SLUG, ver, "ko") == "https://chaekgalpi.co.kr/tools/txttoepub?utm_source=app&utm_medium=feedback#feedback"
    assert uc.feedback_url(SLUG, ver, "en") == "https://chaekgalpi.co.kr/en/tools/txttoepub?utm_source=app&utm_medium=feedback#feedback"


def test_the_program_version_is_what_is_sent():
    assert parts(uc.feedback_url(version.UPDATE_SLUG, version.APP_VERSION, "ko"))[1]["v"] == [version.APP_VERSION]


# ---------------------------------------------------------------- the window
@pytest.fixture
def app(tmp_path, monkeypatch):
    """A real window, withdrawn; a fake browser; nothing written to the user's settings.json."""
    import gui

    monkeypatch.setattr(i18n, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    saved: dict = {}
    monkeypatch.setattr(i18n, "save_settings", lambda data: saved.update(data))
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda title, msg, **k: warnings.append((title, msg)))
    for name in ("showinfo", "showerror"):
        monkeypatch.setattr(gui.messagebox, name, lambda *a, **k: pytest.fail("unexpected message box"))
    checks: list = []
    monkeypatch.setattr(gui.update_check, "check_async", lambda *a, **k: checks.append(a))
    opened: list[str] = []
    browser = {"result": True}

    def fake_open(url, *a, **k):
        opened.append(url)
        r = browser["result"]
        if isinstance(r, BaseException):
            raise r
        return r

    monkeypatch.setattr(webbrowser, "open", fake_open)
    before = i18n.current_lang()
    i18n.set_lang("en", persist=False)
    a = gui.App()
    a.root.withdraw()
    a.saved, a.warnings, a.opened, a.browser, a.checks = saved, warnings, opened, browser, checks
    try:
        yield a
    finally:
        a._closing = True
        a.root.destroy()
        i18n.set_lang(before, persist=False)


def switch_lang(a, lang: str) -> None:
    """What picking a language in the combobox does."""
    a.cmb_lang.current(i18n.LANGS.index(lang))
    a._on_lang()


def log_text(a) -> str:
    return a.txt_log.get("1.0", "end")


def click(a) -> None:
    a.lnk_feedback.event_generate("<Button-1>", x=2, y=2)
    a.root.update()


# ---------------------------------------------------------------- c. the click
def test_click_opens_the_browser_once_with_the_address(app):
    click(app)
    assert app.opened == [uc.feedback_url(SLUG, version.APP_VERSION, "en")]
    assert app.opened[0] == EN.format(v=version.APP_VERSION)
    assert app.warnings == [] and "chaekgalpi" not in log_text(app)


def test_the_link_sits_in_the_header_next_to_the_update_checkbox(app):
    info, chk = app.lnk_feedback.grid_info(), app.chk_update.grid_info()
    assert info["in"] is chk["in"] and int(info["row"]) == int(chk["row"]) == 0
    assert int(info["column"]) + 1 == int(chk["column"])
    assert str(app.lnk_feedback.cget("cursor")) == "hand2"


def test_enter_and_space_on_the_link_open_it_too(app):
    for seq in ("<Return>", "<space>"):
        assert app.lnk_feedback.bind(seq)  # bound
    app.send_feedback()
    assert len(app.opened) == 1


def test_changing_the_language_changes_the_next_address(app):
    switch_lang(app, "ko")
    click(app)
    switch_lang(app, "ja")
    click(app)
    switch_lang(app, "zh-CN")
    click(app)
    switch_lang(app, "en")
    click(app)
    v = version.APP_VERSION
    assert app.opened == [KO.format(v=v), EN.format(v=v), EN.format(v=v), EN.format(v=v)]


def test_settings_cannot_steer_the_address(app):
    i18n.save_settings({"feedback_url": "https://evil.example/", "url": "https://evil.example/"})
    open(i18n.SETTINGS_PATH, "w", encoding="utf-8").write('{"feedback_url": "https://evil.example/"}')
    app.send_feedback()
    assert app.opened == [EN.format(v=version.APP_VERSION)]


def test_clicking_saves_nothing_and_checks_nothing(app):
    app.saved.clear()
    checks = len(app.checks)
    for _ in range(3):
        click(app)
    assert app.saved == {} and len(app.checks) == checks and len(app.opened) == 3


# ---------------------------------------------------------------- d. no browser
def snapshot(a) -> dict:
    return {
        "files": list(a.files), "status": a.lbl_status.cget("text"), "merge": a.var_merge.get(),
        "update_check": a.var_update_check.get(), "lang": i18n.current_lang(), "update_info": a._update_info,
        "run": str(a.btn_run.cget("state")), "title": a.root.title(), "outputs": list(a.outputs),
    }


@pytest.mark.parametrize("result", [False, None, webbrowser.Error("no runnable browser"), OSError(5, "Access denied"),
                                    RuntimeError("odd")])
@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_no_browser_shows_the_address_and_the_window_carries_on(app, result, lang):
    switch_lang(app, lang)
    app.saved.clear()
    before = snapshot(app)
    app.browser["result"] = result
    click(app)  # must not raise
    url = uc.feedback_url(SLUG, version.APP_VERSION, lang)
    assert app.opened == [url]
    assert len(app.warnings) == 1
    title, msg = app.warnings[0]
    assert title == LINK_TEXT[lang] and url in msg and msg == i18n.t("feedback_failed", url=url)
    assert url in log_text(app)
    assert snapshot(app) == before and app.saved == {}
    assert app.root.winfo_exists()
    app.browser["result"] = True  # and the next click works
    click(app)
    assert len(app.opened) == 2 and len(app.warnings) == 1


# ---------------------------------------------------------------- e. strings
def load_lang(lang: str) -> dict:
    return json.load(open(os.path.join(ROOT, "lang", f"{lang}.json"), encoding="utf-8"))


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_every_language_has_the_new_strings(lang):
    strings = load_lang(lang)
    assert set(strings) == set(load_lang("en"))
    for key in ("btn_feedback", "feedback_failed", "feedback_failed_log"):
        assert isinstance(strings[key], str) and strings[key].strip(), key
    assert strings["btn_feedback"] == LINK_TEXT[lang]
    for key in ("feedback_failed", "feedback_failed_log"):
        assert "{url}" in strings[key]
        assert "http" not in strings[key]  # the address only ever comes from feedback_url


def test_the_link_text_follows_the_language(app):
    for lang in ("ko", "ja", "zh-CN", "en", "ko"):
        switch_lang(app, lang)
        assert app.lnk_feedback.cget("text") == LINK_TEXT[lang]
        assert app.chk_update.cget("text") == load_lang(lang)["opt_update_check"]


# ---------------------------------------------------------------- f. nothing else changed
def run_cli(*argv):
    buf, old = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        with pytest.raises(SystemExit) as e:
            cli.main(list(argv))
    finally:
        sys.stdout = old
    return e.value.code, buf.getvalue()


@pytest.mark.parametrize("lang", list(i18n.LANGS))
def test_cli_help_is_unchanged(lang):
    code, out = run_cli("--help", "--ui-lang", lang)
    assert code == 0
    for opt in ("--encoding", "--chapter-pattern", "--merge", "--output", "--ui-lang", "--gui"):
        assert opt in out
    assert "feedback" not in out.lower() and "chaekgalpi" not in out


def test_cli_has_no_version_option_as_before(capsys):
    """There was no --version before this release and none was added: argparse still refuses it."""
    with pytest.raises(SystemExit) as e:
        cli.main(["--version", "--ui-lang", "en"])
    assert e.value.code == 2


def test_update_check_is_untouched():
    assert uc.API == "https://chaekgalpi.co.kr/api/tools/{slug}/latest"
    assert uc.DELAY_MS == 1500 and uc.TIMEOUT == 4.0
    info = uc.UpdateInfo("9.9.9", "0.2.1", "https://chaekgalpi.co.kr/tools/txttoepub?utm_source=app&utm_medium=update")
    assert uc.page_url(info, "en") == info.url


def test_update_notice_still_works_after_a_feedback_click(app):
    assert len(app.checks) == 1  # the window still schedules the daily check once
    info = uc.UpdateInfo("9.9.9", version.APP_VERSION,
                         "https://chaekgalpi.co.kr/tools/txttoepub?utm_source=app&utm_medium=update",
                         "https://chaekgalpi.co.kr/en/tools/txttoepub?utm_source=app&utm_medium=update")
    app._on_update_result(info, False)
    app.send_feedback()
    assert app._update_info is info and app.frm_update.winfo_manager() == "grid"
    app._update_open()
    assert app.opened == [EN.format(v=version.APP_VERSION), info.url_en]
    assert app._update_info is None
    app.var_update_check.set(False)
    app._on_update_toggle()
    assert app.saved["update_check"] is False
