"""The LoRA folders: what lies in them and whether ComfyUI can put it on the model it is for.

Each model has its own folders, as H3 always had (2026-10-23, the user: «для H3 LoRA просто кладутся в папку, нужно так
же для LTX»): H3 - LORA_DIRS, LTX 2.3 - LTX23_LORA_DIRS, LTX 2.5 - LTX25_LORA_DIRS (a LoRA of one LTX does not fit the
other: other weights), WAN 2.2 5B - WAN_LORA_DIRS. A LoRA's id says whose it is: H3's as they always were (d0/name.safetensors), another
model's with its id in front (ltx23:d0/name.safetensors); a scene shoots only with the LoRA of its own model.

Only the safetensors header is read, never the weights. H3 layer names: blocks.N.attn.qkv_proj / out_proj and
blocks.N.mlp.fc1 / fc2, model width 5376. ComfyUI maps both key styles seen in the wild:
`diffusion_model.blocks.0.attn.qkv_proj.lora_A.weight` (+ .alpha) and PEFT's `blocks.25.attn.qkv_proj.lora_A.default.weight`.
Verdict per file:
  ok       a plain LoRA with H3 layer names and width
  warn     may work, may not (LoKr / LoHa / DoRA on H3 untested, or the names / width don't look like H3)
  blocked  not a LoRA at all
"""
from __future__ import annotations

import json
import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config, i18n

HIDDEN = 5376   # H3's width: the input side of attn.qkv_proj and mlp.fc1
PREVIEW_EXT = (".png", ".jpg", ".jpeg", ".webp")
_H3_KEY = re.compile(r"blocks\.\d+\.(attn\.(qkv_proj|out_proj)|mlp\.(fc1|fc2))\.")
_IN_KEY = re.compile(r"blocks\.\d+\.(attn\.qkv_proj|mlp\.fc1)\.(lora_A|lora_down)(\.default)?\.weight$")
_LORA_SUFFIX = re.compile(r"\.(lora_A|lora_B|lora_down|lora_up)(\.default)?(\.weight)?$")
_META_TRIGGERS = ("modelspec.trigger_phrase", "trigger_word", "trigger_words", "trigger", "ss_trigger_word")


@dataclass
class LoraInfo:
    id: str
    name: str                 # file name without extension
    folder: str               # sub-folder under its LoRA dir ("" = the dir itself)
    path: Path
    comfy_name: str           # how ComfyUI lists it: the path relative to its LoRA dir
    size_mb: float
    mtime: float
    kind: str = "lora"        # lora | lokr | loha | dora | weights | unreadable
    verdict: str = "ok"       # ok | warn | blocked
    notes: tuple[str, str] = ("", "")   # (ru, en): the verdict's explanation; `note` - in the interface's language
    rank: Optional[int] = None
    layers: int = 0
    blocks: int = 0           # how many of the transformer blocks it touches
    base: str = ""            # what the file says it was trained on
    trigger: str = ""
    preview: Optional[Path] = None
    model: str = "h3"         # whose folders it lies in
    v2v: bool = False         # reads a clip and makes it again («Видео → видео», v2v.py): never a scene's LoRA
    ref_down: int = 1         # an IC-LoRA's reference_downscale_factor: the clip goes in at 1/n of the result's size

    @property
    def note(self) -> str:
        return i18n.L(*self.notes)


def read_header(path: Path) -> dict:
    with open(path, "rb") as f:
        (n,) = struct.unpack("<Q", f.read(8))
        if n > 200_000_000:
            raise ValueError("header too large")
        return json.loads(f.read(n))


def _find_preview(path: Path) -> Optional[Path]:
    for ext in PREVIEW_EXT:
        for cand in (path.with_suffix(ext), path.with_name(path.stem + ".preview" + ext)):
            if cand.exists():
                return cand
    return None


def _sidecar_trigger(path: Path) -> str:
    """Civitai Helper (`.civitai.info`) or a plain `<name>.json` with trainedWords."""
    for cand in (path.with_name(path.stem + ".civitai.info"), path.with_suffix(".json")):
        try:
            words = json.loads(cand.read_text(encoding="utf-8")).get("trainedWords")
        except (OSError, ValueError, AttributeError):
            continue
        if words:
            return ", ".join(map(str, words))
    return ""


