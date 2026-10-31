"""The GPU queue: one job at a time, in order, with one worker - the LLM and H3 never run together.
A job is a scene of the lab (kind "scene") or a task (any other kind: its coroutine is given to submit_task, its
answer lands in job.result): the writer's calls, a project's shooting (kind "render", render.py). State is in memory (it is only a progress display); finished scenes live in outputs/ as
<name>.mp4 + <name>.png (last frame) + <name>.json."""
from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from . import config, timings
from .engine import graphs
from .engine.comfy import COMFY, EngineError, output_files
from .llm import client as llm
from . import loras as lora_lib
from . import i18n



@dataclass
class Job:
    id: str
    params: dict
    kind: str = "scene"         # scene | describe | write ...
    status: str = "queued"      # queued | running | done | error | cancelled
    phase: str = "queued"       # queued | starting | loading | encoding | sampling | decoding | saving | llm | done
    step: int = 0
    steps: int = graphs.STEPS
    estimate: float = 0         # seconds, for "about N min left"
    file: Optional[str] = None  # name in outputs/
    result: Any = None          # what a task answered
    progress: dict = field(default_factory=dict)   # a render's per-scene state, for the video screen
    stop_after: bool = False    # a render: stop after the scene being shot
    error: Optional[str] = None
    created: float = field(default_factory=time.time)
    started: Optional[float] = None
    finished: Optional[float] = None

    def public(self) -> dict:
        d = asdict(self)
        d["elapsed"] = round((self.finished or time.time()) - self.started, 1) if self.started else 0
        return d


JOBS: dict[str, Job] = {}
_queue: asyncio.Queue[str] = asyncio.Queue()
_current: dict = {"task": None, "id": None}
_tasks: dict[str, Callable[[Job], Awaitable[Any]]] = {}


def estimate(p: dict) -> float:
    """Seconds for one warm scene: from this machine's recent shots (timings.py), of its model (phase 10)."""
    from . import videomodels
    c = videomodels.card(p.get("model"))
    if c.id == "h3":
        return timings.scene_seconds(p["quality"], p["width"], p["height"], p["length"])
    cw, ch = videomodels.size(c, 16 / 9, p["quality"])
    base = c.base.get(p["quality"], c.base["draft"]) * p["width"] * p["height"] / (cw * ch) * p["length"] / videomodels.frames(c, 5)
    return timings.scene_seconds(videomodels.timing_key(c, p["quality"]), p["width"], p["height"], p["length"], base)


def cold_extra(quality: str, model: str = "h3") -> float:
    """What a scene costs on top when ComfyUI must start or load the model first (another model in memory counts)."""
    from . import videomodels
    from .engine.comfy import COMFY
    if COMFY.warm and getattr(COMFY, "model", "h3") == model:
        return 0.0
    return timings.cold_seconds(videomodels.timing_key(videomodels.card(model), quality)) + (0 if COMFY.pid else 12)


def submit(params: dict) -> Job:
    job = Job(id=uuid.uuid4().hex[:10], params=params, estimate=round(estimate(params)))
    JOBS[job.id] = job
    _queue.put_nowait(job.id)
    return job


def submit_task(kind: str, params: dict, fn: Callable[[Job], Awaitable[Any]], estimate: float = 30) -> Job:
    """An LLM job: `fn(job)` runs in the queue, its return value becomes job.result."""
    job = Job(id=uuid.uuid4().hex[:10], params=params, kind=kind, steps=0, estimate=estimate)
    JOBS[job.id] = job
    _tasks[job.id] = fn
    _queue.put_nowait(job.id)
    return job


def cancel(job_id: str) -> bool:
    job = JOBS.get(job_id)
    if not job or job.status not in ("queued", "running"):
        return False
    if job.status == "queued":
        job.status, job.phase, job.finished = "cancelled", "done", time.time()
        _tasks.pop(job_id, None)
    elif _current["id"] == job_id and _current["task"]:
        _current["task"].cancel()
    return True


def busy() -> bool:
    return _current["id"] is not None


async def comfy_loras(job: Job, items: list[dict]) -> list[tuple[str, float]]:
    """(name as ComfyUI lists it, strength). A LoRA folder ComfyUI doesn't know yet (LORA_DIRS changed, a new
    sub-folder) costs one restart of ComfyUI: it reads our paths yaml only at start."""
    want = []
    for item in items:
        info = lora_lib.get(item["id"])
        if not info:
            raise EngineError(i18n.L(f"LoRA не найдена: {item.get('name', item['id'])}", f"LoRA not found: {item.get('name', item['id'])}"))
        if info.verdict == "blocked":
            raise EngineError(i18n.L(f"LoRA «{info.name}» нельзя использовать: {info.note}", f"LoRA «{info.name}» can't be used: {info.note}"))
        want.append((info, float(item["strength"])))
    if not want:
        return []
    known = set(await COMFY.lora_names())
    if any(i.comfy_name not in known for i, _ in want) and COMFY.pid:
        job.phase = "starting"
        await COMFY.stop()
        await COMFY.ensure()
        known = set(await COMFY.lora_names())
    missing = [i.name for i, _ in want if i.comfy_name not in known]
    if missing:
        raise EngineError(i18n.L("ComfyUI не видит LoRA: ", "ComfyUI can't see the LoRA: ") + ", ".join(missing))
    return [(i.comfy_name, s) for i, s in want]


