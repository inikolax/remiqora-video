"""«Сделать ролик» (the home's «Что снимаем?»): the whole video in one job, the existing stages run with defaults one
after another. From a song («Песня → клип»): the words (song.py), the clip's project and its writer
(clip_api.start_clip), the hero's portrait (hero.py), the places and the scenes' frames (clip_api.group_places /
draw_places / draw_frames), the shooting with its checks and retakes, the assembly and the 1080p (render.run). From text
(a story): the idea screen's project and writer (story.py) instead of the first two, then the same stages. Where the
screens ask the user, it picks: the likest of the tries drawn from the user's photo (SFace), without a photo the first
try with one face; every frame the writer would draw.

«Спрашивать меня» (`ask`): two stops, each a server-side wait of WAIT seconds - «Выберите героя» after the hero's tries
(none picked: the one it would have taken), «Пробная сцена» after the frames (one scene shot before the rest: «Дальше»,
or «Сменить вид» - the style rebuilt, the frames drawn again, the trial shot again). The answer comes by POST
/api/projects/{pid}/autopilot/answer. The stop is kept in project["autopilot"]["ask"], so «Продолжить» after a restart
asks again (the hero's tries are not drawn twice).

The job is kind "autopilot"; job.progress["auto"] says the stage it is at and every stage's estimate (the bar is one
for all of them), job.progress["ask"] the stop it waits at, the rest of job.progress is the stage's own (the frames, the
render's scenes - the video screen shows it). The project keeps project["autopilot"]: what was asked, the stages done,
the stage that failed and why - so «Продолжить» (POST /api/projects/{pid}/autopilot) goes on from there, after a
restart too. A stop keeps what is done. The result is an ordinary project: everything can be changed and shot again on
its screens.
"""
from __future__ import annotations

import asyncio
import random
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import clip_api, config, i18n, jobs, looks, picture, projects, render, song, story, sysinfo, timings, videomodels
from .engine import graphs
from .engine.comfy import COMFY, EngineError
from .llm import client as llm
from .planner import check, grid, prompts

router = APIRouter()

STAGES = ("words", "write", "hero", "places", "frames", "trial", "render")
NAMES = {"words": ("слова песни", "the song's words"), "write": ("сценарий", "the script"), "hero": ("герой", "the hero"),
         "places": ("места", "the places"), "frames": ("кадры сцен", "the scenes' frames"), "trial": ("пробная сцена", "the trial scene"),
         "render": ("съёмка и склейка", "shooting and assembly")}
BEST = 60.0       # «лучшая минута»: this long, holding the first chorus
LEAD = 25.0       # ... from this long before the chorus (the verse's end leads into it)
DROP_BUILD_BARS, DROP_BARS = 3, 8   # «drop» window (the beat clip, app/beatedit.py): bars of build before the riser bar, bars of the drop
TRIES = 3         # the hero's tries
FACE_ROUNDS = 2   # after the shooting: rounds of reshooting the scenes whose face is not the hero's (audit)
# the shot plan the writer is asked for (the owner's «Ночной дрифт», 2026-10-30, held the face where the autopilot's
# first clips did not: 9 of 13 scenes singing, 4 without a face, two places, the singers pushing in or orbiting)
PLAN_HINT = "Shot plan: the singing scenes are spread over at least two different places."
FACELESS = 0.5    # this share of the scenes are inserts without a face, fixed before the writer (clip_api: faceless)
WAIT = 60.0       # «Спрашивать меня»: a stop waits this long for the user, then goes on with its own pick
HOLD = 600.0      # ... and at most this long from the stop's start once the user opened «Сменить вид» (the GPU queue
                  # waits with it: a hold is never re-armed past it, and the page releases it when the panel closes)
POLL = 0.25
STORY_SECONDS = 30.0
ASSEMBLY = 60.0   # the render's assembly, mixing and 1080p on top of the scenes (the route's «Монтаж»)
IDEA_CLIP = 600   # a clip's idea is one line; a story's may be a page (story.NewProject)

# «Поняли так»: what the home's box makes of what it was given (the page's lib/home.ts says the same)
WHATS = ("clip", "clip_hero", "story", "story_hero", "story_start", "beat")


def understand(has_song: bool, has_photo: bool, text: str) -> str:
    """A song -> a clip (a photo too: with this hero), a photo -> the hero of a story (the text its idea, or the
    writer's own), text -> a story; nothing given -> ""."""
    if has_song:
        return "clip_hero" if has_photo else "clip"
    if has_photo:
        return "story_hero"
    return "story" if len(text.strip()) >= 3 else ""


def misfit(what: str, has_song: bool, has_photo: bool, text: str) -> Optional[str]:
    """Why `what` («Не так? Изменить») can't be made of what was given; None - it can."""
    if what not in WHATS:
        return i18n.L(f"Неизвестно, что снимать: {what}", f"Unknown kind of video: {what}")
    if what == "beat":
        return None if has_song else i18n.L("Для бит-клипа нужна песня", "A beat clip needs a song")
    if what.startswith("clip") and not has_song:
        return i18n.L("Для клипа нужна песня", "A clip needs a song")
    if what in ("clip_hero", "story_hero", "story_start") and not has_photo:
        return i18n.L("Нужно фото", "A photo is needed")
    if what == "story" and len(text.strip()) < 3:
        return i18n.L("Напишите идею", "Write an idea")
    return None


