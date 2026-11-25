"""A screenplay as text (the graph's «Сценарий» node): parse it, cut it into shots, subtitle it. No I/O, no LLM.

The format (Russian, simple enough to type by hand):

    СЦЕНА 1. Берег моря, закат.
    ОН (тихо): Ты замёрзла?
    ОНА (с улыбкой): Нет. Мне хорошо.
    — Она кладёт голову ему на плечо.

- «СЦЕНА N. Место, время.» starts a new place;
- «ИМЯ (ремарка): слова» is a line; the remark maps to prompts.HOW (сердито -> angry), an unknown one stays as free text;
- a line starting with «—» is an action; any other line of text is an action too.

Names map to the cast (the connected «Герой» nodes, in order): by the hero's name first (case-insensitive), then
«ОН» / «ОНА» by the hero's gender, then in the order the names first appear (the first new name is the first hero).

The shots follow the rules the GPU tests of 2026-11-09 proved on H3 Ref2VA: ONE SPEAKER PER SHOT, the line in that
shot only, «Only X speaks; the other one listens silently»; the speaker's face first among the pictures.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from . import i18n, looks
from .planner import prompts

WORDS_PER_SECOND = prompts.WORDS_PER_SECOND   # 2.5
MIN_SHOT, MAX_SHOT, ACTION_SHOT = 3, 10, 5    # seconds (an action 5: room for the camera move)
LEAD = 1                                       # a line starts a second into its shot (a look first): lines_timeline's own

# remark words (Russian stems) -> prompts.HOW keys; matched on the whole remark, lower-cased, ё = е
_HOW_RU = [
    ("whisper", ("шепот", "шепч", "whisper")), ("shout", ("кричит", "крича", "крик", "орет", "вопит", "shout", "yell")),
    ("loud", ("громк", "loud")), ("soft", ("тих", "мягк", "soft", "quiet", "gentl")), ("calm", ("спокой", "ровно", "невозмутим", "calm")),
    ("laugh", ("смех", "смея", "смеет", "хохоч", "хихик", "laugh", "giggl", "chuckl")), ("smile", ("улыб", "smil")),
    ("angry", ("серд", "зло", "злой", "злост", "гневн", "раздраж", "яростн", "angr", "furious")),
    ("sad", ("грустн", "печальн", "уныло", "с грустью", "горьк", "sad")), ("scared", ("испуг", "со страхом", "боязл", "в ужасе", "дрожащ", "fear", "scared", "afraid")),
    ("thoughtful", ("задумчив", "размышл", "thought")), ("tender", ("нежн", "ласков", "tender")), ("sing", ("поет", "напева", "поющ", "sing")),
]
_REMARK_RU = {"soft": "тихо", "whisper": "шёпотом", "loud": "громко", "shout": "кричит", "laugh": "со смехом", "smile": "с улыбкой",
              "angry": "сердито", "sad": "грустно", "scared": "испуганно", "thoughtful": "задумчиво", "tender": "нежно",
              "calm": "спокойно", "sing": "поёт"}
_REMARK_EN = {"soft": "softly", "whisper": "whispering", "loud": "loudly", "shout": "shouting", "laugh": "laughing", "smile": "smiling",
              "angry": "angrily", "sad": "sadly", "scared": "fearfully", "thoughtful": "thoughtfully", "tender": "tenderly",
              "calm": "calmly", "sing": "singing"}   # every word is read back by how_of (the stems in _HOW_RU)

SCENE_RE = re.compile(r"^\s*(?:СЦЕНА|SCENE)(?![^\W\d_])\s*(\d+)?\s*[.:)\-–—]?\s*(.*)$", re.I)
LINE_RE = re.compile(r"^\s*([^\W\d_][^:()—–]{0,38}?)\s*(?:\(([^)]*)\))?\s*:\s*(\S.*)$", re.U)
ACTION_RE = re.compile(r"^\s*[—–]\s*(.*\S)\s*$|^\s*-\s+(.*\S)\s*$")
FALLBACK_NAME = re.compile(r"^(?:герой|hero)\s+(\d{1,2})$")
QUOTES = '"«»“”„ '
MALE_PRON, FEMALE_PRON = {"он", "he"}, {"она", "she"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").casefold().replace("ё", "е")).strip()


def how_of(remark: str) -> tuple[str, str]:
    """A remark in parentheses -> (a prompts.HOW key, the free manner). A known remark gives the key and no manner; an
    unknown one gives no key and keeps the words as the manner; an empty one gives neither."""
    r = _norm(remark)
    if not r:
        return "", ""
    if r in prompts.HOW and r:
        return r, ""
    for key, stems in _HOW_RU:
        if any(r.startswith(s.strip()) or f" {s.strip()}" in f" {r}" for s in stems):
            return key, ""
    return "", remark.strip()


def remark_ru(how: str, manner: str = "", english: bool = False) -> str:
    """The way back: a HOW key (or a free manner) -> the remark's words (English ones for an English text), "" for a plain line."""
    return manner or (_REMARK_EN if english else _REMARK_RU).get(how, "")


