"""«Лица» (the graph's facefix node): the small, far faces of a shot made sharp again.

On a wide shot H3 and LTX leave a face a blur that changes from frame to frame. The remedy, in four passes over the
clip (the idea from comfyui-vrgamedevgirl's Face Fix, written anew; its numbers are the starting point):

1. track: YuNet (checks.py has it) finds the face in every frame; the box follows it (IoU, confidence, the centre's
   shift, the area's change), smoothed (EMA); up to two missed frames keep the last box, fading; a cut (the frames'
   difference) or a longer loss ends the *run*. Only far faces are fixed: the face's width in per cent of the frame's
   gives a strength (MODES), 1 → 0 between two thresholds, so a face walking closer fades out of the repair.
2. crop: each run's square (the face × 1.2) at 512×512 as an mp4 in COMFY_INPUT; anchors - every 16th frame + the
   last, off the 8n+1 indices LTX won't take - through Krea 2 img2img (denoise 0.5): a sharp face on a few stills.
3. LTX 2.3 as video-to-video: the crop's latent, the anchors as guides (LTXVAddGuide, 0.5), 3 steps from ~0.9 noise
   (SIGMAS) - the anchors' detail spread over time, the motion the crop's. No LTXVLoopingSampler in our core: runs
   go in pieces of at most MAX_RUN frames.
4. composite: the result back into its box under a soft ellipse (inset, Gaussian feather), its mean colour shifted
   towards the original's, alpha = mask × the frame's strength - a face comes and goes smoothly.

Nothing found - the clip is copied as it is (a note on the node); any frame the model shortens stays original.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

from . import checks, config, i18n, jobs, picture
from .engine import graphs, other_graphs
from .engine.comfy import COMFY, EngineError, output_files
from .v2v import FPS, _ffmpeg, probe

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
VERSION = 1                 # of the algorithm: in a result's key
CROP = 512
PAD = 0.10                  # the square: the face's longer side × (1 + 2 PAD)
DETECT_W = 960              # frames wider than this are detected at this width
MIN_SCORE = 0.5             # YuNet: a far face scores lower than a close one (checks.py asks 0.6)
EMA = 0.65                  # the box's weight of the new frame
GAP_STRENGTH = (0.65, 0.30)   # the 1st and 2nd missed frame keep the last box at this strength; a 3rd ends the run
CUT_DIFF = 0.28             # the frames' mean difference (64×64, 0..1) from this on is a cut
ANCHOR_EVERY = 16
MIN_RUN = 9                 # LTX: 8n+1 frames; shorter runs are padded with clones
MAX_RUN = 161               # and longer ones go in pieces
MODES: dict[str, Optional[tuple[float, float]]] = {   # face width, % of the frame's: full strength up to, none from
    "very_far": (4.0, 6.0), "far": (7.0, 9.0), "medium": (10.0, 12.0), "all": None}
FEATHER = 18                # the mask's Gaussian sigma at CROP
INSET = 0.035               # the ellipse inside the crop by this share
COLOR_MATCH = 0.65          # how much of the mean colour's difference is undone
SIGMAS = "0.725, 0.421875, 0.0"   # the distilled schedule's tail: ~0.7 noise, 2 steps (0.9 drew another person)
GUIDE = 0.5                 # an anchor's strength in LTXVAddGuide
KREA_DENOISE = 0.3          # (0.5 drew another person: a clean face, not hers)
PROMPT = "A sharp, detailed close-up of a person's face, natural skin texture, clear eyes, realistic lighting."
# the node's own words (the hero's look) go in front of it: "...woman, dark hair... A sharp, detailed close-up..."
STEPS = len(SIGMAS.split(",")) - 1


@dataclass
class Run:
    """A stretch of frames with one tracked face: the square box per frame (x, y, side, in the clip's pixels), the
    repair's strength per frame, whether the face was really seen there (an anchor wants a seen one)."""
    first: int
    boxes: list[tuple[int, int, int]] = field(default_factory=list)
    strength: list[float] = field(default_factory=list)
    seen: list[bool] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.boxes)


