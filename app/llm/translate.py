"""The lab's Russian prompt -> an English prompt for the lab's model: for H3 in the lab's format (style, Scene:,
Camera:, Timeline:, Audio:, the tail), for LTX and WAN in their makers' form (planner/model_prompts.py: one flowing
paragraph; WAN silent). Spoken lines in quotes stay Russian, word for word: H3 and LTX say them in Russian. Only by
the lab's button.
And the other way, for reading: a storyboard's English scenes (clips brought from Remiqora) in Russian - «Перевести
на русский» on the board."""
from __future__ import annotations

import json
import re
from typing import Optional

from .. import i18n, videomodels
from . import client

SYSTEM = """You turn a scene written in Russian into an English prompt for the MiniMax H3 video model, which makes one shot of {seconds} seconds with its sound.

The prompt is paragraphs separated by one blank line, in this order (skip a part the source does not have, except Timeline):
1. "Continue seamlessly from <Picture 1>." - only if the source has this line or says the scene starts from a picture or frame.
2. The style: one sentence on the look, light and film (no label).
3. "Scene: " where and when, who is there and how they look.
4. "Camera: " the shot size and the camera movement.
5. "Timeline:" then one line per action: "[0s-2s] ...", "[2s-5s] ...", consecutive, from 0s to {seconds}s, one action per line.
6. "Audio: " the sounds of the place and actions, and the music (instruments and tempo).
7. The tail, e.g. "No text, subtitles, logos or watermarks."

Labels map to these parts: Стиль -> the style, Место or Сцена -> Scene:, Камера -> Camera:, Таймлайн or Действия -> Timeline:, Звук or Музыка -> Audio:, Хвост -> the tail; English labels (Scene:, Camera:, Timeline:, Audio:, Continue seamlessly from <Picture 1>.) with the text after them in the user's language are the same parts. Free text without labels: sort it into the parts.

Rules:
- Translate into plain, concrete English: what is seen and heard. Keep every detail of the source; do not add people, events or story it does not have.
- Words in quotes ("...", «...», “...”) are lines a character says aloud. Keep them exactly as written, in Russian, inside straight double quotes, and say who speaks, how, and the language: He says in a low voice, in Russian: "Садись."
- Keep unchanged: timestamps like [0s-2s], <Picture N>, numbers, "...", and any part already written in English.
- People are adults: keep a given age; never make anyone a child.
- Outside the quotes the prompt has no Russian letters at all."""

SCHEMA = {"type": "object", "properties": {"prompt_en": {"type": "string"}}, "required": ["prompt_en"], "additionalProperties": False}

# The source's parts, the same for every model: the Russian sheet keeps the lab's labels whatever shoots
_SOURCE = """The source may have labelled parts: Стиль (the look), Место or Сцена (where, who), Камера (the camera), Таймлайн or Действия (the actions, maybe with timestamps like [0s-2s]), Звук or Музыка (the sound), and a tail (no text, the same faces); English labels (Scene:, Camera:, Timeline:, Audio:) with the text after them in the user's language are the same parts. Free text without labels: take what each sentence says."""

LTX_SYSTEM = """You turn a scene written in Russian into an English prompt for the LTX-2 video model (Lightricks), which makes one shot of {seconds} seconds with its sound.

The prompt is ONE flowing paragraph in the present tense, 4-8 sentences, in this order:
1. The look and genre: style, light, film.
2. The place and time.
3. Who is there and how they look: few, strong visual traits.
4. The action from beginning to end, in the order it happens, one clear action per sentence.
5. The camera: the shot size and how it moves.
6. The sound: the sounds of the place and the actions, the music, and the spoken lines.

""" + _SOURCE + """

Rules:
- One paragraph: no labels, no timestamps, no line breaks, no "<Picture N>", no "no text / watermarks" tail.
- Translate into plain, concrete English: what is seen and heard. Keep every detail of the source; do not add people, events or story it does not have.
- Words in quotes ("...", «...», “...”) are lines a character says aloud. Keep them exactly as written, in Russian, inside straight double quotes, and say who speaks, how, and the language: He says in a low voice, in Russian: "Садись."
- Keep unchanged: numbers, "...", and any words already written in English.
- People are adults: keep a given age; never make anyone a child.
- Outside the quotes the prompt has no Russian letters at all."""

