"""Start-up picture and the deferred Pillow import (the hub's 2026-11-10 note).

The one-file exe shows assets/splash.png while it unpacks; the program closes it once
its window is drawn (gui.launch) or, in a console run, before the CLI starts. Pillow
is imported behind the window; a conversion that starts earlier waits for it. None of
this needs PyInstaller: a fake pyi_splash module stands in for the loader's one, and a
fake App stands in for the window, so nothing is drawn and no settings are written.
"""
from __future__ import annotations

import os
import sys
import threading
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import cover  # noqa: E402
import gui  # noqa: E402
import i18n  # noqa: E402
import main as cli  # noqa: E402
import splash  # noqa: E402


@pytest.fixture
def pyi_splash(monkeypatch):
    """A fake loader module: records close() calls, can be told to fail."""
    mod = types.ModuleType("pyi_splash")
    mod.calls = []
    mod.fail = None

    def close():
        if mod.fail is not None:
            raise mod.fail
        mod.calls.append(1)

    mod.close = close
    monkeypatch.setitem(sys.modules, "pyi_splash", mod)
    return mod


@pytest.fixture
def deferred(monkeypatch):
    """cover.py as it is before Pillow was loaded: the stand-ins are back in place."""
    monkeypatch.setattr(cover, "_heavy_loaded", False)
    for name in ("Image", "ImageDraw", "ImageFont"):
        monkeypatch.setattr(cover, name, cover._Deferred(name))
    yield
    cover.load_heavy()   # leave the module usable for the other test files


# ---------------------------------------------------------------- close_splash