async def _ref_models(job: Job) -> None:
    """Ref2VA needs the ref2va weights and their turbo LoRA from H3_REF_DIR (the worker is given the folder at its
    start; a changed folder restarts it - see shoot)."""
    async def have() -> bool:
        unets = (await COMFY.object_info("UNETLoader")).get("input", {}).get("required", {}).get("unet_name", [[]])[0]
        return config.H3_REF_UNET in unets and config.H3_REF_LORA in await COMFY.lora_names()
    if await have():
        return
    if not (config.H3_REF_DIR / "diffusion_models" / config.H3_REF_UNET).exists():
        raise EngineError(i18n.L(f"Нет модели Ref2VA: {config.H3_REF_DIR}\\diffusion_models\\{config.H3_REF_UNET} («Модели и настройки» или H3_REF_DIR в .env)", f"No Ref2VA model: {config.H3_REF_DIR}\\diffusion_models\\{config.H3_REF_UNET} («Models and settings» or H3_REF_DIR in .env)"))
    # the worker is told every folder at its start: missing means not there
    raise EngineError(i18n.L(f"Воркер H3 не видит {config.H3_REF_UNET} или {config.H3_REF_LORA} в {config.H3_REF_DIR}", f"The H3 worker can't see {config.H3_REF_UNET} or {config.H3_REF_LORA} in {config.H3_REF_DIR}"))


async def engine(job: Job, model: str, loras: list[dict], ref: bool = False) -> list[tuple[str, float]]:
    """The worker up for a model's weights (a videomodels card id): the LLM down, the worker told of every weights
    folder, another model in memory freed first (two 20 GB models never share it), Ref2VA's weights seen. -> the LoRA
    as ComfyUI names them. A scene (shoot) and «Видео → видео» (v2v.py) start their graphs after this."""
    from . import videomodels
    card = videomodels.card(model)
    if card.id != "h3" and (missing := videomodels.weights_missing(card)):
        raise EngineError(i18n.L(f"{card.name}: нет файлов " + ", ".join(missing) + " («Модели и настройки»)", f"{card.name}: missing files " + ", ".join(missing) + " («Models and settings»)"))
    await llm.SERVER.stop()   # normally already down: a writer job stops it after itself
    await COMFY.ensure()
    from .engine.worker import model_folders
    if getattr(COMFY, "folders", None) is not None and COMFY.folders != model_folders():
        job.phase = "starting"   # a weights folder appeared since the worker started (a download): it must know it
        await COMFY.stop()
        await COMFY.ensure()
    if getattr(COMFY, "model", "h3") != card.id:
        if COMFY.warm:
            job.phase = "loading"
            await COMFY.free()   # another model is in memory: out with it first
        COMFY.model = card.id
    if ref:
        await _ref_models(job)
    return await comfy_loras(job, loras)


def scene_graph(model: str, prompt: str, width: int, height: int, length: int, seed: int, prefix: str,
                names: list[tuple[str, float]], first_frame: Optional[str] = None, ref_images: list[str] = (),
                track: Optional[str] = None, track_start: float = 0.0, voice: Optional[dict] = None,
                last_frame: Optional[str] = None) -> dict:
    """A scene's graph for the worker, by its model (a videomodels card id) - what shoot() sends, and what the scene's
    «Граф для ComfyUI» shows without shooting (render.scene_graph_preview)."""
    from . import videomodels
    from .engine import other_graphs
    card = videomodels.card(model)
    if card.id == "h3":
        return graphs.scene(prompt, width, height, length, seed, prefix, names, first_frame, list(ref_images))
    if videomodels.family(card) == "wan5b":
        return other_graphs.wan(prompt, width, height, length, seed, prefix, names, first_frame, card.id == "wan5b_fast")
    if card.id == "ltx25":
        return other_graphs.ltx25(prompt, width, height, length, seed, prefix, names, first_frame, last_frame)
    return other_graphs.ltx23(prompt, width, height, length, seed, prefix, names, first_frame, track, track_start, voice, last_frame)


