"""The scene grid, in code (never the LLM's to change): the length -> scenes of 5 s, each "new" (text-to-video, its own
place) or "continue" (image-to-video from the previous scene's last frame). A model that shoots 10 s well (LTX,
videomodels.Card.grid_seconds) gets scenes of 10 s: 30 s = 3 scenes, 15 s = 10 + 5.

Chains: with people at most 3 continuations in a row, then a new scene - the face drifts over a longer chain
(30 s held with the look repeated word for word); with 10 s scenes one (a chain of 20 s, as 4 x 5).
The scenes are spread over as few chains as that allows, as evenly as possible: 30 s = 3 + 3, not 4 + 2. Without
people the whole video is one chain: landscapes and effects don't drift in a way that matters, and a cut would break
the flow.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

from .. import i18n

SCENE_SECONDS = 5
MAX_CONTINUES = 3          # with people
CHAIN_SECONDS = 20         # ... so a chain of 5 s scenes is 20 s; longer scenes keep to that
MODES = ("one", "several", "none")   # who is in the frame: one hero / several / no people
MAX_SECONDS = 900   # 15 min; past 3 min the writer works from an outline (writer.write_long)


@dataclass
class Slot:
    index: int
    kind: str      # new | continue
    chain: int     # chains count from 0; a "new" slot opens one
    start: float
    end: float
    seconds: Optional[float] = None   # a grid of longer scenes: each one's own (seconds_of); None - the 5 s

    def public(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def max_continues(scene_seconds: float) -> int:
    """Continuations in a row with people: 3 of 5 s scenes, of 10 s one - the chain stays about CHAIN_SECONDS."""
    return MAX_CONTINUES if scene_seconds < 2 * SCENE_SECONDS else max(1, round(CHAIN_SECONDS / scene_seconds) - 1)


def chain_lengths(n: int, mode: str, continues: int = MAX_CONTINUES) -> list[int]:
    if mode == "none":
        return [n]
    chains = math.ceil(n / (continues + 1))
    base, extra = divmod(n, chains)
    return [base + (1 if i < extra else 0) for i in range(chains)]


def lengths(seconds: float, scene_seconds: float = SCENE_SECONDS) -> list[float]:
    """The scenes' lengths: 5 s each; longer scenes - as many as fit in the length (rounded to 5 s), the rest one
    scene of 5 s at the end (15 s with 10 s scenes: 10 + 5)."""
    total = max(1, round(min(seconds, MAX_SECONDS) / SCENE_SECONDS)) * SCENE_SECONDS
    if scene_seconds == SCENE_SECONDS:
        return [SCENE_SECONDS] * (total // SCENE_SECONDS)
    n, rest = divmod(total, scene_seconds)
    return [scene_seconds] * int(n) + ([rest] if rest else [])


def grid(seconds: float, mode: str, scene_seconds: float = SCENE_SECONDS) -> list[Slot]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    secs = lengths(seconds, scene_seconds)
    own = scene_seconds != SCENE_SECONDS   # a 5 s grid's scenes carry no length, as always
    slots, i, t = [], 0, 0
    for c, length in enumerate(chain_lengths(len(secs), mode, max_continues(scene_seconds))):
        for k in range(length):
            slots.append(Slot(index=i, kind="new" if k == 0 else "continue", chain=c, start=t, end=t + secs[i],
                              seconds=secs[i] if own else None))
            t += secs[i]
            i += 1
    return slots


def renumber(scenes: list[dict], mode: str) -> list[str]:
    """After a hand edit (a scene added, removed, moved, its kind changed): indices, times and chains again, in place.
    The first scene is always "new". A continuation starts from the last frame of the scene before it, or of any
    earlier scene it names (`from`, a scene id - dropped when that scene is gone, later, or the one just before).
    A chain is a run of scenes each going on from the one just before it (they play as one shot); a continuation
    from an earlier scene opens a chain of its own. The face drifts along the frames, not the order: the depth
    counts through `from`. Returns the Russian warnings about the grid (the chain rule is advice, not a lock)."""
    chain, warnings, t = -1, [], 0.0
    depth: dict[int, int] = {}
    for i, s in enumerate(scenes):
        if i == 0:
            s["kind"] = "new"
        d = 0
        if s["kind"] == "new":
            s.pop("from", None)
            chain += 1
        else:
            src = next((x for x in scenes[:i] if s.get("from") and x.get("id") == s["from"]), None)
            if src is None or src is scenes[i - 1]:
                s.pop("from", None)
                src = scenes[i - 1]
            else:
                chain += 1   # back to an earlier scene's frame: a shot of its own after the scene before it
            d = depth[id(src)] + 1
            if mode != "none" and d == max_continues(seconds_of(s)) + 1:
                warnings.append(i18n.L(f"Сцена {i + 1}: уже {d}-е продолжение подряд — лицо может уплыть, лучше начать новую сцену", f"Scene {i + 1}: already continuation no. {d} in a row - the face may drift, better start a new scene"))
        depth[id(s)] = d
        n = seconds_of(s)
        s.update(index=i, chain=chain, start=round(t, 4), end=round(t + n, 4))
        t += n
    return warnings


def seconds_of(s: dict) -> float:
    """A scene's length: its own (`seconds`: a clip's scene cut on the bars - phase 11, a scene of a 10 s grid) or
    SCENE_SECONDS."""
    try:
        return min(15.0, max(0.5, float(s["seconds"]))) if s.get("seconds") else SCENE_SECONDS
    except (TypeError, ValueError):
        return SCENE_SECONDS
