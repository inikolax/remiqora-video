"""The beat clip's shot pool: the code side of what the writer proposes.

A beat clip is cut from a POOL of short shots with roles, not from a timeline. The writer (writer.write_pool) only
proposes; this module makes the pool right, in code, because a small local model mixes up the roles, drags a place into
a macro and writes «hard» and «frantic» for a body:

  fix_pool          the roles filled (>= 6 hero, >= 6 atmos, exactly one close / impact / riser), the hero always in the
                    preset's own words, no place in a close-up, nothing the doll list or the owner's word list bans
  styles / picture_prompt   the style by framing: a close-up or a macro gets the place-free style (spec54's lesson: a
                    style that names a place turned the macros into diptychs - two pictures in one frame)
  scene_prompt      motion and camera only: a scene that starts from a picture never describes the place (H3 cuts to it)
  pool_to_nodes     picture / prompt / scene node specs of the graph, the role and the framing on the scene node
                    (what the beat renderer node reads)

Pure: no GPU, no LLM, no files. The hero line comes from hero.FACELESS_PRESETS (the caller passes the strings).
"""
from __future__ import annotations

import re
import uuid
from typing import Callable, Optional

from .. import looks

ROLES = ("hero", "atmos", "close", "impact", "riser")
FRAMINGS = ("macro", "close", "medium", "wide")
PLACE_FREE = ("macro", "close")      # framings whose picture never names a place
MIN_HERO, MIN_ATMOS = 6, 6
HERO_MARK = "[HERO]"                 # the writer's stand-in for the hero's line; the code puts the preset's words there
SCENE_SECONDS = 3

# the style: spec54 / c55 / c56's STYLE and MSTYLE with the clip's place and light put in
NO_TEXT = "No text, no letters, no logos, no signs anywhere."
SINGLE = "One single continuous photograph filling the whole frame, not a collage, no split screen, no second picture."
STYLE_FMT = ("Cinematic film still, shot on 35mm, very high contrast, deep crushed blacks, {place}, {light}, sharp focus, "
             "gritty film grain. " + NO_TEXT)
MSTYLE_FMT = (SINGLE + " Shot on a macro lens, very high contrast, deep crushed blacks, {light} in darkness, shallow depth "
              "of field, gritty film grain. No text, no letters, no logos anywhere.")
DEFAULT_PLACE = "a dark concrete warehouse at night, thick haze"
DEFAULT_LIGHT = "bold coloured light beams and white strobe light"

# the nouns that make a shot a PLACE; a close-up or a macro describing one becomes a diptych
PLACE_WORDS = ("warehouse", "hall", "stage", "club", "street", "city", "town", "tunnel", "room", "festival", "highway", "road",
               "bridge", "stadium", "arena", "forest", "skyline", "field", "beach", "desert", "building", "rooftop", "roof",
               "alley", "corridor", "factory", "concrete", "sky", "landscape", "avenue", "platform", "dancefloor", "floor",
               "wall", "ceiling", "crowd", "audience", "mountain", "ocean", "sea", "lake", "river", "garage", "studio")
_PLACE = re.compile(r"\b(?:" + "|".join(PLACE_WORDS) + r")s?\b", re.I)
# a prepositional phrase that ends in a place noun: «in a dark concrete warehouse», «on a stage», «against the city skyline»
_PLACE_PHRASE = re.compile(r"\s*\b(?:in|at|inside|on|against|under|over|above|across|from|beneath|beside|near|before)\s+(?:the\s+|an?\s+)?"
                           r"(?:[\w-]+\s+){0,3}?(?:" + "|".join(PLACE_WORDS) + r")s?\b(?:\s+(?:of|at|in)\s+(?:the\s+|an?\s+)?\w+(?:\s+\w+)?)?", re.I)
# a body that moves «hard», «wild», «frantic» grows hands and loses its face (writer.CLIP_RULES)
_FRANTIC = re.compile(r"\b(?:very\s+)?(?:hard(?![- ]?techno|[- ]?style)|wildly|wild|frantically|frantic|frenzied|violently|crazy|crazily)\b\s*", re.I)
# anything that draws letters: the pictures must have none
_TEXTY = re.compile(r"(?:\b(?:an?\s+|the\s+)?(?:neon\s+|street\s+|road\s+|shop\s+)?(?:signs?|signage|billboards?|logos?|lettering|captions?|"
                    r"subtitles?|writing|graffiti text|text|letters|words|numbers|license plates?|number plates?)\b"
                    r"(?:\s+(?:saying|reading|that says|spelling|written|with the word)\s+[\"']?\w+[\"']?)?(?:\s+written)?)", re.I)
_RISER = re.compile(r"\b(?:tunnel|corridor|flights?|forward|point-of-view|pov|(?:fly|flies|flying)\s+(?:through|down|toward)|rush(?:es|ing)?|"
                    r"race[sd]?|racing)\b", re.I)
_IMPACT = re.compile(r"\b(?:jump|jumps|leap|leaps|burst|bursts|explod\w*|raise[sd]?|fist|slam\w*|spin\w*|lands?|stomp\w*|smash\w*|"
                     r"rear\w*|lift\w*)\b", re.I)


