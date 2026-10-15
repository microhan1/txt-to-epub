"""No test may reach the production server.

Why this exists: in another Chaekgalpi tool the GUI tests created the App, and
1.5 s later check_async really asked chaekgalpi.co.kr for the latest version -
51 requests per test run, 511 over two days, all counted as real users. Module
attribute patches (update_check.fetch = fake) do not help: `fetch(opener=urlopen)`
and `check_async(fetcher=fetch)` bind their defaults at definition time. So the
defaults themselves and urllib.request.urlopen are replaced here, for every test,
and a test that still tries to reach the server fails in teardown.

Tests that want a server reply pass their own `fetcher=`/`opener=` as before.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import update_check as uc  # noqa: E402

BLOCKED_HOST = "chaekgalpi.co.kr"
_attempts: list[str] = []          # URLs that tried to leave during the current test
_real_urlopen = urllib.request.urlopen


def guarded_urlopen(req, *args, **kwargs):
    """Records and refuses anything for the tools site; everything else is refused
    too (tests have no business on the network), but only the tools site is counted."""
    url = str(getattr(req, "full_url", req))
    if BLOCKED_HOST in url:
        _attempts.append(url)
    raise urllib.error.URLError(f"network blocked in tests: {url}")


def no_fetch(slug: str, version: str) -> None:
    """check_async's default fetcher under test: as if the server never answered."""
    return None


# Installed once at import, before any test module runs, and kept for the whole
# session: these are definition-time defaults, so a per-test monkeypatch would
# leave a window during collection.
urllib.request.urlopen = guarded_urlopen
uc.fetch.__kwdefaults__["opener"] = guarded_urlopen
uc.check_async.__kwdefaults__["fetcher"] = no_fetch


@pytest.fixture(autouse=True)
def no_production_requests(request):
    """Fails the test if anything tried to reach the production server."""
    _attempts.clear()
    # re-assert every test, in case a test replaced them and forgot to restore
    urllib.request.urlopen = guarded_urlopen
    uc.fetch.__kwdefaults__["opener"] = guarded_urlopen
    uc.check_async.__kwdefaults__["fetcher"] = no_fetch
    yield
    fail_if_attempted(request.node.nodeid)


def fail_if_attempted(nodeid: str) -> None:
    if _attempts:
        urls = '; '.join(_attempts)
        _attempts.clear()
        pytest.fail(f'{nodeid} tried to reach {BLOCKED_HOST}: {urls}', pytrace=False)
