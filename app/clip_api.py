"""Phase 11: a clip from a song - its API. A song is uploaded and analysed once (song.py, data/songs/<id>); its words
are recognised by a GPU job (Demucs + Whisper); «Расписать клип» makes a storyboard project whose scenes are cut on
the song (planner/clip.py) and written by the clip writer (writer.write_clip), the song its track.
"""
from __future__ import annotations

import asyncio
import random
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import config, jobs, music, picture, projects, song, timings, videomodels
from .engine import graphs
from .engine.comfy import COMFY, EngineError
from .llm import client as llm, writer
from .planner import check, clip, grid
from . import i18n

router = APIRouter()


def _song(sid: str) -> dict:
    try:
        return song.public(sid)
    except EngineError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/api/songs")
async def upload_song(file: UploadFile):
    """A song for a clip: stored once (by its bytes) and analysed (~1 s): tempo, bars, parts."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in music.AUDIO_EXT:
        raise HTTPException(400, i18n.L("Нужен звуковой файл: mp3, wav, m4a, flac или ogg", "A sound file is needed: mp3, wav, m4a, flac or ogg"))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"song{ext}"
        with open(src, "wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            sid = await asyncio.to_thread(song.store, src, Path(file.filename or "").name)
        except EngineError as e:
            raise HTTPException(400, str(e)) from e
    return await asyncio.to_thread(_song, sid)


@router.get("/api/songs/{sid}")
async def get_song(sid: str):
    return await asyncio.to_thread(_song, sid)


@router.get("/api/songs/{sid}/file")
def song_file(sid: str):
    from fastapi.responses import FileResponse
    try:
        return FileResponse(song.file_of(sid))
    except EngineError as e:
        raise HTTPException(404, str(e)) from e


class SongText(BaseModel):
    text: str = Field("", max_length=20000)


@router.put("/api/songs/{sid}/text")
async def put_song_text(sid: str, body: SongText):
    """The user's words of the song: aligned on the recognised ones (their times), kept for every clip of it."""
    _song(sid)
    song.set_text(sid, body.text)
    return await asyncio.to_thread(_song, sid)


async def _recognise(job: jobs.Job, sid: str) -> dict:
    """The words, on the GPU: the video model and the writer out of memory first (Demucs + Whisper need ~6 GB)."""
    job.phase = "loading"
    await llm.SERVER.stop()
    if COMFY.warm:
        await COMFY.free()
        COMFY.warm = False

    def said(m: str) -> None:
        job.progress["message"] = m
    return await song.recognise(sid, said, song.language_of(sid))


@router.post("/api/songs/{sid}/lyrics")
def recognise_song(sid: str):
    """«Распознать слова»: a GPU job (~30 s; the first time Whisper's 3 GB are downloaded)."""
    info = _song(sid)

    async def run(job):
        await _recognise(job, sid)
        return {"song": sid}
    return jobs.submit_task("lyrics", {"song": sid, "name": info["name"]}, run, estimate=40).public()


class NewClip(BaseModel):
    song: str
    start: float = Field(0, ge=0)                 # where the fragment begins in the song (snapped to a bar)
    seconds: float = Field(60, ge=4, le=grid.MAX_SECONDS)
    idea: str = Field("", max_length=4000)
    mode: str = "one"                             # one | several | none
    aspect: str = "16:9"
    mood: str = Field("", max_length=200)
    photo: Optional[str] = None                   # the singer's photo (a name from /api/frames)
    seed: int = -1
    model: Optional[str] = None                   # the writer
    video_model: str = "ltx23"                    # what shoots the clip
    sing_model: str = "auto"                      # what shoots the singing scenes: auto = LTX 2.3 when the video's can't
    lyrics: bool = True                           # recognise the words first, when they are not yet
    draw_singer: bool = True                      # no singer's photo: Krea 2 draws one from the writer's look (hero.py)
    loras: list[dict] = []                        # the video's LoRA, as «Съёмка» → LoRA keeps them
    pic_loras: dict = {}                          # «LoRA картинок»: {"krea": [...], "flux2": [...]} (picture.project_loras)
    frames: bool = True                           # a start frame for every scene with the singer, from the photo (frames.py)
    places: bool = True                           # «Места» (places.py): the places gathered and painted, the frames drawn in them
    # «Что пишет сценарист»: the user's control of the first run
    look: str = "writer"                          # character 1's look: writer | own (look_ru, gender) | photo (the photo above)
    look_ru: str = Field("", max_length=1000)
    gender: str = "female"
    story: str = "writer"                         # writer | idea: the writer's story, or the user's idea as it is
    scenes: str = "all"                           # all | empty | none: every scene written, or the skeleton opens first