# ---------- the palette ----------
def _hex_bgr(h: str) -> list[int]:
    h = h.lstrip("#")
    return [int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)]


def palette_of(source) -> dict:
    """{a, b, tint} (BGR lists: two accents and the shadow tint, edit2's cfg `palette`) from a look id (looks.LOOKS[*].tint
    is two hex colours), a look's dict, or a palette that is already one."""
    if isinstance(source, dict) and {"a", "b", "tint"} <= set(source):
        return {k: [int(v) for v in source[k]] for k in ("a", "b", "tint")}
    look = looks.LOOKS.get(source) if isinstance(source, str) else source if isinstance(source, dict) else None
    if not look or not look.get("tint"):
        look = looks.LOOKS.get("night_neon") or next(iter(looks.LOOKS.values()))
    a, b = (_hex_bgr(x) for x in look["tint"])
    return {"a": a, "b": b, "tint": [round(v * 0.15) for v in a]}


# colour word -> BGR (an accent for edit2's palette). Longest phrases first: «warm white» is read before «white».
# Neutrals (white, silver) are never the main accent when a real colour is named next to them.
_NEUTRAL = {"white", "warm white", "silver"}
COLOUR_BGR = {
    "warm white": [180, 225, 255], "white": [255, 255, 255], "silver": [215, 215, 215],
    "icy blue": [255, 215, 150], "ice blue": [255, 215, 150],
    "acid green": [0, 255, 150], "lime": [0, 255, 150], "neon green": [100, 255, 60],
    "orange": [20, 120, 255], "amber": [0, 170, 255], "golden": [40, 200, 255], "gold": [40, 200, 255],
    "yellow": [60, 235, 255], "copper": [60, 120, 220], "ember": [20, 110, 255], "red": [40, 40, 255], "crimson": [60, 20, 220],
    "scarlet": [40, 30, 255], "green": [80, 220, 40], "emerald": [110, 200, 30], "teal": [180, 200, 0], "turquoise": [200, 220, 40],
    "cyan": [255, 230, 0], "aqua": [255, 230, 0], "blue": [255, 100, 40], "sapphire": [200, 60, 20],
    "violet": [255, 60, 140], "purple": [200, 40, 150], "indigo": [200, 40, 80], "lavender": [255, 150, 190],
    "magenta": [200, 0, 255], "pink": [180, 100, 255],
}
_COLOUR_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(k) for k in COLOUR_BGR), key=len, reverse=True)) + r")\b", re.I)


def palette_from_light(light: str) -> Optional[dict]:
    """{a, b, tint} (BGR) from the colour words of the writer's `light_en` («molten orange and white sparks» -> orange, white):
    a = the first real colour named (the main accent), b = the next different colour (a neutral is fine; white when only one
    is named), tint = a dark version of `a` for the shadows (the LOOKS tints' way). None when the text names no colour at
    all - the caller falls back to a look."""
    found: list[str] = []
    for m in _COLOUR_RE.finditer(light or ""):
        w = re.sub(r"\s+", " ", m.group(1).lower())
        if w not in found:
            found.append(w)
    if not found:
        return None
    chroma = [w for w in found if w not in _NEUTRAL]
    a_name = chroma[0] if chroma else found[0]
    rest = [w for w in found if w != a_name]
    b_name = next((w for w in rest if COLOUR_BGR[w] != COLOUR_BGR[a_name]), "white" if a_name != "white" else "warm white")
    a, b = list(COLOUR_BGR[a_name]), list(COLOUR_BGR[b_name])
    return {"a": a, "b": b, "tint": [round(v * 0.15) for v in a]}


def _colour_word(bgr: list[int]) -> str:
    """A rough English name of a BGR colour for the writer's brief («violet», «icy blue»)."""
    import colorsys
    b, g, r = (v / 255 for v in bgr)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if v < 0.25:
        return "black"
    if s < 0.18:
        return "white" if v > 0.7 else "grey"
    deg = h * 360
    for top, name in ((15, "red"), (40, "orange"), (65, "yellow"), (95, "acid green"), (165, "green"), (200, "cyan"), (255, "icy blue"),
                      (290, "violet"), (335, "magenta"), (361, "red")):
        if deg < top:
            return name
    return "red"


def palette_words(p: dict) -> str:
    """«cyan and white»: the palette said for the writer and the style."""
    a, b = _colour_word(p["a"]), _colour_word(p["b"])
    return a if a == b else f"{a} and {b}"


# ---------- the style by framing ----------
def styles(place: str = "", light: str = "") -> tuple[str, str]:
    """(STYLE with the place, MSTYLE without) for this clip's place and light."""
    place = (place or DEFAULT_PLACE).strip().rstrip(".")
    light = (light or DEFAULT_LIGHT).strip().rstrip(".")
    return STYLE_FMT.format(place=place, light=light), MSTYLE_FMT.format(light=strip_place(light) or DEFAULT_LIGHT)


