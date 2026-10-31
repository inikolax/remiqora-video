"""A project's storyboard -> the video: the scenes shot as a chain, cached, assembled with sound, upscaled by RTX.

Chain: a "new" scene is text-to-video; a "continue" scene is image-to-video from the previous scene's last frame -
the PNG the graph saves straight from the decoder (no mp4 round trip).
Cache: every shot is projects/<id>/scenes/<key>.mp4 (+ .png, its last frame), the key a hash of everything that makes
it: the prompt, seed, size, length, the model, the LoRA and the start frame. Edit scene k and only k changes key - and
the continuations after it, because their start frame (k's last frame) is new. A second run without edits takes all
from the cache.
Assembly (ffmpeg, as in make_h3_long.py): a continuation's first frame repeats the previous last one, so it is cut;
the sound joins with a 0.15 s crossfade, then `apad` + `-shortest` so the crossfades don't cut the tail.
Music (music.py): the user's own track over the assembled video, before the upscale.
Upscale: NVIDIA RTX Video Super Resolution (rtx_vsr.exe: raw RGBA frames on stdin -> stdout) to 1080p.
Phase 10: the project's video model (videomodels.py, settings.video_model) - H3, WAN 2.2 5B, LTX 2.5, LTX 2.3. Its card
gives the size, the frames, the timing; its graph shoots; the prompt is rewritten for it (videomodels.adapt) and that is
what the key hashes. A model without sound gets a silent track, so the assembly and the montage need no other way. LTX
2.3 with «Снимать под трек» (settings.track_sync) makes every scene to its own piece of the project's track: the piece
that plays where the scene stands in the video; the video's sound is then the track itself.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from . import checks, config, i18n, jobs, music, post, projects, timings, videomodels
from . import loras as lora_lib
from .engine import graphs
from .engine.comfy import EngineError
from .planner import model_prompts, prompts

EDGE = 0.03   # the sound's fade at a join of the graph's «Склейка», against clicks (edit.EDGE)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def size(settings: dict, c: Optional[videomodels.Card] = None) -> tuple[int, int]:
    """The frame of the video (the project's model), or of a scene shot with another model `c`."""
    c = c or videomodels.of(settings)
    return videomodels.own_size(settings, c) or videomodels.size(c, graphs.ASPECTS[settings.get("aspect", "16:9")], settings.get("quality", "draft"))


PICTURE_MP = 0.85   # a picture is never smaller than this (megapixels of 1024 * 1024): an own frame set small by hand


def picture_size(settings: dict, c: Optional[videomodels.Card] = None) -> tuple[int, int]:
    """The size a picture is drawn at - a scene's start frame, the hero's portrait, a place: the final frame of the
    project's model (or of the scene's, `c`) whatever the quality, as the graph's «Картинка» (2e75e55). At the draft's
    960×544 the face of a medium shot was a few dozen pixels and the final scene started from a picture blown up 1.4
    times; fit_frame brings it to any scene's frame. An own frame under PICTURE_MP keeps its
    shape, drawn bigger."""
    w, h = size({**settings, "quality": "final"}, c)
    if w * h >= PICTURE_MP * 1024 * 1024:
        return w, h
    return videomodels.canvas(w / h, PICTURE_MP, 64)


def scene_length(settings: dict, seconds: float = 5, c: Optional[videomodels.Card] = None) -> int:
    """A storyboard scene's frames for the project's model or `c` (5 s: H3 124, LTX / WAN 121)."""
    return videomodels.frames(c or videomodels.of(settings), seconds)


def one_scene(settings: dict, quality: str, w: int, h: int, length: int, ref: bool = False,
              c: Optional[videomodels.Card] = None) -> float:
    """Seconds of one warm scene of the project's model (or `c`) at this size (measured here, or the card's guess)."""
    c = c or videomodels.of(settings)
    if c.id == "h3":
        return timings.scene_seconds(quality + ("_ref" if ref else ""), w, h, length)
    cw, ch = videomodels.size(c, 16 / 9, quality)
    base = c.base.get(quality, c.base["draft"]) * (w * h) / (cw * ch) * length / videomodels.frames(c, 5)
    return timings.scene_seconds(videomodels.timing_key(c, quality), w, h, length, base)


# ---------- a scene's own model and length (phase 11) ----------
def scene_card(plan: dict, settings: dict, s: dict) -> videomodels.Card:
    """The model a scene is shot with: its chain's - the `model` of the new scene that opened it - else the video's.
    A continuation goes on in its chain's model: its start frame is that model's picture."""
    head = prompts.opener_of(plan, s) or s
    return videomodels.card(head.get("model") or settings.get("video_model"))


def scene_seconds(s: dict) -> float:
    """A scene's length in the video: its own (`seconds`: a clip's scene cut on the bars, a 10 s grid's) or 5 s."""
    try:
        return max(0.5, float(s.get("seconds") or 5))
    except (TypeError, ValueError):
        return 5.0


def preroll(plan: dict, s: dict, length: Optional[int] = None) -> int:
    """The frames a clip's scene from a picture is shot before its bar (clip.preroll, a clip made since 2026-10-30;
    planner/clip.PREROLL): i2v's first frames are the still picture, the montage starts the scene after them and its
    piece of the track starts that much earlier. Never before the song's start; 0 for anything else. `length`: the
    shot's frames (scene_spec) - a shot the model's limit kept shorter than its bar and the preroll (WAN 5B's 5 s under
    a 5 s scene) has only what is left before the bar, so the scene still ends on it and nothing after it slips; a shot
    long enough keeps the whole preroll (scene_spec's length is made with it)."""
    n = (plan.get("clip") or {}).get("preroll")
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0 or not prompts.starts_from_photo(s):
        return 0
    n = max(0, min(n, int((float(plan["clip"].get("from") or 0) + float(s.get("start") or 0)) * graphs.FPS + 1e-6)))
    if length is not None:
        bar = round(float(s.get("end") or 0) * graphs.FPS) - round(float(s.get("start") or 0) * graphs.FPS)
        n = max(0, min(n, length - bar))
    return n


def scene_spec(plan: dict, settings: dict, s: dict) -> tuple[videomodels.Card, int, int, int]:
    """(model, width, height, frames) of a scene's shot. A clip's scene is shot up to its model's frame grid and cut
    on the bar in the montage (a scene from a picture with its preroll before it). An imported shot (its chain on an
    imported model) keeps the frames it was made with (`frames`: Remiqora shot a little longer than our grid, and the
    montage places a continuation after the whole shot)."""
    c = scene_card(plan, settings, s)
    w, h = size(settings, c)
    if c.shoots_as and str(s.get("frames") or "").isdigit():
        return c, w, h, int(s["frames"])
    return c, w, h, scene_length(settings, scene_seconds(s) + preroll(plan, s) / graphs.FPS, c)


def sync_track(proj: dict) -> Optional[dict]:
    """The track the scenes are shot to («Снимать под трек» on, the track's file there), else None. Only a scene whose
    model can (LTX 2.3) takes it - see scene_track."""
    st = proj.get("settings") or {}
    tr = st.get("track")
    if not (st.get("track_sync") and tr):
        return None
    if not (videomodels.of(st).track or any(videomodels.card(s.get("model")).track for s in (proj.get("plan") or {}).get("scenes") or [])):
        return None
    return tr if (projects.folder(proj["id"]) / tr["file"]).exists() else None


def track_starts(plan: dict, lengths: list[int], offset: float) -> list[float]:
    """Where each scene's piece of the track begins: the scene's place in the video. A clip (plan.clip) cuts every scene
    on its bar, so its place is its `start`; a storyboard plays the shots whole (a continuation's first frame is cut -
    it repeats the last one before it)."""
    scenes = plan.get("scenes") or []
    if plan.get("clip"):
        # on its bar, to the song's own time (not the frame: a key made that way stays); a continuation where it plays
        places = clip_places(plan, lengths)
        return [round(offset + (places[k] / graphs.FPS if places[k] != round(float(s.get("start") or 0) * graphs.FPS)
                                else float(s.get("start") or 0)), 4) for k, s in enumerate(scenes)]
    out, t = [], 0
    for k, s in enumerate(scenes):
        cut = 1 if s.get("kind") == "continue" and k else 0
        out.append(round(offset + (t - cut) / graphs.FPS, 4) if t else round(offset, 4))
        t += lengths[k] - cut
    return out


def clip_places(plan: dict, lengths: list[int]) -> list[int]:
    """Where a clip's scenes' shots begin in the video, in frames: on their bars - but a continuation of the scene just
    before it goes on from that whole shot (its first frame cut), wherever its bar is: the shot it starts from is
    played to its last frame. The montage (edit.resolve) places it the same, its track piece starts there, and it
    ends on its own bar, so nothing after it slips. A scene with a preroll begins that many frames before its bar."""
    scenes, out = plan.get("scenes") or [], []
    for k, s in enumerate(scenes):
        if k and s.get("kind") == "continue" and prompts.from_of(plan, s) is scenes[k - 1]:
            out.append(out[k - 1] + lengths[k - 1] - 1)
        else:
            out.append(round(float(s.get("start") or 0) * graphs.FPS) - preroll(plan, s, lengths[k]))
    return out


NO_VOICE_SHOTS = ("perform", "insert")   # a clip's scenes where nobody sings: shot to the song without its voice


def scene_track(proj: dict, c: videomodels.Card, plan: Optional[dict] = None, s: Optional[dict] = None) -> Optional[Path]:
    """The track file a scene of model `c` is shot to, or None. With the scene (`plan`, `s`): a clip's performance or
    insert gets the song without its voice (song.no_vocals) - the model makes every face sing
    what it hears, and these faces must not; a shot made to the whole song before stays (preview's `tracks`)."""
    sync = sync_track(proj)
    if not (sync and c.track):
        return None
    if plan is not None and s is not None and plan.get("clip") and s.get("shot") in NO_VOICE_SHOTS and plan["clip"].get("song"):
        from . import song
        if (nv := song.no_vocals(plan["clip"]["song"])):
            return nv
    return projects.folder(proj["id"]) / sync["file"]


_sha_memo: dict[tuple, str] = {}


def file_sha(p: Path) -> str:
    """sha1 of a file's bytes, remembered while its size and time stay (the graph's state asks for 120 start frames
    on every save)."""
    st = p.stat()
    k = (str(p), st.st_size, st.st_mtime_ns)
    if k not in _sha_memo:
        if len(_sha_memo) > 4000:
            _sha_memo.clear()
        _sha_memo[k] = hashlib.sha1(p.read_bytes()).hexdigest()
    return _sha_memo[k]


def ref_extra(ref: Optional[dict]) -> Optional[list]:
    """What a scene's reference LoRA (graph: ID-LoRA, its voice) adds to its key: the LoRA, its strength, the voice's
    bytes and piece, how strongly it is held."""
    if not ref:
        return None
    i = lora_lib.get(ref["lora"]["id"])
    return ["id-lora", ref["lora"]["id"], i.size_mb if i else None, round(float(ref["lora"]["strength"]), 3), file_sha(ref["voice"]),
            round(float(ref["from"]), 3), round(float(ref["secs"]), 3), round(float(ref["identity"]), 3)]


def scene_key(prompt: str, seed: int, w: int, h: int, length: int, loras: list[dict], start: Optional[Path],
              refs: list[Path] = (), model: str = "h3", track: Optional[Path] = None, track_start: float = 0.0,
              ref: Optional[dict] = None, end: Optional[Path] = None, legacy: bool = False,
              fit: Optional[tuple[int, int, int, int]] = None) -> str:
    """The cache key of a shot. H3's keys are what they were before phase 10; another model hashes its own weights and
    recipe and the prompt it really gets (videomodels.adapt), LTX 2.3 to a track - the track's bytes and where its
    piece begins, with a reference LoRA (ID-LoRA) - ref_extra, with an end frame (flf2v) - its bytes; without them
    the key is what it was. `fit` (start_crop): the start photo cut to another rectangle than the centre one - the
    shot is another, so its key is another (a photo the centre already frames keeps its key)."""
    c = videomodels.card(model)
    fit = list(fit) if fit else None
    if c.id != "h3":   # its own LoRA only (loras.py); none - the key as it was before LTX had LoRA
        own = sorted((x["id"], round(float(x["strength"]), 3)) for x in lora_lib.for_model(loras, videomodels.shooter(c).id))
        parts = [videomodels.adapt(c, prompt, legacy), seed, w, h, length, c.id, c.recipe, *(getattr(config, k) for k in c.keys),
                 own, file_sha(start) if start else None]
        if fit:
            parts += ["fit", *fit]
        if track:
            parts += ["track", file_sha(track), round(track_start, 3)]
        if ref:
            parts += ref_extra(ref)
        if end and c.ends:
            parts += ["end", file_sha(end)]
        return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:16]
    parts = [prompt, seed, w, h, length, config.H3_UNET, config.H3_CLIP, config.H3_VAE, graphs.STEPS, graphs.SAMPLER,
             sorted((x["id"], round(float(x["strength"]), 3)) for x in lora_lib.for_model(loras, "h3")),
             file_sha(start) if start else None]
    if fit:
        parts += ["fit", *fit]
    if not refs and (turbo := graphs.h3_turbo_lora()):   # the official model's speed-up: its shots are not a TURBO fine-tune's (whose keys stay)
        parts += ["turbo", turbo]
    if refs:   # Ref2VA: other weights, the turbo LoRA, its steps and the photos themselves (keys of other shots stay as they were)
        parts += ["ref2va", config.H3_REF_UNET, config.H3_REF_LORA, graphs.REF_STEPS, *(file_sha(r) for r in refs)]
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:16]