class Autopilot(BaseModel):
    song: Optional[str] = None            # a clip's song (the song library); none - a story from text
    what: str = Field("auto", max_length=20)   # WHATS, or auto - understand()
    photo: Optional[str] = None           # the hero's photo (a name from /api/frames)
    idea: str = Field("", max_length=4000)  # a clip: one line, the idea or the mood; a story: the idea
    mode: str = "auto"                    # a story: who is in the frame (grid.MODES); auto - story.people_of(the idea)
    delivery: str = Field("auto", max_length=40)   # «Подача» (looks.DELIVERIES); auto - the writer picks
    look: str = Field("auto", max_length=40)       # «Вид» (looks.LOOKS, a saved «my_…»); auto - the writer picks
    look_own: str = Field("", max_length=600)      # «Свой вид»
    hero_text: str = Field("", max_length=1200)    # a story: «Герой своими словами» (cast 1, the writer puts it into English)
    hero_kind: str = "person"                      # person | animal | robot | creature
    aspect: str = "16:9"
    length: str = "whole"                 # a clip: whole | best (the best ~1 minute) | own (from `start`, `seconds` long)
    start: float = Field(0, ge=0)         # own: where the piece begins (snapped to a bar, clip.fragment)
    video_model: str = ""                 # "" - a clip: videomodels.clip_default(), a story: videomodels.default()
    model: Optional[str] = None           # the writer
    quality: str = "final"
    seconds: Optional[float] = Field(None, ge=5, le=grid.MAX_SECONDS)   # a clip's own piece / best (tests); a story's length
    ask: bool = False                     # «Спрашивать меня»: the stops for the hero and the trial scene
    # «Ещё настройки»: what runs (the defaults are everything, as before the switches)
    script: str = "writer"                # writer | own: «пишу сам» - the scenes cut and the board opened, nothing more runs
    hero: bool = True                     # the hero's portrait is drawn (Krea / Klein from the photo); off - text or the photo as it is
    frames: bool = True                   # the scenes' start frames are drawn (FLUX.2 Klein); forced on by a look that needs them
    places: bool = True                   # «Места»: the places painted first (only with the frames)
    # «Бит-клип» (what == "beat", app/beat_clip.py): the faceless hero's preset, the genre preset (auto - by the tempo), the pictures' model
    hero_preset: str = Field("chrome", max_length=20)
    # the beat hero in the user's words: `hero_text` (shared with a story's «Герой своими словами») adds details to the preset,
    # or is the hero alone when `hero_own` («Свой герой»); `hero_face_hidden` (own hero only) off lets the hero show a face
    hero_own: bool = False
    hero_face_hidden: bool = True
    genre: str = Field("auto", max_length=20)
    picture_model: str = Field("krea2", max_length=20)


def name(stage: str) -> str:
    if stage in NAMES:
        return i18n.L(*NAMES[stage])
    from . import beat_clip
    return beat_clip.name(stage)


def what_of(req: Autopilot) -> str:
    return req.what if req.what in WHATS else understand(bool(req.song), bool(req.photo), req.idea) or "story"


def is_clip(req: Autopilot) -> bool:
    return what_of(req).startswith("clip")


def needs_frame(look_id: str) -> bool:
    """The look draws every scene's start frame (looks `needs_frame`, when this build has the field; a saved «my_…» look
    takes its base's)."""
    x = looks.LOOKS.get(look_id)
    if x is None and look_id:
        x = looks.LOOKS.get((looks.mine_of(look_id) or {}).get("base") or "")
    return bool((x or {}).get("needs_frame"))


def stages_of(req: Autopilot) -> tuple[str, ...]:
    """The stages this request runs: a story has no song's words; the trial scene only when the user is asked; «пишу
    сам» stops at the cut scenes (the board opens); the switches drop the hero, the places and the frames."""
    if what_of(req) == "beat":
        from . import beat_clip
        return beat_clip.STAGES
    if req.script == "own":
        return tuple(x for x in STAGES[:2] if x != "words" or is_clip(req))
    frames = req.frames or needs_frame(req.look)
    skip = {"hero": not req.hero, "frames": not frames, "places": not (frames and req.places)}
    return tuple(x for x in STAGES if (x != "words" or is_clip(req)) and (x != "trial" or req.ask) and not skip.get(x))


def drop_at(sid: str) -> float:
    """Where the song's drop starts, in song seconds, on a beat: the first chorus by the words (the lines sung twice), else
    the first part the sound calls a drop, else the beat nearest to a third of the song."""
    a = song.analysis(sid)
    chorus = song.chorus_spans(song.lines(sid))
    at = chorus[0][0] if chorus else next((x.start for x in a.sections if x.kind == "drop"), None)
    if at is None:
        at = a.duration / 3
    return min(a.beats, key=lambda b: abs(b - at)) if a.beats else float(at)


def window(sid: str, length: str, seconds: Optional[float] = None, start: float = 0.0) -> tuple[float, float]:
    """(start, seconds) of the song the clip takes: the user's own piece, the whole song, a minute (`seconds`, when
    given) holding the first chorus (the lines sung twice); no chorus - from the first sung line, no words - before the
    first loud part. «drop» (the beat clip): the drop (drop_at) with one bar more than the build before it and one bar
    more than the drop after it - the bars the beat renderer cuts."""
    a = song.analysis(sid)
    if length == "drop":
        at = drop_at(sid)
        t0 = max(0.0, at - 4 * (DROP_BUILD_BARS + 1) * a.beat_s)
        return round(t0, 3), round(min(4 * (DROP_BUILD_BARS + DROP_BARS + 2) * a.beat_s, a.duration - t0), 3)
    if length == "own":   # clip.fragment snaps it to a bar and moves a piece past the end back
        return round(min(start, a.duration), 3), round(min(seconds or BEST, a.duration), 3)
    want = seconds or BEST
    if (length != "best" and not seconds) or a.duration <= want + 15:
        return 0.0, round(a.duration, 3)
    lead = min(LEAD, want * 0.4)
    ls = song.lines(sid)
    chorus = song.chorus_spans(ls)
    loud = next((x.start for x in a.sections if x.kind == "drop"), None)
    start = (chorus[0][0] - lead if chorus else ls[0]["start"] - 2.0 if ls else loud - lead if loud is not None
             else (a.duration - want) / 2)
    return round(max(0.0, min(start, a.duration - want)), 3), want


