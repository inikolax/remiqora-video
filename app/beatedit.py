"""Beat-synced edit of a song piece: a pool of short shots cut on the beat grid (a port of the hand-made beat
editor this module was ported from, to the app's own libraries: numpy + cv2 + Pillow + ffmpeg).

What it makes: a 9:16 clip of one drop - an intro bar of strobe on the close-up, build cuts (2 beats, then 1), a riser
bar (quarter-beat inserts, a half-beat gap), the drop (impact, cut patterns, a mirrored bar, a stutter bar with
one-frame inverts, a last bar in half beats) and an outro on the close-up with a tape stop. Frame effects (warp, RGB
split, glitch, zoom blur, whip, kaleido, strobe, invert), a grade (curve + shadow tint, vignette, grain), captions from
the timed words, a title over the intro, a tiny HUD. The sound: the song's piece + a noise riser, a half-beat duck gap,
a sub boom + crash on the drop, a tape stop, loudness by ffmpeg's two-pass loudnorm.

The beat grid is the app's own (song.analyze: beats, bpm); the kick and snare envelopes (30-180 Hz, 1.8-8 kHz at 60 Hz)
come from the piece's STFT with a mel band onset like librosa's - no librosa / scipy / pyloudnorm.

A run is a process of its own (the CPU render of ~1400 frames must not hold the server's event loop):

    python -m app.beatedit cfg.json

and prints JSON progress lines ({"stage": ..., "done": ..., "total": ...}); the last one is {"stage": "done", ...}, an
error is {"error": ...} (exit 1). The same from Python: `render(cfg, progress)`; `plan(cfg)` gives the grid, the edit
decision list and the captions without touching a video (what the tests and the graph node read).

cfg (a dict / the JSON file):
  clips      [{id, path, role | roles}]  the pool: role hero | atmos | close | impact | riser (a clip may have several)
  song       the song file; analysis: {beats, bpm} (optional: the stored analysis, else song.analyze runs)
  drop       the song second where the drop starts (snapped to the nearest beat); bpm: a tempo hint (the grid is folded to it)
  words      [{start, end, word}] the sung words in the song's time; written: the written lyrics (spelling fix, optional)
  title, hud, palette {a, b, tint} (BGR), preset, params (overrides), fps (30 | 60), loudness (LUFS), preview (540x960)
  out        the mp4 to write (its .json beside it: the cuts as frame numbers, the edit decision list)
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

VERSION = 1                 # in the node's key: bump it when the picture or the sound changes
SR = 44100
KEY_FPS = 60                # the envelopes' and the effects' own rate: an effect lasts as many ms at 30 fps as at 60
ROLES = ("hero", "atmos", "close", "impact", "riser")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FONT_DIR = Path(__file__).resolve().parent / "static" / "fonts"

# ---------------------------------------------------------------- presets: sets of values
TECHNO: dict = dict(
    build_bars=3, drop_bars=8,
    zoom_build=0.04, zoom_drop=0.07,        # the kick's punch-in
    shake_build=0.004, shake_drop=0.009,    # the kick's shake (share of the width)
    rgb_build=0.007, rgb_drop=0.013,        # the snare's RGB split (share of the width)
    strobe=True, kaleido=True, invert=True, stutter=True, tape_stop=True,
    riser=True,                             # the noise riser and the half-beat gap in the sound
    impact_sound=True,
    patterns=[[2], [1, 1], [2, 1, 1], [1, 1, 2], [1, 1, 1, 1], [2, 2]], impact_every=4,
    grade=1.0, vignette=1.0, grain=7.0,
    captions=True, hud=True, sharpen=True,
)
# TODO(stage 4): tune the other genres on the owner's clips 55 (DnB, 174 BPM) and 56 (hardstyle, 150 BPM); until then
# they are copies of "techno"
PRESETS: dict[str, dict] = {
    "techno": TECHNO,
    "dnb": json.loads(json.dumps(TECHNO)),
    "hardstyle": json.loads(json.dumps(TECHNO)),
    "pop": json.loads(json.dumps(TECHNO)),
}
DEFAULTS = dict(preset="techno", fps=60, loudness=-10.0)
PRESET_NAMES = {"techno": ("Техно", "Techno"), "dnb": ("DnB", "DnB"), "hardstyle": ("Хардстайл", "Hardstyle"), "pop": ("Поп", "Pop")}


def _spec(key, kind, lo, hi, step, group, ru, en, help_ru, help_en):
    return {"key": key, "kind": kind, "min": lo, "max": hi, "step": step, "group": group, "ru": ru, "en": en,
            "help_ru": help_ru, "help_en": help_en}


# what the beat node's panel shows: every parameter the preset sets and the user may change (the page builds its sliders from it)
PARAM_SPEC = [
    _spec("build_bars", "int", 2, 6, 1, "length", "Тактов нарастания", "Build bars", "Сколько тактов до такта-райзера: чем больше, тем дольше вступление и нарастание.",
          "Bars before the riser bar: more bars, a longer intro and build."),
    _spec("drop_bars", "int", 4, 16, 1, "length", "Тактов дропа", "Drop bars", "Сколько тактов длится дроп. 8 тактов при 140 BPM - около 14 секунд.",
          "How many bars the drop lasts. 8 bars at 140 BPM is about 14 seconds."),
    _spec("zoom_build", "float", 0, 0.15, 0.005, "kick", "Зум на кике (нарастание)", "Kick zoom (build)", "Насколько кадр наезжает на каждый удар бочки в нарастании.",
          "How far the picture punches in on every kick in the build."),
    _spec("zoom_drop", "float", 0, 0.15, 0.005, "kick", "Зум на кике (дроп)", "Kick zoom (drop)", "Насколько кадр наезжает на каждый удар бочки в дропе.",
          "How far the picture punches in on every kick in the drop."),
    _spec("shake_build", "float", 0, 0.03, 0.001, "kick", "Тряска на кике (нарастание)", "Kick shake (build)", "Тряска кадра на ударе, доля ширины.", "Shake of the picture on a kick, a share of the width."),
    _spec("shake_drop", "float", 0, 0.03, 0.001, "kick", "Тряска на кике (дроп)", "Kick shake (drop)", "Тряска кадра на ударе в дропе, доля ширины.", "Shake on a kick in the drop, a share of the width."),
    _spec("rgb_build", "float", 0, 0.04, 0.001, "snare", "RGB-сдвиг на снейре (нарастание)", "Snare RGB split (build)", "Расхождение красного и синего каналов на снейре.", "How far the red and blue channels split on a snare."),
    _spec("rgb_drop", "float", 0, 0.04, 0.001, "snare", "RGB-сдвиг на снейре (дроп)", "Snare RGB split (drop)", "Расхождение каналов на снейре в дропе.", "Channel split on a snare in the drop."),
    _spec("strobe", "bool", 0, 1, 1, "effects", "Строб на вступлении", "Intro strobe", "Белые вспышки на крупном плане в первом такте.", "White flashes on the close-up in the first bar."),
    _spec("kaleido", "bool", 0, 1, 1, "effects", "Калейдоскоп", "Kaleidoscope", "Зеркальные такты в дропе (не на герое).", "Mirrored bars in the drop (never on the hero)."),
    _spec("invert", "bool", 0, 1, 1, "effects", "Инверсии", "Inverts", "Однокадровые негативы на снейре в такте-статтере.", "One-frame negatives on the snare in the stutter bar."),
    _spec("stutter", "bool", 0, 1, 1, "effects", "Статтер", "Stutter", "Повтор короткого куска кадра перед последним тактом дропа.", "A short piece of the picture repeated before the last drop bar."),
    _spec("tape_stop", "bool", 0, 1, 1, "effects", "Остановка ленты", "Tape stop", "Концовка: картинка и звук замедляются до остановки.", "The outro: picture and sound slow down to a stop."),
    _spec("riser", "bool", 0, 1, 1, "sound", "Райзер и провал", "Riser and gap", "Шумовой райзер и провал в полдоли перед дропом.", "A noise riser and a half-beat gap before the drop."),
    _spec("impact_sound", "bool", 0, 1, 1, "sound", "Удар на дропе", "Drop impact", "Саб-бум и крэш на первой доле дропа.", "A sub boom and a crash on the first beat of the drop."),
    _spec("grade", "float", 0, 1.5, 0.05, "grade", "Сила грейда", "Grade strength", "Кино-цвет: давленые чёрные и тонированные тени. 0 - без грейда.", "Cinema colour: crushed blacks and tinted shadows. 0 is no grade."),
    _spec("vignette", "float", 0, 1.5, 0.05, "grade", "Виньетка", "Vignette", "Затемнение краёв кадра.", "Dark edges of the frame."),
    _spec("grain", "float", 0, 20, 0.5, "grade", "Зерно", "Grain", "Плёночное зерно.", "Film grain."),
    _spec("hud", "bool", 0, 1, 1, "effects", "HUD", "HUD", "Крошечная надпись «TECHNO // 140 BPM», номер такта и точка на кике.", "A tiny «TECHNO // 140 BPM» line, the bar number and a kick dot."),
]


def words_of(cfg: dict) -> list[dict]:
    """The sung words of the cfg as the captions use them: the written lyrics' spelling, then the user's table edits
    (`caption_edits`: [{i, word?, start?, end?, hide?}], i = the word's index; a hidden word gets `hide`)."""
    words = [dict(w) for w in cfg.get("words") or []]
    if words and cfg.get("written"):
        from . import song
        words = song.timed_words(words, cfg["written"])
    for e in cfg.get("caption_edits") or []:
        try:
            w = words[int(e["i"])]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if e.get("word") not in (None, ""):
            w["word"] = str(e["word"])
        for k in ("start", "end"):
            if e.get(k) not in (None, ""):
                w[k] = float(e[k])
        if e.get("hide"):
            w["hide"] = True
    return words


def params_of(cfg: dict) -> dict:
    """The preset's values with the cfg's own on top (`params`, and edit2's build_bars / drop_bars at the top level)."""
    p = json.loads(json.dumps(PRESETS.get(cfg.get("preset") or "techno", TECHNO)))
    for k in ("build_bars", "drop_bars"):
        if cfg.get(k) is not None:
            p[k] = int(cfg[k])
    p.update(cfg.get("params") or {})
    p["build_bars"] = max(2, int(p["build_bars"]))
    p["drop_bars"] = max(2, int(p["drop_bars"]))
    return p


def default_role(k: int) -> str:
    """A shot nobody gave a role: hero and atmosphere in turn."""
    return "hero" if k % 2 == 0 else "atmos"


# ---------------------------------------------------------------- the beat grid
@dataclass
class Grid:
    t0: float                  # the song second the piece starts at
    beat: float                # seconds per beat
    bb: int                    # build bars
    db: int                    # drop bars
    beats: dict                # j (0 = the drop) -> the beat's song time

    def t(self, j: int) -> float:
        """Piece time of beat j."""
        return self.beats[j] - self.t0

    def at(self, j: float) -> float:
        """Piece time of beat j, a fraction of a beat too."""
        f = math.floor(j)
        return self.t(f) if float(j).is_integer() else self.t(f) + (j - f) * self.beat

    @property
    def need_before(self) -> int:
        return (self.bb + 1) * 4

    @property
    def drop(self) -> float:
        return self.t(0)

    @property
    def riser(self) -> float:
        return self.t(-4)

    @property
    def outro(self) -> float:
        return self.t(self.db * 4)

    @property
    def dur(self) -> float:
        return self.t(self.db * 4 + 4)

    @property
    def bpm(self) -> float:
        return 60.0 / self.beat


def make_grid(beats, drop: float, bpm_hint: Optional[float], bb: int, db: int) -> Grid:
    """The beats around the drop (0 = the drop, snapped to the nearest beat) from the song's own beat list. The tempo
    guard of edit2: a grid at half the hinted tempo gets its missing beats in between, one at double keeps every other."""
    bt = np.asarray(beats, float)
    if len(bt) < 8:
        raise ValueError("the beat grid is too short")
    per = float(np.median(np.diff(bt)))
    hint = 60.0 / float(bpm_hint) if bpm_hint else per
    if per > hint * 1.5:          # half tempo: put the missing beats in between
        bt = np.sort(np.concatenate([bt, (bt[:-1] + bt[1:]) / 2]))
        per /= 2
    k0 = int(np.argmin(np.abs(bt - drop)))
    if per < hint * 0.66:         # double tempo: keep every other one, aligned to the drop
        bt = bt[k0 % 2::2]
        k0 = int(np.argmin(np.abs(bt - drop)))
    period = float(np.median(np.diff(bt)))
    need_before, need_after = (bb + 1) * 4, (db + 1) * 4
    out = {}
    for j in range(-need_before, need_after + 1):   # the grid runs on with the median period where the song ran out
        i = k0 + j
        out[j] = float(bt[i]) if 0 <= i < len(bt) else float(bt[k0] + j * period)
    return Grid(t0=out[-need_before], beat=period, bb=bb, db=db, beats=out)


# ---------------------------------------------------------------- the envelopes from the sound
def _hz_to_mel(f):
    f = np.asarray(f, float)
    return np.where(f >= 1000.0, 15.0 + np.log(np.maximum(f, 1e-9) / 1000.0) / (np.log(6.4) / 27.0), f / (200.0 / 3))


def _mel_to_hz(m):
    m = np.asarray(m, float)
    return np.where(m >= 15.0, 1000.0 * np.exp((np.log(6.4) / 27.0) * (m - 15.0)), m * (200.0 / 3))


def mel_bank(sr: int, n_fft: int, n_mels: int, fmin: float, fmax: float) -> np.ndarray:
    """A Slaney mel filter bank (area-normalised), as librosa builds it by default: (n_mels, n_fft // 2 + 1)."""
    fft_f = np.linspace(0, sr / 2, n_fft // 2 + 1)
    mel_f = _mel_to_hz(np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_mels + 2))
    fdiff = np.diff(mel_f)
    ramps = mel_f[:, None] - fft_f[None, :]
    lower = -ramps[:-2] / fdiff[:-1, None]
    upper = ramps[2:] / fdiff[1:, None]
    w = np.maximum(0, np.minimum(lower, upper))
    return (w * (2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels]))[:, None]).astype(np.float32)