def _cast_list(cast) -> list[dict]:
    return [{"name": c, "gender": ""} if isinstance(c, str) else
            {"name": c.get("name") or "", "gender": c.get("gender") or "", "kind": c.get("kind") or "person"} for c in cast or []]


def person(cast: list[dict], i: int) -> bool:
    """A human hero: the car rules (seated inside, standing by it) are for people only - a robot that IS the car, or a
    dog, is not a passenger (GPU test 2026-11-10, «Стальные стражи»: the robot Volt was put «inside the car»)."""
    return 0 <= i < len(cast) and (cast[i].get("kind") or "person") == "person"


def _is_name(token: str, cast: list[dict]) -> bool:
    """«Маша» before a colon is a speaker when it is written in capitals (ОНА, МАША) or is a hero's name; «Примечание: …»
    is not."""
    t = token.strip()
    return bool(t) and (t.upper() == t or _match(t, cast) is not None)


def _match(token: str, cast: list[dict]) -> Optional[int]:
    n = _norm(token)
    for i, c in enumerate(cast):
        full = _norm(c["name"])
        if full and (n == full or n == full.split(" ")[0] or f" {n} " in f" {full} "):
            return i
    if (m := FALLBACK_NAME.match(n)) and 0 < int(m.group(1)) <= len(cast):   # «Герой 2»: what render writes for a name that can't be read back
        return int(m.group(1)) - 1
    return None


def parse(text: str, cast=None) -> dict:
    """The screenplay -> {"scenes": [{"n", "place"}], "beats": [...], "unknown": [names that found no hero]}.
    A beat: {"kind": "line" | "action", "scene": index into scenes, "text", and for a line "who" (as written), "cast"
    (the hero's index in the cast, None for a stranger), "how" (a prompts.HOW key), "manner" (a free remark)}."""
    cast = _cast_list(cast)
    scenes: list[dict] = []
    raw: list[dict] = []
    for row in (text or "").replace("\r", "").split("\n"):
        row = row.strip()
        if not row:
            continue
        if m := SCENE_RE.match(row):
            scenes.append({"n": int(m.group(1)) if m.group(1) else len(scenes) + 1, "place": m.group(2).strip().rstrip(".").strip()})
            continue
        if not scenes:
            scenes.append({"n": 1, "place": ""})
        if m := ACTION_RE.match(row):
            raw.append({"kind": "action", "scene": len(scenes) - 1, "text": (m.group(1) or m.group(2)).strip()})
            continue
        if (m := LINE_RE.match(row)) and _is_name(m.group(1), cast):
            how, manner = how_of(m.group(2) or "")
            raw.append({"kind": "line", "scene": len(scenes) - 1, "who": m.group(1).strip(), "text": m.group(3).strip().strip(QUOTES).strip(),
                        "how": how, "manner": manner, "remark": (m.group(2) or "").strip()})
            continue
        raw.append({"kind": "action", "scene": len(scenes) - 1, "text": row.strip(QUOTES).strip()})
    # the names -> the cast: the heroes' own names first (the whole text), then ОН / ОНА by gender, then in order
    who_of: dict[str, Optional[int]] = {}
    names = list(dict.fromkeys(_norm(b["who"]) for b in raw if b["kind"] == "line"))
    for n in names:
        if (i := _match(n, cast)) is not None:
            who_of[n] = i
    used = {i for i in who_of.values() if i is not None}
    for n in names:
        if n in who_of:
            continue
        want = "male" if n in MALE_PRON else "female" if n in FEMALE_PRON else ""
        pick = next((i for i, c in enumerate(cast) if i not in used and want and c["gender"] == want), None)
        if pick is None and want:   # «ОНА» when the one woman has a name in the text: she is that woman
            pick = next((i for i, c in enumerate(cast) if c["gender"] == want), None)
        if pick is not None:
            who_of[n] = pick
            used.add(pick)
    for n in names:
        if n in who_of:
            continue
        pick = next((i for i in range(len(cast)) if i not in used), None)
        who_of[n] = pick
        if pick is not None:
            used.add(pick)
    unknown = []
    for b in raw:
        if b["kind"] == "line":
            b["cast"] = who_of.get(_norm(b["who"]))
            if b["cast"] is None and b["who"] not in unknown:
                unknown.append(b["who"])
    return {"scenes": scenes, "beats": raw, "unknown": unknown}


