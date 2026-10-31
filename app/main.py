"""H3 Studio: FastAPI. One process serves the API and the page (the Vue app built into frontend/dist); ComfyUI is its child process."""
from __future__ import annotations

import asyncio
import json
import os
import random
import shutil
import subprocess
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from . import config, settings  # settings first: data/settings.json goes on top of .env before anything reads config
from . import clip_api, downloads, edit, graph, graph_api, i18n, jobs, lora_prefs, models_page, music, picture, post, projects, render, sysinfo, timings, v2v, videomodels
from .engine import graphs
from .engine.comfy import COMFY, EngineError
from .llm import client as llm, describe, translate, writer
from .planner import check, grid, model_prompts, prompts
from . import loras as lora_lib
from .loras import LoraInfo

# the page: the Vue app in frontend/, built by `npm run build` (dev.bat does it) into frontend/dist
WEB = Path(__file__).parent.parent / "frontend" / "dist"
MAX_PROMPT = 8000
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(jobs.worker())
    yield
    task.cancel()
    await llm.SERVER.stop()
    await COMFY.stop()


app = FastAPI(title="Remiqora Video", lifespan=lifespan)
# text over 1 KB goes compressed (the page's 1.4 MB script is ~0.4 MB): it matters through a tunnel, from another device;
# pictures and videos are compressed already
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(graph_api.router)   # phase 9: graph projects
app.include_router(clip_api.router)    # phase 11: a clip from a song


@app.middleware("http")
async def ui_language(request, call_next):
    """The messages of a request in the page's language (its X-Lang header; i18n.L)."""
    token = i18n.set_request(request.headers.get("x-lang"))
    try:
        return await call_next(request)
    finally:
        i18n.reset_request(token)


LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_remote: tuple[float, frozenset[str]] = (0.0, frozenset())


def remote_hosts() -> frozenset[str]:
    """The tunnel's own public names (data/remote_hosts.txt, a name a line), whose pages may call the API: the user
    looking at the studio from another device through their tunnel (ngrok, which rewrites the Host to this machine's
    and lets in only the user's own account). Read again when the file changes; no file - nobody."""
    global _remote
    f = config.DATA_DIR / "remote_hosts.txt"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return frozenset()
    if mt != _remote[0]:
        # a BOM (Notepad, PowerShell's utf8) or a comment in the ANSI code page (Set-Content in PowerShell 5.1) must
        # neither hide the first name nor take every request down with it: unreadable - the names it had, and not
        # read again until the file changes
        try:
            names = (x.strip().lower() for x in f.read_text(encoding="utf-8-sig", errors="replace").splitlines())
            _remote = (mt, frozenset(x for x in names if x and not x.startswith("#")))
        except (OSError, ValueError):
            _remote = (mt, _remote[1])
    return _remote[1]


def _hostname(netloc: str) -> Optional[str]:
    try:
        return urlsplit(f"//{netloc}").hostname
    except ValueError:
        return None


@app.middleware("http")
async def this_machine_only(request, call_next):
    """The API answers this machine's own pages only. Any site open in the browser could otherwise send it a form or a
    bodiless POST (cancel every job, stop the engine, open folders, upload files - CSRF), and a site's name pointed at
    127.0.0.1 (DNS rebinding) could read the projects too. The Host must be this machine's (unless HOST in .env opens
    the server to the network); an Origin, when the browser sends one, this server's or another local one (Vite's
    5173 in development) or the user's tunnel (remote_hosts)."""
    host = request.headers.get("host", "")
    if config.HOST in LOOPBACK and _hostname(host) not in LOOPBACK:
        return PlainTextResponse("Forbidden: unknown host", 403)
    origin = request.headers.get("origin")
    if origin is not None and urlsplit(origin).netloc != host and _hostname(urlsplit(origin).netloc) not in LOOPBACK | remote_hosts():
        return PlainTextResponse("Forbidden: another site", 403)
    return await call_next(request)


class LangRequest(BaseModel):
    ui: Optional[str] = None
    text: Optional[str] = None


@app.get("/api/lang")
def get_lang():
    """The interface's language, the texts' one and the texts' choices (their own names)."""
    return {**i18n.get(), "langs": [{"code": k, "name": v[0], "en": v[1]} for k, v in i18n.LANGS.items()]}


@app.put("/api/lang")
def put_lang(req: LangRequest):
    try:
        i18n.save(req.ui, req.text)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return get_lang()


def _lora_json(i: LoraInfo) -> dict:
    return {"id": i.id, "model": i.model, "name": i.name, "folder": i.folder, "size_mb": i.size_mb, "kind": i.kind, "verdict": i.verdict,
            "note": i.note, "rank": i.rank, "layers": i.layers, "blocks": i.blocks, "base": i.base, "trigger": i.trigger,
            "strength": lora_prefs.strength(i.id, i.model),
            "preview": f"/api/loras/preview?id={i.id}&v={int(i.mtime)}" if i.preview else None,
            **({"v2v": {**v2v.profile(i), "known": v2v.known(i)}} if i.v2v else {})}