def picture_prompt(shot: dict, style: str, mstyle: str) -> str:
    """The start picture's prompt: a close-up or a macro takes the place-free style (code, not the writer: a style that
    names a place turns a macro into a diptych), everything else the style with the place - shots.py's way: the style
    first for a wide or medium shot, after the picture for a macro."""
    pic = (shot.get("picture_en") or "").strip()
    if shot.get("framing") in PLACE_FREE:
        return f"{pic} {mstyle}".strip()
    return f"{style} {pic}".strip()


# The live run of 2026-11-06 (clip «Feed Me Now» v2): the writer gave camera-only motions («Static camera», «Slow camera
# push-in on the chains»), a «Sharp freeze frame» for the impact and «Fast forward flight through the tunnel» for the
# riser, which the place filter emptied - an empty prompt stopped the shooting. A scene must have something that moves.
_FREEZE = re.compile(r"\b(?:freeze|freezes|frozen|freeze-frame|still frame|motionless|static shot|no movement|pause[sd]?)\b", re.I)
_CAMERA_ONLY = re.compile(r"\b(?:camera|static|slow(?:ly)?|fast|quick(?:ly)?|very|smooth(?:ly)?|gentle|gently|push-in|push|pull-back|pull|"
                          r"zoom(?:s|ing)?|in|out|pan(?:s|ning)?|orbit(?:s|ing)?|tilt(?:s|ing)?|dolly|tracking|tracks?|handheld|"
                          r"shot|close-up|macro|wide|medium|"
                          r"into|onto|on|to|toward|towards|around|across|along|over|up|down|from|at|of|the|a|an|and|with|level|"
                          r"ground|frame|focus|forward|backward|angle|low|high|then)\b", re.I)
ROLE_MOTION = {"hero": "The figure moves slowly and with weight, the clothes sway, light slides over the figure",
               "impact": "The figure throws both arms forward with force, the clothes whip, light bursts behind",
               "close": "The head turns slowly toward the camera, light slides across it",
               "riser": "The camera flies forward very fast, the lights rush past in streaks",
               "atmos": "Smoke drifts and swirls, sparks and light flicker"}
ROLE_MOTION_NEAR = "Fabric and metal sway a little, light slides across the surface"   # a hero macro / close of hands, chains, the hood
ROLE_CAMERA = {"riser": "Fast forward flight.", "impact": "Static camera.", "close": "Slow push-in."}


_CAMERA_CLAUSE = re.compile(r"\b(?:camera|push-in|pull-back|zoom(?:s|ing)?|pan(?:s|ning)?|orbit(?:s|ing)?|tilt(?:s|ing)?|dolly|tracking|"
                            r"flight|fly|flies|flying|pov|point-of-view)\b", re.I)


def _subject_moves(text: str) -> bool:
    """Whether a motion text says what moves besides the camera: a clause that does not speak of the camera (push-in, zoom,
    pan, orbit, tilt, dolly, tracking, a flight) and has two words or more once the filler is out («Smoke drifts»,
    «The figure moves slowly», «Sparks rain down»). «Static camera», «Slow camera push-in on the chains» are the camera's."""
    return any(len(re.findall(r"[A-Za-z]{3,}", _CAMERA_ONLY.sub(" ", c))) >= 2 for c in _clauses(text or "") if not _CAMERA_CLAUSE.search(c))


def scene_prompt(shot: dict, hold: bool = False, model: str = "h3") -> str:
    """The scene's prompt: the motion and the camera only. The picture shows the place, the people and the light; a prompt
    that says them again makes H3 cut to the place it describes (prompts.FRAME_HOLD, translate.H3_FRAME_RULE). `hold`
    adds FRAME_HOLD for a caller whose text does not go through the translator. `model` "ltx25": the text opens with LTX's own hold
    (beat_models.LTX_HOLD: its picture rule, no picture tags) and says only what happens; H3's text is as it always was."""
    text = tidy(_TEXTY.sub("", strip_place(shot.get("motion_en") or "", keep_camera=True)))
    text = tidy(" ".join(c for c in _clauses(text) if not _FREEZE.search(c)))   # «Sharp freeze frame»: H3 would hold the picture
    if not _subject_moves(text):   # «Static camera», «Slow camera push-in» or nothing left: the shot gets its role's own movement
        lead = ROLE_MOTION.get(shot.get("role") or "", ROLE_MOTION["atmos"])
        if shot.get("role") == "hero" and shot.get("framing") in ("macro", "close"):
            lead = ROLE_MOTION_NEAR
        text = f"{lead}. {text}".strip() if text else f"{lead}. {ROLE_CAMERA.get(shot.get('role') or '', 'Slow push-in.')}"
    if hold:
        from . import prompts
        text = f"{text} {prompts.FRAME_HOLD}".strip()
    if model == "ltx25":
        from .. import beat_models
        text = f"{beat_models.LTX_HOLD} {text}".strip()
    return text