# an action about «они» / «оба» / «all together» has no single subject: every hero of the scene is in the shot
_PLURAL = {"они", "оба", "обе", "обоих", "обеих", "оба", "все", "вместе", "вдвоем", "друг", "друга", "пара", "парой", "they", "both", "together", "everyone"}
# pronouns of heroes named «Он» / «Она» (a prefix match would find «Он» inside «Они» and «Она»), ё = е
_PRON = {"он": {"он", "его", "ему", "им", "ним", "нем", "he", "him", "his"}, "она": {"она", "ее", "ей", "ею", "ней", "she", "her"}}
_PRON["he"], _PRON["she"] = _PRON["он"], _PRON["она"]   # an English template names its heroes «He» / «She»


def _words(text: str) -> list[str]:
    return re.findall(r"[\w'-]+", _norm(text))


def mentioned(text: str, cast: list[dict]) -> list[int]:
    """The heroes an action names, in order of the text: by the name's stem («Маша», «Маши», «Машу»; a case ending of up
    to three letters), a short name («Он», «Она») only as that word or its own pronoun forms - never as the start of
    «Они»."""
    found = []
    for i, c in enumerate(cast):
        name = _norm(c["name"]).split(" ")[0]
        if not name:
            continue
        stem = name[:-1] if len(name) > 3 else name
        forms = _PRON.get(name, {name})
        for k, w in enumerate(_words(text)):
            if w in forms or (len(name) > 3 and w.startswith(stem) and len(w) <= len(name) + 3):
                found.append((k, i))
                break
    return [i for _, i in sorted(found)]


def plural(text: str) -> bool:
    """The action speaks of several people at once («Они…», «Оба…», «вместе»)."""
    return any(w in _PLURAL for w in _words(text))


# Cars (GPU test «Полный газ: Рио» 2026-11-10, the owner: «люди плывут по асфальту, девушка проходит сквозь машины»):
# a car action with no hero named got the scene's heroine as its face, and H3 drew her standing on the highway gliding
# along with the traffic; «leans out of the car window» became standing on the car. A car with no hero named is a
# shot of cars only; a hero in a car stays seated inside it, and the prompt asks for solid cars.
_VEHICLE = ("машин", "маслкар", "автомоб", "грузовик", "броневик", "внедорожник", "мотоцикл", "джип", "фургон", "автобус")
_VEHICLE_EN = {"car", "cars", "truck", "trucks", "suv", "van", "motorcycle", "vehicle", "vehicles"}   # whole words: not «vanish»
_IN_CAR = ("за рулем", "сиденье", "сиденьи", "из окна", "в окне", "в машине", "в салоне", "behind the wheel", "seat", "window",
           # the driver's verbs: «Марко разворачивает маслкар в заносе» is at the wheel
           "разворачива", "ведет", "гонит", "жмет", "тормозит", "дрифт", "занос")
