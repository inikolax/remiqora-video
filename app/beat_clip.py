"""The beat clip's one button and its HTTP side: the autopilot kind `beat` with the stages

    words -> window -> pool -> pictures -> scenes -> beat -> render

each a function the graph uses too (graph_beat.write / expand, graph._make, graph.run); the project is a graph project made
from the template `beat-clip`, so everything the button made can be opened and edited in the graph. Also the beat montage
node's panel (parameters, captions, preview), the output's phone copy / cover / publication text, the faceless hero's
preset and `/api/beat/info` for the home page.

The stages: `words` (Demucs + Whisper, unless known), `window` (the drop and the project), `pool` (the writer writes the
shots - the only LLM stage - and «Развернуть» makes the chains), `pictures` (picture_checks.draw_checked: a diptych or a
face on a faceless hero is drawn again on a new seed), `scenes` (3 s from the picture; a still scene is shot again with a new
seed up to SCENE_ROUNDS times, the most moving take stays), `beat` (the montage, CPU), `render` (the output: the file as it
is, the phone copy <= 10 MB, the cover frame of the drop).
"""
from __future__ import annotations

import asyncio
import random
import shutil
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import beat_models, beatedit, checks, graph, graph_api, graph_beat, graph_io, hero as hero_lib, i18n, jobs, looks, picture, picture_checks, post, projects, render, song, timings
from .engine.comfy import EngineError

router = APIRouter()

STAGES = ("words", "window", "pool", "pictures", "scenes", "beat", "render")
NAMES = {"words": ("слова песни", "the song's words"), "window": ("окно дропа", "the drop's window"), "pool": ("план шотов", "the shot plan"),
         "pictures": ("картинки", "the pictures"), "scenes": ("сцены", "the scenes"), "beat": ("бит-монтаж", "the beat montage"),
         "render": ("ролик", "the video")}
SCENE_ROUNDS = 2      # a still scene is shot again this many times (a new seed each), the most moving take stays
PICTURE_S = 5.0       # a picture's seconds in the estimate
REDRAW = 1.2          # the estimate's share for the pictures drawn again and the scenes shot again
PHONE_S = 0.6         # seconds of the phone copy's two passes per second of the clip (estimate)


def name(stage: str) -> str:
    return i18n.L(*NAMES[stage])


# ---------------------------------------------------------------------------------------------------------------
# the project: the template `beat-clip` with the request's values in it
# ---------------------------------------------------------------------------------------------------------------
def build_project(req, title: str) -> tuple[str, str]:
    """A graph project from the template, the request put in: the song (copied into the project), the idea, the faceless hero
    of the preset, the writer's genre and look, the beat montage's preset, 9:16. -> (project id, the pool writer's node id)."""
    t = next((x for x in graph_io.templates() if x["id"] == "beat-clip"), None)
    if not t:
        raise EngineError(i18n.L("Нет шаблона «Бит-клип»", "No «Beat clip» template"))
    proj = graph_io.new_project(title, "9:16", quality=req.quality, g=graph_api._fresh_ids({"nodes": t["nodes"], "edges": t["edges"]}))
    pid = proj["id"]
    proj["settings"].update(video_model=req.video_model, delivery="auto", look=req.look or "auto", look_own="")
    projects.save(proj)
    got = graph_api.nodes_song(pid, graph_api.SongPick(song=req.song))
    bpm = song.analysis(req.song).bpm
    genre = req.genre if req.genre in graph_beat.GENRES else graph_beat.genre_of_bpm(bpm)
    g = graph.load(pid)
    ids = {n["type"]: n["id"] for n in g["nodes"]}

    def put(gg: dict) -> None:
        graph.node(gg, ids["song"])["data"].update(song=req.song, file=got["file"], name=got["name"], length="whole")
        graph.node(gg, ids["idea"])["data"]["text"] = req.idea.strip()
        graph.node(gg, ids["hero"])["data"].update(graph_beat.hero_data(
            req.hero_preset if req.hero_preset in hero_lib.FACELESS_PRESETS else hero_lib.FACELESS_DEFAULT, req.hero_text, req.hero_own, req.hero_face_hidden))
        graph.node(gg, ids["pool_writer"])["data"].update(genre=genre, look=req.look or "auto", n=graph_beat.POOL_N)
        graph.node(gg, ids["beat_montage"])["data"].update(preset=genre)
    graph.update(pid, put)
    return pid, ids["pool_writer"]


def _ids(pid: str) -> dict:
    g = graph.load(pid)
    return {n["type"]: n["id"] for n in g["nodes"] if n["type"] in ("pool_writer", "beat_montage", "output", "song")}


