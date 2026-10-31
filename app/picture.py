"""Krea 2 pictures: the graph's «Картинка» node (phase 9) and whatever else needs a still. Drawn on the video models'
worker (other_graphs.krea2: the official ComfyUI template's pipeline, Turbo, 8 steps, no guidance), its weights from
«Модели и настройки» → Krea 2 (KREA_UNET / KREA_CLIP / KREA_VAE in the worker's folders), its LoRA from KREA_LORA_DIRS.
Until 2026-10-23 sd.cpp drew them; an A/B test found the worker 2-4 times faster with the same look and
every LoRA working (LoKr, txtfusion), so sd.cpp is gone.

The picture is made at the video's size (multiples of 16), so a scene started from it gets exactly its frame. One
model in the worker at a time: a video model in memory is put out first (as jobs.shoot does between models), the
writer's llama-server too; Krea stays in memory until another model is needed - the next pictures take ~3.5 s.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Optional

from . import config, jobs, krea_loras, timings
from .engine import other_graphs
from .engine.comfy import COMFY, EngineError, output_files
from .llm import client as llm
from . import i18n

MODEL = "krea2"   # what COMFY.model says while Krea is in the worker
EDIT_MODEL = "flux2"   # ... while FLUX.2 Klein is (edit)


def problem() -> Optional[str]:
    """Why a picture can't be made, or None."""
    from .models_page import find_file
    missing = [getattr(config, k) for k in ("KREA_UNET", "KREA_CLIP", "KREA_VAE") if not find_file(k)]
    return i18n.L("Krea 2: нет файлов " + ", ".join(missing) + " («Модели и настройки» → Krea 2)", "Krea 2: missing files " + ", ".join(missing) + " («Models and settings» → Krea 2)") if missing else None


def project_loras(settings: dict, model: str) -> list[dict]:
    """«LoRA картинок» of a project (settings.pic_loras): "krea" - Krea 2's (the heroes' portraits and tries, the places,
    a frame from words), "flux2" - FLUX.2 Klein's (the scenes' start frames, a portrait's adjusted features)."""
    return [x for x in ((settings or {}).get("pic_loras") or {}).get(model) or [] if isinstance(x, dict) and x.get("id")]


def pick_loras(items) -> list[dict]:
    """LoRA picks as a form sends them: [{id, name, strength}], nothing else kept."""
    out = []
    for x in items or []:
        if isinstance(x, dict) and str(x.get("id") or "").strip():
            try:
                k = max(-5.0, min(5.0, float(x.get("strength", 0.8))))
            except (TypeError, ValueError):
                k = 0.8
            out.append({"id": str(x["id"]), "name": str(x.get("name") or "")[:200], "strength": k})
    return out[:8]


def pick_pic_loras(d) -> dict:
    """«LoRA картинок» as a form sends them: Krea 2's and FLUX.2 Klein's picks (project_loras)."""
    d = d if isinstance(d, dict) else {}
    return {k: v for k in ("krea", "flux2") if (v := pick_loras(d.get(k)))}


async def _lora_names(items: list[dict]) -> list[tuple[str, float]]:
    """The Krea LoRA as the worker lists them (a path under one of its LoRA folders) with their strengths."""
    use = krea_loras.resolve(items)
    if not use:
        return []
    names = await COMFY.lora_names()
    out = []
    for info, s in use:
        rel = next((n for n in names if Path(n.replace("\\", "/")).name == info.path.name
                    and str(info.path).replace("\\", "/").endswith(n.replace("\\", "/"))), None)
        if not rel:
            raise EngineError(i18n.L(f"Воркер не видит LoRA «{info.name}» ({info.path.parent}): папка LoRA Krea появится у него после перезапуска", f"The worker can't see LoRA «{info.name}» ({info.path.parent}): it will see the Krea LoRA folder after a restart"))
        out.append((rel, s))
    return out


async def ready(job: jobs.Job) -> None:
    """The worker up with Krea as its model: the writer's server down, a video model in memory out first (a picture here,
    facefix.py's anchor frames)."""
    if why := problem():
        raise EngineError(why)
    job.phase, job.step, job.steps = "starting", 0, config.KREA_STEPS
    await llm.SERVER.stop()
    await COMFY.ensure()
    from .engine.worker import model_folders
    if getattr(COMFY, "folders", None) is not None and COMFY.folders != model_folders():
        job.phase = "starting"   # a weights or LoRA folder appeared since the worker started: it must know it
        await COMFY.stop()
        await COMFY.ensure()
    if getattr(COMFY, "model", "h3") != MODEL:
        if COMFY.warm:
            job.phase = "loading"
            await COMFY.free()   # a video model is in memory: out with it first
        COMFY.model = MODEL


