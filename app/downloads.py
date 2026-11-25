"""Weights from Hugging Face, one file at a time, in the background (phase 6, after Remiqora's Models page).

A file goes to <folder>/<name>.part and is renamed when its size matches what Hugging Face says; a cut or stopped
download continues from the .part (HTTP Range). The token, if any, is kept in data/hf_token and only sent to
huggingface.co. Sizes come from Hugging Face's API when the page asks, never written into the code.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from . import config
from . import i18n

HF = "https://huggingface.co"
TOKEN_FILE = config.DATA_DIR / "hf_token"
CHUNK = 8 * 1024 * 1024
RENAME_WAIT = 60.0   # seconds in total that a file held by another program is waited for
_sizes: dict[tuple[str, str], tuple[float, Optional[int]]] = {}   # (repo, path) -> (when, bytes)
_offline: dict[tuple[str, str], float] = {}                        # (repo, folder) -> when asking failed


class DownloadError(Exception):
    pass


_pins: tuple[float, dict] = (-1.0, {})   # (manifest mtime, (repo, path) -> manifest entry)


def pin(repo: str, path: str) -> Optional[dict]:
    """The file's entry in install/manifest.json (rev, bytes, sha256 - the same pin the installer downloads by), or None.
    Read on the server from repo+path, never from the client; re-read when the manifest changes."""
    global _pins
    mf = config.ROOT / "install" / "manifest.json"
    try:
        mt = mf.stat().st_mtime
        if mt != _pins[0]:
            sets = json.loads(mf.read_text(encoding="utf-8")).get("sets", {})
            _pins = (mt, {(f["repo"], f["path"]): f for s in sets.values() for f in s.get("files", []) if f.get("repo") and f.get("path")})
    except (OSError, ValueError, AttributeError):
        _pins = (-1.0, {})
    return _pins[1].get((repo, path))


def _token() -> Optional[str]:
    try:
        t = TOKEN_FILE.read_text(encoding="utf-8").strip()
        return t or None
    except OSError:
        return None


def has_token() -> bool:
    return bool(_token())


def set_token(token: Optional[str]) -> None:
    if token:
        TOKEN_FILE.write_text(token.strip(), encoding="utf-8")
    else:
        TOKEN_FILE.unlink(missing_ok=True)


def _request(url: str, headers: Optional[dict] = None) -> urllib.request.Request:
    h = {"User-Agent": "h3studio"}
    if (t := _token()) and urllib.parse.urlparse(url).hostname == "huggingface.co":
        h["Authorization"] = f"Bearer {t}"
    return urllib.request.Request(url, headers={**h, **(headers or {})})


def _http_error(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 401:
            return i18n.L("Нужен токен Hugging Face: впишите его ниже", "A Hugging Face token is needed: enter it below")
        if e.code == 403:
            return i18n.L("Нет доступа: откройте страницу модели на Hugging Face и примите лицензию (Agree)", "No access: open the model's page on Hugging Face and accept the license (Agree)")
        if e.code == 404:
            return i18n.L("Файла нет на Hugging Face (переименовали или убрали)", "The file is not on Hugging Face (renamed or removed)")
        return i18n.L(f"Hugging Face ответил {e.code}", f"Hugging Face answered {e.code}")
    return i18n.L("Нет связи с Hugging Face", "No connection to Hugging Face")


def size(repo: str, path: str, rev: str = "main") -> Optional[int]:
    """The file's size from Hugging Face (cached for an hour); None when it can't be asked."""
    key = (repo, path) if rev == "main" else (repo, path, rev)
    when, n = _sizes.get(key, (0.0, None))
    if time.time() - when < 3600 and n:
        return n
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    if time.time() - _offline.get((repo, folder), 0.0) < 300:
        return n   # asked a moment ago and failed: the page must not wait on the network every time
    try:
        url = f"{HF}/api/models/{repo}/tree/{urllib.parse.quote(rev, safe='')}" + (f"/{urllib.parse.quote(folder)}" if folder else "")
        with urllib.request.urlopen(_request(url), timeout=10) as r:
            for f in json.load(r):
                if f.get("path") and f.get("type") == "file":
                    _sizes[(repo, f["path"]) if rev == "main" else (repo, f["path"], rev)] = (time.time(), int((f.get("lfs") or {}).get("size") or f.get("size") or 0) or None)
    except (OSError, ValueError):
        _offline[(repo, folder)] = time.time()
        return n
    return _sizes.get(key, (0.0, None))[1]


def parse_url(url: str) -> tuple[str, str]:
    """A Hugging Face file link (…/<owner>/<repo>/blob|resolve/<rev>/<path>) -> (repo, path)."""
    repo, path, _ = parse_link(url)
    return repo, path


def parse_link(url: str) -> tuple[str, str, str]:
    """The same link -> (repo, path, rev): the link's own revision (a branch or a commit) is what gets downloaded."""
    u = urllib.parse.urlparse(url.strip())
    parts = [p for p in u.path.split("/") if p]
    if u.hostname != "huggingface.co" or len(parts) < 5 or parts[2] not in ("blob", "resolve"):
        raise DownloadError(i18n.L("Нужна ссылка на файл Hugging Face: https://huggingface.co/<автор>/<модель>/blob/main/<файл>", "A Hugging Face file link is needed: https://huggingface.co/<author>/<model>/blob/main/<file>"))
    return f"{parts[0]}/{parts[1]}", urllib.parse.unquote("/".join(parts[4:])), urllib.parse.unquote(parts[3]) or "main"


