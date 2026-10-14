"""Update check: once a day, off switch, silent failures, what is sent, when a notice shows.
The network is always faked - these tests never reach the real server."""
from __future__ import annotations

import io
import json
import os
import socket
import sys
import urllib.error
import urllib.parse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import prefs as prefs_mod  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402

DAY = "2026-10-13"
OK = {"slug": "txttoepub", "latest": "0.2.0", "tag": "v0.2.0", "client": version.APP_VERSION, "updateAvailable": True,
      "url": "https://chaekgalpi.co.kr/tools/txttoepub?utm_source=app&utm_medium=update"}


class FakeRoot:
    """after() runs the callback at once; the background thread is run inline (see fixture)."""

    def __init__(self):
        self.delays = []

    def after(self, ms, fn):
        self.delays.append(ms)
        fn()


@pytest.fixture(autouse=True)
def inline_threads(monkeypatch):
    class InlineThread:
        def __init__(self, target, name=None, daemon=None):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(uc.threading, "Thread", InlineThread)


def run(prefs, fetcher, day=DAY):
    """One app start: schedule the check; the caller records the day only when answered (as the GUI does)."""
    results = []

    def on_result(info, answered):
        results.append(info)
        if answered:
            prefs.update_check_last = day

    root = FakeRoot()
    scheduled = uc.check_async(root, version.UPDATE_SLUG, version.APP_VERSION, prefs, on_result, fetcher=fetcher, day=day)
    return scheduled, results, root


def counting(answer):
    calls = []

    def fetcher(slug, ver):
        calls.append((slug, ver))
        return answer

    return fetcher, calls


# ------------------------------------------------------------------ how often
def test_same_day_twice_asks_once():
    p = prefs_mod.Prefs()
    fetcher, calls = counting(OK)
    run(p, fetcher)
    run(p, fetcher)
    assert len(calls) == 1
    run(p, fetcher, day="2026-10-14")
    assert len(calls) == 2


def test_switched_off_never_asks():
    p = prefs_mod.Prefs(update_check=False)
    fetcher, calls = counting(OK)
    scheduled, results, root = run(p, fetcher)
    assert not scheduled and calls == [] and results == []


def test_offline_does_not_use_up_the_day():
    p = prefs_mod.Prefs()
    fetcher, calls = counting(None)  # no answer
    run(p, fetcher)
    run(p, fetcher)
    assert len(calls) == 2 and p.update_check_last == ""


def test_waits_one_and_a_half_seconds_first():
    _, _, root = run(prefs_mod.Prefs(), counting(OK)[0])
    assert root.delays[0] == 1500


def test_closed_window_is_harmless():
    class DeadRoot:
        def after(self, ms, fn):
            raise RuntimeError("main thread is not in main loop")

    assert uc.check_async(DeadRoot(), "txttoepub", "0.1.2", prefs_mod.Prefs(), lambda *a: None, fetcher=lambda s, v: OK,
                          day=DAY) is False


# ------------------------------------------------------------------ what is sent
class FakeResp(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_request_carries_only_slug_version_and_os():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["timeout"] = req.full_url, timeout
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        return FakeResp(json.dumps(OK).encode())

    assert uc.fetch("txttoepub", "0.1.2", opener=opener) == OK
    url = urllib.parse.urlsplit(seen["url"])
    assert (url.scheme, url.netloc, url.path) == ("https", "chaekgalpi.co.kr", "/api/tools/txttoepub/latest")
    assert urllib.parse.parse_qs(url.query) == {"v": ["0.1.2"], "os": ["win"]}
    assert seen["timeout"] == 4.0
    assert seen["headers"]["user-agent"] == "chaekgalpi-tool/txttoepub/0.1.2"
    assert set(seen["headers"]) <= {"user-agent", "accept"}  # nothing else about the user or machine


@pytest.mark.parametrize("behaviour", ["urlerror", "timeout", "http500", "badjson", "list", "status500", "oserror", "huge"])
def test_failures_are_silent(behaviour):
    def opener(req, timeout):
        if behaviour == "urlerror":
            raise urllib.error.URLError("offline")
        if behaviour == "timeout":
            raise socket.timeout("slow")
        if behaviour == "http500":
            raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, None)
        if behaviour == "oserror":
            raise OSError("reset")
        if behaviour == "badjson":
            return FakeResp(b"<html>not json")
        if behaviour == "list":
            return FakeResp(b"[1, 2]")
        if behaviour == "huge":
            return FakeResp(b'{"a": "' + b"x" * (uc.MAX_BYTES + 10) + b'"}')  # cut at MAX_BYTES -> not JSON
        return FakeResp(json.dumps(OK).encode(), status=500)

    assert uc.fetch("txttoepub", "0.1.2", opener=opener) is None


# ------------------------------------------------------------------ when a notice shows
@pytest.mark.parametrize("flag", [False, None, "true", 1, "yes"])
def test_no_notice_unless_server_says_true(flag):
    assert uc.interpret(dict(OK, updateAvailable=flag), "0.1.2") is None


def test_notice_once_when_newer():
    p = prefs_mod.Prefs()
    fetcher, _ = counting(OK)
    _, results, _ = run(p, fetcher)
    assert len(results) == 1 and results[0] == uc.UpdateInfo("0.2.0", version.APP_VERSION, OK["url"])


def test_later_hides_that_version_but_not_a_newer_one():
    p = prefs_mod.Prefs(update_check_skipped="0.2.0")
    assert uc.interpret(OK, "0.1.2", p.update_check_skipped) is None
    newer = dict(OK, latest="0.2.1")
    assert uc.interpret(newer, "0.1.2", p.update_check_skipped).latest == "0.2.1"


