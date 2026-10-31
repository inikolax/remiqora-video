"""The final H3 prompt is put together by code, from what the writer filled in; and the scene validator.

The formula (what held up in the first long H3 test runs):
  style  ·  the lock (the hero's look word for word, or the world)  ·  the place: "Scene: …" on a new scene,
  "Scene continues …" on a continuation (a new place inside one gives a hard cut)  ·  camera  ·  timeline [0s-2s] …
  ·  Audio: …  ·  the tail (keep the face and outfit / No people; never text in the frame).
A continuation is shot from the previous scene's last frame, so it opens with "Continue seamlessly from <Picture 1>."

The formula has a version (`prompt_v` on the plan, formula()): every save composes every scene again and an H3 shot's
key is a hash of its prompt, so a plan keeps the formula it was written with - a change of it would reshoot every
scene of every video. Version 2 (new plans since 2026-10-30, the video-quality audit of that day):
  - a scene that names nobody (an insert: waves on the sand, the empty chair) gets no look and no face to keep - the
    look drew the heroine or a stranger into it; its tail says there are no people;
  - a new scene from a picture holds the picture instead of describing the style, the look and the place again - H3
    left the picture for the described place (as translate.H3_FRAME_RULE does for the graph);
  - a clip's scene that does not sing keeps the lips closed: H3 makes the picture and the sound in one latent, and the
    writer's "her voice singing" opened the mouth out of sync with the song.
Version 3 (new plans since 2026-10-30, the same audit, items 9 and «руки»): the formula of 2, and around it - a clip's
singing close and medium scenes get the handheld camera (clip.vary_cameras; LTX from a frame with a static camera
was an almost still picture), the writer is told one body movement in time, hands below the shoulders and empty
(waving arms and a pair of shoes in the hands smeared), and hand_problems sends such beats back.
"""
from __future__ import annotations

import re
from typing import Optional

from ..i18n import LANGS, L, plan_lang_name, text_name
from .grid import SCENE_SECONDS

FRAMING = {"wide": "Wide shot", "medium": "Medium shot", "close": "Close-up"}
CAMERAS = {
    "static": "static camera",
    "push_in": "slow push-in",
    "pull_back": "slow pull-back",
    "track_side": "smooth tracking shot alongside",
    "track_front": "leading shot, the camera stays ahead as they walk toward it",   # no "backward": it made people walk backward
    "follow": "the camera follows from behind",
    "orbit": "slow orbit",
    "pan": "slow pan",
    "rise": "the camera slowly rises",
    # a singer from her frame: LTX 2.3 with a static camera or a slow push-in made an almost still picture (a test
    # clip's singing scenes moved 1.8-5.2 against H3's 3.6-11.9)
    "handheld": "handheld camera close to the face, a gentle natural sway",
}
CYRILLIC_LANGS = ("Russian", "Ukrainian", "Belarusian", "Kazakh")   # the languages written in Cyrillic
TAIL_PEOPLE = "Keep {who} face, hair and outfit exactly the same. No text, subtitles, logos or watermarks."
TAIL_NONE = "No text, subtitles, logos, watermarks or people."
TAIL_EMPTY = "There are no people and no faces anywhere in this shot. No text, subtitles, logos or watermarks."
FRAME_HOLD = "Everything stays as in <Picture 1>: the same people, place, light, colours and framing."
# from a picture the camera only eases in or across: a tracking or orbiting move makes H3 invent what the picture lacks
HOLD_CAMERAS = ("static", "push_in", "pull_back", "pan", "handheld")
MIN_AGE = 21
PROMPT_V = 3   # the formula of new plans (formula())


def formula(plan: dict) -> int:
    """The prompt formula this plan was written with: `prompt_v`, a plan from before versions - 1 (its prompts, and so
    its shots' keys, stay as they were)."""
    v = plan.get("prompt_v")
    return v if isinstance(v, int) and not isinstance(v, bool) else 1


_STYLIZED = re.compile(r"\banime\b|\bmanga\b|cel[- ]?shad|cartoon|\b[23]d\b|\banimat(?:ed|ion)\b|pixar|\bcgi?\b|illustrat|"
                       r"claymation|stop[- ]motion|ghibli|\btoon", re.I)


def stylized(plan: dict) -> bool:
    """A drawn or animated picture by the video's style (style_en: anime, cel-shading, cartoon, 3D animation, an
    illustration), not live action: a handheld camera there jumps and pulls the drawing away, and flat fills move few
    pixels (checks.still_line). Not used in any prompt."""
    st = str(plan.get("style_en") or "")
    return bool(_STYLIZED.search(st)) and not re.search(r"live[- ]action|photoreal", st, re.I)


def beats_timeline(beats: list[str], seconds: int = SCENE_SECONDS, even: bool = False) -> str:
    """1-3 beats over the scene: 3 beats of a 5 s scene -> [0s-2s] [2s-4s] [4s-5s], as in the tested prompts. `even`
    (a 10 s grid's scene): 3 beats share any other length evenly too - a clip's scenes keep the 2-4-5 they were shot with."""
    beats = [b.strip() for b in beats if b and b.strip()][:3] or ["The scene holds, everything gently alive."]
    n = len(beats)
    fixed = n == 3 and not (even and seconds != SCENE_SECONDS)
    cuts = [0] + [(2, 4, 5)[i] if fixed else round(seconds * (i + 1) / n) for i in range(n)]
    return "\n".join(f"[{cuts[i]}s-{cuts[i + 1]}s] {b}" for i, b in enumerate(beats))


# ---------- spoken lines: under each person of a scene, what they say (Russian, said in Russian) ----------
# A line is {"who": the character's number (1 in a one-hero video), "text": the Russian words, "how": a key of HOW}.
# In the prompt it is a timeline line of its own, in the format tested in the lab:
#   [1s-4s] Character 2 says softly, in Russian: "Я обещал."
# The speaker is named the way the lock names them (The heroine / Character N), so the lips move on the right face.
HOW = {"": "says", "calm": "says calmly", "soft": "says softly", "whisper": "whispers", "loud": "says loudly",
       "shout": "shouts", "laugh": "says with a laugh", "smile": "says with a smile", "angry": "says angrily",
       "sad": "says sadly", "scared": "says fearfully", "thoughtful": "says thoughtfully", "tender": "says tenderly",
       "sing": "sings"}   # phase 10: a line sung (H3 and LTX make the voice themselves; LTX 2.3 to a track - the song's own)
LINE_WORDS = 10          # what fits a 5 s scene with a moment for a look: about 10 words, 2-3 a second
WORDS_PER_SECOND = 2.5


def lines_of(plan: dict, scene: dict) -> list[dict]:
    """The scene's spoken lines that have words, of people who are in it (none in a video without people)."""
    if plan.get("mode") == "none":
        return []
    out = []
    for ln in scene.get("lines") or []:
        text = (ln.get("text") or "").strip().strip('"«»“”„ ').strip()
        if text:
            out.append({"who": int(ln.get("who") or 1), "text": text.replace('"', "”"), "how": ln.get("how") or ""})
    return out