def estimate(settings: dict, scenes: list[dict]) -> float:
    """The whole storyboard shot anew, each scene at its own length (a 10 s grid's take twice a 5 s one's frames)."""
    w, h = size(settings)
    return sum(one_scene(settings, settings.get("quality", "draft"), w, h, scene_length(settings, scene_seconds(s))) for s in scenes)


def lips_of(plan: dict, s: dict, mp4: Path, length: Optional[int] = None) -> Optional[float]:
    """A clip's singing scene: how much the lips move where the song's voice is (checks.py), None when not judged.
    `length`: the shot's frames (its preroll cut to fit the model's limit - preroll)."""
    clip = plan.get("clip") or {}
    if not clip.get("song"):
        return None
    from . import song
    try:
        pre = preroll(plan, s, length)   # the shot starts that many frames before its bar
        n = round(scene_seconds(s) * graphs.FPS) + pre
        start = float(clip.get("from") or 0) + float(s.get("start") or 0) - pre / graphs.FPS
        voice = checks.voice_frames(song.vocals(clip["song"]), song.lines(clip["song"]), start, n, graphs.FPS,
                                    (float(clip.get("from") or 0), float(clip.get("to") or start + n / graphs.FPS)))
    except EngineError:
        return None
    return checks.lip_motion(mp4, n, voice, graphs.FPS) if voice else None


def shoot_order(plan: dict, cards: list[videomodels.Card], first: str = "h3") -> list[int]:
    """The order to shoot a storyboard of several models in: a model at a time (each loads once - LTX 2.3 is a 25 GB
    read), the one in memory first, then in the storyboard's order; a continuation only after the scene it starts
    from. Scenes of one model are the plain storyboard order."""
    scenes = plan.get("scenes") or []
    models = [first] if any(c.id == first for c in cards) else []
    models += [c.id for c in cards if c.id not in models]
    models = list(dict.fromkeys(models))
    done: set[int] = set()
    order: list[int] = []
    while len(order) < len(scenes):
        moved = False
        for m in models:
            for s in scenes:
                i = s["index"]
                if i in done or cards[i].id != m:
                    continue
                src = prompts.from_of(plan, s)
                if src is not None and src["index"] not in done:
                    continue
                done.add(i)
                order.append(i)
                moved = True
        if not moved:   # a loop of `from` (renumber forbids it): what is left in the storyboard's order
            order += [s["index"] for s in scenes if s["index"] not in done]
            break
    return order


def ref_photos(proj: dict, plan: dict, s: dict) -> list[Path]:
    """Ref2VA for this scene: a new scene of a people video whose plan says `ref_photo` - the photos of the people in it,
    in the order of prompts.photo_people (<Picture 1>, <Picture 2>...). A character's own photo, or the project's photo
    for the hero described from it. Only H3 holds faces from photos: another model gets none."""
    if not prompts.uses_refs(plan, s) or not scene_card(plan, proj.get("settings") or {}, s).refs:
        return []
    cast, folder, out = plan.get("cast") or [], projects.folder(proj["id"]), []
    for i in prompts.photo_people(plan, s):
        path = folder / cast[i]["photo"] if cast[i].get("photo") else projects.photo_path(proj)
        if path and path.exists():
            out.append(path)
    return out


def hero_photo(proj: dict, plan: dict, s: dict) -> Optional[Path]:
    """The portrait the shot's face is checked against (checks `hero`): the photo of the one person of the scene who
    has one, when someone is in it and the face comes from a picture - its chain starts from a frame or a photo, or
    Ref2VA holds it (a scene from words alone draws a face of its own: another seed would not bring hers). None with
    nobody, with several people or without a photo."""
    if plan.get("mode") == "none" or prompts.nobody(plan, s) or not prompts.has_people(s, plan):
        return None
    head = prompts.opener_of(plan, s) or s
    if not (prompts.starts_from_photo(head) or prompts.uses_refs(plan, head) or prompts.uses_refs(plan, s)):
        return None
    people = [i for i, _ in prompts.scene_cast(plan, s)]
    who = prompts.photo_people(plan, s)
    if len(people) != 1 or len(who) != 1:
        return None
    c = (plan.get("cast") or [])[who[0]]
    path = projects.folder(proj["id"]) / c["photo"] if c.get("photo") else projects.photo_path(proj)
    return path if path and path.exists() else None


def still_retake(plan: dict, s: dict) -> bool:
    """Formula 3: a clip's singing scene found `still` is shot once more (render.run) - handheld when it can be."""
    return prompts.formula(plan) >= 3 and bool(plan.get("clip")) and s.get("shot") == "sing" and not prompts.is_raw(s)


def unlike_frame(s: dict) -> Optional[dict]:
    """A new scene starting from a drawn frame whose face missed the hero's (frames.draw_one: frame.ok false) - the
    shot takes that face: a note for the board («кадр не похож на героя»), as the checks of a shot are."""
    f = s.get("frame") or {}
    if s.get("kind") != "new" or f.get("ok") is not False or not (s.get("start_photo") or "").startswith("frame_"):
        return None
    return {"code": "frame", "at": 0.0, "length": 0.0, "value": float(f.get("face") or 0), "name": checks.name("frame"), "severe": False,
            "line": config.FRAME_FACE_MIN}


