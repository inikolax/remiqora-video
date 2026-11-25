"""post.finish reads the source video's real size and fps (a «Бит-монтаж» is 1080x1920 at 60 fps, not a 24 fps scene):
the ffmpeg / rtx_vsr command lines are captured, nothing is encoded, no GPU.

    .venv\\Scripts\\python.exe tools\\test_post_finish.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, post  # noqa: E402

failed = 0
real_run = subprocess.run
calls: list[list[str]] = []
rife_calls: list[Path] = []


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"  FAIL {what}")


class FakeProc:
    returncode = 0

    class _Pipe:
        def close(self):
            pass

        def read(self):
            return b""

    def wait(self):
        return 0

    def __init__(self, args):
        self.stdout, self.stderr = self._Pipe(), self._Pipe()
        calls.append([str(a) for a in args])


def fake_run(args, *a, **k):
    if str(args[0]) == str(config.FFPROBE):
        return real_run(args, *a, **k)
    r = FakeProc(args)
    r.stdout = r.stderr = ""
    return r



class _Sub:   # stands in for `subprocess` inside app.post only
    CREATE_NO_WINDOW = 0
    run = staticmethod(fake_run)
    Popen = staticmethod(lambda args, **k: FakeProc(args))
    PIPE = subprocess.PIPE


post.subprocess = _Sub
post.interpolate = lambda src, work, cuts: (rife_calls.append(src) or (Path("rife"), 1))
post.shutil.rmtree = lambda *a, **k: None


def make(path: Path, w: int, h: int, fps: int) -> Path:
    real_run([config.FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate={fps}:duration=0.5",
              "-f", "lavfi", "-i", "sine=duration=0.5", "-pix_fmt", "yuv420p", "-shortest", str(path)], check=True)
    return path


def finish(src: Path, w: int, h: int, aspect: str, out: dict):
    calls.clear()
    rife_calls.clear()
    res = post.finish(src, Path("dest.mp4"), w, h, aspect, dict(out), [], Path("work"))
    return res, [" ".join(c) for c in calls]


tmp = Path(tempfile.mkdtemp())
scene = make(tmp / "scene.mp4", 544, 960, 24)
beat = make(tmp / "beat.mp4", 1080, 1920, 60)
beat_small = make(tmp / "beat_small.mp4", 540, 960, 60)
vsr = config.RTX_VSR
fake_vsr = tmp / "rtx_vsr.exe"
fake_vsr.write_bytes(b"")
config.RTX_VSR = fake_vsr
base = {"size": "1080p", "hdr": False, "fps48": False}

# a normal 544x960 @ 24 scene: as before
res, cmds = finish(scene, 544, 960, "9:16", base)
vsr_cmd = next(c for c in cmds if "rtx_vsr" in c)
ok(res == (1080, 1920, 24), f"scene 1080p: result {res}")
ok(vsr_cmd.split()[1:6] == ["544", "960", "1080", "1920", "4"], "scene: rtx_vsr gets 544x960 -> 1080x1920")
ok(any("-framerate 24 -i -" in c for c in cmds), "scene: encoder raw stream at 24 fps")
res, cmds = finish(scene, 544, 960, "9:16", dict(base, fps48=True))
ok(res[2] == 48 and len(rife_calls) == 1, "scene fps48: RIFE runs, encoded at 48")
ok(any("-framerate 48 -i -" in c for c in cmds), "scene fps48: raw stream at 48")
config.RTX_VSR = tmp / "missing.exe"
res, cmds = finish(scene, 544, 960, "9:16", base)
ok(any("scale=1080:1920:flags=lanczos" in c and "-r 24" in c for c in cmds), "scene, no VSR: lanczos to 1080x1920 at 24")
config.RTX_VSR = fake_vsr

# the beat montage: 1080x1920 @ 60; the caller still says 544x960
res, cmds = finish(beat, 544, 960, "9:16", base)
ok(res == (1080, 1920, 60), f"beat 1080x1920@60: result {res}")
ok(not any("rtx_vsr" in c for c in cmds) and any("-r 60" in c for c in cmds), "beat: no upscale, plain re-encode at 60")
res, cmds = finish(beat, 544, 960, "9:16", dict(base, size="4k"))
vsr_cmd = next(c for c in cmds if "rtx_vsr" in c)
ok(vsr_cmd.split()[1:6] == ["1080", "1920", "2160", "3840", "4"], "beat 4k: rtx_vsr gets the real 1080x1920 input")
ok(any("-framerate 60 -i -" in c for c in cmds), "beat 4k: raw stream at 60 fps")
res, cmds = finish(beat, 544, 960, "9:16", dict(base, fps48=True))
ok(not rife_calls and res[2] == 60 and not any("-framerate 48" in c or "-r 48" in c for c in cmds), "beat fps48: no RIFE, stays 60")
res, cmds = finish(beat_small, 544, 960, "9:16", base)
vsr_cmd = next(c for c in cmds if "rtx_vsr" in c)
ok(vsr_cmd.split()[1:6] == ["540", "960", "1080", "1920", "4"] and res == (1080, 1920, 60), "540x960@60 preview: upscaled 2x from its real size")
config.RTX_VSR = tmp / "missing.exe"
res, cmds = finish(beat_small, 544, 960, "9:16", base)
ok(any("-r 60" in c and "scale=1080:1920" in c for c in cmds), "beat, no VSR: keeps 60 fps")
config.RTX_VSR = vsr

print("all passed" if not failed else f"{failed} FAILED")
sys.exit(1 if failed else 0)
