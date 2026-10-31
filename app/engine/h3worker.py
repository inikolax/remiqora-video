"""The H3 worker (phase 7): ComfyUI's core as a library in a process of our own - no server, no port, no browser part.

Run by worker.py with ComfyUI's python, cwd = ComfyUI's folder:
    python h3worker.py <settings.json>
settings: {"input": dir, "output": dir, "folders": {"diffusion_models": [dirs], "text_encoders": [...], ...}}

The graph is the same API-format graph as before (graphs.py), run by ComfyUI's own PromptExecutor - so the frames and
the speed are ComfyUI's, and the loaded models stay in memory between scenes (its cache). Our side of the pipe:
  stdin, one JSON per line:  {"cmd": "run", "id", "graph"} | {"cmd": "free"} | {"cmd": "interrupt"} | {"cmd": "loras"}
                             | {"cmd": "models", "kind"}
  protocol fd (stdout), one JSON per line: {"event": "ready"} | {"event": "executing", "node"} | {"event": "progress",
      "value", "max", "node"} | {"event": "done", "id", "outputs"} | {"event": "error", "id", "message"}
      | {"event": "interrupted", "id"} | {"event": "freed"} | {"event": "list", "names"}
Everything else the core prints goes to stderr (our log).
"""
import json
import os
import queue
import sys
import threading
import traceback

# the protocol keeps the real stdout; whatever ComfyUI prints goes to stderr, so it can't break a line of ours
_proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
os.dup2(2, 1)
sys.stdout = sys.stderr
_out_lock = threading.Lock()


def emit(event: str, **data) -> None:
    with _out_lock:
        _proto.write(json.dumps({"event": event, **data}, ensure_ascii=False) + "\n")
        _proto.flush()


settings = json.loads(open(sys.argv[1], encoding="utf-8").read())
comfy_root = os.getcwd()
# ComfyUI's modules first, and not our app/engine folder: its comfy.py and graphs.py would shadow ComfyUI's packages
_here = os.path.dirname(os.path.abspath(__file__))
sys.path = [comfy_root] + [p for p in sys.path if os.path.abspath(p or ".") not in (_here, comfy_root)]

# what ComfyUI's main.py does before torch when it is the program
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")
if os.name == "nt":
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
sys.argv = ["main.py", "--preview-method", "none", "--disable-all-custom-nodes", "--offline", "--disable-assets",
            "--disable-dynamic-vram",   # 2026-10-26: the core's new dynamic VRAM (23.10) died with an access violation
                                        # on the H3 text encoder (Qwen3VL 32B, ~15 GB, partially_load on a 16 GB card);
                                        # the estimate-based loading before it held the same models
            "--input-directory", settings["input"], "--output-directory", settings["output"]]
import comfy.options  # noqa: E402
comfy.options.enable_args_parsing()   # before cuda_malloc: it imports comfy.cli_args, which parses (or not) only once
import cuda_malloc  # noqa: E402,F401  (sets the CUDA allocator before torch, as main.py does)
import main  # noqa: E402  (ComfyUI's setup: args, paths, logging, comfy-aimdo; the server is started only as __main__)

import asyncio  # noqa: E402
import gc  # noqa: E402

import comfy.model_management as mm  # noqa: E402
import comfy.utils  # noqa: E402
import execution  # noqa: E402
import folder_paths  # noqa: E402
import hook_breaker_ac10a0  # noqa: E402
import nodes  # noqa: E402

for kind, dirs in settings.get("folders", {}).items():
    for d in dirs:
        folder_paths.add_model_folder_path(kind, d)

hook_breaker_ac10a0.save_functions()
asyncio.run(nodes.init_extra_nodes(init_custom_nodes=False, init_api_nodes=False))
mm.set_cudnn_benchmark()
hook_breaker_ac10a0.restore_functions()

# our own nodes (h3nodes.py beside this file; our folder is off sys.path, so by path)
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("h3nodes", os.path.join(_here, "h3nodes.py"))
_h3nodes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_h3nodes)
nodes.NODE_CLASS_MAPPINGS.update(_h3nodes.NODE_CLASS_MAPPINGS)


