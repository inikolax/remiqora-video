"""The writer: an idea in Russian -> the storyboard. The grid (how many scenes, new / continue, chains) comes from
planner/grid.py and is not the LLM's to change; the LLM fills in only the content:
  cast (people modes): each character's look, en / ru, an adult age   |   world (no people): the place and its look
  style_en, audio_en: the video's look and its one continuous soundscape
  per scene: ru (for the user), beats_en (1-3 short English beats), framing, camera (enums), sound_en,
             place_en on a new scene, to_en without people (what the frame shows at the end: the next scene starts there)
planner/prompts.py::compose puts the final prompt together and validates every scene; the scenes that fail are sent
back once with the problems spelled out, what still fails is marked "check" for the user.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from ..planner import prompts
from ..planner.grid import SCENE_SECONDS, grid
from .. import i18n
from . import client, describe

GENDERS = ["female", "male", "other"]
CAST_COUNT = {"one": (1, 1), "several": (2, 3)}
NO_MUSIC = "no music, only natural sounds of the scene"

SYSTEM = """You are the screenwriter of a short video made by the AI video model MiniMax H3, scene by scene. Every scene is exactly 5 seconds; the model generates the picture and the sound together from your English text. The user writes in Russian; every *_en field is English, every *_ru / ru field is natural Russian.

How the video is cut is fixed and given to you: a "new" scene starts a shot in its own place (text-to-video); a "continue" scene goes on from the very last frame of the previous one (image-to-video): the same place, the same moment, the camera keeps rolling.

Write so the model can show it:
- beats_en: 1-3 beats, each one simple visible action in present tense, 4-25 words ("She turns her head toward the camera and smiles softly."). One action per beat, no "then". Five seconds hold about three small beats; slow, natural motion looks best.
- Concrete visual words: what moves, where light falls, what the wind does. No feelings without a visible sign, no story told in words, no inner thoughts.
- When someone walks or moves, say the direction relative to the camera, and keep it through the scene: "walks toward the camera" (faces seen) or "walks away from the camera, seen from behind". Never "walks forward", "moves deeper into", "heads down the path" without that - the video model then keeps the faces to the camera while moving away, and people walk backward.
- A "continue" scene never moves to another place and never jumps in time.
- ru: 1-2 Russian sentences telling the user what happens in this scene (never just "Сцена 1").
- framing (wide / medium / close) and camera are separate fields: do not describe the camera inside beats. Pick the camera that serves the action and vary framing and camera from scene to scene; "static" for at most half of the scenes.
- style_en: 15-40 words, the look of the whole video: live-action or a genre, light, lens, colour palette, film grain.
- sound_en: one short sentence: what is heard in this scene besides the music (steps, wind, rain, a door). No speech.
- Never: text, signs, letters, logos or screens with writing in the frame; changes of clothing; children or teenagers; names of real people or celebrities.
- Everyone in the video is an adult; give an explicit age of 21 or older."""

# A look of bare anatomy («lean build, high cheekbones, expressive features») gave a man's face to every heroine Krea drew
# (2026-10-29); a name or role in front («Singer - lean build») went into the prompt as it is
LOOK_RULE = ("A woman's look reads clearly feminine and attractive (a soft, delicate face, gentle features, full lips, long "
             "lashes); a man's clearly masculine. The look starts with the build or the face: never with a name, a role or "
             "a label (\"Singer - ...\").")

MODE_RULES = {
    "one": """There is exactly one person in the video: the hero. cast has one entry. Their look (en: build, skin, face, eyes, hair; no clothes there) and outfit (outfit_en) are pasted word for word into every scene by code, so make them specific: 30-60 words, colours and materials. """ + LOOK_RULE + """ In beats write "she" / "he" (or "they"), never repeat the look.
place_en on a "new" scene: one sentence about the place, light and time of day.""",
    "several": """There are 2-3 people. cast lists each with the same detail as a hero (look 30-60 words + outfit). """ + LOOK_RULE + """ In beats refer to them clearly ("the woman in the red coat", "the older man") and keep the same people through the video.
who: on every scene, the numbers of the characters visible in it (1 = the first in cast). Only their looks are pasted into that scene's prompt, so a person not listed is not in the frame - list everyone your beats show or mention as present. A "continue" scene usually keeps the people of the scene before; someone may walk in or out of the frame. Not everyone has to be in every scene.
place_en on a "new" scene: one sentence about the place, light and time of day.""",
    "none": """There are NO people in the video at all: no persons, hands, silhouettes or crowds. Instead of a cast write world: the place and its look (en, 25-60 words: setting, materials, palette, light) - pasted into every scene.
The whole video is one continuous shot. to_en: in 4-15 words, what the frame shows at the very end of the scene - the next scene starts from exactly that ("a glowing phoenix spreading its wings over the dunes"). Make the scenes flow: each one develops or transforms what the previous ended with.
place_en of the first scene: one sentence about the very first picture (what is in the frame at second 0), without repeating world; "" on the other scenes.""",
}


# ---------- a clip from a song (phase 11; remiqora-video's music writer) ----------
# The scenes are cut on the song's bars in code (planner/clip.py); the writer gives each its shot kind and content,
# from a treatment on the song's parts. A "sing" scene gets the words sung during it as its line (how "sing"): code,
# not the LLM - the song is what it is.
SHOTS = ("sing", "perform", "insert")
SHOTS_NONE = ("perform", "insert")
SING_MIN_VOICE = 0.2   # under this much voice in a scene "sing" is a mistake: it becomes "perform"
CLIP_RULES = ("""This is a MUSIC VIDEO to the user's song. Every scene is its own shot, cut on the song's bars; the scenes have different lengths (given per scene), a loud part cuts often, a quiet one holds.
For each scene choose shot:
- "sing": character 1 (the singer) sings, the face big and clear (framing close or medium), facing the camera, lips moving with the words. Only on scenes whose voice is there (see "sung" and "voice").
- "perform": the body to the music - swaying, dancing with the upper body, walking toward the camera, playing; lips don't matter.
- "insert": a detail without a face - hands, light, fire, smoke, fabric, the place itself (a short breath between faces).
Mostly "sing" where the voice is; "perform" and "insert" in the instrumental parts and between the lines.
- Loud parts (chorus, drop): the strongest images and livelier camera; quiet parts (intro, verse, break): calm, small movement.
- Take the key words of a sung line literally in its scene ("the sky falls" - debris and ash fall).
- A person does ONE concrete, moderate movement - never "hard", "wild" or "frantic" (bodies moving like that grow extra hands and lose their faces). The energy comes from light, smoke, fire, dust, hair and fabric in the wind and the camera.
- beats_en: as many beats as the scene holds: 1 under 3 s, 2 for 3-5 s, up to 3 longer.
- sound_en: "" - the song is the sound of the video.
- place_en on every scene: one sentence about its place, light and time of day; keep to 2-3 places in the whole video, returning to them.""",
              """This is a MUSIC VIDEO to the user's song, without people. Every scene is its own shot, cut on the song's bars; the scenes have different lengths (given per scene), a loud part cuts often, a quiet one holds.
For each scene choose shot: "perform" - the place in motion to the music (light, water, smoke, traffic, the sky); "insert" - a close detail (fire, a lamp, rain on glass, fabric).
- Loud parts (chorus, drop): the strongest images and livelier camera; quiet parts: calm, slow motion.
- Take the key words of a sung line literally in its scene ("the sky falls" - debris and ash fall).
- beats_en: as many beats as the scene holds: 1 under 3 s, 2 for 3-5 s, up to 3 longer.
- sound_en: "" - the song is the sound of the video.""")


def _mmss(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60}:{t % 60:02d}"


def _clip_line(s: dict) -> str:
    """A clip's scene for the writer: its time and length, its part of the song, what is sung and how much voice."""
    sung = " / ".join(x["text"] for x in s.get("sung") or [])
    return (f"scene {s['index'] + 1} ({_mmss(s['start'])}, {grid_seconds(s):.1f} s): {s.get('part', '')}, "
            f"{'loud' if s.get('loud') else 'quiet'}; " + (f"sung: «{sung}»; voice: {s.get('singing', '')}" if sung else "no singing"))


def grid_seconds(s: dict) -> float:
    from ..planner.grid import seconds_of
    return seconds_of(s)


