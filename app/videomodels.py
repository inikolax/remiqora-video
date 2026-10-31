"""Phase 10: the video models a project shoots with - H3 and, on the same worker, WAN 2.2 5B, LTX 2.5 and LTX 2.3.

A card says what a model can do (its own sound, Russian spoken lines, faces from photos, a picture made to a given
track), its frame grid and longest scene, its sizes, how long a scene takes until this machine has measured it, its
license, and which config keys name its weights («Модели и настройки» shows them). The project chooses the model
(settings.video_model; none = H3, as every project before phase 10); everything that was H3's own - the size, the
frame count, the cache key, the graph, the prompt - asks the card.

The prompt: a storyboard composes it for H3 (prompts.compose: «Continue seamlessly from <Picture 1>.», a timeline in
[0s-2s] steps, «says, in Russian: "..."»). Another model gets it rewritten at shooting time (adapt): no picture tags,
the timeline as plain sentences in order; WAN, which makes no sound, without the spoken lines and the audio line.
The storyboard keeps its H3 prompt, so changing the model back finds the H3 shots in the cache.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Optional

from . import config, i18n

FPS = 24


@dataclass(frozen=True)
class Card:
    id: str
    name: str
    short: str                     # in a line or on a card
    text: str                      # what it is for, one sentence
    sound: bool                    # makes the scene's sound itself
    voice: bool                    # says the scene's spoken lines (Russian)
    refs: bool                     # holds faces from photos (Ref2VA)
    track: bool                    # can make the picture to a given track (music videos, singing)
    max_seconds: float             # the longest scene it makes well
    grid: tuple[int, int]          # frames n with n % grid[0] == grid[1]
    step: int                      # width and height in multiples of this
    mp: dict = field(default_factory=dict)      # quality -> megapixels (of 1024 * 1024)
    base: dict = field(default_factory=dict)    # quality -> seconds per 5 s scene, warm, until measured here
    steps: int = 8
    keys: tuple[str, ...] = ()     # config keys of its weights
    license: str = ""
    recipe: str = ""               # what changes its shots besides the prompt and the size (part of the cache key)
    shoots_as: str = ""            # an imported model: its shots come ready; a scene shot again is shot by this one
    color: str = ""                # on the page: the shelf's model ribbon and filter dots, the disk bar of the models
    ends: bool = False             # ends a scene on a given picture (flf2v, «прийти к кадру»)
    grid_seconds: float = 5        # a storyboard's scenes are this long (planner/grid.py): 10 s where it shoots that well


CARDS: dict[str, Card] = {
    "h3": Card("h3", "MiniMax H3", "H3", "Картинка и звук вместе, реплики на языке ролика, лица по фото (Ref2VA).",
               sound=True, voice=True, refs=True, track=False, max_seconds=15, grid=(17, 5), step=32,
               mp={"draft": 0.5, "final": 0.98}, base={"draft": 95.0, "final": 271.0}, steps=8,
               keys=("H3_UNET", "H3_CLIP", "H3_VAE", "H3_AUDIO_VAE"), license="MiniMax H3: своя лицензия, проверьте условия для коммерции", color="#7F77DD"),
    "ltx25": Card("ltx25", "LTX 2.5", "LTX 2.5", "Быстрая: картинка и свой звук, две стадии с апскейлом латента.",
                  sound=True, voice=True, refs=False, track=False, max_seconds=10, grid=(8, 1), step=64,
                  mp={"draft": 0.5625, "final": 0.86}, base={"draft": 30.0, "final": 70.0}, steps=11,
                  keys=("LTX25_UNET", "LTX25_CLIP", "LTX25_VAE", "LTX25_AUDIO_VAE", "LTX25_UPSCALER"),
                  license="LTX-2 Community License: бесплатно до $10 млн выручки в год", recipe="ltx25-2stage-8+3", color="#D85A30",
                  ends=True, grid_seconds=10),
    "ltx23": Card("ltx23", "LTX 2.3", "LTX 2.3", "Картинка и звук; умеет снимать под ваш трек — клипы, герои поют песню.",
                  sound=True, voice=True, refs=False, track=True, max_seconds=10, grid=(8, 1), step=64,
                  mp={"draft": 0.5625, "final": 0.86}, base={"draft": 35.0, "final": 80.0}, steps=11,
                  keys=("LTX23_CKPT", "LTX23_CLIP", "LTX23_LORA", "LTX23_UPSCALER"),
                  license="LTX-2 Community License: бесплатно до $10 млн выручки в год", recipe="ltx23-dev+distilled0.5-2stage-8+3", color="#BA7517",
                  ends=True, grid_seconds=10),
    "wan5b": Card("wan5b", "WAN 2.2 5B", "WAN 5B", "Только картинка, без звука: звук ролика — ваш трек.",
                  sound=False, voice=False, refs=False, track=False, max_seconds=5, grid=(4, 1), step=32,
                  mp={"draft": 0.5, "final": 0.86}, base={"draft": 120.0, "final": 300.0}, steps=20,
                  keys=("WAN_UNET", "WAN_CLIP", "WAN_VAE"), license="Apache-2.0: можно и для коммерции", recipe="wan5b-20-cfg5-shift8", color="#639922"),
}
# Shots imported from remiqora-video (tools/import_remiqora.py): LTX made there by its own engine - the official Lightricks
# pipelines on other weights (2.3: the full distilled-1.1 checkpoint, the track driving it; 2.5: the bf16 transformer
# rebuilt from the int8 files). Their keys name that recipe, so they never pass for a shot of ours; a scene changed
# after the import (its prompt, seed, start frame) is shot by our LTX of the same version.
for _id, _rq in (("ltx23", "remiqora-ltx23-distilled1.1-a2vid"), ("ltx25", "remiqora-ltx25-distilled-bf16")):
    CARDS[f"rq_{_id}"] = replace(CARDS[_id], id=f"rq_{_id}", name=f"{CARDS[_id].name} · Remiqora", short=f"{CARDS[_id].short} · R",
                                 text="Сцены, снятые в Remiqora и перенесённые как есть; изменённую сцену снимет наша "
                                      f"{CARDS[_id].name}.", keys=(), recipe=_rq, shoots_as=_id)
# FastWan: WAN 2.2 5B with its distillation LoRA - 8 steps, CFG 1, shift 5 (remiqora-video's recipe: «FastWan до 10
# шагов»). A model of its own, so the WAN scenes shot before keep their keys; `family` - the graph and the prompt are WAN's.
CARDS["wan5b_fast"] = replace(CARDS["wan5b"], id="wan5b_fast", name="WAN 2.2 5B · FastWan", short="WAN Fast",
                              text="WAN 2.2 5B с LoRA FastWan: 8 шагов вместо 20, в разы быстрее; без звука.",
                              base={"draft": 30.0, "final": 75.0}, steps=8, keys=CARDS["wan5b"].keys + ("WAN_FAST_LORA",),
                              recipe="wan5b-fastwan-r128-8-cfg1-shift5", color="#8DB04A")
DEFAULT = "h3"


# the cards' texts and licenses in English (the Russian ones are the keys): text_of / license_of pick by the interface
_EN = {
    "Картинка и звук вместе, реплики на языке ролика, лица по фото (Ref2VA).":
        "Picture and sound together, spoken lines in the video's language, faces from photos (Ref2VA).",
    "MiniMax H3: своя лицензия, проверьте условия для коммерции": "MiniMax H3: its own license, check the terms for commercial use",
    "Быстрая: картинка и свой звук, две стадии с апскейлом латента.": "Fast: picture and its own sound, two stages with a latent upscale.",
    "LTX-2 Community License: бесплатно до $10 млн выручки в год": "LTX-2 Community License: free up to $10M revenue a year",
    "Картинка и звук; умеет снимать под ваш трек — клипы, герои поют песню.":
        "Picture and sound; can shoot to your track: clips, heroes singing the song.",
    "Только картинка, без звука: звук ролика — ваш трек.": "Picture only, no sound: the video's sound is your track.",
    "Apache-2.0: можно и для коммерции": "Apache-2.0: commercial use too",
    "WAN 2.2 5B с LoRA FastWan: 8 шагов вместо 20, в разы быстрее; без звука.":
        "WAN 2.2 5B with the FastWan LoRA: 8 steps instead of 20, several times faster; no sound.",
}
for _id in ("ltx23", "ltx25"):
    _EN[CARDS[f"rq_{_id}"].text] = (f"Scenes shot in Remiqora and brought over as they are; a changed scene is shot by our "
                                    f"{CARDS[_id].name}.")


def text_of(c: Card) -> str:
    """The card's text in the interface's language."""
    return i18n.L(c.text, _EN.get(c.text, c.text))


def license_of(c: Card) -> str:
    return i18n.L(c.license, _EN.get(c.license, c.license))


def family(c: Card) -> str:
    """Whose graph and prompt a model's are: FastWan's are WAN's."""
    return "wan5b" if c.id.startswith("wan5b") else c.id


