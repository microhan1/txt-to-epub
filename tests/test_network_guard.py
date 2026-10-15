"""The guard in conftest.py itself: with no fetcher/opener given, nothing leaves."""
from __future__ import annotations

import os
import sys
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import conftest  # noqa: E402  (tests/conftest.py, importable because pytest adds tests/ to sys.path)
import prefs as prefs_mod  # noqa: E402
import update_check as uc  # noqa: E402


def test_defaults_are_the_guard_and_a_bare_fetch_is_recorded_and_silent():
    assert urllib.request.urlopen is conftest.guarded_urlopen
    assert uc.fetch.__kwdefaults__["opener"] is conftest.guarded_urlopen
    assert uc.check_async.__kwdefaults__["fetcher"] is conftest.no_fetch

    assert uc.fetch("txttoepub", "0.1.2") is None  # no opener given -> the guard, URLError -> None
    assert len(conftest._attempts) == 1 and "chaekgalpi.co.kr/api/tools/txttoepub/latest" in conftest._attempts[0]
    conftest._attempts.clear()  # otherwise this very test fails in teardown, which is the point of the guard


def test_check_async_without_a_fetcher_never_asks_the_server():
    class Root:
        def after(self, ms, fn):
            fn()

    class InlineThread:
        def __init__(self, target, name=None, daemon=None):
            self.target = target

        def start(self):
            self.target()

    real_thread = uc.threading.Thread
    uc.threading.Thread = InlineThread
    try:
        answered = []
        uc.check_async(Root(), "txttoepub", "0.1.2", prefs_mod.Prefs(), lambda info, ok: answered.append((info, ok)),
                       day="2026-10-15")
    finally:
        uc.threading.Thread = real_thread
    assert answered == [(None, False)]  # "server did not answer": no notice, day not recorded
    assert conftest._attempts == []


def test_a_test_that_reaches_the_server_is_failed():
    """Simulate a leak and check the teardown check would fail that test."""
    conftest._attempts.append("https://chaekgalpi.co.kr/api/tools/txttoepub/latest?v=0.1.2&os=win")
    with pytest.raises(pytest.fail.Exception):
        conftest.fail_if_attempted("tests/test_x.py::test_leak")
    assert conftest._attempts == []  # cleared, so this test's own teardown passes
