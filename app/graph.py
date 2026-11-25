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
import math
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

from . import checks, config, edit, i18n, jobs, looks, music, post, projects, render, timings, videomodels
from .engine import graphs
from .engine.comfy import COMFY, EngineError
from .planner import grid, prompts

LENGTH_S = 5                 # a scene's seconds unless it says (`seconds`); a storyboard's scenes are all 5 s
MIN_S, MAX_S = 3, 15         # H3 is trained on 5-15 s; 3 s still holds one action
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------------------------------------------------------
# node types: ports (name -> port type; an input is single or multi), who does the work (the header's colour)
# ---------------------------------------------------------------------------------------------------------------
# a mini-series (2026-11-09): «Сериал» holds the bible, «Сценарий» a screenplay in the «ИМЯ (как): слова» format
# (app/screenplay.py); «Развернуть в шоты» makes a «Промт» + «Сцена» per line or action, one speaker per shot
# ---------------------------------------------------------------------------------------------------------------
SERIES_FIELDS = (("title", "Название"), ("look_text", "Вид"), ("world", "Мир"), ("characters", "Персонажи"), ("recap", "Ранее"))


def series_text(d: dict) -> str:
    """The bible as the writer reads it: «Название: …» per filled field (the look's name for the picked look)."""
    rows = []
    for k, label in SERIES_FIELDS:
        v = (d.get("style") if k == "look_text" else d.get(k)) or ""
        if k == "look_text" and d.get("look") in looks.LOOKS and d["look"] != looks.AUTO:   # the picked look's name, then the user's words
            v = looks.LOOKS[d["look"]]["ru"] + ("; " + str(v).strip() if str(v).strip() else "")
        if str(v).strip():
            rows.append(f"{label}: {str(v).strip()}")
    return "\n".join(rows)


def hero_name(h: dict, k: int) -> str:
    """How the screenplay names a hero: the node's title, «Герой N» without one."""
    return (h["data"].get("title") or "").strip() or i18n.L(f"Герой {k + 1}", f"Hero {k + 1}")


def screenplay_inputs(c: Ctx, n: dict) -> tuple[str, list[dict], Optional[dict], str]:
    """(the idea, the hero nodes in the order of the canvas = the characters, the «Сериал» node wired to `series` or
    None, the bible's text: that node's, a text node's or the node's own `series`)."""
    idea = next((c.by[s]["data"].get("text", "") for s, _ in c.inputs(n["id"], "idea") if s in c.by), "") or n["data"].get("idea", "")
    heroes = [c.by[s] for s, _ in c.inputs(n["id"], "cast") if s in c.by and c.by[s]["type"] == "hero"]
    heroes.sort(key=lambda h: (h["position"]["y"], h["position"]["x"]))
    src = next((c.by[s] for s, _ in c.inputs(n["id"], "series") if s in c.by), None)
    sv = src if src and src["type"] == "series" else None
    bible = series_text(sv["data"]) if sv else (src["data"].get("text", "") if src else "") or n["data"].get("series", "")
    return (idea or "").strip(), heroes, sv, (bible or "").strip()


def _hero_look(h: dict) -> str:
    d = h["data"]
    return ", ".join(x for x in ((d.get("en") or "").strip(), (f"wearing {d['outfit_en']}" if d.get("outfit_en") else "")) if x)


async def write_screenplay(client, c: Ctx, n: dict, action: str = "write") -> dict:
    """«Написать сценарий» (the idea, the heroes' looks and the bible -> the screenplay's text, with the writer's English
    for the places and actions in `tr`) or «Добавить в "Ранее"» (1-2 sentences of this episode into the «Сериал» node).
    -> {node id: the data to put}. A ValueError says what is missing."""
    from . import screenplay
    from .llm import writer
    d = n["data"]
    idea, heroes, sv, bible = screenplay_inputs(c, n)
    seed = int(d.get("seed") or random.randrange(100000))
    if action == "recap":
        text = (d.get("text") or "").strip()
        if not text:
            raise ValueError(i18n.L("нет сценария: сначала «Написать сценарий»", "no screenplay: «Write the screenplay» first"))
        if not sv:
            raise ValueError(i18n.L("нет «Сериала»: подключите узел «Сериал» ко входу «сериал»", "no «Series»: connect a «Series» node to the «series» input"))
        sig = _sha(text)
        if d.get("recap_of") == sig:
            raise ValueError(i18n.L("Этот сценарий уже добавлен в «Ранее»", "This screenplay is already in «Previously»"))
        recap = await writer.recap_for(client, text, bible, seed)
        if not recap:
            raise ValueError(i18n.L("модель не написала краткое содержание", "the model wrote no summary"))
        old = (sv["data"].get("recap") or "").strip()
        sv["data"]["recap"] = (old + "\n" if old else "") + recap
        return {n["id"]: {"recap_of": sig}, sv["id"]: {"recap": sv["data"]["recap"]}}
    if not idea:
        raise ValueError(i18n.L("нет идеи: подключите узел «Идея»", "no idea: connect an «Idea» node"))
    if not heroes:
        raise ValueError(i18n.L("нет героев: подключите узлы «Герой» ко входу «герои»", "no heroes: connect «Hero» nodes to the «cast» input"))
    cast = [{"name": hero_name(h, k), "gender": h["data"].get("gender") or "", "look": _hero_look(h)} for k, h in enumerate(heroes)]
    data = await writer.screenplay_for(client, idea, cast, bible, int(d.get("seconds") or 30), seed)
    text, tr = screenplay.render(data, [x["name"] for x in cast])
    if not text:
        raise ValueError(i18n.L("модель не написала сценарий", "the model wrote no screenplay"))
    return {n["id"]: {"text": text, "tr": tr, "name": str(data.get("title") or "").strip(), "recap_of": None}}


def _screenplay_shots(c: Ctx, w: dict) -> tuple[list[dict], list[dict], dict, list[dict]]:
    """(the cast [{name, gender}], the shots, the parse, the heroes) of a «Сценарий» node."""
    from . import screenplay
    _, heroes, _, _ = screenplay_inputs(c, w)
    cast = [{"name": hero_name(h, k), "gender": h["data"].get("gender") or "", "kind": hero_kind(h["data"])}
            for k, h in enumerate(heroes)]
    parsed = screenplay.parse(w["data"].get("text") or "", cast)
    return cast, screenplay.shots(parsed, cast), parsed, heroes


def screenplay_style(c: Ctx, w: dict) -> tuple[Optional[str], str]:
    """(the series' look id or None, the free `style` words) of the «Сериал» node wired to a «Сценарий»."""
    _, _, sv, _ = screenplay_inputs(c, w)
    d = (sv or {}).get("data") or {}
    look = d.get("look") if d.get("look") in looks.LOOKS and d.get("look") != looks.AUTO else None
    return look, str(d.get("style") or "").strip()


def screenplay_missing(pid: str, wid: str) -> list[tuple[str, str]]:
    """[(kind, Russian text)] the screenplay's English prompts still lack: places, actions, free remarks and the series'
    free style that are in Cyrillic and have no translation in the node's `tr`."""
    from . import screenplay
    g = load(pid)
    w = node(g, wid)
    if not w or w["type"] != "screenplay":
        return []
    c = Ctx(projects.load(pid), g)
    _, shots, _, _ = _screenplay_shots(c, w)
    free = screenplay_style(c, w)[1]
    tr = w["data"].get("tr") if isinstance(w["data"].get("tr"), dict) else {}
    kinds = {}
    for sh in shots:
        for t in screenplay.texts_for_prompt(sh):
            kinds.setdefault(t, "place" if t == sh["place"] else "action" if sh["kind"] == "action" else "manner")
    if free:
        kinds.setdefault(free, "style")
    return [(kinds.get(t, "action"), t) for t in screenplay.missing_tr(shots, tr, (free,) if free else ())]


async def translate_screenplay(client, pid: str, wid: str, seed: int = 1) -> dict:
    """The missing English of a screenplay (screenplay_missing) by the studio's writer, cached per text in the node's
    `tr` (an edited line is translated again, the others stay). -> {node id: {"tr": the whole table}}; {} when nothing
    was missing."""
    from .llm import writer
    todo = screenplay_missing(pid, wid)
    if not todo:
        return {}
    got = await writer.translate_screenplay(client, todo, seed)
    tr = dict(node(load(pid), wid)["data"].get("tr") or {})
    tr.update(got)
    return {wid: {"tr": tr}}


def screenplay_edited(pid: str, wid: str) -> list[str]:
    """The names of the shots' nodes the user changed since «Развернуть в шоты» (what expanding again would ask about)."""
    g = load(pid)
    return [nn["data"].get("title") or type_title(nn["type"]) for nn in g["nodes"]
            if nn["data"].get("from") == wid and not nn["data"].get("detached") and nn["data"].get("made") and _made(nn) != nn["data"]["made"]]


def expand_screenplay(pid: str, wid: str, edited: str = "ask") -> dict:
    """«Развернуть в шоты»: the screenplay -> a «Промт» (its one line in `lines`, the prompt in H3's form) and a «Сцена»
    per line or action - ONE speaker per shot, the camera on the speaker, the listener over the shoulder, the length
    from the words; each scene's «лица» wired from the heroes in the shot (the speaker's picture first), so Ref2VA
    gets them as <Picture N>. All in a «Монтаж» in order and an «Выход». Again: the same nodes get the new texts (their
    seeds stay), extra ones go away. What the user did to the shots since is theirs: wires they added into a scene's
    prompt / start / faces stay (only the writer's own wires are made again); a prompt or scene they changed (`made`):
    `edited` "ask" - Edited (the page asks), "keep" - left as it is, "replace" - made again. -> the graph, `kept`."""
    from . import screenplay
    bad: list[int] = []   # the shots whose English is missing (their prompts say «проверь перевод»)
    kept: list[str] = []

    def go(g: dict) -> None:
        w = node(g, wid)
        if not w or w["type"] != "screenplay" or not (w["data"].get("text") or "").strip():
            raise ValueError(i18n.L("В сценарии нет текста: напишите его или нажмите «Написать сценарий»",
                                    "The screenplay has no text: write it or press «Write the screenplay»"))
        c = Ctx(projects.load(pid), g)
        cast, shots, parsed, heroes = _screenplay_shots(c, w)
        if not shots:
            raise ValueError(i18n.L("В сценарии нет ни реплик, ни действий", "The screenplay has no lines and no actions"))
        look, free = screenplay_style(c, w)
        looks_en = {i: {"en": screenplay.unstyle((h["data"].get("en") or "").strip(), look or ""), "outfit_en": screenplay.unstyle(h["data"].get("outfit_en") or "", look or "")}
                    for i, h in enumerate(heroes)}
        # a hero has a picture when the graph would really feed one (`heroes` are resolved: an actor of the library gives
        # its face panel or none) - a bare `actor` or a path to a missing file is no picture
        photos = [i for i, h in enumerate(heroes) if h["data"].get("photo") and (c.folder / h["data"]["photo"]).exists()]
        tr = w["data"].get("tr") if isinstance(w["data"].get("tr"), dict) else {}
        style = screenplay.style_line(look, free, tr)   # the series' look first in every prompt
        x0, y0 = w["position"]["x"] + 380, w["position"]["y"]
        detach_copies(g, wid, lambda nn: (nn["data"].get("scene"), nn["data"].get("hero"), nn["type"]))
        mine = {(nn["data"].get("from"), nn["data"].get("scene"), nn["type"]): nn for nn in g["nodes"] if nn["data"].get("from") == wid and not nn["data"].get("detached")}
        changed = [nn for nn in mine.values() if nn["data"].get("made") and _made(nn) != nn["data"]["made"]]
        if changed and edited == "ask":
            raise Edited([nn["data"].get("title") or type_title(nn["type"]) for nn in changed])
        hold = {nn["id"] for nn in changed} if edited == "keep" else set()
        kept.extend(nn["data"].get("title") or type_title(nn["type"]) for nn in changed if nn["id"] in hold)
        cast_ids = {h["id"] for h in heroes}
        keep, scene_ids, row, col, last = set(), [], 0, 0, None
        for sh in shots:
            if last is not None and sh["scene"] != last:
                row, col = row + 1, 0
            elif col == EXPAND_COLS:
                row, col = row + 1, 0
            last = sh["scene"]
            x, y = x0 + col * 640, y0 + row * 300
            col += 1
            k = sh["i"]
            text, lines = screenplay.prompt_of(sh, cast, looks_en, photos, tr, style)
            check = bool(screenplay.missing_tr([sh], tr))   # no English for the place or the action: the prompt is marked, never silent
            name = cast[sh["speaker"]]["name"] if sh["speaker"] is not None else sh["who"]
            ru = (f"{name}: {sh['text']}" if sh["kind"] == "line" else f"— {sh['text']}")
            title = i18n.L(f"Шот {k + 1}", f"Shot {k + 1}") + (f" · {name}" if sh["kind"] == "line" and name else "")
            if check:
                bad.append(k + 1)
                title += i18n.L(" · проверь перевод", " · check the translation")
            pn = mine.get((wid, k, "prompt"))
            if not pn:
                pn = {"id": uuid.uuid4().hex[:8], "type": "prompt", "position": {"x": x, "y": y}, "data": {"from": wid, "scene": k}}
                g["nodes"].append(pn)
            if pn["id"] not in hold:
                pn["data"].update(text=text, lines=lines, title=title, ru=ru)
                if check:
                    pn["data"]["check"] = "translate"
                else:
                    pn["data"].pop("check", None)
                pn["data"]["made"] = _made(pn)
            sn = mine.get((wid, k, "scene"))
            if not sn:
                sn = {"id": uuid.uuid4().hex[:8], "type": "scene", "position": {"x": x + 300, "y": y},
                      "data": {"from": wid, "scene": k, "takes": [random.randrange(1, 2**31)], "take": 0}}
                g["nodes"].append(sn)
            if sn["id"] not in hold:
                sn["data"].update(title=title, seconds=sh["seconds"])
                if look:
                    sn["data"]["look"] = look
                else:
                    sn["data"].pop("look", None)
                sn["data"]["made"] = _made(sn)
            keep |= {pn["id"], sn["id"]}
            scene_ids.append(sn["id"])
            # the writer's own wires into the scene are made again; the user's stay (a start «Картинка», a face of theirs).
            # The scene remembers the ids of its own (`wired`); one made before that is told by its ends.
            wired = set(sn["data"].get("wired") or [])
            legacy = "wired" not in sn["data"]
            into = [e for e in g["edges"] if e["target"] == sn["id"] and e["targetHandle"] in ("prompt", "start", "faces")]
            mine_e = [e for e in into if e["id"] in wired or (legacy and (
                (e["targetHandle"] == "prompt" and (node(g, e["source"]) or {"data": {}})["data"].get("from") == wid
                 and not (node(g, e["source"]) or {"data": {}})["data"].get("detached"))
                or (e["targetHandle"] == "faces" and e["source"] in cast_ids)))]
            theirs = [e for e in into if e not in mine_e]
            g["edges"] = [e for e in g["edges"] if e not in mine_e and not (e in theirs and e["targetHandle"] == "faces")]
            new_e: list[dict] = []
            if not any(e["targetHandle"] == "prompt" for e in theirs):   # a prompt the user wired themselves stays the scene's
                new_e.append({"id": uuid.uuid4().hex[:8], "source": pn["id"], "sourceHandle": "text", "target": sn["id"], "targetHandle": "prompt"})
            for i in sh["faces"]:   # the speaker first: <Picture 1> is the one who talks
                if i in photos:
                    new_e.append({"id": uuid.uuid4().hex[:8], "source": heroes[i]["id"], "sourceHandle": "image", "target": sn["id"], "targetHandle": "faces"})
            g["edges"].extend(new_e)
            g["edges"].extend(e for e in theirs if e["targetHandle"] == "faces")   # the user's faces come after the writer's
            sn["data"]["wired"] = [e["id"] for e in new_e]
        gone = {nn["id"] for nn in g["nodes"] if nn["data"].get("from") == wid and not nn["data"].get("detached") and nn["id"] not in keep and nn["id"] not in hold and nn["type"] in ("prompt", "scene")}
        g["nodes"] = [nn for nn in g["nodes"] if nn["id"] not in gone]
        g["edges"] = [e for e in g["edges"] if e["source"] not in gone and e["target"] not in gone]
        mn = mine.get((wid, None, "montage"))
        if not mn:
            top = x0 + EXPAND_COLS * 640
            mn = {"id": uuid.uuid4().hex[:8], "type": "montage", "position": {"x": top, "y": y0},
                  "data": {"from": wid, "title": i18n.L("Серия", "Episode")}}
            g["nodes"].append(mn)
            on = {"id": uuid.uuid4().hex[:8], "type": "output", "position": {"x": top + 320, "y": y0},
                  "data": {"from": wid, "output": {"size": "1080p", "hdr": False, "fps48": False}}}
            g["nodes"].append(on)
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": mn["id"], "sourceHandle": "video", "target": on["id"], "targetHandle": "video"})
        g["edges"] = [e for e in g["edges"] if not (e["target"] == mn["id"] and e["targetHandle"] == "clips")]
        for sid in scene_ids:
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": sid, "sourceHandle": "clip", "target": mn["id"], "targetHandle": "clips"})
        mn["data"]["order"] = scene_ids
    out = update(pid, go)
    return {**out, "untranslated": bad, "kept": kept}