# Second GPU test (the owner: «люди выходят сквозь машины, полицейский стоя, машина едет назад»): a hero «ставит
# внедорожник поперёк моста» was drawn standing on the road, a car drove backwards. A hero with a car is at its wheel
# unless the action puts them by it («стоит у», «выходит из»), and the cars drive nose first.
_OUT_OF_CAR = ("стоит у", "стоят у", "стоит возле", "стоят возле", "рядом с", "выходит", "выходят", "выпрыгивает",
               "вылезает", "подходит к", "подходят к", "опирается", "на капоте", "on the hood", "steps out", "stand by", "stands by")
CAR_PHYSICS = ("Real physics: the cars are solid and never pass through each other or through people; every car drives "
               "forward, nose first, its wheels turning the right way; anyone in a moving car stays seated inside it; "
               "nobody stands or walks on the road among moving traffic.")
IN_CAR_ACTION = ("{who} stays inside the car the whole time, seen through the windshield or the side window, at most "
                 "leaning out of the window; {who} never stands on the road or walks through a car.")
# Third GPU test (the owner: «все люди вылазят сквозь машину», «смотрит вбок - там персонаж»): heroes «у машины» were
# drawn climbing out through the car body, and a hero looking off-screen got a double of a hero in that direction.
# By a car the heroes stand still in front of it, the car closed behind them; a look goes just past the lens.
BY_CAR = ("{who} already stand{s} outside the car from the first frame, a step in front of it, the car parked behind "
          "{them} with its doors shut; nobody opens a door, gets out of the car or passes through its body; {who} "
          "stay{s} on this side of the car and do{es} not walk around it.")
_EXIT = ("выходит", "выходят", "выпрыгивает", "выпрыгивают", "вылезает", "вылезают", "steps out", "get out", "gets out")
SOLO_SEAT = "The seat beside {who} is empty or out of the frame: no passenger, no second person in the car."
_EXIT_EN = re.compile(r"\b(get|step|climb|jump|leap|hop)(s?)\s+out\s+of\b", re.I)


def by_car_text(act: str) -> str:
    """«Marko steps out of the car» -> «Marko stands by the car»: the getting out itself is what H3 draws through the
    car body, so the shot starts with the heroes already out."""
    return _EXIT_EN.sub(lambda m: "stand" + m.group(2) + " by", act)
CARS_ONLY = "Only the vehicles are seen: no people on the road, the drivers hidden behind dark tinted glass."


def vehicle(text: str) -> bool:
    """The action is about a car (a truck, a motorbike…)."""
    return any(w.startswith(_VEHICLE) or w in _VEHICLE_EN for w in _words(text))


def in_car(text: str) -> bool:
    """The action puts its heroes inside a car («за рулём», «на сиденье», «высовывается из окна»)."""
    t = " ".join(_words(text))
    return vehicle(text) and (any(x in t for x in _IN_CAR) or not any(x in t for x in _OUT_OF_CAR))


def explicit_in_car(text: str) -> bool:
    """The action itself says a hero is in the seat («за рулём», «на сиденье», «из окна»), not only that a car is there."""
    t = " ".join(_words(text))
    return vehicle(text) and any(x in t for x in _IN_CAR)


def words_of(text: str) -> int:
    return len(re.findall(r"[\w'-]+", text or ""))


# The camera moves (the owner, 2026-11-10: «фон будто статичный, мы же кино делаем — нужны динамичные сцены»): every
# shot gets a camera move and a living background instead of «static camera». A scene opens on a wide establishing
# move; the actions cycle through the moves; a line keeps the speaker in a close-up, the camera drifting gently.
OPENING_MOVES = ("a slow sweeping crane shot descending", "a smooth drone-like glide forward", "a slow orbit")
ACTION_MOVES = ("tracking shot following the action", "low-angle dolly push-in", "slow orbit around the subject",
                "handheld shot moving with the action", "crane shot rising over the action", "fast push-in")
LINE_MOVES = ("slow push-in", "subtle handheld movement", "slow lateral slide")
ALIVE_ACTION = "Dynamic shot with real depth and motion: the light, the air and the background move (particles, weather, flickering light)."
ALIVE_LINE = "The background is alive and out of focus: light and atmosphere move behind."


def line_move(shot: dict) -> str:
    return LINE_MOVES[shot["i"] % len(LINE_MOVES)]


