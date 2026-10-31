"""The montage for DaVinci Resolve: an FCPXML 1.9 timeline that File > Import > Timeline
reads, beside the files it plays, in a folder the user chose («<name> · Resolve» in it) or the project's resolve/
(made anew on each export; only a folder marked as ours is ever cleared).

What goes over (edit.resolve's montage, frame for frame): the scenes' shots on V1 with their trims, speed (a
timeMap) and their sound on A1 at its level (times the track's «звук сцен»); a dissolve and «через чёрное» as a
transition starting on the edit (the clip before it plays on in its handle, as edit.render overlaps them); the
track on a lane of its own from its offset, at its level, with its fades; the sounds from files on lanes below it
(one lane while they do not overlap). A flash is a cut with a marker «Вспышка». A scene not shot yet is a gap of
its length named «Сцена N — не снята»: the rest stays in its time (shoot it, export again). Not carried: the ducking, the
video's colour (a LUT of the user's is copied beside the timeline) - Resolve does both its own way.
"""
from __future__ import annotations

import math
import os
import re
import shutil
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import quoteattr

from . import edit, i18n, music

FPS = edit.FPS
DISSOLVE = '<effect id="rx" name="Cross Dissolve" uid="FxPlug:4731E73A-8DAC-4113-9A30-AE85B1761265"/>'


def _t(frames: int) -> str:
    return f"{frames}/{FPS}s" if frames else "0s"


def _fr(seconds: float) -> int:
    return round(float(seconds) * FPS)


def _db(x: float) -> str:
    return f"{20 * math.log10(x):.2f}dB" if x > 0.0001 else "-96dB"


def _volume(x: float, fade_in: float = 0, fade_out: float = 0) -> str:
    if abs(x - 1) < 0.005 and not fade_in and not fade_out:
        return ""
    fades = (f'<fadeIn type="easeIn" duration="{_t(_fr(fade_in))}"/>' if fade_in else "") + \
            (f'<fadeOut type="easeIn" duration="{_t(_fr(fade_out))}"/>' if fade_out else "")
    return f'<adjust-volume amount="{_db(x)}">' + (f'<param name="amount">{fades}</param>' if fades else "") + "</adjust-volume>"


def _link(src: Path, dst: Path) -> None:
    """The file beside the timeline: a hard link (same disk, no space), else a copy."""
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:80] or "montage"


MARK = ".remiqora-resolve"   # a folder with it is one of ours: an export again may clear it


def target(folder: Path, place: Optional[Path], name: str) -> Path:
    """Where the export goes: resolve/ in the project, or «<name> · Resolve» in a folder the user chose. A folder of
    that name that is not ours is never cleared - the export takes the next free name («… 2»)."""
    if place is None:
        return folder / "resolve"
    base = f"{_safe(name)} · Resolve"
    for n in range(1, 100):
        out = place / (base if n == 1 else f"{base} {n}")
        if not out.exists() or (out / MARK).exists():
            return out
    raise ValueError(i18n.L("В этой папке уже 99 выгрузок с таким именем", "This folder already has 99 exports with this name"))


