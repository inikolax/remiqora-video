"""Phase 11: a clip's scenes cut on the song (remiqora-video planner/grid.py), in code - never the LLM's to change.

The fragment is whole bars from where the user starts it. Every part of the song inside it is a cut (the audio's
parts, and the chorus found from the repeated lines - a dense mix has no breaks to find it by), and inside a part the
scenes are whole bars, as even as possible: a loud part (a drop, a chorus) cuts about every 3 s, a quiet one (a
verse, a break) holds a scene twice as long - a music video's rhythm of cuts. Never longer than the model shoots
well (MAX_SHOT), never shorter than MIN_SHOT; a tempo too slow for whole bars cuts on beats.

Every clip scene is "new" (its own shot, a cut on the bar): the montage plays it to its bar (edit.lay `want`), the
shot is a little longer, up to its model's frame grid. What is sung during a scene, and how much of it has a voice,
goes with it to the writer (llm/writer.write_clip).
"""
from __future__ import annotations

import math
from typing import Optional

from .. import song

MIN_SHOT = 1.5      # s
MAX_SHOT = 8.0      # s: longer scenes of a clip are dull, and LTX's longest good one is 10
LOUD_SHOT = 3.0     # s a scene of a loud part aims at; a quiet part - twice that
SING_SHARE = 0.4    # a scene with a voice over this much of it is a singing one by default
# frames a clip's scene from a picture is shot longer and its start cut in the montage: the first frames of i2v are the
# still picture (a test clip on H3: the first 6 frames moved 2.5-4.4 against 5.9-9.3 after) - on
# every cut a photo that then starts moving. On the plan (clip.preroll): only the clips made since keep it
PREROLL = 8


def fragment(a: song.Analysis, start: float, seconds: float) -> tuple[float, float]:
    """[from, to] in the song's time: whole bars from the bar line nearest `start`, about `seconds` long; a start too
    close to the end moves back so the whole length fits. The whole song when the length covers it."""
    bar = a.bar_s
    if not a.bars or seconds >= a.duration - bar / 2:
        return 0.0, a.duration
    n = max(1, round(seconds / bar))
    i = min(range(len(a.bars)), key=lambda k: abs(a.bars[k] - start))
    last = max((k for k, t in enumerate(a.bars) if t + n * bar <= a.duration + 1e-3), default=0)
    ex0 = a.bars[max(0, min(i, last))]
    return round(ex0, 4), round(min(ex0 + n * bar, a.duration), 4)


def _snap(t: float, grid: list[float]) -> float:
    return min(grid, key=lambda g: abs(g - t)) if grid else t


def _split(a: float, b: float, grid: list[float], max_len: float, target: float) -> Optional[list[float]]:
    """Cut [a, b] at grid points into about length / target pieces, as even as possible, none over max_len."""
    length = b - a
    fewest = max(1, math.ceil(length / max_len - 1e-6))
    want = max(fewest, round(length / target))
    if want == 1:
        return [a, b]
    points = [g for g in grid if a + MIN_SHOT - 1e-6 <= g <= b - MIN_SHOT + 1e-6]
    for n in range(want, len(points) + 2):
        cuts, prev = [], a
        for i in range(1, n):
            ideal = a + i * length / n
            later = [p for p in points if p > prev + MIN_SHOT - 1e-6]
            if not later:
                break
            prev = min(later, key=lambda p: abs(p - ideal))
            cuts.append(prev)
        pieces = [a, *cuts, b]
        if len(pieces) == n + 1 and all(MIN_SHOT - 1e-6 <= y - x <= max_len + 1e-6 for x, y in zip(pieces, pieces[1:])):
            return pieces
    return None


def scenes(a: song.Analysis, lines: list[dict], ex0: float, ex1: float, max_shot: float = MAX_SHOT) -> list[dict]:
    """The clip's scenes over [ex0, ex1] (song time): [{start, seconds} in the video's time, part, loud, energy,
    chorus, sung: [{start, end, text}] relative to the scene, voice: 0..1, singing: words for the writer, shot}]."""
    max_shot = min(MAX_SHOT, max_shot)
    chorus = song.chorus_spans(lines)
    peak = max((s.energy for s in a.sections), default=1.0) or 1.0
    bars = [t for t in a.bars if ex0 - 1e-6 <= t <= ex1 + 1e-6]
    # the cuts between parts: the audio's parts and the chorus, on the nearest bar line
    bounds = {ex0, ex1}
    for s in a.sections:
        if ex0 + MIN_SHOT < s.start < ex1 - MIN_SHOT:
            bounds.add(_snap(s.start, bars))
    for c0, c1 in chorus:
        for t in (c0, c1):
            if ex0 + MIN_SHOT < t < ex1 - MIN_SHOT:
                bounds.add(_snap(t, bars))
    edges = sorted(bounds)
    while len(edges) > 2:   # a part shorter than a shot folds into its neighbour
        short = [i for i in range(len(edges) - 1) if edges[i + 1] - edges[i] < MIN_SHOT]
        if not short:
            break
        i = short[0]
        del edges[i + 1 if i + 1 < len(edges) - 1 else i]
    out = []
    for p0, p1 in zip(edges[:-1], edges[1:]):
        mid = (p0 + p1) / 2
        sec = a.section_at(mid)
        in_chorus = any(min(p1, cb) - max(p0, ca) >= 0.5 * (p1 - p0) for ca, cb in chorus)
        loud = in_chorus or sec.kind == "drop" or sec.energy >= 0.8 * peak
        target = LOUD_SHOT if loud else 2 * LOUD_SHOT
        bar_target = max(1, round(target / a.bar_s)) * a.bar_s
        pieces = None
        for grid in (bars, a.beats):
            pieces = _split(p0, p1, grid, max_shot, bar_target)
            if pieces:
                break
        if pieces is None:   # no grid fits (a tempo slower than the longest shot): even pieces
            n = max(math.ceil((p1 - p0) / max_shot), round((p1 - p0) / target))
            pieces = [p0 + (p1 - p0) * i / n for i in range(n + 1)]
        part = "chorus" if in_chorus else sec.kind
        for s0, s1 in zip(pieces[:-1], pieces[1:]):
            voice = song.voice_share(lines, s0, s1)
            e = [en for t, en in zip(a.bars, a.bar_energy) if s0 - 1e-6 <= t < s1 - 1e-6]
            out.append({"start": round(s0 - ex0, 4), "seconds": round(s1 - s0, 4), "part": part, "loud": loud,
                        "energy": round(sum(e) / len(e), 3) if e else sec.energy, "chorus": in_chorus,
                        "sung": sung_in(lines, s0, s1), "voice": round(voice, 2), "singing": song.singing(lines, s0, s1),
                        "shot": "sing" if voice >= SING_SHARE else "perform"})
    return out