# ---------- text repair ----------
def tidy(text: str) -> str:
    """A text after words were cut out of it: no dangling «with a», no «, ,», no space before a comma."""
    for _ in range(4):
        before = text
        text = re.sub(r"(?<![-\w])(?:with|and|of|in|on|at|a|an|the|its|his|her)\s*([,.;]|$)", lambda m: m.group(1), text, flags=re.I)   # not «push-in»
        text = re.sub(r"\s+([,.;:!?])", lambda m: m.group(1), text)
        text = re.sub(r"([,;])\s*(?:[,;]\s*)+", lambda m: m.group(1) + " ", text)
        text = re.sub(r"\s{2,}", " ", text).strip(" ,;")
        text = re.sub(r"\s+[\w]+-$", "", text)   # a word cut in half at the end («Slow camera push-»)
        if text == before:
            break
    return text


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"(?<=[,;.])\s+", text.strip()) if c.strip()]


def strip_place(text: str, keep_camera: bool = False) -> str:
    """The clauses of a text that name a place cut out (a close-up has no place). A motion text keeps the camera clause
    («Static macro camera», «the camera flies forward through the tunnel» is a MOVE: kept when `keep_camera`)."""
    out = []
    for c in _clauses(text):
        if _PLACE.search(c) and not (keep_camera and re.search(r"\b(?:camera|flight|fly|flies|flying|pov|point-of-view)\b", c, re.I)):
            c = tidy(_PLACE_PHRASE.sub("", c))   # «in a dark warehouse on a stage» out of a clause that has more to say
            if _PLACE.search(c) or len(c) < 8:
                continue
        out.append(c)
    return tidy(" ".join(out))


FIGURE = "the figure"
_HERO_POSS = re.compile(r"\[HERO\]\s*(?:['’]s|’|')\s+", re.I)   # «[HERO]'s shoulders» (the nouns after it stay)
_HERO_BARE = re.compile(r"\[HERO\]")
_BODY = re.compile(r"\b(?:hands?|fingers?|arms?|shoulders?|chains?|boots?|feet|foot|sword|gloves?|chest|back|torso|legs?|fists?|wrists?|"
                   r"belt|cape|cloak|coat|jacket|weapon|blade|staff|bandages?|knees?|spine|palms?|knuckles?)\b", re.I)
_HEAD = re.compile(r"\b(?:head|mask|helmet|visor|hood|face|skull|portrait|eyes?)\b", re.I)
_GEAR = re.compile(r"\b(?:mask|helmet|visor|hood)\b", re.I)   # the hero's head gear named without the marker: it is the hero's
_ARTICLE_BEFORE = re.compile(r"\b(?:the|a|an)\s+$", re.I)
_ARTICLE_START = re.compile(r"(?:the|a|an)\s", re.I)


def _sentence_of(text: str, pos: int) -> str:
    a = max(text.rfind(". ", 0, pos), text.rfind("; ", 0, pos))
    b = [i for i in (text.find(". ", pos), text.find("; ", pos)) if i >= 0]
    return text[a + 1: min(b) if b else len(text)]


def _cap_at(text: str, pos: int, word: str) -> str:
    """`word` capitalised when it opens the text or a sentence."""
    before = text[:pos].rstrip()
    return word[:1].upper() + word[1:] if not before or before[-1] in ".!?" else word


def _put_hero(pic: str, line: str, close: bool) -> str:
    """The writer's [HERO] marker replaced, grammatically. `line` is the hero line (medium / wide) or the head line (close /
    macro). [HERO]'s <noun> is always «the figure's <noun>» (the line + 's gives «shoulders's shoulders»). A bare [HERO]
    in a wide / medium shot: the first one is the hero line, later ones «the figure»; with a possessive only, the line opens
    the picture («<line>: the figure's hands ...»). In a close / macro shot: the head line only when the shot is the head
    (its sentence names a mask, a hood or a face, or no body part), else «the figure» (hands, chains, boots, a sword)."""
    pic = _HERO_POSS.sub(f"{FIGURE}'s ", pic)
    used = False
    while True:
        m = _HERO_BARE.search(pic)
        if not m:
            break
        sent = _sentence_of(pic, m.start())
        head_shot = not _BODY.search(sent) or bool(_HEAD.search(sent))
        if close:
            word = line if head_shot and not used else FIGURE
        else:
            word = line if not used else FIGURE
        used = used or word == line
        start = m.start()
        # «The [HERO]» / «a [HERO]»: the preset's words bring their own article («a dancer wearing ...») - one article only
        if (art := _ARTICLE_BEFORE.search(pic[:start])) and _ARTICLE_START.match(word):
            start = art.start()
        pic = pic[:start] + _cap_at(pic, start, word) + pic[m.end():]
    if not close and not used and f"{FIGURE}'s " in pic:
        pic = f"{line[:1].upper()}{line[1:]}: {pic[:1].lower()}{pic[1:]}"
    return pic[:1].upper() + pic[1:]


