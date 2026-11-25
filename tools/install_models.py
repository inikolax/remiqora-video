"""Downloads the model sets of install/manifest.json into the models folder - the one downloader of both installers
(setup_models.ps1 and the desktop wizard). Only the stdlib, so any Python runs it.

    python tools/install_models.py --models-dir D:\\models --sets h3,writer [--find D:\\ComfyUI\\models] [--json]
    python tools/install_models.py --models-dir D:\\models --profile faces --plan --json

A file already in the models folder (or in a --find folder, as the worker finds it there) with the size of the official
one is not downloaded again. A download goes to <name>.part and continues from it (HTTP Range) after a cut or a stop,
three tries with a pause, then the sha256 is checked against Hugging Face's. A set that fails (no network, no access to
a gated repository) does not stop the others: the summary says what is missing and why, and a second run continues.
--json prints one JSON object per line for the wizard: plan, file, progress, set, summary.
--pretty (the default on a terminal without --json) is the person's view: a table of sets, a coloured bar per file with
percent, speed and ETA, ✓ / ✗ per file (tools/install_console.py). --plan (--dry-run) downloads nothing.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))   # python -I does not put the script's folder there
try:
    import install_console as con  # noqa: E402
except ImportError:   # the downloader alone (cloud worker, a stray copy): no pretty view
    con = None

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
PRETTY = False
LANG = "ru"
SET_TITLES: dict[str, str] = {}


def say(event: str, text: str = "", **data) -> None:
    if JSON:
        print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)
    elif PRETTY:
        show(event, text, data)
    elif text:
        print(text, flush=True)


def L(ru: str, en: str) -> str:
    return ru if LANG == "ru" else en


def gb(n: float) -> str:
    return f"{n / 1e9:.1f} {L('ГБ', 'GB')}"


# ----- the person's view (--pretty): the same events the wizard gets as JSON, as lines and bars -----
_cur: dict | None = None   # the file on screen: name, bytes, start, base (bytes at the first tick), speed, last, pct


def _cols() -> int:
    return shutil.get_terminal_size((100, 24)).columns


def _pad(line: str) -> str:
    """The line padded to the window's width, so a redraw leaves nothing of the longer one before it."""
    return line + " " * max(_cols() - 1 - len(con.strip(line)), 0)


def _end_file(line: str) -> None:
    global _cur
    con.write(("\r" + _pad(line)) if (_cur and con.is_tty()) else line)
    _cur = None


def _progress(name: str, done: int, total: int) -> None:
    c = _cur
    if c is None:
        return
    now = time.time()
    if c["base"] is None:
        c["base"] = done   # a resumed .part starts above zero: the speed counts only what came in now
    if c["last"] is not None and now > c["last"][0]:
        inst = (done - c["last"][1]) / (now - c["last"][0])
        c["speed"] = inst if not c["speed"] else c["speed"] * 0.8 + inst * 0.2
    c["last"] = (now, done)
    pct = int(done * 100 / total) if total else 0
    if not con.is_tty():   # redirected: a line per 10 %, not a thousand redraws
        if pct // 10 != c["pct"] // 10:
            con.write(f"    {name} {pct}%")
        c["pct"] = pct
        return
    c["pct"] = pct
    eta = (total - done) / c["speed"] if c["speed"] > 0 else None
    tail = (f" {pct:3d}%  {done / 1e9:.1f}/{total / 1e9:.1f} {L('ГБ', 'GB')}  {c['speed'] / 1e6:5.0f} {L('МБ/с', 'MB/s')}  "
            + (L("ещё ", "ETA ") + con.clock(eta) if eta is not None else L("считаю скорость…", "measuring speed…")))
    label = (name if len(name) <= 30 else name[:29] + "…").ljust(30)
    width = min(max(_cols() - 6 - 30 - len(tail) - 3, 8), 30)
    con.write("\r" + _pad(f"    {con.paint('violet', '▸')} {label} {con.bar(done / total if total else 0, width)}{tail}"), end="")