def _version() -> str:
    """The code's version for the footer: the commit it runs (git), or "" outside a checkout."""
    try:
        r = subprocess.run(["git", "-C", str(config.ROOT), "log", "-1", "--format=%h %cs"], capture_output=True, text=True,
                           timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


VERSION = _version()


@app.get("/api/config")
def get_config():
    qualities = []
    for q, mp in graphs.QUALITY_MP.items():
        w, h = graphs.canvas(16 / 9, mp)
        qualities.append({"id": q, "mp": mp, "w": w, "h": h,
                          "per_scene": round(jobs.estimate({"quality": q, "width": w, "height": h, "length": 124}))})
    return {"aspects": [{"id": k, "ratio": v} for k, v in graphs.ASPECTS.items()], "qualities": qualities,
            "video_models": videomodels.public(),   # phase 10: H3, LTX 2.5, LTX 2.3, WAN 2.2 5B
            "problems": COMFY.problems(), "max_prompt": MAX_PROMPT, "fps": graphs.FPS,
            "lora_dirs": [str(d) for d in config.LORA_DIRS], "output_dir": str(config.OUTPUT_DIR), "version": VERSION}


@app.get("/api/system")
def system_state():
    """RAM and video memory for the header; `engine_ram` is what our ComfyUI process holds (None when it is off)."""
    engine = getattr(COMFY, "stats_pid", COMFY.pid)   # the worker reports its real process (a venv python is a launcher)
    pids = {"engine": engine, "llm": llm.SERVER.pid, "backend": os.getpid()}
    card = sysinfo.vram()
    return {"ram": sysinfo.ram(), "vram": card, "engine_ram": sysinfo.process_ram(engine),
            "engine": COMFY.state(), "busy": jobs.busy(),
            "engine_model": videomodels.card(getattr(COMFY, "model", "h3")).short if COMFY.warm else None,   # whose weights sit in memory
            "llm": llm.SERVER.model.name if llm.SERVER.pid and llm.SERVER.model else None,
            "procs": {k: sysinfo.process_ram(pid) for k, pid in pids.items()},   # RAM, GB
            "vram_by": sysinfo.vram_holders(pids, card["used"] if card else None)}


@app.post("/api/engine/free")
async def engine_free():
    if jobs.busy():
        raise HTTPException(409, i18n.L("Сейчас идёт съёмка", "A shoot is running"))
    await COMFY.free()
    return {"ok": True}


@app.post("/api/engine/stop")
async def engine_stop():
    if jobs.busy():
        raise HTTPException(409, i18n.L("Сейчас идёт съёмка", "A shoot is running"))
    await COMFY.stop()
    return {"ok": True}


@app.get("/api/loras")
def get_loras():
    return [_lora_json(i) for i in lora_lib.scan_all()]


class LoraStrength(BaseModel):
    id: str
    model: str                                 # h3 | ltx23 | ltx25 | wan5b | flux2 | krea
    strength: Optional[float] = Field(None, ge=lora_prefs.LO, le=lora_prefs.HI)   # None: back to lora_prefs.DEFAULT


@app.post("/api/loras/strength")
def lora_strength(req: LoraStrength):
    """The «LoRA» tab of a model's card: the strength a LoRA takes when it is added to a scene or a node."""
    if req.model not in (*lora_lib.LIBRARIES, "krea"):
        raise HTTPException(400, i18n.L(f"Неизвестная модель: {req.model}", f"Unknown model: {req.model}"))
    lora_prefs.set_(req.id, req.model, req.strength)
    return models_page.snapshot()


@app.get("/api/loras/preview")
def lora_preview(id: str):
    info = lora_lib.get(id)
    if not info or not info.preview:
        raise HTTPException(404)
    return FileResponse(info.preview)


# ---------- Krea 2's LoRA (KREA_LORA_DIRS) ----------
@app.get("/api/krea/loras")
def krea_lora_list():
    from . import krea_loras, picture
    return {"loras": [x.public() for x in krea_loras.LIBRARY.scan()], "dirs": [str(d) for d in config.KREA_LORA_DIRS],
            "problem": picture.problem()}


@app.get("/api/krea/loras/preview")
def krea_lora_preview(id: str):
    from . import krea_loras
    info = krea_loras.LIBRARY.get(id)
    if not info or not info.preview:
        raise HTTPException(404)
    return FileResponse(info.preview)


@app.post("/api/frames")
async def upload_frame(file: UploadFile):
    """A start frame for "from a picture": stored in ComfyUI's input folder under a plain name."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(400, i18n.L("Нужна картинка: png, jpg или webp", "A picture is needed: png, jpg or webp"))
    name = f"h3s_{uuid.uuid4().hex[:12]}{ext}"
    with open(config.COMFY_INPUT / name, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"name": name, "url": f"/frames/{name}"}


@app.post("/api/frames/from-video/{name}")
def frame_from_video(name: str):
    """The last frame of a finished scene as the start frame of the next one (a manual chain)."""
    png = (config.OUTPUT_DIR / Path(name).name).with_suffix(".png")
    if not png.exists():
        raise HTTPException(404, i18n.L("У этого ролика нет последнего кадра", "This video has no last frame"))
    dst = f"h3s_{uuid.uuid4().hex[:12]}.png"
    shutil.copyfile(png, config.COMFY_INPUT / dst)
    return {"name": dst, "url": f"/frames/{dst}"}


@app.get("/api/llm/models")
def llm_models():
    """GGUF models from LLM_DIRS (LM Studio's download folder among them) and which one is the default."""
    ms = llm.models()
    try:
        default = llm.find(None).id
    except llm.LLMError:
        default = None
    return {"models": [m.public() for m in ms], "default": default, "dirs": [str(d) for d in config.LLM_DIRS],
            "server_ok": config.LLAMA_SERVER_BIN.exists()}


class DescribeRequest(BaseModel):
    frame: str                       # a name from /api/frames
    model: Optional[str] = None      # an id from /api/llm/models; None = the default


@app.post("/api/llm/describe")
def llm_describe(req: DescribeRequest):
    """The person in the start frame -> the hero's look (en / ru). A job in the GPU queue; poll /api/jobs/{id}."""
    path = config.COMFY_INPUT / Path(req.frame).name
    if not path.exists():
        raise HTTPException(400, i18n.L("Кадр не найден, загрузите его снова", "Frame not found, upload it again"))
    try:
        m = llm.find(req.model)
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    if not m.mmproj:
        raise HTTPException(400, i18n.L(f"Модель {m.name} не видит картинок: рядом с ней нет mmproj-файла", f"Model {m.name} can't see pictures: there is no mmproj file next to it"))
    return jobs.submit_task("describe", {"frame": req.frame, "model": m.id, "model_name": m.name},
                            lambda job: describe.describe(path, m.id), estimate=25).public()


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_PROMPT)   # the lab's prompt in Russian
    seconds: float = Field(5, ge=1, le=15)                   # the lab's length: the timeline runs to it
    model: Optional[str] = None
    video_model: str = "h3"                                  # the lab's model: the prompt takes its form
    frame: bool = False                                      # the shot starts from a picture
    target: str = Field("video", pattern="^(video|picture|frame)$")   # "picture": a graph's Krea node, a still; "frame": one drawn by reference (FLUX.2 Klein)


@app.post("/api/llm/translate")
def llm_translate(req: TranslateRequest):
    """The lab's Russian prompt -> an English one in its model's form (spoken lines stay Russian). A job in the GPU queue."""
    try:
        m = llm.find(req.model)
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    return jobs.submit_task("translate", {"model": m.id, "model_name": m.name, "seconds": req.seconds},
                            lambda job: translate.translate(req.text, req.seconds, m.id, video=req.video_model, frame=req.frame, target=req.target), estimate=30).public()


class TranslateLookRequest(BaseModel):
    ru: str = Field(min_length=1, max_length=2000)            # a graph Hero's look and outfit, in Russian
    gender: str = ""
    age: Optional[int] = None
    model: Optional[str] = None


@app.post("/api/llm/translate-look")
def llm_translate_look(req: TranslateLookRequest):
    """A graph Hero's Russian look -> its English look and outfit (writer.translate_look). A job in the GPU queue."""
    try:
        m = llm.find(req.model)
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    return jobs.submit_task("translate", {"model": m.id, "model_name": m.name, "what": "look"},
                            lambda job: writer.translate_look(req.ru, req.gender, req.age, m.id), estimate=20).public()


class TranslateFieldsRequest(BaseModel):
    fields: dict                                             # the lab's scene form, Russian: style, place, camera, beats, audio
    seconds: float = Field(5, ge=1, le=15)
    model: Optional[str] = None
    video_model: str = "h3"


@app.post("/api/llm/translate-fields")
def llm_translate_fields(req: TranslateFieldsRequest):
    """The lab's scene form, Russian -> English, field by field (spoken lines stay Russian). A job in the GPU queue."""
    if sum(len(str(v)) for v in req.fields.values()) > MAX_PROMPT:
        raise HTTPException(400, i18n.L("Слишком длинный текст", "The text is too long"))
    try:
        m = llm.find(req.model)
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    return jobs.submit_task("translate", {"model": m.id, "model_name": m.name, "seconds": req.seconds},
                            lambda job: translate.translate_fields(req.fields, req.seconds, m.id, video=req.video_model), estimate=30).public()


# ---------- projects: the idea, the storyboard, (phase 4) the shots ----------

MOODS = {   # the idea screen's chips -> what the writer reads
    "Кино": "cinematic live-action film",
    "Клип": "music video: rhythmic, stylish, expressive motion",
    "Реклама": "polished commercial: clean, bright, aspirational",
    "Фэнтези и эффекты": "epic fantasy with visual effects, photoreal",
    "Документальное": "documentary: natural, observational, handheld feel",
}


def _project(pid: str) -> dict:
    try:
        return projects.load(pid)
    except projects.NotFound as e:
        raise HTTPException(404, i18n.L("Проект не найден", "Project not found")) from e


@app.get("/api/projects")
def list_projects():
    return {"projects": projects.all_projects(), "moods": list(MOODS)}


class NewProject(BaseModel):
    idea: str = Field("", max_length=4000)
    seconds: float = Field(30, ge=5, le=grid.MAX_SECONDS)
    mode: str = "one"                # one | several | none: who is in the frame
    aspect: str = "16:9"
    mood: str = Field("", max_length=200)
    music: str = Field("", max_length=300)
    photo: Optional[str] = None      # a name from /api/frames: the hero's photo, described by the writer
    photo_start: bool = False        # the photo is also the very first frame: scene 1 starts from it (i2v)
    seed: int = -1
    model: Optional[str] = None
    manual: bool = False             # no writer: empty scenes, the user writes every prompt by hand
    video_model: str = "h3"          # phase 10: which model shoots it (videomodels.CARDS)
    loras: list[dict] = []           # the video's LoRA [{id, name, strength}], as «Съёмка» → LoRA keeps them
    pic_loras: dict = {}             # «LoRA картинок»: {"krea": [...], "flux2": [...]} (picture.project_loras)


@app.post("/api/projects")
def new_project(req: NewProject):
    """The idea screen's «Расписать сцены»: a project on disk + the writer's job (photo description and storyboard
    in one model load). The plan is saved into the project by the job itself."""
    if req.mode not in grid.MODES:
        raise HTTPException(400, i18n.L(f"Неизвестный режим: {req.mode}", f"Unknown mode: {req.mode}"))
    if req.aspect not in graphs.ASPECTS:
        raise HTTPException(400, i18n.L(f"Неизвестный формат кадра: {req.aspect}", f"Unknown frame format: {req.aspect}"))
    if not videomodels.offered(req.video_model):
        raise HTTPException(400, i18n.L(f"Неизвестная модель: {req.video_model}", f"Unknown model: {req.video_model}"))
    if req.manual:
        return _manual_project(req)
    if len(req.idea.strip()) < 3:
        raise HTTPException(400, i18n.L("Напишите идею", "Write an idea"))
    try:
        model = llm.find(req.model)
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    photo = None
    if req.photo:
        photo = config.COMFY_INPUT / Path(req.photo).name
        if not photo.exists():
            raise HTTPException(400, i18n.L("Фото не найдено, загрузите его снова", "Photo not found, upload it again"))
        if (req.mode != "none" or req.photo_start) and not model.mmproj:
            raise HTTPException(400, i18n.L(f"Модель {model.name} не видит картинок: выберите другую или уберите фото", f"Model {model.name} can't see pictures: choose another one or remove the photo"))
    settings = {**req.model_dump(exclude={"photo", "model"}), "model": model.id, "quality": "draft", "loras": picture.pick_loras(req.loras), "rtx": True,
                "pic_loras": picture.pick_pic_loras(req.pic_loras)}
    proj = projects.create(settings)
    if photo:
        settings["photo"] = projects.put_photo(proj["id"], photo)
        projects.save(proj)
    return {"project": proj["id"], "job": _writer_job(proj["id"], req, model, settings.get("photo"))}


class WriteAgain(BaseModel):
    model: Optional[str] = None      # the writer picked in the header now


@app.post("/api/projects/{pid}/write")
def project_write(pid: str, req: WriteAgain):
    """«Расписать ещё раз» on an empty storyboard: the writer failed on a new project - the same idea and settings once
    more (a clip starts again from the home screen: its job cuts the song first)."""
    proj = _project(pid)
    st = proj.get("settings") or {}
    if proj.get("plan"):
        raise HTTPException(400, i18n.L("Раскадровка уже написана", "The storyboard is written already"))
    if st.get("clip") or len((st.get("idea") or "").strip()) < 3:
        raise HTTPException(400, i18n.L("Нечего расписывать заново: начните с главной", "Nothing to write again: start from the home screen"))
    # the saved settings checked as a new project's are: a model gone since (removed, an import) is said, not shot as H3
    # with its 5 s grid
    if not videomodels.offered(st.get("video_model") or "h3"):
        raise HTTPException(400, i18n.L(f"Неизвестная модель: {st.get('video_model')}", f"Unknown model: {st.get('video_model')}"))
    if (st.get("mode") or "one") not in grid.MODES or (st.get("aspect") or "16:9") not in graphs.ASPECTS:
        raise HTTPException(400, i18n.L("Нечего расписывать заново: начните с главной", "Nothing to write again: start from the home screen"))
    try:
        model = llm.find(req.model or st.get("model"))
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    if st.get("photo") and (st.get("mode") != "none" or st.get("photo_start")) and not model.mmproj:
        raise HTTPException(400, i18n.L(f"Модель {model.name} не видит картинок: выберите другую в шапке", f"Model {model.name} can't see pictures: choose another one in the header"))
    again = NewProject(**{k: v for k, v in st.items() if k in NewProject.model_fields and k not in ("photo", "model", "manual")})
    with _write_lock:   # two quick clicks: one writer, the second hears it is writing
        if any(j.kind == "write" and j.status in ("queued", "running") and j.params.get("project") == pid for j in jobs.JOBS.values()):
            raise HTTPException(409, i18n.L("Сценарист уже пишет этот ролик", "The writer is already writing this video"))
        return {"project": pid, "job": _writer_job(pid, again, model, st.get("photo"))}


_write_lock = threading.Lock()


def _writer_job(pid: str, req: NewProject, model, photo: Optional[str]) -> dict:
    """The writer's job of a new project: the storyboard written from the idea and saved into the project."""
    mood = ", ".join(x for x in (MOODS.get(req.mood, req.mood),) if x)
    plan = writer.new_plan(req.idea, req.seconds, req.mode, mood, req.music, None,
                           seed=req.seed if req.seed >= 0 else random.randrange(100000), model=model.id,
                           scene_seconds=videomodels.card(req.video_model).grid_seconds)   # LTX: scenes of 10 s
    if photo and req.photo_start:
        plan["scenes"][0]["start_photo"] = photo
    plan["video"] = req.video_model   # the writer knows what shoots (writer.MODEL_NOTES)

    async def run(job):
        p = await writer.write(plan, projects.photo_path(projects.load(pid)) if req.mode != "none" else None, projects.folder(pid))
        timings.record_writer(p.get("writer") or {}, len(p["scenes"]))
        cur = projects.load(pid)
        cur["plan"] = check.plan(p)
        cur["name"] = p.get("title_ru") or cur.get("name")
        projects.save(cur)
        return {"project": pid}

    n = len(plan["scenes"])
    job = jobs.submit_task("write", {"project": pid, "idea": req.idea[:80], "scenes": n}, run,
                           estimate=timings.writer_seconds(model.name, n, 8 + 3 * n) + (10 if photo else 0))
    return job.public()


def _manual_project(req: NewProject) -> dict:
    """«Без сценариста»: the storyboard's grid with empty scenes, each one's prompt written by hand (prompts.is_raw)."""
    settings = {**req.model_dump(exclude={"photo", "model", "manual"}), "model": None, "quality": "draft", "loras": picture.pick_loras(req.loras), "rtx": True,
                "pic_loras": picture.pick_pic_loras(req.pic_loras)}
    proj = projects.create(settings)
    plan = writer.new_plan(req.idea or "", req.seconds, req.mode, seed=random.randrange(100000),
                           scene_seconds=videomodels.card(req.video_model).grid_seconds)
    plan["manual"] = True
    for s in plan["scenes"]:
        s.update(raw="", locked=True, source="user")
    proj["plan"] = check.plan(plan)
    proj["name"] = req.idea.strip()[:60] or i18n.L("Свои промты", "Own prompts")
    projects.save(proj)
    return {"project": proj["id"], "job": None}


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    proj = _project(pid)
    if proj.get("plan") and edit.ensure_ids(proj["plan"]):   # a plan written before ids: they are given for good
        projects.save(proj)
    return proj


@app.get("/api/projects/{pid}/photo")
def project_photo(pid: str):
    path = projects.photo_path(_project(pid))
    if not path or not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


class ProjectEdit(BaseModel):
    plan: Optional[dict] = None      # the storyboard after hand edits
    settings: Optional[dict] = None  # quality, loras, rtx, aspect
    name: Optional[str] = Field(None, max_length=120)
    # the project's `updated` the page's copy was made from: a job that saved the project since (a retake's seed and
    # camera, a drawn frame) makes the edit a 409 - the page takes the saved project, keeps its own edits on top and
    # sends again (lib/project.ts adopt), instead of a whole stale plan putting the job's fields back. None: no check
    # (a script, the graph's own page)
    rev: Optional[float] = None


def _stale(pid: str, rev: Optional[float], proj: Optional[dict] = None) -> None:
    if rev is None:
        return
    now = (proj or _project(pid)).get("updated") or 0
    if abs(now - rev) > 1e-6:
        raise HTTPException(409, {"message": i18n.L("Проект изменился, пока вы правили: беру новый и сохраняю правку ещё раз",
                                                    "The project changed while you edited: taking the new one and saving the edit again"),
                                  "rev": now})


@app.put("/api/projects/{pid}")
def put_project(pid: str, body: ProjectEdit):
    """Save hand edits; the grid, the prompts and the validator run again on the way (no LLM)."""
    proj = _project(pid)
    _stale(pid, body.rev, proj)
    if body.plan is not None:
        if not isinstance(body.plan.get("scenes"), list) or body.plan.get("mode") not in grid.MODES or not body.plan["scenes"]:
            raise HTTPException(400, i18n.L("Это не раскадровка", "This is not a storyboard"))
        proj["plan"] = check.plan(body.plan)
    if body.settings is not None:
        keep = {k: body.settings[k] for k in ("quality", "loras", "rtx", "aspect", "output", "video_model", "track_sync", "size") if k in body.settings}
        if "pic_loras" in body.settings:
            keep["pic_loras"] = picture.pick_pic_loras(body.settings["pic_loras"])
        if keep.get("quality", "draft") not in graphs.QUALITY_MP or keep.get("aspect", "16:9") not in graphs.ASPECTS:
            raise HTTPException(400, i18n.L("Неизвестное качество или формат кадра", "Unknown quality or frame format"))
        if not videomodels.offered(keep.get("video_model", "h3")):
            raise HTTPException(400, i18n.L("Неизвестная модель", "Unknown model"))
        if "track_sync" in keep:
            keep["track_sync"] = bool(keep["track_sync"])
        if "size" in keep:   # an own frame {w, h} snapped to the model's step, or None - back to the format's size
            if keep["size"] is None:
                proj["settings"].pop("size", None)
                del keep["size"]
            else:
                own = videomodels.own_size({"size": keep["size"]}, videomodels.card(keep.get("video_model", proj["settings"].get("video_model"))))
                if not own:
                    raise HTTPException(400, i18n.L("Размер кадра: ширина и высота в пикселях", "Frame size: width and height in pixels"))
                keep["size"] = {"w": own[0], "h": own[1]}
        if "output" in keep:   # size off / 1080p / 4k, HDR10, 48 fps; `rtx` follows for older readers
            keep["output"] = post.output_of({"output": keep["output"]})
            keep["rtx"] = keep["output"]["size"] != "off"
        proj["settings"].update(keep)
    if body.name is not None:
        proj["name"] = body.name.strip() or proj.get("name")
    _stale(pid, body.rev)   # a job saved while the plan was checked (the window of check.plan): not over it
    return projects.save(proj)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    if any(j.status in ("queued", "running") and j.params.get("project") == pid for j in jobs.JOBS.values()):
        raise HTTPException(409, i18n.L("Ролик сейчас в работе — удалить его можно, когда работа закончится", "The video is being worked on: it can be deleted when the work is done"))
    _project(pid)
    projects.remove(pid)
    return {"ok": True}


class RewriteRequest(BaseModel):
    scenes: list[int] = []
    how: str = "variant"             # improve | variant | unlocked | fill | translate
    note: str = Field("", max_length=1000)
    seed: Optional[int] = None


@app.post("/api/projects/{pid}/rewrite")
def project_rewrite(pid: str, req: RewriteRequest):
    """The scene buttons («Улучшить», «Другой вариант», «Пересоздать незакреплённые»), filling added scenes and
    following the user's Russian edits. The job reads the saved project when it starts: save edits first."""
    if req.how not in ("improve", "variant", "unlocked", "fill", "translate", "looks", "frame", "lines", "ru", "propagate"):
        raise HTTPException(400, i18n.L(f"Неизвестное действие: {req.how}", f"Unknown action: {req.how}"))
    proj = _project(pid)
    if not proj.get("plan"):
        raise HTTPException(400, i18n.L("Раскадровка ещё не написана", "The storyboard is not written yet"))
    if req.how == "frame":   # the writer looks at the start photo first
        try:
            m = llm.find(proj["plan"].get("model"))
        except llm.LLMError as e:
            raise HTTPException(400, str(e)) from e
        if not m.mmproj:
            raise HTTPException(400, i18n.L(f"Модель {m.name} не видит картинок: выберите другую в шапке", f"Model {m.name} can't see pictures: choose another one in the header"))
    if req.how == "propagate" and not (req.scenes and 0 <= req.scenes[0] < len(proj["plan"]["scenes"])):
        raise HTTPException(400, i18n.L("«Обновить сюжет»: нет такой сцены", "«Update the story»: no such scene"))
    n = len(proj["plan"]["scenes"]) if req.how == "unlocked" else len(req.scenes)
    if req.how == "ru":   # «Перевести на русский»: the English scenes (all of them when none are named)
        n = sum(1 for i, s in enumerate(proj["plan"]["scenes"]) if (not req.scenes or i in req.scenes) and translate.needs_russian(s))
        if not n:
            raise HTTPException(400, i18n.L(f"Переводить нечего: все сцены уже на языке текстов ({i18n.LANGS[i18n.text()][0]})", f"Nothing to translate: every scene is in the texts' language already ({i18n.LANGS[i18n.text()][0]})"))

    async def run(job):
        cur = projects.load(pid)
        cur["plan"]["video"] = cur["settings"].get("video_model") or "h3"   # the model may have changed since it was written
        if req.how == "looks":   # the edited Russian look of the characters (scenes = their indices) or the world
            p = await writer.rewrite_looks(cur["plan"], req.scenes or None, req.seed)
        elif req.how == "lines":   # «Придумать реплики»: what the people of these scenes say
            p = await writer.write_lines(cur["plan"], req.scenes, req.seed)
        elif req.how == "propagate":   # «Обновить сюжет от этой сцены»: the scenes the edited one makes wrong
            p = await writer.propagate(cur["plan"], req.scenes[0] if req.scenes else -1, req.seed)
            job.progress["propagated"] = [{"scene": x["index"] + 1, "reason": x["reason"]} for x in (p.get("propagated") or {}).get("scenes") or []]
        elif req.how == "ru":
            def step(done: int, total: int) -> None:
                job.phase, job.step, job.steps = "writing", done, total
            p = await translate.to_russian(cur["plan"], req.scenes or None, step)
            cur = projects.load(pid)   # the user may have edited while it ran: only the translations go in
            done = {y.get("id"): y for y in p["scenes"]}
            for x in cur["plan"]["scenes"]:
                y = done.get(x.get("id")) or {}
                if y.get("ru_en") and x.get("ru") == y["ru_en"]:   # its English text, untouched meanwhile
                    x["ru_en"], x["ru"] = y["ru_en"], y["ru"]
                if y.get("raw_ru") and x.get("raw") == y.get("raw"):
                    x["raw_ru"] = y["raw_ru"]
            projects.save(cur)
            return {"project": pid}
        else:
            p = await writer.rewrite_scenes(cur["plan"], req.scenes, req.how, req.seed, req.note, projects.folder(pid))
        cur = projects.load(pid)   # settings may have changed meanwhile; the plan is ours
        cur["plan"] = check.plan(p)
        projects.save(cur)
        return {"project": pid}

    return jobs.submit_task("rewrite", {"project": pid, "how": req.how, "scenes": req.scenes}, run,
                            estimate=8 + (9 if req.how == "ru" else 25 if req.how == "propagate" else 3) * max(1, n)).public()


@app.post("/api/projects/{pid}/propagate/undo")
def propagate_undo(pid: str):
    """«Вернуть как было»: the scenes the last «Обновить сюжет от этой сцены» rewrote, back as they were."""
    proj = _project(pid)
    if not writer.unpropagate(proj.get("plan") or {}):
        raise HTTPException(400, i18n.L("Возвращать нечего", "Nothing to put back"))
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)



