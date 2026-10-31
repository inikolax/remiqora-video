"""Krea 2's LoRA (from krea2-ui app/loras.py): what lies in KREA_LORA_DIRS and whether it fits Krea 2.

Only the safetensors header is read, never the weights. Verdict per file:
  ok       a plain LoRA (lora_A/lora_B or lora_down/lora_up) with Krea 2's layer names and width, or a LoKr (the
           worker's ComfyUI applies it; checked on 15 real ones)
  warn     may work, may not: DoRA, LoHa, or the names / width don't look like Krea 2 - allowed, the picture's note
           says how many tensors were really applied
  blocked  not a LoRA at all (full weights) or a broken file
The worker sees KREA_LORA_DIRS with its other LoRA folders (engine/worker.model_folders); picture.py names a LoRA
the way it lists them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config, lora_prefs
from .loras import _find_preview, _sidecar_trigger, read_header
from . import i18n

HIDDEN = 6144       # Krea 2's width: the input side of attn.wq / wk / wv / gate
TXT_HIDDEN = 2560   # the text-fusion blocks' width (Qwen3-VL 4B)
_KREA_KEY = re.compile(r"blocks[._]\d+[._]attn[._](wq|wk|wv|wo|gate)\b")   # dotted (ai-toolkit) or kohya's underscores
_LORA_SUFFIX = re.compile(r"\.(lora_A|lora_B|lora_down|lora_up)(\.weight)?$")
_META_TRIGGERS = ("modelspec.trigger_phrase", "trigger_word", "trigger_words", "trigger", "ss_trigger_word")


@dataclass
class KreaLora:
    id: str                   # "d<dir index>/<path under it>"
    name: str
    folder: str
    path: Path
    size_mb: float
    mtime: float
    kind: str = "lora"        # lora | lokr | loha | dora | weights | unreadable
    verdict: str = "ok"       # ok | warn | blocked
    notes: tuple[str, str] = ("", "")   # (ru, en): the verdict's explanation; `note` - in the interface's language
    rank: Optional[int] = None
    trigger: str = ""
    preview: Optional[Path] = None

    @property
    def note(self) -> str:
        return i18n.L(*self.notes)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "folder": self.folder, "size_mb": self.size_mb, "kind": self.kind,
                "verdict": self.verdict, "note": self.note, "rank": self.rank, "trigger": self.trigger,
                "strength": lora_prefs.strength(self.id, "krea"),
                "preview": f"/api/krea/loras/preview?id={self.id}&v={int(self.mtime)}" if self.preview else None}


def inspect(path: Path, info: KreaLora) -> KreaLora:
    info.preview, info.trigger = _find_preview(path), _sidecar_trigger(path)
    try:
        header = read_header(path)
    except Exception as e:  # noqa: BLE001 - any broken file is just reported
        info.kind, info.verdict, info.notes = "unreadable", "blocked", (f"Не читается как safetensors ({e})", f"Can't be read as safetensors ({e})")
        return info
    meta = header.pop("__metadata__", None) or {}
    for k in _META_TRIGGERS:
        if not info.trigger and meta.get(k):
            info.trigger = str(meta[k])
    keys = list(header)
    has = lambda s: any(s in k for k in keys)  # noqa: E731
    for k in keys:   # the rank: the small side of a lora_A / lora_down
        if k.endswith(("lora_A.weight", "lora_down.weight")):
            info.rank = min(header[k]["shape"])
            break
    if has("lokr_w"):
        info.kind = "lokr"
    elif not (has("lora_A") or has("lora_B") or has("lora_down") or has("lora_up") or has("hada_w")):
        info.kind, info.verdict = "weights", "blocked"
        info.notes = ("Это не LoRA, а полные веса модели: их кладут в папку весов Krea, не сюда.", "This is not a LoRA but full model weights: they go in the Krea weights folder, not here.")
    elif has("hada_w"):
        info.kind, info.verdict, info.notes = "loha", "warn", ("LoHa: на Krea 2 не проверено, может не примениться.", "LoHa: not tested on Krea 2, may not apply.")
    elif has("dora_scale") or has(".magnitude") or has("lora_magnitude_vector"):
        info.kind, info.verdict = "dora", "warn"
        info.notes = ("DoRA: применится только LoRA-часть — эффект слабее или другой.", "DoRA: only the LoRA part will apply - the effect is weaker or different.")
    elif not any(_KREA_KEY.search(k) for k in keys):
        info.verdict, info.notes = "warn", ("Имена слоёв не похожи на Krea 2 (нет attn.wq / wk / wv): возможно, LoRA от другой модели.", "The layer names don't look like Krea 2 (no attn.wq / wk / wv): maybe a LoRA for another model.")
    else:
        for k in keys:   # the q-projections' width: 6144 in the main blocks, 2560 in the text-fusion ones
            if re.search(r"attn[._]wq[._](lora_A|lora_down)", k):
                want = TXT_HIDDEN if "txtfusion" in k else HIDDEN
                if header[k]["shape"][-1] != want:
                    info.verdict = "warn"
                    info.notes = (f"Ширина слоя {header[k]['shape'][-1]}, у Krea 2 — {want}: похоже на другую модель.", f"Layer width {header[k]['shape'][-1]}, Krea 2 has {want}: looks like another model.")
                    break
    return info


class Library:
    """The KREA_LORA_DIRS; a file is read again only when its time changes."""

    def __init__(self) -> None:
        self._cache: dict[str, KreaLora] = {}

    def scan(self) -> list[KreaLora]:
        out, seen = [], set()
        for i, root in enumerate(config.KREA_LORA_DIRS):
            if not root.is_dir():
                continue
            for p in sorted(root.rglob("*.safetensors"), key=lambda q: str(q).lower()):
                rel = p.relative_to(root)
                lid = f"d{i}/{rel.as_posix()}"
                seen.add(lid)
                st = p.stat()
                c = self._cache.get(lid)
                if not (c and c.mtime == st.st_mtime and c.path == p):
                    c = inspect(p, KreaLora(id=lid, name=p.stem, folder=rel.parent.as_posix() if rel.parent != Path(".") else "",
                                           path=p, size_mb=round(st.st_size / 2**20, 1), mtime=st.st_mtime))
                    self._cache[lid] = c
                c.preview = _find_preview(p)   # a preview can come after the LoRA itself
                out.append(c)
        for gone in set(self._cache) - seen:
            del self._cache[gone]
        return out

    def get(self, lid: str) -> Optional[KreaLora]:
        if lid not in self._cache:
            self.scan()
        return self._cache.get(lid)


LIBRARY = Library()


def resolve(items: list[dict]) -> list[tuple[KreaLora, float]]:
    """[{id, strength}] -> the LoRA and their strengths; a missing or blocked one is an error (a picture silently
    without the LoRA the user asked for is worse)."""
    from .engine.comfy import EngineError
    out = []
    for it in items or []:
        info = LIBRARY.get(str(it.get("id") or ""))
        if not info:
            raise EngineError(i18n.L(f"LoRA Krea не найдена: {it.get('name') or it.get('id')}", f"Krea LoRA not found: {it.get('name') or it.get('id')}"))
        if info.verdict == "blocked":
            raise EngineError(i18n.L(f"LoRA «{info.name}» нельзя использовать: {info.note}", f"LoRA «{info.name}» can't be used: {info.note}"))
        out.append((info, max(-30.0, min(30.0, float(it.get("strength", 0.8))))))
    return out