# ---------------------------------------------------------------------------------------------------------------
# frames in and out
# ---------------------------------------------------------------------------------------------------------------
def _frames(path: Path, w: int, h: int) -> Iterator[np.ndarray]:
    """The clip's frames one by one (BGR), never the whole clip in memory (15 s of 1344×768 is 1 GB)."""
    p = subprocess.Popen([config.FFMPEG, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         stdout=subprocess.PIPE, creationflags=NO_WINDOW)
    n = w * h * 3
    try:
        while True:
            buf = bytearray()
            while len(buf) < n:
                chunk = p.stdout.read(n - len(buf))
                if not chunk:
                    break
                buf += chunk
            if len(buf) < n:
                return
            yield np.frombuffer(bytes(buf), np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        p.wait()


class _Writer:
    """Frames (BGR) into an mp4 through ffmpeg's stdin; `audio_from` - a clip whose sound the mp4 gets."""

    def __init__(self, dest: Path, w: int, h: int, crf: int, audio_from: Optional[Path] = None, length: Optional[float] = None):
        args = [config.FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-"]
        if audio_from:
            args += ["-i", str(audio_from), "-map", "0:v", "-map", "1:a?", "-c:a", "aac", "-b:a", "192k"]
        if length:
            args += ["-t", f"{length:.4f}"]
        args += ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium" if audio_from else "fast", "-pix_fmt", "yuv420p",
                 *(["-movflags", "+faststart"] if audio_from else []), str(dest)]
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=NO_WINDOW)

    def write(self, frame: np.ndarray) -> None:
        self.p.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self) -> None:
        self.p.stdin.close()
        err = self.p.stderr.read().decode("utf-8", "replace")
        if self.p.wait():
            raise EngineError("ffmpeg: " + err.strip()[-800:])


# ---------------------------------------------------------------------------------------------------------------
# 1. track
# ---------------------------------------------------------------------------------------------------------------
def _iou(a: tuple, b: tuple) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw, ih = max(0.0, min(ax + aw, bx + bw) - max(ax, bx)), max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = iw * ih
    return inter / (aw * ah + bw * bh - inter + 1e-6)


def _pick(faces: list, prev: Optional[tuple]) -> Optional[tuple]:
    """The face to follow: without a track the most confident; with one, the candidate closest to it (IoU, confidence,
    the centre's shift in units of the face, the area's change) - none when every candidate is far from the track."""
    if not faces:
        return None
    if prev is None:
        return max(faces, key=lambda f: f[-1])
    px, py, pw, ph = prev
    pc, size = (px + pw / 2, py + ph / 2), max(pw, ph)

    def score(f) -> float:
        x, y, w, h, conf = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
        dist = math.hypot(x + w / 2 - pc[0], y + h / 2 - pc[1]) / size
        return _iou(prev, (x, y, w, h)) * 3 + conf - 4 * dist - 0.35 * abs(math.log((w * h) / (pw * ph + 1e-6) + 1e-6))
    best = max(faces, key=score)
    bx, by, bw, bh = (float(v) for v in best[:4])
    near = _iou(prev, (bx, by, bw, bh)) > 0 or math.hypot(bx + bw / 2 - pc[0], by + bh / 2 - pc[1]) < 1.5 * size
    return best if near else None


def _square(cx: float, cy: float, side: float, w: int, h: int) -> tuple[int, int, int]:
    """The crop's square around a centre, inside the frame."""
    s = int(round(min(side, w, h)))
    s -= s % 2
    x = int(round(min(max(cx - s / 2, 0), w - s)))
    y = int(round(min(max(cy - s / 2, 0), h - s)))
    return x, y, s


def _distance_strength(face_w: float, frame_w: int, mode: str) -> float:
    lim = MODES.get(mode, MODES["far"])
    if lim is None:
        return 1.0
    pct = 100.0 * face_w / frame_w
    lo, hi = lim
    return 1.0 if pct <= lo else 0.0 if pct >= hi else (hi - pct) / (hi - lo)


