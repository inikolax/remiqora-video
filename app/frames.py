"""«Кадр сцены»: a new scene's start frame drawn by FLUX.2 Klein from the photos of the people
in it (picture.edit) - the hero with the face from their photo in the scene's own place, framing and first action. The
picture becomes the scene's start photo (it is shot i2v from it, like «Начать с фото»), and `start_en` says what is on
it, so the writer needn't look. The face on the frame is checked against the photo (SFace); below the aim of its
framing (FACE_AIM) another seed is tried, the best of them stays and the scene is told when none passed FACE_MIN. One model load for a batch of scenes.
A scene in a place with a picture («Места», places.py) gets it as the last reference: the same set on every scene of
that place, from the scene's own camera.
"""
from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional

from . import checks, config, i18n, jobs, picture, places, projects, render
from .engine.comfy import EngineError
from .planner import check, prompts

# config.FRAME_FACE_MIN: SFace cosine frame ↔ photo below this - not her (a wide shot's small face scores ~0.3 while hers);
# config.FRAME_TRIES: seeds tried for a face that doesn't pass («Модели и настройки» → FLUX.2 Klein → Параметры)
SEED_STEP = 7919
# how big the person is on the frame: the action («she stands amidst the leaves») made a close-up scene's frame a
# full figure with a small face that FLUX.2 Klein drew less like her (2026-10-29)
FRAMES = {"close": "Close-up: head and shoulders fill the frame, the face large, sharp and in full view",
          "medium": "Medium shot: from the waist up, the face clear", "wide": "Wide shot: the whole figure in the place"}
# the face the tries aim for: a close or medium frame takes more seeds while its face is only somewhat like hers
# (0.55 read as another actress), the best stays; FRAME_FACE_MIN still says what is a miss
FACE_AIM = {"close": 0.65, "medium": 0.6, "wide": 0.4}
PREFIX = "frame_"     # our frames in the project folder: frame_<scene id>_<seed>.png
ORDINALS = ("first", "second", "third")
# A singing scene is shot from its frame, and LTX sings surely only from a face to the camera with the mouth open;
# the first beat drew profiles and «head thrown back, eyes closed» (a test clip's scene: SFace 0.17, the lips not
# judged). Its frame: facing the camera, singing, no wider than medium.
SING_ACTION = ("{who} sings toward the camera, mouth open mid-word, eyes open, {pos} face turned to the camera; "
               "{pos} hands are empty and relaxed below {pos} shoulders, there is no microphone anywhere")
# a frame whose face missed FRAME_FACE_MIN is tried again a step closer: the face bigger, drawn more like the photo
CLOSER = {"wide": "medium", "medium": "close"}
# Klein's first reference is the face cut out of the portrait (FACE_CROP times the face, FACE_PX square): the portrait
# alone is a medium close-up at the draft's size, its face a few hundred pixels of the megapixel Klein scales it to
FACE_CROP = 2.2
FACE_PX = 1024
FACES = config.DATA_DIR / "cache" / "faces"


def can_draw(plan: dict, s: dict) -> bool:
    """A new scene of a people video: with someone in the picture who has a photo (their face in the scene's place),
    or with nobody in it at all - a clip's insert of the empty coat on the chair is drawn empty (empty())."""
    if s.get("kind") != "new" or plan.get("mode") == "none" or prompts.is_raw(s):
        return False
    return empty(plan, s) or bool(frame_people(plan, s))


def frame_people(plan: dict, s: dict) -> list[int]:
    """«Кто в кадре» of the first frame: the heroes the user picked (`frame_people`, cast indices; [] - nobody), else
    the scene's people with photos (photo_people)."""
    cast = plan.get("cast") or []
    pick = s.get("frame_people")
    if isinstance(pick, list):
        return [i for i in pick if isinstance(i, int) and 0 <= i < len(cast) and prompts.has_photo(cast[i])]
    return prompts.photo_people(plan, s)


def empty(plan: dict, s: dict) -> bool:
    """A scene drawn without people: the user said nobody (`frame_people` []), or its actions name nobody."""
    pick = s.get("frame_people")
    return pick == [] if isinstance(pick, list) else not prompts.has_people(s, plan)