def _clip_req(req: Autopilot, start: float, seconds: float) -> clip_api.NewClip:
    """The clip's form as «Клип из песни» would send it: one hero (from the photo, or the writer's), the writer's story,
    every scene written; the words, the portrait, the places and the frames are the autopilot's own stages."""
    return clip_api.NewClip(song=req.song, start=start, seconds=max(4.0, seconds), idea=f"{req.idea.strip()} {PLAN_HINT}".strip(), mode="one", aspect=req.aspect,
                            photo=req.photo, model=req.model, video_model=req.video_model, sing_model="auto", lyrics=False,
                            draw_singer=False, frames=False, places=False, look="photo" if req.photo else "writer",
                            story="writer", scenes="none" if req.script == "own" else "all", faceless=0 if req.script == "own" else FACELESS,
                            delivery=req.delivery, look_id=req.look, look_own=req.look_own)


def _story_req(req: Autopilot) -> story.NewProject:
    """The idea screen's form for a story: the photo as the hero (or the first frame), no idea - one about the person
    in the photo."""
    what = what_of(req)
    idea = req.idea.strip() or (i18n.L("Короткая история о человеке с фото", "A short story about the person in the photo")
                                if req.photo else "")
    return story.NewProject(idea=idea, seconds=req.seconds or STORY_SECONDS,
                            mode=story.people_of(idea, bool(req.photo)) if req.mode == "auto" else req.mode, aspect=req.aspect,
                            delivery=req.delivery, look=req.look, look_own=req.look_own,
                            photo=req.photo if what in ("story_hero", "story_start") else None, photo_start=what == "story_start",
                            hero_text=req.hero_text, hero_kind=req.hero_kind,
                            model=req.model, video_model=req.video_model)


def _check(req: Autopilot) -> None:
    """What would fail at once: the same checks as «Расписать клип» / «Расписать сцены» and «Снять ролик», before
    anything runs. The request is settled on the way: what it makes, the photo it keeps, the writer."""
    what = what_of(req)
    if why := misfit(what, bool(req.song), bool(req.photo), req.idea):
        raise HTTPException(400, why)
    req.what = what
    if what == "beat":
        from . import beat_clip
        return beat_clip.check(req)
    if req.script not in ("writer", "own"):
        raise HTTPException(400, i18n.L(f"Неизвестный сценарий: {req.script}", f"Unknown script choice: {req.script}"))
    req.frames = req.frames or needs_frame(req.look)   # a look that draws every frame can't go without them
    req.places = req.places and req.frames
    if what == "clip" or what == "story":
        req.photo = None   # given, but «Не так? Изменить» said not to use it
    if not what.startswith("clip"):
        req.song = None
    if req.quality not in graphs.QUALITY_MP:
        raise HTTPException(400, i18n.L(f"Неизвестное качество: {req.quality}", f"Unknown quality: {req.quality}"))
    req.video_model = req.video_model or (videomodels.clip_default() if what.startswith("clip") else videomodels.default())
    if not videomodels.offered(req.video_model):
        raise HTTPException(400, i18n.L(f"Неизвестная модель: {req.video_model}", f"Unknown model: {req.video_model}"))
    if missing := videomodels.weights_missing(c := videomodels.card(req.video_model)):
        raise HTTPException(400, videomodels.missing_text(c, missing))
    if what.startswith("clip"):
        try:
            song.public(req.song)
        except EngineError as e:
            raise HTTPException(404, str(e)) from e
        if req.aspect not in graphs.ASPECTS:
            raise HTTPException(400, i18n.L(f"Неизвестный формат кадра: {req.aspect}", f"Unknown frame format: {req.aspect}"))
        if req.length not in ("whole", "best", "own"):
            raise HTTPException(400, i18n.L(f"Неизвестная длина: {req.length}", f"Unknown length: {req.length}"))
        if len(req.idea) > IDEA_CLIP:
            raise HTTPException(400, i18n.L(f"Идея клипа — одна строка, до {IDEA_CLIP} знаков", f"A clip's idea is one line, up to {IDEA_CLIP} characters"))
        try:
            model = llm.find(req.model)
        except llm.LLMError as e:
            raise HTTPException(400, str(e)) from e
        if req.photo:
            if Path(req.photo).name != req.photo or not (config.COMFY_INPUT / req.photo).exists():
                raise HTTPException(400, i18n.L("Фото не найдено, загрузите его снова", "Photo not found, upload it again"))
            if not model.mmproj:
                raise HTTPException(400, i18n.L(f"Модель {model.name} не видит картинок: выберите другую или уберите фото",
                                                f"Model {model.name} can't see pictures: choose another one or remove the photo"))
    else:
        model = story.check_new(_story_req(req))
    if issues := COMFY.problems():
        raise HTTPException(400, "; ".join(issues))
    req.model = model.id   # «Продолжить» writes with the same one


def _busy(pid: str) -> bool:
    return any(j.status in ("queued", "running") and j.kind in ("autopilot", "render", "write") and j.params.get("project") == pid
               for j in jobs.JOBS.values())


def _submit(req: Autopilot, pid: Optional[str], proj: Optional[dict]) -> dict:
    title = (proj or {}).get("name") or (song.public(req.song)["name"] if req.song else req.idea.strip()[:60] or i18n.L("История", "Story"))
    return jobs.submit_task("autopilot", {"song": req.song, "name": title, "project": pid, "what": req.what, "req": req.model_dump()},
                            lambda job: run(job, req, pid), estimate=_estimates(req, proj)[0]).public()


@router.post("/api/autopilot")
def start(req: Autopilot):
    """«Сделать ролик»: one job from the song or the idea to the finished video (run). The project appears in
    job.params once it is made (a clip's after the words: the best minute is found by them)."""
    _check(req)
    return _submit(req, None, None)