@router.post("/api/clips")
def new_clip(req: NewClip):
    """«Расписать клип»: a storyboard project with the song as its track (from the fragment's start) and one job: the
    words (when asked and not yet recognised), the scenes cut on the song, the clip writer."""
    info = _song(req.song)
    if req.mode not in grid.MODES:
        raise HTTPException(400, i18n.L(f"Неизвестный режим: {req.mode}", f"Unknown mode: {req.mode}"))
    if req.aspect not in graphs.ASPECTS:
        raise HTTPException(400, i18n.L(f"Неизвестный формат кадра: {req.aspect}", f"Unknown frame format: {req.aspect}"))
    if not videomodels.offered(req.video_model):
        raise HTTPException(400, i18n.L(f"Неизвестная модель: {req.video_model}", f"Unknown model: {req.video_model}"))
    if req.look not in ("writer", "own", "photo") or req.story not in ("writer", "idea") or req.scenes not in ("all", "empty", "none"):
        raise HTTPException(400, i18n.L("Неизвестный выбор «Что пишет сценарист»", "Unknown choice in «What the writer writes»"))
    if req.mode != "none" and req.look == "own" and not req.look_ru.strip():
        raise HTTPException(400, i18n.L("Опишите внешность героя или выберите «Сценарист»", "Describe the hero's look or pick «Writer»"))
    if req.mode != "none" and req.look == "photo" and not req.photo:
        raise HTTPException(400, i18n.L("Загрузите фото героя или выберите другой вариант внешности", "Upload the hero's photo or pick another way for the look"))
    if req.story == "idea" and not req.idea.strip():
        raise HTTPException(400, i18n.L("Напишите идею клипа: сценарист возьмёт её как есть", "Write the clip's idea: the writer takes it as it is"))
    try:
        model = llm.find(req.model)
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    photo = None
    if req.photo:
        photo = config.COMFY_INPUT / Path(req.photo).name
        if not photo.exists():
            raise HTTPException(400, i18n.L("Фото не найдено, загрузите его снова", "Photo not found, upload it again"))
        if req.mode != "none" and not model.mmproj:
            raise HTTPException(400, i18n.L(f"Модель {model.name} не видит картинок: выберите другую или уберите фото", f"Model {model.name} can't see pictures: choose another one or remove the photo"))
    card = videomodels.card(req.video_model)
    sing = req.sing_model
    if sing == "auto":
        sing = "" if card.track else "ltx23" if not videomodels.weights_missing(videomodels.card("ltx23")) else ""
    elif not videomodels.offered(sing) or sing == card.id:
        sing = ""
    a = song.analysis(req.song)
    ex0, ex1 = clip.fragment(a, req.start, req.seconds)
    from .main import MOODS   # the idea screen's chips -> what the writer reads (a clip's default: a music video)
    mood = MOODS.get(req.mood or "Клип", req.mood)
    title = Path(info["name"]).stem or i18n.L("Клип", "Clip")
    settings = {"idea": req.idea, "seconds": round(ex1 - ex0, 3), "mode": req.mode, "aspect": req.aspect, "mood": req.mood or "Клип",
                "music": "", "seed": req.seed, "video_model": card.id, "model": model.id, "quality": "draft",
                "loras": picture.pick_loras(req.loras), "pic_loras": picture.pick_pic_loras(req.pic_loras), "rtx": True, "track_sync": True, "clip": {"song": req.song, "sing_model": sing}}
    proj = projects.create(settings)
    pid = proj["id"]
    folder = projects.folder(pid)
    src = song.file_of(req.song)
    shutil.copyfile(src, folder / f"track{src.suffix}")
    settings["track"] = {**music.DEFAULTS, "volume": 1.0, "scene_volume": 0.0, "offset": ex0, "fade_in": 0.0, "fade_out": 1.5,
                         "file": f"track{src.suffix}", "name": title, "duration": round(a.duration, 2)}
    photo_name = projects.put_photo(pid, photo) if photo else None
    if photo_name:
        settings["photo"] = photo_name
    proj["name"] = title
    projects.save(proj)
    seed = req.seed if req.seed >= 0 else random.randrange(100000)
    n = len(clip.scenes(a, song.lines(req.song), ex0, ex1, min(card.max_seconds, videomodels.card(sing or card.id).max_seconds)))
    # the job's stages and their seconds: the words, the writer (this machine's speed), then the places gathered and
    # painted, the singer, the frames - an estimate of the writer alone held the bar at 99 % for minutes
    from . import frames, places
    people = req.mode != "none"
    lyrics_s = 0 if song.recognised(req.song) or not req.lyrics else 40
    writer_s = timings.writer_seconds(model.name, n, 10 + 4 * n) + (10 if photo else 0)
    group_s = 25 if people and req.frames and req.places else 0
    singer_s = 20 if people and not photo_name and req.draw_singer else 0
    places_s = lambda k: places.estimate(k) if group_s else 0  # noqa: E731
    frames_s = lambda k: frames.estimate(k) if people and req.frames else 0  # noqa: E731

    def ahead(job, *stages: float) -> None:
        """The job's estimate from now on: what it has taken so far and the stages still ahead."""
        job.estimate = round(time.time() - (job.started or time.time()) + sum(stages))

    async def run(job):
        note = ""
        if req.lyrics and not song.recognised(req.song):
            job.progress["stage"] = "lyrics"
            try:
                await _recognise(job, req.song)
            except EngineError as e:   # the clip is written without the words: no singing scenes
                note = str(e)
            ahead(job, writer_s, group_s, places_s(3), singer_s, frames_s(n))
        job.progress["stage"] = "writing"
        lines = song.lines(req.song)
        # every scene must fit the model that may shoot it: WAN's 5 s scene would play short and slip the cuts after it
        slots = clip.scenes(a, lines, ex0, ex1, min(card.max_seconds, videomodels.card(sing or card.id).max_seconds))
        plan = writer.new_clip_plan(req.idea, req.mode, mood, {"song": req.song, "name": title, "from": ex0, "to": ex1,
                                                                   "bpm": a.bpm, "bar_s": a.bar_s}, slots, seed, model.id)
        # the singing scenes' model and the singer's photo ride in the plan: clip_shot gives them to every scene that
        # sings - now, so the writer reads the photo, and whenever a rewrite makes a scene sing
        # the song's language (prompts.voices: she sings in it, whatever the storyboard's texts are in)
        plan["clip"].update(sing_model=sing or None, photo=photo_name if req.mode != "none" else None,
                            lang=(song.recognised(req.song) or {}).get("language") or None)
        plan["video"] = card.id
        plan["ref_photo"] = req.mode != "none"   # the singer's photo (given or drawn) holds the face on H3 (Ref2VA) too
        for s in plan["scenes"]:
            writer.clip_shot(plan, s, s.get("shot"))
        plan["clip"]["story"] = req.story
        if req.mode != "none" and req.look == "own":   # «Опишу сам»: kept, only put into English (writer.write_clip)
            plan["cast"] = [{"gender": req.gender if req.gender in writer.GENDERS else "female", "age": 25, "ru": req.look_ru.strip(),
                             "outfit_ru": "", "en": "", "outfit_en": "", "ru_dirty": True, "from_user": True}]
        if req.scenes != "all":
            # the skeleton: the scenes cut on the song, nothing written - the user writes their scenes on the board,
            # «Написать остальные» (clip_write) writes the rest
            cur = projects.load(pid)
            if note:
                plan["clip"]["lyrics_error"] = note
            cur["plan"] = check.plan(plan)
            projects.save(cur)
            return {"project": pid}
        p = await writer.write_clip(plan, projects.photo_path(projects.load(pid)) if req.mode != "none" else None, folder)
        timings.record_writer(p.get("writer") or {}, len(p["scenes"]))
        if note:
            p["clip"]["lyrics_error"] = note
        cur = projects.load(pid)
        cur["plan"] = check.plan(p)
        cur["name"] = p.get("title_ru") or cur.get("name")
        projects.save(cur)
        ahead(job, group_s, places_s(3), singer_s, frames_s(len(p["scenes"])))
        if req.mode != "none" and req.frames and req.places:
            # «Места» (places.py): the writer groups the scenes into a few places, Krea paints them right after the
            # singer (one load), and every frame is drawn in its place's picture -
            # the same flat or street from scene to scene, not a new one from the words each time
            from . import picture
            try:
                job.progress["stage"] = "grouping"
                await places.group(pid)
            except EngineError as e:
                cur = projects.load(pid)
                cur["plan"].setdefault("clip", {})["places_error"] = str(e)
                projects.save(cur)
            ahead(job, places_s(len(projects.load(pid)["plan"].get("places") or [])), singer_s, frames_s(len(p["scenes"])))
        if req.mode != "none" and not photo_name and req.draw_singer and (p.get("cast") or [{}])[0].get("en"):
            from . import hero, picture
            if not picture.problem():   # one face for every singing scene (LTX holds none from words)
                try:
                    await hero.draw(job, pid, 0)
                except EngineError as e:
                    cur = projects.load(pid)
                    cur["plan"].setdefault("clip", {})["draw_error"] = str(e)
                    projects.save(cur)
        if req.mode != "none" and req.frames and req.places and not picture.problem() and projects.load(pid)["plan"].get("places"):
            try:
                await places.draw(job, pid)
            except EngineError as e:
                cur = projects.load(pid)
                cur["plan"].setdefault("clip", {})["places_error"] = str(e)
                projects.save(cur)
        if req.mode != "none" and req.frames:
            # every scene with the singer starts from its own frame: her face from the photo in the scene's place
            # (frames.py) - the singing scenes no longer all start from the one portrait
            from . import picture
            if not picture.edit_problem():
                plan = projects.load(pid)["plan"]
                ahead(job, frames_s(sum(1 for s in plan["scenes"] if frames.can_draw(plan, s))))
                job.progress["stage"] = "frames"
                try:
                    await frames.draw_many(job, pid)
                    # «перерисовать непохожие»: a frame whose face is not the singer's would be her face in the shot -
                    # one more round for those, a new frame kept only when it is closer to her
                    if (bad := frames.unlike(projects.load(pid)["plan"])):
                        ahead(job, frames_s(2 * len(bad)))
                        job.progress["stage"] = "unlike"
                        await frames.draw_many(job, pid, bad, better=True)
                except EngineError as e:
                    cur = projects.load(pid)
                    cur["plan"].setdefault("clip", {})["frames_error"] = str(e)
                    projects.save(cur)
        return {"project": pid}

    skeleton = req.scenes != "all"
    job = jobs.submit_task("write", {"project": pid, "idea": (req.idea or title)[:80], "scenes": n, "clip": True}, run,
                           estimate=lyrics_s + 3 if skeleton else lyrics_s + writer_s + group_s + places_s(3) + singer_s + frames_s(n))
    return {"project": pid, "job": job.public()}


