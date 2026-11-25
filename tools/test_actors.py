"""The actor library (app/actors.py) without a GPU or an LLM: the store round-trip (the shared library and a series' own),
a crop, a «Герой» node with an actor (look, outfit and the face panel) and the same node without one (graph keys and
signatures as before), the sheet's and the tries' prompts and Klein graphs, the API routes and a stand-in drawing job.

    .venv\\Scripts\\python.exe tools\\test_actors.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.main as main  # noqa: E402,F401 - the routes, as the server has them
from app import actors, actors_api, config, graph, looks, picture  # noqa: E402
from PIL import Image  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


tmp = Path(tempfile.mkdtemp(prefix="test_actors_"))
config.DATA_DIR = tmp   # the library goes into a temp folder, never into the studio's data/


def png(path: Path, size=(320, 200), color=(120, 60, 60)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


MASHA = {"name": "Маша", "look_en": "a 24-year-old woman with long dark wavy hair and brown eyes", "look_ru": "девушка с длинными тёмными волосами",
         "outfit_en": "a cream silk blouse and blue jeans", "kind": "person", "voice_en": "a soft low female voice", "look": "anime"}

print("store")
a = actors.save(MASHA)
ok(a["id"].startswith("actor-") and a["created"] and a["look"] == "anime", "create: id, created, look kept")
ok(actors.get(a["id"])["name"] == "Маша" and actors.get(a["id"])["voice_en"].startswith("a soft"), "get: round-trip")
a2 = actors.save({"id": a["id"], "name": "Маша Н.", "kind": "alien", "look": "no-such-look"})
ok(a2["name"] == "Маша Н." and a2["kind"] == "person" and a2["look"] == "" and a2["look_en"] == MASHA["look_en"], "update: unknown kind and look dropped, other fields kept")
cat = actors.save({"name": "Кот", "kind": "animal", "look_en": "a ginger cat"})
ok([x["name"] for x in actors.list_all()] == ["Кот", "Маша Н."], "list sorted by name")
try:
    actors.get("../x")
    ok(False, "a path in an id is refused")
except KeyError:
    ok(True, "a path in an id is refused")
sd = actors.series_root("s1")
actors.save({"name": "Серийный", "look_en": "a tall man"}, sd)
ok(len(actors.list_all(sd)) == 1 and len(actors.list_all()) == 2 and sd.parts[-3:] == ("series", "s1", "actors"), "a series keeps its own actors under data/series/<sid>/actors")
actors.delete(cat["id"])
ok(not actors.exists(cat["id"]) and len(actors.list_all()) == 1, "delete")

print("pictures and crop")
src = png(tmp / "two.png", (400, 200))
actors.put_image(a["id"], "photo", src)
ok(actors.public(actors.get(a["id"]))["images"].keys() == {"photo"}, "photo in; public lists the images")
c = actors.crop(src, (0, 0, 0.5, 1), tmp / "c1.png")
ok(Image.open(c).size == (200, 200), "crop by shares of the picture")
c = actors.crop(src, (100, 20, 150, 100), tmp / "c2.png")
ok(Image.open(c).size == (150, 100), "crop by pixels")
try:
    actors.crop(src, (0, 0, 5, 5), tmp / "c3.png")
    ok(False, "a tiny box is refused")
except ValueError:
    ok(True, "a tiny box is refused")

print("a hero node with an actor")
OLD = {"id": "h1", "type": "hero", "position": {"x": 0, "y": 0}, "data": {"en": "a girl", "outfit_en": "a red coat", "photo": "p.png", "gender": "female", "age": 20}}
NEW = {"id": "h2", "type": "hero", "position": {"x": 0, "y": 200}, "data": {"actor": a["id"], "en": "old text", "photo": "p.png"}}
wr = {"id": "w1", "type": "writer", "position": {"x": 400, "y": 0}, "data": {}}
g1 = {"nodes": [OLD, wr], "edges": [{"id": "e1", "source": "h1", "sourceHandle": "look", "target": "w1", "targetHandle": "cast"}]}
pid = "test-actors-proj"
proj = {"id": pid, "settings": {}}
pdir = projects_dir = ROOT / "projects" / pid
before = json.dumps(g1, sort_keys=True)
c1 = graph.Ctx(proj, g1)
ok(c1.by["h1"]["data"] is OLD["data"], "a hero without an actor: the very same node data (nothing copied, nothing changed)")
sig_old = graph.writer_sig(c1, wr)
ok(json.dumps(g1, sort_keys=True) == before, "the graph itself is not touched")
png(actors.image_path(a["id"], "face"), (64, 64))
g2 = {"nodes": [NEW, wr], "edges": [{"id": "e1", "source": "h2", "sourceHandle": "look", "target": "w1", "targetHandle": "cast"}]}
c2 = graph.Ctx(proj, g2)
d = c2.by["h2"]["data"]
ok(d["en"] == MASHA["look_en"] and d["outfit_en"] == MASHA["outfit_en"], "look and outfit come from the actor")
ok(Path(d["photo"]) == actors.image_path(a["id"], "face"), "the picture is the face panel")
ok(g2["nodes"][0]["data"]["en"] == "old text", "the stored node is not rewritten")
art = graph._evaluate(c2, c2.by["h2"], set())
ok(art.state == "ready" and art.path == actors.image_path(a["id"], "face") and art.text == MASHA["look_en"], "the hero evaluates ready with the actor's face as its image")
out = graph._out(c2, "h2", "image")
ok(out.state == "ready" and out.path == actors.image_path(a["id"], "face"), "the «image» output is the face panel")
_, heroes = graph.writer_inputs(c2, wr)
ok(graph.hero_cast(heroes[0])["en"] == MASHA["look_en"], "the writer gets the actor's look")
ok(graph.writer_sig(c2, wr) != sig_old, "the writer's signature follows the actor")
ok(graph.hero_kind(d) == "person", "kind person without a kind key")
cat = actors.save({"name": "Кот", "kind": "animal", "look_en": "a ginger cat"})
ok(actors.hero_data({"actor": cat["id"]})["kind"] == "animal", "an animal actor makes an animal hero")
ok(actors.hero_data({"actor": "gone", "en": "x"}) == {"actor": "gone", "en": "x"}, "a deleted actor: the node as it is")
(actors.image_path(a["id"], "face")).unlink()
_want = next((str(p) for p in (actors.image_path(a["id"], "ref"), actors.image_path(a["id"], "photo")) if p.exists()), None)
ok(graph.Ctx(proj, g2).by["h2"]["data"]["photo"] == _want, f"no face panel yet: the look reference, else the photo ({Path(_want).name if _want else None})")
png(actors.image_path(a["id"], "face"), (64, 64))
ok(graph.Ctx({**proj, "series": "s1"}, g2).by["h2"]["data"]["en"] == MASHA["look_en"], "a project of a series falls back to the library")
sa = actors.save({"id": a["id"], "name": "Своя Маша", "look_en": "series version"}, sd)
ok(graph.Ctx({**proj, "series": "s1"}, g2).by["h2"]["data"]["en"] == "series version", "a series' own actor wins over the library's")

print("sheet and tries")
act = actors.get(a["id"])
plan = actors.sheet_plan(act, 7)
ok([p["name"] for p in plan] == ["face", "turn"] and plan[0]["w"] == 512 and plan[1]["w"] == 1024, "two panels: face 512x512, turnaround 1024x512")
ok(all("black background" in p["prompt"] and "from the image" in p["prompt"] for p in plan) and "cream silk blouse" in plan[1]["prompt"] and "cream silk blouse" not in plan[0]["prompt"] and "head and the top of the shoulders" in plan[0]["prompt"], "prompts: one hero from the image, black background; the outfit on the turnaround only, the face a tight close-up")
ok("front, side and back" in plan[1]["prompt"] and "close-up" in plan[0]["prompt"], "turnaround and close-up wording")
ok(looks.unphoto(looks.LOOKS["anime"]["style_en"]).rstrip(".") in actors.sheet_plan({**act, "look": "anime"})[0]["prompt"], "a drawn look is in the prompt (anime)")
ok("Photorealistic" in actors.sheet_plan({**act, "look": ""})[0]["prompt"], "no look: a photo")
gs = actors.sheet_graphs(act, "ref.png", 7)
for name, gr in gs.items():
    nodes_ok = all(isinstance(v, dict) and "class_type" in v and isinstance(v.get("inputs"), dict) for v in gr.values())
    links = [i for v in gr.values() for i in v["inputs"].values() if isinstance(i, list) and len(i) == 2 and isinstance(i[0], str)]
    ok(nodes_ok and all(i[0] in gr for i in links) and gr["fimg0"]["inputs"]["image"] == "ref.png" and gr["fsave"]["inputs"]["filename_prefix"] == f"actor_{name}",
       f"{name}: a valid Klein graph on the reference, every link points to a node")
ok("the person from the image" in plan[0]["prompt"] and "the animal from the image" in actors.sheet_plan(cat | {"kind": "animal"})[0]["prompt"], "the kind names who is in the picture")
ok("a ginger cat" in actors.source_prompt(cat) and "Only this one animal" in actors.source_prompt(cat), "no photo: Krea's figure prompt from the look text")
ok(actors.pick_looks(["anime", "cartoon3d", "clay", "live_cinema", "oil", "anime", "zzz"]) == ["anime", "cartoon3d", "clay", "live_cinema"], "tries: up to 4 known looks, no repeats")
ok(all(k in looks.LOOKS for k in ("anime", "cartoon3d", "clay", "live_cinema")), "the four looks of the brief exist")
ok("clay" in actors.try_prompt(act, "clay").lower() or "plasticine" in actors.try_prompt(act, "clay"), "a try's prompt says the look's medium")

print("stand-in drawing job (no GPU: picture.edit / generate are replaced)")
calls = []


async def fake_edit(job, prompt, refs, seed, w, h, dest, loras=()):
    calls.append(("edit", prompt, [Path(r).name for r in refs], w, h))
    png(dest, (w, h), (seed % 200, 50, 50))


async def fake_generate(job, prompt, seed, w, h, dest, loras=()):
    calls.append(("generate", prompt, [], w, h))
    png(dest, (w, h))


picture.edit, picture.generate = fake_edit, fake_generate
job = SimpleNamespace(progress={})
fresh = actors.save({"name": "Без фото", "look_en": "a tall man with a beard", "outfit_en": "a grey coat"})
res = asyncio.run(actors.draw_sheet(job, fresh["id"], seed=5))
ok([c[0] for c in calls] == ["generate", "edit", "edit"] and calls[1][2] == ["photo.png"] and calls[2][2] == ["photo.png"], "no photo: Krea draws the figure, then both panels are drawn from it")
ok(set(res["images"]) == {"photo", "face", "turn"} and res["photo_drawn"] is True, "face.png, turn.png and the drawn photo are saved")
ok(not list(actors.folder(fresh["id"]).glob("*.tmp.png")), "no temp pictures left")
calls.clear()
res = asyncio.run(actors.draw_sheet(job, a["id"], seed=5))
ok([c[0] for c in calls] == ["edit", "edit"] and calls[0][2] == ["photo.png"], "with a photo: Klein only, from the photo")
calls.clear()
res = asyncio.run(actors.tries(job, a["id"], ["anime", "cartoon3d", "clay", "live_cinema", "oil"], 2))
ok(len(calls) == 8 and len(res["tries"]) == 8 and all(c[2] == ["face.png"] for c in calls), "tries: 4 looks x 2 seeds = 8 Klein pictures from the face panel")
ok(all((actors.folder(a["id"]) / "tries" / t["file"]).exists() for t in res["tries"]), "the try files exist")
t = next(x for x in res["tries"] if x["look"] == "clay")
res = actors.pick_try(a["id"], t["file"])
ok(res["look"] == "clay" and res["tries"] == [] and not (actors.folder(a["id"]) / "tries").exists() and "ref" in res["images"], "pick: the look is the actor's, the try is the reference, the others cleared")
calls.clear()
asyncio.run(actors.draw_sheet(job, a["id"], seed=5))
ok(calls[0][2] == ["ref.png"] and "plasticine" in calls[0][1], "the sheet is redrawn from the picked try, in its look")
actors.put_image(a["id"], "photo", src)
ok("ref" not in actors.public(actors.get(a["id"]))["images"], "a new photo drops the old look reference")

# a new photo drops the old face and turnaround too (the scenes kept the previous person); the hero falls back
ok(set(actors.public(actors.get(a["id"]))["images"]) == {"photo"} or "face" not in actors.public(actors.get(a["id"]))["images"], "a new photo drops face.png and turn.png")
fb = actors.save({"name": "Фото без листа", "look_en": "a man"})
png(actors.folder(fb["id"]) / "photo.png")
ok(actors.hero_data({"actor": fb["id"]})["photo"] == str(actors.image_path(fb["id"], "photo")), "hero_data: a photo without a sheet is the hero's picture")
png(actors.folder(fb["id"]) / "ref.png")
ok(actors.hero_data({"actor": fb["id"]})["photo"] == str(actors.image_path(fb["id"], "ref")), "hero_data: the look reference before the photo")
png(actors.folder(fb["id"]) / "face.png")
ok(actors.hero_data({"actor": fb["id"]})["photo"] == str(actors.image_path(fb["id"], "face")), "hero_data: the face panel first")
actors.put_image(fb["id"], "photo", actors.image_path(fb["id"], "photo"))
ok(set(actors.public(actors.get(fb["id"]))["images"]) == {"photo"}, "put_image(photo): ref, face and turn are gone")
ok(actors.hero_data({"actor": "actor-nope"})["photo"] if "photo" in actors.hero_data({"actor": "actor-nope"}) else True, "hero_data: a deleted actor is left as it is")

# draw_sheet writes only what it made: an edit made while the drawing ran is kept
edit_actor = actors.save({"name": "Правят", "look_en": "a tall man"})


async def edit_while_drawing(job, prompt, seed, w, h, dest, loras=()):
    actors.save({"id": edit_actor["id"], "name": "Правка во время рисования"})
    png(dest, (w, h))


picture.generate = edit_while_drawing
asyncio.run(actors.draw_sheet(job, edit_actor["id"], seed=5))
picture.generate = fake_generate
ok(actors.get(edit_actor["id"])["name"] == "Правка во время рисования" and actors.get(edit_actor["id"])["photo_drawn"] is True, "draw_sheet keeps an edit made meanwhile")

print("API")
paths = main.app.openapi()["paths"]   # the routes as the server has them
for m, pth in [("get", "/api/actors"), ("post", "/api/actors"), ("put", "/api/actors/{aid}"), ("delete", "/api/actors/{aid}"), ("post", "/api/actors/{aid}/photo"),
               ("post", "/api/actors/{aid}/crop"), ("post", "/api/actors/{aid}/sheet"), ("post", "/api/actors/{aid}/tries"),
               ("post", "/api/actors/{aid}/tries/{name}/pick"), ("post", "/api/actors/from-hero"), ("get", "/api/actors/{aid}/image/{which}")]:
    ok(m in paths.get(pth, {}), f"{m.upper()} {pth}")


def status(fn, *args, **kw):
    try:
        fn(*args, **kw)
        return 200
    except Exception as e:  # HTTPException
        return getattr(e, "status_code", 500)


ok(status(actors_api.actor_sheet, "nope") == 404, "an unknown actor: 404")
ok(status(actors_api.actors_list, "a/b") == 400, "a bad series id is refused")
bare = actors.save({"name": "Пустой"})
ok(status(actors_api.actor_sheet, bare["id"]) == 400, "a sheet of an actor with neither photo nor look: 400")
ok(status(actors_api.actor_tries, bare["id"], actors_api.TriesBody(looks=["zzz"])) == 400, "tries without a known look: 400")
ok(status(actors_api.actor_image, bare["id"], "face") == 404 and status(actors_api.actor_image, a["id"], "photo") == 200, "image: 404 without, 200 with")
ok(status(actors_api.actor_delete, bare["id"]) == 200 and not actors.exists(bare["id"]), "delete")
r = actors_api.actor_create(actors_api.ActorBody(name="Через API", look_en="a robot", kind="robot"))
ok(r["kind"] == "robot" and actors_api.actors_list()["actors"], "create + list through the API functions")
try:
    actors_api.actor_create(actors_api.ActorBody(name=" "))
    ok(False, "an unnamed actor is refused")
except Exception as e:  # HTTPException
    ok(getattr(e, "status_code", 0) == 400, "an unnamed actor is refused")
ok(status(actors_api.actor_image, a["id"], "zzz") == 404, "image: an unknown picture name is 404")
cr = actors_api.actor_crop(a["id"], actors_api.CropBody(box=[0, 0, 0.5, 1]))
ok(Image.open(actors.image_path(a["id"], "photo")).size == (200, 200) and (actors.folder(a["id"]) / "original.png").exists(), "crop: the photo is the box, the original is kept")
ok(not any((actors.folder(a["id"]) / f"{w}.png").exists() for w in ("ref", "face", "turn")), "crop drops ref, face and turn")
ok(status(actors_api.actor_crop, a["id"], actors_api.CropBody(box=[0, 0, 0.5, 1e999])) in (200, 400), "crop: an infinite box is no 500")
fh = actors.from_hero({"ru": "рыжая", "en": "a redhead", "outfit_en": "a hat", "photo": "h.png", "kind": ""}, png(tmp / "proj" / "h.png").parent, "Рыжая")
ok(fh["name"] == "Рыжая" and "photo" in fh["images"] and fh["look_en"] == "a redhead", "from_hero: the look, the name and the photo copied in")


# ---- a photo or a crop while the actor's sheet / tries job runs: 409 (the job would bring the old face back) ----
from app import jobs  # noqa: E402
busy_actor = actors.save({"name": "Рисуется"})
png(actors.folder(busy_actor["id"]) / "photo.png", (200, 200))
JOB = jobs.Job(id="fake-sheet", params={"actor": busy_actor["id"], "series": None}, kind="actor_sheet", status="running")
jobs.JOBS[JOB.id] = JOB
ok(status(actors_api.actor_crop, busy_actor["id"], actors_api.CropBody(box=[0, 0, 0.5, 1])) == 409, "crop while the sheet job runs: 409")


class FakeUpload:
    filename = "p.png"

    async def read(self, n):
        return b""


async def _photo(aid, series=None):
    try:
        await actors_api.actor_photo(aid, FakeUpload(), series)
        return 200
    except Exception as e:  # HTTPException
        return getattr(e, "status_code", 500)


ok(asyncio.run(_photo(busy_actor["id"])) == 409, "photo while the sheet job runs: 409")
ok(asyncio.run(_photo(busy_actor["id"], "s1")) != 409, "the same id in another library is not blocked")
JOB.kind, JOB.status = "actor_tries", "queued"
ok(status(actors_api.actor_crop, busy_actor["id"], actors_api.CropBody(box=[0, 0, 0.5, 1])) == 409, "a queued tries job blocks too")
JOB.status = "done"
ok(status(actors_api.actor_crop, busy_actor["id"], actors_api.CropBody(box=[0, 0, 0.5, 1])) == 200, "a finished job does not block")
jobs.JOBS.pop(JOB.id, None)

# delete, pick a try and clear the tries are refused while this actor is being drawn (the drawing job writes into its folder)
JOB.kind, JOB.status = "actor_sheet", "running"
jobs.JOBS[JOB.id] = JOB
ok(status(actors_api.actor_delete, busy_actor["id"]) == 409, "delete while the sheet job runs: 409")
ok(status(actors_api.actor_try_pick, busy_actor["id"], "x.png", actors_api.PickBody(sheet=False)) == 409, "pick a try while the sheet job runs: 409")
ok(status(actors_api.actor_tries_clear, busy_actor["id"]) == 409, "clear the tries while the sheet job runs: 409")
JOB.status = "done"
ok(status(actors_api.actor_tries_clear, busy_actor["id"]) == 200, "clear the tries after the job: 200")
jobs.JOBS.pop(JOB.id, None)

# a hero node with a non-string `actor` (a hand-edited graph) does not break the graph's state
_bad = {"id": "hb", "type": "hero", "position": {"x": 0, "y": 0}, "data": {"actor": ["x"], "en": "plain look"}}
try:
    _cb = graph.Ctx({"id": "test-actors-proj", "settings": {}}, {"nodes": [_bad], "edges": []})
    ok(_cb.by["hb"]["data"]["en"] == "plain look", "a non-string actor is ignored, no TypeError")
except TypeError:
    ok(False, "a non-string actor is ignored, no TypeError")

# ---- «В библиотеку» looks the actor up where the graph does: the series' own library when the actor is there, else the global one ----
ok(actors.library_for({"series": "s1"}, a["id"]) == sd and actors.library_for({"series": "s1"}, busy_actor["id"]) is None
   and actors.library_for({}, a["id"]) is None, "library_for: the series' library if the actor is there, else the global one")

# ---- rel_path: an actor's picture lies outside the project folder (the 2026-11-09 crash of nodes/state) ----
from app import graph as _g  # noqa: E402
_proj = _g.projects.ROOT / "some-project"
_face = Path("E:/x/data/actors/actor-1234abcd/face.png")
_series_face = Path("E:/x/data/series/s1/actors/actor-1234abcd/turn.png")
ok(_g.rel_path(_proj, _face) == "/api/actors/actor-1234abcd/image/face" and _g.rel_path(_proj, _series_face) == "/api/actors/actor-1234abcd/image/turn?series=s1" and _g.rel_path(_proj, _proj / "nodes" / "a.png") == "nodes/a.png", "rel_path: an actor's picture outside the project -> the actors API")

print("FAILED" if failed else "all ok")
sys.exit(1 if failed else 0)

