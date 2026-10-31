"""Downloads the model sets of install/manifest.json into the models folder - the one downloader of both installers
(setup_models.ps1 and the desktop wizard). Only the stdlib, so any Python runs it.

    python tools/install_models.py --models-dir D:\\models --sets h3,writer [--find D:\\ComfyUI\\models] [--json]
    python tools/install_models.py --models-dir D:\\models --profile faces --plan --json

A file already in the models folder (or in a --find folder, as the worker finds it there) with the size of the official
one is not downloaded again. A download goes to <name>.part and continues from it (HTTP Range) after a cut or a stop,
three tries with a pause, then the sha256 is checked against Hugging Face's. A set that fails (no network, no access to
a gated repository) does not stop the others: the summary says what is missing and why, and a second run continues.
--json prints one JSON object per line for the wizard: plan, file, progress, set, summary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HF = "https://huggingface.co"
CHUNK = 8 * 1024 * 1024
TRIES = 3
# the worker's folders for each kind (app/engine/worker.py KINDS): a file found in any of them counts
KINDS = {"diffusion_models": ("diffusion_models", "unet"), "text_encoders": ("text_encoders", "clip"), "vae": ("vae",),
         "loras": ("loras",), "checkpoints": ("checkpoints",), "latent_upscale_models": ("latent_upscale_models",),
         "llm": ("llm",)}
# empty folders for what the user adds himself: the models' style LoRA
EMPTY = ("loras/h3", "loras/ltx23", "loras/ltx25", "loras/wan5b", "loras/krea2", "loras/flux2")

JSON = False
LANG = "ru"


def say(event: str, text: str = "", **data) -> None:
    if JSON:
        print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)
    elif text:
        print(text, flush=True)


def L(ru: str, en: str) -> str:
    return ru if LANG == "ru" else en


def gb(n: float) -> str:
    return f"{n / 1e9:.1f} {L('ГБ', 'GB')}"


class Refused(Exception):
    """Hugging Face said no: a token is needed, or the license is not accepted. Trying again will not help."""


def token(args) -> str | None:
    if t := (args.token or os.environ.get("HF_TOKEN") or "").strip():
        return t
    for f in ([Path(args.token_file)] if args.token_file else []) + [ROOT / "data" / "hf_token"]:
        if f.exists() and (t := f.read_text(encoding="utf-8").strip()):
            return t
    return None


def find(name: str, size: int, kind: str, roots: list[Path]) -> Path | None:
    """The file with this name and size in a root's folders for its kind (the LLM folder: anywhere under it)."""
    for root in roots:
        for sub in KINDS[kind]:
            d = root / sub
            if kind == "llm":
                hits = [p for p in d.rglob(name)] if d.is_dir() else []
            else:
                hits = [d / name] if (d / name).is_file() else []
            for p in hits:
                if p.stat().st_size == size:
                    return p
    return None


def sha256(path: Path, limit: int | None = None) -> "hashlib._Hash":
    h = hashlib.sha256()
    with open(path, "rb") as f:
        left = limit if limit is not None else None
        while True:
            block = f.read(CHUNK if left is None else min(CHUNK, left))
            if not block:
                break
            h.update(block)
            if left is not None:
                left -= len(block)
                if left <= 0:
                    break
    return h


def download(f: dict, dest: Path, tok: str | None, on_bytes) -> None:
    """One file into dest, through dest.part; raises Refused, or OSError after the tries."""
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{HF}/{f['repo']}/resolve/main/{urllib.parse.quote(f['path'])}"
    total = f["bytes"]
    for attempt in range(1, TRIES + 1):
        have = part.stat().st_size if part.exists() else 0
        if have > total:
            part.unlink()
            have = 0
        free = shutil.disk_usage(dest.parent).free
        if free < total - have + 512 * 2**20:
            raise OSError(L(f"мало места: нужно {gb(total - have)}, свободно {gb(free)}", f"not enough space: {gb(total - have)} needed, {gb(free)} free"))
        try:
            if have < total:
                headers = {"User-Agent": "remiqora-video-installer"}
                if tok:
                    headers["Authorization"] = f"Bearer {tok}"
                if have:
                    headers["Range"] = f"bytes={have}-"
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                    if have and r.status != 206:   # the server ignored Range: from the start
                        have = 0
                    with open(part, "ab" if have else "wb") as out:
                        done = have
                        on_bytes(done)
                        while block := r.read(CHUNK):
                            out.write(block)
                            done += len(block)
                            on_bytes(done)
            got = part.stat().st_size
            if got != total:
                raise OSError(L(f"скачано {got} из {total} байт", f"{got} of {total} bytes downloaded"))
            if f.get("sha256") and sha256(part).hexdigest() != f["sha256"]:
                part.unlink()   # a broken file is not continued: the next try starts over
                raise OSError(L("не сошлась контрольная сумма sha256", "the sha256 checksum does not match"))
            part.replace(dest)
            return
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise Refused(L("нужен токен Hugging Face с доступом: примите лицензию на странице модели (Agree)",
                                "a Hugging Face token with access is needed: accept the license on the model's page (Agree)")) from e
            if e.code == 404:
                raise OSError(L("файла нет на Hugging Face", "the file is not on Hugging Face")) from e
            err: Exception = e
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if isinstance(e, OSError) and "sha256" in str(e) and attempt == TRIES:
                raise
            err = e
        if attempt < TRIES:
            say("retry", L(f"  не вышло ({err}), ещё раз через {5 * attempt} с…", f"  failed ({err}), again in {5 * attempt} s…"),
                name=dest.name, attempt=attempt, tries=TRIES, error=str(err))
            time.sleep(5 * attempt)
    raise OSError(str(err))