class RenderRequest(BaseModel):
    quality: Optional[str] = None    # draft | final; None = the project's


@app.post("/api/projects/{pid}/render")
def project_render(pid: str, req: RenderRequest):
    """«Снять ролик»: the whole storyboard as a chain (cached scenes are taken as they are), assembled, upscaled."""
    proj = _project(pid)
    if not proj.get("plan"):
        raise HTTPException(400, i18n.L("Раскадровка ещё не написана", "The storyboard is not written yet"))
    if issues := COMFY.problems():
        raise HTTPException(400, "; ".join(issues))
    if any(j.status in ("queued", "running") and j.kind == "render" and j.params.get("project") == pid for j in jobs.JOBS.values()):
        raise HTTPException(409, i18n.L("Этот ролик уже снимается", "This video is already being shot"))
    if req.quality:
        if req.quality not in graphs.QUALITY_MP:
            raise HTTPException(400, i18n.L(f"Неизвестное качество: {req.quality}", f"Unknown quality: {req.quality}"))
        proj["settings"]["quality"] = req.quality
        projects.save(proj)
    n = len(proj["plan"]["scenes"])
    return jobs.submit_task("render", {"project": pid, "quality": proj["settings"]["quality"], "scenes": n,
                                       "model": videomodels.of(proj["settings"]).short},
                            lambda job: render.run(job, pid), estimate=render.estimate(proj["settings"], proj["plan"]["scenes"]) + 30).public()


# ---------- the montage (phase 8): how the shots are cut and joined; nothing is shot again ----------
def _edit_view(proj: dict, quality: Optional[str] = None) -> dict:
    pre = render.preview(proj, quality)
    ed = edit.resolve(proj, pre["keys"], [r == "cached" for r in pre["scenes"]], pre["takes"])
    saved = (proj.get("renders") or {}).get(pre["quality"]) or {}
    return {**ed, "quality": pre["quality"], "width": pre["width"], "height": pre["height"], "fps": edit.FPS,
            "sig": edit.signature(ed), "built_sig": saved.get("edit_sig"), "built": bool(saved.get("complete")),
            "to_shoot": pre["to_shoot"], "track": proj["settings"].get("track"), "kind": "board",
            "resolve_dir": proj.get("resolve_dir") or str(projects.folder(proj["id"]))}


@app.get("/api/projects/{pid}/edit")
def get_edit(pid: str, quality: Optional[str] = None):
    """The montage against the storyboard and the shots of this quality (a stored one, or the storyboard's own)."""
    proj = _project(pid)
    if not (proj.get("plan") or {}).get("scenes"):
        raise HTTPException(400, i18n.L("Раскадровка ещё не написана", "The storyboard is not written yet"))
    if edit.ensure_ids(proj["plan"]):   # scenes of a plan written before the montage get their ids for good
        projects.save(proj)
    return _edit_view(proj, quality)


