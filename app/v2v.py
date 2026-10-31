"""«Видео → видео» (the graph's v2v node): a clip made again by a LoRA that reads the clip itself, not a text.

Two kinds of such LoRA, one node for both (the user, 2026-10-23: «нужен универсальный узел для таких LoRA»):
- LTX IC-LoRA, 2.5 (Lightricks' Alpha-Gen, Restore, Deblur, Clean-Plate…) and 2.3 (3DREAL, CrossView, upscalers…;
  the user, the same day: «нужно сделать IC lora и для 2.3»): the clip is a guide of the latent (LTXVAddGuide), the
  result has its frames one for one. The file says it is one: `reference_downscale_factor` in its metadata, or
  "ic-lora" in its name; the version is the folder it lies in. A factor n > 1: the clip goes in at 1/n of the
  result's size (the size then divides by 32 * n).
- H3 Ref2VA LoRA (Character-Swap, Person-Remover…): the clip is <Video 1> of Ref2VA with its sound, pictures
  <Picture 1>…, the prompt says what to do. Known by name (BUILTIN) or by a profile next to the file.

- LTX 2.3 ID-LoRA (TalkVid): a new shot of a person from a photo (the scene's start) and a voice sample - the
  face and the voice held (template video_ltx2_3_id_lora: LTXVReferenceAudio). It reads no clip: it is a scene's.

Since 2026-10-23 (the user: «Сцена принимает образцы (клип, голос), поведение — по профилю LoRA») a Scene takes any of
them in its «LoRA» input, with its «клип» / «голос» inputs (graph._evaluate_ref_scene); «Видео → видео» stays for
the clip-reading ones. As a plain LoRA such a file makes a flat picture (Alpha-Gen drew a grey mask of nothing), so
loras.for_model keeps them out of the plain LoRA a shot gets.

A LoRA's profile says how to run it: the BUILTIN one by its file name (from the model cards), then `<name>.v2v.json`
next to the file over it, field by field:
  reads       clip | voice   what it reads besides the prompt: a clip (IC-LoRA, Ref2VA), or a photo + a voice (ID-LoRA)
  identity    voice: how strongly the voice is held (LTXVReferenceAudio's identity_guidance_scale; 0 - no extra pass)
  voice_secs  voice: the sample's seconds (ID-LoRA was trained on ~5)
  prompt      none | optional | required    (Alpha-Gen: none - the card says an empty prompt, always)
  template    the prompt when the node has none (H3: <Video 1> must be in it - it is put in front when it is not)
  lead        the LoRA's trigger: the prompt starts with it, it is put in front when it does not (3DREAL: "3DREAL.")
  scale       1 | 2 | 4   the result's size to the clip's (an upscaler: its reference_downscale_factor)
  stages      1 | 2   LTX: one stage at the full size (the guide stays on all the way), or half size + x2 + full
  out         video | matte   a matte (white = the object) -> the clip with that alpha (WebM VP9) + the mask (MP4)
  max_frames  longer clips go in pieces of at most this (LTX: 8n+1 each), glued back
  sound       source | model   whose sound the result has: the clip's, or what the model made (H3)

The run: the clip padded (never stretched) to the model's step and grid, through the graph, cropped back, the
pieces glued, the sound put back; a matte also merged with the clip as its alpha.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from . import config, i18n, jobs, videomodels
from .engine import graphs, other_graphs
from .engine.comfy import COMFY, EngineError, output_files

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ENGINES = ("ltx25", "ltx23", "h3")   # whose LoRA folders hold such files
LTX = ("ltx25", "ltx23")
FPS = 24

_BASE = {"reads": "clip", "template": "", "lead": "", "scale": 1, "stages": 1, "out": "video", "sound": "source"}
ID_TEMPLATE = ("[VISUAL]: A medium shot of the person speaking to the camera, their mouth moving naturally.\n"
               "[SPEECH]: Hello.\n[SOUNDS]: A calm conversational tone at moderate volume, close to the microphone.")
DEFAULT = {
    "ltx25": {**_BASE, "prompt": "optional", "max_frames": 241},
    "ltx23": {**_BASE, "prompt": "optional", "max_frames": 161},
    "h3": {**_BASE, "prompt": "required", "template": "Remake <Video 1>.", "max_frames": 365},
}
UPSCALER = 0   # BUILTIN's scale of an upscaler: its reference_downscale_factor (x2 or x4 by the file)
# (engine, a pattern of the file's name, what differs from DEFAULT, a line for the user (ru, en)); from the model cards
BUILTIN: list[tuple[str, str, dict, tuple[str, str]]] = [
    ("ltx25", r"alpha[-_ ]?gen", {"prompt": "none", "stages": 1, "out": "matte", "max_frames": 145},
     ("Маска объекта (белое — объект, чёрное — фон) и клип с прозрачным фоном. Без промта, до 145 кадров за раз.",
      "An object mask (white is the object, black the background) and the clip with a transparent background. No prompt, "
      "up to 145 frames at a time.")),
    ("ltx23", r"3dreal", {"prompt": "required", "lead": "3DREAL.", "template": "3DREAL. Make it photorealistic."},
     ("3D-рендер, игровой или CG-клип → фотореалистичное видео: кадр и движение камеры те же. В промте — каким должен "
      "стать кадр; он начинается с 3DREAL.",
      "A 3D render, game or CG clip → photoreal video: the same frame and camera motion. The prompt says what the frame "
      "should become; it starts with 3DREAL.")),
    ("ltx23", r"crossview[-_ ]?prompt", {"prompt": "required", "lead": "crossview.",
                                         "template": "crossview. new camera angle: slightly to the right, same height, same distance."},
     ("Та же сцена с другой точки съёмки. Промт — только словами из словаря LoRA: «crossview. new camera angle: "
      "<slightly to the left / to the left / far to the left / same angle / …right>, <lower / same height / higher>, "
      "<closer / same distance / further>.» Шаг за раз — небольшой. Учили на полной 2.3: силу LoRA ставят 1.2–1.5.",
      "The same scene from another viewpoint. The prompt uses only the LoRA's vocabulary: «crossview. new camera angle: "
      "<slightly to the left / to the left / far to the left / same angle / …right>, <lower / same height / higher>, "
      "<closer / same distance / further>.» Keep each step small. Trained on the full 2.3: set the LoRA strength to 1.2–1.5.")),
    ("ltx23", r"upscal", {"prompt": "optional", "scale": UPSCALER, "max_frames": 121},
     ("Апскейл: клип больше по каждой стороне, детали дорисовываются. Не убирает шум и артефакты.",
      "Upscale: the clip gets larger on each side, details are filled in. Does not remove noise or artifacts.")),
    ("ltx23", r"(^|[-_ .])id[-_ ]?lora|talkvid", {"reads": "voice", "prompt": "required", "template": ID_TEMPLATE, "stages": 2,
                                                   "sound": "model", "identity": 3.0, "voice_secs": 5.0},
     ("Говорящий герой: лицо — с фото во входе «старт», голос — с образца во входе «голос» (лучше 5 с чистой речи). "
      "Промт из трёх частей: [VISUAL] — кадр и человек, [SPEECH] — точные слова, [SOUNDS] — манера речи и фон. "
      "Реплики узла «Промт» сами станут [SPEECH]. Снимает LTX 2.3.",
      "A talking hero: the face from the photo in the «start» input, the voice from the sample in the «voice» input "
      "(5 s of clean speech is best). A prompt in three parts: [VISUAL] the frame and the person, [SPEECH] the exact words, "
      "[SOUNDS] the manner of speech and the background. The «Prompt» node's spoken lines become [SPEECH] by themselves. "
      "Shot by LTX 2.3.")),
    ("h3", r"character[-_ ]?swap", {"prompt": "required", "template":
        "Replace the person in <Video 1> with the character in <Picture 1>. Keep the reference character's face, hair and "
        "clothing. Follow the source performance's pose, gaze, expression and movement. Preserve the scene and the other people."},
     ("Меняет человека в клипе на персонажа с картинки («картинка» → <Picture 1>).",
      "Replaces the person in the clip with the character from the picture («picture» → <Picture 1>).")),
    ("h3", r"person[-_ ]?remover", {"prompt": "optional", "template":
        "Remove the person from <Video 1>. Keep the background, the camera movement and the lighting as they are."},
     ("Убирает человека из клипа.", "Removes the person from the clip.")),
]
FIELDS = {"prompt": ("none", "optional", "required"), "stages": (1, 2), "out": ("video", "matte"), "sound": ("source", "model"),
          "scale": (1, 2, 4), "reads": ("clip", "voice")}
NEUTRAL = {"lead": "", "scale": 1, "ref_down": 1, "reads": "clip"}   # left out of a result's key: results made before these fields stay


def _sidecar(path: Path) -> Optional[dict]:
    p = path.with_name(path.stem + ".v2v.json")
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _builtin(model: str, name: str) -> Optional[tuple[dict, str]]:
    for eng, pat, prof, note in BUILTIN:
        if eng == model and re.search(pat, name, re.I):
            return prof, i18n.L(*note)
    return None


def is_v2v(path: Path, model: str, meta: dict) -> bool:
    """Does this LoRA read a clip (loras.inspect asks for every file)?"""
    if model not in ENGINES:
        return False
    if _sidecar(path) is not None or _builtin(model, path.stem):
        return True
    return model in LTX and (any(k.endswith("reference_downscale_factor") for k in meta)
                             or bool(re.search(r"ic[-_ ]?lora", path.stem, re.I)))


def ref_down(meta: dict) -> int:
    """An IC-LoRA's reference_downscale_factor, as GetICLoRAParameters reads it (1 when there is none)."""
    try:
        return max(1, round(float(next(v for k, v in meta.items() if k.endswith("reference_downscale_factor")))))
    except (StopIteration, TypeError, ValueError):
        return 1


