"""The local LLM, as in Remiqora: our own llama-server (llama.cpp) with a GGUF, started for an LLM job and stopped after,
so H3 gets the memory back. No LM Studio and no Ollama: only LM Studio's download folder is read, so a model fetched
there shows up here by itself.

Models: every *.gguf under LLM_DIRS, sub-folders included. An mmproj file is the part that sees pictures; it is paired
with a model from the same folder, or else by name ("gemma-4-E4B-it-mmproj-BF16" goes with "gemma-4-E4B-it-…-Q8_0").
Answers: JSON constrained by a schema (`response_format: json_schema`), cached on disk by a hash of the whole request,
so the same idea with the same seed gives the same storyboard at once.

ENGINE=remote: the writer runs on the cloud server too (cloud/worker_server.py): its GGUFs are the server's (<models>/llm on
the pod's volume), RemoteLlama starts and stops its llama-server there, and a call goes through /llm/call - the request
runs on the server and the answer is fetched, so RunPod's proxy (100 s per request) never cuts a long answer.
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
import threading
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .. import config, i18n
from ..engine import remote, winjob
from ..engine.comfy import COMFY
from ..engine.errors import EngineError

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
    bytes: int = 0             # a cloud model's size (its path is the server's, relative to its models folder)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "size_gb": self.size_gb, "vision": self.mmproj is not None,
                "mmproj": self.mmproj.name if self.mmproj else None, "source": self.source}


def _key(stem: str) -> str:
    """'gemma-4-E4B-it-mmproj-BF16' -> 'gemma-4-e4b-it': what an mmproj and its model have in common."""
    s = stem.lower().replace("mmproj", "")
    while (t := _QUANT.sub("", s)) != s:
        s = t
    return re.sub(r"[-_.]+", "-", s).strip("-")


def cloud() -> bool:
    return config.ENGINE == "remote"


def _manifest_llms(sets: list[str]) -> list[dict]:
    """The writer's GGUFs a deployed server got from install/manifest.json (its «writer» set): the list before the
    server ever answered."""
    try:
        m = json.loads((config.ROOT / "install" / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    files = [f for k in sets for f in m["sets"].get(k, {}).get("files", []) if f.get("kind") == "llm"]
    projs = [f for f in files if "mmproj" in f["path"].lower()]
    return [{"rel": f"llm/{f['path']}", "name": Path(f["path"]).stem, "bytes": f["bytes"],
             "mmproj": f"llm/{projs[0]['path']}" if projs else None} for f in files if f not in projs]


def cloud_models() -> list[LlmModel]:
    """The server's GGUFs; a stopped server (RunPod's proxy says 404) gives the list it gave last time, kept in
    data/cloud.json - a list is not worth starting a paid server for, the writer's job starts it (remote.WAKE)."""
    from ..cloud import state
    try:
        ms = remote.http_json("GET", "/llm/models", timeout=15)["models"]
        d = state.load()
        if d.get("pod") and d["pod"].get("llm_models") != ms:
            d["pod"]["llm_models"] = ms
            state.save(d)
    except (EngineError, KeyError, ValueError) as e:
        d = state.load()
        pod = d.get("pod") or {} if d["mode"] == "cloud" else {}
        ms = pod.get("llm_models") or _manifest_llms(pod.get("sets") or [])
        if not ms:
            raise LLMError(i18n.L(f"Облачный сервер не дал список моделей сценариста: {e}", f"The cloud server did not list the writer's models: {e}")) from e
    return [LlmModel(id=f"cloud/{m['rel']}", name=m["name"], path=Path(m["rel"]), size_gb=round(m["bytes"] / 2**30, 1),
                     mmproj=Path(m["mmproj"]) if m.get("mmproj") else None, source=i18n.L("Облако", "Cloud"), bytes=m["bytes"])
            for m in ms]


