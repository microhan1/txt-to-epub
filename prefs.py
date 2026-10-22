"""Small settings.json values with type checking (the conversion options are
handled by gui._saved_options). The file sits next to the exe where anyone can
edit it, so nothing in it is trusted: a wrong type falls back to the default.
"""
from __future__ import annotations

import dataclasses

import i18n

MERGE_MODES = ("each", "one")


@dataclasses.dataclass
class Prefs:
    update_check: bool = True  # once a day, ask the tools site whether a newer version exists
    update_check_last: str = ""  # YYYY-MM-DD of the last check the server answered
    update_check_skipped: str = ""  # "Later" was pressed for this version: do not show it again
    merge_mode: str = "each"  # "each": one EPUB per file; "one": all files into one book


def load() -> Prefs:
    raw = i18n.load_settings()
    default = Prefs()

    def typed(key: str, kind: type):
        value = raw.get(key)
        ok = isinstance(value, kind) and (kind is bool or not isinstance(value, bool))
        return value if ok else getattr(default, key)

    return Prefs(
        update_check=typed("update_check", bool),
        update_check_last=typed("update_check_last", str).strip()[:10],
        update_check_skipped=typed("update_check_skipped", str).strip()[:32],
        merge_mode=typed("merge_mode", str) if typed("merge_mode", str) in MERGE_MODES else "each",
    )


def save(p: Prefs) -> None:
    settings = i18n.load_settings()
    settings.update(dataclasses.asdict(p))
    i18n.save_settings(settings)