def empty_prompt(plan: dict, s: dict, place: bool) -> str:
    """The frame of a scene without people: the video's style, the place (its picture as the image when `place`), the
    framing and the first action; nobody in it."""
    style = (plan.get("style_en") or "").strip().rstrip(".")
    beats = [b.strip() for b in s.get("beats_en") or [] if b and b.strip()]
    framing = prompts.FRAMING.get(s.get("framing"), "Medium shot")
    set_ = places.of_scene(plan, s) if place else None
    where = (f"The location is the place in the image: the same architecture, materials, colors and light, seen from another spot "
             f"in it that suits this shot. Scene: {prompts._sentence(set_['en'])}" if set_ else prompts.place_line(plan, s))
    return " ".join(x for x in (
        f"{style}. Photorealistic film still." if style else "Photorealistic cinematic film still.",
        where, f"{framing}: {prompts._sentence(_empty_action(plan, s))}",
        "There are no people, no faces and no hands anywhere in this picture. No text, no watermark.") if x)


def _empty_action(plan: dict, s: dict) -> str:
    """What an empty frame shows: the scene's first action, or - when it names someone the user left out - the place."""
    beats = [b.strip() for b in s.get("beats_en") or [] if b and b.strip()]
    if beats and not prompts.has_people({"beats_en": beats[:1]}, plan):
        return beats[0]
    return "the place itself, empty, nobody in it"


def people(proj: dict, plan: dict, s: dict) -> list[tuple[str, Path, str]]:
    """[(how the prompt calls them, their photo, their outfit)] for the frame's people with photos (frame_people), in
    its order."""
    cast, folder, out = plan.get("cast") or [], projects.folder(proj["id"]), []
    for i in frame_people(plan, s):
        path = folder / cast[i]["photo"] if cast[i].get("photo") else projects.photo_path(proj)
        if path and path.exists():
            out.append((prompts.speaker(plan, i + 1), path, cast[i].get("outfit_en") or ""))
    return out[:3]


def place_photo(proj: dict, s: dict) -> Optional[Path]:
    """The picture of the scene's place, when it has one on disk and the places are on («Места», places_off)."""
    if proj["plan"].get("places_off"):
        return None
    x = places.of_scene(proj["plan"], s)
    path = projects.folder(proj["id"]) / x["photo"] if x and x.get("photo") else None
    return path if path and path.exists() else None


def first_moment(plan: dict, s: dict, names: list[str], shot: Optional[str] = None) -> tuple[str, Optional[str]]:
    """(framing, action) of the frame: the scene's framing (or `shot`, a try a step closer) and first beat (None
    without one); a singing scene's - SING_ACTION, medium at the widest."""
    beats = [b.strip() for b in s.get("beats_en") or [] if b and b.strip()]
    framing = shot if shot in FRAMES else s.get("framing") if s.get("framing") in FRAMES else "medium"
    if s.get("shot") == "sing" and names:
        cast = plan.get("cast") or []
        # the one who sings in this frame (names[0] is the frame's first person), not the cast's first: a man singing
        # in «several» got «her face» when the heroine was cast 1
        who = (frame_people(plan, s) or [0])[0]
        pos = {"female": "her", "male": "his"}.get((cast[who] if who < len(cast) else {}).get("gender"), "their")
        return ("medium" if framing == "wide" else framing), SING_ACTION.format(who=names[0], pos=pos)
    return framing, beats[0] if beats else None


