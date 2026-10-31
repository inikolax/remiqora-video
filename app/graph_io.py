"""The graph's ways in and out (phase 9, G4/G5): a storyboard -> a new graph project with the same keys (its shots
are taken from the storyboard's cache, nothing is copied), a linear graph -> a new storyboard of own prompts, graph
templates (local files), cleaning unused takes and stale files into the Recycle Bin."""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional

from . import config, graph, i18n, post, projects, render
from .planner import prompts

BUILTIN_TEMPLATES = Path(__file__).parent / "graph_templates"
USER_TEMPLATES = config.ROOT / "data" / "graph_templates"
COL, ROW_H = 640, 300   # a prompt and its scene take one column of 640; a row is a chain


def _id() -> str:
    return uuid.uuid4().hex[:8]


def _edge(s: str, sp: str, t: str, tp: str) -> dict:
    return {"id": _id(), "source": s, "sourceHandle": sp, "target": t, "targetHandle": tp}


def _copy_in(src: Path, folder: Path, prefix: str) -> str:
    """A file into the project, its bytes as they are (keys hash the bytes); one copy per source file."""
    name = f"{prefix}_{src.name}"
    if not (folder / name).exists():
        shutil.copyfile(src, folder / name)
    return name


def new_project(name: str, aspect: str, quality: str = "draft", g: Optional[dict] = None,
                extra: Optional[dict] = None) -> dict:
    proj = projects.create({"aspect": aspect, "quality": quality, **(extra or {})})
    proj["type"] = "graph"
    proj["name"] = name.strip() or i18n.L("Граф", "Graph")
    projects.save(proj)
    graph._write(proj["id"], graph.clean(g or starter()))
    return proj


def starter() -> dict:
    """A new graph: one prompt -> one scene -> the assembly -> the output, to start from."""
    p, s, j, o = _id(), _id(), _id(), _id()
    return {"rev": 0, "nodes": [
        {"id": p, "type": "prompt", "position": {"x": 0, "y": 0}, "data": {"title": i18n.L("Сцена 1", "Scene 1"), "text": ""}},
        {"id": s, "type": "scene", "position": {"x": 320, "y": 0}, "data": {"title": i18n.L("Сцена 1", "Scene 1"), "takes": [random.randrange(1, 2**31)], "take": 0}},
        {"id": j, "type": "join", "position": {"x": 680, "y": 0}, "data": {"order": [s]}},
        {"id": o, "type": "output", "position": {"x": 1000, "y": 0}, "data": {"output": {"size": "1080p", "hdr": False, "fps48": False}}}],
        "edges": [_edge(p, "text", s, "prompt"), _edge(s, "clip", j, "clips"), _edge(j, "video", o, "video")]}


