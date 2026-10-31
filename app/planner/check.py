"""A storyboard after any edit: the grid, the prompts and the validator again (code only, no LLM).
Every place that changes a plan - the writer's job, a hand edit, a photo, a start frame - and the graph (phase 9),
whose Сценарист node holds a plan of its own, goes through plan()."""
from __future__ import annotations

import random
from pathlib import Path

from .. import projects
from ..llm import writer
from . import prompts


def _bare(x: dict, key: str) -> None:
    """A file name the project keeps (a photo, a frame): a bare name inside the project's folder, else dropped."""
    v = x.get(key)
    if v is not None and (not isinstance(v, str) or not v or Path(v).name != v or v in (".", "..")):
        x.pop(key)


def plan(p: dict) -> dict:
    from .. import edit, places, videomodels
    for c in p.get("cast") or []:   # the files the plan points at, before anything deletes or reads them
        _bare(c, "photo")
        c["tries"] = [t for t in c.get("tries") or [] if isinstance(t, dict) and isinstance(t.get("file"), str) and Path(t["file"]).name == t["file"]]
        if not c["tries"]:
            c.pop("tries")
    for x in p.get("places") or []:
        _bare(x, "photo")
    for s in p.get("scenes") or []:
        _bare(s, "start_photo")
        _bare(s, "end_photo")
    if isinstance(p.get("clip"), dict):
        _bare(p["clip"], "photo")
    edit.ensure_ids(p)   # the montage points at scenes by id (phase 8)
    places.tidy(p)       # «Места»: a scene points at a place that is there
    for s in p.get("scenes") or []:   # a scene's own model (phase 11): a known one, on the scene that opens a chain
        if s.get("model") not in videomodels.CARDS or s.get("kind") == "continue":
            s.pop("model", None)
    projects.apply_grid(p)
    if p["mode"] != "none":
        prompts.fix_cast(p)   # an age edited by hand goes into "a 35-year-old ..." (a no-op on looks already fixed)
    writer.check(p)
    for s in p["scenes"]:
        s["status"] = "check" if s["problems"] else "ok"
        if not s.get("seed"):   # a scene keeps its seed: the final is shot with the draft's seeds
            s["seed"] = random.randrange(1, 2**31)
        if s.get("takes"):   # the takes («Ещё дубль»): seeds, the chosen one (`seed`) among them
            s["takes"] = list(dict.fromkeys(int(x) for x in s["takes"] if str(x).lstrip("-").isdigit()))
            if s["seed"] not in s["takes"]:
                s["takes"].append(s["seed"])
            if len(s["takes"]) < 2:
                s.pop("takes")
        if s.get("loras") is not None and not isinstance(s["loras"], list):
            s.pop("loras")   # a scene's own LoRA: a list ([] = none); anything else - the video's
        if "facefix" in s:   # «Починить лица» (facefix.py): {mode, strength} or nothing
            ff = s["facefix"]
            from .. import facefix
            if not isinstance(ff, dict) or ff.get("mode", "far") not in facefix.MODES:
                s.pop("facefix")
            else:
                s["facefix"] = {"mode": ff.get("mode", "far"), "strength": round(min(1.0, max(0.0, float(ff.get("strength", 1.0)))), 2)}
    return p