@router.post("/api/projects/{pid}/autopilot")
def resume(pid: str):
    """«Продолжить»: the autopilot of this project goes on from the stage that failed or was stopped."""
    try:
        proj = projects.load(pid)
    except projects.NotFound as e:
        raise HTTPException(404, i18n.L("Проект не найден", "Project not found")) from e
    st = proj.get("autopilot")
    if not st or not st.get("req"):
        raise HTTPException(400, i18n.L("Этот ролик сделан не «Сделать ролик»", "This video was not made by «Make the video»"))
    if _busy(pid):
        raise HTTPException(409, i18n.L("Над этим роликом уже идёт работа", "This video is already being worked on"))
    req = Autopilot(**st["req"])
    _check(req)
    return _submit(req, pid, proj)


@router.get("/api/autopilot/window")
def song_window(song_id: str, length: str = "whole", seconds: Optional[float] = None, start: float = 0.0):
    """The piece of the song a clip takes («Пошагово» from the home makes the clip with it): {start, seconds}."""
    try:
        song.public(song_id)
    except EngineError as e:
        raise HTTPException(404, str(e)) from e
    if length not in ("whole", "best", "own", "drop"):
        raise HTTPException(400, i18n.L(f"Неизвестная длина: {length}", f"Unknown length: {length}"))
    a, b = window(song_id, length, seconds, max(0.0, start))
    return {"start": a, "seconds": b}


class Answer(BaseModel):
    pick: Optional[str] = Field(None, max_length=80)   # «Выберите героя»: this try
    more: bool = False                    # ... «Попросить других кандидатов»
    go: bool = False                      # «Пробная сцена»: «Дальше»
    hold: bool = False                    # ... the user opened «Сменить вид»: the wait is longer
    delivery: Optional[str] = Field(None, max_length=40)   # ... and changed the look: the style rebuilt
    look: Optional[str] = Field(None, max_length=40)
    look_own: Optional[str] = Field(None, max_length=600)


ANSWERS: dict[str, dict] = {}   # project id -> the user's answer to the stop its autopilot waits at


def waiting(pid: str) -> Optional[jobs.Job]:
    """The project's autopilot job that waits at a stop now."""
    return next((j for j in jobs.JOBS.values() if j.kind == "autopilot" and j.status == "running"
                 and j.params.get("project") == pid and j.progress.get("ask")), None)


@router.post("/api/projects/{pid}/autopilot/answer")
def answer(pid: str, body: Answer):
    """The user's answer at a stop of «Спрашивать меня»: the hero picked or more tries; the trial scene good, or the
    look changed (saved here at once, as the board's «Подача · Вид ✎» does: the style rebuilt)."""
    job = waiting(pid)
    if not job:
        raise HTTPException(409, i18n.L("Сейчас автопилот ничего не спрашивает", "The autopilot is not asking anything now"))
    ask = job.progress["ask"]
    looked = any(x is not None for x in (body.delivery, body.look, body.look_own))
    if ask["kind"] == "hero":
        if body.pick is None and not body.more:
            raise HTTPException(400, i18n.L("Выберите героя", "Pick the hero"))
        if body.pick is not None and body.pick not in [t["file"] for t in ask["tries"]]:
            raise HTTPException(400, i18n.L("Нет такой пробы", "No such try"))
        ANSWERS[pid] = {"pick": body.pick} if body.pick else {"more": True}
    else:
        if not (body.go or body.hold or looked):
            raise HTTPException(400, i18n.L("«Дальше» или «Сменить вид»", "«Next» or «Change the look»"))
        if looked:
            proj = projects.load(pid)
            if story.change_look(proj, {k: v for k, v in body.model_dump().items() if k in ("delivery", "look", "look_own") and v is not None}):
                projects.save(proj)
                ANSWERS[pid] = {"look": True}
            else:   # «Готово» on the same choice: nothing to rebuild or shoot again
                ANSWERS[pid] = {"go": True}
        else:
            ANSWERS[pid] = {"hold": True} if body.hold else {"go": True}
    return {"ok": True}


async def _ask(job: jobs.Job, pid: str, ask: dict) -> Optional[dict]:
    """A stop: the question in job.progress["ask"] (the page shows it with its countdown) and in the project (asked
    again after a restart), the answer awaited WAIT seconds. -> the answer, None when nobody answered."""
    t0 = time.time()
    ask = {**ask, "id": uuid.uuid4().hex[:8], "wait": WAIT, "until": t0 + WAIT}
    ANSWERS.pop(pid, None)
    job.progress["ask"] = ask
    _state(pid, ask=ask)
    got = None
    try:
        while time.time() < ask["until"]:
            got = ANSWERS.pop(pid, None)
            if got and got.get("hold"):   # «Сменить вид» is open: the countdown waits for the choice, HOLD at most
                ask.update(until=max(ask["until"], t0 + HOLD), wait=HOLD, held=True)
                got = None
                continue
            if got is not None:
                break
            await asyncio.sleep(POLL)
    finally:   # answered, timed out or stopped: the stop is gone (only a restart leaves it, to be asked again)
        job.progress.pop("ask", None)
        ANSWERS.pop(pid, None)
        _state(pid, ask=None)
    return got


def _length(req: Autopilot) -> tuple[float, float]:
    """(seconds of the video, seconds of a scene) before the script: a clip's piece of the song (a scene every ~4 s of
    it), a story's length (the model's scene length)."""
    if is_clip(req):
        a = song.analysis(req.song)
        secs = (window(req.song, req.length, req.seconds, req.start)[1] if song.recognised(req.song) or req.length == "own" or (req.length == "whole" and not req.seconds)
                else req.seconds or BEST)
        return min(a.duration, secs), 4.0
    return req.seconds or STORY_SECONDS, float(videomodels.card(req.video_model).grid_seconds)


def _writer(req: Autopilot) -> str:
    """The writer's name for its timings; none found (the route's estimate before any LLM is there): any model's."""
    try:
        return llm.find(req.model).name
    except llm.LLMError:
        return ""