def models() -> list[LlmModel]:
    if cloud():
        return cloud_models()
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
        # a project written on this machine names its local model: in the cloud the same file, else the default
        same = next((m for m in ms if cloud() and m.path.name == Path(model_id).name), None)
        if same or cloud():
            return same or next((m for m in ms if config.LLM_MODEL.lower() in m.name.lower()), None) or ms[0]
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


class RemoteLlama:
    """The writer's llama-server on the cloud server: the same start / stop / model as LlamaServer."""

    def __init__(self) -> None:
        self.model: Optional[LlmModel] = None

    @property
    def pid(self) -> Optional[int]:
        return None   # no process here: the header's meters show none

    async def start(self, m: LlmModel) -> None:
        if self.model and self.model.path == m.path:
            return
        if remote.WAKE is not None:
            await remote.WAKE(lambda s: None)
        try:
            await asyncio.to_thread(remote.http_json, "POST", "/llm/start", {"model": m.path.as_posix(), "ctx": config.LLM_CTX}, 300)
        except EngineError as e:
            raise LLMError(i18n.L(f"Сценарист в облаке не запустился: {e}", f"The writer did not start in the cloud: {e}")) from e
        self.model = m

    async def stop(self) -> None:
        if self.model is None:
            return
        self.model = None
        try:
            await asyncio.to_thread(remote.http_json, "POST", "/llm/stop", {}, 60)
        except EngineError:
            pass


class Writer:
    """SERVER: this machine's llama-server or the cloud one, by the mode at each use (like engine.comfy.Engine)."""

    def __init__(self) -> None:
        self.local, self.remote = LlamaServer(), RemoteLlama()

    def current(self):
        return self.remote if cloud() else self.local

    @property
    def pid(self) -> Optional[int]:
        return self.current().pid

    @property
    def model(self) -> Optional[LlmModel]:
        return self.current().model

    async def start(self, m: LlmModel) -> None:
        await self.current().start(m)

    async def stop(self) -> None:
        await self.current().stop()


SERVER = Writer()


# ---------- asking ----------

def _post_cloud(path: str, body: dict, timeout: float = 600) -> dict:
    t0 = time.time()
    try:
        cid = remote.http_json("POST", "/llm/call", {"path": path, "body": body})["id"]
        while time.time() - t0 < timeout:
            r = remote.http_json("GET", f"/llm/call/{cid}", timeout=90)   # the server holds each ask up to 50 s
            if r.get("done"):
                if r.get("status") != 200:
                    raise LLMError(f"llama-server {r.get('status')}: {str(r.get('body'))[:500]}")
                return json.loads(r["body"])
    except EngineError as e:
        raise LLMError(str(e)) from e
    raise LLMError(i18n.L("Сценарист в облаке не ответил", "The writer in the cloud did not answer"))


