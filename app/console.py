"""The server's console window (dev.bat's «Remiqora API», `uvicorn app.main:app` by hand): a splash at the start, the
window's title with what the studio does, and a quiet log - one line per event a person cares about (a job started,
a scene, done with its file, failed with what to do, the cloud server up or down) instead of the page's polls.

Colour only where the console takes it: a Windows console with VT processing on (SetConsoleMode) or any other tty,
NO_COLOR unset. Redirected output gets the same lines plain; no stdout at all (pythonw) gets nothing. A failure's
full traceback goes to data/studio.log, the console shows its first line. REMIQORA_LOG=full keeps every request."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime
from typing import Optional

from . import config, i18n

LOG = config.DATA_DIR / "studio.log"
TITLE = "Remiqora Video"
GRAD = ((0x93, 0x33, 0xea), (0xdb, 0x27, 0x77))   # studio.css --grad: violet -> pink

# «REMIQORA» in ANSI Shadow, one letter per column of rows
_LETTERS = {
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "M": ["███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║", "██║ ╚═╝ ██║", "╚═╝     ╚═╝"],
    "I": ["██╗", "██║", "██║", "██║", "██║", "╚═╝"],
    "Q": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║▄▄ ██║", "╚██████╔╝", " ╚══▀▀═╝ "],
    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
}
LOGO = ["".join(_LETTERS[c][r] for c in "REMIQORA") for r in range(6)]

_state = {"color": False, "title": None, "links": False}
RESET, DIM, BOLD = "\x1b[0m", "\x1b[2m", "\x1b[1m"
COLORS = {"violet": (168, 85, 247), "pink": (236, 72, 153), "green": (74, 222, 128), "red": (248, 113, 113),
          "amber": (251, 191, 36), "cyan": (103, 232, 249), "grey": (148, 163, 184)}


# ----- the terminal -----
def _vt_on() -> bool:
    """VT sequences on stdout: a Windows console needs ENABLE_VIRTUAL_TERMINAL_PROCESSING switched on."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetStdHandle.restype = wintypes.HANDLE   # a 64-bit handle: the default int return cuts it
        k32.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k32.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        h = k32.GetStdHandle(-11)   # STD_OUTPUT_HANDLE
        mode = wintypes.DWORD()
        if not k32.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(mode.value & 0x4) or bool(k32.SetConsoleMode(h, mode.value | 0x4 | 0x1))   # VT | processed output
    except (OSError, AttributeError, ValueError):
        return False


