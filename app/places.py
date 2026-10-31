"""«Места»: a picture of each place of the video, the second reference of a scene's start frame (frames.py). Without
it FLUX.2 Klein draws «the same» flat from the words anew on every scene, and the place jumps from cut to cut; with it
every scene of that place is the same room, street or roof, seen from its own camera - the way comfyui-vrgamedevgirl's
Video Builder maps a location reference to its scenes.

`plan.places`: [{id, name_ru, en, photo?, drawn?}] - the writer groups the new scenes' place_en into a few places
(«Собрать места», an LLM job), the user can fix the grouping and the texts; `scene.place` = a place's id (a new scene
only - a continuation is in its chain's place). The picture: Krea 2 from the place's words, empty of people, or the
user's own photo. Neither touches a shot's key: only a frame drawn from it does (its file is the scene's start photo).
"""
from __future__ import annotations

import random
import time
import uuid
from typing import Optional

from . import i18n, jobs, picture, projects, render
from .engine.comfy import EngineError
from .planner import check

MAX = 6
PREFIX = "place_"   # our pictures in the project folder: place_<place id>_<seed>.png


def by_id(plan: dict, pid: Optional[str]) -> Optional[dict]:
    return next((x for x in plan.get("places") or [] if x.get("id") == pid), None) if pid else None


def of_scene(plan: dict, s: dict) -> Optional[dict]:
    """The scene's place (a new scene's own)."""
    return by_id(plan, s.get("place")) if s.get("kind") == "new" else None


def tidy(plan: dict) -> None:
    """check.plan's part: places with an id and texts, scenes pointing at none that is gone."""
    places = [x for x in plan.get("places") or [] if isinstance(x, dict)]
    for x in places:
        x["id"] = str(x.get("id") or uuid.uuid4().hex[:8])
        x["name_ru"], x["en"] = str(x.get("name_ru") or "").strip()[:80], str(x.get("en") or "").strip()[:500]
    if places:
        plan["places"] = places
    else:
        plan.pop("places", None)
    ids = {x["id"] for x in places}
    for s in plan.get("scenes") or []:
        if s.get("place") and (s["place"] not in ids or s.get("kind") != "new"):
            s.pop("place")


# ---------- «Собрать места»: the writer groups the scenes' places ----------
SYSTEM = """You are the production designer of a video. The storyboard's scenes each say where they happen in one sentence, often mixed with the camera or the action. Group the scenes into the few real LOCATIONS the video is shot in: one location is one set the camera returns to (the same flat, the same street, the same rooftop), whatever the angle or the moment.

For each location write:
- name_ru: its short name, 1-4 words in Russian (e.g. «Квартира ночью», «Мост под дождём»).
- en: one English sentence, 15-40 words, describing the location itself as an empty set: the kind of place, the architecture and materials, the colors, the light and the time of day. No people, no action, no camera words (no "close-up", "wide shot", "tracking").
- scenes: the numbers of the scenes shot there.

Use 2 to 6 locations - fewer is better: two scenes in the same café, at the door and at the table, are one location. A close-up of an object, a hand or a face is not a location: it goes into the location where it happens (the nearest one in the story when the scene does not say). Every scene listed goes into exactly one location."""


def _ask(plan: dict) -> tuple[str, dict, list[int]]:
    new = [s["index"] for s in plan["scenes"] if s.get("kind") == "new"]
    lines = "\n".join(f"scene {i + 1}: {(plan['scenes'][i].get('place_en') or '').strip() or '(no place said)'}"
                      + (f" - {' '.join(plan['scenes'][i].get('beats_en') or [])[:160]}" if plan["scenes"][i].get("beats_en") else "")
                      for i in new)
    world = (plan.get("world") or {}).get("en") or ""
    user = (f"The video's look: {(plan.get('style_en') or '').strip()}\n" + (f"Its world: {world}\n" if world else "")
            + f"\nThe scenes, each with where it happens (and what happens):\n{lines}\n\nGroup them into locations.")
    schema = {"type": "object", "properties": {"places": {"type": "array", "minItems": 1, "maxItems": MAX, "items": {
        "type": "object", "properties": {"name_ru": {"type": "string", "maxLength": 80}, "en": {"type": "string", "maxLength": 500},
                                         "scenes": {"type": "array", "items": {"type": "integer"}}},
        "required": ["name_ru", "en", "scenes"], "additionalProperties": False}}},
        "required": ["places"], "additionalProperties": False}
    return user, schema, new


def _apply(plan: dict, got: list[dict], new: list[int]) -> None:
    """The writer's answer onto the plan. A place keeps its picture when it keeps its id: a regroup matches the old
    places by name. A scene left out stays without a place (its frame is drawn from words, as before)."""
    old = {x.get("name_ru", "").lower(): x for x in plan.get("places") or []}
    places, seen = [], set()
    for g in got[:MAX]:
        en, name = str(g.get("en") or "").strip(), str(g.get("name_ru") or "").strip()
        nums = [int(n) - 1 for n in g.get("scenes") or [] if str(n).lstrip("-").isdigit()]
        mine = [i for i in nums if i in new and i not in seen]
        if not en or not mine:
            continue
        keep = old.get(name.lower())
        x = {**(keep or {}), "id": (keep or {}).get("id") or uuid.uuid4().hex[:8], "name_ru": name or en[:40], "en": en}
        places.append(x)
        for i in mine:
            seen.add(i)
            plan["scenes"][i]["place"] = x["id"]
    for i in new:
        if i not in seen:
            plan["scenes"][i].pop("place", None)
    plan["places"] = places