# ---------------------------------------------------------------------------------------------------------------
# storyboard -> graph
# ---------------------------------------------------------------------------------------------------------------
def from_storyboard(src: dict) -> dict:
    """«Копия — проект-граф»: every scene becomes a Prompt (its composed prompt, word for word) and a Scene (its seed);
    a continuation starts from the previous scene's last frame; start photos and Ref2VA photos become Photo nodes
    (the same bytes); the project's LoRA one LoRA node; the track a Track and a Music node; the output its own.
    The keys are the storyboard's, so its shots are found in its cache (`cache_from`)."""
    plan, st = src.get("plan") or {}, src.get("settings") or {}
    if not plan.get("scenes"):
        raise ValueError(i18n.L("Раскадровки нет", "No storyboard"))
    bad = [s["index"] + 1 for s in plan["scenes"] if not prompts.is_written(s)]
    if bad:
        raise ValueError(i18n.L("Сцены без промта: ", "Scenes without a prompt: ") + ", ".join(map(str, bad)))
    proj = new_project(f"{src.get('name') or i18n.L('Ролик', 'Video')} · {i18n.L('граф', 'graph')}", st.get("aspect", "16:9"), st.get("quality", "draft"),
                       {"nodes": [], "edges": []}, {"cache_from": [src["id"]], "from_storyboard": src["id"],
                                                    **({"video_model": st["video_model"]} if st.get("video_model") else {})})   # the same model: its shots are the same keys
    proj["lang"] = i18n.plan_lang(src.get("plan"))   # its lines are the storyboard's, in its language
    projects.save(proj)
    folder, sfolder = projects.folder(proj["id"]), projects.folder(src["id"])
    nodes, edges = [], []
    photos: dict[str, str] = {}   # source file -> Photo node id

    def photo(path: Path, y: float) -> str:
        if str(path) not in photos:
            nid = _id()
            nodes.append({"id": nid, "type": "photo", "position": {"x": -340, "y": y},
                          "data": {"file": _copy_in(path, folder, "photo"), "title": path.name}})
            photos[str(path)] = nid
        return photos[str(path)]

    lora = None
    if st.get("loras"):
        lora = _id()
        nodes.append({"id": lora, "type": "lora", "position": {"x": -340, "y": -320}, "data": {"items": st["loras"]}})
    row, col, scene_ids = -1, 0, []
    for s in plan["scenes"]:
        if s["kind"] == "new" or row < 0 or col == 6:
            row, col = row + 1, 0
        x, y = col * COL, row * ROW_H
        col += 1
        p, sc = _id(), _id()
        title = i18n.L(f"Сцена {s['index'] + 1}", f"Scene {s['index'] + 1}")
        text, lines = prompts.split_lines(plan, s)
        nodes.append({"id": p, "type": "prompt", "position": {"x": x, "y": y},
                      "data": {"title": title, "text": text, "ru": s.get("ru", ""), **({"lines": lines} if lines else {})}})
        nodes.append({"id": sc, "type": "scene", "position": {"x": x + 300, "y": y},
                      "data": {"title": title, "takes": [render._seed(plan, s)], "take": 0}})
        edges.append(_edge(p, "text", sc, "prompt"))
        src = prompts.from_of(plan, s)
        if src is not None and scene_ids:   # a continuation: from the scene it names, or the one just before it
            edges.append(_edge(scene_ids[src["index"]], "frame", sc, "start"))
        elif prompts.starts_from_photo(s) and (sfolder / s["start_photo"]).exists():
            edges.append(_edge(photo(sfolder / s["start_photo"], y), "image", sc, "start"))
        for r in render.ref_photos(src, plan, s):
            edges.append(_edge(photo(r, y + 40), "image", sc, "faces"))
        if lora:
            edges.append(_edge(lora, "lora", sc, "lora"))
        scene_ids.append(sc)
    x_end = 6 * COL + 40
    j, o = _id(), _id()
    nodes.append({"id": j, "type": "join", "position": {"x": x_end, "y": 0}, "data": {"order": scene_ids}})
    edges += [_edge(sc, "clip", j, "clips") for sc in scene_ids]
    last = j
    track = st.get("track")
    if track and (sfolder / track["file"]).exists():
        t, m = _id(), _id()
        name = _copy_in(sfolder / track["file"], folder, "track")
        nodes.append({"id": t, "type": "track", "position": {"x": x_end, "y": 260}, "data": {"file": name, "name": track.get("name") or name}})
        nodes.append({"id": m, "type": "music", "position": {"x": x_end + 320, "y": 120},
                      "data": {k: track[k] for k in ("volume", "scene_volume", "offset", "fade_in", "fade_out") if k in track}})
        edges += [_edge(j, "video", m, "video"), _edge(t, "audio", m, "audio")]
        last = m
    nodes.append({"id": o, "type": "output", "position": {"x": x_end + 660, "y": 0}, "data": {"output": post.output_of(st)}})
    edges.append(_edge(last, "video", o, "video"))
    graph._write(proj["id"], graph.clean({"rev": 0, "nodes": nodes, "edges": edges}))
    return proj


