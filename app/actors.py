"""Actors: a character library that lives outside any project (data/actors/<id>/), so a hero can be the same person in every
project and series. A series may keep its own actors the same way (data/series/<sid>/actors/): every store function takes
a root folder (`base`), None meaning the shared library.

An actor is `actor.json` + pictures: `photo.png` (the real or drawn reference of the person), `face.png` (a close-up on a
plain black background), `turn.png` (a full-body turnaround, front / side / back, on black), `ref.png` (a face drawn in the
actor's look: the sheet is drawn from it when there is one). The recipe is the one proven on the GPU (2026-11-09): one
hero per reference picture (FLUX.2 Klein mixed two people up), the face and the turnaround drawn from the same crop, and
H3 Ref2VA then holds the face when the face panel is a reference picture of the scene.

The graph's «Герой» node with `actor` set takes its look and its picture from here (hero_data).
The drawing goes through the studio's queue like every picture job (jobs.submit_task in actors_api.py): draw_sheet / tries
are the job functions, they never run by themselves.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from . import config, i18n, jobs, looks
from .engine import other_graphs
from .engine.comfy import EngineError

KINDS = ("person", "animal", "robot", "creature")
TEXT_FIELDS = ("name", "look_en", "look_ru", "outfit_en", "outfit_ru", "voice_en")
IMAGES = ("photo", "face", "turn", "ref")
MAX_TRY_LOOKS, TRY_SEEDS = 4, 2
FACE_SIZE, TURN_SIZE = (512, 512), (1024, 512)
BLACK = "on a plain pure black background"
_ID = re.compile(r"^[A-Za-z0-9_-]{1,48}$")


# ---------------------------------------------------------------------------------------------------------------
# the store
# ---------------------------------------------------------------------------------------------------------------
def root(base: Optional[Path] = None) -> Path:
    return Path(base) if base else config.DATA_DIR / "actors"


def series_root(sid: str) -> Path:
    """A series' own actors (the series branch uses it as `base`)."""
    if not _ID.match(sid or ""):
        raise ValueError("bad series id")
    return config.DATA_DIR / "series" / sid / "actors"


def folder(aid: str, base: Optional[Path] = None) -> Path:
    if not _ID.match(aid or ""):
        raise KeyError(aid)
    return root(base) / aid


def image_path(aid: str, which: str, base: Optional[Path] = None) -> Path:
    if which not in IMAGES:
        raise KeyError(which)
    return folder(aid, base) / f"{which}.png"


def _clean(a: dict, old: Optional[dict] = None) -> dict:
    out = dict(old or {})
    for k in TEXT_FIELDS:
        if k in a or k not in out:
            out[k] = str(a.get(k) or "").strip()[:2000]
    kind = a.get("kind", out.get("kind", "person"))
    out["kind"] = kind if kind in KINDS else "person"
    if "look" in a or "look" not in out:
        lk = a.get("look")
        out["look"] = lk if lk in looks.LOOKS and lk != looks.AUTO else ""
    if "tries" in a:
        out["tries"] = [t for t in a["tries"] if isinstance(t, dict) and t.get("file")]
    return out


def get(aid: str, base: Optional[Path] = None) -> dict:
    p = folder(aid, base) / "actor.json"
    if not p.exists():
        raise KeyError(aid)
    return json.loads(p.read_text(encoding="utf-8"))


def exists(aid: str, base: Optional[Path] = None) -> bool:
    try:
        return (folder(aid, base) / "actor.json").exists()
    except KeyError:
        return False


def _write(a: dict, base: Optional[Path]) -> dict:
    d = folder(a["id"], base)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "actor.json.tmp"
    tmp.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(d / "actor.json")
    return a


def save(a: dict, base: Optional[Path] = None) -> dict:
    """Create (no id, or an unknown one) or update an actor; only the known fields are kept."""
    aid = a.get("id")
    old = get(aid, base) if aid and exists(aid, base) else None
    new = _clean(a, old)
    if not old:
        new["id"] = aid if aid and _ID.match(aid) else "actor-" + uuid.uuid4().hex[:8]
        new["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return _write(new, base)


def delete(aid: str, base: Optional[Path] = None) -> None:
    d = folder(aid, base)
    if d.exists():
        shutil.rmtree(d)


def public(a: dict, base: Optional[Path] = None) -> dict:
    """The actor for the page: which pictures it has (with their age: a redrawn picture must not stay cached)."""
    d = folder(a["id"], base)
    have = {w: int((d / f"{w}.png").stat().st_mtime) for w in IMAGES if (d / f"{w}.png").exists()}
    return {**a, "images": have}


def list_all(base: Optional[Path] = None) -> list[dict]:
    r = root(base)
    out = []
    for p in sorted(r.glob("*/actor.json")) if r.exists() else []:
        try:
            out.append(public(json.loads(p.read_text(encoding="utf-8")), base))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda a: (a.get("name") or "").lower())


