"""The start-up picture of the one-file exe (PyInstaller --splash assets/splash.png).

The picture is shown by the exe loader while the archive is unpacked and Python
starts; the program closes it once its window is drawn. Run from Python there is
no pyi_splash module and close_splash() does nothing.
"""
from __future__ import annotations


def close_splash() -> None:
    """Close the start-up picture. Never raises: without PyInstaller the module is
    missing, and a loader that already closed it must not break the program."""
    try:
        import pyi_splash  # type: ignore[import-not-found]  # only exists inside the built exe

        pyi_splash.close()
    except Exception:
        pass
