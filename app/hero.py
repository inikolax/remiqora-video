"""Phase 11: a hero without a photo gets one drawn - Krea 2 paints the character from their storyboard description (the
look, the outfit, the video's style), and the picture becomes the character's photo: Ref2VA holds the face from it on H3,
and in a clip the singing scenes start from it (LTX holds no face from words: without a photo every singing scene drew
another face). «Нарисовать по описанию» on the hero card; a clip without a singer's photo draws one itself.

The hero tab's casting: «Ещё 4 пробы» draws several tries in one job (Krea loads once), each kept in cast[i].tries with
its seed and how many faces the detector found on it (two people in a try - Krea drew a second figure at times); one
try is approved as the photo (pick), the rest stay to come back to. «Поправить черты» (adjust) changes features
(«моложе», «волосы короче», the user's own words) with the face kept: FLUX.2 Klein edits the approved picture, or Krea
draws on its seed; approving such a try writes the change into the look. «Нарисовать по описанию» (redraw) puts an
edited look into English and draws new faces. faces() says how close each shot scene's face is to the photo (SFace).
"""
from __future__ import annotations

import random
import re
import uuid

from . import jobs, picture, projects, render
from .engine.comfy import EngineError
from .planner import check
from . import i18n


def who_of(c: dict) -> str:
    """Who the portrait shows, said outright: Krea follows a look's anatomy («lean build, high cheekbones») to a man's
    face whatever the «woman» in it (2026-10-29, three heroines in a row), and the user wants feminine, beautiful women."""
    young = int(c.get("age") or 30) < 36
    if c.get("gender") == "female":
        return f"one beautiful {'young ' if young else ''}woman with a soft, delicate, clearly feminine face"
    if c.get("gender") == "male":
        return f"one handsome {'young ' if young else ''}man with a clearly masculine face"
    return "one person"


def prompt_of(plan: dict, i: int) -> str:
    """Krea's prompt for character i: a photo of them alone, facing the camera, in the video's look and the place of
    their first scene."""
    c = (plan.get("cast") or [])[i]
    place = next((s.get("place_en") for s in plan.get("scenes") or [] if s.get("place_en") and (i + 1) in (s.get("who") or [1])), "")
    style = (plan.get("style_en") or "").strip().rstrip(".")
    outfit = re.sub(r"^\s*(wearing|dressed in)\s+", "", (c.get("outfit_en") or "").strip(), flags=re.I).rstrip(".")
    return " ".join(x for x in (
        f"{style}." if style else "",
        f"A medium close-up photo of {who_of(c)}, facing the camera: {c.get('en', '').strip().rstrip('.')}.",
        f"Wearing {outfit}." if outfit else "",
        f"Behind them: {place.strip().rstrip('.')}." if place else "",
        "Natural light on the face, sharp focus on the eyes, neutral expression. Only this one person in the picture. "
        "No text, no watermark.") if x)


# the features a try changes («Поправить черты»): (ru, en) - en goes into the tries' prompt and, approved, after the look;
# the light is the try's only (LIGHT)
TWEAKS = {
    "younger": ("моложе", "Looks a few years younger."),
    "older": ("старше", "Looks a few years older."),
    "shorter": ("волосы короче", "Shorter hair, shoulder length."),
    "longer": ("волосы длиннее", "Longer hair, well past the shoulders."),
    "lighter": ("волосы светлее", "Lighter hair colour."),
    "curly": ("кудрявые волосы", "Curly hair."),
    "smile": ("улыбается", "A warm, gentle smile."),
    "makeup": ("ярче макияж", "Bolder makeup."),
    "softer": ("мягче черты лица", "Softer, more delicate facial features."),
    "warm": ("теплее свет", "Warm golden light."),
    "studio": ("студийный свет", "Soft, even studio light."),
}
LIGHT = {"warm", "studio"}
CHANGE_SYSTEM = """You turn a user's short change to a person's look into one short English sentence for an image model:
concrete visual words about the person only (hair, face, makeup, body, clothes), no names, no feelings."""


