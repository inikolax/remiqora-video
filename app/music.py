"""Your own track over the whole video: one piece of music instead of each scene's own.

H3 makes every scene's sound with the picture, and every scene makes its own music - they don't match across cuts.
Here the assembled video gets one track laid over it: the track from an offset, faded in and out,
its level and the level of the scenes' own sound set by the user (the scenes' sound kept low gives the steps, the
wind, the rain under the music). The mix is the last step before RTX; changing the track or its levels only mixes
again (seconds), the scenes come from the cache.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from . import config
from .engine.comfy import EngineError
from . import i18n

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
DEFAULTS = {"volume": 0.9, "scene_volume": 0.3, "offset": 0.0, "fade_in": 0.5, "fade_out": 2.0}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def duration(path: Path) -> float:
    r = subprocess.run([config.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError) as e:
        raise EngineError(i18n.L("Не читается как звук: ", "Can't be read as sound: ") + (r.stderr or "").strip()[-300:]) from e


def has_audio(path: Path) -> bool:
    r = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True, creationflags=NO_WINDOW)
    return bool(r.stdout.strip())


def settings(track: dict) -> dict:
    """The track's mix settings with defaults, clamped to what makes sense."""
    t = {**DEFAULTS, **{k: track[k] for k in DEFAULTS if k in track}}
    t["volume"] = min(2.0, max(0.0, float(t["volume"])))
    t["scene_volume"] = min(2.0, max(0.0, float(t["scene_volume"])))
    t["offset"] = max(0.0, float(t["offset"]))
    t["fade_in"] = min(10.0, max(0.0, float(t["fade_in"])))
    t["fade_out"] = min(10.0, max(0.0, float(t["fade_out"])))
    return t


def signature(folder: Path, track: dict | None) -> str | None:
    """What the mix depends on: the file and the levels. A finished video with another signature needs a new mix."""
    if not track:
        return None
    f = folder / track["file"]
    st = f.stat() if f.exists() else None
    return hashlib.sha1(json.dumps([track["file"], st and st.st_size, st and int(st.st_mtime), settings(track)]).encode()).hexdigest()[:12]


def mix(video: Path, track_file: Path, track: dict, dest: Path) -> None:
    """The video's picture as it is; the sound = the track (offset, fades, level) + the scenes' sound at its level,
    cut to the video's length, a limiter against clipping."""
    t = settings(track)
    dur = duration(video)
    fade_out_at = max(0.0, dur - t["fade_out"])
    music = (f"[1:a]volume={t['volume']},afade=t=in:st=0:d={t['fade_in']},apad,atrim=0:{dur:.3f},"
             f"afade=t=out:st={fade_out_at:.3f}:d={t['fade_out']},asetpts=PTS-STARTPTS[m]")
    if t["scene_volume"] > 0 and has_audio(video):
        graph = f"{music};[0:a]volume={t['scene_volume']}[s];[s][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]"
    else:
        graph = f"{music};[m]alimiter=limit=0.95[a]"
    args = [config.FFMPEG, "-y", "-v", "error", "-i", str(video)]
    if t["offset"]:
        args += ["-ss", f"{t['offset']:.3f}"]
    args += ["-i", str(track_file), "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
             "-c:a", "aac", "-b:a", "256k", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(dest)]
    r = subprocess.run(args, capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode:
        raise EngineError(i18n.L("ffmpeg (музыка): ", "ffmpeg (music): ") + (r.stderr or "").strip()[-600:])
