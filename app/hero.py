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
from typing import Optional

from . import jobs, looks, picture, projects, render
from .engine.comfy import EngineError
from .planner import check, prompts
from . import i18n


def who_of(c: dict, plan: Optional[dict] = None) -> str:
    """Who the portrait shows, said outright: Krea follows a look's anatomy («lean build, high cheekbones») to a man's
    face whatever the «woman» in it (2026-10-29, three heroines in a row). A plan written since rules_v 2 (2026-11-03):
    the gender and age only - nothing about beauty, the cast's look decides."""
    if is_faceless(c):   # the beat clip's hero: the line is the preset's, the picture needs no «one man»
        return "one faceless figure"
    if prompts.is_nonperson(c):   # `kind` comes from a rules_v 4 writer or from the user in the hero card; the look starts with the species
        return f"one {prompts.kind_of(c)}"
    young = int(c.get("age") or 30) < 36
    if plan and int(plan.get("rules_v") or 0) >= 2:
        who = {"female": "woman", "male": "man"}.get(c.get("gender", ""))
        return f"one {'young ' if young else ''}{who}" if who else "one person"
    if c.get("gender") == "female":
        return f"one beautiful {'young ' if young else ''}woman with a soft, delicate, clearly feminine face"
    if c.get("gender") == "male":
        return f"one handsome {'young ' if young else ''}man with a clearly masculine face"
    return "one person"


LIGHT_OF = {"animal": "Soft natural light, sharp focus on the eyes.", "creature": "Soft natural light, sharp focus on the eyes.",
            "robot": "Soft even light, sharp focus on the details.", "faceless": "Dramatic light, sharp focus on the mask."}


# The beat clip's hero (kind "faceless"): a figure whose face is hidden for good - a mask, a
# visor, a hood - so no face drifts from shot to shot. Every picture of it carries the preset's line word for word (the
# hand-made clips' HERO lines: spec54, c55, c56). The face detector is OFF for it as for any non-person hero
# (prompts.is_nonperson: the kind is in KIND_KEEP); the picture check is the opposite one - a face found on it is a redraw
# (picture_checks.face_on_faceless). id: (Russian label, English label, the hero's line)
FACELESS_PRESETS = {
    "chrome": ("Хромовая маска", "Chrome mask",
               "a tall slim dancer wearing a seamless mirror-polished chrome full-face mask with no features at all, a smooth "
               "reflective chrome oval instead of a face, a black oversized hoodie with the hood up, black techwear cargo "
               "pants, black gloves"),
    "visor": ("Зеркальный визор", "Mirror visor helmet",
              "a motorcyclist in a black full-face helmet with a mirror-chrome visor that hides the face completely, a black "
              "leather riding jacket with thin white stripes on the sleeves, black gloves, black riding boots"),
    "porcelain": ("Белая фарфоровая маска", "White porcelain mask",
                  "a dancer wearing a seamless glossy white porcelain full-face mask with no features at all, a smooth white "
                  "oval instead of a face, a long flowing white coat, white gloves, white boots"),
    "hood": ("Капюшон в тени", "Hood in shadow",
             "a tall figure in a black oversized hoodie with the hood pulled low, the face in deep black shadow so that no "
             "face is visible at all, black techwear pants, black gloves"),
    "silhouette": ("Силуэт", "Silhouette",
                   "a tall dark silhouette of a person seen as a flat black shape against the light, no face and no features "
                   "visible at all, only the outline of the head and body"),
}
FACELESS_DEFAULT = "chrome"
# the same hero in a close-up / macro: the head only, no body (spec54 / c55 / c56's mask_macro words)
FACELESS_HEAD = {
    "chrome": "a seamless mirror-polished chrome full-face mask with no features, a smooth reflective chrome oval instead of a face, framed by a black hood",
    "visor": "a black full-face motorcycle helmet with a mirror-chrome visor that hides the face completely",
    "porcelain": "a seamless glossy white porcelain full-face mask with no features, a smooth white oval instead of a face",
    "hood": "a black hood pulled low over a face lost in deep black shadow, no face visible at all",
    "silhouette": "the black silhouette of a head against the light, no face and no features visible at all",
}