def setup() -> None:
    out = sys.stdout
    tty = bool(out) and hasattr(out, "isatty") and out.isatty()
    _state["color"] = tty and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb" and _vt_on()
    # OSC 8 links: Windows Terminal, VS Code and most terminals elsewhere; the old conhost would print them raw
    _state["links"] = _state["color"] and (os.name != "nt" or bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM")))


def _write(s: str, end: str = "\n") -> None:
    out = sys.stdout
    if out is None:
        return
    try:
        out.write(s + end)
        out.flush()
    except UnicodeEncodeError:   # redirected into a code page that has no box drawing: what it can show
        enc = getattr(out, "encoding", None) or "ascii"
        try:
            out.write(s.encode(enc, "replace").decode(enc) + end)
            out.flush()
        except (OSError, ValueError):
            pass
    except (OSError, ValueError):
        pass


def rgb(c: tuple[int, int, int], s: str, bold: bool = False) -> str:
    if not _state["color"]:
        return s
    return f"\x1b[{'1;' if bold else ''}38;2;{c[0]};{c[1]};{c[2]}m{s}{RESET}"


def paint(name: str, s: str, bold: bool = False) -> str:
    return rgb(COLORS[name], s, bold)


def dim(s: str) -> str:
    return f"{DIM}{s}{RESET}" if _state["color"] else s


def link(url: str, text: Optional[str] = None) -> str:
    text = text or url
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\" if _state["links"] else text


def title(state: Optional[str] = None) -> None:
    """The window's title: «Remiqora Video», with what runs after a dot. Written only when it changes."""
    t = f"{TITLE} · {state}" if state else TITLE
    if not _state["color"] or t == _state["title"]:
        return
    _state["title"] = t
    _write(f"\x1b]0;{t}\x07", end="")


# ----- the splash -----
def _gradient_line(row: str) -> str:
    n = max(len(row) - 1, 1)
    out, last = [], None
    for x, ch in enumerate(row):
        if ch == " ":
            out.append(ch)
            continue
        t = x / n
        c = tuple(round(a + (b - a) * t) for a, b in zip(*GRAD))
        if ch not in "█▄▀":   # the shadow's lines: the same hue, darker
            c = tuple(round(v * 0.55) for v in c)
        code = f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m"
        out.append(ch if code == last else code + ch)
        last = code
    return "".join(out) + RESET


def _where() -> str:
    from .cloud import state as cloud_state
    d = cloud_state.load()
    if d["mode"] == "cloud":
        pod = d.get("pod") or {}
        prov = {"runpod": "RunPod", "vast": "Vast.ai"}.get(d.get("provider"), d.get("provider") or "")
        card = pod.get("gpu_name") or i18n.L("сервер не развёрнут", "no server deployed")
        return i18n.L(f"облако {prov} · {card}", f"cloud {prov} · {card}")
    if d["mode"] == "server":
        return i18n.L("свой сервер · ", "own server · ") + (d["server"].get("url") or "?")
    from . import sysinfo
    card = sysinfo.vram()
    gpu = f"{card['name']} · {card['total']:g} GB" if card else i18n.L("видеокарта не найдена", "no GPU found")
    return i18n.L("этот компьютер · ", "this computer · ") + gpu


def _writer() -> str:
    try:
        from .llm import client as llm
        return llm.find(None).name
    except Exception:  # noqa: BLE001 - the splash says so instead
        return i18n.L("нет (положите GGUF в папку LLM)", "none (put a GGUF into the LLM folder)")


def _reloaded(port: int) -> bool:
    """`uvicorn --reload` starts the app again in a new process on every code change: the splash once per reloader,
    a short line after."""
    if "--reload" not in sys.argv:
        return False
    mark = os.path.join(tempfile.gettempdir(), f"remiqora-video-{os.getppid()}-{port}.splash")
    if os.path.exists(mark):
        return True
    try:
        open(mark, "w").close()
    except OSError:
        pass
    return False


def _addr() -> tuple[str, int]:
    """Where uvicorn listens: its --host / --port (the reloader's child gets the same argv), else config.PORT."""
    host, port, a = "127.0.0.1", config.PORT, sys.argv
    for i, x in enumerate(a[:-1]):
        if x == "--host":
            host = a[i + 1]
        elif x == "--port" and a[i + 1].isdigit():
            port = int(a[i + 1])
    return ("127.0.0.1" if host in ("0.0.0.0", "::") else host), port


def splash(version: str, git: str = "") -> None:
    host, port = _addr()
    url = f"http://{host}:{port}"
    if _reloaded(port):
        event("↻", "grey", i18n.L("код изменён — сервер перезапущен", "code changed - the server restarted"))
        return
    from . import projects
    count = sum(1 for _ in projects.ROOT.glob("*/project.json"))
    rows = [
        (i18n.L("Студия", "Studio"), link(url) if _state["links"] else url),
        (i18n.L("Модели", "Models"), _where()),
        (i18n.L("Сценарист", "Writer"), _writer()),
        (i18n.L("Проекты", "Projects"), f"{count} · {projects.ROOT}"),
    ]
    tag = "V I D E O" + (f"  ·  {version}" if version else "") + (f"  ·  {git}" if git else "")
    if _state["color"]:
        _write("")
        for row in LOGO:
            _write("  " + _gradient_line(row))
        _write("  " + rgb(GRAD[1], tag, bold=True))
        _write("")
        w = max(len(k) for k, _ in rows)
        for k, v in rows:
            _write(f"  {paint('violet', '▍')} {dim(k.ljust(w))}  {paint('cyan', v) if k == rows[0][0] else v}")
        _write("")
        _write("  " + dim(i18n.L("Ctrl+C — остановить студию · события ниже", "Ctrl+C stops the studio · events below")))
        _write("  " + dim("─" * len(LOGO[0])))
    else:
        _write("")
        _write("  REMIQORA VIDEO" + (f"  ·  {version}" if version else "") + (f"  ·  {git}" if git else ""))
        _write("  " + "-" * 40)
        w = max(len(k) for k, _ in rows)
        for k, v in rows:
            _write(f"  {k.ljust(w)}  {v}")
        _write("")
    title()


def bye() -> None:
    if "--reload" not in sys.argv:
        event("■", "grey", i18n.L("студия остановлена", "the studio stopped"))


# ----- events -----
def event(mark: str, color: str, text: str, hint: str = "") -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"  {dim(stamp)}  {paint(color, mark, bold=True)} {paint(color, text) if color in ('red', 'amber') else text}"
    if hint:
        line += "  " + dim("→ " + hint)
    _write(line)


def trace(what: str) -> None:
    """The current exception's traceback into data/studio.log (inside an except)."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now().isoformat(timespec='seconds')} {what}\n{traceback.format_exc()}\n")
    except OSError:
        pass


def _hint(err: str) -> str:
    e = err.lower()
    if "out of memory" in e or "outofmemory" in e:
        return i18n.L("освободите видеопамять («Освободить») или снимите в меньшем качестве",
                      "free the video memory («Free») or shoot at a lower quality")
    if "lora" in e:
        return i18n.L("проверьте LoRA сцены во вкладке «Съёмка»", "check the scene's LoRA in «Shooting»")
    if "облак" in e or "cloud" in e:
        return i18n.L("«Модели» → «Облако»", "Models → Cloud")
    if "нет модели" in e or "missing files" in e or "no ref2va" in e or "gguf" in e or "llm" in e:
        return i18n.L("«Модели и настройки»", "«Models and settings»")
    return i18n.L("подробности в data\\studio.log и data\\h3worker.log", "details in data\\studio.log and data\\h3worker.log")


# what a job is, in the log and in the title: kind -> (the line's words, the title's verb)
def _kinds() -> dict[str, tuple[str, str]]:
    L = i18n.L
    return {
        "scene": (L("сцена в «Лаборатории»", "a «Lab» scene"), L("снимает", "shooting")),
        "render": (L("съёмка ролика", "shooting the video"), L("снимает", "shooting")),
        "take": (L("ещё дубль", "another take"), L("снимает дубль", "shooting a take")),
        "graph": (L("граф", "the graph"), L("снимает граф", "running the graph")),
        "write": (L("сценарий", "the script"), L("пишет сценарист", "the writer writes")),
        "rewrite": (L("правка сценария", "rewriting the script"), L("пишет сценарист", "the writer writes")),
        "graph-llm": (L("тексты узлов графа", "the graph nodes' texts"), L("пишет сценарист", "the writer writes")),
        "describe": (L("описание кадра", "describing a frame"), L("смотрит кадр", "describing")),
        "translate": (L("перевод", "translating"), L("переводит", "translating")),
        "lyrics": (L("слова песни", "the song's lyrics"), L("слушает песню", "listening")),
        "voice": (L("голос героя", "the hero's voice"), L("берёт голос", "taking a voice")),
        "draw": (L("портрет героя", "the hero's portrait"), L("рисует", "drawing")),
        "cast_tries": (L("пробы героя", "the hero's tries"), L("рисует пробы", "drawing tries")),
        "actor_sheet": (L("лист актёра", "the actor's sheet"), L("рисует лист", "drawing the sheet")),
        "actor_tries": (L("пробы актёра", "the actor's tries"), L("рисует пробы", "drawing tries")),
        "frame": (L("стартовые кадры", "start frames"), L("рисует кадры", "drawing frames")),
        "places": (L("места сцен", "the scenes' places"), L("ищет места", "grouping places")),
        "place": (L("кадры мест", "the places' pictures"), L("рисует места", "drawing places")),
    }


_names: dict[str, str] = {}


def _project_name(pid: Optional[str]) -> str:
    if not pid:
        return ""
    if pid not in _names:
        try:
            from . import projects
            _names[pid] = projects.load(pid).get("name") or ""
        except Exception:  # noqa: BLE001 - only a label
            _names[pid] = ""
    return _names[pid]


def _label(job) -> str:
    what = _kinds().get(job.kind, (job.kind, ""))[0]
    p = job.params or {}
    name = _project_name(p.get("project"))
    if job.kind == "take" and p.get("scene") is not None:
        what += i18n.L(f" сцены {int(p['scene']) + 1}", f" of scene {int(p['scene']) + 1}")
    if job.kind == "scene":
        name = (p.get("prompt") or "")[:40] + ("…" if len(p.get("prompt") or "") > 40 else "")
    return f"{what} «{name}»" if name else what


def _secs(job) -> str:
    s = round((job.finished or time.time()) - (job.started or time.time()))
    return f"{s // 60}:{s % 60:02d}" if s >= 60 else i18n.L(f"{s} с", f"{s} s")


def _output(job) -> str:
    """Where a finished job's file is, for the done line."""
    if job.kind == "scene" and job.file:
        return str(config.OUTPUT_DIR / job.file)
    r = job.result if isinstance(job.result, dict) else {}
    if job.kind == "render" and r.get("video"):
        from . import projects
        return str(projects.ROOT / job.params.get("project", "") / r["video"])
    return ""


def _render_rows(job) -> list[dict]:
    return [r for r in (job.progress or {}).get("scenes") or [] if isinstance(r, dict)]


class _Watch:
    """Looks at the queue and the cloud twice a second and tells what changed: no hooks through the jobs' code."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}    # job id -> what was told: status, scenes' status and notes
        self.told: set[str] = set()        # jobs whose end was told
        self.cloud = {"status": None, "step": None, "error": None}

    def tick(self) -> None:
        from . import jobs
        busy = None
        for job in list(jobs.JOBS.values()):
            if job.id in self.told:
                continue
            seen = self.jobs.setdefault(job.id, {"status": None, "rows": {}})
            if job.status == "running":
                if seen["status"] != "running":
                    event("▶", "violet", _label(job))
                self._scenes(job, seen)
                busy = job
            elif job.status in ("done", "error", "cancelled"):
                if seen["status"] in ("running", "queued", None) and job.started:
                    self._end(job)
                self.told.add(job.id)
                self.jobs.pop(job.id, None)
                continue
            seen["status"] = job.status
        self._cloud()
        title(self._title(busy))

    def _scenes(self, job, seen: dict) -> None:
        rows = _render_rows(job)
        n = len(rows)
        for r in rows:
            k = r.get("index")
            was = seen["rows"].get(k, {})
            st, note = r.get("status"), r.get("note")
            if st == "running" and was.get("status") != "running":
                model = f" · {r['model']}" if r.get("model") else ""
                event("·", "grey", i18n.L(f"сцена {k + 1} из {n}", f"scene {k + 1} of {n}") + model)
            if note and note != was.get("note"):
                event("↻", "amber", i18n.L(f"сцена {k + 1}: ", f"scene {k + 1}: ") + note)
            seen["rows"][k] = {"status": st, "note": note}

    def _end(self, job) -> None:
        label = _label(job)
        if job.status == "done":
            out = _output(job)
            r = job.result if isinstance(job.result, dict) else {}
            if job.kind == "render" and r and not r.get("complete", True):
                event("■", "amber", label + i18n.L(f" — остановлена, снято {len(r.get('shots') or [])}",
                                                    f" - stopped, {len(r.get('shots') or [])} shot") + f" · {_secs(job)}")
                return
            event("✓", "green", f"{label} · {_secs(job)}" + (f"  {dim(out)}" if out else ""))
        elif job.status == "cancelled":
            event("■", "grey", label + i18n.L(" — отменено", " - cancelled"))
        else:
            err = (job.error or "").strip().splitlines()
            one = (err[0] if err else i18n.L("неизвестная ошибка", "unknown error"))[:160]
            event("✗", "red", f"{label}: {one}", _hint(job.error or ""))

    def _title(self, job) -> Optional[str]:
        if job is not None:
            verb = _kinds().get(job.kind, ("", job.kind))[1]
            rows = _render_rows(job)
            if rows:
                done = sum(1 for r in rows if r.get("status") in ("done", "cached"))
                live = [r for r in rows if r.get("status") != "skipped"]
                return f"{verb} {min(done + 1, len(live))}/{len(live)}"
            return verb
        from .cloud import manager, state as cloud_state
        d = cloud_state.load()
        if d["mode"] == "cloud" and d.get("pod"):
            card = d["pod"].get("gpu_name") or ""
            st = manager.LIVE.get("status")
            if st == "running":
                return i18n.L("облако ", "cloud ") + card
            if st == "starting":
                return i18n.L("облако запускается", "cloud starting")
        return None

    def _cloud(self) -> None:
        from .cloud import manager, state as cloud_state
        st, dep = manager.LIVE.get("status"), manager.DEPLOY
        was = self.cloud["status"]
        if st != was and was is not None and st is not None:
            card = (cloud_state.load().get("pod") or {}).get("gpu_name") or ""
            if st == "running":
                event("☁", "cyan", i18n.L(f"облачный сервер готов · {card}", f"the cloud server is ready · {card}"))
            elif st == "starting":
                event("☁", "cyan", i18n.L("облачный сервер запускается…", "the cloud server is starting…"))
            elif st == "stopped":
                event("☁", "grey", i18n.L("облачный сервер остановлен", "the cloud server stopped"))
            elif st == "error":
                event("✗", "red", i18n.L("облачный сервер не отвечает", "the cloud server does not answer"),
                      i18n.L("«Модели» → «Облако»", "Models → Cloud"))
        self.cloud["status"] = st
        step = dep.get("step") if dep.get("running") else None
        if step and step != self.cloud["step"]:
            event("☁", "cyan", i18n.L("развёртывание: ", "deploy: ") + step)
        self.cloud["step"] = step
        err = dep.get("error")
        if err and err != self.cloud["error"]:
            event("✗", "red", i18n.L("облако: ", "cloud: ") + str(err).splitlines()[0][:160],
                  i18n.L("«Модели» → «Облако»", "Models → Cloud"))
        self.cloud["error"] = err


async def watch() -> None:
    w = _Watch()
    while True:
        await asyncio.sleep(0.5)
        try:
            w.tick()
        except Exception:  # noqa: BLE001 - the console must never stop the studio
            trace("console")
            await asyncio.sleep(5)


def cloud_auto_stop(minutes: int, stalled: bool = False) -> None:
    """manager.watch() stopping the rented server by itself."""
    if stalled:
        event("☁", "amber", i18n.L("облачный сервер не ответил за 20 мин — остановлен",
                                   "the cloud server did not answer for 20 min - stopped"))
    else:
        event("☁", "grey", i18n.L(f"облачный сервер простаивал {minutes} мин — остановлен",
                                  f"the cloud server was idle for {minutes} min - stopped"))


# ----- uvicorn's own lines -----
_NOISE = ("Started server process", "Waiting for application startup", "Application startup complete",
          "Waiting for application shutdown", "Application shutdown complete", "Finished server process",
          "Uvicorn running on")


class _Quiet(logging.Filter):
    """uvicorn.access: a GET that worked is the page reading (its polls of /api/jobs each second, /api/system each
    3 s, previews…) - not shown; what changes something (POST, PUT, DELETE) and every error are, in our own form."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            _, method, path, _, status = record.args
            status = int(status)
        except (TypeError, ValueError):
            return True
        if method in ("GET", "HEAD", "OPTIONS") and status < 400:
            return False
        mark, color = ("!", "red") if status >= 500 else ("!", "amber") if status >= 400 else ("›", "grey")
        stamp = datetime.now().strftime("%H:%M:%S")
        text = f"{method} {path.split('?')[0]}  {status}"
        _write(f"  {dim(stamp)}  {paint(color, mark)} {dim(text) if status < 400 else paint(color, text)}")
        return False


class _Errors(logging.Filter):
    """uvicorn.error: its start/stop chatter goes (the splash says it), an exception's traceback goes to
    data/studio.log and one red line to the console."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if any(msg.startswith(n) for n in _NOISE):
            return False
        if record.exc_info:
            try:
                LOG.parent.mkdir(parents=True, exist_ok=True)
                with open(LOG, "a", encoding="utf-8") as f:
                    f.write(f"--- {datetime.now().isoformat(timespec='seconds')} {msg}\n"
                            + "".join(traceback.format_exception(*record.exc_info)) + "\n")
            except OSError:
                pass
            e = record.exc_info[1]
            event("✗", "red", i18n.L("ошибка сервера: ", "server error: ") + f"{type(e).__name__}: {str(e).splitlines()[0][:140] if str(e) else ''}",
                  i18n.L("подробности в data\\studio.log", "details in data\\studio.log"))
            return False
        return True


def quiet_log() -> None:
    if os.environ.get("REMIQORA_LOG", "").lower() == "full":
        return
    acc = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _Quiet) for f in acc.filters):
        acc.addFilter(_Quiet())
    err = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, _Errors) for f in err.filters):
        err.addFilter(_Errors())
