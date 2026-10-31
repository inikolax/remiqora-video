"""How long a scene really takes on this machine: every fresh shot is recorded, estimates come from the recent ones.

A record: quality, the frame's pixels, the frame count, the number of LoRA, the seconds, and whether ComfyUI had to
start / load the model first (a cold shot also pays the model load, ~10-40 s). An estimate takes the median seconds
per megapixel-frame of the last warm shots of that quality and scales it to the asked size; the cold overhead is the
median difference between cold and warm shots. Until there are records, the 2026-10-21 measurements stand in.
"""
from __future__ import annotations

import json
import statistics
import threading
import time

from . import config

FILE = config.DATA_DIR / "timings.json"
KEEP = 60
# seconds per 5 s scene (124 frames), int8, warm, RTX 4080 - measured 2026-10-21
BASE = {"draft": (960 * 544, 95.0), "final": (1344 * 768, 271.0)}
COLD = 25.0
_lock = threading.Lock()


def _load() -> list[dict]:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def record(quality: str, width: int, height: int, length: int, loras: int, seconds: float, cold: bool) -> None:
    with _lock:
        rows = _load()
        rows.append({"q": quality, "px": width * height, "frames": length, "loras": loras, "s": round(seconds, 1),
                     "cold": cold, "t": int(time.time())})
        FILE.write_text(json.dumps(rows[-KEEP:], indent=0), encoding="utf-8")


def _rate(rows: list[dict]) -> float:
    """Median seconds per (pixel * frame)."""
    return statistics.median(r["s"] / (r["px"] * r["frames"]) for r in rows)


def scene_seconds(quality: str, width: int, height: int, length: int = 124, base: float | None = None) -> float:
    """`quality` is a timings key (videomodels.timing_key: H3's draft / final / draft_ref, another model's
    "ltx25:draft"); `base` - that model's guess for this size until it is measured here."""
    rows = [r for r in _load() if r["q"] == quality]
    warm = [r for r in rows if not r["cold"]][-12:]
    if warm:
        return _rate(warm) * width * height * length
    if base is not None:
        return base
    px, secs = BASE.get(quality.split("_")[0], BASE["draft"])
    if quality.endswith("_ref"):
        secs *= 0.7   # Ref2VA: 4 turbo steps instead of 8, but the photo's tokens ride along every step
    return secs * (width * height / px) * (length / 124)


def cold_seconds(quality: str) -> float:
    rows = [r for r in _load() if r["q"] == quality]
    cold, warm = [r for r in rows if r["cold"]][-6:], [r for r in rows if not r["cold"]][-12:]
    if cold and warm:
        return max(0.0, statistics.median(r["s"] / (r["px"] * r["frames"]) for r in cold) * statistics.median(r["px"] * r["frames"] for r in cold)
                   - _rate(warm) * statistics.median(r["px"] * r["frames"] for r in cold))
    return COLD


def samples(quality: str) -> int:
    return sum(1 for r in _load() if r["q"] == quality and not r["cold"])


# The writer's new storyboard: seconds a scene, the model's start among them, from this machine's last ones. A fixed
# 4 s a scene was a 12B model's; a 24B one that spills out of the video memory wrote a 10-scene clip in 198 s, and the
# job's bar stood at 99 % for minutes (2026-10-29).
WRITER_FILE = config.DATA_DIR / "writer_timings.json"
WRITER_KEEP = 40


def _load_writer() -> list[dict]:
    try:
        return json.loads(WRITER_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def record_writer(writer: dict, scenes: int) -> None:
    """A storyboard written (the plan's `writer`: model, seconds, cached calls) - not one taken from the LLM cache."""
    if not scenes or writer.get("cached") or not writer.get("seconds"):
        return
    with _lock:
        rows = _load_writer()
        rows.append({"model": writer.get("model"), "scenes": scenes, "s": round(float(writer["seconds"]), 1), "t": int(time.time())})
        WRITER_FILE.write_text(json.dumps(rows[-WRITER_KEEP:], indent=0), encoding="utf-8")


def writer_seconds(model: str, scenes: int, base: float) -> float:
    """A new storyboard of `scenes` by `model` (its name): this model's last ones, else any model's, else `base`."""
    rows = _load_writer()
    mine = [r for r in rows if r["model"] == model][-8:] or rows[-8:]
    if not mine:
        return base
    return statistics.median(r["s"] / r["scenes"] for r in mine) * scenes