def _power_frames(x: np.ndarray, n_fft: int, hop: int) -> np.ndarray:
    """|STFT|^2 of mono x, frames centred on i * hop (zero-padded like librosa's center=True): (frames, bins)."""
    x = np.pad(x.astype(np.float32), (n_fft // 2, n_fft // 2))
    n = 1 + (len(x) - n_fft) // hop
    fr = np.lib.stride_tricks.as_strided(x, (n, n_fft), (x.strides[0] * hop, x.strides[0]))
    win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n_fft) / n_fft)).astype(np.float32)   # periodic Hann
    out = np.empty((n, n_fft // 2 + 1), np.float32)
    for i in range(0, n, 2048):
        out[i:i + 2048] = np.abs(np.fft.rfft(fr[i:i + 2048] * win, axis=1)) ** 2
    return out


def band_envelopes(mono: np.ndarray, bands=((30, 180, 0.80), (1800, 8000, 0.75))) -> list[np.ndarray]:
    """Per band (fmin, fmax, decay): an onset envelope at 60 per second - the positive change of the band's
    log-mel energy (32 mels), a 98th-percentile normalisation, a clipped peak that decays - as edit2 had it from librosa."""
    n_fft, hop = 2048, SR // KEY_FPS
    P = _power_frames(mono, n_fft, hop)
    out = []
    for fmin, fmax, decay in bands:
        mel = P @ mel_bank(SR, n_fft, 32, fmin, fmax).T                     # (frames, 32)
        db = 10 * np.log10(np.maximum(1e-10, mel))
        db = np.maximum(db, db.max() - 80.0)
        d = np.maximum(0.0, db[1:] - db[:-1]).mean(axis=1)
        pad = 1 + n_fft // (2 * hop)
        o = np.concatenate([np.zeros(pad), d])[:len(db)]
        o = o / (np.percentile(o, 98) + 1e-6)
        e = np.zeros_like(o)
        v = 0.0
        for i, x in enumerate(o):
            v = max(min(1.0, float(x)), v * decay)
            e[i] = v
        out.append(e)
    return out


# ---------------------------------------------------------------- the captions
def caption_groups(words: list[dict], g: Grid) -> list[list]:
    """[start, end, TEXT] in piece time: the sung words of the piece (not the last two beats), short ones joined."""
    ws = []
    for w in words:
        s = float(w["start"])
        if g.t0 - 0.05 <= s < g.t0 + g.dur - 2 * g.beat:
            txt = re.sub(r"[^\w'!?-]", "", str(w["word"]).strip()).upper()
            if txt:
                ws.append([s - g.t0, float(w["end"]) - g.t0, txt])
    groups: list[list] = []
    for s, e, w in ws:
        if groups and (s - groups[-1][1] < 0.10) and len(groups[-1][2]) + len(w) <= 9 and len(w) <= 3:
            groups[-1][1] = e
            groups[-1][2] += " " + w
        else:
            groups.append([s, e, w])
    for i, grp in enumerate(groups):
        nxt = groups[i + 1][0] if i + 1 < len(groups) else grp[1] + 0.4
        grp[1] = max(grp[0] + 0.18, min(nxt, grp[1] + 0.35, grp[0] + 1.2))
    return groups


# ---------------------------------------------------------------- the pool and the edit decision list
@dataclass
class Pool:
    hero: list
    atmos: list
    close: str
    impact: str
    riser: str


def pool_of(clips: list[dict]) -> Pool:
    """The shots by their roles. A clip's `roles` (or `role`) - one or several; a clip without one gets hero / atmos in turn.
    Missing parts fall back: no hero - every clip that is not atmosphere, no atmosphere - the heroes, no close / impact /
    riser - the first hero / the first hero / the first atmosphere."""
    names = [c["id"] for c in clips]
    if len(set(names)) != len(names):
        raise ValueError("two shots with one id")
    roles = {}
    for k, c in enumerate(clips):
        r = c.get("roles") or c.get("role") or default_role(k)
        roles[c["id"]] = [r] if isinstance(r, str) else list(r)
    by = lambda role: [n for n in names if role in roles[n]]  # noqa: E731
    hero, atmos = by("hero"), by("atmos")
    if not hero:
        hero = [n for n in names if "atmos" not in roles[n]] or list(names)
    if not atmos:
        atmos = list(hero)
    close = (by("close") or hero)[0]
    impact = (by("impact") or hero)[0]
    riser = (by("riser") or atmos)[0]
    return Pool(hero, atmos, close, impact, riser)


def build_edl(g: Grid, pool: Pool, p: dict) -> list[dict]:
    """The edit decision list as edit2 makes it: segments {t0, t1, j, n, title, speed, tr, fx, inp} in piece time (beat
    index j, 0 = the drop; n beats). `pick` avoids the last three used shots."""
    edl: list[dict] = []
    use: dict[str, int] = {}
    BB, DB, B = g.bb, g.db, g.beat

    def seg(j, n, title, speed=1.0, tr="cut", fx=(), inp=None):
        k = use.get(title, 0)
        use[title] = k + 1
        if inp is None:
            inp = 0.45 + (k * 0.83) % 1.6
        edl.append(dict(t0=g.at(j), j=j, n=n, title=title, speed=speed, tr=tr, fx=set(fx), inp=inp))

    ptr = {"h": 0, "a": 0}
    recent: list[str] = []

    def pick(kind):
        lst = pool.hero if kind == "h" else pool.atmos
        for _ in range(len(lst)):
            t = lst[ptr[kind] % len(lst)]
            ptr[kind] += 1
            if t not in recent[-3:]:
                recent.append(t)
                return t
        t = lst[ptr[kind] % len(lst)]
        recent.append(t)
        return t

    TR = ["glitch", "flash", "whip", "zoomblur"]
    j = -g.need_before
    seg(j, 4, pool.close, 0.45, "cut", {"strobe"} if p["strobe"] else (), inp=0.6)          # intro bar: strobe on the close-up
    j += 4
    for b in range(BB - 2):                                                                  # build: 2-beat cuts
        for h in range(2):
            seg(j, 2, pick("a" if (b + h) % 2 == 0 else "h"), 0.7, TR[(b * 2 + h) % 4])
            j += 2
    for h in range(4):                                                                       # last build bar: 1-beat cuts
        seg(j, 1, pick("h" if h % 2 else "a"), 1.0 + 0.3 * h, TR[h % 4])
        j += 1
    seg(j, 2, pool.riser, 0.8, "flash", {"riser"}, inp=0.5)                                  # riser bar
    j += 2
    for q in range(6):
        seg(j + q / 4, 0.25, pool.riser if q % 2 == 0 else pick("h"), 1.6, "cut", {"riser"})
    seg(j + 1.5, 0.5, pool.riser, 2.6, "glitch", {"riser", "gap"})
    j += 2
    assert j == 0, j
    seg(0, 2, pool.impact, 0.55, "impact")                                                   # the drop
    recent.append(pool.impact)
    j = 2
    pats = p["patterns"]
    every = max(1, int(p["impact_every"]))
    pi = 0
    while j < DB * 4:
        bar = j // 4
        left = 4 - j % 4
        if j % 4 == 0 and bar % every == 0 and bar > 0:
            seg(j, 2, pick("h"), 0.6, "impact")
            j += 2
            continue
        pat = list(pats[pi % len(pats)])
        pi += 1
        if sum(pat) > left:
            pat = [1] * left
        for n in pat:
            fx = set()
            if bar % 4 == 2 and p["kaleido"]:
                fx.add("kaleido")
            if bar % 4 == 3 and j % 4 == 3 and p["stutter"]:
                fx.add("stutter")
            if bar == DB - 1 and n == 1:     # the last drop bar runs in half beats
                seg(j, 0.5, pick("a"), 1.6, "glitch", fx)
                seg(j + 0.5, 0.5, pick("h"), 1.6, "flash", fx)
                j += 1
                continue
            seg(j, n, pick("h" if n >= 2 or (j % 2 == 0) else "a"), 0.9 + 0.4 * (n == 1), TR[(j + pi) % 4], fx)
            j += n
    seg(DB * 4, 4, pool.close, 0.45, "flash", {"outro"}, inp=1.2)
    edl.sort(key=lambda s: s["t0"])
    for i, s in enumerate(edl):
        s["t1"] = edl[i + 1]["t0"] if i + 1 < len(edl) else g.dur
    return edl


# ---------------------------------------------------------------- the plan: everything but the pictures and the sound
@dataclass
class Plan:
    cfg: dict
    p: dict
    grid: Grid
    pool: Pool
    edl: list
    groups: list
    clips: dict                       # id -> path
    W: int
    H: int
    fps: int
    bpm_show: int
    palette: dict = field(default_factory=dict)
    pre: dict = field(default_factory=dict)   # id -> the seconds at the start of that shot that stand still (beat_models.preroll)

    @property
    def n_frames(self) -> int:
        return int(round(self.grid.dur * self.fps))

    def section(self, t: float) -> str:
        g = self.grid
        return ("intro" if t < g.t(-g.need_before + 4) else "build" if t < g.riser else "riser" if t < g.drop
                else "drop" if t < g.outro else "outro")

    def cuts(self) -> list[int]:
        """The first frame of every segment after the first: the first frame i with i / fps >= t0, the one frame_segments
        switches at (a rounded frame would be reported one early for 9 of 42 cuts at 143 BPM / 30 fps)."""
        return sorted({switch_frame(s["t0"], self.fps) for s in self.edl[1:]})


def _beats_of(cfg: dict) -> tuple[list, Optional[float]]:
    """The song's beat list: the cfg's stored analysis, else the analysis of the song file."""
    an = cfg.get("analysis")
    hint = cfg.get("bpm")
    if an and an.get("beats"):
        return an["beats"], hint
    from . import song
    a = song.analyze(Path(cfg["song"]), float(hint) if hint else None)
    return a.beats, hint


def plan(cfg: dict) -> Plan:
    p = params_of(cfg)
    if cfg.get("drop") is None:
        raise ValueError("the cfg has no drop")
    beats, hint = _beats_of(cfg)
    g = make_grid(beats, float(cfg["drop"]), hint, p["build_bars"], p["drop_bars"])
    clips = {c["id"]: c["path"] for c in cfg["clips"]}
    pre = {c["id"]: float(c["pre"]) for c in cfg["clips"] if c.get("pre") is not None}
    pool = pool_of(cfg["clips"])
    edl = build_edl(g, pool, p)
    words = [w for w in words_of(cfg) if not w.get("hide")]
    groups = caption_groups(words, g) if p["captions"] else []
    W, H = (540, 960) if cfg.get("preview") else (1080, 1920)
    fps = int(cfg.get("fps") or DEFAULTS["fps"])
    return Plan(cfg=cfg, p=p, grid=g, pool=pool, edl=edl, groups=groups, clips=clips, W=W, H=H, fps=fps,
                bpm_show=int(round(60 / g.beat)), palette=cfg.get("palette") or {}, pre=pre)


# ---------------------------------------------------------------- the shots: decode what the edit uses
PRE_DEFAULT = 0.35          # H3's (beat_models.PREROLL_S["h3"]); the cfg's clip says its own model's


def src_index(x: float, n: int, fps: float, pre: float = PRE_DEFAULT) -> int:
    """The source frame of a shot at source time x: it plays from `pre` s (the first frames of an i2v scene stand still;
    0.35 s for H3, beat_models.preroll for the model) to its end and back (ping-pong) as long as the edit asks."""
    lo, hi = pre, n / fps - 1 / fps
    span = hi - lo
    if span < 1 / fps:
        lo, span = 0.0, max(hi, 1 / fps)
    x = (x - lo) % (2 * span)
    x = lo + (x if x <= span else 2 * span - x)
    return min(n - 1, max(0, int(x * fps)))


def src_time(pl: Plan, s: dict, t: float) -> float:
    """The source time a segment shows at piece time t (the stutter repeats a slice, the outro's tape stop slows down)."""
    B, DUR = pl.grid.beat, pl.grid.dur
    lt = t - s["t0"]
    if "stutter" in s["fx"]:
        ch = B / 4 if lt < B / 2 else B / 8
        lt = lt % ch
    if "outro" in s["fx"] and pl.p["tape_stop"]:
        ts = DUR - 2 * B
        if t > ts:
            u = (t - ts) / (2 * B)
            lt = (ts - s["t0"]) + 2 * B * (u - u * u / 2)
    return s["inp"] + lt * s["speed"]


class Shots:
    """The frames the edit uses, decoded once. A clip is read whole, only the frames the edit shows are kept (the
    edit is known before the first frame is drawn), so a pool of 16 clips does not sit in memory whole."""

    def __init__(self, pl: Plan, seg_of: list[int], progress: Callable = lambda *a: None):
        self.pl, self.keep, self.meta = pl, {}, {}
        self.cache: OrderedDict = OrderedDict()
        titles = sorted({s["title"] for s in pl.edl})
        for k, title in enumerate(titles):
            progress("shots", k, len(titles))
            cap = cv2.VideoCapture(str(pl.clips[title]))
            fps = cap.get(cv2.CAP_PROP_FPS) or 24
            frames = []
            while True:
                ok, f = cap.read()
                if not ok:
                    break
                frames.append(f)
            cap.release()
            if not frames:
                raise ValueError(f"no frames in {pl.clips[title]}")
            self.meta[title] = (len(frames), fps)
            need = set()
            for i, si in enumerate(seg_of):
                s = pl.edl[si]
                if s["title"] == title:
                    need.add(src_index(src_time(pl, s, i / pl.fps), len(frames), fps, pl.pre.get(title, PRE_DEFAULT)))
            for idx in need:
                self.keep[(title, idx)] = frames[idx]
        progress("shots", len(titles), len(titles))

    def frame(self, title: str, x: float) -> np.ndarray:
        n, fps = self.meta[title]
        idx = src_index(x, n, fps, self.pl.pre.get(title, PRE_DEFAULT))
        key = (title, idx)
        hit = self.cache.get(key)
        if hit is not None:
            self.cache.move_to_end(key)
            return hit
        f = self.keep[key]
        W, H = self.pl.W, self.pl.H
        h0, w0 = f.shape[:2]
        if abs(w0 / h0 - W / H) > 0.01:      # not 9:16: the centre crop fills the frame
            if w0 * H > h0 * W:
                nw = int(round(h0 * W / H))
                f = f[:, (w0 - nw) // 2:(w0 - nw) // 2 + nw]
            else:
                nh = int(round(w0 * H / W))
                f = f[(h0 - nh) // 2:(h0 - nh) // 2 + nh]
        if f.shape[1] != W:
            f = cv2.resize(f, (W, H), interpolation=cv2.INTER_CUBIC if W > f.shape[1] else cv2.INTER_AREA)
            if W > 800 and self.pl.p["sharpen"]:
                bl = cv2.GaussianBlur(f, (0, 0), 1.2)
                f = cv2.addWeighted(f, 1.45, bl, -0.45, 0)
        self.cache[key] = f
        if len(self.cache) > 48:
            self.cache.popitem(last=False)
        return f


# ---------------------------------------------------------------- effects (uint8 BGR)
def warp(img, scale=1.0, dx=0.0, dy=0.0, ang=0.0):
    if scale == 1 and not dx and not dy and not ang:
        return img
    H, W = img.shape[:2]
    M = cv2.getRotationMatrix2D((W / 2, H / 2), ang, scale)
    M[0, 2] += dx
    M[1, 2] += dy
    return cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)


def rgb_split(img, px):
    px = int(round(px))
    if px == 0:
        return img
    out = img.copy()
    out[:, :, 2] = np.roll(img[:, :, 2], px, axis=1)
    out[:, :, 0] = np.roll(img[:, :, 0], -px, axis=1)
    return out


def flash(img, a, col=(255, 255, 255)):
    if a <= 0.01:
        return img
    c = np.empty_like(img)
    c[:] = col
    return cv2.addWeighted(img, 1 - a, c, a, 0)


def glitch(img, amt, rng):
    H, W = img.shape[:2]
    out = img.copy()
    for _ in range(int(4 + 10 * amt)):
        y = rng.integers(0, H)
        h = int(rng.integers(H // 80, H // 10))
        band = np.roll(img[y:y + h], int(rng.normal(0, W * 0.12 * amt)), axis=1)
        if rng.random() < 0.4:
            band = band[:, :, rng.permutation(3)]
        out[y:y + h] = band
    return rgb_split(out, W * 0.012 * amt * (1 if rng.random() < 0.5 else -1))


def zoom_blur(img, k):
    acc = img.astype(np.float32)
    for i in range(1, 5):
        acc += warp(img, 1 + k * i / 4).astype(np.float32)
    return (acc / 5).astype(np.uint8)


def hblur(img, k):
    k = max(1, int(k))
    return cv2.blur(img, (k, 1)) if k > 1 else img


def kaleido(img):
    W = img.shape[1]
    out = img.copy()
    out[:, W // 2:] = img[:, :W - W // 2][:, ::-1]
    return out


class Look:
    """The grade (a curve and a tint in the shadows), the vignette and the grain for one frame size."""

    def __init__(self, W: int, H: int, p: dict, palette: dict):
        tint = np.array(palette.get("tint", [30, 10, 0]), np.float32)
        s = float(p["grade"])
        x = np.arange(256) / 255.0
        curve = np.clip((x - 0.04) / 0.92, 0, 1)
        curve = curve * curve * (3 - 2 * curve) * 0.55 + curve * 0.45
        curve = x + (curve - x) * s
        self.lut = np.stack([np.clip(curve * 255 + tint[c] * s * (1 - curve) ** 3, 0, 255) for c in range(3)], axis=1).astype(np.uint8)
        yy, xx = np.mgrid[0:H, 0:W]
        rr = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        self.vig = np.clip(1.08 - 0.42 * float(p["vignette"]) * rr ** 2.2, 0.35, 1.0).astype(np.float32)[..., None]
        rng = np.random.default_rng(7)
        self.grain = [cv2.resize(rng.normal(0, float(p["grain"]), (H // 2, W // 2)).astype(np.float32), (W, H))[..., None] for _ in range(6)]

    def __call__(self, img, i):
        img = cv2.LUT(img, self.lut.reshape(256, 1, 3))
        return np.clip(img.astype(np.float32) * self.vig + self.grain[i % 6], 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- text
def _font_file(kind: str) -> Optional[str]:
    """Impact (titles) / Bahnschrift (HUD) where Windows has them, else a .ttf of app/static/fonts, else None (Pillow's own)."""
    win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    f = win / ("impact.ttf" if kind == "title" else "bahnschrift.ttf")
    if f.exists():
        return str(f)
    own = sorted(FONT_DIR.glob("*.ttf")) if FONT_DIR.is_dir() else []
    if own:
        return str(own[0])
    return None


@lru_cache(maxsize=32)
def _font(kind: str, size: int):
    f = _font_file(kind)
    if f:
        return ImageFont.truetype(f, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:   # Pillow before 10.1: one size only
        return ImageFont.load_default()


@lru_cache(maxsize=128)
def word_mask(text: str, size: int, W: int):
    f = _font("title", size)
    l, t, r_, b = f.getbbox(text)
    im = Image.new("L", (max(1, r_ - l + 40), max(1, b - t + 40)), 0)
    ImageDraw.Draw(im).text((20 - l, 20 - t), text, font=f, fill=255)
    m = np.asarray(im, dtype=np.float32) / 255.0
    if m.shape[1] > W * 0.92:
        k = W * 0.92 / m.shape[1]
        m = cv2.resize(m, None, fx=k, fy=k)
    return m


@lru_cache(maxsize=16)
def hud_mask(text: str, size: int):
    f = _font("hud", size)
    l, t, r_, b = f.getbbox(text)
    im = Image.new("L", (max(1, r_ - l + 8), max(1, b - t + 8)), 0)
    ImageDraw.Draw(im).text((4 - l, 4 - t), text, font=f, fill=255)
    return np.asarray(im, dtype=np.float32) / 255.0


def paste(img, mask, cx, cy, col, alpha=1.0, scale=1.0):
    H, W = img.shape[:2]
    if scale != 1.0:
        mask = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
    h, w = mask.shape
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if xa >= xb or ya >= yb:
        return
    m = mask[ya - y0:yb - y0, xa - x0:xb - x0, None] * alpha
    reg = img[ya:yb, xa:xb].astype(np.float32)
    img[ya:yb, xa:xb] = (reg * (1 - m) + np.array(col, np.float32) * m).astype(np.uint8)


def draw_text(img, txt, t, ta, tb, rng, big, cy, col_a, col_b):
    H, W = img.shape[:2]
    lt = t - ta
    size = int((280 if big else 150) * W / 1080) if len(txt) <= 8 else int((200 if big else 120) * W / 1080)
    m = word_mask(txt, max(8, size), W)
    sc = 1.0 + (0.28 if big else 0.12) * math.exp(-lt / 0.05)
    sc = min(sc, max(1.0, W * 0.98 / max(1, m.shape[1])))   # the pop never pushes a long word past the frame's edges
    fade = 1.0 if t < tb - 0.06 else max(0.0, (tb - t) / 0.06)
    if big and rng.random() < 0.08:
        return
    cx = W / 2 + rng.normal(0, W * 0.003)
    off = W * (0.010 if big else 0.005) * (1 + 2 * math.exp(-lt / 0.08))
    paste(img, m, cx - off, cy, col_a, 0.85 * fade, sc)
    paste(img, m, cx + off, cy, col_b, 0.85 * fade, sc)
    paste(img, m, cx, cy, (255, 255, 255), fade, sc)


# ---------------------------------------------------------------- one frame
def switch_frame(t0: float, fps: int) -> int:
    """The first frame that shows a segment starting at t0 seconds (the epsilon keeps a t0 that is a whole frame on its frame)."""
    return math.ceil(t0 * fps - 1e-9)


def frame_segments(pl: Plan) -> list[int]:
    """The segment of every frame (the edit is sorted by time)."""
    out, k = [], 0
    for i in range(pl.n_frames):
        while k + 1 < len(pl.edl) and i >= switch_frame(pl.edl[k + 1]["t0"], pl.fps):   # the same frame Plan.cuts() reports
            k += 1
        out.append(k)
    return out


class Frames:
    def __init__(self, pl: Plan, shots: Shots, kick: np.ndarray, snare: np.ndarray, seg_of: list[int]):
        self.pl, self.shots, self.kick, self.snare, self.seg_of = pl, shots, kick, snare, seg_of
        pal = pl.palette
        self.col_a = tuple(pal.get("a", [255, 220, 120]))
        self.col_b = tuple(pal.get("b", [255, 255, 255]))
        self.look = Look(pl.W, pl.H, pl.p, pal)

    @staticmethod
    def env(arr, t):
        i = int(t * KEY_FPS)
        return float(arr[i]) if 0 <= i < len(arr) else 0.0

    def render(self, i: int) -> np.ndarray:
        pl, g, p = self.pl, self.pl.grid, self.pl.p
        W, H = pl.W, pl.H
        B, DUR, DROP, RISER, OUTRO = g.beat, g.dur, g.drop, g.riser, g.outro
        edl = pl.edl
        t = i / pl.fps
        rng = np.random.default_rng(1000 + i)
        k = self.seg_of[i]
        s = edl[k]
        lt = t - s["t0"]
        img = self.shots.frame(s["title"], src_time(pl, s, t))
        fx, tr = s["fx"], s["tr"]
        section = pl.section(t)
        ke, se = self.env(self.kick, t), self.env(self.snare, t)
        scale, dx, dy, ang = 1.0, 0.0, 0.0, 0.0
        if section in ("build", "drop"):
            scale += (p["zoom_build"] if section == "build" else p["zoom_drop"]) * ke
            amp = (p["shake_build"] if section == "build" else p["shake_drop"]) * W * ke
            dx, dy = rng.normal(0, amp), rng.normal(0, amp)
        if "riser" in fx:
            u = (t - RISER) / (DROP - RISER)
            scale += 0.25 * u ** 1.5
            amp = W * 0.012 * u ** 2
            dx, dy, ang = rng.normal(0, amp), rng.normal(0, amp), rng.normal(0, 1.2 * u ** 2)
        if "outro" in fx:
            scale += 0.12 * lt / (s["t1"] - s["t0"])
        if tr == "impact" and lt < 0.25:
            e = math.exp(-lt / 0.06)
            scale += 0.18 * e
            dx += rng.normal(0, W * 0.03 * e)
            dy += rng.normal(0, W * 0.03 * e)
            ang += rng.normal(0, 2.5 * e)
        img = warp(img, scale, dx, dy, ang)
        if "kaleido" in fx and s["title"] not in pl.pool.hero:   # a mirrored face looks wrong
            img = kaleido(img)
        ft = lt * KEY_FPS
        if tr == "glitch" and ft < 5:
            img = glitch(img, 1.0 - ft / 6, rng)
        elif tr == "flash" and ft < 8:
            img = flash(img, 0.85 * math.exp(-ft / 2.2))
        elif tr == "impact" and ft < 14:
            img = flash(img, math.exp(-ft / 3.0))
        elif tr == "zoomblur" and ft < 7:
            img = zoom_blur(img, 0.22 * (1 - ft / 7))
        elif tr == "whip" and ft < 6:
            u = 1 - ft / 6
            img = hblur(warp(img, 1.0, W * 0.35 * u ** 2), W * 0.18 * u)
        if k + 1 < len(edl) and edl[k + 1]["tr"] == "whip":
            left = (s["t1"] - t) * KEY_FPS
            if left < 5:
                u = 1 - left / 5
                img = hblur(warp(img, 1.0, -W * 0.35 * u ** 2), W * 0.18 * u)
        if "strobe" in fx:
            lvl = max(0.3, ke ** 1.3)
            img = cv2.convertScaleAbs(img, alpha=lvl)
            if ke > 0.7:
                img = rgb_split(img, W * 0.01 * ke)
        if section in ("build", "drop") and se > 0.1:
            img = rgb_split(img, W * (p["rgb_build"] if section == "build" else p["rgb_drop"]) * se)
        if p["invert"] and section == "drop" and se > 0.85 and (t - DROP) // (4 * B) % 4 == 3:
            img = 255 - img
        if "riser" in fx:
            u = (t - RISER) / (DROP - RISER)
            img = rgb_split(img, W * 0.02 * u ** 2)
            if t > DROP - 0.12:
                img = flash(img, min(1, (t - (DROP - 0.12)) / 0.12))
        if "gap" in fx and DROP - B / 2 < t < DROP - 0.12:
            img = cv2.convertScaleAbs(img, alpha=0.12)
            if rng.random() < 0.5:
                img = glitch(img, 0.6, rng)
        if "stutter" in fx:
            ch = B / 4 if lt < B / 2 else B / 8
            if (lt % ch) * KEY_FPS < 2:
                img = glitch(img, 0.7, rng)
        if "outro" in fx:
            ts = DUR - 2 * B
            gray = cv2.cvtColor(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
            d = min(1.0, lt / (s["t1"] - s["t0"]) * 1.4)
            img = cv2.addWeighted(img, 1 - 0.6 * d, gray, 0.6 * d, 0)
            if t > ts and p["tape_stop"]:
                u = (t - ts) / (2 * B)
                sq = cv2.resize(img, (W, max(2, int(H * (1 - 0.18 * u * u)))))
                img = np.zeros_like(img)
                y0 = (H - sq.shape[0]) // 2
                img[y0:y0 + sq.shape[0]] = sq
                img = rgb_split(img, W * 0.02 * u)
                if rng.random() < 0.3 * u:
                    img = glitch(img, u, rng)
                img = cv2.convertScaleAbs(img, alpha=max(0.0, 1 - u ** 1.6))
        img = self.look(img, i)
        # captions: the title over the intro bar, then the sung words
        intro_end = g.t(-g.need_before + 4)
        title = pl.cfg.get("title")
        if t < intro_end and title and p["captions"]:
            draw_text(img, str(title).upper(), t, 0.0, intro_end, rng, True, H * 0.40, self.col_a, self.col_b)
        elif t < DUR - 2 * B:
            for gr in pl.groups:
                if gr[0] <= t < gr[1] and gr[0] >= intro_end - 0.05:
                    draw_text(img, gr[2], t, gr[0], gr[1], rng, t >= DROP - 0.05, H * 0.66, self.col_a, self.col_b)
        if p["hud"] and 0.05 < t < DUR - 2 * B:
            hs = max(8, int(30 * W / 1080))
            paste(img, hud_mask(f"{pl.cfg.get('hud') or 'REMIQORA'} // {pl.bpm_show} BPM", hs), W * 0.22, H * 0.075, (255, 255, 255), 0.75)
            bar = int(t // (4 * B)) + 1
            nb = int(round(DUR / (4 * B)))
            paste(img, hud_mask(f"BAR {bar:02d}/{nb:02d}", hs), W * 0.8, H * 0.075, (255, 255, 255), 0.75)
            if ke > 0.5:
                cv2.circle(img, (int(W * 0.8 + 95 * W / 1080), int(H * 0.075)), max(3, int(9 * W / 1080)), self.col_a, -1)
        return img


# ---------------------------------------------------------------- the sound
def decode_piece(path: str, start: float, seconds: float) -> np.ndarray:
    """The song from `start` for `seconds`, stereo float32 at 44.1 kHz: (2, samples). Before the song's start - silence."""
    n = int(round(seconds * SR))
    pre = int(round(max(0.0, -start) * SR))
    r = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(0.0, start):.4f}", "-t", f"{seconds + 0.1:.3f}", "-i", str(path),
                        "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg could not read the song: " + r.stderr.decode(errors="replace")[-300:])
    a = np.frombuffer(r.stdout, np.float32).reshape(-1, 2).T
    a = np.pad(a, ((0, 0), (pre, 0)))
    a = a[:, :n] if a.shape[1] >= n else np.pad(a, ((0, 0), (0, n - a.shape[1])))
    return a.astype(np.float32).copy()


def _riser_noise(n: int, rng) -> np.ndarray:
    """Noise through a rising band-pass (600 Hz -> 12 kHz, an octave wide), made block by block in the spectrum:
    2048-sample Hann windows at a hop of 1024, Butterworth-shaped edges - the scipy-free version of edit2's sosfilt loop."""
    nz = rng.normal(0, 1, n)
    blk, hop = 2048, 1024
    win = np.hanning(blk)
    f = np.fft.rfftfreq(blk, 1 / SR)
    out = np.zeros(n + blk)
    for b0 in range(0, n, hop):
        u = b0 / max(1, n - 1)
        fc = 600 * (12000 / 600) ** u
        lo, hi = fc * 0.7, min(fc * 1.4, SR / 2 - 100)
        gain = (f > 400) / np.sqrt(1 + (lo / np.maximum(f, 1e-9)) ** 4) / np.sqrt(1 + (f / hi) ** 4)
        seg = np.zeros(blk)
        part = nz[b0:b0 + blk]
        seg[:len(part)] = part
        out[b0:b0 + blk] += np.fft.irfft(np.fft.rfft(seg * win) * gain, blk) * win
    return out[:n]


def soundtrack(pl: Plan, piece: np.ndarray) -> np.ndarray:
    """The piece's sound as the edit has it (stereo (2, n), before the loudness): the song, a riser, the gap, the drop's
    boom and crash, the tape stop, a soft limiter."""
    g, p, B = pl.grid, pl.p, pl.grid.beat
    n = int(round(g.dur * SR))
    a = piece[:, :n].copy()
    a[:, :int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))
    rng = np.random.default_rng(3)
    r0, r1 = int(g.riser * SR), int((g.drop - B / 2) * SR)
    if p["riser"] and r1 > r0:
        u = np.linspace(0, 1, r1 - r0)
        out = _riser_noise(r1 - r0, rng)
        out *= (u ** 2) * 0.35 / (np.abs(out).max() + 1e-9)
        a[:, r0:r1] += out
        g0, g1 = int((g.drop - B / 2) * SR), int(g.drop * SR)    # the gap: the song ducks for the last half beat
        a[:, g0:g1] *= np.linspace(1, 0.08, g1 - g0) ** 0.5
    if p["impact_sound"]:
        i0 = int(g.drop * SR)
        L = int(1.2 * SR)
        tt = np.arange(L) / SR
        boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-tt / 0.06)) / SR) * np.exp(-tt / 0.45) * 0.6
        crash = rng.normal(0, 1, L) * np.exp(-tt / 0.25) * 0.18
        c = np.fft.irfft(np.fft.rfft(crash) * (1 / np.sqrt(1 + (3000 / np.maximum(np.fft.rfftfreq(L, 1 / SR), 1e-9)) ** 4)), L)   # high-pass 3 kHz
        seg_ = (boom + c)[:n - i0]
        a[:, i0:i0 + len(seg_)] += seg_
    if p["tape_stop"]:                                           # over the last 2 beats
        s0 = int((g.dur - 2 * B) * SR)
        m = n - s0
        uu = np.arange(m) / m
        pos = s0 + (2 * B * SR) * (uu - uu * uu / 2)
        for ch in range(2):
            a[ch, s0:] = np.interp(pos, np.arange(n), a[ch]) * (1 - uu) ** 0.7
    return np.tanh(a * 1.1) / np.tanh(1.1)


def _loudnorm_pass1(raw: bytes, lufs: float) -> Optional[dict]:
    """ffmpeg's loudnorm analysis of raw stereo f32 samples: its measurements, or None for silence."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        "-af", f"loudnorm=I={lufs}:TP=-1.0:LRA=20:print_format=json", "-f", "null", "-"],
                       input=raw, capture_output=True, creationflags=NO_WINDOW)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr.decode(errors="replace"), re.S)
    meas = json.loads(m.group(0)) if m else None
    return None if not meas or meas["input_i"] in ("-inf", "inf") else meas


def _to_wav(raw: bytes, af: str, out_wav: Path) -> None:
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-af", af, "-ar", str(SR),
                        "-c:a", "pcm_s24le", "-y", str(out_wav)], input=raw, capture_output=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg loudnorm failed: " + r.stderr.decode(errors="replace")[-300:])


def master(a: np.ndarray, lufs: float, out_wav: Path) -> dict:
    """The loudness: ffmpeg's two-pass loudnorm - the first pass measures, the second applies the gain linearly to `lufs`
    (true peak -1 dB) -> out_wav (24 bit). A mix too peaky for that (the gain would pass the true-peak ceiling: loudnorm
    stops short) is pushed into edit2's soft clipper in steps, each step measured again, until it is within 0.5 LU.
    -> {"in": the mix's measured LUFS, "out": the result's, "target": lufs}."""
    raw = a.T.astype("<f4").tobytes()
    meas = _loudnorm_pass1(raw, lufs)
    if meas is None:   # silence: nothing to measure
        _to_wav(raw, "volume=0dB", out_wav)
        return {"in": None, "out": None, "target": lufs}
    first = float(meas["input_i"])
    af = (f"loudnorm=I={lufs}:TP=-1.0:LRA=20:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:measured_LRA={meas['input_lra']}:"
          f"measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")
    _to_wav(raw, af, out_wav)
    got = _wav_loudness(out_wav, lufs)
    x = a.astype(np.float64)
    gain = lufs - first
    for _ in range(5):
        if got is None or abs(got - lufs) <= 0.5:
            break
        gain += lufs - got
        y = np.tanh(x * 10 ** (gain / 20) * 1.2) / 1.2
        y *= 10 ** (-1.0 / 20) / max(1e-9, np.abs(y).max())
        raw2 = y.T.astype("<f4").tobytes()
        _to_wav(raw2, "volume=0dB", out_wav)
        got = _wav_loudness(out_wav, lufs)
    return {"in": round(first, 2), "out": None if got is None else round(got, 2), "target": lufs}


def _wav_loudness(path: Path, lufs: float) -> Optional[float]:
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-af", f"loudnorm=I={lufs}:TP=-1.0:LRA=20:print_format=json", "-f", "null", "-"],
                       capture_output=True, creationflags=NO_WINDOW)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr.decode(errors="replace"), re.S)
    try:
        v = float(json.loads(m.group(0))["input_i"]) if m else None
    except ValueError:
        return None
    return v if v is not None and math.isfinite(v) else None


# ---------------------------------------------------------------- the render
def _noop(*a, **k):
    pass


def render(cfg: dict, progress: Callable = _noop) -> dict:
    """cfg -> the mp4 at cfg["out"] (and its .json: cuts as frame numbers, the edit decision list, the grid). `progress`
    (stage, done, total) is called as it goes. -> {"out", "seconds", "frames", "fps", "cuts", "bpm", "drop"}."""
    out = Path(cfg["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    progress("plan", 0, 1)
    pl = plan(cfg)
    g = pl.grid
    progress("plan", 1, 1)
    piece = decode_piece(cfg["song"], g.t0, g.dur + 1.0)
    kick, snare = band_envelopes(piece.mean(0))
    progress("audio", 0, 1)
    wav = out.with_suffix(".tmp.wav")   # temp names: a failed or cancelled render leaves nothing under the real names
    tmp = out.with_name(out.stem + ".tmp.mp4")
    try:
        lufs = float(cfg.get("loudness") if cfg.get("loudness") is not None else DEFAULTS["loudness"])
        levels = master(soundtrack(pl, piece), lufs, wav)
        progress("audio", 1, 1)
        seg_of = frame_segments(pl)   # first: the shots keep only the frames the edit shows
        shots = Shots(pl, seg_of, progress)
        fr = Frames(pl, shots, kick, snare, seg_of)
    except BaseException:   # the temp files of a failed or cancelled start do not stay
        wav.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
        raise
    n = pl.n_frames
    pv = bool(cfg.get("preview"))
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{pl.W}x{pl.H}", "-r", str(pl.fps), "-i", "-",
           "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", str(cfg.get("preset_x264") or ("veryfast" if pv else "slow")),
           "-crf", "24" if pv else "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", "-shortest", "-movflags", "+faststart", str(tmp)]
    log = tempfile.TemporaryFile()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log, creationflags=NO_WINDOW)
    ok = False
    broken: Optional[OSError] = None
    try:
        try:
            for i in range(n):
                proc.stdin.write(fr.render(i).tobytes())
                if i % 30 == 0:
                    progress("frames", i, n)
            proc.stdin.close()
            code = proc.wait()
        except OSError as e:   # ffmpeg died (BrokenPipeError, EINVAL on Windows...): its own message below
            code = proc.wait() or 1
            broken = e
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        if code != 0:
            log.seek(0)
            msg = log.read().decode(errors="replace")[-400:].strip()
            raise RuntimeError("ffmpeg could not encode: " + (msg or str(broken or f"exit code {code}")))
        progress("frames", n, n)
        cuts = pl.cuts()
        meta = {"cuts": cuts, "fps": pl.fps, "bpm": round(60 / g.beat, 3), "drop": round(g.drop, 4), "t0": round(g.t0, 4), "dur": round(g.dur, 4),
                "loudness": levels, "version": VERSION,
                "edl": [{"t0": round(s["t0"], 4), "t1": round(s["t1"], 4), "title": s["title"], "tr": s["tr"], "fx": sorted(s["fx"])} for s in pl.edl]}
        # the cuts file goes first, the video last: a crash in between leaves cuts without a video (not ready), never a video without cuts
        meta_path = out.with_suffix(".json")
        meta_tmp = meta_path.with_name(meta_path.name + ".tmp")
        meta_tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        os.replace(meta_tmp, meta_path)
        os.replace(tmp, out)
        ok = True
    finally:
        log.close()
        wav.unlink(missing_ok=True)
        if not ok:
            tmp.unlink(missing_ok=True)
    return {"out": str(out), "frames": n, "fps": pl.fps, "cuts": cuts, "bpm": meta["bpm"], "drop": meta["drop"], "seconds": round(g.dur, 3)}


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(argv) < 2:
        print("usage: python -m app.beatedit cfg.json", file=sys.stderr)
        return 2

    def say(stage, done, total):
        print(json.dumps({"stage": stage, "done": done, "total": total}), flush=True)
    try:
        cfg = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        res = render(cfg, say)
    except Exception as e:  # noqa: BLE001 - one JSON line for the parent process
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps({"stage": "done", **res}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