def profile(info) -> dict:
    """A v2v LoRA's profile (loras.LoraInfo): DEFAULT of its engine, BUILTIN by name, its .v2v.json over them."""
    p = {**DEFAULT[info.model], "engine": info.model, "note": "", "own": False, "ref_down": 1}
    if (b := _builtin(info.model, info.name)):
        p.update(b[0])
        p["note"] = b[1]
    if (s := _sidecar(info.path)):
        p["own"] = True
        for k, v in s.items():
            if k in FIELDS and v in FIELDS[k] or k in ("template", "lead", "note") and isinstance(v, str):
                p[k] = v
            elif k == "max_frames" and isinstance(v, int) and v >= 9:
                p[k] = v
            elif k in ("identity", "voice_secs") and isinstance(v, (int, float)) and 0 <= v <= 100:
                p[k] = float(v)
    if p["reads"] == "voice":   # a scene of its own: LTX's two stages, its own sound
        p.update(stages=2, scale=1, sound="model", identity=p.get("identity", 3.0), voice_secs=p.get("voice_secs", 5.0))
        return p
    if p["engine"] == "h3":
        p["stages"], p["scale"] = 1, 1
    else:
        p["ref_down"] = info.ref_down
        if p["scale"] == UPSCALER:
            p["scale"] = info.ref_down if info.ref_down in FIELDS["scale"] else 2
    return p