WAN_SYSTEM = """You turn a scene written in Russian into an English prompt for the WAN 2.2 video model, which makes one SILENT shot of {seconds} seconds.

{order}

""" + _SOURCE + """

Rules:{frame}
- One paragraph: no labels, no timestamps, no line breaks, no "<Picture N>", no "no text / watermarks" tail.
- WAN makes no sound: leave out the sounds, the music and the spoken lines; someone who speaks in the source is only seen talking, without the words.
- Translate into plain, concrete English: what is seen. Keep every visible detail of the source; do not add people, events or story it does not have.
- Keep unchanged: numbers, "...", and any words already written in English.
- People are adults: keep a given age; never make anyone a child.
- The prompt has no Russian letters at all."""

WAN_ORDER = """The prompt is ONE paragraph, 60-200 words, in this order:
1. Who is there and how they look.
2. Where and when.
3. The motion, in the order it happens: simple, slow, continuous movement of one subject.
4. The camera: the shot size and the movement (static or slow).
5. The look: light, colour, lens, style."""

# the shot starts from a picture: the frame already shows who, where and the look (WAN's guide). A note after the
# order was not enough (a 24B writer described the woman, the kitchen and the light anyway): the order
# itself is the two parts, and the first rule says so
WAN_FRAME_ORDER = """The shot starts from a given picture that already shows who is there, the place, the clothes, the light and the style. The prompt is ONE short paragraph, 20-80 words, of only two things, in this order:
1. The motion, in the order it happens: simple, slow, continuous movement; name the people only as "the woman", "the man", "the dog".
2. The camera: the shot size and the movement (static or slow)."""
WAN_FRAME_RULE = """
- Do NOT describe how anyone looks, their age or clothes, the place, the time, the light, the colours or the style: the picture shows them; drop those parts of the source (this rule comes before keeping every detail)."""


# A shot that starts from a picture (a photo, a «Картинка», the last frame of a scene) on H3 or LTX: the picture already
# shows the place, the people, their clothes, the light and the style; a prompt that describes them again - in other
# words, or a place of its own - makes the model leave the picture for that (H3 cut to a café within a second,
# 2026-10-28). So the prompt holds the picture and says only what happens.
H3_FRAME_RULE = """

The shot starts from a given picture that already shows who is there, the place, the clothes, the light and the style. This comes before keeping every detail of the source:
- Part 1 is always there: "Continue seamlessly from <Picture 1>."
- Instead of parts 2 and 3 write one line: "Everything stays as in the picture: the same people, place, light, colours and framing." Do NOT describe how anyone looks, their age or clothes, the place, the time, the light, the colours or the style - unless the source asks to change one of them; then say only that change.
- Camera: the shot size and framing of the picture ("static camera, the framing of the picture"), unless the source asks for a movement.
- Timeline: only what happens, from the picture on.
- The tail: "Keep the faces, hair and clothes exactly as in the picture. No new people. No text, subtitles, logos or watermarks." (without "No new people" when the source brings someone in)."""

LTX_FRAME_RULE = """

The shot starts from a given picture that already shows who is there, the place, the clothes, the light and the style. This comes before keeping every detail of the source:
- Begin with: "Everything stays as in the picture: the same people, place, light and colours."
- Then only the action from the picture on, the camera and the sound. Do NOT describe how anyone looks, their age or clothes, the place, the time, the light, the colours or the style - unless the source asks to change one of them; then say only that change."""


