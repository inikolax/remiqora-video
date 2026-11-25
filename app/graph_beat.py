"""The graph's side of the beat clip: the «Сценарист пула» node (writes the shot pool),
«Развернуть» (the pool as picture -> scene chains into a «Бит-монтаж» and an «Выход»), the faceless hero's preset.
graph.py calls these; the autopilot's `beat` kind (beat_clip.py) runs the same functions."""
from __future__ import annotations

import random
import uuid
from typing import Optional

from . import beat_models, graph, hero as hero_lib, i18n, projects, song
from .planner import beat

GENRES = ("techno", "dnb", "hardstyle", "pop")
POOL_N = 16
COLS = 6
CELL_W = 360


def genre_of_bpm(bpm: float) -> str:
    """The genre preset by tempo: < 120 pop, 120-150 techno, 150-160 hardstyle, > 160 DnB."""
    if bpm < 120:
        return "pop"
    if bpm <= 150:
        return "techno"
    return "hardstyle" if bpm < 160 else "dnb"


def inputs(c: "graph.Ctx", n: dict) -> tuple[Optional[dict], str, Optional[dict]]:
    """(the «Песня» node, the idea, the hero node) of a «Сценарист пула»."""
    song_n = next((c.by[s] for s, _ in c.inputs(n["id"], "song") if s in c.by), None)
    idea = next((c.by[s]["data"].get("text", "") for s, _ in c.inputs(n["id"], "idea") if s in c.by), "") or n["data"].get("idea", "")
    hero = next((c.by[s] for s, _ in c.inputs(n["id"], "cast") if s in c.by), None)
    return song_n, (idea or "").strip(), hero


def hero_lines(hero: Optional[dict]) -> tuple[str, str]:
    """(the hero's line, its close-up line): a faceless hero node's preset; no hero - the default preset."""
    d = (hero or {}).get("data") or {}
    card = d if hero_lib.is_faceless(d) else hero_lib.faceless_card(hero_lib.FACELESS_DEFAULT)
    return hero_lib.faceless_line(card), hero_lib.faceless_head(card)


def hero_brief(hero: Optional[dict]) -> dict:
    """What the user said about the hero, {text, own, hidden, base, keep}: `text` the user's words (empty = the preset as
    it is), `own` «Свой герой» (the text alone), `hidden` the faceless rules, `base` the preset's line the words are details of
    (empty for an own hero), `keep` the words of the preset's mask that must stay."""
    d = (hero or {}).get("data") or {}
    if not hero_lib.is_faceless(d):
        return {"text": "", "own": False, "hidden": True, "base": "", "keep": ()}
    own = hero_lib.is_own(d)
    preset = d.get("preset") or ""
    return {"text": hero_lib.hero_text(d), "own": own, "hidden": hero_lib.face_hidden(d),
            "base": "" if own else hero_lib.faceless_line(d),
            "keep": () if own or not hero_lib.face_hidden(d) else hero_lib.PRESET_KEEP.get(preset, ())}


def genre_of(n: dict, song_n: Optional[dict]) -> str:
    g = n["data"].get("genre")
    if g in GENRES:
        return g
    try:
        return genre_of_bpm(song.analysis(song_n["data"]["song"]).bpm) if song_n and song_n["data"].get("song") else "techno"
    except Exception:  # noqa: BLE001 - no analysis: the default
        return "techno"


def effective_look(d: dict, st: dict) -> str:
    """The look write() sends: the node's own, else the project's, else «auto»."""
    return d.get("look") if d.get("look") not in (None, "", "auto") else st.get("look") if st.get("look") not in (None, "", "auto") else "auto"