def _ctx(pid: str, quality: Optional[str] = None) -> graph.Ctx:
    return graph.Ctx(projects.load(pid), graph.load(pid), quality)


def _set(pid: str, nid: str, **data) -> dict:
    """Write node data (rev + 1). Returns the new rev and the keys as saved (None = gone), so a panel can take both over
    instead of keeping a stale rev that makes the canvas' next save a conflict."""
    def put(g: dict) -> None:
        if (n := graph.node(g, nid)):
            n["data"].update(data)
    g = graph.update(pid, put)
    n = graph.node(g, nid)
    return {"rev": g.get("rev", 0), "data": {k: (n["data"].get(k) if n else None) for k in data}}


def window_of(sid: str) -> dict:
    """The drop's window of a song for the home page: where the drop is, the length of the clip, the tempo, the genre."""
    from . import autopilot
    a = song.analysis(sid)
    start, secs = autopilot.window(sid, "drop")
    return {"bpm": round(a.bpm, 1), "genre": graph_beat.genre_of_bpm(a.bpm), "drop": round(autopilot.drop_at(sid), 3),
            "window": {"start": start, "seconds": secs}, "seconds": secs, "build_bars": autopilot.DROP_BUILD_BARS, "drop_bars": autopilot.DROP_BARS}


# ---------------------------------------------------------------------------------------------------------------
# the request's checks and estimates (autopilot.py calls these for what == "beat")
# ---------------------------------------------------------------------------------------------------------------
def check(req) -> None:
    """What would fail at once; the request is settled on the way (the 9:16 frame, the drop length)."""
    from . import videomodels
    from .engine.comfy import COMFY
    from .llm import client as llm
    if not req.song:
        raise HTTPException(400, i18n.L("Для бит-клипа нужна песня", "A beat clip needs a song"))
    try:
        song.public(req.song)
    except EngineError as e:
        raise HTTPException(404, str(e)) from e
    if len(req.idea.strip()) < 3:   # the idea is optional on the page: the song's name stands for it
        req.idea = i18n.L(f"Бит-клип под трек «{(song.public(req.song)['name'] or '').rsplit('.', 1)[0]}»",
                          f"A beat clip for the track «{(song.public(req.song)['name'] or '').rsplit('.', 1)[0]}»")
    if req.length not in ("drop",):
        raise HTTPException(400, i18n.L("Бит-клип пока только «дроп ≈ 24 с»", "A beat clip is «drop ≈ 24 s» only for now"))
    if req.genre != "auto" and req.genre not in graph_beat.GENRES:
        raise HTTPException(400, i18n.L(f"Неизвестный жанр: {req.genre}", f"Unknown genre: {req.genre}"))
    if req.hero_preset not in hero_lib.FACELESS_PRESETS:
        raise HTTPException(400, i18n.L(f"Неизвестный герой: {req.hero_preset}", f"Unknown hero: {req.hero_preset}"))
    req.hero_text = req.hero_text.strip()
    if req.hero_own and not req.hero_text:
        raise HTTPException(400, i18n.L("Опишите героя: для «Своего героя» нужен текст", "Describe the hero: «Own hero» needs a text"))
    if req.picture_model != "krea2":
        raise HTTPException(400, i18n.L("Картинки бит-клипа пока только Krea 2", "A beat clip's pictures are Krea 2 only for now"))
    if why := picture.problem():   # the weights of Krea 2: fail at once, not after minutes of the writer
        raise HTTPException(400, why)
    req.aspect, req.what = "9:16", "beat"
    req.photo = None
    req.video_model = req.video_model or videomodels.default()
    if not videomodels.offered(req.video_model):
        raise HTTPException(400, i18n.L(f"Неизвестная модель: {req.video_model}", f"Unknown model: {req.video_model}"))
    if req.video_model not in beat_models.MODELS:
        raise HTTPException(400, beat_models.refusal(req.video_model))
    if missing := videomodels.weights_missing(c := videomodels.card(req.video_model)):
        raise HTTPException(400, videomodels.missing_text(c, missing))
    try:
        req.model = llm.find(req.model).id
    except llm.LLMError as e:
        raise HTTPException(400, str(e)) from e
    if issues := COMFY.problems():
        raise HTTPException(400, "; ".join(issues))


def seconds_of(req) -> float:
    from . import autopilot
    return autopilot.window(req.song, "drop")[1]