def show(event: str, text: str, d: dict) -> None:
    global _cur
    P = con.paint
    if event == "set" and d.get("status") == "running":
        con.write()
        con.write(f"  {P('violet', '▍', bold=True)} {text.strip().strip('=').strip()}")
    elif event == "file":
        st, name = d.get("status"), d.get("name", "")
        if st == "present":
            con.write(f"    {P('green', '✓')} {name}  {con.dim(L('уже есть', 'already there'))}")
        elif st == "download":
            _cur = {"name": name, "bytes": d["bytes"], "t0": time.time(), "speed": 0.0, "last": None, "pct": -1, "base": None}
            _progress(name, 0, d["bytes"])
        elif st == "done":
            c = _cur or {}
            took = time.time() - c.get("t0", time.time())
            avg = (c.get("bytes", 0) - (c.get("base") or 0)) / took / 1e6 if took > 0.5 else 0
            more = gb(c.get("bytes", 0)) + "  ·  " + con.clock(took) + (f"  ·  {avg:.0f} {L('МБ/с', 'MB/s')}" if avg else "")
            _end_file(f"    {P('green', '✓')} {name}  {con.dim(more)}")
        elif st == "failed":
            _end_file(f"    {P('red', '✗')} {name}  {P('red', d.get('error', ''))}")
    elif event == "progress":
        _progress(d["name"], d["done"], d["total"])
        if d.get("overallTotal"):
            con.title(f"{L('установка', 'installing')} · {int(d['overall'] * 100 / d['overallTotal'])}%")
    elif event == "retry":
        _end_file(f"    {P('amber', '↻')} {text.strip()}")
    elif event == "error":
        con.write(f"  {P('red', '✗', bold=True)} {P('red', text)}")
    elif event == "summary":
        summary(d["sets"])


def plan_table(p: dict, total: int, models: Path, files: bool) -> None:
    """The sets with what is there already and what comes, the models folder and the disk."""
    P = con.paint
    w = max(len(s["title"]) for s in p.values()) + 2
    head = L("Набор", "Set").ljust(w + 2) + L("размер", "size").rjust(10) + L("уже есть", "there").rjust(12) + L("скачать", "to get").rjust(12)
    con.write("  " + con.dim(head))
    for sid, s in p.items():
        need = s["bytes"] - s["have"]
        con.write(f"  {P('green', '✓') if need == 0 else P('violet', '▍')} {s['title'].ljust(w)}{gb(s['bytes']).rjust(10)}{gb(s['have']).rjust(12)}"
                  + (P("cyan", gb(need).rjust(12)) if need else con.dim("—".rjust(12))))
        if files:
            for f in s["files"]:
                con.write(f"      {P('green', '✓') if f['found'] else P('grey', '○')} {f['name']}  {con.dim(gb(f['bytes']))}")
    try:
        free = shutil.disk_usage(models if models.exists() else models.parent).free
    except OSError:
        free = None
    con.write()
    con.write(f"  {con.dim(L('Папка моделей:', 'Models folder:'))} {models}")
    line = f"  {L('Будет скачано', 'To download')}: {P('cyan', gb(total), bold=True)}"
    if free is not None:
        enough = free >= total + 512 * 2**20
        line += f", {L('свободно', 'free')}: {P('green' if enough else 'red', gb(free), bold=True)}"
        if not enough:
            line += "  " + P("red", L("— не хватает места", "- not enough space"))
    con.write(line)


def summary(result: dict) -> None:
    P = con.paint
    con.write()
    con.write(f"  {P('violet', '▍', bold=True)} {L('Итог', 'Summary')}")
    for sid, r in result.items():
        word = {"done": L("готово", "ready"), "skipped": L("пропущен", "skipped"), "failed": L("не докачан", "not finished")}[r["status"]]
        mark, col = ("✓", "green") if r["status"] == "done" else ("✗", "red") if r["status"] == "failed" else ("○", "amber")
        con.write(f"    {P(col, mark)} {SET_TITLES.get(sid, sid).ljust(14)}{P(col, word)}" + (f"  {con.dim(r['error'])}" if r["error"] else ""))
    if any(r["status"] != "done" for r in result.values()):
        con.write()
        con.write("  " + P("amber", L("Часть наборов не скачалась. Запустите setup_models.bat ещё раз — он продолжит с того же места (файлы .part).",
                                     "Some sets did not download. Run setup_models.bat again - it resumes where it stopped (.part files).")))
    con.write()


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


class RenameError(OSError):
    """The file is downloaded and verified, but <name>.part could not be moved into place (held by another program)."""


class ChangedError(OSError):
    """The file on Hugging Face is not the one the manifest describes (re-uploaded, or a wrong pin): retrying cannot help."""