def sig(c: "graph.Ctx", n: dict) -> str:
    """What the pool was written from: the song's key, the idea, the hero's words, the look, the genre, the count."""
    song_n, idea, hero = inputs(c, n)
    sa = graph.evaluate_node(c, song_n["id"]) if song_n else None
    d = n["data"]
    b = hero_brief(hero)
    extra = (b["text"], b["own"], b["hidden"]) if b["text"] else ()   # no words: the key is what it always was
    # the look write() really uses: the node's own, else the project's. Both auto / empty: the old inputs only (no stale pools)
    if d.get("look") in (None, "", "auto") and (eff := effective_look(d, c.proj.get("settings") or {})) != "auto":
        extra += (eff,)
    return graph._sha("pool", sa.key if sa and sa.state == "ready" else None, idea, hero_lines(hero), d.get("look"), d.get("genre"), d.get("n"), *extra)


def chorus_words(sid: str) -> str:
    """The words of the first chorus (the lines sung twice) for the writer's brief."""
    try:
        ls = song.lines(sid)
        spans = song.chorus_spans(ls)
    except Exception:  # noqa: BLE001
        return ""
    if not spans:
        return ""
    a, b = spans[0]
    return " / ".join(x["text"] for x in ls if x["start"] >= a - 0.01 and x["end"] <= b + 0.01)[:400]


async def write(client, proj: dict, c: "graph.Ctx", w: dict) -> dict:
    """«Написать» of a «Сценарист пула»: writer.write_pool by the idea, the hero's preset, the look (or the node's palette) and
    the chorus words. -> the node's new data (pool, palette, style, mstyle, sig, seed)."""
    from .llm import writer
    song_n, idea, hero = inputs(c, w)
    if not idea:
        raise ValueError(i18n.L("нет идеи: подключите узел «Идея»", "no idea: connect an «Idea» node"))
    d = w["data"]
    st = proj.get("settings") or {}
    # a look the user picked wins; «auto» sends no colours to the writer - the palette comes from the light it chose for the idea.
    # A palette on the node is taken as the user's only when this module did not write it (palette_auto)
    look = effective_look(d, st)
    own_pal = d.get("palette") if isinstance(d.get("palette"), dict) and not d.get("palette_auto") else None
    line, head = hero_lines(hero)
    sid = (song_n or {}).get("data", {}).get("song")
    seed = int(d.get("seed") or random.randrange(100000))
    b = hero_brief(hero)
    words = {"hero_text": b["text"], "hero_base": b["base"], "face_hidden": b["hidden"], "hero_keep": b["keep"]} if b["text"] else {}
    pool = await writer.write_pool(idea, line, own_pal or look,
                                   chorus_words(sid) if sid else "", genre_of(w, song_n), int(d.get("n") or POOL_N),
                                   model_id=client.model.id, seed=seed, head_line=head, **words)
    out = {"pool": [dict(s) for s in pool], "palette": pool.palette, "palette_auto": pool.palette_auto, "style": pool.style, "mstyle": pool.mstyle, "seed": seed, "sig": sig(c, w)}
    if b["text"]:   # the hero's line the artist sees: the user can edit it, «Развернуть» puts the edit into the pool
        out.update(hero_en=pool.hero_en, head_en=pool.head_en, hero_used=pool.hero_en, head_used=pool.head_en, hero_fallback=bool(pool.hero_fallback))
    elif d.get("hero_en") or d.get("hero_used"):   # the words were taken away since: the preset's line is back
        out.update(hero_en="", head_en="", hero_used="", head_used="", hero_fallback=False)
    return out


def apply_hero_edit(d: dict) -> None:
    """The user's edit of «Как видит художник» (`hero_en` / `head_en`) goes into the pool: the line the pool was written with
    (`hero_used` / `head_used`) is replaced by the edited one in every shot's picture, in place (the hero's own words are in
    the pool's text as the writer's marker was replaced by them)."""
    for key, used in (("hero_en", "hero_used"), ("head_en", "head_used")):
        new, old = (d.get(key) or "").strip(), (d.get(used) or "").strip()
        if not new or not old or new == old:
            continue
        for s in d.get("pool") or []:
            for o, n in ((old, new), (old[:1].upper() + old[1:], new[:1].upper() + new[1:])):   # the line opens a picture capitalised
                if isinstance(s, dict) and o in (s.get("picture_en") or ""):
                    s["picture_en"] = s["picture_en"].replace(o, n)
        d[used] = new


