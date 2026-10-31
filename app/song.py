"""Phase 11: a song for a clip - its beat grid and parts, its words with their times.

The analysis is remiqora-video's analysis/audio.py (measured there on ACE-Step / YuE songs and «Take Me Higher»):
the tempo without a hint (autocorrelation, then a comb fit), the beat phase on the real kick attacks, the downbeat
from the kick and the loudness changes, bars, per-bar energy, breaks and drops, and the parts cut at them (intro,
groove, break, drop, outro). Assumes 4/4 and one steady tempo. numpy + ffmpeg, ~1 s for a 3-minute song.

The words: tools/lyrics/lyrics_worker.py (Demucs separates the vocals, faster-whisper writes the words with their
times) as its own process in its own environment - torch never loads into the backend and the GPU memory is back
when it exits; a GPU job in the queue (jobs.py), the video model freed first. The user's own text is aligned on the
recognised words (timed_lines): their line breaks and fixed words keep real times.

A song lives in data/songs/<id>/ (id: the file's sha1), once for every clip made from it: the file, analysis.json,
lyrics/ (lyrics.json, vocals.wav - the lips check of phase 11 reads it), text.txt (the user's words).
"""
from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import config
from .engine.comfy import EngineError
from . import i18n

SONGS = config.DATA_DIR / "songs"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------- the song's files ----------
def folder(sid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", sid or ""):
        raise EngineError(i18n.L("Нет такой песни", "No such song"))
    return SONGS / sid


def file_of(sid: str) -> Path:
    f = next((p for p in folder(sid).glob("song.*")), None)
    if not f:
        raise EngineError(i18n.L("Нет такой песни", "No such song"))
    return f


def store(src: Path, name: str) -> str:
    """A song file into data/songs/<sha1>/ (the same file twice is one song) with its analysis. -> its id."""
    h = hashlib.sha1()
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    sid = h.hexdigest()[:12]
    d = SONGS / sid
    d.mkdir(parents=True, exist_ok=True)
    dst = d / f"song{src.suffix.lower()}"
    if not dst.exists():
        shutil.copyfile(src, dst)
    meta = d / "meta.json"
    if not meta.exists():
        meta.write_text(json.dumps({"name": name}, ensure_ascii=False), encoding="utf-8")
    if not (d / "analysis.json").exists():
        a = analyze(dst)
        if len(a.bars) < 2 or not a.sections:
            shutil.rmtree(d, ignore_errors=True)
            raise EngineError(i18n.L("В песне не нашлись такты: слишком короткая или без ритма", "No bars found in the song: too short or without a beat"))
        (d / "analysis.json").write_text(json.dumps(a.to_dict()), encoding="utf-8")
    return sid


def analysis(sid: str) -> "Analysis":
    f = folder(sid) / "analysis.json"
    if not f.exists():
        f.write_text(json.dumps(analyze(file_of(sid)).to_dict()), encoding="utf-8")
    return Analysis.from_dict(json.loads(f.read_text(encoding="utf-8")))


def name_of(sid: str) -> str:
    try:
        return json.loads((folder(sid) / "meta.json").read_text(encoding="utf-8")).get("name") or i18n.L("Песня", "Song")
    except (OSError, ValueError):
        return i18n.L("Песня", "Song")


def recognised(sid: str) -> Optional[dict]:
    try:
        return json.loads((folder(sid) / "lyrics" / "lyrics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def text_of(sid: str) -> str:
    """The words as the user keeps them (text.txt), else as recognised, a line per sung line."""
    f = folder(sid) / "text.txt"
    if f.exists():
        return f.read_text(encoding="utf-8")
    rec = recognised(sid)
    return "\n".join(line["text"] for line in (rec or {}).get("lines", []))


def set_text(sid: str, text: str) -> None:
    """The user's words; empty - back to the recognised ones."""
    f = folder(sid) / "text.txt"
    if text.strip():
        f.write_text(text.strip() + "\n", encoding="utf-8")
    else:
        f.unlink(missing_ok=True)


def language_of(sid: str) -> Optional[str]:
    """What to tell Whisper: "ru" when the user's own words are Cyrillic; otherwise None - the lyrics tool detects the
    language on the loudest 30 s of the vocals (a forced "ru" turned English songs into a Russian transliteration)."""
    f = folder(sid) / "text.txt"
    text = f.read_text(encoding="utf-8") if f.exists() else ""
    cyr, lat = len(re.findall(r"[А-Яа-яЁё]", text)), len(re.findall(r"[A-Za-z]", text))
    return "ru" if cyr > lat else None


def lines(sid: str) -> list[dict]:
    """The timed lines [{start, end, text}] in the song's time: the user's text aligned on the recognised words, or
    the recognised lines; [] before the words are recognised (or when the text is not this song's)."""
    rec = recognised(sid)
    if not rec:
        return []
    f = folder(sid) / "text.txt"
    if f.exists() and (mine := timed_lines(rec, f.read_text(encoding="utf-8"))):
        return mine
    # no text of the user's, or one that is not this song's (under a fifth of its words heard): the recognised lines
    return [{"start": l["start"], "end": l["end"], "text": l["text"]} for l in rec.get("lines", [])]


def vocals(sid: str) -> Optional[Path]:
    p = folder(sid) / "lyrics" / "vocals.wav"
    return p if p.exists() else None


def no_vocals(sid: str) -> Optional[Path]:
    """The song without its voice (lyrics/no_vocals.wav): the song minus Demucs' vocals, made on the first call. A
    clip's scene where nobody sings (a performance, an insert) is shot to it, so the model doesn't make every face
    sing what it hears; the video's sound is the song itself. None until the words were
    recognised (no vocals yet)."""
    v = vocals(sid)
    if v is None:
        return None
    p = folder(sid) / "lyrics" / "no_vocals.wav"
    if p.exists() and p.stat().st_mtime >= v.stat().st_mtime:
        return p
    tmp = p.with_suffix(".part.wav")
    r = subprocess.run([config.FFMPEG, "-y", "-v", "error", "-i", str(file_of(sid)), "-i", str(v), "-filter_complex",
                        "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[s];"
                        "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=-1[v];"
                        "[s][v]amix=inputs=2:normalize=0:duration=first[m]", "-map", "[m]", "-c:a", "pcm_s16le", str(tmp)],
                       capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode or not tmp.exists():
        return None
    tmp.replace(p)
    return p


def public(sid: str) -> dict:
    """The song for the page: its parts, bars, the chorus and the words with their times, the loudness for the wave."""
    a = analysis(sid)
    ls = lines(sid)
    rec = recognised(sid)
    from .edit import peaks
    return {"id": sid, "name": name_of(sid), "duration": a.duration, "bpm": round(a.bpm, 1), "bar_s": round(a.bar_s, 4),
            "bars": a.bars, "sections": [asdict(s) for s in a.sections], "chorus": chorus_spans(ls),
            "lines": ls, "text": text_of(sid), "recognised": bool(rec), "language": (rec or {}).get("language"),
            "peaks": peaks(file_of(sid))}


# ---------- the beat grid and the parts (remiqora-video analysis/audio.py) ----------
SR = 22050
N_FFT = 2048
HOP = 256
ENV_FPS = SR / HOP  # onset-envelope frames per second (~86)
# Bar-mean bass level (0..1): a break starts below BREAK_LOW and lasts until the low end is clearly back (BREAK_EXIT).
# The gap keeps a lone hit or a half-level build bass from splitting one intro/break into fragments.
BREAK_LOW = 0.3
BREAK_EXIT = 0.55
MIN_SECTION_BARS = 2


@dataclass
class Section:
    kind: str       # intro | drop | groove | break | outro
    start: float    # seconds
    end: float
    bar0: int       # index into Analysis.bars of the first bar line at/after start
    bar1: int       # ... and at/after end
    energy: float   # 0..1, mean over its bars


@dataclass
class Analysis:
    duration: float
    bpm: float
    beat_s: float
    bar_s: float
    downbeat: float                 # first bar line (>= 0)
    beats: list
    bars: list                      # bar line times
    bar_energy: list                # 0..1 per bar (bass-weighted)
    bar_rms: list                   # 0..1 per bar (broadband loudness)
    sections: list

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Analysis":
        d = {k: d[k] for k in cls.__dataclass_fields__}
        d["sections"] = [Section(**s) for s in d["sections"]]
        return cls(**d)

    def section_at(self, t: float) -> Section:
        for s in self.sections:
            if s.start <= t < s.end:
                return s
        return self.sections[-1]

    def bar_index_at(self, t: float) -> int:
        """Index of the first bar line at or after t."""
        return int(np.searchsorted(np.asarray(self.bars), t - 1e-6))


def load_audio(path: Path, sr: int) -> np.ndarray:
    """Any audio file -> mono float32 samples at `sr` (ffmpeg)."""
    r = subprocess.run([config.FFMPEG, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                       capture_output=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise EngineError(i18n.L("Не читается как звук: ", "Can't be read as sound: ") + r.stderr.decode(errors="replace")[-300:])
    return np.frombuffer(r.stdout, np.float32)


def _spectrogram(x: np.ndarray) -> np.ndarray:
    """|STFT|, frames centred on t = i*HOP/SR (padded like librosa's center=True)."""
    x = np.pad(x, (N_FFT // 2, N_FFT // 2))
    n = 1 + (len(x) - N_FFT) // HOP
    frames = np.lib.stride_tricks.as_strided(x, (n, N_FFT), (x.strides[0] * HOP, x.strides[0]))
    win = np.hanning(N_FFT).astype(np.float32)
    out = np.empty((n, N_FFT // 2 + 1), np.float32)
    for i in range(0, n, 4096):
        out[i:i + 4096] = np.abs(np.fft.rfft(frames[i:i + 4096] * win, axis=1))
    return out


def _moving_average(x: np.ndarray, width: int) -> np.ndarray:
    c = np.cumsum(np.concatenate(([0.0], x)))
    y = (c[width:] - c[:-width]) / width
    return np.concatenate((np.full(width // 2, y[0]), y, np.full(width - 1 - width // 2, y[-1])))


def _estimate_bpm(onset: np.ndarray, lo: float = 60.0, hi: float = 200.0) -> float:
    """Tempo from the onset envelope's autocorrelation, weighted toward 120 BPM (log-normal, one octave wide) to
    settle half/double-tempo ambiguity."""
    o = onset - onset.mean()
    n = len(o)
    spec = np.fft.rfft(o, 2 * n)
    acf = np.fft.irfft(spec * np.conj(spec))[:n]
    acf /= acf[0] + 1e-12
    bpms = np.arange(lo, hi, 0.25)
    vals = np.interp(60.0 * ENV_FPS / bpms, np.arange(n), acf)
    prior = np.exp(-0.5 * np.log2(bpms / 120.0) ** 2)
    return float(bpms[np.argmax(vals * prior)])


def _comb_fit(onset: np.ndarray, bpms: np.ndarray) -> tuple[float, float, float]:
    """Best (score, bpm, phase_frames): the beat grid that lands on the most onset energy, each beat allowed
    +-1 envelope frame of slack."""
    o3 = np.maximum(onset, np.maximum(np.roll(onset, 1), np.roll(onset, -1)))
    best = (-1.0, float(bpms[0]), 0.0)
    for bpm in bpms:
        period = 60.0 * ENV_FPS / bpm
        n_beats = int((len(onset) - 2) / period)
        if n_beats < 8:
            continue
        phases = np.arange(0.0, period, 0.25)
        idx = np.rint(phases[:, None] + np.arange(n_beats)[None, :] * period).astype(int)
        idx = np.clip(idx, 0, len(onset) - 1)
        scores = o3[idx].mean(axis=1)
        j = int(np.argmax(scores))
        if scores[j] > best[0]:
            best = (float(scores[j]), float(bpm), float(phases[j]))
    return best


def _refine_phase_on_attacks(x: np.ndarray, first_beat: float, beat_s: float) -> float:
    """Shift the grid onto the real kick attacks: crude 200 Hz low-pass, 4 ms envelope, per beat the first crossing
    of 40 % of the local peak; median offset."""
    env = np.abs(_moving_average(x.astype(np.float64), max(2, SR // 200)))
    env = _moving_average(env, max(2, int(0.004 * SR)))
    gate = 0.35 * np.percentile(env, 95)
    offsets = []
    t = first_beat
    while t + 0.2 < len(x) / SR:
        a0, a1 = max(0, int((t - 0.07) * SR)), int((t + 0.20) * SR)
        seg = env[a0:a1]
        if len(seg) and seg.max() >= gate:
            offsets.append((a0 + int(np.argmax(seg > 0.4 * seg.max()))) / SR - t)
        t += beat_s
    if len(offsets) < 8:
        return first_beat
    return (first_beat + float(np.median(offsets))) % beat_s


def analyze(path: Path, bpm_hint: Optional[float] = None) -> Analysis:
    x = load_audio(path, SR)
    if len(x) < SR * 4:
        raise EngineError(i18n.L("Песня короче 4 секунд", "The song is shorter than 4 seconds"))
    duration = len(x) / SR
    S = _spectrogram(x)
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    t_frames = np.arange(len(S)) / ENV_FPS

    # Onset envelope: positive log-spectral flux over 30 Hz - 5 kHz.
    logmag = np.log1p(30.0 * S[:, (freqs > 30) & (freqs < 5000)])
    onset = np.maximum(np.diff(logmag, axis=0, prepend=logmag[:1]), 0).sum(axis=1)
    onset /= onset.max() + 1e-12
    del logmag

    low_mag = S[:, (freqs >= 30) & (freqs < 150)].sum(axis=1)
    low_flux = np.maximum(np.diff(low_mag, prepend=low_mag[0]), 0)
    low_energy = np.sqrt((S[:, (freqs >= 30) & (freqs < 130)] ** 2).sum(axis=1))
    hi_db = 10 * np.log10((S[:, freqs >= 2400] ** 2).mean(axis=1) + 1e-9)
    rms = np.sqrt((S ** 2).mean(axis=1))

    # Tempo: coarse estimate (or the caller's hint), then a fine comb fit around it.
    center = bpm_hint or _estimate_bpm(onset)
    span = 0.04 if bpm_hint else 0.03
    _, bpm, _ = _comb_fit(onset, np.arange(center * (1 - span), center * (1 + span), 0.02))
    _, bpm, phase = _comb_fit(onset, np.arange(bpm - 0.03, bpm + 0.03, 0.002))
    beat_s = 60.0 / bpm
    first_beat = _refine_phase_on_attacks(x, phase / ENV_FPS, beat_s)
    beats = np.arange(first_beat, duration, beat_s)

    # Downbeat: which of the 4 beat positions carries the most kick onset and the biggest loudness rises.
    def at(signal: np.ndarray, times: np.ndarray) -> np.ndarray:
        i = np.clip(np.rint(times * ENV_FPS).astype(int), 1, len(signal) - 2)
        return np.maximum(signal[i], np.maximum(signal[i - 1], signal[i + 1]))

    beat_rms = np.array([rms[(t_frames >= t) & (t_frames < t + beat_s)].mean() if t + beat_s <= duration else np.nan
                         for t in beats])
    # Rises only: the silent beat right before a drop is a bigger change than the drop itself, but it falls on "four".
    novelty = np.maximum(np.diff(np.log(beat_rms + 1e-6), prepend=np.nan), 0)
    kick = at(low_flux, beats)
    scores = []
    for d in range(4):
        k = np.arange(d, len(beats), 4)
        nov = np.nanmean(novelty[k]) / (np.nanmean(novelty) + 1e-12)
        scores.append(kick[k].mean() / (kick.mean() + 1e-12) + nov)
    downbeat = float(beats[int(np.argmax(scores))])
    bar_s = 4 * beat_s
    downbeat -= np.floor(downbeat / bar_s + 1e-9) * bar_s  # earliest bar line >= 0
    bars = np.arange(downbeat, duration - 0.5 * bar_s, bar_s)

    low_n = low_energy / (np.percentile(low_energy, 95) + 1e-12)
    lo_p, hi_p = np.percentile(hi_db, 8), np.percentile(hi_db, 99.5)
    hi_n = np.clip((hi_db - lo_p) / max(1e-6, hi_p - lo_p), 0, 1)
    rms_n = np.clip(rms / (np.percentile(rms, 99) + 1e-12), 0, 1)

    def bar_mean(signal: np.ndarray) -> np.ndarray:
        return np.array([signal[(t_frames >= b) & (t_frames < b + bar_s)].mean() for b in bars])

    bar_low, bar_hi, bar_rms = bar_mean(low_n), bar_mean(hi_n), bar_mean(rms_n)
    bar_energy = np.clip(0.7 * bar_low + 0.3 * bar_hi, 0, 1)

    # Structure: a break is 2+ bars without the low end that ends with it coming back (the drop).
    breaks = []
    k = 0
    while k < len(bars):
        if bar_low[k] < BREAK_LOW:
            j = k
            while j < len(bars) and bar_low[j] < BREAK_EXIT:
                j += 1
            if j - k >= 2 and j < len(bars):
                breaks.append((k, j))
            k = j
        else:
            k += 1
    return Analysis(
        duration=round(duration, 4), bpm=round(float(bpm), 3), beat_s=float(beat_s), bar_s=float(bar_s),
        downbeat=round(float(downbeat), 4), beats=[round(float(t), 4) for t in beats], bars=[round(float(t), 4) for t in bars],
        bar_energy=[round(float(e), 3) for e in bar_energy], bar_rms=[round(float(e), 3) for e in bar_rms],
        sections=_sections(duration, bars, bar_energy, breaks))


def _sections(duration: float, bars: np.ndarray, energy: np.ndarray, breaks: list[tuple[int, int]]) -> list[Section]:
    """Cut the track at break starts and drops; name the pieces."""
    cuts = sorted({b for a, b in breaks} | {a for a, b in breaks if a > 0})
    edges = [0] + cuts + [len(bars)]
    # A piece under 2 bars (a lone hit before the intro, a one-bar stab) folds into the next one (the last into the previous).
    while len(edges) > 2:
        short = [i for i in range(len(edges) - 1) if edges[i + 1] - edges[i] < MIN_SECTION_BARS]
        if not short:
            break
        i = short[0]
        del edges[i + 1 if i + 1 < len(edges) - 1 else i]
    in_break = {a for a, _ in breaks}
    drops = {b for _, b in breaks}
    out: list[Section] = []
    for i, (b0, b1) in enumerate(zip(edges[:-1], edges[1:])):
        if b1 <= b0:
            continue
        start = 0.0 if i == 0 else float(bars[b0])
        end = duration if b1 >= len(bars) else float(bars[b1])
        e = float(energy[b0:b1].mean())
        kind = "break" if b0 in in_break else "drop" if b0 in drops else "groove"
        out.append(Section(kind=kind, start=round(start, 4), end=round(end, 4), bar0=int(b0), bar1=int(b1), energy=round(e, 3)))
    if out:
        peak = max(s.energy for s in out)
        # A quiet first/last piece is the intro/outro (a break at the very start is an intro with no kick yet).
        if out[0].kind in ("groove", "break") and (out[0].kind == "break" or out[0].energy < 0.6 * peak):
            out[0].kind = "intro"
        if len(out) > 1 and out[-1].kind == "groove" and out[-1].energy < 0.6 * peak:
            out[-1].kind = "outro"
    return out


# ---------- the words (remiqora-video app/lyrics.py) ----------
_NON_WORD = re.compile(r"[^\w]", re.UNICODE)
# below this fraction of matched words the pasted text probably isn't this song at all - no times
MIN_MATCH_FRACTION = 0.2


def _norm(word: str) -> str:
    return _NON_WORD.sub("", word.lower().replace("ё", "е"))


def timed_lines(rec: Optional[dict], text: str) -> list[dict]:
    """The user's text, timed: the recognised words (each already timed) aligned word by word on the user's words
    (difflib, ignoring case, «ё» and punctuation), so their line breaks and fixed words keep real times. A line with
    no matched word gets one by interpolating between its matched neighbours. Too few matches - no times."""
    if not rec or not text.strip():
        return []
    rec_words = [w for line in rec.get("lines", []) for w in line["words"]]
    mine_lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not rec_words or not mine_lines:
        return []
    mine_words = [(li, w) for li, line in enumerate(mine_lines) for w in line.split()]
    rec_norm = [_norm(w["word"]) for w in rec_words]
    # a word that normalises to nothing (pure punctuation) never matches another one that also does
    mine_norm = [_norm(w) or f"\0{i}" for i, (_, w) in enumerate(mine_words)]
    matcher = difflib.SequenceMatcher(None, rec_norm, mine_norm, autojunk=False)
    times: list = [None] * len(mine_words)
    matched = 0
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            times[block.b + k] = (rec_words[block.a + k]["start"], rec_words[block.a + k]["end"])
            matched += 1
    if matched < MIN_MATCH_FRACTION * len(mine_words):
        return []
    song_end = rec_words[-1]["end"]
    i = 0
    while i < len(times):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(times) and times[j] is None:
            j += 1
        prev_end = times[i - 1][1] if i > 0 else 0.0
        next_start = times[j][0] if j < len(times) else song_end
        span = max(next_start - prev_end, 0.01)
        for k in range(i, j):
            times[k] = (prev_end + span * (k - i) / (j - i), prev_end + span * (k - i + 1) / (j - i))
        i = j
    by_line: dict[int, list[int]] = {}
    for idx, (li, _) in enumerate(mine_words):
        by_line.setdefault(li, []).append(idx)
    return [{"start": round(min(times[k][0] for k in idxs), 3), "end": round(max(times[k][1] for k in idxs), 3),
             "text": mine_lines[li]} for li, idxs in by_line.items()]


def lines_in(ls: list[dict], start: float, end: float) -> list[dict]:
    """The lines sung during [start, end): those that overlap it by at least 0.3 s or half their own length."""
    out = []
    for l in ls:
        overlap = min(end, l["end"]) - max(start, l["start"])
        if overlap > 0 and overlap >= min(0.3, 0.5 * (l["end"] - l["start"])):
            out.append(l)
    return out


def chorus_spans(ls: list[dict], gap: float = 2.5) -> list[list[float]]:
    """Where the chorus is: the lines sung more than once (3+ words, compared without case and punctuation),
    neighbours under `gap` s apart joined. The audio parts can't find it on a dense mix, the words can."""
    norm = lambda s: " ".join(re.sub(r"[^\w\s]", " ", s.lower()).split())  # noqa: E731
    counts: dict[str, int] = {}
    for l in ls:
        k = norm(l["text"])
        if len(k.split()) >= 3:
            counts[k] = counts.get(k, 0) + 1
    rep = sorted((l["start"], l["end"]) for l in ls if counts.get(norm(l["text"]), 0) >= 2)
    spans: list[list[float]] = []
    for a, b in rep:
        if spans and a - spans[-1][1] <= gap:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return [[round(a, 3), round(b, 3)] for a, b in spans]


def voice_share(ls: list[dict], start: float, end: float) -> float:
    """How much of [start, end) has a sung line over it (0..1)."""
    spans = sorted((max(start, l["start"]), min(end, l["end"])) for l in ls if min(end, l["end"]) > max(start, l["start"]))
    covered, cur = 0.0, None
    for a, b in spans:
        if cur and a <= cur[1]:
            cur = (cur[0], max(cur[1], b))
        else:
            if cur:
                covered += cur[1] - cur[0]
            cur = (a, b)
    if cur:
        covered += cur[1] - cur[0]
    return covered / max(end - start, 1e-6)


def singing(ls: list[dict], start: float, end: float) -> str:
    """Where in [start, end) the voice is, in words for the writer. Lines alone misled it: one line ending 1.8 s into
    a 10 s shot made it write singing for the whole shot, over the instrumental."""
    spans = [(max(start, l["start"]), min(end, l["end"])) for l in ls if min(end, l["end"]) > max(start, l["start"])]
    length = end - start
    covered = voice_share(ls, start, end) * length
    if covered < 0.3:
        return "none - an instrumental part, nobody sings"
    if covered >= 0.6 * length:
        return "through most of the shot"
    first, last = min(a for a, _ in spans) - start, max(b for _, b in spans) - start
    if last <= 0.5 * length:
        return f"only the first {last:.0f} s of {length:.0f} s, then instrumental"
    if first >= 0.5 * length:
        return f"only from {first:.0f} s of {length:.0f} s on - instrumental before that"
    return f"about {covered:.0f} s of {length:.0f} s, with instrumental gaps"


def lyrics_python() -> Path:
    """The lyrics tool's python: LYRICS_PYTHON when it is there, else the engine's (engine/.venv has Demucs and
    Whisper)."""
    engine = config.COMFY_PYTHON if (config.COMFY_PYTHON.parent.parent / "Lib" / "site-packages" / "demucs").is_dir() else None
    for p in (config.LYRICS_PYTHON, engine):
        if p and p.exists():
            return p
    raise EngineError(i18n.L("Нет окружения для распознавания слов: запустите install.bat (torch, Demucs, Whisper — в engine\\.venv)", "No environment for recognizing words: run install.bat (torch, Demucs, Whisper - in engine\\.venv)"))


async def recognise(sid: str, on_message: Callable[[str], None] = lambda m: None, language: Optional[str] = None) -> dict:
    """Vocals + words of the song into its lyrics/ folder (a GPU job: Demucs + Whisper large-v3, ~25 s for a 3-minute
    song; Whisper's 3 GB are downloaded the first time). -> lyrics.json."""
    out = folder(sid) / "lyrics"
    out.mkdir(exist_ok=True)
    args = [str(file_of(sid).resolve()), str(out.resolve()), "--model", config.LYRICS_MODEL]
    if language:
        args += ["--language", language]
    code, error, tail = await _tool(args, on_message)
    rec = recognised(sid)
    if code != 0 or rec is None:
        raise EngineError(i18n.L("Слова не распознаны: ", "Words not recognized: ") + (error[0] if error else "\n".join(tail[-5:])))
    return rec


async def separate(src: Path, dest: Path, on_message: Callable[[str], None] = lambda m: None) -> None:
    """The voice of a clip or a sound without its music and noise (Demucs, the same tool as the words: a GPU job, ~1 min
    with torch's start) -> dest (wav)."""
    out = dest.parent / f"_{dest.stem}"
    out.mkdir(parents=True, exist_ok=True)
    try:
        code, error, tail = await _tool([str(src.resolve()), str(out.resolve()), "--vocals-only"], on_message)
        if code != 0 or not (out / "vocals.wav").exists():
            raise EngineError(i18n.L("Голос не отделён: ", "Voice not separated: ") + (error[0] if error else "\n".join(tail[-5:])))
        (out / "vocals.wav").replace(dest)
    finally:
        shutil.rmtree(out, ignore_errors=True)


async def _tool(args: list[str], on_message: Callable[[str], None]) -> tuple[int, list[str], list[str]]:
    """tools/lyrics/lyrics_worker.py with these arguments in its own environment: (exit code, errors, the last lines)."""
    py = lyrics_python()
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env.update(FFMPEG=config.FFMPEG, HF_HUB_DISABLE_SYMLINKS_WARNING="1", PYTHONIOENCODING="utf-8")
    # a plain Popen read in a thread, not asyncio's subprocess: under `uvicorn --reload` on Windows the loop is a
    # selector loop, where create_subprocess_exec raises a bare NotImplementedError (the job died with an empty error)
    proc = subprocess.Popen([str(py), "-u", "lyrics_worker.py", *args], cwd=str(config.LYRICS_TOOL_DIR), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    tail: list[str] = []
    error: list[str] = []
    loop = asyncio.get_running_loop()

    def read() -> int:
        assert proc.stdout
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            tail.append(line)
            del tail[:-20]
            try:
                msg = json.loads(line)
            except ValueError:
                continue   # library chatter
            if isinstance(msg, dict) and msg.get("error"):
                error.append(msg["error"])
            elif isinstance(msg, dict) and msg.get("message"):
                loop.call_soon_threadsafe(on_message, msg["message"])
        return proc.wait()
    try:
        code = await asyncio.to_thread(read)
    except asyncio.CancelledError:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
        raise
    return code, error, tail
