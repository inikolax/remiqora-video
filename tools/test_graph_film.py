"""The graph's «Кино» template (app/graph_templates/film.json) without a GPU or an LLM: the template and its English
twin, «Написать» of a writer with two heroes and «Реплики» (a stand-in writer), «Развернуть в сцены» - a Krea portrait
per hero without a photo, each scene's «лица» from the heroes in it (the plan's `who`), the lines' speakers, the
scenes into the template's «Монтаж»; «Проверять лица» judging each scene by its own heroes; an older graph as it was.

    .venv\\Scripts\\python.exe tools\\test_graph_film.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.main as main  # noqa: E402,F401 - the routes, as the server has them
from app import checks, graph, graph_api, graph_io, jobs, projects  # noqa: E402
from app.llm import client as llm, writer  # noqa: E402
from app.planner import prompts  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


class Patch:
    def __init__(self):
        self.saved = []

    def __call__(self, obj, name, value):
        self.saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self.saved):
            setattr(obj, name, value)
        self.saved.clear()


MODEL = SimpleNamespace(id="stand-in.gguf", name="stand-in", mmproj="mm.gguf")


class FakeSession:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return SimpleNamespace(model=MODEL)

    async def __aexit__(self, *a):
        return False


def _job(kind: str) -> jobs.Job:
    j = jobs.Job(id=f"t-{kind}", params={}, kind=kind, status="running", steps=0)
    j.started = __import__("time").time()
    return j


SCENES = [  # (kind, who, beats): scene 1 both of them, 2 goes on, 3 only him, 4 both again
    ("new", [1, 2], ["Character 1 stands under the bus stop roof.", "Character 2 walks up with an umbrella."]),
    ("continue", [1, 2], ["They look at each other.", "Character 1 smiles."]),
    ("new", [2], ["Character 2 checks the timetable."]),
    ("new", [1, 2], ["The woman and the man walk away under one umbrella."]),
]


def fake_plan(plan: dict) -> dict:
    p = json.loads(json.dumps(plan))
    p.update(title_ru="Остановка", style_en="Realistic live-action cinematic look, night, rain.", audio_en="Soft rain.")
    p["scenes"] = p["scenes"][:len(SCENES)]
    for s, (kind, who, beats) in zip(p["scenes"], SCENES):
        s.update(kind=kind, who=who, beats_en=beats, ru=" ".join(beats), place_en="A bus stop at night in the rain.", sound_en="rain")
    p["cast"] = (p.get("cast") or [])[:1] + [{"gender": "male", "age": 40, "en": "a writer's own man", "outfit_en": "a coat"}]
    return p


def run() -> None:
    print("the template")
    ru = json.loads((graph_io.BUILTIN_TEMPLATES / "film.json").read_text(encoding="utf-8"))
    en = json.loads((graph_io.BUILTIN_TEMPLATES / "en" / "film.json").read_text(encoding="utf-8"))
    ok(any(t["id"] == "film" for t in graph_io.templates()), "«Кино» is listed")
    ok([(n["id"], n["type"]) for n in ru["nodes"]] == [(n["id"], n["type"]) for n in en["nodes"]] and ru["edges"] == en["edges"],
       "its English twin: the same nodes and wires")
    types = [n["type"] for n in ru["nodes"]]
    ok(types.count("hero") == 2 and {"idea", "writer", "montage", "output", "note"} <= set(types), "an idea, two heroes, a writer, a montage, an output, a note")
    w0 = next(n for n in ru["nodes"] if n["type"] == "writer")["data"]
    ok(w0.get("mode") == "several" and w0.get("lines") and w0.get("ref_photo") and w0.get("seconds") == 60, "the writer: several people, lines, faces, a minute")
    ok(sorted(e["id"] for e in graph.clean({"nodes": ru["nodes"], "edges": ru["edges"]})["edges"]) == sorted(e["id"] for e in ru["edges"]), "every wire is between existing ports")

    pt = Patch()
    pids = []
    seen: dict = {}

    async def fake_write(plan, photo=None, folder=None):
        seen["cast"] = json.loads(json.dumps(plan.get("cast")))
        return fake_plan(plan)

    async def fake_lines(plan, indices, seed=None):
        seen["lines"] = list(indices)
        for s in plan["scenes"]:
            s["lines"] = [{"who": s["who"][-1], "text": "Сорок второй ещё ходит?", "how": ""}]
        return plan
    pt(writer, "write", fake_write)
    pt(writer, "write_lines", fake_lines)
    pt(llm, "session", FakeSession)
    try:
        t = next(x for x in graph_io.templates() if x["id"] == "film")
        proj = graph_io.new_project("Кино", "16:9", g=graph_api._fresh_ids({"nodes": t["nodes"], "edges": t["edges"]}))
        proj["settings"].update(delivery="cinema", look="live_cinema", look_own="")
        projects.save(proj)
        pid = proj["id"]
        pids.append(pid)
        g = graph.load(pid)
        by = {n["type"]: n for n in g["nodes"]}
        wid, mid = by["writer"]["id"], by["montage"]["id"]
        heroes = sorted((n for n in g["nodes"] if n["type"] == "hero"), key=lambda n: n["position"]["y"])
        ok(by["montage"]["data"].get("from") == wid, "a new project: the montage's `from` is its writer's new id")

        print("«Написать»: two heroes, lines")
        asyncio.run(graph.run_llm(_job("llm"), pid, [wid], None))
        g = graph.load(pid)
        w = graph.node(g, wid)
        plan = w["data"].get("plan") or {}
        ok(len(seen.get("cast") or []) == 2 and seen["cast"][1]["en"] == heroes[1]["data"]["en"], "the writer is given both heroes' looks")
        ok(seen.get("lines") == list(range(len(SCENES))), "«Реплики»: the lines written for every scene")
        ok([c["en"] for c in plan.get("cast") or []] == [h["data"]["en"] for h in heroes], "the plan cast")
        ok(graph.evaluate_node(graph.Ctx(projects.load(pid), g), wid).state == "ready", "the writer is ready (its sig with «Реплики»)")

        print("«Развернуть в сцены»")
        graph.expand(pid, wid)
        g = graph.load(pid)
        c = graph.Ctx(projects.load(pid), g)
        pics = [n for n in g["nodes"] if n["type"] == "picture" and n["data"].get("hero")]
        por = {n["data"]["hero"]: n["id"] for n in pics}
        ok(len(pics) == 2 and set(por) == {h["id"] for h in heroes} and all(n["data"]["model"] == "krea2" and n["data"]["prompt"] for n in pics),
           "a Krea portrait for each hero without a photo")
        scenes = sorted((n for n in g["nodes"] if n["type"] == "scene"), key=lambda n: n["data"]["scene"])
        faces = {n["data"]["scene"]: [s for s, _ in c.inputs(n["id"], "faces")] for n in scenes}
        h1, h2 = por[heroes[0]["id"]], por[heroes[1]["id"]]
        ok(faces == {0: [h1, h2], 1: [], 2: [h2], 3: [h1, h2]}, f"each scene's «лица»: the heroes in it ({faces})")
        ok([s for s, _ in c.inputs(scenes[1]["id"], "start")] == [scenes[0]["id"]], "a continuation starts from the scene before")
        p3 = next(n for n in g["nodes"] if n["type"] == "prompt" and n["data"].get("scene") == 2)
        ok("Character 2 is the person in <Picture 1>" in p3["data"]["text"] and "Character 1 (" not in p3["data"]["text"],
           "scene 3: only him, his portrait is <Picture 1>")
        ok([ln["who"] for ln in p3["data"]["lines"]] == ["Character 2"] and "Character 2" in prompts.speakers_in(p3["data"]["text"]),
           "the line's speaker: the hero in the scene, as the prompt names him")
        p1 = next(n for n in g["nodes"] if n["type"] == "prompt" and n["data"].get("scene") == 0)
        ok("Character 1 is the person in <Picture 1>" in p1["data"]["text"] and "Character 2 is the person in <Picture 2>" in p1["data"]["text"],
           "scene 1: both, in the order of its «лица»")
        mon = graph.node(g, mid)
        ok(mon["data"].get("order") == [n["id"] for n in scenes] and len(c.inputs(mid, "clips")) == len(SCENES),
           "the scenes go into the template's montage, in order")
        ok(not [n for n in g["nodes"] if n["type"] in ("join",)] and sum(1 for n in g["nodes"] if n["type"] == "output") == 1,
           "no join or second output of its own")
        ids_before = sorted(n["id"] for n in g["nodes"])
        graph.expand(pid, wid)
        g2 = graph.load(pid)
        ok(sorted(n["id"] for n in g2["nodes"]) == ids_before and len(g2["edges"]) == len(g["edges"]), "expanded again: the same nodes and wires")

        print("«Проверять лица»: each scene by its heroes")
        ok(graph.face_judged(c, mid) and not graph.evaluate_node(c, mid).warn, "the montage judges without «лицо»: no warning")
        tmp = Path(c.folder) / "t.png"
        tmp.write_bytes(b"x")
        got: dict = {}
        real_out, real_eval = graph._out, graph.evaluate_node
        pt(graph, "_out", lambda cc, nid, port: graph.Art("ready", path=tmp) if cc.by[nid]["type"] == "picture" else real_out(cc, nid, port))
        pt(graph, "evaluate_node", lambda cc, nid, _s=None: graph.Art("ready", path=tmp) if cc.by[nid]["type"] == "scene" else real_eval(cc, nid, _s))
        pt(checks, "heroes_similarity", lambda v, refs: got.setdefault(len(got), len(refs)) and 0.5)
        sc = graph.face_scores(graph.Ctx(projects.load(pid), graph.load(pid)), mid)
        ok(set(sc) == {scenes[0]["id"], scenes[2]["id"], scenes[3]["id"]} and list(got.values()) == [2, 1, 2],
           f"judged: the scenes with faces, each against its own ({list(got.values())})")
        pt.undo()   # the real evaluation again (the writer's stand-ins are done with too)

        print("a hero with a photo of their own")

        def photo(gg):
            graph.node(gg, heroes[0]["id"])["data"]["photo"] = "she.png"
        (Path(c.folder) / "she.png").write_bytes(b"x")
        graph.update(pid, photo)
        graph.expand(pid, wid)
        g = graph.load(pid)
        c = graph.Ctx(projects.load(pid), g)
        pics = [n for n in g["nodes"] if n["type"] == "picture" and n["data"].get("hero")]
        s0 = next(n for n in g["nodes"] if n["type"] == "scene" and n["data"]["scene"] == 0)
        ok([n["data"]["hero"] for n in pics] == [heroes[1]["id"]], "her portrait goes away, his stays")
        ok([s for s, _ in c.inputs(s0["id"], "faces")] == [heroes[0]["id"], h2], "scene 1's «лица»: her photo, his portrait")

        print("an older graph stays as it was")
        t2 = next(x for x in graph_io.templates() if x["id"] == "writer-face")
        p2 = graph_io.new_project("старый", "16:9", g=graph_api._fresh_ids({"nodes": t2["nodes"], "edges": t2["edges"]}))
        pids.append(p2["id"])
        g = graph.load(p2["id"])
        w2 = next(n for n in g["nodes"] if n["type"] == "writer")
        hh = next(n for n in g["nodes"] if n["type"] == "hero")
        c2 = graph.Ctx(projects.load(p2["id"]), g)
        idea, hs = graph.writer_inputs(c2, w2)
        d = w2["data"]
        old_sig = graph._sha(idea, [{k: h["data"].get(k) for k in ("gender", "age", "en", "outfit_en", "photo")} for h in hs],
                             {k: d.get(k) for k in ("seconds", "mode", "mood", "music", "ref_photo")})
        ok(graph.writer_sig(c2, w2) == old_sig, "a writer without «Реплики»: its sig as before")
        (projects.folder(p2["id"]) / "me.png").write_bytes(b"x")
        one = fake_plan(writer.new_plan("x", 15, "one", seed=3))
        one["mode"], one["cast"] = "one", [{"gender": "female", "age": 30, "en": "a woman", "outfit_en": "a coat"}]
        for s in one["scenes"]:
            s["who"] = [1]

        def put(gg):
            graph.node(gg, hh["id"])["data"].update(photo="me.png", en="a woman", gender="female")
            graph.node(gg, w2["id"])["data"]["plan"] = one
        graph.update(p2["id"], put)
        graph.expand(p2["id"], w2["id"])
        g = graph.load(p2["id"])
        c2 = graph.Ctx(projects.load(p2["id"]), g)
        ok(not [n for n in g["nodes"] if n["type"] == "picture"], "a hero with a photo: no portrait")
        ok(sum(1 for n in g["nodes"] if n["type"] == "join") == 1 and sum(1 for n in g["nodes"] if n["type"] == "output") == 1,
           "its own join and output, as before")
        s0 = next(n for n in g["nodes"] if n["type"] == "scene" and n["data"]["scene"] == 0)
        ok([s for s, _ in c2.inputs(s0["id"], "faces")] == [hh["id"]], "its first scene's «лица»: the hero's photo")
    finally:
        pt.undo()
        for p in pids:
            projects.remove(p)


def stale_hints_and_drop_pin():
    """retry_hint goes when the picture's prompt, look or its scene's role is edited; a hand-built beat montage pins its drop once."""
    def doc(prompt="a club", look="", role="hero", hint="no faces"):
        return {"nodes": [{"id": "p", "type": "picture", "data": {"prompt": prompt, "look": look, "retry_hint": hint}},
                          {"id": "s", "type": "scene", "data": {"role": role}}],
                "edges": [{"id": "e", "source": "p", "sourceHandle": "image", "target": "s", "targetHandle": "start"}]}
    for what, new in [("prompt", doc(prompt="a beach")), ("look", doc(look="anime")), ("scene role", doc(role="macro"))]:
        graph.drop_stale_hints(doc(), new)
        ok("retry_hint" not in new["nodes"][0]["data"], f"retry_hint is dropped when the {what} is edited")
    same = doc()
    graph.drop_stale_hints(doc(), same)
    ok(same["nodes"][0]["data"]["retry_hint"] == "no faces", "an untouched picture keeps its retry_hint")
    moved = doc()
    moved["nodes"][0]["position"] = {"x": 5, "y": 5}
    graph.drop_stale_hints(doc(), moved)
    ok(moved["nodes"][0]["data"].get("retry_hint") == "no faces", "moving the node keeps its retry_hint")

    saved = {}
    pt = Patch()
    try:
        pt(graph, "_out", lambda c, *a: SimpleNamespace(song="sg1"))
        pt(graph, "song_sig", lambda sid: "sig:" + sid)
        pt(graph, "update", lambda pid, fn: fn(saved.setdefault("g", {"nodes": [{"id": "m", "type": "beat_montage", "data": {}}]})))
        c = SimpleNamespace(by={"m": {"data": {}}}, pid="x", inputs=lambda nid, h: [("t", "song")])
        art = SimpleNamespace(beat={"drop": 31.5})
        graph._pin_beat_drop(c, "m", art)
        ok(saved["g"]["nodes"][0]["data"].get("drop_auto") == {"drop": 31.5, "sig": "sig:sg1"}, "a hand-built beat montage pins its drop on the first build")
        c.by["m"]["data"]["drop_auto"] = {"drop": 1.0, "sig": "x"}
        saved["g"]["nodes"][0]["data"]["drop_auto"] = {"drop": 1.0, "sig": "x"}
        graph._pin_beat_drop(c, "m", art)
        ok(saved["g"]["nodes"][0]["data"]["drop_auto"]["drop"] == 1.0, "an existing pin is not overwritten")
        saved.clear()
        c.by["m"]["data"] = {"drop": 20}
        graph._pin_beat_drop(c, "m", art)
        ok("g" not in saved, "the user's own drop needs no pin")
    finally:
        pt.undo()


if __name__ == "__main__":
    run()
    stale_hints_and_drop_pin()
    print("FAILED: %d" % failed if failed else "all passed")
    sys.exit(1 if failed else 0)