def clip_shot(plan: dict, s: dict, shot: Optional[str]) -> None:
    """A clip's scene takes its shot kind and, singing, its line: the words sung during it, «поёт». A "sing" on an
    instrumental scene is a mistake (the lips would move over nothing): "perform"."""
    allowed = SHOTS if plan["mode"] != "none" else SHOTS_NONE
    shot = shot if shot in allowed else s.get("shot") if s.get("shot") in allowed else "perform"
    if shot == "sing" and float(s.get("voice") or 0) < SING_MIN_VOICE:
        shot = "perform"
    s["shot"] = shot
    words = " ".join(x["text"] for x in s.get("sung") or []).strip()
    s["lines"] = [{"who": 1, "text": words, "how": "sing"}] if shot == "sing" and words else []
    if plan["mode"] == "several" and shot == "sing" and 1 not in (s.get("who") or [1]):
        s["who"] = sorted({1, *(s.get("who") or [])})   # the singer is character 1
    # a singing scene goes to the model that sings to the track (when the video's can't) and starts from the singer's
    # photo (LTX holds no face from words); a scene that stops singing leaves that model
    c = plan.get("clip") or {}
    if s.get("kind") != "new":
        return
    if shot == "sing":
        if c.get("sing_model"):
            s["model"] = c["sing_model"]
        if c.get("photo") and not s.get("start_photo"):
            s["start_photo"] = c["photo"]
            seen = next((x.get("start_en") for x in plan["scenes"] if x.get("start_photo") == c["photo"] and x.get("start_en")), None)
            if seen:
                s["start_en"] = seen
    else:
        if c.get("sing_model") and s.get("model") == c["sing_model"]:
            s.pop("model")
        if c.get("photo") and s.get("start_photo") == c["photo"]:   # it leaves the singer's photo too: Ref2VA holds the face, the place is the scene's
            s.pop("start_photo")
            s.pop("start_en", None)


def _clip_brief(plan: dict) -> str:
    c = plan["clip"]
    return (f"Idea ({client.lang()}): {plan['idea'] or '(no idea: invent a music video that fits the song)'}\n"
            f"The song: «{c.get('name', '')}», {c.get('bpm', 0):.0f} BPM; the video is {plan['seconds']:.0f} s of it, "
            f"{len(plan['scenes'])} scenes.\n"
            f"Mood: {plan.get('mood') or 'as the song suggests'}.\n"
            f"The song's parts (times in the video):\n{c.get('map', '')}\n")


def _scene_schema(mode: str, clip: bool = False, plan: Optional[dict] = None) -> dict:
    props = {
        **({"shot": {"type": "string", "enum": list(SHOTS if mode != "none" else SHOTS_NONE)}} if clip else {}),
        "ru": {"type": "string"},
        "beats_en": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
        "framing": {"type": "string", "enum": list(prompts.FRAMING)},
        "camera": {"type": "string", "enum": cameras(plan)},
        "sound_en": {"type": "string"},
        "place_en": {"type": "string"},
    }
    if mode == "none":
        props["to_en"] = {"type": "string"}
    if mode == "several":
        props["who"] = {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 3}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _cast_item() -> dict:
    props = {"gender": {"type": "string", "enum": GENDERS}, "age": {"type": "integer"}, "en": {"type": "string"},
             "outfit_en": {"type": "string"}, "ru": {"type": "string"}, "outfit_ru": {"type": "string"}}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _plan_schema(mode: str, n: int, cast_count: Optional[tuple[int, int]], plan: Optional[dict] = None) -> dict:
    props: dict = {"title_ru": {"type": "string"}, "style_en": {"type": "string"}, "audio_en": {"type": "string"}}
    if mode == "none":
        world = {"en": {"type": "string"}, "ru": {"type": "string"}}
        props["world"] = {"type": "object", "properties": world, "required": list(world), "additionalProperties": False}
    elif cast_count:
        props["cast"] = {"type": "array", "items": _cast_item(), "minItems": cast_count[0], "maxItems": cast_count[1]}
    props["scenes"] = {"type": "array", "items": _scene_schema(mode, plan=plan), "minItems": n, "maxItems": n}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _system(plan: dict) -> str:
    """The writer's rules; a clip's scenes are not 5 s each, nor are a 10 s grid's (plan.scene_seconds: the H3 rules
    stay word for word, and so its answers in the LLM cache). A plan of formula 2 (prompts.formula) gets its rules too."""
    if not plan.get("clip"):
        n = float(plan.get("scene_seconds") or SCENE_SECONDS)
        if n == SCENE_SECONDS:
            return SYSTEM + _rules_v2(plan)
        return SYSTEM.replace("Every scene is exactly 5 seconds; the model",
                              f"Every scene is {n:g} seconds (the last one may be shorter; each scene's length is given with it); the model").replace(
            "Five seconds hold about three small beats", f"{n:g} seconds hold up to three beats, each given its time") + _rules_v2(plan)
    return SYSTEM.replace("Every scene is exactly 5 seconds; the model", "Every scene has its own length, given with it; the model").replace(
        "Five seconds hold about three small beats", "A scene holds about one small beat for every 2 seconds") + _rules_v2(plan)


# Formula 2 (prompts.formula, new plans): a continuation starts on the last frame of the scene before, so another
# framing there is a cut or a long zoom inside 5 s (147 of 232 continuations had one, 2026-10-30); _take_scene holds it
CONTINUE_RULE = ('\n- A "continue" scene keeps the framing of the scene it goes on from (it starts on that very frame); '
                 "to get closer use the camera push_in, to get wider pull_back.")


def _rules_v2(plan: dict) -> str:
    return CONTINUE_RULE if prompts.formula(plan) >= 2 else ""


# Formula 2: a singing scene's start frame is drawn from its first beat (frames.prompt_of), and LTX sings surely only
# from a face to the camera with the mouth open
SING_FIRST_BEAT = ('\n- The first beat of a "sing" scene faces the camera, eyes open, singing: never in profile, never '
                   "with the eyes closed or the head thrown back.")


# Formula 3: LTX sang from the frame as a still picture (one body movement in time keeps it alive), and waving arms or
# a thing in the hands smeared - the hands and the thing swam (the user, 2026-10-30; prompts.hand_problems checks it)
SING_BODY = ('\n- A "sing" scene: one body movement in time with the music - a nod, a sway of the shoulders, a step toward '
             "the camera - the face toward the camera.")
HANDS_RULE = ('\n- In "sing" and "perform" scenes the hands stay empty and below the shoulders: no waving, no arms raised or '
              "above the head, nothing held in the hands, no spinning around. The movement is a sway, a turn of the head, the "
              "shoulders, the hair in the wind, a step toward the camera.")


def _clip_rules(plan: dict) -> str:
    rules = CLIP_RULES[plan["mode"] == "none"]
    if plan["mode"] == "none" or prompts.formula(plan) < 2:
        return rules
    return rules + SING_FIRST_BEAT + (SING_BODY + HANDS_RULE if prompts.formula(plan) >= 3 else "")


def cameras(plan: Optional[dict]) -> list[str]:
    """The cameras the writer may pick: the handheld one from formula 3 (an older plan's schema stays word for word,
    and so its answers in the LLM cache), for a clip's live action only - a storyboard's scenes don't need it, and in
    anime or 3D animation it jumped and pulled away from the drawing (prompts.stylized)."""
    return [c for c in prompts.CAMERAS if c != "handheld" or (plan is not None and prompts.formula(plan) >= 3 and _hand_ok(plan))]


def _hand_ok(plan: dict) -> bool:
    """Formula 3's handheld camera for singers: a clip in live action (the plan's style once it is written)."""
    return bool(plan.get("clip")) and not prompts.stylized(plan)


# Phase 10: the writer knows the model that shoots (plan["video"], the project's video model; none or H3 - the brief
# as it always was, so H3's answers stay in the LLM cache). What each does well and badly, from their makers' guides
# and our shots.
MODEL_NOTES = {
    "ltx25": "The video is shot by LTX-2.5 (Lightricks), not H3. It shows one clear action per beat well and moves the camera "
             "smoothly; it holds no face from words alone from scene to scene, so give the people few, strong visual traits "
             "and repeat them in beats; fast action and crowds smear. It speaks the lines in Russian with lip movement.",
    "ltx23": "The video is shot by LTX-2.3 (Lightricks), not H3. It shows one clear action per beat well and moves the camera "
             "smoothly; it holds no face from words alone from scene to scene, so give the people few, strong visual traits "
             "and repeat them in beats; fast action and crowds smear. It speaks the lines in Russian with lip movement.",
    "wan5b": "The video is shot by WAN 2.2 5B, not H3. It makes NO sound and nobody speaks: no dialogue, sound_en is only a "
             "note. Slow, simple, continuous motion of one subject works best; avoid crowds, fast action and big camera "
             "moves - a static or slowly moving camera.",
}


def _model_note(plan: dict) -> str:
    note = MODEL_NOTES.get("wan5b" if str(plan.get("video")).startswith("wan5b") else plan.get("video") or "h3")
    return f"Video model: {note}\n" if note else ""


def _brief(plan: dict) -> str:
    if plan.get("clip"):
        return _clip_brief(plan) + _model_note(plan)
    music = plan.get("music") or NO_MUSIC
    length = (f"Length: {len(plan['scenes'])} scenes x {SCENE_SECONDS} s = {len(plan['scenes']) * SCENE_SECONDS} s.\n" if not plan.get("scene_seconds")
              else f"Length: {len(plan['scenes'])} scenes, {plan['seconds']:g} s in all (each scene's seconds are given with it).\n")
    return (f"Idea ({client.lang()}): {plan['idea']}\n" + length +
            f"Mood: {plan.get('mood') or 'as the idea suggests'}.\n"
            f"Music: {music}. audio_en describes the music and the overall soundscape of the whole video in one sentence.\n"
            + _model_note(plan))