def changed_message(expected: int, got: int | None) -> str:
    return L(f"файл на Hugging Face изменился с выхода этой версии Remiqora Video (ожидалось {expected} байт, на сервере "
             f"{got if got is not None else 'другой размер'}). Обновите Remiqora Video или сообщите об этом",
             f"the file on Hugging Face changed since this version of Remiqora Video (expected {expected} bytes, the server has "
             f"{got if got is not None else 'a different size'}). Update Remiqora Video or report it")


def server_total(r) -> int | None:
    """The whole file's size from a response: Content-Range's total on 206, Content-Length on 200."""
    cr = r.headers.get("Content-Range") or ""
    if "/" in cr and cr.rsplit("/", 1)[1].strip().isdigit():
        return int(cr.rsplit("/", 1)[1])
    if r.status == 206:
        return None
    cl = r.headers.get("Content-Length") or ""
    return int(cl) if cl.isdigit() else None


def resolve_url(f: dict) -> str:
    """The file's download link: the manifest's pinned commit (rev), main when there is none."""
    return f"{HF}/{f['repo']}/resolve/{urllib.parse.quote(f.get('rev') or 'main', safe='')}/{urllib.parse.quote(f['path'])}"


RENAME_WAIT = 60.0   # seconds in total that a held file is waited for


def _held(e: OSError) -> bool:
    return isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32)


def move_into_place(part: Path, dest: Path) -> None:
    """os.replace with a wait: an antivirus or an indexer may hold a freshly written file for a while (WinError 5/32)."""
    waited, pause = 0.0, 1.0
    while True:
        try:
            os.replace(part, dest)
            return
        except OSError as e:
            if not _held(e):
                raise
            if waited >= RENAME_WAIT:
                raise RenameError(L(
                    f"файл скачан и проверен, но переименовать не удалось: его держит другая программа (антивирус?). "
                    f"Подождите и нажмите «повторить» или переименуйте {part.name} в {dest.name} вручную в папке {dest.parent}",
                    f"the file is downloaded and verified, but could not be renamed: another program holds it (antivirus?). "
                    f"Wait and press retry, or rename {part.name} to {dest.name} by hand in {dest.parent}")) from e
            say("retry", L(f"  файл занят другой программой, жду ({int(waited)} с из {int(RENAME_WAIT)})…",
                           f"  the file is held by another program, waiting ({int(waited)} s of {int(RENAME_WAIT)})…"),
                name=dest.name, waited=int(waited), error=str(e))
            time.sleep(pause)
            waited += pause
            pause = min(pause * 2, 10.0)


def download(f: dict, dest: Path, tok: str | None, on_bytes) -> None:
    """One file into dest, through dest.part; raises Refused, or OSError after the tries."""
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = resolve_url(f)
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
                    seen = server_total(r)
                    if seen is not None and seen != total:
                        raise ChangedError(changed_message(total, seen))
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
            if got > total:
                raise ChangedError(changed_message(total, got))
            if got != total:
                raise OSError(L(f"скачано {got} из {total} байт", f"{got} of {total} bytes downloaded"))
            if f.get("sha256") and sha256(part).hexdigest() != f["sha256"]:
                part.unlink()   # a broken file is not continued: the next try starts over
                if not f.get("rev"):   # unpinned: the right size with another content means upstream changed it; retrying cannot help
                    raise ChangedError(L("файл на Hugging Face изменился с выхода этой версии Remiqora Video (не сошлась контрольная сумма sha256). Обновите Remiqora Video или сообщите об этом",
                                         "the file on Hugging Face changed since this version of Remiqora Video (the sha256 checksum does not match). Update Remiqora Video or report it"))
                raise OSError(L("не сошлась контрольная сумма sha256", "the sha256 checksum does not match"))
            break
        except ChangedError:
            part.unlink(missing_ok=True)   # a later run (a fixed manifest) starts clean
            raise
        except urllib.error.HTTPError as e:
            if e.code == 416:   # Range past the end of the server's file: it is not the file we were resuming
                cr = (e.headers.get("Content-Range") or "") if e.headers else ""
                seen = int(cr.rsplit("/", 1)[1]) if "/" in cr and cr.rsplit("/", 1)[1].strip().isdigit() else None
                part.unlink(missing_ok=True)
                raise ChangedError(changed_message(total, seen)) from e
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
    else:
        raise OSError(str(err))
    move_into_place(part, dest)   # outside the network retries: no re-download, no re-hash


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


