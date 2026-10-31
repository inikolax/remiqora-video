"""The prompt LTX and WAN shoot a storyboard scene with, from the scene's fields, each by its maker's guide - H3's
formula (prompts.compose: labelled parts, a timeline in seconds, a tail) is H3's (2026-10-23, the user: «сделай для
новых»).

LTX 2.3 / 2.5 (Lightricks, ltx.io/blog/prompting-guide-for-ltx-2): one flowing paragraph in the present tense, 4-8
  sentences - the look and genre first, the place, who is there, the action from beginning to end, the camera, the
  sound with the spoken lines in quotes and their language. No labels, no timestamps.
WAN 2.2 5B (Alibaba's prompt guide, the Wan2.2 prompt extender): text-to-video = who + where + the motion + the
  camera and shot + the look (light, colour, lens, style), 60-200 words; from a frame (a continuation, a start photo)
  only the motion and the camera - the frame already shows who, where and the look. No sound.

The words are the writer's, the same as H3 gets; only their order and form change. A scene with its own prompt, an
unwritten one and H3 keep their prompt. render keeps a shot made before with the H3-derived prompt
(videomodels.adapt): only new shots get these.
"""
from __future__ import annotations

import re

from .. import i18n, videomodels
from . import prompts

_SAME = re.compile(r" \(the same (?:person )?in every shot\)")   # the lock's words for H3's Ref2VA and chains
_LABEL = re.compile(r"^Scene(?: continues(?: in the same place)?)?[:.]\s*")


def for_model(model: str, plan: dict, scene: dict) -> str:
    """The prompt `model` (a card id) gets for this scene; the scene's own (H3's) one when nothing is to change."""
    c = videomodels.shooter(videomodels.card(model))
    if c.id == "h3" or prompts.is_raw(scene) or not prompts.is_written(scene):
        return scene.get("prompt") or ""
    return _wan(c, plan, scene) if videomodels.family(c) == "wan5b" else _ltx(c, plan, scene)


def _parts(c: videomodels.Card, plan: dict, scene: dict) -> dict:
    framing = prompts.FRAMING.get(scene.get("framing"), "Medium shot")
    cam = prompts.CAMERAS.get(scene.get("camera"), prompts.CAMERAS["static"])
    place = _LABEL.sub("", prompts.place_line(plan, scene)).strip()
    if place.lower() in ("the same place as before", "the same place as before."):
        place = ""
    place = place[:1].upper() + place[1:] if place else ""
    if place and not place.endswith((".", "!", "?")):
        place += "."
    who = _SAME.sub("", prompts.lock_text(plan, scene))
    if plan["mode"] == "none":   # the lock is the world, the place what the frame shows now: the world first
        who, place = "", _join(who, place)
    empty = prompts.formula(plan) >= 2 and prompts.nobody(plan, scene)   # formula 2 (prompts.compose): no look where nobody is
    hold = prompts.held(plan, scene)
    return {"style": prompts._sentence(plan.get("style_en", "")),
            "who": "" if empty else who,
            "place": place,
            "action": videomodels.timeline_sentences(c, prompts.scene_timeline(plan, scene)),
            "camera": f"The framing of the picture, {prompts.hold_camera(scene)}." if hold else f"{framing}, {cam}.",
            "none": plan["mode"] == "none",
            "empty": empty,
            "hold": hold}


# a scene held on its picture (prompts.held): LTX gets the graph's rule (translate.LTX_FRAME_RULE)
LTX_HOLD = "Everything stays as in the picture: the same people, place, light and colours."
LTX_EMPTY = "There are no people and no faces anywhere in this shot."


def _ltx(c: videomodels.Card, plan: dict, scene: dict) -> str:
    """Look, place, who, the action, the camera, the sound - one paragraph. Held on its picture (formula 2): the
    picture instead of the look, the place and the people."""
    x = _parts(c, plan, scene)
    audio = prompts.audio_text(plan, scene)
    audio = audio[:1].upper() + audio[1:] if audio else ""
    tail = "No people." if x["none"] else LTX_EMPTY if x["empty"] else ""
    if x["hold"]:
        who = x["who"] if (scene.get("frame") or {}).get("empty") else ""   # a frame drawn empty that people come into
        return _join(LTX_HOLD, who, x["action"], x["camera"], audio, tail)
    return _join(x["style"], x["place"], x["who"], x["action"], x["camera"], audio, tail)


def _wan(c: videomodels.Card, plan: dict, scene: dict) -> str:
    """Who, where, the motion, the camera, the look; from a frame - the motion and the camera only."""
    x = _parts(c, plan, scene)
    if scene["kind"] == "continue" or prompts.starts_from_photo(scene):
        return _join(x["action"], x["camera"])
    return _join(x["who"], x["place"], x["action"], x["camera"], x["style"], "No people." if x["none"] or x["empty"] else "")


def for_id(plan: dict, scene: dict) -> str:
    """ID-LoRA's three parts for a storyboard scene shot with a hero's voice sample (render.voice_ref): [VISUAL] - the
    LTX paragraph without its sound, [SPEECH] - the lines word for word, [SOUNDS] - how they are said and the scene's
    own sound."""
    x = _parts(videomodels.card("ltx23"), plan, scene)
    lines = prompts.lines_of(plan, scene)
    hows = ", ".join(dict.fromkeys(prompts.HOW.get(ln["how"], "says") for ln in lines))
    sound = prompts._sentence(scene.get("sound_en", ""))
    return (f"[VISUAL]: {_join(x['style'], x['place'], x['who'], x['action'], x['camera'])}\n"
            f"[SPEECH]: {' '.join(ln['text'] for ln in lines)}\n"
            f"[SOUNDS]: Speaking {i18n.plan_lang_name(plan)} ({hows}), a clear voice close to the microphone. {sound}".strip())


def _join(*parts: str) -> str:
    return re.sub(r"\s+", " ", " ".join(p.strip() for p in parts if p and p.strip())).strip()