def _outline_text(plan: dict, want: set[int]) -> str:
    """The chapters of the outline (a long video) that the scenes being written belong to (a clip's: its song's
    parts, `chapter` on the scene)."""
    chapters = plan.get("outline") or []
    chains = sorted({plan["scenes"][i].get("chapter", plan["scenes"][i]["chain"]) for i in want})
    lines = [f"chapter {c + 1} (scenes {chapters[c]['first'] + 1}-{chapters[c]['last'] + 1}): {chapters[c]['en']}"
             + (f" [place: {chapters[c]['place_en']}]" if chapters[c].get("place_en") else "")
             for c in chains if c < len(chapters)]
    return "\n".join(lines)


def _grid_text(plan: dict, only: Optional[set[int]] = None) -> str:
    lines = []
    for s in plan["scenes"]:
        if only is not None and s["index"] not in only:
            continue
        if plan.get("clip"):
            lines.append(_clip_line(s))
            continue
        src = prompts.from_of(plan, s)
        lines.append(f"scene {s['index'] + 1} ({s['start']:g}-{s['end']:g} s): {s['kind']}"
                     + (" - opens a new shot" if s["kind"] == "new" and s["index"] else "")
                     + (f" - goes on from the end of scene {src['index'] + 1}, not of the scene before it"
                        if src is not None and src["index"] != s["index"] - 1 else "") + _start_note(s))
    return "\n".join(lines)


def _start_note(s: dict) -> str:
    """A new scene that starts from the user's photo (prompts.starts_from_photo): the writer must begin from it."""
    if not prompts.starts_from_photo(s):
        return ""
    seen = s.get("start_en") or "(not described yet)"
    return (f" - STARTS FROM THE USER'S PHOTO: second 0 is exactly this picture: {seen} Begin from that very moment,"
            " pose and place and let the action grow out of it; place_en is that place.")


async def describe_starts(llm: client.Client, plan: dict, folder: Path, only: Optional[set[int]] = None,
                          again: bool = False) -> None:
    """Read the start photos the writer has not seen yet (or `again`): start_en, and place_en for the scene."""
    for s in plan["scenes"]:
        if not prompts.starts_from_photo(s) or (only is not None and s["index"] not in only) or (s.get("start_en") and not again):
            continue
        path = folder / s["start_photo"]
        if path.exists():
            d = await describe.describe_frame_with(llm, path)
            s["start_en"] = d["en"]
            if d["place_en"]:
                s["place_en"] = d["place_en"]


LONG = 16      # scenes; a longer video is written from an outline, in batches (write_long)
WINDOW = 4    # on a long video a rewrite sees this many scenes around the ones it writes, not the whole film
BATCH = 8     # scenes per call when writing / fixing a long video


def _near(plan: dict, want: set[int]) -> Optional[set[int]]:
    """On a long video: the indices within WINDOW of the scenes being written; None = all (a short video)."""
    if len(plan["scenes"]) <= LONG:
        return None
    return {j for i in want for j in range(i - WINDOW, i + WINDOW + 1)}


def _context(plan: dict, skip: set[int]) -> str:
    """The scenes that stay as they are, so a rewrite fits between them (on a long video only the neighbours)."""
    out, near = [], _near(plan, skip)
    for s in plan["scenes"]:
        if s["index"] in skip or not s.get("beats_en") or (near is not None and s["index"] not in near):
            continue
        out.append(f"scene {s['index'] + 1} ({s['kind']}): " + " ".join(s["beats_en"])
                   + (f" [place: {s['place_en']}]" if s["kind"] == "new" and s.get("place_en") else "")
                   + (f" [who: {', '.join(map(str, s['who']))}]" if s.get("who") else "")
                   + (f" [ends with: {s['to_en']}]" if s.get("to_en") else ""))
    return "\n".join(out)


def _locks_text(plan: dict) -> str:
    if plan["mode"] == "none":
        return "World: " + plan.get("world", {}).get("en", "")
    return "\n".join(f"Character {i + 1}: {c['en']} Outfit: {c.get('outfit_en', '')}" for i, c in enumerate(plan.get("cast") or []))


def _take_scene(plan: dict, index: int, d: dict) -> None:
    s = plan["scenes"][index]
    if plan["mode"] == "several" and isinstance(d.get("who"), list):
        n = len(plan.get("cast") or [])
        s["who"] = sorted({int(x) for x in d["who"] if isinstance(x, (int, float)) and 1 <= int(x) <= n})
    for k in ("ru", "beats_en", "framing", "camera", "sound_en", "place_en", "to_en"):
        if k in d:
            s[k] = [b.strip() for b in d[k] if b.strip()] if k == "beats_en" else str(d[k]).strip()
    if s["kind"] == "continue":
        s["place_en"] = ""   # a continuation has no place of its own: compose takes its chain's (or the previous to_en)
    if prompts.formula(plan) >= 2:
        _hold_framing(plan, s)
        if plan.get("clip"):
            s["sound_en"] = ""   # the song is the clip's sound; "her voice singing" here opened H3's mouths (CLIP_RULES asks for "" too)
    if plan.get("clip"):   # a shot kind the user picked, or of a scene the user wrote (the clip's skeleton), stays theirs
        clip_shot(plan, s, s.get("shot") if s.get("shot_user") or s.get("source") == "user" else d.get("shot"))
    s["source"] = "llm"


def _hold_framing(plan: dict, s: dict) -> None:
    """Formula 2: a continuation starts on its source's last frame, so it keeps the source's framing; the writer's
    closer or wider one becomes the camera's push-in or pull-back (CONTINUE_RULE)."""
    src = prompts.from_of(plan, s)
    order = list(prompts.FRAMING)   # wide, medium, close
    if src is None or src.get("framing") not in order or s.get("framing") not in order:
        return
    want, have = order.index(s["framing"]), order.index(src["framing"])
    s["framing"] = src["framing"]
    if want != have:
        s["camera"] = "push_in" if want > have else "pull_back"


def check(plan: dict) -> list[int]:
    """Validate every scene, compose its prompt; the indices that fail."""
    bad = []
    for s in plan["scenes"]:
        if prompts.is_raw(s):   # the user's own prompt: nothing to check but that it is there
            s["locked"] = True
            s["problems"] = [] if prompts.is_written(s) else ["the prompt is empty"]
        else:
            s["problems"] = prompts.scene_problems(plan, s)
            if s["problems"]:
                bad.append(s["index"])
            s["problems"] += prompts.line_problems(plan, s)   # the user's to fix: not a reason to rewrite the scene
            # the writer has not read the start photo: the text describes another place and pose, and H3 cuts away from
            # the photo to it with a new face (2026-10-22, «Танец под грозу»). Only the user's button fixes it - not
            # sent back to the writer
            if prompts.starts_from_photo(s) and not s.get("start_en"):
                s["problems"].append("the scene starts from a photo the writer has not seen")
        s["problems_ru"] = [prompts.problem_ru(x) for x in s["problems"]]
        s["prompt"] = prompts.compose(plan, s)
    # the look and the style go into no prompt when every scene has its own (a clip imported from Remiqora): no warnings
    own = plan.get("manual") or all(prompts.is_raw(s) for s in plan.get("scenes") or [])
    plan["cast_problems"] = [] if own else prompts.cast_problems(plan) + prompts.style_problems(plan)
    plan["cast_problems_ru"] = [prompts.problem_ru(x) for x in plan["cast_problems"]]
    return bad


async def _fix_looks(llm: client.Client, plan: dict, seed: int) -> None:
    """The style and the cast / world, asked again once when they fail (a photo's hero is never touched)."""
    if not (prompts.cast_problems(plan) + prompts.style_problems(plan)):
        return
    mode = plan["mode"]
    props: dict = {"style_en": {"type": "string"}}
    keep = [c for c in plan.get("cast") or [] if c.get("from_photo") or c.get("from_user")]   # the user's look: theirs
    others = [c for c in plan.get("cast") or [] if not (c.get("from_photo") or c.get("from_user"))]
    if mode == "none":
        props["world"] = {"type": "object", "properties": {"en": {"type": "string"}, "ru": {"type": "string"}},
                          "required": ["en", "ru"], "additionalProperties": False}
    elif others:
        props["cast"] = {"type": "array", "items": _cast_item(), "minItems": len(others), "maxItems": len(others)}
    schema = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    now = {"style_en": plan.get("style_en", ""), **({"world": plan.get("world")} if mode == "none" else {"cast": others})}
    user = (_brief(plan) + "\n" + MODE_RULES[mode] + "\n\nNow:\n" + json.dumps(now, ensure_ascii=False, indent=1)
            + "\n\nProblems to fix:\n" + "\n".join(prompts.cast_problems(plan) + prompts.style_problems(plan))
            + "\n\nRewrite these fields so they pass; keep who the characters are and what the video looks like.")
    d = await llm.chat_json(_system(plan), user, schema, temperature=0.6, seed=seed, max_tokens=1200)
    plan["style_en"] = str(d.get("style_en") or plan.get("style_en", "")).strip()
    if mode == "none":
        plan["world"] = d.get("world") or plan["world"]
    elif others and d.get("cast"):
        plan["cast"] = keep + list(d["cast"])
        prompts.fix_cast(plan)