def shot_seconds(text: str, line: bool = True) -> int:
    """A shot's length from its words: 2.5 words a second and the second the line starts after, 3 to 10 s. An action
    is 4 s."""
    if not line:
        return ACTION_SHOT
    return max(MIN_SHOT, min(MAX_SHOT, math.ceil(words_of(text) / WORDS_PER_SECOND) + LEAD))


def shots(sp: dict, cast=None) -> list[dict]:
    """The beats -> the shots, one each: a line (one speaker, the listener, the camera) or an action. A shot:
    {"i", "kind", "scene", "place", "text", "who", "how", "manner", "speaker", "listener", "faces", "seconds", "camera", "gaze"}
    - `speaker` is the cast index (None for an action or a stranger), `listener` the one who stays silent, `faces` the
    cast indexes in the picture, the speaker first (at most 3)."""
    cast = _cast_list(cast) or []
    beats = sp["beats"]
    # who is in each scene: the speakers and the names an action mentions, in order of appearance
    present: dict[int, list[int]] = {}
    for b in beats:
        ids = [b["cast"]] if b["kind"] == "line" and b["cast"] is not None else mentioned(b["text"], cast) if b["kind"] == "action" else []
        for i in ids:
            if i not in present.setdefault(b["scene"], []):
                present[b["scene"]].append(i)
    out: list[dict] = []
    last: dict[int, int] = {}   # scene -> who spoke last
    opener: dict[int, int] = {}   # scene -> its first speaker: looks off-screen right, the others left (shot / reverse shot)
    # scene -> who is in it so far: a listener must be there already. Those of the scene's first two beats are there
    # from its start («ОН: Ты замёрзла?» opens the scene and she listens); the others come in when they first appear
    seen: dict[int, list[int]] = {}
    riding: list[int] = []   # the heroes seated in a car (lines from inside it) until an action puts them out of it
    first: dict[int, int] = {}
    for b in beats:
        n = first[b["scene"]] = first.get(b["scene"], 0) + 1
        if n <= 2:
            ids = [b["cast"]] if b["kind"] == "line" and b["cast"] is not None else mentioned(b["text"], cast) if b["kind"] == "action" else []
            for i in ids:
                if i not in seen.setdefault(b["scene"], []):
                    seen[b["scene"]].append(i)
    for b in beats:
        s = b["scene"]
        place = sp["scenes"][s]["place"] if s < len(sp["scenes"]) else ""
        here = present.get(s, [])
        shot = {"i": len(out), "kind": b["kind"], "scene": s, "place": place, "text": b["text"], "who": "", "how": "", "manner": "",
                "speaker": None, "listener": None, "faces": [], "camera": "", "gaze": "", "vehicle": False, "in_car": False,
                "opening": not any(o["scene"] == s for o in out)}
        if b["kind"] == "line":
            sp_i = b["cast"]
            # the listener: someone already in the scene - a heroine alone in the street does not get the hero, who
            # only comes three shots later, behind her shoulder (GPU test 2026-11-09)
            others = [i for i in seen.get(s, []) if i != sp_i]
            prev = last.get(s)
            listener = prev if prev is not None and prev != sp_i and prev in others else (others[-1] if others else None)
            shot.update(who=b["who"], how=b["how"], manner=b["manner"], speaker=sp_i, listener=listener,
                        # only the speaker's picture: with the listener's too H3 drew the listener twice - facing
                        # the camera beside the speaker and again from behind (GPU test 2026-11-09); the listener is
                        # described as seen from behind instead (shot_prompt)
                        faces=[sp_i] if sp_i is not None else ([listener] if listener is not None else []),
                        camera="close", seconds=shot_seconds(b["text"]),
                        gaze=("right" if opener.setdefault(s, sp_i) == sp_i else "left") if listener is not None else "",
                        in_car=sp_i is not None and sp_i in riding and person(cast, sp_i))
            if sp_i is not None:
                last[s] = sp_i
        else:
            ids = mentioned(b["text"], cast)
            car = vehicle(b["text"])
            if car and not ids and not plural(b["text"]):
                ids = []   # «Чёрный маслкар проносится…»: the cars alone, not the scene's heroine on the highway
            elif (plural(b["text"]) and len(ids) < 2) or not ids:   # «Они…» or no subject: everyone of the scene;
                # «Вольт и Крон бросаются друг на друга» stays the two named, not the heroine watching
                ids = here if here and (len(here) > 1 or not plural(b["text"])) else list(range(len(cast)))
            named = [i for i in mentioned(b["text"], cast) if person(cast, i)]
            robot = any(not person(cast, i) for i in mentioned(b["text"], cast))
            if car and named and in_car(b["text"]) and (not robot or explicit_in_car(b["text"])):
                riding.extend(i for i in named if i not in riding)
            elif named:   # «Марко и Ника стоят у маслкара», «Иван выходит на обочину»: out of the car
                riding[:] = [i for i in riding if i not in named]
            shot.update(faces=ids[:3], camera="medium", seconds=shot_seconds(b["text"], line=False), vehicle=car,
                        # a robot in the action: the car is the robot, the heroine beside it is not riding
                        # unless the action says so («Ника за рулём»)
                        in_car=any(person(cast, i) for i in ids[:3]) and in_car(b["text"])
                        and (all(person(cast, i) for i in ids[:3]) or explicit_in_car(b["text"])))
        for i in ([shot["speaker"]] if shot["speaker"] is not None else []) + list(shot["faces"]):
            if i not in seen.setdefault(s, []):
                seen[s].append(i)
        out.append(shot)
    return out