def _clean_picture(pic: str, hero_line: str, head_line: str, framing: str, prefix: bool, hero_in: bool = False) -> str:
    """The writer's picture text made right: the doll words out, no letters, a close-up without a place, the hero in the
    preset's words (at the marker, else - `prefix` - in front)."""
    pic = looks._BANNED.sub("", pic or "")
    pic = _TEXTY.sub("", pic)
    if framing in PLACE_FREE:
        pic = strip_place(pic)
    pic = tidy(pic)
    close = framing in PLACE_FREE
    line = head_line if close else hero_line
    if HERO_MARK in pic:
        pic = _put_hero(pic, line, close)
        prefix = False
    elif close:
        # a close-up is the head (the head line in front) or a detail of the body (a boot, a hand): the head line in
        # front of a boot drew a mask beside the feet. A close-up of the hero (`hero_in`) naming the mask / helmet and no
        # body part gets the head line, or the picture model draws a stock mask with eyes and lips (a car's hood or a
        # helmet on the asphalt in a shot without the hero is not the hero's).
        head_shot = not _BODY.search(pic) or bool(_HEAD.search(pic))
        prefix = (prefix and head_shot) or (hero_in and bool(_GEAR.search(pic)) and not _BODY.search(pic))
    if prefix:
        pic = f"{line[:1].upper()}{line[1:]}: {pic[:1].lower()}{pic[1:]}" if pic else line[:1].upper() + line[1:]
    return _one_article(re.sub(r"\s{2,}", " ", pic).strip())


_TWO_ARTICLES = re.compile(r"\b(the|a|an)\s+the\s+", re.I)   # «an a cappella» is English, «The the figure» is not


def _one_article(text: str) -> str:
    """«The the figure» (the writer's «The [HERO]» + «the figure»): one article, the first one's case kept."""
    return _TWO_ARTICLES.sub(lambda m: m.group(1) + " ", text)


def _clean_motion(motion: str, is_hero: bool) -> str:
    text = _TEXTY.sub("", motion or "")
    text = _HERO_BARE.sub(FIGURE, _HERO_POSS.sub(f"{FIGURE}'s ", text))   # the motion never carries the marker (nor the hero's line)
    if is_hero:
        text = _FRANTIC.sub("", text)
    return _one_article(tidy(text))


# ---------- the hero written from the user's words ----------
# the owner's rule: the hero follows the idea, nothing built-in «feminine / beautiful»; the writer's line with such words
# (or the doll words) is not used
_HERO_BANNED = re.compile(r"\b(?:femin\w*|beautiful|beauty|pretty|sexy|sexual|seductive|gorgeous|handsome|attractive|alluring|glamou?r\w*|"
                          r"busty|curvy|voluptuous|sensual|erotic|lingerie|cleavage|naked|nude|girly|doll\w*)\b", re.I)
_FACE_WORDS = re.compile(r"\b(?:eyes?|eyebrows?|eyelashes|lashes|lips?|mouth|smil\w+|nose|cheeks?|cheekbones?|teeth|freckles?|"
                         r"face|facial|gaze|stare|staring|looking)\b", re.I)
# a clause that says the face is hidden is kept: «the face hidden in shadow», «a mask that covers the face»
_FACE_HIDDEN = re.compile(r"(?:\b(?:no|without|hidden|hides?|hiding|covers?|covered|concealed?|conceals?|obscured?|obscures?|masked|veiled|lost)\b"
                          r"[^,;.]*\bface\b|\bface\b[^,;.]*\b(?:hidden|covered|concealed|obscured|masked|veiled|in (?:deep )?(?:black )?shadow|"
                          r"lost|invisible|not visible)\b|\bfull[- ]face\b|\bfaceless\b)", re.I)
_HIDES = re.compile(r"\b(?:mask|masked|helmet|visor|hood|hooded|veil|balaclava|shadow|silhouette|hidden|covered|concealed|faceless|goggles|mirror)\b", re.I)
HERO_MIN_WORDS, HERO_MAX_WORDS = 5, 60
HEAD_MIN_WORDS, HEAD_MAX_WORDS = 4, 40
HIDE_TAIL = "the face completely hidden in shadow"


def _words(text: str) -> int:
    return len(re.findall(r"[\w'-]+", text))


def _hero_clean(text: str, hidden: bool, max_words: int, tail: bool = True) -> str:
    """A hero line from the writer: one line, no place, no letters, the face words out when the face is hidden (a clause that
    says the face is hidden stays), cut at a comma when it runs past the limit. May come back empty."""
    text = re.sub(r"\s+", " ", str(text or "")).strip().strip("\"'«»“” ").rstrip(".")
    text = strip_place(_TEXTY.sub("", text))
    if hidden:
        text = tidy(", ".join(c.strip(" ,;.") for c in _clauses(text + ",")
                              if not _FACE_WORDS.search(c) or _FACE_HIDDEN.search(c)))
        if tail and text and not _HIDES.search(text):
            text = f"{text}, {HIDE_TAIL}"
    while _words(text) > max_words and "," in text:
        text = text.rsplit(",", 1)[0].strip()
    return text