def sung_in(lines: list[dict], s0: float, s1: float) -> list[dict]:
    """The words sung during [s0, s1), line by line, times relative to s0. A line is spread evenly over its time and
    the scene takes the words whose middle falls in it: Whisper writes a held verse as one 13 s line, and two scenes
    under it each sing their own half, not the whole line twice."""
    out = []
    for l in lines:
        words = l["text"].split()
        if not words or l["end"] <= s0 or l["start"] >= s1:
            continue
        step = (l["end"] - l["start"]) / len(words)
        mine = [k for k in range(len(words)) if s0 <= l["start"] + (k + 0.5) * step < s1]
        if mine:
            a, b = l["start"] + mine[0] * step, l["start"] + (mine[-1] + 1) * step
            out.append({"start": round(max(0.0, a - s0), 2), "end": round(min(s1, b) - s0, 2),
                        "text": " ".join(words[mine[0]: mine[-1] + 1])})
    return out


LIVELY = ("orbit", "track_side", "push_in", "pan", "rise", "pull_back")   # a loud part's camera, in turn
CALM = ("static", "push_in", "static", "pan")                          # a quiet one's


def vary_cameras(scenes: list[dict], handheld: bool = False) -> None:
    """A small writer gives every scene of a clip a static camera (2026-10-23: 15 of 15); a music video wants the
    camera to move with the music. When more than half are static, the static ones get a camera by their part:
    lively in a loud part, calm in a quiet one; a singing close-up stays static or pushes in slowly. `handheld`
    (formula 3): every singing close or medium scene gets the handheld camera - from its frame with a static camera
    or a push-in LTX sang an almost still picture."""
    if handheld:
        hand_held(scenes)
    static = [s for s in scenes if s.get("camera") == "static"]
    if len(static) * 2 <= len(scenes):
        return
    k_loud = k_calm = 0
    for s in static:
        if s.get("shot") == "sing":
            s["camera"] = "push_in" if s.get("loud") and s.get("framing") != "close" else "static"
        elif s.get("loud"):
            s["camera"] = LIVELY[k_loud % len(LIVELY)]
            k_loud += 1
        else:
            s["camera"] = CALM[k_calm % len(CALM)]
            k_calm += 1


def hand_held(scenes: list[dict]) -> None:
    """Formula 3: a singing close or medium scene is shot with the handheld camera."""
    for s in scenes:
        if s.get("shot") == "sing" and s.get("framing") in ("close", "medium"):
            s["camera"] = "handheld"


def split(plan: dict, i: int, bars: list[float], lines: list[dict]) -> Optional[dict]:
    """«+ Сцена» in a clip: scene i gives the second half of its time - cut on the bar nearest its middle, each half at
    least MIN_SHOT - to a new scene after it, so no other scene moves along the song. Both halves get what is sung in
    them again. -> the new scene's song facts ({seconds, part, loud, energy, chorus, sung, voice, singing}), or None
    when the scene is too short to split. Scene i is shortened in place."""
    s = plan["scenes"][i]
    t0 = float((plan.get("clip") or {}).get("from") or 0) + sum(float(x.get("seconds") or 0) for x in plan["scenes"][:i])
    t1 = t0 + float(s.get("seconds") or 0)
    mid = (t0 + t1) / 2
    cuts = [b for b in bars if t0 + MIN_SHOT - 1e-6 <= b <= t1 - MIN_SHOT + 1e-6]
    if not cuts:
        if t1 - t0 < 2 * MIN_SHOT:
            return None
        cuts = [mid]
    cut = min(cuts, key=lambda b: abs(b - mid))

    def facts(a: float, b: float) -> dict:
        return {"seconds": round(b - a, 4), "sung": sung_in(lines, a, b), "voice": round(song.voice_share(lines, a, b), 2),
                "singing": song.singing(lines, a, b)}
    s.update(facts(t0, cut))
    return {**{k: s[k] for k in ("part", "loud", "energy", "chorus") if k in s}, **facts(cut, t1)}