class EditBody(BaseModel):
    clips: list[dict]
    off: list[str] = []
    sounds: list[dict] = []
    overlays: list[dict] = []        # «Поверх» (edit.py)
    duck: float = 0
    grade: Optional[str] = None      # the video's colour (edit.GRADES or "lut")
    lut: Optional[str] = None
    match: bool = False
    color: Optional[dict] = None
    scene_colors: dict[str, dict] = {}
    lut_mix: float = 1               # how much of the LUT (edit.look_of)
    vignette: float = 0
    grain: float = 0


@app.put("/api/projects/{pid}/edit")
def put_edit(pid: str, body: EditBody, quality: Optional[str] = None):
    proj = _project(pid)
    if not (proj.get("plan") or {}).get("scenes"):
        raise HTTPException(400, i18n.L("Раскадровка ещё не написана", "The storyboard is not written yet"))
    edit.ensure_ids(proj["plan"])
    try:
        proj["edit"] = edit.stored(body.model_dump())
    except (TypeError, ValueError) as e:
        raise HTTPException(400, i18n.L(f"Монтаж не читается: {e}", f"The montage can't be read: {e}")) from e
    projects.save(proj)
    return _edit_view(proj, quality)


@app.post("/api/projects/{pid}/sounds")
async def upload_sound(pid: str, file: UploadFile):
    """A sound for the montage's «Звуки» lane: kept in the project's sounds/ (the montage points at it)."""
    _project(pid)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in music.AUDIO_EXT:
        raise HTTPException(400, i18n.L("Нужен звуковой файл: mp3, wav, m4a, flac или ogg", "A sound file is needed: mp3, wav, m4a, flac or ogg"))
    d = projects.folder(pid) / "sounds"
    d.mkdir(exist_ok=True)
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in Path(file.filename or "sound").stem)[:40] or "sound"
    dst = d / f"{uuid.uuid4().hex[:6]}_{stem}{ext}"
    with open(dst, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        dur = await asyncio.to_thread(music.duration, dst)
    except Exception as e:  # noqa: BLE001 - a broken file is the user's to replace
        dst.unlink(missing_ok=True)
        raise HTTPException(400, str(e)) from e
    return {"file": f"sounds/{dst.name}", "name": Path(file.filename or dst.name).name, "length": round(dur, 3)}


@app.post("/api/projects/{pid}/luts")
async def upload_lut(pid: str, file: UploadFile):
    """A colour LUT (.cube) for the montage's «Цвет ролика»: kept in the project's luts/."""
    _project(pid)
    if Path(file.filename or "").suffix.lower() != ".cube":
        raise HTTPException(400, i18n.L("Нужен LUT в формате .cube", "A LUT in .cube format is needed"))
    d = projects.folder(pid) / "luts"
    d.mkdir(exist_ok=True)
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in Path(file.filename or "lut").stem)[:40] or "lut"
    dst = d / f"{uuid.uuid4().hex[:6]}_{stem}.cube"
    with open(dst, "wb") as f:
        shutil.copyfileobj(file.file, f)
    if b"LUT_3D_SIZE" not in dst.read_bytes()[:20000]:
        dst.unlink(missing_ok=True)
        raise HTTPException(400, i18n.L("Это не 3D LUT (.cube без LUT_3D_SIZE)", "This is not a 3D LUT (.cube without LUT_3D_SIZE)"))
    return {"file": f"luts/{dst.name}", "name": Path(file.filename or dst.name).name}


@app.get("/api/projects/{pid}/peaks")
def file_peaks(pid: str, file: str):
    """A file's waveform for the montage's lanes: 50 values a second, 0-255."""
    folder = projects.folder(_project(pid)["id"])
    p = (folder / file).resolve()
    if folder.resolve() not in p.parents or not p.is_file():
        raise HTTPException(404, i18n.L("Нет такого файла", "No such file"))
    try:
        return {"rate": edit.PEAKS_PER_S, "peaks": edit.peaks(p)}
    except OSError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/projects/{pid}/beats")
def track_beats(pid: str):
    """The montage's «Магнит»: the beats and bar lines of the video's track, in the video's time (the track plays from
    its offset), from the song analysis of phase 11 (song.analyze, ~0.4 s; kept next to the waveforms)."""
    return _beats(_project(pid))


def _beats(proj: dict, fixed: bool = True) -> dict:
    """track_beats of a project as loaded; `fixed=False` - the found beats without «Отметить удар»'s fix."""
    track = proj["settings"].get("track") or {}
    folder = projects.folder(proj["id"])
    p = folder / track["file"] if track.get("file") else None
    if not p or not p.is_file():
        return {"bpm": None, "beats": [], "bars": []}
    side = folder / "_peaks" / f"{p.name}.beats.json"
    try:
        a = json.loads(side.read_text(encoding="utf-8"))
        if a.get("mtime") != int(p.stat().st_mtime):
            raise ValueError
    except (OSError, ValueError):
        from . import song
        x = song.analyze(p)
        a = {"mtime": int(p.stat().st_mtime), "bpm": x.bpm, "beats": [round(float(t), 3) for t in x.beats],
             "bars": [round(float(t), 3) for t in x.bars]}
        side.parent.mkdir(exist_ok=True)
        side.write_text(json.dumps(a), encoding="utf-8")
    off = float(track.get("offset") or 0)
    fx = (track.get("beat_fix") or {}) if fixed else {}
    k, c = float(fx.get("a", 1.0)), float(fx.get("b", 0.0))   # «Отметить удар»: the found beats moved onto the heard ones
    shift = lambda ts: [round(k * t + c - off, 3) for t in ts if k * t + c >= off]  # noqa: E731
    return {"bpm": round(a["bpm"] / k, 1), "beats": shift(a["beats"]), "bars": shift(a["bars"]),
            "fixed": len(fx.get("taps") or [])}


class BeatTaps(BaseModel):
    taps: list[float] = []           # the video's seconds where the user heard a beat (the montage's «Удар», key B)


BEAT_FIX_MAX = (0.9, 1.1)            # a tempo fix past ±10 % is a wrong tap, not a drift


@app.put("/api/projects/{pid}/beats/fix")
def track_beats_fix(pid: str, req: BeatTaps):
    """«Отметить удар»: on a live song the found beats drift from the heard ones. Each tap is
    paired with the found beat nearest to it; one tap moves all the beats (an offset), two and more also stretch them
    (the drift) - a line t' = a·t + b by least squares, in the song's time (the track's offset may change). No taps -
    the found beats as they are."""
    proj = _project(pid)
    track = proj["settings"].get("track")
    if not track:
        raise HTTPException(400, i18n.L("У ролика нет трека", "The video has no track"))
    # the fix before stays until the new one is made: taps that find no beats leave it as it was
    if not req.taps:
        track.pop("beat_fix", None)
    else:
        found = _beats(proj, fixed=False)["beats"]   # in the video's time
        if not found:
            raise HTTPException(400, i18n.L("У трека не нашлось долей", "No beats were found in the track"))
        off = float(track.get("offset") or 0)
        song_beats = [t + off for t in found]
        a, b, pairs = 1.0, 0.0, {}

        def fit() -> tuple[float, float]:
            xs, ys = list(pairs), list(pairs.values())
            if len(xs) < 2 or max(xs) - min(xs) < 1:
                return 1.0, sum(y - x for x, y in pairs.items()) / len(pairs)
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            k = min(max(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs), *BEAT_FIX_MAX[:1]), BEAT_FIX_MAX[1])
            return k, my - k * mx
        # in time order, each tap read through the fix of the taps before it: a drift grown past half a beat by the
        # end of the song still pairs the last tap with its own beat, not the next one
        for t in sorted(x + off for x in req.taps):
            x = min(song_beats, key=lambda s: abs(a * s + b - t))
            pairs[x] = t
            a, b = fit()
        track["beat_fix"] = {"a": round(a, 6), "b": round(b, 4), "taps": [round(t, 3) for t in req.taps][:32]}
    projects.save(proj)
    return _beats(proj)


class ResolveRequest(BaseModel):
    dir: Optional[str] = None        # the folder the user chose; none - the project's resolve/


@app.post("/api/projects/{pid}/edit/resolve")
def edit_to_resolve(pid: str, req: ResolveRequest, quality: Optional[str] = None):
    """«Для DaVinci Resolve»: the montage as an FCPXML timeline with its files, in a folder of its own in the one the
    user chose (remembered in the project) or in the project's resolve/; it opens in Explorer (resolve.py)."""
    from . import resolve
    proj = _project(pid)
    if not (proj.get("plan") or {}).get("scenes"):
        raise HTTPException(400, i18n.L("Раскадровка ещё не написана", "The storyboard is not written yet"))
    place = Path(req.dir) if req.dir else None
    if place is not None and not place.is_dir():
        raise HTTPException(400, i18n.L(f"Нет такой папки: {req.dir}", f"No such folder: {req.dir}"))
    v = _edit_view(proj, quality)
    try:
        out = resolve.export(proj, v, projects.folder(pid), v["width"], v["height"], v["quality"], place)
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e)) from e
    if place is not None and proj.get("resolve_dir") != str(place):
        proj["resolve_dir"] = str(place)
        projects.save(proj)
    os.startfile(out["dir"])  # Windows: the Explorer window on this machine
    return out


@app.delete("/api/projects/{pid}/edit")
def reset_edit(pid: str, quality: Optional[str] = None):
    """«Как в раскадровке»: the montage goes, the video is put together as the storyboard says."""
    proj = _project(pid)
    proj.pop("edit", None)
    projects.save(proj)
    return _edit_view(proj, quality)


class InsertScene(BaseModel):
    kind: str = "continue"   # continue: in the episode of scene i; new: a new episode after it


@app.post("/api/projects/{pid}/scenes/{i}/insert")
def insert_scene(pid: str, i: int, req: InsertScene):
    """«+ Сцена» / «+ Эпизод»: an empty scene after scene i - a continuation in its episode, or a new episode. In a clip
    it takes the second half of scene i's time (clip.split), so the song stays where it is under every other scene;
    elsewhere it is one scene more. The writer fills it after (rewrite "fill"). -> the project."""
    from .planner import clip as clip_plan
    proj = _project(pid)
    plan = proj.get("plan") or {}
    scenes = plan.get("scenes") or []
    if not 0 <= i < len(scenes) or req.kind not in ("continue", "new"):
        raise HTTPException(404, i18n.L("Нет такой сцены", "No such scene"))
    if _shooting(pid):
        raise HTTPException(409, i18n.L("Этот ролик сейчас снимается — сцену после", "This video is being shot now: the scene after that"))
    new = {"kind": req.kind, "ru": "", "beats_en": [], "framing": "medium", "camera": "static", "sound_en": "", "place_en": "", "to_en": "",
           "locked": bool(plan.get("manual")), "source": "user" if plan.get("manual") else "", "status": "", "problems": [], "prompt": "",
           **({"raw": ""} if plan.get("manual") else {})}
    c = plan.get("clip")
    if c and c.get("song"):
        from . import song
        facts = clip_plan.split(plan, i, song.analysis(c["song"]).bars, song.lines(c["song"]))
        if facts is None:
            raise HTTPException(400, i18n.L(f"Сцена {i + 1} слишком короткая, чтобы отдать время новой: выберите другую",
                                            f"Scene {i + 1} is too short to give time to a new one: pick another"))
        new.update(facts)
        if scenes[i].get("model"):
            new["model"] = scenes[i]["model"]
        writer.clip_shot(plan, scenes[i], scenes[i].get("shot") if scenes[i].get("shot_user") else None)
        writer.clip_shot(plan, new, "sing" if new["voice"] >= clip_plan.SING_SHARE else "perform")
    else:
        new["seconds"] = scenes[i].get("seconds")
    scenes.insert(i + 1, new)
    proj["plan"] = check.plan(plan)
    projects.save(proj)
    return proj