def track(src: Path, w: int, h: int, mode: str) -> tuple[list[Run], int]:
    """The runs of one tracked face over the clip, and the clip's frame count."""
    import cv2
    scale = min(1.0, DETECT_W / w)
    dw, dh = (int(round(w * scale)) // 2 * 2, int(round(h * scale)) // 2 * 2) if scale < 1 else (w, h)
    detector = cv2.FaceDetectorYN_create(checks._yunet(), "", (dw, dh), score_threshold=MIN_SCORE)
    runs: list[Run] = []
    cur: Optional[Run] = None
    prev_face: Optional[tuple] = None     # the last seen face (x, y, w, h) in the clip's pixels
    box: Optional[tuple[float, float, float]] = None   # the smoothed square (cx, cy, side)
    gap, small_prev, n = 0, None, 0

    def close() -> None:
        nonlocal cur, prev_face, box, gap
        if cur and max(cur.strength, default=0) > 0:
            runs.append(cur)
        cur, prev_face, box, gap = None, None, None, 0

    for n, frame in enumerate(_frames(src, w, h)):
        small = cv2.resize(frame, (dw, dh), interpolation=cv2.INTER_AREA) if scale < 1 else frame
        gray = cv2.resize(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
        if small_prev is not None and float(np.abs(gray - small_prev).mean()) / 255 >= CUT_DIFF:
            close()
        small_prev = gray
        _, rows = detector.detect(small)
        faces = [f for f in (rows if rows is not None else []) if f[-1] >= MIN_SCORE]
        if scale < 1:
            faces = [np.concatenate([f[:-1] / scale, f[-1:]]) for f in faces]
        f = _pick(faces, prev_face)
        if f is not None:
            x, y, fw, fh = (float(v) for v in f[:4])
            prev_face, gap = (x, y, fw, fh), 0
            target = (x + fw / 2, y + fh / 2, max(fw, fh) * (1 + 2 * PAD))
            box = target if box is None else tuple(b * (1 - EMA) + t * EMA for b, t in zip(box, target))
            if cur is None:
                cur = Run(first=n)
            cur.boxes.append(_square(*box, w, h))
            cur.strength.append(_distance_strength(fw, w, mode))
            cur.seen.append(True)
        elif cur is not None and gap < len(GAP_STRENGTH):
            cur.boxes.append(cur.boxes[-1])
            cur.strength.append(cur.strength[-1] * GAP_STRENGTH[gap])
            cur.seen.append(False)
            gap += 1
        else:
            close()
    close()
    return runs, n + 1 if small_prev is not None else 0


# ---------------------------------------------------------------------------------------------------------------
# 2. crops and anchors
# ---------------------------------------------------------------------------------------------------------------
def _pieces(run: Run) -> list[tuple[int, int, int]]:
    """A run in pieces LTX takes: [(offset in the run, frames, frames padded to 8n+1)]."""
    out, at = [], 0
    while at < len(run):
        k = min(MAX_RUN, len(run) - at)
        padded = max(MIN_RUN, k)
        while padded % 8 != 1:
            padded += 1
        out.append((at, k, padded))
        at += k
    return out


def _anchors(run: Run, at: int, k: int, padded: int) -> list[int]:
    """The anchor indices of a piece: every ANCHOR_EVERY-th frame and the last, moved to the nearest seen frame, off
    the 8n+1 indices (LTXVAddGuide refuses them)."""
    want = sorted(set(list(range(0, k, ANCHOR_EVERY)) + [k - 1]))
    out = []
    for i in want:
        seen = [j for j in range(max(0, i - 8), min(k, i + 9)) if run.seen[at + j]]
        j = min(seen, key=lambda j: abs(j - i)) if seen else i
        if j % 8 == 1:
            j = j + 1 if j + 1 < padded else j - 1
        if j not in out and 0 <= j < padded:
            out.append(j)
    return sorted(out)


def crops(src: Path, w: int, h: int, runs: list[Run], tag: str) -> list[dict]:
    """Each run's pieces as 512×512 mp4 in COMFY_INPUT, their anchor frames as PNG: [{run, at, frames, padded, video,
    anchors: [(png, index)]}]. One pass over the clip: a frame goes to every piece that holds it."""
    import cv2
    work = config.COMFY_INPUT
    pieces: list[dict] = []
    open_: dict[int, tuple[dict, _Writer]] = {}   # the clip's frame a piece starts at -> (piece, writer)
    for r, run in enumerate(runs):
        for q, (at, k, padded) in enumerate(_pieces(run)):
            name = f"{tag}_{r}_{q}"
            pc = {"run": r, "at": at, "frames": k, "padded": padded, "video": name + ".mp4", "anchors": [],
                  "want": _anchors(run, at, k, padded), "last": None}
            pieces.append(pc)
    starts = {run.first + pc["at"]: pc for pc in pieces for run in [runs[pc["run"]]]}
    for n, frame in enumerate(_frames(src, w, h)):
        if n in starts:
            pc = starts[n]
            open_[n] = (pc, _Writer(work / pc["video"], CROP, CROP, 10))
        for start, (pc, wr) in list(open_.items()):
            i = n - start
            run = runs[pc["run"]]
            x, y, s = run.boxes[pc["at"] + i]
            crop = cv2.resize(frame[y:y + s, x:x + s], (CROP, CROP), interpolation=cv2.INTER_LANCZOS4)
            wr.write(crop)
            pc["last"] = crop
            if i in pc["want"]:
                png = f"{pc['video'][:-4]}_a{i}.png"
                cv2.imwrite(str(work / png), crop)
                pc["anchors"].append((png, i))
            if i == pc["frames"] - 1:
                for _ in range(pc["padded"] - pc["frames"]):   # padding: the last crop again
                    wr.write(crop)
                for j in pc["want"]:
                    if j >= pc["frames"]:   # an anchor index in the padding: the last crop
                        png = f"{pc['video'][:-4]}_a{j}.png"
                        cv2.imwrite(str(work / png), crop)
                        pc["anchors"].append((png, j))
                wr.close()
                del open_[start]
    for _, wr in open_.values():   # a clip shorter than the track said: close what is open
        wr.close()
    return pieces


# ---------------------------------------------------------------------------------------------------------------
# 3. the models
# ---------------------------------------------------------------------------------------------------------------
def prompt_of(text: str) -> str:
    """What the models get: the node's words (who the person is) and then the fixed line."""
    text = " ".join((text or "").split())
    return f"{text.rstrip('.')}. {PROMPT}" if text else PROMPT


async def _krea_anchors(job: jobs.Job, pieces: list[dict], seed: int, prompt: str) -> None:
    """Every anchor PNG through Krea 2 img2img, replaced in place (the worker reads and writes COMFY_INPUT/OUTPUT)."""
    todo = [(pc, k) for pc in pieces for k in range(len(pc["anchors"]))]
    if not todo:
        return
    await picture.ready(job)
    job.phase, job.step, job.steps = "sampling", 0, len(todo)
    for i, (pc, k) in enumerate(todo):
        png, idx = pc["anchors"][k]
        g = other_graphs.krea2_img2img(prompt, png, seed + i, f"h3studio/facefix/{png[:-4]}", KREA_DENOISE,
                                       config.KREA_UNET, config.KREA_CLIP, config.KREA_VAE)
        files = output_files(await COMFY.run(g, lambda n: None, lambda v, m, n: None))
        out = next((f for f in files if f.endswith(".png")), None)
        if not out:
            raise EngineError(i18n.L("Krea 2 не сделала опорный кадр", "Krea 2 made no anchor frame"))
        COMFY.warm = True
        shutil.move(out, config.COMFY_INPUT / png)
        job.step = i + 1


async def _ltx_pieces(job: jobs.Job, pieces: list[dict], seed: int, prompt: str) -> list[Path]:
    """Every piece through LTX 2.3 as video-to-video with its anchors -> the result mp4 per piece (COMFY_OUTPUT)."""
    await jobs.engine(job, "ltx23", [])
    outs = []
    job.steps = STEPS

    def on_node(node: str) -> None:
        if ph := other_graphs.phase_of(node):
            job.phase = ph

    def on_progress(value: int, maximum: int, node: str) -> None:
        if node == "sample1":
            job.phase, job.step, job.steps = "sampling", value, STEPS
    for i, pc in enumerate(pieces):
        job.progress["part"] = f"{i + 1}/{len(pieces)}"
        g = other_graphs.ltx_facefix(prompt, CROP, CROP, pc["padded"], seed + i, f"h3studio/facefix/{pc['video'][:-4]}",
                                     pc["video"], pc["anchors"], GUIDE, SIGMAS)
        files = output_files(await COMFY.run(g, on_node, on_progress))
        COMFY.warm = True
        mp4 = next((f for f in files if f.endswith(".mp4")), None)
        if not mp4:
            raise EngineError(i18n.L("ComfyUI закончил без mp4", "ComfyUI finished without an mp4"))
        for f in files:
            if f.endswith(".png"):
                Path(f).unlink(missing_ok=True)
        outs.append(Path(mp4))
    return outs


# ---------------------------------------------------------------------------------------------------------------
# 4. composite
# ---------------------------------------------------------------------------------------------------------------
def _mask() -> np.ndarray:
    """The soft ellipse at CROP (float 0..1)."""
    import cv2
    m = np.zeros((CROP, CROP), np.float32)
    r = int(round(CROP / 2 * (1 - INSET)))
    cv2.ellipse(m, (CROP // 2, CROP // 2), (r, r), 0, 0, 360, 1.0, -1)
    k = 4 * FEATHER + 1
    return cv2.GaussianBlur(m, (k, k), FEATHER)


def composite(src: Path, w: int, h: int, runs: list[Run], pieces: list[dict], outs: list[Path], dest: Path, png: Path,
              length: float) -> int:
    """The pieces' results into the clip under the soft mask -> dest (+ its last frame png). -> frames touched."""
    import cv2
    fixed: dict[int, tuple[Run, int, np.ndarray]] = {}   # the clip's frame -> (its run, the index in it, the result crop)
    for pc, out in zip(pieces, outs):
        run = runs[pc["run"]]
        frames = list(_frames(out, CROP, CROP))
        for i in range(min(pc["frames"], len(frames))):   # a result short by a few frames: those stay original
            fixed[run.first + pc["at"] + i] = (run, pc["at"] + i, frames[i])
    mask0 = _mask()
    wr = _Writer(dest, w, h, 14, audio_from=src, length=length)
    touched = 0
    try:
        for n, frame in enumerate(_frames(src, w, h)):
            if n in fixed:
                run, i, crop = fixed[n]
                x, y, s = run.boxes[i]
                strength = run.strength[i]
                if strength > 0 and s > 0:
                    orig = frame[y:y + s, x:x + s].astype(np.float32)
                    new = cv2.resize(crop, (s, s), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
                    m = cv2.resize(mask0, (s, s), interpolation=cv2.INTER_LINEAR)
                    inside = m > 0.35
                    if inside.any():
                        new += (orig[inside].mean(axis=0) - new[inside].mean(axis=0)) * COLOR_MATCH
                    a = (m * strength)[..., None]
                    frame = frame.copy()
                    frame[y:y + s, x:x + s] = np.clip(orig * (1 - a) + new * a, 0, 255).astype(np.uint8)
                    touched += 1
            wr.write(frame)
    finally:
        wr.close()
    _ffmpeg(["-sseof", "-0.5", "-i", str(dest), "-update", "1", str(png)])
    return touched


# ---------------------------------------------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------------------------------------------
def seconds(clip_seconds: float) -> float:
    """A guess until measured: Krea on ~1 anchor per 2/3 s, LTX's 3 steps on 512² per 5 s, the models' loading."""
    return 4 * max(1, clip_seconds * 1.5) + 12 * max(1.0, clip_seconds) / 5 + 40


def signature(mode: str, strength: float, text: str) -> str:
    """What besides the clip makes a result (the storyboard's fixed shot is `<key>.ff<signature>`): the settings, the
    words, the algorithm, the models' weights."""
    import hashlib
    parts = [mode, round(strength, 2), prompt_of(text), VERSION, config.LTX23_CKPT, config.LTX23_CLIP, config.LTX23_LORA,
             config.KREA_UNET, config.KREA_CLIP, config.KREA_VAE]
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:8]


async def make(job: jobs.Job, src: Path, mode: str, strength: float, seed: int, text: str, dest: Path, png: Path, label: str) -> dict:
    """The clip `src` with its far faces fixed into `dest` (+ its last frame `png`); `text` - who the person is (the
    hero's look), in front of the models' prompt. -> a note for the node: {faces: frames with a face, fixed: frames
    touched, runs, anchors}; written next to the result as .json."""
    return (await make_many(job, [{"src": src, "mode": mode, "strength": strength, "seed": seed, "text": text, "dest": dest,
                                   "png": png, "label": label}]))[0]


async def make_many(job: jobs.Job, items: list[dict], on_item=None) -> list[dict]:
    """Several clips at once ([{src, mode, strength, seed, text, dest, png, label}]), each model loaded once: the
    tracking and crops of all, Krea on every anchor, LTX on every piece, then the composites. `on_item(k, phase)` -
    the caller's progress per clip (phase: "track", "krea", "ltx", "done"). -> a note per clip (make)."""
    work = config.COMFY_INPUT
    notes: list[dict] = []
    jobs_: list[dict] = []   # the clips with faces: their runs, pieces, outs
    tell = on_item or (lambda k, ph: None)
    t0 = time.time()
    job.phase, job.step, job.steps = "analyzing", 0, 0
    for k, it in enumerate(items):
        tell(k, "track")
        meta = await asyncio.to_thread(probe, it["src"])
        w, h = meta["w"], meta["h"]
        runs, n = await asyncio.to_thread(track, it["src"], w, h, it["mode"])
        for run in runs:
            run.strength = [min(1.0, s * it["strength"]) for s in run.strength]
        note = {"version": VERSION, "frames": n, "faces": sum(len(r) for r in runs), "runs": len(runs), "anchors": 0, "fixed": 0,
                "seconds": {"track": round(time.time() - t0, 1)}}
        t0 = time.time()
        it["dest"].parent.mkdir(parents=True, exist_ok=True)
        notes.append(note)
        if not runs:   # nothing to fix: the clip as it is
            await asyncio.to_thread(shutil.copyfile, it["src"], it["dest"])
            await asyncio.to_thread(_ffmpeg, ["-sseof", "-0.5", "-i", str(it["dest"]), "-update", "1", str(it["png"])])
            it["dest"].with_suffix(".json").write_text(json.dumps(note), encoding="utf-8")
            tell(k, "done")
            continue
        job.phase = "encoding"
        pieces = await asyncio.to_thread(crops, it["src"], w, h, runs, it["dest"].stem)
        note["anchors"] = sum(len(pc["anchors"]) for pc in pieces)
        jobs_.append({"k": k, "it": it, "w": w, "h": h, "n": n, "runs": runs, "pieces": pieces, "outs": [], "note": note,
                      "prompt": prompt_of(it["text"])})
    try:
        for x in jobs_:
            tell(x["k"], "krea")
            t1 = time.time()
            await _krea_anchors(job, x["pieces"], x["it"]["seed"], x["prompt"])
            x["note"]["seconds"]["krea"] = round(time.time() - t1, 1)
        for x in jobs_:
            tell(x["k"], "ltx")
            t2 = time.time()
            x["outs"] = await _ltx_pieces(job, x["pieces"], x["it"]["seed"], x["prompt"])
            x["note"]["seconds"]["ltx"] = round(time.time() - t2, 1)
        job.phase = "saving"
        for x in jobs_:
            t3 = time.time()
            it = x["it"]
            x["note"]["fixed"] = await asyncio.to_thread(composite, it["src"], x["w"], x["h"], x["runs"], x["pieces"], x["outs"],
                                                         it["dest"], it["png"], x["n"] / FPS)
            x["note"]["seconds"]["composite"] = round(time.time() - t3, 1)
            it["dest"].with_suffix(".json").write_text(json.dumps(x["note"]), encoding="utf-8")
            tell(x["k"], "done")
    finally:
        keep = config.DATA_DIR / "facefix_debug"   # FACEFIX_KEEP=1: the crops, anchors and LTX results stay there to look at
        if os.environ.get("FACEFIX_KEEP"):
            keep.mkdir(parents=True, exist_ok=True)
        for x in jobs_:
            for f in list(work.glob(f"{x['it']['dest'].stem}*")) + list(x["outs"]):
                if os.environ.get("FACEFIX_KEEP"):
                    shutil.move(str(f), keep / f.name)
                else:
                    f.unlink(missing_ok=True)
    return notes


def saved(dest: Path) -> Optional[dict]:
    """A result's note, when it is there."""
    try:
        return json.loads(dest.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