@router.post("/api/projects/{pid}/clip/write")
def clip_write(pid: str):
    """«Написать остальные» on the clip's skeleton: the writer writes the scenes nobody wrote, puts the user's own scenes
    (their words) into English and keeps them, keeps the scenes already written; the first time also the treatment, the
    cast (or the user's look into English) and the style (writer.write_clip)."""
    try:
        proj = projects.load(pid)
    except projects.NotFound as e:
        raise HTTPException(404, i18n.L("Проект не найден", "Project not found")) from e
    plan = proj.get("plan") or {}
    if not plan.get("clip"):
        raise HTTPException(400, i18n.L("Это не клип", "This is not a clip"))
    try:
        model = llm.find(plan.get("model"))
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    from .planner import prompts
    left = [s for s in plan["scenes"] if not prompts.is_written(s) or (s.get("source") == "user" and s.get("ru_dirty"))]
    if not left and plan.get("outline"):
        raise HTTPException(400, i18n.L("Все сцены уже написаны", "Every scene is written already"))

    async def run(job):
        job.progress["stage"] = "writing"
        cur = projects.load(pid)
        p = await writer.write_clip(cur["plan"], projects.photo_path(cur) if cur["plan"].get("mode") != "none" else None,
                                    projects.folder(pid))
        timings.record_writer(p.get("writer") or {}, len(left))
        cur = projects.load(pid)
        cur["plan"] = check.plan(p)
        if p.get("title_ru") and cur.get("name") in ("", None, (cur["plan"].get("clip") or {}).get("name")):
            cur["name"] = p["title_ru"]
        projects.save(cur)
        return {"project": pid}

    n = len(left)
    return jobs.submit_task("write", {"project": pid, "idea": proj.get("name", "")[:80], "scenes": n, "clip": True}, run,
                            estimate=timings.writer_seconds(model.name, n, 10 + 4 * n) + (0 if plan.get("outline") else 20)).public()