def estimates(req, proj: Optional[dict]) -> tuple[float, dict]:
    """(total, {stage: seconds}) of the stages still to run."""
    from . import autopilot
    n = graph_beat.POOL_N
    secs = seconds_of(req)
    st = {"aspect": "9:16", "quality": req.quality, "video_model": req.video_model or "h3"}
    try:
        name_ = autopilot._writer(req)
    except Exception:  # noqa: BLE001
        name_ = ""
    est = {"words": 0 if song.recognised(req.song) else 40, "window": 2, "pool": timings.writer_seconds(name_, n, 10 + 4 * n) + 5,
           "pictures": PICTURE_S * n * REDRAW,
           "scenes": render.estimate(st, [{"seconds": 3}] * n) * REDRAW,
           "beat": graph.BEAT_RENDER_S * secs, "render": 10 + PHONE_S * secs}
    done = set(((proj or {}).get("autopilot") or {}).get("done") or [])
    est = {k: round(v) for k, v in est.items() if k not in done}
    return sum(est.values()), est


# ---------------------------------------------------------------------------------------------------------------
# the stages
# ---------------------------------------------------------------------------------------------------------------
class Stopped(Exception):
    """«Остановить после текущей сцены» was pressed: what is done stays, the run ends as stopped (not as an error)."""


async def run_stage(job, req, pid: Optional[str], stage: str, note: str = "") -> Optional[str]:
    """One stage of the beat kind. -> the project's id (made by `window`)."""
    from . import autopilot
    if stage == "words":
        await autopilot._words(job, req)
    elif stage == "window":
        pid = await asyncio.to_thread(_window, job, req, pid)
    elif stage == "pool":
        await _pool(job, req, pid)
    elif stage == "pictures":
        await draw_pictures(job, req, pid)
    elif stage == "scenes":
        await shoot_scenes(job, req, pid)
    elif stage in ("beat", "render"):
        await make_targets(job, pid, req, [_ids(pid)["beat_montage" if stage == "beat" else "output"]])
    return pid


def _window(job, req, pid: Optional[str]) -> str:
    from . import autopilot
    start, secs = autopilot.window(req.song, "drop")
    if pid is None:
        title = (song.public(req.song)["name"] or "").rsplit(".", 1)[0][:50] or i18n.L("Бит-клип", "Beat clip")
        pid, _ = build_project(req, i18n.L(f"Бит-клип: {title}", f"Beat clip: {title}"))
    job.params["project"] = pid
    drop = autopilot.drop_at(req.song)   # the words are recognised by now: pin this drop on the montage (graph.beat_drop)
    try:
        _set(pid, _ids(pid)["beat_montage"], drop_auto={"drop": round(drop, 4), "sig": graph.song_sig(req.song)})
    except (KeyError, OSError, EngineError):
        pass
    autopilot._state(pid, req=req.model_dump(), window=[start, secs], drop=drop, done=["words"], stage="window", started=time.time())
    return pid


async def _pool(job, req, pid: str) -> None:
    """The writer writes the pool (unless it is written from this very input), «Развернуть» makes the chains."""
    ids = _ids(pid)
    c = _ctx(pid)
    w = c.by[ids["pool_writer"]]
    if not w["data"].get("pool") or w["data"].get("sig") != graph_beat.sig(c, w):
        r = await graph.run_llm(job, pid, [w["id"]], req.model)
        if (err := r["errors"].get(w["id"])):
            raise EngineError(err)
    if not graph.node(graph.load(pid), w["id"])["data"].get("pool"):
        raise EngineError(i18n.L("Сценарист не написал шоты", "The writer wrote no shots"))
    await asyncio.to_thread(graph_beat.expand, pid, w["id"], "replace")


def _chain(g: dict, wid: str) -> list[tuple[dict, dict]]:
    """[(the picture node, the scene node)] of the pool's chains that are wired into the beat montage, in the pool's order."""
    by = {n["id"]: n for n in g["nodes"]}
    bm = next((n for n in g["nodes"] if n["type"] == "beat_montage" and (n["data"].get("from") == wid)), None)
    wired = {e["source"] for e in g["edges"] if bm and e["target"] == bm["id"] and e["targetHandle"] == "clips"}
    out = []
    for e in g["edges"]:
        if e["targetHandle"] == "start" and e["source"] in by and by[e["source"]]["type"] == "picture" and e["target"] in wired:
            out.append((by[e["source"]], by[e["target"]]))
    pos = {n["id"]: i for i, n in enumerate(g["nodes"])}
    return sorted(out, key=lambda pr: pos[pr[0]["id"]])