# A graph's «Картинка» node (Krea 2, a Qwen-Image text encoder): a still, so no time, motion, camera moves or sound
KREA_SYSTEM = """You turn a description of a picture written in Russian into an English prompt for the Krea 2 image model, which makes ONE still picture (no video, no sound).

The prompt is ONE flowing paragraph of 40-120 words, in this order:
1. The subject: who or what, how they look (few, strong visual traits), their pose and expression - frozen in one moment.
2. The place and time of day.
3. The composition: the shot size, the angle, the framing.
4. The light, colours and mood.
5. The style and the lens: photo, film, painting; focal length, depth of field.

""" + _SOURCE + """

Rules:
- It is a still: leave out time, timestamps, actions in sequence, camera movement, sounds, music and "Continue seamlessly" lines; turn a movement of the source into the one moment of it that is seen.
- Spoken lines are not heard in a picture: leave out words in quotes (unless they are text written on a sign or a screen: then keep it in quotes, as written).
- One paragraph: no labels, no timestamps, no line breaks, no "<Picture N>".
- Translate into plain, concrete English: what is seen. Keep every visible detail of the source; do not add people, objects or story it does not have.
- Keep unchanged: numbers, "...", and any words already written in English.
- People are adults: keep a given age; never make anyone a child.
- The prompt has no Russian letters at all."""


# A «Картинка» node drawn by FLUX.2 Klein from reference pictures (picture.edit): the prompt tells what to take from
# the first, second, third image and what the new still shows; the same still rules as Krea's
FLUX_SYSTEM = """You turn a description of a picture written in Russian into an English prompt for the FLUX.2 Klein image model, which makes ONE new still picture from one to three reference images given with it (no video, no sound).

The prompt is ONE flowing paragraph of 40-120 words, in this order:
1. What is taken from the references: "The woman in the first image: exactly the same face, hair and clothes" (the second, the third image likewise - a person, a place or an object the source names). When the source does not say who is in the references, the first image is the main person.
2. "A new photograph of her/him/them, a different camera position and framing than the reference images; do not copy their backgrounds."
3. The subject's pose, expression and action - frozen in one moment; the place and time of day.
4. The composition: the shot size, the angle, the framing.
5. The light, colours, mood, style and lens.

An edit is different: when the source asks to change something in a reference picture and keep the rest (another background, remove or add an object, other clothes, another colour, "the same picture but..."), the prompt is "The first image, with <the change, said concretely>; everything else exactly as in the first image: the same people, pose, place, framing and light." - and nothing from points 1-5 that the source does not ask to change.

""" + _SOURCE + """

Rules:
- It is a still: leave out time, timestamps, actions in sequence, camera movement, sounds, music and "Continue seamlessly" lines; turn a movement of the source into the one moment of it that is seen.
- Spoken lines are not heard in a picture: leave out words in quotes (unless they are text written on a sign or a screen: then keep it in quotes, as written).
- One paragraph: no labels, no timestamps, no line breaks, no "<Picture N>" - the references are "the first image", "the second image".
- Translate into plain, concrete English: what is seen. Keep every visible detail of the source; do not add people, objects or story it does not have.
- Keep unchanged: numbers, "...", and any words already written in English.
- People are adults: keep a given age; never make anyone a child.
- The prompt has no Russian letters at all."""


def form(video: Optional[str], target: str = "video") -> str:
    """The prompt form of the target: 'krea' for a picture node, 'flux2' for one drawn by reference, else the lab's
    model (a card id): 'h3', 'ltx' or 'wan'."""
    if target == "picture":
        return "krea"
    if target == "frame":
        return "flux2"
    c = videomodels.shooter(videomodels.card(video or "h3"))
    return "h3" if c.id == "h3" else "wan" if videomodels.family(c) == "wan5b" else "ltx"