def _set_photo(p: dict, i: int, name: str) -> None:
    """Character i's photo is `name` now (drawn by Krea); in a clip, character 1's is the singer's photo too (clip.photo,
    the singing scenes start from it)."""
    c = p["cast"][i]
    old = c.get("photo")
    c.update(photo=name, drawn=True)
    c.pop("photo_stale", None)   # the picture is the look as it is now
    clip = p.get("clip")
    if clip and i == 0 and (not clip.get("photo") or clip.get("photo") == old):
        from .llm import writer
        clip["photo"] = name
        p["ref_photo"] = True   # the face holds on H3 too: without this the scenes not started from the photo drew another one
        for s in p["scenes"]:
            if s.get("start_photo") == old and old:
                s.pop("start_photo")
            writer.clip_shot(p, s, s.get("shot"))


def faces_on(path) -> int:
    """How many confident faces the detector finds on a picture (-1: it could not tell)."""
    try:
        import cv2
        from . import checks
        img = cv2.imread(str(path))
        return len(checks._confident_faces(img)) if img is not None else -1
    except Exception:  # noqa: BLE001 - a check is a bonus, never a blocker
        return -1


async def tries(job: jobs.Job, pid: str, i: int, n: int = 4, tweak: str | None = None) -> dict:
    """n tries of character i into cast[i].tries ({file, seed, faces, tweak}); the photo stays as it is. With a tweak
    the tries go on the approved one's seed (and the seeds next to it) with the tweak's phrase. -> the project."""
    proj = projects.load(pid)
    plan = proj.get("plan") or {}
    cast = plan.get("cast") or []
    if not 0 <= i < len(cast):
        raise EngineError(i18n.L("Нет такого героя", "No such hero"))
    if not (cast[i].get("en") or "").strip():
        raise EngineError(i18n.L("У героя нет описания внешности: опишите его и обновите промт", "The hero has no look description: describe it and update the prompt"))
    prompt = prompt_of(plan, i)
    if tweak:
        prompt = prompt.replace(" Natural light", f" {TWEAKS[tweak][1]} Natural light", 1)
        if tweak == "smile":
            prompt = prompt.replace(", neutral expression", "", 1)
    base = cast[i].get("seed") if tweak else None
    w, h = render.picture_size(proj["settings"])
    folder = projects.folder(pid)
    for k in range(n):
        seed = base + k if base else random.randrange(1, 2**31 - 1)
        name = f"cast_{uuid.uuid4().hex[:8]}.png"
        job.progress["stage"] = "drawing"
        job.progress["message"] = i18n.L(f"проба {k + 1} из {n}", f"try {k + 1} of {n}")
        await picture.generate(job, prompt, seed, w, h, folder / name, picture.project_loras(proj["settings"], "krea"))
        cur = projects.load(pid)   # the user may have edited meanwhile: only the try goes in
        if i >= len(cur["plan"].get("cast") or []):   # the hero was removed meanwhile
            (folder / name).unlink(missing_ok=True)
            return cur
        c = cur["plan"]["cast"][i]
        c.setdefault("tries", []).append({"file": name, "seed": seed, "faces": faces_on(folder / name), **({"tweak": tweak} if tweak else {})})
        proj = projects.save(cur)
    return proj


def pick(proj: dict, i: int, name: str) -> None:
    """Approve a try as character i's photo; a tweaked try writes its phrase into the look (ru and en)."""
    p = proj["plan"]
    c = p["cast"][i]
    t = next((x for x in c.get("tries") or [] if x["file"] == name), None)
    if t is None:
        raise EngineError(i18n.L("Нет такой пробы", "No such try"))
    old = c.get("photo")
    if old and c.get("drawn") and not any(x["file"] == old for x in c.get("tries") or []):
        c.setdefault("tries", []).insert(0, {"file": old, "seed": c.get("seed"), "faces": -1})   # the photo before stays a try
    ru, en = change_of(t)
    if ru:
        c["ru"] = f"{(c.get('ru') or '').rstrip().rstrip('.')}, {ru}."
    if en:
        c["en"] = f"{(c.get('en') or '').rstrip()} {en}"
    _set_photo(p, i, name)
    c["seed"] = t.get("seed")


