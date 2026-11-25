"""Checks of a start PICTURE of the beat clip, before it becomes a scene:

  diptych(path)          two pictures in one frame (Krea gives a collage when a macro's style names a place: spec54, 2026-11-06)
  face_on_faceless(path) a face on a hero that has none (a mask, a visor): the hero's face drifts from shot to shot
  check_picture(...)     both, as problems; draw_checked(...) the re-seed policy (up to TRIES draws, like frames.draw_one)

The seam heuristic is cheap and runs on the CPU: a picture of two panels has, at the middle (the two halves are drawn at
0.5; a 0.43-0.57 band is searched), a full-width STEP of colour that the rows around it do not have. It cannot see a
soft blend, so it gives a score and three verdicts: `single`, `borderline` (ask the VLM when there is one; without one it is
only a note) and `diptych` (a redraw).
Calibrated on the labelled pictures of three hand-made beat clips.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Awaitable, Callable, Optional

import numpy as np

from . import checks

TRIES = 3                  # a picture is drawn up to this many times (frames.TRIES' way: new seed, keep the best)
SEED_STEP = 7919           # frames.SEED_STEP's idea: far apart seeds
SEAM_WIDTH = 160           # the picture is looked at this wide
SEAM_BAND = (0.43, 0.57)   # where a two-panel picture's seam is searched (the middle)
SEAM_WINDOW = 6            # rows (pixels at SEAM_WIDTH) averaged on each side of a candidate seam
# the three terms of the score (each is 1.0 at its line): the step at the seam against the rows around it, the share of the
# seam's length with a real step, and the step itself in CIE Lab units; the score is the smallest of the three
SEAM_LOCAL, SEAM_COVER, SEAM_STEP = 2.4, 0.65, 24.0
SEAM_HALVES = 0.10         # ...and (a fourth term) how much the two halves' colour histograms differ (1 - Bhattacharyya)
SEAM_COLUMN_STEP = 10.0    # a column counts as stepping above this
DIPTYCH_AT = 1.0           # score >= this: a diptych
BORDERLINE_AT = 0.75       # ... >= this: borderline (asks the VLM; without one a note only)


def _read(path: Path) -> Optional[np.ndarray]:
    try:
        import cv2
        return checks.imread(path)
    except Exception:  # noqa: BLE001
        return None


def _step_profile(lab: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For every row y: the colour step between the SEAM_WINDOW rows above and below it, per column -> (ys, (n, w))."""
    k = SEAM_WINDOW
    h = lab.shape[0]
    cs = np.concatenate([np.zeros((1,) + lab.shape[1:], np.float32), np.cumsum(lab, axis=0)])
    ys = np.arange(k, h - k)
    return ys, np.linalg.norm((cs[ys] - cs[ys - k]) / k - (cs[ys + k] - cs[ys]) / k, axis=2)


def _halves_distance(small: np.ndarray, axis: int, j: int) -> float:
    """1 - the Bhattacharyya coefficient of the hue-saturation histograms of the two halves cut at row / column `j`."""
    import cv2
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    if axis == 1:
        hsv = hsv.transpose(1, 0, 2)

    def hist(a):
        h = cv2.calcHist([np.ascontiguousarray(a)], [0, 1], None, [18, 8], [0, 180, 0, 256])
        return h / max(float(h.sum()), 1e-6)
    return float(1.0 - np.sqrt(hist(hsv[:j]) * hist(hsv[j:])).sum())