def _system(video: Optional[str], seconds: str, frame: bool, target: str = "video") -> str:
    f = form(video, target)
    if f == "krea":
        return KREA_SYSTEM
    if f == "flux2":
        return FLUX_SYSTEM
    s = SYSTEM if f == "h3" else LTX_SYSTEM if f == "ltx" else (
        WAN_SYSTEM.replace("{order}", WAN_FRAME_ORDER if frame else WAN_ORDER).replace("{frame}", WAN_FRAME_RULE if frame else ""))
    if frame and f in ("h3", "ltx"):
        s += H3_FRAME_RULE if f == "h3" else LTX_FRAME_RULE
    return s.replace("{seconds}", seconds)


FIELDS_SYSTEM = """You translate the fields of one scene for the MiniMax H3 video model from Russian into plain, concrete English: what is seen and heard. The scene is {seconds} seconds long. The input is JSON with the fields; answer with the same fields in English.

- style: one sentence on the look, light and film.
- place: where and when, who is there and how they look (adults; keep a given age, never make anyone a child).
- camera: an addition to the camera line (may be empty).
- beats: the actions in order, one per entry; keep their number and their order exactly, do not merge or split them.
- audio: the sounds of the place and the actions, the music as instruments and tempo.

Keep every detail of the source; add no people, events or story. Words in quotes ("...", «...», “...”) are lines a character says aloud: keep them exactly as written, in Russian, inside straight double quotes, and say who speaks, how, and the language, e.g. He says in a low voice, in Russian: "Садись." Keep unchanged: <Picture N>, numbers, "...", and anything already in English. An empty field stays an empty string. Outside the quotes there are no Russian letters at all."""

# LTX and WAN get the fields as one paragraph (the lab's sceneForm.composeFor): the beats become its sentences
FIELDS_NOTE = {
    "ltx": "\n\nThe fields go to the LTX-2 video model (Lightricks) instead, joined into one flowing paragraph: write every beat as a full sentence in the present tense, one clear action each; give the people few, strong visual traits.",
    "wan": "\n\nThe fields go to the WAN 2.2 video model instead, joined into one paragraph. WAN makes no sound: audio is an empty string, and someone who speaks is only seen talking, without the words (no quotes). Every beat is a full sentence in the present tense: simple, slow, continuous motion.",
}

FIELDS_SCHEMA = {"type": "object", "properties": {"style": {"type": "string"}, "place": {"type": "string"}, "camera": {"type": "string"},
                                                   "beats": {"type": "array", "items": {"type": "string"}}, "audio": {"type": "string"}},
                 "required": ["style", "place", "camera", "beats", "audio"], "additionalProperties": False}


async def translate_fields(fields: dict, seconds: float = 5, model_id: Optional[str] = None, seed: int = 1,
                           video: Optional[str] = None) -> dict:
    """The lab's scene form, Russian -> English, field by field; the beats come back as many as they went. `video`:
    the lab's model (H3 - the prompt as it always was, so its answers stay in the LLM cache)."""
    client.use_lang(i18n.text_name())   # the texts' language (i18n)
    want = [str(b) for b in fields.get("beats") or []]
    src = {"style": str(fields.get("style") or ""), "place": str(fields.get("place") or ""), "camera": str(fields.get("camera") or ""),
           "beats": want, "audio": str(fields.get("audio") or "")}
    async with client.session(model_id) as llm:
        system = FIELDS_SYSTEM.replace("{seconds}", f"{seconds:g}") + FIELDS_NOTE.get(form(video), "")
        d = await llm.chat_json(system, json.dumps(src, ensure_ascii=False, indent=1),
                                FIELDS_SCHEMA, temperature=0.2, seed=seed, max_tokens=2500)
        beats = [str(b).strip() for b in d.get("beats") or []]
        beats = (beats + [""] * len(want))[:len(want)]
        return {"style": str(d.get("style", "")).strip(), "place": str(d.get("place", "")).strip(), "camera": str(d.get("camera", "")).strip(),
                "beats": beats, "audio": str(d.get("audio", "")).strip(), "model": llm.model.name}


