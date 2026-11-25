"""Pinned revisions in install/manifest.json: every "rev" is a full commit sha, the installer builds its link with it, and a
file that is not the manifest's size (re-uploaded upstream) stops at once with the «changed» error, .part removed.
No network, no GPU. Run: python tools/test_manifest_pins.py"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import urllib.error
from contextlib import redirect_stdout
from email.message import Message
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
    def __init__(self, status: int, headers: dict, body: bytes = b""):
        self.status, self.headers, self._b = status, headers, io.BytesIO(body)

    def read(self, n=-1):
        return self._b.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code: int, headers: dict | None = None):
    m = Message()
    for k, v in (headers or {}).items():
        m[k] = v
    return urllib.error.HTTPError("https://x", code, "err", m, None)


m = json.loads((ROOT / "install" / "manifest.json").read_text(encoding="utf-8"))
files = [f for s in m["sets"].values() for f in s["files"]]

print("manifest: revisions")
pinned = [f for f in files if "rev" in f]
ok(len(pinned) > 0, f"{len(pinned)} files are pinned")
ok(all(re.fullmatch(r"[0-9a-f]{40}", f["rev"]) for f in pinned), "every rev is a 40-hex commit sha")
ok(all(list(f).index("rev") == list(f).index("path") + 1 for f in pinned), "rev follows path")

print("install_models: the link")
f = pinned[0]
url = im.resolve_url(f)
ok(f"/resolve/{f['rev']}/" in url and "/resolve/main/" not in url, "pinned file: resolve/<rev>/")
ok("/resolve/main/" in im.resolve_url({"repo": "a/b", "path": "x.bin"}), "no rev: main")

with tempfile.TemporaryDirectory() as d:
    im.JSON, im.LANG = True, "en"
    DATA = b"x" * 1000
    fd = {"repo": "a/b", "path": "m.gguf", "rev": "c" * 40, "bytes": len(DATA)}

    def run(dest: Path, responses: list):
        calls: list = []

        def fake(req, timeout=0):
            calls.append(req)
            r = responses[min(len(calls), len(responses)) - 1]
            if isinstance(r, Exception):
                raise r
            return r
        err = None
        with mock.patch.object(im.urllib.request, "urlopen", fake), mock.patch.object(im.time, "sleep"), redirect_stdout(io.StringIO()):
            try:
                im.download(fd, dest, None, lambda n: None)
            except OSError as e:
                err = e
        return err, calls

    print("install_models: the server's file is another size (200)")
    dest = Path(d) / "a" / "m.gguf"
    dest.parent.mkdir()
    part = dest.with_name("m.gguf.part")
    part.write_bytes(b"y" * 10)
    err, calls = run(dest, [Resp(206, {"Content-Range": "bytes 10-1005/1006", "Content-Length": "996"}, b"z" * 996)])
    ok(isinstance(err, im.ChangedError), "ChangedError")
    ok(len(calls) == 1, "one request, no retries")
    ok(not part.exists() and not dest.exists(), ".part removed")
    ok("1000" in str(err) and "1006" in str(err), "the message names both sizes")
    ok(f"/resolve/{'c' * 40}/m.gguf" in calls[0].full_url, "the request used the pinned rev")

    print("install_models: 200 with another Content-Length")
    err, calls = run(dest, [Resp(200, {"Content-Length": "1006"}, b"z" * 1006)])
    ok(isinstance(err, im.ChangedError) and len(calls) == 1 and not part.exists(), "changed after one request")

    print("install_models: 416 on a resume")
    part.write_bytes(b"y" * 10)
    err, calls = run(dest, [http_error(416, {"Content-Range": "bytes */990"})])
    ok(isinstance(err, im.ChangedError) and len(calls) == 1 and not part.exists(), "416: changed, one request, .part removed")
    ok("990" in str(err), "416: the total from Content-Range is in the message")

    print("install_models: normal resume (206, same file)")
    part.write_bytes(DATA[:400])
    err, calls = run(dest, [Resp(206, {"Content-Range": "bytes 400-999/1000", "Content-Length": "600"}, DATA[400:])])
    ok(err is None and dest.read_bytes() == DATA and not part.exists(), "resumed and finished")
    ok(calls[0].get_header("Range") == "bytes=400-", "Range was sent")

    print("install_models: server ignores Range (200 on the same file)")
    dest.unlink()
    part.write_bytes(DATA[:400])
    err, calls = run(dest, [Resp(200, {"Content-Length": "1000"}, DATA)])
    ok(err is None and dest.read_bytes() == DATA, "restarted from zero")

    print("app.downloads: the server's file is another size")
    folder = Path(d) / "dl"
    with mock.patch.object(downloads, "size", lambda repo, path, rev="main": 1000):
        dl = downloads.Download("a/b", "m.gguf", folder, "c" * 40)
    seen: list = []

    def fake_open(req, timeout=0):
        seen.append(req)
        return Resp(206, {"Content-Range": "bytes 10-1005/1006"}, b"z" * 996)
    folder.mkdir()
    (folder / "m.gguf.part").write_bytes(b"y" * 10)
    with mock.patch.object(downloads.urllib.request, "urlopen", fake_open):
        dl.run()
    ok(dl.status == "failed" and "изменил" in (dl.error or "") or "changed" in (dl.error or ""), "failed with the «changed» text")
    ok(not (folder / "m.gguf.part").exists(), ".part removed")
    ok(len(seen) == 1 and f"/resolve/{'c' * 40}/m.gguf" in seen[0].full_url, "one request, with the link's rev")

    dl2 = None
    with mock.patch.object(downloads, "size", lambda repo, path, rev="main": 1000):
        dl2 = downloads.Download("a/b", "m.gguf", folder)
    (folder / "m.gguf.part").write_bytes(b"y" * 10)

    def raise416(req, timeout=0):
        raise http_error(416)
    with mock.patch.object(downloads.urllib.request, "urlopen", raise416):
        dl2.run()
    ok(dl2.status == "failed" and not (folder / "m.gguf.part").exists(), "416: failed, .part removed")

print("app.downloads: link revision")
ok(downloads.parse_link("https://huggingface.co/a/b/blob/abc123/x/y.gguf") == ("a/b", "x/y.gguf", "abc123"), "blob link keeps its rev")
ok(downloads.parse_link("https://huggingface.co/a/b/resolve/main/y.gguf")[2] == "main", "main stays main")
ok(downloads.parse_url("https://huggingface.co/a/b/blob/main/y.gguf") == ("a/b", "y.gguf"), "parse_url unchanged")

print(f"\n{'FAILED: ' + str(failed) if failed else 'all ok'}")
sys.exit(1 if failed else 0)
