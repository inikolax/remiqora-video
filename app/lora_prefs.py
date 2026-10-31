"""A LoRA's own strength: the one it takes when it is added to a scene or a node (the «LoRA» tab of a model's card). Kept in
data/lora_strength.json by the model and the file's path under its folder, not by the id: an id holds the folder's place
in the list (d0/, d1/), which moves when the folders do. A LoRA nobody set takes DEFAULT."""
from __future__ import annotations

import json
import threading

from . import config

DEFAULT = 0.8
LO, HI = -5.0, 5.0
_FILE = config.DATA_DIR / "lora_strength.json"
_lock = threading.Lock()


def key(model: str, rel: str) -> str:
    """`rel` is the path under its LoRA folder (an id without its model and d<N>/)."""
    return f"{model}:{rel.replace(chr(92), '/').lower()}"


def key_of(lid: str, model: str) -> str:
    rest = lid.split(":", 1)[1] if ":" in lid else lid
    return key(model, rest.split("/", 1)[1] if "/" in rest else rest)


def _read() -> dict[str, float]:
    try:
        return {str(k): float(v) for k, v in json.loads(_FILE.read_text("utf-8")).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def get(lid: str, model: str) -> float | None:
    """The strength set for this LoRA, or None (it takes DEFAULT)."""
    return _read().get(key_of(lid, model))


def strength(lid: str, model: str) -> float:
    v = get(lid, model)
    return DEFAULT if v is None else v


def set_(lid: str, model: str, strength: float | None) -> None:
    with _lock:
        data = _read()
        k = key_of(lid, model)
        if strength is None:
            data.pop(k, None)
        else:
            data[k] = round(min(HI, max(LO, float(strength))), 2)
        _FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")
