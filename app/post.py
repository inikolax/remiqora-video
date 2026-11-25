"""After the assembly: 48 fps by RIFE, 1080p / 4K by RTX Video Super Resolution, HDR10 by RTX TrueHDR.

  frames (PNG) -> RIFE x2 (rife-ncnn-vulkan, v4.6) -> rtx_vsr [hdr] -> ffmpeg encoder, the sound copied.
RIFE draws a frame between every two; across a hard cut (a "new" scene) that frame would blend two shots, so it is
replaced by the last frame of the outgoing shot (as in Remiqora's final_rtx.py). Continuations have no cut: the next
scene starts from the previous last frame.
rtx_vsr: raw RGBA on stdin -> stdout; with `hdr` the output is R10G10B10A2 (ffmpeg x2bgr10le), PQ / BT.2020, full range.
Encoders: 1080p SDR - libx264 (as before); 4K and HDR - HEVC on NVENC (x264 at 4K is slow); HDR is 10-bit Main10
with the BT.2020 / PQ colour tags (limited range). Mastering-display metadata is not written: NVENC through ffmpeg's
command line can't, players go by the PQ tags.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from . import config
from .engine import graphs
from .engine.comfy import EngineError
from . import i18n

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SIZES = {   # the output frame per aspect
    "1080p": {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)},
    "4k": {"16:9": (3840, 2160), "9:16": (2160, 3840), "1:1": (2160, 2160)},
}
HDR_NITS = 1000


def output_of(settings: dict) -> dict:
    """The project's output choice; old projects had one checkbox `rtx` (= 1080p)."""
    out = dict(settings.get("output") or {})
    out.setdefault("size", "1080p" if settings.get("rtx", True) else "off")
    out.setdefault("hdr", False)
    out.setdefault("fps48", False)
    if out["size"] not in ("off", "1080p", "4k"):
        out["size"] = "1080p"
    if out["size"] == "off":
        out["hdr"] = False   # TrueHDR rides on the RTX pass
    return out


def tag(out: dict) -> Optional[str]:
    """The suffix of the finished file: video_draft_4k_hdr_48fps.mp4; None when there is nothing to do."""
    parts = [p for p in (out["size"] if out["size"] != "off" else None, "hdr" if out["hdr"] else None,
                         "48fps" if out["fps48"] else None) if p]
    return "_".join(parts) or None


def target(out: dict, w: int, h: int, aspect: str) -> tuple[int, int]:
    if out["size"] == "off":
        return w, h
    return SIZES[out["size"]].get(aspect) or ((1920, round(1920 * h / w / 2) * 2) if w >= h else (round(1920 * w / h / 2) * 2, 1920))


def seconds(out: dict, video_seconds: float, w: int, h: int) -> float:
    """Measured 2026-10-21 on an RTX 4080, 30.9 s video at 960x544: RTX 1080p 0.33 s per second of video, 4K 0.45
    (NVENC), TrueHDR +5%; RIFE ~0.55 s per second (PNG out and in), and the RTX pass then has twice the frames."""
    t = 0.0
    k = (w * h) / (960 * 544)
    if out["fps48"]:
        t += 0.55 * video_seconds * k
    if out["size"] != "off":
        rtx = {"1080p": 0.33, "4k": 0.45}[out["size"]] * video_seconds * k
        if out["hdr"]:
            rtx *= 1.05
        t += rtx * (2 if out["fps48"] else 1)
    return t


def _run(args: list[str], what: str, cwd: Optional[Path] = None) -> None:
    r = subprocess.run(args, capture_output=True, text=True, cwd=cwd, creationflags=NO_WINDOW)
    if r.returncode:
        raise EngineError(f"{what}: " + (r.stderr or r.stdout or "").strip()[-600:])


def interpolate(src: Path, work: Path, cuts: list[int]) -> tuple[Path, int]:
    """RIFE x2: the video's frames -> work/rife/%05d.png at 48 fps. Returns (the folder, frame count)."""
    if not config.RIFE_BIN.exists():
        raise EngineError(i18n.L(f"Нет RIFE: {config.RIFE_BIN} («Модели и настройки» или RIFE_BIN в .env)", f"No RIFE: {config.RIFE_BIN} («Models and settings» or RIFE_BIN in .env)"))
    frames, mid = work / "src", work / "rife"
    shutil.rmtree(work, ignore_errors=True)
    frames.mkdir(parents=True)
    mid.mkdir()
    _run([config.FFMPEG, "-v", "error", "-i", str(src), "-fps_mode", "passthrough", "-an", str(frames / "%05d.png")], i18n.L("ffmpeg (кадры)", "ffmpeg (frames)"))
    n = len(list(frames.glob("*.png")))
    _run([str(config.RIFE_BIN), "-i", str(frames), "-o", str(mid), "-m", str(config.RIFE_BIN.parent / config.RIFE_MODEL),
          "-f", "%05d.png"], "RIFE", cwd=config.RIFE_BIN.parent)
    out = sorted(mid.glob("*.png"))
    # out frame 2k = source k, 2k+1 = between k and k+1: across a cut the in-between becomes the outgoing shot's last
    for s in cuts:
        if 0 < s < n and 2 * s - 1 < len(out):
            shutil.copyfile(out[2 * s - 2], out[2 * s - 1])
    shutil.rmtree(frames, ignore_errors=True)
    return mid, len(out)


