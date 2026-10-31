"""Projects on disk: projects/<id>/project.json holds the settings (frame, quality, LoRA, the hero's photo) and the
storyboard (the writer's plan); the photo lies beside it. Shots of phase 4 will go to projects/<id>/scenes/.
The file is the truth: every job (writing, rewriting) reads it when it starts and writes it when it ends, so a closed
page loses nothing."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config
from .planner import grid, prompts
from . import i18n

ROOT = config.ROOT / "projects"
ROOT.mkdir(exist_ok=True)
_ID = re.compile(r"^[a-z0-9-]{6,40}$")


class NotFound(Exception):
    pass


def folder(pid: str) -> Path:
    if not _ID.match(pid or ""):
        raise NotFound(pid)
    return ROOT / pid


def create(settings: dict) -> dict:
    pid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    folder(pid).mkdir(parents=True)
    now = time.time()
    from . import i18n
    # lang: the language of its texts and spoken lines (i18n.plan_lang; a graph's prompt nodes read it here)
    proj = {"id": pid, "name": "", "created": now, "updated": now, "settings": settings, "plan": None, "lang": i18n.text()}
    save(proj)
    return proj


# What a branch does not take: the videos built from the shots (a branch builds its own), the exports
BRANCH_SKIP_DIRS = {"resolve", "_post"}
BRANCH_SKIP = re.compile(r"^video_.*\.mp4$")


def branch(src: dict, name: str = "") -> dict:
    """«Ветка»: a copy of a storyboard to try another take, model or edit without losing this
    one. Its shots are the source's, hard-linked (no space, nothing shot again; another disk - copied), its photos and
    track copied; the built videos are not taken. It remembers where it came from (`branch_of`) - the storyboard says what differs."""
    pid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    s, d = folder(src["id"]), folder(pid)
    d.mkdir(parents=True)
    for f in s.rglob("*"):
        rel = f.relative_to(s)
        if f.is_dir() or rel.parts[0] in BRANCH_SKIP_DIRS or (len(rel.parts) == 1 and (f.name == "project.json" or BRANCH_SKIP.match(f.name))):
            continue
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        # hard links only to what is never written again: the shots and the files under a folder (each a new name). A
        # photo, the track, a cache file (_frames.json, _peaks) can be written over in place - through a link that would
        # change the source's too, so those are copied
        if len(rel.parts) > 1 and not any(p.startswith("_") for p in rel.parts):
            try:
                os.link(f, d / rel)
                continue
            except OSError:
                pass
        shutil.copy2(f, d / rel)
    proj = json.loads(json.dumps(src))
    proj.pop("renders", None)
    now = time.time()
    proj.update(id=pid, created=now, name=name or i18n.L(f"{src.get('name') or 'Ролик'} · ветка", f"{src.get('name') or 'Video'} · branch"),
                branch_of={"id": src["id"], "name": src.get("name") or "", "at": now})
    return save(proj)


def branch_diff(proj: dict) -> Optional[dict]:
    """A branch against its source: the scenes whose shot would differ (their prompt, seed, takes, model, start, own
    LoRA...), the ones only here or only there (by their id), the settings that differ. None - not a branch."""
    b = proj.get("branch_of")
    if not b:
        return None
    try:
        src = load(b["id"])
    except NotFound:
        return {"id": b["id"], "name": b.get("name", ""), "gone": True}
    mine = {s.get("id"): s for s in (proj.get("plan") or {}).get("scenes") or []}
    theirs = {s.get("id"): s for s in (src.get("plan") or {}).get("scenes") or []}
    keys = ("prompt", "seed", "takes", "model", "seconds", "kind", "from", "start_photo", "end_photo", "loras", "facefix")
    changed = [s["index"] + 1 for i, s in mine.items() if i in theirs and any(s.get(k) != theirs[i].get(k) for k in keys)]
    st, st0 = proj.get("settings") or {}, src.get("settings") or {}
    return {"id": b["id"], "name": src.get("name") or b.get("name", ""), "gone": False, "changed": changed,
            "added": [s["index"] + 1 for i, s in mine.items() if i not in theirs],
            "removed": len([i for i in theirs if i not in mine]),
            "settings": sorted(k for k in set(st) | set(st0) if st.get(k) != st0.get(k)),
            "edit": proj.get("edit") != src.get("edit")}


def load(pid: str) -> dict:
    try:
        return json.loads((folder(pid) / "project.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise NotFound(pid) from e


def save(proj: dict) -> dict:
    proj["updated"] = time.time()
    plan = proj.get("plan")
    if plan and not proj.get("name"):
        proj["name"] = plan.get("title_ru") or plan.get("idea", "")[:40]
    path = folder(proj["id"]) / "project.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(proj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)   # never a half-written project
    return proj


def remove(pid: str) -> None:
    shutil.rmtree(folder(pid), ignore_errors=True)


def put_photo(pid: str, src: Path) -> str:
    """The hero's photo copied into the project (the input folder of ComfyUI is shared scratch)."""
    name = "hero" + src.suffix.lower()
    shutil.copyfile(src, folder(pid) / name)
    return name