@pytest.mark.parametrize("url", ["https://github.com/microhan1/txt-to-epub/releases", "http://chaekgalpi.co.kr/tools/x",
                                 "https://chaekgalpi.co.kr.evil.example/", "javascript:alert(1)", None, 5, ""])
def test_only_pages_of_the_tools_site_are_opened(url):
    assert uc.interpret(dict(OK, url=url), "0.1.2") is None


@pytest.mark.parametrize("latest", ["", "   ", None, 3, "x" * 40])
def test_odd_versions_show_nothing(latest):
    assert uc.interpret(dict(OK, latest=latest), "0.1.2") is None


# ------------------------------------------------------------------ which page [Update] opens
EN_URL = "https://chaekgalpi.co.kr/en/tools/txttoepub?utm_source=app&utm_medium=update"


def test_korean_ui_opens_the_korean_page_even_with_url_en():
    info = uc.interpret(dict(OK, urlEn=EN_URL), "0.1.2")
    assert uc.page_url(info, "ko") == OK["url"]


@pytest.mark.parametrize("lang", ["en", "ja", "zh-CN"])
def test_other_ui_languages_open_the_english_page_when_offered(lang):
    info = uc.interpret(dict(OK, urlEn=EN_URL), "0.1.2")
    assert uc.page_url(info, lang) == EN_URL


@pytest.mark.parametrize("url_en", [None, "", "https://github.com/microhan1/txt-to-epub", "http://chaekgalpi.co.kr/en/x", 7])
def test_english_ui_falls_back_to_the_korean_page(url_en):
    info = uc.interpret(dict(OK, urlEn=url_en), "0.1.2")
    assert info.url_en == "" and uc.page_url(info, "en") == OK["url"]


def test_missing_url_en_field_falls_back():
    info = uc.interpret(OK, "0.1.2")  # the v1.95 server has no urlEn at all
    assert uc.page_url(info, "en") == OK["url"] and uc.page_url(info, "ko") == OK["url"]


def test_url_en_does_not_rescue_a_bad_url():
    assert uc.interpret(dict(OK, url="https://evil.example/", urlEn=EN_URL), "0.1.2") is None


def test_version_constants():
    assert version.UPDATE_SLUG == "txttoepub"
    parts = version.APP_VERSION.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts)


# ------------------------------------------------------------------ the thread must not touch Tk
def test_worker_thread_holds_no_tk_object(monkeypatch):
    """The fetch thread must keep neither the root nor the callback: when the window
    closes while a request is out, the thread would otherwise free Tk objects off
    the main thread (Tcl_AsyncDelete crash)."""
    captured = {}

    class CaptureThread:
        def __init__(self, target, name=None, daemon=None):
            captured["target"] = target

        def start(self):
            pass

    monkeypatch.setattr(uc.threading, "Thread", CaptureThread)

    class Root:
        def after(self, ms, fn):
            if ms == uc.DELAY_MS:
                fn()

    root, on_result = Root(), lambda info, answered: None
    uc.check_async(root, "txttoepub", "0.1.2", prefs_mod.Prefs(), on_result, fetcher=lambda s, v: OK, day=DAY)
    target = captured["target"]
    held = [c.cell_contents for c in (target.__closure__ or ())] + list(target.__defaults__ or ())
    assert not any(x is root or x is on_result for x in held)
    assert not any(hasattr(x, 'after') or hasattr(x, 'tk') for x in held)  # nothing Tk-like at all


def test_closing_the_window_while_a_request_is_out_survives(monkeypatch):
    """Real Tk, real thread: destroy the window while the fetcher is still blocked,
    three times in a row. The answer arriving afterwards must be dropped quietly."""
    import threading
    import tkinter as tk

    monkeypatch.undo()  # this test needs real threads
    for _ in range(3):
        release = threading.Event()
        answered = []

        def fetcher(slug, ver):
            release.wait(5)
            return OK

        root = tk.Tk()
        root.withdraw()
        uc.check_async(root, "txttoepub", "0.1.2", prefs_mod.Prefs(), lambda info, ok: answered.append(ok),
                       fetcher=fetcher, day=DAY)
        root.after(uc.DELAY_MS + 50, root.destroy)  # the request is out when the window dies
        root.mainloop()
        release.set()
        for th in threading.enumerate():
            if th.name == "update-check":
                th.join(5)
        assert answered == []  # nothing reached a dead window, nothing crashed


# ------------------------------------------------------------------ settings
def test_settings_are_type_checked(monkeypatch):
    import i18n

    monkeypatch.setattr(i18n, "load_settings", lambda: {"update_check": "no", "update_check_last": 20261013,
                                                        "update_check_skipped": ["0.2.0"]})
    p = prefs_mod.load()
    assert p.update_check is True and p.update_check_last == "" and p.update_check_skipped == ""


def test_save_keeps_other_settings(monkeypatch):
    import i18n

    store = {"lang": "ko", "options": {"indent": True}}
    monkeypatch.setattr(i18n, "load_settings", lambda: dict(store))
    monkeypatch.setattr(i18n, "save_settings", lambda d: store.update(d))
    prefs_mod.save(prefs_mod.Prefs(update_check=False, update_check_last=DAY))
    assert store["lang"] == "ko" and store["options"] == {"indent": True}
    assert store["update_check"] is False and store["update_check_last"] == DAY