def key_of(prof: dict) -> dict:
    """What of a profile makes a result: not its words, nor the fields at their neutral value (graph.py's key)."""
    return {k: v for k, v in prof.items() if k not in ("note", "own", "template") and not (k in NEUTRAL and v == NEUTRAL[k])}


def known(info) -> bool:
    """Is there a profile beyond the engine's defaults (the node warns when there is none)?"""
    return bool(_builtin(info.model, info.name)) or _sidecar(info.path) is not None


def prompt_of(prof: dict, text: str) -> str:
    """What the model gets: the node's prompt or the profile's template; none for a LoRA trained on an empty one;
    H3 always names the clip <Video 1>; a LoRA with a trigger gets it in front."""
    if prof["prompt"] == "none":
        return ""
    text = (text or "").strip() or prof["template"]
    if prof["engine"] == "h3" and "<Video 1>" not in text:
        text = "<Video 1>. " + text
    if prof.get("lead") and not text.lower().startswith(prof["lead"].lower()):
        text = f"{prof['lead']} {text}"
    return text


_TAG = re.compile(r"\[(VISUAL|SPEECH|SOUNDS)\]\s*:", re.I)


def id_prompt(text: str, lines: list[dict]) -> str:
    """ID-LoRA's three-part prompt: as the user wrote it when it has the [VISUAL] / [SPEECH] / [SOUNDS] tags; else the
    prompt is [VISUAL], the «Промт» node's spoken lines are [SPEECH] and their manner [SOUNDS]."""
    text = (text or "").strip()
    if _TAG.search(text):
        return text
    speech = " ".join(x.get("text", "").strip() for x in lines or [] if x.get("text"))
    how = "; ".join(x.get("how", "").strip() for x in lines or [] if x.get("how"))
    text = text or "A medium shot of the person speaking to the camera."
    text += "" if text[-1] in ".!?" else "."
    return (f"[VISUAL]: {text} The person is speaking, their mouth "
            f"moving naturally.\n[SPEECH]: {speech or '…'}\n[SOUNDS]: {how or 'A natural conversational tone'}, close to the "
            f"microphone.")