class Download:
    def __init__(self, repo: str, path: str, folder: Path, rev: str = "main"):
        self.repo, self.path, self.folder, self.rev = repo, path, folder, rev or "main"
        self.name = path.rsplit("/", 1)[-1]
        self.status = "running"            # running | done | failed | cancelled
        # a manifest file asked for by main (the catalog's «Скачать») is fetched at the manifest's pinned commit and
        # checked against its size and sha256; a link pasted with its own revision, or a file off the manifest, is not
        self.pin = pin(repo, path) if self.rev == "main" else None
        if self.pin and self.pin.get("rev"):
            self.rev = self.pin["rev"]
        self.done = 0
        self.total = (self.pin or {}).get("bytes") or (size(repo, path, self.rev) if self.rev != "main" else size(repo, path))
        self.error: Optional[str] = None
        self.started = time.time()
        self._stop = threading.Event()
        self.speed = 0.0

    def public(self) -> dict:
        return {"repo": self.repo, "path": self.path, "name": self.name, "folder": str(self.folder), "status": self.status,
                "done": self.done, "total": self.total, "error": self.error, "speed": round(self.speed)}

    def run(self) -> None:
        dest, part = self.folder / self.name, self.folder / (self.name + ".part")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            have = part.stat().st_size if part.exists() else 0
            if self.total:
                free = shutil.disk_usage(self.folder).free
                if free < self.total - have + 512 * 1024 * 1024:
                    raise DownloadError(i18n.L(f"Мало места на диске: нужно {(self.total - have) / 2**30:.1f} ГБ, свободно {free / 2**30:.1f} ГБ", f"Not enough disk space: {(self.total - have) / 2**30:.1f} GB needed, {free / 2**30:.1f} GB free"))
            url = f"{HF}/{self.repo}/resolve/{urllib.parse.quote(self.rev, safe='')}/{urllib.parse.quote(self.path)}"
            req = _request(url, {"Range": f"bytes={have}-"} if have else None)
            try:
                r = urllib.request.urlopen(req, timeout=60)
            except urllib.error.HTTPError as e:
                if e.code == 416 and self.total and have >= self.total:   # the .part is already whole
                    r = None
                elif e.code == 416:   # Range past the end of the server's file: it is not the file we were resuming
                    part.unlink(missing_ok=True)
                    raise DownloadError(self._changed(None)) from e
                else:
                    raise
            if r is not None:
                with r:
                    seen = _server_total(r)
                    if seen is not None and self.total and seen != self.total:
                        part.unlink(missing_ok=True)
                        raise DownloadError(self._changed(seen))
                    if have and r.status != 206:   # the server ignored Range: start over
                        have = 0
                    self.total = self.total or (int(r.headers.get("Content-Length", 0)) + have) or None
                    self.done = have
                    t0, d0 = time.time(), have
                    with open(part, "ab" if have else "wb") as f:
                        while True:
                            if self._stop.is_set():
                                self.status = "cancelled"
                                return
                            block = r.read(CHUNK)
                            if not block:
                                break
                            f.write(block)
                            self.done += len(block)
                            if (dt := time.time() - t0) > 2:
                                self.speed, t0, d0 = (self.done - d0) / dt, time.time(), self.done
            got = part.stat().st_size
            if self.total and got > self.total:
                part.unlink(missing_ok=True)
                raise DownloadError(self._changed(got))
            if self.total and got != self.total:
                raise DownloadError(i18n.L(f"Файл скачался не целиком: {got} из {self.total} байт — нажмите «Продолжить»", f"The file was not downloaded fully: {got} of {self.total} bytes - press «Continue»"))
            want = (self.pin or {}).get("sha256")
            if want and self._sha256(part) != want:
                part.unlink(missing_ok=True)   # a wrong file is not continued: «Скачать» starts over
                raise DownloadError(i18n.L("Не сошлась контрольная сумма sha256: файл на Hugging Face не тот, что в списке Remiqora Video. Файл удалён; обновите Remiqora Video или сообщите об этом",
                                           "The sha256 checksum does not match: the file on Hugging Face is not the one in Remiqora Video's list. The file was deleted; update Remiqora Video or report it"))
            if not self._move_into_place(part, dest):
                self.status = "cancelled"
                return
            self.done, self.status = got, "done"
        except DownloadError as e:
            self.status, self.error = "failed", str(e)
        except (urllib.error.URLError, OSError) as e:
            self.status, self.error = "failed", _http_error(e) if isinstance(e, urllib.error.URLError) else i18n.L(f"Ошибка записи: {e}", f"Write error: {e}")

    @staticmethod
    def _sha256(path: Path) -> str:
        """Hash of a finished .part; run() is already in its own thread, so a 20 GB file does not block the server."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while block := f.read(CHUNK):
                h.update(block)
        return h.hexdigest()

    def _changed(self, seen: Optional[int]) -> str:
        """The server's file is not the size we know (it was re-uploaded): the .part is useless, retrying will not help."""
        had = f"{self.total}" if self.total else "?"
        got = f"{seen}" if seen is not None else i18n.L("другой размер", "a different size")
        return i18n.L(f"Файл на Hugging Face изменился с выхода этой версии Remiqora Video (ожидалось {had} байт, на сервере {got}). Обновите Remiqora Video или сообщите об этом",
                      f"The file on Hugging Face changed since this version of Remiqora Video (expected {had} bytes, the server has {got}). Update Remiqora Video or report it")

    def _move_into_place(self, part: Path, dest: Path) -> bool:
        """part -> dest, waiting while another program (antivirus, indexer) holds the file; False if cancelled meanwhile."""
        waited, pause = 0.0, 1.0
        while True:
            try:
                part.replace(dest)
                return True
            except OSError as e:
                if not (isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32)):
                    raise
                if waited >= RENAME_WAIT:
                    raise DownloadError(i18n.L(
                        f"Файл скачан целиком, но переименовать его не удалось: его держит другая программа (антивирус?). Нажмите «Продолжить» или переименуйте {part.name} в {dest.name} вручную в папке {dest.parent}",
                        f"The file was downloaded fully, but could not be renamed: another program holds it (antivirus?). Press «Continue» or rename {part.name} to {dest.name} by hand in {dest.parent}")) from e
                if self._stop.wait(pause):
                    return False
                waited += pause
                pause = min(pause * 2, 10.0)

    def cancel(self) -> None:
        self._stop.set()


