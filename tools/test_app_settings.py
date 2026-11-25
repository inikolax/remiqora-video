"""The «Настройки» page's server side, without a GPU: /api/app-settings returns the moved keys, accepts them under the same
settings.json keys, the H3 card no longer lists COMFY_ATTENTION, and the worker still reads the saved value.

    .venv\\Scripts\\python.exe tools\\test_app_settings.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, main, models_page, settings  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    print(("  ok   " if cond else "  FAIL ") + what)
    failed += 0 if cond else 1


KEYS = [k for k in settings.KEYS]
REAL = {k: getattr(config, k) for k in KEYS}
REAL_FILE = settings.FILE
tmp = tempfile.TemporaryDirectory()
settings.FILE = Path(tmp.name) / "settings.json"   # never the owner's data/settings.json
try:
    print("the page's view")
    view = main.app_settings_get()
    ok({"engine", "folders", "tools", "writer"} <= set(view), "engine, folders, tools and writer are there")
    ok([p["key"] for p in view["engine"]["params"]] == ["COMFY_ATTENTION"], "the engine section carries the fast-attention switch")
    ok(view["engine"]["params"][0]["kind"] == "switch" and isinstance(view["engine"]["params"][0]["value"], bool), "it is a switch with a bool value")
    tools = {t["key"] for t in view["tools"]}
    ok({"COMFY_DIR", "COMFY_PYTHON", "LLAMA_SERVER_BIN", "FFMPEG", "FFPROBE", "RIFE_BIN", "RTX_VSR", "H3_REF_DIR"} <= tools, "every tool path moved to the page")
    ok({f["key"] for f in view["folders"]} == {"H3_MODEL_ROOTS", "LORA_DIRS", "LTX25_LORA_DIRS", "LTX23_LORA_DIRS", "WAN_LORA_DIRS",
                                              "KREA_LORA_DIRS", "FLUX2_LORA_DIRS", "LLM_DIRS"}, "model roots and the LoRA / GGUF folders are listed")
    ok(view["writer"]["ctx"] == config.LLM_CTX and view["writer"]["contexts"] == list(settings.CONTEXTS), "the writer's context and its choices")
    ok({"COMFY_ATTENTION", "LLM_CTX", "COMFY_DIR"} <= set(view["values"]), "the plain settings are in `values`")

    print("the H3 card")
    snap = models_page.snapshot()
    h3 = [p["key"] for p in snap["sections"]["h3"]["params"]]
    ok("COMFY_ATTENTION" not in h3 and h3 == ["H3_TE_AHEAD"], "H3 parameters: only H3_TE_AHEAD is left")
    ok("tools" not in snap["sections"], "the models page no longer has a Tools section")
    ok(all("COMFY_ATTENTION" not in [p["key"] for p in s["params"]] for s in snap["sections"].values()), "no card lists COMFY_ATTENTION")

    print("saving")
    asyncio.run(main.app_settings_post(main.SettingsPatch(values={"COMFY_ATTENTION": True})))
    ok(json.loads(settings.FILE.read_text(encoding="utf-8")).get("COMFY_ATTENTION") == "ck", "settings.json keeps the same key, value «ck»")
    ok(config.COMFY_ATTENTION == "ck", "config has it at once")
    config.COMFY_ATTENTION = "sdpa"
    settings.apply(settings.saved())   # a fresh start reads the file
    ok(config.COMFY_ATTENTION == "ck", "a restart reads the saved value")
    src = (ROOT / "app" / "engine" / "worker.py").read_text(encoding="utf-8")
    ok('--use-ck-attention' in src and 'config.COMFY_ATTENTION == "ck"' in src, "the worker launches with the flag from config.COMFY_ATTENTION")
    ok(main.app_settings_get()["engine"]["params"][0]["value"] is True, "the page reads it back as on")

    asyncio.run(main.app_settings_post(main.SettingsPatch(values={"COMFY_ATTENTION": ""})))
    ok("COMFY_ATTENTION" not in json.loads(settings.FILE.read_text(encoding="utf-8")), "«Вернуть» drops the key from the file")

    asyncio.run(main.app_settings_post(main.SettingsPatch(values={"LLM_CTX": 16384})))
    ok(main.app_settings_get()["writer"]["ctx"] == 16384 and json.loads(settings.FILE.read_text(encoding="utf-8"))["LLM_CTX"] == 16384, "the writer's context saves under LLM_CTX")
    folder = str(Path(tmp.name) / "lora")
    asyncio.run(main.app_settings_post(main.SettingsPatch(values={"LORA_DIRS": [folder]})))
    got = next(f for f in main.app_settings_get()["folders"] if f["key"] == "LORA_DIRS")
    ok([d["dir"] for d in got["dirs"]] == [folder] and got["own"], "a folder list saves under its own key and shows as set here")
    try:
        asyncio.run(main.app_settings_post(main.SettingsPatch(values={"NOPE": 1})))
        ok(False, "an unknown key is refused")
    except Exception as e:   # HTTPException 400
        ok(getattr(e, "status_code", 0) == 400, "an unknown key is refused")

    print("the old route still works")
    asyncio.run(main.models_settings(main.SettingsPatch(values={"COMFY_ATTENTION": True})))
    ok(config.COMFY_ATTENTION == "ck", "/api/models/settings accepts the moved key too")
finally:
    settings.FILE = REAL_FILE
    for k, v in REAL.items():
        setattr(config, k, v)
    tmp.cleanup()

print("FAILED" if failed else "all ok")
sys.exit(1 if failed else 0)