# ---------- the English the prompt needs: places, actions, free remarks, the series' free style ----------
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
NEUTRAL_STYLE = "Realistic live-action cinematic look"   # no «Сериал» / no look: as the other templates start


def russian(text: str) -> bool:
    return bool(CYRILLIC.search(text or ""))


def texts_for_prompt(shot: dict) -> list[str]:
    """The Russian words of a shot that go into its ENGLISH prompt: the place, an action, a line's free manner."""
    out = [shot["place"]] if shot.get("place") else []
    if shot["kind"] == "action":
        out.append(shot["text"])
    elif shot.get("manner"):
        out.append(shot["manner"])
    return [x for x in out if x and russian(x)]


def missing_tr(shots_: list[dict], tr: Optional[dict], extra: tuple = ()) -> list[str]:
    """What still has no English in `tr` (the Russian text -> its English), once each, in order; `extra`: more texts
    (the series' free style)."""
    tr = tr or {}
    seen: dict[str, None] = {}
    for x in [t for sh in shots_ for t in texts_for_prompt(sh)] + [e for e in extra if russian(e)]:
        if not (tr.get(x) or "").strip():
            seen[x] = None
    return list(seen)


def style_line(look_id: Optional[str], free: str = "", tr: Optional[dict] = None) -> str:
    """The series' look as the first line of a shot's prompt: the look's style_en (the words the studio's prompts start
    with, the same the scene's look puts in front - a swap finds it), then the free `style` in English; the neutral
    live-action look when neither is set."""
    parts = []
    if look_id and look_id in looks.LOOKS and look_id != looks.AUTO:
        parts.append(looks.LOOKS[look_id]["style_en"].strip().rstrip("."))
    free = (free or "").strip()
    if free:
        en = (tr or {}).get(free) or ("" if russian(free) else free)
        if en:
            parts.append(en.strip().rstrip("."))
    out = ", ".join(x for x in parts if x) or NEUTRAL_STYLE
    return out[0].upper() + out[1:]


# ---------- the prompt of a shot (H3's format, the one «Промт» nodes hold: the lines are woven in by prompts.weave_lines) ----------
def _who(cast: list[dict], i: int) -> str:
    """How the prompt names a hero: Character N, the single hero by gender (as prompts.speaker)."""
    if len(cast) > 1:
        return f"Character {i + 1}"
    g = cast[0].get("gender") if cast else ""
    return "The heroine" if g == "female" else "The hero" if g == "male" else "The main character"