# The writer often puts the parts on single lines, without the blank line between them (most answers in the cache,
# 2026-10-22); the lab finds a part by its paragraph, so the style glued to the frame line or to the scene was lost.
_LABEL = re.compile(r"^(Continue seamlessly from|Scene( continues)?:|Camera:|Timeline:|Audio:)", re.IGNORECASE)
_FRAME = re.compile(r"^Continue seamlessly from", re.IGNORECASE)
_STAMP = re.compile(r"^\[\s*\d")
_TAIL = re.compile(r"^(No text|Keep every face)", re.IGNORECASE)


def layout(text: str) -> str:
    """The English prompt as the lab's paragraphs, a blank line between the parts: a new one at a label, after the frame
    line and at the tail; the timeline's lines stay together; the style loses a "Style:" label it should not have."""
    paras: list[list[str]] = []
    blank = False
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            blank = True
            continue
        head = paras[-1][0] if paras else ""
        if not paras:
            new = True
        elif _STAMP.match(line):   # a timeline line joins the timeline even across a blank line
            new = not (head.lower().startswith("timeline") or _STAMP.match(head))
        else:
            new = blank or bool(_LABEL.match(line) or _FRAME.match(head) or (_TAIL.match(line) and not _TAIL.match(head)))
        blank = False
        if not new:
            paras[-1].append(line)
            continue
        if not paras or (len(paras) == 1 and _FRAME.match(head)):   # the style's place: first, or right after the frame line
            line = re.sub(r"^Style:\s*", "", line, flags=re.IGNORECASE)
        paras.append([line])
    return "\n\n".join("\n".join(p) for p in paras)


async def translate(text: str, seconds: float = 5, model_id: Optional[str] = None, seed: int = 1,
                    video: Optional[str] = None, frame: bool = False, target: str = "video") -> dict:
    """`video`: the lab's model, whose form the prompt takes; `frame`: the shot starts from a picture (H3 and LTX hold
    it and get what happens, WAN only the motion and the camera); `target`: "picture" - the prompt goes to a «Картинка» node (Krea 2), a still."""
    client.use_lang(i18n.text_name())   # the texts' language (i18n)
    async with client.session(model_id) as llm:
        d = await llm.chat_json(_system(video, f"{seconds:g}", frame, target), text.strip(), SCHEMA, temperature=0.2, seed=seed, max_tokens=3000)
        en = str(d.get("prompt_en", ""))
        return {"en": layout(en) if form(video, target) == "h3" else re.sub(r"\s+", " ", en).strip(), "model": llm.model.name}


# ---------- a storyboard's scenes -> the texts' language, for the user to read («Перевести на …», only by the button) ----------
# Scenes come in another language than the user's: English from Remiqora's clips, Russian when the texts' language
# was changed after writing. "Russian" below is the target: client.LANG says the texts' language (i18n).
RU_SYSTEM = """You translate one scene of a short video into natural Russian, for the person who made the video to read. Answer with two fields:
- ru: what happens in the scene, one or two short sentences, from "action" (if it is empty, from the prompt).
- prompt_ru: the whole prompt in Russian, keeping its paragraphs and line breaks. The labels become the Russian words for "Scene:", "Camera:", "Timeline:", "Audio:"; timestamps like [0s-2s], <Picture N>, numbers and names stay as they are; words in quotes (spoken lines) stay word for word.
Translate faithfully: add nothing, leave nothing out, no comments."""

RU_SCHEMA = {"type": "object", "properties": {"ru": {"type": "string"}, "prompt_ru": {"type": "string"}},
             "required": ["ru", "prompt_ru"], "additionalProperties": False}