async def _rewrite(llm: client.Client, plan: dict, indices: list[int], why: dict[int, list[str]], how: str, seed: int,
                   different: bool = False, ru_only: bool = False) -> None:
    """Rewrite some scenes in one call, the rest of the plan given as fixed context. `different`: the current text is
    shown as what not to repeat (otherwise a small model hands the same scene back). `ru_only`: only the Russian text
    is shown - the English must follow it, and with the old English in sight a small model just keeps it."""
    want = set(indices)
    item = _scene_schema(plan["mode"], bool(plan.get("clip")), plan)
    item = {**item, "properties": {"scene": {"type": "integer"}, **item["properties"]}, "required": ["scene", *item["required"]]}
    schema = {"type": "object", "properties": {"scenes": {"type": "array", "items": item, "minItems": len(want), "maxItems": len(want)}},
              "required": ["scenes"], "additionalProperties": False}
    label = "old version, do NOT repeat its actions or wording" if different else "the user's Russian text" if ru_only else "now"
    keys = ("ru",) if ru_only else ("ru", "beats_en", "place_en", "to_en")
    current = "\n".join(f"scene {i + 1} {label}: " + json.dumps({k: plan["scenes"][i].get(k) for k in keys},
                                                             ensure_ascii=False) for i in sorted(want))
    problems = "\n".join(f"scene {i + 1}: " + "; ".join(p) for i, p in why.items() if p)
    user = (_brief(plan) + "\n" + MODE_RULES[plan["mode"]] + (("\n" + _clip_rules(plan)) if plan.get("clip") else "")
            + "\n\n" + _locks_text(plan)
            + f"\nStyle: {plan.get('style_en', '')}\n\n" + ("The whole video:\n" + _grid_text(plan) if _near(plan, want) is None
               else f"The video has {len(plan['scenes'])} scenes; around these ones:\n" + _grid_text(plan, _near(plan, want)))
            + (f"\n\nThe story of these scenes (follow it):\n{_outline_text(plan, want)}" if plan.get("outline") else "")
            + "\n\nScenes that stay as they are:\n" + (_context(plan, want) or "(none)")
            + f"\n\n{how}\n" + current + (f"\n\nProblems to fix:\n{problems}" if problems else "")
            + f"\n\nAnswer with scenes {', '.join(str(i + 1) for i in sorted(want))} (field scene = its number).")
    d = await llm.chat_json(_system(plan), user, schema, temperature=1.0 if different else 0.8, seed=seed,
                            max_tokens=500 * len(want) + 200)
    got = d.get("scenes", [])
    order = sorted(want)
    numbers = [int(s.get("scene", 0)) - 1 for s in got]
    if sorted(numbers) != order:   # a small model numbers its answer 1, 2... whatever was asked: take them in order
        numbers = order[: len(got)]
    for i, s in zip(numbers, got):
        _take_scene(plan, i, s)


async def _fix_round(llm: client.Client, plan: dict, seed: int, only: Optional[set[int]] = None) -> None:
    """Validate; the failing scenes go back once with their problems; what still fails stays marked.
    `only`: a rewrite of some scenes may fix just those - not the style or the cast (that would change every scene's
    prompt and throw the whole shot cache away), not other scenes, never a locked one."""
    if only is None:
        await _fix_looks(llm, plan, seed + 2)
    bad = [i for i in check(plan) if (only is None or i in only) and not plan["scenes"][i].get("locked")]
    for k in range(0, len(bad), BATCH):   # a long video can have dozens: a few per call
        part = bad[k:k + BATCH]
        await _rewrite(llm, plan, part, {i: plan["scenes"][i]["problems"] for i in part},
                       "Rewrite these scenes so they pass the rules; keep what the scene is about.", seed + 1 + k)
    if bad:
        check(plan)
    for s in plan["scenes"]:
        s["status"] = "check" if s["problems"] else "ok"


# Phase 2's open point: the writer picks "static" for nearly every scene though asked to vary (gemma: 14 of 16). A new
# storyboard with more than half static gets every other static scene a calm move by what happens in it - someone
# walking or running: alongside; a close shot: a slow push-in; else in turn the calm ones. WAN keeps its static camera
# (its note asks for it); a clip has its own (planner/clip.vary_cameras).
_WALK = re.compile(r"\b(walk|walks|walking|run|runs|running|stride|strides|steps?|rides?|riding|drives?|driving)\b", re.I)
_CALM = ("push_in", "pan", "pull_back", "orbit", "rise")


def vary_cameras(plan: dict) -> None:
    if plan.get("clip") or str(plan.get("video")).startswith("wan5b"):
        return
    scenes = plan.get("scenes") or []
    static = [x for x in scenes if x.get("camera") == "static" and not x.get("locked")]
    if len(static) * 2 <= len(scenes):
        return
    k = 0
    for x in static[1::2]:
        if _WALK.search(" ".join(x.get("beats_en") or [])):
            x["camera"] = "track_side"
        elif x.get("framing") == "close":
            x["camera"] = "push_in"
        else:
            x["camera"] = _CALM[k % len(_CALM)]
            k += 1


def new_plan(idea: str, seconds: float, mode: str, mood: str = "", music: str = "", hero: Optional[dict] = None,
             seed: int = 1, model: Optional[str] = None, scene_seconds: float = SCENE_SECONDS) -> dict:
    """An empty storyboard on the grid. `scene_seconds`: the video model's scene (videomodels.Card.grid_seconds) - 10 s
    for LTX; the plan then keeps it (`scene_seconds`: a scene added later gets it, the writer is told)."""
    slots = grid(seconds, mode, scene_seconds)
    plan = {"idea": idea.strip(), "seconds": slots[-1].end, "mode": mode, "mood": mood, "music": music, "lang": i18n.text(),
            "seed": seed, "model": model, "title_ru": "", "style_en": "", "audio_en": "", "prompt_v": prompts.PROMPT_V,
            "scenes": [{**s.public(), "ru": "", "beats_en": [], "framing": "medium", "camera": "static", "sound_en": "",
                        "place_en": "", "to_en": "", "locked": False, "source": "", "status": "", "problems": [], "prompt": ""}
                       for s in slots]}
    if scene_seconds != SCENE_SECONDS:
        plan["scene_seconds"] = scene_seconds
    if mode == "none":
        plan["world"] = {"en": "", "ru": ""}
    else:
        plan["cast"] = [hero] if hero else []
    return plan


async def write(plan: dict, photo: Optional[Path] = None, folder: Optional[Path] = None) -> dict:
    """Fill a fresh plan (new_plan) in one call + one fixing round. `photo`: the hero's photo, described first in the
    same model load (people modes only). `folder`: the project's, where the scenes' start photos are."""
    client.use_lang(i18n.plan_lang_name(plan))   # the video's language (i18n.plan_lang)
    t0 = time.time()
    mode, n = plan["mode"], len(plan["scenes"])
    if n > LONG:
        return await write_long(plan, photo, folder)
    async with client.session(plan.get("model")) as llm:
        if folder:
            await describe_starts(llm, plan, folder)
        if photo and mode != "none" and not plan.get("cast"):
            h = await describe.describe_with(llm, photo)
            plan["cast"] = [{**{k: h.get(k, "") for k in ("gender", "age", "en", "outfit_en", "ru", "outfit_ru")}, "from_photo": True}]
        hero = (plan.get("cast") or [None])[0] if mode != "none" else None
        cast_count = None
        if mode == "one" and not hero:
            cast_count = CAST_COUNT["one"]
        elif mode == "several":
            cast_count = (1, 2) if hero else CAST_COUNT["several"]
        user = _brief(plan) + "\n" + MODE_RULES[mode]
        if hero:
            user += ("\n\nCharacter 1 is fixed from the user's photo, do not change or repeat it" + (", list only the others in cast" if mode == "several" else "")
                     + f":\n{hero['en']} Outfit: {hero.get('outfit_en', '')}")
        user += "\n\nThe scenes (fixed, write exactly one entry per line, in order):\n" + _grid_text(plan)
        d = await llm.chat_json(_system(plan), user, _plan_schema(mode, n, cast_count, plan), temperature=0.8, seed=plan["seed"],
                                max_tokens=420 * n + 900)
        for k in ("title_ru", "style_en", "audio_en"):
            plan[k] = str(d.get(k, "")).strip()
        if mode == "none":
            plan["world"] = d.get("world") or plan["world"]
        elif cast_count:
            plan["cast"] = ([hero] if hero else []) + list(d.get("cast") or [])
        prompts.fix_cast(plan)
        for i, s in enumerate(d.get("scenes", [])[:n]):
            _take_scene(plan, i, s)
        await _fix_round(llm, plan, plan["seed"])
        vary_cameras(plan)
        plan["writer"] = {"model": llm.model.name, "seconds": round(time.time() - t0, 1), "calls": llm.calls, "cached": llm.cached}
    return plan