def prompt_of(shot: dict, cast: list[dict], looks_en: dict[int, dict], photos: list[int], tr: Optional[dict] = None,
              style: str = "") -> tuple[str, list[dict]]:
    """A shot -> (the «Промт» text without its line, the lines [{who, text, how}] - one or none).
    `cast`: [{name, gender}], `looks_en`: cast index -> {en, outfit_en} (the heroes' looks), `photos`: the cast indexes
    whose picture goes in as <Picture k>, in the order of the shot's `faces` (the speaker first); `tr`: the Russian
    place / action -> its English, when the writer gave one; `style`: the look's words in front, when no look is set
    on the scene itself."""
    tr = tr or {}
    parts = [style.rstrip(".") + "."] if style else []
    pics = [i for i in shot["faces"] if i in photos]
    for k, i in enumerate(pics):
        parts.append(f"{_who(cast, i)} is the person in <Picture {k + 1}>: exactly the same face and hair as in <Picture {k + 1}>.")
    locks = []
    for i in shot["faces"]:
        c = looks_en.get(i) or {}
        if c.get("en"):
            locks.append(f"{_who(cast, i)} (the same in every shot): {prompts._sentence(c['en'])}{prompts._wearing(c)}")
    parts += locks
    place = tr.get(shot["place"]) or shot["place"]
    if place:
        parts.append("Scene: " + prompts._sentence(place))
    lines: list[dict] = []
    if shot["kind"] == "line":
        spk = _who(cast, shot["speaker"]) if shot["speaker"] is not None else "The other person"
        lst = _who(cast, shot["listener"]) if shot["listener"] is not None else ""
        if shot.get("in_car"):
            # the hero said «за рулём» a beat before: the line comes from the car's seat, not from the road
            # no «the person beside them»: H3 drew that person, often a double of the speaker (GPU test 2026-11-10)
            parts.append(f"Camera: close-up of {spk} seated inside the moving car, filmed through the side window, "
                         f"the city lights streaking past outside, {line_move(shot)}; a single person in the frame.")
            parts.append(f"Only {spk} speaks. {SOLO_SEAT.format(who=spk)} {CAR_PHYSICS}")
            beat = f"{spk} keeps the eyes on the road ahead and is about to speak"
        elif lst:
            # shot / reverse shot: the speaker alone, the listener off-screen. Any over-the-shoulder wording (the
            # listener's picture or not, «exactly two people») made H3 draw both facing the camera plus a third person
            # from behind, and the listener's face drifted without a picture (GPU tests 2026-11-09, «Зонт»). A look
            # «off-screen to the right at the other person» drew that person (a double) on that side (2026-11-10):
            # the eyes go just past the lens and nobody else is named.
            side = "left" if shot.get("gaze") == "left" else "right"
            parts.append(f"Camera: close-up of {spk} alone in the frame, nobody else in the shot, {line_move(shot)}; {spk} looks "
                         f"just past the camera lens, slightly to the {side}; the background behind is empty of people.")
            parts.append(f"Only {spk} speaks. {ALIVE_LINE}")
            beat = f"{spk} looks just past the camera and is about to speak"
        else:
            parts.append(f"Camera: close-up on {spk}, {line_move(shot)}. {ALIVE_LINE}")
            parts.append(f"Only {spk} speaks.")
            beat = f"{spk} looks ahead and is about to speak"
        if shot["manner"]:
            beat += f", the manner: {tr.get(shot['manner']) or shot['manner']}"
        parts.append(f"Timeline:\n[0s-{shot['seconds']}s] {beat}.")
        parts.append("Audio: quiet ambience, no music.")
        lines = [{"who": spk, "text": shot["text"], "how": shot["how"]}]
    else:
        act = tr.get(shot["text"]) or shot["text"]
        if shot.get("opening") and place:
            parts.append(f"Camera: wide establishing shot, {OPENING_MOVES[shot['i'] % len(OPENING_MOVES)]} revealing the place, "
                         f"then settling on the action. {ALIVE_ACTION}")
        else:
            parts.append(f"Camera: {ACTION_MOVES[shot['i'] % len(ACTION_MOVES)]}. {ALIVE_ACTION}")
        if shot["faces"]:
            n = len(shot["faces"])
            folk = all(person(cast, i) for i in shot["faces"])
            one, many = ("one person", "people") if folk else ("one character", "characters")
            parts.append(f"Exactly {one if n == 1 else f'{n} {many}'} in the shot: "
                         f"{', '.join(_who(cast, i) for i in shot['faces'])}, nobody else.")
        elif shot.get("vehicle"):
            parts.append(CARS_ONLY)
        if shot.get("vehicle"):
            folk = [i for i in shot["faces"] if person(cast, i)]
            who = " and ".join(_who(cast, i) for i in folk)
            if shot.get("in_car") and folk:
                parts.append(IN_CAR_ACTION.format(who=who))
                if len(folk) == 1:
                    parts.append(SOLO_SEAT.format(who=who))
            elif folk and len(folk) == len(shot["faces"]):   # a robot here: the car is the robot, nothing parked
                one = len(folk) == 1
                parts.append(BY_CAR.format(who=who, s="s" if one else "", es="es" if one else "",
                                           them={"male": "him", "female": "her"}.get(cast[folk[0]].get("gender"), "them") if one else "them"))
                if any(x in " ".join(_words(shot["text"])) for x in _EXIT):
                    act = by_car_text(act)
            parts.append(CAR_PHYSICS)
        parts.append(f"Timeline:\n[0s-{shot['seconds']}s] {prompts._sentence(act)}")
        parts.append("Audio: quiet ambience, no music. Nobody speaks.")
    if not shot["faces"]:
        parts.append(prompts.TAIL_PLAIN)
    else:
        g = cast[shot["faces"][0]].get("gender") if len(shot["faces"]) == 1 else ""
        parts.append(prompts.TAIL_PEOPLE.format(who={"male": "his", "female": "her"}.get(g, "their")))
    return "\n\n".join(p for p in parts if p), lines