def _estimates(req: Autopilot, proj: Optional[dict]) -> tuple[float, dict]:
    """(total, {stage: seconds}) of the stages still to run: rough before the script (a clip: a scene every ~4 s of
    the song; a story: the model's scene length), this machine's own figures after it (the writer's speed, the
    render's estimate with its cache)."""
    if what_of(req) == "beat":
        from . import beat_clip
        return beat_clip.estimates(req, proj)
    clip = is_clip(req)
    secs, each = _length(req)
    own = req.script == "own"
    plan = (proj or {}).get("plan") or {}
    n = len(plan.get("scenes") or []) or max(1, round(secs / each))
    from . import frames, places
    # the frames: the scenes that get one once the script is known (a look drawn by every frame - every new scene,
    # looks.needs_frame), before it every scene
    drawn = sum(1 for s in plan["scenes"] if frames.can_draw(plan, s)) if plan.get("scenes") else n
    writer = _writer(req)
    est = {"words": 0 if not clip or song.recognised(req.song) else 40,
           "write": (timings.writer_seconds(writer, n, 10 + 4 * n) if clip else timings.writer_seconds(writer, n, 8 + 3 * n)) + (10 if req.photo else 0),
           "hero": 20 + 15 * TRIES + (WAIT if req.ask else 0), "places": 25 + places.estimate(4), "frames": frames.estimate(drawn) * 1.4}
    if own:   # the scenes only cut: seconds
        est["write"] = 8 if clip else 2
    if plan.get("scenes"):
        st = {**proj["settings"], "quality": req.quality}
        est["render"] = render.estimate(st, plan["scenes"]) + ASSEMBLY
    else:
        st = {"aspect": req.aspect, "quality": req.quality, "video_model": req.video_model}
        est["render"] = render.estimate(st, [{"seconds": secs / n}] * n) + ASSEMBLY
    est["trial"] = est["render"] / n + WAIT
    done = set(((proj or {}).get("autopilot") or {}).get("done") or [])
    est = {k: round(v) for k, v in est.items() if k in stages_of(req) and k not in done}
    return sum(est.values()), est


# the route «Как снимаем» (the home's seven steps, lib/home.ts STEPS): the server's stages fall on them as on the bar
STEP_OF = {"words": "words", "write": "write", "hero": "hero", "places": "places", "frames": "frames", "trial": "shoot", "render": "shoot"}


@router.post("/api/autopilot/estimate")
def route_estimate(req: Autopilot):
    """The route before the start: the same stages and figures «Сделать ролик» starts its job with (_estimates), by the
    home's steps (the trial scene is «Съёмка»; the render's assembly, mixing and 1080p are «Монтаж»), the scenes, the
    card the times are of (this PC's GPU, or the cloud server's) and every offered model's time of one scene (the
    «Съёмка» step's model list). Nothing is checked that only the start needs (weights, the engine, the writer)."""
    req = req.model_copy()
    req.what = what_of(req)
    if why := misfit(req.what, bool(req.song), bool(req.photo), req.idea):
        raise HTTPException(400, why)
    if not req.what.startswith("clip") and req.what != "beat":
        req.song = None
    if req.what in ("clip", "story"):
        req.photo = None
    if req.what == "beat":
        from . import beat_clip
        if req.quality not in graphs.QUALITY_MP:
            raise HTTPException(400, i18n.L("Неизвестное качество", "Unknown quality"))
        req.video_model = req.video_model or videomodels.default()
        total, est = _estimates(req, None)
        return {"what": "beat", "total": round(total), "stages": est, "run": list(beat_clip.STAGES), "scenes": 16, "seconds": round(beat_clip.seconds_of(req), 1),
                "model": videomodels.card(req.video_model).name, "gpu": ((sysinfo.vram() or {}).get("name") or "").replace("NVIDIA ", "").replace("GeForce ", "")
                if timings.engine_key() == "local" else timings.engine_key(), "steps": est, "models": {}, "words_done": est.get("words", 0) == 0}
    if req.length not in ("whole", "best", "own") or req.quality not in graphs.QUALITY_MP:
        raise HTTPException(400, i18n.L("Неизвестная длина или качество", "Unknown length or quality"))
    req.video_model = req.video_model or (videomodels.clip_default() if req.song else videomodels.default())
    if not videomodels.offered(req.video_model):
        raise HTTPException(400, i18n.L(f"Неизвестная модель: {req.video_model}", f"Unknown model: {req.video_model}"))
    if req.song:
        try:
            song.public(req.song)
        except EngineError as e:
            raise HTTPException(404, str(e)) from e
    total, est = _estimates(req, None)
    secs, each = _length(req)
    steps: dict[str, int] = {}
    for k, v in est.items():
        steps[STEP_OF[k]] = steps.get(STEP_OF[k], 0) + v
    if "render" in est:   # the assembly is the montage's
        steps["shoot"] = max(0, steps["shoot"] - round(ASSEMBLY))
        steps["montage"] = round(ASSEMBLY)
    st = {"aspect": req.aspect, "quality": req.quality}
    models = {c: round(render.estimate({**st, "video_model": c}, [{"seconds": min(each, videomodels.card(c).max_seconds)}]))
              for c in videomodels.CARDS if videomodels.offered(c)}
    key = timings.engine_key()
    gpu = ((sysinfo.vram() or {}).get("name") or "").replace("NVIDIA ", "").replace("GeForce ", "") if key == "local" else key
    stages = stages_of(req)
    return {"what": req.what, "total": round(total), "stages": est, "steps": steps, "scenes": max(1, round(secs / each)),
            "seconds": round(secs, 1), "run": list(stages), "model": videomodels.card(req.video_model).name, "models": models,
            "gpu": gpu, "words_done": "words" in stages and est.get("words", 0) == 0}


class _Lens:
    """The job as one stage sees it: its own start, so the estimate it sets (elapsed + its own rest) lands on the
    job's as the time before the stage + that + the stages after it. Everything else is the job itself."""

    def __init__(self, job: jobs.Job, after: float):
        object.__setattr__(self, "_job", job)
        object.__setattr__(self, "_t0", time.time())
        object.__setattr__(self, "_after", after)

    def __getattr__(self, k):
        return self._t0 if k == "started" else getattr(self._job, k)

    def __setattr__(self, k, v):
        if k == "estimate":
            v = round(self._t0 - (self._job.started or self._t0) + v + self._after)
        setattr(self._job, k, v)