def put_image(aid: str, which: str, src: Path, base: Optional[Path] = None) -> Path:
    """Copy a picture (any format PIL reads) in as the actor's PNG."""
    from PIL import Image
    dest = image_path(aid, which, base)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im.convert("RGB").save(dest)
    if which == "photo":
        # a new photo: the old look reference, face panel and turnaround are of another face
        for old in ("ref", "face", "turn"):
            (dest.parent / f"{old}.png").unlink(missing_ok=True)
    return dest


def crop(src: Path, box: tuple, dest: Path) -> Path:
    """One person out of a picture: `box` = (x, y, w, h), in pixels or (all four <= 1) as shares of the picture. A
    reference picture holds ONE hero: drawing from a picture with two people mixed them up."""
    from PIL import Image
    with Image.open(src) as im:
        im = im.convert("RGB")
        x, y, w, h = (float(v) for v in box)
        if max(x, y, w, h) <= 1.0:
            x, y, w, h = x * im.width, y * im.height, w * im.width, h * im.height
        x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
        x1, y1 = min(im.width, int(round(x + w))), min(im.height, int(round(y + h)))
        if x1 - x0 < 16 or y1 - y0 < 16:
            raise ValueError(i18n.L("Рамка слишком маленькая", "The box is too small"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.crop((x0, y0, x1, y1)).save(dest)
    return dest


# ---------------------------------------------------------------------------------------------------------------
# a hero node with an actor
# ---------------------------------------------------------------------------------------------------------------
def look_text(a: dict) -> tuple[str, str]:
    """(the look, the outfit) in English, as a hero node keeps them."""
    return (a.get("look_en") or "").strip(), (a.get("outfit_en") or "").strip()


def library_for(proj: dict, aid: str) -> Optional[Path]:
    """The library an actor of a project is looked up in: the project's series' own when the actor is there, else the
    global one (None). The graph and «В библиотеку» both use it."""
    if proj.get("series"):
        root = series_root(proj["series"])
        if exists(aid, root):
            return root
    return None


def hero_data(d: dict, base: Optional[Path] = None) -> dict:
    """What a «Герой» node with `actor` is: the actor's look and outfit, their face panel (an absolute path - the graph
    joins it to the project's folder, which leaves an absolute path as it is) and kind. A node without `actor`, or with a
    deleted one, is returned as it is."""
    aid = d.get("actor")
    if not aid or not exists(aid, base):
        return d
    a = get(aid, base)
    look, outfit = look_text(a)
    out = {**d, "en": look, "outfit_en": outfit, "ru": a.get("look_ru") or d.get("ru", ""), "outfit_ru": a.get("outfit_ru") or d.get("outfit_ru", "")}
    face = image_path(aid, "face", base)
    # the face panel, else the look reference, else the photo: a hero with a picture of any kind has a picture
    pic = next((p for p in (face, image_path(aid, "ref", base), image_path(aid, "photo", base)) if p.exists()), None)
    out["photo"] = str(pic) if pic else None
    if a.get("kind") and a["kind"] != "person":
        out["kind"] = a["kind"]
    elif "kind" in out:
        out.pop("kind")
    return out


def from_hero(d: dict, folder_: Path, name: str = "", base: Optional[Path] = None) -> dict:
    """«В библиотеку»: a hero (a graph node's data or a cast member of a project; `folder_` is the project's folder) becomes
    an actor, its photo copied in as the actor's photo."""
    a = save({"name": name or d.get("title") or d.get("name") or d.get("ru") or "", "look_en": d.get("en", ""), "look_ru": d.get("ru", ""),
              "outfit_en": d.get("outfit_en", ""), "outfit_ru": d.get("outfit_ru", ""), "kind": d.get("kind") or "person",
              "voice_en": d.get("voice_en", "")}, base)
    p = folder_ / d["photo"] if d.get("photo") else None
    if p and p.exists():
        put_image(a["id"], "photo", p, base)
    return public(a, base)


# ---------------------------------------------------------------------------------------------------------------
# the sheet: prompts, graphs, the job
# ---------------------------------------------------------------------------------------------------------------
def who(a: dict) -> str:
    return "person" if a.get("kind", "person") == "person" else a["kind"]


def style_of(look: str, kind: str = "person") -> str:
    """The picture's style sentence: a drawn look in its own words (a frame look says its medium strongly), none - a plain photo."""
    lk = looks.LOOKS.get(look or "")
    if not lk or look == looks.AUTO:
        return "Photorealistic, natural light." if kind == "person" else "Photorealistic, natural light, sharp details."
    text = (lk.get("frame_en") or lk.get("style_en") or "").strip().rstrip(".")
    if not lk.get("live"):
        text = looks.unphoto(text)
    return text + "." if text else ""


def _appearance(a: dict) -> str:
    look, outfit = look_text(a)
    return ", ".join(x.rstrip(".") for x in (look, outfit) if x)


def source_prompt(a: dict) -> str:
    """A reference picture drawn from the look text alone (Krea 2), when the actor has no photo."""
    kind = who(a)
    pose = "a waist-up portrait, facing the camera, neutral expression" if kind == "person" else "a portrait, facing the camera"
    return (f"{pose.capitalize()} of {_appearance(a)}. Only this one {kind} in the picture, a plain neutral background. "
            f"{style_of(a.get('look', ''), kind)} No text, no watermark.").replace("  ", " ")


def sheet_plan(a: dict, seed: int = 1) -> list[dict]:
    """The sheet's two panels as picture jobs: name (face / turn), prompt, size and seed. Both are drawn from the same
    reference (one hero in it); the prompt's «the person from the image» is the first reference picture."""
    kind = who(a)
    the = f"the {kind} from the image"
    style = style_of(a.get("look", ""), kind)
    outfit = (a.get("outfit_en") or "").strip().rstrip(".")
    in_ = f" in {outfit}" if outfit else ""
    # no outfit words in the face: "a short skirt and white sneakers" made FLUX.2 Klein draw the whole figure, the face
    # a few pixels (2026-11-09) - the turnaround carries the outfit
    face = (f"A tight close-up portrait of {the}: only the head and the top of the shoulders, the face fills most of the "
            f"frame, facing the camera, neutral expression, {BLACK}. {style}").strip()
    turn = (f"A character turnaround of {the}{in_}: full body, standing, front, side and back views in a row, {BLACK}. {style}").strip()
    return [{"name": "face", "prompt": face, "w": FACE_SIZE[0], "h": FACE_SIZE[1], "seed": seed},
            {"name": "turn", "prompt": turn, "w": TURN_SIZE[0], "h": TURN_SIZE[1], "seed": seed}]


def sheet_graphs(a: dict, ref: str, seed: int = 1, prefix: str = "actor") -> dict[str, dict]:
    """The Klein graphs of the sheet's panels from the reference `ref` (a file in COMFY_INPUT): name -> node dict. The
    queue's job draws through picture.edit (it manages the model in memory); this is the same graph, to look at and to test."""
    return {p["name"]: other_graphs.flux2_edit(p["prompt"], [ref], p["w"], p["h"], p["seed"], f"{prefix}_{p['name']}",
                                               config.FLUX2_UNET, config.FLUX2_CLIP, config.FLUX2_VAE)
            for p in sheet_plan(a, seed)}


def reference(a: dict, base: Optional[Path] = None) -> Optional[Path]:
    """The picture the sheet is drawn from: a face drawn in the actor's look, else their photo; None - to be drawn."""
    for w in ("ref", "photo"):
        p = image_path(a["id"], w, base)
        if p.exists():
            return p
    return None


async def draw_sheet(job: jobs.Job, aid: str, base: Optional[Path] = None, seed: Optional[int] = None) -> dict:
    """«Нарисовать лист»: face.png and turn.png from the actor's reference. No photo: Krea 2 draws one from the look text
    first (photo.png, `photo_drawn`). -> the actor (public)."""
    import random
    from . import picture
    a = get(aid, base)
    d = folder(aid, base)
    seed = seed or random.randrange(1, 2**31 - 1)
    ref = reference(a, base)
    if not ref:
        if not _appearance(a):
            raise EngineError(i18n.L("У актёра нет ни фото, ни описания внешности", "The actor has neither a photo nor a look"))
        job.progress["message"] = i18n.L("рисую образ по описанию", "drawing the figure from the look")
        await picture.generate(job, source_prompt(a), seed, 1024, 1024, d / "photo.tmp.png")
        put_image(aid, "photo", d / "photo.tmp.png", base)
        (d / "photo.tmp.png").unlink(missing_ok=True)
        cur = get(aid, base)   # re-read: the actor may have been edited while the picture was drawn
        cur["photo_drawn"] = True
        _write(cur, base)
        ref = d / "photo.png"
    for k, p in enumerate(sheet_plan(a, seed)):
        job.progress["stage"] = "drawing"
        job.progress["message"] = i18n.L(f"панель {k + 1} из 2", f"panel {k + 1} of 2")
        tmp = d / f"{p['name']}.tmp.png"
        await picture.edit(job, p["prompt"], [ref], p["seed"], p["w"], p["h"], tmp)
        put_image(aid, p["name"], tmp, base)
        tmp.unlink(missing_ok=True)
    return public(get(aid, base), base)


# ---------------------------------------------------------------------------------------------------------------
# «Пробы»: the actor × looks
# ---------------------------------------------------------------------------------------------------------------
def pick_looks(keys) -> list[str]:
    """Up to four known looks, in order, each once."""
    out: list[str] = []
    for k in keys or []:
        if k in looks.LOOKS and k != looks.AUTO and k not in out:
            out.append(k)
    return out[:MAX_TRY_LOOKS]


def try_prompt(a: dict, look: str) -> str:
    kind = who(a)
    outfit = (a.get("outfit_en") or "").strip().rstrip(".")
    return (f"The same {kind} as in the first image: exactly the same face and identity" + (f", {outfit}" if outfit else "")
            + f". Redrawn as a close-up portrait facing the camera, neutral expression, {BLACK}. {style_of(look, kind)} "
            "Only this one character. No text, no watermark.")


async def tries(job: jobs.Job, aid: str, keys: list[str], seeds: int = TRY_SEEDS, base: Optional[Path] = None) -> dict:
    """«Пробы»: Klein redraws the actor's face in each of up to four looks × `seeds` seeds, from their face panel (else the
    reference). The files go into tries/ and actor.tries; one is chosen with pick_try. -> the actor (public)."""
    import random
    from . import picture
    a = get(aid, base)
    keys = pick_looks(keys)
    if not keys:
        raise EngineError(i18n.L("Выберите хотя бы один вид", "Pick at least one look"))
    src = next((p for p in (image_path(aid, "face", base), reference(a, base)) if p and p.exists()), None)
    if not src:
        raise EngineError(i18n.L("Сначала нужен лист или фото актёра", "The actor needs a sheet or a photo first"))
    d = folder(aid, base) / "tries"
    d.mkdir(exist_ok=True)
    seeds = max(1, min(int(seeds), 4))
    total, k = len(keys) * seeds, 0
    for look in keys:
        for _ in range(seeds):
            k += 1
            seed = random.randrange(1, 2**31 - 1)
            name = f"{look}_{uuid.uuid4().hex[:6]}.png"
            job.progress["stage"] = "drawing"
            job.progress["message"] = i18n.L(f"проба {k} из {total}", f"try {k} of {total}")
            await picture.edit(job, try_prompt(a, look), [src], seed, FACE_SIZE[0], FACE_SIZE[1], d / name)
            cur = get(aid, base)
            cur.setdefault("tries", []).append({"file": name, "look": look, "seed": seed})
            _write(cur, base)
    return public(get(aid, base), base)


def try_path(aid: str, name: str, base: Optional[Path] = None) -> Path:
    if not re.match(r"^[A-Za-z0-9_-]+\.png$", name or ""):
        raise KeyError(name)
    return folder(aid, base) / "tries" / name


def pick_try(aid: str, name: str, base: Optional[Path] = None) -> dict:
    """The chosen try becomes the actor's look: `look` is its look and it is the face panel and the reference the sheet is
    redrawn from (ref.png; draw_sheet next). The other tries are cleared. -> the actor (public)."""
    a = get(aid, base)
    t = next((x for x in a.get("tries") or [] if x.get("file") == name), None)
    p = try_path(aid, name, base)
    if not t or not p.exists():
        raise KeyError(name)
    a["look"] = t["look"]
    put_image(aid, "face", p, base)
    put_image(aid, "ref", p, base)
    _write(a, base)
    clear_tries(aid, base)
    return public(get(aid, base), base)


def clear_tries(aid: str, base: Optional[Path] = None) -> None:
    a = get(aid, base)
    a["tries"] = []
    _write(a, base)
    shutil.rmtree(folder(aid, base) / "tries", ignore_errors=True)