def inspect(path: Path, info: LoraInfo) -> LoraInfo:
    """The file's kind and whether it fits its folder's model (H3 by layer names and width, LTX by layer names)."""
    info.preview, info.trigger = _find_preview(path), _sidecar_trigger(path)
    try:
        header = read_header(path)
    except Exception as e:  # noqa: BLE001 - any broken file is just reported
        info.kind, info.verdict, info.notes = "unreadable", "blocked", (f"Не читается как safetensors ({e})", f"Does not read as safetensors ({e})")
        return info

    meta = header.pop("__metadata__", None) or {}
    info.base = str(meta.get("base_model") or meta.get("ss_base_model_version") or meta.get("modelspec.architecture") or "")
    for k in _META_TRIGGERS:
        if not info.trigger and meta.get(k):
            info.trigger = str(meta[k])
    from . import v2v
    info.v2v = v2v.is_v2v(path, info.model, meta)
    info.ref_down = v2v.ref_down(meta)

    keys = list(header)
    has = lambda s: any(s in k for k in keys)  # noqa: E731
    info.layers = len({_LORA_SUFFIX.sub("", k) for k in keys if _LORA_SUFFIX.search(k)})
    info.blocks = len({m.group(0).split(".")[1] for k in keys if (m := re.search(r"blocks\.\d+\.", k))})
    for k in keys:   # the rank: the small side of a lora_A / lora_down
        if _LORA_SUFFIX.search(k) and ("lora_A" in k or "lora_down" in k):
            info.rank = min(header[k]["shape"])
            break

    h3 = sum(1 for k in keys if _H3_KEY.search(k))
    who = {"h3": "H3", "wan5b": "WAN", "flux2": "FLUX.2"}.get(info.model, "LTX")
    if has("lokr_w"):
        info.kind, info.verdict, info.notes = "lokr", "warn", (f"LoKr: на {who} не проверено.", f"LoKr: not tested on {who}.")
    elif has("hada_w"):
        info.kind, info.verdict, info.notes = "loha", "warn", (f"LoHa: на {who} не проверено.", f"LoHa: not tested on {who}.")
    elif not any(_LORA_SUFFIX.search(k) for k in keys):
        info.kind, info.verdict = "weights", "blocked"
        info.notes = ("Это не LoRA, а полные веса модели. Такой файл кладут в папку моделей, не сюда.",
                      "This is not a LoRA but a model's full weights. Such a file goes into the models folder, not here.")
    elif has("dora_scale") or has(".magnitude") or has("lora_magnitude_vector"):
        info.kind, info.verdict, info.notes = "dora", "warn", (f"DoRA: на {who} не проверено.", f"DoRA: not tested on {who}.")
    elif info.model == "flux2":   # FLUX.2 Klein: Flux's double_blocks / single_blocks, or diffusers' single_transformer_blocks
        if not (has("double_blocks") or has("single_blocks") or has("single_transformer_blocks")):
            info.verdict = "warn"
            info.notes = ("Имена слоёв не похожи на FLUX.2 (нет double_blocks / single_blocks). Скорее всего, LoRA от другой модели.",
                          "The layer names don't look like FLUX.2 (no double_blocks / single_blocks). Most likely a LoRA for another model.")
    elif info.model == "wan5b":
        if not (has("self_attn") or has("cross_attn")):
            info.verdict = "warn"
            info.notes = ("Имена слоёв не похожи на WAN (нет self_attn / cross_attn). Скорее всего, LoRA от другой модели.",
                          "The layer names don't look like WAN (no self_attn / cross_attn). Most likely a LoRA for another model.")
        elif re.search(r"14b|a14b", path.name, re.I):
            info.verdict, info.notes = "warn", ("Похоже на LoRA для WAN 14B: к 5B не подойдёт (другая ширина).",
                                               "Looks like a LoRA for WAN 14B: it won't fit 5B (a different width).")
    elif info.model != "h3":
        if not has("transformer_blocks."):
            info.verdict = "warn"
            info.notes = ("Имена слоёв не похожи на LTX-2 (нет transformer_blocks…). Скорее всего, LoRA от другой модели.",
                          "The layer names don't look like LTX-2 (no transformer_blocks…). Most likely a LoRA for another model.")
        elif h3:
            info.verdict, info.notes = "warn", ("Похоже на LoRA для H3: такие кладут в папку LoRA для H3.",
                                               "Looks like a LoRA for H3: those go into the H3 LoRA folder.")
        elif info.model == "ltx23" and re.search(r"19b", path.name, re.I) and not has("to_gate_logits"):
            # LTX-2 (19B) has the same layers but not 2.3's gates: the file's name is all that tells them apart
            info.verdict, info.notes = "warn", ("LoRA для LTX-2 (19B), не 2.3: может сработать слабо или иначе.",
                                               "A LoRA for LTX-2 (19B), not 2.3: it may work weakly or differently.")
    elif h3 == 0:
        info.verdict = "warn"
        info.notes = ("Имена слоёв не похожи на H3 (нет attn.qkv_proj / mlp.fc1…). Скорее всего, LoRA от другой модели.",
                      "The layer names don't look like H3 (no attn.qkv_proj / mlp.fc1…). Most likely a LoRA for another model.")
    else:
        for k in keys:
            if _IN_KEY.search(k):
                width = header[k]["shape"][-1]
                if width != HIDDEN:
                    info.verdict = "warn"
                    info.notes = (f"Ширина слоя {width}, у H3 — {HIDDEN}: похоже на другую модель.",
                                   f"Layer width {width}, H3 has {HIDDEN}: looks like another model.")
                break
    return info