def fix_hero(hero_en, head_en, fallback_hero: str, fallback_head: str, hidden: bool = True, keep: tuple[str, ...] = ()) -> dict:
    """The writer's `hero_en` / `head_en` (the hero from the user's words) made safe, in code:
    - empty, too short or carrying a banned word (feminine / beautiful / sexy..., the doll words) -> the fallback line
      (the preset's, or the generic figure of «Свой герой»);
    - face hidden: the face words (eyes, lips, smile, face...) are cut out except as «the face hidden» and a hiding word
      (mask, hood, shadow...) is guaranteed;
    - `keep` (a preset's mask / helmet words): at least one must stay, else the preset's line comes first and the writer's
      words follow as details.
    -> {hero, head, fallback_hero, fallback_head} (the last two: True when the fallback was used)."""
    out, flags = {}, {}
    for key, raw, fb, lo, hi in (("hero", hero_en, fallback_hero, HERO_MIN_WORDS, HERO_MAX_WORDS),
                                 ("head", head_en, fallback_head, HEAD_MIN_WORDS, HEAD_MAX_WORDS)):
        text = "" if _HERO_BANNED.search(str(raw or "")) or looks.has_banned(str(raw or "")) else _hero_clean(raw, hidden, hi, tail=False)
        bad = _words(text) < lo or bool(_HERO_BANNED.search(text))
        if bad:
            text = fb
        elif hidden and not _HIDES.search(text):
            text = f"{text}, {HIDE_TAIL}"
        elif key == "hero" and keep and not any(k in text.lower() for k in keep):
            text = f"{fb.rstrip('.')}, {text}"   # the preset's mask first, the user's details after it
        out[key], flags[key] = text, bad
    return {"hero": out["hero"], "head": out["head"], "fallback_hero": flags["hero"], "fallback_head": flags["head"]}


# ---------- the pool ----------
def _slug(title: str) -> str:
    words = re.sub(r"[^A-Za-z0-9]+", " ", str(title or ""))   # a drug word glued by underscores is still a word
    return re.sub(r"[^a-z0-9]+", "_", looks.clean_text(words).lower()).strip("_")[:28]


def _default_framing(role: str) -> str:
    return {"close": "macro", "impact": "medium", "riser": "wide", "hero": "medium", "atmos": "wide"}.get(role, "medium")


def _synth(role: str, hero_line: str, head_line: str, place: str, light: str, k: int = 0, framing: str = "") -> dict:
    """A shot the writer did not give, from a template (the hand-made clips' own shots): the pool is never short."""
    place = (place or DEFAULT_PLACE).rstrip(".")
    if role == "close":
        return {"title": "mask_macro", "framing": "macro", "role": "close",
                "picture_en": f"Extreme close-up portrait, the head fills the whole frame: {head_line}; thin {light} lines are reflected across it.",
                "motion_en": "The head slowly turns toward the camera; the reflections slide across it; haze drifts. Slow push-in."}
    if role == "riser":
        return {"title": "tunnel_flight", "framing": "wide", "role": "riser",
                "picture_en": f"Symmetrical point-of-view shot looking straight down the middle of a long dark tunnel of glowing lights receding into the distance, {light}, haze.",
                "motion_en": "The camera flies forward very fast through the tunnel; the lights rush past. Fast forward flight."}
    if role == "impact":
        return {"title": "hero_arms", "framing": "medium", "role": "impact",
                "picture_en": f"Low-angle shot of {hero_line}, standing in {place}, {light} radiating from behind.",
                "motion_en": "The figure slowly raises both arms up; the light behind explodes outward and sweeps; haze swirls. Slow push-in."}
    if role == "hero":
        poses = (("Full-body shot of", "stands still, then turns the head slowly toward the camera"),
                 ("Medium shot of", "nods the head to the beat and moves the shoulders"),
                 ("Wide shot of", "walks toward the camera with confident steps"),
                 ("Low-angle shot of", "slowly spreads both arms"),
                 ("Seen from behind:", "raises one arm toward the light"),
                 ("Waist-up shot of", "slowly turns the head from side to side"))[k % 6]
        return {"title": f"hero_{k + 1}", "framing": "medium" if k % 3 else "wide", "role": "hero",
                "picture_en": f"{poses[0]} {hero_line}, in {place}, {light}, haze.",
                "motion_en": f"The figure {poses[1]}; the light flickers; haze drifts. Static camera."}
    if role == "atmos" and framing in PLACE_FREE:
        mac = ("Macro of a black speaker cone with tiny water droplets resting on it, a rim of coloured light, darkness behind.",
               "Macro of liquid chrome drops on a black glossy surface, reflecting a bright line of light, dark.",
               "Extreme macro of tiny glitter particles floating in a single beam of light in darkness.",
               "Close-up of a black-gloved hand on a hardware synthesizer with rows of knobs and glowing LEDs, haze.")[k % 4]
        return {"title": f"macro_{k + 1}", "framing": framing, "role": "atmos", "picture_en": mac,
                "motion_en": "Droplets and reflections shimmer in rhythm; haze drifts. Static macro."}
    atm = ("A fan of bright light beams sweeps over a silhouetted crowd with raised hands, thick haze.",
           "A huge wall of strobe light panels flashing on a dark stage, haze in front.",
           "Top-down view from high above a packed crowd, many raised hands, light beams cutting through haze, faces too small to see.",
           "A row of CO2 cannons blasting tall white jets of fog over a dark crowd.",
           "A dense shower of sparks falling in darkness, silhouettes below.",
           "Black glossy floor reflecting a bright line of light, small ripples.")[k % 6]
    return {"title": f"atmos_{k + 1}", "framing": "wide", "role": "atmos", "picture_en": atm,
            "motion_en": "The lights sweep and flicker in rhythm; haze rolls. Static camera."}