async def generate(job: jobs.Job, prompt: str, seed: int, w: int, h: int, dest: Path, loras: list[dict] = ()) -> list[str]:
    """One picture into `dest`. `loras`: [{id, strength}] from the Krea LoRA library. -> notes about the LoRA (a key
    the worker could not put on the model)."""
    await ready(job)
    names = await _lora_names(list(loras))

    def on_node(node: str) -> None:
        if ph := other_graphs.phase_of(node):
            job.phase = ph

    def on_progress(value: int, maximum: int, node: str) -> None:
        if node == "ksample":
            job.phase, job.step, job.steps = "sampling", value, maximum

    log = config.WORKER_LOG
    before = log.stat().st_size if log.exists() else 0
    t0, cold = time.time(), not COMFY.warm
    graph = other_graphs.krea2(prompt, w, h, seed, f"h3studio/pictures/{dest.stem}", names,
                               config.KREA_UNET, config.KREA_CLIP, config.KREA_VAE)
    files = output_files(await COMFY.run(graph, on_node, on_progress))
    png = next((f for f in files if f.endswith(".png")), None)
    if not png:
        raise EngineError(i18n.L("Krea 2 не сделала картинку", "Krea 2 made no picture"))
    COMFY.warm = True
    timings.record(f"krea2:{w}x{h}", w, h, 1, len(names), time.time() - t0, cold)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(png, dest)
    text = log.read_bytes()[before:].decode("utf-8", "replace") if log.exists() else ""
    lost = text.count("lora key not loaded")
    return [i18n.L(f"LoRA: {lost} ключей не подошли к модели — часть LoRA не применилась", f"LoRA: {lost} keys didn't fit the model - part of the LoRA was not applied")] if lost else []


def edit_problem() -> Optional[str]:
    """Why a picture by reference can't be made (FLUX.2 Klein's files), or None."""
    from .models_page import find_file
    missing = [getattr(config, k) for k in ("FLUX2_UNET", "FLUX2_CLIP", "FLUX2_VAE") if not find_file(k)]
    return i18n.L("FLUX.2 Klein: нет файлов " + ", ".join(missing), "FLUX.2 Klein: missing files " + ", ".join(missing)) if missing else None


async def edit(job: jobs.Job, prompt: str, refs: list[Path], seed: int, w: int, h: int, dest: Path, loras: list[dict] = ()) -> None:
    """One picture into `dest` by FLUX.2 Klein from the reference pictures `refs` (the prompt calls them "the first
    image", "the second image"...): a scene's start frame with the hero's face from their photo. `loras`: [{id, strength}]
    from its library (loras.py, flux2:…). The same worker rules as generate(): one model in memory, the writer's server down."""
    if why := edit_problem():
        raise EngineError(why)
    job.phase, job.step, job.steps = "starting", 0, config.FLUX2_STEPS
    await llm.SERVER.stop()
    await COMFY.ensure()
    lora_names = await jobs.comfy_loras(job, list(loras))
    if getattr(COMFY, "model", "h3") != EDIT_MODEL:
        if COMFY.warm:
            job.phase = "loading"
            await COMFY.free()
        COMFY.model = EDIT_MODEL
    names = []
    for i, p in enumerate(refs[:4]):   # ReferenceLatent takes any number; a scene's cast (up to three) and its place
        name = f"h3s_ref_{dest.stem}_{i}{p.suffix.lower()}"
        shutil.copyfile(p, config.COMFY_INPUT / name)
        names.append(name)

    def on_node(node: str) -> None:
        if ph := other_graphs.phase_of(node):
            job.phase = ph

    def on_progress(value: int, maximum: int, node: str) -> None:
        if node == "fsample":
            job.phase, job.step, job.steps = "sampling", value, maximum

    t0, cold = time.time(), not COMFY.warm
    graph = other_graphs.flux2_edit(prompt, names, w, h, seed, f"h3studio/pictures/{dest.stem}", config.FLUX2_UNET, config.FLUX2_CLIP, config.FLUX2_VAE,
                                    lora_names)
    try:
        files = output_files(await COMFY.run(graph, on_node, on_progress))
    finally:
        for name in names:
            (config.COMFY_INPUT / name).unlink(missing_ok=True)
    png = next((f for f in files if f.endswith(".png")), None)
    if not png:
        raise EngineError(i18n.L("FLUX.2 Klein не сделала картинку", "FLUX.2 Klein made no picture"))
    COMFY.warm = True
    timings.record(f"flux2:{w}x{h}", w, h, 1, len(lora_names), time.time() - t0, cold)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(png, dest)


def status() -> Optional[str]:
    return problem() or config.KREA_UNET