def seam_scores(img: np.ndarray) -> dict:
    """The seam evidence on both axes: {row|col: {pos, local, cover, step, halves, score}} - `row`: a horizontal seam (the picture
    is a top and a bottom), `col`: a vertical one."""
    import cv2
    s = SEAM_WIDTH / img.shape[1]
    small = cv2.resize(img, (SEAM_WIDTH, max(8, round(img.shape[0] * s))), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    out = {}
    for axis, name in ((0, "row"), (1, "col")):
        ys, step = _step_profile(lab if axis == 0 else lab.transpose(1, 0, 2))
        n = lab.shape[axis]
        m = step.mean(axis=1)
        band = (ys >= SEAM_BAND[0] * n) & (ys <= SEAM_BAND[1] * n)
        if not band.any():
            out[name] = {"pos": 0.5, "local": 0.0, "cover": 0.0, "step": 0.0, "halves": 0.0, "score": 0.0}
            continue
        j = int(np.argmax(np.where(band, m, -1.0)))
        around = np.r_[m[max(0, j - 14):max(0, j - 4)], m[j + 5:j + 15]]
        local = float(m[j] / (around.mean() + 1e-3)) if len(around) else 0.0
        cover = float((step[j] > SEAM_COLUMN_STEP).mean())
        st = float(m[j])
        halves = _halves_distance(small, axis, int(ys[j]))
        out[name] = {"pos": round(float(ys[j] / n), 3), "local": round(local, 2), "cover": round(cover, 2), "step": round(st, 1),
                     "halves": round(halves, 2),
                     "score": round(min(local / SEAM_LOCAL, cover / SEAM_COVER, st / SEAM_STEP, halves / SEAM_HALVES), 3)}
    return out


def diptych(path: Path) -> dict:
    """{score, verdict, axis, pos, detail}: verdict `single` / `borderline` / `diptych` (module doc); `unread` when the
    picture can't be read (never a reason to redraw)."""
    img = _read(path)
    if img is None:
        return {"score": 0.0, "verdict": "unread", "axis": None, "pos": None, "detail": {}}
    d = seam_scores(img)
    axis = max(d, key=lambda a: d[a]["score"])
    score = d[axis]["score"]
    verdict = "diptych" if score >= DIPTYCH_AT else "borderline" if score >= BORDERLINE_AT else "single"
    return {"score": score, "verdict": verdict, "axis": axis, "pos": d[axis]["pos"], "detail": d}


# ---------- the VLM's word on a borderline picture ----------
COLLAGE_SYSTEM = ("You look at one generated picture and answer a yes/no question about its composition. Answer collage = true "
                  "only if the picture is made of two or more separate pictures or panels joined in one frame (a split screen, a "
                  "diptych, a contact sheet, one scene on top and another below it, a character sheet with a figure and a close-up "
                  "side by side); answer false for one continuous photograph, even a very dark or busy one.")
COLLAGE_SCHEMA = {"type": "object", "properties": {"collage": {"type": "boolean"}}, "required": ["collage"], "additionalProperties": False}


async def confirm_diptych(llm, path: Path) -> Optional[bool]:
    """The VLM's yes / no on `path` inside an open llm session (llm.client.session; describe.describe_with describes a
    person, so a one-field schema is asked directly). None when the model can't tell (no mmproj, an error): the caller decides."""
    try:
        d = await llm.chat_json(COLLAGE_SYSTEM, "Is this picture a collage of two or more pictures, or one continuous photograph?",
                                COLLAGE_SCHEMA, images=(path,), temperature=0.1, seed=1, max_tokens=60, step="photo")
        return bool(d.get("collage"))
    except Exception:  # noqa: BLE001 - a missing vision model is not a failed picture
        return None


# ---------- a face on a hero that has none ----------
_FACE_LOCK = threading.Lock()   # checks._still_detector is one shared object whose input size is its own state


def _faces_of(img: np.ndarray) -> list[tuple[float, float, float, float, float]]:
    h, w = img.shape[:2]
    try:
        with _FACE_LOCK:
            det = checks._still_detector()
            det.setInputSize((w, h))
            _, rows = det.detect(img)
    except Exception:  # noqa: BLE001 - YuNet downloads on the first call: no net, no check
        return []
    return [tuple(float(v) for v in r[:4]) + (float(r[-1]),) for r in (rows if rows is not None else []) if r[-1] >= checks.FACE_MIN_SCORE]


def faces_in(path: Path) -> list[tuple[float, float, float, float, float]]:
    """Every confident face YuNet finds in the picture: (x, y, w, h, score)."""
    img = _read(path)
    return [] if img is None else _faces_of(img)


def face_on_faceless(path: Path) -> dict:
    """{faces, score, redraw, area}: a face found on a faceless hero's picture is a redraw. `area` is the biggest face's share
    of the picture (a crowd's tiny faces in the far background of a wide shot are not the hero's: below FACE_AREA_MIN of the
    picture they are not counted)."""
    img = _read(path)
    fs = faces_in(path)
    area = 0.0
    if img is not None and fs:
        area = max(f[2] * f[3] for f in fs) / float(img.shape[0] * img.shape[1])
    big = [f for f in fs if img is not None and f[2] * f[3] / float(img.shape[0] * img.shape[1]) >= FACE_AREA_MIN]
    return {"faces": len(big), "score": max((f[4] for f in big), default=0.0), "area": round(area, 5), "redraw": bool(big)}


SCENE_FRAMES = 6           # frames sampled across a scene for the face check
SCENE_SKIP = 0.35          # the first seconds of a scene are the start picture itself (already checked): not looked at
# A scene's face must score higher than a picture's: in the smoke and the sparks of a moving shot YuNet finds «faces» at 0.60-0.73
# (clip 2 of 2026-11-06: three hero scenes, the boxes sat in clouds away from the hooded figure), while the two real faces under
# a hood (the close shot, the impact shot) scored 0.84 and 0.93 at best and in 6 of 6 frames
SCENE_FACE_SCORE = 0.78


def faces_in_frame(img: np.ndarray) -> list[tuple[float, float, float, float, float]]:
    """faces_in for a decoded BGR frame (the scene check's hook)."""
    return _faces_of(img)


def _video_frames(video: Path, n: int, skip: float) -> list[tuple[float, np.ndarray]]:
    """[(t, BGR frame)] at `n` times spread over the video after its first `skip` seconds, decoded at the video's own size."""
    import subprocess
    r = subprocess.run([checks.config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "csv=p=0:s=,", str(video)], capture_output=True, text=True, creationflags=checks.NO_WINDOW)
    rows = [x.split(",") for x in r.stdout.split() if x.strip()]
    w, h = int(rows[0][0]), int(rows[0][1])
    dur = float(rows[-1][-1] if len(rows) > 1 else rows[0][-1])
    lo, hi = min(skip, dur * 0.5), max(dur - 0.05, skip)
    out = []
    for i in range(n):
        t = lo + (hi - lo) * (i + 0.5) / n
        p = subprocess.run([checks.config.FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-f", "rawvideo",
                            "-pix_fmt", "bgr24", "-"], capture_output=True, creationflags=checks.NO_WINDOW)
        if len(p.stdout) == w * h * 3:
            out.append((t, np.frombuffer(p.stdout, np.uint8).reshape(h, w, 3).copy()))
    return out


def faces_in_scene(video: Path, n: int = SCENE_FRAMES, skip: float = SCENE_SKIP) -> dict:
    """The scene of a faceless hero, looked at by the same YuNet as the picture: `n` frames across it (after the first `skip`
    s); a face of at least FACE_AREA_MIN of the frame and SCENE_FACE_SCORE on any frame makes `bad`. H3 animates a face under
    a hood on a close shot although the start picture had none (clip 2, 2026-11-06).
    -> {bad, frames (looked at), hits [{t, score, area}] (the strong ones), weak (frames with only a weaker face: smoke and
    sparks, not counted), score (the best hit's), at (its time)}. An unreadable file: not bad."""
    try:
        frames = _video_frames(Path(video), n, skip)
    except Exception:  # noqa: BLE001 - an unreadable scene is not a face
        return {"bad": False, "frames": 0, "hits": [], "weak": 0, "score": 0.0, "at": None}
    hits, weak = [], 0
    for t, img in frames:
        area = float(img.shape[0] * img.shape[1])
        big = [f for f in faces_in_frame(img) if f[2] * f[3] / area >= FACE_AREA_MIN]
        if big and max(x[4] for x in big) < SCENE_FACE_SCORE:
            weak += 1
        elif big:
            f = max(big, key=lambda x: x[4])
            hits.append({"t": round(t, 2), "score": round(f[4], 3), "area": round(f[2] * f[3] / area, 5)})
    best = max(hits, key=lambda x: x["score"], default=None)
    return {"bad": bool(hits), "frames": len(frames), "hits": hits, "weak": weak, "score": best["score"] if best else 0.0, "at": best["t"] if best else None}


FACE_AREA_MIN = 0.0008     # a face smaller than this share of the picture is a crowd's or a poster's, not the hero's


def check_picture(path: Path, faceless: bool = True, framing: Optional[str] = None) -> list[dict]:
    """The picture's problems as [{code, ...}]: `diptych` (also `borderline`) and, for a faceless hero, `face`. Empty: fine."""
    out = []
    d = diptych(path)
    if d["verdict"] in ("diptych", "borderline"):
        out.append({"code": d["verdict"], "value": d["score"], "axis": d["axis"], "pos": d["pos"]})
    if faceless:
        f = face_on_faceless(path)
        if f["redraw"]:
            out.append({"code": "face", "value": f["score"], "faces": f["faces"]})
    return out


def is_bad(problems: list[dict], vlm: Optional[dict] = None) -> bool:
    """Whether a redraw is due: a diptych, a face on a faceless hero, or a borderline picture the VLM said is a collage
    (`vlm`: the answers already got, {'borderline': True}). Without a VLM a borderline picture stays a note: the seam
    heuristic alone flagged 7 of 67 good pictures as borderline, and a redraw of a good mask macro costs more than it saves."""
    for p in problems:
        if p["code"] in ("diptych", "face"):
            return True
        if p["code"] == "borderline" and (vlm or {}).get("borderline") is True:
            return True
    return False


# ---------- the re-seed policy ----------
RETRY_HINT = {"face": "Seen straight from the front: a smooth featureless mask, no human face anywhere.",
              "diptych": "One single continuous photograph filling the whole frame, not a collage, no split screen."}


async def draw_checked(draw: Callable[[int, str], Awaitable[Path]], seed: int, faceless: bool = True, framing: Optional[str] = None,
                       tries: int = TRIES, llm=None, step: int = SEED_STEP) -> dict:
    """frames.draw_one's way for the beat clip's pictures: draw on `seed`, check, and on a diptych or a face on a faceless
    hero draw again on a new seed (with the matching RETRY_HINT) up to `tries` times; the best try (the fewest problems) is
    kept. `draw(seed, hint) -> Path` draws one picture (hint: '' on the first try); `llm`: an open session for the VLM on a
    borderline picture. -> {path, seed, tries, problems, ok}"""
    best = None
    hint = ""
    for n in range(max(1, tries)):
        sd = seed + n * step
        path = await draw(sd, hint)
        probs = check_picture(path, faceless, framing)
        vlm = {}
        if llm is not None and any(p["code"] == "borderline" for p in probs):
            vlm["borderline"] = await confirm_diptych(llm, path)
            if vlm["borderline"] is False:
                probs = [p for p in probs if p["code"] != "borderline"]
            elif vlm["borderline"] is True:
                probs = [{**p, "code": "diptych", "vlm": True} if p["code"] == "borderline" else p for p in probs]
        bad = is_bad(probs, vlm)
        score = (sum(10 if p["code"] in ("diptych", "face") else 1 for p in probs))
        if best is None or score < best["_score"]:
            best = {"path": path, "seed": sd, "problems": probs, "_score": score}
        if not bad:
            break
        codes = {"diptych" if p["code"] == "borderline" else p["code"] for p in probs}
        hint = " ".join(RETRY_HINT[c] for c in ("face", "diptych") if c in codes)
    best["tries"] = n + 1
    best["ok"] = not is_bad(best["problems"])
    del best["_score"]
    return best