def screenplay_srt(pid: str, wid: str, names: bool = False) -> str:
    """«Экспорт .srt»: the lines' subtitles, timed by the shots in order - the lengths of the expanded scenes when the
    screenplay is expanded (the user may have changed them), else the lengths the words give."""
    from . import screenplay
    g = load(pid)
    w = node(g, wid)
    if not w or w["type"] != "screenplay":
        raise ValueError(i18n.L("Это не «Сценарий»", "This is not a «Screenplay»"))
    c = Ctx(projects.load(pid), g)
    _, shots, _, _ = _screenplay_shots(c, w)
    if not any(s["kind"] == "line" for s in shots):
        raise ValueError(i18n.L("В сценарии нет реплик", "The screenplay has no lines"))
    made = {nn["data"].get("scene"): nn for nn in g["nodes"] if nn["type"] == "scene" and nn["data"].get("from") == wid and not nn["data"].get("detached")}
    if len(made) == len(shots) and all(s["i"] in made for s in shots):
        for s in shots:
            s["seconds"] = int(seconds_of(made[s["i"]]))
    return screenplay.srt(shots, names)


# ---------------------------------------------------------------------------------------------------------------
TYPES: dict[str, dict] = {
    "idea":    {"title": "Идея", "who": "user", "in": {}, "out": {"text": "text"}},
    "hero":    {"title": "Герой", "who": "writer", "in": {}, "out": {"look": "look", "image": "image"}},
    "writer":  {"title": "Сценарист", "who": "writer", "in": {"idea": ("text", False), "cast": ("look", True)}, "out": {}},
    # «Песня → клип» in parts (2026-11-03): the song's piece, bars and words; the clip writer of the «Песня → клип» button
    "song":    {"title": "Песня", "who": "user", "in": {}, "out": {"song": "song", "audio": "audio"}},
    "clip_writer": {"title": "Сценарист клипа", "who": "writer", "in": {"song": ("song", False), "idea": ("text", False),
                                                                      "cast": ("look", False)}, "out": {}},
    # «Бит-клип» (2026-11-06): the shot pool of a beat clip (graph_beat.py)
    "pool_writer": {"title": "Сценарист пула", "who": "writer", "in": {"song": ("song", False), "idea": ("text", False),
                                                                    "cast": ("look", False)}, "out": {}},
    # a mini-series (2026-11-09): the series bible, and a screenplay in the «ИМЯ (как): слова» format (app/screenplay.py)
    "series":  {"title": "Сериал", "who": "user", "in": {}, "out": {"text": "text"}},
    "screenplay": {"title": "Сценарий", "who": "writer", "in": {"cast": ("look", True), "idea": ("text", False),
                                                                "series": ("text", False)}, "out": {}},
    "prompt":  {"title": "Промт", "who": "user", "in": {}, "out": {"text": "text"}},
    "photo":   {"title": "Фото", "who": "user", "in": {}, "out": {"image": "image"}},
    "picture": {"title": "Картинка", "who": "krea", "in": {"text": ("text", False), "ref": ("image", True)}, "out": {"image": "image"}},
    "scene":   {"title": "Сцена", "who": "h3", "in": {"prompt": ("text", False), "start": ("image", False),
                                                     "end": ("image", False), "faces": ("image", True), "lora": ("lora", True),
                                                     "clip": ("clip", False), "voice": ("audio", False), "sound": ("audio", False)},
                "out": {"frame": "image", "clip": "clip"}},
    "v2v":     {"title": "Видео → видео", "who": "v2v", "in": {"clip": ("clip", False), "prompt": ("text", False),
                                                            "image": ("image", True), "lora": ("lora", True)},
                "out": {"clip": "clip"}},
    "facefix": {"title": "Лица", "who": "facefix", "in": {"clip": ("clip", False), "prompt": ("text", False)}, "out": {"clip": "clip"}},
    "frame":   {"title": "Кадр", "who": "ffmpeg", "in": {"clip": ("clip", False)}, "out": {"image": "image"}},
    "sound":   {"title": "Звук сцены", "who": "ffmpeg", "in": {"clip": ("clip", False)}, "out": {"audio": "audio"}},
    "lora":    {"title": "LoRA", "who": "user", "in": {}, "out": {"lora": "lora"}},
    "join":    {"title": "Склейка", "who": "ffmpeg", "in": {"clips": ("clip", True)}, "out": {"video": "video"}},
    "montage": {"title": "Монтаж", "who": "ffmpeg", "in": {"clips": ("clip", True), "track": ("audio", False), "face": ("image", False)},
                "out": {"video": "video"}},
    # «Бит-монтаж» (2026-11-06): a pool of short shots cut on the beat of a song's drop (app/beatedit.py, its own process)
    "beat_montage": {"title": "Бит-монтаж", "who": "ffmpeg", "in": {"clips": ("clip", True), "track": ("song", False), "title": ("text", False)},
                     "out": {"video": "video"}},
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
MAKES = ("picture", "scene", "v2v", "facefix", "sound", "frame", "join", "montage", "beat_montage", "music", "output")
LLM_TYPES = ("writer", "hero", "clip_writer", "screenplay", "pool_writer")
LLM_BUTTONS = LLM_TYPES + ("prompt",)   # «Придумать реплики» of a prompt is a button too, never stale


# the node types' names in English (TYPES keeps the Russian ones)
_TITLES_EN = {"idea": "Idea", "hero": "Hero", "writer": "Writer", "song": "Song", "clip_writer": "Clip writer", "series": "Series", "screenplay": "Screenplay", "pool_writer": "Pool writer", "prompt": "Prompt", "photo": "Photo", "picture": "Picture",
              "scene": "Scene", "v2v": "Video → video", "facefix": "Faces", "frame": "Frame", "sound": "Scene sound", "join": "Join",
              "montage": "Montage", "beat_montage": "Beat montage", "track": "Track", "music": "Music", "output": "Output", "note": "Note", "group": "Group"}


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


LINES = ("smooth", "step", "straight")


def clean(g: dict) -> dict:
    """Only known node types; only edges between existing ports of the same type; a single input keeps its last edge.
    The editor's view (`view.lines`: how the links are drawn) is kept when it is one it knows."""
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
    out = {"rev": int(g.get("rev") or 0), "nodes": nodes, "edges": edges + list(single.values())}
    view = g.get("view") if isinstance(g.get("view"), dict) else {}
    if view.get("lines") in LINES:   # how the editor draws the links; none - its default (smooth)
        out["view"] = {"lines": view["lines"]}
    return out


def save(pid: str, g: dict, rev: Optional[int]) -> dict:
    """The client's graph; `rev` is the one it read. A newer graph on disk (a job wrote an LLM result, another tab)
    -> Conflict, the client takes the server's."""
    cur = load(pid)
    if rev is not None and rev != cur.get("rev", 0):
        raise Conflict()
    g = clean(g)
    drop_stale_hints(cur, g)
    g["rev"] = cur.get("rev", 0) + 1
    return _write(pid, g)


def drop_stale_hints(old: dict, new: dict) -> None:
    """A picture's `retry_hint` (the beat clip's redraw hint) belongs to the prompt, look and scene role it was drawn for: when
    the user edits one of them, the hint goes, or it would ride on the picture's text forever."""
    before = {n["id"]: n["data"] for n in old.get("nodes") or []}
    after = {n["id"]: n for n in new.get("nodes") or []}
    for nid, n in after.items():
        if n["type"] != "picture" or not n["data"].get("retry_hint") or nid not in before:
            continue
        was = before[nid]
        changed = any((was.get(k) or "") != (n["data"].get(k) or "") for k in ("prompt", "look"))
        for e in new.get("edges") or []:   # the role lives on the scene the picture starts
            if e["source"] == nid and (t := after.get(e["target"])) and t["type"] in ("scene", "ref_scene", "v2v") and e["target"] in before:
                changed = changed or (before[e["target"]].get("role") or "") != (t["data"].get("role") or "")
        if changed:
            n["data"].pop("retry_hint", None)


def update(pid: str, fn) -> dict:
    """A server-side change (a job's result, «Развернуть в сцены»): read the newest, change it, rev + 1."""
    g = load(pid)
    fn(g)
    g = clean(g)
    g["rev"] = load(pid).get("rev", 0) + 1
    return _write(pid, g)


def node(g: dict, nid: str) -> Optional[dict]:
    return next((n for n in g["nodes"] if n["id"] == nid), None)


def detach_copies(g: dict, wid: str, key) -> None:
    """A writer's nodes are found by `from` + a key (shot / scene / place, type). A Ctrl+C/V or a branch copy used to keep `from`
    and the key: two nodes then answer to one key and «Развернуть» deleted the user's original. The first one in the list is the
    writer's, the others are copies: `detached` (they keep `from` - the look logic reads it - but lose shot/made), theirs from now on."""
    seen: set = set()
    for nn in g["nodes"]:
        d = nn["data"]
        if d.get("from") != wid or d.get("detached") or nn["type"] not in ("picture", "prompt", "scene"):
            continue
        k = key(nn)
        if k in seen:
            d["detached"] = True
            for f in ("shot", "made"):
                d.pop(f, None)
        else:
            seen.add(k)


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
    lips: Optional[dict] = None      # a scene drawn under a given sound, shot: the lips' motion in the voiced / silent frames (checks.audio_lips)
    note: Optional[dict] = None      # «Лица», made: what it found and fixed (facefix.py)
    piece: Optional[list] = None     # «Песня»: [from, to] of the song the clip takes (song time)
    song: Optional[str] = None       # «Песня»: its id in the song library (song.py)
    beat: Optional[dict] = None      # «Бит-монтаж»: the beat renderer's cfg without `out` (_evaluate_beat)
    extra: dict = field(default_factory=dict)   # «Выход»: the phone copy and the cover (_output_extras)

    def public(self, folder: Path) -> dict:
        rel = lambda p: rel_path(folder, p)  # noqa: E731
        return {"state": self.state, "key": self.key, "file": rel(self.path), "png": rel(self.png), "error": self.error,
                "refs": self.refs, "seconds": self.seconds, "start_of": self.start_of,
                "takes": [{**t, "png": rel(t.get("png"))} for t in self.takes], **({"text": self.woven} if self.woven else {}),
                **({"alpha": rel(self.alpha)} if self.alpha else {}), **({"warn": self.warn} if self.warn else {}),
                **({"model": self.model, "ref_mode": self.ref["mode"]} if self.ref else {}),
                **({"voice": self.voice} if self.voice else {}), **({"checks": self.checks} if self.checks else {}),
                **({"lips": self.lips} if self.lips else {}),
                **({"note": self.note} if self.note else {}), **({"piece": self.piece} if self.piece else {}),
                **({"phone": rel(self.extra.get("phone")) if self.extra.get("phone") and self.extra["phone"].exists() else None,
                    "cover": rel(self.extra.get("cover")) if self.extra.get("cover") and self.extra["cover"].exists() else None,
                    "cover_at": self.extra.get("cover_at")} if self.extra else {})}


def rel_path(folder: Path, p: Optional[Path]) -> Optional[str]:
    """A file as the page asks for it: its path in the project, or "@<project>/…" for a shot in the cache of the
    storyboard this graph came from."""
    if not p:
        return None
    try:
        return p.relative_to(folder).as_posix()
    except ValueError:
        pass
    try:
        return "@" + p.relative_to(projects.ROOT).as_posix()
    except ValueError:
        pass
    # an actor's picture (data/actors/<id>/face.png, or data/series/<sid>/actors/<id>/…): the actors API serves it
    if p.parent.parent.name == "actors" and p.stem in ("face", "turn", "photo", "ref"):
        series = p.parent.parent.parent
        q = f"?series={series.name}" if series.parent.name == "series" else ""
        return f"/api/actors/{p.parent.name}/image/{p.stem}{q}"
    return None


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
        for nid, n in list(self.by.items()):   # a hero from the actor library: the actor's look and face panel (a node without `actor` is as it was)
            if n["type"] == "hero" and isinstance(n["data"].get("actor"), str) and n["data"]["actor"]:   # a non-string actor is ignored
                from . import actors
                self.by[nid] = {**n, "data": actors.hero_data(n["data"], actors.library_for(proj, n["data"]["actor"]))}
        self.ins: dict[str, dict[str, list[tuple[str, str]]]] = {n["id"]: {} for n in g["nodes"]}
        for e in g["edges"]:
            if e["target"] in self.ins:
                self.ins[e["target"]].setdefault(e["targetHandle"], []).append((e["source"], e["sourceHandle"]))
        # where cached shots may also be: the storyboard projects this graph was made from (their keys are the same)
        self.caches = [self.folder / "scenes"] + [projects.ROOT / p / "scenes" for p in st.get("cache_from") or []
                                                   if (projects.ROOT / p / "scenes").exists()]
        self.memo: dict[str, Art] = {}
        self.force_preview: set[str] = set()   # beat montages evaluated as their 540x960 preview (beat_clip.preview)

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


def seconds_of(n: dict) -> float:
    """A scene's length: its own `seconds` (3-15), 5 when it says nothing. A clip's scene (`cut`: its bar span, made by
    «Сценарист клипа») is as long as its bars - 1.5 s and fractions too."""
    try:
        if isinstance(n["data"].get("cut"), dict):
            return max(0.5, min(float(MAX_S), float(n["data"].get("seconds") or LENGTH_S)))
        return max(MIN_S, min(MAX_S, int(n["data"].get("seconds") or LENGTH_S)))
    except (TypeError, ValueError):
        return LENGTH_S


def scene_card(c: "Ctx", n: dict) -> tuple[videomodels.Card, int, int]:
    """(model, width, height) a scene is shot with: its own `model` (a clip's singing scene: the model that sings to the
    track; another model for one scene) or the graph's. A scene without one keeps the graph's - and its keys."""
    m = n["data"].get("model")
    if m and m in videomodels.CARDS and m != c.card.id and videomodels.offered(m):
        card = videomodels.card(m)
        w, h = c.own or render.size(c.settings, card)
        return card, w, h
    return c.card, c.w, c.h


def scene_frames(c: "Ctx", n: dict, card: videomodels.Card) -> tuple[float, int]:
    """(the seconds a scene's shot is, its pre-roll in frames). A clip's scene from a picture (`cut.pre`, set by
    «Развернуть в сцены» as the button's clip.preroll) is shot that many frames longer: i2v's first frames are the
    still picture, the montage starts the scene after them and its piece of the song starts that much earlier - fitted
    as the button's (render.preroll_fit). Anything else: (its length, 0) - an older graph's keys stay."""
    secs = min(seconds_of(n), card.max_seconds)
    cut = n["data"].get("cut")
    want = cut.get("pre") if isinstance(cut, dict) else None
    if not (isinstance(want, int) and not isinstance(want, bool) and want > 0 and c.inputs(n["id"], "start")
            and start_scene(c, n["id"]) is None):   # a continuation starts on a moving frame: nothing to cut
        return secs, 0
    a, b = float(cut.get("start") or 0), float(cut.get("end") or 0)
    pre = render.preroll_fit(want, a, a, b)
    secs = min(seconds_of(n) + pre / graphs.FPS, float(card.max_seconds))
    return secs, render.preroll_fit(want, a, a, b, videomodels.frames(card, secs))


def scene_track(c: "Ctx", n: dict, card: videomodels.Card, pre: int = 0) -> tuple[Optional[Path], float, list]:
    """A clip's scene shot to the song (its `cut` and a «Песня» on its «голос» input, a model that takes a track - LTX
    2.3): (the file, where its piece begins in it - `pre` frames before its bar, scene_frames -, the inputs' arts); a
    performance or an insert gets the song without its voice, as the button's clip (render.scene_track). Anything
    else: (None, 0, [])."""
    cut = n["data"].get("cut")
    src = c.inputs(n["id"], "voice")
    if not (isinstance(cut, dict) and card.track and src and src[0][0] in c.by):
        return None, 0.0, []
    a = _out(c, *src[0])
    if a.state != "ready" or not a.path:
        return None, 0.0, [a]
    path = a.path
    if cut.get("voice") is False and a.song:
        from . import song
        path = song.no_vocals(a.song) or path
    return path, round(float(cut.get("start") or 0) - pre / graphs.FPS, 3), [a]


def scene_sound(c: "Ctx", n: dict, card: videomodels.Card) -> tuple[Optional[Path], float, list]:
    """The sound an H3 scene is drawn UNDER (graphs.scene's `audio`): (the file, where its piece begins in it in seconds,
    the inputs' arts to wait for). It is the «звук» input's audio (a «Трек», a recorded or uploaded voice, a «Звук
    сцены»; the scene's `sound_from` says where its piece begins), else the «Промт»'s only line that has its own sound
    (`audio` in the line: an uploaded or recorded file of the project). Not «голос»: that input is a SAMPLE of a voice
    (ID-LoRA) or a song to shoot to (LTX 2.3), a sound to imitate; «звук» is what is actually heard in the shot. Only H3 draws
    under a sound; anything else: (None, 0, [])."""
    if card.id != "h3":
        return None, 0.0, []
    src = c.inputs(n["id"], "sound")
    if src and src[0][0] in c.by:
        a = _out(c, *src[0])
        if a.state != "ready" or not a.path or not a.path.exists():
            return None, 0.0, [a]
        try:
            at = max(0.0, float(n["data"].get("sound_from") or 0))
        except (TypeError, ValueError):
            at = 0.0
        return a.path, round(at, 3), [a]
    pr = c.inputs(n["id"], "prompt")
    if pr and pr[0][0] in c.by:
        pa = _out(c, *pr[0])
        own = [ln for ln in pa.lines if ln.get("audio")]
        if len(pa.lines) == 1 and len(own) == 1:   # one spoken line and it has its sound: the scene is drawn under it
            p = c.folder / own[0]["audio"]
            if p.is_file():
                return p, 0.0, [pa]
    return None, 0.0, []


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
    if t == "series":
        text = series_text(d)
        return Art("ready", text=text, key=_sha(text)) if text else Art("empty")
    if t == "screenplay":
        return Art("ready" if (d.get("text") or "").strip() else "empty")
    if t == "lora":
        items = [{"id": x["id"], "strength": float(x.get("strength", 0.8))} for x in d.get("items") or [] if x.get("id")]
        return Art("ready", loras=items, key=_sha(items))
    if t == "track":
        p = c.folder / d["file"] if d.get("file") else None
        if not p or not p.exists():
            return Art("error", error=i18n.L("нет файла трека", "no track file"))
        return Art("ready", path=p, key=music.signature(c.folder, {"file": d["file"]}))
    if t == "song":
        return _evaluate_song(c, n)
    if t == "clip_writer":
        if not d.get("plan"):
            return Art("empty")
        return Art("stale" if d.get("sig") != clip_writer_sig(c, n) else "ready")

    if t == "pool_writer":
        from . import graph_beat
        if not d.get("pool"):
            return Art("empty")
        return Art("stale" if d.get("sig") != graph_beat.sig(c, n) else "ready")

    if t == "picture":
        src = ins("text")
        if src:
            if (u := _upstream(c, src)):
                return u
            text = src[0].picture or src[0].text   # a prompt that feeds a scene too: its picture text, a still's
        else:
            text = (d.get("prompt") or "").strip()
        text = picture_in_look(d.get("look"), text) if text else text   # a drawn look: its medium, no photo words
        if text and (rh := (d.get("retry_hint") or "").strip()):   # the beat clip's redraw hint the kept picture was drawn with: in the text, so in the key
            text = f"{text} {rh}"
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
        pr, start, faces, lo, end, snd = ins("prompt"), ins("start"), ins("faces"), ins("lora"), ins("end"), ins("sound")
        if (u := _upstream(c, pr + start + faces + lo + end + snd)):
            return u
        loras = [x for a in lo for x in a.loras]
        from . import loras as lora_lib
        refl = [x for x in loras if (i := lora_lib.get(x["id"])) and i.v2v]
        if refl:   # a LoRA that reads a clip or a voice: the scene is made its way
            return _evaluate_ref_scene(c, n, ins, refl, [x for x in loras if x not in refl])
        if not pr:
            return Art("error", error=i18n.L("нет промта: подключите узел «Промт»", "no prompt: connect a «Prompt» node"))
        card, w, h = scene_card(c, n)
        secs, pre = scene_frames(c, n, card)   # the model shoots no longer than its limit; a clip's pre-roll in it
        tr, tr_at, tr_arts = scene_track(c, n, card, pre)
        if (u := _upstream(c, tr_arts)):
            return u
        au, au_from, _ = scene_sound(c, n, card)
        ak = {"audio": au, "audio_from": au_from} if au else {}   # no sound: the keys as they were
        st = start[0].path if start else None
        en = end[0].path if end and card.ends else None   # flf2v: the scene comes to this picture (LTX)
        refs = [a.path for a in faces if a.path] if card.refs else []
        fit = render.start_crop(st, w, h, "continue" if start and start[0].start_of else "new")   # a photo's face
        length = videomodels.frames(card, secs)
        text = scene_text(c, nid)
        old = scene_text(c, nid, legacy=True)   # a drawn look rewrites a hand-written prompt now; 0.3.0 shot it as written
        if old == text:
            old = None

        def shot_of(s: int) -> tuple[str, Optional[tuple[Path, Path]], str]:
            """(key, cached shot, the prompt it holds) of seed s: a shot made with the earlier prompt is kept, not reshot."""
            k = render.scene_key(text, s, w, h, length, loras, st, refs, card.id, tr, tr_at, end=en, fit=fit, **ak)
            hit = c.cached_shot(k)
            if not hit and old:
                k0 = render.scene_key(old, s, w, h, length, loras, st, refs, card.id, tr, tr_at, end=en, fit=fit, **ak)
                if (hit0 := c.cached_shot(k0)):
                    return k0, hit0, old
            return k, hit, text

        takes = []
        for s in [int(x) for x in d.get("takes") or []] or [seed_of(n)]:
            k, hit, _ = shot_of(s)
            takes.append({"seed": s, "key": k, "cached": bool(hit), "png": hit[1] if hit else None})
        seed = seed_of(n)
        key, hit, text = shot_of(seed)
        a = Art("ready" if hit else "todo", key=key, text=text, loras=loras, refs=bool(refs), takes=takes,
                start_of=start[0].start_of if start else None, seconds=secs, woven=text if pr[0].lines else None,
                model=card.id if card is not c.card else None)
        if c.inputs(nid, "clip") or (c.inputs(nid, "voice") and not tr):
            a.warn = i18n.L("входы «сцена» и «голос» читает только LoRA по образцу (во входе «LoRA»): эта сцена снимется без них",
                            "only a sample LoRA (in the «LoRA» input) reads the «scene» and «voice» inputs: this scene will be shot without them")
        elif snd and card.id != "h3":
            a.warn = i18n.L(f"{card.name} не снимает под готовый звук: вход «звук» возьмёт только H3 — сцена снимется без него",
                            f"{card.name} can't be shot under a given sound: only H3 takes the «sound» input — the scene will be shot without it")
        elif end and not card.ends:
            a.warn = i18n.L(f"{card.name} не умеет приходить к кадру: вход «конец» возьмёт только LTX — сцена снимется без него",
                            f"{card.name} can't end on a frame: only LTX takes the «end» input — the scene will be shot without it")
        if hit:
            a.path, a.png = hit
            a.checks = checks.saved(a.path)
            a.lips = checks.saved_lips(a.path) if au else None
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
        tra = ins("track")
        if (u := _upstream(c, tra)):
            return u
        if d.get("beats") and not (tra and tra[0].song):
            return Art("error", error=i18n.L("«По тактам» нужна «Песня» во входе «трек»: по её тактам режутся сцены",
                                             "«On the bars» needs a «Song» at the «track» input: the scenes are cut on its bars"))
        ed = montage_of(c, nid)
        if not ed["complete"]:
            return Art("error", error=i18n.L("в монтаже дубль, который ещё не снят: снимите его или верните дубль сцены",
                                         "the montage has a take not shot yet: shoot it or switch the scene back to its take"))
        track = montage_track(c, nid, ed)   # no track: the key as it was
        key = _sha("montage", edit.signature(ed), *(["track", track, tra[0].key] if track else []))
        p = c.folder / "out" / f"montage_{key}.mp4"
        cuts = _cuts(p)
        a = Art("ready" if p.exists() and cuts is not None else "todo", key=key, path=p, cuts=cuts or [], seconds=ed["duration"])
        if d.get("faces") and not face_judged(c, nid) and (any(faceless_src(c, s) for s, _ in c.inputs(nid, "face"))
                                                           or any(faceless_src(c, s) for sid in join_order(c, nid) for s, _ in c.inputs(sid, "faces"))):
            a.warn = i18n.L("«Проверять лица»: у героя нет лица (животное, робот или существо) — лица не проверяются",
                            "«Check the faces»: the hero has no face (an animal, a robot or a creature), so the faces are not checked")
        elif d.get("faces") and not face_judged(c, nid):   # «Проверять лица»: the face on «лицо», or a film scene's own «лица»
            a.warn = i18n.L("«Проверять лица» без входа «лицо»: подключите фото или портрет героя — иначе лица не проверятся",
                            "«Check the faces» without the «face» input: connect the hero's photo or portrait — otherwise the faces are not checked")
        return a

    if t == "beat_montage":
        return _evaluate_beat(c, n, ins)

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
            a = Art("ready", key=v[0].key, path=v[0].path, seconds=v[0].seconds)
        else:
            key = _sha("output", v[0].key, out, c.aspect)
            p = c.folder / "out" / f"{key}.mp4"
            a = Art("ready" if p.exists() else "todo", key=key, path=p, cuts=v[0].cuts, seconds=v[0].seconds)
        if d.get("phone") or d.get("cover"):
            _output_extras(c, d, a, v[0])
        return a
    return Art("idle")


PHONE_MB = 10.0   # the phone copy's size limit (TikTok's upload limit)


def cover_time(d: dict, src: Art) -> float:
    """The cover's second: the node's `cover_at`, else the drop's impact (the beat montage saves it beside its file), else 0."""
    if d.get("cover_at") not in (None, ""):
        try:
            return max(0.0, float(d["cover_at"]))
        except (TypeError, ValueError):   # a stored value that is not a number: the drop's frame, as without one
            pass
    try:
        return float(json.loads(src.path.with_suffix(".json").read_text(encoding="utf-8"))["drop"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


def _output_extras(c: Ctx, d: dict, a: Art, src: Art) -> None:
    """The output's phone copy (<= PHONE_MB) and cover frame, when its switches are on: files next to the output, named by its
    key (the cover also by its second). The output is `todo` until they exist."""
    a.extra = {"cover_at": round(cover_time(d, src), 2)}
    if d.get("phone"):
        a.extra["phone"] = c.folder / "out" / f"phone_{a.key}.mp4"
    if d.get("cover"):
        a.extra["cover"] = c.folder / "out" / f"cover_{a.key}_{int(round(a.extra['cover_at'] * 100))}.png"
    if a.state == "ready" and any(not p.exists() for k, p in a.extra.items() if k in ("phone", "cover")):
        a.state = "todo"


BEAT_RENDER_S = 4.2   # a beat montage renders about this many seconds per second of its clip on the CPU (measured 2026-11-06: 96-103 s for a 24 s clip, 1080x1920, 60 fps)


def beat_roles(c: Ctx, ids: list[str]) -> list[str]:
    """The roles of a «Бит-монтаж»'s shots (hero | atmos | close | impact | riser): each scene's own `role`; a scene with
    none is a hero or an atmosphere in turn."""
    from . import beatedit
    return [r if (r := c.by[s]["data"].get("role")) in beatedit.ROLES else beatedit.default_role(k) for k, s in enumerate(ids)]


def song_sig(sid: str) -> str:
    """A song file's identity for a pinned drop: its size and time of change."""
    from . import song
    st = song.file_of(sid).stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def beat_drop(d: dict, sid: str) -> float:
    """The drop of a beat montage: the user's (data.drop), else the one pinned when the clip's window was made (data.drop_auto,
    valid while the song file is the same), else the song's own guess. autopilot.drop_at moves with the recognised words and the
    lyrics text, so a drop that is not pinned would re-cut the montage after every edit of the words."""
    from . import autopilot
    if d.get("drop") not in (None, "", 0):
        return float(d["drop"])
    pin = d.get("drop_auto")
    if isinstance(pin, dict) and pin.get("drop") is not None:
        try:
            if pin.get("sig") == song_sig(sid):
                return float(pin["drop"])
        except (OSError, EngineError, ValueError, TypeError):
            pass
    return autopilot.drop_at(sid)


def _evaluate_beat(c: Ctx, n: dict, ins) -> Art:
    """«Бит-монтаж»: the scenes on `clips` are the pool, the «Песня» on `track` gives the beat grid, the words and the drop,
    `title` (a text) the clip's title. Its key is the scenes' keys with their roles, the song's, the window and every
    parameter - a change that only touches the render (a preset, a colour) leaves the scenes alone."""
    from . import autopilot, beat_models, beatedit, song
    d, nid = n["data"], n["id"]
    if not c.inputs(nid, "clips"):
        return Art("error", error=i18n.L("нет сцен на входе", "no scenes at the input"))
    ids = join_order(c, nid)
    arts = [_out(c, s, "clip") for s in ids]
    tra, tit = ins("track"), ins("title")
    if (u := _upstream(c, arts + tra + tit)):
        return u
    if not (tra and tra[0].song):
        return Art("error", error=i18n.L("«Бит-монтаж» нужна «Песня» во входе «трек»: по её долям режутся сцены",
                                         "«Beat montage» needs a «Song» at the «track» input: the scenes are cut on its beats"))
    sid = tra[0].song
    try:
        an = song.analysis(sid)
        recd = song.recognised(sid)
        drop = beat_drop(d, sid)
        src = song.file_of(sid)
        text_f = song.folder(sid) / "text.txt"
        written = text_f.read_text(encoding="utf-8") if text_f.exists() else None
    except (EngineError, OSError, ValueError, TypeError) as e:
        return Art("error", error=str(e))
    if len(an.beats) < 8:   # the same condition as beatedit.make_grid's
        return Art("error", error=i18n.L("в песне слишком мало долей для бита (меньше 8): нужна песня с ровным ритмом",
                                         "the song has too few beats (fewer than 8): a song with a steady rhythm is needed"))
    roles = beat_roles(c, ids)
    words = [{"start": w["start"], "end": w["end"], "word": w["word"]} for line in (recd or {}).get("lines", []) for w in line.get("words", [])]
    known = beatedit.PRESETS["techno"]
    over = {k: v for k, v in (d.get("params") or {}).items() if k in known} if isinstance(d.get("params"), dict) else {}
    pal = d.get("palette") if isinstance(d.get("palette"), dict) else {}
    # the clip's title: a text on «title», else data.clip_title (data.title is the card's own name «Бит-монтаж», which
    # the first beat clips of 2026-11-06 drew as their title), else the song's name; the sung words are never filtered, the title is
    own_title = tit[0].text if tit else (d["clip_title"] if "clip_title" in d else song.title_of(sid))
    title = looks.clean_text((own_title or "").strip())
    edits = [e for e in d.get("caption_edits") or [] if isinstance(e, dict) and "i" in e]
    try:
        fps = 30 if int(d.get("fps") or 60) == 30 else 60
        loud = float(d["loudness"]) if d.get("loudness") not in (None, "") else beatedit.DEFAULTS["loudness"]
        bpm = float(d["bpm"]) if d.get("bpm") not in (None, "") else None
    except (TypeError, ValueError):
        return Art("error", error=i18n.L("громкость, темп или кадры в секунду — не число", "the loudness, tempo or frames per second is not a number"))
    preset = d.get("preset") if d.get("preset") in beatedit.PRESETS else "techno"
    preview = bool(d.get("preview")) or nid in c.force_preview
    pres = [beat_models.preroll(scene_card(c, c.by[s])[0].id) if c.by[s]["type"] == "scene" else beat_models.preroll(None) for s in ids]
    cfg = {"clips": [{"id": s, "path": str(a.path), "role": r, "pre": p_} for s, a, r, p_ in zip(ids, arts, roles, pres)],
           "song": str(src), "analysis": {"beats": an.beats, "bpm": an.bpm}, "drop": round(drop, 4), "bpm": bpm,
           "words": words, "written": written, "title": title, "hud": looks.clean_text((d.get("hud") or "").strip()), "palette": pal,
           "preset": preset, "params": over, "fps": fps, "loudness": loud, "preview": preview, "caption_edits": edits}
    # the scenes' keys + roles, the song (its id, not the song node's key: that one holds the node's piece, which the montage
    # does not use), the drop, then everything that only the render reads
    # a scene's pre-roll is in the key only when it is not H3's (the montage plays from there): an H3 beat project keeps its keys
    key = _sha("beat", [(a.key, r) + (() if p_ == beatedit.PRE_DEFAULT else (p_,)) for a, r, p_ in zip(arts, roles, pres)], sid, cfg["drop"], bpm, preset, over, pal, title, cfg["hud"],
               fps, loud, preview, _sha(words, written, edits), beatedit.VERSION)
    p = c.folder / "out" / f"beat_{key}.mp4"
    cuts = _cuts(p)
    p_ = beatedit.params_of(cfg)
    secs = (p_["build_bars"] + p_["drop_bars"] + 2) * 4 * an.beat_s
    try:
        secs = float(json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))["dur"]) if p.exists() else secs
    except (OSError, ValueError, KeyError):
        pass
    a = Art("ready" if p.exists() and cuts is not None else "todo", key=key, path=p, cuts=cuts or [], seconds=round(secs, 3), beat=cfg)
    if "close" not in roles:
        a.warn = i18n.L("нет шота с ролью «крупный план» (close): вступление и концовка возьмут героя",
                        "no shot with the «close» role: the intro and the outro take a hero shot")
    return a


async def _run_beat(cfg_file: Path, on_progress) -> tuple[int, str, list[str]]:
    """app.beatedit on a cfg as a process of its own (the CPU render must not hold this loop): (exit code, the error it
    printed, the last lines). A plain Popen read in a thread, like song._tool: under `uvicorn --reload` on Windows the loop
    is a selector loop, where asyncio.create_subprocess_exec raises NotImplementedError."""
    import sys
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env.update(FFMPEG=config.FFMPEG, PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen([sys.executable, "-u", "-m", "app.beatedit", str(cfg_file)], cwd=str(config.ROOT), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW, **({} if os.name == "nt" else {"start_new_session": True}))
    tail: list[str] = []
    error: list[str] = []
    loop = asyncio.get_running_loop()

    def read() -> int:
        assert proc.stdout
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            tail.append(line)
            del tail[:-20]
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("error"):
                error.append(msg["error"])
            elif isinstance(msg, dict) and msg.get("stage"):
                loop.call_soon_threadsafe(on_progress, msg)
        return proc.wait()
    try:
        code = await asyncio.to_thread(read)
    except asyncio.CancelledError:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
        else:   # its own session (start_new_session): the whole group goes
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
        raise
    return code, (error[0] if error else ""), tail


def _pin_beat_drop(c: Ctx, x: str, a: Art) -> None:
    """A montage built by hand (not by the beat clip's button) has no pinned drop, so it would follow every edit of the words.
    Evaluation stays pure; the first build pins the drop it was built with (the same value, so the cache key does not change)."""
    d = c.by[x]["data"]
    if d.get("drop") not in (None, "", 0) or d.get("drop_auto") or not a.beat or a.beat.get("drop") is None:
        return
    try:
        sid = _out(c, *c.inputs(x, "track")[0]).song
        pin = {"drop": a.beat["drop"], "sig": song_sig(sid)}

        def put(g: dict) -> None:
            if (n := node(g, x)) and n["data"].get("drop") in (None, "", 0) and not n["data"].get("drop_auto"):
                n["data"]["drop_auto"] = pin
        update(c.pid, put)
    except (EngineError, OSError, ValueError, TypeError, IndexError, KeyError):
        pass   # a pin is a convenience: a build never fails for it


async def _make_beat(job: jobs.Job, x: str, a: Art) -> None:
    """The beat montage's file: its cfg next to it, the renderer's progress into the node's row of the job."""
    a.path.parent.mkdir(exist_ok=True)
    cfg_file = a.path.with_suffix(".cfg.json")
    cfg_file.write_text(json.dumps({**a.beat, "out": str(a.path)}, ensure_ascii=False), encoding="utf-8")
    job.phase = "rendering"
    row = job.progress.get("nodes", {}).get(x, {})
    label = {"plan": "grid", "audio": "sound", "shots": "shots", "frames": "frames"}

    def on_progress(m: dict) -> None:
        if m.get("stage") == "done":
            return
        row.update(stage=m.get("stage"), done=m.get("done"), total=m.get("total"))
        job.progress["message"] = f"{label.get(m.get('stage'), m.get('stage'))} {m.get('done')}/{m.get('total')}"
    try:
        code, error, tail = await _run_beat(cfg_file, on_progress)
    finally:
        cfg_file.unlink(missing_ok=True)
    if code != 0 or not a.path.exists():
        raise EngineError(i18n.L("Бит-монтаж не собрался: ", "The beat montage failed: ") + (error or "\n".join(tail[-4:])))


LENGTHS = ("whole", "best", "own", "drop")   # «Песня»: the whole song, the best minute (autopilot.window), a piece of its own, the drop (beat clip)


def song_piece(sid: str, d: dict) -> tuple[float, float]:
    """(from, to) of the song a «Песня» node gives, in the song's time: the «Песня → клип» button's piece
    (autopilot.window, then snapped to the bars as start_clip does - clip.fragment)."""
    from . import autopilot, song
    from .planner import clip
    length = d.get("length") if d.get("length") in LENGTHS else "whole"
    secs = float(d["seconds"]) if length != "whole" and d.get("seconds") else None
    start, seconds = autopilot.window(sid, length, secs, max(0.0, float(d.get("start") or 0)))
    return clip.fragment(song.analysis(sid), start, max(4.0, seconds))


def _evaluate_song(c: Ctx, n: dict) -> Art:
    """«Песня»: a song of the song library (its bars and parts known on upload, the words once recognised) and the
    piece of it the clip takes. Ready when its file is in the project; its key - the song, the piece, the words."""
    from . import song
    d = n["data"]
    p = c.folder / d["file"] if d.get("file") else None
    if not d.get("song") or not p or not p.exists():
        return Art("error", error=i18n.L("нет песни: загрузите её в узел", "no song: upload it into the node"))
    try:
        ex0, ex1 = song_piece(d["song"], d)
        words = song.lines(d["song"])
    except EngineError as e:
        return Art("error", error=str(e))
    return Art("ready", path=p, song=d["song"], piece=[round(ex0, 3), round(ex1, 3)], seconds=round(ex1 - ex0, 3),
               key=_sha("song", d["song"], round(ex0, 3), round(ex1, 3), words))


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
        old = v2v.prompt_of(prof, scene_text(c, nid, legacy=True) or "")   # 0.3.0 shot it as written, before a drawn look rewrote it
        if old == text:
            old = None
        if prof["prompt"] == "required" and not (pa and pa.text) and not prof["template"]:
            return Art("error", error=i18n.L("этой LoRA нужен промт: что сделать с клипом", "this LoRA needs a prompt: what to do with the clip"))
        pics = [a.path for a in faces if a.path] if eng == "h3" else []
        extra = sorted(({"id": x["id"], "strength": round(float(x["strength"]), 3)} for x in lora_lib.for_model(plain, eng)),
                       key=lambda x: x["id"])
        guide = round(float(d.get("guide", 1.0)), 3)
        weights = [config.H3_REF_UNET, config.H3_REF_LORA, config.H3_CLIP, config.H3_VAE, graphs.REF_STEPS] if eng == "h3" else \
            [getattr(config, k) for k in card.keys]
        shas = [render.file_sha(p) for p in pics]

        def key_for(s: int, t: str = text) -> str:   # the «Видео → видео» key's parts, as a scene's
            return _sha("v2v-scene", clip_in[0].key, info.id, info.size_mb, strength, guide if eng != "h3" else None, s, t, shas,
                        extra, v2v.key_of(prof), weights)
        unused += [i18n.L("«старт»", "«start»")] if start else []
        unused += [i18n.L("«голос»", "«voice»")] if voice_in else []
        unused += [i18n.L("«лица»", "«faces»")] if faces and eng != "h3" else []
        ref = {"mode": "clip", "info": info, "prof": prof, "strength": strength, "guide": guide, "pics": pics, "extra": extra,
               "clip": clip_in[0]}
        a = _ref_art(c, key_for, seeds, seed, old=old, text=text, seconds=clip_in[0].seconds, model=eng, ref=ref, loras=extra)
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


def _ref_art(c: Ctx, key_for, seeds: list[int], seed: int, old: Optional[str] = None, **kw) -> Art:
    """A reference scene's Art: its takes and its shot, here or in a cache, as a scene's. `old`: the prompt as 0.3.0 had it
    (key_for(s, old)) - a shot made with it is kept, not reshot."""
    def shot_of(s: int) -> tuple[str, Optional[tuple[Path, Path]], bool]:
        k = key_for(s)
        hit = c.cached_shot(k)
        if not hit and old:
            k0 = key_for(s, old)
            if (hit0 := c.cached_shot(k0)):
                return k0, hit0, True
        return k, hit, False
    takes = []
    for s in seeds:
        k, hit, _ = shot_of(s)
        takes.append({"seed": s, "key": k, "cached": bool(hit), "png": hit[1] if hit else None})
    key, hit, was_old = shot_of(seed)
    if was_old:
        kw["text"] = old
    a = Art("ready" if hit else "todo", key=key, takes=takes, **kw)
    a.path, a.png = hit if hit else render.shot_paths(c.folder / "scenes", key)
    a.checks = checks.saved(a.path) if hit else None
    return a


def scene_text(c: Ctx, nid: str, legacy: bool = False) -> Optional[str]:
    """What H3 gets as a scene's prompt: its «Промт»'s text with the spoken lines woven in for the scene's length
    (prompts.weave_lines; without lines - the text as it is). None: no prompt or an empty one."""
    pr = c.inputs(nid, "prompt")
    a = _out(c, *pr[0]) if pr and pr[0][0] in c.by else None
    if not a or a.state != "ready":
        return None
    text = look_text(c, nid, pr[0][0], a.text, legacy)
    return prompts.weave_lines(text, a.lines, math.ceil(seconds_of(c.by[nid])), i18n.plan_lang_name(c.proj)) if a.lines else text


def project_look(proj: dict) -> Optional[str]:
    """The graph's «Стиль проекта» look fragment when one is chosen («Решит сценарист» - none: the writer's plan has
    its own)."""
    st = proj.get("settings") or {}
    if "delivery" not in st or str(st.get("look") or looks.AUTO) == looks.AUTO:
        return None
    return looks.look_of(dict(st))["style_en"] or None


def look_text(c: Ctx, nid: str, src: str, text: str, legacy: bool = False) -> str:
    """A scene's prompt in its look: the scene's own (its node's `look`, the chip ◆ on it) or the project's. A writer's
    prompt already starts with its plan's look (look_style) - that one is swapped; a prompt written by hand gets the
    look's words in front. Nothing chosen: the text as it is (an older graph's keys stay). `legacy`: the text as it was
    before a drawn look rewrote it (a73783a) - for finding a shot made in 0.3.0 (see the scene node's cache lookup)."""
    d = c.by[nid]["data"]
    own = d.get("look") if d.get("look") in looks.LOOKS and d.get("look") != looks.AUTO else None
    out = _look_swap(c, nid, src, text, own)
    lid = scene_look(c, nid)
    # live looks, none, an older graph, and a writer's prompt (its plan holds the look itself; its shot scenes keep
    # their cache keys): the text as it was
    if legacy or not looks.drawn_of(lid) or ((c.by.get(src) or {}).get("data") or {}).get("from"):
        return out
    out = looks.unphoto_text(out)
    lk = looks.LOOKS[lid]
    if looks.frame_look(lid):   # H3 holds a drawn look from a picture, not from words (see frame_look_of)
        start = bool(c.inputs(nid, "start"))
        add = lk["tech_en"] if start else lk["frame_en"]
        if add.lower() in out.lower():   # a writer's plan of looks_v 2 has said it already
            return out
        return f"{out} {add}" if start else f"{add} {out}"
    return out


def scene_look(c: Ctx, nid: str) -> Optional[str]:
    """The look id in effect for scene `nid`: its own (the chip ◆), else the project's «Стиль проекта»; None: not chosen."""
    d = c.by[nid]["data"]
    if d.get("look") in looks.LOOKS and d.get("look") != looks.AUTO:
        return d["look"]
    st = c.proj.get("settings") or {}
    if "delivery" not in st or str(st.get("look") or looks.AUTO) == looks.AUTO:
        return None
    return looks.resolve(dict(st))[1]


def frame_look_of(c: Ctx, nid: str) -> Optional[str]:
    """A scene's look when it is drawn by every frame (FRAME_LOOKS) and the scene has no «старт» picture: the interface
    offers to draw the first frame. None otherwise."""
    if c.by[nid]["type"] != "scene" or c.inputs(nid, "start"):
        return None
    lid = scene_look(c, nid)
    return lid if looks.frame_look(lid) else None


def picture_in_look(look: Optional[str], text: str) -> str:
    """A «Картинка» node's prompt in a drawn-by-frame look: the look's medium in front, the photographic words out."""
    if not looks.frame_look(look):
        return text
    return f"{looks.LOOKS[look]['frame_en']} {looks.unphoto_text(text)}"


def _look_swap(c: Ctx, nid: str, src: str, text: str, own: Optional[str]) -> str:
    pn = c.by.get(src) or {}
    w = c.by.get((pn.get("data") or {}).get("from")) or {}
    have = (((w.get("data") or {}).get("plan")) or {}).get("look_style") or ""
    want = looks.LOOKS[own]["style_en"] if own else project_look(c.proj) or have
    if not want:
        return text
    if have and (m := re.search(re.escape(have), text, re.I)):
        if want.lower() == have.lower():
            return text
        rep_ = want[0].upper() + want[1:] if m.group(0)[:1].isupper() else want
        return text[:m.start()] + rep_ + text[m.end():]
    if re.search(re.escape(want), text, re.I):
        return text
    return f"{want[0].upper()}{want[1:]}. {text}"


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
    if beat_s := montage_beat(c, nid):
        on_bars(c, items, beat_s)
    return items


def montage_song(c: Ctx, nid: str) -> Optional[Art]:
    """The «Песня» on a «Монтаж» node's «трек» input, ready, or None."""
    src = c.inputs(nid, "track")
    a = _out(c, *src[0]) if src and src[0][0] in c.by else None
    return a if a and a.state == "ready" and a.song else None


def montage_beat(c: Ctx, nid: str) -> Optional[float]:
    """«По тактам» (`beats`) with a «Песня» on the track: the song's beat (seconds); otherwise None."""
    if not c.by[nid]["data"].get("beats") or not (a := montage_song(c, nid)):
        return None
    from . import song
    return song.analysis(a.song).beat_s


def on_bars(c: Ctx, items: list[dict], beat_s: float) -> None:
    """«Склейка по тактам»: a clip's scene (`cut`, «Сценарист клипа») plays its bars, from the frame its bar starts on
    to the frame the next one does (edit.resolve's `want`, the button's clip); any other scene - an intro, an ending
    of the user's - whole beats of its length, at least one, so every cut after it still falls on a beat. A cut into a
    loud part after a quiet one flashes, as the button's clip does (`accent`)."""
    loud_before = False
    for it in items:
        n = c.by[it["id"]]
        if n["type"] != "scene":
            continue
        cut = n["data"].get("cut") if isinstance(n["data"].get("cut"), dict) else None
        card, _, _ = scene_card(c, n)
        secs, pre = scene_frames(c, n, card)
        it["unshot"] = videomodels.frames(card, secs)
        if pre:   # a scene from a picture: its still start is cut, the bar starts after it (edit.lay's `pre`)
            it["pre"] = round(pre / edit.FPS, 4)
        if cut:
            it["want"] = max(edit.MIN_CLIP, (round(float(cut["end"]) * edit.FPS) - round(float(cut["start"]) * edit.FPS)) / edit.FPS)
            it["accent"] = bool(cut.get("loud")) and not loud_before and it["index"] > 0
            loud_before = bool(cut.get("loud"))
        else:
            it["want"] = round(max(1, math.floor(seconds_of(n) / beat_s + 1e-6)) * beat_s, 4)


def montage_track(c: Ctx, nid: str, ed: dict) -> Optional[dict]:
    """The sound under a «Монтаж» with something on its «трек» input (edit.mix's track): a «Песня» «по тактам» plays
    as the button's clip has it - the song alone (the scenes' sound off), at full level, from where the first clip's
    scene sits in it (its bar), later when an intro comes before (`delay`); a «Трек» or a song without «по тактам» -
    from its start at the usual levels. None: nothing on the input (the key and the sound as they were)."""
    src = c.inputs(nid, "track")
    a = _out(c, *src[0]) if src and src[0][0] in c.by else None
    if not a or a.state != "ready" or not a.path:
        return None
    rel = rel_path(c.folder, a.path)
    if not (c.by[nid]["data"].get("beats") and a.song):
        return {"file": rel, **music.DEFAULTS}
    at = a.piece[0] if a.piece else 0.0   # no clip's scene: the song from the piece's start
    for cl in ed["clips"]:
        cut = c.by[cl["scene"]]["data"].get("cut") if cl["scene"] in c.by else None
        if isinstance(cut, dict):
            at = float(cut["start"]) - float(cl["start"])   # the clip's first frame is on its bar
            break
    return {"file": rel, "volume": 1.0, "scene_volume": 0.0, "fade_in": 0.0, "fade_out": 1.5,
            "offset": round(max(0.0, at), 3), "delay": round(max(0.0, -at), 3)}


def montage_track_view(c: Ctx, nid: str, ed: dict) -> Optional[dict]:
    """The «Музыка» lane of a «Монтаж»'s editor: the sound on its «трек» input as the montage mixes it
    (montage_track) - the song «по тактам» from its bar (`offset`), after an intro (`delay`) - with its name and length;
    `node`: the node it comes from (it is changed there, not in the editor). None: nothing on the input."""
    track = montage_track(c, nid, ed)
    if not track:
        return None
    src = c.inputs(nid, "track")[0][0]
    a = _out(c, src, c.inputs(nid, "track")[0][1])
    n = c.by[src]
    if a.song:
        from . import song
        name, dur = Path(song.name_of(a.song)).stem, song.analysis(a.song).duration
    else:
        try:
            dur = music.duration(a.path)
        except (OSError, ValueError, KeyError):
            dur = 0.0
        name = n["data"].get("name") or Path(track["file"]).name
    return {**track, "name": name, "duration": round(float(dur), 2), "node": src, "beats": bool(c.by[nid]["data"].get("beats") and a.song)}


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
    for n in g["nodes"]:   # a hero from the actor library: the card shows the actor (name, look), not the template's old text
        if n["type"] == "hero" and n["data"].get("actor") and n["id"] in nodes:
            from . import actors
            aid = n["data"]["actor"]
            own = actors.series_root(proj["series"]) if proj.get("series") and actors.exists(aid, actors.series_root(proj["series"])) else None
            if actors.exists(aid, own):
                a = actors.get(aid, own)
                # the picture the hero card shows: the same fallback as actors.hero_data (face, else look reference, else photo)
                pic = next(((w, p) for w in ("face", "ref", "photo") if (p := actors.image_path(aid, w, own)).exists()), None)
                nodes[n["id"]]["actor"] = {"name": a.get("name") or "", "look_ru": a.get("look_ru") or "", "look_en": a.get("look_en") or "",
                                           "image": pic[0] if pic else None, "v": int(pic[1].stat().st_mtime) if pic else 0}
    for k in nodes:   # a drawn look with no first frame: the card offers to draw it
        if (fl := frame_look_of(c, k)):
            nodes[k]["frame_look"] = fl
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
        if t == "beat_montage" and a.state in ("todo", "wait"):
            secs += BEAT_RENDER_S * (a.seconds or 24)
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
    card, w, h = scene_card(c, c.by[x])
    ref = (a.refs or bool(c.inputs(x, "faces"))) and card.refs
    if card is not c.card:   # a scene of its own model: its speed, never the graph model's measured one
        return render.one_scene(c.settings, c.quality, w, h, videomodels.frames(card, seconds_of(c.by[x])), ref, card)
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
    t0, last_ref, made, tried, audited = time.time(), None, 0, set(), set()
    ahead, ahead_files = set(), []   # the scenes whose prompts went into a text-encoder pass ahead (_encode_ahead)
    try:
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
            if c.by[x]["type"] == "montage" and c.by[x]["data"].get("faces") and face_judged(c, x) and x not in audited:
                # its scenes are shot: the button's face audit first, then the montage of the takes it chose
                audited.add(x)
                try:
                    await face_audit(job, pid, x, quality, failed)
                except asyncio.CancelledError:
                    row["status"] = "cancelled"
                    raise
                except Exception as e:  # noqa: BLE001 - noted; the montage is made of the takes as they are
                    prog.setdefault("notes", []).append(i18n.L(f"«{c.by[x]['data'].get('title') or 'Монтаж'}»: проверка лиц не прошла — {e}",
                                                               f"«{c.by[x]['data'].get('title') or 'Montage'}»: the face check failed — {e}"))
                g = load(pid)
                continue
            ts = time.time()
            try:
                if x in tried:
                    raise EngineError(i18n.L("узел сделан, а его файла нет", "the node is done, but its file is missing"))
                tried.add(x)
                if c.by[x]["type"] == "scene" and not arts[x].ref and x not in ahead:
                    ahead_files += await _encode_ahead(job, c, arts, x, todo, ahead)
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
    finally:   # a stop, an error or a cancel: the start frames of scenes encoded ahead and not shot after all go
        for f in ahead_files:
            f.unlink(missing_ok=True)
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


def _scene_kw(c: Ctx, x: str, a: Art) -> dict:
    """A plain scene node's render.shoot_scene arguments (its shot in _make, its prompt ahead in _encode_ahead)."""
    n = c.by[x]
    start = c.inputs(x, "start")
    st_art = _out(c, *start[0]) if start else None
    kind = "continue" if st_art and st_art.start_of else "new"   # a last frame as it is; a photo cropped to the frame
    faces = [_out(c, s, sp).path for s, sp in c.inputs(x, "faces")]
    card, w, h = scene_card(c, n)
    tr, tr_at, _ = scene_track(c, n, card, scene_frames(c, n, card)[1])
    au, au_from, _ = scene_sound(c, n, card)
    return dict(prompt=a.text, kind=kind, seed=seed_of(n), w=w, h=h, length=videomodels.frames(card, a.seconds), loras=a.loras,
                start=st_art.path if st_art else None, refs=[f for f in faces if f], quality=c.quality, model=card.id,
                track=tr, track_start=tr_at, end=_out(c, *c.inputs(x, "end")[0]).path if c.inputs(x, "end") else None,
                **({"audio": au, "audio_from": au_from} if au else {}))


async def _encode_ahead(job: jobs.Job, c: Ctx, arts: dict[str, Art], x: str, todo: list[str], done: set) -> list[Path]:
    """Before plain scene `x`, when H3 shoots it: the prompts of it and of every other plain H3 scene that can be shot
    now, in one pass of the text encoder (render.encode_ahead). `done`: the scenes already in such a pass (not encoded
    twice). -> the files it put into COMFY_INPUT."""
    calls = {}
    for y in [x] + [y for y in todo if y != x and y not in done and c.by[y]["type"] == "scene" and not arts[y].ref]:
        try:
            kw = _scene_kw(c, y, arts[y])
        except Exception:  # noqa: BLE001 - such a node's own shot reports what is wrong with it
            continue
        if videomodels.shooter(videomodels.card(kw["model"])).id == "h3" and (kw["start"] is None or kw["start"].exists()):
            calls[y] = kw
    if x not in calls:   # another model's scene: its scenes first (_pick), the H3 ones then get their pass
        return []
    done.update(calls)
    return await render.encode_ahead(job, c.pid, c.folder / "scenes", list(calls.values()))


async def _make(job: jobs.Job, c: Ctx, x: str, a: Art) -> None:
    n = c.by[x]
    t, d = n["type"], n["data"]
    if t == "scene" and a.ref:
        await _make_ref_scene(job, c, x, a)
    elif t == "scene":
        kw = _scene_kw(c, x, a)
        title = d.get("title") or i18n.L("Сцена", "Scene")
        res = await render.shoot_scene(job, c.pid, c.folder / "scenes", label=f"«{title}»", **kw)
        if not res["cached"]:   # the clip's checks (phase 10, stage A): a badge on the node; «Ещё дубль» is the user's
            face = kw["start"] or next((f for f in kw["refs"]), None)
            await asyncio.to_thread(checks.check_clip, res["mp4"], face)
            if kw.get("audio"):   # drawn under a given sound: the lips' motion in its voiced / silent frames, for the page (not a blocker)
                await asyncio.to_thread(lambda: checks.save_lips(res["mp4"], checks.audio_lips(
                    res["mp4"], kw["audio"], kw.get("audio_from", 0.0), kw["length"], graphs.FPS)))
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
        track = montage_track(c, x, ed)   # the «трек» input (a «Песня» by its bars); none - the «Музыка» node's job
        a.path.parent.mkdir(exist_ok=True)
        job.phase = "assembling"
        pic = a.path.with_name(a.path.stem + "_pic.mp4") if ed["sounds"] or track else a.path
        size = await asyncio.to_thread(render.mixed_size, [Path(x["src"]) for x in ed["clips"] if x.get("src")], c.w, c.h)
        cuts = await asyncio.to_thread(edit.render, ed, c.folder, pic, size)
        if ed["sounds"] or track:   # the sounds from files over the scenes' sound, the track under them
            job.phase = "mixing"
            await asyncio.to_thread(edit.mix, ed, c.folder, pic, track, a.path)
            pic.unlink(missing_ok=True)
        a.path.with_suffix(".json").write_text(json.dumps({"cuts": cuts, "clips": [x["id"] for x in ed["clips"]]}), encoding="utf-8")
    elif t == "beat_montage":
        _pin_beat_drop(c, x, a)
        await _make_beat(job, x, a)
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
        if not a.path.exists():
            job.phase = "upscaling"
            # an own frame: the output keeps its proportions instead of the format's 1080p / 4k frame
            await asyncio.to_thread(post.finish, v.path, a.path, c.w, c.h, "own" if c.own else c.aspect, out, v.cuts, c.folder / "_post")
        if (p := a.extra.get("phone")) and not p.exists():
            job.phase = "phone copy"
            await asyncio.to_thread(post.phone_copy, a.path, p, PHONE_MB)
        if (p := a.extra.get("cover")) and not p.exists():
            await asyncio.to_thread(post.cover_frame, a.path, p, a.extra["cover_at"])


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


def faceless_src(c: Ctx, src: str) -> bool:
    """Whether the node a face comes from is a hero that is not a person (an animal, a robot, a creature: no face for the
    detector), or the portrait drawn for one (`kind` on the picture, or its `hero` node)."""
    n = c.by.get(src)
    if not n:
        return False
    if n["type"] == "hero":
        return hero_kind(n["data"]) != "person"
    if n["type"] == "picture":
        h = c.by.get(n["data"].get("hero") or "")
        return hero_kind(n["data"]) != "person" or bool(h and hero_kind(h["data"]) != "person")
    return False


def scene_faces(c: Ctx, sid: str) -> list[Path]:
    """The ready faces on a scene's «лица» (Ref2VA's photos or portraits of the heroes in it); the faces of heroes that
    are not people are left out - the detector has none to find on them."""
    out = []
    for s, sp in c.inputs(sid, "faces"):
        if faceless_src(c, s):
            continue
        a = _out(c, s, sp) if s in c.by else None
        if a and a.state == "ready" and a.path and a.path.exists():
            out.append(a.path)
    return out


def face_judged(c: Ctx, mid: str) -> bool:
    """Whether «Проверять лица» of a «Монтаж» has faces to judge by: the face on its «лицо» (a clip's hero), or a
    scene of a story (no `cut`) with heroes on its own «лица» (the «Кино» template: each scene its own heroes)."""
    return any(not faceless_src(c, s) for s, _ in c.inputs(mid, "face")) or any(
        sid in c.by and c.by[sid]["type"] == "scene" and not isinstance(c.by[sid]["data"].get("cut"), dict)
        and any(not faceless_src(c, s) for s, _ in c.inputs(sid, "faces"))
        for sid in join_order(c, mid))


def face_scores(c: Ctx, mid: str) -> dict[str, tuple[int, Optional[float]]]:
    """{scene: (its chosen seed, how like its heroes its shot's faces are)} of the montage's shot scenes: a clip's
    marked `cut.face` (the hero framed close or medium: autopilot.face_judged) against the face on the montage's
    «лицо» - checks.hero_similarity, the median over five frames, as the button's audit (autopilot._scores); a story's
    scene (no `cut`) against the faces on its own «лица» - checks.heroes_similarity, as like as its least like hero
    (each expected hero's face must be found). None: no face to judge."""
    src = c.inputs(mid, "face")
    fa = _out(c, *src[0]) if src and src[0][0] in c.by and not faceless_src(c, src[0][0]) else None
    fa_ok = bool(fa and fa.state == "ready" and fa.path and fa.path.exists())
    out = {}
    for sid in join_order(c, mid):
        n = c.by[sid]
        if n["type"] != "scene":
            continue
        cut = n["data"].get("cut")
        if isinstance(cut, dict):
            if not (cut.get("face") and fa_ok):
                continue
            judge = lambda p: checks.hero_similarity(p, fa.path)  # noqa: E731
        else:
            refs = scene_faces(c, sid)
            if not refs:
                continue
            judge = lambda p, refs=refs: checks.heroes_similarity(p, refs)  # noqa: E731
        a = evaluate_node(c, sid)
        if a.state == "ready" and a.path and a.path.exists():
            out[sid] = (seed_of(n), judge(a.path))
    return out


async def face_audit(job: jobs.Job, pid: str, mid: str, quality: Optional[str], failed: dict) -> bool:
    """«Проверять лица» of a «Монтаж» (`faces`, the hero's face on its «лицо»), before it is assembled: the «Песня →
    клип» button's face audit (autopilot.face_rounds - its threshold FRAME_FACE_MIN, its FACE_ROUNDS rounds, the
    likest take kept). A weak scene gets a take more (a new seed on the scene node, as «Ещё дубль»; the shot before
    stays a take) and is shot; at the end every judged scene is set to its likest take, so the montage is built of
    them. -> False when stopped («Остановить после текущей»)."""
    from . import autopilot
    ctx = lambda: Ctx(projects.load(pid), load(pid), quality, failed)  # noqa: E731
    rows = job.progress.setdefault("nodes", {})

    async def scores():
        return await asyncio.to_thread(face_scores, ctx(), mid)

    async def reshoot(bad: list[str]) -> bool:
        def go(g: dict) -> None:
            for sid in bad:
                if (n := node(g, sid)):
                    takes = [int(x) for x in n["data"].get("takes") or []] or [seed_of(n)]
                    takes.append(random.randrange(1, 2**31))
                    n["data"].update(takes=takes, take=len(takes) - 1)
        update(pid, go)
        for sid in bad:
            if job.stop_after:
                return False
            c = ctx()
            a = evaluate_node(c, sid)
            if a.state != "todo":
                continue
            row = rows.setdefault(sid, {"type": "scene"})
            row.update(status="running", key=a.key)
            job.progress["current"] = sid
            ts = time.time()
            await _make(job, c, sid, a)
            row.update(status="done", seconds=round(time.time() - ts, 1))
        return not job.stop_after

    keep = await autopilot.face_rounds(job, scores, reshoot)
    if keep is None:
        return False

    def pick(g: dict) -> None:
        for sid, seed in keep.items():
            n = node(g, sid)
            takes = [int(x) for x in (n or {}).get("data", {}).get("takes") or []]
            if n and seed in takes and seed_of(n) != seed:
                n["data"]["take"] = takes.index(seed)
    update(pid, pick)
    return True


def _picture_text(c: Ctx, x: str) -> str:
    src = c.inputs(x, "text")
    if not src:
        return c.by[x]["data"].get("prompt") or ""
    a = _out(c, *src[0])
    return picture_in_look(c.by[x]["data"].get("look"), a.picture or a.text)


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
    st = c.proj.get("settings") or {}
    style = [{k: st.get(k) for k in ("delivery", "look", "look_own")}] if "delivery" in st else []   # an older graph's sig stays
    said = [{"lines": True}] if d.get("lines") else []   # «Реплики»: the writer writes what they say too
    return _sha(idea, [{**{k: h["data"].get(k) for k in ("gender", "age", "en", "outfit_en", "photo")}, **_kind_key(h["data"])} for h in heroes],
                {k: d.get(k) for k in ("seconds", "mode", "mood", "music", "ref_photo")}, *style, *said)


def writer_mode(d: dict, heroes: list) -> str:
    m = d.get("mode") or "auto"
    if m != "auto":
        return m
    return "none" if not heroes else "one" if len(heroes) == 1 else "several"


def hero_kind(d: dict) -> str:
    """What a «Герой» node is: person (no kind - an older graph), animal, robot or creature (prompts.kind_of)."""
    return prompts.kind_of(d)


def _kind_key(d: dict) -> dict:
    """A non-person hero's kind for a signature: the key stays out for a person, so an older graph's cache keys are the same."""
    return {"kind": d["kind"]} if hero_kind(d) != "person" else {}


def hero_cast(h: dict) -> dict:
    d = h["data"]
    out = {"gender": d.get("gender", ""), "age": d.get("age", ""), "en": d.get("en", ""), "ru": d.get("ru", ""),
           "outfit_en": d.get("outfit_en", ""), "outfit_ru": d.get("outfit_ru", ""), "photo": d.get("photo"), "node": h["id"]}
    if hero_kind(d) != "person":   # an animal, a robot or a creature (a node without a kind is a person: nothing added, the keys as before)
        out.update(kind=d["kind"], age=0, from_user=True)
    return out


async def run_llm(job: jobs.Job, pid: str, ids: list[str], model: Optional[str], action: str = "write", edited: str = "keep") -> dict:
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
    clip_writers = [n for n in todo if n["type"] == "clip_writer"]
    pool_writers = [n for n in todo if n["type"] == "pool_writer"]
    plays = [n for n in todo if n["type"] == "screenplay"]
    prog = job.progress
    prog.update(stage="llm", nodes={n["id"]: {"status": "queued", "type": n["type"]} for n in todo})
    done = {}
    notes = await _clip_words(job, Ctx(proj, g), clip_writers)   # before the writer loads: Demucs + Whisper need the GPU
    async with llm.session(model) as client:
        for h in heroes:
            prog["nodes"][h["id"]]["status"] = "running"
            p = folder / h["data"]["photo"] if h["data"].get("photo") else None
            if not p or not p.exists():
                prog["nodes"][h["id"]].update(status="error", error=i18n.L("у героя нет фото", "the hero has no photo"))
                continue
            dsc = await describe.describe_with(client, p, kind=h["data"].get("kind") or "person")
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
            secs = next((math.ceil(seconds_of(c.by[e["target"]])) for e in g["edges"]
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
            st = proj.get("settings") or {}
            styled = "delivery" in st   # «Стиль проекта»: the writer reads the delivery and the look, not the node's mood
            plan = writer.new_plan(idea, float(d.get("seconds") or 15), mode, "" if styled else d.get("mood", ""), d.get("music", ""),
                                   None, seed=int(d.get("seed") or random.randrange(100000)), model=client.model.id)
            if styled:
                plan.update({k: st[k] for k in ("look_mine", "look_pick") if k in st})
                looks.choose(plan, st.get("delivery"), st.get("look"), st.get("look_own", ""))
            plan["video"] = videomodels.stored(proj.get("settings") or {})   # the graph's model shoots it
            if mode != "none" and hs:   # with several people every hero of the canvas goes in (writer.write: fixed looks)
                plan["cast"] = [{k: v for k, v in hero_cast(h).items() if k not in ("photo", "node")} for h in (hs if mode == "several" else hs[:1])]
            p = await writer.write(plan, None, folder)
            if mode != "none":   # the user's heroes stay as they are, in the order of the canvas
                p.setdefault("cast", [])
                for i, h in enumerate(hs):
                    look = {k: v for k, v in hero_cast(h).items() if k not in ("photo", "node")}
                    if i < len(p["cast"]):
                        p["cast"][i].update(look)
                    else:
                        p["cast"].append(look)
            if d.get("lines") and mode != "none":   # «Реплики»: the board's «Придумать реплики» over every scene
                p = await writer.write_lines(p, list(range(len(p["scenes"]))), int(p.get("seed") or 1))
            p = check.plan(p)
            done[w["id"]] = {"plan": p, "sig": writer_sig(c, w)}
            row["status"] = "done"
        for w in pool_writers:
            from . import graph_beat
            row = prog["nodes"][w["id"]]
            row["status"] = "running"
            try:
                done[w["id"]] = await graph_beat.write(client, proj, c, w)
            except ValueError as e:
                row.update(status="error", error=str(e))
                continue
            row["status"] = "done"
        for w in clip_writers:
            row = prog["nodes"][w["id"]]
            row["status"] = "running"
            try:
                done[w["id"]] = await write_clip(client, proj, c, w, notes.get(w["id"], ""))
            except ValueError as e:   # what the node lacks: said on it, the others go on
                row.update(status="error", error=str(e))
                continue
            row["status"] = "done"

        for sn in plays:   # «Сценарий»: «Написать сценарий» (action "write") or «Добавить в "Ранее"» ("recap")
            row = prog["nodes"][sn["id"]]
            row["status"] = "running"
            try:
                if action == "expand":   # «Развернуть в шоты»: the English of the places and actions first (cached per text)
                    try:
                        for nid, data in (await translate_screenplay(client, pid, sn["id"], random.randrange(100000))).items():
                            done.setdefault(nid, {}).update(data)
                    except Exception as e:   # no translation: the shots are still made, their prompts say «проверь перевод»
                        row["note"] = i18n.L(f"перевод не вышел: {e}", f"the translation failed: {e}")
                    row["status"] = "done"
                    continue
                for nid, data in (await write_screenplay(client, c, sn, action)).items():
                    done.setdefault(nid, {}).update(data)
            except ValueError as e:   # what the node lacks: said on it, the others go on
                row.update(status="error", error=str(e))
                continue
            row["status"] = "done"

    def put(gg: dict) -> None:
        for nid, data in done.items():
            if (nn := node(gg, nid)):
                nn["data"].update(data)
    update(pid, put)
    if action == "expand":
        for sn in plays:
            try:
                expand_screenplay(pid, sn["id"], edited)
            except ValueError as e:
                prog["nodes"][sn["id"]].update(status="error", error=str(e))
    prog["stage"] = "done"
    return {"done": list(done), "errors": {k: v.get("error") for k, v in prog["nodes"].items() if v.get("status") == "error"}}


def expand(pid: str, wid: str, edited: str = "ask") -> dict:
    """«Развернуть в сцены»: the writer's plan -> a Prompt and a Scene per scene (a continuation starts from the
    previous scene's last frame), a Join of them and an Output. Again after a rewrite: the same nodes get the new
    texts (their seeds stay), extra ones go away. A «Сценарист клипа»'s: expand_clip.
    A hero without a photo of their own, with «Держать лицо по фото» on: a Krea 2 portrait «Картинка» is their face -
    each scene's «лица» get the faces of the heroes in it (the plan's `who`). The scenes go into the writer's join -
    or into its «Монтаж» (`from`, the «Кино» template's)."""
    from . import hero as hero_lib
    from .planner import check
    if (w := node(load(pid), wid)) and w["type"] == "clip_writer":
        return expand_clip(pid, wid, edited)
    if (w := node(load(pid), wid)) and w["type"] == "pool_writer":
        from . import graph_beat
        return graph_beat.expand(pid, wid, edited)
    if w and w["type"] == "screenplay":
        return expand_screenplay(pid, wid, edited)

    def go(g: dict) -> None:
        w = node(g, wid)
        if not w or w["type"] != "writer" or not w["data"].get("plan"):
            raise ValueError(i18n.L("У сценариста нет раскадровки: сначала «Написать»", "The writer has no storyboard: «Write» first"))
        plan = json.loads(json.dumps(w["data"]["plan"]))
        c = Ctx(projects.load(pid), g)
        _, heroes = writer_inputs(c, w)
        drawn: list[int] = []   # the cast without a photo of their own: a Krea 2 portrait is their face for Ref2VA
        if plan.get("mode") != "none":   # Ref2VA: the hero's photo as <Picture k> where prompts.uses_refs says so
            for i, h in enumerate(heroes):
                if i < len(plan.get("cast") or []) and h["data"].get("photo"):
                    plan["cast"][i]["photo"] = h["data"]["photo"]
                elif i < len(plan.get("cast") or []) and w["data"].get("ref_photo") and (plan["cast"][i].get("en") or "").strip():
                    plan["cast"][i]["photo"] = "hero.png"   # the portrait node gives the face (as expand_clip's hero)
                    drawn.append(i)
            plan["ref_photo"] = bool(w["data"].get("ref_photo"))
            plan = check.plan(plan)
        x0, y0 = w["position"]["x"] + 380, w["position"]["y"]
        detach_copies(g, wid, lambda nn: (nn["data"].get("scene"), nn["data"].get("hero"), nn["type"]))
        mine = {(nn["data"].get("from"), nn["data"].get("scene"), nn["type"]): nn for nn in g["nodes"] if not nn["data"].get("detached")}
        face_of = {i: (h["id"], "image") for i, h in enumerate(heroes) if h["data"].get("photo")}
        portraits = {nn["data"]["hero"]: nn for nn in g["nodes"]
                     if nn["type"] == "picture" and nn["data"].get("from") == wid and not nn["data"].get("detached") and nn["data"].get("hero")}
        drawn_ids = set()
        for k, i in enumerate(drawn):   # one portrait per hero, kept by the hero's node; the prompt follows the look
            hid = heroes[i]["id"]
            pt = portraits.get(hid)
            if not pt:
                pt = {"id": uuid.uuid4().hex[:8], "type": "picture", "position": {"x": w["position"]["x"], "y": w["position"]["y"] + 300 + k * 360},
                      "data": {"from": wid, "scene": None, "hero": hid, "seed": random.randrange(1, 2**31)}}
                g["nodes"].append(pt)
            pt["data"].update(model="krea2", prompt=hero_lib.prompt_of(plan, i), **_kind_key(heroes[i]["data"]),
                              title=i18n.L(f"Портрет: {heroes[i]['data'].get('title') or i + 1}", f"Portrait: {heroes[i]['data'].get('title') or i + 1}"))
            face_of[i] = (pt["id"], "image")
            drawn_ids.add(pt["id"])
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
                    if k in face_of:
                        g["edges"].append({"id": uuid.uuid4().hex[:8], "source": face_of[k][0], "sourceHandle": face_of[k][1], "target": sn["id"], "targetHandle": "faces"})
        gone = {nn["id"] for nn in g["nodes"] if nn["data"].get("from") == wid and not nn["data"].get("detached") and nn["id"] not in keep
                and (nn["type"] in ("prompt", "scene") or (nn["type"] == "picture" and nn["data"].get("hero") and nn["id"] not in drawn_ids))}
        g["nodes"] = [nn for nn in g["nodes"] if nn["id"] not in gone]
        g["edges"] = [e for e in g["edges"] if e["source"] not in gone and e["target"] not in gone]
        # the scenes go into the writer's own join - or into a «Монтаж» of its (`from`: a template's, the «Кино»)
        jn = mine.get((wid, None, "join")) or mine.get((wid, None, "montage"))
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
# «Песня → клип» in parts (2026-11-03): «Сценарист клипа» runs the button's stages (clip_api.clip_plan, the clip
# writer, autopilot.sing_cameras) into its node; «Развернуть в сцены» lays its plan out as ordinary nodes
# ---------------------------------------------------------------------------------------------------------------
def clip_writer_inputs(c: Ctx, n: dict) -> tuple[Optional[dict], str, Optional[dict]]:
    """(the «Песня» node, the idea or mood line, the hero node) of a «Сценарист клипа»."""
    song_n = next((c.by[s] for s, _ in c.inputs(n["id"], "song") if s in c.by), None)
    idea = next((c.by[s]["data"].get("text", "") for s, _ in c.inputs(n["id"], "idea") if s in c.by), "") or n["data"].get("idea", "")
    hero = next((c.by[s] for s, _ in c.inputs(n["id"], "cast") if s in c.by), None)
    return song_n, (idea or "").strip(), hero


def clip_writer_sig(c: Ctx, n: dict) -> str:
    """What the clip writer's plan was written from: the song's piece and words, the idea, the hero's look, the graph's
    model (it picks the singing scenes' model), «Стиль проекта»."""
    song_n, idea, hero = clip_writer_inputs(c, n)
    sa = evaluate_node(c, song_n["id"]) if song_n else None
    st = c.proj.get("settings") or {}
    style = [{k: st.get(k) for k in ("delivery", "look", "look_own")}] if "delivery" in st else []
    return _sha("clip", sa.key if sa and sa.state == "ready" else None, idea, c.card.id,
                {**{k: hero["data"].get(k) for k in ("gender", "age", "en", "outfit_en", "photo")}, **_kind_key(hero["data"])} if hero else None, *style)


async def _clip_words(job: jobs.Job, c: Ctx, writers: list[dict]) -> dict[str, str]:
    """The songs' words (Demucs + Whisper) the clip writers need, unless known - the button's «слова» stage
    (autopilot._words): a failure is noted, the clip is written without singing scenes. -> {writer: the note}."""
    from . import autopilot, song
    notes = {}
    for w in writers:
        song_n, _, _ = clip_writer_inputs(c, w)
        sid = (song_n or {}).get("data", {}).get("song")
        if sid and not song.recognised(sid):
            job.progress["nodes"][w["id"]]["status"] = "running"
            notes[w["id"]] = await autopilot._words(job, autopilot.Autopilot(song=sid))
    return notes


async def write_clip(client, proj: dict, c: Ctx, w: dict, note: str = "") -> dict:
    """«Написать» of a «Сценарист клипа»: the «Песня → клип» button's script - the request it makes
    (autopilot._clip_req: the idea with its shot plan, inserts without a face, one hero), the plan cut on the song's
    bars (clip_api.clip_plan: singing scenes, inserts, the look, the singing scenes' model), «Решит сценарист», the clip
    writer, the singers' cameras. The hero node's look, when it has one, stays the hero's. -> the node's new data."""
    from . import autopilot, clip_api, song
    from .llm import writer
    from .planner import check
    song_n, idea, hero = clip_writer_inputs(c, w)
    if not song_n:
        raise ValueError(i18n.L("нет песни: подключите узел «Песня»", "no song: connect a «Song» node"))
    sa = evaluate_node(c, song_n["id"])
    if sa.state != "ready":
        raise ValueError(sa.error or i18n.L("песня не готова", "the song is not ready"))
    st = proj.get("settings") or {}
    styled = "delivery" in st
    photo = hero["data"].get("photo") if hero and hero["data"].get("photo") and (c.folder / hero["data"]["photo"]).exists() else None
    look = {k: v for k, v in hero_cast(hero).items() if k not in ("photo", "node")} if hero and (hero["data"].get("en") or "").strip() else None
    ex0, ex1 = sa.piece
    req = autopilot._clip_req(autopilot.Autopilot(
        song=sa.song, idea=idea[:autopilot.IDEA_CLIP], photo=photo, aspect=c.aspect, video_model=c.card.id, model=client.model.id,
        delivery=(st.get("delivery") or looks.AUTO) if styled else looks.AUTO, look=(st.get("look") or looks.AUTO) if styled else looks.AUTO,
        look_own=st.get("look_own") or "" if styled else ""), ex0, ex1 - ex0)
    a = song.analysis(sa.song)
    sing = clip_api.sing_model(req.sing_model, c.card)
    title = Path(song.name_of(sa.song)).stem or i18n.L("Клип", "Clip")
    choice = clip_api.clip_choice(req, title, a.bpm)
    if styled:
        choice.update({k: st[k] for k in ("look_mine", "look_pick") if k in st})
    seed = int(w["data"].get("seed") or random.randrange(100000))
    lines = song.lines(sa.song)
    if looks.needs_pick(choice):
        await clip_api.decide_look(client, choice, lines, seed)
    plan = clip_api.clip_plan(req, a, lines, ex0, ex1, c.card, sing, choice, seed, client.model.id, title, photo)
    if look:   # the user's hero: the writer writes them, not one of its own
        plan["cast"] = [dict(look)]
    p = await writer.write_clip(plan, c.folder / photo if photo else None, c.folder)
    if look:
        p.setdefault("cast", [{}])
        p["cast"][0].update(look)
    if note:
        p["clip"]["lyrics_error"] = note
    autopilot.sing_cameras(p)
    await clip_places(client, p, (w["data"].get("plan") or {}).get("places") or [], seed)
    return {"plan": check.plan(p), "sig": clip_writer_sig(c, w), "seed": seed, "v": CLIP_V}


# a «Сценарист клипа»'s plan written since 2026-11-03 (its data `v`): «Развернуть в сцены» gives it the button's places,
# the pre-rolls of the scenes from a picture and the montage's face check; an older plan expands as it did
CLIP_V = 2


async def clip_places(client, p: dict, old: list[dict], seed: int) -> None:
    """«Места» of the «Песня → клип» button (its stage «места»: clip_api.group_places) on the clip writer's plan: the
    writer groups the scenes into a few places (places.ask, the same request), the places of the plan before keep
    their ids by name (their «Картинка» nodes stay). Only with FLUX.2 Klein, as the button: a place is the frames'
    second picture. A failure is noted on the clip (`places_error`), the frames are drawn without places then."""
    from . import picture, places
    from .llm import client as llm
    if picture.edit_problem() or not any(s.get("kind") == "new" for s in p.get("scenes") or []):
        return
    p["places"] = [{k: x[k] for k in ("id", "name_ru", "en") if k in x} for x in old if isinstance(x, dict)]
    try:
        llm.use_lang(i18n.plan_lang_name(p))
        places.gather(p, await places.ask(client, p, seed))
        p["places_by"] = {"model": client.model.name}
    except (EngineError, llm.LLMError) as e:
        p.pop("places", None)
        for s in p["scenes"]:
            s.pop("place", None)
        p["clip"]["places_error"] = str(e)


class Edited(Exception):
    """«Развернуть в сцены» again over nodes the user changed since: the page asks - keep them or replace them."""

    def __init__(self, names: list[str]):
        super().__init__(", ".join(names))
        self.names = names


def _made(n: dict) -> str:
    """A generated node's own fields as «Развернуть в сцены» made them: another value now - the user edited it."""
    d = n["data"]
    if n["type"] == "prompt":
        return _sha(d.get("text"), d.get("lines") or [])
    if n["type"] == "scene":
        return _sha(d.get("seconds"), d.get("model"), d.get("look"), d.get("items"), *([d["role"]] if d.get("role") else []))
    if n["type"] == "picture":
        return _sha(d.get("prompt"), d.get("model"), d.get("loras"))
    return ""


EXPAND_COLS = 6            # scenes in a row of the canvas (a part of the song starts a new row)
EXPAND_W, EXPAND_H = 640, 440


def expand_clip(pid: str, wid: str, edited: str = "ask") -> dict:
    """«Развернуть в сцены» of a «Сценарист клипа»: per scene a «Промт» -> «Сцена» with the scene's length on the bars
    (its `cut`: where it sits in the song), the prompt in the form of the model that shoots it (H3's formula, LTX's
    paragraph: the storyboard's own), a singing scene on the model that sings to the track with the song on its
    «голос»; a scene with the hero starts from a «Картинка» (FLUX.2 Klein, the button's frame prompt) of the hero's
    photo - or of a Krea portrait of the writer's hero; a continuation from the scene before. All into a «Склейка по
    тактам» (a «Монтаж» by the song's bars, the song its track) and an «Выход». A part of the song is a row.

    Again after a rewrite: its own nodes (`from`) get the new plan, their places and seeds stay; the user's nodes and
    wires are never touched. Own nodes the user changed since (`made`): `edited` "ask" - Edited (the page asks),
    "keep" - left as they are, "replace" - made again. -> the graph, `kept`: the names of the nodes left."""
    from . import autopilot, frames, hero as hero_lib, places as places_lib
    from .planner import model_prompts
    kept: list[str] = []

    def go(g: dict) -> None:
        w = node(g, wid)
        if not w or w["type"] != "clip_writer" or not w["data"].get("plan"):
            raise ValueError(i18n.L("У сценариста клипа нет раскадровки: сначала «Написать»", "The clip writer has no storyboard: «Write» first"))
        plan = json.loads(json.dumps(w["data"]["plan"]))
        c = Ctx(projects.load(pid), g)
        song_n, _, hero = clip_writer_inputs(c, w)
        v2 = int(w["data"].get("v") or 1) >= CLIP_V   # places, pre-rolls, the face check: a plan written since (CLIP_V)
        detach_copies(g, wid, lambda nn: (nn["data"].get("place") or nn["data"].get("scene"), nn["data"].get("hero"), nn["type"]))
        mine = {(nn["data"].get("place") or nn["data"].get("scene"), nn["type"]): nn for nn in g["nodes"] if nn["data"].get("from") == wid and not nn["data"].get("detached")}
        changed = [nn for nn in mine.values() if nn["data"].get("made") and _made(nn) != nn["data"]["made"]]
        if changed and edited == "ask":
            raise Edited([nn["data"].get("title") or type_title(nn["type"]) for nn in changed])
        hold = {nn["id"] for nn in changed} if edited == "keep" else set()
        kept.extend(nn["data"].get("title") or type_title(nn["type"]) for nn in changed if nn["id"] in hold)
        fixed = {x for x in (hero and hero["id"], song_n and song_n["id"]) if x}
        own = lambda sid: sid in fixed or ((node(g, sid) or {}).get("data") or {}).get("from") == wid and not ((node(g, sid) or {}).get("data") or {}).get("detached")  # noqa: E731

        def new(t: str, x: float, y: float, data: dict) -> dict:
            nn = {"id": uuid.uuid4().hex[:8], "type": t, "position": {"x": x, "y": y}, "data": {"from": wid, **data}}
            g["nodes"].append(nn)
            return nn

        def wire(target: dict, port: str, sources: list[tuple[str, str]]) -> None:
            """The target's input from these sources - unless the user wired it from a node of theirs (that stays)."""
            old = [e for e in g["edges"] if e["target"] == target["id"] and e["targetHandle"] == port]
            if any(not own(e["source"]) for e in old):
                return
            g["edges"] = [e for e in g["edges"] if e not in old]
            for s, sp in sources:
                g["edges"].append({"id": uuid.uuid4().hex[:8], "source": s, "sourceHandle": sp, "target": target["id"], "targetHandle": port})

        def fill(nn: dict, data: dict) -> None:
            if nn["id"] not in hold:
                nn["data"].update(data)
                nn["data"]["made"] = _made(nn)

        people = plan.get("mode") != "none" and bool(plan.get("cast"))
        keep: set[str] = set()
        # the face the frames are drawn from: the hero's photo, else a Krea 2 portrait of the writer's hero
        face = None
        if people and hero and hero["data"].get("photo"):
            face = (hero["id"], "image")
        elif people and (plan["cast"][0].get("en") or "").strip():
            pt = mine.get((None, "picture")) or new("picture", w["position"]["x"], w["position"]["y"] + 300,
                                                     {"scene": None, "seed": random.randrange(1, 2**31)})
            fill(pt, {"model": "krea2", "prompt": hero_lib.prompt_of(plan, 0), "title": i18n.L("Герой: портрет", "Hero: portrait"),
                      **({"kind": plan["cast"][0]["kind"]} if prompts.is_nonperson(plan["cast"][0]) else {})})
            keep.add(pt["id"])
            face = (pt["id"], "image")
        if face:   # the frames' people have a photo now (frames.frame_people, prompts.photo_people)
            plan["cast"][0]["photo"] = plan["cast"][0].get("photo") or "hero.png"
        place_of: dict[str, dict] = {}

        def place_node(s: dict) -> Optional[dict]:
            """«Места» of the button: the scene's place as a «Картинка» (Krea 2, places.prompt_of - the set, empty),
            made once for all its scenes; a column under the writer."""
            x = places_lib.of_scene(plan, s) if v2 else None
            if not x or not x.get("en"):
                return None
            if x["id"] not in place_of:
                k = len(place_of)
                pl = mine.get((x["id"], "picture")) or new("picture", w["position"]["x"], w["position"]["y"] + 560 + k * 360,
                                                            {"scene": None, "place": x["id"], "seed": random.randrange(1, 2**31)})
                fill(pl, {"model": "krea2", "prompt": places_lib.prompt_of(plan, x),
                          "title": i18n.L(f"Место: {x.get('name_ru') or k + 1}", f"Place: {x.get('name_ru') or k + 1}")})
                keep.add(pl["id"])
                place_of[x["id"]] = pl
            return place_of[x["id"]]
        preroll = (plan.get("clip") or {}).get("preroll") if v2 else None
        x0, y0 = w["position"]["x"] + 420, w["position"]["y"]
        scene_of: dict[int, str] = {}
        row, col, part, wide = -1, 0, object(), 1
        for s in plan["scenes"]:
            i = s["index"]
            if s.get("chapter") != part or col == EXPAND_COLS:
                row, col, part = row + 1, 0, s.get("chapter")
            x, y = x0 + col * EXPAND_W, y0 + row * EXPAND_H
            col += 1
            wide = max(wide, col)
            head = prompts.opener_of(plan, s) or s   # a continuation goes on in its chain's model (render.scene_card)
            m = head.get("model") if head.get("model") in videomodels.CARDS and head.get("model") != c.card.id else None
            card = videomodels.card(m or c.card.id)
            drawn = looks.needs_frame(plan)   # a look drawn by every frame: a «Картинка» for every new scene
            empty = s.get("kind") == "new" and frames.can_draw(plan, s) and frames.empty(plan, s)
            pl = place_node(s) if s.get("kind") == "new" and frames.can_draw(plan, s) and (face or empty or drawn) else None
            # a frame: the hero's (in the scene's place when it has one), or - the button's insert - the empty place
            pic = s.get("kind") == "new" and frames.can_draw(plan, s) and ((bool(face) and not empty) or (empty and pl is not None) or drawn)
            # ... or a drawn look's scene whose people have no portrait: from the words (frames._draw_empty, nobody=False)
            words = drawn and pic and not empty and not (face and frames.frame_people(plan, s))
            s2 = {k: v for k, v in s.items() if k not in ("prompt", "start_photo", "start_en")}
            names: list[str] = []
            if pic and (empty or words):   # frames._draw_empty's start text
                beats = [b.strip() for b in s.get("beats_en") or [] if b and b.strip()]
                what = frames._empty_action(plan, s) if empty else (beats[0] if beats else "the place itself")
                s2.update(start_photo="frame.png", start_en=f"{prompts.FRAMING.get(s.get('framing'), 'Medium shot')}: "
                                                            f"{prompts._sentence(what)}")
            elif pic:   # the prompt says the scene starts from a picture (prompts.starts_from_photo): no place described
                names = [prompts.speaker(plan, k + 1) for k in frames.frame_people(plan, s)][:3]
                s2.update(start_photo="frame.png", start_en=frames.start_text(plan, s, names))
            if videomodels.shooter(card).id == "h3":
                text, lines = prompts.split_lines(plan, s2)
            else:
                text, lines = model_prompts.for_model(card.id, plan, s2), []
            pn = mine.get((i, "prompt")) or new("prompt", x, y, {"scene": i})
            fill(pn, {"text": text, "lines": lines, "title": i18n.L(f"Сцена {i + 1}", f"Scene {i + 1}"), "ru": s.get("ru", "")})
            sn = mine.get((i, "scene")) or new("scene", x + 300, y, {"scene": i, "takes": [int(s.get("seed") or random.randrange(1, 2**31))], "take": 0})
            cut = {"start": round(float(plan["clip"]["from"]) + float(s["start"]), 4),
                   "end": round(float(plan["clip"]["from"]) + float(s["end"]), 4),
                   "voice": s.get("shot") not in render.NO_VOICE_SHOTS, "loud": bool(s.get("loud"))}
            if pic and isinstance(preroll, int) and not isinstance(preroll, bool) and preroll > 0:
                cut["pre"] = preroll   # from a picture: shot longer, its still start cut (scene_frames, render.preroll)
            if v2 and face and autopilot.face_judged(plan, s):
                cut["face"] = True     # the montage's «Проверять лица» judges it (face_audit)
            fill(sn, {"title": i18n.L(f"Сцена {i + 1}", f"Scene {i + 1}"), "seconds": round(float(s["seconds"]), 4), "model": m, "cut": cut})
            if sn["id"] not in hold and not sn["data"].get("model"):
                sn["data"].pop("model", None)
            keep |= {pn["id"], sn["id"]}
            scene_of[i] = sn["id"]
            pc = None
            if pic:
                pc = mine.get((i, "picture")) or new("picture", x, y + 200, {"scene": i, "seed": int(s.get("seed") or 1)})
                outfits = [(plan["cast"][k].get("outfit_en") or "") for k in frames.frame_people(plan, s)][:3]
                # the button's frame: the face first, then the place's picture (frames.draw_one / _draw_empty)
                bare = empty or words   # no face to give: in the place's picture (FLUX.2 Klein), else Krea 2 from the words
                fill(pc, {"model": "krea2" if bare and pl is None else "flux2",
                          "prompt": frames.empty_prompt(plan, s, pl is not None, not words) if bare
                          else frames.prompt_of(plan, s, names, pl is not None, False, outfits),
                          "title": i18n.L(f"Кадр {i + 1}", f"Frame {i + 1}")})
                keep.add(pc["id"])
                if pc["id"] not in hold:
                    wire(pc, "ref", ([] if bare else [face]) + ([(pl["id"], "image")] if pl else []))
            if sn["id"] in hold:
                continue
            src = prompts.from_of(plan, s)
            wire(sn, "prompt", [(pn["id"], "text")])
            wire(sn, "start", [(pc["id"], "image")] if pc else [(scene_of[src["index"]], "frame")] if src and src["index"] in scene_of else [])
            wire(sn, "faces", [face] if face and prompts.uses_refs(plan, s2) else [])
            wire(sn, "voice", [(song_n["id"], "audio")] if song_n and card.track else [])
        # what the plan no longer has: gone - or, changed by the user and kept, theirs from now on
        for nn in [x for x in g["nodes"] if x["data"].get("from") == wid and not x["data"].get("detached") and x["type"] in ("prompt", "scene", "picture") and x["id"] not in keep]:
            if nn["id"] in hold:
                for k in ("from", "scene", "made"):
                    nn["data"].pop(k, None)
            else:
                g["nodes"].remove(nn)
        ids = {x["id"] for x in g["nodes"]}
        g["edges"] = [e for e in g["edges"] if e["source"] in ids and e["target"] in ids]
        # «Склейка по тактам» and the «Выход»: made once, the song on its track
        mon = mine.get((None, "montage"))
        if not mon or mon["id"] not in ids:
            mon = new("montage", x0 + wide * EXPAND_W + 40, y0, {"scene": None, "beats": True,
                                                                         "title": i18n.L("Склейка по тактам", "Join on the bars")})
            out = new("output", x0 + wide * EXPAND_W + 380, y0, {"scene": None, "output": {"size": "1080p", "hdr": False, "fps48": False}})
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": mon["id"], "sourceHandle": "video", "target": out["id"], "targetHandle": "video"})
        if song_n:
            wire(mon, "track", [(song_n["id"], "audio")])
        if v2 and face:   # the button's face audit after the shooting: on by default, the hero's face its reference
            mon["data"].setdefault("faces", True)
            wire(mon, "face", [face])
        scenes = [scene_of[s["index"]] for s in plan["scenes"]]
        g["edges"] = [e for e in g["edges"] if not (e["target"] == mon["id"] and e["targetHandle"] == "clips" and e["source"] in scenes)]
        for sid in scenes:
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": sid, "sourceHandle": "clip", "target": mon["id"], "targetHandle": "clips"})
        # the user's clips keep their places around the clip's: an intro before it, an ending after it
        was = [x for x in mon["data"].get("order") or [] if x in ids]
        first = next((k for k, x in enumerate(was) if node(g, x) and node(g, x)["data"].get("from") == wid and not node(g, x)["data"].get("detached")), len(was))
        users = [x for x in was if not (((node(g, x) or {}).get("data") or {}).get("from") == wid and not ((node(g, x) or {}).get("data") or {}).get("detached"))]
        mon["data"]["order"] = [x for x in was[:first] if x in users] + scenes + [x for x in users if x not in was[:first]]

    g = update(pid, go)
    return {**g, "kept": kept}


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
                    "who": [i for i, _ in prompts.scene_cast(plan, s)] if people and not prompts.no_cast(plan, s) else [],
                    "refs": prompts.photo_people(plan, s) if prompts.uses_refs(plan, s) else []})
    return {"scenes": out}