OUTLINE_RULES = """This is a long film. First write its outline: one chapter per chain of scenes (a chain is a "new"
scene and the continuations after it - one place, one continuous moment). The chapters together tell the whole story like
a feature film: a strong opening, rising action, turns, a climax and an ending, never repeating themselves. Each chapter:
en - 1-2 English sentences, what happens in it, concrete and visual; ru - the same in Russian; place_en - where it happens
(one sentence: place, light, time of day). Change places, scale and rhythm between chapters like a film editor would."""


def _outline_schema(mode: str, chains: int, cast_count: Optional[tuple[int, int]]) -> dict:
    ch = {"en": {"type": "string"}, "ru": {"type": "string"}, "place_en": {"type": "string"}}
    props: dict = {"title_ru": {"type": "string"}, "style_en": {"type": "string"}, "audio_en": {"type": "string"},
                   "chapters": {"type": "array", "items": {"type": "object", "properties": ch, "required": list(ch),
                                                           "additionalProperties": False}, "minItems": chains, "maxItems": chains}}
    if mode == "none":
        world = {"en": {"type": "string"}, "ru": {"type": "string"}}
        props["world"] = {"type": "object", "properties": world, "required": list(world), "additionalProperties": False}
    elif cast_count:
        props["cast"] = {"type": "array", "items": _cast_item(), "minItems": cast_count[0], "maxItems": cast_count[1]}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


async def write_long(plan: dict, photo: Optional[Path] = None, folder: Optional[Path] = None) -> dict:
    """A long video (more than LONG scenes, up to 15 min): an outline first - the cast or world, the style and one
    chapter per chain - then the scenes in batches of about BATCH, each batch seeing its chapters and its neighbours,
    then the fixing round in batches. One model load for all of it."""
    client.use_lang(i18n.plan_lang_name(plan))   # the video's language (i18n.plan_lang)
    t0 = time.time()
    mode, n = plan["mode"], len(plan["scenes"])
    chains = sorted({s["chain"] for s in plan["scenes"]})
    async with client.session(plan.get("model")) as llm:
        if folder:
            await describe_starts(llm, plan, folder)
        if photo and mode != "none" and not plan.get("cast"):
            h = await describe.describe_with(llm, photo)
            plan["cast"] = [{**{k: h.get(k, "") for k in ("gender", "age", "en", "outfit_en", "ru", "outfit_ru")}, "from_photo": True}]
        hero = (plan.get("cast") or [None])[0] if mode != "none" else None
        cast_count = None
        if mode == "one" and not hero:
            cast_count = CAST_COUNT["one"]
        elif mode == "several":
            cast_count = (1, 2) if hero else CAST_COUNT["several"]
        spans = []
        for c in chains:
            idx = [s["index"] for s in plan["scenes"] if s["chain"] == c]
            spans.append((c, idx[0], idx[-1]))
        user = (_brief(plan) + "\n" + MODE_RULES[mode] + "\n\n" + OUTLINE_RULES
                + f"\n\nThe film has {n} scenes in {len(chains)} chains:\n"
                + "\n".join(f"chapter {c + 1}: scenes {a + 1}-{b + 1} ({sum(grid_seconds(plan['scenes'][i]) for i in range(a, b + 1)):g} s)" for c, a, b in spans))
        if hero:
            user += (f"\n\nCharacter 1 is fixed from the user's photo, do not change it:\n{hero['en']} Outfit: {hero.get('outfit_en', '')}")
        d = await llm.chat_json(_system(plan), user, _outline_schema(mode, len(chains), cast_count), temperature=0.8,
                                seed=plan["seed"], max_tokens=140 * len(chains) + 1600)
        for k in ("title_ru", "style_en", "audio_en"):
            plan[k] = str(d.get(k, "")).strip()
        if mode == "none":
            plan["world"] = d.get("world") or plan["world"]
        elif cast_count:
            plan["cast"] = ([hero] if hero else []) + list(d.get("cast") or [])
        prompts.fix_cast(plan)
        got = d.get("chapters") or []
        plan["outline"] = [{"chain": c, "first": a, "last": b, **{k: str((got[k_i] if k_i < len(got) else {}).get(k, "")).strip()
                                                                    for k in ("en", "ru", "place_en")}}
                           for k_i, (c, a, b) in enumerate(spans)]
        # the scenes, a couple of chapters at a time
        batch: list[int] = []
        for c, a, b in spans:
            batch += list(range(a, b + 1))
            if len(batch) >= BATCH or c == spans[-1][0]:
                await _rewrite(llm, plan, batch, {}, "Write these scenes, following their chapters of the story; the beats of a "
                               "continuation go on from the scene before it.", plan["seed"] + 10 + batch[0])
                for i in batch:   # a new scene without a place takes its chapter's
                    sc = plan["scenes"][i]
                    if sc["kind"] == "new" and not sc.get("place_en"):
                        sc["place_en"] = plan["outline"][sc["chain"]].get("place_en", "")
                batch = []
        await _fix_round(llm, plan, plan["seed"])
        vary_cameras(plan)
        plan["writer"] = {"model": llm.model.name, "seconds": round(time.time() - t0, 1), "calls": llm.calls,
                          "cached": llm.cached, "long": True}
    return plan


def clip_chapters(scenes: list[dict]) -> list[dict]:
    """A clip's parts: runs of scenes of one part of the song (its kind, the chorus) - the treatment's lines."""
    out: list[dict] = []
    for s in scenes:
        key = (s.get("part"), bool(s.get("chorus")))
        if out and out[-1]["key"] == key:
            out[-1]["last"] = s["index"]
            out[-1]["end"] = s["end"]
        else:
            out.append({"key": key, "part": s.get("part"), "loud": bool(s.get("loud")), "first": s["index"], "last": s["index"],
                        "start": s["start"], "end": s["end"]})
    for c in out:
        c.pop("key")
    return out


def new_clip_plan(idea: str, mode: str, mood: str, song_info: dict, slots: list[dict], seed: int = 1,
                  model: Optional[str] = None) -> dict:
    """A clip's plan before the writer: the scenes cut on the song (planner/clip.py), each "new" with its own length.
    `song_info`: {song, name, from, to, bpm, bar_s} - the song's id and the fragment in its time."""
    scenes, t = [], 0.0
    for i, x in enumerate(slots):
        scenes.append({"index": i, "kind": "new", "chain": i, "start": round(t, 4), "end": round(t + x["seconds"], 4), **x,
                       "ru": "", "beats_en": [], "framing": "medium", "camera": "static", "sound_en": "", "place_en": "",
                       "to_en": "", "locked": False, "source": "", "status": "", "problems": [], "prompt": ""})
        t += x["seconds"]
    for k, c in enumerate(clip_chapters(scenes)):
        for s in scenes[c["first"]: c["last"] + 1]:
            s["chapter"] = k
    plan = {"idea": idea.strip(), "seconds": round(t, 3), "mode": mode, "mood": mood, "music": "", "seed": seed, "model": model, "lang": i18n.text(),
            "title_ru": "", "style_en": "", "audio_en": "", "no_music": True, "clip": {**song_info}, "scenes": scenes,
            "prompt_v": prompts.PROMPT_V}
    plan["clip"]["map"] = _song_map(plan)
    from ..planner.clip import PREROLL
    plan["clip"]["preroll"] = PREROLL   # a new clip only: its scenes from a picture are shot longer, their warm-up cut (render.preroll)
    if mode == "none":
        plan["world"] = {"en": "", "ru": ""}
    else:
        plan["cast"] = []
    return plan


def _song_map(plan: dict) -> str:
    rows = []
    for c in clip_chapters(plan["scenes"]):
        part = plan["scenes"][c["first"]: c["last"] + 1]
        sung = [x["text"] for s in part for x in s.get("sung") or []]
        sung = list(dict.fromkeys(sung))
        rows.append(f"{_mmss(c['start'])}-{_mmss(c['end'])} {'chorus' if part[0].get('chorus') else c['part']}, "
                    f"{'loud' if c['loud'] else 'quiet'}: " + (" / ".join(sung)[:300] if sung else "no singing"))
    return "\n".join(rows)


TREATMENT_RULES = """First write the TREATMENT of the music video: format_en - one or two sentences: the format (performance, story, metaphor or a mix of performance and story), the palette and light, and one visual motif that grows through the video (a spark in the verse becomes a fire in the chorus); then one chapter per part of the song, in order: en - 1-2 English sentences, what happens in this part, concrete and visual, the strongest images on the chorus and the loud parts; ru - the same in Russian; place_en - where (one sentence: place, light, time of day). Keep to 2-3 places in the whole video and return to them."""


def _treatment_schema(mode: str, chapters: int, cast_count: Optional[tuple[int, int]]) -> dict:
    s = _outline_schema(mode, chapters, cast_count)
    s["properties"]["format_en"] = {"type": "string"}
    s["required"] = list(s["properties"])
    return s


