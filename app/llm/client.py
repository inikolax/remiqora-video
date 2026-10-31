"""The local LLM, as in Remiqora: our own llama-server (llama.cpp) with a GGUF, started for an LLM job and stopped after,
so H3 gets the memory back. No LM Studio and no Ollama: only LM Studio's download folder is read, so a model fetched
there shows up here by itself.

Models: every *.gguf under LLM_DIRS, sub-folders included. An mmproj file is the part that sees pictures; it is paired
with a model from the same folder, or else by name ("gemma-4-E4B-it-mmproj-BF16" goes with "gemma-4-E4B-it-…-Q8_0").
Answers: JSON constrained by a schema (`response_format: json_schema`), cached on disk by a hash of the whole request,
so the same idea with the same seed gives the same storyboard at once.
"""
from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .. import config, i18n
from ..engine import winjob
from ..engine.comfy import COMFY

START_TIMEOUT = 180
URL = f"http://127.0.0.1:{config.LLM_PORT}"
_QUANT = re.compile(r"[-_.](i?q\d\w*|bf16|f16|f32|fp16|mxfp4|ud-\w+)$", re.IGNORECASE)
_SPLIT = re.compile(r"-(\d{5})-of-\d{5}$")
MIME = {".png": "image/png", ".webp": "image/webp"}


# The texts' language the writer and the translator work in (i18n): the system prompts say "Russian" where they mean
# the user's language, and get the language of the job at hand instead - a video's own (i18n.plan_lang), else the
# texts' setting. Russian leaves them word for word as they were (and so their cached answers).
LANG: contextvars.ContextVar[str] = contextvars.ContextVar("llm_lang", default="Russian")


def use_lang(name: str) -> None:
    LANG.set(name or "Russian")


def lang() -> str:
    return LANG.get()


class LLMError(Exception):
    pass


# Every text field gets a length cap in the schema, so llama-server's grammar closes it there: a model can get stuck
# inside one string until max_tokens runs out (Mistral-Small 24B on a world description, gemma on a look, 2026-10-22),
# and the answer is cut JSON. Caps in characters, generous: a Russian field is longer than its English twin.
FIELD_CAP = {"title_ru": 160, "style_en": 700, "audio_en": 500, "sound_en": 400, "place_en": 500, "to_en": 300,
             "en": 1000, "ru": 1400, "outfit_en": 500, "outfit_ru": 700, "start_en": 600, "beats_en": 400,
             "prompt_en": 6000}
DEFAULT_CAP = 900


def capped(schema, key: str = "") -> dict:
    """The schema with maxLength on every string that has none (enums are left alone)."""
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if out.get("type") == "string" and "enum" not in out and "maxLength" not in out:
        out["maxLength"] = FIELD_CAP.get(key, DEFAULT_CAP)
    if isinstance(out.get("properties"), dict):
        out["properties"] = {k: capped(v, k) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = capped(out["items"], key)   # an array's items keep its name: beats_en -> each beat
    return out


@dataclass
class LlmModel:
    id: str                    # d<dir index>/<path relative to it>
    name: str                  # file name without .gguf
    path: Path
    size_gb: float
    mmproj: Optional[Path]     # None: the model can't see pictures
    source: str                # "LM Studio" or the folder

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "size_gb": self.size_gb, "vision": self.mmproj is not None,
                "mmproj": self.mmproj.name if self.mmproj else None, "source": self.source}


def _key(stem: str) -> str:
    """'gemma-4-E4B-it-mmproj-BF16' -> 'gemma-4-e4b-it': what an mmproj and its model have in common."""
    s = stem.lower().replace("mmproj", "")
    while (t := _QUANT.sub("", s)) != s:
        s = t
    return re.sub(r"[-_.]+", "-", s).strip("-")