_id_lora: dict = {}


def id_lora() -> Optional[lora_lib.LoraInfo]:
    """The LoRA that takes a voice by sample (ID-LoRA, LTX 2.3) in the LoRA folders, looked up once in 30 s."""
    if time.time() - _id_lora.get("t", 0) > 30:
        from . import v2v
        found = [i for i in lora_lib.LIBRARIES["ltx23"].scan() if i.v2v and v2v.profile(i)["reads"] == "voice"]
        _id_lora.update(t=time.time(), info=found[0] if found else None)
    return _id_lora["info"]


def voice_ref(proj: dict, plan: dict, s: dict, c: videomodels.Card, tpath: Optional[Path]) -> Optional[dict]:
    """A hero's voice by sample for a storyboard scene (ID-LoRA, as the graph's voice scene): the scene is shot by
    LTX 2.3 (not to a track), all its lines are one character's and that character has a voice sample (cast[i].voice:
    a file in the project, `from`, `secs`), and an ID-LoRA is in the LoRA folders. None: the scene is shot as before
    (its key too)."""
    if c.id != "ltx23" or tpath:
        return None
    who = {ln["who"] for ln in prompts.lines_of(plan, s)}
    cast = plan.get("cast") or []
    if len(who) != 1 or not 1 <= (n := who.pop()) <= len(cast):
        return None
    v = cast[n - 1].get("voice") or {}
    f = projects.folder(proj["id"]) / v["file"] if v.get("file") else None
    info = id_lora() if f and f.exists() else None
    if not info:
        return None
    from . import v2v
    prof = v2v.profile(info)
    return {"lora": {"id": info.id, "strength": 1.0}, "voice": f, "from": max(0.0, float(v.get("from") or 0)),
            "secs": float(v.get("secs") or prof["voice_secs"]), "identity": prof["identity"]}


def start_frame(proj: dict, s: dict, prev_png: Optional[Path]) -> Optional[Path]:
    """What a scene starts from: a continuation - the last frame of the scene it goes on from (`prev_png`: the one
    just before it, or its `from`); a new scene with a start photo - that photo; otherwise nothing (text only)."""
    if s["kind"] == "continue":
        return prev_png
    if prompts.starts_from_photo(s):
        path = projects.folder(proj["id"]) / s["start_photo"]
        return path if path.exists() else None
    return None


def facefix_of(s: dict) -> Optional[dict]:
    """«Починить лица» on a scene ({mode, strength}, planner.check keeps it sane), or None."""
    ff = s.get("facefix")
    return ff if isinstance(ff, dict) else None


def facefix_text(plan: dict, s: dict) -> str:
    """Who is in the scene, for facefix.py's prompt: the looks of its people (the models then draw them, not someone)."""
    if plan.get("mode") == "none":
        return ""
    return "; ".join(x.get("en", "") for _, x in prompts.scene_cast(plan, s) if x.get("en"))


def fixed_key(plan: dict, s: dict, key: str) -> str:
    """The key of a shot with its faces fixed: the shot's key + the fix's signature (scenes/<key>.ff<sig>.mp4 next to
    the shot; the shot itself stays - a continuation starts from its own last frame, and the fix can be turned off)."""
    from . import facefix
    ff = facefix_of(s) or {}
    return f"{key}.ff{facefix.signature(ff.get('mode', 'far'), float(ff.get('strength', 1.0)), facefix_text(plan, s))}"


def end_frame(proj: dict, s: dict) -> Optional[Path]:
    """The picture a scene comes to (`end_photo`, a file in the project; flf2v - LTX only, render.shoot_scene)."""
    path = projects.folder(proj["id"]) / s["end_photo"] if s.get("end_photo") else None
    return path if path and path.exists() else None


def video_size(p: Path) -> Optional[tuple[int, int]]:
    """(width, height) of a picture or a video's first stream; None when ffprobe can't read it."""
    r = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                        str(p)], capture_output=True, text=True, creationflags=NO_WINDOW)
    try:
        w, h = r.stdout.strip().splitlines()[0].split(",")[:2]
        return int(w), int(h)
    except (ValueError, IndexError):
        return None


def fit_frame(src: Path, dest: Path, w: int, h: int, crop: Optional[tuple[int, int, int, int]] = None) -> None:
    """A start photo cropped to the video's proportions around the centre and scaled to its size, so H3 gets exactly
    the frame it will continue (a phone photo is 3:4, the video 16:9). `crop` (start_crop): the rectangle the photo is
    cut to instead - a photo with a face is framed on it."""
    if crop:
        x, y, cw, ch = crop
        _ffmpeg(["-i", str(src), "-vf", f"crop={cw}:{ch}:{x}:{y},scale={w}:{h}:flags=lanczos", "-frames:v", "1", str(dest)])
        return
    _ffmpeg(["-i", str(src), "-vf", f"crop='min(iw,ih*{w}/{h})':'min(ih,iw*{h}/{w})',scale={w}:{h}:flags=lanczos",
             "-frames:v", "1", str(dest)])


# A photo that starts a scene is cut to the video's frame about its centre - and a phone portrait (3:4) loses its head
# altogether: the middle band of a full-length shot is a torso. ID-LoRA reads the face from that very frame, so the
# scene had no face to hold (2026-10-26, the user: «ID lora не видит лица» - a man's photo, a woman in the shot). A
# photo with one confident face is framed on the face instead: the face takes FACE_SHARE of the frame's height, with
# FACE_HEADROOM above the head; a plain start photo keeps its composition and only moves off the centre when the
# centre crop would cut the face off (FACE_KEEP - how much around the face stays inside).
FACE_SHARE = 0.34
FACE_HEADROOM = 0.10
FACE_KEEP = 1.40
FACE_SMALL = 0.09   # a face smaller than this part of the photo's height isn't framed close: a 40 px face blown up to
                    # the frame is mush (a person far away in a landscape is shot as the photo is)


def _fit_rect(iw: int, ih: int, w: int, h: int, box: tuple[int, int, int, int], tight: bool) -> Optional[tuple[int, int, int, int]]:
    """The rectangle of an iw x ih photo to cut to a w x h frame, or None for the plain centre crop (the face is
    already framed, or it can't be framed): the face (`box`) framed (`tight`), else the centre moved the least that
    keeps the face whole."""
    fx, fy, fw, fh = box
    clamp = lambda v, lo, hi: max(lo, min(hi, v))  # noqa: E731
    if iw * h > ih * w:   # wider than the frame: the centre crop cuts the sides
        cxw, cxh = round(ih * w / h), ih
    else:                 # taller: it cuts the top and bottom
        cxw, cxh = iw, round(iw * h / w)
    cx0, cy0 = clamp(round((iw - cxw) / 2), 0, iw - cxw), clamp(round((ih - cxh) / 2), 0, ih - cxh)
    if tight:
        ch = max(1, round(fh / FACE_SHARE))
        cw = max(1, round(ch * w / h))
        if cw > iw:
            cw, ch = iw, max(1, round(iw * h / w))
        if ch > ih or fh < ih * FACE_SMALL:
            return None
        x0 = clamp(round(fx + fw / 2 - cw / 2), 0, iw - cw)
        if fh > ch:   # the photo is narrower than the frame: the face can't be framed whole, its middle is the best
            y0 = clamp(round(fy + fh / 2 - ch / 2), 0, ih - ch)
        else:
            y0 = clamp(round(fy - FACE_HEADROOM * ch), 0, ih - ch)
        return None if (x0, y0, cw, ch) == (cx0, cy0, cxw, cxh) else (x0, y0, cw, ch)
    gap = round((FACE_KEEP - 1) * fh / 2)   # the face and this much around it stay inside
    lo, hi = fx + fw + gap - cxw, fx - gap
    x0 = clamp(cx0, lo, hi) if lo <= hi else clamp(round(fx + fw / 2 - cxw / 2), 0, iw - cxw)
    lo, hi = fy + fh + gap - cxh, fy - gap
    y0 = clamp(cy0, lo, hi) if lo <= hi else clamp(round(fy + fh / 2 - cxh / 2), 0, ih - cxh)
    x0, y0 = clamp(x0, 0, iw - cxw), clamp(y0, 0, ih - cxh)
    return None if (x0, y0, cxw, cxh) == (cx0, cy0, cxw, cxh) else (x0, y0, cxw, cxh)


@functools.lru_cache(maxsize=64)
def _crop_of(path: str, mtime: float, w: int, h: int, tight: bool) -> Optional[tuple[int, int, int, int]]:
    """start_crop of one photo, looked for once (the face check is ~0.1 s: a preview of a graph of ten scenes takes it
    ten times); `mtime` is in the key so a replaced photo is looked for again."""
    box, size = checks.face_picture(Path(path))
    if not box or not size or size == (w, h):   # no face, or already the frame: nothing to crop
        return None
    return _fit_rect(size[0], size[1], w, h, box, tight)


