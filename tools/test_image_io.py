"""checks.imread / imwrite work under a folder named in Cyrillic (plain cv2.imread returns None there on Windows).

    .venv\\Scripts\\python.exe tools\\test_image_io.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import checks, picture_checks  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp) / "Иван_фото"
    d.mkdir()
    img = np.zeros((40, 60, 3), np.uint8)
    img[:, :30] = (0, 0, 255)
    p = d / "кадр.png"
    ok(checks.imwrite(p, img) and p.exists(), "written under a Cyrillic path")
    back = checks.imread(p)
    ok(back is not None and back.shape == img.shape and (back == img).all(), "read back the same")
    ok(checks.imread(d / "нет.png") is None, "a missing file: None")
    (d / "пусто.png").write_bytes(b"")
    ok(checks.imread(d / "пусто.png") is None, "an empty file: None")
    ok(picture_checks._read(p) is not None, "picture_checks reads it too")
    ok(checks.face_picture(p) == (None, (60, 40)), "face_picture sees the picture (no face, its size)")

print("FAILED: %d" % failed if failed else "all passed")
sys.exit(1 if failed else 0)