def prompt_of(plan: dict, s: dict, names: list[str], place: bool = False, crop: bool = False,
              outfits: Optional[list[str]] = None, shot: Optional[str] = None) -> str:
    """FLUX.2 Klein's prompt: the video's style, who is in which image (the same face, hair and clothes; a new camera,
    not the photo's background) and what they wear, word for word, the scene's place - the image after the people's
    when `place` (its set, not its framing), else the scene's words - its framing (`shot`: a try a step closer) and
    first action; nobody else. `crop`: one person, the first image the face cut out of their photo (face_crop), the
    second the photo."""
    style = (plan.get("style_en") or "").strip().rstrip(".")
    if crop and len(names) == 1:
        refs = (f"{names[0]} is the person in the first and the second image (the first is a close-up of the face): exactly "
                "the same face, hair and clothes.")
    else:
        refs = " ".join(f"{who} is the person in the {ORDINALS[k]} image: exactly the same face, hair and clothes." for k, who in enumerate(names))
    wear = " ".join(f"{who} is wearing {prompts._lower_first(o.strip().rstrip('.'))}." for who, o in zip(names, outfits or []) if o and o.strip())
    shot, action = first_moment(plan, s, names, shot)
    framing, action = FRAMES[shot], action or f"{names[0]} looks at the camera"
    only = "Only this one person in the picture." if len(names) == 1 else f"Only these {len(names)} people in the picture."
    set_ = places.of_scene(plan, s) if place else None
    n = len(names) + (1 if crop and len(names) == 1 else 0)   # the images before the place's
    where = (f"The location is the place in the {ORDINALS[n] if n < 3 else 'fourth'} image: the same architecture, "
             f"materials, colors and light, seen from another spot in it that suits this shot. Scene: {prompts._sentence(set_['en'])}"
             if set_ else prompts.place_line(plan, s))
    return " ".join(x for x in (
        f"{style}. Photorealistic film still." if style else "Photorealistic cinematic film still.",
        refs, wear,
        "A new photograph with a different camera position and framing than the reference images; "
        + ("do not copy the people's backgrounds." if place else "do not copy their backgrounds."),
        where,
        f"{framing}: {prompts._sentence(action)}",
        only, "No text, no watermark.") if x)


def face_crop(photo: Path) -> Optional[Path]:
    """The face of a portrait cut out square (FACE_CROP times the face, FACE_PX), made once per photo (data/cache/faces);
    None when the photo has no single face."""
    try:
        dest = FACES / f"{render.file_sha(photo)[:16]}.png"
        if dest.exists():
            return dest
        box, size = checks.face_picture(photo)
        if not box or not size:
            return None
        import cv2
        img = cv2.imread(str(photo))
        x, y, fw, fh = box
        side = min(round(max(fw, fh) * FACE_CROP), size[0], size[1])
        x0 = max(0, min(size[0] - side, round(x + fw / 2 - side / 2)))
        y0 = max(0, min(size[1] - side, round(y + fh / 2 - side / 2)))
        cut = cv2.resize(img[y0:y0 + side, x0:x0 + side], (FACE_PX, FACE_PX),
                         interpolation=cv2.INTER_LANCZOS4 if side < FACE_PX else cv2.INTER_AREA)
        FACES.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), cut)
        return dest
    except Exception:  # noqa: BLE001 - the crop is a bonus: the portrait alone as before
        return None


def start_text(plan: dict, s: dict, names: list[str], shot: Optional[str] = None) -> str:
    """What the frame shows, for the writer (`start_en`, as describe_frame would say it)."""
    shot, action = first_moment(plan, s, names, shot)
    framing, action = prompts.FRAMING[shot], action or "looking at the camera"
    place = (s.get("place_en") or "").strip().rstrip(".")
    who = ", ".join(prompts._lower_first(n) for n in names)
    return f"{framing} of {who}: {prompts._sentence(action)}" + (f" {place}." if place else "")


def similarity(frame: Path, photo: Path) -> Optional[float]:
    """SFace cosine of the one face on the frame and the one on the photo; None when either isn't found alone."""
    try:
        import cv2
        a, b = cv2.imread(str(photo)), cv2.imread(str(frame))
        fa, fb = (checks._face_feature(x) if x is not None else None for x in (a, b))
        if fa is None or fb is None:
            return None
        return float(checks._recognizer().match(fa, fb, cv2.FaceRecognizerSF_FR_COSINE))
    except Exception:  # noqa: BLE001 - a check is a bonus, never a blocker
        return None


def _drop_frame(proj: dict, s: dict, keep: str = "") -> None:
    """The scene's old drawn frame, when no other scene starts from it."""
    old = s.get("start_photo")
    if old and old.startswith(PREFIX) and old != keep and not any(x.get("start_photo") == old for x in proj["plan"]["scenes"] if x is not s):
        (projects.folder(proj["id"]) / old).unlink(missing_ok=True)