_current: Optional[Download] = None
_last: dict[tuple[str, str], Download] = {}


def _server_total(r) -> Optional[int]:
    """The whole file's size from a response: Content-Range's total on 206, Content-Length on 200."""
    cr = r.headers.get("Content-Range") or ""
    if "/" in cr and cr.rsplit("/", 1)[1].strip().isdigit():
        return int(cr.rsplit("/", 1)[1])
    if r.status == 206:
        return None
    cl = r.headers.get("Content-Length") or ""
    return int(cl) if cl.isdigit() else None


def active() -> Optional[Download]:
    return _current if _current and _current.status == "running" else None


def start(repo: str, path: str, folder: Path, rev: str = "main") -> Download:
    global _current
    if active():
        raise DownloadError(i18n.L("Уже идёт скачивание: файлы качаются по одному", "A download is already running: files download one at a time"))
    # the file's name lands in `folder`: a pasted link's «%5C» (a backslash on Windows) or «..» must not lead out of it
    name = path.rsplit("/", 1)[-1]
    if not name or name in (".", "..") or any(ch in name for ch in '\\:*?"<>|'):
        raise DownloadError(i18n.L(f"Такое имя файла не годится: {name}", f"This file name can't be used: {name}"))
    d = Download(repo, path, folder, rev)
    _current = _last[(repo, path)] = d
    threading.Thread(target=d.run, daemon=True).start()
    return d


def cancel() -> None:
    if d := active():
        d.cancel()


def state(repo: str, path: str) -> Optional[dict]:
    d = _last.get((repo, path))
    return d.public() if d else None


def partial(folder: Path, name: str) -> int:
    """Bytes already in a stopped download's .part (shown as «Продолжить»)."""
    p = folder / (name + ".part")
    return p.stat().st_size if p.exists() else 0