def _post(path: str, body: dict, timeout: float = 600) -> dict:
    if cloud():
        return _post_cloud(path, body, timeout)
    req = urllib.request.Request(URL + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise LLMError(f"llama-server {e.code}: {e.read().decode('utf-8', 'replace')[:500]}") from e


# ---------- the writer's thinking, live ----------
# A job's writer calls stream (`stream: true`): the model's reasoning (llama-server's `reasoning_content`, or a
# <think> block left in the content) goes into job.progress["thinking"] a couple of times a second, the answer is
# put together and parsed exactly as the plain call's. The request itself (and so the cache key) is the same.

THINK: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("llm_think", default=None)   # the job's progress
THINK_TAIL = 4000      # characters of thinking a job keeps (and a cache entry beside its answer)
THINK_EVERY = 0.5      # seconds between two updates of the progress


def think_into(progress: Optional[dict]) -> None:
    """The running job's progress dict: its writer calls stream their thinking into progress["thinking"]."""
    THINK.set(progress)


class _Split:
    """Reasoning vs answer in a streamed reply: `reasoning_content` / `reasoning` deltas are thinking; a content that
    opens with <think> is thinking up to </think> (a server that does not parse it out)."""
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.answer: list[str] = []
        self.thought: list[str] = []
        self._buf = ""
        self._state = "start"   # start | think | answer

    def content(self, piece: str) -> tuple[str, str]:
        """-> (thinking, answer) of this piece of content."""
        if self._state == "answer":
            self.answer.append(piece)
            return "", piece
        self._buf += piece
        if self._state == "start":
            head = self._buf.lstrip()
            if self.OPEN.startswith(head) and len(head) < len(self.OPEN):
                return "", ""   # maybe the start of <think>: wait for more
            if not head.startswith(self.OPEN):
                self._state, rest, self._buf = "answer", self._buf, ""
                self.answer.append(rest)
                return "", rest
            self._state, self._buf = "think", head[len(self.OPEN):]
        # inside <think>: everything up to </think> is thinking (a tail that may be a cut </think> waits)
        if (k := self._buf.find(self.CLOSE)) >= 0:
            th, rest = self._buf[:k], self._buf[k + len(self.CLOSE):].lstrip()
            self._state, self._buf = "answer", ""
            self.thought.append(th)
            if rest:
                self.answer.append(rest)
            return th, rest
        keep = next((n for n in range(len(self.CLOSE) - 1, 0, -1) if self._buf.endswith(self.CLOSE[:n])), 0)
        th, self._buf = (self._buf[:-keep], self._buf[-keep:]) if keep else (self._buf, "")
        self.thought.append(th)
        return th, ""

    def finish(self) -> str:
        if self._buf:   # a reply that ended inside <think> or on its first characters
            (self.thought if self._state == "think" else self.answer).append(self._buf)
            self._buf = ""
        return "".join(self.answer)


def _post_stream(path: str, body: dict, on_piece, timeout: float = 600) -> dict:
    """_post with `stream: true`: on_piece(thinking, answer) for each delta; -> the reply in the plain call's shape."""
    req = urllib.request.Request(URL + path, json.dumps({**body, "stream": True}).encode(),
                                 {"Content-Type": "application/json", "Accept": "text/event-stream"})
    sp, reasoning, finish = _Split(), [], None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                ev = json.loads(data)
                if ev.get("error"):
                    raise LLMError(f"llama-server: {str(ev['error'])[:500]}")
                ch = (ev.get("choices") or [{}])[0]
                delta = ch.get("delta") or {}
                th = delta.get("reasoning_content") or delta.get("reasoning") or ""
                if th:
                    reasoning.append(th)
                ans = ""
                if delta.get("content"):
                    th2, ans = sp.content(delta["content"])
                    th += th2
                if th or ans:
                    on_piece(th, ans)
                finish = ch.get("finish_reason") or finish
    except urllib.error.HTTPError as e:
        raise LLMError(f"llama-server {e.code}: {e.read().decode('utf-8', 'replace')[:500]}") from e
    text = sp.finish()
    return {"choices": [{"message": {"content": text, "reasoning_content": "".join(reasoning) + "".join(sp.thought)},
                         "finish_reason": finish}]}


class Thoughts:
    """One job's thinking in its progress["thinking"]: {step, text (the last THINK_TAIL characters, the calls one
    after another), live, secs (the thinking time of all its calls), calls, cached, node (the graph's node at work),
    parts}. `parts`: the steps one after another, [{step, at, secs, calls, cached, live, node}] - `at` is where the
    step's thinking starts in `text` (0 once its start scrolled out of the tail); calls of the same step in a row are
    one part. The text alone could not say which step wrote it: a call that had not thought yet showed the previous
    step's thinking under its own name («Сценарий» over the look pick).
    Written on the event loop's thread only: the streaming thread hands its pieces over with call_soon_threadsafe."""

    def __init__(self, progress: dict, step: str, loop: asyncio.AbstractEventLoop) -> None:
        self.p, self.step, self.loop = progress, step, loop
        prev = progress.get("thinking") or {}
        self.text = prev.get("text", "")
        self.secs0 = float(prev.get("secs", 0.0))
        self.calls = int(prev.get("calls", 0))
        self.cached = int(prev.get("cached", 0))
        self.parts: list[dict] = [dict(x) for x in (prev.get("parts") or []) if isinstance(x, dict)]
        self.t0 = time.time()
        self.thinking_until: Optional[float] = None   # the first answer token: the thinking time stops there
        self.seg = ""                                  # this call's thinking
        self._last = 0.0
        self._lock = threading.Lock()

    def _node(self) -> Optional[str]:
        rows = self.p.get("nodes")
        if isinstance(rows, dict):
            return next((k for k, r in rows.items() if isinstance(r, dict) and r.get("status") == "running"), None)
        return None

    def _snap(self, live: bool, call_secs: Optional[float] = None, cached: bool = False) -> dict:
        end = self.thinking_until or time.time()
        took = (end - self.t0 if self.seg else 0.0) if call_secs is None else call_secs
        sep = "\n\n" if self.text and self.seg else ""
        full = self.text + sep + self.seg
        drop = max(0, len(full) - THINK_TAIL)
        node = self._node()
        # this call: the last part goes on when it is the same step (and node), else a new part starts here
        parts = [dict(x) for x in self.parts]
        last = parts[-1] if parts else None
        if last and last.get("step") == self.step and last.get("node") == node:
            last.update(secs=round(float(last.get("secs", 0)) + took, 1), calls=int(last.get("calls", 0)) + (0 if cached else 1),
                        cached=int(last.get("cached", 0)) + (1 if cached else 0), live=live)
            if self.seg and int(last.get("at", 0)) >= len(self.text):   # its earlier calls thought nothing: it starts here
                last["at"] = len(self.text) + len(sep)
        else:
            parts.append({"step": self.step, "at": len(self.text) + len(sep), "secs": round(took, 1),
                          "calls": 0 if cached else 1, "cached": 1 if cached else 0, "live": live, "node": node})
        for x in parts:
            x["at"] = max(0, int(x.get("at", 0)) - drop)
            if x is not parts[-1]:
                x["live"] = False   # the steps before are done
        return {"step": self.step, "text": full[-THINK_TAIL:], "live": live, "secs": round(self.secs0 + took, 1),
                "calls": self.calls, "cached": self.cached, "node": node, "parts": parts[-40:]}

    def _put(self, snap: dict) -> None:
        self.p["thinking"] = snap

    def begin(self) -> None:
        self.t0, self.thinking_until, self.seg = time.time(), None, ""
        self._put(self._snap(True, call_secs=0.0))

    def piece(self, thought: str, answer: str) -> None:
        """From the streaming thread."""
        with self._lock:
            if thought:
                self.seg += thought
            if answer and self.thinking_until is None:
                self.thinking_until = time.time()
            now = time.time()
            if now - self._last < THINK_EVERY:
                return
            self._last = now
            snap = self._snap(True)
        self.loop.call_soon_threadsafe(self._put, snap)

    def end(self, cached_text: Optional[str] = None) -> None:
        """The call is over (or answered from the cache, with the thinking saved beside it if any)."""
        with self._lock:
            if cached_text is not None:
                self.cached += 1
                self.seg, self.thinking_until = cached_text, self.t0
                snap = self._snap(False, call_secs=0.0, cached=True)   # no time was spent thinking now
            else:
                self.calls += 1
                snap = self._snap(False)
            self.text, self.seg = snap["text"], ""
            self.secs0 = snap["secs"]
            self.parts = snap["parts"]
        self._put(snap)


def _think_file(cache: Path) -> Path:
    return cache.with_name(cache.stem + ".think.txt")


class Client:
    def __init__(self, m: LlmModel) -> None:
        self.model = m
        self.calls = self.cached = self.retries = 0
        self.seconds = 0.0

    async def chat_json(self, system: str, user: str, schema: dict, *, images: tuple[Path, ...] = (),
                        temperature: float = 0.7, seed: int = 1, max_tokens: int = 4096, use_cache: bool = True,
                        step: str = "script") -> dict:
        """`step`: what this call is to the user while its thinking shows (script, look, places, lines, photo,
        translate, cast) - not a part of the request."""
        system = system.replace("Russian", LANG.get())
        if LANG.get() != "Russian":   # the fields' names keep their old «_ru», and a model follows the name over the rules
            system += (f"\n\nLanguage: every field named ru, title_ru, outfit_ru or ending in _ru is written in {LANG.get()}, "
                       f"never in Russian - the names are historical.")
        if images and not self.model.mmproj:
            raise LLMError(i18n.L(f"Модель {self.model.name} не видит картинок: рядом с ней нет mmproj-файла",
                                  f"The model {self.model.name} does not see pictures: there is no mmproj file next to it"))
        imgs = [(MIME.get(Path(p).suffix.lower(), "image/jpeg"), base64.b64encode(Path(p).read_bytes()).decode()) for p in images]
        key = hashlib.sha1(json.dumps(
            [self.model.name, self.model.bytes or self.model.path.stat().st_size, system, user, schema,
             [hashlib.sha1(b.encode()).hexdigest() for _, b in imgs], temperature, seed, max_tokens],
            ensure_ascii=False).encode()).hexdigest()
        cache = config.LLM_CACHE / f"{key}.json"
        progress = THINK.get()
        thoughts = Thoughts(progress, step, asyncio.get_running_loop()) if progress is not None else None
        if use_cache and cache.exists():
            self.cached += 1
            if thoughts:   # no live thinking for a cached answer: the one saved with it, if any
                try:
                    saved = _think_file(cache).read_text(encoding="utf-8")
                except OSError:
                    saved = ""
                thoughts.end(saved)
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
        thought = ""
        for attempt in (1, 2):
            t0 = time.time()
            if thoughts and not cloud():   # streamed: the same request, its thinking shown as it comes
                thoughts.begin()
                try:
                    d = await asyncio.to_thread(_post_stream, "/v1/chat/completions", body, thoughts.piece)
                finally:
                    thoughts.end()
                thought = d["choices"][0]["message"].get("reasoning_content") or ""
            else:
                d = await asyncio.to_thread(_post, "/v1/chat/completions", body)
            self.calls += 1
            self.seconds += time.time() - t0
            choice = d["choices"][0]
            text = choice["message"].get("content") or ""
            thought = choice["message"].get("reasoning_content") or thought
            try:
                data = json.loads(text)
                break
            except json.JSONDecodeError as e:
                cut = choice.get("finish_reason") == "length"
                if cut and not text.strip() and thought.strip():   # a thinking model spent the whole limit on its reasoning
                    why = i18n.L("потратила весь лимит ответа на размышления", "spent the whole answer limit on its reasoning")
                    start = i18n.L(f"Начало размышлений: {thought.strip()[:300]}", f"The reasoning's start: {thought.strip()[:300]}")
                else:
                    why = (i18n.L("упёрлась в лимит ответа", "hit the answer limit") if cut
                           else i18n.L(f"ответила не JSON ({e})", f"answered not in JSON ({e})"))
                    start = i18n.L(f"Начало ответа: {text[:300]}", f"The answer's start: {text[:300]}")
                if attempt == 2:
                    raise LLMError(i18n.L(f"{self.model.name} дважды оборвала ответ: {why}. Попробуйте ещё раз или другую модель. {start}",
                                          f"{self.model.name} cut its answer short twice: {why}. Try again or another model. {start}")) from e
                self.retries += 1
                body = {**body, "seed": seed + 7919}
        cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if thoughts and thought.strip():   # a job's thinking, beside the answer, not in it: the cached answer stays what it was
            try:
                _think_file(cache).write_text(thought.strip()[-THINK_TAIL:], encoding="utf-8")
            except OSError:
                pass
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