def seconds(prof: dict, clip_seconds: float) -> float:
    """How long making it takes, until measured: the model's own scene time for that length (one stage of LTX ~ the
    two of a scene at the full size; an upscaler's result has scale² the pixels), Ref2VA as a draft of H3 at the
    final size."""
    c = videomodels.card(prof["engine"])
    per5 = c.base["final"] * (0.8 if prof["engine"] in LTX and prof["stages"] == 1 else 1.0) * prof.get("scale", 1) ** 2
    return per5 * max(1.0, clip_seconds) / 5 + 20


# ---------------------------------------------------------------------------------------------------------------
# ffmpeg
# ---------------------------------------------------------------------------------------------------------------
def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run([config.FFMPEG, "-y", "-v", "error", *args], capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode:
        raise EngineError("ffmpeg: " + (r.stderr or "").strip()[-800:])


def probe(p: Path) -> dict:
    """{w, h, frames, sound} of a clip."""
    r = subprocess.run([config.FFPROBE, "-v", "error", "-count_packets", "-show_entries",
                        "stream=codec_type,width,height,nb_read_packets", "-of", "json", str(p)],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    try:
        streams = json.loads(r.stdout)["streams"]
        v = next(s for s in streams if s["codec_type"] == "video")
        return {"w": int(v["width"]), "h": int(v["height"]), "frames": int(v["nb_read_packets"]),
                "sound": any(s["codec_type"] == "audio" for s in streams)}
    except (ValueError, KeyError, StopIteration) as e:
        raise EngineError(i18n.L(f"Не прочитать клип {p.name}", f"Cannot read the clip {p.name}")) from e


def _up(v: int, step: int) -> int:
    return -(-v // step) * step


def _pieces(n: int, most: int, grid: tuple[int, int]) -> list[tuple[int, int, int]]:
    """A clip of n frames in pieces of at most `most`: [(first, frames, frames padded to the model's grid)]."""
    m, r = grid
    most = max(m + r, most - (most - r) % m)
    out, at = [], 0
    while at < n:
        k = min(most, n - at)
        padded = max(m + r, k)
        while padded % m != r:
            padded += 1
        out.append((at, k, padded))
        at += k
    return out


# ---------------------------------------------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------------------------------------------
async def make(job: jobs.Job, src: Path, info, prof: dict, strength: float, guide: float, seed: int, text: str,
               pictures: list[Path], extra: list[dict], dest: Path, png: Path, alpha: Optional[Path], label: str) -> None:
    """The clip `src` made again by the v2v LoRA `info` into `dest` (+ its last frame `png`); a matte LoRA: `dest` is the
    mask (with the clip's sound) and `alpha` the clip with that mask as its alpha (WebM). `extra`: plain LoRA of the
    same engine on top ([{id, strength}])."""
    eng = prof["engine"]
    meta = await asyncio.to_thread(probe, src)
    if meta["frames"] < 9:
        raise EngineError(i18n.L(f"{label}: клип слишком короткий", f"{label}: the clip is too short"))
    tag = dest.stem   # v2v_<key>: its files in ComfyUI's input
    work = config.COMFY_INPUT
    job.phase, job.step, job.steps = "starting", 0, 0
    loras = [*extra, {"id": info.id, "strength": strength}]   # the IC-LoRA last: GetICLoRAParameters reads the last loader
    names = await jobs.engine(job, eng, loras, ref=eng == "h3")
    outs: list[tuple[Path, int]] = []   # the made pieces and their real frames
    try:
        if eng in LTX:
            # the latent (1/32 of the size, half that in a two-stage first pass) must divide by the reference's factor
            step = 32 * prof["stages"] * prof["ref_down"]
            s = prof["scale"]
            W, H = _up(meta["w"] * s, step), _up(meta["h"] * s, step)
            size = f"scale={meta['w'] * s}:{meta['h'] * s}:flags=lanczos," if s > 1 else ""   # LTXVAddGuide brings it down to 1/n again
            parts = _pieces(meta["frames"], prof["max_frames"], (8, 1))
            for k, (at, n, padded) in enumerate(parts):
                name = f"{tag}_{k}.mp4"
                job.phase = "encoding"
                await asyncio.to_thread(_ffmpeg, ["-i", str(src), "-vf",
                                                  f"trim=start_frame={at}:end_frame={at + n},setpts=PTS-STARTPTS,{size}"
                                                  f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,tpad=stop_mode=clone:stop={padded - n},fps={FPS}",
                                                  "-an", "-c:v", "libx264", "-crf", "10", "-preset", "fast", "-pix_fmt", "yuv420p",
                                                  str(work / name)])
                g = other_graphs.ltx_ic(eng, prompt_of(prof, text), W, H, padded, seed, f"h3studio/v2v/{dest.stem}_{k}", name, names,
                                        guide, prof["stages"])
                outs.append((Path(await _run(job, g, prof, k, len(parts))), n))
        else:
            n = min(meta["frames"], prof["max_frames"], round(15 * FPS) + 5)
            if n < 2 * FPS:
                raise EngineError(i18n.L(f"{label}: Ref2VA берёт клип от 2 с", f"{label}: Ref2VA takes a clip of 2 s or longer"))
            while n % 17 != 5:
                n -= 1
            W, H = _up(meta["w"], 32), _up(meta["h"], 32)
            name = f"{tag}.mp4"
            job.phase = "encoding"
            sound = [] if meta["sound"] else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            await asyncio.to_thread(_ffmpeg, ["-i", str(src), *sound, "-vf",
                                              f"trim=end_frame={n},setpts=PTS-STARTPTS,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps={FPS}",
                                              "-map", "0:v", "-map", "0:a" if meta["sound"] else "1:a", "-af", "apad", "-t", f"{n / FPS:.4f}",
                                              "-c:v", "libx264", "-crf", "10", "-preset", "fast", "-pix_fmt", "yuv420p",
                                              "-c:a", "aac", "-b:a", "192k", str(work / name)])
            refs = []
            for k, p in enumerate(pictures[:9], 1):
                refs.append(f"{tag}_pic{k}{p.suffix}")
                shutil.copyfile(p, work / refs[-1])
            g = graphs.scene(prompt_of(prof, text), W, H, n, seed, f"h3studio/v2v/{dest.stem}", names, None, refs, name)
            outs.append((Path(await _run(job, g, prof, 0, 1)), n))
        job.phase = "saving"
        await asyncio.to_thread(_finish, src, meta, outs, W, H, prof, dest, png, alpha)
    finally:
        for f in work.glob(f"{tag}*"):
            f.unlink(missing_ok=True)
        for f, _ in outs:
            f.unlink(missing_ok=True)


async def _run(job: jobs.Job, g: dict, prof: dict, k: int, of: int) -> str:
    """One graph on the worker -> its mp4; the phases and steps on the job (a piece of several: «кусок k/of»)."""
    h3 = prof["engine"] == "h3"
    phase_of = graphs.phase_of if h3 else other_graphs.phase_of
    samplers = (graphs.SAMPLE,) if h3 else other_graphs.SAMPLERS
    steps = graphs.REF_STEPS if h3 else len(other_graphs.LTX_SIGMAS_1.split(",")) - 1 + (
        len(other_graphs.LTX_SIGMAS_2.split(",")) - 1 if prof["stages"] == 2 else 0)
    before = {"n": 0}

    def on_node(node: str) -> None:
        if ph := phase_of(node):
            job.phase = ph
        if node == "sample2":
            before["n"] = len(other_graphs.LTX_SIGMAS_1.split(",")) - 1

    def on_progress(value: int, maximum: int, node: str) -> None:
        if node in samplers:
            job.phase, job.step, job.steps = "sampling", before["n"] + value, steps
    job.steps = steps
    if of > 1:
        job.progress["part"] = f"{k + 1}/{of}"
    t0 = time.time()
    files = output_files(await COMFY.run(g, on_node, on_progress))
    COMFY.warm = True
    job.progress.setdefault("v2v_seconds", []).append(round(time.time() - t0, 1))
    mp4 = next((f for f in files if f.endswith(".mp4")), None)
    if not mp4:
        raise EngineError(i18n.L("ComfyUI закончил без mp4", "ComfyUI finished without an mp4"))
    for f in files:
        if f.endswith(".png"):
            Path(f).unlink(missing_ok=True)
    return mp4


def _finish(src: Path, meta: dict, outs: list[tuple[Path, int]], W: int, H: int, prof: dict, dest: Path, png: Path,
            alpha: Optional[Path]) -> None:
    """The pieces cropped back to the clip's size (times the profile's scale) and frames, glued, with the clip's sound (or
    the model's); a matte as a grey mask + the clip with it as alpha; the last frame."""
    w, h = meta["w"], meta["h"]
    ow, oh = w * prof.get("scale", 1), h * prof.get("scale", 1)
    crop = f"crop={ow}:{oh}:{(W - ow) // 2}:{(H - oh) // 2}"
    matte = prof["out"] == "matte"
    args, parts = [], []
    for k, (f, n) in enumerate(outs):
        args += ["-i", str(f)]
        parts.append(f"[{k}:v]{crop},trim=end_frame={n},setpts=PTS-STARTPTS{',format=gray' if matte else ''}[v{k}]")
    j = len(outs)
    vcat = "".join(f"[v{k}]" for k in range(j)) + f"concat=n={j}:v=1:a=0,format=yuv420p[vout]"
    if prof["sound"] == "model" and prof["engine"] == "h3":
        sound = ["-map", "0:a?"]
    else:
        args += ["-i", str(src)]
        sound = ["-map", f"{j}:a?"]
    length = f"{sum(n for _, n in outs) / FPS:.4f}"   # the picture's: a sound a little shorter must not cut a frame
    dest.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(args + ["-filter_complex", ";".join(parts + [vcat]), "-map", "[vout]", *sound, "-t", length,
                    "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dest)])
    if matte and alpha:
        # the clip's own picture, the model's mask as its alpha: VP9 keeps it (yuva420p); Chrome and editors read it
        _ffmpeg(["-i", str(src), "-i", str(dest), "-filter_complex",
                 f"[1:v]format=gray,scale={w}:{h}[a];[0:v]format=yuv420p[c];[c][a]alphamerge,format=yuva420p[v]",
                 "-map", "[v]", "-map", "0:a?", "-t", length, "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24",
                 "-deadline", "good", "-cpu-used", "4", "-row-mt", "1", "-auto-alt-ref", "0", "-c:a", "libopus", "-b:a", "160k",
                 str(alpha)])
    _ffmpeg(["-sseof", "-0.5", "-i", str(dest), "-update", "1", str(png)])


def prores(webm: Path, mov: Path) -> None:
    """The clip without its background for editors: ProRes 4444 with its alpha (MOV). Players ignore VP9's alpha and show
    the whole picture (the user took the WebM for the plain clip); DaVinci and Premiere read this one. Made on the first
    download (main.project_file), through a temp file: two clicks never read a half-written one."""
    tmp = mov.with_name(mov.stem + ".part.mov")
    _ffmpeg(["-c:v", "libvpx-vp9", "-i", str(webm), "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
             "-alpha_bits", "16", "-vendor", "apl0", "-c:a", "pcm_s16le", str(tmp)])
    tmp.replace(mov)
