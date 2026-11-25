"""The graph «Идея» node's modes (app/llm/idea.py) without a GPU or an LLM: a stand-in for client.session.

    .venv\\Scripts\\python.exe tools\\test_idea_modes.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.main as main  # noqa: E402,F401 - the routes, as the server has them
from app.llm import client, idea, translate  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


class Stand:
    def __init__(self):
        self.model = SimpleNamespace(name="stand-in")
        self.calls: list[tuple[str, str]] = []

    async def chat_json(self, system, user, schema, **kw):
        self.calls.append((system, user))
        props = schema.get("properties", {})
        if "prompt_en" in props:
            return {"prompt_en": "A woman stands in a rainy street, medium close-up."}
        if "scenes" in props:
            return {"title": "Дождь", "scenes": [
                {"where": "Улица ночью", "who": "Девушка", "what": "Идёт под дождём."},
                {"where": "Кафе", "who": "Девушка, бариста", "what": "Берёт чашку."},
                {"where": "Окно", "who": "Девушка", "what": "Улыбается отражению."}]}
        return {"answer": "Варианты: 1) тихо; 2) ярко. Ловушки: текст в кадре."}


def run(coro_fn):
    stand = Stand()

    @asynccontextmanager
    async def session(model_id=None):
        yield stand

    saved = client.session
    client.session = session
    try:
        return asyncio.run(coro_fn()), stand
    finally:
        client.session = saved


T = "Девушка идёт под дождём и заходит в кафе."
SCENE = {"id": "s1", "kind": "scene", "seconds": 5, "frame": False}
SCENE2 = {"id": "s2", "kind": "scene", "seconds": 5, "frame": False}
PIC = {"id": "p1", "kind": "picture"}
FLUX = {"id": "p2", "kind": "picture", "flux": True}

print("default mode by the wiring")
ok(idea.default_mode([]) == "video", "nothing wired -> video")
ok(idea.default_mode(["scene"]) == "video", "scenes only -> video")
ok(idea.default_mode(["picture", "picture"]) == "picture", "pictures only -> picture")
ok(idea.default_mode(["scene", "picture"]) == "video", "both -> video by hand (auto makes two)")

print("wiring plan")
p = idea.plan("auto", [PIC])
ok(len(p) == 1 and p[0]["form"] == "picture" and p[0]["targets"] == ["p1"], "auto, pictures only: one picture prompt")
p = idea.plan("auto", [SCENE, SCENE2])
ok(len(p) == 1 and p[0]["form"] == "video" and p[0]["targets"] == ["s1", "s2"], "auto, scenes only: one video prompt on both scenes")
p = idea.plan("auto", [])
ok(len(p) == 1 and p[0]["form"] == "video" and p[0]["targets"] == [], "auto, nothing wired: one video prompt, no wires")
p = idea.plan("auto", [SCENE, PIC])
ok([x["form"] for x in p] == ["video", "picture"] and p[0]["targets"] == ["s1"] and p[1]["targets"] == ["p1"], "auto, both: two prompts, each with its own wires")
p = idea.plan("auto", [{**SCENE, "seconds": 10, "frame": True}])
ok(p[0]["seconds"] == 10 and p[0]["frame"], "the scene's seconds and start frame go to the video prompt")
ok(idea.plan("auto", [SCENE, FLUX])[1]["form"] == "frame", "a picture drawn by reference takes the FLUX form")
p = idea.plan("video", [SCENE, PIC])
ok(len(p) == 1 and p[0]["form"] == "video" and p[0]["targets"] == ["s1"], "video by hand: the picture's wire stays on the idea")
p = idea.plan("picture", [SCENE, PIC])
ok(len(p) == 1 and p[0]["form"] == "picture" and p[0]["targets"] == ["p1"], "picture by hand: the scene's wire stays on the idea")

print("prompt modes")
r, st = run(lambda: idea.make("picture", T, [PIC]))
sysp = st.calls[0][0]
ok(len(st.calls) == 1 and r["prompts"][0]["form"] == "picture" and r["prompts"][0]["targets"] == ["p1"], "picture: one call, one picture prompt")
ok("ONE still picture" in sysp and "No motion words" in sysp and "no camera moves" in sysp.lower(), "picture: the system prompt asks for a frozen frame, no motion, no camera moves")
ok("No text, no letters, no logos" in sysp and "feminine" in sysp and "Never add" in sysp, "picture: no text/logos, no built-in beauty or gender")
ok("Krea 2" in sysp, "picture: Krea 2 rules")
r, st = run(lambda: idea.make("picture", T, [FLUX]))
ok("FLUX.2 Klein" in st.calls[0][0] and r["prompts"][0]["form"] == "frame", "picture by reference: FLUX.2 rules")
r, st = run(lambda: idea.make("video", T, [SCENE]))
ok(st.calls[0][0] == translate._system(None, "5", False, "video").replace("Russian", "Russian"), "video: the system prompt is the translator's, unchanged")
ok("PICTURE" not in st.calls[0][0] and "frozen frame" not in st.calls[0][0], "video: no picture rules mixed in")
r, st = run(lambda: idea.make("auto", T, [SCENE, PIC]))
ok(len(st.calls) == 2 and [x["form"] for x in r["prompts"]] == ["video", "picture"], "both wired: two calls, a video and a picture prompt")
ok("Krea 2" not in st.calls[0][0] and "Krea 2" in st.calls[1][0], "both wired: each prompt has its own rules")

print("script and talk change no wires")
r, st = run(lambda: idea.make("script", T, [SCENE, PIC]))
ok("prompts" not in r and r["note"]["text"], "script: a note, no prompts to wire")
ok(r["note"]["text"].count("Сцена ") == 3 and "Где: Кафе" in r["note"]["text"], "script: three scenes with where/who/what")
ok("3 to 8 scenes" in st.calls[0][0] and "where" in st.calls[0][0], "script: its rules are in the system prompt")
r, st = run(lambda: idea.make("think", T, [SCENE]))
ok("prompts" not in r and "Ловушки" in r["note"]["text"], "think: a note with the answer")
ok("pitfalls" in st.calls[0][0] and "do not write the script" in st.calls[0][0].lower(), "think: asks for variants and pitfalls, not a script")

print("a bad mode, the route")
try:
    run(lambda: idea.make("nonsense", T, []))
    ok(False, "unknown mode refused")
except client.LLMError:
    ok(True, "unknown mode refused")
ok(any(getattr(r, "path", "") == "/api/llm/idea" for r in main.app.routes), "the route /api/llm/idea exists")
ok(any(getattr(r, "path", "") == "/api/llm/translate" for r in main.app.routes), "the old /api/llm/translate stays")

print("old behaviour")
import inspect  # noqa: E402
ok(inspect.signature(translate.translate).parameters["extra"].default == "", "translate: the extra rules are off by default")
src = (ROOT / "frontend/src/components/graph/NodeInspector.vue").read_text(encoding="utf-8")
ok("'prompt_id'" in src and "'prompt_en'" in src and "ideaMode.value || ''" not in src and "IDEA_MODES as readonly string[]).includes(d.value.mode)" in src,
   "the inspector keeps prompt_id / prompt_en for the video prompt; an idea without a mode goes by its wiring")

print(f"\n{'ALL OK' if not failed else str(failed) + ' FAILED'}")
sys.exit(1 if failed else 0)