# «Свой герой» (the user describes the hero in their own words): what stands in until the writer has put the words into the
# hero's look - and what the code falls back to when the writer's line is empty or banned. {face hidden: (line, head line)}
OWN_FALLBACK = {
    True: ("a figure in a dark hooded coat, the face hidden in shadow",
           "a dark hood pulled low over a face lost in deep black shadow, no face visible at all"),
    False: ("a person in a long dark coat, black gloves and black boots",
            "a close-up of the head and shoulders of a person in a long dark hooded coat"),
}
# a preset's own words: at least one of them must stay in a line written for «preset + details» (the mask / helmet stays)
PRESET_KEEP = {"chrome": ("chrome",), "visor": ("visor", "helmet"), "porcelain": ("porcelain",), "hood": ("hood",),
               "silhouette": ("silhouette",)}


def hero_text(c: Optional[dict]) -> str:
    """The user's own words about the hero (the card's `desc`); empty = the preset as it is, today's way."""
    return str((c or {}).get("desc") or "").strip()


def is_own(c: Optional[dict]) -> bool:
    """«Свой герой»: no preset, the text alone is the hero."""
    return bool((c or {}).get("own"))


def face_hidden(c: Optional[dict]) -> bool:
    """Whether the hero's face is hidden (the faceless rules: the picture check, no face words). On unless the card says off."""
    return (c or {}).get("face_hidden") is not False


def own_card(text: str, hidden: bool = True) -> dict:
    """A «Герой» node's data for «Свой герой»: faceless kind, no preset, the user's words, the stand-in lines."""
    line, head = OWN_FALLBACK[bool(hidden)]
    return {"kind": "faceless", "preset": "", "own": True, "desc": text.strip(), "face_hidden": bool(hidden), "gender": "other", "age": 0,
            "en": line, "head_en": head, "ru": "Свой герой", "outfit_en": "", "outfit_ru": ""}


def faceless_head(c) -> str:
    """The hero's close-up line (the head only) for a card or a preset id; a card with its own words keeps them."""
    if isinstance(c, str):
        return FACELESS_HEAD.get(c, FACELESS_HEAD[FACELESS_DEFAULT])
    c = c or {}
    if is_own(c):
        return (c.get("head_en") or "").strip() or OWN_FALLBACK[face_hidden(c)][1]
    preset = c.get("preset") or ""
    own = (c.get("en") or "").strip()
    if own and (preset not in FACELESS_PRESETS or own != FACELESS_PRESETS[preset][2]):
        return own
    return FACELESS_HEAD.get(preset, FACELESS_HEAD[FACELESS_DEFAULT])


def is_faceless(c: Optional[dict]) -> bool:
    """A cast entry / hero node of the faceless kind."""
    return (c or {}).get("kind") == "faceless"


def faceless_line(c) -> str:
    """The hero's line for a faceless hero: a card (its `preset`, else its own `en`) or a preset id."""
    if isinstance(c, str):
        return FACELESS_PRESETS.get(c, FACELESS_PRESETS[FACELESS_DEFAULT])[2]
    c = c or {}
    if is_own(c) and not (c.get("en") or "").strip():
        return OWN_FALLBACK[face_hidden(c)][0]
    return (c.get("en") or "").strip() or FACELESS_PRESETS.get(c.get("preset") or "", FACELESS_PRESETS[FACELESS_DEFAULT])[2]