def photo_path(proj: dict) -> Optional[Path]:
    name = (proj.get("settings") or {}).get("photo")
    return folder(proj["id"]) / name if name else None


def used_files(proj: dict) -> set[str]:
    """The project's own files its storyboard points at: the hero's photo, the cast's photos, tries and voices, the
    places' pictures, the scenes' first and last frames, the clip's singer. One file is often several of these (a
    drawn singer is character 1's photo, the clip's and every singing scene's start) - a file goes only when none is
    left."""
    plan, st = proj.get("plan") or {}, proj.get("settings") or {}
    cast = plan.get("cast") or []
    used = {st.get("photo"), (plan.get("clip") or {}).get("photo")}
    used |= {c.get("photo") for c in cast} | {(c.get("voice") or {}).get("file") for c in cast}
    used |= {x.get("file") for c in cast for x in c.get("tries") or []}
    used |= {x.get("photo") for x in plan.get("places") or []}
    used |= {s.get(k) for s in plan.get("scenes") or [] for k in ("start_photo", "end_photo")}
    return used - {None, ""}


def drop_unused(proj: dict, name: Optional[str]) -> None:
    """A file the storyboard no longer points at (used_files), removed from the project's folder."""
    if name and Path(name).name == name and name not in used_files(proj):
        (folder(proj["id"]) / name).unlink(missing_ok=True)


def summary(proj: dict) -> dict:
    if proj.get("type") == "graph":
        return _graph_summary(proj)
    plan = proj.get("plan") or {}
    scenes = plan.get("scenes") or []
    s = proj.get("settings") or {}
    clip = plan.get("clip") or {}
    return {"id": proj["id"], "name": proj.get("name") or i18n.L("Без названия", "Untitled"), "created": proj.get("created"),
            "updated": proj.get("updated"), "scenes": len(scenes), "seconds": plan.get("seconds") or s.get("seconds"),
            "mode": plan.get("mode") or s.get("mode"), "aspect": s.get("aspect"), "quality": s.get("quality"),
            "checks": sum(1 for x in scenes if x.get("status") == "check"), "written": bool(scenes) and all(prompts.is_written(x) for x in scenes),
            "manual": bool(plan.get("manual")),
            "kind": "clip" if clip else "manual" if plan.get("manual") else "board",
            "source": "remiqora" if clip.get("imported") else None, "models": _models(plan, s),
            "photo": f"/api/projects/{proj['id']}/photo" if s.get("photo") else None, **_shot_info(proj)}


def _base_model(m: Optional[str]) -> str:
    """A model as the shelf names it: an imported one (rq_ltx23: shot in Remiqora) is its version of ours."""
    m = m or "h3"
    return m[3:] if m.startswith("rq_") else m


def _models(plan: dict, settings: dict) -> list[dict]:
    """Which models shoot the video and how many of its scenes each: [{id, n}], the most first. A scene's model is its
    chain's (the `model` of the new scene that opened it), else the video's (render.scene_card, without importing it).
    The chain is followed by the scenes' places in the list, not their `index`, so a half-written plan still counts."""
    count: dict[str, int] = {}
    scenes = plan.get("scenes") or []
    head_of: list[dict] = []
    for i, x in enumerate(scenes):
        head = x
        if x.get("kind") == "continue" and i:
            src = next((j for j in range(i) if x.get("from") and scenes[j].get("id") == x["from"]), i - 1)
            head = head_of[src]
        head_of.append(head)
        m = _base_model(head.get("model") or settings.get("video_model"))
        count[m] = count.get(m, 0) + 1
    if not count:
        count[_base_model(settings.get("video_model"))] = 0
    return [{"id": k, "n": v} for k, v in sorted(count.items(), key=lambda kv: -kv[1])]