def change_of(t: dict) -> tuple[str, str]:
    """What approving a try writes into the look: its features (not the light) and the user's own change, (ru, en)."""
    keys = [k for k in (t.get("tweaks") or ([t["tweak"]] if t.get("tweak") else [])) if k in TWEAKS and k not in LIGHT]
    ru = ", ".join([TWEAKS[k][0] for k in keys] + ([t["change_ru"].strip().rstrip(".")] if t.get("change_ru") else []))
    own = (t.get("change_en") or "").strip().rstrip(".")
    en = " ".join([TWEAKS[k][1] for k in keys] + ([f"{own[:1].upper()}{own[1:]}."] if own else []))
    return ru, en


def portrait_path(proj: dict, i: int):
    """Character i's approved picture on disk: their photo, or the project's photo for the hero described from it."""
    c = proj["plan"]["cast"][i]
    path = projects.folder(proj["id"]) / c["photo"] if c.get("photo") else projects.photo_path(proj) if c.get("from_photo") else None
    return path if path and path.exists() else None


async def adjust(job: jobs.Job, pid: str, i: int, keys: list[str], text: str = "", n: int = 2) -> dict:
    """«Поправить черты»: n tries of character i with these features changed and the face kept. FLUX.2 Klein edits the
    approved picture itself (an own photo too); without FLUX.2, Krea draws on the approved try's seed. The user's own
    change (`text`, the video's language) is put into English by the writer first. -> the project."""
    from . import picture
    proj = projects.load(pid)
    plan = proj.get("plan") or {}
    if not 0 <= i < len(plan.get("cast") or []):
        raise EngineError(i18n.L("Нет такого героя", "No such hero"))
    src = portrait_path(proj, i)
    if not src:
        raise EngineError(i18n.L("Сначала нужен портрет героя", "The hero needs a portrait first"))
    text_en = ""
    if text.strip():
        from .llm import client as llm
        job.progress["message"] = i18n.L("сценарист переводит правку", "the writer translates the change")
        llm.use_lang(i18n.plan_lang_name(plan))
        schema = {"type": "object", "properties": {"en": {"type": "string"}}, "required": ["en"], "additionalProperties": False}
        async with llm.session(plan.get("model")) as cl:
            d = await cl.chat_json(CHANGE_SYSTEM, f"The change ({llm.lang()}): {text.strip()}", schema, temperature=0.2, seed=1, max_tokens=200)
        text_en = str(d.get("en", "")).strip()
    change = " ".join([TWEAKS[k][1] for k in keys] + ([text_en] if text_en else []))
    flux = picture.edit_problem() is None
    seed0 = plan["cast"][i].get("seed")
    w, h = render.picture_size(proj["settings"])
    folder = projects.folder(pid)
    for k in range(n):
        seed = random.randrange(1, 2**31 - 1) if flux or not seed0 else seed0 + k
        name = f"cast_{uuid.uuid4().hex[:8]}.png"
        job.progress["stage"] = "drawing"
        job.progress["message"] = i18n.L(f"проба {k + 1} из {n}", f"try {k + 1} of {n}")
        if flux:
            await picture.edit(job, "The same person as in the first image: exactly the same face, identity and skin tone, the same "
                               f"framing, pose and background. Change only this: {change} Photorealistic portrait, sharp focus on the eyes. "
                               "No text, no watermark.", [src], seed, w, h, folder / name, picture.project_loras(proj["settings"], "flux2"))
        else:
            prompt = prompt_of(plan, i).replace(" Natural light", f" {change} Natural light", 1)
            await picture.generate(job, prompt, seed, w, h, folder / name, picture.project_loras(proj["settings"], "krea"))
        cur = projects.load(pid)
        if i >= len(cur["plan"].get("cast") or []):   # the hero was removed meanwhile
            (folder / name).unlink(missing_ok=True)
            return cur
        cur["plan"]["cast"][i].setdefault("tries", []).append(
            {"file": name, "seed": seed, "faces": faces_on(folder / name), "tweaks": keys, "edit": flux,
             **({"change_ru": text.strip(), "change_en": text_en} if text_en else {})})
        proj = projects.save(cur)
    return proj