def _state(pid: str, **kw) -> None:
    """project["autopilot"] updated (the project as it is now: the stages save it themselves)."""
    cur = projects.load(pid)
    cur.setdefault("autopilot", {}).update(kw)
    projects.save(cur)


async def run(job: jobs.Job, req: Autopilot, pid: Optional[str] = None) -> dict:
    from . import beat_clip
    proj = projects.load(pid) if pid else None
    done: list[str] = list(((proj or {}).get("autopilot") or {}).get("done") or [])
    stages = stages_of(req)
    _, est = _estimates(req, proj)
    auto = job.progress["auto"] = {"stages": [{"id": k, "est": est.get(k, 0), "done": k in done} for k in stages], "stage": None,
                                   "what": req.what, "ask": req.ask}
    note = ""
    for stage in stages:
        if stage in done:
            continue
        if pid:   # the estimates of the stages ahead, the script known now
            _, est = _estimates(req, projects.load(pid))
            for x in auto["stages"]:
                x["est"] = est.get(x["id"], 0) if not x["done"] else x["est"]
        after = sum(est.get(k, 0) for k in stages[stages.index(stage) + 1:] if k not in done)
        auto.update(stage=stage, t=time.time())
        job.estimate = round(time.time() - (job.started or time.time()) + est.get(stage, 0) + after)
        lens = _Lens(job, after)
        if pid:
            _state(pid, stage=stage, error=None, stopped=False, finished=False)
        try:
            if req.what == "beat":
                pid = await beat_clip_run(lens, req, pid, stage)
            elif stage == "words":
                note = await _words(lens, req)
            elif stage == "write":
                pid = await (_write(lens, req, pid, note) if is_clip(req) else _write_story(lens, req, pid))
            elif stage == "hero":
                await _hero(lens, req, pid)
            elif stage == "places":
                if not picture.edit_problem():   # places are only the frames' second picture
                    await clip_api.group_places(lens, pid)
                    await clip_api.draw_places(lens, pid)
            elif stage == "frames":
                await clip_api.draw_frames(lens, pid)
            elif stage == "trial":
                await _trial(lens, req, pid)
            elif stage == "render":
                r = await _render(lens, req, pid)
                if not r.get("complete"):   # «Остановить после текущей сцены»: the shots so far stay
                    _state(pid, stopped=True)
                    return {"project": pid, "complete": False}
        except asyncio.CancelledError:
            if pid:
                _state(pid, stopped=True)
            raise
        except beat_clip.Stopped:   # «Остановить после текущей сцены» in a beat clip: the work so far stays
            if pid:
                _state(pid, stopped=True)
            return {"project": pid, "complete": False}
        except Exception as e:  # noqa: BLE001 - the stage named, «Продолжить» goes on from it
            msg = getattr(e, "detail", None) or str(e) or type(e).__name__
            if pid:
                _state(pid, error=msg)
            raise EngineError(i18n.L(f"Этап «{name(stage)}»: {msg}", f"Stage «{name(stage)}»: {msg}")) from e
        done.append(stage)
        next(x for x in auto["stages"] if x["id"] == stage)["done"] = True
        if pid:
            _state(pid, done=list(done))
    auto["stage"] = None
    _state(pid, stage=None, finished=True)
    return {"project": pid, "complete": True}


async def beat_clip_run(job, req: Autopilot, pid: Optional[str], stage: str) -> Optional[str]:
    from . import beat_clip
    return await beat_clip.run_stage(job, req, pid, stage)


async def _words(job, req: Autopilot) -> str:
    """The words with their times (Demucs + Whisper), unless known: the singing scenes and the best minute need them. A
    failure is noted, not fatal - the clip is written without singing scenes, as «Клип из песни» does."""
    if song.recognised(req.song):
        return ""
    try:
        await clip_api._recognise(job, req.song)
    except EngineError as e:
        return str(e)
    return ""


async def _write(job, req: Autopilot, pid: Optional[str], note: str) -> str:
    """The clip's project (made now, or the one whose writer failed) and its script: the scenes cut on the song, the
    treatment, the hero (described from the photo), every scene written. -> the project's id."""
    start, seconds = window(req.song, req.length, req.seconds, req.start)
    try:
        pid, write, _, _ = clip_api.start_clip(_clip_req(req, start, seconds), pid)
    except HTTPException as e:
        raise EngineError(str(e.detail)) from e
    job.params["project"] = pid
    _state(pid, req=req.model_dump(), window=[start, seconds], done=["words"], stage="write", started=time.time())
    await write(job)
    cur = projects.load(pid)
    if req.script == "own":   # the skeleton, saved by the clip's own run: the user writes on the board («Написать остальные»)
        if not (cur.get("plan") or {}).get("scenes"):
            raise EngineError(i18n.L("Не удалось нарезать сцены", "The scenes could not be cut"))
        return pid
    if not (cur.get("plan") or {}).get("scenes"):
        raise EngineError(i18n.L("Сценарист не написал сцены", "The writer wrote no scenes"))
    if note:
        cur["plan"].setdefault("clip", {})["lyrics_error"] = note
    sing_cameras(cur["plan"])
    cur["plan"] = check.plan(cur["plan"])
    projects.save(cur)
    return pid


def sing_cameras(plan: dict) -> None:
    """The singers push in (a close-up) or orbit (medium) instead of formula 3's handheld: LTX 2.3 lost the face from
    its frame in 13 of 29 handheld singing scenes (2026-11-02), «Ночной дрифт» with these cameras held it. «Вид» may
    have its own camera for singers (a drawn or animated look: a slow push-in). The graph's «Сценарист клипа» too."""
    cam = looks.camera_for_singing(plan)
    for s in plan["scenes"]:
        if s.get("shot") == "sing" and s.get("camera") in (None, "static", "handheld"):
            s["camera"] = cam or ("push_in" if s.get("framing") == "close" else "orbit")


