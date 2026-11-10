"""Time how long the built exe takes to show its start-up picture and its window.

    python tools/measure_startup.py <exe> [runs=3] [--shot picture.png]

Prints one row per run: seconds from launch until the start-up picture appears, until
the program window exists (window handle created), and until the picture is gone;
plus the most taskbar entries seen at once, whether a picture window was left over
1.5 s after the program window came up, and how many _MEI* folders remain.

Safety: HTTP(S)_PROXY point at a dead port, so the start-up update check cannot reach
the Chaekgalpi server; APPDATA/LOCALAPPDATA/TEMP point at a throw-away folder, so the
user's own settings are untouched and the _MEI* folders left by the forced kill are
removed with that folder. Only windows of the launched process tree are counted - a
copy of the program the user has open is ignored.

The exe is run where it is, not from a fresh copy: Windows scans a newly written 32 MB
exe before its first start (15-20 s here), which would be measured instead of the
program. The process is killed before it can write settings.json beside the exe.

Window classification: a visible top-level window with a title bar (WS_CAPTION) whose
title is one of the four app titles is the program window; a visible window without a
title bar is the start-up picture (PyInstaller's splash is a plain Tk window titled
"tk" with no caption).
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLES = set()
for _lang in ("ko", "en", "ja", "zh-CN"):
    with open(os.path.join(ROOT, "lang", f"{_lang}.json"), encoding="utf-8") as _f:
        TITLES.add(json.load(_f)["app_title"])

DEAD_PROXY = "http://127.0.0.1:9"
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.SetProcessDPIAware()
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION, WS_EX_TOOLWINDOW = 0x00C00000, 0x00000080
GW_OWNER = 4
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindow.restype = wintypes.HWND
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE


class PE(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


def family(root_pid: int) -> set[int]:
    """root_pid and its descendants (the one-file exe runs the program in a child)."""
    snap = kernel32.CreateToolhelp32Snapshot(2, 0)
    pe = PE()
    pe.dwSize = ctypes.sizeof(PE)
    parents = {}
    ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        parents[pe.th32ProcessID] = pe.th32ParentProcessID
        ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
    kernel32.CloseHandle(snap)
    found, grew = {root_pid}, True
    while grew:
        grew = False
        for pid, parent in parents.items():
            if parent in found and pid not in found:
                found.add(pid)
                grew = True
    return found


def windows_of(pids: set[int]) -> list[dict]:
    out: list[dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append(dict(hwnd=hwnd, title=buf.value, caption=(style & WS_CAPTION) == WS_CAPTION,
                            taskbar=not (ex & WS_EX_TOOLWINDOW) and not user32.GetWindow(hwnd, GW_OWNER),
                            size=(r.right - r.left, r.bottom - r.top)))
        return True

    user32.EnumWindows(cb, 0)
    return out


def shot(hwnd: int, path: str) -> None:
    """What is really on screen. The picture window is not DPI-aware, so PrintWindow would
    miss the scaling; grab the screen area instead."""
    from PIL import ImageGrab
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    ImageGrab.grab((r.left, r.top, r.right, r.bottom), all_screens=True).save(path)


def measure(exe: str, limit: float = 60.0, shot_path: str | None = None) -> dict:
    root = tempfile.mkdtemp(prefix="txt2epub_measure_")
    tmp = os.path.join(root, "tmp")
    appdata = os.path.join(root, "appdata")
    os.makedirs(tmp)
    os.makedirs(appdata)
    env = dict(os.environ, HTTP_PROXY=DEAD_PROXY, HTTPS_PROXY=DEAD_PROXY, http_proxy=DEAD_PROXY,
               https_proxy=DEAD_PROXY, NO_PROXY="", no_proxy="", APPDATA=appdata, LOCALAPPDATA=appdata,
               TEMP=tmp, TMP=tmp)
    res: dict = dict(splash=None, window=None, splash_gone=None, tasks_max=0, tasks_after=None,
                     leftover=None, mei=0, splash_info=None)
    t0 = time.perf_counter()
    proc = subprocess.Popen([exe], env=env, cwd=root)
    try:
        pids, last_family, settled = family(proc.pid), 0.0, None
        while time.perf_counter() - t0 < limit:
            now = time.perf_counter() - t0
            if now - last_family > 0.1:
                pids, last_family = family(proc.pid), now
            ws = windows_of(pids)
            plain = [w for w in ws if not w["caption"]]
            main = [w for w in ws if w["caption"] and w["title"] in TITLES]
            res["tasks_max"] = max(res["tasks_max"], sum(w["taskbar"] for w in ws))
            if plain and res["splash"] is None:
                res["splash"], res["splash_info"] = now, plain[0]
                if shot_path:
                    time.sleep(0.15)
                    shot(plain[0]["hwnd"], shot_path)
            if main and res["window"] is None:
                res["window"] = settled = now
            if res["window"] is not None and not plain and res["splash_gone"] is None:
                res["splash_gone"] = now
            if settled is not None and now - settled > 1.5:          # the picture 1.5 s after the window
                res["tasks_after"] = sum(w["taskbar"] for w in ws)
                res["leftover"] = len(plain)
                break
            time.sleep(0.01)
        res["mei"] = len([d for d in os.listdir(tmp) if d.startswith("_MEI")])
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        time.sleep(1.0)
        shutil.rmtree(root, ignore_errors=True)   # the _MEI* left by the kill live only in this folder
    return res


def fmt(v) -> str:
    return f"{v:.2f}" if isinstance(v, float) else "-"


def main() -> None:
    args = sys.argv[1:]
    shot_path = None
    if "--shot" in args:
        i = args.index("--shot")
        shot_path = args[i + 1]
        del args[i:i + 2]
    exe = args[0]
    n = int(args[1]) if len(args) > 1 else 3
    print(f"{exe}  ({os.path.getsize(exe) / 1024 / 1024:.1f} MB)")
    print("run | picture (s) | window (s) | picture gone (s) | taskbar max | taskbar after | leftover picture | _MEI")
    rows = []
    for k in range(1, n + 1):
        r = measure(exe, shot_path=shot_path if k == 1 else None)
        rows.append(r)
        print(f"{k} | {fmt(r['splash'])} | {fmt(r['window'])} | {fmt(r['splash_gone'])} | {r['tasks_max']} | "
              f"{r['tasks_after']} | {r['leftover']} | {r['mei']}", flush=True)
        if r["splash_info"]:
            i = r["splash_info"]
            print(f"    picture window: title={i['title']!r} taskbar={i['taskbar']} size={i['size']}", flush=True)
    win = [r["window"] for r in rows if r["window"]]
    spl = [r["splash"] for r in rows if r["splash"]]
    if win:
        line = f"average: window {sum(win) / len(win):.2f} s"
        if spl:
            line += f" / picture {sum(spl) / len(spl):.2f} s"
        print(line)


if __name__ == "__main__":
    main()