def card(model_id: str | None) -> Card:
    return CARDS.get(model_id or DEFAULT, CARDS[DEFAULT])


def offered(model_id: str | None) -> bool:
    """A model a project, a clip, a graph or the lab may choose: a known one that shoots itself (not an imported one)."""
    return model_id in CARDS and not CARDS[model_id].shoots_as


def shooter(c: Card) -> Card:
    """The model that really shoots a scene of `c`: an imported model's own one, else `c` itself."""
    return CARDS[c.shoots_as] if c.shoots_as else c


def of(settings: dict) -> Card:
    """The project's model (settings.video_model; a project from before phase 10 shoots with H3)."""
    return card(settings.get("video_model"))


def frames(c: Card, seconds: float) -> int:
    """Frames at 24 fps on the model's grid, never shorter than asked (H3: 5 s -> 124; LTX, WAN: 5 s -> 121)."""
    n = max(c.grid[0] + c.grid[1], round(min(seconds, c.max_seconds) * FPS))
    while n % c.grid[0] != c.grid[1]:
        n += 1
    return n


def canvas(aspect: float, megapixels: float, step: int = 32) -> tuple[int, int]:
    area = megapixels * 1024 * 1024
    w = math.sqrt(area * aspect)
    h = w / aspect
    return max(step, round(w / step) * step), max(step, round(h / step) * step)