class TakeRequest(BaseModel):
    scene: int


@app.post("/api/projects/{pid}/takes")
def new_take(pid: str, req: TakeRequest):
    """«Ещё дубль»: the scene gets one more take with a new seed, chosen at once, and only it is shot (a job of its
    own). The scenes that start from its last frame will be shot again by «Снять ролик»."""
    proj = _project(pid)
    plan = proj.get("plan") or {}
    if not 0 <= req.scene < len(plan.get("scenes") or []):
        raise HTTPException(404, i18n.L("Нет такой сцены", "No such scene"))
    if issues := COMFY.problems():
        raise HTTPException(400, "; ".join(issues))
    if _shooting(pid):
        raise HTTPException(409, i18n.L("Этот ролик сейчас снимается — дубль после", "This video is being shot now: the take after that"))
    s = plan["scenes"][req.scene]
    seeds = render.takes_of(plan, s)
    seed = random.randrange(1, 2**31)
    s["takes"], s["seed"] = seeds + [seed], seed
    proj["plan"] = check.plan(plan)
    projects.save(proj)
    w, h = render.size(proj["settings"])
    q = proj["settings"].get("quality", "draft")
    return jobs.submit_task("take", {"project": pid, "scene": req.scene, "seed": seed, "quality": q, "model": videomodels.of(proj["settings"]).short},
                            lambda job: render.shoot_take(job, pid, req.scene, seed),
                            estimate=render.one_scene(proj["settings"], q, w, h, render.scene_length(proj["settings"])) + 30).public()


def _shooting(pid: str) -> bool:
    """A shot of this video is queued or running: it reads the track (a scene shot to it) and the frames."""
    return any(j.status in ("queued", "running") and j.kind in ("render", "take") and j.params.get("project") == pid
               for j in jobs.JOBS.values())


