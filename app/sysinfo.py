"""Memory of this computer for the header: system RAM, the video memory of the card, and what the engine process holds."""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from typing import Optional

GB = 1024 ** 3


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _ProcMem(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]


def ram() -> Optional[dict]:
    if sys.platform != "win32":
        return None
    st = _MemStatus()
    st.dwLength = ctypes.sizeof(st)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return None
    return {"used": round((st.ullTotalPhys - st.ullAvailPhys) / GB, 1), "total": round(st.ullTotalPhys / GB, 1)}


_vram_cache: tuple[float, Optional[dict]] = (0.0, None)


def vram() -> Optional[dict]:
    """The first card, from nvidia-smi (cached for a second: it is a process start): GB used / total, the name, the
    load in percent and the temperature (None where the driver can't tell)."""
    global _vram_cache
    now = time.monotonic()
    if now - _vram_cache[0] < 1.0:
        return _vram_cache[1]
    out = None
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,name,utilization.gpu,temperature.gpu",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and r.stdout.strip():
            used, total, name, load, temp = ([x.strip() for x in r.stdout.splitlines()[0].split(",")] + ["", ""])[:5]
            num = lambda v: int(float(v)) if v.replace(".", "", 1).isdigit() else None   # "[N/A]" -> None
            out = {"used": round(float(used) / 1024, 1), "total": round(float(total) / 1024, 1), "name": name,
                   "load": num(load), "temp": num(temp)}
    except (OSError, ValueError, subprocess.SubprocessError):
        out = None
    _vram_cache = (now, out)
    return out


_vproc_cache: tuple[float, dict] = (0.0, {})


def gpu_processes() -> dict[int, int]:
    """The dedicated video memory of every process, bytes by pid: the Windows counter "GPU Process Memory" (what Task
    Manager shows; nvidia-smi can't tell it under WDDM). Reading it takes ~1.5 s, so it is cached for 4 s (as in
    Remiqora). {} where the counter isn't there."""
    global _vproc_cache
    now = time.monotonic()
    if now - _vproc_cache[0] < 4.0:
        return _vproc_cache[1]
    out: dict[int, int] = {}
    if sys.platform == "win32":
        try:
            r = subprocess.run(["typeperf", r"\GPU Process Memory(*)\Dedicated Usage", "-sc", "1"], capture_output=True,
                               timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            lines = [x for x in r.stdout.decode("latin-1", errors="ignore").splitlines() if x.startswith('"')]
            if len(lines) >= 2:
                names = [c.strip().strip('"') for c in lines[0].split('","')]
                values = [c.strip().strip('"') for c in lines[1].split('","')]
                for name, value in zip(names[1:], values[1:]):   # one counter per adapter: added up
                    at = name.find("(pid_")
                    try:
                        pid = int(name[at + 5:].split("_", 1)[0]) if at >= 0 else None
                        if pid is not None:
                            out[pid] = out.get(pid, 0) + int(float(value))
                    except ValueError:
                        continue
        except (OSError, subprocess.SubprocessError):
            out = {}
    _vproc_cache = (now, out)
    return out


def vram_holders(pids: dict[str, Optional[int]], used_gb: Optional[float]) -> list[dict]:
    """Who holds the card's memory: [{key, gb}] for our processes (engine, llm, backend) and `other` for the rest
    (the browser, Windows, other programs). Empty without the counters. `other` is the card's used memory (nvidia-smi)
    minus ours, not the sum of the other counters: dwm's counter claims the whole card (15.6 GB of 16 seen 2026-10-22)."""
    per = gpu_processes()
    if not per:
        return []
    out, known = [], 0
    for key, pid in pids.items():
        b = per.get(pid) if pid else None
        if b is not None:
            out.append({"key": key, "gb": round(b / GB, 2)})
            known += b
    rest = used_gb * GB - known if used_gb is not None else sum(per.values()) - known
    out.append({"key": "other", "gb": round(max(0, rest) / GB, 2)})
    return out


def process_ram(pid: Optional[int]) -> Optional[float]:
    """Private memory of one process in GB (the engine: its weights live there)."""
    if sys.platform != "win32" or not pid:
        return None
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = ctypes.c_void_p
    handle = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        pm = _ProcMem()
        pm.cb = ctypes.sizeof(pm)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(handle), ctypes.byref(pm), pm.cb):
            return None
        return round(max(pm.PrivateUsage, pm.WorkingSetSize) / GB, 1)
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))