def h3_licensed(m: dict, sid: str) -> bool:
    """A set under the MiniMax H3 licence (H3 itself, Ref2VA): it does not apply in the US, EU, UK and South Korea."""
    return str(m["sets"][sid].get("license", {}).get("name", "")).startswith("MiniMax H3")


def version() -> str:
    if v := os.environ.get("REMIQORA_VIDEO_VERSION", "").strip():   # the desktop app's own version
        return v
    try:
        return json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return ""


def main() -> int:
    global JSON, PRETTY, LANG
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", default=str(ROOT / "install" / "manifest.json"))
    ap.add_argument("--models-dir", required=True)
    ap.add_argument("--sets", default="")
    ap.add_argument("--profile", default="")
    ap.add_argument("--find", default="", help="folders with weights already downloaded, separated by ;")
    ap.add_argument("--token", default="")
    ap.add_argument("--token-file", default="")
    ap.add_argument("--plan", "--dry-run", dest="plan", action="store_true", help="only say what is there and what would be downloaded")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pretty", action="store_true", help="the person's view (the default on a terminal); --json wins")
    ap.add_argument("--no-banner", action="store_true", help="--pretty without the splash (setup_models.ps1 has shown it)")
    ap.add_argument("--lang", default="ru", choices=("ru", "en"))
    ap.add_argument("--accept-h3", action="store_true", help="the user accepted the MiniMax H3 licence statement (required for H3's sets)")
    args = ap.parse_args()
    JSON, LANG = args.json, args.lang
    PRETTY = con is not None and not JSON and (args.pretty or con.is_tty())
    sys.stdout.reconfigure(encoding="utf-8")   # the wizard and PowerShell read UTF-8, not the console's code page
    if PRETTY:
        con.setup()
        con.title(L("установка", "installing"))
        if not args.no_banner:
            con.banner(L("Установка моделей", "Model installer") + f"  ·  {version()}")
            con.write()

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
    SET_TITLES.update({sid: st["title"] for sid, st in p.items()})
    # the licence matters only for what is still to download: a complete H3 set (an upgrade) needs no tick
    h3_sets = [sid for sid, st in p.items() if h3_licensed(m, sid) and st["bytes"] - st["have"] > 0]
    if h3_sets and not args.accept_h3:   # the licence statement is accepted explicitly in every front end
        say("error", L("Лицензия MiniMax H3 не принята: наборы H3 не качаются без --accept-h3 (галочка в мастере, «y» в меню скрипта).",
                       "The MiniMax H3 licence is not accepted: the H3 sets are not downloaded without --accept-h3."),
            code="licence", sets=h3_sets)
        return 1
    total = sum(s["bytes"] - s["have"] for s in p.values())
    say("plan", L(f"Наборы: {', '.join(s['title'] for s in p.values())}; скачать {gb(total)}",
                  f"Sets: {', '.join(s['title'] for s in p.values())}; to download {gb(total)}"),
        sets={k: {kk: v for kk, v in s.items() if kk != "files"} for k, s in p.items()}, total=total)
    if PRETTY:
        plan_table(p, total, models, files=args.plan)
    if args.plan:
        return 0

    tok = token(args)
    overall = 0
    result: dict[str, dict] = {}
    for sid, s in p.items():
        say("set", f"\n== {s['title']} ({gb(s['bytes'])}) ==", id=sid, status="running")
        error, refused = None, False
        codes: dict[str, str] = {}
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
                code = "rename" if isinstance(e, RenameError) else "changed" if isinstance(e, ChangedError) else "network"
                codes[sid] = code
                say("file", f"  {f['name']}: {e}", set=sid, name=f["name"], status="failed", code=code, error=str(e))
        status = "done" if error is None else "skipped" if refused else "failed"
        result[sid] = {"status": status, "error": error}
        say("set", "", id=sid, status=status, error=error, code="access" if refused else codes.get(sid, "network") if error else None)

    lines = []
    for sid, r in result.items():
        word = {"done": L("готово", "ready"), "skipped": L("пропущен", "skipped"), "failed": L("не докачан", "not finished")}[r["status"]]
        lines.append(f"  {p[sid]['title']:12} {word}" + (f": {r['error']}" if r["error"] else ""))
    say("summary", L("\nИтог:\n", "\nSummary:\n") + "\n".join(lines), sets=result)
    return 0 if all(r["status"] == "done" for r in result.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