async def group(pid: str, seed: Optional[int] = None) -> dict:
    """«Собрать места»: the writer groups the new scenes into places. -> the project. The pictures of places that are
    gone are thrown away."""
    from .llm import client
    proj = projects.load(pid)
    plan = proj.get("plan") or {}
    if not any(s.get("kind") == "new" for s in plan.get("scenes") or []):
        raise EngineError(i18n.L("В ролике нет новых сцен", "The video has no new scenes"))
    client.use_lang(i18n.plan_lang_name(plan))
    user, schema, new = _ask(plan)
    t0 = time.time()
    async with client.session(plan.get("model")) as llm:
        # a small model thinks before it answers (writer.propagate's budget): the tokens hold both
        d = await llm.chat_json(SYSTEM, user, schema, temperature=0.3, seed=seed or int(time.time()) % 100000, max_tokens=3000)
    cur = projects.load(pid)   # the user may have edited meanwhile: only the places go in
    p = cur["plan"]
    before = {x.get("photo") for x in p.get("places") or [] if x.get("drawn")}
    _apply(p, d.get("places") or [], [s["index"] for s in p["scenes"] if s.get("kind") == "new"])
    if not p["places"]:
        raise EngineError(i18n.L("Сценарист не собрал места — попробуйте ещё раз", "The writer gathered no places - try again"))
    kept = {x.get("photo") for x in p["places"]}
    for f in before - kept:
        if f:
            (projects.folder(pid) / f).unlink(missing_ok=True)
    p["places_by"] = {"model": llm.model.name, "seconds": round(time.time() - t0, 1)}
    cur["plan"] = check.plan(p)
    return projects.save(cur)


def assign(plan: dict, s: dict, place: Optional[str]) -> None:
    """A scene put in a place by hand (None: none)."""
    if place and by_id(plan, place) and s.get("kind") == "new":
        s["place"] = place
    else:
        s.pop("place", None)


# ---------- the picture of a place ----------
def prompt_of(plan: dict, x: dict) -> str:
    """Krea's prompt: the place as an empty set, seen whole - the reference every scene's frame takes its walls,
    materials and light from. Not the video's style: it often dresses the hero («deep blue velvet, embroidery») and Krea
    paints her into the place (2026-10-29, three places of three); the place's words carry its light and colors, and
    the frame gets the style from its own prompt."""
    return (f"Photorealistic cinematic establishing shot of an empty location with nobody in it: {x['en'].rstrip('.')}. "
            "Wide shot at eye level, deep focus, the whole place and its light readable. "
            "No people, no person, no figure, no clothing, no animals, no text, no watermark.")


def scenes_of(plan: dict, place: str) -> list[int]:
    return [s["index"] for s in plan.get("scenes") or [] if s.get("place") == place and s.get("kind") == "new"]


def drop_photo(pid: str, x: dict) -> None:
    if x.get("photo"):
        (projects.folder(pid) / x["photo"]).unlink(missing_ok=True)
    x.pop("photo", None)
    x.pop("drawn", None)


async def draw(job: jobs.Job, pid: str, ids: Optional[list[str]] = None, seed: Optional[int] = None) -> dict:
    """The pictures of places `ids` (None: every place without one) by Krea 2, one model load; the project is saved
    after each. -> {done: [ids]}"""
    proj = projects.load(pid)
    plan = proj.get("plan") or {}
    todo = [x["id"] for x in plan.get("places") or [] if (x["id"] in ids if ids is not None else not x.get("photo"))]
    if not todo:
        raise EngineError(i18n.L("Нет мест, которым нужна картинка", "No place needs a picture"))
    w, h = render.picture_size(proj["settings"])
    job.progress.update(total=len(todo), done=0, stage="places")
    done = []
    for n, xid in enumerate(todo):
        cur = projects.load(pid)
        x = by_id(cur["plan"], xid)
        if not x or not x.get("en"):
            continue
        sd = seed if seed is not None else random.randrange(1, 2**31 - 1)
        name = f"{PREFIX}{xid}_{sd}.png"
        await picture.generate(job, prompt_of(cur["plan"], x), sd, w, h, projects.folder(pid) / name, picture.project_loras(cur["settings"], "krea"))
        cur = projects.load(pid)
        x = by_id(cur["plan"], xid)
        if not x:   # gone meanwhile
            (projects.folder(pid) / name).unlink(missing_ok=True)
            continue
        if x.get("drawn") or (x.get("photo") or "").startswith(PREFIX):
            drop_photo(pid, x)
        x.update(photo=name, drawn=True, seed=sd)
        x.pop("stale", None)   # drawn from its words as they are now
        projects.save(cur)
        done.append(xid)
        job.progress.update(done=n + 1)
    return {"done": done}


def estimate(n: int) -> float:
    """Krea's start and ~4 s a picture (picture.generate)."""
    return 15 + 5 * n