_CYR, _LAT = re.compile("[а-яёіїєґўқғүұһә]", re.I), re.compile("[a-zà-ÿąćęłńóśźżčďěňřšťůž]", re.I)
_CJK = re.compile("[぀-ヿ㐀-鿿가-힯]")
_EN_WORDS = re.compile(r"\b(the|and|of|is|are|with|her|his|she|he|in|on|a|to|at|from|into|their)\b", re.I)
CYRILLIC_LANGS = {"ru", "uk", "be", "kk"}


def english(text: str) -> bool:
    """More Latin letters than Cyrillic (a Russian line in quotes inside an English prompt does not make it Russian)."""
    return len(_LAT.findall(text or "")) > len(_CYR.findall(text or ""))


def in_lang(text: str, code: str) -> bool:
    """Whether a text is (most likely) in the language `code`: its alphabet, and for Latin ones English or not."""
    t = text or ""
    if not t.strip():
        return True
    cyr, lat, cjk = len(_CYR.findall(t)), len(_LAT.findall(t)), len(_CJK.findall(t))
    if code in CYRILLIC_LANGS:
        return cyr > lat
    if code in ("zh", "ja", "ko"):
        return cjk > lat
    if cyr > lat or cjk > lat:
        return False
    en = len(_EN_WORDS.findall(t)) >= max(1, len(t.split()) // 8)   # English: its little words, a few of every eight
    return en if code == "en" else not en


def _lang_of_text(scene: dict, key: str, code: str) -> bool:
    """The scene's text `key` is in `code`: as tagged when it was translated (ru_lang), else as it reads."""
    if scene.get("ru_lang"):
        return scene["ru_lang"] == code
    return in_lang(scene.get(key, ""), code)


def needs_translation(scene: dict, code: Optional[str] = None) -> bool:
    """Its «what happens» is in another language than the texts', or its own prompt is and has no copy in it yet
    (an own prompt in English needs none for an English reader)."""
    code = code or i18n.text()
    raw = scene.get("raw")
    own = isinstance(raw, str) and raw.strip() and code != "en" and not in_lang(raw, code) \
        and not (scene.get("raw_ru") and scene.get("ru_lang", "ru") == code)
    return not _lang_of_text(scene, "ru", code) or bool(own)


needs_russian = needs_translation   # the name main.py has known it by


async def to_local(plan: dict, indices: Optional[list[int]] = None, step=None) -> dict:
    """The scenes that need it (all of them when indices is None) in the texts' language: `ru` becomes that language
    (the old text stays in `ru_en`), an own prompt gets `raw_ru` beside it, both tagged `ru_lang`. The prompt that goes
    to the model does not change, so neither do the shots; a locked scene is translated too. step(done, total) after
    each scene."""
    code = i18n.text()
    client.use_lang(i18n.text_name(code))
    scenes = plan["scenes"]
    want = [i for i in (range(len(scenes)) if indices is None else indices) if 0 <= i < len(scenes) and needs_translation(scenes[i], code)]
    if not want:
        return plan
    async with client.session(plan.get("model")) as llm:
        for k, i in enumerate(want):
            s = scenes[i]
            raw = s.get("raw") if isinstance(s.get("raw"), str) else ""
            action = s.get("ru", "") if not _lang_of_text(s, "ru", code) else ""
            user = json.dumps({"action": action, "prompt": raw or s.get("prompt", "")}, ensure_ascii=False)
            d = await llm.chat_json(RU_SYSTEM, user, RU_SCHEMA, temperature=0.2, seed=1, max_tokens=3000)
            ru, prompt_ru = str(d.get("ru", "")).strip(), str(d.get("prompt_ru", "")).strip()
            if action and ru and in_lang(ru, code):
                s["ru_en"], s["ru"] = s.get("ru", ""), ru
            if raw and code != "en" and prompt_ru and in_lang(prompt_ru, code):
                s["raw_ru"] = prompt_ru
            s["ru_lang"] = code
            if step:
                step(k + 1, len(want))
    return plan


to_russian = to_local
