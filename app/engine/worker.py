"""H3 in our own worker process (phase 7): h3worker.py runs ComfyUI's core as a library - no server, no port, no
WebSocket, no Comfy Desktop config. The same interface as comfy.Comfy (ensure, run, free, interrupt, stop, state), so
jobs.py and render.py don't care which one shoots.

The worker is ComfyUI's python with ComfyUI's folder as its cwd (its code and packages: torch, comfy-kitchen,
comfy-aimdo). It is put into a Windows Job Object (winjob.py): when H3 Studio dies, the worker goes with it.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from .. import config
from . import winjob
from .errors import EngineError, Interrupted
from .. import i18n

_REJECTED = "ComfyUI не принял граф:"   # h3worker.py's words (it runs in ComfyUI's python, without app.i18n)


def _worker_message(m: Optional[str]) -> Optional[str]:
    if m and m.startswith(_REJECTED):
        return i18n.L(m, "ComfyUI rejected the graph:" + m[len(_REJECTED):])
    return m

START_TIMEOUT = 240   # seconds: importing torch and ComfyUI's nodes
SCRIPT = Path(__file__).with_name("h3worker.py")
KINDS = {"diffusion_models": ("diffusion_models", "unet"), "text_encoders": ("text_encoders", "clip"),
         "vae": ("vae",), "loras": ("loras",), "checkpoints": ("checkpoints",),   # phase 10: LTX 2.3 is one checkpoint,
         "latent_upscale_models": ("latent_upscale_models",)}                     # LTX's second stage upscales the latent


def model_folders() -> dict[str, list[str]]:
    """Where the worker looks for each kind of weights: H3_MODEL_ROOTS and H3_REF_DIR by their sub-folders, LORA_DIRS
    and Krea's and LTX's LoRA folders."""
    out: dict[str, list[str]] = {k: [] for k in KINDS}
    for root in [*config.H3_MODEL_ROOTS, config.H3_REF_DIR]:
        for kind, subs in KINDS.items():
            out[kind] += [str(root / s) for s in subs if (root / s).is_dir()]
    out["loras"] += [str(d) for d in [*config.LORA_DIRS, *config.KREA_LORA_DIRS, *config.LTX23_LORA_DIRS, *config.LTX25_LORA_DIRS,
                                      *config.WAN_LORA_DIRS, *config.FLUX2_LORA_DIRS] if d.is_dir()]
    return out


def _log_tail(n: int = 25) -> str:
    try:
        return "\n".join(config.WORKER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


class Worker:
    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self._job = None
        self._lock = asyncio.Lock()     # start / stop
        self._talk = asyncio.Lock()     # one request at a time on the pipe
        self._events: Optional[asyncio.Queue] = None
        self.started_at: Optional[float] = None
        self.work_pid: Optional[int] = None   # the worker's own process (proc may be a venv's launcher)
        self.warm = False   # the H3 weights are in memory (a shot since the last start / free)
        self.model = "h3"   # phase 10: whose weights `warm` means (a videomodels card id)
        self.folders: Optional[dict] = None   # the weights folders it was started with

    # ----- state -----
    @property
    def pid(self) -> Optional[int]:
        return self.proc.pid if self.proc and self.proc.poll() is None else None

    @property
    def stats_pid(self) -> Optional[int]:
        """The process that holds the memory, for the header's meters."""
        return (self.work_pid or self.pid) if self.pid else None

    def problems(self) -> list[str]:
        out = []
        if not (config.COMFY_DIR / "ComfyUI" / "comfy").is_dir():
            out.append(i18n.L(f"Не найдено ядро ComfyUI: {config.COMFY_DIR}\\ComfyUI\\comfy («Модели и настройки» или COMFY_DIR в .env)", f"ComfyUI core not found: {config.COMFY_DIR}\\ComfyUI\\comfy («Models and settings» or COMFY_DIR in .env)"))
        if not config.COMFY_PYTHON.exists():
            out.append(i18n.L(f"Не найден python для H3: {config.COMFY_PYTHON} («Модели и настройки» или COMFY_PYTHON в .env)", f"Python for H3 not found: {config.COMFY_PYTHON} («Models and settings» or COMFY_PYTHON in .env)"))
        if not any(r.is_dir() for r in config.H3_MODEL_ROOTS):
            out.append(i18n.L("Нет папки с весами H3: ", "No H3 weights folder: ") + "; ".join(map(str, config.H3_MODEL_ROOTS)) + i18n.L(" (H3_MODEL_ROOTS в .env)", " (H3_MODEL_ROOTS in .env)"))
        return out

    def state(self) -> str:
        """off | starting | ready"""
        if self.proc and self.proc.poll() is None:
            return "ready" if self.started_at else "starting"
        return "off"

    # ----- the pipe -----
    def _reader(self, loop: asyncio.AbstractEventLoop, q: asyncio.Queue, stdout) -> None:
        for line in stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            loop.call_soon_threadsafe(q.put_nowait, msg)
        loop.call_soon_threadsafe(q.put_nowait, {"event": "exit"})

    def _send(self, msg: dict) -> None:
        if not self.pid:
            raise EngineError(i18n.L("Воркер H3 не запущен", "The H3 worker is not running"))
        try:
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except OSError as e:
            raise EngineError(i18n.L("Воркер H3 упал. Конец журнала data\\h3worker.log:\n", "The H3 worker crashed. The end of data\\h3worker.log:\n") + _log_tail()) from e

    async def _next(self, timeout: Optional[float] = None) -> dict:
        try:
            msg = await asyncio.wait_for(self._events.get(), timeout)
        except asyncio.TimeoutError as e:
            raise EngineError(i18n.L("Воркер H3 не ответил. Конец журнала data\\h3worker.log:\n", "The H3 worker did not answer. The end of data\\h3worker.log:\n") + _log_tail()) from e
        if msg.get("event") == "exit":
            self.started_at, self.warm = None, False
            raise EngineError(i18n.L("Воркер H3 упал. Конец журнала data\\h3worker.log:\n", "The H3 worker crashed. The end of data\\h3worker.log:\n") + _log_tail())
        return msg

    # ----- start / stop -----
    async def ensure(self, on_status: Callable[[str], None] = lambda s: None) -> None:
        async with self._lock:
            if self.pid and self.started_at:
                return
            if self.proc:
                await self.stop()
            if issues := self.problems():
                raise EngineError("; ".join(issues))
            self.folders = model_folders()   # what it is told now; jobs.shoot restarts it when that changes
            settings = {"input": str(config.COMFY_INPUT), "output": str(config.COMFY_OUTPUT), "folders": self.folders}
            sfile = config.DATA_DIR / "h3worker.json"
            sfile.write_text(json.dumps(settings, ensure_ascii=False, indent=1), encoding="utf-8")
            log = open(config.WORKER_LOG, "w", encoding="utf-8", errors="replace")
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            on_status(i18n.L("Запускаю H3…", "Starting H3…"))
            self.started_at, self.warm = None, False
            self.proc = subprocess.Popen([str(config.COMFY_PYTHON), "-s", str(SCRIPT), str(sfile)],
                                         cwd=config.COMFY_DIR / "ComfyUI", stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=log, env=env, text=True, encoding="utf-8", errors="replace",
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            log.close()
            self._job = winjob.kill_with_us(self.proc.pid)
            self._events = asyncio.Queue()
            threading.Thread(target=self._reader, args=(asyncio.get_running_loop(), self._events, self.proc.stdout),
                             daemon=True).start()
            t0 = time.time()
            while True:
                msg = await self._next(max(1.0, START_TIMEOUT - (time.time() - t0)))
                if msg.get("event") == "ready":
                    self.started_at, self.work_pid = time.time(), msg.get("pid")
                    return

    async def stop(self) -> None:
        p, self.proc, self.started_at, self.warm = self.proc, None, None, False
        if p and p.poll() is None:
            try:
                p.stdin.close()   # the worker leaves its loop on EOF
                await asyncio.to_thread(p.wait, 10)
            except (OSError, subprocess.TimeoutExpired):
                p.kill()
        winjob.close(self._job)
        self._job = None

    async def free(self) -> None:
        """Unload the models but keep the worker (the next shot loads them again from the disk cache)."""
        self.warm = False
        if not (self.pid and self.started_at):
            return
        async with self._talk:
            self._send({"cmd": "free"})
            while (await self._next(120)).get("event") != "freed":
                pass

    async def interrupt(self) -> None:
        if self.pid:
            try:
                self._send({"cmd": "interrupt"})   # read on the worker's own thread, even mid-graph
            except EngineError:
                pass

    async def _list(self, cmd: dict) -> list[str]:
        await self.ensure()
        async with self._talk:
            self._send(cmd)
            while True:
                msg = await self._next(60)
                if msg.get("event") == "list":
                    return list(msg.get("names") or [])

    async def lora_names(self) -> list[str]:
        return await self._list({"cmd": "loras"})

    async def object_info(self, node: str) -> dict:
        """Only what jobs.py asks: the UNETLoader's list of diffusion models (the shape of ComfyUI's /object_info)."""
        if node != "UNETLoader":
            return {}
        names = await self._list({"cmd": "models", "kind": "diffusion_models"})
        return {"input": {"required": {"unet_name": [names]}}}

    # ----- running a graph -----
    async def run(self, graph: dict, on_node: Callable[[str], None], on_progress: Callable[[int, int, str], None]) -> dict:
        """The API-format graph -> the outputs {node_id: {...}} as ComfyUI's history gives them."""
        await self.ensure()
        rid = uuid.uuid4().hex
        async with self._talk:
            self._send({"cmd": "run", "id": rid, "graph": graph})
            while True:
                msg = await self._next()
                ev = msg.get("event")
                if ev == "executing":
                    on_node(str(msg.get("node")))
                elif ev == "progress":
                    on_progress(int(msg.get("value", 0)), int(msg.get("max", 0)), str(msg.get("node")))
                elif msg.get("id") not in (None, rid):
                    continue
                elif ev == "done":
                    return msg.get("outputs") or {}
                elif ev == "interrupted":
                    raise Interrupted(i18n.L("остановлено", "stopped"))
                elif ev == "error":
                    raise EngineError(_worker_message(msg.get("message")) or i18n.L("ошибка воркера H3", "H3 worker error"))
