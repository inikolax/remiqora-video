"""The montage. A storyboard's video as clips on a timeline: the scenes' shots trimmed, cut in two,
copied, played slower or faster, their sound louder or quieter; the chains moved as one; a transition at the start of
a clip (a cut, a dissolve, through black); the user's sounds from files on a lane of their own; the user's track
(settings.track) under all of it, quieter where the scenes speak if asked. Nothing is shot again: the clips are the
shots in scenes/, the montage only says how they are put together.

project.json -> "edit" (only once the user changes something; without it the montage is the storyboard as
render.assemble put it together - a continuation loses its first frame, which repeats the last one before it):
  {"version": 2,
   "clips": [{"id", "scene": <scene id>, "in": s, "out": s, "tr": "cut"|"fade"|"black", "td": s, "speed": x, "vol": x,
              "take": <seed> - another take of the scene than the storyboard's (none: the storyboard's)}],
   "off": [<scene id>],             - scenes taken out of the video (they stay in the storyboard)
   "sounds": [{"id", "file", "name", "start": s, "in": s, "out": s, "vol": x, "fade_in": s, "fade_out": s}],
   "overlays": [{"id", "scene", "take", "start": s, "in": s, "out": s}],   - «Поверх»: a piece of a scene's shot over
                                     the video from `start` (its picture only: the sound and the timing are the clips')
   "duck": 0..1}                     - how much the track gives way to the scenes' sound
A version 1 montage (one clip per scene, no ids) reads as it is. resolve() reads it against the current storyboard:
a scene that is gone leaves, a new one stands after the scene before it, a reshot one keeps its clips; the clips of
a chain always stand together. render() builds the picture with the scenes' sound in whole frames (the sound never
runs ahead of the picture: acrossfade on a cut shortened only the sound, 0.15 s a join with render.assemble);
mix() lays the sounds and the track over it.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from . import config
from .engine import graphs
from .engine.comfy import EngineError
from . import i18n

FPS = graphs.FPS
FRAME = 1 / FPS
TRANSITIONS = ("cut", "fade", "black", "flash")   # flash: a cut with a white flash fading out (a clip's entry into a loud part)
FLASH = 4                 # frames of the flash; it takes no time from the video
TD = 0.5                  # a dissolve's seconds by default
MIN_CLIP = 0.5            # a clip is never shorter (in its shot)
# Phase 11: the video's common colour, one look over every clip (remiqora-video's GRADES, frame for frame - no frame is
# added or dropped, so the cuts stay where they are): `match` first brings each clip's colour and contrast part of the
# way to the whole video's average (scenes of H3 and LTX side by side stop jumping in colour), then the look - a grade
# or the user's .cube LUT (luts/ in the project). Nothing of it: the montage as it always was, its signature too.
GRADES = {
    "film": "eq=contrast=1.06:saturation=1.05,vignette=PI/5,noise=alls=5:allf=t",
    "warm": "colorbalance=rs=0.05:gs=0.01:bs=-0.05:rm=0.04:bm=-0.04,eq=contrast=1.04:saturation=1.08,vignette=PI/5",
    "cold": "colorbalance=rs=-0.04:bs=0.06:rm=-0.03:bm=0.05,eq=contrast=1.06:saturation=0.9,vignette=PI/5",
    "teal": "colorbalance=rs=-0.06:gs=0.0:bs=0.07:rh=0.07:gh=0.02:bh=-0.07,eq=contrast=1.08:saturation=1.1,vignette=PI/5",
    "bw": "hue=s=0,eq=contrast=1.12,vignette=PI/5,noise=alls=4:allf=t",
}
MATCH = 0.6               # how far each clip goes toward the average (1 - all the way: flat; 0.6 keeps a scene's mood)
VIGNETTE_MAX = 1.0        # the vignette's angle at 100 % (radians; the grades use PI/5 = 0.63)
GRAIN_MAX = 18            # the grain's strength at 100 % (ffmpeg noise alls; «Плёнка» has 5)
EDGE = 0.03               # the sound's fade at a cut, against clicks
# A seamless join (a continuation, the next piece of a take) is one sound going on: the 30 ms out + 30 ms in of a cut
# made a 60 ms hole in it, 15-46 dB deep (2026-10-28, measured on «Красный акцент» and «Возвращение»). Its new sound is
# still generated anew, so a bare join would click: a fade this short stops the click and isn't heard
EDGE_SEAMLESS = 0.005
SPEED = (0.5, 2.0)        # atempo's range in one step; the picture follows the same
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ensure_ids(plan: dict) -> bool:
    """Every scene a stable `id` (the montage's clips point at it; an index changes when scenes move). A copied
    scene that came with another's id gets its own. -> whether anything was added."""
    seen, changed = set(), False
    for s in plan.get("scenes") or []:
        if not s.get("id") or s["id"] in seen:
            s["id"] = uuid.uuid4().hex[:8]
            changed = True
        seen.add(s["id"])
    return changed


_frames: dict[str, dict] = {}   # a folder -> {file name: [size, frames]}, kept in its _frames.json


def shot_seconds(mp4: Optional[Path], unshot: Optional[int] = None) -> float:
    """A shot's length (its frames at 24 fps); a scene not shot yet - the 5 s it will have. A shot never changes
    once written, so its frames are read once (ffprobe, ~45 ms) and kept next to it: a storyboard of 120 scenes
    would wait 5 s for its estimate after every start of the server. `unshot`: the frames a scene not shot yet will
    have with the project's model (phase 10: LTX and WAN 121, H3 124)."""
    if not mp4 or not mp4.exists():
        return (unshot or graphs.frames_for(5)) / FPS
    d = str(mp4.parent)
    if d not in _frames:
        try:
            _frames[d] = json.loads((mp4.parent / "_frames.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _frames[d] = {}
    known, size = _frames[d], mp4.stat().st_size
    if (known.get(mp4.name) or [None])[0] != size:
        from .render import frame_count
        known[mp4.name] = [size, frame_count(mp4)]
        try:
            (mp4.parent / "_frames.json").write_text(json.dumps(known), encoding="utf-8")
        except OSError:
            pass
    return known[mp4.name][1] / FPS


def _frame(x: float) -> float:
    return round(round(float(x) * FPS) / FPS, 4)


def _num(x, lo: float, hi: float, default: float) -> float:
    try:
        return min(hi, max(lo, float(x)))
    except (TypeError, ValueError):
        return default


def _own_take(s: dict, take) -> Optional[dict]:
    """The take of item `s` a clip or an overlay asks for (a seed), when it is another than the scene's own shot."""
    sh = s["shot"]
    return next((x for x in s["takes"] or [] if str(take or "").lstrip("-").isdigit() and x["seed"] == int(take)
                 and x["key"] != (sh or {}).get("key") and x["seed"] != s.get("chosen")), None)


def _shot_of(s: dict, own: Optional[dict]) -> Optional[dict]:
    if not own:
        return s["shot"]
    return {k: own[k] for k in ("key", "file", "png", "src")} if own.get("cached") else None


def frames_out(c: dict) -> int:
    """A clip's frames in the video: its frames in the shot at its speed."""
    return max(1, round(round((c["out"] - c["in"]) * FPS) / c["speed"]))


def resolve(proj: dict, keys: list[Optional[str]], cached: list[bool], takes: Optional[list[list[dict]]] = None) -> dict:
    """A storyboard's montage, against its shots (`keys` / `cached` / `takes` per scene - from render.preview; a take:
    {seed, key, cached}): the scenes as items for lay()."""
    plan = proj.get("plan") or {}
    ensure_ids(plan)
    folder = None
    if proj.get("id"):
        from . import projects
        folder = projects.folder(proj["id"])
    from .planner import prompts
    from . import render
    shot = lambda k: {"key": k, "file": f"scenes/{k}.mp4", "png": f"scenes/{k}.png", "src": str(folder / "scenes" / f"{k}.mp4")}  # noqa: E731
    st = proj.get("settings") or {}
    items = []
    if plan.get("clip"):   # a clip's scenes end on their bars; a continuation starts where its scene's whole shot ends
        lengths = [render.scene_spec(plan, st, s)[3] for s in plan.get("scenes") or []]
        places = render.clip_places(plan, lengths)
        sc = plan.get("scenes") or []
        goes_on = [bool(k and x.get("kind") == "continue" and prompts.from_of(plan, x) is sc[k - 1]) for k, x in enumerate(sc)]
        pre = [render.preroll(plan, x, lengths[k]) for k, x in enumerate(sc)]   # a scene from a picture: its warm-up before the bar is cut
    for i, s in enumerate(plan.get("scenes") or []):
        key = keys[i] if i < len(keys) else None
        src = prompts.from_of(plan, s)
        mine = (takes[i] if takes and i < len(takes) else None) or []
        items.append({"id": s["id"], "index": i, "name": i18n.L(f"Сцена {i + 1}", f"Scene {i + 1}"), "chain": s.get("chain", 0), "kind": s.get("kind"),
                      "from": src["id"] if src else None, "chosen": int(s["seed"]) if s.get("seed") else None,
                      "shot": shot(key) if folder and key and i < len(cached) and cached[i] else None,
                      "unshot": render.scene_spec(plan, st, s)[3],
                      # from the frame its bar starts on to the frame the next one does: rounding each length alone
                      # drifted the cuts off the beat (0.17 s by the end of a 15-scene clip)
                      "want": max(MIN_CLIP, (round(float(s["end"]) * FPS) - places[i] - pre[i] - goes_on[i]) / FPS)
                      if plan.get("clip") else None,
                      **({"pre": round(pre[i] / FPS, 4)} if plan.get("clip") and pre[i] else {}),
                      # a clip's way into a loud part (a chorus, a drop) after a quiet one: a white flash on the cut
                      "accent": bool(plan.get("clip") and s.get("loud") and i and not plan["scenes"][i - 1].get("loud")),
                      "takes": [{**t, **(shot(t["key"]) if folder and t.get("cached") else {"file": None, "png": None, "src": None})} for t in mine]})
    return lay(items, proj.get("edit") or {}, folder)


def lay(items: list[dict], ed: dict, folder: Optional[Path], unshot: Optional[int] = None) -> dict:
    """The montage as it will be built, from its scenes (a storyboard's or the inputs of a graph's «Монтаж»): items
    [{id, index, name, chain, kind, from, chosen, shot: {key, file, png, src} | None, takes: [{seed, key, cached,
    file, png, src}], unshot?, want?}] in their order; `chain` - a run of scenes each going on from the one before it,
    `from` - the item whose last frame a continuation starts from; `unshot` - the frames a scene not shot yet will have
    (its model's, phase 11), `want` - a clip's scene: the seconds it plays, cut on its bar (the shot is a little longer,
    up to its model's frame grid; a scene another one goes on from plays whole). -> {clips: [{id, scene, index, name, chain, kind, from, file, png,
    src, length, in, out, tr, td, speed, vol, take, takes, take_list, chosen, start, dur, frames, seamless, jump}],
    off, sounds, duck, duration, complete, changed}. take: the clip's own take (a seed), None - the scene's chosen
    one. start / dur: where the clip is on the timeline (a dissolve overlaps the clip before it); seamless: the
    picture goes on without a seam - the next piece of the same take, or a continuation right after its scene,
    untouched at the join (no cut for RIFE); jump: such a join trimmed (or after another take) - the picture jumps."""
    ids = [x["id"] for x in items]
    by_id = {x["id"]: x for x in items}
    off = [x for x in ed.get("off") or [] if x in by_id]
    stored, seen_ids = [], set()
    for c in ed.get("clips") or []:
        if isinstance(c, dict) and c.get("scene") in by_id and c["scene"] not in off:
            cid = str(c.get("id") or c["scene"])
            if cid in seen_ids:
                cid = uuid.uuid4().hex[:8]
            seen_ids.add(cid)
            stored.append({**c, "id": cid})
    # a scene with no clip and not taken out: a new one, after the last clip of the scene before it
    present = {c["scene"] for c in stored}
    for i, sid in enumerate(ids):
        if sid in present or sid in off:
            continue
        at = 0
        for j in range(i - 1, -1, -1):
            idx = [k for k, c in enumerate(stored) if c["scene"] == ids[j]]
            if idx:
                at = idx[-1] + 1
                break
        stored.insert(at, {"id": sid if sid not in seen_ids else uuid.uuid4().hex[:8], "scene": sid})
        present.add(sid)
    # a chain stands together: chains in the order of their first clip, the clips of a chain in their own order
    chains: list = []
    for c in stored:
        ch = by_id[c["scene"]].get("chain", 0)
        if ch not in chains:
            chains.append(ch)
    seq = [c for ch in chains for c in stored if by_id[c["scene"]].get("chain", 0) == ch]
    clips, t = [], 0
    for k, c in enumerate(seq):
        s = by_id[c["scene"]]
        mine = s["takes"] or []
        own = _own_take(s, c.get("take"))
        sh = _shot_of(s, own)   # another take of this scene: its own shot
        length = shot_seconds(Path(sh["src"]) if sh else None, s.get("unshot") or unshot)
        prev = clips[-1] if clips else None
        nxt = seq[k + 1] if k + 1 < len(seq) else None
        feeds = nxt is not None and by_id[nxt["scene"]].get("from") == s["id"]   # the next clip starts from this one's last frame
        # this clip goes on from the one before it: the next piece of the same take, or the continuation of the
        # scene before it (its start frame is the last frame of that scene's chosen take)
        same_scene = prev is not None and prev["scene"] == s["id"]
        same = same_scene and prev["take"] == (own["seed"] if own else None)
        link = prev is not None and s.get("from") is not None and prev["scene"] == s["from"]
        cont = link and prev["take"] is None   # another take before it: its last frame is not this one's start
        # a continuation untouched: its first frame repeats the last one before it; a clip's scene from a picture
        # starts after its warm-up (`pre`, render.preroll)
        first_in = FRAME if cont else float(s.get("pre") or 0.0)
        a = _frame(min(_num(c.get("in", first_in), 0.0, length, first_in), length - MIN_CLIP))
        end = length if feeds or not s.get("want") else min(length, a + float(s["want"]))   # a clip's scene: on its bar
        b = _frame(min(max(a + MIN_CLIP, _num(c.get("out") or end, 0.0, length, end)), length))
        speed = round(_num(c.get("speed"), *SPEED, 1.0) * 20) / 20
        cl = {"id": c["id"], "scene": s["id"], "index": s["index"], "name": s.get("name") or i18n.L(f"Сцена {s['index'] + 1}", f"Scene {s['index'] + 1}"),
              "chain": s.get("chain", 0), "kind": s.get("kind"), "from": s.get("from"),
              "file": sh["file"] if sh else None, "png": sh["png"] if sh else None, "src": sh["src"] if sh else None,
              "length": round(length, 4), "in": a, "out": b, "speed": speed, "vol": round(_num(c.get("vol"), 0.0, 2.0, 1.0), 2),
              **({"color": color_of(c.get("color"))} if color_of(c.get("color")) else {}),
              **({"scene_color": color_of((ed.get("scene_colors") or {}).get(s["id"]))} if color_of((ed.get("scene_colors") or {}).get(s["id"])) else {}),
              "take": own["seed"] if own else None, "takes": len(mine), "chosen": s.get("chosen"),
              "take_list": [{"seed": x["seed"], "key": x["key"], "cached": bool(x.get("cached")), "png": x.get("png")} for x in mine]}
        n = frames_out(cl)
        tr = c.get("tr") if c.get("tr") in TRANSITIONS and k else "flash" if k and s.get("accent") and "tr" not in c else "cut"
        td = 0
        if tr not in ("cut", "flash") and prev:
            td = round(min(max(0.2, _num(c.get("td"), 0.2, 2.0, TD)), 2.0) * FPS)
            td = max(1, min(td, prev["frames"] // 2, n // 2))
        whole = speed == 1 and (prev or {}).get("speed") == 1
        joined = prev is not None and ((same and abs(prev["out"] - a) < FRAME / 2)
                                       or (cont and abs(prev["out"] - prev["length"]) < FRAME / 2 and abs(a - FRAME) < FRAME / 2))
        seamless = (same or cont) and tr == "cut" and whole and joined
        begin = t - td
        cl.update(tr=tr, td=round(td / FPS, 4), start=round(begin / FPS, 4), dur=round(n / FPS, 4), frames=n,
                  seamless=seamless, jump=(same_scene or link) and not seamless and tr == "cut")
        clips.append(cl)
        t = begin + n
    sounds = []
    for x in ed.get("sounds") or []:
        if not isinstance(x, dict) or not x.get("file") or not folder or not (folder / x["file"]).exists():
            continue
        ln = _num(x.get("length") or 0, 0, 36000, 0) or sound_seconds(folder / x["file"])
        a = round(_num(x.get("in"), 0, max(0.0, ln - 0.1), 0), 3)
        b = round(_num(x.get("out") or ln, a + 0.1, ln, ln), 3)
        sounds.append({"id": str(x.get("id") or uuid.uuid4().hex[:8]), "file": x["file"], "name": x.get("name") or x["file"],
                       "length": round(ln, 3), "start": round(_num(x.get("start"), 0, 36000, 0), 3), "in": a, "out": b,
                       "vol": round(_num(x.get("vol"), 0, 2, 1), 2), "fade_in": round(_num(x.get("fade_in"), 0, 10, 0), 2),
                       "fade_out": round(_num(x.get("fade_out"), 0, 10, 0), 2)})
    overlays = []
    for o in ed.get("overlays") or []:   # «Поверх»: inside the video, at least MIN_CLIP long, whole frames
        if not isinstance(o, dict) or o.get("scene") not in by_id or t < MIN_CLIP * FPS:
            continue
        s = by_id[o["scene"]]
        own = _own_take(s, o.get("take"))
        sh = _shot_of(s, own)
        length = shot_seconds(Path(sh["src"]) if sh else None, s.get("unshot") or unshot)
        start = round(_num(o.get("start"), 0, t / FPS - MIN_CLIP, 0) * FPS)
        a = round(_num(o.get("in"), 0, length - MIN_CLIP, 0) * FPS)
        b = round(_num(o.get("out") or a / FPS + 2, a / FPS + MIN_CLIP, length, length) * FPS)
        n = max(1, min(b - a, t - start))
        overlays.append({"id": str(o.get("id") or uuid.uuid4().hex[:8]), "scene": s["id"], "index": s["index"],
                         "name": s.get("name") or i18n.L(f"Сцена {s['index'] + 1}", f"Scene {s['index'] + 1}"),
                         "take": own["seed"] if own else None, "chosen": s.get("chosen"),
                         "file": sh["file"] if sh else None, "png": sh["png"] if sh else None, "src": sh["src"] if sh else None,
                         "length": round(length, 4), "in": round(a / FPS, 4), "out": round((a + n) / FPS, 4),
                         "start": round(start / FPS, 4), "dur": round(n / FPS, 4), "frames": n,
                         "take_list": [{"seed": x["seed"], "key": x["key"], "cached": bool(x.get("cached")), "png": x.get("png")} for x in s["takes"] or []]})
    scene_colors = {sid: color for sid, value in (ed.get("scene_colors") or {}).items()
                    if sid in by_id and (color := color_of(value))}
    return {"clips": clips, "off": off, "off_names": {x: by_id[x].get("name") or "" for x in off}, "sounds": sounds,
            "overlays": overlays, "scene_colors": scene_colors,
            "duck": round(_num(ed.get("duck"), 0, 1, 0), 2), **look_of(ed, folder),
            "duration": round(t / FPS, 3), "complete": all(c["file"] for c in clips) and bool(clips), "changed": bool(ed)}


_sound_len: dict[tuple, float] = {}


def sound_seconds(p: Path) -> float:
    st = p.stat()
    k = (str(p), st.st_size)
    if k not in _sound_len:
        from . import music
        _sound_len[k] = music.duration(p)
    return _sound_len[k]


def stored(body: dict) -> dict:
    """What goes into project.json from the editor (its clips in order with their trims, transitions, speed and level;
    the scenes taken out; the sounds; the ducking)."""
    clips = []
    for c in body.get("clips") or []:
        if not isinstance(c, dict) or not c.get("scene"):
            continue
        clips.append({"id": str(c.get("id") or uuid.uuid4().hex[:8])[:16], "scene": str(c["scene"]),
                      "in": _frame(_num(c.get("in"), 0, 36000, 0)), "out": _frame(float(c["out"])) if c.get("out") else None,
                      "tr": c.get("tr") if c.get("tr") in TRANSITIONS else "cut", "td": _frame(_num(c.get("td"), 0.2, 2, TD)),
                      "speed": round(_num(c.get("speed"), *SPEED, 1.0) * 20) / 20, "vol": round(_num(c.get("vol"), 0, 2, 1), 2),
                      **({"color": color_of(c.get("color"))} if color_of(c.get("color")) else {}),
                      **({"take": int(c["take"])} if str(c.get("take") or "").lstrip("-").isdigit() else {})})
    sounds = []
    for x in body.get("sounds") or []:
        if isinstance(x, dict) and x.get("file") and ".." not in str(x["file"]) and str(x["file"]).startswith("sounds/"):
            sounds.append({"id": str(x.get("id") or uuid.uuid4().hex[:8])[:16], "file": str(x["file"]), "name": str(x.get("name") or "")[:120],
                           "length": _num(x.get("length"), 0, 36000, 0), "start": _num(x.get("start"), 0, 36000, 0),
                           "in": _num(x.get("in"), 0, 36000, 0), "out": _num(x.get("out"), 0, 36000, 0) or None,
                           "vol": _num(x.get("vol"), 0, 2, 1), "fade_in": _num(x.get("fade_in"), 0, 10, 0), "fade_out": _num(x.get("fade_out"), 0, 10, 0)})
    overlays = []
    for o in body.get("overlays") or []:
        if isinstance(o, dict) and o.get("scene"):
            overlays.append({"id": str(o.get("id") or uuid.uuid4().hex[:8])[:16], "scene": str(o["scene"]),
                             "start": _frame(_num(o.get("start"), 0, 36000, 0)), "in": _frame(_num(o.get("in"), 0, 36000, 0)),
                             "out": _frame(_num(o.get("out"), 0, 36000, 0)) or None,
                             **({"take": int(o["take"])} if str(o.get("take") or "").lstrip("-").isdigit() else {})})
    scene_colors = {}
    for sid, value in (body.get("scene_colors") or {}).items():
        sid = str(sid)[:32]
        if sid and (color := color_of(value)):
            scene_colors[sid] = color
    return {"version": 2, "clips": clips, "off": [str(x) for x in body.get("off") or []], "sounds": sounds,
            **({"overlays": overlays} if overlays else {}), "scene_colors": scene_colors,
            "duck": round(_num(body.get("duck"), 0, 1, 0), 2), **look_of(body, None)}


def look_of(ed: dict, folder: Optional[Path]) -> dict:
    """The video's colour as kept: {grade: a GRADES key | "lut", lut: "luts/<file>.cube", lut_mix: 0..1 (how much of
    the LUT), match: true, color, vignette: 0..1, grain: 0..1}, only what is set (a montage without them stays as it
    was). A LUT file that is gone is no look."""
    out: dict = {}
    g = ed.get("grade")
    if g in GRADES:
        out["grade"] = g
    elif g == "lut" and isinstance(ed.get("lut"), str) and ed["lut"].startswith("luts/") and ".." not in ed["lut"] \
            and (folder is None or (folder / ed["lut"]).exists()):
        out.update(grade="lut", lut=ed["lut"])
    if ed.get("match"):
        out["match"] = True
    if color := color_of(ed.get("color")):
        out["color"] = color
    for k in ("vignette", "grain"):   # 0..1 of their most; none - not there
        if (x := round(_num(ed.get(k), 0, 1, 0), 2)) > 0:
            out[k] = x
    if out.get("grade") == "lut" and (m := round(_num(ed.get("lut_mix"), 0, 1, 1), 2)) < 1:
        out["lut_mix"] = m
    return out


def color_of(value: object) -> Optional[dict]:
    """A clip's reversible colour adjustment; neutral values stay absent for old project compatibility."""
    if not isinstance(value, dict):
        return None
    color = {"exposure": round(_num(value.get("exposure"), -1, 1, 0), 2),
             "contrast": round(_num(value.get("contrast"), 0.5, 1.5, 1), 2),
             "saturation": round(_num(value.get("saturation"), 0, 2, 1), 2),
             "temperature": round(_num(value.get("temperature"), -50, 50, 0), 1)}
    return color if color != {"exposure": 0, "contrast": 1, "saturation": 1, "temperature": 0} else None


TEMP = 0.12                         # temperature ±50: red and blue ±12%, against each other
LUMA = (0.2126, 0.7152, 0.0722)     # Rec.709: saturation turns about it


def color_filter(value: object) -> str:
    """FFmpeg filters for the editor's exposure, contrast, saturation and temperature controls - the numbers of the
    preview (frontend/src/lib/edit.ts colorSteps): per channel in·gain·contrast + (1 - contrast)/2, then the
    saturation as a matrix about luma."""
    color = color_of(value)
    if not color:
        return ""
    e, w, c, s = 2 ** color["exposure"], color["temperature"] / 50, color["contrast"], color["saturation"]
    out = ""
    gains = (e * (1 + TEMP * w) * c, e * c, e * (1 - TEMP * w) * c)
    if gains != (1, 1, 1) or c != 1:   # lutrgb clips to 0..255 itself
        out += ",lutrgb=" + ":".join(f"{ch}=val*{g:.5f}{(1 - c) / 2 * 255:+.3f}" for ch, g in zip("rgb", gains))
    if s != 1:
        m = [[LUMA[j] * (1 - s) + (s if i == j else 0) for j in range(3)] for i in range(3)]
        out += ",colorchannelmixer=" + ":".join(f"{o}{i}={m[a][b]:.5f}" for a, o in enumerate("rgb") for b, i in enumerate("rgb"))
    return out


def signature(ed: dict) -> str:
    """What the built video depends on: the shots, how they are cut, timed and joined, the sounds, the ducking."""
    parts = [[(c["file"], c["in"], c["out"], c["tr"], c["td"], c["speed"], c["vol"]) for c in ed["clips"]],
             [(x["file"], x["start"], x["in"], x["out"], x["vol"], x["fade_in"], x["fade_out"]) for x in ed.get("sounds") or []],
             ed.get("duck") or 0]
    if not parts[1] and not parts[2] and all(c["speed"] == 1 and c["vol"] == 1 for c in ed["clips"]):
        parts = [p[:5] for p in parts[0]]   # as stage A signed it: a video built then is still «built»
    if look := {k: ed[k] for k in ("grade", "lut", "match", "color", "vignette", "grain", "lut_mix") if ed.get(k)}:
        parts = [parts, look]   # only with a look: a video built before it is still «built»
    colors = [(c.get("id"), c["color"]) for c in ed["clips"] if c.get("color")]
    scene_colors = ed.get("scene_colors") or {}
    if colors or scene_colors:
        parts = [parts, {"clip_colors": colors, "scene_colors": scene_colors}]
    if ed.get("overlays"):   # only with them: a video built before stays «built»
        parts = [parts, {"overlays": [(o["file"], o["start"], o["in"], o["out"]) for o in ed["overlays"]]}]
    return hashlib.sha1(json.dumps(parts).encode()).hexdigest()[:12]


def _stats(src: str, a: float, b: float) -> Optional[tuple[list[float], list[float]]]:
    """A clip's colour between `a` and `b` seconds of its shot: the mean and spread of R, G, B (0-255) over a few
    small frames; None when it can't be read."""
    import numpy as np
    r = subprocess.run([config.FFMPEG, "-v", "error", "-ss", f"{a:.3f}", "-t", f"{max(0.1, b - a):.3f}", "-i", src,
                        "-vf", "fps=3,scale=96:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, creationflags=NO_WINDOW)
    px = np.frombuffer(r.stdout, np.uint8).reshape(-1, 3).astype(np.float64) if r.returncode == 0 and r.stdout else None
    if px is None or len(px) < 100:
        return None
    return px.mean(0).tolist(), (px.std(0) + 1e-3).tolist()


def _match_filters(clips: list[dict]) -> list[str]:
    """Per clip, a lutrgb taking its colour MATCH of the way to the average of the clips (mean and spread per channel);
    "" for a clip that can't be read."""
    stats = [_stats(c["src"], c["in"], c["out"]) for c in clips]
    ok = [s for s in stats if s]
    if not ok:
        return [""] * len(clips)
    mean = [sum(s[0][i] for s in ok) / len(ok) for i in range(3)]
    spread = [sum(s[1][i] for s in ok) / len(ok) for i in range(3)]
    out = []
    for s in stats:
        if not s:
            out.append("")
            continue
        ch = []
        for i, name in enumerate("rgb"):
            k = 1 + MATCH * (spread[i] / s[1][i] - 1)
            m = s[0][i] + MATCH * (mean[i] - s[0][i])
            ch.append(f"{name}='clip((val-{s[0][i]:.2f})*{k:.4f}+{m:.2f},0,255)'")
        out.append(",format=rgb24,lutrgb=" + ":".join(ch))
    return out


def cuts(ed: dict) -> list[int]:
    """The hard cuts (frame numbers in the built video) RIFE must not blend across: every cut that is not a seamless
    continuation. A dissolve is a blend already. An overlay («Поверх») cuts in and out where it stands."""
    out = [round(c["start"] * FPS) for k, c in enumerate(ed["clips"]) if k and c["tr"] in ("cut", "flash") and not c["seamless"]]
    total = round(ed["duration"] * FPS)
    for o in ed.get("overlays") or []:
        if o.get("src"):
            out += [f for f in (round(o["start"] * FPS), round(o["start"] * FPS) + o["frames"]) if 0 < f < total]
    return sorted(set(out))


def _ffmpeg(args: list[str], what: str = "") -> None:
    r = subprocess.run([config.FFMPEG, "-y", "-v", "error", *args], capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode:
        raise EngineError(f"ffmpeg ({what or i18n.L('монтаж', 'montage')}): " + (r.stderr or "").strip()[-800:])


def _script(parts: list[str], dest: Path) -> Path:
    """The filter graph in a file next to dest (120 clips do not fit a Windows command line)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    script = dest.with_suffix(".filter.txt")
    script.write_text(";".join(parts), encoding="utf-8")
    return script


def render(ed: dict, folder: Path, dest: Path, size: Optional[tuple[int, int]] = None) -> list[int]:
    """The clips -> one mp4, the picture with the scenes' sound (H.264 CRF 16, AAC), as render.assemble made it.
    `size`: the video's frame - a scene shot with another model (phase 11, another size) is scaled and cropped to it.
    -> the hard cuts."""
    clips = ed["clips"]
    if not ed["complete"]:
        raise EngineError(i18n.L("Не все сцены сняты — монтаж не собрать", "Not all scenes are shot: the montage can't be built"))
    c0 = clips[0]
    look = look_of(ed, folder)
    overlays = [o for o in ed.get("overlays") or [] if o.get("src")]   # one not shot yet is left out (its file is in the signature)
    if len(clips) == 1 and c0["in"] == 0 and abs(c0["out"] - c0["length"]) < FRAME / 2 and c0["speed"] == 1 and c0["vol"] == 1 and not size \
            and not look and not c0.get("color") and not c0.get("scene_color") and not overlays:
        shutil.copyfile(c0["src"], dest)
        return []
    fit = f",scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase:flags=lanczos,crop={size[0]}:{size[1]},setsar=1" if size else ""
    # in whole frames: a time in seconds is rounded (5.1667 for 124 frames), and an offset a hair past a frame's
    # start gave a dissolve one frame more than the montage counts (and the cuts for RIFE one frame off); a video
    # bound sits half a frame before the frame it means, so it can only pick that frame
    fr = lambda x: round(x * FPS)   # noqa: E731
    vt = lambda f: f"{max(0.0, (f - 0.5) / FPS):.6f}"   # noqa: E731
    at = lambda f: f"{f / FPS:.6f}"   # noqa: E731
    args, parts = [], []
    matched = _match_filters(clips) if look.get("match") and len(clips) > 1 else [""] * len(clips)
    for k, c in enumerate(clips):
        args += ["-i", c["src"]]   # a shot of this project, or of the storyboard a graph was made from
        a, b, n = fr(c["in"]), fr(c["out"]), c["frames"]
        e_in = EDGE_SEAMLESS if c.get("seamless") else EDGE
        e_out = EDGE_SEAMLESS if k < len(clips) - 1 and clips[k + 1].get("seamless") else EDGE
        fin = f",afade=t=in:st=0:d={e_in}" if k and c["tr"] in ("cut", "flash") else ""
        fout = f",afade=t=out:st={n / FPS - e_out:.6f}:d={e_out}" if k < len(clips) - 1 and clips[k + 1]["tr"] in ("cut", "flash") else ""
        flash = f",fade=t=in:st=0:d={FLASH / FPS:.6f}:color=white" if k and c["tr"] == "flash" else ""
        if c["speed"] == 1:
            pv, pa = "setpts=PTS-STARTPTS", "asetpts=PTS-STARTPTS"
        else:   # slower / faster: the frames follow, then exactly n of them (a last one repeated if the rate came short)
            pv = (f"setpts=(PTS-STARTPTS)/{c['speed']},fps={FPS},tpad=stop_mode=clone:stop=2,trim=end_frame={n},"
                  f"setpts=PTS-STARTPTS")
            pa = f"asetpts=PTS-STARTPTS,atempo={c['speed']},apad,atrim=0:{at(n)}"
        vol = f",volume={c['vol']}" if c["vol"] != 1 else ""
        grade = color_filter(c.get("color")) + color_filter(c.get("scene_color"))
        parts.append(f"[{k}:v]trim=start={vt(a)}:end={vt(b)},{pv},fps={FPS}{fit}{matched[k]}{grade}{flash},settb=AVTB,format=yuv420p[v{k}]")
        parts.append(f"[{k}:a]atrim=start={at(a)}:end={at(b)},{pa},aresample=48000,aformat=channel_layouts=stereo{vol}{fin}{fout}[a{k}]")
    v, a, length = "v0", "a0", clips[0]["frames"]
    for k in range(1, len(clips)):
        c = clips[k]
        n, td = c["frames"], fr(c["td"])
        if c["tr"] in ("cut", "flash") or not td:
            parts.append(f"[{v}][v{k}]concat=n=2:v=1:a=0[vj{k}]")
            parts.append(f"[{a}][a{k}]concat=n=2:v=0:a=1[aj{k}]")
            length += n
        else:
            kind = "fadeblack" if c["tr"] == "black" else "fade"
            parts.append(f"[{v}][v{k}]xfade=transition={kind}:duration={at(td)}:offset={vt(length - td)}[vj{k}]")
            parts.append(f"[{a}][a{k}]acrossfade=d={at(td)}[aj{k}]")
            length += n - td
        v, a = f"vj{k}", f"aj{k}"
    if overlays:   # «Поверх»: each piece over the joined picture on its frames (before the look, so the look covers it too)
        if size:
            w, h = size
        else:
            from .render import video_size
            w, h = video_size(Path(c0["src"])) or (0, 0)
        for j, o in enumerate(overlays):
            idx = len(clips) + j
            args += ["-i", o["src"]]
            oa, s0, n = fr(o["in"]), fr(o["start"]), o["frames"]
            parts.append(f"[{idx}:v]trim=start={vt(oa)}:end={vt(oa + n)},setpts=PTS-STARTPTS,fps={FPS},"
                         f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1,"
                         f"setpts=PTS+{at(s0)}/TB,format=yuv420p[o{j}]")
            parts.append(f"[{v}][o{j}]overlay=0:0:eof_action=pass:enable='between(t,{vt(s0)},{vt(s0 + n)})',format=yuv420p[vo{j}]")
            v = f"vo{j}"
    if look.get("grade"):   # the look over the whole video, frame for frame
        lut = (folder / look["lut"]).as_posix().replace(":", "\\:") if look["grade"] == "lut" else ""
        mix = look.get("lut_mix", 1) if lut else 1
        if mix < 1:   # the LUT part of the way: the graded picture blended over the one as it is
            parts.append(f"[{v}]split[gl0][gl1];[gl1]lut3d=file='{lut}'[gl2];[gl0][gl2]blend=all_mode=normal:all_opacity={mix},format=yuv420p[vg]")
        else:
            parts.append(f"[{v}]" + (f"lut3d=file='{lut}'" if lut else GRADES[look["grade"]]) + ",format=yuv420p[vg]")
        v = "vg"
    if grade := color_filter(look.get("color")):
        parts.append(f"[{v}]{grade.lstrip(',')},format=yuv420p[vgc]")
        v = "vgc"
    if look.get("vignette") or look.get("grain"):   # the film's finish: darker corners, a living grain (a new one each frame)
        fin = [f"vignette=angle={look['vignette'] * VIGNETTE_MAX:.4f}"] if look.get("vignette") else []
        fin += [f"noise=alls={round(look['grain'] * GRAIN_MAX)}:allf=t"] if look.get("grain") else []
        parts.append(f"[{v}]{','.join(fin)},format=yuv420p[vfin]")
        v = "vfin"
    script = _script(parts, dest)
    try:
        _ffmpeg(args + ["-/filter_complex", str(script), "-map", f"[{v}]", "-map", f"[{a}]",
                        "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest)])
    finally:
        script.unlink(missing_ok=True)
    return cuts(ed)


def needs_mix(ed: dict, track: Optional[dict], folder: Path) -> bool:
    return bool(ed.get("sounds")) or bool(track and (folder / track["file"]).exists())


def mix(ed: dict, folder: Path, video: Path, track: Optional[dict], dest: Path) -> None:
    """The sound of the video: the scenes' (as built, at the track's «звук сцен» when there is a track), the sounds
    from files where they stand, the track from its offset with its fades - quieter under the scenes' sound by
    `duck` (a sidechain compressor) - and a limiter. The picture is copied."""
    from . import music
    dur = music.duration(video)
    track = track if track and (folder / track["file"]).exists() else None
    t = music.settings(track) if track else None
    args, parts, mixed = ["-i", str(video)], [], []
    duck = ed.get("duck") or 0
    scene_vol = t["scene_volume"] if t else 1.0
    parts.append(f"[0:a]volume={scene_vol}" + (",asplit=2[s][sc]" if t and duck else "[s]"))
    mixed.append("[s]")
    if t:
        if t["offset"]:
            args += ["-ss", f"{t['offset']:.3f}"]
        args += ["-i", str(folder / track["file"])]
        m = (f"[1:a]volume={t['volume']},afade=t=in:st=0:d={t['fade_in']},apad,atrim=0:{dur:.3f},"
             f"afade=t=out:st={max(0.0, dur - t['fade_out']):.3f}:d={t['fade_out']},asetpts=PTS-STARTPTS")
        if duck:   # the track gives way where the scenes speak: up to 10:1 above -34 dB of their sound
            parts.append(f"{m}[m0]")
            parts.append(f"[m0][sc]sidechaincompress=threshold=0.02:ratio={1 + 9 * duck:.2f}:attack=20:release=400:makeup=1[m]")
        else:
            parts.append(f"{m}[m]")
        mixed.append("[m]")
    base = 2 if t else 1   # the inputs before the sounds: the video, the track
    for j, x in enumerate(ed.get("sounds") or []):
        k = base + j
        args += ["-i", str(folder / x["file"])]
        n = x["out"] - x["in"]
        if x["start"] >= dur or n <= 0:
            continue
        ms = round(x["start"] * 1000)
        fades = (f",afade=t=in:st=0:d={x['fade_in']}" if x["fade_in"] else "") + \
                (f",afade=t=out:st={max(0.0, n - x['fade_out']):.3f}:d={x['fade_out']}" if x["fade_out"] else "")
        parts.append(f"[{k}:a]atrim=start={x['in']:.3f}:end={x['out']:.3f},asetpts=PTS-STARTPTS,aresample=48000,"
                     f"aformat=channel_layouts=stereo,volume={x['vol']}{fades},adelay={ms}|{ms}[x{j}]")
        mixed.append(f"[x{j}]")
    parts.append(f"{''.join(mixed)}amix=inputs={len(mixed)}:duration=first:normalize=0,alimiter=limit=0.95[a]")
    script = _script(parts, dest)
    try:
        _ffmpeg(args + ["-/filter_complex", str(script), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "256k", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(dest)], i18n.L("звук", "sound"))
    finally:
        script.unlink(missing_ok=True)


# ---------- the waveform of a file, for the lanes ----------
PEAKS_PER_S = 50


def peaks(path: Path) -> list[int]:
    """The loudness of a file's sound, 50 values a second (0-255, the peak of each 20 ms), kept next to it in
    _peaks/<name>.json (a shot or a sound never changes once written)."""
    cache = path.parent / "_peaks" / f"{path.name}.json"
    st = path.stat()
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if c.get("size") == st.st_size:
            return c["peaks"]
    except (OSError, ValueError, KeyError):
        pass
    import array
    rate = 8000
    r = subprocess.run([config.FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                       capture_output=True, creationflags=NO_WINDOW)
    a = array.array("h", r.stdout)
    step = rate // PEAKS_PER_S
    out = [min(255, round(max((abs(v) for v in a[i:i + step]), default=0) / 128)) for i in range(0, len(a), step)]
    try:
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps({"size": st.st_size, "peaks": out}), encoding="utf-8")
    except OSError:
        pass
    return out