# ---------------------------------------------------------------------------------------------------------------
# graph -> storyboard
# ---------------------------------------------------------------------------------------------------------------
def to_storyboard(proj: dict) -> dict:
    """«Собрать раскадровку»: only a linear graph - one output, one assembly, every clip a 5 s scene whose prompt is a
    text node and which starts from nothing, from a photo or from the scene just before it; one set of LoRA. Faces
    (Ref2VA) become the cast - one character per photo, a hero's look with it - and each scene lists its own
    (`faces`, prompts.photo_people), in its order. The result is a storyboard of own prompts (manual) with the same
    seeds and keys; the shots it needs are linked (hard links, not copies) into its scenes/."""
    from .llm import writer
    from .planner import check
    g = graph.load(proj["id"])
    c = graph.Ctx(proj, g)
    outs = graph.outputs_of(g)
    if len(outs) != 1:
        raise ValueError(i18n.L("Нужен ровно один «Выход» (сейчас: %d)", "Exactly one «Output» is needed (now: %d)") % len(outs))
    o = outs[0]
    up = c.inputs(o, "video")
    if not up:
        raise ValueError(i18n.L("«Выход» ни к чему не подключён", "«Output» is not connected to anything"))
    v, track_node, music_node = up[0][0], None, None
    if c.by[v]["type"] == "music":
        music_node = c.by[v]
        a = c.inputs(v, "audio")
        track_node = c.by[a[0][0]] if a else None
        vv = c.inputs(v, "video")
        if not vv:
            raise ValueError(i18n.L("«Музыка» без ролика на входе", "«Music» has no video at its input"))
        v = vv[0][0]
    if c.by[v]["type"] != "join":
        raise ValueError(i18n.L("Перед выходом должна быть «Склейка»", "A «Join» must come before the output"))
    folder = projects.folder(proj["id"])
    ids = graph.join_order(c, v)
    if not ids:
        raise ValueError(i18n.L("В склейке нет сцен", "The join has no scenes"))
    scenes_out, loras = [], None
    faces: dict[str, dict] = {}   # a photo's hash -> {path, hero node}: the cast, in order of first appearance
    for k, sid in enumerate(ids):
        n = c.by[sid]
        name = n["data"].get("title") or i18n.L("Сцена", "Scene")
        if n["type"] != "scene":
            raise ValueError(i18n.L(f"В склейке «{name}» — не сцена", f"«{name}» in the join is not a scene"))
        if graph.seconds_of(n) != graph.LENGTH_S:
            raise ValueError(i18n.L(f"«{name}» длиной {graph.seconds_of(n)} с: в раскадровке все сцены по {graph.LENGTH_S} с",
                                     f"«{name}» is {graph.seconds_of(n)} s long: in a storyboard every scene is {graph.LENGTH_S} s"))
        text = graph.scene_text(c, sid)
        if not text:
            raise ValueError(i18n.L(f"«{name}»: нет промта", f"«{name}»: no prompt"))
        mine = []
        for s_id, sp in c.inputs(sid, "faces"):
            f = graph._out(c, s_id, sp)
            if not f.path or not f.path.exists():
                raise ValueError(i18n.L(f"«{name}»: фото для лица ещё нет — снимите или загрузите его",
                                         f"«{name}»: no face photo yet — shoot or upload it"))
            h = render.file_sha(f.path)
            faces.setdefault(h, {"path": f.path, "hero": c.by[s_id] if c.by[s_id]["type"] == "hero" else None})
            mine.append(list(faces).index(h) + 1)
        start, start_photo = c.inputs(sid, "start"), None
        from_scene = graph.start_scene(c, sid)
        cont = bool(k) and from_scene in ids[:k]   # from the scene before it, or from any earlier one («from»)
        if start and not cont:   # a picture as the first frame: a photo, a drawn picture, a hero's photo
            f = graph._out(c, *start[0])
            if c.by[start[0][0]]["type"] not in ("photo", "picture", "hero") or not f.path or not f.path.exists():
                raise ValueError(i18n.L(f"«{name}» стартует не с кадра более ранней сцены и не с готовой картинки",
                                         f"«{name}» starts neither from an earlier scene's frame nor from a ready picture"))
            start_photo = f.path
        mine_loras = [x for s_id, _ in c.inputs(sid, "lora") for x in graph.evaluate_node(c, s_id).loras]
        ls = sorted((x["id"], round(float(x["strength"]), 3)) for x in mine_loras)
        if loras is not None and ls != sorted((x["id"], round(float(x["strength"]), 3)) for x in loras):
            raise ValueError(i18n.L("У сцен разные LoRA: в раскадровке один набор на весь ролик",
                                "The scenes have different LoRAs: a storyboard has one set for the whole video"))
        loras = loras if loras is not None else mine_loras
        a = graph.evaluate_node(c, sid)
        scenes_out.append({"text": text, "seed": graph.seed_of(n), "kind": "continue" if cont else "new",
                           "from": ids.index(from_scene) if cont else None,
                           "start_photo": start_photo, "key": a.key if a.state in ("ready", "todo") else None, "faces": mine})
    st = proj.get("settings") or {}
    n_sc = len(scenes_out)
    out_set = post.output_of({"output": c.by[o]["data"].get("output") or {"size": "1080p"}})
    mode = "none" if not faces else "one" if len(faces) == 1 else "several"
    settings = {"idea": proj.get("name") or "", "seconds": n_sc * graph.LENGTH_S, "aspect": c.aspect, "mood": "", "mode": mode,
                "music": "", "photo_start": False, "seed": -1, "manual": True, "model": None, "quality": c.quality,
                "loras": loras or [], "output": out_set, "rtx": out_set["size"] != "off",
                **({"video_model": st["video_model"]} if st.get("video_model") else {})}
    sb = projects.create(settings)
    sfolder = projects.folder(sb["id"])
    plan = writer.new_plan(proj.get("name") or "", n_sc * graph.LENGTH_S, mode, seed=random.randrange(100000))
    plan["manual"] = True
    plan["lang"] = i18n.plan_lang(proj)   # the graph's lines, in its language
    plan["scenes"] = plan["scenes"][:n_sc]
    if faces:   # Ref2VA: a character per photo; the scenes name theirs, so the others are shot without
        plan["cast"] = [_face_cast(f, sfolder, i) for i, f in enumerate(faces.values())]
        plan["ref_photo"] = True
    from . import edit
    edit.ensure_ids(plan)
    for s, x in zip(plan["scenes"], scenes_out):
        s.update(raw=x["text"], locked=True, source="user", kind=x["kind"], seed=x["seed"])
        if x["from"] is not None and x["from"] != s["index"] - 1:
            s["from"] = plan["scenes"][x["from"]]["id"]
        if x["start_photo"]:
            s["start_photo"] = _copy_in(x["start_photo"], sfolder, "start")
        if faces:
            s["faces"] = x["faces"]
            if mode == "several":
                s["who"] = sorted(x["faces"])
    sb["plan"] = check.plan(plan)
    if track_node and (folder / track_node["data"].get("file", "")).exists():
        name = _copy_in(folder / track_node["data"]["file"], sfolder, "track")
        from . import music
        sb["settings"]["track"] = {**music.DEFAULTS, **{k: music_node["data"][k] for k in music.DEFAULTS if k in music_node["data"]},
                                   "file": name, "name": track_node["data"].get("name") or name}
    sb["name"] = f"{proj.get('name') or i18n.L('Граф', 'Graph')} · {i18n.L('раскадровка', 'storyboard')}"
    projects.save(sb)
    # the shots: linked, so «Снять ролик» finds them (a storyboard reads only its own scenes/)
    (sfolder / "scenes").mkdir(exist_ok=True)
    for x in scenes_out:
        hit = c.cached_shot(x["key"]) if x["key"] else None
        for p in hit or ():
            dst = sfolder / "scenes" / p.name
            if not dst.exists():
                try:
                    os.link(p, dst)
                except OSError:
                    shutil.copyfile(p, dst)
    return sb