def speaker(plan: dict, n: int) -> str:
    cast = plan.get("cast") or []
    if len(cast) <= 1:
        g = (cast[0] if cast else {}).get("gender")
        return "The heroine" if g == "female" else "The hero" if g == "male" else "The main character"
    return f"Character {n}"


def scene_timeline(plan: dict, scene: dict, seconds: Optional[int] = None) -> str:
    """The timeline: the beats alone (as before, word for word), or with the spoken lines. Over the scene's own
    length (a clip's scene, phase 11), in whole seconds; a storyboard scene's 5."""
    if seconds is None:
        from .grid import seconds_of
        seconds = max(2, round(seconds_of(scene)))
    lines = lines_of(plan, scene)
    if not lines:
        return beats_timeline(scene.get("beats_en") or [], seconds, bool(plan.get("scene_seconds")))
    return lines_timeline(scene.get("beats_en") or [], [(speaker(plan, ln["who"]), ln["how"], ln["text"]) for ln in lines], seconds,
                          spoken_lang_name(plan, lines))


def spoken_lang_name(plan: dict, lines: list[dict]) -> str:
    """The language the lines are in: a clip's sung words are the song's (clip.lang, recognised), whatever the
    storyboard's texts are in (an English song in a Russian storyboard); the rest the video's (i18n.plan_lang)."""
    sung = bool(plan.get("clip")) and all(ln["how"] == "sing" for ln in lines)
    if sung and plan["clip"].get("lang") in LANGS:
        return text_name(plan["clip"]["lang"])
    return plan_lang_name(plan)