TRANSLATE_ASK = ("The user rewrote the Russian text (ru) of these scenes. Write the English fields so they show exactly "
                 "what the Russian says, by the rules; keep ru exactly as the user wrote it.")
IDEA_AS_IS = ("The story is the user's idea, as it is: keep its events, people and places and their order, and spread them "
              "over the parts of the song; invent no other story.")


async def write_clip(plan: dict, photo: Optional[Path] = None, folder: Optional[Path] = None) -> dict:
    """Fill a clip's plan (new_clip_plan): the hero from the photo, then the treatment - the look, the people, one
    chapter per part of the song - then the scenes a few parts at a time, each with its shot kind, then the fixing
    round. A "sing" scene gets the words sung during it as its line (clip_shot). One model load for all of it.
    The user's control («Что пишет сценарист», the clip's skeleton): a scene with the user's own words (source "user")
    keeps them - only its English follows them, as «translate» does; a scene already written stays; only the rest are
    written. A look the user wrote (character 1 with words and no English yet, `from_user`) goes into English and is
    kept like a photo's; `clip.story` "idea" tells the writer to keep the user's idea as it is. The treatment is written
    once: a second run («Написать остальные») keeps it, the cast and the style."""
    client.use_lang(i18n.plan_lang_name(plan))   # the video's language (i18n.plan_lang)
    t0 = time.time()
    mode = plan["mode"]
    chapters = clip_chapters(plan["scenes"])
    scenes = plan["scenes"]
    mine = {i for i, s in enumerate(scenes) if s.get("source") == "user" and (s.get("ru") or "").strip()}
    typed = {i: scenes[i]["ru"] for i in mine if not prompts.is_written(scenes[i]) or scenes[i].get("ru_dirty")}
    todo = [i for i, s in enumerate(scenes) if i not in mine and not prompts.is_written(s)]
    first = not plan.get("outline")
    async with client.session(plan.get("model")) as llm:
        if folder:
            await describe_starts(llm, plan, folder)
        if photo and mode != "none" and not plan.get("cast"):
            h = await describe.describe_with(llm, photo)
            plan["cast"] = [{**{k: h.get(k, "") for k in ("gender", "age", "en", "outfit_en", "ru", "outfit_ru")}, "from_photo": True}]
        own = (plan.get("cast") or [None])[0] if mode != "none" else None
        if own and own.get("from_user") and own.get("ru_dirty"):   # «Опишу сам»: the user's look into English
            await rewrite_looks(plan, [0])
        hero = (plan.get("cast") or [None])[0] if mode != "none" else None
        if first:
            cast_count = None
            if mode == "one" and not hero:
                cast_count = CAST_COUNT["one"]
            elif mode == "several":
                cast_count = (1, 2) if hero else CAST_COUNT["several"]
            user = (_brief(plan) + "\n" + MODE_RULES[mode] + "\n" + _clip_rules(plan) + "\n\n" + TREATMENT_RULES
                    + (f"\n{IDEA_AS_IS}" if plan["clip"].get("story") == "idea" else "")
                    + f"\n\nThe parts ({len(chapters)} chapters, in order):\n"
                    + "\n".join(f"chapter {k + 1}: {_mmss(c['start'])}-{_mmss(c['end'])}, scenes {c['first'] + 1}-{c['last'] + 1}"
                                for k, c in enumerate(chapters)))
            if mode == "one" or mode == "several":
                user += "\nCharacter 1 is the singer of the song."
            if hero:
                user += (f"\n\nCharacter 1 is fixed, do not change it:\n{hero['en']} Outfit: {hero.get('outfit_en', '')}")
            if mine:   # the user's own scenes: the story goes through them
                user += ("\n\nThe user wrote these scenes themselves; the treatment must lead to them:\n"
                         + "\n".join(f"scene {i + 1}: {scenes[i]['ru']}" for i in sorted(mine)))
            d = await llm.chat_json(_system(plan), user, _treatment_schema(mode, len(chapters), cast_count), temperature=0.8,
                                    seed=plan["seed"], max_tokens=160 * len(chapters) + 1800)
            for k in ("title_ru", "style_en", "audio_en"):
                plan[k] = str(d.get(k, "")).strip()
            plan["clip"]["treatment_en"] = str(d.get("format_en", "")).strip()
            if mode == "none":
                plan["world"] = d.get("world") or plan["world"]
            elif cast_count:
                plan["cast"] = ([hero] if hero else []) + list(d.get("cast") or [])
            prompts.fix_cast(plan)
            got = d.get("chapters") or []
            plan["outline"] = [{"chain": k, "first": c["first"], "last": c["last"],
                                **{f: str((got[k] if k < len(got) else {}).get(f, "")).strip() for f in ("en", "ru", "place_en")}}
                               for k, c in enumerate(chapters)]
            if plan["clip"]["treatment_en"]:
                plan["outline"][0]["en"] = (plan["clip"]["treatment_en"] + " " + plan["outline"][0]["en"]).strip()
        batch: list[int] = []
        for k, c in enumerate(chapters):
            batch += list(range(c["first"], c["last"] + 1))
            if len(batch) >= BATCH or k == len(chapters) - 1:
                write = [i for i in batch if i in todo]
                if write:
                    await _rewrite(llm, plan, write, {}, "Write these scenes of the music video, following their chapters of the "
                                   "treatment; choose each one's shot by its part and its voice.", plan["seed"] + 10 + batch[0])
                own_words = [i for i in batch if i in typed]
                if own_words:
                    await _rewrite(llm, plan, own_words, {}, TRANSLATE_ASK, plan["seed"] + 20 + batch[0], ru_only=True)
                for i in write + own_words:   # a scene without a place takes its chapter's
                    sc = plan["scenes"][i]
                    if not sc.get("place_en") and sc.get("chapter") is not None and sc["chapter"] < len(plan["outline"]):
                        sc["place_en"] = plan["outline"][sc["chapter"]].get("place_en", "")
                    if "shot" not in sc:
                        clip_shot(plan, sc, None)
                batch = []
        for i, ru in typed.items():   # the user's words win over the writer's; the scene stays theirs, pinned
            scenes[i].update(ru=ru, ru_dirty=False, source="user", locked=True)
        from ..planner.clip import hand_held, vary_cameras
        # a written or the user's scene keeps its camera (and its shot)
        vary_cameras([scenes[i] for i in todo], prompts.formula(plan) >= 3 and _hand_ok(plan))
        await _fix_round(llm, plan, plan["seed"], only=None if first and not mine else set(todo) | set(typed))
        for i, ru in typed.items():   # the fixing round may have rewritten it
            scenes[i]["ru"] = ru
        if prompts.formula(plan) >= 3 and _hand_ok(plan):   # ...and the camera of a singing scene it sent back
            hand_held([scenes[i] for i in todo])
            check(plan)
        plan["writer"] = {"model": llm.model.name, "seconds": round(time.time() - t0, 1), "calls": llm.calls,
                          "cached": llm.cached, "clip": True}
    return plan


LOOKS_SYSTEM = """You write the English look of the people of a video for the video model MiniMax H3, from the user's Russian.
The text is pasted word for word into every scene, so it fixes how each person looks.
en: body and face only, 30-60 words: build, skin, face, eyes, hair (colour, length, style), notable features (freckles,
glasses, earrings, makeup). outfit_en: clothes, shoes and accessories, 10-30 words, colours and materials. Concrete visual
words, no feelings, no names. Keep everything the user wrote; add only plausible visual detail the Russian leaves open.
""" + LOOK_RULE

# a small model at times starts its answer with the rule it was given: «body and face only, 30-60 words: Athletic build...»
# (a 24B model) - and fix_cast then wrote «a 28-year-old woman with body and face only, 30-60 words: ...»
_ECHO = re.compile(r"^\s*(?:(?:outfit_)?en\s*:\s*)?[^:.]{0,70}\b\d+\s*-\s*\d+\s+words\s*:\s*", re.I)

WORLD_SYSTEM = """You write the English "world" of a video without people for the video model MiniMax H3, from the user's
Russian: the place and its look (setting, materials, palette, light), 25-60 words, concrete visual words. It is pasted
word for word into every scene. No people."""


