"""Checks of a shot, from remiqora-video render/checks.py: the clip's (phase 10, stage A - black, frozen, cut, blur,
face; below) and phase 11 (K5): «не поёт» - the voice sings but the lips stand still (`mute`).

Where the voice is in a clip's scene comes from the song's separated vocals (song.py, Demucs: lyrics/vocals.wav) - a
frame is voiced when the vocals there are louder than a quarter of their loud level over the clip's stretch - or,
without them, from the timed lines. The mouth is found in every voiced frame (YuNet's two mouth corners), cut out,
scaled to the face's own brightness and compared with the frame before: the mean change is the lips' motion.
Calibrated in remiqora-video on 16 LTX 2.3 clips labelled by eye (2026-10-08): standing lips 0.0015-0.013, singing
0.044-0.103; under MUTE_MOTION is «не поёт». Not judged with under a second of voice or without a face in most voiced
frames. A check is a bonus, never a blocker: anything going wrong is «not judged».

opencv-python-headless (Apache-2.0) and YuNet (OpenCV Zoo, Apache-2.0, ~230 KB, downloaded once to data/models/face).
"""
from __future__ import annotations

import functools
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np

from . import config
from . import i18n

FACE_DIR = config.DATA_DIR / "models" / "face"
YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
FACE_MIN_SCORE = 0.6
LIPS_WIDTH = 640          # the lips are measured at this width (at 320 a mid shot's mouth is a few pixels)
MUTE_MOTION = 0.025       # the lips' motion on the voice below this: not singing
MUTE_MIN_VOICE_S = 1.0    # less voice than this in a scene isn't judged
MUTE_FACE_SHARE = 0.6     # the face must be found in this share of the voiced frames
VOICED = 0.25             # a frame is voiced when the vocals are louder than this share of their loud level
VOICE_SR = 16000
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _yunet() -> str:
    dest = FACE_DIR / "yunet.onnx"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(YUNET_URL, tmp)
        tmp.rename(dest)
    return str(dest)


@functools.lru_cache(maxsize=1)
def _detector():
    import cv2   # only the lips check loads opencv
    return cv2, cv2.FaceDetectorYN_create(_yunet(), "", (320, 320), score_threshold=FACE_MIN_SCORE)


def _load(path: Path, start: float, length: float) -> np.ndarray:
    r = subprocess.run([config.FFMPEG, "-v", "error", "-ss", f"{max(start, 0):.4f}", "-t", f"{length:.4f}", "-i", str(path),
                        "-ac", "1", "-ar", str(VOICE_SR), "-f", "f32le", "-"], capture_output=True, creationflags=NO_WINDOW)
    return np.frombuffer(r.stdout, np.float32) if r.returncode == 0 else np.zeros(0, np.float32)


def _rms(x: np.ndarray, n: int) -> list[float]:
    hop = max(1, len(x) // max(n, 1))
    return [float(np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2))) if len(x[i * hop:(i + 1) * hop]) else 0.0 for i in range(n)]


@functools.lru_cache(maxsize=16)
def _vocal_level(vocals: str, mtime: float, start: float, end: float) -> float:
    """The loud level of the vocals over the clip's stretch (95th percentile of 1/24 s RMS)."""
    env = _rms(_load(Path(vocals), start, end - start), max(1, int((end - start) * 24)))
    return float(np.percentile(env, 95)) if env else 0.0


def voice_frames(vocals: Optional[Path], lines: list[dict], start: float, n_frames: int, fps: float,
                 stretch: tuple[float, float]) -> Optional[list[bool]]:
    """Where the voice is, a flag per frame of a scene starting at `start` (song time): from the vocals against their
    level over `stretch`, else from the lines; None without either."""
    if vocals is not None and vocals.exists():
        try:
            level = _vocal_level(str(vocals), vocals.stat().st_mtime, *stretch)
            env = _rms(_load(vocals, start, n_frames / fps), n_frames)
            if level > 0:
                return [bool(e > VOICED * level) for e in env]
        except Exception:  # noqa: BLE001 - the lines then
            pass
    if not lines:
        return None
    t = [start + (i + 0.5) / fps for i in range(n_frames)]
    return [any(l["start"] <= x < l["end"] for l in lines) for x in t]