def plan(m: dict, sets: list[str], models: Path, roots: list[Path]) -> dict:
    out = {}
    for sid in sets:
        s = m["sets"][sid]
        files = []
        for f in s["files"]:
            name = f["path"].rsplit("/", 1)[-1]
            hit = find(name, f["bytes"], f["kind"], [models, *roots])
            files.append({**f, "name": name, "dest": str(models / f["kind"] / name), "found": str(hit) if hit else None})
        out[sid] = {"title": s["title"], "bytes": sum(f["bytes"] for f in files),
                    "have": sum(f["bytes"] for f in files if f["found"]), "gated": bool(s.get("gated")), "files": files}
    return out


def main() -> int:
    global JSON, LANG
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", default=str(ROOT / "install" / "manifest.json"))
    ap.add_argument("--models-dir", required=True)
    ap.add_argument("--sets", default="")
    ap.add_argument("--profile", default="")
    ap.add_argument("--find", default="", help="folders with weights already downloaded, separated by ;")
    ap.add_argument("--token", default="")
    ap.add_argument("--token-file", default="")
    ap.add_argument("--plan", action="store_true", help="only say what is there and what would be downloaded")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--lang", default="ru", choices=("ru", "en"))
    args = ap.parse_args()
    JSON, LANG = args.json, args.lang
    sys.stdout.reconfigure(encoding="utf-8")   # the wizard and PowerShell read UTF-8, not the console's code page

    m = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    sets = [s for s in (m["profiles"].get(args.profile, []) if args.profile else args.sets.split(",")) if s.strip()]
    sets = [s.strip() for s in sets]
    unknown = [s for s in sets if s not in m["sets"]]
    if unknown:
        say("error", L(f"Нет таких наборов: {', '.join(unknown)}", f"No such sets: {', '.join(unknown)}"), code="sets", sets=unknown)
        return 1
    for s in list(sets):   # a set needs another (Ref2VA takes H3's encoder and VAE): it comes along
        for need in m["sets"][s].get("needs", []):
            if need not in sets:
                sets.insert(sets.index(s), need)
    models = Path(args.models_dir)
    roots = [Path(p) for p in args.find.split(";") if p.strip()]
    for kind in KINDS:
        (models / kind).mkdir(parents=True, exist_ok=True)
    for sub in EMPTY:
        (models / sub).mkdir(parents=True, exist_ok=True)

    p = plan(m, sets, models, roots)
    total = sum(s["bytes"] - s["have"] for s in p.values())
    say("plan", L(f"Наборы: {', '.join(s['title'] for s in p.values())}; скачать {gb(total)}",
                  f"Sets: {', '.join(s['title'] for s in p.values())}; to download {gb(total)}"),
        sets={k: {kk: v for kk, v in s.items() if kk != "files"} for k, s in p.items()}, total=total)
    if args.plan:
        return 0

    tok = token(args)
    overall = 0
    result: dict[str, dict] = {}
    for sid, s in p.items():
        say("set", f"\n== {s['title']} ({gb(s['bytes'])}) ==", id=sid, status="running")
        error, refused = None, False
        # small files first: a bad connection shows on the first gigabyte, not after twenty
        for f in sorted(s["files"], key=lambda x: x["bytes"]):
            if f["found"]:
                say("file", L(f"  есть: {f['name']}", f"  present: {f['name']}"), set=sid, name=f["name"], status="present", path=f["found"])
                continue
            if refused:
                continue
            say("file", L(f"  качаю: {f['name']} ({gb(f['bytes'])})", f"  downloading: {f['name']} ({gb(f['bytes'])})"),
                set=sid, name=f["name"], status="download", bytes=f["bytes"])
            last = [0.0]
            base = overall

            def on_bytes(done: int, f=f, base=base) -> None:
                now = time.time()
                if now - last[0] >= 0.5 or done >= f["bytes"]:
                    last[0] = now
                    say("progress", set=sid, name=f["name"], done=done, total=f["bytes"], overall=base + done, overallTotal=total)

            try:
                download(f, Path(f["dest"]), tok, on_bytes)
                overall += f["bytes"]
                say("file", L(f"  готово: {f['name']}", f"  done: {f['name']}"), set=sid, name=f["name"], status="done")
            except Refused as e:
                error, refused = str(e), True
                say("file", f"  {f['name']}: {e}", set=sid, name=f["name"], status="failed", code="access", error=str(e))
            except OSError as e:
                error = str(e)
                say("file", f"  {f['name']}: {e}", set=sid, name=f["name"], status="failed", code="network", error=str(e))
        status = "done" if error is None else "skipped" if refused else "failed"
        result[sid] = {"status": status, "error": error}
        say("set", "", id=sid, status=status, error=error, code="access" if refused else "network" if error else None)

    lines = []
    for sid, r in result.items():
        word = {"done": L("готово", "ready"), "skipped": L("пропущен", "skipped"), "failed": L("не докачан", "not finished")}[r["status"]]
        lines.append(f"  {p[sid]['title']:12} {word}" + (f": {r['error']}" if r["error"] else ""))
    say("summary", L("\nИтог:\n", "\nSummary:\n") + "\n".join(lines), sets=result)
    return 0 if all(r["status"] == "done" for r in result.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
