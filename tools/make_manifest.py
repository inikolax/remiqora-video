"""Fills in install/manifest.json: each model file's size and sha256 from the Hugging Face API (lfs.size, lfs.oid), so
neither installer asks Hugging Face for them on every run. Run after changing a set; a file the API does not know stops
it. A gated repository (LTX 2.5) needs a token with access: HF_TOKEN, or data/hf_token.

    python tools/make_manifest.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "install" / "manifest.json"
# Names only an official repository may carry: a set must never point at an uncensored repack
FORBIDDEN = ("uncensored", "eros", "abliterated", "heretic", "nsfw")


def token() -> str | None:
    if t := os.environ.get("HF_TOKEN"):
        return t.strip()
    f = ROOT / "data" / "hf_token"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def tree(repo: str, folder: str) -> dict[str, dict]:
    url = f"https://huggingface.co/api/models/{repo}/tree/main" + (f"/{urllib.parse.quote(folder)}" if folder else "")
    headers = {"User-Agent": "remiqora-video-manifest"}
    if t := token():
        headers["Authorization"] = f"Bearer {t}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return {f["path"]: f for f in json.load(r) if f.get("type") == "file"}


def main() -> int:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cache: dict[tuple[str, str], dict] = {}
    for sid, s in m["sets"].items():
        total = 0
        for f in s["files"]:
            if any(w in (f["repo"] + "/" + f["path"]).lower() for w in FORBIDDEN):
                print(f"{sid}: {f['repo']}/{f['path']} is not an official file", file=sys.stderr)
                return 1
            folder = f["path"].rsplit("/", 1)[0] if "/" in f["path"] else ""
            if (f["repo"], folder) not in cache:
                cache[(f["repo"], folder)] = tree(f["repo"], folder)
            info = cache[(f["repo"], folder)].get(f["path"])
            if not info:
                print(f"{sid}: {f['repo']} has no {f['path']}", file=sys.stderr)
                return 1
            lfs = info.get("lfs") or {}
            f["bytes"] = int(lfs.get("size") or info.get("size"))
            oid = str(lfs.get("oid") or "")
            if len(oid) == 64 and all(c in "0123456789abcdef" for c in oid):   # a gated repo hides it: size only
                f["sha256"] = oid
            else:
                f.pop("sha256", None)
            total += f["bytes"]
        s["bytes"] = total
        print(f"{sid:8} {total / 1e9:6.1f} GB  {len(s['files'])} files")
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