def size(c: Card, aspect: float, quality: str) -> tuple[int, int]:
    return canvas(aspect, c.mp.get(quality, c.mp["draft"]), c.step)


SIZE_MIN, SIZE_MAX = 256, 2048   # an own frame (settings.size) stays within this, in the card's steps


def own_size(settings: dict, c: Card) -> Optional[tuple[int, int]]:
    """The frame the user set by hand (settings.size = {w, h}), snapped to the card's step; None - the size follows
    the format and the quality."""
    s = settings.get("size")
    if not isinstance(s, dict):
        return None
    try:
        w, h = int(s.get("w") or 0), int(s.get("h") or 0)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    snap = lambda v: max(c.step, round(min(max(v, SIZE_MIN), SIZE_MAX) / c.step) * c.step)
    return snap(w), snap(h)


def timing_key(c: Card, quality: str, ref: bool = False) -> str:
    """timings.py keeps each model's shots apart; H3's keys stay as they were (draft, final, draft_ref...)."""
    c = shooter(c)
    return quality + ("_ref" if ref else "") if c.id == "h3" else f"{c.id}:{quality}"


def weights_missing(c: Card) -> list[str]:
    """The card's weight files the worker would not find. H3's turbo LoRA only for a model without the speed-up inside
    (TURBO in its name, the Models page says the same)."""
    c = shooter(c)
    from .models_page import find_file
    keys = list(c.keys) + (["H3_TURBO_LORA"] if c.id == "h3" and "turbo" not in config.H3_UNET.lower() else [])
    return [getattr(config, k) for k in keys if not find_file(k)]