async def shoot(job: Job, prompt: str, width: int, height: int, length: int, seed: int, loras: list[dict],
                first_frame: Optional[str], prefix: str, quality: str = "draft",
                ref_images: list[str] = (), model: str = "h3", track: Optional[str] = None,
                track_start: float = 0.0, voice: Optional[dict] = None, last_frame: Optional[str] = None) -> tuple[str, Optional[str]]:
    """One scene through ComfyUI: (the mp4, the last frame png) in COMFY_OUTPUT. job.phase / step follow it; the time
    goes to timings.py, so the next estimates are this machine's. `model` - a videomodels card (phase 10): its graph
    (other_graphs.py), its sampler's steps; another model than the one in memory frees the worker first, so two 20 GB
    models never share it. `track` (LTX 2.3): a file in COMFY_INPUT the picture is made to, from `track_start`. `voice`
    (LTX 2.3, ID-LoRA): {lora: {id, strength}, voice: a file in COMFY_INPUT, from, secs, identity}. `last_frame` (LTX,
    flf2v): a picture in COMFY_INPUT the scene ends on."""
    from . import videomodels
    from .engine import other_graphs
    card = videomodels.card(model)
    h3 = card.id == "h3"
    phase_of = graphs.phase_of if h3 else other_graphs.phase_of
    samplers = (graphs.SAMPLE,) if h3 else other_graphs.SAMPLERS
    done_before = {"n": 0}   # LTX: the second stage's steps go on from the first's

    def on_node(node: str) -> None:
        if ph := phase_of(node):
            job.phase = ph
        if node == "sample2":
            done_before["n"] = len(other_graphs.LTX_SIGMAS_1.split(",")) - 1

    def on_progress(value: int, maximum: int, node: str) -> None:
        if node in samplers:
            job.phase, job.step = "sampling", done_before["n"] + value
            job.steps = maximum if h3 or videomodels.family(card) == "wan5b" else card.steps

    # the steps are known before the sampler reports any: the sampler's node is announced first, and 0 of 0 steps
    # made the video screen say NaN%
    job.phase, job.step, job.steps = "starting", 0, (graphs.REF_STEPS if ref_images else graphs.STEPS) if h3 else card.steps
    names = await engine(job, card.id, loras + ([voice["lora"]] if voice else []), bool(ref_images) and h3)
    idv = None
    if voice:   # the ID-LoRA as ComfyUI names it is the last; the graph puts it on after the others
        (lname, lstrength), names = names[-1], names[:-1]
        idv = {**voice, "lora": lname, "strength": lstrength}
    t0, cold = time.time(), not COMFY.warm
    job.phase = "loading"
    graph = scene_graph(card.id, prompt, width, height, length, seed, prefix, names, first_frame, ref_images, track, track_start, idv, last_frame)
    files = output_files(await COMFY.run(graph, on_node, on_progress))
    mp4 = next((f for f in files if f.endswith(".mp4")), None)
    if not mp4:
        raise EngineError(i18n.L("ComfyUI закончил без mp4", "ComfyUI finished without an mp4"))
    COMFY.warm = True
    timings.record(videomodels.timing_key(card, quality, bool(ref_images) and h3), width, height, length, len(loras), time.time() - t0, cold)
    return mp4, next((f for f in files if f.endswith(".png")), None)


async def _run_scene(job: Job) -> None:
    p = job.params
    t0 = time.time()
    try:
        job.estimate += round(cold_extra(p["quality"], p.get("model", "h3")))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = f"{stamp}_{p['seed']}_{job.id[:4]}"
        mp4, png = await shoot(job, p["prompt"], p["width"], p["height"], p["length"], p["seed"], p.get("loras", []),
                               p.get("first_frame"), f"h3studio/{name}", p["quality"], model=p.get("model", "h3"))
        shutil.move(mp4, config.OUTPUT_DIR / f"{name}.mp4")
        from . import render, videomodels
        if not videomodels.card(p.get("model")).sound:
            await asyncio.to_thread(render.add_silence, config.OUTPUT_DIR / f"{name}.mp4")
        if png:
            shutil.move(png, config.OUTPUT_DIR / f"{name}.png")
        meta = {"params": p, "created": datetime.now().isoformat(timespec="seconds"), "seconds": round(time.time() - t0, 1)}
        (config.OUTPUT_DIR / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        job.file, job.status, job.phase = f"{name}.mp4", "done", "done"
    except asyncio.CancelledError:
        await COMFY.interrupt()
        job.status, job.phase = "cancelled", "done"
    except Exception as e:  # noqa: BLE001 - shown in the UI
        job.status, job.phase, job.error = "error", "done", str(e)
    finally:
        job.finished = time.time()


async def _run_task(job: Job) -> None:
    fn = _tasks.pop(job.id)
    try:
        job.phase = "starting" if job.kind in ("render", "graph", "take") else "llm"
        job.result = await fn(job)
        job.status, job.phase = "done", "done"
    except asyncio.CancelledError:
        if job.kind in ("render", "graph", "take"):
            await COMFY.interrupt()
        job.status, job.phase = "cancelled", "done"
    except Exception as e:  # noqa: BLE001 - shown in the UI
        job.status, job.phase, job.error = "error", "done", str(e)
    finally:
        job.finished = time.time()


async def worker() -> None:
    while True:
        job = JOBS.get(await _queue.get())
        if not job or job.status != "queued":
            continue
        job.status, job.started = "running", time.time()
        _current["id"] = job.id
        _current["task"] = asyncio.ensure_future(_run_scene(job) if job.kind == "scene" else _run_task(job))
        try:
            await _current["task"]
        except asyncio.CancelledError:
            pass
        _current["id"] = _current["task"] = None