def _graph_summary(proj: dict) -> dict:
    """A graph project's card: its scene nodes, a frame of its newest shot, whether an output was made."""
    f = folder(proj["id"])
    try:
        g = json.loads((f / "graph.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        g = {"nodes": []}
    s = proj.get("settings") or {}
    scenes = [x for x in g.get("nodes", []) if x.get("type") == "scene"]
    n = len(scenes)
    secs = 0
    for x in scenes:   # a scene's own length (graph.seconds_of: 3-15, 5 when it says nothing)
        try:
            secs += max(3, min(15, int((x.get("data") or {}).get("seconds") or grid.SCENE_SECONDS)))
        except (TypeError, ValueError):
            secs += grid.SCENE_SECONDS
    pngs = sorted((f / "scenes").glob("*.png"), key=lambda p: p.stat().st_mtime) if (f / "scenes").exists() else []
    outs = [p for p in (f / "out").glob("*.mp4") if not p.name.startswith(("join_", "music_"))] if (f / "out").exists() else []
    poster = f"/api/projects/{proj['id']}/files/scenes/{pngs[-1].name}" if pngs else None
    for src in ([] if poster else s.get("cache_from") or []):   # a copy of a storyboard shoots from its cache: its frame
        try:
            poster = _shot_info(json.loads((folder(src) / "project.json").read_text(encoding="utf-8")))["poster"]
        except (OSError, ValueError, KeyError):
            continue
        if poster:
            break
    return {"id": proj["id"], "type": "graph", "name": proj.get("name") or i18n.L("Граф", "Graph"), "created": proj.get("created"),
            "updated": proj.get("updated"), "scenes": n, "seconds": secs, "mode": None,
            "aspect": s.get("aspect"), "quality": s.get("quality"), "checks": 0, "written": True, "manual": False, "photo": None,
            "kind": "graph", "source": None, "models": [{"id": _base_model(s.get("video_model")), "n": n}],
            "poster": poster, "video": i18n.L("граф", "graph") if outs else None}


def _shot_info(proj: dict) -> dict:
    """For the video's card: a frame of its newest render and whether the video is assembled (and in what size)."""
    renders = sorted((proj.get("renders") or {}).values(), key=lambda r: r.get("finished") or 0, reverse=True)
    if not renders:
        return {"poster": None, "video": None}
    r = renders[0]
    shot = r["shots"][len(r["shots"]) // 2] if r.get("shots") else None
    return {"poster": f"/api/projects/{proj['id']}/files/{shot['png']}" if shot else None,
            "video": _out_label(r) if r.get("video") else None}


def _out_label(r: dict) -> str:
    """video_draft_4k_hdr_48fps -> "4K · HDR10 · 48 fps"; a render without RTX -> its own width."""
    tag = r.get("out_tag") if "out_tag" in r else ("1080p" if r.get("video_up") else None)
    if not tag or not r.get("video_up"):
        return str(r.get("width"))
    names = {"1080p": "1080p", "4k": "4K", "hdr": "HDR10", "48fps": "48 fps"}
    return " · ".join(names.get(p, p) for p in tag.split("_"))


def all_projects() -> list[dict]:
    out = []
    for f in ROOT.glob("*/project.json"):
        try:
            out.append(summary(json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda p: p["updated"] or 0, reverse=True)


def apply_grid(plan: dict) -> None:
    if plan.get("scene_seconds") and not plan.get("clip"):   # a 10 s grid: a scene added by hand is that long too
        for s in plan["scenes"]:
            if not s.get("seconds"):
                s["seconds"] = plan["scene_seconds"]
    plan["grid_warnings"] = grid.renumber(plan["scenes"], plan["mode"])
    secs = round(sum(grid.seconds_of(s) for s in plan["scenes"]), 3)
    plan["seconds"] = int(secs) if secs == int(secs) else secs
