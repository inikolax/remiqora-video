"""Weights from Hugging Face, one file at a time, in the background (phase 6, after Remiqora's Models page).

A file goes to <folder>/<name>.part and is renamed when its size matches what Hugging Face says; a cut or stopped
download continues from the .part (HTTP Range). The token, if any, is kept in data/hf_token and only sent to
huggingface.co. Sizes come from Hugging Face's API when the page asks, never written into the code.
"""
from __future__ import annotations

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
_sizes: dict[tuple[str, str], tuple[float, Optional[int]]] = {}   # (repo, path) -> (when, bytes)
_offline: dict[tuple[str, str], float] = {}                        # (repo, folder) -> when asking failed


class DownloadError(Exception):
    pass


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


def size(repo: str, path: str) -> Optional[int]:
    """The file's size from Hugging Face (cached for an hour); None when it can't be asked."""
    key = (repo, path)
    when, n = _sizes.get(key, (0.0, None))
    if time.time() - when < 3600 and n:
        return n
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    if time.time() - _offline.get((repo, folder), 0.0) < 300:
        return n   # asked a moment ago and failed: the page must not wait on the network every time
    try:
        url = f"{HF}/api/models/{repo}/tree/main" + (f"/{urllib.parse.quote(folder)}" if folder else "")
        with urllib.request.urlopen(_request(url), timeout=10) as r:
            for f in json.load(r):
                if f.get("path") and f.get("type") == "file":
                    _sizes[(repo, f["path"])] = (time.time(), int((f.get("lfs") or {}).get("size") or f.get("size") or 0) or None)
    except (OSError, ValueError):
        _offline[(repo, folder)] = time.time()
        return n
    return _sizes.get(key, (0.0, None))[1]


def parse_url(url: str) -> tuple[str, str]:
    """A Hugging Face file link (…/<owner>/<repo>/blob|resolve/<rev>/<path>) -> (repo, path)."""
    u = urllib.parse.urlparse(url.strip())
    parts = [p for p in u.path.split("/") if p]
    if u.hostname != "huggingface.co" or len(parts) < 5 or parts[2] not in ("blob", "resolve"):
        raise DownloadError(i18n.L("Нужна ссылка на файл Hugging Face: https://huggingface.co/<автор>/<модель>/blob/main/<файл>", "A Hugging Face file link is needed: https://huggingface.co/<author>/<model>/blob/main/<file>"))
    return f"{parts[0]}/{parts[1]}", urllib.parse.unquote("/".join(parts[4:]))


class Download:
    def __init__(self, repo: str, path: str, folder: Path):
        self.repo, self.path, self.folder = repo, path, folder
        self.name = path.rsplit("/", 1)[-1]
        self.status = "running"            # running | done | failed | cancelled
        self.done, self.total = 0, size(repo, path)
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
            url = f"{HF}/{self.repo}/resolve/main/{urllib.parse.quote(self.path)}"
            req = _request(url, {"Range": f"bytes={have}-"} if have else None)
            try:
                r = urllib.request.urlopen(req, timeout=60)
            except urllib.error.HTTPError as e:
                if e.code == 416 and self.total and have >= self.total:   # the .part is already whole
                    r = None
                else:
                    raise
            if r is not None:
                with r:
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
            if self.total and got != self.total:
                raise DownloadError(i18n.L(f"Файл скачался не целиком: {got} из {self.total} байт — нажмите «Продолжить»", f"The file was not downloaded fully: {got} of {self.total} bytes - press «Continue»"))
            part.replace(dest)
            self.done, self.status = got, "done"
        except DownloadError as e:
            self.status, self.error = "failed", str(e)
        except (urllib.error.URLError, OSError) as e:
            self.status, self.error = "failed", _http_error(e) if isinstance(e, urllib.error.URLError) else i18n.L(f"Ошибка записи: {e}", f"Write error: {e}")

    def cancel(self) -> None:
        self._stop.set()


_current: Optional[Download] = None
_last: dict[tuple[str, str], Download] = {}


def active() -> Optional[Download]:
    return _current if _current and _current.status == "running" else None


def start(repo: str, path: str, folder: Path) -> Download:
    global _current
    if active():
        raise DownloadError(i18n.L("Уже идёт скачивание: файлы качаются по одному", "A download is already running: files download one at a time"))
    # the file's name lands in `folder`: a pasted link's «%5C» (a backslash on Windows) or «..» must not lead out of it
    name = path.rsplit("/", 1)[-1]
    if not name or name in (".", "..") or any(ch in name for ch in '\\:*?"<>|'):
        raise DownloadError(i18n.L(f"Такое имя файла не годится: {name}", f"This file name can't be used: {name}"))
    d = Download(repo, path, folder)
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
