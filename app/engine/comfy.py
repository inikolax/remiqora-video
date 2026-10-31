"""The engine every model shoots on (phase 7): COMFY is our worker (worker.py + h3worker.py) - ComfyUI's core as a
library in a process of our own, in H3 Studio's own environment (engine/: the core at a pinned commit, its venv).
No ComfyUI server, port, WebSocket or Comfy Desktop: the server path (H3_ENGINE=comfy) is gone since 2026-10-23.
The name stays: the app imports COMFY, EngineError and output_files from here.
"""
from __future__ import annotations

from .. import config
from .errors import EngineError, Interrupted  # noqa: F401  (imported from here by the rest of the app)
from .worker import Worker

COMFY = Worker()


def output_files(outputs: dict) -> list[str]:
    """Absolute paths of everything the graph saved (SaveVideo / SaveImage), in node order."""
    out = []
    for nid in sorted(outputs, key=lambda k: int(k) if k.isdigit() else 0):
        for v in outputs[nid].values():
            for f in v if isinstance(v, list) else []:
                if isinstance(f, dict) and f.get("filename") and f.get("type", "output") == "output":
                    out.append(str(config.COMFY_OUTPUT / f.get("subfolder", "") / f["filename"]))
    return out