def test_close_splash_is_silent_without_pyinstaller(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyi_splash", None)   # import raises ImportError
    splash.close_splash()


def test_close_splash_calls_the_loader_and_swallows_its_errors(pyi_splash):
    splash.close_splash()
    assert pyi_splash.calls == [1]
    pyi_splash.fail = RuntimeError("already closed")
    splash.close_splash()                                     # no exception
    assert pyi_splash.calls == [1]


# ---------------------------------------------------------------- gui.launch

class FakeRoot:
    def __init__(self, log):
        self.log = log

    def update(self):
        self.log.append("update")


class FakeApp:
    """Stands in for gui.App: no Tk, just the order of events."""
    log: list = []
    files = None

    def __init__(self, initial_files=None):
        FakeApp.files = initial_files
        self.log = FakeApp.log
        self.log.append("init")
        self.root = FakeRoot(self.log)

    def mainloop(self):
        self.log.append("mainloop")


@pytest.fixture
def fake_app(monkeypatch):
    FakeApp.log = []
    monkeypatch.setattr(gui, "App", FakeApp)
    preloaded = threading.Event()
    monkeypatch.setattr(cover, "preload_heavy", preloaded.set)
    return FakeApp, preloaded


def test_launch_closes_the_picture_after_the_window_is_drawn(fake_app, pyi_splash):
    FakeApp, preloaded = fake_app
    pyi_splash.close = lambda: FakeApp.log.append("close")
    gui.launch(["a.txt"])
    assert FakeApp.log == ["init", "update", "close", "mainloop"]
    assert FakeApp.files == ["a.txt"]
    assert preloaded.wait(5), "Pillow was not preloaded on a background thread"


def test_launch_closes_the_picture_when_the_window_cannot_be_built(fake_app, pyi_splash):
    FakeApp, preloaded = fake_app

    def boom(initial_files=None):
        raise RuntimeError("no display")

    gui.App = boom
    with pytest.raises(RuntimeError, match="no display"):
        gui.launch()
    assert pyi_splash.calls == [1], "the error must not stay hidden behind the picture"
    assert not preloaded.is_set()


def test_launch_without_pyinstaller_still_runs(fake_app, monkeypatch):
    FakeApp, _ = fake_app
    monkeypatch.setitem(sys.modules, "pyi_splash", None)
    gui.launch()
    assert FakeApp.log == ["init", "update", "mainloop"]


# ---------------------------------------------------------------- CLI path

def test_cli_run_closes_the_picture_before_converting(monkeypatch, tmp_path, pyi_splash):
    monkeypatch.setattr(i18n, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    order = []
    pyi_splash.close = lambda: order.append("close")
    monkeypatch.setattr(cli, "run_cli", lambda args: order.append("cli") or 0)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert cli.main([str(tmp_path / "x.txt"), "--ui-lang", "en"]) == 0
    assert order == ["close", "cli"]


def test_gui_path_does_not_close_the_picture_itself(monkeypatch, tmp_path, pyi_splash):
    """gui.launch closes it after the window; main() must not close it earlier."""
    monkeypatch.setattr(i18n, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    launched = []
    monkeypatch.setattr(gui, "launch", lambda files=None: launched.append(files))
    assert cli.main(["--gui", "--ui-lang", "en"]) == 0
    assert launched == [None]
    assert pyi_splash.calls == []


# ---------------------------------------------------------------- deferred Pillow

def test_pillow_is_not_imported_until_a_cover_is_needed(deferred):
    assert isinstance(cover.Image, cover._Deferred)
    assert isinstance(cover.ImageFont, cover._Deferred)
    img = cover.make_cover("Book", "Author", "en")
    assert img.width == cover.COVER_W and img.data[:2] == b"\xff\xd8"
    assert isinstance(cover.Image, types.ModuleType), "the stand-in was not replaced"
    assert isinstance(cover.ImageDraw, types.ModuleType)
    assert cover._heavy_loaded


def test_stand_in_attribute_access_loads_pillow(deferred):
    new = cover.Image.new          # first attribute read on the stand-in
    assert callable(new)
    assert isinstance(cover.Image, types.ModuleType)


def test_load_cover_works_from_the_stand_in(deferred, tmp_path):
    cover.load_heavy()
    p = tmp_path / "c.png"
    cover.Image.new("RGB", (700, 1000), (1, 2, 3)).save(p)
    # back to the stand-ins: a user who picked a cover file right after the window opened
    cover._heavy_loaded = False
    cover.Image = cover._Deferred("Image")
    img = cover.load_cover(str(p))
    assert (img.width, img.height, img.media_type) == (700, 1000, "image/png")


def test_a_conversion_during_the_preload_waits_and_gets_the_same_cover(deferred):
    """The window is up, Pillow is loading in the background, the user clicks Convert."""
    gate = threading.Event()

    # the preload thread takes the lock first and holds it (a slow disk); make_cover must wait, not fail
    def preload():
        with cover._heavy_lock:
            gate.wait(5)
            from PIL import Image, ImageDraw, ImageFont
            cover.Image, cover.ImageDraw, cover.ImageFont = Image, ImageDraw, ImageFont
            cover._heavy_loaded = True

    t = threading.Thread(target=preload, name="preload", daemon=True)
    t.start()
    result: dict = {}

    def convert():
        result["img"] = cover.make_cover("Same Book", "Same Author", "en")

    c = threading.Thread(target=convert, daemon=True)
    c.start()
    c.join(0.3)
    assert c.is_alive(), "make_cover did not wait for the preload"
    gate.set()
    c.join(10)
    t.join(10)
    assert not c.is_alive() and "img" in result
    again = cover.make_cover("Same Book", "Same Author", "en")
    assert result["img"].data == again.data


def test_preload_heavy_swallows_a_failed_import(monkeypatch, deferred):
    def fail():
        raise ImportError("DLL load failed")

    monkeypatch.setattr(cover, "load_heavy", fail)
    cover.preload_heavy()           # no exception on the background thread
    monkeypatch.undo()
    cover.load_heavy()              # the real use tries again and succeeds
    assert isinstance(cover.Image, types.ModuleType)


def test_load_heavy_is_safe_from_many_threads_at_once(deferred):
    errors = []

    def go():
        try:
            cover.load_heavy()
            cover.Image.new("RGB", (2, 2))
        except Exception as exc:  # pragma: no cover - the assertion below reports it
            errors.append(exc)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert errors == []
    assert isinstance(cover.Image, types.ModuleType)


# ---------------------------------------------------------------- the picture file and build

def test_splash_png_is_small_and_the_build_uses_it():
    png = os.path.join(ROOT, "assets", "splash.png")
    assert os.path.isfile(png)
    assert os.path.getsize(png) < 20_000, "keep the picture small: it is shown before anything is unpacked"
    with open(png, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    with open(os.path.join(ROOT, "build.bat"), encoding="utf-8") as f:
        bat = f.read()
    assert "--splash assets/splash.png" in bat