def _face_cast(f: dict, sfolder: Path, i: int) -> dict:
    """A character of a storyboard made from a graph: the photo (its bytes - the key hashes them) and, when the face
    came from a «Герой», his look; from a plain photo only the photo."""
    d = (f["hero"] or {}).get("data") or {}
    c = {k: d.get(k, "") for k in ("gender", "age", "en", "ru", "outfit_en", "outfit_ru")}
    c["ru"] = c["ru"] or i18n.L(f"Лицо с фото {f['path'].name}", f"Face from the photo {f['path'].name}")
    c["photo"] = _copy_in(f["path"], sfolder, f"face{i + 1}")
    return c


# ---------------------------------------------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------------------------------------------
def _slug(name: str) -> str:
    s = re.sub(r"[^\w-]+", "-", name.strip().lower(), flags=re.UNICODE).strip("-")
    return (s or "shablon")[:60]


def templates() -> list[dict]:
    out = []
    for d, own in ((BUILTIN_TEMPLATES, False), (USER_TEMPLATES, True)):
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            if not own and i18n.ui() == "en" and (BUILTIN_TEMPLATES / "en" / f.name).exists():
                f = BUILTIN_TEMPLATES / "en" / f.name   # the English twin: the same graph, its texts in English
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append({"id": ("user:" if own else "") + f.stem, "name": t.get("name") or f.stem, "about": t.get("about", ""),
                        "own": own, "order": t.get("order", 999), "saved": f.stat().st_mtime if own else None,
                        "nodes": t.get("nodes", []), "edges": t.get("edges", [])})
    # the built-in ones in their order (simple to complex), then the user's, newest first
    return sorted(out, key=lambda t: (t["own"], t["order"] if not t["own"] else -(t["saved"] or 0), t["name"]))