def _is_hero_text(shot: dict) -> bool:
    return HERO_MARK in (shot.get("picture_en") or "")


def _normalise(raw: list, hero_line: str, head_line: str) -> list[dict]:
    shots = []
    for r in raw or []:
        if not isinstance(r, dict) or not str(r.get("picture_en") or "").strip():
            continue
        role = str(r.get("role") or "").strip().lower()
        role = role if role in ROLES else "atmos"
        if role == "atmos" and HERO_MARK in str(r.get("picture_en") or ""):
            role = "hero"   # the marker says a body is in it, whatever the writer called it
        framing = str(r.get("framing") or "").strip().lower()
        framing = framing if framing in FRAMINGS else _default_framing(role)
        shots.append({"title": _slug(r.get("title") or "") or role, "framing": framing, "role": role,
                      "picture_en": str(r["picture_en"]).strip(), "motion_en": str(r.get("motion_en") or "").strip()})
    return shots


def _pick(shots: list[dict], role: str, score: Callable[[dict], float], pool: tuple[str, ...]) -> Optional[dict]:
    cands = [s for s in shots if s["role"] in pool]
    cands = [s for s in cands if score(s) > 0]
    return max(cands, key=score) if cands else None


def fix_pool(raw: list, hero_line: str, head_line: str = "", place: str = "", light: str = "", n: int = 16) -> list[dict]:
    """The writer's list made a pool: the fields normalised, the roles filled (repair by reassigning where a shot fits,
    else a template shot), the hero in the preset's words, the doll and drug words out of the titles and pictures, a
    close-up without a place, no «hard / wild / frantic» for a body, no letters. The order of the writer's list is kept;
    a shot the code adds goes to the end. `hero_line` is the preset's line, `head_line` its mask close-up (hero.FACELESS_HEAD)."""
    head_line = head_line or hero_line
    shots = _normalise(raw, hero_line, head_line)
    for s in shots:
        s["_hero"] = _is_hero_text(s) or s["role"] in ("hero", "impact")   # a body is in it (the marker or the role says)

    # --- the roles: one close, one impact, one riser; the surplus goes back to hero / atmos
    for role, back in (("close", "atmos"), ("impact", "hero"), ("riser", "atmos")):
        have = [s for s in shots if s["role"] == role]
        for extra in have[1:]:
            extra["role"] = "hero" if extra["_hero"] else back
    if not any(s["role"] == "close" for s in shots):
        # the mask macro: a hero shot that is already a close-up, else a template (an object's macro is not the mask)
        s = _pick(shots, "close", lambda x: 2.0 if x["framing"] in PLACE_FREE else 0.0, ("hero",))
        if s:
            s["role"], s["framing"] = "close", s["framing"] if s["framing"] in PLACE_FREE else "macro"
        else:
            shots.append({**_synth("close", hero_line, head_line, place, light), "_hero": True, "_syn": True})
    if not any(s["role"] == "impact" for s in shots):
        # the sharpest hero shot: a wider hero shot whose motion is a burst, a jump, a spin
        s = _pick(shots, "impact", lambda x: (1.0 + 2 * bool(_IMPACT.search(x["motion_en"])) + (x["framing"] in ("medium", "wide")))
                  if x["_hero"] and x["framing"] not in PLACE_FREE else 0.0, ("hero",))
        if s:
            s["role"] = "impact"
        else:
            shots.append({**_synth("impact", hero_line, head_line, place, light), "_hero": True, "_syn": True})
    if not any(s["role"] == "riser" for s in shots):
        # a tunnel / point-of-view flight; a shot that is not the hero's close-up
        s = _pick(shots, "riser", lambda x: (1.0 + 3 * bool(_RISER.search(x["picture_en"] + " " + x["motion_en"])) + 2 * (not x["_hero"])) if x["framing"] not in PLACE_FREE
                  and (x["role"] == "atmos" or x["_hero"]) and x["role"] not in ("close", "impact")
                  and _RISER.search(x["picture_en"] + " " + x["motion_en"]) else 0.0, ("atmos", "hero"))
        if s:
            s["role"] = "riser"
        else:
            shots.append({**_synth("riser", hero_line, head_line, place, light), "_hero": False, "_syn": True})
    for role, need, key in (("hero", MIN_HERO, 0), ("atmos", MIN_ATMOS, 0)):
        k = 0
        while sum(s["role"] == role for s in shots) < need:
            shots.append({**_synth(role, hero_line, head_line, place, light, k), "_hero": role == "hero", "_syn": True})
            k += 1
    # trim a pool longer than n: the surplus atmos / hero shots (never a special one), from the end
    while len(shots) > max(n, MIN_HERO + MIN_ATMOS + 3):
        spare = [s for s in shots if s["role"] in ("hero", "atmos")]
        counts = {r: sum(s["role"] == r for s in shots) for r in ("hero", "atmos")}
        spare = [s for s in spare if counts[s["role"]] > (MIN_HERO if s["role"] == "hero" else MIN_ATMOS)]
        if not spare:
            break
        shots.remove(spare[-1])

    # --- the close shot is a macro or a close-up by definition; the riser a wide flight
    for s in shots:
        if s["role"] == "close" and s["framing"] not in PLACE_FREE:
            s["framing"] = "macro"
        if s["role"] == "riser" and s["framing"] in PLACE_FREE:
            s["framing"] = "wide"

    # --- the text, by the rules of the code
    seen: set[str] = set()
    for i, s in enumerate(shots):
        body = s.pop("_hero")
        syn = s.pop("_syn", False)
        if not syn:   # a template shot already carries the preset's words and no place in a close-up
            s["picture_en"] = _clean_picture(s["picture_en"], hero_line, head_line, s["framing"],
                                             prefix=s["role"] in ("hero", "impact") and HERO_MARK not in s["picture_en"],
                                             hero_in=bool(body) or s["role"] in ("hero", "impact", "close"))
        s["motion_en"] = _clean_motion(s["motion_en"], body)
        if looks.has_banned_title(s["title"]):
            s["title"] = looks.clean_text(s["title"])
        base = _slug(s["title"]) or s["role"]
        t, k = base, 2
        while t in seen:
            t, k = f"{base}_{k}", k + 1
        seen.add(t)
        s["title"] = t
        # the writer's picture / motion left empty by the clean-up: a template of the same role takes its place
        if len(s["picture_en"]) < 12:
            s.update({k2: v for k2, v in _synth(s["role"], hero_line, head_line, place, light, i, s["framing"]).items() if k2 in ("picture_en", "motion_en")})
        if len(s["motion_en"]) < 8:
            s["motion_en"] = "Light flickers and haze drifts in rhythm. Static camera."
    return shots


