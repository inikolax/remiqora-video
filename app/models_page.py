"""What the «Модели и настройки» page shows (phase 6, after Remiqora's Models page): the weights by role, where each
file lies (or would go), where it comes from on Hugging Face, the writer's GGUF models, the LoRA folders and the
tools. Recomputed on every request, so a file put into a folder by hand shows up on the next look.
Phase 10: the other video models (WAN 2.2 5B, LTX 2.5, LTX 2.3) are sections of their own, each with its card -
what it can do, its speed here, its license (videomodels.py).
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import config, downloads, i18n, lora_prefs, settings
from .engine.worker import KINDS

REPO_H3 = "Comfy-Org/MiniMax-H3"
REPO_WAN22 = "Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
REPO_WAN21 = "Comfy-Org/Wan_2.1_ComfyUI_repackaged"
REPO_LTX25 = "Lightricks/LTX-2.5"
REPO_KREA = "Comfy-Org/Krea-2"
REPO_FLUX2 = "Comfy-Org/Flux-2-Klein-4B"   # Apache-2.0 (the 9B is under FLUX's non-commercial license)
REPO_ZIMAGE = "Comfy-Org/z_image_turbo"     # Qwen3 4B fp8, the text encoder FLUX.2 Klein shares with Z-Image
WEIGHT_EXT = (".safetensors", ".gguf", ".ckpt", ".pt", ".bin")


@dataclass(frozen=True)
class Slot:
    key: str                      # the config / settings key
    section: str                  # h3 | ref | wan5b | ltx25 | ltx23 | krea
    kind: str                     # diffusion_models | text_encoders | vae | loras | checkpoints | latent_upscale_models
    title: str
    text: str
    match: tuple[str, ...]        # a file of this role has one of these in its name (lowercase)
    skip: tuple[str, ...] = ()    # ... and none of these
    sources: tuple[tuple[str, str], ...] = ()   # (repo, path) to download from


SLOTS = (
    Slot("H3_UNET", "h3", "diffusion_models", "Основная модель", "Снимает сцены: из текста, с последнего кадра, с фото.",
         ("h3",), ("ref2va",),
         ((REPO_H3, "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors"),)),   # the official model; a fine-tune
                                                                                             # of yours in the folder is listed as your own file
    Slot("H3_TURBO_LORA", "h3", "loras", "Turbo-LoRA", "8 шагов без CFG для официальной модели; модель с ускорением внутри (TURBO в имени) снимает без неё.",
         ("fl2v_turbo",), (), ((REPO_H3, "loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"),)),
    Slot("H3_CLIP", "h3", "text_encoders", "Энкодер текста", "Читает промт (Qwen3-VL 32B, сжатый до nvfp4).",
         ("minimax_h3",), (), ((REPO_H3, "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"),)),
    Slot("H3_VAE", "h3", "vae", "VAE видео", "Переводит результат в кадры.", ("minimax_h3_video",), (),
         ((REPO_H3, "vae/minimax_h3_video_vae_fp16.safetensors"),)),
    Slot("H3_AUDIO_VAE", "h3", "vae", "VAE звука", "Переводит результат в звук.", ("minimax_h3_audio",), (),
         ((REPO_H3, "vae/minimax_h3_audio_vae_fp32.safetensors"),)),
    Slot("H3_REF_UNET", "ref", "diffusion_models", "Модель Ref2VA", "Держит лицо по фото героя («Держать лицо по фото»).",
         ("ref2va",), (), ((REPO_H3, "diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors"),)),
    Slot("H3_REF_LORA", "ref", "loras", "Turbo-LoRA Ref2VA", "4 шага вместо 20 для Ref2VA.", ("ref2v",), (),
         ((REPO_H3, "loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"),)),
    # phase 10: the other video models (videomodels.py), from the official ComfyUI templates' links
    Slot("WAN_UNET", "wan5b", "diffusion_models", "Основная модель", "Снимает сцены: из текста или с кадра (ti2v).",
         ("ti2v_5b", "wan2.2_ti2v"), (), ((REPO_WAN22, "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"),)),
    Slot("WAN_CLIP", "wan5b", "text_encoders", "Энкодер текста", "Читает промт (UMT5-XXL).", ("umt5",), (),
         ((REPO_WAN21, "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"),)),
    Slot("WAN_VAE", "wan5b", "vae", "VAE видео", "Переводит результат в кадры.", ("wan2.2_vae", "wan_2.2_vae"), (),
         ((REPO_WAN22, "split_files/vae/wan2.2_vae.safetensors"),)),
    Slot("WAN_FAST_LORA", "wan5b", "loras", "LoRA FastWan", "Для «WAN 2.2 5B · FastWan»: 8 шагов вместо 20, CFG 1.", ("fastwan",), ("14b",),
         (("Kijai/WanVideo_comfy", "FastWan/Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors"),)),
    Slot("LTX25_UNET", "ltx25", "diffusion_models", "Основная модель", "22B distilled, int8: картинка и звук вместе.",
         ("ltx-2.5", "ltx25"), (), ((REPO_LTX25, "diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"),)),
    Slot("LTX25_CLIP", "ltx25", "text_encoders", "Энкодер текста", "Читает промт (Gemma 4 12B, int8).", ("gemma4",), ("e2b",),
         ((REPO_LTX25, "text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"),)),
    Slot("LTX25_VAE", "ltx25", "vae", "VAE видео", "Переводит результат в кадры.", ("ltx-2.5-video", "ltx25_uncensored_video"), (),
         ((REPO_LTX25, "vae/ltx-2.5-video-vae-bf16.safetensors"),)),
    Slot("LTX25_AUDIO_VAE", "ltx25", "vae", "VAE звука", "Переводит результат в звук.", ("ltx-2.5-audio", "ltx25_uncensored_audio"), (),
         ((REPO_LTX25, "vae/ltx-2.5-audio-vae-bf16.safetensors"),)),
    Slot("LTX25_UPSCALER", "ltx25", "latent_upscale_models", "Апскейл латента ×2", "Вторая стадия: из половины размера в полный.",
         ("ltx-2.5",), (), ((REPO_LTX25, "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"),)),
    Slot("LTX23_CKPT", "ltx23", "checkpoints", "Основная модель", "22B dev, fp8: картинка, звук и VAE в одном файле.",
         ("ltx-2.3",), (), (("Lightricks/LTX-2.3-fp8", "ltx-2.3-22b-dev-fp8.safetensors"),)),
    Slot("LTX23_CLIP", "ltx23", "text_encoders", "Энкодер текста", "Читает промт (Gemma 3 12B, fp4).", ("gemma_3", "gemma-3"), (),
         (("Comfy-Org/ltx-2", "split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"),)),
    Slot("LTX23_LORA", "ltx23", "loras", "Distilled-LoRA", "8 + 3 шага вместо полного расписания.", ("ltx_2.3", "ltx-2.3"), (),
         (("Comfy-Org/ltx-2.3", "split_files/loras/ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors"),)),
    Slot("LTX23_UPSCALER", "ltx23", "latent_upscale_models", "Апскейл латента ×2", "Вторая стадия: из половины размера в полный.",
         ("ltx-2.3",), (), (("Lightricks/LTX-2.3", "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"),)),
    # Krea 2, the pictures: on the same worker (other_graphs.krea2), from the official ComfyUI repack
    Slot("KREA_UNET", "krea", "diffusion_models", "Модель", "Рисует картинку: Turbo, 8 шагов без CFG. int8 — быстрее всего на RTX 40xx.",
         ("krea2",), ("lora", ".gguf", "raw"), ((REPO_KREA, "diffusion_models/krea2_turbo_int8_convrot.safetensors"),
                                               (REPO_KREA, "diffusion_models/krea2_turbo_fp8_scaled.safetensors"))),
    Slot("KREA_CLIP", "krea", "text_encoders", "Энкодер текста", "Читает промт (Qwen3-VL 4B, fp8).", ("qwen3vl_4b",), (),
         ((REPO_KREA, "text_encoders/qwen3vl_4b_fp8_scaled.safetensors"),)),
    Slot("KREA_VAE", "krea", "vae", "VAE", "Переводит результат в картинку (VAE Qwen-Image).", ("qwen_image_vae",), (),
         ((REPO_KREA, "vae/qwen_image_vae.safetensors"),)),
    # FLUX.2 Klein 4B, the pictures by reference (other_graphs.flux2_edit): a scene's start frame with the hero's face
    Slot("FLUX2_UNET", "flux2", "diffusion_models", "Модель", "Рисует кадр по картинкам-образцам: герой с фото в месте сцены. 4 шага без CFG.",
         ("flux-2-klein", "flux2-klein", "flux_2_klein"), ("base", ".gguf"), ((REPO_FLUX2, "split_files/diffusion_models/flux-2-klein-4b.safetensors"),)),
    Slot("FLUX2_CLIP", "flux2", "text_encoders", "Энкодер текста", "Читает промт (Qwen3 4B — тот же файл, что у Z-Image).", ("qwen_3_4b",), ("flux2",),
         ((REPO_ZIMAGE, "split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors"),)),
    Slot("FLUX2_VAE", "flux2", "vae", "VAE", "Переводит результат в картинку (VAE FLUX.2).", ("flux2-vae", "flux2_vae"), (),
         ((REPO_FLUX2, "split_files/vae/flux2-vae.safetensors"),)),
)
MODEL_SECTIONS = {"wan5b": "WAN 2.2 5B", "ltx25": "LTX 2.5", "ltx23": "LTX 2.3"}   # phase 10, after «Видео H3» and «Ref2VA»


# the slots' titles and texts in English (the Russian ones are the keys; L() picks by the interface's language)
_EN = {
    # FLUX.2 Klein's slots and the parameters (PARAMS)
    "Рисует кадр по картинкам-образцам: герой с фото в месте сцены. 4 шага без CFG.": "Draws a frame from reference pictures: the hero from the photo in the scene's place. 4 steps, no CFG.",
    "Читает промт (Qwen3 4B — тот же файл, что у Z-Image).": "Reads the prompt (Qwen3 4B - the same file as Z-Image's).",
    "Переводит результат в картинку (VAE FLUX.2).": "Turns the result into a picture (the FLUX.2 VAE).",
    "Шагов": "Steps", "Порог лица": "Face threshold", "Попыток на лицо": "Tries for the face",
    "Turbo: 8 без CFG. Меньше — быстрее и грубее; больше 8 почти ничего не добавляет.": "Turbo: 8 without CFG. Fewer - faster and rougher; above 8 adds almost nothing.",
    "Distilled: 4. Меньше — быстрее, но мягче детали.": "Distilled: 4. Fewer - faster, but softer detail.",
    "Сходство лица на кадре сцены с фото героя (SFace, 0–1), ниже которого пробуется другой сид. Общий план с мелким лицом даёт ~0,3 на той же героине.":
        "How alike the face on a scene's frame is to the hero's photo (SFace, 0-1); below this another seed is tried. A wide shot with a small face scores ~0.3 on the same heroine.",
    "Сколько сидов пробовать, пока лицо не пройдёт порог; лучший остаётся.": "How many seeds to try until the face passes the threshold; the best one stays.",
    "Основная модель": "Main model", "Энкодер текста": "Text encoder", "VAE видео": "Video VAE", "VAE звука": "Audio VAE",
    "Модель Ref2VA": "Ref2VA model", "Апскейл латента ×2": "Latent upscale ×2", "Модель": "Model",
    "Снимает сцены: из текста, с последнего кадра, с фото.": "Shoots scenes: from text, from the last frame, from a photo.",
    "Читает промт (Qwen3-VL 32B, сжатый до nvfp4).": "Reads the prompt (Qwen3-VL 32B, compressed to nvfp4).",
    "Переводит результат в кадры.": "Turns the result into frames.",
    "Переводит результат в звук.": "Turns the result into sound.",
    "Держит лицо по фото героя («Держать лицо по фото»).": "Keeps the face from the hero's photo («Keep the face from the photo»).",
    "4 шага вместо 20 для Ref2VA.": "4 steps instead of 20 for Ref2VA.",
    "8 шагов без CFG для официальной модели; модель с ускорением внутри (TURBO в имени) снимает без неё.": "8 steps without CFG for the official model; a model with the speed-up built in (TURBO in its name) shoots without it.",
    "Снимает сцены: из текста или с кадра (ti2v).": "Shoots scenes: from text or from a frame (ti2v).",
    "Читает промт (UMT5-XXL).": "Reads the prompt (UMT5-XXL).",
    "Для «WAN 2.2 5B · FastWan»: 8 шагов вместо 20, CFG 1.": "For «WAN 2.2 5B · FastWan»: 8 steps instead of 20, CFG 1.",
    "22B distilled, int8: картинка и звук вместе.": "22B distilled, int8: picture and sound together.",
    "Читает промт (Gemma 4 12B, int8).": "Reads the prompt (Gemma 4 12B, int8).",
    "Вторая стадия: из половины размера в полный.": "The second stage: from half size to full.",
    "22B dev, fp8: картинка, звук и VAE в одном файле.": "22B dev, fp8: picture, sound and VAE in one file.",
    "Читает промт (Gemma 3 12B, fp4).": "Reads the prompt (Gemma 3 12B, fp4).",
    "8 + 3 шага вместо полного расписания.": "8 + 3 steps instead of the full schedule.",
    "Рисует картинку: Turbo, 8 шагов без CFG. int8 — быстрее всего на RTX 40xx.": "Draws the picture: Turbo, 8 steps without CFG. int8 is the fastest on RTX 40xx.",
    "Читает промт (Qwen3-VL 4B, fp8).": "Reads the prompt (Qwen3-VL 4B, fp8).",
    "Переводит результат в картинку (VAE Qwen-Image).": "Turns the result into a picture (the Qwen-Image VAE).",
}


def _t(ru: str) -> str:
    return i18n.L(ru, _EN.get(ru, ru))


def folders(kind: str, section: str = "h3") -> list[Path]:
    """Where files of this kind are looked for; the first one is where a download goes."""
    roots = [config.H3_REF_DIR, *config.H3_MODEL_ROOTS] if section == "ref" else [*config.H3_MODEL_ROOTS, config.H3_REF_DIR]
    out = [r / s for r in roots for s in KINDS[kind]]
    if kind == "loras" and section != "ref":
        out += list(config.LORA_DIRS)
    seen, uniq = set(), []
    for d in out:
        if str(d).lower() not in seen:
            seen.add(str(d).lower())
            uniq.append(d)
    return uniq


def _files(kind: str) -> dict[str, Path]:
    """name -> path of every weight file of this kind (the first folder wins, as in ComfyUI)."""
    out: dict[str, Path] = {}
    for d in folders(kind, "ref") + folders(kind):
        if d.is_dir():
            for p in sorted(d.iterdir(), key=lambda q: q.name.lower()):
                if p.is_file() and p.suffix.lower() in WEIGHT_EXT:
                    out.setdefault(p.name, p)
    return out


def find_file(key: str) -> Optional[Path]:
    """Where the file a slot's key names lies (None: the worker won't find it)."""
    s = next((x for x in SLOTS if x.key == key), None)
    return _files(s.kind).get(getattr(config, key)) if s else None


def _gb(n: Optional[int]) -> Optional[float]:
    return round(n / 2**30, 2) if n else None


def _row(name: str, path: Optional[Path], repo: Optional[str], src: Optional[str], dest: Path, current: str) -> dict:
    size = path.stat().st_size if path else (downloads.size(repo, src) if repo else None)
    return {"name": name, "installed": bool(path), "path": str(path) if path else None, "folder": str(path.parent if path else dest),
            "size": size, "gb": _gb(size), "repo": repo, "src": src, "url": f"https://huggingface.co/{repo}/blob/main/{src}" if repo else None,
            "selected": name == current, "partial": downloads.partial(dest, name) if not path else 0,
            "download": downloads.state(repo, src) if repo else None}


def slot_view(s: Slot) -> dict:
    files, current = _files(s.kind), getattr(config, s.key)
    dest = folders(s.kind, s.section)[0]
    rows, names = [], set()
    for repo, src in s.sources:
        name = src.rsplit("/", 1)[-1]
        names.add(name)
        rows.append(_row(name, files.get(name), repo, src, dest, current))
    for name, p in files.items():   # the user's own files of this role
        low = name.lower()
        if name not in names and any(m in low for m in s.match) and not any(x in low for x in s.skip) and not low.endswith(".gguf"):   # no ComfyUI-GGUF on the worker
            rows.append(_row(name, p, None, None, dest, current))
    found = files.get(current)
    return {"key": s.key, "section": s.section, "title": _t(s.title), "text": _t(s.text), "current": current,
            "ok": bool(found), "files": rows, "dest": str(dest)}


def _llm_view() -> dict:
    from .llm import client as llm
    try:
        default = llm.find(None).id
    except llm.LLMError:
        default = None
    ms = []
    for m in llm.models():
        size = m.path.stat().st_size + (m.mmproj.stat().st_size if m.mmproj else 0)
        ms.append({**m.public(), "path": str(m.path), "gb": _gb(size), "default": m.id == default})
    return {"models": ms, "dirs": [str(d) for d in config.LLM_DIRS], "ctx": config.LLM_CTX, "contexts": list(settings.CONTEXTS),
            "server": str(config.LLAMA_SERVER_BIN), "server_ok": config.LLAMA_SERVER_BIN.exists(),
            "dest": str(config.LLM_DIRS[-1]) if config.LLM_DIRS else None}


def _lora_view() -> dict:
    out = []
    for d in config.LORA_DIRS:
        files = [p for p in d.rglob("*.safetensors")] if d.is_dir() else []
        out.append({"dir": str(d), "exists": d.is_dir(), "count": len(files), "gb": _gb(sum(p.stat().st_size for p in files))})
    return {"dirs": out}


def _krea_lora_view() -> dict:
    from . import krea_loras
    out = []
    for d in config.KREA_LORA_DIRS:
        files = [p for p in d.rglob("*.safetensors")] if d.is_dir() else []
        out.append({"dir": str(d), "exists": d.is_dir(), "count": len(files), "gb": _gb(sum(p.stat().st_size for p in files))})
    lib = [{**x.public(), "own": lora_prefs.get(x.id, "krea") is not None} for x in krea_loras.LIBRARY.scan()]
    return {"dirs": out, "loras": lib}


def _ltx_lora_view(model: str) -> dict:
    """A model's own LoRA folders (LORA_DIRS / LTX23_LORA_DIRS / LTX25_LORA_DIRS / WAN_LORA_DIRS / FLUX2_LORA_DIRS), what lies in them
    (loras.py) and each one's strength (lora_prefs.py)."""
    from . import loras
    key = {"h3": "LORA_DIRS", "wan5b": "WAN_LORA_DIRS"}.get(model, f"{model.upper()}_LORA_DIRS")
    out = []
    for d in getattr(config, key):
        files = [p for p in d.rglob("*.safetensors")] if d.is_dir() else []
        out.append({"dir": str(d), "exists": d.is_dir(), "count": len(files), "gb": _gb(sum(p.stat().st_size for p in files))})
    lib = [{"id": x.id, "name": x.name, "folder": x.folder, "size_mb": x.size_mb, "kind": x.kind, "verdict": x.verdict,
            "note": x.note, "rank": x.rank, "trigger": x.trigger, "v2v": x.v2v,
            "strength": lora_prefs.strength(x.id, model), "own": lora_prefs.get(x.id, model) is not None,
            "preview": f"/api/loras/preview?id={x.id}&v={int(x.mtime)}" if x.preview else None} for x in loras.LIBRARIES[model].scan()]
    return {"key": key, "dirs": out, "loras": lib}