def unstyle(text: str, look_id: str) -> str:
    """The heroes' looks in a drawn or animated look: the photographic words (grain, pores) out, as the storyboard does."""
    return looks.unphoto(text, True) if looks.drawn_of(look_id) else text


# ---------- subtitles ----------
def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(shot_list: list[dict], names: bool = False) -> str:
    """Subtitles of the lines, timed by the shots in order: a line shows from LEAD seconds into its shot to the shot's
    end (the montage plays the shots one after another)."""
    out, t, n = [], 0.0, 0
    for s in shot_list:
        if s["kind"] == "line":
            n += 1
            a, b = t + min(LEAD, s["seconds"] - 1), t + s["seconds"]
            text = (f"{s['who']}: " if names and s.get("who") else "") + s["text"]
            out.append(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n")
        t += s["seconds"]
    return "\n".join(out)


# ---------- writing a screenplay out (the LLM's JSON -> the text) ----------
def line_name(name: str, k: int, english: bool = False) -> str:
    """A hero's name as a speaker's cue that LINE_RE reads back: no colon, brackets or dashes, a letter first, at most 39
    characters; otherwise «Герой k» / «Hero k» (parse maps that back to the k-th hero)."""
    n = re.sub(r"\s+", " ", re.sub(r"[:()—–]", " ", name or "")).strip()
    if not n or len(n) > 39 or not re.match(r"[^\W\d_]", n):
        return f"{'Hero' if english else 'Герой'} {k}"
    return n


def render(data: dict, names: list[str]) -> tuple[str, dict]:
    """The writer's JSON {scenes: [{place, place_en, items: [{who, text, how, en}]}]} -> (the screenplay's text, the
    translation table {Russian place / action: English}). `who`: 0 an action, k the k-th hero of `names`."""
    rows, tr, n = [], {}, 0
    english = i18n.text() == "en"
    word = "SCENE" if english else "СЦЕНА"
    for sc in data.get("scenes") or []:
        n += 1
        place = str(sc.get("place") or "").strip().rstrip(".")
        rows.append(f"{word} {n}. {place}.")
        if place and (en := str(sc.get("place_en") or "").strip()):
            tr[place] = en
        for it in sc.get("items") or []:
            text = str(it.get("text") or "").strip().strip(QUOTES).strip()
            if not text:
                continue
            who = int(it.get("who") or 0)
            if who and who <= len(names):
                how = it.get("how") if it.get("how") in prompts.HOW else ""
                remark = remark_ru(how, english=english)
                rows.append(f"{line_name(names[who - 1], who, english).upper()}{f' ({remark})' if remark else ''}: {text}")
            else:
                rows.append(f"— {text}")
                if en := str(it.get("en") or "").strip():
                    tr[text] = en
        rows.append("")
    return "\n".join(rows).strip(), tr