# A mask carved or painted with a face (an oni / demon, a skull, a Venetian or kabuki mask...) is a face to YuNet: the
# first live beat clip (2026-11-06, a red oni mask) had 4 of its 6 hero pictures flagged and redrawn with a hint for a
# smooth mask the user had not asked for. For such a hero the face-on-mask check is off.
_FACE_MASK = re.compile(r"\b(oni|demon|devil|skull|skeleton|venetian|carnival|kabuki|noh|hannya|tengu|plague doctor)\b", re.I)
_ANIMAL = r"(?:animal|wolf|fox|cat|tiger|lion|bear|owl|raven|crow|bird|deer|stag|boar|dog|jackal|rabbit|bull|ram|goat)"
# a feature word counts only when it is tied to the mask / helmet / head itself: «wolf mask», «mask of a fox», «horned mask»,
# «mask with fangs». «cat-ear hood», «balaclava covering the nose and mouth» say nothing of a face on the mask.
_MASK_TIED = re.compile(
    r"\b" + _ANIMAL + r"[- ]head(?:ed)?\b|"
    r"\b" + _ANIMAL + r"(?:[- ]faced)?\s+(?:mask|helmet)\b|"
    r"\b(?:mask|helmet)\s+of\s+(?:a\s+|an\s+|the\s+)?" + _ANIMAL + r"\b|"
    r"\b(?:fanged|grinning|horned|toothed|tusked|snarling|smiling)\s+(?:\w+\s+)?(?:mask|helmet)\b|"
    r"\b(?:carved|painted)\s+(?:\w+\s+)?(?:face\b|mask\b)|"
    r"\b(?:mask|helmet)\s+with\s+(?:\w+\s+){0,2}(?:fangs?|teeth|tusks?|horns|a\s+grin|a\s+mouth|a\s+nose|eye\s+holes?|eye\s+slots?)\b", re.I)


def mask_has_features(text: str) -> bool:
    """Whether the hero's words give the mask a face of its own (eyes, a mouth, a muzzle): then YuNet sees a face in it."""
    t = text or ""
    return bool(_FACE_MASK.search(t) or _MASK_TIED.search(t))


def faces_checked(c: Optional[dict]) -> bool:
    """Whether the face detector may judge this hero's shots (SFace, similarity): not for a faceless one - for it the
    check is the reverse, picture_checks.face_on_faceless."""
    return not is_faceless(c) and not prompts.is_nonperson(c)


def faceless_card(preset: str = FACELESS_DEFAULT) -> dict:
    """A cast entry / hero node's data for a preset."""
    p = preset if preset in FACELESS_PRESETS else FACELESS_DEFAULT
    ru, en, line = FACELESS_PRESETS[p]
    return {"kind": "faceless", "preset": p, "gender": "other", "age": 0, "en": line, "ru": ru, "outfit_en": "", "outfit_ru": ""}


def prompt_of(plan: dict, i: int) -> str:
    """Krea's prompt for character i: a photo of them alone, facing the camera, in the video's look and the place of
    their first scene."""
    c = (plan.get("cast") or [])[i]
    place = next((s.get("place_en") for s in plan.get("scenes") or [] if s.get("place_en") and (i + 1) in (s.get("who") or [1])), "")
    style = (plan.get("style_en") or "").strip().rstrip(".")
    outfit = re.sub(r"^\s*(wearing|dressed in)\s+", "", (c.get("outfit_en") or "").strip(), flags=re.I).rstrip(".")
    # «Вид»: the portrait's framing and medium (a live look: waist-up, «Photo of a real woman, natural skin texture»);
    # an older plan keeps «A medium close-up photo of»
    kind = prompts.kind_of(c)
    opening, anchor = looks.portrait(plan, who_of(c, plan), "" if kind != "person" else c.get("gender", ""), kind)
    ending = (f"{LIGHT_OF[kind]} Only this one {kind} in the picture. No text, no watermark." if kind != "person" else
              "Natural light on the face, sharp focus on the eyes, neutral expression. Only this one person in the picture. "
              "No text, no watermark.")
    return " ".join(x for x in (
        f"{style}." if style else "",
        f"{opening}, facing the camera: {c.get('en', '').strip().rstrip('.')}.",
        anchor,
        f"Wearing {outfit}." if outfit else "",
        f"Behind them: {place.strip().rstrip('.')}." if place else "",
        ending) if x)


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
    "bigger": ("крупнее", "Looks a little bigger."),
    "smaller": ("меньше", "Looks a little smaller."),
    "fluffier": ("пушистее", "A fluffier, thicker coat."),
    "coat": ("светлее окрас", "A lighter coat colour."),
    "newer": ("новее", "Looks new, clean and polished."),
    "worn": ("потрёпаннее", "Looks worn, scratched and weathered."),
    "glow": ("ярче подсветка", "Brighter glowing lights."),
    "warm": ("теплее свет", "Warm golden light."),
    "studio": ("студийный свет", "Soft, even studio light."),
}
LIGHT = {"warm", "studio"}
CHANGE_SYSTEM_NONPERSON = """You turn a user's short change to a character's look (an animal, a robot or a creature) into one short English
sentence for an image model: concrete visual words about the character only (fur, colours, shape, materials, lights, size), no names, no feelings.
Words or tags already in English (like Some_Trigger_Word) stay as they are. Only the sentence, no notes, no placeholders."""
CHANGE_SYSTEM = """You turn a user's short change to a person's look into one short English sentence for an image model:
concrete visual words about the person only (hair, face, makeup, body, clothes), no names, no feelings.
Words or tags already in English (like Some_Trigger_Word) stay as they are. Only the sentence, no notes, no placeholders."""