async def translate_look(ru: str, gender: str = "", age: Optional[int] = None, model_id: Optional[str] = None) -> dict:
    """A graph's Hero written in Russian («Перевести на английский»): its English look and outfit, by the rules a
    storyboard's cast is written with (LOOKS_SYSTEM). Only by the button."""
    client.use_lang(i18n.text_name())   # the texts' language (i18n)
    schema = {"type": "object", "properties": {"en": {"type": "string"}, "outfit_en": {"type": "string"}},
              "required": ["en", "outfit_en"], "additionalProperties": False}
    who = ", ".join(x for x in (gender, f"{max(prompts.MIN_AGE, int(age))} years old" if age else "") if x) or "an adult"
    async with client.session(model_id) as llm:
        d = await llm.chat_json(LOOKS_SYSTEM, f"Person 1: {who}.\n  look and outfit ({client.lang()}): {ru.strip()}\n\nAnswer with people in the same order.",
                                {"type": "object", "properties": {"people": {"type": "array", "items": schema, "minItems": 1, "maxItems": 1}},
                                 "required": ["people"], "additionalProperties": False}, temperature=0.3, seed=1, max_tokens=800)
        got = (d.get("people") or [{}])[0]
        # a small model writes the outfit into the look too ("... glasses. outfit_en: Dark blue ..."): the look stops there
        en = re.split(r"\s*\boutfit(?:_en)?\s*:", str(got.get("en", "")), maxsplit=1, flags=re.I)[0].strip()
        return {"en": en, "outfit_en": str(got.get("outfit_en", "")).strip(), "model": llm.model.name}


async def rewrite_looks(plan: dict, indices: Optional[list[int]] = None, seed: Optional[int] = None) -> dict:
    """The user edited the Russian look of some characters (or the world): the English follows it. The Russian stays as
    typed, the age and gender as set; a character from a photo is translated too when the user changed it."""
    client.use_lang(i18n.plan_lang_name(plan))   # the video's language (i18n.plan_lang)
    seed = seed if seed is not None else int(time.time()) % 100000
    t0 = time.time()
    async with client.session(plan.get("model")) as llm:
        if plan["mode"] == "none":
            w = plan.get("world") or {}
            schema = {"type": "object", "properties": {"en": {"type": "string"}}, "required": ["en"], "additionalProperties": False}
            d = await llm.chat_json(WORLD_SYSTEM, f"Idea: {plan.get('idea', '')}\nThe world ({client.lang()}): {w.get('ru', '')}", schema,
                                    temperature=0.4, seed=seed, max_tokens=600)
            plan["world"] = {**w, "en": str(d.get("en", "")).strip() or w.get("en", ""), "ru_dirty": False}
        else:
            cast = plan.get("cast") or []
            want = [i for i in (indices if indices is not None else range(len(cast))) if 0 <= i < len(cast)]
            item = {"type": "object", "properties": {"en": {"type": "string"}, "outfit_en": {"type": "string"}},
                    "required": ["en", "outfit_en"], "additionalProperties": False}
            schema = {"type": "object", "properties": {"people": {"type": "array", "items": item, "minItems": len(want), "maxItems": len(want)}},
                      "required": ["people"], "additionalProperties": False}
            user = (f"Idea ({client.lang()}): {plan.get('idea', '')}\nStyle: {plan.get('style_en', '')}\n\n"
                    + "\n".join(f"Person {k + 1}: {cast[i].get('gender', '')}, {cast[i].get('age', '')} years old.\n"
                                f"  look ({client.lang()}): {cast[i].get('ru', '')}\n  outfit ({client.lang()}): {cast[i].get('outfit_ru', '')}"
                                for k, i in enumerate(want))
                    + "\n\nAnswer with people in the same order.")
            d = await llm.chat_json(LOOKS_SYSTEM, user, schema, temperature=0.4, seed=seed, max_tokens=500 * len(want) + 200)
            for i, got in zip(want, d.get("people", [])):
                cast[i].update(en=_ECHO.sub("", str(got.get("en", ""))).strip() or cast[i].get("en", ""),
                               outfit_en=_ECHO.sub("", str(got.get("outfit_en", ""))).strip(), ru_dirty=False)
            prompts.fix_cast(plan)
        check(plan)
        for s in plan["scenes"]:
            s["status"] = "check" if s["problems"] else "ok"
        plan["writer"] = {"model": llm.model.name, "seconds": round(time.time() - t0, 1), "calls": llm.calls, "cached": llm.cached}
    return plan


async def rewrite_scenes(plan: dict, indices: list[int], how: str = "variant", seed: Optional[int] = None,
                         note: str = "", folder: Optional[Path] = None) -> dict:
    """The scene buttons. how: "improve" (keep the meaning, make it better), "variant" (a different version: a new answer
    seed), "unlocked" (every scene that is not locked, the locked ones as fixed context), "fill" (empty scenes the user
    added), "translate" (the user rewrote the Russian text: the English follows it, the Russian stays as typed), "frame"
    (the scene got a start photo: read it, then write the scene so it starts from that picture)."""
    client.use_lang(i18n.plan_lang_name(plan))   # the video's language (i18n.plan_lang)
    if how == "unlocked":
        indices = [s["index"] for s in plan["scenes"] if not s.get("locked")]
    indices = [i for i in indices if 0 <= i < len(plan["scenes"])]
    if not indices:
        return plan
    seed = seed if seed is not None else int(time.time()) % 100000
    ask = {"improve": "Improve these scenes: more concrete and visual, motion the video model can show well; keep what each is about.",
           "variant": "Write a different version of these scenes: another action and angle that still fits the video.",
           "unlocked": "Write these scenes anew; they must fit with the scenes that stay.",
           "fill": "Write these new scenes so they fit between the scenes that stay.",
           "translate": TRANSLATE_ASK,
           "frame": ("These scenes start from the user's photo (see STARTS FROM THE USER'S PHOTO above): write them so second 0 "
                     "is exactly that picture and the action grows out of it, while the scene still fits the video.")}[how]
    if note:
        ask += f"\nThe user's wish ({client.lang()}): {note}"
    typed = {i: plan["scenes"][i].get("ru", "") for i in indices} if how == "translate" else {}
    t0 = time.time()
    async with client.session(plan.get("model")) as llm:
        if folder:
            await describe_starts(llm, plan, folder, set(indices), again=how == "frame")
        await _rewrite(llm, plan, indices, {i: plan["scenes"][i].get("problems") or [] for i in indices}, ask, seed,
                       different=how in ("variant", "unlocked"), ru_only=how == "translate")
        for i, ru in typed.items():   # the user's words: the scene stays theirs, pinned
            plan["scenes"][i].update(ru=ru, ru_dirty=False, source="user", locked=True)
        await _fix_round(llm, plan, seed, only=set(indices))
        for i, ru in typed.items():   # the fixing round may have rewritten it: the user's words win
            plan["scenes"][i]["ru"] = ru
        plan["writer"] = {"model": llm.model.name, "seconds": round(time.time() - t0, 1), "calls": llm.calls, "cached": llm.cached}
    return plan


# ---------- «Обновить сюжет от этой сцены» ----------
# The user changed one scene; the rest of the story may no longer agree with it (who is where, what was found, how a
# chain ends). The writer names the scenes that must change and why, then only those are rewritten - not the whole
# storyboard as «Пересоздать незакреплённые» does (on 120 scenes that throws every shot away). A locked scene and
# one with the user's own prompt are never touched. What they were is kept (plan["propagated"]["before"]): one
# «Вернуть как было» puts every one of them back.
PROPAGATE_MAX = 6
PROPAGATE_TOKENS = 2400
PROPAGATE_KEYS = ("ru", "beats_en", "place_en", "to_en", "who", "framing", "camera", "sound_en", "source")


def _story_lines(plan: dict) -> str:
    """Every scene in a line - what happens (its text in the video's language, else its actions): a long video too,
    the writer must see the whole story to know what no longer fits."""
    return "\n".join(f"scene {s['index'] + 1} ({s['kind']}{', locked' if s.get('locked') else ''}): "
                     + (s.get("ru") or " ".join(s.get("beats_en") or []))[:240] for s in plan["scenes"])


def _propagate_ask(plan: dict, index: int) -> tuple[str, dict]:
    """The question of propagate(): the user's text and the answer's schema."""
    src = plan["scenes"][index]
    # strings "N: reason": a number and its reason can't come apart (the plainest shape for a small model)
    schema = {"type": "object", "properties": {"other_scenes": {"type": "array", "maxItems": PROPAGATE_MAX,
                                                                "items": {"type": "string", "maxLength": 320}}},
              "required": ["other_scenes"], "additionalProperties": False}
    changed = json.dumps({k: src.get(k) for k in ("ru", "beats_en", "place_en", "to_en", "who") if src.get(k)}, ensure_ascii=False)
    user = (_brief(plan) + "\n" + _locks_text(plan) + "\n\nThe whole story, scene by scene:\n" + _story_lines(plan)
            + f"\n\nThe user has just changed scene {index + 1}. It is now:\n{changed}\n\n"
            "Which OTHER scenes no longer agree with it - the people, the place, an object, what happened before or after, "
            "how a chain of scenes continues? Name only scenes that really contradict it now, at most "
            f"{PROPAGATE_MAX}; none is a fine answer. Never name a locked scene or scene {index + 1} itself. "
            f"Each item is one line: the scene's number, a colon, the reason in one English sentence "
            f"(e.g. \"9: they embrace, but in scene {index + 1} she has left\").")
    return user, schema