async def draw_one(job: jobs.Job, proj: dict, index: int, seed: Optional[int] = None) -> dict:
    """The frame of scene `index` (the project as loaded), tried on up to TRIES seeds for the face; the best one is
    kept. -> {seed, similarity, ok, update: what goes on the scene} - draw_many puts it on the project as it is by then."""
    plan, s = proj["plan"], proj["plan"]["scenes"][index]
    if empty(plan, s):
        return await _draw_empty(job, proj, s, seed)
    who = people(proj, plan, s)
    if not who:
        raise EngineError(i18n.L(f"Сцена {index + 1}: ни у кого в ней нет фото", f"Scene {index + 1}: nobody in it has a photo"))
    names, photos, outfits = [n for n, _, _ in who], [p for _, p, _ in who], [o for _, _, o in who]
    where = place_photo(proj, s)
    w, h = render.picture_size(proj["settings"], render.scene_card(plan, proj["settings"], s))   # the frame of the model that shoots it
    folder = projects.folder(proj["id"])
    crop = face_crop(photos[0]) if len(photos) == 1 else None   # the face first, then the portrait, then the place
    refs = ([crop] if crop else []) + photos + ([where] if where else [])
    seed = seed if seed is not None else random.randrange(1, 2**31 - 1)
    best: tuple[Optional[float], Path, int, str] | None = None
    shot0 = first_moment(plan, s, names)[0]
    n = 0
    for shot in (shot0, CLOSER.get(shot0)):
        # a step closer only when no try passed FRAME_FACE_MIN (a face found but not hers)
        if shot is None or (shot != shot0 and (best is None or best[0] is None or best[0] >= config.FRAME_FACE_MIN)):
            break
        prompt = prompt_of(plan, s, names, where is not None, crop is not None, outfits, shot)
        aim = max(config.FRAME_FACE_MIN, FACE_AIM.get(shot, 0.6))
        for _ in range(config.FRAME_TRIES):
            sd = seed + n * SEED_STEP
            n += 1
            dest = folder / f"{PREFIX}{s['id']}_{sd}.png"
            await picture.edit(job, prompt, refs, sd, w, h, dest, picture.project_loras(proj["settings"], "flux2"))
            sim = similarity(dest, photos[0])
            if best is None or (sim is not None and (best[0] is None or sim > best[0])):
                if best is not None:
                    best[1].unlink(missing_ok=True)
                best = (sim, dest, sd, shot)
            else:
                dest.unlink(missing_ok=True)
            if sim is None or sim >= aim:
                break
    sim, dest, sd, shot = best
    ok = sim is None or sim >= config.FRAME_FACE_MIN
    # `frame`: the drawn frame's seed, its face's score (None: no single face to judge) and the place's picture it was
    # drawn in; the inspector shows a miss, and a frame older than its place's picture. A frame a step closer than the
    # scene's framing gives the scene its framing: the prompt says what the picture shows
    closer = shot != shot0
    return {"seed": sd, "similarity": sim, "ok": ok,
            "update": {"start_photo": dest.name, "start_en": start_text(plan, s, names, shot), "kind": "new",
                       **({"framing": shot} if closer else {}),
                       "frame": {"seed": sd, "face": None if sim is None else round(sim, 3), "ok": ok, **({"place": where.name} if where else {}),
                                 **({"closer": True} if closer else {})}}}


async def _draw_empty(job: jobs.Job, proj: dict, s: dict, seed: Optional[int]) -> dict:
    """A scene without people: FLUX.2 Klein in the place's picture when it has one, else Krea 2 from the words."""
    plan = proj["plan"]
    where = place_photo(proj, s)
    w, h = render.picture_size(proj["settings"], render.scene_card(plan, proj["settings"], s))
    sd = seed if seed is not None else random.randrange(1, 2**31 - 1)
    dest = projects.folder(proj["id"]) / f"{PREFIX}{s['id']}_{sd}.png"
    prompt = empty_prompt(plan, s, where is not None)
    if where:
        await picture.edit(job, prompt, [where], sd, w, h, dest, picture.project_loras(proj["settings"], "flux2"))
    else:
        await picture.generate(job, prompt, sd, w, h, dest, picture.project_loras(proj["settings"], "krea"))
    framing = prompts.FRAMING.get(s.get("framing"), "Medium shot")
    return {"seed": sd, "similarity": None, "ok": True,
            "update": {"start_photo": dest.name, "start_en": f"{framing}: {prompts._sentence(_empty_action(plan, s))}",
                       "kind": "new", "frame": {"seed": sd, "face": None, "ok": True, "empty": True, **({"place": where.name} if where else {})}}}