def _mouth(cv2, detector, frame: np.ndarray) -> Optional[np.ndarray]:
    """The mouth of the most confident face, a small grey patch in units of the face's median brightness (light and
    size don't count), or None without a face."""
    _, faces = detector.detect(frame)
    faces = [x for x in (faces if faces is not None else []) if x[-1] >= FACE_MIN_SCORE]
    if not faces:
        return None
    x = max(faces, key=lambda r: r[-1])
    right, left = np.array(x[10:12]), np.array(x[12:14])   # YuNet: ... right mouth corner, left mouth corner, score
    d = float(np.linalg.norm(left - right))
    if d < 4:
        return None
    mx, my = (right + left) / 2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    fx, fy, fw, fh = (max(int(v), 0) for v in x[:4])
    face = gray[fy:fy + fh, fx:fx + fw]
    mouth = gray[max(int(my - 0.35 * d), 0):int(my + 0.55 * d), max(int(mx - 0.45 * d), 0):int(mx + 0.45 * d)]
    if face.size == 0 or mouth.size == 0:
        return None
    return cv2.resize(mouth, (24, 16)) / (float(np.median(face)) + 1.0)


def lip_motion(video: Path, n_frames: int, voice: list[bool], fps: float = 24.0) -> Optional[float]:
    """How much the lips move while the voice sings, or None when it can't be judged."""
    try:
        if sum(voice[:n_frames]) < MUTE_MIN_VOICE_S * fps:
            return None
        r = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(video)], capture_output=True, text=True, creationflags=NO_WINDOW)
        w, h = (int(v) for v in r.stdout.strip().split(",")[:2])
        # the mouth the size it was calibrated at (9:16, 640 wide): a wide frame is measured at that height, not width
        ww = max(LIPS_WIDTH, round(LIPS_WIDTH * w / h / 2) * 2)
        hh = max(2, round(h * ww / w / 2) * 2)
        r = subprocess.run([config.FFMPEG, "-v", "error", "-i", str(video), "-frames:v", str(n_frames),
                            "-vf", f"scale={ww}:{hh}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                           capture_output=True, creationflags=NO_WINDOW)
        frames = np.frombuffer(r.stdout, np.uint8).reshape(-1, hh, ww, 3)
        cv2, detector = _detector()
        detector.setInputSize((ww, hh))
        crops = [_mouth(cv2, detector, f) if v else None for f, v in zip(frames, voice)]
        seen = [c is not None for c, v in zip(crops, voice) if v]
        if not seen or sum(seen) / len(seen) < MUTE_FACE_SHARE:
            return None
        moves = [float(np.abs(a - b).mean()) for a, b in zip(crops, crops[1:]) if a is not None and b is not None]
        return float(np.mean(moves)) if moves else None
    except Exception:  # noqa: BLE001 - a check is a bonus, never a blocker
        return None


def mute(motion: Optional[float]) -> bool:
    return motion is not None and motion < MUTE_MOTION


# ---------------------------------------------------------------------------------------------------------------
# Phase 10, stage A: the clip's checks (remiqora-video render/checks.py) - what needed a person watching the draft.
#   black  - (near) black frames;  frozen - the picture stops moving for a while (the model stalled);
#   cut    - a jump inside the shot: a frame far from the one before it, many times the shot's usual motion;
#   blur   - the picture loses its detail against its first frame (smeared, or changed a lot: a close-up, turned away);
#   face   - the last frame's face doesn't look like the shot's reference (its start photo or frame; SFace).
# black / frozen / cut and a long, deep blur are severe: one retake with another seed (render.run, like «не поёт»).
# Frames small and grey through ffmpeg, numpy only, ~1 s a shot; kept next to the shot as <key>.checks.json.
# Thresholds: remiqora-video's (LTX 2.3 and WAN, labelled by eye there), checked on 700 shots of this cache (H3, LTX
# 2.5 / 2.3, 2026-10-23, by eye): every `cut` looked at was a real cut inside the shot (a man in a street becomes a robot
# in a desert, a motorbike a biker, a two-shot a close-up) but one - a flash of light; `black` was only dark night scenes
# (BLACK_* tightened); one `frozen` was a singer standing still - the lips' check drops it (render.run).
# ---------------------------------------------------------------------------------------------------------------
import hashlib  # noqa: E402
import json  # noqa: E402
from dataclasses import asdict, dataclass  # noqa: E402

CHECKS_VERSION = 2        # 2: `hero` - the face against the hero's portrait, `still`
WIDTH = 320               # decode width; sharpness is measured at this scale
BLUR_RATIO = 0.35         # a stretch this much softer than the first frame...
BLUR_DIP = 0.6            # ...and softer than the shot's own median by this much (a dip, not the whole shot)
BLUR_STRONG = 0.15        # this soft next to the first frame counts on its own
BLUR_MIN_S = 0.5          # ...for at least this long
BLUR_SEVERE_RATIO = 0.12  # this soft for BLUR_SEVERE_S: smeared or lost - a retake
BLUR_SEVERE_S = 1.0
BLACK_LUMA = 4.0          # mean luma (0-255) below this with the brightest 1 % below BLACK_BRIGHT is a black frame.
BLACK_BRIGHT = 20.0       # remiqora-video's 12 / 48 flagged 9 of 700 shots here - all of them deliberately dark night
                          # scenes (a man in the rain at luma 5, a door in the dark, a lighthouse at night; 2026-10-23)
BLACK_MIN_S = 0.25
FROZEN_DIFF = 0.25        # mean abs difference (0-255) between frames below this is no motion
FROZEN_MIN_S = 1.5
CUT_DIFF = 28.0           # a frame-to-frame jump above this...
CUT_TIMES_MEDIAN = 8.0    # ...and this many times the shot's median motion is a cut
FACE_COSINE_MIN = 0.12    # SFace cosine below this: the shot's face isn't its reference's (remiqora-video's calibration)
# `hero` (severe): the shot's face against the hero's own portrait, the median of FACE_AT's frames - a continuation's
# last frame or a frame drawn unlike her let the face drift from her unseen (a test clip's
# shots at 0.082 and 0.019 went into the video). A wide shot's small face isn't judged; FRAME_FACE_MIN is the frames' own line
HERO_MIN = {"close": 0.3, "medium": 0.3}
FACE_AT = (0.0, 0.25, 0.5, 0.75, 1.0)
FACE_SEEN = 3             # the face judged in at least this many of them, else not judged (turned away, two people)
# `still` (not severe): the median motion of a shot with people below this - an almost still picture (LTX singing from
# its frame with a static camera or a push-in). The median frame-to-frame difference at WIDTH, measured on 100 shots
# of 7 projects (2026-10-30): H3 perform 4.3-14.8 (median 9.7), LTX 2.3 sing 0.5-13.8 (p25 2.7, median 4.1); the
# audit's «almost a still» Golden Hour singers 2.2-2.9 here. A quarter of LTX's singers fall under it, no H3 shot
STILL_DIFF = 3.0
# ...but the line was too strict to say: singing close-ups at 0.5-2.9 looked normal by eye, and on an anime clip it
# marked 12 scenes of 18 (cel-shading and flat fills move few pixels). STILL_DIFF stays what a shot's check records
# (the measure kept next to it); a `still` counts only below STILL_LINE of the scene's framing - a stylized picture
# (anime, cartoon, 3D animation: prompts.stylized) at STILL_STYLIZED of it - and it is a quiet note: grey on the board,
# not among the notes, never a retake but a singer's (render.still_retake). Applied when read, so the shots checked
# before follow it without being checked again. The cache's flagged values 2026-11-01: close sing 0.45-2.9 (40 of 62),
# medium perform 0.9-2.6, anime 0.14-2.7
STILL_LINE = {"close": 0.5, "medium": 1.0, "wide": 1.0}
STILL_STYLIZED = 0.5


def still_line(framing: Optional[str], stylized: bool = False) -> float:
    """The motion below which a shot of this framing counts as almost still (`still`)."""
    return STILL_LINE.get(framing or "", STILL_LINE["medium"]) * (STILL_STYLIZED if stylized else 1.0)


def calm(problems, framing: Optional[str], stylized: bool = False):
    """The problems without a `still` above the scene's line (Problem objects or their public dicts); a kept `still`
    dict says its line (`line`), so the board can say «движение 0,4 при норме от 0,5»."""
    if problems is None:
        return None
    line = still_line(framing, stylized)
    out = []
    for p in problems:
        code, value = (p.get("code"), p.get("value")) if isinstance(p, dict) else (p.code, p.value)
        if code == "still":
            if value is not None and float(value) >= line:
                continue
            if isinstance(p, dict):
                p = {**p, "line": round(line, 2), "quiet": True}
        out.append(p)
    return out


SFACE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
_NAMES = {"black": ("чёрные кадры", "black frames"), "frozen": ("замерло", "frozen"), "cut": ("скачок внутри сцены", "a jump inside the scene"),
          "blur": ("смаз или сильно изменилось", "blurred or changed a lot"), "face": ("лицо не похоже", "the face is not alike"),
          "mute": ("не поёт", "not singing"), "hero": ("лицо не как у героя", "the face is not the hero's"),
          "still": ("почти не движется", "almost still"), "frame": ("кадр не похож на героя", "the frame is not like the hero")}


def name(code: str) -> str:
    """A problem's name in the interface's language."""
    return i18n.L(*_NAMES[code]) if code in _NAMES else code


@dataclass
class Problem:
    code: str      # black | frozen | cut | blur | face
    at: float      # seconds into the shot
    length: float  # seconds (0 for a cut or a face)
    value: float   # the measure that tripped it

    def to_dict(self) -> dict:
        return {k: round(float(v), 3) if k != "code" else v for k, v in asdict(self).items()}

    @property
    def severe(self) -> bool:
        if self.code == "blur":
            return self.value < BLUR_SEVERE_RATIO and self.length >= BLUR_SEVERE_S
        return self.code in ("black", "frozen", "cut", "hero")


def load_gray(video: Path) -> tuple[np.ndarray, float]:
    """Every frame, grey, WIDTH wide: (n, h, w) float32 0..255, and the fps."""
    r = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True, creationflags=NO_WINDOW)
    w, h, rate = r.stdout.strip().split(",")[:3]
    num, _, den = rate.partition("/")
    fps = float(num) / float(den or 1)
    hh = max(2, round(int(h) * WIDTH / int(w) / 2) * 2)
    r = subprocess.run([config.FFMPEG, "-v", "error", "-i", str(video), "-vf", f"scale={WIDTH}:{hh}:flags=area",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, creationflags=NO_WINDOW)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, hh, WIDTH).astype(np.float32), fps


def measure(frames: np.ndarray) -> dict:
    f = frames
    lap = -4 * f[:, 1:-1, 1:-1] + f[:, :-2, 1:-1] + f[:, 2:, 1:-1] + f[:, 1:-1, :-2] + f[:, 1:-1, 2:]
    flat = f.reshape(len(f), -1)
    return {"sharp": lap.reshape(len(f), -1).var(axis=1), "luma": flat.mean(axis=1),
            "bright": np.percentile(flat, 99, axis=1),   # the highlights: a dark scene has them, a black frame doesn't
            "diff": np.abs(np.diff(f, axis=0)).reshape(len(f) - 1, -1).mean(axis=1) if len(f) > 1 else np.zeros(0, np.float32)}


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    out, start = [], None
    for i, v in enumerate(list(mask) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((start, i - start))
            start = None
    return out


def find_problems(m: dict, fps: float) -> list[Problem]:
    sharp, luma, diff = m["sharp"], m["luma"], m["diff"]
    problems: list[Problem] = []
    if len(sharp) < 2:
        return problems
    black = (luma < BLACK_LUMA) & (m["bright"] < BLACK_BRIGHT)
    for s, k in _runs(black, max(1, round(BLACK_MIN_S * fps))):
        problems.append(Problem("black", s / fps, k / fps, float(luma[s:s + k].mean())))
    ref = float(sharp[0])
    if ref > 1.0:
        to_first, to_shot = sharp / ref, sharp / (float(np.median(sharp)) + 1e-6)
        soft = (((to_first < BLUR_RATIO) & (to_shot < BLUR_DIP)) | (to_first < BLUR_STRONG)) & ~black
        for s, k in _runs(soft, max(1, round(BLUR_MIN_S * fps))):
            problems.append(Problem("blur", s / fps, k / fps, float(np.median(sharp[s:s + k]) / ref)))
    if len(diff):
        for s, k in _runs(diff < FROZEN_DIFF, max(1, round(FROZEN_MIN_S * fps))):
            if not black[s:s + k + 1].all():
                problems.append(Problem("frozen", s / fps, (k + 1) / fps, float(diff[s:s + k].mean())))
        typical = float(np.median(diff)) + 1e-3
        for i in np.flatnonzero((diff > CUT_DIFF) & (diff > CUT_TIMES_MEDIAN * typical)):
            if not (black[i] or black[i + 1]):
                problems.append(Problem("cut", float(i + 1) / fps, 0.0, float(diff[i])))
    return sorted(problems, key=lambda p: p.at)


def _sface() -> str:
    dest = FACE_DIR / "sface.onnx"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        urllib.request.urlretrieve(SFACE_URL, tmp)
        tmp.rename(dest)
    return str(dest)


@functools.lru_cache(maxsize=1)
def _recognizer():
    import cv2
    return cv2.FaceRecognizerSF_create(_sface(), "")


def _confident_faces(image: np.ndarray) -> list:
    """YuNet's faces with a confident score (a row: x, y, w, h, five landmarks, the score)."""
    _, detector = _detector()
    detector.setInputSize((image.shape[1], image.shape[0]))
    _, faces = detector.detect(image)
    return [f for f in (faces if faces is not None else []) if f[-1] >= FACE_MIN_SCORE]


def _face_feature(image: np.ndarray):
    """The embedding of the one confident face in `image`; more than one isn't judged (two people: which is whose?)."""
    faces = _confident_faces(image)
    if len(faces) != 1:
        return None
    rec = _recognizer()
    return rec.feature(rec.alignCrop(image, faces[0]))


@functools.lru_cache(maxsize=1)
def _still_detector():
    """A detector of its own for a photo's crop (render.start_crop): the lips check's one is fed by another thread and
    its input size is its own state."""
    import cv2
    return cv2.FaceDetectorYN_create(_yunet(), "", (320, 320), score_threshold=FACE_MIN_SCORE)


def face_picture(path: Path) -> tuple[Optional[tuple[int, int, int, int]], Optional[tuple[int, int]]]:
    """A photo's one confident face (x, y, w, h in its pixels) and the photo's size: (None, size) when there is no face
    or more than one (a group: which face is whose?), (None, None) when it can't be read. The photo is the one
    cv2.imread returns, EXIF rotation and all - the same picture render.fit_frame crops."""
    try:
        import cv2
        img = cv2.imread(str(path))
    except Exception:  # noqa: BLE001 - a crop is a bonus, never a blocker
        return None, None
    if img is None:
        return None, None
    h, w = img.shape[:2]
    try:
        detector = _still_detector()
        detector.setInputSize((w, h))
        _, rows = detector.detect(img)
    except Exception:  # noqa: BLE001 - YuNet is downloaded on the first call: no net, no crop
        return None, (w, h)
    faces = [f for f in (rows if rows is not None else []) if f[-1] >= FACE_MIN_SCORE]
    if len(faces) != 1:
        return None, (w, h)
    x, y, fw, fh = (round(float(v)) for v in faces[0][:4])
    return (x, y, fw, fh), (w, h)


def face_similarity(video: Path, reference: Path) -> Optional[float]:
    """SFace cosine of the reference's face and the clip's last frame's face; None when not judged."""
    try:
        import cv2
        ref = cv2.imread(str(reference))
        a = _face_feature(ref) if ref is not None else None
        if a is None:
            return None
        r = subprocess.run([config.FFMPEG, "-v", "error", "-sseof", "-0.1", "-i", str(video), "-frames:v", "1", "-f", "image2pipe",
                            "-vcodec", "png", "-"], capture_output=True, creationflags=NO_WINDOW)
        frame = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR) if r.stdout else None
        b = _face_feature(frame) if frame is not None else None
        return None if b is None else float(_recognizer().match(a, b, cv2.FaceRecognizerSF_FR_COSINE))
    except Exception:  # noqa: BLE001 - a check is a bonus, never a blocker
        return None


def frames_at(video: Path, at: tuple[float, ...] = FACE_AT) -> list[np.ndarray]:
    """The shot's frames at these shares of its length (0 - the first, 1 - the last), full size, BGR."""
    r = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True, creationflags=NO_WINDOW)
    w, h, n = (int(v) for v in r.stdout.strip().split(",")[:3])
    idx = sorted({min(n - 1, round(a * (n - 1))) for a in at})
    pick = "+".join(f"eq(n,{i})" for i in idx)
    r = subprocess.run([config.FFMPEG, "-v", "error", "-i", str(video), "-vf", f"select='{pick}'", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, creationflags=NO_WINDOW)
    return list(np.frombuffer(r.stdout, np.uint8).reshape(-1, h, w, 3))


def hero_similarity(video: Path, portrait: Path) -> Optional[float]:
    """SFace cosine of the hero's portrait and the shot's face: the median over FACE_AT's frames that show one face;
    None when the portrait has none or fewer than FACE_SEEN frames do."""
    try:
        import cv2
        ref = cv2.imread(str(portrait))
        a = _face_feature(ref) if ref is not None else None
        if a is None:
            return None
        scores = []
        for f in frames_at(video):
            b = _face_feature(np.ascontiguousarray(f))
            if b is not None:
                scores.append(float(_recognizer().match(a, b, cv2.FaceRecognizerSF_FR_COSINE)))
        return float(np.median(scores)) if len(scores) >= FACE_SEEN else None
    except Exception:  # noqa: BLE001 - a check is a bonus, never a blocker
        return None


def motion(m: dict) -> Optional[float]:
    """The shot's typical motion: the median frame-to-frame difference (`still` below STILL_DIFF)."""
    return float(np.median(m["diff"])) if len(m["diff"]) else None


def check_clip(video: Path, reference: Optional[Path] = None, hero: Optional[Path] = None, framing: Optional[str] = None,
               people: bool = False) -> list[Problem]:
    """The problems of a shot, kept next to it (<key>.checks.json); `reference` - the face it should keep (a start
    photo, the last frame a continuation starts from, a Ref2VA photo) - adds the face check. `hero` - the portrait of
    the one hero in the scene: the face is judged against it instead (`hero`, severe; `framing` - a wide shot's isn't
    judged). `people`: a scene with someone in it - an almost still shot is `still`. Never raises: a shot that can't be
    read has no problems."""
    side = video.with_suffix(".checks.json")
    judge = bool(hero and hero.exists() and framing in HERO_MIN)
    face_sig = (f"hero:{hashlib.sha1(hero.read_bytes()).hexdigest()[:12]}:{framing}" if judge
                else hashlib.sha1(reference.read_bytes()).hexdigest()[:12] if reference and reference.exists() else "")
    sig = face_sig + (":people" if people else "")
    try:
        saved = json.loads(side.read_text(encoding="utf-8"))
        if saved.get("version") == CHECKS_VERSION and saved.get("face_sig", "") == sig:
            return [Problem(**p) for p in saved["problems"]]
    except (OSError, ValueError, TypeError, KeyError):
        pass
    try:
        frames, fps = load_gray(video)
        m = measure(frames)
        problems = find_problems(m, fps)
        if people and (mo := motion(m)) is not None and mo < STILL_DIFF:
            problems.append(Problem("still", 0.0, len(frames) / fps, mo))
        score = hero_similarity(video, hero) if judge else None
        if score is not None and score < HERO_MIN[framing]:
            problems.append(Problem("hero", 0.0, 0.0, score))
        # the portrait's face not found (a stylized portrait) or the face seen too seldom: the start frame's check as
        # before, so a scene is never left with no face check at all
        if score is None and reference and reference.exists():
            score = face_similarity(video, reference)
            if score is not None and score < FACE_COSINE_MIN:
                problems.append(Problem("face", (len(frames) - 1) / fps, 0.0, score))
    except Exception:  # noqa: BLE001
        return []
    problems.sort(key=lambda p: p.at)
    try:
        side.write_text(json.dumps({"version": CHECKS_VERSION, "face_sig": sig, "problems": [p.to_dict() for p in problems]}),
                        encoding="utf-8")
    except OSError:
        pass
    return problems


def saved(video: Path) -> Optional[list[dict]]:
    """The checks kept next to a shot (public form), None when it was never checked. A shot checked by an older
    version keeps what it found then (check_clip checks only a new shot)."""
    try:
        d = json.loads(video.with_suffix(".checks.json").read_text(encoding="utf-8"))
        return public([Problem(**p) for p in d["problems"]]) if 1 <= int(d.get("version") or 0) <= CHECKS_VERSION else None
    except (OSError, ValueError, TypeError, KeyError):
        return None


def severe(problems: list[Problem]) -> bool:
    return any(p.severe for p in problems)


def badness(problems: list[Problem]) -> float:
    """For picking the better of two takes (remiqora-video chain._badness): a severe one weighs most; `still` (the
    whole shot's length) weighs as one light problem - an 8 s calm shot weighed almost as much as a severe one."""
    return sum((10 if p.severe else 1) + (0 if p.code == "still" else p.length) for p in problems)


def better(a: list[Problem], b: list[Problem]) -> bool:
    """Whether take `a` is better than `b`: fewer and lighter problems; alike - the face closer to the hero's and the
    livelier shot (`hero` and `still` carry their measure)."""
    if badness(a) != badness(b):
        return badness(a) < badness(b)
    val = lambda ps, code: next((p.value for p in ps if p.code == code), None)  # noqa: E731
    for code in ("hero", "still"):
        x, y = val(a, code), val(b, code)
        if x is not None and y is not None and x != y:
            return x > y
    return False


def public(problems: list[Problem]) -> list[dict]:
    """The board's form: `quiet` - a note to glance at, not a fault (`still`); `line` - the measure's line where the
    note says it (the hero's face: the similarity it must reach)."""
    return [{**p.to_dict(), "name": name(p.code), "severe": p.severe, **({"quiet": True} if p.code == "still" else {}),
             **({"line": HERO_MIN.get("close")} if p.code == "hero" else {})} for p in problems]