def models() -> list[LlmModel]:
    found: list[tuple[int, Path, Path]] = []
    projs: list[Path] = []
    for i, root in enumerate(config.LLM_DIRS):
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.gguf"), key=lambda q: str(q).lower()):
            if "mmproj" in p.name.lower():
                projs.append(p)
            elif not (m := _SPLIT.search(p.stem)) or m.group(1) == "00001":   # a split model: its first part only
                found.append((i, root, p))
    lms = str(config.LLM_DIRS[0]) if config.LLM_DIRS else ""
    out = []
    for i, root, p in found:
        same = [q for q in projs if q.parent == p.parent]
        by_name = sorted((q for q in projs if len(_key(q.stem)) >= 6 and p.stem.lower().replace("_", "-").startswith(_key(q.stem))),
                         key=lambda q: -len(_key(q.stem)))
        mm = (same or by_name or [None])[0]
        size = sum(q.stat().st_size for q in p.parent.glob(_SPLIT.sub("", p.stem) + "*.gguf")) if _SPLIT.search(p.stem) else p.stat().st_size
        out.append(LlmModel(id=f"d{i}/{p.relative_to(root).as_posix()}", name=_SPLIT.sub("", p.stem), path=p,
                            size_gb=round(size / 2**30, 1), mmproj=mm,
                            source="LM Studio" if str(root) == lms and "lmstudio" in lms.lower() else str(root)))
    return out


def find(model_id: Optional[str]) -> LlmModel:
    """The model by id; without one, the default (LLM_MODEL in the file name), else the first one with eyes."""
    ms = models()
    if not ms:
        raise LLMError(i18n.L("Нет ни одной LLM: положите GGUF в ", "No LLM at all: put a GGUF into ")
                       + i18n.L(" или ", " or ").join(map(str, config.LLM_DIRS)) + i18n.L(" (LLM_DIRS в .env)", " (LLM_DIRS in .env)"))
    if model_id:
        for m in ms:
            if m.id == model_id:
                return m
        raise LLMError(i18n.L(f"Модель не найдена: {model_id}", f"Model not found: {model_id}"))
    want = config.LLM_MODEL.lower()
    return next((m for m in ms if want in m.name.lower()), None) or next((m for m in ms if m.mmproj), ms[0])


# ---------- llama-server ----------

def _port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", config.LLM_PORT)) == 0


def _env(server: Path) -> dict:
    """The server's environment: LM Studio keeps an engine's CUDA (or Vulkan) runtime apart, in backends/vendor - on
    PATH, or its llama-server does not start."""
    env, vendor = dict(os.environ), server.parent.parent / "vendor"
    kind = next((k for k in ("cuda", "vulkan") if k in server.parent.name), None)
    if kind and vendor.is_dir():
        extra = [str(d) for d in sorted(vendor.iterdir()) if d.is_dir() and kind in d.name]
        env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    return env


# why a llama-server dies at once, by its exit code, in the user's words
BLOCKED, NO_DLL = 0xC0E90002, 0xC0000135


def _quiet_errors() -> None:
    """No Windows box («Bad Image») over the user's screen for a server that cannot load: the child inherits this
    process's error mode, and the job says what happened in its own words."""
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        k.SetErrorMode(k.GetErrorMode() | 0x0001)   # SEM_FAILCRITICALERRORS


def _start_failed(code: int) -> str:
    server = config.LLAMA_SERVER_BIN
    if code & 0xFFFFFFFF == BLOCKED:
        return i18n.L(f"Windows не дала запустить llama-server: включено «Интеллектуальное управление приложениями» "
                      f"(Smart App Control), а у этой сборки llama.cpp нет цифровой подписи ({server}). Выключать защиту не "
                      f"нужно: установите LM Studio (бесплатно; запускать её не придётся) — после перезапуска студия сама "
                      f"возьмёт её подписанный движок; или положите подписанную сборку в tools\\llama и перезапустите студию, "
                      f"или укажите её путь в «Модели и настройки» → «Инструменты».",
                      f"Windows did not let llama-server start: Smart App Control is on, and this llama.cpp build has no "
                      f"digital signature ({server}). No need to turn the protection off: install LM Studio (free; you won't "
                      f"have to run it) and after a restart the studio takes its signed engine by itself; or put a signed "
                      f"build into tools\\llama and restart the studio, or give its path in «Models and settings» → «Tools».")
    if code & 0xFFFFFFFF == NO_DLL:
        return i18n.L(f"llama-server не нашёл свои библиотеки ({server}): рядом с ним должны лежать DLL его сборки "
                      f"(ggml, llama, для видеокарты — cudart и cublas).",
                      f"llama-server did not find its libraries ({server}): its build's DLLs must lie next to it "
                      f"(ggml, llama, and for the GPU cudart and cublas).")
    return i18n.L(f"llama-server не запустился (код {code}). Конец журнала data\\llama-server.log:\n{_log_tail()}",
                  f"llama-server did not start (code {code}). The end of the log data\\llama-server.log:\n{_log_tail()}")