async def _write_story(job, req: Autopilot, pid: Optional[str]) -> str:
    """A story's project (made now, as «Расписать сцены» makes it, or the one whose writer failed) and its storyboard
    written from the idea (story.py). -> the project's id."""
    nr = _story_req(req)
    model = llm.find(req.model)
    if req.script == "own":   # «пишу сам»: the empty storyboard of the length, as «Свои промты» makes it
        if pid is None:
            from . import main   # late: main imports this module
            nr.manual, nr.photo = True, None
            pid = main._manual_project(nr)["project"]
            job.params["project"] = pid
            _state(pid, req=req.model_dump(), done=[], stage="write", started=time.time())
        return pid
    if pid is None:
        proj = story.create(nr, model)
        pid = proj["id"]
        proj["name"] = nr.idea.strip()[:60]
        projects.save(proj)
        job.params["project"] = pid
        _state(pid, req=req.model_dump(), done=[], stage="write", started=time.time())
    cur = projects.load(pid)
    if not (cur.get("plan") or {}).get("scenes"):
        job.progress["stage"] = "writing"
        await story.write(pid, story.plan_for(nr, model, cur["settings"].get("photo")), nr.mode)
    if not (projects.load(pid).get("plan") or {}).get("scenes"):
        raise EngineError(i18n.L("Сценарист не написал сцены", "The writer wrote no scenes"))
    return pid


def _try_view(t: dict) -> dict:
    return {"file": t["file"], "faces": t.get("faces"), "sim": t.get("sim")}


async def _hero(job, req: Autopilot, pid: str) -> None:
    """The hero's portrait, approved as the casting tab would: from the user's photo FLUX.2 Klein draws TRIES tries and
    the likest (SFace, one face, at least FRAME_FACE_MIN) is approved - none that close: the photo itself stays; without a
    photo Krea 2 draws tries until one has a single face, and that one is approved; none has - the first cut to its
    biggest face (hero.one_face), as it is only when even that fails. «Спрашивать меня»: every try is drawn and the
    user picks («Выберите героя»), or asks for others; nobody answers - the one it would have taken. A story's other
    heroes get a portrait each the same way, without asking."""
    from . import hero
    proj = projects.load(pid)
    cast = (proj["plan"].get("cast") or [])
    if proj["plan"].get("mode") == "none" or not cast:
        return
    photo = bool(proj["settings"].get("photo"))
    if photo:
        if picture.edit_problem() or not cast[0].get("en"):
            return
    elif why := picture.problem():
        raise EngineError(why)
    if not (cast[0].get("photo") and not photo):   # «Продолжить» after the portrait was approved: it stays
        pending = (proj.get("autopilot") or {}).get("ask") or {}
        have = {t["file"]: t for t in cast[0].get("tries") or []}
        new = [have[t["file"]] for t in pending.get("tries") or [] if pending.get("kind") == "hero" and t["file"] in have]
        while True:
            if not new:
                new = await _tries(job, pid, 0, photo, every=req.ask)
            best = _best(pid, new, photo)
            if not req.ask:
                break
            got = await _ask(job, pid, {"kind": "hero", "photo": photo, "tries": [_try_view(t) for t in new],
                                        "best": best["file"] if best else None})
            if got and got.get("more"):
                new = []
                continue
            if got and got.get("pick"):
                best = next((t for t in new if t["file"] == got["pick"]), best)
            break
        if best:
            cur = projects.load(pid)
            hero.pick(cur, 0, best["file"])
            cur["plan"] = check.plan(cur["plan"])
            projects.save(cur)
    if is_clip(req) or picture.problem():
        return
    for i in range(1, len(projects.load(pid)["plan"].get("cast") or [])):
        c = projects.load(pid)["plan"]["cast"][i]
        if c.get("photo") or not (c.get("en") or "").strip():
            continue
        best = _best(pid, await _tries(job, pid, i, False, every=False), False, i)
        if best:
            cur = projects.load(pid)
            hero.pick(cur, i, best["file"])
            cur["plan"] = check.plan(cur["plan"])
            projects.save(cur)


async def _tries(job, pid: str, i: int, photo: bool, every: bool) -> list[dict]:
    """New tries of hero i: from the photo (FLUX.2 Klein, TRIES of them), else Krea 2 until one has a single face
    (`every`: all TRIES, for the user to choose)."""
    from . import hero
    before = {t["file"] for t in projects.load(pid)["plan"]["cast"][i].get("tries") or []}
    if photo:
        proj = await hero.photo_tries(job, pid, i, TRIES)
        return [t for t in proj["plan"]["cast"][i].get("tries") or [] if t["file"] not in before]
    new = []
    for _ in range(TRIES):
        proj = await hero.tries(job, pid, i, 1)
        new.append(proj["plan"]["cast"][i]["tries"][-1])
        if new[-1].get("faces") == 1 and not every:
            break
    return new


def _best(pid: str, new: list[dict], photo: bool, i: int = 0) -> Optional[dict]:
    """The try the autopilot takes: from a photo the likest with one face that is close enough (none: None, the photo
    stays); else the first with one face, else the first cut to its biggest face, else the first."""
    from . import hero
    if not new:
        return None
    if photo:
        good = [t for t in new if t.get("faces") == 1 and (t.get("sim") or 0) >= config.FRAME_FACE_MIN]
        return max(good, key=lambda t: t["sim"]) if good else None
    return next((t for t in new if t.get("faces") == 1), None) or next((c for t in new if (c := hero.one_face(pid, i, t["file"]))), new[0])


def trial_scene(plan: dict) -> Optional[int]:
    """The scene «Пробная сцена» shoots: a new written scene (a continuation needs its source shot first) - the first
    singing one, else the first with the hero, else the first."""
    new = [s for s in plan.get("scenes") or [] if s.get("kind") != "continue" and prompts.is_written(s)]
    people = plan.get("mode") != "none"
    for cond in (lambda s: s.get("shot") == "sing", lambda s: people and not prompts.no_cast(plan, s), lambda s: True):
        if x := next((s for s in new if cond(s)), None):
            return x["index"]
    return None


