"""The video models a beat clip's scenes can be shot with, and what differs between them in one place:
the scene's length, the pre-roll (the first frames of an i2v scene stand still: the montage skips them, the checks do not
measure them) and the model's prompt hold. The still lines per model are checks.BEAT_STILL_BY_MODEL.

H3's values are measured (clips 54-56 of 2026-11-06). LTX 2.5's are GUESSES copied from H3 until the live test of the beat clip on
LTX 2.5 values were measured on the live test of 2026-11-07."""
from __future__ import annotations

from . import i18n, videomodels

MODELS = ("h3", "ltx25")
DEFAULT = "h3"
SCENE_S = 3                 # a scene's seconds on the node; the model's frame grid decides the frames (frames())
PREROLL_S = {"h3": 0.35,    # measured: H3's scene stands still for its first ~0.3 s
             "ltx25": 0.1}   # measured 2026-11-07 (16 LTX 2.5 scenes of «Neon Samurai», final): moving from frame 0 (median 0 frames, at most 4 = 0.17 s)
# What an LTX scene from a picture is told first (translate.LTX_FRAME_RULE): the picture holds the place, the people, the light
LTX_HOLD = "Everything stays as in the picture: the same people, place, light and colours."


def known(model: str | None) -> str:
    """A model a beat clip knows; anything else is H3's (an old project has none)."""
    return model if model in MODELS else DEFAULT


def preroll(model: str | None) -> float:
    """Seconds at the start of a scene from a picture that stand still (the montage plays from there, the checks look after it)."""
    return PREROLL_S[known(model)]


def frames(model: str | None) -> int:
    """The frames a beat scene is shot with: the model's grid frame count closest to SCENE_S seconds (H3 and LTX 2.5: 73)."""
    return videomodels.frames(videomodels.card(known(model)), SCENE_S)


def refusal(model: str | None) -> str:
    return i18n.L(f"Бит-клип снимают H3 и LTX 2.5: сцены по 3 с с картинки (модель «{model}» не подходит)",
                  f"A beat clip is shot by H3 or LTX 2.5: 3 s scenes from a picture (the model «{model}» does not fit)")