def _healthy() -> bool:
    if not _port_open():   # asking a closed port over HTTP waits for a timeout
        return False
    try:
        with urllib.request.urlopen(URL + "/health", timeout=3) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def _log_tail(n: int = 20) -> str:
    try:
        return "\n".join(config.LLM_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


class LlamaServer:
    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.model: Optional[LlmModel] = None
        self._job = None

    @property
    def pid(self) -> Optional[int]:
        return self.proc.pid if self.proc and self.proc.poll() is None else None

    async def start(self, m: LlmModel) -> None:
        if self.pid and self.model and self.model.path == m.path:
            return
        await self.stop()
        if not config.LLAMA_SERVER_BIN.exists():
            raise LLMError(i18n.L(f"Нет llama-server: {config.LLAMA_SERVER_BIN} («Модели и настройки» или LLAMA_SERVER_BIN в .env)",
                                      f"No llama-server: {config.LLAMA_SERVER_BIN} («Models and settings» or LLAMA_SERVER_BIN in .env)"))
        if await asyncio.to_thread(_port_open):
            raise LLMError(i18n.L(f"Порт {config.LLM_PORT} занят другим процессом (LLM_PORT в .env)",
                                      f"Port {config.LLM_PORT} is taken by another process (LLM_PORT in .env)"))
        cmd = [str(config.LLAMA_SERVER_BIN), "-m", str(m.path), "--host", "127.0.0.1", "--port", str(config.LLM_PORT),
               "-c", str(config.LLM_CTX), "-ngl", "99",
               "-np", "1",        # one slot: the whole context is this job's
               "--jinja",         # the model's chat template, so `enable_thinking: false` reaches it
               "--no-webui"]
        if m.mmproj:
            cmd += ["--mmproj", str(m.mmproj)]
        log = open(config.LLM_LOG, "w", encoding="utf-8", errors="replace")
        _quiet_errors()
        self.proc = subprocess.Popen(cmd, cwd=config.LLAMA_SERVER_BIN.parent, stdout=log, stderr=subprocess.STDOUT, env=_env(config.LLAMA_SERVER_BIN),
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.close()
        self._job = winjob.kill_with_us(self.proc.pid)
        self.model = m
        t0 = time.time()
        while time.time() - t0 < START_TIMEOUT:
            if self.proc.poll() is not None:
                code = self.proc.returncode
                await self.stop()
                raise LLMError(_start_failed(code))
            if await asyncio.to_thread(_healthy):
                return
            await asyncio.sleep(0.5)
        await self.stop()
        raise LLMError(i18n.L(f"llama-server не поднялся за {START_TIMEOUT} с. Журнал: data\\llama-server.log",
                              f"llama-server did not come up in {START_TIMEOUT} s. Log: data\\llama-server.log"))

    async def stop(self) -> None:
        p, self.proc, self.model = self.proc, None, None
        if p and p.poll() is None:
            p.terminate()
            try:
                await asyncio.to_thread(p.wait, 10)
            except subprocess.TimeoutExpired:
                p.kill()
        winjob.close(self._job)
        self._job = None


SERVER = LlamaServer()


# ---------- asking ----------

def _post(path: str, body: dict, timeout: float = 600) -> dict:
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise LLMError(f"llama-server {e.code}: {e.read().decode('utf-8', 'replace')[:500]}") from e


class Client:
    def __init__(self, m: LlmModel) -> None:
        self.model = m
        self.calls = self.cached = self.retries = 0
        self.seconds = 0.0

    async def chat_json(self, system: str, user: str, schema: dict, *, images: tuple[Path, ...] = (),
                        temperature: float = 0.7, seed: int = 1, max_tokens: int = 4096, use_cache: bool = True) -> dict:
        system = system.replace("Russian", LANG.get())
        if LANG.get() != "Russian":   # the fields' names keep their old «_ru», and a model follows the name over the rules
            system += (f"\n\nLanguage: every field named ru, title_ru, outfit_ru or ending in _ru is written in {LANG.get()}, "
                       f"never in Russian - the names are historical.")
        if images and not self.model.mmproj:
            raise LLMError(i18n.L(f"Модель {self.model.name} не видит картинок: рядом с ней нет mmproj-файла",
                                  f"The model {self.model.name} does not see pictures: there is no mmproj file next to it"))
        imgs = [(MIME.get(Path(p).suffix.lower(), "image/jpeg"), base64.b64encode(Path(p).read_bytes()).decode()) for p in images]
        key = hashlib.sha1(json.dumps(
            [self.model.name, self.model.path.stat().st_size, system, user, schema,
             [hashlib.sha1(b.encode()).hexdigest() for _, b in imgs], temperature, seed, max_tokens],
            ensure_ascii=False).encode()).hexdigest()
        cache = config.LLM_CACHE / f"{key}.json"
        if use_cache and cache.exists():
            self.cached += 1
            return json.loads(cache.read_text(encoding="utf-8"))

        content: list[dict] | str = user
        if imgs:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b}"}} for mime, b in imgs]
        body = {
            "model": self.model.name, "temperature": temperature, "seed": seed, "max_tokens": max_tokens, "top_p": 0.95,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": capped(schema)}},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        # a cut answer (the token limit hit, broken JSON) is asked once more with another seed before it is an error
        for attempt in (1, 2):
            t0 = time.time()
            d = await asyncio.to_thread(_post, "/v1/chat/completions", body)
            self.calls += 1
            self.seconds += time.time() - t0
            choice = d["choices"][0]
            text = choice["message"].get("content") or ""
            try:
                data = json.loads(text)
                break
            except json.JSONDecodeError as e:
                why = (i18n.L("упёрлась в лимит ответа", "hit the answer limit") if choice.get("finish_reason") == "length"
                       else i18n.L(f"ответила не JSON ({e})", f"answered not in JSON ({e})"))
                if attempt == 2:
                    raise LLMError(i18n.L(f"{self.model.name} дважды оборвала ответ: {why}. Попробуйте ещё раз или другую модель. "
                                          f"Начало ответа: {text[:300]}",
                                          f"{self.model.name} cut its answer short twice: {why}. Try again or another model. "
                                          f"The answer's start: {text[:300]}")) from e
                self.retries += 1
                body = {**body, "seed": seed + 7919}
        cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return data


_depth = {"n": 0, "model": None}


@asynccontextmanager
async def session(model_id: Optional[str] = None):
    """For one GPU job: H3's weights out of the memory, our llama-server up, and down again after.
    Re-entrant: a session inside another with the same model (the graph's «Переписать» runs several writer nodes,
    each opening its own) uses the running server and leaves it up - one model load for the whole job."""
    m = find(model_id)
    if _depth["n"] and _depth["model"] == m.path:
        _depth["n"] += 1
        try:
            yield Client(m)
        finally:
            _depth["n"] -= 1
        return
    await COMFY.free()
    await SERVER.start(m)
    outer = _depth["n"] == 0
    _depth.update(n=_depth["n"] + 1, model=m.path)
    try:
        yield Client(m)
    finally:
        _depth["n"] -= 1
        if outer:
            _depth["model"] = None
            await SERVER.stop()