def export(proj: dict, ed: dict, folder: Path, width: int, height: int, quality: str, place: Optional[Path] = None) -> dict:
    """The montage (edit.resolve) -> <target>/<name>.fcpxml + media/ (target(): the project's resolve/, or a folder of
    its own in `place`). -> {dir, file, clips, unshot, sounds, track, seconds}."""
    clips = ed["clips"]
    if not any(c["file"] for c in clips):
        raise ValueError(i18n.L("Ни одна сцена ещё не снята — в Resolve нечего отдать", "No scene is shot yet: nothing to give to Resolve"))
    out = target(folder, place, proj.get("name") or i18n.L("Ролик", "Video"))
    media = out / "media"
    if out.exists():
        shutil.rmtree(out)
    media.mkdir(parents=True)
    (out / MARK).write_text(i18n.L("Выгрузка монтажа для DaVinci Resolve (Remiqora Video): папка пересоздаётся при каждой выгрузке.\n",
                                   "A montage export for DaVinci Resolve (Remiqora Video): the folder is made again at every export.\n"),
                            encoding="utf-8")

    assets: dict[str, tuple[str, Path]] = {}   # a source file -> (asset id, its copy)
    res: list[str] = [f'<format id="r1" frameDuration="1/{FPS}s" width="{width}" height="{height}"/>']

    def asset(src: Path, name: str, frames: int, video: bool) -> str:
        key = str(src)
        if key not in assets:
            dst = media / name
            _link(src, dst)
            aid = f"r{len(assets) + 2}"
            assets[key] = (aid, dst)
            vid = ' hasVideo="1" format="r1" videoSources="1"' if video else ""
            res.append(f'<asset id="{aid}" name={quoteattr(dst.stem)} start="0s" duration="{_t(frames)}"{vid} hasAudio="1" '
                       f'audioSources="1" audioChannels="2" audioRate="48000"><media-rep kind="original-media" '
                       f'src={quoteattr(dst.resolve().as_uri())}/></asset>')
        return assets[key][0]

    track = (proj.get("settings") or {}).get("track")
    track = track if track and track.get("file") and (folder / track["file"]).exists() else None
    tset = music.settings(track) if track else None
    scene_vol = tset["scene_volume"] if tset else 1.0

    # the spine: clip k from its start for its frames, less the dissolve of the next one (that plays in its handle)
    spine = []
    for k, c in enumerate(clips):
        td_next = _fr(clips[k + 1]["td"]) if k + 1 < len(clips) and clips[k + 1]["tr"] in ("fade", "black") else 0
        if not c["file"]:   # a scene not shot yet: a gap of its length, named, so the timeline keeps its time
            spine.append({"c": c, "aid": None, "offset": _fr(c["start"]), "dur": c["frames"] - td_next, "start": 0, "anchored": []})
            continue
        src = Path(c["src"])
        aid = asset(src, f"{c['index'] + 1:02d}_{src.stem[:10]}{src.suffix}", _fr(c["length"]), True)
        spine.append({"c": c, "aid": aid, "offset": _fr(c["start"]), "dur": c["frames"] - td_next,
                      "start": 0 if c["speed"] != 1 else _fr(c["in"]), "anchored": []})

    def anchor(at: int, xml_of) -> None:
        """A clip on a lane, connected to the spine clip that plays at frame `at` (its offset in that clip's time)."""
        p = next((s for s in reversed(spine) if s["offset"] <= at), spine[0])
        p["anchored"].append(xml_of(p["start"] + at - p["offset"]))

    total = spine[-1]["offset"] + spine[-1]["dur"]
    if track:
        tf = folder / track["file"]
        ln = _fr(music.duration(tf))
        a = _fr(tset["offset"])
        n = min(ln - a, total)
        if n > 0:
            aid = asset(tf, f"track{tf.suffix}", ln, False)
            vol = _volume(tset["volume"], tset["fade_in"], tset["fade_out"])
            anchor(0, lambda off: f'<asset-clip ref="{aid}" lane="-1" offset="{_t(off)}" name={quoteattr(track.get("name") or i18n.L("Трек", "Track"))} '
                                  f'start="{_t(a)}" duration="{_t(n)}" audioRole="music">{vol}</asset-clip>')

    lanes: list[int] = []   # the sounds: each lane's last frame
    placed = 0
    for x in ed.get("sounds") or []:
        at, a, b = _fr(x["start"]), _fr(x["in"]), _fr(x["out"])
        n = min(b - a, total - at)
        if n <= 0:
            continue
        lane = next((i for i, end in enumerate(lanes) if end <= at), None)
        if lane is None:
            lanes.append(0)
            lane = len(lanes) - 1
        lanes[lane] = at + n
        sf = folder / x["file"]
        aid = asset(sf, f"sound_{len(assets):02d}{sf.suffix}", _fr(edit.sound_seconds(sf)), False)   # Latin names: a URL as it is
        vol = _volume(x["vol"], x["fade_in"], x["fade_out"])
        nm, ln_ = x.get("name") or sf.stem, -2 - lane
        anchor(at, lambda off, aid=aid, nm=nm, ln_=ln_, a=a, n=n, vol=vol:
               f'<asset-clip ref="{aid}" lane="{ln_}" offset="{_t(off)}" name={quoteattr(nm)} start="{_t(a)}" '
               f'duration="{_t(n)}" audioRole="effects">{vol}</asset-clip>')
        placed += 1

    for o in ed.get("overlays") or []:   # «Поверх»: on V2 over the spine, its picture only (its sound silenced)
        if not o.get("src"):
            continue
        src = Path(o["src"])
        aid = asset(src, f"{o['index'] + 1:02d}_{src.stem[:10]}{src.suffix}", _fr(o["length"]), True)
        at, a, n = _fr(o["start"]), _fr(o["in"]), o["frames"]
        anchor(at, lambda off, aid=aid, o=o, a=a, n=n:
               f'<asset-clip ref="{aid}" lane="1" offset="{_t(off)}" name={quoteattr(o["name"] + i18n.L(" · поверх", " · over"))} '
               f'start="{_t(a)}" duration="{_t(n)}" tcFormat="NDF"><adjust-volume amount="-96dB"/></asset-clip>')

    body, dissolves = [], False
    for k, s in enumerate(spine):
        c = s["c"]
        if not s["aid"]:
            body.append(f'<gap name={quoteattr(c["name"] + i18n.L(" — не снята", " (not shot)"))} offset="{_t(s["offset"])}" start="0s" '
                        f'duration="{_t(s["dur"])}">{"".join(s["anchored"])}</gap>')
            continue
        if k and c["tr"] in ("fade", "black") and spine[k - 1]["aid"]:   # a gap has no picture to dissolve from
            dissolves = True
            name = "Cross Dissolve" if c["tr"] == "fade" else "Dip to Color Dissolve"
            body.append(f'<transition name="{name}" offset="{_t(s["offset"])}" duration="{_t(_fr(c["td"]))}">'
                        f'<filter-video ref="rx" name="Cross Dissolve"/></transition>')
        tm = ""
        if c["speed"] != 1:   # local time from 0 -> the shot's time from its in, at the clip's speed
            a = _fr(c["in"])
            tm = (f'<timeMap><timept time="0s" value="{_t(a)}" interp="linear"/>'
                  f'<timept time="{_t(c["frames"])}" value="{_t(a + round(c["frames"] * c["speed"]))}" interp="linear"/></timeMap>')
        mark = f'<marker start="{_t(s["start"])}" duration="1/{FPS}s" value="{i18n.L('Вспышка', 'Flash')}"/>' if k and c["tr"] == "flash" else ""
        body.append(f'<asset-clip ref="{s["aid"]}" offset="{_t(s["offset"])}" name={quoteattr(c["name"])} start="{_t(s["start"])}" '
                    f'duration="{_t(s["dur"])}" tcFormat="NDF" audioRole="dialogue">{tm}{_volume(c["vol"] * scene_vol)}'
                    f'{"".join(s["anchored"])}{mark}</asset-clip>')
    if dissolves:
        res.append(DISSOLVE)

    name = proj.get("name") or i18n.L("Ролик", "Video")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.9">\n'
           f'<resources>\n{chr(10).join(res)}\n</resources>\n'
           f'<library><event name={quoteattr(name)}><project name={quoteattr(f"{name} · {quality}")}>'
           f'<sequence format="r1" duration="{_t(total)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">'
           f'<spine>\n{chr(10).join(body)}\n</spine></sequence></project></event></library>\n</fcpxml>\n')
    dest = out / f"{_safe(name)}.fcpxml"
    dest.write_text(xml, encoding="utf-8")
    if ed.get("grade") == "lut" and ed.get("lut") and (folder / ed["lut"]).exists():
        shutil.copy2(folder / ed["lut"], out / Path(ed["lut"]).name)
    return {"dir": str(out), "file": dest.name, "clips": len(clips), "unshot": sum(1 for c in clips if not c["file"]), "sounds": placed, "track": bool(track),
            "seconds": round(total / FPS, 3)}