FACELESS_ROLES = ("hero", "impact", "close")   # a body of the hero is in the picture: no face may be seen on it


def faces_checked(pid: str) -> bool:
    """Whether a face on the hero's pictures and scenes is a fault: the hero hides its face, and its mask has no face of its
    own (oni, skull...: YuNet would see a face in every hero shot, so no check for those)."""
    g = graph.load(pid)
    hero = next((n for n in g["nodes"] if n["type"] == "hero"), None)
    hidden = hero_lib.face_hidden((hero or {}).get("data"))   # a hero who may show a face: no face-on-mask check
    pw = next((n["data"] for n in g["nodes"] if n["id"] == _ids(pid)["pool_writer"]), {})
    return hidden and not hero_lib.mask_has_features(f"{pw.get('hero_used') or ''} {pw.get('head_used') or ''}")


async def draw_pictures(job, req, pid: str) -> None:
    """Every picture of the pool through picture_checks.draw_checked (a diptych or a face on a faceless hero is drawn again on a
    new seed, up to TRIES times, the best try stays); the picture node keeps the seed that was kept."""
    ids = _ids(pid)
    chain = _chain(graph.load(pid), ids["pool_writer"])
    hidden = faces_checked(pid)
    prog = job.progress.setdefault("beat", {})
    prog["pictures"] = {"done": 0, "total": len(chain), "redraws": 0}
    for pn, sn in chain:
        if job.stop_after:   # «Остановить после текущей сцены»: between the pictures
            raise Stopped()
        c = _ctx(pid, req.quality)
        a = graph.evaluate_node(c, pn["id"])
        if a.state == "ready":
            prog["pictures"]["done"] += 1
            continue
        if a.state in ("error", "blocked", "wait"):
            raise EngineError(a.error or i18n.L("картинка не готова к съёмке", "the picture can not be drawn"))
        text = a.text if a.text else graph._picture_text(c, pn["id"])
        if (old := (pn["data"].get("retry_hint") or "").strip()) and text.endswith(old):
            text = text[:-len(old)].rstrip()   # the hint of an earlier draw is replaced, not doubled
        hints: dict[int, str] = {}
        seed0 = int(pn["data"].get("seed") or 1)
        tmp = c.folder / "pictures"
        tmp.mkdir(exist_ok=True)

        async def draw(seed: int, hint: str, _t=text, _c=c, _a=a, _id=pn["id"]) -> Path:
            dest = tmp / f"{_id}_{seed}.png"
            hints[seed] = hint
            await picture.generate(job, f"{_t} {hint}".strip(), seed, _c.pw, _c.ph, dest, _a.loras)
            return dest
        res = await picture_checks.draw_checked(draw, seed0, faceless=hidden and sn["data"].get("role") in FACELESS_ROLES, framing=sn["data"].get("framing"))
        prog["pictures"]["redraws"] += res["tries"] - 1
        # the hint the kept picture was drawn with stays on the node (graph's picture key reads it): key and picture agree
        if res["seed"] != seed0 or hints.get(res["seed"], "") != old:
            _set(pid, pn["id"], seed=res["seed"], retry_hint=hints.get(res["seed"], ""))
        a2 = graph.evaluate_node(_ctx(pid, req.quality), pn["id"])
        a2.path.parent.mkdir(exist_ok=True)
        shutil.copyfile(res["path"], a2.path)
        for f in tmp.glob(f"{pn['id']}_*.png"):
            f.unlink(missing_ok=True)
        prog["pictures"]["done"] += 1


