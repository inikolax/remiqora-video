"""How alike a scene's voice is to its sample (ID-LoRA, «Сцена по образцу»): WeSpeaker ResNet34 speaker embeddings
(VoxCeleb, Apache-2.0, ONNX, 26 MB in data/models/voice) of the sample and of the scene's sound, their cosine.

The model runs in OpenCV's DNN on the CPU (opencv is here for the lips check already; torch in another environment
is what Smart App Control blocks), its input - Kaldi's 80-bin log-mel fbank, written here in numpy (matches
torchaudio.compliance.kaldi.fbank to 1e-3, checked 2026-10-23). ~0,3 s for a 5 s scene.

Calibrated 2026-10-23 on clean speech (two Windows voices, two sentences each): one voice 0.88-0.90, two voices
0.37-0.45 - see ALIKE / UNLIKE. A sample with music under it scores lower against itself (0.2-0.3): the sample should
be clean speech («Звук сцены» separates the voice). A check is a bonus, never a blocker: anything going wrong is «not measured» (None).
"""
from __future__ import annotations

import functools
import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np

from . import config

MODEL = config.DATA_DIR / "models" / "voice" / "voxceleb_resnet34_LM.onnx"
MODEL_URL = "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/voxceleb_resnet34_LM.onnx"
SR = 16000
ALIKE, UNLIKE = 0.6, 0.4      # cosine: above - «похож», below - «не похож», between - «отчасти»
MIN_SPEECH_S = 0.8            # less speech than this isn't measured
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _model() -> str:
    if not MODEL.exists():
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        tmp = MODEL.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.rename(MODEL)
    return str(MODEL)


@functools.lru_cache(maxsize=1)
def _net():
    import cv2
    return cv2.dnn.readNetFromONNX(_model())


def load(path: Path, start: float = 0, length: Optional[float] = None) -> np.ndarray:
    args = [config.FFMPEG, "-v", "error", "-ss", f"{max(start, 0):.3f}"] + (["-t", f"{length:.3f}"] if length else [])
    r = subprocess.run(args + ["-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True,
                       creationflags=NO_WINDOW)
    return np.frombuffer(r.stdout, np.float32) if r.returncode == 0 else np.zeros(0, np.float32)


def speech(x: np.ndarray) -> np.ndarray:
    """The 30 ms frames louder than a tenth of the loud level: pauses and silence don't count."""
    n = 480
    frames = x[: len(x) // n * n].reshape(-1, n)
    if not len(frames):
        return x
    rms = np.sqrt((frames ** 2).mean(1))
    keep = rms > 0.1 * np.percentile(rms, 95)
    return frames[keep].reshape(-1) if keep.sum() > 20 else x


@functools.lru_cache(maxsize=1)
def _mel(n_fft: int = 512, bins: int = 80, low: float = 20.0) -> np.ndarray:
    """Kaldi's triangular mel filters on the FFT's bins (no Nyquist bin), (bins, n_fft // 2)."""
    mel = lambda f: 1127.0 * np.log(1.0 + np.asarray(f) / 700.0)  # noqa: E731
    lo, hi = mel(low), mel(SR / 2)
    centers = lo + (hi - lo) / (bins + 1) * np.arange(bins + 2)
    f = mel(np.arange(n_fft // 2) * SR / n_fft)
    l, c, r = centers[:-2, None], centers[1:-1, None], centers[2:, None]
    return np.maximum(0.0, np.minimum((f - l) / (c - l), (r - f) / (r - c))).astype(np.float64)


def fbank(x: np.ndarray) -> np.ndarray:
    """Kaldi fbank as WeSpeaker feeds it: 25 ms / 10 ms frames, DC removed, pre-emphasis 0.97, Hamming, 512-point
    power spectrum, 80 log-mel bins, then the mean over time taken off. (frames, 80)"""
    x = x.astype(np.float64) * (1 << 15)
    n, hop = 400, 160
    if len(x) < n:
        return np.zeros((0, 80), np.float32)
    idx = np.arange(n)[None] + hop * np.arange(1 + (len(x) - n) // hop)[:, None]
    fr = x[idx]
    fr = fr - fr.mean(1, keepdims=True)
    fr = np.concatenate([fr[:, :1] - 0.97 * fr[:, :1], fr[:, 1:] - 0.97 * fr[:, :-1]], 1)
    fr = fr * (0.54 - 0.46 * np.cos(2 * np.pi * np.arange(n) / (n - 1)))
    power = np.abs(np.fft.rfft(fr, 512)) ** 2
    feat = np.log(np.maximum(power[:, :256] @ _mel().T, np.finfo(np.float32).eps))
    return (feat - feat.mean(0)).astype(np.float32)


def embed(x: np.ndarray) -> Optional[np.ndarray]:
    x = speech(x)
    if len(x) < MIN_SPEECH_S * SR:
        return None
    net = _net()
    net.setInput(fbank(x)[None])
    e = net.forward()[0].astype(np.float64)
    return e / (np.linalg.norm(e) + 1e-9)


def similarity(sample: Path, other: Path, sample_from: float = 0, sample_secs: Optional[float] = None) -> Optional[float]:
    """The cosine of the two voices (a piece of the sample, all of the other), or None when it can't be measured."""
    try:
        a, b = embed(load(sample, sample_from, sample_secs)), embed(load(other))
        return None if a is None or b is None else round(float(np.dot(a, b)), 3)
    except Exception:  # noqa: BLE001 - a check is a bonus, never a blocker
        return None


def verdict(sim: Optional[float]) -> Optional[str]:
    return None if sim is None else "alike" if sim >= ALIKE else "unlike" if sim < UNLIKE else "partly"


def measured(shot: Path, sample: Path, sample_from: float, sample_secs: float) -> Optional[dict]:
    """A voice scene's likeness, kept next to its shot (<key>.voice.json) and measured once."""
    j = shot.with_suffix(".voice.json")
    try:
        return json.loads(j.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if not shot.exists():
        return None
    sim = similarity(sample, shot, sample_from, sample_secs)
    out = {"sim": sim, "verdict": verdict(sim)}
    try:
        j.write_text(json.dumps(out), encoding="utf-8")   # «not measured» too: measured once
    except OSError:
        pass
    return out