def split_change(text: str) -> tuple[list[str], str]:
    """The user's own change -> (the pieces to keep verbatim, the rest for the writer to put into English). In a text
    with Cyrillic letters, a comma-separated piece written in Latin letters only is a LoRA's trigger or an English
    phrase meant for the model as it is: the writer used to translate or drop it. A text with no Cyrillic at all
    goes to the writer whole (English - normalized, another Latin-script language - translated)."""
    text = text.strip()
    if not re.search(r"[Ѐ-ӿ]", text):
        return [], text
    pieces = [p.strip(" .;") for p in re.split(r"\s*,\s*", text) if p.strip(" .;")]
    keep = [p for p in pieces if re.search(r"[A-Za-z]", p) and not re.search(r"[Ѐ-ӿ]", p)]
    return keep, ", ".join(p for p in pieces if p not in keep)


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


def faces_on(path, c: Optional[dict] = None) -> int:
    """How many confident faces the detector finds on a picture (-1: it could not tell; always for a hero that is not a
    person - an animal or a robot has no face to find, and no fault is shown for it)."""
    if prompts.is_nonperson(c):
        return -1
    try:
        import cv2
        from . import checks
        img = checks.imread(path)
        return len(checks._confident_faces(img)) if img is not None else -1
    except Exception:  # noqa: BLE001 - a check is a bonus, never a blocker
        return -1


def one_face(pid: str, i: int, name: str) -> dict | None:
    """Try `name` of character i cut to its biggest face: the whole height, a 4:5 width around the face - Krea at the
    video's 16:9 draws a «character sheet» at times (a close-up and the whole figure, 2026-11-02: three tries in a
    row), and a portrait with two faces puts her twice into the frames. The cut is a try of its own when exactly one
    face is left on it. -> the try, or None."""
    try:
        import cv2
        from . import checks
        folder = projects.folder(pid)
        img = checks.imread(folder / name)
        faces = checks._confident_faces(img) if img is not None else []
        if not faces:
            return None
        h, w = img.shape[:2]
        x, _, fw, _ = max(faces, key=lambda f: f[2] * f[3])[:4]
        side = min(w, round(h * 0.8))
        x0 = int(max(0, min(w - side, x + fw / 2 - side / 2)))
        cut = img[:, x0:x0 + side]
        if len(checks._confident_faces(cut)) != 1:
            return None
        out = f"cast_{uuid.uuid4().hex[:8]}.png"
        checks.imwrite(folder / out, cut)
    except Exception:  # noqa: BLE001 - the try as it is, then
        return None
    cur = projects.load(pid)
    t = next((x for x in cur["plan"]["cast"][i].get("tries") or [] if x["file"] == name), {})
    new = {"file": out, "seed": t.get("seed"), "faces": 1, "cut_of": name}
    cur["plan"]["cast"][i].setdefault("tries", []).append(new)
    projects.save(cur)
    return new


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
        c.setdefault("tries", []).append({"file": name, "seed": seed, "faces": faces_on(folder / name, c), **({"tweak": tweak} if tweak else {})})
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
    keep, to_translate = split_change(text)
    text_en = ""
    if to_translate:
        from .llm import client as llm
        job.progress["message"] = i18n.L("сценарист переводит правку", "the writer translates the change")
        llm.use_lang(i18n.plan_lang_name(plan))
        schema = {"type": "object", "properties": {"en": {"type": "string"}}, "required": ["en"], "additionalProperties": False}
        async with llm.session(plan.get("model")) as cl:
            d = await cl.chat_json(CHANGE_SYSTEM_NONPERSON if prompts.is_nonperson(plan["cast"][i]) else CHANGE_SYSTEM, f"The change ({llm.lang()}): {to_translate}", schema, temperature=0.2, seed=1, max_tokens=1500, step="cast")   # 1500: a thinking model (Gemma 4) reasons first, 200 was all thought
        text_en = str(d.get("en", "")).strip()
    text_en = ", ".join([*keep, text_en] if text_en else keep)
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
            same = ("The same person as in the first image: exactly the same face, identity and skin tone" if not prompts.is_nonperson(plan["cast"][i])
                    else f"The same {prompts.kind_of(plan['cast'][i])} as in the first image: exactly the same {prompts.KIND_KEEP[prompts.kind_of(plan['cast'][i])]}")
            await picture.edit(job, same + ", the same "
                               f"framing, pose and background. Change only this: {change} Photorealistic portrait, sharp focus on the eyes. "
                               "No text, no watermark.", [src], seed, w, h, folder / name, picture.project_loras(proj["settings"], "flux2"))
        else:
            prompt = prompt_of(plan, i).replace(" Natural light", f" {change} Natural light", 1).replace(" Soft natural light", f" {change} Soft natural light", 1).replace(" Soft even light", f" {change} Soft even light", 1)
            await picture.generate(job, prompt, seed, w, h, folder / name, picture.project_loras(proj["settings"], "krea"))
        cur = projects.load(pid)
        if i >= len(cur["plan"].get("cast") or []):   # the hero was removed meanwhile
            (folder / name).unlink(missing_ok=True)
            return cur
        cur["plan"]["cast"][i].setdefault("tries", []).append(
            {"file": name, "seed": seed, "faces": faces_on(folder / name, cur["plan"]["cast"][i]), "tweaks": keys, "edit": flux,
             **({"change_ru": text.strip(), "change_en": text_en} if text_en else {})})
        proj = projects.save(cur)
    return proj


