"""A drawn look rewrites a hand-written scene prompt (a73783a), but a shot made before that (0.3.0) stays: found by the key
of the prompt as it was, not shot again; a scene changed after that shoots with the new prompt. No GPU.

    .venv\\Scripts\\python.exe tools\\test_graph_drawn_cache.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.main as main  # noqa: E402,F401
from app import graph, graph_io, looks, projects, render  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


PROMPT = "A woman walks along the pier, photorealistic, shallow depth of field."


def run() -> None:
    g = {"rev": 0, "nodes": [
        {"id": "p1", "type": "prompt", "position": {"x": 0, "y": 0}, "data": {"title": "p", "text": PROMPT}},
        {"id": "s1", "type": "scene", "position": {"x": 320, "y": 0},
         "data": {"title": "s", "takes": [7], "take": 0, "look": "watercolor"}}],
        "edges": [{"id": "e1", "source": "p1", "sourceHandle": "text", "target": "s1", "targetHandle": "prompt"}]}
    proj = graph_io.new_project("drawn-cache", "16:9", g=g)
    pid = proj["id"]
    try:
        def node():
            c = graph.Ctx(projects.load(pid), graph.load(pid))
            return graph._out(c, "s1", "scene")

        new = node()
        ok(new.state == "todo" and "photorealistic" not in new.text and looks.LOOKS["watercolor"]["frame_en"] in new.text,
           "a drawn look: the prompt is rewritten, nothing shot yet")
        real = looks.drawn_of
        looks.drawn_of = lambda _x: False   # the prompt as 0.3.0 had it
        try:
            old = node()
        finally:
            looks.drawn_of = real
        ok(old.key != new.key and "photorealistic" in old.text, "the old key is another one")
        mp4, png = render.shot_paths(projects.folder(pid) / "scenes", old.key)
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"x")
        png.write_bytes(b"x")
        got = node()
        ok(got.state == "ready" and got.key == old.key and got.text == old.text,
           "a shot under the old key is kept: the scene is done")
        ok(got.takes[0]["cached"] and got.takes[0]["key"] == old.key, "its take is the cached one")

        def edit(gg):
            graph.node(gg, "p1")["data"]["text"] = PROMPT + " She smiles."
        graph.update(pid, edit)
        ch = node()
        ok(ch.state == "todo" and ch.key not in (old.key, new.key) and looks.LOOKS["watercolor"]["frame_en"] in ch.text
           and "photorealistic" not in ch.text, "a changed scene is to shoot, with the new prompt")
        pr, gr = projects.load(pid), graph.load(pid)
        c = graph.Ctx(pr, gr)
        a = graph._out(c, "s1", "scene")
        ok(graph._scene_kw(c, "s1", a)["prompt"] == ch.text, "it is shot with the new prompt")
    finally:
        projects.remove(pid)


if __name__ == "__main__":
    run()
    print("FAILED: %d" % failed if failed else "all passed")
    sys.exit(1 if failed else 0)
