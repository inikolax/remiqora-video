"""A photo -> the hero's lock: how the person looks, in English for the prompt and in Russian for the card.
The age is always an explicit adult number (21 or older: a fixed part of the prompt formula, not a filter), and no
names of real people get into the text."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .. import i18n
from . import client

MIN_AGE = 21

SYSTEM = """You describe the main person in a photo for a video generation prompt. The description is pasted word for word into every scene, so it must fix the look: what stays the same from scene to scene.

Write:
- gender: female, male or other.
- age: the apparent age as one number; the person is an adult, never under 21.
- en: one English paragraph, 35-70 words, starting with "a <age>-year-old" and the gender: build, skin tone, face, eyes, hair (color, length, style), notable features (freckles, tattoos, glasses, makeup). Concrete visual words only, no feelings, no story, no camera or lighting. No clothing here: it goes to outfit_en.
- outfit_en: what the person wears, 10-30 words, colors and materials; "" if not visible.
- ru, outfit_ru: the same descriptions in natural Russian for the user, with every detail of en / outfit_en (ru is a full paragraph, not one word).
Never write a name, even if you recognize the person. Describe only what is visible."""

SCHEMA = {
    "type": "object",
    "properties": {
        "gender": {"type": "string", "enum": ["female", "male", "other"]},
        "age": {"type": "integer"},
        "en": {"type": "string"},
        "outfit_en": {"type": "string"},
        "ru": {"type": "string"},
        "outfit_ru": {"type": "string"},
    },
    "required": ["gender", "age", "en", "outfit_en", "ru", "outfit_ru"],
    "additionalProperties": False,
}


RU_SCHEMA = {"type": "object", "properties": {"ru": {"type": "string"}, "outfit_ru": {"type": "string"}},
             "required": ["ru", "outfit_ru"], "additionalProperties": False}


async def describe_with(llm: client.Client, image: Path, seed: int = 1) -> dict:
    """Inside an open session (the writer describes the photo and writes the storyboard in one model load)."""
    d = await llm.chat_json(SYSTEM, "Describe the main person in this photo.", SCHEMA, images=(image,),
                            temperature=0.3, seed=seed, max_tokens=1024)
    d["age"] = max(MIN_AGE, int(d.get("age") or MIN_AGE))
    if len(d.get("ru", "").split()) < 8:   # a small model sometimes answers ru with one word: translate en instead
        t = await llm.chat_json("You translate a description of a person from English into natural Russian, every detail kept.",
                                f"look: {d.get('en', '')}\noutfit: {d.get('outfit_en', '')}", RU_SCHEMA,
                                temperature=0.2, seed=seed, max_tokens=800)
        d.update(ru=t.get("ru") or d.get("ru", ""), outfit_ru=t.get("outfit_ru") or d.get("outfit_ru", ""))
    d["model"] = llm.model.name
    return d


FRAME_SYSTEM = """You describe a photo that becomes the very first frame of a video: the video model starts from exactly this picture and the scene grows out of it. The screenwriter reads your words to continue the moment, so say what is in the frame at second 0.

Write:
- en: 30-60 English words: who or what is in the frame and where in it, their pose and what they are doing, where they look, the framing (close-up, medium or wide), the light and time of day. Concrete visual words only, no story, no feelings, no names (even if you recognize someone).
- place_en: one English sentence, 8-25 words: the place, the light and the time of day, as a location for the scene."""

FRAME_SCHEMA = {"type": "object", "properties": {"en": {"type": "string"}, "place_en": {"type": "string"}},
                "required": ["en", "place_en"], "additionalProperties": False}


async def describe_frame_with(llm: client.Client, image: Path, seed: int = 1) -> dict:
    """A start photo -> {en: what the frame shows at second 0, place_en: where}, for the writer (inside a session)."""
    d = await llm.chat_json(FRAME_SYSTEM, "Describe this first frame.", FRAME_SCHEMA, images=(image,),
                            temperature=0.3, seed=seed, max_tokens=600)
    return {"en": str(d.get("en", "")).strip(), "place_en": str(d.get("place_en", "")).strip()}


async def describe(image: Path, model_id: Optional[str] = None, seed: int = 1) -> dict:
    client.use_lang(i18n.text_name())   # the texts' language (i18n)
    async with client.session(model_id) as llm:
        return await describe_with(llm, image, seed)