def lines_timeline(beats: list[str], lines: list[tuple[str, str, str]], seconds: int, spoken: str = "Russian") -> str:
    """Beats with spoken lines [(who, how, text)]: the first beat, the lines, the rest of the beats. A line gets the
    seconds its words need (2.5 words a second, at least 2); the beats share what is left, at least a second each
    (beats past two are dropped to make room)."""
    beats = [b.strip() for b in beats if b and b.strip()][:3]
    need = [max(2, -(-len(text.split()) * 2 // 5)) for _, _, text in lines]   # ceil(words / 2.5)
    while beats and sum(need) + len(beats) > seconds and len(beats) > 1:
        beats.pop(1 if len(beats) > 2 else len(beats) - 1)
    while sum(need) + len(beats) > seconds and max(need) > 1:   # long lines on a short scene: squeeze them evenly
        need[need.index(max(need))] -= 1
    spare = seconds - sum(need) - len(beats)
    beat_secs = [1 + spare // len(beats) + (1 if k < spare % len(beats) else 0) for k in range(len(beats))] if beats else []
    if not beats:   # no action: the lines take the whole scene
        need[-1] += seconds - sum(need)
    items = []
    if beats:
        items.append((beats[0], beat_secs[0]))
    for (who, how, text), sec in zip(lines, need):
        items.append((f"{who} {HOW.get(how, 'says')}, in {spoken}: \"{text}\"", sec))   # spoken: the video's language (i18n.plan_lang)
    items += list(zip(beats[1:], beat_secs[1:]))
    out, t = [], 0
    for text, sec in items:
        out.append(f"[{t}s-{t + sec}s] {text}")
        t += sec
    return "\n".join(out)


# «Склейки внутри сцены»: H3 follows shot markup in its prompt - «[Shot 2] 00:04.000 -
# hard cut to a close-up …» gave a cut at 3.88 s (on its latent grid, 3 frames early) on 2 seeds of 2, the same woman,
# light and place; the same beats as our timeline gave one continuous shot (2026-10-28). Each beat becomes a shot, the
# framing turning wide -> medium -> close from the scene's own; the first keeps the scene's (a continuation starts on it).
SHOT_ORDER = ("wide", "medium", "close")


def shots_timeline(plan: dict, scene: dict) -> str:
    """The scene's beats as shots with hard cuts between them, when the scene asks for it (`cuts`) and has 2-3 beats and
    no spoken lines (a line across a cut moves to another face); "" otherwise - the timeline as it always was."""
    beats = [b.strip() for b in scene.get("beats_en") or [] if b and b.strip()][:3]
    if not scene.get("cuts") or len(beats) < 2 or lines_of(plan, scene):
        return ""
    from .grid import seconds_of
    seconds = max(2, round(seconds_of(scene)))
    n = len(beats)
    fixed = n == 3 and not (plan.get("scene_seconds") and seconds != SCENE_SECONDS)
    at = [0] + [(2, 4, 5)[i] if fixed else round(seconds * (i + 1) / n) for i in range(n)]
    k0 = SHOT_ORDER.index(scene.get("framing")) if scene.get("framing") in SHOT_ORDER else 1
    cam = CAMERAS.get(scene.get("camera"), CAMERAS["static"])
    out = []
    for i, b in enumerate(beats):
        framing = FRAMING[SHOT_ORDER[(k0 + i) % 3]].lower()
        how = f"{framing}, {cam}" if i == 0 else f"hard cut to a {framing}, static camera"
        out.append(f"[Shot {i + 1}] 00:{at[i]:02d}.000 - {how}: {b}")
    return "\n".join(out)


def voices(plan: dict, scene: dict) -> str:
    """What the audio line says about the voices of a scene with lines ("" without)."""
    lines = lines_of(plan, scene)
    if not lines:
        return ""
    who = {ln["who"] for ln in lines}
    sung = bool(plan.get("clip")) and all(ln["how"] == "sing" for ln in lines)   # a clip's singing scene (phase 11); a storyboard's prompts stay as they were
    spoken = spoken_lang_name(plan, lines)
    if len(who) > 1:
        return f"Their clear voices singing in {spoken}." if sung else f"Their clear voices speaking {spoken}."
    cast = plan.get("cast") or []
    g = cast[min(who.pop(), len(cast)) - 1].get("gender") if cast else None
    return _voice(g, sung, spoken)


def _voice(gender: Optional[str], sung: bool = False, spoken: str = "Russian") -> str:
    return {"female": "Her", "male": "His"}.get(gender or "", "Their") + (f" clear voice singing in {spoken}." if sung else f" clear voice speaking {spoken}.")


# ---------- spoken lines in a prompt written by hand (the graph's «Промт» node) ----------
# A line there is {"who": how the prompt names the speaker ("The heroine", "Character 2", "The old man"), "text",
# "how"}. weave_lines puts them into the prompt the way compose does for a storyboard scene: so a storyboard scene's
# prompt composed without its lines and woven with them is its prompt with them, word for word.
TIME_TAG = re.compile(r"^\s*\[\s*\d+(?:[.,]\d+)?\s*s?\s*[-–]\s*\d+(?:[.,]\d+)?\s*s?\s*\]\s*")
SPEAKER = re.compile(r"\b(The (?:heroine|hero|main character)|Character \d+)\b")
_FEMALE = re.compile(r"\b(heroine|woman|lady|girl|she|her|female|mother|grandmother|wife|sister|daughter)\b", re.I)
_MALE = re.compile(r"\b(hero|man|guy|boy|he|his|him|male|father|grandfather|husband|brother|son)\b", re.I)


def clean_line(ln: dict) -> Optional[dict]:
    text = (ln.get("text") or "").strip().strip('"«»“”„ ').strip()
    who = (ln.get("who") or "").strip() if isinstance(ln.get("who"), str) else ""
    if not text:
        return None
    return {"who": who or "The main character", "text": text.replace('"', "”"), "how": ln.get("how") if ln.get("how") in HOW else ""}


PERSON = re.compile(r"\b(?:an?|the)\s+(?:[\w-]+\s+){0,3}?(woman|man|lady|person)\b", re.I)


def speakers_in(text: str) -> list[str]:
    """Who may speak in a prompt: the people it names the way the storyboard does, in order of their first mention;
    without such names - "The woman", "The man"... for the people it mentions."""
    out: list[str] = []
    for m in SPEAKER.finditer(text or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    if not out:
        for m in PERSON.finditer(text or ""):
            who = "The " + m.group(1).lower()
            if who not in out:
                out.append(who)
    return out


def gender_of(who: str, text: str) -> Optional[str]:
    """Whose voice: the speaker's own word ("The heroine", "the old man"), or the first word for a person in the
    sentence that introduces them in the prompt ("Character 2 (the same in every shot): a 40-year-old man ...")."""
    for s in (who, *(m.group(0) for m in re.finditer(re.escape(who) + r"[^.\n]{0,160}", text or "", re.I))):
        f, m = _FEMALE.search(s), _MALE.search(s)
        if f or m:
            return "female" if f and (not m or f.start() < m.start()) else "male"
    return None


def split_lines(plan: dict, scene: dict) -> tuple[str, list[dict]]:
    """A storyboard scene -> a «Промт» node's text and lines: its prompt without the lines, the lines with their
    speakers named (woven back, they give its prompt word for word - the same cache key)."""
    lines = [] if is_raw(scene) else lines_of(plan, scene)
    if not lines:
        return scene.get("prompt") or compose(plan, scene), []
    bare = {k: v for k, v in scene.items() if k != "lines"}
    return compose(plan, bare), [{"who": speaker(plan, ln["who"]), "text": ln["text"], "how": ln["how"]} for ln in lines]


def weave_lines(text: str, lines: list[dict], seconds: int = SCENE_SECONDS, spoken: str = "Russian") -> str:
    """A prompt and its spoken lines -> the prompt H3 gets: the lines go into its Timeline among the beats
    (lines_timeline; a prompt without a Timeline gets one), the voices first in its Audio line (one is added after the
    timeline when there is none). No lines: the text as it is."""
    lines = [x for x in (clean_line(ln) for ln in lines or []) if x]
    if not lines:
        return text
    rows = (text or "").strip().split("\n")
    head = next((i for i, r in enumerate(rows) if r.strip().lower().startswith("timeline:")), None)
    if head is None:   # no timeline: one before the audio line, or at the end
        at = next((i for i, r in enumerate(rows) if r.strip().lower().startswith("audio:")), None)
        if at is None:
            rows += ["", "Timeline:"]
            head = len(rows) - 1
        else:
            rows[at:at] = ["Timeline:", ""]
            head = at
    end = head + 1
    while end < len(rows) and TIME_TAG.match(rows[end]):
        end += 1
    beats = [TIME_TAG.sub("", r).strip() for r in rows[head + 1:end]]
    timeline = lines_timeline(beats, [(x["who"], x["how"], x["text"]) for x in lines], seconds, spoken).split("\n")
    rows[head + 1:end] = timeline
    who = {x["who"] for x in lines}
    voice = f"Their clear voices speaking {spoken}." if len(who) > 1 else _voice(gender_of(next(iter(who)), text), spoken=spoken)
    audio = next((i for i, r in enumerate(rows) if r.strip().lower().startswith("audio:")), None)
    if audio is None:
        at = head + 1 + len(timeline)
        rows[at:at] = ["", f"Audio: {voice}"]
    else:
        rest = rows[audio].strip()[6:].strip()
        rest = rest[:1].upper() + rest[1:]   # a sentence of its own after the voice
        if rest.lower().startswith("no music"):
            rows[audio] = f"Audio: {voice} {rest}"
        else:
            rows[audio] = f"Audio: {voice} {rest} Everything else stays quiet under the voices." if rest else f"Audio: {voice}"
    return re.sub(r"\n{3,}", "\n\n", "\n".join(rows)).strip()


def _sentence(s: str) -> str:
    s = (s or "").strip()
    return s if not s or s[-1] in ".!?" else s + "."


def _lower_first(s: str) -> str:
    """'Dark waterproof jacket' -> 'dark waterproof jacket' inside a sentence; 'NASA' and 'I' stay."""
    s = (s or "").strip()
    return s[0].lower() + s[1:] if len(s) > 1 and s[0].isupper() and not s[1].isupper() else s


def _wearing(c: dict) -> str:
    return f" Wearing {_sentence(_lower_first(c['outfit_en']))}" if c.get("outfit_en") else ""


def from_of(plan: dict, scene: dict) -> Optional[dict]:
    """The scene whose last frame a continuation starts from: its `from` (the id of any earlier scene), else the
    scene just before it. None for a new scene."""
    if scene.get("kind") != "continue":
        return None
    scenes, i = plan["scenes"], scene["index"]
    if scene.get("from"):
        src = next((s for s in scenes[:i] if s.get("id") == scene["from"]), None)
        if src:
            return src
    return scenes[i - 1] if i > 0 else None


def opener_of(plan: dict, scene: dict) -> Optional[dict]:
    """The "new" scene this scene goes on from, through the frames it starts from (the scene itself when it is new)."""
    s, steps = scene, 0
    while s is not None and s["kind"] != "new" and steps <= len(plan["scenes"]):
        s, steps = from_of(plan, s), steps + 1
    return s


def scene_cast(plan: dict, scene: Optional[dict] = None) -> list[tuple[int, dict]]:
    """[(index in cast, character)] in this scene. With several people a scene says who is in it (`who`, numbers from 1);
    a continuation that says nothing keeps the people of the scene that opened its chain; none said = everyone.
    A look in the prompt draws that person, so only the people of the scene go in."""
    cast = plan.get("cast") or []
    everyone = list(enumerate(cast))
    if plan["mode"] != "several" or scene is None:
        return everyone
    said = scene.get("who") or (opener_of(plan, scene) or {}).get("who") or []
    who = sorted({n for n in said if isinstance(n, int) and 1 <= n <= len(cast)})
    return [(n - 1, cast[n - 1]) for n in who] or everyone


def has_photo(c: dict) -> bool:
    """A character with a photo of their own (`photo`, a file in the project), or the hero described from the photo of
    the idea screen (`from_photo`: the project's photo)."""
    return bool(c.get("photo") or c.get("from_photo"))


def photo_people(plan: dict, scene: dict) -> list[int]:
    """The cast indices of the people in this scene who have a photo, in cast order: Ref2VA gets their photos as
    <Picture 1>, <Picture 2>... in exactly this order. A scene that lists its `faces` (cast numbers from 1; a storyboard
    made from a graph) gets those, in its own order."""
    cast = plan.get("cast") or []
    if scene.get("faces") is not None:
        return [n - 1 for n in scene["faces"] if isinstance(n, int) and 1 <= n <= len(cast) and has_photo(cast[n - 1])]
    if len(cast) == 1:
        return [0] if has_photo(cast[0]) else []
    return [i for i, c in scene_cast(plan, scene) if has_photo(c)]


# who may be in the frame by role or by name (the writer names the heroine «Alisa»): with PEOPLE, has_people's words
ROLES = re.compile(r"\b(heroine|hero|singer|dancer|character|protagonist|performer|musician|guitarist|drummer|band|couple|crowd)\b", re.I)
_NAME = re.compile(r"\b[A-ZА-ЯЁ][a-zа-яё]{2,}\b")
_SMALL = re.compile(r"\b[a-zа-яё]+\b")   # the words written small (no re.I)


def has_people(scene: dict, plan: Optional[dict] = None) -> bool:
    """Whether the scene's actions name someone in the frame: a person, a pronoun, a hand, a role, or a hero by the name
    their look uses (a capitalised word of the actions found in a hero's look); a scene without actions is taken as
    having its people. A clip's insert of the empty coat on the chair names nobody: no portrait goes to it."""
    beats = " ".join(b for b in scene.get("beats_en") or [] if b)
    if not beats.strip() or PEOPLE.search(beats) or ROLES.search(beats):
        return True
    looks = " ".join(f"{c.get('en') or ''} {c.get('ru') or ''}" for c in (plan or {}).get("cast") or [])
    # a name is never written small: «The» starting a sentence of the actions and of a look is no one's name
    small = set(_SMALL.findall(f"{beats} {looks}"))
    return any(w.lower() not in small and re.search(rf"\b{re.escape(w)}\b", looks) for w in _NAME.findall(beats))


def uses_refs(plan: dict, scene: dict) -> bool:
    """Ref2VA for this scene: the plan says `ref_photo` and someone in the scene has a photo. A new scene that is not
    started from a photo; with `ref_all` (an experiment, off by default) every scene - a continuation and a scene from
    a photo too, their start frame anchored on top (graphs.scene's guide), so the face is checked against the photo
    every 5 s instead of drifting. Tried 2026-10-22: the face at 15 s stayed closer to the photo, but the framing
    suffered (the head out of the frame, the photo's surroundings in it). A scene with its own `faces` - any kind, as
    the graph shoots it."""
    if not plan.get("ref_photo") or plan["mode"] == "none" or not photo_people(plan, scene) or not has_people(scene, plan):
        return False
    return bool(plan.get("ref_all")) or scene.get("faces") is not None or (scene["kind"] == "new" and not starts_from_photo(scene))


def lock_text(plan: dict, scene: Optional[dict] = None) -> str:
    """The part that must stay word for word the same in every scene (with several people: in every scene of theirs)."""
    if plan["mode"] == "none":
        return _sentence(plan.get("world", {}).get("en", ""))
    cast = plan.get("cast") or []
    if len(cast) == 1:
        c = cast[0]
        who = "The heroine" if c.get("gender") == "female" else "The hero" if c.get("gender") == "male" else "The main character"
        return f"{who} (the same person in every shot): {_sentence(c['en'])}{_wearing(c)}"
    people = scene_cast(plan, scene)
    text = " ".join(f"Character {i + 1} (the same in every shot): {_sentence(c['en'])}{_wearing(c)}" for i, c in people)
    if len(people) < len(cast):
        names = " and ".join(f"Character {i + 1}" for i, _ in people)
        text += f" Only {names} {'is' if len(people) == 1 else 'are'} in this scene, nobody else."
    return text


def _whose(plan: dict, scene: Optional[dict] = None) -> str:
    people = scene_cast(plan, scene)
    if len(people) != 1:
        return "everyone's"
    return {"female": "her", "male": "his"}.get(people[0][1].get("gender"), "their")


def place_line(plan: dict, scene: dict) -> str:
    if scene["kind"] == "new":
        place = scene.get("place_en", "").strip()
        if plan["mode"] == "none" and (not place or place in plan.get("world", {}).get("en", "")):
            return ""   # the world line already says where it starts
        return "Scene: " + _sentence(place or "the same place as before")
    if plan["mode"] == "none":
        prev = from_of(plan, scene)
        return "Scene continues: " + _sentence(_lower_first((prev or {}).get("to_en") or "the previous moment"))
    place = (opener_of(plan, scene) or {}).get("place_en", "")
    return "Scene continues in the same place" + (f": {_sentence(place)}" if place else ".")


def is_raw(scene: dict) -> bool:
    """The user writes this scene's prompt by hand (`raw`, maybe still empty): it goes to H3 as it is - no formula,
    no look, no validator, and the writer never touches the scene."""
    return scene.get("raw") is not None


def starts_from_photo(scene: dict) -> bool:
    """A new scene with a start photo (`start_photo`, a file in the project): H3 starts from that picture (i2v), the
    way a continuation starts from the previous last frame. A continuation ignores it."""
    return scene.get("kind") == "new" and bool(scene.get("start_photo"))


def nobody(plan: dict, scene: dict, steps: int = 0) -> bool:
    """A people video's scene with nobody in it: its actions name no one, nobody speaks, and the frame it starts from
    is empty too - a continuation's source names nobody, a start picture is a frame drawn empty (frames._draw_empty;
    the user's photo may show anyone)."""
    if plan["mode"] == "none" or lines_of(plan, scene) or has_people(scene, plan):
        return False
    if scene.get("kind") == "continue":
        src = from_of(plan, scene)
        return src is None or (steps <= len(plan["scenes"]) and nobody(plan, src, steps + 1))
    if starts_from_photo(scene):
        return bool((scene.get("frame") or {}).get("empty"))
    return True


def held(plan: dict, scene: dict) -> bool:
    """Formula 2: a new scene shot from its picture without Ref2VA - the picture is the place, the people, the light
    and the style, the prompt only what happens from it on."""
    return formula(plan) >= 2 and starts_from_photo(scene) and not uses_refs(plan, scene)


def hold_camera(scene: dict) -> str:
    """The camera of a scene held on its picture: the scene's own when it is calm, else a slow push-in."""
    cam = scene.get("camera") if scene.get("camera") in HOLD_CAMERAS else "push_in"
    return CAMERAS[cam]


def is_written(scene: dict) -> bool:
    return bool((scene.get("raw") or "").strip()) if is_raw(scene) else bool(scene.get("beats_en"))


def compose(plan: dict, scene: dict) -> str:
    if is_raw(scene):
        return scene["raw"].strip()
    cam = CAMERAS.get(scene.get("camera"), CAMERAS["static"])
    framing = FRAMING.get(scene.get("framing"), "Medium shot")
    parts = []
    refs = uses_refs(plan, scene)
    hold = held(plan, scene)
    empty = formula(plan) >= 2 and nobody(plan, scene)   # formula 2: no look, no face to keep where nobody is
    if (scene["kind"] == "continue" or starts_from_photo(scene)) and not refs:
        # i2v: the start frame is <Picture 1>. With Ref2VA the pictures are the faces and the start frame is anchored
        # in the latent (graphs.scene's guide), so it is not named
        parts.append("Continue seamlessly from <Picture 1>.")
    if hold:
        # the picture is the style, the people and the place: their words again made H3 cut to the described place
        # (2026-10-28, a café instead of the street of the picture)
        parts.append(FRAME_HOLD)
        if (scene.get("frame") or {}).get("empty") and not empty and (lock := lock_text(plan, scene)):
            parts.append(lock)   # a frame drawn empty that the scene's people come into: only the look shows them
    else:
        parts.append(_sentence(plan.get("style_en", "")))
        if refs:
            # Ref2VA (render.py gives the photos as <Picture 1>, <Picture 2>... in this order): name who each photo is,
            # in the words of the lock below
            cast = plan.get("cast") or []
            for k, i in enumerate(photo_people(plan, scene)):
                who = (("The heroine" if cast[0].get("gender") == "female" else "The hero" if cast[0].get("gender") == "male" else "The main character")
                       if len(cast) == 1 else f"Character {i + 1}")
                parts.append(f"{who} is the person in <Picture {k + 1}>: exactly the same face and hair as in <Picture {k + 1}>.")
        if not empty and (lock := lock_text(plan, scene)):
            parts.append(lock)
        parts.append(place_line(plan, scene))
    if shots := shots_timeline(plan, scene):
        parts.append("Shots:\n" + shots)
    else:
        parts.append(f"Camera: the framing of <Picture 1>, {hold_camera(scene)}." if hold else f"Camera: {framing.lower()}, {cam}.")
        parts.append("Timeline:\n" + scene_timeline(plan, scene))
    if audio := audio_text(plan, scene):
        parts.append("Audio: " + audio)
    parts.append(TAIL_NONE if plan["mode"] == "none" else TAIL_EMPTY if empty else TAIL_PEOPLE.format(who=_whose(plan, scene)))
    return "\n\n".join(p for p in parts if p)


def audio_text(plan: dict, scene: dict) -> str:
    """What the scene's sound is, after "Audio: ": the voices first, then the music (or none: the user's own track
    plays over the video) and the scene's own sound under them."""
    sound = _sentence(scene.get("sound_en", ""))
    voice = voices(plan, scene)   # "" without spoken lines: the audio line stays as it was
    # formula 2: a clip's scene that does not sing (its sound is off, the song plays over it) keeps the lips closed -
    # H3 opened them for "her voice singing" out of time with the song
    closed = ""
    if not voice and plan.get("clip") and scene.get("shot") != "sing" and formula(plan) >= 2 and plan["mode"] != "none" \
            and not nobody(plan, scene):
        closed = f"No singing and no speech: {_whose(plan, scene)} lips stay closed."
    if plan.get("no_music"):
        # the user's own track plays over the video: the scenes make only their natural sound, no music of their own
        natural = "the natural sound of the scene" + (f": {_lower_first(sound)}" if sound else ", quiet ambience.")
        head = voice or closed
        return f"{head} No music, only {natural}" if head else f"no music, only {natural}"
    if sound and sound.rstrip(".").lower() in plan.get("audio_en", "").lower():
        sound = ""
    music = _sentence(plan.get("audio_en", ""))
    # the voices first; whatever the video's sound is (music or a soundscape), it stays under them
    under = "Everything else stays quiet under the voices." if voice and (music or sound) else ""
    return " ".join(x for x in (voice, closed, music, sound, under) if x)


# ---------- the validator ----------

CYRILLIC = re.compile(r"[А-Яа-яЁё]")
NEW_PLACE = re.compile(r"\b(arriv\w*|enters?|entering|walks? (in)?to (a|an|another|the next)|steps? (in)?to (a|an|another)|"
                       r"(in|at|to) (a|an) (new|different|another) (place|room|location|street|world)|moves? to (a|another)|"
                       r"cut(s)? to|transitions? to (a|an|another)|suddenly|teleport\w*|now (in|at|on) (a|an|another)|"
                       r"(the )?scene (changes|shifts))\b", re.I)
TEXT_IN_FRAME = re.compile(r"\b(text|captions?|subtitles?|logos?|watermarks?|lettering|letters|typography|title card|"
                           r"(sign|banner|screen|poster|note) (that )?(reads?|says?|reading|saying)|writ(es|ing) (on|in)|the words)\b", re.I)
OUTFIT_CHANGE = re.compile(r"\b(takes? off|taking off|puts? on|putting on|chang\w* (into|clothes|outfit)|undress\w*|"
                           r"removes? (her|his|their)|strips?|unbutton\w*|gets? dressed|slips? out of)\b", re.I)
PEOPLE = re.compile(r"\b(she|he|her|his|him|woman|women|man|men|girl|boy|person|people|crowd|figure|hand|hands|"
                    r"silhouette|someone|anyone)\b", re.I)
MINOR = re.compile(r"\b(teen\w*|adolescen\w*|child\w*|kids?|minors?|school ?(girl|boy)s?|underage|juvenile|young girl|"
                   r"little (girl|boy)|baby|toddler)\b", re.I)
CLOTHING = re.compile(r"\b(dressed|clad|coats?|jackets?|blazers?|dress(es)?|gowns?|skirts?|shirts?|blouses?|"
                      r"t-shirts?|hoodies?|sweaters?|jumpers?|cardigans?|trousers|pants|jeans|shorts|leggings|boots|shoes|"
                      r"sneakers|heels|fleece|waders|uniform|suit|robe|bikini|lingerie|scarf|hat|cap)\b", re.I)
PLACEHOLDER_RU = re.compile(r"^\s*(сцена|scene)\s*\d*\s*\.?\s*$", re.I)
# Walking without a direction to the camera: H3 keeps the faces to the camera and moves people away - they walk backward
# (2026-10-22, «Прогулка в парке»: "walks forward slowly" + "move deeper into the path").
VAGUE_WALK = re.compile(r"\b(walk(s|ing)?|stroll(s|ing)?|mov(e|es|ing)|step(s|ping)?|head(s|ing)?|go(es|ing)?)\s+"
                        r"(forward|forwards|ahead|on|onward|deeper|further|farther|along|down|up)\b", re.I)
CAMERA_DIRECTION = re.compile(r"\b(toward|towards|away from|to|past)\s+(the\s+)?(camera|lens|viewer)\b|\bfrom behind\b|\bfacing\b", re.I)
TOWARD = re.compile(r"\btowards?\s+(the\s+)?(camera|lens|viewer)\b", re.I)
AWAY = re.compile(r"\baway from\s+(the\s+)?(camera|lens|viewer)\b|\b(deeper|further|farther) (into|down|along)\b|\binto the distance\b", re.I)
# Cast guard: people the cast does not have. Only words that can't name a cast member - a role
# noun ("the soldier", "a figure") is how the writer often names the hero (2026-10-28, «Неоновый киборг»: 40 of 120
# scenes would have been flagged for nothing), so no role nouns here. A look the prompt does not carry draws a random face.
INVENTED = re.compile(r"\b(strangers?|crowds?|passers?-?by|bystanders?|onlookers?|pedestrians|spectators|"
                      r"other (people|dancers|guests|men|women)|a group of (people|men|women|friends)|"
                      r"another (man|woman|person|girl|guy)|someone else)\b", re.I)
SEQUENCE = re.compile(r"\b(then|after that|afterwards|and finally)\b", re.I)   # "they" / "before" are not: shards fly, she stops before the gate
BEAT_WORDS = (3, 40)
# Formula 3, a clip's singer and performer: waving arms and a pair of shoes in her hands smeared - the hands and what
# they held swam (the user, 2026-10-30). The hands stay empty and below the shoulders, she doesn't spin
_HIS = r"(?:her|his|their|both)"
HANDS = re.compile(rf"\b(wav(?:es|ing) {_HIS} (?:arms?|hands?)|waves? (?:goodbye|at)|"
                   rf"(?:rais|lift|throw|stretch|reach|fling|swing)(?:es|s|ing)? {_HIS} (?:arms?|hands?)|"
                   rf"(?:arms?|hands?) (?:raised|up high|in the air|over {_HIS} head)|above {_HIS} head|"
                   # «holds the last note», «holds still», «holding back tears», «holds her gaze» hold nothing
                   rf"hold(?:s|ing)?\b(?!\s+(?:still|back|steady|on\b|{_HIS}\s+(?:gaze|breath|pose|position|stare|note|head|chin)|"
                   r"(?:the|a|that|this)\s+(?:\w+\s+)?(?:note|gaze|look|pose|moment|beat|line|silence)))|clutch(?:es|ing)?|"
                   r"grip(?:s|ping)?|carr(?:y|ies|ying)|"
                   # the wind spins her hair, a scarf twirls: not her spinning (and see hand_problems: «the wind spins»)
                   rf"(?:spin(?:s|ning)?|twirl(?:s|ing)?|whirl(?:s|ing)?)\b(?!\s+(?:{_HIS}\s+|the\s+)?(?:hair|dress|skirt|scarf|coat|cape|veil|ribbon)s?\b)|pirouett\w*|"
                   # «turns around to face the camera» is what the writer is asked for (SING_FIRST_BEAT, SING_BODY)
                   r"(?:turns?|turning|circles?|circling) around\b(?!\s+(?:to\s+(?:face|look)|toward|towards|to\s+the\s+(?:camera|lens|viewer))))\b", re.I)
HAND_SHOTS = ("sing", "perform")
_NOT_HER = re.compile(r"\b(?:wind|breeze|gust|snow|snowflakes|leaves|petals|confetti|lights?|dust|sparks|smoke|camera|water|mist|fog|"
                      r"hair|dress|skirt|scarf|coat|cape|veil|ribbons?)\b[^.;,]{0,30}$", re.I)


def _hands_in(beat: str) -> Optional[str]:
    """The first hands' or spinning words of a beat that are the singer's (not «the wind spins…», «snow whirls…»)."""
    for m in HANDS.finditer(beat):
        w = m.group(0).lower()
        if w.startswith(("spin", "twirl", "whirl")) and (n := _NOT_HER.search(beat[:m.start()])) \
                and not re.search(r"\b(?:she|he|they|i|we)\b", n.group(0)[len(n.group(0).split()[0]):], re.I):   # «her hair flies as she spins»: hers
            continue
        return m.group(0)
    return None


def hand_problems(plan: dict, scene: dict) -> list[str]:
    """Formula 3: a clip's singing or performing scene whose beats wave, raise or fill the hands, or spin."""
    if formula(plan) < 3 or not plan.get("clip") or plan["mode"] == "none" or scene.get("shot") not in HAND_SHOTS:
        return []
    out = []
    for i, b in enumerate(x for x in scene.get("beats_en") or [] if x.strip()):
        if m := _hands_in(b):
            out.append(f"beat {i + 1}: '{m}' - in a sing or perform scene the hands stay empty and below the shoulders: "
                       "no waving, no arms raised or above the head, nothing held, no spinning; move with a sway, a turn of the "
                       "head, the shoulders, the hair in the wind or a step toward the camera")
    return out


def _words(s: str) -> int:
    return len(re.findall(r"[A-Za-z']+", s or ""))


GENDER_WORDS = {
    "female": re.compile(r"\b(she|her|hers|herself|woman|girl|lady|daughter|mother|wife|sister)\b", re.I),
    "male": re.compile(r"\b(he|him|his|himself|man|guy|son|father|dad|husband|brother)\b", re.I),
}


def _absent_mentioned(plan: dict, scene: dict, text: str) -> int:
    """With several people: a character left out of the scene whose gender no one present shares, yet the beats speak
    of a person of that gender - the look is missing from the prompt, so that person won't be drawn. Its number or 0."""
    cast = plan.get("cast") or []
    present = {i for i, _ in scene_cast(plan, scene)}
    present_genders = {cast[i].get("gender") for i in present}
    for i, c in enumerate(cast):
        g = c.get("gender")
        if i not in present and g in GENDER_WORDS and g not in present_genders and GENDER_WORDS[g].search(text):
            return i + 1
    return 0


def _other_gender(plan: dict, text: str) -> Optional[tuple[str, str]]:
    """One hero: the beats speak of a person of a gender the hero is not (a man in a heroine's video) - someone the
    writer made up. (the gender's word, the word found) or None."""
    have = {c.get("gender") for c in plan.get("cast") or []}
    for g, rx in GENDER_WORDS.items():
        if g not in have and "other" not in have and (m := rx.search(text)):
            return ("a woman" if g == "female" else "a man"), m.group(0)
    return None


def scene_problems(plan: dict, scene: dict) -> list[str]:
    """English problems, said so the writer can fix them (they are sent back to it as they are)."""
    out = []
    beats = [b for b in scene.get("beats_en") or [] if b.strip()]
    en = " ".join([*beats, scene.get("place_en", ""), scene.get("to_en", ""), scene.get("sound_en", "")])
    if CYRILLIC.search(en):
        out.append("the English fields contain Cyrillic: write them in English only")
    if not 1 <= len(beats) <= 3:
        out.append(f"beats_en must have 1 to 3 beats, it has {len(beats)}")
    for i, b in enumerate(beats):
        w = _words(b)
        if not BEAT_WORDS[0] <= w <= BEAT_WORDS[1]:
            out.append(f"beat {i + 1} has {w} words, keep each beat {BEAT_WORDS[0]}-{BEAT_WORDS[1]} words")
        if SEQUENCE.search(b):
            out.append(f"beat {i + 1} chains several actions ('{SEQUENCE.search(b).group(0)}'): one action per beat")
        if (m := VAGUE_WALK.search(b)) and not CAMERA_DIRECTION.search(b):
            out.append(f"beat {i + 1}: '{m.group(0)}' has no direction to the camera - say 'toward the camera' or "
                       "'away from the camera, seen from behind' (otherwise people walk backward)")
    toward = [i + 1 for i, b in enumerate(beats) if TOWARD.search(b)]
    away = [i + 1 for i, b in enumerate(beats) if AWAY.search(b)]
    if toward and away:
        out.append(f"beats {toward[0]} and {away[0]} walk toward the camera and away from it in one scene: "
                   "keep one direction (a turn around between them looks like walking backward)")
    if scene["kind"] == "continue" and (m := NEW_PLACE.search(" ".join(beats + [scene.get("to_en", "")]))):
        out.append(f"a continuation stays in the same place and moment - no new location ('{m.group(0)}')")
    if scene["kind"] == "new" and plan["mode"] != "none" and _words(scene.get("place_en", "")) < 4:
        out.append("a new scene needs place_en: one sentence about the place")
    if scene["kind"] == "new" and plan["mode"] == "several" and not scene.get("who"):
        out.append("a new scene needs who: the numbers of the characters in it")
    if plan["mode"] != "none" and (m := INVENTED.search(" ".join(beats))):
        out.append(f"only the cast is in the video: no other people ('{m.group(0)}') - the model would draw a random face")
    if plan["mode"] == "one" and (g := _other_gender(plan, " ".join(beats))):
        out.append(f"the only character is not {g[0]} ('{g[1]}'): no other person in the video")
    if plan["mode"] == "several" and (missing := _absent_mentioned(plan, scene, " ".join(beats))):
        out.append(f"the beats show character {missing} ('{GENDER_WORDS[(plan.get('cast') or [])[missing - 1].get('gender')].search(' '.join(beats)).group(0)}'), "
                   f"but who does not list them: add {missing} to who or leave them out of the beats")
    if m := TEXT_IN_FRAME.search(en):
        out.append(f"no text, signs or writing in the frame ('{m.group(0)}')")
    if plan["mode"] != "none" and (m := OUTFIT_CHANGE.search(en)):
        out.append(f"the outfit never changes ('{m.group(0)}')")
    if plan["mode"] == "none" and (m := PEOPLE.search(en)):
        out.append(f"no people at all in this video ('{m.group(0)}')")
    if plan["mode"] == "none" and _words(scene.get("to_en", "")) < 3:
        out.append("to_en must say in a few words what the frame shows at the end of the scene")
    if m := MINOR.search(en):
        out.append(f"only adults ('{m.group(0)}')")
    out += hand_problems(plan, scene)
    ru, lang = scene.get("ru", ""), plan_lang_name(plan)   # ru: the scene told in the video's language (i18n.plan_lang)
    short = len(ru.strip()) < 12 if lang in ("Chinese", "Japanese", "Korean") else len(ru.split()) < 5
    script = bool(CYRILLIC.search(ru)) == (lang in CYRILLIC_LANGS)   # written in the alphabet of its language
    if PLACEHOLDER_RU.match(ru) or short or not script:
        out.append(f"ru must tell the user in {lang}, in 1-2 sentences, what happens in the scene (not 'Scene N')")
    return out


def line_problems(plan: dict, scene: dict) -> list[str]:
    """The spoken lines are the user's (or «Придумать реплики»): their problems are shown, never sent to the writer's
    fixing round, which does not write lines."""
    out = []
    lines = lines_of(plan, scene)
    words = sum(len(ln["text"].split()) for ln in lines if not (plan.get("clip") and ln["how"] == "sing"))   # a clip's sung line is as long as it is sung
    from .grid import seconds_of
    secs = round(seconds_of(scene)) if plan.get("scene_seconds") else SCENE_SECONDS   # a 10 s grid's scene holds twice as many
    limit = round(LINE_WORDS * secs / SCENE_SECONDS)
    if words > limit:
        out.append(f"the spoken lines have {words} words: about {limit} fit in a {secs} s scene")
    if plan["mode"] == "several":
        present = {i + 1 for i, _ in scene_cast(plan, scene)}
        for ln in lines:
            if ln["who"] not in present:
                out.append(f"a line of character {ln['who']}, who is not in the scene")
    return out


def style_problems(plan: dict) -> list[str]:
    w = _words(plan.get("style_en", ""))
    return [] if 12 <= w <= 50 else [f"style_en has {w} words: write 15-40 words about the look (realism or genre, light, lens, colour, grain)"]


def cast_problems(plan: dict) -> list[str]:
    if plan["mode"] == "none":
        return [] if _words(plan.get("world", {}).get("en", "")) >= 8 else ["world.en must describe the place and look in a sentence or two"]
    out = []
    for i, c in enumerate(plan.get("cast") or []):
        if c.get("from_photo"):
            continue
        if _words(c.get("en", "")) < 15:
            out.append(f"character {i + 1}: describe the look in more detail (build, skin, face, eyes, hair)")
        if m := CLOTHING.search(c.get("en", "")):
            out.append(f"character {i + 1}: en is the body and face only, clothing goes to outfit_en ('{m.group(0)}')")
        if m := MINOR.search(c.get("en", "")):
            out.append(f"character {i + 1}: only adults ('{m.group(0)}')")
    return out


NOUN = {"female": "woman", "male": "man", "other": "person"}
_GENDER_WORD = re.compile(r"^([\w,-]+\s+){0,5}(woman|man|person|lady|guy|female|male)\b", re.I)


def fix_cast(plan: dict) -> None:
    """Fixed parts of the formula, not filters: "a <age>-year-old <woman / man>" at the start of every description,
    the age 21 or more; a "wearing ..." clause that slipped into the look is cut (the outfit has its own field)."""
    for c in plan.get("cast") or []:
        c["age"] = max(MIN_AGE, int(c.get("age") or MIN_AGE))
        en = c.get("en", "")
        if not c.get("from_photo"):
            en = re.sub(r",?\s*(?<![a-z])(wearing|dressed in|clad in)(?![a-z])[^.]*", "", en, flags=re.I)
        # every age at the start, in digits or words: "a 24-year-old twenty-four-year-old female" was seen (2026-10-22)
        en = re.sub(r"^\s*(an?|the)?\s*((\d+|[a-z]+(-[a-z]+)?)[- ]year[- ]old,?\s*)*", "", en, flags=re.I)
        en = re.sub(r"\s+in (her|his|their) (early |mid-?|late )?\d0s(?![a-z])", "", en, flags=re.I)   # the number says it
        en = re.sub(r"^(young|adult)\s+", "", en.strip(), flags=re.I)
        # a name or role in front, «Singer - lean build», also once made into «woman with singer - lean build» (2026-10-29)
        en = re.sub(r"^((?:woman|man|person)\s+with\s+)?[a-z]+\s+[-–—:]\s+", r"\1", en, flags=re.I)
        if not _GENDER_WORD.match(en):   # "Slim build, fair skin..." -> "woman with slim build, fair skin..."
            noun = NOUN.get(c.get("gender"), "person")
            en = f"{noun} with {_lower_first(en)}" if en else noun
        c["en"] = f"a {c['age']}-year-old {_lower_first(en)}"


# The problems are written for the writer (English, sent back to it as they are); the user reads them in the interface's language.
_RU = [
    (r"^the English fields contain Cyrillic", "В английском промте есть русские буквы",
     "The English prompt has Russian letters"),
    (r"^beats_en must have 1 to 3 beats, it has (\d+)", r"Нужно 1–3 действия, а их \1",
     r"1–3 actions are needed, there are \1"),
    (r"^beat (\d+) has (\d+) words", r"Действие \1: \2 слов — слишком коротко или длинно",
     r"Action \1: \2 words, too short or too long"),
    (r"^beat (\d+) chains several actions \('(.+)'\)", r"Действие \1 — это несколько действий подряд («\2»)",
     r"Action \1 is several actions in a row («\2»)"),
    (r"^a continuation stays in the same place.*\('(.+)'\)", r"Продолжение уходит в другое место («\1») — H3 сделает склейку",
     r"The continuation goes to another place («\1»): H3 will make a cut"),
    (r"^a new scene needs place_en", "У новой сцены не описано место",
     "The new scene's place is not described"),
    (r"^a new scene needs who", "Не сказано, кто в сцене",
     "It is not said who is in the scene"),
    (r"^beat (\d+): '(.+?)' has no direction to the camera", r"Действие \1: «\2» без направления к камере — люди могут пойти назад",
     r"Action \1: «\2» has no direction to the camera, people may walk backwards"),
    (r"^beat (\d+): '(.+?)' - in a sing or perform scene the hands", r"Действие \1: «\2» — у поющей и танцующей героини руки "
     "пустые и ниже плеч: без взмахов, без рук над головой, без предметов в руках, без кружения (руки и предмет поплывут)",
     r"Action \1: «\2» — a singing or performing heroine keeps her hands empty and below the shoulders: no waving, no "
     "arms above the head, nothing in the hands, no spinning (the hands and the thing will smear)"),
    (r"^beats (\d+) and (\d+) walk toward the camera and away", r"Действия \1 и \2: к камере и от камеры в одной сцене — получится ходьба назад",
     r"Actions \1 and \2: toward the camera and away in one scene, that gives walking backwards"),
    (r"^the beats show character (\d+) \('(.+?)'\)", r"В действиях есть герой \1 («\2»), а в составе сцены его нет — его не будет в кадре",
     r"The actions have hero \1 («\2»), but the scene's cast does not: they won't be in the frame"),
    (r"^only the cast is in the video: no other people \('(.+?)'\)", r"В сцене чужие люди («\1») — их нет среди героев, модель нарисует случайные лица",
     r"Strangers in the scene («\1»): they are not among the heroes, the model will draw random faces"),
    (r"^the only character is not (a woman|a man) \('(.+?)'\)", r"В действиях кто-то другой («\2»), а герой в ролике один — модель нарисует случайного человека",
     r"Someone else in the actions («\2»), but the video has one hero: the model will draw a random person"),
    (r"^no text, signs or writing in the frame \('(.+)'\)", r"В кадре будет текст или надпись («\1»)",
     r"There will be text or writing in the frame («\1»)"),
    (r"^the outfit never changes \('(.+)'\)", r"Одежда меняется («\1»)",
     r"The outfit changes («\1»)"),
    (r"^no people at all in this video \('(.+)'\)", r"В ролике без людей появился человек («\1»)",
     r"A person appeared in a video without people («\1»)"),
    (r"^to_en must say", "Не сказано, чем заканчивается сцена — следующей не с чего начаться",
     "It is not said how the scene ends: the next one has nothing to start from"),
    (r"^only adults \('(.+)'\)", r"Только взрослые («\1»)",
     r"Adults only («\1»)"),
    (r"^ru must tell the user", "Нет описания сцены по-русски",
     "The scene has no description in your language"),
    (r"^the spoken lines have (\d+) words: about (\d+) fit in a (\d+) s scene", r"Реплики: \1 слов — в сцену \3 с помещается около \2, сократите",
     r"Spoken lines: \1 words, about \2 fit in a \3 s scene, shorten them"),
    (r"^a line of character (\d+), who is not in the scene", r"Реплика героя \1, а его нет в сцене — отметьте его в «Кто в сцене»",
     r"A line of hero \1, who is not in the scene: tick them in «Who is in the scene»"),
    (r"^the prompt is empty", "Промт пуст — напишите его сами",
     "The prompt is empty: write it yourself"),
    (r"^the scene starts from a photo the writer has not seen", "Сцена начинается с фото, но сценарист его не видел — "
     "текст про другое место и позу, H3 уйдёт от фото к нему. Нажмите «Переписать под фото»",
     "The scene starts from a photo the writer has not seen: the text is about another place and pose, H3 will drift from the photo to it. Press «Rewrite for the photo»"),
    (r"^style_en has (\d+) words", r"Стиль ролика описан слишком коротко или длинно (\1 слов)",
     r"The video's style is described too briefly or too long (\1 words)"),
    (r"^world\.en must describe", "Мир описан слишком коротко",
     "The world is described too briefly"),
    (r"^character (\d+): describe the look in more detail", r"Герой \1: внешность описана слишком коротко — лицо может меняться",
     r"Hero \1: the look is described too briefly, the face may change"),
    (r"^character (\d+): en is the body and face only.*\('(.+)'\)", r"Герой \1: одежда попала в описание внешности («\2»)",
     r"Hero \1: the outfit got into the look («\2»)"),
    (r"^character (\d+): only adults \('(.+)'\)", r"Герой \1: только взрослые («\2»)",
     r"Hero \1: adults only («\2»)"),
]


def problem_ru(text: str) -> str:
    for pat, ru, en in _RU:
        if re.search(pat, text):
            return re.sub(pat + r".*$", L(ru, en), text, count=1)
    return text