async def redraw(job: jobs.Job, pid: str, i: int, n: int = 4) -> dict:
    """«Нарисовать по описанию» / «Новые лица по этому описанию»: the look edited in words goes into English first (the
    writer, only when it changed), then Krea draws n new faces from it. -> the project."""
    proj = projects.load(pid)
    cast = (proj.get("plan") or {}).get("cast") or []
    if not 0 <= i < len(cast):
        raise EngineError(i18n.L("Нет такого героя", "No such hero"))
    if cast[i].get("ru_dirty"):
        from .llm import writer
        job.progress["message"] = i18n.L("сценарист переводит описание", "the writer translates the look")
        p = await writer.rewrite_looks(proj["plan"], [i])
        cur = projects.load(pid)   # only this hero's English goes in
        if i < len(cur["plan"].get("cast") or []):
            c, got = cur["plan"]["cast"][i], p["cast"][i]
            c.update(en=got.get("en", c.get("en")), outfit_en=got.get("outfit_en", c.get("outfit_en")), ru_dirty=False)
            cur["plan"] = check.plan(cur["plan"])
            projects.save(cur)
    return await tries(job, pid, i, n)


def faces(proj: dict, i: int) -> list[dict]:
    """How close the face on each shot scene of character i is to their photo: [{index, sim}] (sim None - no single
    face to judge on the scene's last frame)."""
    from . import frames
    p = proj["plan"]
    c = p["cast"][i]
    if not c.get("photo"):
        return []
    folder = projects.folder(proj["id"])
    photo = folder / c["photo"]
    r = (proj.get("renders") or {}).get(proj["settings"].get("quality") or "draft") or {}
    # a render's shots by the scene's id (by its place for a render made before the ids: a deleted scene shifts those)
    shots = r.get("shots") or []
    by_id = {x["id"]: x.get("png") for x in shots if x.get("id")}
    by_index = {} if by_id else {x["index"]: x.get("png") for x in shots}
    several = p.get("mode") == "several"
    out = []
    for s in p["scenes"]:
        if several and (i + 1) not in (s.get("who") or []):
            continue
        png = by_id.get(render.sid(s)) if by_id else by_index.get(s["index"])
        if png and (folder / png).exists():
            sim = frames.similarity(folder / png, photo)
            out.append({"index": s["index"], "sim": None if sim is None else round(sim, 3)})
    return out


async def draw(job: jobs.Job, pid: str, i: int, seed: int | None = None) -> dict:
    """Character i's picture -> their photo (cast[i].photo, drawn: true); in a clip, character 1's is the singer's
    photo too (clip.photo, the singing scenes start from it). -> the project."""
    proj = projects.load(pid)
    plan = proj.get("plan") or {}
    cast = plan.get("cast") or []
    if not 0 <= i < len(cast):
        raise EngineError(i18n.L("Нет такого героя", "No such hero"))
    if not (cast[i].get("en") or "").strip():
        raise EngineError(i18n.L("У героя нет описания внешности: опишите его и обновите промт", "The hero has no look description: describe it and update the prompt"))
    w, h = render.picture_size(proj["settings"])
    name = f"cast_{uuid.uuid4().hex[:8]}.png"
    dest = projects.folder(pid) / name
    job.progress["stage"] = "drawing"
    await picture.generate(job, prompt_of(plan, i), seed if seed is not None else random.randrange(1, 2**31 - 1), w, h, dest,
                           picture.project_loras(proj["settings"], "krea"))
    cur = projects.load(pid)   # the user may have edited meanwhile: only the photo goes in
    p = cur["plan"]
    c = p["cast"][i]
    old = c.get("photo")
    if old and old != name and c.get("drawn") and not any(x["file"] == old for x in c.get("tries") or []):
        (projects.folder(pid) / old).unlink(missing_ok=True)
    _set_photo(p, i, name)
    cur["plan"] = check.plan(p)
    return projects.save(cur)