async def photo_tries(job: jobs.Job, pid: str, i: int, n: int = 3) -> dict:
    """Tries of character i from their own photo (from_photo): FLUX.2 Klein draws the same person anew as the casting's
    portrait - the look, the outfit, the video's style, the place of their first scene - each try with how close its
    face is to the photo (SFace, `sim`), so «Песня → клип» (autopilot.py) approves the likest. -> the project."""
    proj = projects.load(pid)
    plan = proj.get("plan") or {}
    if not 0 <= i < len(plan.get("cast") or []):
        raise EngineError(i18n.L("Нет такого героя", "No such hero"))
    src = portrait_path(proj, i)
    if not src:
        raise EngineError(i18n.L("Сначала нужен портрет героя", "The hero needs a portrait first"))
    prompt = ("The same person as in the first image: exactly the same face, identity, skin tone and hair. A new photograph "
              "of them with another camera position and framing; do not copy the background. " + prompt_of(plan, i))
    w, h = render.picture_size(proj["settings"])
    folder = projects.folder(pid)
    from . import frames
    for k in range(n):
        seed = random.randrange(1, 2**31 - 1)
        name = f"cast_{uuid.uuid4().hex[:8]}.png"
        job.progress["stage"] = "drawing"
        job.progress["message"] = i18n.L(f"проба {k + 1} из {n}", f"try {k + 1} of {n}")
        await picture.edit(job, prompt, [src], seed, w, h, folder / name, picture.project_loras(proj["settings"], "flux2"))
        sim = frames.similarity(folder / name, src)
        cur = projects.load(pid)
        if i >= len(cur["plan"].get("cast") or []):   # the hero was removed meanwhile
            (folder / name).unlink(missing_ok=True)
            return cur
        cur["plan"]["cast"][i].setdefault("tries", []).append(
            {"file": name, "seed": seed, "faces": faces_on(folder / name, cur["plan"]["cast"][i]), "edit": True, "sim": None if sim is None else round(sim, 3)})
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
    if not c.get("photo") or prompts.is_nonperson(c):   # no face to compare on an animal, a robot or a creature
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
        if several and (i + 1) not in (s.get("who") or []) or prompts.no_cast(p, s):
            continue   # no_cast: a landscape or a stranger is not the hero's likeness
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