# ---------- the graph's nodes ----------
def pool_to_nodes(pool: list[dict], style: str, mstyle: str, seed: int = 1, cols: int = 6, new_id: Optional[Callable[[], str]] = None,
                  ref_id: Optional[str] = None, ref_model: str = "flux2", model: str = "h3") -> dict:
    """The pool as graph nodes, shots.py's way: per shot a `picture` (the prompt by framing, the title «pic <t>»), a `prompt`
    («move <t>», the scene's text) and a `scene` (3 s, from the picture, titled <t>) with `data.role` and `data.framing`
    (the beat renderer reads them). The edges: picture.image -> scene.start, prompt.text -> scene.prompt. `ref_id`: a
    picture node (a hero's portrait) that goes into every hero shot's `ref` (the model switches to `ref_model`). `model`: the
    video model of the scenes - "h3" is the graph's own and leaves the nodes as they were; another one is put on every scene
    (`model`) with its own prompt (scene_prompt).
    -> {"nodes": [...], "edges": [...]}"""
    new_id = new_id or (lambda: uuid.uuid4().hex[:8])
    nodes, edges = [], []
    for i, shot in enumerate(pool):
        x, y = 360 * (i % cols), 900 * (i // cols)
        title = shot["title"]
        pic_data = {"prompt": picture_prompt(shot, style, mstyle), "seed": int(shot.get("seed") or seed), "title": f"pic {title}"}
        use_ref = bool(ref_id) and shot["role"] in ("hero", "impact", "close")
        if use_ref:
            pic_data["model"] = ref_model
        pic = {"id": new_id(), "type": "picture", "position": {"x": x, "y": y}, "data": pic_data}
        mov = {"id": new_id(), "type": "prompt", "position": {"x": x, "y": y + 380}, "data": {"text": scene_prompt(shot, model=model), "title": f"move {title}"}}
        scn = {"id": new_id(), "type": "scene", "position": {"x": x, "y": y + 560},
               "data": {"seconds": SCENE_SECONDS, "seed": 1, "title": title, "role": shot["role"], "framing": shot["framing"]}}
        if model != "h3":
            scn["data"]["model"] = model
        nodes += [pic, mov, scn]
        edges.append({"id": new_id(), "source": pic["id"], "sourceHandle": "image", "target": scn["id"], "targetHandle": "start"})
        edges.append({"id": new_id(), "source": mov["id"], "sourceHandle": "text", "target": scn["id"], "targetHandle": "prompt"})
        if use_ref:
            edges.append({"id": new_id(), "source": ref_id, "sourceHandle": "image", "target": pic["id"], "targetHandle": "ref"})
    return {"nodes": nodes, "edges": edges}
