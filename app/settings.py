"""The «Модели и настройки» page's settings: data/settings.json on top of .env (phase 6).

Only these keys, each applied to the config module at once - everything reads config at call time, so no restart:
the H3 weights by role, the writer's default model and context, the folders and the tools' paths. A folder or an
engine path reaches the H3 worker at its next start (main.py stops an idle one). An empty path or folder list
takes the key back to its .env value (or the built-in default).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import config
from . import i18n

FILE = config.DATA_DIR / "settings.json"
NAMES = ("H3_UNET", "H3_TURBO_LORA", "H3_CLIP", "H3_VAE", "H3_AUDIO_VAE", "H3_REF_UNET", "H3_REF_LORA", "LLM_MODEL",
         # phase 10: the other video models' weights (videomodels.py)
         "WAN_UNET", "WAN_CLIP", "WAN_VAE", "LTX25_UNET", "LTX25_CLIP", "LTX25_VAE", "LTX25_AUDIO_VAE", "LTX25_UPSCALER",
         "LTX23_CKPT", "LTX23_CLIP", "LTX23_LORA", "LTX23_UPSCALER",
         "KREA_UNET", "KREA_CLIP", "KREA_VAE",   # Krea 2, the pictures (picture.py)
         "FLUX2_UNET", "FLUX2_CLIP", "FLUX2_VAE")   # FLUX.2 Klein, the pictures by reference (frames.py)
FOLDERS = ("H3_MODEL_ROOTS", "LORA_DIRS", "LLM_DIRS", "KREA_LORA_DIRS", "LTX23_LORA_DIRS", "LTX25_LORA_DIRS", "WAN_LORA_DIRS", "FLUX2_LORA_DIRS")
PATHS = ("H3_REF_DIR", "COMFY_DIR", "COMFY_PYTHON", "LLAMA_SERVER_BIN", "RIFE_BIN", "RTX_VSR")   # one folder or file
COMMANDS = ("FFMPEG", "FFPROBE")   # a path or a name on PATH
CONTEXTS = (8192, 16384, 32768)
# the models' parameters (the page's «Параметры»): key -> (type, min, max)
NUMBERS: dict[str, tuple[type, float, float]] = {"KREA_STEPS": (int, 1, 30), "FLUX2_STEPS": (int, 1, 20),
                                                 "FRAME_FACE_MIN": (float, 0.0, 1.0), "FRAME_TRIES": (int, 1, 6)}
KEYS = (*NAMES, *FOLDERS, *PATHS, *COMMANDS, "LLM_CTX", *NUMBERS)
ENGINE_KEYS = {"H3_MODEL_ROOTS", "LORA_DIRS", "KREA_LORA_DIRS", "LTX23_LORA_DIRS", "LTX25_LORA_DIRS", "WAN_LORA_DIRS", "FLUX2_LORA_DIRS", "H3_REF_DIR", "COMFY_DIR", "COMFY_PYTHON"}   # the worker reads them at start
DEFAULTS = {k: getattr(config, k) for k in KEYS}   # .env or built-in, before settings.json


def _value(key: str, v: Any) -> Any:
    if key in FOLDERS:
        dirs = [Path(str(p).strip().strip('"')) for p in (v if isinstance(v, list) else str(v).splitlines()) if str(p).strip()]
        if not dirs:
            raise ValueError(i18n.L("Нужна хотя бы одна папка", "At least one folder is needed"))
        return dirs
    if key in PATHS or key in COMMANDS:
        s = str(v or "").strip().strip('"')
        if not s:
            raise ValueError(i18n.L("Нужен путь", "A path is needed"))
        return Path(s) if key in PATHS else s
    if key == "LLM_CTX":
        if int(v) not in CONTEXTS:
            raise ValueError(i18n.L("Контекст: ", "Context: ") + ", ".join(map(str, CONTEXTS)))
        return int(v)
    if key in NUMBERS:
        kind, lo, hi = NUMBERS[key]
        x = kind(float(v))
        if not lo <= x <= hi:
            raise ValueError(i18n.L(f"{key}: от {lo:g} до {hi:g}", f"{key}: {lo:g} to {hi:g}"))
        return x
    if not isinstance(v, str) or not v.strip() or "/" in v or "\\" in v:
        raise ValueError(i18n.L("Нужно имя файла", "A file name is needed"))
    if key != "LLM_MODEL" and v.strip().lower().endswith(".gguf"):   # the worker has no ComfyUI-GGUF: a saved one falls back to .env
        raise ValueError(i18n.L("Воркер не грузит GGUF: нужен .safetensors", "The worker doesn't load GGUF: a .safetensors is needed"))
    return v.strip()


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not any(str(x).strip() for x in v))


def _python_follows_dir() -> None:
    """COMFY_PYTHON set nowhere: it is COMFY_DIR's own, as config derives it (engine/.venv, or Desktop's inside its
    ComfyUI)."""
    if "COMFY_PYTHON" not in os.environ and "COMFY_PYTHON" not in saved():
        config.COMFY_PYTHON = config.engine_python(config.COMFY_DIR)


def saved() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apply(values: dict) -> None:
    for k, v in values.items():
        if k in KEYS:
            try:
                setattr(config, k, _value(k, v))
            except (ValueError, TypeError):
                continue   # a broken entry in the file: the .env value stays
    _python_follows_dir()


def update(patch: dict) -> list[str]:
    """Check, apply and save; the keys that changed. An empty path or folder list = back to .env.
    Raises ValueError with a Russian message."""
    clean, reset = {}, []
    for k, v in patch.items():
        if k not in KEYS:
            raise ValueError(i18n.L(f"Неизвестная настройка: {k}", f"Unknown setting: {k}"))
        if (k in FOLDERS or k in PATHS or k in COMMANDS or k in NUMBERS) and _empty(v):   # empty: back to .env or the default
            reset.append(k)
        else:
            clean[k] = _value(k, v)
    before = {k: getattr(config, k) for k in KEYS}
    data = saved()
    for k in reset:
        data.pop(k, None)
        setattr(config, k, DEFAULTS[k])
    data.update({k: [str(p) for p in v] if k in FOLDERS else str(v) if k in PATHS else v for k, v in clean.items()})
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    apply(clean)
    if "COMFY_PYTHON" in reset:
        _python_follows_dir()
    return [k for k in KEYS if getattr(config, k) != before[k]]


def _public(k: str, v: Any) -> Any:
    return [str(p) for p in v] if k in FOLDERS else str(v) if k in PATHS else v


def current() -> dict:
    return {k: _public(k, getattr(config, k)) for k in KEYS}


def own() -> list[str]:
    """The keys set on the page (the rest come from .env or the defaults)."""
    return [k for k in saved() if k in KEYS]


apply(saved())