def hold_chain(plan: dict, s: dict, was: Optional[str]) -> None:
    """Formula 2: a continuation keeps its source's framing (CONTINUE_RULE, writer._hold_framing). A frame drawn a step
    closer gave scene `s` a new framing: the continuations that went on at its old one follow it, or each would start
    on a close-up and say «medium shot» - a cut inside 5 s."""
    scenes = plan.get("scenes") or []
    src = [s]
    for x in scenes[scenes.index(s) + 1:]:
        if x.get("kind") == "continue" and any(prompts.from_of(plan, x) is y for y in src) and x.get("framing") == was:
            x["framing"] = s["framing"]
            src.append(x)


def unlike(plan: dict) -> list[int]:
    """The scenes that start from a drawn frame whose face missed the hero's (frame.ok false): «перерисовать непохожие»."""
    return [s["index"] for s in plan.get("scenes") or [] if s.get("kind") == "new" and (s.get("start_photo") or "").startswith(PREFIX)
            and (s.get("frame") or {}).get("ok") is False and can_draw(plan, s)]


async def draw_many(job: jobs.Job, pid: str, indices: Optional[list[int]] = None, seed: Optional[int] = None,
                    better: bool = False) -> dict:
    """The frames of `indices` (None: every scene can_draw says yes to) one after another, the model loaded once; the
    project is saved after each frame (a stop keeps what is done). `better` («перерисовать непохожие»): a new frame
    whose face is no closer to the hero's than the scene's frame is dropped, the old one stays. -> {done: [...],
    failed: [...]}"""
    proj = projects.load(pid)
    plan = proj.get("plan") or {}
    todo = [i for i in (indices if indices is not None else range(len(plan.get("scenes") or [])))
            if 0 <= i < len(plan["scenes"]) and can_draw(plan, plan["scenes"][i])]
    if not todo:
        raise EngineError(i18n.L("Нет сцен, которым можно нарисовать кадр: нужна новая сцена с героем, у которого есть фото, или сцена без людей",
                                 "No scene to draw a frame for: a new scene with a hero who has a photo, or a scene with nobody in it"))
    job.progress.update(total=len(todo), done=0, scene=None, frames=[])
    done, failed, t0 = [], [], time.time()
    for n, i in enumerate(todo):
        job.progress.update(scene=i)
        proj = projects.load(pid)
        sid = proj["plan"]["scenes"][i]["id"]
        r = await draw_one(job, proj, i, seed)
        upd = r.pop("update")
        cur = projects.load(pid)   # the user may have edited while it drew: only the frame goes in
        s = next((x for x in cur["plan"]["scenes"] if x.get("id") == sid), None)
        old = (s or {}).get("frame") or {}
        if s is None:   # the scene was removed meanwhile
            (projects.folder(pid) / upd["start_photo"]).unlink(missing_ok=True)
        elif better and old.get("face") is not None and (s.get("start_photo") or "").startswith(PREFIX) \
                and (r["similarity"] is None or r["similarity"] <= old["face"]):
            (projects.folder(pid) / upd["start_photo"]).unlink(missing_ok=True)   # no closer to the hero: the old frame stays
            r.update(similarity=old["face"], ok=bool(old.get("ok")), kept=True)
        else:
            _drop_frame(cur, s, upd["start_photo"])
            was = s.get("framing")
            s.update(upd)
            if upd.get("framing") and upd["framing"] != was and prompts.formula(cur["plan"]) >= 2:
                hold_chain(cur["plan"], s, was)
            cur["plan"] = check.plan(cur["plan"])
            projects.save(cur)
        (done if r["ok"] else failed).append(i)
        job.progress.update(done=n + 1)
        job.progress["frames"].append({"scene": i, **r})
        # the frames still to draw at this job's own pace (a frame takes one to FRAME_TRIES tries): the bar follows
        job.estimate = round(time.time() - (job.started or t0) + (time.time() - t0) / (n + 1) * (len(todo) - n - 1))
    return {"done": done, "failed": failed, "seconds": round(time.time() - t0, 1)}


def estimate(n: int) -> float:
    """Seconds for n frames: the model's start and ~5 s a frame (tools/probe_flux2: 4 s warm at 1344×768)."""
    return 20 + 5 * n