TEMPLATE_FORMAT = "h3studio-graph-template"   # the JSON a template is saved to and loaded from
MAX_TEMPLATE_NODES = 400


def save_template(name: str, about: str, nodes: list, edges: list, replace: bool = True) -> dict:
    """A user's template into data/graph_templates. `replace=False` (a loaded JSON) never overwrites one of the same
    name: the name gets « (2)», « (3)»…"""
    USER_TEMPLATES.mkdir(parents=True, exist_ok=True)
    if len(nodes) > MAX_TEMPLATE_NODES:
        raise ValueError(i18n.L(f"Слишком большой шаблон: {len(nodes)} узлов (не больше {MAX_TEMPLATE_NODES})",
                                f"Template too big: {len(nodes)} nodes (at most {MAX_TEMPLATE_NODES})"))
    g = graph.clean({"nodes": nodes, "edges": edges})
    if not g["nodes"]:
        raise ValueError(i18n.L("В шаблоне нет ни одного узла, который знает Remiqora Video",
                                "The template has no node Remiqora Video knows"))
    # files of this project don't travel: a template keeps the structure and the texts
    for n in g["nodes"]:
        for k in ("file", "photo", "plan", "sig"):
            n["data"].pop(k, None)
    t = {"format": TEMPLATE_FORMAT, "version": 1, "name": name.strip()[:80] or i18n.L("Шаблон", "Template"), "about": about.strip()[:300],
         "nodes": g["nodes"], "edges": g["edges"]}
    slug = _slug(t["name"])
    if not replace:
        base, k = t["name"], 2
        while (USER_TEMPLATES / f"{slug}.json").exists():
            t["name"] = f"{base} ({k})"
            slug, k = _slug(t["name"]), k + 1
    (USER_TEMPLATES / f"{slug}.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"id": "user:" + slug, **t, "own": True, "dropped": {"nodes": len(nodes) - len(g["nodes"]), "edges": len(edges) - len(g["edges"])}}


def delete_template(tid: str) -> None:
    if not tid.startswith("user:"):
        raise ValueError(i18n.L("Встроенный шаблон не удаляется", "A built-in template can't be deleted"))
    p = USER_TEMPLATES / f"{_slug(tid[5:])}.json"
    if p.exists():
        from .models_page import to_recycle_bin
        to_recycle_bin(p)


# ---------------------------------------------------------------------------------------------------------------
# cleaning (G5): takes not chosen, and files no node points to, into the Recycle Bin
# ---------------------------------------------------------------------------------------------------------------
def cleanup(proj: dict, do: bool = False) -> dict:
    """What can go: the shots of takes that are not the chosen one, and - only when every node's key is known (no
    scene waits for an unshot start) - every file under scenes/, out/, frames/, pictures/ that no current key names.
    The storyboard this graph came from is never touched. do=True moves them to the Recycle Bin and forgets the takes."""
    g = graph.load(proj["id"])
    folder = projects.folder(proj["id"])
    c = graph.Ctx(proj, g)
    arts = graph.evaluate(c)
    keep, takes_gone, files = set(), {}, []
    for n in g["nodes"]:
        a = arts[n["id"]]
        if a.key:
            keep.add(a.key)
        if n["type"] == "scene" and a.takes:
            chosen = graph.seed_of(n)
            for t in a.takes:
                if t["seed"] != chosen:
                    takes_gone.setdefault(n["id"], []).append(t["seed"])
                    files += [p for p in render.shot_paths(folder / "scenes", t["key"]) if p.exists()]
    # a folder's stale files only when every node writing into it knows its key (none waits for an unshot input)
    writers = {"scenes": ("scene",), "out": ("join", "montage", "music", "output", "v2v", "sound", "facefix", "enhance"), "frames": ("frame",),
               "pictures": ("picture",)}
    sure = {sub: not any(arts[n["id"]].state in ("wait", "blocked") for n in g["nodes"] if n["type"] in types)
            for sub, types in writers.items()}
    known = all(sure.values())
    for sub in writers:
        d = folder / sub
        if sure[sub] and d.exists():
            for p in d.iterdir():
                # v2v_<key>.mp4 / .png / .webm / .mov: «Видео → видео» (its .mov made on a download)
                # <key>.voice.json: how alike a voice scene is to its sample (voice.py)
                # facefix_<key> / enhance_<key>.mp4 / .png / .json: «Лица», «Улучшить» (missing until 2026-10-28: their
                # results counted as stale)
                stem = p.name.split(".", 1)[0]
                stem = stem.split("_", 1)[1] if stem.startswith(("join_", "music_", "montage_", "v2v_", "sound_", "facefix_", "enhance_")) else stem
                if p.is_file() and not p.name.startswith("_") and stem not in keep and p not in files:   # _frames.json: edit.py's
                    files.append(p)
    size = sum(p.stat().st_size for p in files if p.exists())
    if do:
        from .models_page import to_recycle_bin
        for p in files:
            if p.exists():
                to_recycle_bin(p)

        def prune(gg: dict) -> None:
            for nid, seeds in takes_gone.items():
                nn = graph.node(gg, nid)
                if nn:
                    chosen = graph.seed_of(nn)
                    nn["data"]["takes"] = [s for s in nn["data"].get("takes") or [] if int(s) not in seeds] or [chosen]
                    nn["data"]["take"] = nn["data"]["takes"].index(chosen) if chosen in nn["data"]["takes"] else 0
        graph.update(proj["id"], prune)
    return {"files": len(files), "bytes": size, "takes": sum(len(v) for v in takes_gone.values()), "all_known": known,
            "names": [p.relative_to(folder).as_posix() for p in files[:50]]}