def _tool(key: str, name: str, text: str, kind: str = "file", check: Optional[Path] = None) -> dict:
    """A path the page edits: `key` in settings, `kind` folder | file | command (a name on PATH will do),
    `check` what must exist for it to be found (the value itself by default)."""
    v = getattr(config, key)
    p = check or Path(v)
    found = p.exists() or (kind == "command" and bool(shutil.which(str(v))))
    return {"key": key, "name": name, "path": str(v), "kind": kind, "ok": found, "text": text,
            "own": key in settings.own(), "default": str(settings.DEFAULTS[key])}


# the page's groups: video models, picture models, the writer, the rest; Ref2VA is H3's (shown under it), the H3 LoRA too
GROUPS = {"h3": "video", "ref": "video", "ltx25": "video", "ltx23": "video", "wan5b": "video", "krea": "photo", "flux2": "photo",
          "llm": "writer", "lora": "video", "tools": "common"}
# a model's parameters (settings.NUMBERS): section -> [(key, title, text)]
PARAMS = {
    "krea": [("KREA_STEPS", "Шагов", "Turbo: 8 без CFG. Меньше — быстрее и грубее; больше 8 почти ничего не добавляет.")],
    "flux2": [("FLUX2_STEPS", "Шагов", "Distilled: 4. Меньше — быстрее, но мягче детали."),
              ("FRAME_FACE_MIN", "Порог лица", "Сходство лица на кадре сцены с фото героя (SFace, 0–1), ниже которого пробуется другой сид. Общий план с мелким лицом даёт ~0,3 на той же героине."),
              ("FRAME_TRIES", "Попыток на лицо", "Сколько сидов пробовать, пока лицо не пройдёт порог; лучший остаётся.")],
}


