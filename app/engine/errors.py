"""The engine's errors, shared by the ComfyUI server client (comfy.py) and our worker (worker.py)."""


class EngineError(Exception):
    pass


class Interrupted(EngineError):
    pass