class Server:
    """What PromptExecutor needs of ComfyUI's server (comfy_execution/server_protocol.py): its events go to our pipe."""
    client_id = "h3studio"
    last_node_id = None
    last_prompt_id = None
    sockets_metadata: dict = {}

    def send_sync(self, event, data, sid=None):
        if not isinstance(event, str) or not isinstance(data, dict):
            return   # previews and other binary events
        if event == "executing":
            self.last_node_id = data.get("node")
            if data.get("node") is not None:
                emit("executing", node=str(data["node"]))
        elif event == "execution_error":
            emit("node_error", node_type=data.get("node_type"), message=str(data.get("exception_message", "")).strip())

    def queue_updated(self):
        pass


SERVER = Server()


def _progress(value, total, preview_image, prompt_id=None, node_id=None):
    """ComfyUI's main.hijack_progress, our pipe instead of the WebSocket (and «Остановить» checked at every step)."""
    mm.throw_exception_if_processing_interrupted()
    emit("progress", value=int(value), max=int(total), node=str(node_id or SERVER.last_node_id))


comfy.utils.set_progress_bar_global_hook(_progress)

# the cache as the server sets it up (RAM pressure: the loaders' results - the models - stay between scenes)
_ram = mm.total_ram / 1024.0
EXECUTOR = execution.PromptExecutor(SERVER, cache_type=execution.CacheType.RAM_PRESSURE,
                                    cache_args={"lru": 0, "ram": min(10.0, max(2.0, _ram * 0.10)), "ram_inactive": min(128.0, _ram)})

work: "queue.Queue[dict]" = queue.Queue()


def read_stdin() -> None:
    """«Остановить» must reach us while a graph runs, so commands are read on their own thread."""
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("cmd") == "interrupt":
            mm.interrupt_current_processing(True)
        else:
            work.put(msg)
    work.put({"cmd": "exit"})


def run(msg: dict) -> None:
    pid, graph = msg["id"], msg["graph"]
    valid = asyncio.run(execution.validate_prompt(pid, graph, None))
    if not valid[0]:
        errors = [str((valid[1] or {}).get("message", ""))]
        for nid, ne in (valid[3] or {}).items():
            for e in ne.get("errors", []):
                errors.append(f"{ne.get('class_type', nid)}: {e.get('message')} {e.get('details', '')}".strip())
        emit("error", id=pid, message="ComfyUI не принял граф:\n" + "\n".join(x for x in errors if x))
        return
    mm.interrupt_current_processing(False)
    SERVER.last_prompt_id = pid
    EXECUTOR.execute(graph, pid, {"client_id": SERVER.client_id}, valid[2])
    kinds = [ev for ev, _ in EXECUTOR.status_messages]
    if "execution_interrupted" in kinds:
        emit("interrupted", id=pid)
    elif not EXECUTOR.success:
        data = next((d for ev, d in EXECUTOR.status_messages if ev == "execution_error"), {})
        emit("error", id=pid, message=f"{data.get('node_type')}: {str(data.get('exception_message', '')).strip()}")
    else:
        emit("done", id=pid, outputs=(EXECUTOR.history_result or {}).get("outputs", {}))
    gc.collect()
    mm.soft_empty_cache()


def main_loop() -> None:
    threading.Thread(target=read_stdin, daemon=True).start()
    emit("ready", comfy=comfy_root, pid=os.getpid())   # a venv's python.exe is a launcher: this is the real process
    while True:
        msg = work.get()
        cmd = msg.get("cmd")
        if cmd == "exit":
            return
        try:
            if cmd == "run":
                run(msg)
            elif cmd == "free":
                mm.unload_all_models()
                EXECUTOR.reset()
                gc.collect()
                mm.soft_empty_cache()
                emit("freed")
            elif cmd == "loras":
                emit("list", names=folder_paths.get_filename_list("loras"))
            elif cmd == "models":
                emit("list", names=folder_paths.get_filename_list(msg.get("kind", "diffusion_models")))
        except Exception as e:  # noqa: BLE001 - a failed scene must not kill the worker
            traceback.print_exc()
            emit("error", id=msg.get("id"), message=f"{type(e).__name__}: {e}")


main_loop()