def _final(pid: str, quality: str) -> dict:
    """The quality asked (the final by default) with 1080p out, saved before anything is shot."""
    cur = projects.load(pid)
    st = cur["settings"]
    st["quality"] = quality
    st["output"] = {**(st.get("output") or {}), "size": "1080p"}
    return projects.save(cur)


async def _trial(job, req: Autopilot, pid: str) -> None:
    """«Пробная сцена»: one scene shot as the video will shoot it (the same quality and seed - the full shooting takes
    it from the cache), shown, and the user waited for: «Дальше», or «Сменить вид» - the look saved by the answer, the
    frames drawn again in it and the trial shot again."""
    if issues := COMFY.problems():
        raise EngineError("; ".join(issues))
    _final(pid, req.quality)
    while True:
        plan = projects.load(pid)["plan"]
        i = trial_scene(plan)
        if i is None:
            return
        s = plan["scenes"][i]
        r = await render.shoot_take(job, pid, i, render._seed(plan, s))
        got = await _ask(job, pid, {"kind": "trial", "scene": i, "file": f"scenes/{r['key']}.mp4", "video": plan.get("video") or "h3"})
        if not (got and got.get("look")):
            return
        await clip_api.draw_frames(job, pid)


async def _render(job, req: Autopilot, pid: str) -> dict:
    """The quality asked (the final by default) with 1080p out, then the project's own render: every scene shot with its
    checks and retakes (lips, black or frozen shots), the montage, the song, the RTX upscale."""
    if issues := COMFY.problems():
        raise EngineError("; ".join(issues))
    cur = _final(pid, req.quality)
    job.estimate = render.preview(cur)["seconds"] + 60
    r = await render.run(job, pid)
    return await _faces(job, pid, r) if r.get("complete") else r


def _scores(pid: str) -> dict[str, tuple[int, Optional[float]]]:
    """{scene id: (its seed, how like the hero's portrait its face is)} of the shot scenes with the hero framed close
    or medium - the median over five frames (checks.hero_similarity, the render's own `hero` check); None: no single
    face to judge."""
    from . import checks, hero
    proj = projects.load(pid)
    plan, folder = proj["plan"], projects.folder(pid)
    portrait = hero.portrait_path(proj, 0) if plan.get("cast") else None
    r = (proj.get("renders") or {}).get(proj["settings"].get("quality") or "draft") or {}
    if not portrait:
        return {}
    by_id = {s.get("id"): s for s in plan["scenes"]}
    out = {}
    for sh in r.get("shots") or []:
        s = by_id.get(sh.get("id"))
        if s and face_judged(plan, s) and (folder / sh["file"]).exists():
            out[s["id"]] = (sh["seed"], checks.hero_similarity(folder / sh["file"], portrait))
    return out


def face_judged(plan: dict, s: dict) -> bool:
    """A scene the face audit judges: the hero in it, framed close or medium (checks.HERO_MIN). The graph's
    «Развернуть в сцены» marks such scenes (`cut.face`) for its montage's «Проверять лица»."""
    from . import checks
    return not prompts.no_cast(plan, s) and prompts.faces_apply(plan) and s.get("framing") in checks.HERO_MIN


async def face_rounds(job, scores, reshoot) -> Optional[dict[str, int]]:
    """The face audit's rounds, the button's and the graph's: `scores()` -> {scene: (its seed, how like the hero its
    face is | None)} of the shots as they are; a scene below FRAME_FACE_MIN (and no take of it that close yet) is shot
    again with another seed by `reshoot(bad ids)` (-> False: stopped), up to FACE_ROUNDS rounds. -> {scene: the seed
    of its likest take} to keep, None when stopped."""
    best: dict[str, tuple[float, int]] = {}
    for rnd in range(FACE_ROUNDS + 1):
        sc = await scores()
        for k, (seed, v) in sc.items():
            if v is not None and (k not in best or v > best[k][0]):
                best[k] = (v, seed)
        bad = [k for k, (_, v) in sc.items() if v is not None and v < config.FRAME_FACE_MIN and best[k][0] < config.FRAME_FACE_MIN]
        job.progress["faces"] = {"round": rnd, "bad": len(bad), "judged": len(sc)}
        if not bad or rnd == FACE_ROUNDS:
            break
        if not await reshoot(bad):
            return None
    return {k: seed for k, (_, seed) in best.items()}


async def _faces(job, pid: str, r: dict) -> dict:
    """The face audit after the shooting: a scene whose face is not the hero's (below FRAME_FACE_MIN) is shot again
    with another seed, up to FACE_ROUNDS rounds (face_rounds); every scene keeps its likest take (the others stay its
    takes), and the video is assembled from them (the cache: nothing shot twice)."""
    last = {"r": r}

    async def scores():
        return await asyncio.to_thread(_scores, pid)

    async def reshoot(bad: list[str]) -> bool:
        cur = projects.load(pid)
        for s in cur["plan"]["scenes"]:
            if s.get("id") in bad:
                old = render.takes_of(cur["plan"], s)   # the shot before stays a take, as «Новый дубль» does
                s["seed"] = random.randrange(1, 2**31)
                s["takes"] = old + [s["seed"]]
        projects.save(cur)
        last["r"] = await render.run(job, pid)
        return bool(last["r"].get("complete"))

    keep = await face_rounds(job, scores, reshoot)
    if keep is None:
        return last["r"]
    cur, changed = projects.load(pid), False
    for s in cur["plan"]["scenes"]:
        if s.get("id") in keep and s.get("seed") != keep[s["id"]]:
            s["seed"] = keep[s["id"]]
            changed = True
    r = last["r"]
    if changed:
        projects.save(cur)
        r = await render.run(job, pid)
    return r