async def shoot_scenes(job, req, pid: str) -> None:
    """Every scene of the pool: shot, then checks.scene_still; a still one is shot again with a new seed (SCENE_ROUNDS at most),
    the takes are kept on the node and the most moving one (checks.best_take) is the one the montage takes."""
    ids = _ids(pid)
    chain = _chain(graph.load(pid), ids["pool_writer"])
    prog = job.progress.setdefault("beat", {})
    faceless = faces_checked(pid)
    prog["scenes"] = {"done": 0, "total": len(chain), "reshoots": 0, "faces_left": 0}
    prog.setdefault("pictures", {"done": len(chain), "total": len(chain), "redraws": 0})   # a run continued from here: the pictures are done
    for _, sn in chain:
        if job.stop_after:   # «Остановить после текущей сцены»: between the scenes
            raise Stopped()
        nid = sn["id"]
        framing = sn["data"].get("framing")
        look_for_face = faceless and sn["data"].get("role") in FACELESS_ROLES   # a face under the hood, animated by H3
        model = beat_models.known(graph.scene_card(_ctx(pid, req.quality), sn)[0].id)   # its pre-roll and its still lines
        pre = beat_models.preroll(model)
        had = len(graph.node(graph.load(pid), nid)["data"].get("takes") or [1])   # a run continued after a stop: the rounds already used
        for rnd in range(had - 1, SCENE_ROUNDS + 1):
            c = _ctx(pid, req.quality)
            a = graph.evaluate_node(c, nid)
            if a.state in ("error", "blocked", "wait"):
                raise EngineError(a.error or i18n.L("сцена не готова к съёмке", "the scene can not be shot"))
            if a.state != "ready":
                await graph._make(job, c, nid, a)
                a = graph.evaluate_node(_ctx(pid, req.quality), nid)
            if rnd == SCENE_ROUNDS:
                break
            bad = (await asyncio.to_thread(checks.scene_still, a.path, framing, model))["still"] or (
                look_for_face and (await asyncio.to_thread(picture_checks.faces_in_scene, a.path, picture_checks.SCENE_FRAMES, pre))["bad"])
            if not bad:
                break
            old = [int(x) for x in graph.node(graph.load(pid), nid)["data"].get("takes") or [graph.seed_of(c.by[nid])]]
            _set(pid, nid, takes=old + [random.randrange(1, 2**31)], take=len(old))
            prog["scenes"]["reshoots"] += 1
        c = _ctx(pid, req.quality)
        a = graph.evaluate_node(c, nid)
        shot = {t["seed"]: render.shot_paths(c.folder / "scenes", t["key"])[0] for t in a.takes if t["cached"]}
        faced = set()
        if look_for_face and shot:   # a take with a face never beats a faceless one, however much it moves
            faced = {p for p in shot.values() if (await asyncio.to_thread(picture_checks.faces_in_scene, p, picture_checks.SCENE_FRAMES, pre))["bad"]}
        if len(shot) > 1:   # the most moving take is the one the montage takes
            best = await asyncio.to_thread(checks.best_take, list(shot.values()), faced, model)
            seeds = [int(x) for x in c.by[nid]["data"]["takes"]]
            pick = next((i for i, s_ in enumerate(seeds) if shot.get(s_) == best), seeds.index(graph.seed_of(c.by[nid])))
            _set(pid, nid, take=pick)
            chosen = best
        else:
            chosen = next(iter(shot.values()), None)
        if chosen is not None and chosen in faced:
            prog["scenes"]["faces_left"] += 1   # every take has a face: the montage takes the best of them
        prog["scenes"]["done"] += 1


async def make_targets(job, pid: str, req, targets: list[str]) -> None:
    """graph.run for the targets (the beat montage; the output), an error of the node raised."""
    r = await graph.run(job, pid, targets, req.quality)
    c = _ctx(pid, req.quality)
    for t in targets:
        a = graph.evaluate_node(c, t)
        if a.state != "ready":
            if job.stop_after:   # asked to stop: graph.run skipped the rest, that is a stop and not a failure
                raise Stopped()
            err = (r.get("errors") or {}).get(t)
            msg = (err.get("error") if isinstance(err, dict) else str(err or "")) or a.error or (r.get("error") if isinstance(r, dict) else "")
            raise EngineError(msg or i18n.L("узел не собрался или остановлен", "the node was not built or was stopped"))


# ---------------------------------------------------------------------------------------------------------------
# HTTP: info for the home page, the beat montage's panel, the output's publication panel, the hero's preset
# ---------------------------------------------------------------------------------------------------------------
@router.get("/api/beat/info")
def beat_info(song_id: str = Query("", alias="song")):
    """What the home page's «Бит-клип» needs: the faceless presets and the genres always; the song's drop, tempo and default
    genre when a song is given."""
    out = {"presets": [{"id": k, "ru": v[0], "en": v[1]} for k, v in hero_lib.FACELESS_PRESETS.items()],
           "genres": [{"id": k, "ru": v[0], "en": v[1]} for k, v in beatedit.PRESET_NAMES.items()]}
    if song_id:
        try:
            song.public(song_id)
            out.update(window_of(song_id))
        except EngineError as e:
            raise HTTPException(404, str(e)) from e
    return out


def _project(pid: str) -> dict:
    return graph_api._project(pid)


def _node(pid: str, nid: str, t: str) -> dict:
    n = graph.node(graph.load(pid), nid)
    if not n or n["type"] != t:
        raise HTTPException(404, i18n.L("Нет такого узла", "No such node"))
    return n