def expand(pid: str, wid: str, edited: str = "ask") -> dict:
    """«Развернуть» of a «Сценарист пула»: per shot a «Картинка» (the prompt by framing), a «Промт» (the motion) and a «Сцена»
    (3 s, from the picture, with `role` and `framing`), all into a «Бит-монтаж» (the song its track) and an «Выход» (the phone
    copy and the cover on). Again after a rewrite: the nodes of this writer (`from`, by the shot's title) get the new texts,
    their seeds and places stay; nodes the user changed since: `edited` "ask" (graph.Edited, the page asks), "keep",
    "replace". A shot the pool no longer has goes. -> the graph, `kept`."""
    kept: list[str] = []

    def go(g: dict) -> None:
        w = graph.node(g, wid)
        if not w or w["type"] != "pool_writer" or not w["data"].get("pool"):
            raise ValueError(i18n.L("У сценариста пула нет шотов: сначала «Написать»", "The pool writer has no shots: «Write» first"))
        d = w["data"]
        apply_hero_edit(d)
        c = graph.Ctx(projects.load(pid), g)
        song_n, _, _ = inputs(c, w)
        pool = [dict(s) for s in d["pool"] if isinstance(s, dict) and s.get("picture_en")]
        base = int(d.get("seed") or 1)
        for i, s in enumerate(pool):
            s.setdefault("seed", (base + 101 * i) % (2**31 - 1) + 1)
        style, mstyle = d.get("style") or beat.styles()[0], d.get("mstyle") or beat.styles()[1]
        model = beat_models.known(c.card.id)   # the project's video model: the scenes and their prompts are made for it
        specs = beat.pool_to_nodes(pool, style, mstyle, seed=base, cols=COLS, model=model)
        graph.detach_copies(g, wid, lambda nn: (nn["data"].get("shot"), nn["type"]))   # a pasted copy is not the writer's
        mine = {(nn["data"].get("shot"), nn["type"]): nn for nn in g["nodes"] if nn["data"].get("from") == wid and not nn["data"].get("detached")}
        changed = [nn for nn in mine.values() if nn["data"].get("made") and graph._made(nn) != nn["data"]["made"]]
        if changed and edited == "ask":
            raise graph.Edited([nn["data"].get("title") or graph.type_title(nn["type"]) for nn in changed])
        hold = {nn["id"] for nn in changed} if edited == "keep" else set()
        kept.extend(nn["data"].get("title") or graph.type_title(nn["type"]) for nn in changed if nn["id"] in hold)
        x0, y0 = w["position"]["x"] + 420, w["position"]["y"]
        keep: set[str] = set()
        by_spec: dict[str, dict] = {}
        for i, shot in enumerate(pool):
            for k in range(3):
                sp = specs["nodes"][i * 3 + k]
                old = mine.get((shot["title"], sp["type"]))
                data = {**sp["data"], "shot": shot["title"]}
                if old is None:
                    nn = {"id": sp["id"], "type": sp["type"], "position": {"x": x0 + sp["position"]["x"], "y": y0 + sp["position"]["y"]},
                          "data": {"from": wid, **data}}
                    g["nodes"].append(nn)
                else:
                    nn = old
                    if nn["id"] not in hold:
                        for key, val in data.items():
                            if key == "seed" and nn["data"].get("seed"):
                                continue   # the picture's / scene's own seed stays
                            nn["data"][key] = val
                        if nn["type"] == "scene" and "model" not in data and nn["data"].get("model") in beat_models.MODELS:
                            nn["data"].pop("model")   # back to the project's H3: the scene follows it again
                if nn["id"] not in hold:
                    nn["data"]["made"] = graph._made(nn)
                by_spec[sp["id"]] = nn
                keep.add(nn["id"])
        for nn in [x for x in g["nodes"] if x["data"].get("from") == wid and not x["data"].get("detached") and x["type"] in ("picture", "prompt", "scene") and x["id"] not in keep]:
            g["nodes"].remove(nn)
        ids = {x["id"] for x in g["nodes"]}
        g["edges"] = [e for e in g["edges"] if e["source"] in ids and e["target"] in ids]
        for e in specs["edges"]:   # picture -> scene.start, prompt -> scene.prompt (a wire the user moved stays theirs)
            s, t = by_spec[e["source"]], by_spec[e["target"]]
            if t["id"] in hold or any(x["target"] == t["id"] and x["targetHandle"] == e["targetHandle"] for x in g["edges"]):
                continue
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": s["id"], "sourceHandle": e["sourceHandle"], "target": t["id"],
                               "targetHandle": e["targetHandle"]})
        # the beat montage and the output: made once
        bm = next((x for x in g["nodes"] if x["type"] == "beat_montage" and x["data"].get("from") == wid), None)
        if not bm:
            bx = x0 + COLS * CELL_W + 80
            bm = {"id": uuid.uuid4().hex[:8], "type": "beat_montage", "position": {"x": bx, "y": y0},
                  "data": {"from": wid, "title": i18n.L("Бит-монтаж", "Beat montage")}}
            out = {"id": uuid.uuid4().hex[:8], "type": "output", "position": {"x": bx + 420, "y": y0},
                   "data": {"from": wid, "output": {"size": "off", "hdr": False, "fps48": False}, "phone": True, "cover": True}}
            g["nodes"] += [bm, out]
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": bm["id"], "sourceHandle": "video", "target": out["id"], "targetHandle": "video"})
        if song_n and not any(e["target"] == bm["id"] and e["targetHandle"] == "track" for e in g["edges"]):
            g["edges"].append({"id": uuid.uuid4().hex[:8], "source": song_n["id"], "sourceHandle": "song", "target": bm["id"], "targetHandle": "track"})
        # the pool's palette follows the pool (a new look, palette_from_light) unless the user set one in the BeatPanel
        # (put_beat marks it `palette_user`)
        if isinstance(d.get("palette"), dict) and (not bm["data"].get("palette") or not bm["data"].get("palette_user")):
            bm["data"]["palette"] = d["palette"]
            bm["data"]["palette_from_pool"] = True
        shots = [by_spec[specs["nodes"][i * 3 + 2]["id"]]["id"] for i in range(len(pool))]
        wired = {e["source"] for e in g["edges"] if e["target"] == bm["id"] and e["targetHandle"] == "clips"}
        # a shot the user cut from the pool (its wire deleted) stays out when it was wired before: `order` remembers the shots
        known = set(bm["data"].get("order") or [])
        for sid in shots:
            if sid not in wired and sid not in known:
                g["edges"].append({"id": uuid.uuid4().hex[:8], "source": sid, "sourceHandle": "clip", "target": bm["id"], "targetHandle": "clips"})
        bm["data"]["order"] = shots

    return {**graph.update(pid, go), "kept": kept}


def hero_data(preset: str = "", text: str = "", own: bool = False, hidden: bool = True) -> dict:
    """A faceless «Герой» node's data: a preset (alone, or with the user's details in `desc`) or «Свой герой» (`own`: the text
    alone, `face_hidden` on / off). No text and no `own`: exactly hero_preset's data."""
    text = (text or "").strip()
    if own:
        return hero_lib.own_card(text, hidden)
    card = hero_preset(preset)
    if text:
        card["desc"] = text
    return card


def hero_preset(preset: str) -> dict:
    """The data a faceless «Герой» node takes for a preset: kind, preset, the English and Russian lines."""
    if preset not in hero_lib.FACELESS_PRESETS:
        raise ValueError(i18n.L(f"Нет такого героя: {preset}", f"No such hero: {preset}"))
    return hero_lib.faceless_card(preset)