# ---------- the prompt for another model ----------
_PICTURE_LINE = re.compile(r"^\s*Continue seamlessly from <Picture \d+>\.\s*$", re.M)
_PICTURE = re.compile(r"\s*(?:from|in|as in)?\s*<Picture \d+>", re.I)
_TIME = re.compile(r"^\s*\[\s*\d+(?:[.,]\d+)?\s*s?\s*[-–]\s*\d+(?:[.,]\d+)?\s*s?\s*\]\s*")
# H3's tail «No text, subtitles, logos or watermarks.»: at CFG 1 a model has no negative prompt, and the words draw
# what they forbid - LTX put gibberish subtitles under every spoken line (tried 2026-10-23, same seed with and without)
_NO_TEXT = re.compile(r"\s*No text, subtitles, logos,? (?:or )?watermarks( or people)?\.")
_ANAMORPHIC = re.compile(r"\banamorphic(\s+lens(es)?)?", re.I)   # LTX letterboxes the picture for it
_SAYS = re.compile(r"\b(says|whispers|shouts|sings)\b[^:]*,\s*in [A-Z][a-z]+:\s*\"", re.I)   # a spoken line, in the video's language


def adapt(c: Card, prompt: str, legacy: bool = False) -> str:
    """H3's prompt -> this model's: the same words without H3's picture tags; the timeline's steps as one paragraph of
    sentences in their order (LTX and WAN read a flowing description best); WAN without spoken lines and the audio line."""
    if c.id == "h3" or not prompt:
        return prompt
    text = _PICTURE_LINE.sub("", prompt)
    out, beats = [], None
    for row in text.split("\n"):
        r = row.strip()
        if r.lower().startswith("timeline:"):
            beats = []
            continue
        if beats is not None and _TIME.match(r):
            beats.append(_TIME.sub("", r))
            continue
        if beats is not None:
            out.append(_beats(c, beats))
            beats = None
        if not c.sound and r.lower().startswith("audio:"):
            continue
        out.append(row)
    if beats is not None:
        out.append(_beats(c, beats))
    text = _ANAMORPHIC.sub("widescreen lens, the picture filling the whole frame", _PICTURE.sub("", "\n".join(out)))
    if not legacy:   # the shots of the night of 2026-10-23 before 03:00 (363212f) kept H3's tail: render's legacy key
        text = _NO_TEXT.sub(lambda m: " No people." if m.group(1) else "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def timeline_sentences(c: Card, timeline: str) -> str:
    """A timeline's steps ([0s-2s] ...) as sentences in their order; a model without a voice gets no spoken lines."""
    return _beats(c, [_TIME.sub("", r.strip()) for r in timeline.splitlines() if r.strip()])


def _beats(c: Card, beats: list[str]) -> str:
    keep = [b if b[-1:] in ".!?\"”" else b + "." for b in beats if b and (c.voice or not _SAYS.search(b))]
    return " ".join(keep)


def public() -> list[dict]:
    """The cards for the page (the model picker, «Модели и настройки»)."""
    return [{"id": c.id, "name": c.name, "short": c.short, "text": text_of(c), "sound": c.sound, "voice": c.voice, "refs": c.refs,
             "track": c.track, "ends": c.ends, "max_seconds": c.max_seconds, "grid_seconds": c.grid_seconds, "license": license_of(c), "steps": c.steps,
             "sizes": {q: dict(zip(("w", "h"), canvas(16 / 9, mp, c.step))) for q, mp in c.mp.items()}, "mp": c.mp, "step": c.step,
             "per_scene": c.base, "imported": bool(c.shoots_as), "color": c.color,   # an imported model is never offered, only named
             "missing": weights_missing(c)} for c in CARDS.values()]