def start_crop(start: Optional[Path], w: int, h: int, kind: str, tight: bool = False) -> Optional[tuple[int, int, int, int]]:
    """How a start frame goes into the shot's frame (fit_frame): None - the plain centre crop, as it always was; a
    rectangle - the photo's face asked for another one: framed on the face (`tight`: ID-LoRA takes the face from this
    frame), or the centre moved so the head isn't cut off. A continuation - a shot's last frame - is cropped as it
    always was."""
    if not start or kind == "continue" or not start.exists():
        return None
    try:
        return _crop_of(str(start), start.stat().st_mtime, w, h, tight)
    except Exception:  # noqa: BLE001 - a crop is a bonus, never a blocker
        return None


def _seed(plan: dict, s: dict) -> int:
    return int(s.get("seed") or (plan.get("seed", 1) * 100 + s["index"] + 1))


def takes_of(plan: dict, s: dict) -> list[int]:
    """A scene's takes (seeds), the chosen one (`seed`) among them; a scene never retaken has just its seed."""
    chosen = _seed(plan, s)
    seeds = [int(x) for x in s.get("takes") or [] if str(x).lstrip("-").isdigit()]
    return seeds if chosen in seeds else seeds + [chosen]


def sid(s: dict) -> str:
    """A scene's id for the walk over the storyboard (a plan written before ids: its number)."""
    return s.get("id") or f"#{s['index']}"


def loras_of(settings: dict, s: dict) -> list[dict]:
    """The LoRA a scene is shot with: its own set (`loras`, [] = none) over the video's (settings.loras)."""
    own = s.get("loras")
    return own if isinstance(own, list) else settings.get("loras") or []


def scene_inputs(proj: dict, plan: dict, s: dict, prev_png: Optional[Path]) -> tuple[Optional[Path], int, list[Path]]:
    """A storyboard scene -> what its shot is made of besides the prompt: (start frame, seed, Ref2VA photos).
    preview() and run() both take them from here, so the key preview shows is the key run shoots."""
    return start_frame(proj, s, prev_png), _seed(plan, s), ref_photos(proj, plan, s)


def shot_paths(shots_dir: Path, key: str) -> tuple[Path, Path]:
    return shots_dir / f"{key}.mp4", shots_dir / f"{key}.png"


def is_cached(shots_dir: Path, key: str) -> bool:
    return all(p.exists() for p in shot_paths(shots_dir, key))


def preview(proj: dict, quality: Optional[str] = None) -> dict:
    """What «Снять ролик» will do and how long it will take, before it starts: the walk of run() without shooting.
    A scene is cached when its shot exists; a continuation after a scene that must be shot is shot too (its start
    frame will be new). Time = the scenes to shoot at this machine's measured speed + loading the model if it is
    not in memory + assembly + RTX."""
    plan, st = proj.get("plan") or {}, dict(proj["settings"])
    if quality:
        st["quality"] = quality
    q = st.get("quality", "draft")
    w, h = size(st)
    card = videomodels.of(st)
    shots_dir = projects.folder(proj["id"]) / "scenes"
    sync = sync_track(proj)
    specs = [scene_spec(plan, st, s) for s in plan.get("scenes") or []]
    tstarts = track_starts(plan, [x[3] for x in specs], float(sync.get("offset") or 0)) if sync else []
    rows, keys, takes, tracks, secs, used = [], [], [], [], 0.0, {}
    found: dict[int, Optional[list]] = {}   # a shot scene -> what its checks found (checks.py), when it was checked
    pngs: dict[str, Optional[Path]] = {}   # a scene id -> its chosen shot's last frame, when that shot exists
    for s in plan.get("scenes") or []:
        c, sw, sh, length = specs[s["index"]]
        tpath, full = scene_track(proj, c, plan, s), scene_track(proj, c)
        state, key, mine, raw_cached = "shoot", None, [], False
        ff = facefix_of(s)
        ref = ref_photos(proj, plan, s)
        src = prompts.from_of(plan, s)
        prev_png = pngs.get(sid(src)) if src else None
        loras = loras_of(st, s)
        if prompts.is_written(s) and not (s["kind"] == "continue" and prev_png is None and s["index"] > 0):
            start, seed, ref = scene_inputs(proj, plan, s, prev_png)
            vref = voice_ref(proj, plan, s, c, tpath)
            end = end_frame(proj, s) if c.ends else None
            text = model_prompts.for_id(plan, s) if vref else model_prompts.for_model(c.id, plan, s)
            fit = start_crop(start, sw, sh, s["kind"], tight=bool(vref))   # a photo with a face: framed on it

            def keys_for(tpath: Path | None) -> list[dict]:
                """Every take of the scene shot to `tpath`: its key, whether it is shot."""
                out = []
                for t in takes_of(plan, s):
                    k = scene_key(text, t, sw, sh, length, loras, start, ref, c.id, tpath, tstarts[s["index"]] if tpath else 0.0, vref, end,
                                  fit=fit)
                    if not (vref or end) and text != s.get("prompt", "") and not is_cached(shots_dir, k):   # shot before with H3's prompt: it stays
                        k0 = scene_key(s.get("prompt", ""), t, sw, sh, length, loras, start, ref, c.id, tpath,
                                       tstarts[s["index"]] if tpath else 0.0)
                        k = k0 if is_cached(shots_dir, k0) else k
                    if not (vref or end) and c.id != "h3" and not is_cached(shots_dir, k):   # shot the night before 363212f
                        k0 = scene_key(s.get("prompt", ""), t, sw, sh, length, loras, start, ref, c.id, tpath,
                                       tstarts[s["index"]] if tpath else 0.0, legacy=True)
                        k = k0 if is_cached(shots_dir, k0) else k
                    if c.shoots_as and not is_cached(shots_dir, k):   # an imported shot changed: ours shoots it (shoot_scene's key)
                        k = scene_key(text, t, sw, sh, length, loras, start, ref, c.shoots_as, tpath,
                                      tstarts[s["index"]] if tpath else 0.0, vref, end, fit=fit)
                    raw = k
                    if ff:   # «Починить лица»: the take is its fixed shot; the shot itself stays as `raw`
                        k = fixed_key(plan, s, raw)
                    out.append({"seed": t, "key": k, "cached": is_cached(shots_dir, k),
                                **({"raw": raw, "raw_cached": is_cached(shots_dir, raw)} if ff else {})})
                return out
            mine = keys_for(tpath)
            if tpath != full:   # a take shot to the whole song before stays that shot; the chosen one decides the scene's track
                for x, y in zip(mine, keys_for(full)):
                    if not is_cached(shots_dir, x.get("raw", x["key"])) and is_cached(shots_dir, y.get("raw", y["key"])):
                        x.update(y, full=True)
                if next(x for x in mine if x["seed"] == seed).pop("full", False):
                    tpath = full
                for x in mine:
                    x.pop("full", None)
            chosen = next(x for x in mine if x["seed"] == seed)
            key, raw_cached = chosen["key"], is_cached(shots_dir, chosen.get("raw", chosen["key"]))
            if raw_cached:   # a continuation starts from the shot's own last frame, fixed or not; the checks are the shot's
                pngs[sid(s)] = shot_paths(shots_dir, chosen.get("raw", key))[1]
                seen = checks.calm(checks.saved(shot_paths(shots_dir, chosen.get("raw", key))[0]), s.get("framing"), prompts.stylized(plan))
                if seen and prompts.shots_timeline(plan, s):   # «Склейки внутри сцены»: its cuts are asked for
                    seen = [p for p in seen if p.get("code") != "cut"] or None
                found[s["index"]] = seen
            if is_cached(shots_dir, key):
                state = "cached"
        if bad := unlike_frame(s):   # its shot takes a face that is not the hero's
            found[s["index"]] = [bad, *(found.get(s["index"]) or [])]
        rows.append(state)
        keys.append(key)   # None: not known before shooting (no prompt, or the start frame is still to be shot)
        takes.append(mine)
        tracks.append(None if not tpath else "full" if tpath == full else "no_voice")
        if state == "shoot":
            if ff:
                from . import facefix
                secs += facefix.seconds(length / graphs.FPS)
            if not (ff and raw_cached):   # the shot itself is still to be made
                c = videomodels.shooter(c)
                ref_on = bool(ref) and c.refs
                secs += one_scene(st, q, sw, sh, length, ref_on, c)
                used.setdefault(c.id, [0, 0])
                used[c.id][0] += 1
                used[c.id][1] += ref_on
    n_shoot, n = rows.count("shoot"), len(rows)
    from .engine.comfy import COMFY
    for m, (k, n_ref) in used.items():   # loading each model once (the one in memory is free, as the first to shoot)
        secs += jobs.cold_extra(q, m) if len(used) == 1 or m == getattr(COMFY, "model", "h3") else \
            timings.cold_seconds(videomodels.timing_key(videomodels.card(m), q))
        if n_ref and k > n_ref:
            secs += 25 * n_ref   # H3's two 21 GB models take turns in memory: each switch reads one again
    one = one_scene(st, q, w, h, scene_length(st, plan.get("scene_seconds") or 5))
    from . import edit
    ed = edit.resolve(proj, keys, [r == "cached" for r in rows], takes)
    video = ed["duration"] or n * 5
    secs += 2 + 0.05 * video                                            # assembly
    out = post.output_of(st)
    secs += post.seconds(out, video, w, h)
    saved = (proj.get("renders") or {}).get(q) or {}
    track = st.get("track")
    remix = bool(saved.get("complete")) and n_shoot == 0 and saved.get("track_sig") != music.signature(projects.folder(proj["id"]), track)
    # the montage changed since the video was built (a video built before the montage existed = the storyboard's)
    reedit = bool(saved.get("complete")) and n_shoot == 0 and (saved.get("edit_sig") or (None if proj.get("edit") else edit.signature(ed))) != edit.signature(ed)
    remix = remix or reedit
    # the shots and the mix as they are, only the output changed (size, HDR, 48 fps): finish again
    refinish = bool(saved.get("complete")) and n_shoot == 0 and not remix and saved.get("out_tag", "1080p") != post.tag(out)
    if track:
        secs += 3
    return {"quality": q, "width": w, "height": h, "scenes": rows, "keys": keys, "takes": takes, "tracks": tracks, "to_shoot": n_shoot, "cached": n - n_shoot,
            "remix": remix, "refinish": refinish, "reedit": reedit, "duration": ed["duration"], "model": card.id, "sync": bool(sync),
            "models": [x[0].id for x in specs], "lengths": [x[3] for x in specs],
            # the scenes' ids in the order of the lists: the page finds a scene's shot by its id, not its place (a scene
            # deleted or moved gave every scene after it its neighbour's picture)
            "ids": [sid(s) for s in plan.get("scenes") or []],
            "checks": {str(k): v for k, v in found.items() if v},
            "per_scene": round(one), "seconds": round(secs), "measured": timings.samples(videomodels.timing_key(card, q))}


