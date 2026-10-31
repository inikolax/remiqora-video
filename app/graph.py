"""The graph. A project of type "graph" keeps its canvas in projects/<id>/graph.json: nodes
(id, type, position, data), edges (source + sourceHandle -> target + targetHandle) and `rev`. Shots live where the
storyboard keeps them (scenes/<key>.mp4 + .png, the same keys - render.scene_key), the rest under out/, pictures/,
frames/. What a node has made is never stored in the graph: its state is computed from its key, like render.preview,
so the canvas and the cache can't disagree. Only the LLM's results are stored (the writer's plan, a hero's look) -
the user edits them.

G1 (storyboard() at the bottom): a storyboard drawn as a graph, to look at.
G2-G5: evaluate() walks the graph and says what every node is (ready / to make / waiting / blocked / error) and its
key; run() is the queue's "graph" job: it makes what the chosen outputs need, LLM nodes never (they are marked stale -
the user presses «Переписать»), scenes before the assembly, Ref2VA shots next to each other (the two models take
turns in memory), an error stops only its own branch.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import checks, config, edit, i18n, jobs, music, post, projects, render, timings, videomodels
from .engine import graphs
from .engine.comfy import COMFY, EngineError
from .planner import grid, prompts

LENGTH_S = 5                 # a scene's seconds unless it says (`seconds`); a storyboard's scenes are all 5 s
MIN_S, MAX_S = 3, 15         # H3 is trained on 5-15 s; 3 s still holds one action
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------------------------------------------------------
# node types: ports (name -> port type; an input is single or multi), who does the work (the header's colour)
# ---------------------------------------------------------------------------------------------------------------
TYPES: dict[str, dict] = {
    "idea":    {"title": "Идея", "who": "user", "in": {}, "out": {"text": "text"}},
    "hero":    {"title": "Герой", "who": "writer", "in": {}, "out": {"look": "look", "image": "image"}},
    "writer":  {"title": "Сценарист", "who": "writer", "in": {"idea": ("text", False), "cast": ("look", True)}, "out": {}},
    "prompt":  {"title": "Промт", "who": "user", "in": {}, "out": {"text": "text"}},
    "photo":   {"title": "Фото", "who": "user", "in": {}, "out": {"image": "image"}},
    "picture": {"title": "Картинка", "who": "krea", "in": {"text": ("text", False), "ref": ("image", True)}, "out": {"image": "image"}},
    "scene":   {"title": "Сцена", "who": "h3", "in": {"prompt": ("text", False), "start": ("image", False),
                                                     "end": ("image", False), "faces": ("image", True), "lora": ("lora", True),
                                                     "clip": ("clip", False), "voice": ("audio", False)},
                "out": {"frame": "image", "clip": "clip"}},
    "v2v":     {"title": "Видео → видео", "who": "v2v", "in": {"clip": ("clip", False), "prompt": ("text", False),
                                                            "image": ("image", True), "lora": ("lora", True)},
                "out": {"clip": "clip"}},
    "facefix": {"title": "Лица", "who": "facefix", "in": {"clip": ("clip", False), "prompt": ("text", False)}, "out": {"clip": "clip"}},
    "frame":   {"title": "Кадр", "who": "ffmpeg", "in": {"clip": ("clip", False)}, "out": {"image": "image"}},
    "sound":   {"title": "Звук сцены", "who": "ffmpeg", "in": {"clip": ("clip", False)}, "out": {"audio": "audio"}},
    "lora":    {"title": "LoRA", "who": "user", "in": {}, "out": {"lora": "lora"}},
    "join":    {"title": "Склейка", "who": "ffmpeg", "in": {"clips": ("clip", True)}, "out": {"video": "video"}},
    "montage": {"title": "Монтаж", "who": "ffmpeg", "in": {"clips": ("clip", True)}, "out": {"video": "video"}},
    "track":   {"title": "Трек", "who": "user", "in": {}, "out": {"audio": "audio"}},
    "music":   {"title": "Музыка", "who": "ffmpeg", "in": {"video": ("video", False), "audio": ("audio", False)}, "out": {"video": "video"}},
    "output":  {"title": "Выход", "who": "ffmpeg", "in": {"video": ("video", False)}, "out": {}},
    "note":    {"title": "Заметка", "who": "none", "in": {}, "out": {}},
    "group":   {"title": "Группа", "who": "none", "in": {}, "out": {}},
}
# what run() makes, in this order of kinds: pictures feed starts, scenes feed everything after
# a FLUX.2 «Картинка» with reference pictures and no prompt
FLUX_NO_TEXT = ("The person in the first image: exactly the same face, hair and clothes. A new photograph of them, a different camera "
                "position and framing than the reference image; photorealistic, natural light.")
MAKES = ("picture", "scene", "v2v", "facefix", "sound", "frame", "join", "montage", "music", "output")
LLM_TYPES = ("writer", "hero")
LLM_BUTTONS = LLM_TYPES + ("prompt",)   # «Придумать реплики» of a prompt is a button too, never stale


# the node types' names in English (TYPES keeps the Russian ones)
_TITLES_EN = {"idea": "Idea", "hero": "Hero", "writer": "Writer", "prompt": "Prompt", "photo": "Photo", "picture": "Picture",
              "scene": "Scene", "v2v": "Video → video", "facefix": "Faces", "frame": "Frame", "sound": "Scene sound", "join": "Join",
              "montage": "Montage", "track": "Track", "music": "Music", "output": "Output", "note": "Note", "group": "Group"}


def type_title(t: str) -> str:
    """A node type's name in the interface's language."""
    return i18n.L(TYPES[t]["title"], _TITLES_EN.get(t, TYPES[t]["title"]))


def public_types() -> dict:
    return {k: {"title": type_title(k), "who": v["who"], "in": {p: {"type": t[0], "multi": t[1]} for p, t in v["in"].items()},
                "out": v["out"]} for k, v in TYPES.items()}


# ---------------------------------------------------------------------------------------------------------------
# the document
# ---------------------------------------------------------------------------------------------------------------
class Conflict(Exception):
    """The graph changed on the server (another tab, a job's result) since the client read it."""


def path_of(pid: str) -> Path:
    return projects.folder(pid) / "graph.json"


def empty() -> dict:
    return {"rev": 0, "nodes": [], "edges": []}


def load(pid: str) -> dict:
    p = path_of(pid)
    if not p.exists():
        return empty()
    return json.loads(p.read_text(encoding="utf-8"))


def _write(pid: str, g: dict) -> dict:
    p = path_of(pid)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return g


def clean(g: dict) -> dict:
    """Only known node types; only edges between existing ports of the same type; a single input keeps its last edge."""
    nodes = []
    for n in g.get("nodes") or []:
        if not isinstance(n, dict) or n.get("type") not in TYPES or not n.get("id"):
            continue
        pos = n.get("position") or {}
        nodes.append({"id": str(n["id"]), "type": n["type"],
                      "position": {"x": float(pos.get("x", 0)), "y": float(pos.get("y", 0))},
                      "data": n.get("data") if isinstance(n.get("data"), dict) else {}})
    by = {n["id"]: n for n in nodes}
    edges, single = [], {}
    for e in g.get("edges") or []:
        s, t = by.get(e.get("source")), by.get(e.get("target"))
        if not s or not t or s is t:
            continue
        sp, tp = e.get("sourceHandle"), e.get("targetHandle")
        out_t = TYPES[s["type"]]["out"].get(sp)
        inp = TYPES[t["type"]]["in"].get(tp)
        if not out_t or not inp or inp[0] != out_t:
            continue
        edge = {"id": str(e.get("id") or uuid.uuid4().hex[:8]), "source": s["id"], "sourceHandle": sp, "target": t["id"], "targetHandle": tp}
        if not inp[1]:
            single[(t["id"], tp)] = edge
        elif not any(x["source"] == s["id"] and x["sourceHandle"] == sp and x["target"] == t["id"] and x["targetHandle"] == tp for x in edges):
            edges.append(edge)
    return {"rev": int(g.get("rev") or 0), "nodes": nodes, "edges": edges + list(single.values())}


def save(pid: str, g: dict, rev: Optional[int]) -> dict:
    """The client's graph; `rev` is the one it read. A newer graph on disk (a job wrote an LLM result, another tab)
    -> Conflict, the client takes the server's."""
    cur = load(pid)
    if rev is not None and rev != cur.get("rev", 0):
        raise Conflict()
    g = clean(g)
    g["rev"] = cur.get("rev", 0) + 1
    return _write(pid, g)


def update(pid: str, fn) -> dict:
    """A server-side change (a job's result, «Развернуть в сцены»): read the newest, change it, rev + 1."""
    g = load(pid)
    fn(g)
    g = clean(g)
    g["rev"] = load(pid).get("rev", 0) + 1
    return _write(pid, g)


def node(g: dict, nid: str) -> Optional[dict]:
    return next((n for n in g["nodes"] if n["id"] == nid), None)


# ---------------------------------------------------------------------------------------------------------------
# evaluation: what every node is and its key
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Art:
    state: str                       # ready | todo | wait | blocked | error | stale | empty | idle
    key: Optional[str] = None
    path: Optional[Path] = None      # an image / the clip's mp4 / a video
    png: Optional[Path] = None       # a scene's last frame
    text: Optional[str] = None
    loras: list = field(default_factory=list)
    clips: list = field(default_factory=list)   # a join's: [(mp4, kind, scene id)]
    cuts: list = field(default_factory=list)    # hard cuts of a video (RIFE must not blend across them)
    error: Optional[str] = None
    refs: bool = False               # a scene shot by Ref2VA
    start_of: Optional[str] = None   # a scene: the scene whose last frame it starts from
    seconds: float = 0               # a video's length
    takes: list = field(default_factory=list)   # a scene: [{seed, key, cached}]
    lines: list = field(default_factory=list)   # a prompt's spoken lines [{who, text, how}]; a scene weaves them in
    picture: Optional[str] = None    # a prompt: its text in a picture's form (text_picture), when it feeds a «Картинка» and a scene
    images: list = field(default_factory=list)   # a picture by FLUX.2 Klein: its reference pictures (the «образцы» input), in order
    woven: Optional[str] = None      # a scene: its prompt with the lines in it (only when it has lines)
    alpha: Optional[Path] = None     # «Видео → видео» with a matte LoRA: the clip with a transparent background (WebM)
    warn: Optional[str] = None       # made, but not quite as wired (a v2v's pictures its engine can't take)
    model: Optional[str] = None      # a scene: the model that shoots it (a reference LoRA's, else the graph's)
    ref: Optional[dict] = None       # a scene with a reference LoRA: how it is made (_evaluate_ref_scene)
    voice: Optional[dict] = None     # a voice scene, shot: how alike its voice is to the sample (voice.py)
    checks: Optional[list] = None    # a scene, shot: what the clip's checks found (checks.py)
    note: Optional[dict] = None      # «Лица», made: what it found and fixed (facefix.py)

    def public(self, folder: Path) -> dict:
        rel = lambda p: rel_path(folder, p)  # noqa: E731
        return {"state": self.state, "key": self.key, "file": rel(self.path), "png": rel(self.png), "error": self.error,
                "refs": self.refs, "seconds": self.seconds, "start_of": self.start_of,
                "takes": [{**t, "png": rel(t.get("png"))} for t in self.takes], **({"text": self.woven} if self.woven else {}),
                **({"alpha": rel(self.alpha)} if self.alpha else {}), **({"warn": self.warn} if self.warn else {}),
                **({"model": self.model, "ref_mode": self.ref["mode"]} if self.ref else {}),
                **({"voice": self.voice} if self.voice else {}), **({"checks": self.checks} if self.checks else {}),
                **({"note": self.note} if self.note else {})}


def rel_path(folder: Path, p: Optional[Path]) -> Optional[str]:
    """A file as the page asks for it: its path in the project, or "@<project>/…" for a shot in the cache of the
    storyboard this graph came from."""
    if not p:
        return None
    try:
        return p.relative_to(folder).as_posix()
    except ValueError:
        return "@" + p.relative_to(projects.ROOT).as_posix()


class Ctx:
    """One evaluation: the project, its graph, the quality; `failed` - nodes a run could not make (their branch is
    blocked, the others go on)."""

    def __init__(self, proj: dict, g: dict, quality: Optional[str] = None, failed: Optional[dict] = None):
        self.proj, self.g = proj, g
        self.pid = proj["id"]
        self.folder = projects.folder(self.pid)
        st = proj.get("settings") or {}
        self.quality = quality or st.get("quality", "draft")
        self.aspect = st.get("aspect", "16:9")
        self.settings = {"aspect": self.aspect, "quality": self.quality, "video_model": st.get("video_model"), "size": st.get("size")}
        self.card = videomodels.of(st)   # phase 10: the project's video model
        self.own = videomodels.own_size(self.settings, self.card)   # the frame set by hand, else None
        self.w, self.h = self.own or render.size(self.settings)
        self.auto_w, self.auto_h = videomodels.size(self.card, graphs.ASPECTS[self.aspect], self.quality)
        # a «Картинка» is drawn at the final frame whatever the quality (2026-10-29): the draft and the final scene start
        # from the same picture (a draft one scaled down), and a still costs the same ~2 s at either size
        self.pw, self.ph = render.size({**self.settings, "quality": "final"})
        self.failed = failed or {}
        self.by = {n["id"]: n for n in g["nodes"]}
        self.ins: dict[str, dict[str, list[tuple[str, str]]]] = {n["id"]: {} for n in g["nodes"]}
        for e in g["edges"]:
            if e["target"] in self.ins:
                self.ins[e["target"]].setdefault(e["targetHandle"], []).append((e["source"], e["sourceHandle"]))
        # where cached shots may also be: the storyboard projects this graph was made from (their keys are the same)
        self.caches = [self.folder / "scenes"] + [projects.ROOT / p / "scenes" for p in st.get("cache_from") or []
                                                   if (projects.ROOT / p / "scenes").exists()]
        self.memo: dict[str, Art] = {}

    def inputs(self, nid: str, port: str) -> list[tuple[str, str]]:
        return self.ins.get(nid, {}).get(port, [])

    def cached_shot(self, key: str) -> Optional[tuple[Path, Path]]:
        for d in self.caches:
            mp4, png = render.shot_paths(d, key)
            if mp4.exists() and png.exists():
                return mp4, png
        return None


def _picture_loras(d: dict, flux: bool) -> list[dict]:
    """A «Картинка» node's LoRA: [{id, strength}] as stored, without empty ones, in a stable order - Krea's (d0/…) or
    FLUX.2 Klein's (flux2:d0/…, loras.py); the node keeps both and the model drawing takes its own."""
    out = []
    for it in d.get("loras") or []:
        if isinstance(it, dict) and it.get("id") and str(it["id"]).startswith("flux2:") == flux:
            try:
                out.append({"id": str(it["id"]), "strength": round(float(it.get("strength", 0.8)), 2)})
            except (TypeError, ValueError):
                continue
    return sorted(out, key=lambda x: x["id"])


def _krea_loras(d: dict) -> list[dict]:
    return _picture_loras(d, False)


def _flux_loras(d: dict) -> list[dict]:
    return _picture_loras(d, True)


def _sha(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _upstream(c: Ctx, arts: list[Art]) -> Optional[Art]:
    """The worst of the inputs: blocked / waiting, or None when all are ready."""
    if any(a.state in ("error", "blocked") for a in arts):
        return Art("blocked")
    if any(a.state != "ready" for a in arts):
        return Art("wait")
    return None


def _out(c: Ctx, nid: str, port: str) -> Art:
    """What a node gives on one of its outputs (a scene: `frame` is its last frame, `clip` its shot)."""
    n = c.by[nid]
    if n["type"] == "hero" and port == "image":   # the photo, described or not
        a = evaluate_node(c, nid)
        return Art("ready", path=a.path, key=_sha(render.file_sha(a.path))) if a.path else Art("error", error=i18n.L("у героя нет фото", "the hero has no photo"))
    a = evaluate_node(c, nid)
    if a.state != "ready":
        return a
    if n["type"] == "scene" and port == "frame":
        return Art("ready", key=a.key, path=a.png, start_of=nid)
    if n["type"] == "frame" and n["data"].get("at") in (None, "", "last"):
        return Art("ready", key=a.key, path=a.path, start_of=a.start_of)
    return a


def seconds_of(n: dict) -> int:
    """A scene's length: its own `seconds` (3-15), 5 when it says nothing."""
    try:
        return max(MIN_S, min(MAX_S, int(n["data"].get("seconds") or LENGTH_S)))
    except (TypeError, ValueError):
        return LENGTH_S


def seed_of(n: dict) -> int:
    d = n["data"]
    takes = d.get("takes") or []
    if takes:
        return int(takes[min(int(d.get("take") or 0), len(takes) - 1)])
    return int(d.get("seed") or 1)


def evaluate_node(c: Ctx, nid: str, _stack: Optional[set] = None) -> Art:
    if nid in c.memo:
        return c.memo[nid]
    stack = _stack or set()
    if nid in stack:
        return Art("error", error=i18n.L("цикл: узел зависит сам от себя", "a loop: the node depends on itself"))
    stack.add(nid)
    c.memo[nid] = a = _evaluate(c, c.by[nid], stack)
    stack.discard(nid)
    f = c.failed.get(nid)
    if f and a.state == "todo" and (not isinstance(f, dict) or f.get("key") == a.key):   # fixed since: the key is new
        c.memo[nid] = a = Art("error", key=a.key, error=f["error"] if isinstance(f, dict) else f)
    return a


def _evaluate(c: Ctx, n: dict, stack: set) -> Art:
    t, d, nid = n["type"], n["data"], n["id"]
    ins = lambda port: [_out(c, s, sp) if s not in stack else Art("error", error=i18n.L("цикл", "a loop")) for s, sp in c.inputs(nid, port)]  # noqa: E731

    if t in ("note", "group"):
        return Art("idle")
    if t in ("prompt", "idea"):
        text = (d.get("text") or "").strip()
        lines = [x for x in (prompts.clean_line(ln) for ln in d.get("lines") or [] if isinstance(ln, dict)) if x] if t == "prompt" else []
        if not text:
            return Art("error", error=i18n.L("пустой текст", "empty text"))
        return Art("ready", text=text, key=_sha(text, lines) if lines else _sha(text), lines=lines,
                   picture=(d.get("text_picture") or "").strip() or None)
    if t == "photo":
        p = c.folder / d["file"] if d.get("file") else None
        if not p or not p.exists():
            return Art("error", error=i18n.L("нет фото", "no photo"))
        return Art("ready", path=p, key=_sha(render.file_sha(p)))
    if t == "hero":
        p = c.folder / d["photo"] if d.get("photo") else None
        state = "ready" if (d.get("en") or "").strip() else ("empty" if not p else "stale")
        return Art(state, path=p if p and p.exists() else None, text=(d.get("en") or "").strip(),
                   error=None if state == "ready" else i18n.L("внешность не описана", "the look is not described"))
    if t == "writer":
        if not d.get("plan"):
            return Art("empty")
        return Art("stale" if d.get("sig") != writer_sig(c, n) else "ready")
    if t == "lora":
        items = [{"id": x["id"], "strength": float(x.get("strength", 0.8))} for x in d.get("items") or [] if x.get("id")]
        return Art("ready", loras=items, key=_sha(items))
    if t == "track":
        p = c.folder / d["file"] if d.get("file") else None
        if not p or not p.exists():
            return Art("error", error=i18n.L("нет файла трека", "no track file"))
        return Art("ready", path=p, key=music.signature(c.folder, {"file": d["file"]}))

    if t == "picture":
        src = ins("text")
        if src:
            if (u := _upstream(c, src)):
                return u
            text = src[0].picture or src[0].text   # a prompt that feeds a scene too: its picture text, a still's
        else:
            text = (d.get("prompt") or "").strip()
        # Krea 2 draws from the text alone (its node has no «образцы»); FLUX.2 Klein from the text, the pictures on
        # «образцы» (picture.edit), or both - pictures without a text make a new photo of the first one's person
        refs = ins("ref") if d.get("model") == "flux2" else []
        if (u := _upstream(c, refs)):
            return u
        images = [a.path for a in refs if a.path][:3]
        if not text and images:
            text = FLUX_NO_TEXT
        if not text:
            return Art("error", error=i18n.L("нет промта картинки", "no picture prompt"))
        if d.get("model") == "flux2":
            fl = _flux_loras(d)
            key = _sha("flux2", text, int(d.get("seed") or 1), c.pw, c.ph, [render.file_sha(p) for p in images], config.FLUX2_UNET,
                       *(["steps", config.FLUX2_STEPS] if config.FLUX2_STEPS != 4 else []), *(["lora", fl] if fl else []))   # the default's keys stay as they were
            p = c.folder / "pictures" / f"{key}.png"
            return Art("ready" if p.exists() else "todo", key=key, path=p, text=text, images=images, loras=fl)
        kl = _krea_loras(d)
        # the worker and its model (sd.cpp's pictures before 2026-10-23 had neither: they are drawn again), the LoRA
        # only when there are any
        key = _sha("krea2", text, int(d.get("seed") or 1), c.pw, c.ph, *((["lora", kl]) if kl else []), "worker", config.KREA_UNET,
                   *(["steps", config.KREA_STEPS] if config.KREA_STEPS != 8 else []))   # the default's keys stay as they were
        p = c.folder / "pictures" / f"{key}.png"
        return Art("ready" if p.exists() else "todo", key=key, path=p, text=text, loras=kl)

    if t == "scene":
        pr, start, faces, lo, end = ins("prompt"), ins("start"), ins("faces"), ins("lora"), ins("end")
        if (u := _upstream(c, pr + start + faces + lo + end)):
            return u
        loras = [x for a in lo for x in a.loras]
        from . import loras as lora_lib
        refl = [x for x in loras if (i := lora_lib.get(x["id"])) and i.v2v]
        if refl:   # a LoRA that reads a clip or a voice: the scene is made its way
            return _evaluate_ref_scene(c, n, ins, refl, [x for x in loras if x not in refl])
        if not pr:
            return Art("error", error=i18n.L("нет промта: подключите узел «Промт»", "no prompt: connect a «Prompt» node"))
        st = start[0].path if start else None
        en = end[0].path if end and c.card.ends else None   # flf2v: the scene comes to this picture (LTX)
        refs = [a.path for a in faces if a.path] if c.card.refs else []
        fit = render.start_crop(st, c.w, c.h, "continue" if start and start[0].start_of else "new")   # a photo's face
        secs = min(seconds_of(n), c.card.max_seconds)   # the model shoots no longer than this
        length = videomodels.frames(c.card, secs)
        text = scene_text(c, nid)
        takes = []
        for s in [int(x) for x in d.get("takes") or []] or [seed_of(n)]:
            k = render.scene_key(text, s, c.w, c.h, length, loras, st, refs, c.card.id, end=en, fit=fit)
            hit = c.cached_shot(k)
            takes.append({"seed": s, "key": k, "cached": bool(hit), "png": hit[1] if hit else None})
        seed = seed_of(n)
        key = render.scene_key(text, seed, c.w, c.h, length, loras, st, refs, c.card.id, end=en, fit=fit)
        hit = c.cached_shot(key)
        a = Art("ready" if hit else "todo", key=key, text=text, loras=loras, refs=bool(refs), takes=takes,
                start_of=start[0].start_of if start else None, seconds=secs, woven=text if pr[0].lines else None)
        if c.inputs(nid, "clip") or c.inputs(nid, "voice"):
            a.warn = i18n.L("входы «сцена» и «голос» читает только LoRA по образцу (во входе «LoRA»): эта сцена снимется без них",
                            "only a sample LoRA (in the «LoRA» input) reads the «scene» and «voice» inputs: this scene will be shot without them")
        elif end and not c.card.ends:
            a.warn = i18n.L(f"{c.card.name} не умеет приходить к кадру: вход «конец» возьмёт только LTX — сцена снимется без него",
                            f"{c.card.name} can't end on a frame: only LTX takes the «end» input — the scene will be shot without it")
        if hit:
            a.path, a.png = hit
            a.checks = checks.saved(a.path)
        else:
            a.path, a.png = render.shot_paths(c.folder / "scenes", key)
        return a

    if t == "v2v":
        return _evaluate_v2v(c, n, ins)

    if t == "facefix":   # the clip's far faces made sharp (facefix.py): the key - the clip, the settings, the models, the algorithm
        from . import facefix
        src = ins("clip")
        if not src:
            return Art("error", error=i18n.L("нет клипа на входе: подключите «сцену» Сцены", "no clip at the input: connect a Scene's «scene»"))
        pr = ins("prompt")
        if (u := _upstream(c, src + pr)):
            return u
        mode = d.get("mode") if d.get("mode") in facefix.MODES else "far"
        strength = round(min(1.0, max(0.0, float(d.get("strength", 1.0)))), 2)
        seed = int(d.get("seed") or 1)
        text = facefix.prompt_of(pr[0].text if pr else d.get("prompt") or "")
        key = _sha("facefix", src[0].key, mode, strength, seed, text, facefix.VERSION,
                   [config.LTX23_CKPT, config.LTX23_CLIP, config.LTX23_LORA, config.KREA_UNET, config.KREA_CLIP, config.KREA_VAE])
        p = c.folder / "out" / f"facefix_{key}.mp4"
        ready = p.exists() and p.with_suffix(".png").exists()
        return Art("ready" if ready else "todo", key=key, path=p, png=p.with_suffix(".png"), seconds=src[0].seconds, text=text,
                   note=facefix.saved(p) if ready else None)

    if t == "sound":   # a shot scene's sound: a hero's voice for the next scene's «голос» (ID-LoRA), or a track
        src = ins("clip")
        if not src:
            return Art("error", error=i18n.L("нет сцены на входе: подключите выход «сцена» Сцены", "no scene at the input: connect a Scene's «scene» output"))
        if (u := _upstream(c, src)):
            return u
        voice = d.get("voice", True) is not False
        key = _sha("sound", src[0].key, "vocals" if voice else "all")
        p = c.folder / "out" / f"sound_{key}.wav"
        return Art("ready" if p.exists() else "todo", key=key, path=p, seconds=src[0].seconds)

    if t == "frame":
        src = ins("clip")
        if not src:
            return Art("error", error=i18n.L("нет сцены на входе", "no scene at the input"))
        if (u := _upstream(c, src)):
            return u
        at = d.get("at")
        scene_art = evaluate_node(c, c.inputs(nid, "clip")[0][0])
        if at in (None, "", "last"):
            return Art("ready", key=scene_art.key, path=scene_art.png, start_of=c.inputs(nid, "clip")[0][0])
        at = max(0.0, min(float(at), (scene_art.seconds or LENGTH_S) - 0.05))
        key = _sha("frame", src[0].key, round(at, 2))
        p = c.folder / "frames" / f"{key}.png"
        return Art("ready" if p.exists() else "todo", key=key, path=p)

    if t == "join":
        srcs = c.inputs(nid, "clips")
        if not srcs:
            return Art("error", error=i18n.L("нет сцен на входе", "no scenes at the input"))
        ids = join_order(c, nid)
        arts = [_out(c, s, "clip") for s in ids]
        if (u := _upstream(c, arts)):
            return u
        clips = []
        for k, (s, a) in enumerate(zip(ids, arts)):
            kind = "continue" if k and a.start_of and a.start_of == ids[k - 1] else "new"
            clips.append((a.path, kind, s))
        key = _sha("join", [(a.key, cl[1]) for a, cl in zip(arts, clips)])
        p = c.folder / "out" / f"join_{key}.mp4"
        cuts = _cuts(p)
        return Art("ready" if p.exists() and cuts is not None else "todo", key=key, path=p, clips=clips, cuts=cuts or [],
                   seconds=sum(a.seconds for a in arts))

    if t == "montage":
        if not c.inputs(nid, "clips"):
            return Art("error", error=i18n.L("нет сцен на входе", "no scenes at the input"))
        arts = [_out(c, s, "clip") for s in join_order(c, nid)]
        if (u := _upstream(c, arts)):
            return u
        ed = montage_of(c, nid)
        if not ed["complete"]:
            return Art("error", error=i18n.L("в монтаже дубль, который ещё не снят: снимите его или верните дубль сцены",
                                         "the montage has a take not shot yet: shoot it or switch the scene back to its take"))
        key = _sha("montage", edit.signature(ed))
        p = c.folder / "out" / f"montage_{key}.mp4"
        cuts = _cuts(p)
        return Art("ready" if p.exists() and cuts is not None else "todo", key=key, path=p, cuts=cuts or [], seconds=ed["duration"])

    if t == "music":
        v, au = ins("video"), ins("audio")
        if not v or not au:
            return Art("error", error=i18n.L("нужны ролик и трек", "needs a video and a track"))
        if (u := _upstream(c, v + au)):
            return u
        track = {"file": rel_path(c.folder, au[0].path), **{k: d[k] for k in music.DEFAULTS if k in d}}
        key = _sha("music", v[0].key, music.signature(c.folder, track))
        p = c.folder / "out" / f"music_{key}.mp4"
        return Art("ready" if p.exists() else "todo", key=key, path=p, cuts=v[0].cuts, seconds=v[0].seconds)

    if t == "output":
        v = ins("video")
        if not v:
            return Art("error", error=i18n.L("нет ролика на входе", "no video at the input"))
        if (u := _upstream(c, v)):
            return u
        out = post.output_of({"output": d.get("output") or {"size": "1080p"}})
        if not post.tag(out):   # «как снято»: the input itself
            return Art("ready", key=v[0].key, path=v[0].path, seconds=v[0].seconds)
        key = _sha("output", v[0].key, out, c.aspect)
        p = c.folder / "out" / f"{key}.mp4"
        return Art("ready" if p.exists() else "todo", key=key, path=p, cuts=v[0].cuts, seconds=v[0].seconds)
    return Art("idle")


def v2v_lora(d: dict):
    """A «Видео → видео» node's LoRA (loras.LoraInfo) and its profile, or (None, why not)."""
    from . import loras as lora_lib, v2v
    lid = d.get("lora")
    info = lora_lib.get(lid) if lid else None
    if not info:
        return None, (i18n.L("выберите LoRA «видео → видео»", "choose a «video → video» LoRA") if not lid
                      else i18n.L("LoRA не найдена — её убрали из папки?", "LoRA not found — was it removed from the folder?"))
    if not info.v2v:
        return None, i18n.L(f"«{info.name}» — обычная LoRA, клип она не читает: её место во входе «LoRA» сцены",
                            f"«{info.name}» is a plain LoRA, it doesn't read a clip: it goes into a scene's «LoRA» input")
    prof = v2v.profile(info)
    if prof["reads"] != "clip":
        return None, i18n.L(f"«{info.name}» читает фото и голос, а не клип: её место во входе «LoRA» Сцены",
                            f"«{info.name}» reads a photo and a voice, not a clip: it goes into a Scene's «LoRA» input")
    return info, prof


def _evaluate_v2v(c: Ctx, n: dict, ins) -> Art:
    """The clip made again by a LoRA that reads it (v2v.py): ready when its file is there; the key - the clip's, the
    LoRA, its profile, the prompt and pictures it really gets, the plain LoRA on top, the seed."""
    from . import loras as lora_lib, v2v
    d, nid = n["data"], n["id"]
    src = ins("clip")
    if not src:
        return Art("error", error=i18n.L("нет клипа на входе: подключите «клип» сцены", "no clip at the input: connect a scene's «clip»"))
    pr, pics, lo = ins("prompt"), ins("image"), ins("lora")
    if (u := _upstream(c, src + pr + pics + lo)):
        return u
    info, prof = v2v_lora(d)
    if not info:
        return Art("error", error=prof)
    text = v2v.prompt_of(prof, pr[0].text if pr else d.get("prompt") or "")
    if prof["prompt"] == "required" and not (pr[0].text if pr else (d.get("prompt") or "").strip()) and not prof["template"]:
        return Art("error", error=i18n.L("этой LoRA нужен промт: что сделать с клипом", "this LoRA needs a prompt: what to do with the clip"))
    eng = prof["engine"]
    pictures = [a.path for a in pics if a.path] if eng == "h3" else []
    extra = sorted(({"id": x["id"], "strength": round(float(x["strength"]), 3)} for a in lo
                    for x in lora_lib.for_model(a.loras, eng)), key=lambda x: x["id"])
    strength, guide, seed = round(float(d.get("strength", 1.0)), 3), round(float(d.get("guide", 1.0)), 3), int(d.get("seed") or 1)
    card = videomodels.card(eng)
    weights = [config.H3_REF_UNET, config.H3_REF_LORA, config.H3_CLIP, config.H3_VAE, graphs.REF_STEPS] if eng == "h3" else \
        [getattr(config, k) for k in card.keys]
    key = _sha("v2v", src[0].key, info.id, info.size_mb, strength, guide if eng != "h3" else None, seed, text,
               [render.file_sha(p) for p in pictures], extra, v2v.key_of(prof), weights)
    p = c.folder / "out" / f"v2v_{key}.mp4"
    alpha = p.with_suffix(".webm") if prof["out"] == "matte" else None
    ready = p.exists() and p.with_suffix(".png").exists() and (not alpha or alpha.exists())
    warn = i18n.L("картинки на входе: LTX их не берёт, только H3 Ref2VA",
                  "pictures at the input: LTX doesn't take them, only H3 Ref2VA") if pics and eng != "h3" else None
    return Art("ready" if ready else "todo", key=key, path=p, png=p.with_suffix(".png"), text=text, seconds=src[0].seconds,
               loras=extra, alpha=alpha, warn=warn)


def _evaluate_ref_scene(c: Ctx, n: dict, ins, refl: list[dict], plain: list[dict]) -> Art:
    """A Scene with a reference LoRA (its profile: v2v.py): the LoRA's model shoots it, whatever the graph's is, and
    reads what its profile says. reads clip - the «клип» input made again (v2v.make) into scenes/<key>.mp4 + .png, the
    clip's length and frame (times the profile's scale), the prompt optional; reads voice - ID-LoRA: LTX 2.3 from the
    «старт» photo, with the voice of the «голос» input's piece (`voice_from`, `voice_secs`), the scene's seconds.
    Either way a shot like a scene's: takes, the montage, a continuation from its last frame."""
    from . import loras as lora_lib, v2v
    d, nid = n["data"], n["id"]
    if len(refl) > 1:
        return Art("error", error=i18n.L("две LoRA по образцу в одной сцене — оставьте одну (обычные можно рядом)",
                                         "two sample LoRAs in one scene — keep one (plain ones can go alongside)"))
    item = refl[0]
    info = lora_lib.get(item["id"])
    prof = v2v.profile(info)
    eng = prof["engine"]
    card = videomodels.card(eng)
    strength, seed = round(float(item.get("strength", 1.0)), 3), seed_of(n)
    seeds = [int(x) for x in d.get("takes") or []] or [seed]
    start, faces, clip_in, voice_in = ins("start"), ins("faces"), ins("clip"), ins("voice")
    pr = c.inputs(nid, "prompt")
    pa = _out(c, *pr[0]) if pr and pr[0][0] in c.by else None
    unused = []

    if prof["reads"] == "clip":
        if not clip_in:
            return Art("error", error=i18n.L(f"«{info.name}» читает клип: подключите выход «сцена» другой Сцены во вход «сцена»",
                                             f"«{info.name}» reads a clip: connect another Scene's «scene» output to the «scene» input"))
        if (u := _upstream(c, clip_in)):
            return u
        text = v2v.prompt_of(prof, scene_text(c, nid) or "")
        if prof["prompt"] == "required" and not (pa and pa.text) and not prof["template"]:
            return Art("error", error=i18n.L("этой LoRA нужен промт: что сделать с клипом", "this LoRA needs a prompt: what to do with the clip"))
        pics = [a.path for a in faces if a.path] if eng == "h3" else []
        extra = sorted(({"id": x["id"], "strength": round(float(x["strength"]), 3)} for x in lora_lib.for_model(plain, eng)),
                       key=lambda x: x["id"])
        guide = round(float(d.get("guide", 1.0)), 3)
        weights = [config.H3_REF_UNET, config.H3_REF_LORA, config.H3_CLIP, config.H3_VAE, graphs.REF_STEPS] if eng == "h3" else \
            [getattr(config, k) for k in card.keys]
        shas = [render.file_sha(p) for p in pics]

        def key_for(s: int) -> str:   # the «Видео → видео» key's parts, as a scene's
            return _sha("v2v-scene", clip_in[0].key, info.id, info.size_mb, strength, guide if eng != "h3" else None, s, text, shas,
                        extra, v2v.key_of(prof), weights)
        unused += [i18n.L("«старт»", "«start»")] if start else []
        unused += [i18n.L("«голос»", "«voice»")] if voice_in else []
        unused += [i18n.L("«лица»", "«faces»")] if faces and eng != "h3" else []
        ref = {"mode": "clip", "info": info, "prof": prof, "strength": strength, "guide": guide, "pics": pics, "extra": extra,
               "clip": clip_in[0]}
        a = _ref_art(c, key_for, seeds, seed, text=text, seconds=clip_in[0].seconds, model=eng, ref=ref, loras=extra)
        if prof["out"] == "matte":
            a.alpha = a.path.with_suffix(".webm")
            if a.state == "ready" and not a.alpha.exists():
                a.state = "todo"
    else:   # voice: ID-LoRA
        if not start:
            return Art("error", error=i18n.L(f"«{info.name}» берёт лицо с фото: подключите «Фото» героя во вход «старт»",
                                             f"«{info.name}» takes the face from a photo: connect the hero's «Photo» to the «start» input"))
        if not voice_in:
            return Art("error", error=i18n.L(f"«{info.name}» берёт голос с образца: подключите «Трек» с речью во вход «голос»",
                                             f"«{info.name}» takes the voice from a sample: connect a «Track» with speech to the «voice» input"))
        if (u := _upstream(c, voice_in)):
            return u
        if not pa or not pa.text:
            return Art("error", error=i18n.L("нет промта: подключите узел «Промт» — что в кадре и что герой говорит",
                                         "no prompt: connect a «Prompt» node — what is in the frame and what the hero says"))
        text = v2v.id_prompt(pa.text, pa.lines)
        secs = min(seconds_of(n), card.max_seconds)
        length = videomodels.frames(card, secs)
        w, h = render.size(c.settings, card)
        st = start[0].path
        fit = render.start_crop(st, w, h, "continue" if start[0].start_of else "new", tight=True)   # the face, close
        vref = {"lora": {"id": info.id, "strength": strength}, "voice": voice_in[0].path,
                "from": max(0.0, float(d.get("voice_from") or 0)), "secs": float(d.get("voice_secs") or prof["voice_secs"]),
                "identity": prof["identity"]}

        def key_for(s: int) -> str:
            return render.scene_key(text, s, w, h, length, plain, st, [], card.id, ref=vref, fit=fit)
        unused += [i18n.L("«сцена»", "«scene»")] if clip_in else []
        unused += [i18n.L("«лица»", "«faces»")] if faces else []
        ref = {"mode": "voice", "voice": vref, "w": w, "h": h, "length": length, "plain": plain}
        a = _ref_art(c, key_for, seeds, seed, text=text, seconds=secs, model=eng, ref=ref, loras=plain,
                     start_of=start[0].start_of)
        a.woven = text
        if a.state == "ready":
            from . import voice
            a.voice = voice.measured(a.path, vref["voice"], vref["from"], vref["secs"])
    if unused:
        a.warn = i18n.L(f"{', '.join(unused)}: «{info.name}» их не читает — сцена снимется без них",
                        f"{', '.join(unused)}: «{info.name}» doesn't read them — the scene will be shot without them")
    return a


def _ref_art(c: Ctx, key_for, seeds: list[int], seed: int, **kw) -> Art:
    """A reference scene's Art: its takes and its shot, here or in a cache, as a scene's."""
    takes = []
    for s in seeds:
        k = key_for(s)
        hit = c.cached_shot(k)
        takes.append({"seed": s, "key": k, "cached": bool(hit), "png": hit[1] if hit else None})
    key = key_for(seed)
    hit = c.cached_shot(key)
    a = Art("ready" if hit else "todo", key=key, takes=takes, **kw)
    a.path, a.png = hit if hit else render.shot_paths(c.folder / "scenes", key)
    a.checks = checks.saved(a.path) if hit else None
    return a


def scene_text(c: Ctx, nid: str) -> Optional[str]:
    """What H3 gets as a scene's prompt: its «Промт»'s text with the spoken lines woven in for the scene's length
    (prompts.weave_lines; without lines - the text as it is). None: no prompt or an empty one."""
    pr = c.inputs(nid, "prompt")
    a = _out(c, *pr[0]) if pr and pr[0][0] in c.by else None
    if not a or a.state != "ready":
        return None
    return prompts.weave_lines(a.text, a.lines, seconds_of(c.by[nid]), i18n.plan_lang_name(c.proj)) if a.lines else a.text


def montage_items(c: Ctx, nid: str) -> list[dict]:
    """A «Монтаж» node's scenes for edit.lay, in the order of its inputs: a chain is a run of scenes each starting
    from the last frame of the one before it; a scene that starts from the frame of an earlier one of them goes on
    from it (`from`). Each scene's chosen take and all its takes, with their files (here or in the storyboard's cache)."""
    ids = join_order(c, nid)
    items, chain = [], -1

    def shot(key: Optional[str]) -> Optional[dict]:
        hit = c.cached_shot(key) if key else None
        return {"key": key, "file": rel_path(c.folder, hit[0]), "png": rel_path(c.folder, hit[1]), "src": str(hit[0])} if hit else None
    for k, sid in enumerate(ids):
        n = c.by[sid]
        a = evaluate_node(c, sid)
        if n["type"] != "scene":   # «Видео → видео»: one clip, its own file, no takes; nothing goes on from it
            chain += 1
            sh = {"key": a.key, "file": rel_path(c.folder, a.path), "png": rel_path(c.folder, a.png), "src": str(a.path)} \
                if a.state == "ready" and a.path else None
            items.append({"id": sid, "index": k, "name": n["data"].get("title") or type_title(n["type"]), "chain": chain,
                          "kind": "new", "from": None, "chosen": None, "shot": sh, "takes": []})
            continue
        frm = start_scene(c, sid)
        frm = frm if frm in ids[:k] else None
        if not (k and frm == ids[k - 1]):
            chain += 1
        takes = []
        for t in a.takes:
            sh = shot(t["key"]) if t.get("cached") else None
            takes.append({"seed": t["seed"], "key": t["key"], "cached": bool(sh), **(sh or {"file": None, "png": None, "src": None})})
        items.append({"id": sid, "index": k, "name": n["data"].get("title") or i18n.L(f"Сцена {k + 1}", f"Scene {k + 1}"), "chain": chain,
                      "kind": "continue" if frm else "new", "from": frm, "chosen": seed_of(n),
                      "shot": shot(a.key) if a.state == "ready" else None, "takes": takes})
    return items


def montage_of(c: Ctx, nid: str) -> dict:
    """A «Монтаж» node's montage as it will be built (edit.lay): stored in the node (`data.edit`)."""
    return edit.lay(montage_items(c, nid), c.by[nid]["data"].get("edit") or {}, c.folder, videomodels.frames(c.card, LENGTH_S))


def join_order(c: Ctx, nid: str) -> list[str]:
    """A join's scenes in order: its own `order` first, then the rest top to bottom, left to right."""
    srcs = c.inputs(nid, "clips")
    order = [x for x in c.by[nid]["data"].get("order") or [] if any(s == x for s, _ in srcs)]
    rest = sorted((s for s, _ in srcs if s not in order), key=lambda s: (c.by[s]["position"]["y"], c.by[s]["position"]["x"]))
    return order + rest


def start_scene(c: Ctx, nid: str) -> Optional[str]:
    """The scene whose last frame this scene starts from (its «кадр», or a «Кадр» node of the last frame), known
    before anything is shot."""
    src = c.inputs(nid, "start")
    if not src or src[0][0] not in c.by:
        return None
    s, port = c.by[src[0][0]], src[0][1]
    if s["type"] == "scene" and port == "frame":
        return s["id"]
    if s["type"] == "frame" and s["data"].get("at") in (None, "", "last"):
        clip = c.inputs(s["id"], "clip")
        return clip[0][0] if clip and clip[0][0] in c.by and c.by[clip[0][0]]["type"] == "scene" else None
    return None


def _cuts(p: Path) -> Optional[list]:
    j = p.with_suffix(".json")
    try:
        return json.loads(j.read_text(encoding="utf-8"))["cuts"] if p.exists() else None
    except (OSError, ValueError, KeyError):
        return None


def evaluate(c: Ctx) -> dict[str, Art]:
    return {n["id"]: evaluate_node(c, n["id"]) for n in c.g["nodes"]}


def ancestors(c: Ctx, targets: list[str]) -> set[str]:
    seen, todo = set(), list(targets)
    while todo:
        x = todo.pop()
        if x in seen or x not in c.by:
            continue
        seen.add(x)
        todo += [s for port in c.ins.get(x, {}).values() for s, _ in port]
    return seen


def outputs_of(g: dict) -> list[str]:
    return [n["id"] for n in g["nodes"] if n["type"] == "output"]


def state(proj: dict, g: dict, quality: Optional[str] = None) -> dict:
    """The canvas's view of the graph: every node's state, key and files; what «Снять всё» will make and how long.
    The last run's errors stay on their nodes while the key they were made for is the same."""
    c = Ctx(proj, g, quality, (proj.get("graph_last") or {}).get("errors"))
    arts = evaluate(c)
    need = ancestors(c, outputs_of(g))
    est = estimate(c, arts, need)
    nodes = {k: a.public(c.folder) for k, a in arts.items()}
    for k, w in drift(c).items():
        nodes[k]["warn"] = w
    return {"quality": c.quality, "width": c.w, "height": c.h, "auto_size": [c.auto_w, c.auto_h], "own_size": bool(c.own),
            "rev": g.get("rev", 0), "nodes": nodes, **est}


# with people, the face drifts over a chain of continuations: the storyboard's grid allows 3 in a row (grid.py)
NO_PEOPLE = re.compile(r"\b(no|or|without|nor)\s+(people|person|humans?)\b", re.I)


def chain_depth(c: Ctx, nid: str, memo: dict) -> int:
    """How many continuations in a row end at this scene: a scene that starts from a frame of another scene (its
    last frame, or a «Кадр» of it) is that scene's + 1. Faces by photo (Ref2VA) check the face again: 0."""
    if nid in memo:
        return memo[nid]
    memo[nid] = 0   # a cycle stops here
    d = 0
    src = c.inputs(nid, "start")
    if src and not c.inputs(nid, "faces"):
        s = c.by.get(src[0][0])
        if s and s["type"] == "frame":
            clip = c.inputs(s["id"], "clip")
            s = c.by.get(clip[0][0]) if clip else None
        if s and s["type"] == "scene":
            d = chain_depth(c, s["id"], memo) + 1
    memo[nid] = d
    return d


def drift(c: Ctx) -> dict[str, str]:
    """{scene: warning} for scenes past grid.MAX_CONTINUES continuations in a row whose prompt has people in it."""
    memo: dict = {}
    out = {}
    for n in c.g["nodes"]:
        if n["type"] != "scene":
            continue
        d = chain_depth(c, n["id"], memo)
        if d <= grid.MAX_CONTINUES:
            continue
        pr = c.inputs(n["id"], "prompt")
        text = NO_PEOPLE.sub("", (c.by[pr[0][0]]["data"].get("text") or "") if pr and pr[0][0] in c.by else "")
        if prompts.PEOPLE.search(text):
            out[n["id"]] = i18n.L(f"{d}-е продолжение подряд — лицо может уплыть. Начните новую сцену или подключите "
                                  f"фото героя во вход «лица»",
                                  f"continuation {d} in a row — the face may drift. Start a new scene or connect "
                                  f"the hero's photo to the «faces» input")
    return out


def estimate(c: Ctx, arts: dict[str, Art], need: set[str]) -> dict:
    """Scenes to shoot = the needed scenes that are todo or waiting (a waiting one will be shot once its start is)."""
    shoot, keys = [], set()
    for x in need:   # two scenes with one key (a branch copied and not changed yet) are one shot
        if c.by[x]["type"] == "scene" and arts[x].state in ("todo", "wait") and (arts[x].key is None or arts[x].key not in keys):
            shoot.append(x)
            keys.add(arts[x].key)
    n_ref = sum(1 for x in shoot if arts[x].refs or c.inputs(x, "faces")) if c.card.refs else 0
    pics = sum(1 for x in need if c.by[x]["type"] == "picture" and arts[x].state in ("todo", "wait"))
    one = render.one_scene(c.settings, c.quality, c.w, c.h, videomodels.frames(c.card, LENGTH_S))
    secs = sum(shot_seconds(c, x, arts[x]) for x in shoot)
    secs += (jobs.cold_extra(c.quality, c.card.id) if shoot else 0) + (25 * n_ref if n_ref and len(shoot) > n_ref else 0) + 30 * pics
    for x in need:
        t, a = c.by[x]["type"], arts[x]
        if t == "v2v" and a.state in ("todo", "wait"):
            secs += v2v_seconds(c, x, a)
        if t == "facefix" and a.state in ("todo", "wait"):
            from . import facefix
            secs += facefix.seconds(a.seconds or LENGTH_S)
        if t in ("join", "montage", "music", "output") and a.state in ("todo", "wait"):
            v = a.seconds or 5 * len(shoot)
            secs += 3 if t == "music" else 2 + 0.05 * v if t in ("join", "montage") else post.seconds(
                post.output_of({"output": c.by[x]["data"].get("output") or {"size": "1080p"}}), v, c.w, c.h)
    return {"to_shoot": len(shoot), "pictures": pics, "per_scene": round(one), "seconds": round(secs)}


def v2v_seconds(c: Ctx, x: str, a: Art) -> float:
    from . import v2v
    info, prof = v2v_lora(c.by[x]["data"])
    return v2v.seconds(prof, a.seconds or LENGTH_S) if info else 0


def shot_seconds(c: Ctx, x: str, a: Art) -> float:
    """How long a scene's shot takes here: its length and pixels at the measured speed (Ref2VA has its own); with a
    reference LoRA - «Видео → видео»'s guess for the clip, or its model's scene with ID-LoRA's extra pass for the voice."""
    if a.ref and a.ref["mode"] == "clip":
        from . import v2v
        return v2v.seconds(a.ref["prof"], a.seconds or LENGTH_S)
    if a.ref:
        r = a.ref
        return render.one_scene(c.settings, c.quality, r["w"], r["h"], r["length"], False, videomodels.card(a.model)) * 1.5
    ref = (a.refs or bool(c.inputs(x, "faces"))) and c.card.refs
    return render.one_scene(c.settings, c.quality, c.w, c.h, videomodels.frames(c.card, seconds_of(c.by[x])), ref)


# ---------------------------------------------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------------------------------------------
async def run(job: jobs.Job, pid: str, targets: Optional[list[str]], quality: Optional[str]) -> dict:
    """The queue's "graph" job: make what `targets` (default: every output) need. job.progress["nodes"] follows each
    node (queued / running / done / cached / error / blocked / skipped); an error stops its branch only."""
    proj = projects.load(pid)
    g = load(pid)
    failed: dict[str, str] = {}
    c = Ctx(proj, g, quality, failed)
    targets = [t for t in (targets or outputs_of(g)) if t in c.by]
    if not targets:
        raise EngineError(i18n.L("Нечего снимать: нет узла «Выход» (или выберите узел и «Снять до сюда»)",
                                 "Nothing to shoot: no «Output» node (or select a node and «Shoot up to here»)"))
    need = ancestors(c, targets)
    arts = evaluate(c)
    prog = job.progress
    est = estimate(c, arts, need)
    job.estimate = est["seconds"]
    prog.update(stage="running", quality=c.quality, width=c.w, height=c.h, targets=targets,
                nodes={x: {"status": "cached" if arts[x].state == "ready" else "queued", "type": c.by[x]["type"],
                           "estimate": round(shot_seconds(c, x, arts[x])) if c.by[x]["type"] == "scene" else
                           round(v2v_seconds(c, x, arts[x])) if c.by[x]["type"] == "v2v" else
                           round(__import__("app.facefix", fromlist=["seconds"]).seconds(arts[x].seconds or LENGTH_S)) if c.by[x]["type"] == "facefix" else 0}
                       for x in need if c.by[x]["type"] in MAKES})
    t0, last_ref, made, tried = time.time(), None, 0, set()
    while True:
        c = Ctx(proj, g, quality, failed)
        arts = evaluate(c)
        for x, row in prog["nodes"].items():
            a = arts[x]
            if row["status"] in ("queued",) and a.state == "blocked":
                row["status"] = "blocked"
            elif row["status"] == "blocked" and a.state not in ("blocked", "error"):
                row["status"] = "queued"
            if a.state == "error" and row["status"] not in ("error",):
                row.update(status="error", error=a.error)
        todo = [x for x in need if arts[x].state == "todo" and c.by[x]["type"] in MAKES]
        if not todo:
            break
        if job.stop_after:
            for x, row in prog["nodes"].items():
                if row["status"] in ("queued", "blocked"):
                    row["status"] = "skipped"
            break
        x = _pick(c, arts, todo, last_ref)
        row = prog["nodes"][x]
        row.update(status="running", key=arts[x].key)
        prog["current"] = x
        ts = time.time()
        try:
            if x in tried:
                raise EngineError(i18n.L("узел сделан, а его файла нет", "the node is done, but its file is missing"))
            tried.add(x)
            await _make(job, c, x, arts[x])
            row.update(status="done", seconds=round(time.time() - ts, 1))
            made += 1
            if c.by[x]["type"] == "scene":
                last_ref = (arts[x].model or c.card.id, arts[x].refs)
                for k, r in prog["nodes"].items():   # the speed was measured again
                    if r["status"] == "queued" and r["type"] == "scene":
                        r["estimate"] = round(shot_seconds(c, k, arts[k]))
        except asyncio.CancelledError:
            row["status"] = "cancelled"
            raise
        except Exception as e:  # noqa: BLE001 - shown on the node; the other branches go on
            failed[x] = {"key": arts[x].key, "error": str(e)}
            row.update(status="error", error=str(e))
    prog.pop("current", None)
    prog["stage"] = "done"
    result = {"quality": c.quality, "finished": time.time(), "seconds": round(time.time() - t0, 1), "made": made,
              "errors": failed, "targets": targets}
    cur = projects.load(pid)
    cur["graph_last"] = result
    projects.save(cur)
    return result


def _pick(c: Ctx, arts: dict[str, Art], todo: list[str], last_ref: Optional[tuple]) -> str:
    """Pictures first (they feed starts), then scenes - each model's next to its own, Ref2VA next to Ref2VA, plain next
    to plain (each switch reads a 21 GB model again), in the graph's order - then frames, assemblies, music, outputs.
    `last_ref`: (the model, Ref2VA) of the scene shot last."""
    order = {n["id"]: i for i, n in enumerate(c.g["nodes"])}

    def rank(x: str):
        t = c.by[x]["type"]
        same = 0 if t != "scene" or last_ref is None or (arts[x].model or c.card.id, arts[x].refs) == last_ref else 1
        return (MAKES.index(t), same, c.by[x]["position"]["y"], c.by[x]["position"]["x"], order[x])
    return min(todo, key=rank)


async def _make(job: jobs.Job, c: Ctx, x: str, a: Art) -> None:
    n = c.by[x]
    t, d = n["type"], n["data"]
    if t == "scene" and a.ref:
        await _make_ref_scene(job, c, x, a)
    elif t == "scene":
        start = c.inputs(x, "start")
        st_art = _out(c, *start[0]) if start else None
        kind = "continue" if st_art and st_art.start_of else "new"   # a last frame as it is; a photo cropped to the frame
        faces = [_out(c, s, sp).path for s, sp in c.inputs(x, "faces")]
        title = d.get("title") or i18n.L("Сцена", "Scene")
        res = await render.shoot_scene(job, c.pid, c.folder / "scenes", a.text, kind, seed_of(n), c.w, c.h,
                                       videomodels.frames(c.card, a.seconds), a.loras, st_art.path if st_art else None,
                                       [f for f in faces if f], c.quality, label=f"«{title}»", model=c.card.id,
                                       end=_out(c, *c.inputs(x, "end")[0]).path if c.inputs(x, "end") else None)
        if not res["cached"]:   # the clip's checks (phase 10, stage A): a badge on the node; «Ещё дубль» is the user's
            face = (st_art.path if st_art else None) or next((f for f in faces if f), None)
            await asyncio.to_thread(checks.check_clip, res["mp4"], face)
    elif t == "picture":
        from . import picture
        text = a.text if a.text else _picture_text(c, x)
        if d.get("model") == "flux2":
            await picture.edit(job, text, a.images, int(d.get("seed") or 1), c.pw, c.ph, a.path, a.loras)
            notes = []
        else:
            notes = await picture.generate(job, text, int(d.get("seed") or 1), c.pw, c.ph, a.path, a.loras)
        if notes:
            job.progress.setdefault("notes", []).extend(f"«{d.get('title') or i18n.L('Картинка', 'Picture')}»: {n}" for n in notes)
    elif t == "v2v":
        from . import v2v
        info, prof = v2v_lora(d)
        src = _out(c, *c.inputs(x, "clip")[0])
        pics = [_out(c, s, sp).path for s, sp in c.inputs(x, "image")] if prof["engine"] == "h3" else []
        await v2v.make(job, src.path, info, prof, float(d.get("strength", 1.0)), float(d.get("guide", 1.0)), int(d.get("seed") or 1),
                       a.text or "", [p for p in pics if p], a.loras, a.path, a.png, a.alpha, f"«{d.get('title') or i18n.L('Видео → видео', 'Video → video')}»")
    elif t == "facefix":
        from . import facefix
        src = _out(c, *c.inputs(x, "clip")[0])
        mode = d.get("mode") if d.get("mode") in facefix.MODES else "far"
        pr = c.inputs(x, "prompt")
        text = _out(c, *pr[0]).text if pr else d.get("prompt") or ""
        note = await facefix.make(job, src.path, mode, min(1.0, max(0.0, float(d.get("strength", 1.0)))), int(d.get("seed") or 1),
                                  text, a.path, a.png, f"«{d.get('title') or i18n.L('Лица', 'Faces')}»")
        if not note["faces"]:
            job.progress.setdefault("notes", []).append(i18n.L(f"«{d.get('title') or 'Лица'}»: лиц в клипе не найдено — клип как есть",
                                                               f"«{d.get('title') or 'Faces'}»: no faces found in the clip — the clip as it is"))
    elif t == "frame":
        src = _out(c, *c.inputs(x, "clip")[0])
        a.path.parent.mkdir(exist_ok=True)
        at = max(0.0, min(float(d.get("at")), (src.seconds or LENGTH_S) - 0.05))
        job.phase = "saving"
        await asyncio.to_thread(_ffmpeg, ["-ss", f"{at:.3f}", "-i", str(src.path), "-frames:v", "1", str(a.path)])
    elif t == "join":
        a.path.parent.mkdir(exist_ok=True)
        job.phase = "assembling"
        size = await asyncio.to_thread(render.mixed_size, [p for p, _, _ in a.clips], c.w, c.h)
        cuts = await asyncio.to_thread(render.assemble, [(p, k) for p, k, _ in a.clips], a.path, size)
        a.path.with_suffix(".json").write_text(json.dumps({"cuts": cuts, "clips": [s for _, _, s in a.clips]}), encoding="utf-8")
    elif t == "montage":
        ed = montage_of(c, x)
        a.path.parent.mkdir(exist_ok=True)
        job.phase = "assembling"
        pic = a.path.with_name(a.path.stem + "_pic.mp4") if ed["sounds"] else a.path
        size = await asyncio.to_thread(render.mixed_size, [Path(x["src"]) for x in ed["clips"] if x.get("src")], c.w, c.h)
        cuts = await asyncio.to_thread(edit.render, ed, c.folder, pic, size)
        if ed["sounds"]:   # the sounds from files over the scenes' sound (the track is the «Музыка» node's)
            job.phase = "mixing"
            await asyncio.to_thread(edit.mix, ed, c.folder, pic, None, a.path)
            pic.unlink(missing_ok=True)
        a.path.with_suffix(".json").write_text(json.dumps({"cuts": cuts, "clips": [x["id"] for x in ed["clips"]]}), encoding="utf-8")
    elif t == "music":
        v = _out(c, *c.inputs(x, "video")[0])
        au = _out(c, *c.inputs(x, "audio")[0])
        track = {"file": rel_path(c.folder, au.path), **{k: d[k] for k in music.DEFAULTS if k in d}}
        a.path.parent.mkdir(exist_ok=True)
        job.phase = "mixing"
        await asyncio.to_thread(music.mix, v.path, au.path, track, a.path)
    elif t == "sound":
        src = _out(c, *c.inputs(x, "clip")[0])
        a.path.parent.mkdir(exist_ok=True)
        if d.get("voice", True) is not False:   # Demucs on the GPU: the writer and the video model out of memory first
            from . import song
            from .llm import client as llm
            job.phase = "loading"
            await llm.SERVER.stop()
            if COMFY.warm:
                await COMFY.free()
                COMFY.warm = False
            job.phase = "separating"
            await song.separate(src.path, a.path, lambda m: job.progress.update(message=m))
        else:
            job.phase = "saving"
            await asyncio.to_thread(_ffmpeg, ["-i", str(src.path), "-vn", "-ac", "2", "-ar", "48000", str(a.path)])
    elif t == "output":
        v = _out(c, *c.inputs(x, "video")[0])
        out = post.output_of({"output": d.get("output") or {"size": "1080p"}})
        a.path.parent.mkdir(exist_ok=True)
        job.phase = "upscaling"
        # an own frame: the output keeps its proportions instead of the format's 1080p / 4k frame
        await asyncio.to_thread(post.finish, v.path, a.path, c.w, c.h, "own" if c.own else c.aspect, out, v.cuts, c.folder / "_post")


async def _make_ref_scene(job: jobs.Job, c: Ctx, x: str, a: Art) -> None:
    """A scene with a reference LoRA (_evaluate_ref_scene): the clip made again into its shot, or ID-LoRA's shot."""
    d, r = c.by[x]["data"], a.ref
    label = f"«{d.get('title') or i18n.L('Сцена', 'Scene')}»"
    if r["mode"] == "clip":
        from . import v2v
        a.path.parent.mkdir(exist_ok=True)
        await v2v.make(job, r["clip"].path, r["info"], r["prof"], r["strength"], r["guide"], seed_of(c.by[x]), a.text or "",
                       r["pics"], r["extra"], a.path, a.png, a.alpha, label)
        return
    st_art = _out(c, *c.inputs(x, "start")[0])
    kind = "continue" if st_art.start_of else "new"   # a photo is cropped to the frame; a last frame of another size too
    res = await render.shoot_scene(job, c.pid, c.folder / "scenes", a.text, kind, seed_of(c.by[x]), r["w"], r["h"], r["length"],
                                   r["plain"], st_art.path, [], c.quality, label=label, model=a.model, ref=r["voice"])
    if res["key"] != a.key:
        raise EngineError(i18n.L(f"{label}: ключ съёмки разошёлся с ключом сцены ({res['key']} ≠ {a.key})",
                                 f"{label}: the shot's key differs from the scene's ({res['key']} ≠ {a.key})"))
    if not res["cached"]:   # the clip's checks, the face against the photo it starts from
        await asyncio.to_thread(checks.check_clip, res["mp4"], st_art.path)


def _picture_text(c: Ctx, x: str) -> str:
    src = c.inputs(x, "text")
    if not src:
        return c.by[x]["data"].get("prompt") or ""
    a = _out(c, *src[0])
    return a.picture or a.text


def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run([config.FFMPEG, "-y", "-v", "error", *args], capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode:
        raise EngineError("ffmpeg: " + (r.stderr or "").strip()[-600:])


# ---------------------------------------------------------------------------------------------------------------
# the writer's nodes (G3): their signature, the LLM job, «Развернуть в сцены»
# ---------------------------------------------------------------------------------------------------------------
def writer_inputs(c: Ctx, n: dict) -> tuple[str, list[dict]]:
    idea = next((c.by[s]["data"].get("text", "") for s, _ in c.inputs(n["id"], "idea") if s in c.by), "") or n["data"].get("idea", "")
    heroes = [c.by[s] for s, _ in c.inputs(n["id"], "cast") if s in c.by]
    heroes.sort(key=lambda h: (h["position"]["y"], h["position"]["x"]))
    return idea.strip(), heroes


def writer_sig(c: Ctx, n: dict) -> str:
    idea, heroes = writer_inputs(c, n)
    d = n["data"]
    return _sha(idea, [{k: h["data"].get(k) for k in ("gender", "age", "en", "outfit_en", "photo")} for h in heroes],
                {k: d.get(k) for k in ("seconds", "mode", "mood", "music", "ref_photo")})


def writer_mode(d: dict, heroes: list) -> str:
    m = d.get("mode") or "auto"
    if m != "auto":
        return m
    return "none" if not heroes else "one" if len(heroes) == 1 else "several"


def hero_cast(h: dict) -> dict:
    d = h["data"]
    return {"gender": d.get("gender", ""), "age": d.get("age", ""), "en": d.get("en", ""), "ru": d.get("ru", ""),
            "outfit_en": d.get("outfit_en", ""), "outfit_ru": d.get("outfit_ru", ""), "photo": d.get("photo"), "node": h["id"]}


async def run_llm(job: jobs.Job, pid: str, ids: list[str], model: Optional[str]) -> dict:
    """«Переписать» for LLM nodes: heroes «Описать по фото», prompts «Придумать реплики» and writers «Написать», all
    in one model load (the session is re-entrant: llm.session inside keeps the server up). The results go into the
    graph (rev + 1)."""
    from .llm import client as llm, describe, writer
    from .planner import check
    g = load(pid)
    proj = projects.load(pid)
    folder = projects.folder(pid)
    todo = [node(g, i) for i in ids if node(g, i) and node(g, i)["type"] in LLM_BUTTONS]
    heroes = [n for n in todo if n["type"] == "hero"]
    texts = [n for n in todo if n["type"] == "prompt"]
    writers = [n for n in todo if n["type"] == "writer"]
    prog = job.progress
    prog.update(stage="llm", nodes={n["id"]: {"status": "queued", "type": n["type"]} for n in todo})
    done = {}
    async with llm.session(model) as client:
        for h in heroes:
            prog["nodes"][h["id"]]["status"] = "running"
            p = folder / h["data"]["photo"] if h["data"].get("photo") else None
            if not p or not p.exists():
                prog["nodes"][h["id"]].update(status="error", error=i18n.L("у героя нет фото", "the hero has no photo"))
                continue
            dsc = await describe.describe_with(client, p)
            keys = ["gender", "age", "en", "ru"] + ([] if h["data"].get("outfit_en") or h["data"].get("outfit_ru") else ["outfit_en", "outfit_ru"])
            done[h["id"]] = {k: dsc.get(k, h["data"].get(k)) for k in keys}
            h["data"].update(done[h["id"]])
            prog["nodes"][h["id"]]["status"] = "done"
        c = Ctx(proj, g)
        for pn in texts:
            row = prog["nodes"][pn["id"]]
            row["status"] = "running"
            text = (pn["data"].get("text") or "").strip()
            if not text:
                row.update(status="error", error=i18n.L("пустой промт", "empty prompt"))
                continue
            had = [ln.get("who") for ln in pn["data"].get("lines") or [] if isinstance(ln, dict) and ln.get("who")]
            speakers = list(dict.fromkeys(had + prompts.speakers_in(text)))[:4] or ["The main character"]
            secs = next((seconds_of(c.by[e["target"]]) for e in g["edges"]
                         if e["source"] == pn["id"] and e["targetHandle"] == "prompt" and e["target"] in c.by), LENGTH_S)
            done[pn["id"]] = {"lines": await writer.lines_for_prompt(client, text, speakers, secs, random.randrange(100000))}
            row["status"] = "done"
        for w in writers:
            row = prog["nodes"][w["id"]]
            row["status"] = "running"
            d = w["data"]
            idea, hs = writer_inputs(c, w)
            if not idea:
                row.update(status="error", error=i18n.L("нет идеи: подключите узел «Идея»", "no idea: connect an «Idea» node"))
                continue
            missing = [h for h in hs if not (h["data"].get("en") or "").strip()]
            if missing:
                row.update(status="error", error=i18n.L("герой без внешности: «Описать по фото» или впишите её",
                                                   "a hero without a look: «Describe from photo» or write it in"))
                continue
            mode = writer_mode(d, hs)
            plan = writer.new_plan(idea, float(d.get("seconds") or 15), mode, d.get("mood", ""), d.get("music", ""),
                                   None, seed=int(d.get("seed") or random.randrange(100000)), model=client.model.id)
            plan["video"] = (proj.get("settings") or {}).get("video_model") or "h3"   # the graph's model shoots it
            if mode != "none" and hs:
                plan["cast"] = [{k: v for k, v in hero_cast(hs[0]).items() if k not in ("photo", "node")}]
            p = await writer.write(plan, None, folder)
            if mode != "none":   # the user's heroes stay as they are, in the order of the canvas
                p.setdefault("cast", [])
                for i, h in enumerate(hs):
                    look = {k: v for k, v in hero_cast(h).items() if k not in ("photo", "node")}
                    if i < len(p["cast"]):
                        p["cast"][i].update(look)
                    else:
                        p["cast"].append(look)
            p = check.plan(p)
            done[w["id"]] = {"plan": p, "sig": writer_sig(c, w)}
            row["status"] = "done"

    def put(gg: dict) -> None:
        for nid, data in done.items():
            if (nn := node(gg, nid)):
                nn["data"].update(data)
    update(pid, put)
    prog["stage"] = "done"
    return {"done": list(done), "errors": {k: v.get("error") for k, v in prog["nodes"].items() if v.get("status") == "error"}}


def expand(pid: str, wid: str) -> dict:
    """«Развернуть в сцены»: the writer's plan -> a Prompt and a Scene per scene (a continuation starts from the
    previous scene's last frame), a Join of them and an Output. Again after a rewrite: the same nodes get the new
    texts (their seeds stay), extra ones go away."""
    from .planner import check

    def go(g: dict) -> None:
        w = node(g, wid)
        if not w or w["type"] != "writer" or not w["data"].get("plan"):
            raise ValueError(i18n.L("У сценариста нет раскадровки: сначала «Написать»", "The writer has no storyboard: «Write» first"))
        plan = json.loads(json.dumps(w["data"]["plan"]))
        c = Ctx(projects.load(pid), g)
        _, heroes = writer_inputs(c, w)
        if plan.get("mode") != "none":   # Ref2VA: the hero's photo as <Picture k> where prompts.uses_refs says so
            for i, h in enumerate(heroes):
                if i < len(plan.get("cast") or []) and h["data"].get("photo"):
                    plan["cast"][i]["photo"] = h["data"]["photo"]
            plan["ref_photo"] = bool(w["data"].get("ref_photo"))
            plan = check.plan(plan)
        x0, y0 = w["position"]["x"] + 380, w["position"]["y"]
        mine = {(nn["data"].get("from"), nn["data"].get("scene"), nn["type"]): nn for nn in g["nodes"]}
        keep, scene_ids, row, col = set(), [], -1, 0
        for s in plan["scenes"]:
            i = s["index"]
            if s["kind"] == "new" or row < 0 or col == 6:
                row, col = row + 1, 0
            x, y = x0 + col * 640, y0 + row * 300
            col += 1
            pn = mine.get((wid, i, "prompt"))
            if not pn:
                pn = {"id": uuid.uuid4().hex[:8], "type": "prompt", "position": {"x": x, "y": y}, "data": {"from": wid, "scene": i}}
                g["nodes"].append(pn)
            text, lines = prompts.split_lines(plan, s)
            pn["data"].update(text=text, lines=lines, title=i18n.L(f"Сцена {i + 1}", f"Scene {i + 1}"), ru=s.get("ru", ""))
            sn = mine.get((wid, i, "scene"))
            if not sn:
                sn = {"id": uuid.uuid4().hex[:8], "type": "scene", "position": {"x": x + 300, "y": y},
                      "data": {"from": wid, "scene": i, "takes": [int(s.get("seed") or random.randrange(1, 2**31))], "take": 0}}
                g["nodes"].append(sn)
            sn["data"]["title"] = i18n.L(f"Сцена {i + 1}", f"Scene {i + 1}")
            keep |= {pn["id"], sn["id"]}
            scene_ids.append(sn["id"])
            g["edges"] = [e for e in g["edges"] if not (e["target"] == sn["id"] and e["targetHandle"] in ("prompt", "start", "faces"))]
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": pn["id"], "sourceHandle": "text", "target": sn["id"], "targetHandle": "prompt"})
            if s["kind"] == "continue" and len(scene_ids) > 1:
                g["edges"].append({"id": uuid.uuid4().hex[:8], "source": scene_ids[-2], "sourceHandle": "frame", "target": sn["id"], "targetHandle": "start"})
            if prompts.uses_refs(plan, s):
                for k in prompts.photo_people(plan, s):
                    if k < len(heroes):
                        g["edges"].append({"id": uuid.uuid4().hex[:8], "source": heroes[k]["id"], "sourceHandle": "image", "target": sn["id"], "targetHandle": "faces"})
        gone = {nn["id"] for nn in g["nodes"] if nn["data"].get("from") == wid and nn["type"] in ("prompt", "scene") and nn["id"] not in keep}
        g["nodes"] = [nn for nn in g["nodes"] if nn["id"] not in gone]
        g["edges"] = [e for e in g["edges"] if e["source"] not in gone and e["target"] not in gone]
        jn = mine.get((wid, None, "join"))
        if not jn:
            jn = {"id": uuid.uuid4().hex[:8], "type": "join", "position": {"x": x0 + 6 * 640, "y": y0}, "data": {"from": wid}}
            g["nodes"].append(jn)
            on = {"id": uuid.uuid4().hex[:8], "type": "output", "position": {"x": x0 + 6 * 640 + 320, "y": y0},
                  "data": {"from": wid, "output": {"size": "1080p", "hdr": False, "fps48": False}}}
            g["nodes"].append(on)
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": jn["id"], "sourceHandle": "video", "target": on["id"], "targetHandle": "video"})
        g["edges"] = [e for e in g["edges"] if not (e["target"] == jn["id"] and e["source"] in keep | gone)]
        for sid in scene_ids:
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": sid, "sourceHandle": "clip", "target": jn["id"], "targetHandle": "clips"})
        jn["data"]["order"] = scene_ids
    return update(pid, go)


# ---------------------------------------------------------------------------------------------------------------
# G1: a storyboard drawn as a graph (view only)
# ---------------------------------------------------------------------------------------------------------------
def storyboard(proj: dict) -> dict:
    """-> {scenes: [{index, written, start, from, who, refs}]}.
    start: "prev" - a scene's last frame (a continuation; `from` - which scene's), "photo" - the scene's start photo,
    None - text.
    who: the cast indices in the scene's prompt (the people whose looks go in); refs: the cast indices whose photos
    Ref2VA gets, in <Picture N> order (empty: no Ref2VA)."""
    plan = proj.get("plan") or {}
    people = plan.get("mode") != "none"
    out = []
    for s in plan.get("scenes") or []:
        start = "prev" if s["kind"] == "continue" else "photo" if prompts.starts_from_photo(s) else None
        src = prompts.from_of(plan, s)
        out.append({"index": s["index"], "written": prompts.is_written(s), "start": start, "from": src["index"] if src else None,
                    "who": [i for i, _ in prompts.scene_cast(plan, s)] if people else [],
                    "refs": prompts.photo_people(plan, s) if prompts.uses_refs(plan, s) else []})
    return {"scenes": out}