def probe(src: Path, w: int, h: int) -> tuple[int, int, int | float]:
    """(width, height, fps) of the video's first stream; the given w, h and the project's 24 fps when ffprobe can't say."""
    try:
        r = subprocess.run([config.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                            "-of", "csv=p=0", str(src)], capture_output=True, text=True, creationflags=NO_WINDOW)
        pw, ph, rate = r.stdout.strip().split(",")[:3]
        num, _, den = rate.partition("/")
        fps = float(num) / float(den or 1)
        if int(pw) > 0 and int(ph) > 0 and fps > 0:
            return int(pw), int(ph), (round(fps) if abs(fps - round(fps)) < 0.01 else round(fps, 3))
    except (OSError, ValueError):
        pass
    return w, h, graphs.FPS


def finish(src: Path, dest: Path, w: int, h: int, aspect: str, out: dict, cuts: list[int], work: Path) -> tuple[int, int, int]:
    """src (the assembled video with its sound) -> dest. Returns (width, height, fps)."""
    # The caller's w / h / FPS describe a scene video, but the input may be something else (a «Бит-монтаж» is 1080x1920
    # or 540x960 at 30 / 60 fps): the decoder, rtx_vsr and the encoder go by what the file really is.
    w, h, src_fps = probe(src, w, h)
    # RIFE doubles 24 / 30 fps sources only; a faster one (the beat montage at 60) keeps its own rate.
    rife = bool(out["fps48"]) and src_fps <= 30
    fps = src_fps * 2 if rife else src_fps
    ow, oh = target(out, w, h, aspect)
    if out["size"] != "off" and ow <= w and oh <= h:
        ow, oh = w, h   # the source is already that big: no upscale (HDR still goes through the RTX pass at its own size)
        if not out["hdr"]:
            out = dict(out, size="off")   # plain re-encode
    # the frames: straight from the video, or from RIFE's folder
    if rife:
        mid, _ = interpolate(src, work, cuts)
        dec_in = ["-framerate", str(fps), "-i", str(mid / "%05d.png")]
    else:
        dec_in = ["-i", str(src)]
    enc = [config.FFMPEG, "-y", "-v", "error"]
    if out["size"] == "off":   # 48 fps only: encode the frames as they are
        _run(enc + dec_in + ["-i", str(src), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                             "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "copy", "-movflags", "+faststart", str(dest)], "ffmpeg")
        shutil.rmtree(work, ignore_errors=True)
        return ow, oh, fps
    if not config.RTX_VSR.exists():   # no RTX Video: ffmpeg's lanczos to the same size, SDR
        out["hdr"] = False
        _run(enc + dec_in + ["-i", str(src), "-map", "0:v", "-map", "1:a", "-vf", f"scale={ow}:{oh}:flags=lanczos", "-c:v", "libx264",
                             "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "copy", "-movflags", "+faststart",
                             str(dest)], "ffmpeg")
        shutil.rmtree(work, ignore_errors=True)
        return ow, oh, fps
    dec = subprocess.Popen([config.FFMPEG, "-v", "error", *dec_in, "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                           stdout=subprocess.PIPE, creationflags=NO_WINDOW)
    vsr_args = [str(config.RTX_VSR), str(w), str(h), str(ow), str(oh), "4"] + (["hdr", str(HDR_NITS)] if out["hdr"] else [])
    vsr = subprocess.Popen(vsr_args, stdin=dec.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           cwd=config.RTX_VSR.parent, creationflags=NO_WINDOW)
    dec.stdout.close()
    raw = ["-f", "rawvideo", "-pix_fmt", "x2bgr10le" if out["hdr"] else "rgba", "-s", f"{ow}x{oh}", "-framerate", str(fps), "-i", "-"]
    if out["hdr"]:
        # the frames carry no colour properties of their own: setparams gives them, or NVENC writes "unknown"
        video = ["-vf", "scale=in_range=full:out_range=limited:out_color_matrix=bt2020,format=p010le,"
                        "setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc:range=tv",
                 "-c:v", "hevc_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "18", "-profile:v", "main10",
                 "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc", "-color_range", "tv",
                 "-tag:v", "hvc1"]
    elif out["size"] == "4k":
        video = ["-c:v", "hevc_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-pix_fmt", "yuv420p", "-tag:v", "hvc1"]
    else:
        video = ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p"]
    encp = subprocess.run(enc + raw + ["-i", str(src), "-map", "0:v", "-map", "1:a", *video, "-c:a", "copy",
                                       "-movflags", "+faststart", str(dest)],   # no -shortest: it cut frames off the end
                          stdin=vsr.stdout, capture_output=True, text=True, creationflags=NO_WINDOW)
    vsr.stdout.close()
    err = vsr.stderr.read().decode("utf-8", "replace") if vsr.stderr else ""
    shutil.rmtree(work, ignore_errors=True)
    if dec.wait() or vsr.wait() or encp.returncode:
        raise EngineError(i18n.L(f"RTX не сработал (ffmpeg {dec.returncode}, rtx_vsr {vsr.returncode}, кодер {encp.returncode}): ", f"RTX failed (ffmpeg {dec.returncode}, rtx_vsr {vsr.returncode}, encoder {encp.returncode}): ")
                          + (encp.stderr or err or "").strip()[-500:])
    return ow, oh, fps


PHONE_AUDIO_K = 128      # the phone copy's sound, kbit/s
PHONE_MIN_VIDEO_K = 900  # below this the picture is scaled down (1080x1920 would be mush)
PHONE_FLOOR_VIDEO_K = 200  # the encoder never goes below this video bitrate; a target under it cannot be met


def phone_copy(src: Path, dest: Path, max_mb: float = 10.0) -> dict:
    """The small copy for a phone or a browser upload (<= 10 MB decimal: the upload tool used on 2026-11-06 refused 10.7 MB;
    TikTok itself takes much bigger files): two-pass x264 at a bitrate
    computed from the length so that the file stays <= max_mb, 1080x1920 kept when the bitrate allows (else 720 wide).
    A file that still comes out too big is encoded again at 90% of the bitrate (3 times at most).
    -> {file, mb, kbps, width, height, seconds}"""
    import os
    import tempfile
    from . import music
    dur = max(0.5, music.duration(src))
    limit = max_mb * 1000 * 1000 * 8 * 0.96   # bits, 4% for the container
    kbps = int((limit / dur) / 1000 - PHONE_AUDIO_K)   # the video part only: the sound's share is already taken off
    if kbps < PHONE_FLOOR_VIDEO_K:   # a very long video: even the floor bitrate would not fit - say so before encoding
        raise EngineError(i18n.L(f"Видео слишком длинное ({dur:.0f} с) для копии в {max_mb:g} МБ",
                                 f"The video is too long ({dur:.0f} s) for a {max_mb:g} MB copy"))
    scale = []
    out_w = out_h = 0
    if kbps < PHONE_MIN_VIDEO_K:
        scale = ["-vf", "scale=720:-2:flags=lanczos"]
    dest.parent.mkdir(parents=True, exist_ok=True)

    part = dest.with_name(f"{dest.stem}.part{dest.suffix}")   # pass 2 writes here; dest appears only when the copy is whole

    def encode(kb: int, vf: list) -> float:
        with tempfile.TemporaryDirectory() as tmp:
            log = str(Path(tmp) / "pass")
            base = [config.FFMPEG, "-y", "-v", "error", "-i", str(src), *vf, "-c:v", "libx264", "-preset", "slow", "-b:v", f"{max(200, kb)}k",
                    "-maxrate", f"{int(max(200, kb) * 1.4)}k", "-bufsize", f"{int(max(200, kb) * 2)}k", "-pix_fmt", "yuv420p", "-passlogfile", log]
            _run(base + ["-pass", "1", "-an", "-f", "mp4", os.devnull], "ffmpeg (pass 1)")
            _run(base + ["-pass", "2", "-c:a", "aac", "-b:a", f"{PHONE_AUDIO_K}k", "-movflags", "+faststart", str(part)], "ffmpeg (pass 2)")
        return part.stat().st_size / 1000 / 1000

    try:
        for _ in range(4):
            mb = encode(kbps, scale)
            if mb <= max_mb:
                break
            kbps = max(PHONE_FLOOR_VIDEO_K, int(kbps * 0.9))
        else:
            # still too big: a last try at 720 wide (at the bitrate the loop ended with), then an error - never a silent oversize file
            if not scale:
                scale = ["-vf", "scale=720:-2:flags=lanczos"]
                mb = encode(kbps, scale)
            if mb > max_mb:
                raise EngineError(i18n.L(f"Копия для телефона не влезла в {max_mb:g} МБ: получилось {mb:.1f} МБ",
                                         f"The phone copy does not fit {max_mb:g} MB: it came out {mb:.1f} MB"))
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)   # a failed or oversize encode leaves nothing behind
    r = subprocess.run([config.FFMPEG, "-hide_banner", "-i", str(dest)], capture_output=True, text=True, creationflags=NO_WINDOW)
    import re
    m = re.search(r"Video:.*?,\s*(\d{3,4})x(\d{3,4})", r.stderr or "")
    if m:
        out_w, out_h = int(m.group(1)), int(m.group(2))
    return {"file": str(dest), "mb": round(mb, 2), "kbps": kbps, "width": out_w, "height": out_h, "seconds": round(dur, 2)}


def cover_frame(src: Path, dest: Path, at: float) -> Path:
    """One frame of the video at `at` seconds as a PNG (the cover)."""
    import os
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(f"{dest.stem}.part{dest.suffix}")
    try:
        _run([config.FFMPEG, "-y", "-v", "error", "-ss", f"{max(0.0, at):.3f}", "-i", str(src), "-frames:v", "1", str(part)], "ffmpeg (cover)")
        if not part.exists():
            raise EngineError(i18n.L("Кадр обложки не получился", "The cover frame could not be made"))
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)
    return dest