class Library:
    """One model's LoRA folders (`dirs`: the config key, read at every scan - the settings page changes it); a file is
    re-inspected only when its mtime changes."""

    def __init__(self, model: str = "h3", dirs: str = "LORA_DIRS") -> None:
        self.model, self.dirs = model, dirs
        self._cache: dict[str, LoraInfo] = {}

    def scan(self) -> list[LoraInfo]:
        out: list[LoraInfo] = []
        seen: set[str] = set()
        for i, root in enumerate(getattr(config, self.dirs)):
            if not root.exists():
                continue
            for p in sorted(root.rglob("*.safetensors"), key=lambda q: str(q).lower()):
                rel = p.relative_to(root)
                lid = ("" if self.model == "h3" else f"{self.model}:") + f"d{i}/{rel.as_posix()}"
                seen.add(lid)
                st = p.stat()
                cached = self._cache.get(lid)
                if not (cached and cached.mtime == st.st_mtime and cached.path == p):
                    cached = inspect(p, LoraInfo(
                        id=lid, name=p.stem, folder=rel.parent.as_posix() if rel.parent != Path(".") else "", path=p,
                        comfy_name=str(rel).replace("/", os.sep), size_mb=round(st.st_size / 2**20, 1), mtime=st.st_mtime,
                        model=self.model))
                    self._cache[lid] = cached
                cached.preview = _find_preview(p)   # previews can arrive after the LoRA itself
                out.append(cached)
        for gone in set(self._cache) - seen:
            del self._cache[gone]
        return out

    def get(self, lid: str) -> Optional[LoraInfo]:
        if lid not in self._cache:
            self.scan()
        return self._cache.get(lid)


LIBRARIES = {"h3": Library(), "ltx23": Library("ltx23", "LTX23_LORA_DIRS"), "ltx25": Library("ltx25", "LTX25_LORA_DIRS"),
             "wan5b": Library("wan5b", "WAN_LORA_DIRS"), "flux2": Library("flux2", "FLUX2_LORA_DIRS")}   # flux2: the «Картинка» node's
LIBRARY = LIBRARIES["h3"]


def model_of(lid: str) -> str:
    """Whose LoRA an id is (H3's ids have no model in front)."""
    m = lid.split(":", 1)[0] if ":" in lid else "h3"
    return m if m in LIBRARIES else "h3"


def get(lid: str) -> Optional[LoraInfo]:
    return LIBRARIES[model_of(lid)].get(lid)


def scan_all() -> list[LoraInfo]:
    return [x for lib in LIBRARIES.values() for x in lib.scan()]


def for_model(items: list[dict], model: str) -> list[dict]:
    """The LoRA of a scene's list that its model takes (a list may hold another model's: the video's model changed);
    never one that reads a clip (v2v: it made a flat picture as a scene's LoRA). WAN with FastWan takes WAN's."""
    model = "wan5b" if model.startswith("wan5b") else model
    return [x for x in items or [] if model_of(x["id"]) == model and not ((i := get(x["id"])) and i.v2v)]