class HeroPreset(BaseModel):
    preset: str = Field("", max_length=40)
    own: bool = False                          # «Свой герой»: the text alone is the hero
    text: str = Field("", max_length=1200)     # the user's words: details of the preset, or the hero itself
    face_hidden: bool = True                   # own hero: the faceless rules on / off


@router.put("/api/projects/{pid}/nodes/{nid}/hero-preset")
def put_hero_preset(pid: str, nid: str, body: HeroPreset):
    """A «Герой» node's faceless preset: the data it takes (the lines, the titles) - the page merges it into the node."""
    _project(pid)
    try:
        return {"data": graph_beat.hero_data(body.preset, body.text, body.own, body.face_hidden)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _rel(c: graph.Ctx, p: Optional[Path]) -> Optional[str]:
    return graph.rel_path(c.folder, p) if p and p.exists() else None


def _beat_words(c: graph.Ctx, nid: str) -> tuple[list[dict], Optional[str], Optional[str], Optional[dict]]:
    """(the sung words in the song's time, the written text, the song's id, the grid) of a beat montage's song."""
    from . import autopilot
    tra = c.inputs(nid, "track")
    sa = graph.evaluate_node(c, tra[0][0]) if tra else None
    if not sa or not sa.song:
        return [], None, None, None
    sid = sa.song
    recd = song.recognised(sid)
    words = [{"start": w["start"], "end": w["end"], "word": w["word"]} for line in (recd or {}).get("lines", []) for w in line.get("words", [])]
    tf = song.folder(sid) / "text.txt"
    written = tf.read_text(encoding="utf-8") if tf.exists() else None
    d = c.by[nid]["data"]
    p = beatedit.params_of({"preset": d.get("preset"), "params": d.get("params") or {}})
    an = song.analysis(sid)
    drop = graph.beat_drop(d, sid)
    try:
        g = beatedit.make_grid(an.beats, drop, float(d["bpm"]) if d.get("bpm") not in (None, "") else None, p["build_bars"], p["drop_bars"])
    except ValueError:   # fewer than 8 beats: no grid, the view still renders (the caption table shows every word)
        return words, written, sid, None
    return words, written, sid, {"t0": g.t0, "dur": g.dur, "drop": drop}


def beat_view(pid: str, nid: str, cleaned: Optional[dict] = None) -> dict:
    proj = _project(pid)
    g = graph.load(pid)
    n = _node(pid, nid, "beat_montage")
    c = graph.Ctx(proj, g)
    d = n["data"]
    a = graph.evaluate_node(c, nid)
    cp = graph.Ctx(proj, g)
    cp.force_preview.add(nid)
    ap = graph.evaluate_node(cp, nid)
    preset = d.get("preset") if d.get("preset") in beatedit.PRESETS else "techno"
    over = {k: v for k, v in (d.get("params") or {}).items() if k in beatedit.TECHNO} if isinstance(d.get("params"), dict) else {}
    eff = beatedit.params_of({"preset": preset, "params": over})
    words, written, sid, grid = _beat_words(c, nid)
    edits = [e for e in d.get("caption_edits") or [] if isinstance(e, dict) and "i" in e]
    table = []
    if words:
        full = beatedit.words_of({"words": words, "written": written, "caption_edits": edits})
        by_edit = {int(e["i"]): e for e in edits}
        for i, w in enumerate(full):
            if grid and not (grid["t0"] - 0.5 <= float(w["start"]) <= grid["t0"] + grid["dur"]):
                continue
            table.append({"i": i, "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3), "word": w["word"], "hidden": bool(w.get("hide")),
                          "edited": i in by_edit})
    clips = c.inputs(nid, "clips")
    ready = bool(clips) and all(graph.evaluate_node(c, s).state == "ready" for s, _ in clips)
    pal = a.beat["palette"] if a.beat and a.beat.get("palette") else (d.get("palette") if isinstance(d.get("palette"), dict) else {})
    if not pal:
        from .planner import beat as beat_planner
        pal = beat_planner.palette_of("night_neon")
    err = a.error
    if not err and words is not None and sid and grid is None:
        err = i18n.L("в песне слишком мало долей для бита (меньше 8)", "the song has too few beats (fewer than 8)")
    return {"node": nid, "state": a.state, "error": err, "preset": preset,
            "presets": [{"id": k, "ru": v[0], "en": v[1]} for k, v in beatedit.PRESET_NAMES.items()],
            "params": {s["key"]: eff[s["key"]] for s in beatedit.PARAM_SPEC if s["key"] in eff} | {"captions": bool(eff.get("captions", True))},
            "overrides": over, "spec": [{**s, "ru": s["ru"], "en": s["en"]} for s in beatedit.PARAM_SPEC],
            "palette": pal, "title": a.beat["title"] if a.beat else (d.get("clip_title") or ""), "hud": d.get("hud") or "", "fps": 30 if int(d.get("fps") or 60) == 30 else 60,
            "loudness": float(d["loudness"]) if d.get("loudness") not in (None, "") else beatedit.DEFAULTS["loudness"],
            "captions": {"on": bool(eff.get("captions", True)), "words": table},
            "drop": round(grid["drop"], 3) if grid else None, "bpm": float(d["bpm"]) if d.get("bpm") not in (None, "") else None,
            "file": _rel(c, a.path) if a.state == "ready" else None, "preview": _rel(cp, ap.path) if ap.path and ap.state == "ready" else None,
            "scenes_ready": ready, "warn": a.warn, "cleaned": cleaned or {"title": False, "hud": False}}


class BeatBody(BaseModel):
    preset: Optional[str] = None
    params: Optional[dict] = None
    palette: Optional[dict] = None
    title: Optional[str] = Field(None, max_length=120)
    hud: Optional[str] = Field(None, max_length=120)
    fps: Optional[int] = None
    loudness: Optional[float] = None
    caption_edits: Optional[list[dict]] = None
    drop: Optional[float] = None
    bpm: Optional[float] = None


def _pin_drop(pid: str, nid: str) -> Optional[dict]:
    """The song's own drop as it is now ({drop, sig} for data.drop_auto), None when the montage has no song."""
    from . import autopilot
    try:
        c = _ctx(pid)
        tra = c.inputs(nid, "track")
        sa = graph.evaluate_node(c, tra[0][0]) if tra else None
        if not sa or not sa.song:
            return None
        return {"drop": round(autopilot.drop_at(sa.song), 4), "sig": graph.song_sig(sa.song)}
    except (EngineError, OSError, ValueError, TypeError):
        return None


@router.get("/api/projects/{pid}/nodes/{nid}/beat")
def get_beat(pid: str, nid: str):
    return beat_view(pid, nid)


@router.put("/api/projects/{pid}/nodes/{nid}/beat")
def put_beat(pid: str, nid: str, body: BeatBody):
    """The panel's values into the node: the render's parameters only (the scenes stay in the cache); the title and the HUD
    through looks.clean_text; numbers clamped to the spec."""
    _project(pid)
    _node(pid, nid, "beat_montage")
    put: dict = {}
    cleaned = {"title": False, "hud": False}
    if body.preset is not None:
        if body.preset not in beatedit.PRESETS:
            raise HTTPException(400, i18n.L(f"Нет такого пресета: {body.preset}", f"No such preset: {body.preset}"))
        put["preset"] = body.preset
    if body.params is not None:
        spec = {s["key"]: s for s in beatedit.PARAM_SPEC} | {"captions": {"kind": "bool"}}
        over = {}
        for k, v in body.params.items():
            s = spec.get(k)
            if not s:
                continue
            if s["kind"] == "bool":
                over[k] = bool(v)
            else:
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    continue
                x = min(float(s["max"]), max(float(s["min"]), x))
                over[k] = int(round(x)) if s["kind"] == "int" else x
        put["params"] = over
    if body.palette is not None:
        try:
            put["palette"] = {k: [max(0, min(255, int(x))) for x in body.palette[k][:3]] for k in ("a", "b", "tint")}
            put["palette_user"] = True   # the pool's expand keeps a palette the user set
            put["palette_from_pool"] = False
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(400, i18n.L("Палитра: три цвета a, b, tint (B, G, R)", "Palette: three colours a, b, tint (B, G, R)")) from e
    for k in ("title", "hud"):
        v = getattr(body, k)
        if v is not None:
            clean = looks.clean_text(v.strip())
            cleaned[k] = clean != v.strip()
            put["clip_title" if k == "title" else k] = clean   # data.title is the card's name
    if body.fps is not None:
        put["fps"] = 30 if body.fps == 30 else 60
    if body.loudness is not None:
        put["loudness"] = max(-24.0, min(-4.0, body.loudness))
    if body.caption_edits is not None:
        put["caption_edits"] = [{k: e[k] for k in ("i", "word", "start", "end", "hide") if k in e} for e in body.caption_edits if "i" in e][:2000]
    if body.drop is not None:
        put["drop"] = body.drop or None   # empty / 0 = auto: the song's drop is worked out again now and pinned (graph.beat_drop)
        if not body.drop:
            if (pin := _pin_drop(pid, nid)):
                put["drop_auto"] = pin
    if body.bpm is not None:
        put["bpm"] = body.bpm or None
    saved = _set(pid, nid, **put)
    return {**beat_view(pid, nid, cleaned), "graph_rev": saved["rev"], "node_data": saved["data"]}


@router.post("/api/projects/{pid}/nodes/{nid}/beat/preview")
def post_beat_preview(pid: str, nid: str):
    """«Предпросмотр»: the montage at 540x960 (the scenes must be shot): one queue job."""
    _project(pid)
    _node(pid, nid, "beat_montage")
    if graph_api._busy(pid):
        raise HTTPException(409, i18n.L("С этим проектом уже работает задача", "A job is already working on this project"))
    if not beat_view(pid, nid)["scenes_ready"]:
        raise HTTPException(400, i18n.L("Сначала снимите сцены пула", "Shoot the pool's scenes first"))
    return jobs.submit_task("graph", {"project": pid, "name": "preview", "node": nid}, lambda job: preview(job, pid, nid),
                            estimate=graph.BEAT_RENDER_S * 24 * 0.3).public()


async def preview(job, pid: str, nid: str) -> dict:
    c = _ctx(pid)
    c.force_preview.add(nid)
    a = graph.evaluate_node(c, nid)
    if a.state == "todo":
        job.progress["nodes"] = {nid: {"status": "running", "type": "beat_montage"}}
        graph._pin_beat_drop(c, nid, a)
        await graph._make_beat(job, nid, a)
    elif a.state != "ready":
        raise EngineError(a.error or i18n.L("сцены ещё не сняты", "the scenes are not shot yet"))
    return {"file": str(a.path)}


# ---------- the output's publication panel ----------
def publish_view(pid: str, nid: str, removed: bool = False) -> dict:
    proj = _project(pid)
    n = _node(pid, nid, "output")
    c = graph.Ctx(proj, graph.load(pid))
    d = n["data"]
    a = graph.evaluate_node(c, nid)
    v = c.inputs(nid, "video")
    src = graph.evaluate_node(c, v[0][0]) if v else None
    ph = a.extra.get("phone")
    return {"phone": bool(d.get("phone")), "cover": bool(d.get("cover")), "state": a.state,
            "file": _rel(c, a.path) if a.state in ("ready", "todo") else None, "phone_file": _rel(c, ph),
            "phone_mb": round(ph.stat().st_size / 1000 / 1000, 2) if ph and ph.exists() else None, "cover_file": _rel(c, a.extra.get("cover")),
            "cover_at": a.extra.get("cover_at") if a.extra else (graph.cover_time(d, src) if src and src.path else None),
            "duration": round(a.seconds or 0, 2), "drop": graph.cover_time({}, src) if src and src.path else None,
            "text": d.get("publish") or "", "removed": removed}


class PublishBody(BaseModel):
    phone: Optional[bool] = None
    cover: Optional[bool] = None
    cover_at: Optional[float] = Field(None, ge=0)
    text: Optional[str] = Field(None, max_length=2000)


@router.get("/api/projects/{pid}/nodes/{nid}/publish")
def get_publish(pid: str, nid: str):
    return publish_view(pid, nid)


@router.put("/api/projects/{pid}/nodes/{nid}/publish")
def put_publish(pid: str, nid: str, body: PublishBody):
    """The output's phone-copy and cover switches, the cover's second (the frame is made at once from the video when it is
    there) and the publication text (title + hashtags) through looks.clean_text."""
    _project(pid)
    _node(pid, nid, "output")
    put: dict = {}
    removed = False
    if body.phone is not None:
        put["phone"] = body.phone
    if body.cover is not None:
        put["cover"] = body.cover
    if body.cover_at is not None:
        put["cover_at"] = round(body.cover_at, 2)
    if body.text is not None:
        clean = looks.clean_text(body.text.strip())
        removed = clean != body.text.strip()
        put["publish"] = clean
    saved = _set(pid, nid, **put)
    if body.cover_at is not None:
        c = _ctx(pid)
        a = graph.evaluate_node(c, nid)
        if (p := a.extra.get("cover")) and a.path and a.path.exists() and not p.exists():
            try:
                post.cover_frame(a.path, p, a.extra["cover_at"])
            except EngineError as e:
                raise HTTPException(400, str(e)) from e
    return {**publish_view(pid, nid, removed), "graph_rev": saved["rev"], "node_data": saved["data"]}