async def propagate(plan: dict, index: int, seed: Optional[int] = None) -> dict:
    """Scene `index` as the user left it: the scenes it makes wrong rewritten to agree with it. -> the plan, with
    plan["propagated"] = {from: scene id, n: its number, scenes: [{index, id, reason}], before: {id: fields}}."""
    client.use_lang(i18n.plan_lang_name(plan))
    if not 0 <= index < len(plan["scenes"]):
        return plan
    src = plan["scenes"][index]
    seed = seed if seed is not None else int(time.time()) % 100000
    free = [s["index"] for s in plan["scenes"] if s["index"] != index and not s.get("locked") and not prompts.is_raw(s)]
    plan["propagated"] = {"from": src.get("id"), "n": index + 1, "scenes": [], "before": {}}
    if not free:
        return plan
    user, schema = _propagate_ask(plan, index)
    t0 = time.time()
    async with client.session(plan.get("model")) as llm:
        # gemma-4 thinks this question over though thinking is off (reasoning_content, ~800 tokens) before it answers:
        # 900 tokens cut 4 answers of 6 (2026-10-28) - the budget holds the thinking and the answer
        d = await llm.chat_json(_system(plan), user, schema, temperature=0.3, seed=seed, max_tokens=PROPAGATE_TOKENS)
        why: dict[int, str] = {}
        for x in d.get("other_scenes") or []:
            m = re.match(r"\s*(?:scene\s*)?(\d+)\s*[:.\-–—)]\s*(.+)", str(x), re.I)
            i = int(m.group(1)) - 1 if m else -1
            if i in free and i not in why and m.group(2).strip():
                why[i] = m.group(2).strip()
        if why:
            plan["propagated"]["before"] = {plan["scenes"][i]["id"]: {k: plan["scenes"][i].get(k) for k in PROPAGATE_KEYS if k in plan["scenes"][i]}
                                            for i in why}
            # the old text as what not to repeat: shown as "now", gemma handed the same embrace back (2026-10-28, the
            # second try) - these scenes must change
            await _rewrite(llm, plan, sorted(why), {i: [f"it must agree with scene {index + 1} as the user changed it: {r}"] for i, r in why.items()},
                           f"The user changed scene {index + 1} (shown above among the scenes that stay). Rewrite these scenes so the "
                           "story agrees with it: what the reason says can no longer happen must not happen; keep the people, "
                           "the place and the mood.", seed + 1, different=True)
            await _fix_round(llm, plan, seed + 2, only=set(why))
        plan["propagated"]["scenes"] = [{"index": i, "id": plan["scenes"][i]["id"], "reason": r} for i, r in sorted(why.items())]
        plan["writer"] = {"model": llm.model.name, "seconds": round(time.time() - t0, 1), "calls": llm.calls, "cached": llm.cached}
    return plan


def unpropagate(plan: dict) -> bool:
    """«Вернуть как было»: the scenes the last propagation rewrote get their fields back. -> whether anything was."""
    p = plan.get("propagated") or {}
    before = p.get("before") or {}
    if not before:
        return False
    for s in plan["scenes"]:
        if s.get("id") in before:
            for k in PROPAGATE_KEYS:
                s.pop(k, None)
            s.update(before[s["id"]])
    plan.pop("propagated", None)
    return True


# ---------- spoken lines («Придумать реплики», only by the button) ----------
LINES_SYSTEM = """You write what the people in one scene of a short video say aloud. The video model MiniMax H3 speaks the lines itself, in Russian, with lip movement, so every line is natural spoken Russian.

Rules:
- A scene is 5 seconds: all lines of the scene together have at most 10 words; one line has at most 8.
- Only the people listed for the scene speak, each at most once; usually one or two of them.
- The line grows out of what happens in the scene and in the story around it; no stage directions, no names of the characters inside the line, no quotes.
- how: the manner of speaking, one of the given words; "plain" when nothing special.
- Silence is fine: return an empty list when words do not suit the scene (a fight, a long look, nobody near)."""


# a range for who and "plain" for the plain manner: an integer enum and an empty string in an enum made llama.cpp's
# grammar loop on whitespace until the token limit (2026-10-22)
HOW_LLM = ["plain" if k == "" else k for k in prompts.HOW]


def _lines_schema(people: list[int]) -> dict:
    return {"type": "object", "properties": {"lines": {"type": "array", "maxItems": 2, "items": {
        "type": "object", "properties": {"who": {"type": "integer", "minimum": min(people), "maximum": max(people)},
                                         "text": {"type": "string", "maxLength": 120}, "how": {"type": "string", "enum": HOW_LLM}},
        "required": ["who", "text", "how"]}}}, "required": ["lines"]}


def _lines_system(seconds: int) -> str:
    """The rules for a scene of this length: 2 words a second (5 s: 10, as for the storyboard)."""
    if seconds == SCENE_SECONDS:
        return LINES_SYSTEM
    words = 2 * seconds
    return LINES_SYSTEM.replace("A scene is 5 seconds: all lines of the scene together have at most 10 words; one line has at most 8.",
                                f"A scene is {seconds} seconds: all lines of the scene together have at most {words} words; "
                                f"one line has at most {max(4, words - 2)}.")


async def lines_for_prompt(llm, text: str, speakers: list[str], seconds: int, seed: int) -> list[dict]:
    """«Придумать реплики» for the graph's «Промт»: the writer reads the prompt itself (there is no story around it)
    and gives the people it names a line or two. -> [{who: the speaker as named, text, how}] (may be empty)."""
    people = list(range(1, len(speakers) + 1))
    who = "\n".join(f"{i}: {s}" for i, s in enumerate(speakers, 1))
    user = (f"THIS SCENE, as the prompt for the video model (English):\n{text}\n\n"
            f"People in it (number: how the prompt names them):\n{who}\n\nManner words for how: {', '.join(HOW_LLM)}.")
    d = await llm.chat_json(_lines_system(seconds), user, _lines_schema(people), temperature=0.8, seed=seed, max_tokens=700)
    return [{"who": speakers[int(x["who"]) - 1], "text": str(x.get("text", "")).strip().strip('"«»“” '),
             "how": x.get("how") if x.get("how") in prompts.HOW else ""}
            for x in (d.get("lines") or [])[:2] if int(x.get("who", 0)) in people and str(x.get("text", "")).strip()]


async def write_lines(plan: dict, indices: list[int], seed: Optional[int] = None) -> dict:
    """«Придумать реплики»: for each scene, a line or two for the people in it (the writer sees the story, the scene,
    who is there and the lines just before). The lines replace the scene's; the user edits them after. A scene whose
    answer breaks (the model loops past its limit) keeps its lines and the others go on (`lines_failed` in the
    writer's note): one stuck scene of 18 lost every line before it (2026-10-23)."""
    client.use_lang(i18n.plan_lang_name(plan))   # the video's language (i18n.plan_lang)
    if plan.get("mode") == "none":
        return plan
    seed = seed if seed is not None else int(time.time()) % 100000
    cast = plan.get("cast") or []
    t0 = time.time()
    failed: list[int] = []
    async with client.session(plan.get("model")) as llm:
        for i in [i for i in indices if 0 <= i < len(plan["scenes"])]:
            s = plan["scenes"][i]
            people = [k + 1 for k, _ in prompts.scene_cast(plan, s)] if len(cast) > 1 else [1]
            who = "\n".join(f"{n}: {(cast[n - 1].get('ru') or cast[n - 1].get('en') or '')[:160]}" for n in people if n - 1 < len(cast))
            story = "\n".join(f"{x['index'] + 1}. {x.get('ru', '')}" for x in plan["scenes"][max(0, i - 3): i + 3])
            before = "\n".join(f"{ln['who']}: «{ln['text']}»" for x in plan["scenes"][max(0, i - 2): i] for ln in prompts.lines_of(plan, x))
            user = (f"Idea ({client.lang()}): {plan.get('idea', '')}\nTitle: {plan.get('title_ru', '')}\n\nThe story around this scene:\n{story}\n\n"
                    f"THIS SCENE ({i + 1}): {s.get('ru', '')}\nWhat is seen (English): {' '.join(s.get('beats_en') or [])}\n\n"
                    f"People in it (number: who):\n{who}\n" + (f"\nThe last lines before it:\n{before}\n" if before else "")
                    + f"\nManner words for how: {', '.join(HOW_LLM)}.")
            try:
                d = await llm.chat_json(_lines_system(max(2, round(grid_seconds(s)))), user, _lines_schema(people), temperature=0.8,
                                        seed=seed + i, max_tokens=700)
            except client.LLMError:
                if len(indices) == 1:
                    raise
                failed.append(i + 1)
                continue
            s["lines"] = [{"who": int(x["who"]), "text": str(x.get("text", "")).strip().strip('"«»“” '), "how": x.get("how") if x.get("how") in prompts.HOW else ""}
                          for x in (d.get("lines") or [])[:2] if int(x.get("who", 0)) in people and str(x.get("text", "")).strip()]
        plan["writer"] = {"model": llm.model.name, "seconds": round(time.time() - t0, 1), "calls": llm.calls, "cached": llm.cached,
                          **({"lines_failed": failed} if failed else {})}
    return plan