def _params(sec: str) -> list[dict]:
    out = []
    for key, title, text in PARAMS.get(sec, []):
        kind, lo, hi = settings.NUMBERS[key]
        out.append({"key": key, "title": _t(title), "text": _t(text), "value": getattr(config, key), "default": settings.DEFAULTS[key],
                    "min": lo, "max": hi, "step": 1 if kind is int else 0.05, "own": key in settings.own()})
    return out


def snapshot() -> dict:
    from .engine.comfy import COMFY
    slots = [slot_view(s) for s in SLOTS]
    sections = {}
    from . import timings, videomodels
    for sec, title in (("h3", i18n.L("Видео H3", "H3 video")), ("ref", "Ref2VA"), *MODEL_SECTIONS.items()):
        ss = [x for x in slots if x["section"] == sec]
        used = sum((next((f["size"] for f in x["files"] if f["selected"] and f["installed"]), 0) or 0) for x in ss)
        sections[sec] = {"title": title, "slots": ss, "ok": all(x["ok"] for x in ss), "gb": _gb(used)}
        if sec in videomodels.CARDS or sec == "h3":
            c = videomodels.card(sec)
            w, h = videomodels.size(c, 16 / 9, "draft")
            sections[sec]["card"] = {"id": c.id, "name": c.name, "text": videomodels.text_of(c), "sound": c.sound, "voice": c.voice, "refs": c.refs,
                                     "track": c.track, "max_seconds": c.max_seconds, "license": videomodels.license_of(c), "steps": c.steps,
                                     "size": f"{w}×{h}", "per_scene": round(timings.scene_seconds(videomodels.timing_key(c, "draft"), w, h,
                                                                                                     videomodels.frames(c, 5), c.base["draft"])),
                                     "measured": timings.samples(videomodels.timing_key(c, "draft"))}
        if sec in ("ltx23", "ltx25", "wan5b"):
            sections[sec]["loras"] = _ltx_lora_view(sec)
    llm = _llm_view()
    sections["llm"] = {"title": i18n.L("Сценарист", "Writer"), **llm, "ok": bool(llm["models"]) and llm["server_ok"],
                       "gb": _gb(sum(int((m["gb"] or 0) * 2**30) for m in llm["models"]))}
    lora = _lora_view()
    sections["lora"] = {"title": "LoRA", **lora, "key": "LORA_DIRS", "loras": _ltx_lora_view("h3")["loras"], "ok": any(d["exists"] for d in lora["dirs"]),
                        "gb": round(sum(d["gb"] or 0 for d in lora["dirs"]), 2)}
    from . import picture
    krea = [x for x in slots if x["section"] == "krea"]
    kl = _krea_lora_view()
    sections["krea"] = {"title": "Krea 2", "slots": krea, "loras": kl, "problem": picture.problem(),
                        "ok": all(x["ok"] for x in krea),
                        "gb": _gb(sum((next((f["size"] for f in x["files"] if f["selected"] and f["installed"]), 0) or 0) for x in krea))}
    flux2 = [x for x in slots if x["section"] == "flux2"]
    sections["flux2"] = {"title": "FLUX.2 Klein", "slots": flux2, "loras": _ltx_lora_view("flux2"), "problem": picture.edit_problem(), "ok": all(x["ok"] for x in flux2),
                         "gb": _gb(sum((next((f["size"] for f in x["files"] if f["selected"] and f["installed"]), 0) or 0) for x in flux2))}
    tools = [
        _tool("COMFY_DIR", i18n.L("Ядро ComfyUI", "ComfyUI core"),
              i18n.L("Папка, в которой лежит ComfyUI\\comfy: модель H3, энкодер, VAE, сэмплер (воркер импортирует его). Своё — engine\\ComfyUI (install.bat), иначе — из Comfy Desktop",
                     "The folder that holds ComfyUI\\comfy: the H3 model, the encoder, the VAE, the sampler (the worker imports it). Our own is engine\\ComfyUI (install.bat), otherwise the one from Comfy Desktop"),
              "folder", config.COMFY_DIR / "ComfyUI" / "comfy"),
        _tool("COMFY_PYTHON", i18n.L("Python для H3", "Python for H3"),
              i18n.L("python.exe с torch и CUDA, comfy-kitchen, comfy-aimdo; не задан — engine\\.venv или venv внутри ядра",
                     "python.exe with torch and CUDA, comfy-kitchen, comfy-aimdo; when not set, engine\\.venv or the venv inside the core")),
        _tool("LLAMA_SERVER_BIN", "llama-server", i18n.L("Запускает модель сценариста", "Runs the writer's model")),
        _tool("FFMPEG", "ffmpeg", i18n.L("Склейка, звук, кодирование; можно просто имя, если он в PATH", "Joining, sound, encoding; just the name will do if it is on PATH"), "command"),
        _tool("FFPROBE", "ffprobe", i18n.L("Длина и дорожки файлов; обычно рядом с ffmpeg", "Files' length and tracks; usually next to ffmpeg"), "command"),
        _tool("RIFE_BIN", "RIFE", i18n.L("48 кадров в секунду (rife-ncnn-vulkan.exe, папка модели рядом)", "48 frames per second (rife-ncnn-vulkan.exe, the model folder next to it)")),
        _tool("RTX_VSR", "RTX Video", i18n.L("1080p / 4K и HDR10 (rtx_vsr.exe)", "1080p / 4K and HDR10 (rtx_vsr.exe)")),
    ]
    sections["tools"] = {"title": i18n.L("Инструменты", "Tools"), "tools": tools, "ok": all(t["ok"] for t in tools), "gb": None}
    for k, s in sections.items():
        s["group"] = GROUPS[k]
        s["params"] = _params(k)
    total = sum(s["gb"] or 0 for k, s in sections.items() if k != "tools")
    act = downloads.active()
    return {"sections": sections, "gb": round(total, 1), "engine": {"state": COMFY.state(), "own": config.COMFY_DIR == config.OWN_ENGINE},
            "roots": [str(d) for d in config.H3_MODEL_ROOTS], "ref_dir": str(config.H3_REF_DIR),
            "ref_tool": _tool("H3_REF_DIR", i18n.L("Папка Ref2VA", "Ref2VA folder"), i18n.L("В ней diffusion_models и loras", "Holds diffusion_models and loras"), "folder"),
            "downloading": act.public() if act else None, "token": downloads.has_token(), "settings": settings.current()}


