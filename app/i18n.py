"""Two languages, as in Remiqora: the interface's (ru / en - the page's switch in the header) and the texts' (any of
LANGS - «Модели и настройки»): the language the user writes ideas and reads scenes in, which the writer writes the
scene texts in and the translator goes from / to. Prompts for the video models stay English whatever both are.

The server's messages follow the interface: L("…", "…") picks the Russian or the English one - for a request by its
X-Lang header (api.ts sends the page's), for a job running in the background by the language last chosen (kept in
data/lang.json with the texts' one).
"""
from __future__ import annotations

import contextvars
import json
from typing import Optional

from . import config

FILE = config.DATA_DIR / "lang.json"
UI = ("ru", "en")
# the texts' languages: code -> (its own name, the English name the writer and the translator are told)
LANGS: dict[str, tuple[str, str]] = {
    "ru": ("Русский", "Russian"), "en": ("English", "English"), "uk": ("Українська", "Ukrainian"),
    "be": ("Беларуская", "Belarusian"), "kk": ("Қазақша", "Kazakh"), "de": ("Deutsch", "German"),
    "fr": ("Français", "French"), "es": ("Español", "Spanish"), "it": ("Italiano", "Italian"),
    "pt": ("Português", "Portuguese"), "pl": ("Polski", "Polish"), "cs": ("Čeština", "Czech"),
    "nl": ("Nederlands", "Dutch"), "tr": ("Türkçe", "Turkish"), "zh": ("中文", "Chinese"),
    "ja": ("日本語", "Japanese"), "ko": ("한국어", "Korean"),
}

_request_ui: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("ui_lang", default=None)
_saved: Optional[dict] = None


def _load() -> dict:
    global _saved
    if _saved is None:
        try:
            _saved = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _saved = {}
    return _saved


def get() -> dict:
    """{ui, text}: the interface's language and the texts' (by default the interface's)."""
    s = _load()
    ui = s.get("ui") if s.get("ui") in UI else "ru"
    return {"ui": ui, "text": s.get("text") if s.get("text") in LANGS else ui}


def save(ui: Optional[str] = None, text: Optional[str] = None) -> dict:
    s = dict(_load())
    if ui is not None:
        if ui not in UI:
            raise ValueError(L("Язык интерфейса: ru или en", "Interface language: ru or en"))
        s["ui"] = ui
    if text is not None:
        if text not in LANGS:
            raise ValueError(L("Нет такого языка текстов", "No such text language"))
        s["text"] = text
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    global _saved
    _saved = s
    return get()


def ui() -> str:
    return _request_ui.get() or get()["ui"]


def L(ru: str, en: str) -> str:
    """The message in the interface's language."""
    return en if ui() == "en" else ru


def text() -> str:
    """The texts' language code (ru, en, de…)."""
    return get()["text"]


def text_name(code: Optional[str] = None) -> str:
    """The texts' language as the writer and the translator are told it: Russian, German…"""
    return LANGS.get(code or text(), LANGS["ru"])[1]


def plan_lang(plan: Optional[dict]) -> str:
    """The language a video's texts and spoken lines are in: set when it is written (plan["lang"]); a plan written
    before has none and is Russian - its prompts, and so its shots' keys, stay word for word what they were."""
    code = (plan or {}).get("lang")
    return code if code in LANGS else "ru"


def plan_lang_name(plan: Optional[dict]) -> str:
    return text_name(plan_lang(plan))


def set_request(lang: Optional[str]) -> contextvars.Token:
    return _request_ui.set(lang if lang in UI else None)


def reset_request(token: contextvars.Token) -> None:
    _request_ui.reset(token)