@app.post("/api/projects/{pid}/track")
async def upload_track(pid: str, file: UploadFile):
    """Your own track for the whole video: stored in the project, mixed over the assembled video."""
    proj = _project(pid)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in music.AUDIO_EXT:
        raise HTTPException(400, i18n.L("Нужен звуковой файл: mp3, wav, m4a, flac или ogg", "A sound file is needed: mp3, wav, m4a, flac or ogg"))
    if _shooting(pid):
        raise HTTPException(409, i18n.L("Ролик сейчас снимается — трек можно сменить после", "The video is being shot: the track can be changed after that"))
    folder = projects.folder(pid)
    # the new file is read first: a broken one leaves the track there was
    new = folder / f"_track_upload{ext}"
    with open(new, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        dur = await asyncio.to_thread(music.duration, new)
    except Exception as e:  # noqa: BLE001 - a broken file is the user's to replace
        new.unlink(missing_ok=True)
        raise HTTPException(400, str(e)) from e
    for old in folder.glob("track.*"):
        old.unlink()
    dst = folder / f"track{ext}"
    new.replace(dst)
    prev = proj["settings"].get("track") or {}
    proj["settings"]["track"] = {**music.DEFAULTS, **{k: prev[k] for k in music.DEFAULTS if k in prev},
                                 "file": dst.name, "name": Path(file.filename).name, "duration": round(dur, 2)}
    return projects.save(proj)


class TrackEdit(BaseModel):
    volume: Optional[float] = None
    scene_volume: Optional[float] = None
    offset: Optional[float] = None
    fade_in: Optional[float] = None
    fade_out: Optional[float] = None


@app.put("/api/projects/{pid}/track")
def edit_track(pid: str, body: TrackEdit):
    proj = _project(pid)
    track = proj["settings"].get("track")
    if not track:
        raise HTTPException(404, i18n.L("Трека нет", "No track"))
    track.update({k: v for k, v in body.model_dump().items() if v is not None})
    track.update(music.settings(track))
    return projects.save(proj)


@app.delete("/api/projects/{pid}/track")
def delete_track(pid: str):
    proj = _project(pid)
    if _shooting(pid):
        raise HTTPException(409, i18n.L("Ролик сейчас снимается — трек можно убрать после", "The video is being shot: the track can be removed after that"))
    track = proj["settings"].pop("track", None)
    if track:
        (projects.folder(pid) / track["file"]).unlink(missing_ok=True)
    return projects.save(proj)


def _cast_member(proj: dict, i: int) -> dict:
    cast = (proj.get("plan") or {}).get("cast") or []
    if not 0 <= i < len(cast):
        raise HTTPException(404, i18n.L("Нет такого героя", "No such hero"))
    return cast[i]


@app.post("/api/projects/{pid}/cast/{i}/photo")
async def cast_photo(pid: str, i: int, file: UploadFile):
    """A photo of one character: Ref2VA gets it as that character's <Picture k>, «Описать по фото» reads the look."""
    proj = _project(pid)
    c = _cast_member(proj, i)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(400, i18n.L("Нужна картинка: png, jpg или webp", "A picture is needed: png, jpg or webp"))
    from . import hero
    old = c.get("photo")
    name = f"cast_{uuid.uuid4().hex[:8]}{ext}"
    with open(projects.folder(pid) / name, "wb") as f:
        shutil.copyfileobj(file.file, f)
    hero._set_photo(proj["plan"], i, name)   # in a clip, character 1's photo is the singer's too
    c.pop("drawn", None)   # the user's own photo now, not a drawn one
    projects.drop_unused(proj, old)   # a try, the singer's or a scene's frame keeps it
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.delete("/api/projects/{pid}/cast/{i}/photo")
def cast_photo_delete(pid: str, i: int):
    proj = _project(pid)
    c = _cast_member(proj, i)
    projects.drop_unused(proj, c.pop("photo", None))
    c.pop("drawn", None)
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


# ---------- a character's voice by sample: LTX 2.3 scenes where only they speak are shot with ID-LoRA (render.voice_ref) ----------
def _set_voice(proj: dict, c: dict, src: Path, name: str) -> dict:
    """The sample into the project as cast_voice_<id>.wav (a recording from the browser is WebM: every reader takes WAV)."""
    folder = projects.folder(proj["id"])
    dst = folder / f"cast_voice_{uuid.uuid4().hex[:8]}.wav"
    r = subprocess.run([config.FFMPEG, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "48000", str(dst)],
                       capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise HTTPException(400, i18n.L("Не читается как звук: ", "Can't be read as sound: ") + (r.stderr or "").strip()[-300:])
    old = c.get("voice") or {}
    if old.get("file"):
        (folder / old["file"]).unlink(missing_ok=True)
    c["voice"] = {"file": dst.name, "name": name, "from": 0.0, "secs": 5.0, "duration": round(music.duration(dst), 2)}
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.post("/api/projects/{pid}/cast/{i}/voice")
async def cast_voice(pid: str, i: int, file: UploadFile):
    """A character's voice sample: a file or a recording (5-10 s of clean speech is best)."""
    proj = _project(pid)
    c = _cast_member(proj, i)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in music.AUDIO_EXT | {".webm"}:
        raise HTTPException(400, i18n.L("Нужен звук: mp3, wav, m4a, flac, ogg или запись", "A sound is needed: mp3, wav, m4a, flac, ogg or a recording"))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"in{ext}"
        with open(src, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return await asyncio.to_thread(_set_voice, proj, c, src, Path(file.filename or "голос").name)


class VoiceFromScene(BaseModel):
    scene: int


@app.post("/api/projects/{pid}/cast/{i}/voice/scene")
def cast_voice_from_scene(pid: str, i: int, req: VoiceFromScene):
    """«Голос из сцены»: the voice of a shot scene, without its music and noise (Demucs - a GPU job, ~1 min)."""
    proj = _project(pid)
    _cast_member(proj, i)
    pre = render.preview(proj)
    if not 0 <= req.scene < len(pre["keys"]) or pre["scenes"][req.scene] != "cached":
        raise HTTPException(400, i18n.L("Эта сцена ещё не снята", "This scene is not shot yet"))
    mp4 = render.shot_paths(projects.folder(pid) / "scenes", pre["keys"][req.scene])[0]

    async def run(job):
        from . import song
        job.phase = "loading"
        await llm.SERVER.stop()
        if COMFY.warm:
            await COMFY.free()
            COMFY.warm = False
        job.phase = "separating"
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "voice.wav"
            await song.separate(mp4, wav, lambda m: job.progress.update(message=m))
            now = projects.load(pid)
            _set_voice(now, _cast_member(now, i), wav, i18n.L(f"Сцена {req.scene + 1}", f"Scene {req.scene + 1}"))
        return {"project": pid, "cast": i}
    return jobs.submit_task("voice", {"project": pid, "cast": i, "scene": req.scene}, run, estimate=60).public()


class VoiceEdit(BaseModel):
    start: Optional[float] = Field(None, alias="from")
    secs: Optional[float] = None


@app.put("/api/projects/{pid}/cast/{i}/voice")
def cast_voice_edit(pid: str, i: int, body: VoiceEdit):
    """The piece of the sample ID-LoRA hears: from which second, how long."""
    proj = _project(pid)
    v = _cast_member(proj, i).get("voice")
    if not v:
        raise HTTPException(404, i18n.L("У героя нет образца голоса", "The hero has no voice sample"))
    if body.start is not None:
        v["from"] = round(max(0.0, min(float(body.start), max(0.0, float(v.get("duration") or 0) - 1))), 2)
    if body.secs is not None:
        v["secs"] = round(max(1.0, min(float(body.secs), 20.0)), 2)
    return projects.save(proj)


@app.delete("/api/projects/{pid}/cast/{i}/voice")
def cast_voice_delete(pid: str, i: int):
    proj = _project(pid)
    c = _cast_member(proj, i)
    if (c.get("voice") or {}).get("file"):
        (projects.folder(pid) / c.pop("voice")["file"]).unlink(missing_ok=True)
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.post("/api/projects/{pid}/cast/{i}/draw")
def cast_draw(pid: str, i: int):
    """«Нарисовать по описанию»: Krea 2 paints the character from their look and outfit; the picture becomes their
    photo (hero.py) - a GPU job, ~15 s with Krea's start."""
    proj = _project(pid)
    c = _cast_member(proj, i)
    if not (c.get("en") or "").strip():
        raise HTTPException(400, i18n.L("У героя нет описания внешности по-английски: «Обновить промт по тексту»", "The hero has no look description in English: «Update the prompt from the text»"))
    from . import hero, picture
    if why := picture.problem():
        raise HTTPException(400, why)
    return jobs.submit_task("draw", {"project": pid, "cast": i}, lambda job: hero.draw(job, pid, i), estimate=20).public()


class CastTries(BaseModel):
    n: int = 4
    tweak: Optional[str] = None


@app.post("/api/projects/{pid}/cast/{i}/tries")
def cast_tries(pid: str, i: int, body: CastTries):
    """«Ещё 4 пробы»: Krea 2 draws several tries of the character in one job; they wait in cast[i].tries for one to be
    approved (hero.py). A quick tweak draws them on the approved try's seed with its phrase."""
    proj = _project(pid)
    c = _cast_member(proj, i)
    if not (c.get("en") or "").strip():
        raise HTTPException(400, i18n.L("У героя нет описания внешности по-английски: «Обновить промт по тексту»", "The hero has no look description in English: «Update the prompt from the text»"))
    from . import hero, picture
    if body.tweak and body.tweak not in hero.TWEAKS:
        raise HTTPException(400, i18n.L("Нет такой правки", "No such tweak"))
    if body.tweak and not c.get("seed"):
        raise HTTPException(400, i18n.L("Сначала утвердите пробу: правка рисует от неё", "Approve a try first: a tweak draws from it"))
    if why := picture.problem():
        raise HTTPException(400, why)
    n = max(1, min(int(body.n), 6))
    return jobs.submit_task("cast_tries", {"project": pid, "cast": i, "n": n, "tweak": body.tweak},
                            lambda job: hero.tries(job, pid, i, n, body.tweak), estimate=15 + 12 * n).public()


class CastAdjust(BaseModel):
    tweaks: list[str] = []
    text: str = Field("", max_length=200)   # the user's own change, in the video's language
    n: int = 2


@app.post("/api/projects/{pid}/cast/{i}/adjust")
def cast_adjust(pid: str, i: int, body: CastAdjust):
    """«Поправить черты»: tries with these features changed and the face kept (hero.adjust); approving one writes the
    change into the look."""
    proj = _project(pid)
    _cast_member(proj, i)
    from . import hero, picture
    if bad := [k for k in body.tweaks if k not in hero.TWEAKS]:
        raise HTTPException(400, i18n.L(f"Нет такой правки: {', '.join(bad)}", f"No such tweak: {', '.join(bad)}"))
    if not body.tweaks and not body.text.strip():
        raise HTTPException(400, i18n.L("Выберите черту или напишите свою правку", "Pick a feature or write your own change"))
    if not hero.portrait_path(proj, i):
        raise HTTPException(400, i18n.L("Сначала нужен портрет героя", "The hero needs a portrait first"))
    if picture.edit_problem() and (why := picture.problem()):
        raise HTTPException(400, why)
    if body.text.strip():
        try:
            llm.find(proj["plan"].get("model"))
        except llm.LLMError as e:
            raise HTTPException(400, str(e)) from e
    n = max(1, min(int(body.n), 4))
    return jobs.submit_task("cast_tries", {"project": pid, "cast": i, "n": n, "tweaks": body.tweaks},
                            lambda job: hero.adjust(job, pid, i, body.tweaks, body.text, n),
                            estimate=15 + 10 * n + (15 if body.text.strip() else 0)).public()


class CastRedraw(BaseModel):
    n: int = 4


@app.post("/api/projects/{pid}/cast/{i}/redraw")
def cast_redraw(pid: str, i: int, body: CastRedraw = CastRedraw()):
    """«Нарисовать по описанию» / «Новые лица по этому описанию»: the edited look into English (when it changed), then n
    new faces by Krea 2 (hero.redraw)."""
    proj = _project(pid)
    c = _cast_member(proj, i)
    if not (c.get("ru") or c.get("en") or "").strip():
        raise HTTPException(400, i18n.L("Опишите внешность героя", "Describe the hero's look"))
    from . import hero, picture
    if why := picture.problem():
        raise HTTPException(400, why)
    if c.get("ru_dirty"):
        try:
            llm.find(proj["plan"].get("model"))
        except llm.LLMError as e:
            raise HTTPException(400, str(e)) from e
    n = max(1, min(int(body.n), 6))
    return jobs.submit_task("cast_tries", {"project": pid, "cast": i, "n": n}, lambda job: hero.redraw(job, pid, i, n),
                            estimate=15 + 12 * n + (20 if c.get("ru_dirty") else 0)).public()


class CastPick(BaseModel):
    file: str


@app.put("/api/projects/{pid}/cast/{i}/pick")
def cast_pick(pid: str, i: int, body: CastPick):
    """Approve a try as the character's photo (the one before stays among the tries)."""
    proj = _project(pid)
    _cast_member(proj, i)
    from . import hero
    try:
        hero.pick(proj, i, body.file)
    except EngineError as e:
        raise HTTPException(404, str(e)) from e
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.delete("/api/projects/{pid}/cast/{i}/tries/{name}")
def cast_try_delete(pid: str, i: int, name: str):
    """A try thrown away: its file goes only when it was this hero's try and nothing else in the project uses it (a
    photo, a scene's first or last frame, the clip's singer, a place's picture)."""
    proj = _project(pid)
    c = _cast_member(proj, i)
    tries = c.get("tries") or []
    if not any(x["file"] == name for x in tries):
        raise HTTPException(404, i18n.L("Нет такой пробы", "No such try"))
    c["tries"] = [x for x in tries if x["file"] != name]
    projects.drop_unused(proj, name)
    return projects.save(proj)


@app.get("/api/projects/{pid}/cast/{i}/faces")
async def cast_faces(pid: str, i: int):
    """How close the face on each shot scene of the character is to their photo (SFace on the scene's last frame)."""
    proj = _project(pid)
    _cast_member(proj, i)
    from . import hero
    return {"faces": await asyncio.to_thread(hero.faces, proj, i), "min": config.FRAME_FACE_MIN}


@app.post("/api/projects/{pid}/cast/{i}/describe")
def cast_describe(pid: str, i: int):
    """«Описать по фото»: the writer reads the character's photo (or the project's photo for the hero described from
    it) and writes the look and the outfit, en / ru; the gender and age too. A job; the result lands in the project."""
    proj = _project(pid)
    c = _cast_member(proj, i)
    path = projects.folder(pid) / c["photo"] if c.get("photo") else (projects.photo_path(proj) if c.get("from_photo") else None)
    if not path or not path.exists():
        raise HTTPException(400, i18n.L("У героя нет фото", "The hero has no photo"))
    try:
        m = llm.find(proj["plan"].get("model"))
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    if not m.mmproj:
        raise HTTPException(400, i18n.L(f"Модель {m.name} не видит картинок: выберите другую в шапке", f"Model {m.name} can't see pictures: choose another one in the header"))

    async def run(job):
        async with llm.session(m.id) as client:
            d = await describe.describe_with(client, path)
        cur = projects.load(pid)
        cc = _cast_member(cur, i)
        # the photo gives the face; the outfit stays the user's (a fashion shoot styles it), unless there is none yet
        keys = ["gender", "age", "en", "ru"] + ([] if cc.get("outfit_en") or cc.get("outfit_ru") else ["outfit_en", "outfit_ru"])
        cc.update({k: d.get(k, cc.get(k)) for k in keys}, ru_dirty=False)
        cc.pop("photo_stale", None)   # the look is the picture's now
        cur["plan"] = check.plan(cur["plan"])
        projects.save(cur)
        return {"project": pid}

    return jobs.submit_task("rewrite", {"project": pid, "how": "describe", "scenes": [i]}, run, estimate=25).public()


def _scene(proj: dict, i: int) -> dict:
    scenes = (proj.get("plan") or {}).get("scenes") or []
    if not 0 <= i < len(scenes):
        raise HTTPException(404, i18n.L("Нет такой сцены", "No such scene"))
    return scenes[i]


def _set_start(proj: dict, s: dict, name: Optional[str]) -> dict:
    """A scene's start photo set or taken away. A scene with a photo is a new shot (it starts from the picture, not from
    the previous last frame); what the writer read from the old picture no longer holds."""
    old = s.get("start_photo")
    s.pop("start_en", None)
    if name:
        s.update(start_photo=name, kind="new")
    else:
        s.pop("start_photo", None)
    # an upload of its own goes; the hero's photo, the singer's, another scene's frame stay
    projects.drop_unused(proj, old)
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.post("/api/projects/{pid}/scenes/{i}/start")
async def scene_start_upload(pid: str, i: int, file: UploadFile):
    """«Начать с фото»: the scene's first frame is this picture (cropped to the video's frame when shot)."""
    proj = _project(pid)
    s = _scene(proj, i)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(400, i18n.L("Нужна картинка: png, jpg или webp", "A picture is needed: png, jpg or webp"))
    name = f"start_{uuid.uuid4().hex[:8]}{ext}"
    with open(projects.folder(pid) / name, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return _set_start(proj, s, name)


@app.post("/api/projects/{pid}/scenes/{i}/start/hero")
def scene_start_hero(pid: str, i: int):
    """«С фото героя»: the project's photo (the idea screen's) as the scene's first frame."""
    proj = _project(pid)
    s = _scene(proj, i)
    name = proj["settings"].get("photo")
    if not name or not (projects.folder(pid) / name).exists():
        raise HTTPException(400, i18n.L("У ролика нет фото героя", "The video has no hero photo"))
    return _set_start(proj, s, name)


class FrameReq(BaseModel):
    seed: Optional[int] = None
    scenes: Optional[list[int]] = None   # /frames: these scenes (None: every new scene with a hero who has a photo)
    unlike: bool = False                 # /frames: «Перерисовать непохожие» - the scenes whose frame is not like the hero, a new one kept only when closer


@app.post("/api/projects/{pid}/scenes/{i}/start/draw")
def scene_start_draw(pid: str, i: int, req: FrameReq = FrameReq()):
    """«Нарисовать кадр»: FLUX.2 Klein draws the scene's first frame from the photos of its people in its place
    (frames.py); the picture becomes the scene's start photo. A GPU job, ~5 s warm."""
    from . import frames, picture
    proj = _project(pid)
    s = _scene(proj, i)
    if not frames.can_draw(proj["plan"], s):
        raise HTTPException(400, i18n.L("Кадр рисуется новой сцене с героем, у которого есть фото, или сцене без людей", "A frame is drawn for a new scene with a hero who has a photo, or a scene with nobody in it"))
    if why := picture.edit_problem():
        raise HTTPException(400, why)
    return jobs.submit_task("frame", {"project": pid, "scene": i, "scenes": 1}, lambda job: frames.draw_many(job, pid, [i], req.seed),
                            estimate=frames.estimate(1)).public()


@app.post("/api/projects/{pid}/frames")
def project_frames(pid: str, req: FrameReq = FrameReq()):
    """«Нарисовать кадры всем сценам»: one job, the model loaded once (frames.draw_many)."""
    from . import frames, picture
    proj = _project(pid)
    plan = proj.get("plan") or {}
    if why := picture.edit_problem():
        raise HTTPException(400, why)
    todo = [s["index"] for s in plan.get("scenes") or [] if frames.can_draw(plan, s) and (req.scenes is None or s["index"] in req.scenes)]
    if req.unlike:
        todo = [i for i in todo if i in frames.unlike(plan)]
        if not todo:
            raise HTTPException(400, i18n.L("Непохожих кадров нет", "No frame unlike the hero"))
    if not todo:
        raise HTTPException(400, i18n.L("Нет сцен, которым можно нарисовать кадр: нужна новая сцена с героем, у которого есть фото, или сцена без людей", "No scene to draw a frame for: a new scene with a hero who has a photo, or a scene with nobody in it"))
    return jobs.submit_task("frame", {"project": pid, "scenes": len(todo)}, lambda job: frames.draw_many(job, pid, todo, req.seed, req.unlike),
                            estimate=frames.estimate(len(todo) * 2 if req.unlike else len(todo))).public()


# ---------- «Места» (places.py): a picture of each place, the start frames' second reference ----------
def _place(proj: dict, xid: str) -> dict:
    from . import places
    x = places.by_id(proj.get("plan") or {}, xid)
    if not x:
        raise HTTPException(404, i18n.L("Нет такого места", "No such place"))
    return x


@app.post("/api/projects/{pid}/places/group")
def places_group(pid: str):
    """«Собрать места»: the writer groups the new scenes into a few places (an LLM job, ~20 s with its start)."""
    from . import places
    proj = _project(pid)
    if not any(s.get("kind") == "new" for s in (proj.get("plan") or {}).get("scenes") or []):
        raise HTTPException(400, i18n.L("В ролике нет новых сцен", "The video has no new scenes"))
    return jobs.submit_task("places", {"project": pid}, lambda job: places.group(pid), estimate=25).public()


class PlaceReq(BaseModel):
    name_ru: Optional[str] = Field(None, max_length=80)
    en: Optional[str] = Field(None, max_length=500)


@app.post("/api/projects/{pid}/places")
def place_add(pid: str, req: PlaceReq):
    """A place added by hand (its scenes are put in it from the scene panel)."""
    proj = _project(pid)
    plan = proj["plan"]
    plan.setdefault("places", []).append({"id": uuid.uuid4().hex[:8], "name_ru": (req.name_ru or "").strip() or i18n.L("Новое место", "New place"),
                                          "en": (req.en or "").strip()})
    proj["plan"] = check.plan(plan)
    return projects.save(proj)


@app.put("/api/projects/{pid}/places/{xid}")
def place_edit(pid: str, xid: str, req: PlaceReq):
    """A place's name or words; new words make its drawn picture old (it is drawn again by the user's button)."""
    proj = _project(pid)
    x = _place(proj, xid)
    if req.name_ru is not None:
        x["name_ru"] = req.name_ru.strip() or x["name_ru"]
    if req.en is not None and req.en.strip() != x.get("en"):
        x["en"] = req.en.strip()
        if x.get("drawn"):
            x["stale"] = True
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.delete("/api/projects/{pid}/places/{xid}")
def place_delete(pid: str, xid: str):
    from . import places
    proj = _project(pid)
    x = _place(proj, xid)
    places.drop_photo(pid, x)
    proj["plan"]["places"] = [y for y in proj["plan"]["places"] if y is not x]
    proj["plan"] = check.plan(proj["plan"])   # its scenes lose the place (places.tidy)
    return projects.save(proj)


@app.post("/api/projects/{pid}/places/{xid}/photo")
async def place_photo(pid: str, xid: str, file: UploadFile):
    """The user's own picture of the place."""
    from . import places
    proj = _project(pid)
    x = _place(proj, xid)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(400, i18n.L("Нужна картинка: png, jpg или webp", "A picture is needed: png, jpg or webp"))
    places.drop_photo(pid, x)
    name = f"placeown_{uuid.uuid4().hex[:8]}{ext}"
    with open(projects.folder(pid) / name, "wb") as f:
        shutil.copyfileobj(file.file, f)
    x["photo"] = name
    x.pop("stale", None)
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.delete("/api/projects/{pid}/places/{xid}/photo")
def place_photo_delete(pid: str, xid: str):
    from . import places
    proj = _project(pid)
    places.drop_photo(pid, _place(proj, xid))
    _place(proj, xid).pop("stale", None)
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


class PlaceDrawReq(BaseModel):
    places: Optional[list[str]] = None   # these places (None: every place without a picture)
    seed: Optional[int] = None


@app.post("/api/projects/{pid}/places/draw")
def places_draw(pid: str, req: PlaceDrawReq = PlaceDrawReq()):
    """«Нарисовать» / «Ещё вариант» / «Нарисовать все места»: Krea 2 paints the places empty (one model load)."""
    from . import picture, places
    proj = _project(pid)
    plan = proj.get("plan") or {}
    if why := picture.problem():
        raise HTTPException(400, why)
    todo = [x["id"] for x in plan.get("places") or [] if x.get("en") and (x["id"] in req.places if req.places is not None else not x.get("photo"))]
    if not todo:
        raise HTTPException(400, i18n.L("Нет мест, которым нужна картинка: у места должно быть описание", "No place needs a picture: a place needs its words"))
    return jobs.submit_task("place", {"project": pid, "places": len(todo)}, lambda job: places.draw(job, pid, todo, req.seed),
                            estimate=places.estimate(len(todo))).public()


class ScenePlaceReq(BaseModel):
    place: Optional[str] = None


@app.put("/api/projects/{pid}/scenes/{i}/place")
def scene_place(pid: str, i: int, req: ScenePlaceReq):
    """The scene put in a place by hand (None: none); its frame is drawn in it from now on."""
    from . import places
    proj = _project(pid)
    places.assign(proj["plan"], _scene(proj, i), req.place)
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.delete("/api/projects/{pid}/scenes/{i}/start")
def scene_start_delete(pid: str, i: int):
    proj = _project(pid)
    return _set_start(proj, _scene(proj, i), None)


@app.post("/api/projects/{pid}/scenes/{i}/end")
async def scene_end_upload(pid: str, i: int, file: UploadFile):
    """«Прийти к кадру» (flf2v, LTX): the scene ends on this picture (cropped to the frame when shot)."""
    proj = _project(pid)
    s = _scene(proj, i)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in IMAGE_EXT:
        raise HTTPException(400, i18n.L("Нужна картинка: png, jpg или webp", "A picture is needed: png, jpg or webp"))
    name = f"end_{uuid.uuid4().hex[:8]}{ext}"
    with open(projects.folder(pid) / name, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return _set_end(proj, s, name)


@app.delete("/api/projects/{pid}/scenes/{i}/end")
def scene_end_delete(pid: str, i: int):
    proj = _project(pid)
    return _set_end(proj, _scene(proj, i), None)


def _set_end(proj: dict, s: dict, name: Optional[str]) -> dict:
    old = s.get("end_photo")
    if name:
        s["end_photo"] = name
    else:
        s.pop("end_photo", None)
    projects.drop_unused(proj, old)   # another scene may start or end on it
    proj["plan"] = check.plan(proj["plan"])
    return projects.save(proj)


@app.get("/api/projects/{pid}/scenes/{index}/prompt")
def scene_model_prompt(pid: str, index: int):
    """What the scene's model gets for a new shot: H3 its formula, LTX and WAN their own (model_prompts), as sent."""
    proj = _project(pid)
    scenes = (proj.get("plan") or {}).get("scenes") or []
    if not 0 <= index < len(scenes):
        raise HTTPException(404, i18n.L("Нет такой сцены", "No such scene"))
    c = render.scene_card(proj["plan"], proj["settings"], scenes[index])
    sc = videomodels.shooter(c)
    return {"model": sc.id, "name": sc.name,
            "text": videomodels.adapt(sc, model_prompts.for_model(c.id, proj["plan"], scenes[index]))}


@app.post("/api/projects/{pid}/branch")
def project_branch(pid: str):
    """«Ветка»: a copy of the storyboard with its shots (hard links) that remembers where it came from."""
    proj = _project(pid)
    if proj.get("type") == "graph" or not proj.get("plan"):
        raise HTTPException(400, i18n.L("Ветка — у раскадровки; у графа есть «Копия»", "A branch is a storyboard's; a graph has «Copy»"))
    if any(j.status in ("queued", "running") and j.params.get("project") == pid for j in jobs.JOBS.values()):
        raise HTTPException(409, i18n.L("Ролик сейчас снимается или пишется — ветка после", "The video is being shot or written now: the branch after that"))
    return {"project": projects.branch(proj)["id"]}


@app.get("/api/projects/{pid}/branch")
def project_branch_diff(pid: str):
    """What a branch changed against its source (projects.branch_diff); {} - not a branch."""
    return projects.branch_diff(_project(pid)) or {}


@app.get("/api/projects/{pid}/scenes/{index}/graph")
def scene_graph(pid: str, index: int, quality: Optional[str] = None):
    """«Граф для ComfyUI»: the graph a new shot of the scene sends to the worker, without shooting (render.scene_graph_preview)."""
    proj = _project(pid)
    if not 0 <= index < len(((proj.get("plan") or {}).get("scenes") or [])):
        raise HTTPException(404, i18n.L("Нет такой сцены", "No such scene"))
    if quality and quality not in graphs.QUALITY_MP:
        raise HTTPException(400, i18n.L(f"Неизвестное качество: {quality}", f"Unknown quality: {quality}"))
    return render.scene_graph_preview(proj, index, quality)


@app.get("/api/projects/{pid}/estimate")
def project_estimate(pid: str):
    """How long «Снять ролик» will take, for both qualities: which scenes are in the cache, which must be shot, at
    this machine's measured speed."""
    proj = _project(pid)
    if not proj.get("plan"):
        return {}
    return {q: render.preview(proj, q) for q in graphs.QUALITY_MP}


@app.get("/api/projects/{pid}/graph")
def project_graph(pid: str):
    """The storyboard as a graph (phase 9, G1): what each scene starts from, who is in it, whose photos Ref2VA gets."""
    return graph.storyboard(_project(pid))


@app.post("/api/jobs/{job_id}/stop-after")
def stop_after(job_id: str):
    """«Остановить после текущей сцены»: the scene being shot is finished and cached, the rest wait for the next run."""
    job = jobs.JOBS.get(job_id)
    if not job or job.status not in ("queued", "running"):
        raise HTTPException(404, i18n.L("Нечего останавливать", "Nothing to stop"))
    if job.status == "queued":
        jobs.cancel(job_id)
    job.stop_after = True
    return {"ok": True}


@app.post("/api/projects/{pid}/scenes/{index}/retake")
def scene_retake(pid: str, index: int):
    """«Новый дубль»: a new seed for the scene; the next render shoots it again (and the continuations after it)."""
    proj = _project(pid)
    scenes = (proj.get("plan") or {}).get("scenes") or []
    if not 0 <= index < len(scenes):
        raise HTTPException(404, i18n.L("Нет такой сцены", "No such scene"))
    s = scenes[index]
    old = render.takes_of(proj["plan"], s)
    s["seed"] = random.randrange(1, 2**31)
    s["takes"] = old + [s["seed"]]   # the shot before stays a take of its own
    return projects.save(proj)


@app.get("/api/projects/{pid}/files/{path:path}")
def project_file(pid: str, path: str):
    """The project's shots and videos (scenes/<key>.mp4|png, video_*.mp4, a clip without its background .webm, and as
    ProRes 4444 .mov - made from the .webm on its first download); nothing outside its folder."""
    base = projects.folder(pid).resolve()
    f = (base / path).resolve()
    if base not in f.parents or f.suffix.lower() not in (".mp4", ".webm", ".mov", *IMAGE_EXT, *music.AUDIO_EXT):
        raise HTTPException(404)
    if f.suffix.lower() == ".mov" and f.name.startswith("v2v_") and not f.exists() and f.with_suffix(".webm").exists():
        try:
            v2v.prores(f.with_suffix(".webm"), f)
        except EngineError as e:
            raise HTTPException(500, str(e))
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f)


@app.post("/api/projects/{pid}/open")
def project_open(pid: str):
    _project(pid)
    os.startfile(projects.folder(pid))  # Windows: the Explorer window on this machine
    return {"ok": True}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.JOBS.get(job_id)
    if not job:
        raise HTTPException(404)
    return job.public()


class LoraUse(BaseModel):
    id: str
    strength: float = Field(1.0, ge=-5, le=5)


class SceneRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT)
    seconds: float = Field(5, ge=1, le=15)
    quality: str = "draft"
    aspect: str = "16:9"                       # a key of graphs.ASPECTS, or "frame": the start frame's own proportions
    frame_ratio: Optional[float] = Field(None, gt=0.2, lt=5)
    first_frame: Optional[str] = None          # a name from /api/frames
    seed: int = -1                             # < 0: random
    count: int = Field(1, ge=1, le=8)
    loras: list[LoraUse] = []
    video_model: str = "h3"                    # phase 10: which model shoots it (the prompt goes as written)


@app.post("/api/scenes")
def make_scenes(req: SceneRequest):
    if req.quality not in graphs.QUALITY_MP:
        raise HTTPException(400, i18n.L(f"Неизвестное качество: {req.quality}", f"Unknown quality: {req.quality}"))
    if issues := COMFY.problems():
        raise HTTPException(400, "; ".join(issues))
    if req.first_frame:
        if Path(req.first_frame).name != req.first_frame or not (config.COMFY_INPUT / req.first_frame).exists():
            raise HTTPException(400, i18n.L("Стартовый кадр не найден, загрузите его снова", "Start frame not found, upload it again"))
    if req.aspect == "frame":
        if not (req.first_frame and req.frame_ratio):
            raise HTTPException(400, i18n.L("Пропорции кадра берутся со стартового кадра, а его нет", "The frame's proportions come from the start frame, and there is none"))
        ratio = req.frame_ratio
    elif req.aspect in graphs.ASPECTS:
        ratio = graphs.ASPECTS[req.aspect]
    else:
        raise HTTPException(400, i18n.L(f"Неизвестный формат кадра: {req.aspect}", f"Unknown frame format: {req.aspect}"))
    loras = []
    for u in req.loras:
        info = lora_lib.get(u.id)
        if not info:
            raise HTTPException(400, i18n.L(f"LoRA не найдена: {u.id}", f"LoRA not found: {u.id}"))
        if info.verdict == "blocked":
            raise HTTPException(400, i18n.L(f"LoRA «{info.name}»: {info.note}", f"LoRA «{info.name}»: {info.note}"))
        loras.append({"id": u.id, "strength": u.strength, "name": info.name})
    if not videomodels.offered(req.video_model):
        raise HTTPException(400, i18n.L(f"Неизвестная модель: {req.video_model}", f"Unknown model: {req.video_model}"))
    card = videomodels.card(req.video_model)
    if wrong := [x["name"] for x in loras if lora_lib.model_of(x["id"]) != card.id]:
        raise HTTPException(400, i18n.L(f"LoRA не для {card.name}: " + ", ".join(wrong) + " — у каждой модели свои LoRA", f"LoRA not for {card.name}: " + ", ".join(wrong) + " (each model has its own LoRA)"))
    if missing := videomodels.weights_missing(card):
        raise HTTPException(400, i18n.L(f"{card.name}: нет файлов " + ", ".join(missing) + " («Модели и настройки»)", f"{card.name}: missing files " + ", ".join(missing) + " («Models and settings»)"))
    width, height = videomodels.size(card, ratio, req.quality)
    base = req.seed if req.seed >= 0 else random.randrange(2**31 - req.count)
    out = []
    for i in range(req.count):
        p = req.model_dump(exclude={"count", "video_model"})
        p.update(seed=base + i, width=width, height=height, length=videomodels.frames(card, req.seconds), loras=loras, model=card.id,
                 model_name=card.short)
        out.append(jobs.submit(p).public())
    return out


@app.get("/api/jobs")
def get_jobs():
    live = [j for j in jobs.JOBS.values() if j.status in ("queued", "running")]
    recent = sorted((j for j in jobs.JOBS.values() if j.status not in ("queued", "running")),
                    key=lambda j: j.finished or 0, reverse=True)[:12]
    return [j.public() for j in sorted(live, key=lambda j: j.created)] + [j.public() for j in recent]


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    if not jobs.cancel(job_id):
        raise HTTPException(404, i18n.L("Нечего отменять", "Nothing to cancel"))
    return {"ok": True}


@app.post("/api/jobs/cancel-all")
def cancel_all():
    for j in list(jobs.JOBS.values()):
        if j.status in ("queued", "running"):
            jobs.cancel(j.id)
    return {"ok": True}


@app.get("/api/videos")
def get_videos():
    items = []
    for js in sorted(config.OUTPUT_DIR.glob("*.json"), reverse=True):
        mp4 = js.with_suffix(".mp4")
        if not mp4.exists():
            continue
        try:
            meta = json.loads(js.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        items.append({"file": mp4.name, "poster": mp4.with_suffix(".png").name if mp4.with_suffix(".png").exists() else None,
                      **meta})
    return items


@app.delete("/api/videos/{name}")
def delete_video(name: str):
    mp4 = (config.OUTPUT_DIR / Path(name).name).with_suffix(".mp4")
    if not mp4.exists():
        raise HTTPException(404)
    # to the Recycle Bin, as everything else the app removes: a take deleted by mistake comes back from there
    try:
        for ext in (".mp4", ".png", ".json"):
            if mp4.with_suffix(ext).exists():
                models_page.to_recycle_bin(mp4.with_suffix(ext))
    except OSError as e:
        raise HTTPException(500, str(e)) from e
    return {"ok": True}


# ---------- «Модели и настройки» (phase 6) ----------

@app.get("/api/models")
def models_snapshot():
    return models_page.snapshot()


class SettingsPatch(BaseModel):
    values: dict


@app.post("/api/models/settings")
async def models_settings(body: SettingsPatch):
    """A select or a folder list changed: saved at once into data/settings.json. A new folder reaches the H3 worker at its
    next start, so an idle one is stopped (the next shot starts it again, ~10 s)."""
    try:
        changed = settings.update(body.values)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if settings.ENGINE_KEYS & set(changed) and not jobs.busy():
        await COMFY.stop()
    return models_page.snapshot()


class PickRequest(BaseModel):
    kind: str = "folder"             # folder | file
    start: Optional[str] = None      # where the dialog opens


@app.post("/api/models/pick")
async def models_pick(req: PickRequest):
    """«Выбрать…»: Windows' own folder or file dialog on this machine (the server runs where the user sits);
    {"path": None} when the dialog is closed."""
    if req.kind not in ("folder", "file"):
        raise HTTPException(400, i18n.L("folder или file", "folder or file"))
    return {"path": await asyncio.to_thread(models_page.pick, req.kind, req.start)}


class DownloadRequest(BaseModel):
    repo: str
    path: str
    slot: Optional[str] = None       # a weight role (models_page.SLOTS) - its folder; or
    to: Optional[str] = None         # "llm": the writer's last GGUF folder


def _download_folder(req: DownloadRequest) -> Path:
    if req.slot:
        s = next((x for x in models_page.SLOTS if x.key == req.slot), None)
        if not s or (req.repo, req.path) not in s.sources:
            raise HTTPException(400, i18n.L("Этого файла нет в каталоге", "This file is not in the catalog"))
        return models_page.folders(s.kind, s.section)[0]
    if req.to == "llm":
        if not req.path.lower().endswith(".gguf"):
            raise HTTPException(400, i18n.L("Для сценариста нужен файл .gguf", "The writer needs a .gguf file"))
        return config.LLM_DIRS[-1]
    raise HTTPException(400, i18n.L("Куда качать?", "Download where?"))


@app.post("/api/models/download")
def models_download(req: DownloadRequest):
    """«Скачать» / «Продолжить»: one file at a time, in the background; the page polls /api/models."""
    try:
        downloads.start(req.repo, req.path, _download_folder(req))
    except downloads.DownloadError as e:
        raise HTTPException(409, str(e)) from e
    return models_page.snapshot()


class UrlRequest(BaseModel):
    url: str


@app.post("/api/models/download-url")
def models_download_url(req: UrlRequest):
    """A GGUF for the writer by its Hugging Face link."""
    try:
        repo, path = downloads.parse_url(req.url)
    except downloads.DownloadError as e:
        raise HTTPException(400, str(e)) from e
    return models_download(DownloadRequest(repo=repo, path=path, to="llm"))


@app.post("/api/models/download/cancel")
def models_download_cancel():
    downloads.cancel()
    return models_page.snapshot()


class TokenRequest(BaseModel):
    token: Optional[str] = Field(None, max_length=200)


@app.post("/api/models/token")
def models_token(req: TokenRequest):
    downloads.set_token(req.token)
    return models_page.snapshot()


class PathRequest(BaseModel):
    path: str


@app.post("/api/models/delete")
def models_delete(req: PathRequest):
    """«Удалить N ГБ?» -> the Windows Recycle Bin. Not while anything shoots or writes, not the weights in use."""
    path = Path(req.path)
    if not path.is_file() or path.suffix.lower() not in models_page.WEIGHT_EXT or not models_page.inside_known(path):
        raise HTTPException(400, i18n.L("Это не файл модели из папок настроек", "This is not a model file from the settings' folders"))
    if jobs.busy():
        raise HTTPException(409, i18n.L("Сейчас идёт съёмка или пишет сценарист", "A shoot is running or the writer is writing"))
    if path.name in {getattr(config, s.key) for s in models_page.SLOTS}:
        raise HTTPException(409, i18n.L("Эта модель выбрана в настройках — сначала выберите другую", "This model is selected in the settings: choose another one first"))
    try:
        models_page.to_recycle_bin(path)
    except OSError as e:
        raise HTTPException(500, str(e)) from e
    return models_page.snapshot()


@app.post("/api/models/open")
def models_open(req: PathRequest):
    path = Path(req.path)
    if not models_page.inside_known(path) and path not in models_page.known_folders():
        raise HTTPException(400, i18n.L("Эта папка не из настроек", "This folder is not from the settings"))
    path.mkdir(parents=True, exist_ok=True) if not path.suffix else None
    os.startfile(path if path.is_dir() else path.parent)
    return {"ok": True}


@app.post("/api/open-folder/{which}")
def open_folder(which: str):
    path = {"outputs": config.OUTPUT_DIR, "loras": next((d for d in config.LORA_DIRS if d.exists()), None)}.get(which)
    if not path:
        raise HTTPException(404)
    os.startfile(path)  # Windows: the Explorer window on the machine the server runs on (= this one)
    return {"ok": True}


app.mount("/outputs", StaticFiles(directory=config.OUTPUT_DIR), name="outputs")
app.mount("/frames", StaticFiles(directory=config.COMFY_INPUT), name="frames")


@app.get("/")
def index():
    page = WEB / "index.html"
    if not page.exists():
        return HTMLResponse("<meta charset=utf-8><p style='font:16px sans-serif;padding:24px'>" + i18n.L(
            "Страница не собрана: запустите dev.bat или <code>npm install</code> и <code>npm run build</code> в папке frontend.",
            "The page is not built: run dev.bat or <code>npm install</code> and <code>npm run build</code> in the frontend folder.")
            + "</p>", 503)
    return FileResponse(page, headers={"Cache-Control": "no-store"})


@app.get("/lab")
def lab():
    """The lab is a screen of the page now (#/lab); the old address still leads there."""
    return RedirectResponse("/#/lab")


# the page's own js/css: their names carry a hash of their content, so a new build is a new name
app.mount("/assets", StaticFiles(directory=WEB / "assets", check_dir=False), name="assets")