def known_folders() -> list[Path]:
    out = [d for k in KINDS for d in folders(k) + folders(k, "ref")]
    tools = [config.H3_REF_DIR, config.COMFY_DIR, *(Path(getattr(config, k)).parent for k in settings.PATHS[2:])]
    return (out + list(config.LORA_DIRS) + list(config.LLM_DIRS) + list(config.KREA_LORA_DIRS) + list(config.LTX23_LORA_DIRS)
            + list(config.LTX25_LORA_DIRS) + list(config.WAN_LORA_DIRS) + tools)


def inside_known(path: Path) -> bool:
    p = path.resolve()
    return any(str(p).lower().startswith(str(d.resolve()).lower() + os.sep) or p == d.resolve() for d in known_folders())


def to_recycle_bin(path: Path) -> None:
    """Windows' Recycle Bin, not a permanent delete (SHFileOperationW with FOF_ALLOWUNDO)."""
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p)]
    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(None, FO_DELETE, str(path) + "\0\0", None, FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI,
                         0, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc or path.exists():
        raise OSError(i18n.L(f"Не удалось убрать в корзину (код {rc})", f"Could not move to the Recycle Bin (code {rc})"))


_PICK = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$start = $env:H3_PICK_START
if ($env:H3_PICK_KIND -eq 'folder') {
  $d = New-Object System.Windows.Forms.FolderBrowserDialog
  $d.Description = $env:H3_PICK_DESC
  $d.ShowNewFolderButton = $true
  if ($start -and (Test-Path -LiteralPath $start -PathType Container)) { $d.SelectedPath = $start }
  if ($d.ShowDialog($owner) -eq 'OK') { $d.SelectedPath }
} else {
  $d = New-Object System.Windows.Forms.OpenFileDialog
  $d.Title = $env:H3_PICK_DESC
  $d.Filter = $env:H3_PICK_FILTER
  if ($start) { $p = if (Test-Path -LiteralPath $start -PathType Container) { $start } else { Split-Path -LiteralPath $start }
                if ($p -and (Test-Path -LiteralPath $p)) { $d.InitialDirectory = $p } }
  if ($d.ShowDialog($owner) -eq 'OK') { $d.FileName }
}
"""


def pick(kind: str, start: Optional[str]) -> Optional[str]:
    """Windows' folder / file dialog in front of the browser (a TopMost owner); None if it was closed."""
    env = {**os.environ, "H3_PICK_KIND": kind, "H3_PICK_START": start or "",
           "H3_PICK_DESC": i18n.L("Remiqora Video: выберите папку", "Remiqora Video: choose a folder") if kind == "folder"
           else i18n.L("Remiqora Video: выберите файл", "Remiqora Video: choose a file"),
           "H3_PICK_FILTER": i18n.L("Программы (*.exe)|*.exe|Все файлы (*.*)|*.*", "Programs (*.exe)|*.exe|All files (*.*)|*.*")}
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", _PICK],
                       capture_output=True, env=env, timeout=1800)
    out = r.stdout.decode("utf-8", "replace").strip().lstrip("﻿")
    return out.splitlines()[-1].strip() if out else None
