"""Windows Job Object with KILL_ON_JOB_CLOSE: when H3 Studio dies (even killed from Task Manager), Windows closes the
job handle and the child (ComfyUI, llama-server) with all its children goes too - no orphan left holding 30 GB."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Optional


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]


class _BasicLimit(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class _ExtLimit(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", _IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def kill_with_us(pid: int) -> Optional[int]:
    """A job handle that kills the process tree when this process exits. The handle must stay open (kept on the object)."""
    if sys.platform != "win32":
        return None
    k32 = ctypes.windll.kernel32
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    job = k32.CreateJobObjectW(None, None)
    info = _ExtLimit()
    info.BasicLimitInformation.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))  # ExtendedLimitInformation
    proc = k32.OpenProcess(0x0100 | 0x0001, False, pid)   # PROCESS_SET_QUOTA | PROCESS_TERMINATE
    ok = proc and k32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(proc))
    if proc:
        k32.CloseHandle(wintypes.HANDLE(proc))
    return job if ok else None


def close(job: Optional[int]) -> None:
    """Closing the handle kills what is left of the tree."""
    if job and sys.platform == "win32":
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(job))