def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run([config.FFMPEG, "-y", "-v", "error", *args], capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode:
        raise EngineError("ffmpeg: " + (r.stderr or "").strip()[-800:])


def frame_count(mp4: Path) -> int:
    r = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames",
                        "-of", "csv=p=0", str(mp4)], capture_output=True, text=True, creationflags=NO_WINDOW)
    try:
        return int(r.stdout.strip())
    except ValueError as e:
        raise EngineError(i18n.L(f"Не прочитать число кадров: {mp4.name}", f"Cannot read the frame count: {mp4.name}")) from e


def mixed_size(paths: list[Path], w: int, h: int) -> Optional[tuple[int, int]]:
    """(w, h) when any of these clips is of another frame (the graph: a scene a reference LoRA's model shot) - the
    assembly then scales and crops them to it; None when all are (w, h): the assembly as it always was."""
    return (w, h) if any(video_size(p) not in (None, (w, h)) for p in paths) else None


def assemble(segments: list[tuple[Path, str]], dest: Path, size: Optional[tuple[int, int]] = None) -> list[int]:
    """[(mp4, kind)] -> one mp4 with sound; a continuation loses its first frame (it repeats the previous last one).
    Returns the hard cuts: the first frame of every "new" scene after the first (RIFE must not blend across them).
    `size`: the video's frame - clips of another one are scaled and cropped to it (mixed_size)."""
    n = len(segments)
    cuts, at = [], 0
    for k, (mp4, kind) in enumerate(segments):
        if k and kind == "new":
            cuts.append(at)
        at += frame_count(mp4) - (1 if kind == "continue" and k else 0)
    if n == 1 and not size:
        shutil.copyfile(segments[0][0], dest)
        return cuts
    fit = f",scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase:flags=lanczos,crop={size[0]}:{size[1]},setsar=1" if size else ""
    fps = graphs.FPS
    # the sound in whole frames with its picture and joined end to end, a short fade at each join against clicks (as
    # the montage does, edit.render): acrossfade shortened only the sound - 0.15 s ahead of the picture a join
    parts = []
    for k, (mp4, kind) in enumerate(segments):
        a = 1 if kind == "continue" and k else 0
        b = frame_count(mp4)
        fin = f",afade=t=in:st=0:d={EDGE}" if k else ""
        fout = f",afade=t=out:st={(b - a) / fps - EDGE:.6f}:d={EDGE}" if k < n - 1 else ""
        parts.append(f"[{k}:v]trim=start={max(0.0, (a - 0.5) / fps):.6f},setpts=PTS-STARTPTS{fit}[v{k}];"
                     f"[{k}:a]atrim=start={a / fps:.6f}:end={b / fps:.6f},asetpts=PTS-STARTPTS,aresample=48000,"
                     f"aformat=channel_layouts=stereo,apad,atrim=0:{(b - a) / fps:.6f}{fin}{fout}[a{k}]")
    vcat = "".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[vc]"
    chain = ["".join(f"[a{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1[aout]"]
    if n == 1:   # one clip of another frame: its sound as it is
        parts, vcat, chain = [parts[0]], "[v0]null[vc]", ["[a0]anull[aout]"]
    args = []
    for mp4, _ in segments:
        args += ["-i", str(mp4)]
    _ffmpeg(args + ["-filter_complex", ";".join(parts + [vcat] + chain), "-map", "[vc]", "-map", "[aout]", "-shortest",
                    "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest)])
    return cuts


def add_silence(mp4: Path) -> None:
    """A shot without a sound track (WAN) gets a silent one, so the assembly and the montage treat it like any other."""
    r = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(mp4)],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.stdout.strip():
        return
    tmp = mp4.with_name(mp4.stem + "_s.mp4")
    _ffmpeg(["-i", str(mp4), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(tmp)])
    tmp.replace(mp4)


def scene_graph_preview(proj: dict, index: int, quality: Optional[str] = None) -> dict:
    """«Граф для ComfyUI»: the graph a new shot of scene `index` would send to the worker, built
    as shoot_scene builds it, without shooting and without copying a file - the input files named as the shot names
    them, the LoRA by their file names (the worker's own names can carry a folder). For a recipe's debugging.
    -> {model, key, cached, graph, inputs: {name: what it is}}; {error} when the scene can't be shot yet."""
    plan, st = proj.get("plan") or {}, dict(proj["settings"])
    if quality:
        st["quality"] = quality
    s = plan["scenes"][index]
    if not prompts.is_written(s):
        return {"error": i18n.L("У сцены нет промта", "The scene has no prompt")}
    pre = preview(proj, quality)
    c, sw, sh, length = scene_spec(plan, st, s)
    shots_dir = projects.folder(proj["id"]) / "scenes"
    src = prompts.from_of(plan, s)
    prev_png = None
    if src is not None:
        k = pre["keys"][src["index"]]
        raw = next((x.get("raw", x["key"]) for x in pre["takes"][src["index"]] if x["key"] == k), k) if k else None
        prev_png = shot_paths(shots_dir, raw)[1] if raw and is_cached(shots_dir, raw) else None
        if prev_png is None and s["kind"] == "continue":
            return {"error": i18n.L(f"Сцена начинается с последнего кадра сцены {src['index'] + 1}, а она ещё не снята",
                                    f"The scene starts from the last frame of scene {src['index'] + 1}, which isn't shot yet")}
    start, seed, refs = scene_inputs(proj, plan, s, prev_png)
    tpath = scene_track(proj, c) if pre["tracks"][index] == "full" else scene_track(proj, c, plan, s)
    vref = voice_ref(proj, plan, s, c, tpath)
    end = end_frame(proj, s) if c.ends else None
    card = videomodels.shooter(c)
    text = model_prompts.for_id(plan, s) if vref else model_prompts.for_model(c.id, plan, s)
    key = pre["keys"][index]
    pid, inputs = proj["id"], {}
    first = f"h3s_{key}_start.png" if start else None
    if first:
        inputs[first] = str(start)
    ref_names = [f"h3s_{pid}_ref{k}{r.suffix}" for k, r in enumerate(refs if card.refs else [], 1)]
    inputs.update({n: str(r) for n, r in zip(ref_names, refs)})
    tname = f"h3s_{pid}_track{tpath.suffix}" if tpath else None
    if tname:
        inputs[tname] = str(tpath)
    last = f"h3s_{key}_end.png" if end else None
    if last:
        inputs[last] = str(end)
    names = []
    for x in lora_lib.for_model(loras_of(st, s), card.id):
        if (info := lora_lib.get(x["id"])):
            names.append((info.path.name, float(x["strength"])))
    voice = None
    if vref:
        info = lora_lib.get(vref["lora"]["id"])
        voice = {**vref, "voice": f"h3s_{pid}_voice{Path(vref['voice']).suffix}", "lora": info.path.name if info else vref["lora"]["id"],
                 "strength": vref["lora"]["strength"]}
        inputs[voice["voice"]] = str(vref["voice"])
    tstart = 0.0
    if tpath:
        sync = sync_track(proj)
        tstart = track_starts(plan, [scene_spec(plan, st, x)[3] for x in plan["scenes"]], float(sync.get("offset") or 0))[index]
    g = jobs.scene_graph(card.id, videomodels.adapt(card, text), sw, sh, length, seed, f"h3studio/{pid}/{key}", names, first,
                         ref_names, tname, tstart, voice, last)
    return {"model": card.id, "key": key, "cached": pre["scenes"][index] == "cached", "graph": g, "inputs": inputs}


async def shoot_scene(job: jobs.Job, pid: str, shots_dir: Path, prompt: str, kind: str, seed: int, w: int, h: int,
                      length: int, loras: list[dict], start: Optional[Path], refs: list[Path], quality: str,
                      on_start: Optional[Callable[[str], None]] = None, label: str = "", model: str = "h3",
                      track: Optional[Path] = None, track_start: float = 0.0, old_prompt: Optional[str] = None,
                      ref: Optional[dict] = None, end: Optional[Path] = None) -> dict:
    """One shot with the cache: from shots_dir if its key is there, else through the engine (jobs.shoot) into
    shots_dir/<key>.mp4 + .png. `kind` "continue" takes `start` as it is (a last frame); a new scene's start photo is
    cropped to the frame - on its face when it has one (start_crop: ID-LoRA takes the face from that frame).
    on_start(key) is called right before the engine starts - not for a cached shot; `label`
    names the shot in errors («Сцена 3»).
    -> {key, mp4, png, cached, seconds}. The storyboard (run) and the graph (phase 9) both shoot through here.
    `model` (phase 10): the video model; its prompt is rewritten for it here. `track` (LTX 2.3): the picture is made
    to that file's piece from `track_start`. An imported model (videomodels.shooter) gives its shot when there is one;
    otherwise its own model shoots - `model` in the result says whose shot it is. `old_prompt`: the prompt the scene
    was shot with before its model got its own (model_prompts) - a shot made with it is kept. `ref` (LTX 2.3: the graph's
    voice scene, a storyboard hero's voice - voice_ref): ID-LoRA {lora: {id, strength}, voice: a file, from, secs,
    identity} - the face from `start`, that voice. `end` (LTX, flf2v): the picture the scene ends on (cropped to the
    frame, as a start photo); a model that can't (H3, WAN) shoots without it, and its key doesn't have it."""
    label = label or i18n.L("Сцена", "Scene")
    card = videomodels.card(model)
    refs = refs if card.refs else []
    end = end if card.ends else None
    loras = lora_lib.for_model(loras, videomodels.shooter(card).id)   # each model its own LoRA (loras.py)
    crop = start_crop(start, w, h, kind, tight=bool(ref))   # the photo's face, when it has one: ID-LoRA's frame
    key = scene_key(prompt, seed, w, h, length, loras, start, refs, card.id, track, track_start, ref, end, fit=crop)
    if end:
        old_prompt = None   # a shot made without the end frame isn't this one
    if old_prompt and old_prompt != prompt and not is_cached(shots_dir, key):
        k0 = scene_key(old_prompt, seed, w, h, length, loras, start, refs, card.id, track, track_start)
        if is_cached(shots_dir, k0):
            prompt, key = old_prompt, k0
        elif card.id != "h3":   # shot the night of 2026-10-23 before H3's tail left LTX's prompt (363212f)
            k0 = scene_key(old_prompt, seed, w, h, length, loras, start, refs, card.id, track, track_start, legacy=True)
            if is_cached(shots_dir, k0):
                key = k0
    mp4, png = shot_paths(shots_dir, key)
    if not is_cached(shots_dir, key) and card.shoots_as:
        card = videomodels.shooter(card)
        key = scene_key(prompt, seed, w, h, length, loras, start, refs, card.id, track, track_start, ref, end, fit=crop)
        mp4, png = shot_paths(shots_dir, key)
    if is_cached(shots_dir, key):
        return {"key": key, "mp4": mp4, "png": png, "cached": True, "seconds": 0, "model": card.id}
    if on_start:
        on_start(key)
    ts = time.time()
    shots_dir.mkdir(exist_ok=True)
    first = None
    if start:
        first = f"h3s_{key}_start.png"
        if kind == "continue" and video_size(start) == (w, h):
            shutil.copyfile(start, config.COMFY_INPUT / first)
        else:   # the user's photo, or the last frame of a scene another model shot: cropped to the video's frame
            fit_frame(start, config.COMFY_INPUT / first, w, h, crop)
    ref_names = []
    for k, r in enumerate(refs, 1):
        ref_names.append(f"h3s_{pid}_ref{k}{r.suffix}")
        shutil.copyfile(r, config.COMFY_INPUT / ref_names[-1])
    tname = None
    if track:
        tname = f"h3s_{pid}_track{track.suffix}"
        if not (config.COMFY_INPUT / tname).exists() or file_sha(config.COMFY_INPUT / tname) != file_sha(track):
            shutil.copyfile(track, config.COMFY_INPUT / tname)
    last = None
    if end:
        last = f"h3s_{key}_end.png"
        fit_frame(end, config.COMFY_INPUT / last, w, h)
    voice = None
    if ref:
        vname = f"h3s_{pid}_voice{Path(ref['voice']).suffix}"
        shutil.copyfile(ref["voice"], config.COMFY_INPUT / vname)
        voice = {**ref, "voice": vname}
    out_mp4, out_png = await jobs.shoot(job, videomodels.adapt(card, prompt), w, h, length, seed, loras, first, f"h3studio/{pid}/{key}",
                                        quality, ref_names, card.id, tname, track_start, voice, last)
    if not out_png:
        raise EngineError(i18n.L(f"{label}: нет последнего кадра — цепочку не продолжить",
                                 f"{label}: no last frame, the chain cannot go on"))
    shutil.move(out_mp4, mp4)
    shutil.move(out_png, png)
    if not card.sound:
        await asyncio.to_thread(add_silence, mp4)
    for f in (first, last):
        if f:
            (config.COMFY_INPUT / f).unlink(missing_ok=True)
    return {"key": key, "mp4": mp4, "png": png, "cached": False, "seconds": round(time.time() - ts, 1), "model": card.id}


async def finish(job: jobs.Job, folder: Path, ed: dict, stem: str, w: int, h: int,
                 aspect: str, track: Optional[dict], out: dict, synced: bool = False,
                 fit: Optional[tuple[int, int]] = None) -> dict:
    """Shots -> the video: the montage (edit.render: folder/<stem>.mp4), the user's track over it (<stem>_music.mp4), the output -
    RTX size, HDR, 48 fps (<stem>_<tag>.mp4). job.progress["stage"] and job.phase follow it.
    -> the result's fields: video, video_scenes, track_sig / track_name, video_up / up_size / fps / hdr or up_error,
    out_tag. An upscale that fails is not an error of the whole: the video without it is there. `synced`: the scenes
    were shot to the track (LTX 2.3) - their own sound is the track's decoded pieces, so the track alone plays."""
    prog, res = job.progress, {}
    kept = track   # the track as the project keeps it: its signature is what preview() compares
    if synced and track:
        track = {**track, "scene_volume": 0.0}
    prog["stage"] = "assembling"
    job.phase = "assembling"
    video = folder / f"{stem}.mp4"
    from . import edit
    cuts = await asyncio.to_thread(edit.render, ed, folder, video, fit)
    res["video"] = res["video_scenes"] = video.name
    res.update(edit_sig=edit.signature(ed), duration=ed["duration"])
    if edit.needs_mix(ed, track, folder):   # the sounds from files and the track over the scenes' sound
        prog["stage"] = "mixing"
        job.phase = "mixing"
        mixed = folder / f"{stem}_music.mp4"
        await asyncio.to_thread(edit.mix, ed, folder, video, track, mixed)
        video = mixed
        res["video"] = mixed.name
        if track and (folder / track["file"]).exists():
            res.update(track_sig=music.signature(folder, kept), track_name=track.get("name"))
    if suffix := post.tag(out):
        prog["stage"] = "interpolating" if out["fps48"] else "upscaling"
        job.phase = "upscaling"
        up = folder / f"{stem}_{suffix}.mp4"
        try:
            ow, oh, fps = await asyncio.to_thread(post.finish, video, up, w, h, aspect, out, cuts, folder / "_post")
            res.update(video_up=up.name, up_size=f"{ow}x{oh}", fps=fps, hdr=out["hdr"], out_tag=suffix)
        except EngineError as e:
            res["up_error"] = str(e)
    res["out_tag"] = suffix
    return res


async def run(job: jobs.Job, pid: str) -> dict:
    """The render job. job.progress tells the video screen what happens; the result is saved into the project."""
    proj = projects.load(pid)
    plan, st = proj.get("plan"), proj["settings"]
    if not plan or not plan.get("scenes"):
        raise EngineError(i18n.L("Нет раскадровки", "No storyboard"))
    bad = [s["index"] + 1 for s in plan["scenes"] if not prompts.is_written(s)]
    if bad:
        raise EngineError(i18n.L("Сцены без промта: ", "Scenes without a prompt: ") + ", ".join(map(str, bad)))
    quality = st.get("quality", "draft")
    w, h = size(st)
    specs = [scene_spec(plan, st, s) for s in plan["scenes"]]
    stylized = prompts.stylized(plan)   # anime, 3D: a quieter `still`, never a handheld retake
    for c in {x[0].id: x[0] for x in specs}.values():
        if missing := videomodels.weights_missing(c):
            raise EngineError(i18n.L(f"{c.name}: нет файлов ", f"{c.name}: missing files ") + ", ".join(missing)
                              + i18n.L(" («Модели и настройки»)", " («Models and settings»)"))
    pre = preview(proj)
    folder = projects.folder(pid)
    sync = sync_track(proj)
    tstarts = track_starts(plan, [x[3] for x in specs], float(sync.get("offset") or 0)) if sync else []
    if sync and sync.get("duration") and tstarts:
        # only a scene still to shoot reads the track (a clip's last continuation starts past its bar: shot, it is fine)
        end = max((tstarts[i] + (scene_seconds(s) + preroll(plan, s, specs[i][3]) / graphs.FPS if plan.get("clip") else specs[i][3] / graphs.FPS)
                   for i, s in enumerate(plan["scenes"]) if specs[i][0].track and pre["scenes"][i] == "shoot"), default=0)
        if end > float(sync["duration"]) + 0.05:
            raise EngineError(i18n.L(f"Трек кончается на {sync['duration']:.0f} с, а сцены под трек идут до {end:.0f} с: "
                                     "возьмите трек длиннее, начните его раньше или уберите сцены",
                                     f"The track ends at {sync['duration']:.0f} s, but the scenes shot to the track go on to "
                                     f"{end:.0f} s: take a longer track, start it earlier or remove scenes"))
    shots_dir = folder / "scenes"
    shots_dir.mkdir(exist_ok=True)
    t0 = time.time()
    prog = job.progress
    est = lambda i: one_scene(st, quality, specs[i][1], specs[i][2], specs[i][3], bool(ref_photos(proj, plan, plan["scenes"][i])), specs[i][0])  # noqa: E731
    prog.update(stage="shooting", width=w, height=h, quality=quality,
                scenes=[{"index": s["index"], "id": sid(s), "kind": s["kind"], "status": "queued", "model": specs[s["index"]][0].short,
                         "estimate": round(est(s["index"])) if pre["scenes"][s["index"]] == "shoot" else 0} for s in plan["scenes"]])
    from .engine.comfy import COMFY
    order = shoot_order(plan, [x[0] for x in specs], getattr(COMFY, "model", "h3"))
    loaded = None
    for i in order:   # loading a model rides on its first shot
        r = prog["scenes"][i]
        m = videomodels.shooter(specs[i][0])
        if r["estimate"] and m.id != loaded:
            r["estimate"] += round(jobs.cold_extra(quality, m.id) if loaded is None else
                                   timings.cold_seconds(videomodels.timing_key(m, quality)))
            loaded = m.id
    job.estimate = pre["seconds"]
    shots: dict[int, dict] = {}
    pngs: dict[str, Path] = {}   # a scene id -> its shot's last frame (the start of a continuation from it)
    retakes: dict = {}           # a scene shot again for its lips -> the seed that goes into the video
    cams: dict = {}              # a singing scene shot again handheld for its stillness, the handheld take chosen
    for i in order:
        s = plan["scenes"][i]
        c, sw, sh, length = specs[i]
        row = prog["scenes"][i]
        if job.stop_after:
            row["status"] = "skipped"
            continue
        src = prompts.from_of(plan, s)
        start, seed, ref = scene_inputs(proj, plan, s, pngs.get(sid(src)) if src else None)
        if s["kind"] == "continue" and not start:
            raise EngineError(i18n.L(f"Сцене {i + 1} нужен последний кадр сцены {(src or {}).get('index', i - 1) + 1}, а его нет",
                                         f"Scene {i + 1} needs the last frame of scene {(src or {}).get('index', i - 1) + 1}, "
                                         "and there is none"))
        loras = loras_of(st, s)
        tpath = scene_track(proj, c) if pre["tracks"][i] == "full" else scene_track(proj, c, plan, s)

        def started(key: str, row=row, i=i) -> None:
            row.update(status="running", key=key)
            prog["current"] = i

        vref = voice_ref(proj, plan, s, c, tpath)   # a hero's voice by sample (ID-LoRA): its own prompt and key
        end = end_frame(proj, s)                    # the picture it comes to (LTX)
        text = model_prompts.for_id(plan, s) if vref else model_prompts.for_model(c.id, plan, s)
        shot = await shoot_scene(job, pid, shots_dir, text, s["kind"], seed, sw, sh, length, loras, start, ref,
                                 quality, started, i18n.L(f"Сцена {i + 1}", f"Scene {i + 1}"), c.id, tpath, tstarts[i] if tpath else 0.0,
                                 old_prompt=None if vref else s["prompt"], ref=vref, end=end)
        async def retake(seed2: int, text=text, s=s, i=i, c=c, sw=sw, sh=sh, length=length, loras=loras, start=start,
                         ref=ref, tpath=tpath, vref=vref, started=started, end=end, old: Optional[str] = "") -> dict:
            # `old`: the prompt a shot made before may have been shot with ("" - the scene's; None - none: a take with
            # another prompt must not find the first take under the scene's own)
            return await shoot_scene(job, pid, shots_dir, text, s["kind"], seed2, sw, sh, length, loras, start, ref,
                                     quality, started, i18n.L(f"Сцена {i + 1}", f"Scene {i + 1}"), c.id, tpath, tstarts[i] if tpath else 0.0,
                                     old_prompt=None if vref or old is None else s["prompt"], ref=vref, end=end)

        # a new singing shot of a clip: do the lips move where the song's voice is (a cached one was measured when shot)
        lips = await asyncio.to_thread(lips_of, plan, s, shot["mp4"], length) if s.get("shot") == "sing" and plan.get("clip") and not shot["cached"] else None
        retaken = False
        if lips is not None and not shot["cached"] and checks.mute(lips):
            # «не поёт»: one more take with another seed (remiqora-video's rule), the livelier lips go into the video
            row.update(status="running", note=i18n.L("губы не двигаются — переснимаю", "the lips don't move, shooting again"))
            seed2, retaken = seed + 7919, True
            again = await retake(seed2)
            lips2 = await asyncio.to_thread(lips_of, plan, s, again["mp4"], length)
            retakes[s["id"] if s.get("id") else i] = seed2 if (lips2 or 0) > lips else seed
            if (lips2 or 0) > lips:
                shot, seed, lips = {**again, "seconds": shot["seconds"] + again["seconds"]}, seed2, lips2
            row.update(key=shot["key"], note=None)
        # phase 10, stage A: the clip's checks (black, frozen, a cut inside, smeared, the face) on a new shot; a severe
        # problem - one more take with another seed, the one with fewer problems goes into the video (a cached shot:
        # what was found when it was shot)
        # the face against the hero's own portrait when one hero with a photo is in it (`hero`, severe), else against
        # the start frame as before; `still` - an almost still shot with people
        face = start or (ref[0] if ref else None)
        hero = hero_photo(proj, plan, s)
        people = plan["mode"] != "none" and not prompts.nobody(plan, s)
        singing = lips is not None and not checks.mute(lips)   # a singer standing still isn't a stall

        cut_ok = bool(prompts.shots_timeline(plan, s))   # «Склейки внутри сцены»: a cut inside is asked for, not a fault

        async def problems(mp4: Path, s=s, face=face, hero=hero, people=people, singing=singing, cut_ok=cut_ok) -> list:
            found = await asyncio.to_thread(checks.check_clip, mp4, face, hero, s.get("framing"), people)
            found = checks.calm(found, s.get("framing"), stylized)   # `still` by the scene's framing and the style
            return [p for p in found if not (singing and p.code == "frozen") and not (cut_ok and p.code == "cut")]
        found = await problems(shot["mp4"]) if not shot["cached"] else None
        # a face unlike the hero's in a shot that starts from a drawn frame unlike her (frame.ok false; the frame is
        # FACE_AT's first frame too): another seed starts from the same face - no retake for that alone, the board says
        # «кадр не похож на героя», and «Перерисовать кадр» is the way
        hopeless = bool(found) and unlike_frame(s) is not None and all(p.code == "hero" for p in found if p.severe)
        if found and checks.severe(found) and not retaken and not hopeless:
            row.update(status="running", note=", ".join(dict.fromkeys(checks.name(p.code) for p in found if p.severe))
                       + i18n.L(" — переснимаю", ", shooting again"))
            seed2, retaken = seed + 7919, True
            again = await retake(seed2)
            found2 = await problems(again["mp4"])
            better = checks.better(found2, found)   # the face closer to the hero's when both miss it
            retakes[s["id"] if s.get("id") else i] = seed2 if better else seed
            if better:
                shot, seed, found = {**again, "seconds": shot["seconds"] + again["seconds"]}, seed2, found2
            row.update(key=shot["key"], note=None)
        if found and not retaken and any(p.code == "still" for p in found) and still_retake(plan, s):
            # formula 3, a clip's singer almost still: one more take with another seed, the livelier one goes into the
            # video. Handheld (the same seed) only for a scene with no camera of its own - a camera the writer or the
            # user picked (static, a push-in) stays, and a drawn or animated picture never goes handheld: it jumped
            # and pulled away from the drawing there (anime, 3D)
            hand = not s.get("camera") and s.get("framing") in ("close", "medium") and not stylized
            row.update(status="running", note=i18n.L("почти не движется — переснимаю", "almost still, shooting again")
                       + (i18n.L(" с камерой с рук", " handheld") if hand else ""))
            if hand:
                s2 = {**s, "camera": "handheld"}
                plan2 = {**plan, "scenes": [s2 if x is s else x for x in plan["scenes"]]}
                s2["prompt"] = prompts.compose(plan2, s2)
                again = await retake(seed, text=model_prompts.for_id(plan2, s2) if vref else model_prompts.for_model(c.id, plan2, s2),
                                     old=None)
            else:
                again = await retake(seed + 7919)
            found2 = await problems(again["mp4"])
            if checks.better(found2, found):
                if hand:
                    cams[s["id"] if s.get("id") else i] = "handheld"
                else:
                    retakes[s["id"] if s.get("id") else i] = seed + 7919
                    seed += 7919
                shot, found = {**again, "seconds": shot["seconds"] + again["seconds"]}, found2
                if s.get("shot") == "sing" and plan.get("clip"):
                    lips = await asyncio.to_thread(lips_of, plan, s, shot["mp4"], length)
            elif not hand:
                retakes[s["id"] if s.get("id") else i] = seed
            row.update(key=shot["key"], note=None)
        seen = checks.calm(checks.public(found) if found is not None else checks.saved(shot["mp4"]), s.get("framing"), stylized)
        if seen and cut_ok:
            seen = [p for p in seen if p.get("code") != "cut"]
        if seen:
            row["checks"] = seen
        if lips is not None:
            row.update(lips=round(lips, 4), mute=checks.mute(lips))
        if shot["cached"]:
            row.update(status="cached", key=shot["key"], seconds=0)
        else:
            row.update(status="done", seconds=shot["seconds"])
            for j in order:   # now with this shot in it (a cold one doesn't count)
                if prog["scenes"][j]["status"] == "queued" and specs[j][0].id == c.id:
                    prog["scenes"][j]["estimate"] = round(est(j))
        key = shot["key"]
        heard = None
        if vref:   # how alike the scene's voice is to the sample (voice.py; measured once, kept next to the shot)
            from . import voice
            heard = await asyncio.to_thread(voice.measured, shot["mp4"], vref["voice"], vref["from"], vref["secs"])
        shots[i] = {"index": i, "id": sid(s), "kind": s["kind"], "key": key, "seed": seed, "file": f"scenes/{key}.mp4",
                    "png": f"scenes/{key}.png", "cached": shot["cached"], "seconds": shot["seconds"], "model": shot["model"],
                    **({"lips": round(lips, 4), "mute": checks.mute(lips)} if lips is not None else {}),
                    **({"voice": heard} if heard else {}), **({"checks": seen} if seen else {})}
        pngs[sid(s)] = shot["png"]
    # «Починить лица» (facefix.py) on the shot scenes that ask for it, every model loaded once for all of them; a
    # fixed shot lives next to the shot as scenes/<key>.ff<sig>.mp4 and goes into the video in the shot's place
    todo: list[tuple[int, dict]] = []
    for i, sh in shots.items():
        s = plan["scenes"][i]
        if (ff := facefix_of(s)):
            k2 = fixed_key(plan, s, sh["key"])
            sh["raw"] = sh["key"]
            if not is_cached(shots_dir, k2):
                todo.append((i, {"src": shots_dir / f"{sh['key']}.mp4", "mode": ff.get("mode", "far"), "strength": float(ff.get("strength", 1.0)),
                                 "seed": sh["seed"], "text": facefix_text(plan, s), "dest": shots_dir / f"{k2}.mp4",
                                 "png": shots_dir / f"{k2}.png", "label": i18n.L(f"Сцена {i + 1}", f"Scene {i + 1}")}))
    if todo and not job.stop_after:
        from . import facefix
        phases = {"track": i18n.L("ищу лица", "finding the faces"), "krea": i18n.L("лица: опорные кадры (Krea 2)", "faces: anchor frames (Krea 2)"),
                  "ltx": i18n.L("лица: LTX 2.3", "faces: LTX 2.3")}
        t_ff = {}

        def on_item(k: int, ph: str) -> None:
            i, _ = todo[k]
            row = prog["scenes"][i]
            if ph == "done":
                row.update(status="done", note=None, seconds=round(row.get("seconds", 0) + time.time() - t_ff.get(k, time.time()), 1))
            else:
                t_ff.setdefault(k, time.time())
                row.update(status="running", note=phases[ph])
                prog["current"] = i
        await facefix.make_many(job, [x for _, x in todo], on_item)
    for i, sh in shots.items():
        if "raw" in sh:
            k2 = fixed_key(plan, plan["scenes"][i], sh["raw"])
            if is_cached(shots_dir, k2):   # made now or before; stopped before it was made: the shot itself goes in
                sh.update(key=k2, file=f"scenes/{k2}.mp4", png=f"scenes/{k2}.png")
                prog["scenes"][i]["key"] = k2   # the video screen shows the fixed shot
    prog.pop("current", None)
    if retakes or cams:   # the scenes shot twice (their lips, a check): both takes kept, the better one chosen (the montage takes it)
        cur = projects.load(pid)
        for x in cur["plan"]["scenes"]:
            k = x.get("id") or x["index"]
            if k in retakes:
                first = _seed(cur["plan"], x)
                x["takes"] = list(dict.fromkeys([*takes_of(cur["plan"], x), first, first + 7919]))
                x["seed"] = retakes[k]
            if k in cams:   # the handheld take: the scene's camera (its prompt is the one that take was shot with)
                x["camera"] = cams[k]
        from .planner import check
        cur["plan"] = check.plan(cur["plan"])
        projects.save(cur)
        proj = cur
    if len(shots) < len(plan["scenes"]):   # stopped: the shots so far, in the storyboard's order up to the first gap
        shots = {i: shots[i] for i in range(len(plan["scenes"])) if all(j in shots for j in range(i + 1))}
    shots = [shots[i] for i in sorted(shots)]

    result = {"quality": quality, "width": w, "height": h, "shots": shots,
              "complete": len(shots) == len(plan["scenes"]), "finished": time.time()}
    if result["complete"]:
        from . import edit
        now = projects.load(pid)
        ed = edit.resolve(now, [x["key"] for x in shots], [True] * len(shots), preview(now)["takes"])
        # the track alone plays only when every scene was shot to it; a scene of another size is fitted to the frame
        synced = bool(sync) and all(x[0].track for x in specs)
        fit = (w, h) if any((x[1], x[2]) != (w, h) for x in specs) else None
        result.update(await finish(job, folder, ed, f"video_{quality}", w, h, st.get("aspect", "16:9"), st.get("track"), post.output_of(st),
                                   synced, fit))
    result["seconds"] = round(time.time() - t0, 1)
    prog["stage"] = "done"
    cur = projects.load(pid)
    cur.setdefault("renders", {})[result["quality"]] = result
    projects.save(cur)
    return result


async def shoot_take(job: jobs.Job, pid: str, index: int, seed: int) -> dict:
    """«Ещё дубль»: one more shot of one scene with another seed (the take is already in the scene's takes and
    chosen). A continuation needs the chosen shot of the scene it goes on from. Nothing is assembled: the video is
    built again by «Снять ролик» / «Собрать ролик», and the scenes after it that start from its frame are shot then."""
    proj = projects.load(pid)
    plan, st = proj.get("plan") or {}, proj["settings"]
    if not 0 <= index < len(plan.get("scenes") or []):
        raise EngineError(i18n.L("Нет такой сцены", "No such scene"))
    s = plan["scenes"][index]
    if not prompts.is_written(s):
        raise EngineError(i18n.L(f"У сцены {index + 1} нет промта", f"Scene {index + 1} has no prompt"))
    quality = st.get("quality", "draft")
    specs = [scene_spec(plan, st, x) for x in plan["scenes"]]
    card, w, h, length = specs[index]
    pre = preview(proj)
    sync = sync_track(proj)
    tpath = scene_track(proj, card) if pre["tracks"][index] == "full" else scene_track(proj, card, plan, s)
    src = prompts.from_of(plan, s)
    prev_png = None
    if src is not None:
        k = pre["keys"][src["index"]]
        # the shot itself, not its face-fixed copy: a continuation starts from the model's own last frame
        raw = next((x.get("raw", x["key"]) for x in pre["takes"][src["index"]] if x["key"] == k), k) if k else None
        if not raw or not is_cached(projects.folder(pid) / "scenes", raw):
            raise EngineError(i18n.L(f"Сначала снимите сцену {src['index'] + 1}: дубль сцены {index + 1} начинается с её последнего кадра",
                                     f"Shoot scene {src['index'] + 1} first: the take of scene {index + 1} starts from its last frame"))
        prev_png = shot_paths(projects.folder(pid) / "scenes", raw)[1]
    start, _, ref = scene_inputs(proj, plan, s, prev_png)
    job.estimate = one_scene(st, quality, w, h, length, bool(ref) and card.refs, card) + jobs.cold_extra(quality, card.id)
    job.progress.update(stage="shooting", scene=index, seed=seed, quality=quality)
    shots_dir = projects.folder(pid) / "scenes"
    shots_dir.mkdir(exist_ok=True)
    tstart = track_starts(plan, [x[3] for x in specs], float(sync.get("offset") or 0))[index] if tpath else 0.0
    vref = voice_ref(proj, plan, s, card, tpath)
    text = model_prompts.for_id(plan, s) if vref else model_prompts.for_model(card.id, plan, s)
    shot = await shoot_scene(job, pid, shots_dir, text, s["kind"], seed, w, h, length,
                             loras_of(st, s), start, ref, quality, label=i18n.L(f"Сцена {index + 1}, дубль", f"Scene {index + 1}, take"),
                             model=card.id, track=tpath,
                             track_start=tstart, old_prompt=None if vref else s["prompt"], ref=vref, end=end_frame(proj, s))
    if not shot["cached"]:   # the clip's checks, for the take's badge (a take the user asked for isn't retaken)
        await asyncio.to_thread(checks.check_clip, shot["mp4"], start or (ref[0] if ref else None), hero_photo(proj, plan, s),
                                s.get("framing"), plan["mode"] != "none" and not prompts.nobody(plan, s))
    job.progress["stage"] = "done"
    return {"scene": index, "seed": seed, "key": shot["key"], "cached": shot["cached"], "seconds": shot["seconds"]}
