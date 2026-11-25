"""The app's catalog download (app/downloads.py) follows the installer's pins: a file of install/manifest.json is fetched at its
rev and its size + sha256 are checked (a wrong file is deleted, not kept); a file off the manifest keeps main and no sha. And the
installer stops at once on an unpinned file whose sha256 changed at the right size. Fake HTTP, no network.
Run: python tools/test_app_download_pins.py"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import install_models as im  # noqa: E402
from app import downloads  # noqa: E402

failed = 0


def ok(cond: bool, what: str) -> None:
    global failed
    print(("  ok   " if cond else "  FAIL ") + what)
    failed += 0 if cond else 1


class Resp:
    def __init__(self, body: bytes):
        self.status, self.headers, self._b = 200, {"Content-Length": str(len(body))}, io.BytesIO(body)

    def read(self, n=-1):
        return self._b.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


DATA = b"weights" * 100
GOOD = hashlib.sha256(DATA).hexdigest()
REV = "a" * 40
entry = {"repo": "o/m", "path": "sub/w.safetensors", "kind": "vae", "bytes": len(DATA), "sha256": GOOD, "rev": REV}

with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "install").mkdir()
    (d / "install" / "manifest.json").write_text(json.dumps({"sets": {"s": {"files": [entry]}}}), encoding="utf-8")

    def fetch(repo, path, body, folder, rev="main"):
        seen: list = []

        def fake(req, timeout=0):
            seen.append(req.full_url)
            return Resp(body)
        with mock.patch.object(downloads.config, "ROOT", d), mock.patch.object(downloads, "_pins", (-1.0, {})), \
                mock.patch.object(downloads, "size", lambda *a, **k: None), mock.patch.object(downloads.urllib.request, "urlopen", fake):
            dl = downloads.Download(repo, path, folder, rev)
            dl.run()
        return dl, seen

    print("manifest file: rev + sha256")
    f1 = d / "ok"
    dl, seen = fetch("o/m", "sub/w.safetensors", DATA, f1)
    ok(dl.status == "done" and (f1 / "w.safetensors").read_bytes() == DATA, "good file is kept")
    ok(seen == [f"{downloads.HF}/o/m/resolve/{REV}/sub/w.safetensors"], "requested at the pinned rev, not main")
    ok(dl.total == len(DATA), "total comes from the manifest")

    print("manifest file: wrong content at the right size")
    f2 = d / "bad"
    dl, seen = fetch("o/m", "sub/w.safetensors", b"x" * len(DATA), f2)
    ok(dl.status == "failed" and "sha256" in (dl.error or ""), "refused with the sha256 error")
    ok(not (f2 / "w.safetensors").exists() and not (f2 / "w.safetensors.part").exists(), "nothing left on disk")

    print("manifest file: a pasted link's own revision is not overridden")
    dl, seen = fetch("o/m", "sub/w.safetensors", b"x" * len(DATA), d / "own", "feedbeef")
    ok(dl.rev == "feedbeef" and dl.pin is None and dl.status == "done", "explicit rev stays, no pin, no sha check")
    ok(seen == [f"{downloads.HF}/o/m/resolve/feedbeef/sub/w.safetensors"], "requested at the link's rev")

    print("file off the manifest: main, no sha")
    f3 = d / "off"
    dl, seen = fetch("o/other", "z.gguf", b"anything", f3)
    ok(dl.status == "done" and (f3 / "z.gguf").read_bytes() == b"anything", "downloaded without a check")
    ok(seen == [f"{downloads.HF}/o/other/resolve/main/z.gguf"], "requested at main")

print("installer: unpinned sha mismatch")
with tempfile.TemporaryDirectory() as d:
    im.JSON, im.LANG = True, "en"

    def run(fd, sub):
        dest = Path(d) / sub / "m.bin"
        calls: list = []

        def fake(req, timeout=0):
            calls.append(req)
            return Resp(b"y" * fd["bytes"])
        err = None
        with mock.patch.object(im.urllib.request, "urlopen", fake), mock.patch.object(im.time, "sleep"), redirect_stdout(io.StringIO()):
            try:
                im.download(fd, dest, None, lambda n: None)
            except OSError as e:
                err = e
        return err, calls

    base = {"repo": "a/b", "path": "m.bin", "bytes": 100, "sha256": "0" * 64}
    err, calls = run(base, "u")
    ok(isinstance(err, im.ChangedError) and len(calls) == 1, "ChangedError after one request")
    err, calls = run({**base, "rev": "c" * 40}, "p")
    ok(type(err) is OSError and len(calls) == im.TRIES, "pinned file: still retried")

print(f"\n{'FAILED: ' + str(failed) if failed else 'all ok'}")
sys.exit(1 if failed else 0)
