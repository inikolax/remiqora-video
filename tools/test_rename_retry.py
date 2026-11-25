"""A finished <name>.part that cannot be renamed at once (an antivirus holds it, WinError 5/32) is waited for, not treated as
a network failure: tools/install_models.py and app/downloads.py, no network, no GPU. Run: python tools/test_rename_retry.py"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import urllib.error
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


DATA = b"x" * 1000
REAL_REPLACE = im.os.replace
REAL_PATH_REPLACE = Path.replace
real_sha = im.sha256


def flaky(fails: int):
    state = {"n": 0}

    def fn(src, dst):
        state["n"] += 1
        if state["n"] <= fails:
            raise PermissionError(13, "held", str(src))
        return REAL_REPLACE(src, dst)
    return fn, state


def try_download(dest: Path, fails: int, hashed: list):
    fn, st = flaky(fails)
    f = {"repo": "a/b", "path": "m.gguf", "bytes": len(DATA), "sha256": hashlib.sha256(DATA).hexdigest()}
    out = io.StringIO()
    err = None
    with mock.patch.object(im.os, "replace", fn), mock.patch.object(im.time, "sleep"), \
            mock.patch.object(im, "sha256", lambda p: (hashed.append(1), real_sha(p))[1]), redirect_stdout(out):
        try:
            im.download(f, dest, None, lambda n: None)
        except OSError as e:
            err = e
    return err, st, out.getvalue()


with tempfile.TemporaryDirectory() as d:
    im.JSON = True
    im.LANG = "en"

    print("install_models: replace fails twice, then works")
    dest = Path(d) / "one" / "m.gguf"
    dest.parent.mkdir()
    part = dest.with_name("m.gguf.part")
    part.write_bytes(DATA)
    hashed: list = []
    err, st, out = try_download(dest, 2, hashed)
    ok(err is None and dest.read_bytes() == DATA and not part.exists(), "the file landed")
    ok(st["n"] == 3 and len(hashed) == 1, "three replaces, sha256 computed once")
    ok(sum(1 for line in out.splitlines() if json.loads(line)["event"] == "retry") == 2, "a progress line per wait")

    print("install_models: replace always fails")
    dest = Path(d) / "two" / "m.gguf"
    dest.parent.mkdir()
    part = dest.with_name("m.gguf.part")
    part.write_bytes(DATA)
    hashed = []
    err, st, out = try_download(dest, 10**9, hashed)
    ok(isinstance(err, im.RenameError) and "by hand" in str(err), "RenameError with the by-hand hint")
    ok(part.read_bytes() == DATA and not dest.exists(), ".part intact, no dest")
    ok(len(hashed) == 1, "no re-hash and no re-download")

    print("downloads.py: replace fails twice, then works; and always fails")
    for fails, expect in ((2, "done"), (10**9, "failed")):
        folder = Path(d) / f"dl{min(fails, 9)}"
        folder.mkdir()
        dest, part = folder / "m.gguf", folder / "m.gguf.part"
        part.write_bytes(DATA)
        calls = {"n": 0}

        def rep(self, target, calls=calls, fails=fails):
            calls["n"] += 1
            if calls["n"] <= fails:
                raise PermissionError(13, "held")
            return REAL_PATH_REPLACE(self, target)

        with mock.patch.object(downloads, "size", lambda repo, path: len(DATA)):
            dl = downloads.Download("a/b", "m.gguf", folder)
        dl._stop = mock.Mock(is_set=lambda: False, wait=lambda t: False)   # the stop event's wait is the backoff
        # the .part is already whole: the server answers 416 and nothing is fetched
        gone = urllib.error.HTTPError("u", 416, "r", {}, None)
        with mock.patch.object(Path, "replace", rep), mock.patch.object(downloads.urllib.request, "urlopen", side_effect=gone):
            dl.run()
        ok(dl.status == expect, f"status {dl.status}")
        if expect == "done":
            ok(dest.read_bytes() == DATA and calls["n"] == 3, "the file landed after three replaces")
        else:
            ok(part.exists() and not dest.exists() and ("вручную" in (dl.error or "") or "by hand" in (dl.error or "")), "stays as .part, clear message")

print("FAILED" if failed else "all passed")
sys.exit(1 if failed else 0)
