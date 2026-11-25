"""The «Сценарий» node (app/screenplay.py, graph.expand_screenplay) without a GPU or an LLM: the parser (names, remarks,
actions, scenes, strangers), the shots (one speaker each, the listener, the length from the words), «Развернуть в шоты»
(nodes, faces, montage order, again without duplicates), subtitles, «Написать сценарий» and «Добавить в "Ранее"" with a
stand-in writer, the two templates.

    .venv\\Scripts\\python.exe tools\\test_screenplay.py
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
from app import graph, graph_api, graph_io, jobs, projects, screenplay as sp  # noqa: E402
from app.llm import client as llm, writer  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


CAST = [{"name": "Маша", "gender": "female"}, {"name": "Иван", "gender": "male"}]
TEXT = """СЦЕНА 1. Берег моря, закат.
ОН (тихо): Ты замёрзла?
ОНА (с улыбкой): Нет. Мне хорошо.
— Она кладёт голову ему на плечо.
СЦЕНА 2. Причал, ночь.
ОНА (иронично): Ты правда уезжаешь завтра?
ПРОХОЖИЙ: Простите, не подскажете время?
Он молча смотрит на воду.
"""


def parser() -> None:
    print("the parser")
    p = sp.parse(TEXT, CAST)
    ok([s["place"] for s in p["scenes"]] == ["Берег моря, закат", "Причал, ночь"], "scenes and places")
    b = p["beats"]
    ok([x["kind"] for x in b] == ["line", "line", "action", "line", "line", "action"], "lines and actions in order")
    ok(b[0]["cast"] == 1 and b[1]["cast"] == 0, "ОН -> the man, ОНА -> the woman (by gender)")
    ok(b[0]["how"] == "soft" and b[1]["how"] == "smile", "remarks -> HOW keys")
    ok(b[3]["how"] == "" and b[3]["manner"] == "иронично", "an unknown remark stays as a free manner")
    ok(b[4]["cast"] is None and p["unknown"] == ["ПРОХОЖИЙ"], "a name no hero has: unknown")
    ok(b[2]["text"] == "Она кладёт голову ему на плечо." and b[5]["text"] == "Он молча смотрит на воду.", "«—» and a bare sentence are actions")
    n = sp.parse("МАША: Привет!\nИВАН: Здравствуй.\nмаша (шёпотом): Тсс.", CAST)
    ok([x["cast"] for x in n["beats"]] == [0, 1, 0] and n["beats"][2]["how"] == "whisper", "names by the hero's name, case-insensitive")
    o = sp.parse("КОТ: Мяу.\nПЁС: Гав.\nЛИСА: Тяф.", CAST)
    ok([x["cast"] for x in o["beats"]] == [0, 1, None] and o["unknown"] == ["ЛИСА"], "unknown names take the cast in order, then are strangers")
    ok(sp.parse("Примечание: это не реплика.", CAST)["beats"][0]["kind"] == "action", "«Примечание: …» is not a line")
    ok(sp.parse("ОН: Привет", CAST)["scenes"] == [{"n": 1, "place": ""}], "no «СЦЕНА»: one scene without a place")
    ok(sp.how_of("со страхом")[0] == "scared" and sp.how_of("Angry")[0] == "angry" and sp.how_of("")[0] == "", "remarks in Russian and English")


def shots() -> None:
    print("the shots")
    sh = sp.shots(sp.parse(TEXT, CAST), CAST)
    ok(len(sh) == 6 and [s["i"] for s in sh] == list(range(6)), "a shot per line and action")
    l0, l1, a2 = sh[0], sh[1], sh[2]
    ok(l0["speaker"] == 1 and l0["listener"] == 0 and l0["faces"] == [1], "one speaker, the listener; only the speaker's face (the listener from behind)")
    ok(l1["speaker"] == 0 and l1["listener"] == 1 and l1["camera"] == "close" and l0["gaze"] == "right" and l1["gaze"] == "left", "the answer: the other speaks alone in the frame; the opener looks right, the other left")
    ok(a2["kind"] == "action" and a2["speaker"] is None and a2["seconds"] == sp.ACTION_SHOT and set(a2["faces"]) == {0, 1}, "an action: nobody speaks, both in the shot, ACTION_SHOT s")
    ok(sp.shot_seconds("Да") == 3 and sp.shot_seconds("слово " * 5) == 3 and sp.shot_seconds("слово " * 10) == 5 and sp.shot_seconds("слово " * 80) == 10,
       "length: 2.5 words/s + 1 s, from 3 to 10 s")
    ok(sh[4]["speaker"] is None and sh[4]["faces"] == [0], "a stranger speaks: no cast speaker")
    solo = sp.shots(sp.parse("МАША: Привет.", CAST[:1]), CAST[:1])
    ok(solo[0]["listener"] is None and solo[0]["camera"] == "close", "alone: a close-up, no listener")

    text, lines = sp.prompt_of(l0, CAST, {0: {"en": "a woman with a red braid"}, 1: {"en": "a man in a coat", "outfit_en": "a grey coat"}}, [0, 1], {"Берег моря, закат": "A seashore at sunset"})
    ok(lines == [{"who": "Character 2", "text": "Ты замёрзла?", "how": "soft"}], "the prompt's one line, its speaker named as the lock names him")
    ok("Only Character 2 speaks." in text and "alone in the frame, nobody else in the shot" in text and "over-the-shoulder" not in text, "shot / reverse shot: the speaker alone, «Only X speaks»")
    ok("Character 2 is the person in <Picture 1>" in text and "<Picture 2>" not in text and "Character 1" not in text and "looks just past the camera lens, slightly to the right" in text and "other person" not in text, "the speaker is <Picture 1>; the listener off-screen, not named")
    ok("Scene: A seashore at sunset." in text and "Timeline:" in text and "No text, subtitles" in text, "place from the writer's English, a timeline, the tail")
    woven = main.prompts.weave_lines(text, lines, 3) if hasattr(main, "prompts") else None
    if woven:
        ok('Character 2 says softly, in Russian: "Ты замёрзла?"' in woven, "the studio weaves the line into the timeline")
    t2, l2 = sp.prompt_of(a2, CAST, {}, [], {})
    ok(l2 == [] and "Nobody speaks" in t2, "an action has no lines: «Nobody speaks»")

    ok(sp.srt_time(3661.5) == "01:01:01,500", "srt time")
    s = sp.srt(sh)
    ok(s.startswith("1\n00:00:01,000 --> 00:00:03,000\nТы замёрзла?") and s.count(" --> ") == 4, "subtitles: the lines only, from a second into their shot")
    ok("00:00:04,000 --> 00:00:06,000" in s or "00:00:04,000 --> 00:00:07,000" in s, "the second line starts after the first shot")
    text, tr = sp.render({"scenes": [{"place": "Кухня", "place_en": "A kitchen", "items": [{"who": 1, "text": "Привет", "how": "angry", "en": ""},
                                                                                             {"who": 0, "text": "Он уходит.", "how": "plain", "en": "He leaves."}]}]}, ["Маша"])
    ok(text == "СЦЕНА 1. Кухня.\nМАША (сердито): Привет\n— Он уходит." and tr == {"Кухня": "A kitchen", "Он уходит.": "He leaves."}, "render: the LLM's JSON -> the text and the translation table")
    again = sp.parse(text, [{"name": "Маша", "gender": "female"}])
    ok(again["beats"][0]["how"] == "angry", "the rendered text parses back")


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


class FakeSession:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return SimpleNamespace(model=SimpleNamespace(id="stand-in.gguf", name="stand-in", mmproj=None))

    async def __aexit__(self, *a):
        return False


def _job() -> jobs.Job:
    j = jobs.Job(id="t-sp", params={}, kind="graph-llm", status="running", steps=0)
    j.started = __import__("time").time()
    return j


def templates() -> None:
    print("the templates")
    for tid, look in (("series-episode", None), ("series-cartoon", "cartoon3d")):
        ru = json.loads((graph_io.BUILTIN_TEMPLATES / f"{tid}.json").read_text(encoding="utf-8"))
        en = json.loads((graph_io.BUILTIN_TEMPLATES / "en" / f"{tid}.json").read_text(encoding="utf-8"))
        ok(any(t["id"] == tid for t in graph_io.templates()), f"{tid} is listed")
        ok([(n["id"], n["type"]) for n in ru["nodes"]] == [(n["id"], n["type"]) for n in en["nodes"]] and ru["edges"] == en["edges"], f"{tid}: the English twin has the same nodes and wires")
        types = [n["type"] for n in ru["nodes"]]
        ok(types.count("hero") == 2 and {"series", "screenplay", "idea", "note"} <= set(types) and "scene" not in types, f"{tid}: a series, an idea, two heroes, a screenplay, nothing else")
        ok(sorted(e["id"] for e in graph.clean({"nodes": ru["nodes"], "edges": ru["edges"]})["edges"]) == sorted(e["id"] for e in ru["edges"]), f"{tid}: every wire is between existing ports")
        sv = next(n for n in ru["nodes"] if n["type"] == "series")["data"]
        ok((sv.get("look") or None) == look, f"{tid}: the bible's look {look}")
        pl = next(n for n in ru["nodes"] if n["type"] == "screenplay")["data"]["text"]
        heroes = [{"name": n["data"]["title"], "gender": n["data"].get("gender")} for n in ru["nodes"] if n["type"] == "hero"]
        parsed = sp.parse(pl, heroes)
        ok(not parsed["unknown"] and len(sp.shots(parsed, heroes)) >= 4, f"{tid}: the sample parses, every speaker is a hero")


def writer_language() -> None:
    print("the writer's language")
    from app import i18n

    seen_lang: list[str] = []

    class Client:   # the stand-in model: notes the language the writer set (a contextvar, read inside the task)
        async def chat_json(self, *a, **kw):
            seen_lang.append(llm.lang())
            return {"scenes": [], "recap": "x"}
    pt = Patch()
    try:
        pt(i18n, "text_name", lambda code=None: "English")
        asyncio.run(writer.screenplay_for(Client(), "an idea", [{"name": "Anna", "gender": "female", "look": ""}], "", 30, 1))
        ok(seen_lang == ["English"], "screenplay_for asks the writer for the texts' language")
        asyncio.run(writer.recap_for(Client(), "text", "", 1))
        ok(seen_lang == ["English", "English"], "recap_for asks the writer for the texts' language")
    finally:
        pt.undo()


def expansion() -> None:
    print("«Развернуть в шоты»")
    pt = Patch()
    pids = []
    seen: dict = {}

    async def fake_screenplay(client, idea, cast, series, seconds, seed):
        seen.update(idea=idea, cast=cast, series=series)
        return {"title": "Серия", "scenes": [{"place": "Кухня", "place_en": "A kitchen", "items": [
            {"who": 1, "text": "Привет, как дела", "how": "plain", "en": ""}, {"who": 2, "text": "Нормально", "how": "soft", "en": ""},
            {"who": 0, "text": "Они пьют чай.", "how": "plain", "en": "They drink tea."}]}]}

    async def fake_recap(client, screenplay, series, seed):
        seen["recap_series"] = series
        return "Они поговорили на кухне."
    pt(writer, "screenplay_for", fake_screenplay)
    pt(writer, "recap_for", fake_recap)
    pt(llm, "session", FakeSession)
    try:
        t = next(x for x in graph_io.templates() if x["id"] == "series-cartoon")
        proj = graph_io.new_project("Серия", "16:9", g=graph_api._fresh_ids({"nodes": t["nodes"], "edges": t["edges"]}))
        pid = proj["id"]
        pids.append(pid)
        g = graph.load(pid)
        spn = next(n for n in g["nodes"] if n["type"] == "screenplay")["id"]
        heroes = sorted((n for n in g["nodes"] if n["type"] == "hero"), key=lambda n: n["position"]["y"])
        svn = next(n for n in g["nodes"] if n["type"] == "series")
        ok(graph.evaluate_node(graph.Ctx(projects.load(pid), g), spn).state == "ready", "the screenplay with a sample text is ready")
        ok("Вид: 3D-мультфильм" in graph.series_text(svn["data"]), "the bible's text names the look")

        print("the heroes: Маша has a photo, Мурзик none")

        def photo(gg):
            graph.node(gg, heroes[0]["id"])["data"]["photo"] = "masha.png"
        (projects.folder(pid) / "masha.png").write_bytes(b"x")
        graph.update(pid, photo)
        graph.expand(pid, spn)
        g = graph.load(pid)
        c = graph.Ctx(projects.load(pid), g)
        scenes = sorted((n for n in g["nodes"] if n["type"] == "scene"), key=lambda n: n["data"]["scene"])
        prompts_ = sorted((n for n in g["nodes"] if n["type"] == "prompt"), key=lambda n: n["data"]["scene"])
        ok(len(scenes) == len(prompts_) == 5, f"a Prompt and a Scene per line and action ({len(scenes)})")
        ok(all([s for s, _ in c.inputs(sc["id"], "prompt")] == [pn["id"]] for sc, pn in zip(scenes, prompts_)), "each scene's prompt is its own")
        ok(all(len(pn["data"]["lines"]) == (1 if pn["data"]["lines"] else 0) for pn in prompts_) and [len(pn["data"]["lines"]) for pn in prompts_] == [1, 1, 0, 1, 1], "one line per shot at most")
        ok(prompts_[0]["data"]["lines"][0]["who"] == "Character 1" and "Only Character 1 speaks." in prompts_[0]["data"]["text"],
           "shot 1: Маша speaks, Мурзик listens")
        faces = [[s for s, _ in c.inputs(sc["id"], "faces")] for sc in scenes]
        ok(faces[0] == [heroes[0]["id"]] and faces[1] == [] and faces[2] == [] and faces[3] == [heroes[0]["id"]], "faces: only the speaker with a photo is wired (her picture; the cat has none)")
        ok("Character 1 is the person in <Picture 1>" in prompts_[0]["data"]["text"] and "<Picture 2>" not in prompts_[0]["data"]["text"], "<Picture N> only for wired faces")
        ok("Character 2" not in prompts_[0]["data"]["text"] and "cat" not in prompts_[0]["data"]["text"], "the listener stays off-screen: not in her shot")
        ok(all(sc["data"].get("look") == "cartoon3d" for sc in scenes), "every scene has the bible's look")
        ok([sc["data"]["seconds"] for sc in scenes] == [sp.shot_seconds(t) for t in ("Ты опять съел весь сыр?", "Это был не я.")] + [sp.ACTION_SHOT] + [sp.shot_seconds("Тогда откуда крошки на усах?"), sp.shot_seconds("Это... от сухарика.")],
           "the shot lengths come from the words")
        mon = next(n for n in g["nodes"] if n["type"] == "montage")
        ok(mon["data"]["order"] == [s["id"] for s in scenes] and len(c.inputs(mon["id"], "clips")) == 5, "all shots in the montage, in order")
        out = [n for n in g["nodes"] if n["type"] == "output"]
        ok(len(out) == 1 and [e for e in g["edges"] if e["source"] == mon["id"] and e["target"] == out[0]["id"]], "an output after the montage")

        # both heroes with a photo: the speaker's picture is first
        def photo2(gg):
            graph.node(gg, heroes[1]["id"])["data"]["photo"] = "murzik.png"
        (projects.folder(pid) / "murzik.png").write_bytes(b"x")
        graph.update(pid, photo2)
        ids_before = sorted(n["id"] for n in graph.load(pid)["nodes"])
        graph.expand(pid, spn)
        g = graph.load(pid)
        c = graph.Ctx(projects.load(pid), g)
        scenes = sorted((n for n in g["nodes"] if n["type"] == "scene"), key=lambda n: n["data"]["scene"])
        ok(sorted(n["id"] for n in g["nodes"]) == ids_before, "expanded again: the same nodes, no duplicates")
        f1 = [s for s, _ in c.inputs(scenes[1]["id"], "faces")]
        ok(f1 == [heroes[1]["id"]], "the cat answers: only his picture")
        p1 = next(n for n in g["nodes"] if n["type"] == "prompt" and n["data"]["scene"] == 1)
        ok("Character 2 is the person in <Picture 1>" in p1["data"]["text"] and "<Picture 2>" not in p1["data"]["text"] and "alone in the frame" in p1["data"]["text"], "and the prompt says so")

        def shorten(gg):
            graph.node(gg, spn)["data"]["text"] = "СЦЕНА 1. Кухня.\nМАША: Привет.\nМУРЗИК: Мяу."
        graph.update(pid, shorten)
        graph.expand(pid, spn)
        g = graph.load(pid)
        ok(sum(1 for n in g["nodes"] if n["type"] == "scene") == 2 and sum(1 for n in g["nodes"] if n["type"] == "prompt") == 2, "a shorter screenplay: the extra shots go away")
        mon = next(n for n in g["nodes"] if n["type"] == "montage")
        ok(len(mon["data"]["order"]) == 2 and len([e for e in g["edges"] if e["target"] == mon["id"]]) == 2, "and leave the montage")
        ok(graph.screenplay_srt(pid, spn).count(" --> ") == 2, "srt of the expanded shots")
        try:
            graph.node(graph.load(pid), spn)
            graph.update(pid, lambda gg: graph.node(gg, spn)["data"].update(text="  "))
            graph.expand(pid, spn)
            ok(False, "an empty screenplay is refused")
        except ValueError:
            ok(True, "an empty screenplay is refused")

        print("«Написать сценарий» and «Добавить в Ранее»")
        graph.update(pid, lambda gg: graph.node(gg, spn)["data"].update(text=""))
        asyncio.run(graph.run_llm(_job(), pid, [spn], None))
        g = graph.load(pid)
        w = graph.node(g, spn)
        ok(w["data"]["text"].startswith("СЦЕНА 1. Кухня.\nМАША: Привет, как дела\nМУРЗИК (тихо): Нормально\n— Они пьют чай."), f"the written text: {w['data']['text'][:50]!r}")
        ok(w["data"]["tr"] == {"Кухня": "A kitchen", "Они пьют чай.": "They drink tea."}, "the English of the places and actions is kept")
        ok([c["name"] for c in seen["cast"]] == ["Маша", "Мурзик"] and "Название: Маша и Мурзик" in seen["series"] and seen["idea"], "the writer gets the heroes, the bible and the idea")
        graph.expand(pid, spn)
        pn = next(n for n in graph.load(pid)["nodes"] if n["type"] == "prompt" and n["data"]["scene"] == 2)
        ok("They drink tea." in pn["data"]["text"], "an action's English goes into the shot's prompt")
        asyncio.run(graph.run_llm(_job(), pid, [spn], None, "recap"))
        sv = graph.node(graph.load(pid), svn["id"])["data"]["recap"]
        ok(sv == "Они поговорили на кухне.", "«Ранее» got the episode's summary")
        j = _job()
        r = asyncio.run(graph.run_llm(j, pid, [spn], None, "recap"))
        ok(spn in r["errors"] and graph.node(graph.load(pid), svn["id"])["data"]["recap"] == sv, "the same screenplay is not added twice")
    finally:
        pt.undo()
        for p in pids:
            projects.remove(p)


def subjects_and_style() -> None:
    print("who is in an action, the series' style")
    pair = [{"name": "Она", "gender": "female"}, {"name": "Он", "gender": "male"}]   # the heroes are named «Она» and «Он»
    ok(sp.mentioned("Они медленно идут вдоль кромки воды.", pair) == [] and sp.plural("Они медленно идут вдоль кромки воды."), "«Они» is not «Он»: no hero named, a plural subject")
    ok(sp.mentioned("Она кладёт голову ему на плечо.", pair) == [0, 1], "«Она … ему»: both, in order of the text")
    ok(sp.mentioned("Маша смотрит на Ивана.", CAST) == [0, 1] and sp.mentioned("Машу обнимает Иван.", CAST) == [0, 1], "names by stem, any case")
    text = "\n".join(["СЦЕНА 1. Берег моря, закат.", "ОН: Ты не замёрзла?", "ОНА: Нет.", "— Они медленно идут вдоль кромки воды.", "— Оба смеются.",
                      "— Маша смотрит на море.", "— Тишина."])
    sh = sp.shots(sp.parse(text, pair), pair)
    ok(set(sh[2]["faces"]) == {0, 1} and set(sh[3]["faces"]) == {0, 1}, "«Они…» and «Оба…»: both heroes in the shot")
    ok(sh[5]["faces"] == [0, 1] or set(sh[5]["faces"]) == {0, 1}, "no subject: every hero of the scene")
    ok(sh[0]["speaker"] == 1 and sh[0]["faces"][0] == 1, "a line's speaker stays the speaker, first in the shot")
    alone = sp.shots(sp.parse("— Они идут.", pair), pair)
    ok(set(alone[0]["faces"]) == {0, 1}, "«Они» in a scene where nobody has spoken yet: the whole cast")
    ok(sp.style_line(None) == "Realistic live-action cinematic look", "no series look: the neutral live-action look")
    ok(sp.style_line("cartoon3d").startswith(sp.looks.LOOKS["cartoon3d"]["style_en"].rstrip(".")), "a look: its style_en")
    ok(sp.style_line("cartoon3d", "мягкий свет", {"мягкий свет": "soft light"}).endswith(", soft light"), "the free style, translated, after the look")
    ok(sp.style_line(None, "мягкий свет") == "Realistic live-action cinematic look" and sp.style_line(None, "soft light") == "Soft light", "a free style stays out until it is English")
    t, _ = sp.prompt_of(sh[0], pair, {}, [], {}, sp.style_line("cartoon3d"))
    ok(t.startswith(sp.looks.LOOKS["cartoon3d"]["style_en"].rstrip(".")), "the style is the first line of the prompt")


def translation() -> None:
    print("the English of places and actions")
    pt = Patch()
    pids = []
    asked: list = []
    broken = {"on": False}

    async def fake_translate(llm_, items, seed=1):
        asked.append(list(items))
        if broken["on"]:
            raise llm.LLMError("no model")
        table = {"Кухня": "A small kitchen in the evening", "Они пьют чай.": "They drink tea.", "мягкий свет": "soft light", "иронично": "ironically"}
        return {t: table.get(t, "Something happens in English") for _, t in items}
    pt(writer, "translate_screenplay", fake_translate)
    pt(llm, "session", FakeSession)
    try:
        t = next(x for x in graph_io.templates() if x["id"] == "series-episode")
        proj = graph_io.new_project("Серия", "16:9", g=graph_api._fresh_ids({"nodes": t["nodes"], "edges": t["edges"]}))
        pid = proj["id"]
        pids.append(pid)
        g = graph.load(pid)
        spn = next(n for n in g["nodes"] if n["type"] == "screenplay")["id"]
        svn = next(n for n in g["nodes"] if n["type"] == "series")["id"]
        heroes = sorted((n for n in g["nodes"] if n["type"] == "hero"), key=lambda n: n["position"]["y"])

        def edit(gg):
            h0, h1 = (h["data"]["title"].upper() for h in heroes)
            graph.node(gg, spn)["data"]["text"] = "\n".join(["СЦЕНА 1. Кухня.", f"{h0} (иронично): Привет.", f"{h1}: Здравствуй.", "— Они пьют чай.", "— Оба смеются."])
            graph.node(gg, spn)["data"]["tr"] = {}
            graph.node(gg, svn)["data"].update(look="", style="мягкий свет")
        graph.update(pid, edit)
        miss = graph.screenplay_missing(pid, spn)
        ok(sorted(x for _, x in miss) == sorted(["Кухня", "Они пьют чай.", "Оба смеются.", "иронично", "мягкий свет"]) and ("place", "Кухня") in miss,
           f"what is missing: the place, both actions, the free remark, the style ({[x for _, x in miss]})")
        j = _job()
        r = asyncio.run(graph.run_llm(j, pid, [spn], None, "expand"))
        ok(not r["errors"] and len(asked) == 1, "«Развернуть» as an LLM action: one translation call")
        g = graph.load(pid)
        tr = graph.node(g, spn)["data"]["tr"]
        ok(tr.get("Кухня") == "A small kitchen in the evening" and tr.get("Они пьют чай.") == "They drink tea.", "the translations are kept in the node")
        pns = sorted((n for n in g["nodes"] if n["type"] == "prompt"), key=lambda n: n["data"]["scene"])
        ok(len(pns) == 4 and not any(sp.russian(n["data"]["text"]) for n in pns), "no Cyrillic in any English prompt")
        ok("Scene: A small kitchen in the evening." in pns[0]["data"]["text"] and "They drink tea." in pns[2]["data"]["text"], "the place and the action in English")
        ok("the manner: ironically" in pns[0]["data"]["text"], "a free remark in English")
        ok(pns[0]["data"]["text"].startswith("Soft light."), "the series' free style first")
        ok(not any(n["data"].get("check") for n in pns), "nothing marked: all translated")
        ok(graph.screenplay_missing(pid, spn) == [], "cached: nothing to translate again")
        edit_again = lambda gg: graph.node(gg, spn)["data"].update(text=graph.node(gg, spn)["data"]["text"] + "\n— Они уходят.")
        graph.update(pid, edit_again)
        ok(graph.screenplay_missing(pid, spn) == [("action", "Они уходят.")], "an added action: only it is asked again")

        print("no translator: the shots are made and marked")
        broken["on"] = True
        graph.update(pid, lambda gg: graph.node(gg, spn)["data"].update(tr={}))
        r = asyncio.run(graph.run_llm(_job(), pid, [spn], None, "expand"))
        g = graph.load(pid)
        pns = sorted((n for n in g["nodes"] if n["type"] == "prompt"), key=lambda n: n["data"]["scene"])
        ok(len(pns) == 5 and pns[2]["data"].get("check") == "translate" and "проверь перевод" in pns[2]["data"]["title"], "the prompt of an untranslated shot says «проверь перевод»")
        ok(pns[1]["data"].get("check") is None or pns[1]["data"].get("check") == "translate", "every shot with a Russian place is marked (the place is untranslated)")
        d = graph.expand_screenplay(pid, spn)
        ok(d["untranslated"] == [1, 2, 3, 4, 5], "the answer lists the shots to check")
    finally:
        pt.undo()
        for p in pids:
            projects.remove(p)


def late_arrival():
    """A heroine alone in the street, the hero comes in three beats later: her lines before he appears have no listener."""
    text = """СЦЕНА 1. Улица, вечер.
— Маша идёт по брусчатке и смотрит на небо.
МАША (с улыбкой): Только не сейчас… Я же без зонта.
— Начинается дождь, Маша прячется под козырёк.
ИВАН (с улыбкой): Кажется, вам нужен зонт.
МАША: Кажется, да.
"""
    sh = sp.shots(sp.parse(text, CAST), CAST)
    lines = [x for x in sh if x["kind"] == "line"]
    ok(lines[0]["speaker"] == 0 and lines[0]["listener"] is None and lines[0]["camera"] == "close",
       "late arrival: her line before he comes - a close-up, nobody behind her shoulder")
    ok(lines[1]["speaker"] == 1 and lines[1]["listener"] == 0 and lines[2]["listener"] == 1, "once he is there they listen to each other")
    # the camera moves (2026-11-10): no «static camera», a scene opens on a wide establishing move
    looks_en = {0: {"en": "a woman"}, 1: {"en": "a man"}}
    texts = [sp.prompt_of(x, CAST, looks_en, [0, 1], {"Улица, вечер": "A street at evening"})[0] for x in sh]
    ok(sh[0]["opening"] and not any(x["opening"] for x in sh[1:]), "the scene's first shot is its opening")
    ok("wide establishing shot" in texts[0] and all("static camera" not in t for t in texts)
       and any(m in texts[2] for m in sp.ACTION_MOVES) and any(m in texts[1] for m in sp.LINE_MOVES),
       "every shot moves: an establishing move, an action move, a line's gentle move")


def scene_words_and_names():
    ok(sp.SCENE_RE.match("Сценарист входит в комнату.") is None and sp.SCENE_RE.match("Scenery changes slowly.") is None, "«Сценарист», «Scenery» are not scene headers")
    ok(sp.SCENE_RE.match("СЦЕНА 2. Кухня").group(2) == "Кухня" and sp.SCENE_RE.match("Scene 3: Kitchen").group(1) == "3" and sp.SCENE_RE.match("СЦЕНА 4").group(1) == "4", "real scene headers still match")
    ok(sp.SCENE_RE.match("СЦЕНА1. Кухня").group(1) == "1" and sp.SCENE_RE.match("SCENE1: x").group(2) == "x", "a number right after the word is a header: «СЦЕНА1», «SCENE1»")
    # an English screenplay: English remarks, read back by the parser (every HOW key)
    from app import i18n
    real = i18n.get
    i18n.get = lambda: {**real(), "text": "en"}
    try:
        data = {"scenes": [{"place": "Kitchen", "place_en": "", "items": [{"who": 1, "text": "Hi", "how": k, "en": ""} for k in sp.prompts.HOW if k]}]}
        text_en, _ = sp.render(data, ["Anna"])
    finally:
        i18n.get = real
    ok(text_en.startswith("SCENE 1. Kitchen.") and not any("\u0400" <= c <= "\u04ff" for c in text_en), "English text: English remarks, no Russian ones")
    back = sp.parse(text_en, [{"name": "Anna", "gender": "female"}])
    ok([b["how"] for b in back["beats"]] == [k for k in sp.prompts.HOW if k], "English remarks parse back to the same HOW keys")
    p = sp.parse("Сценарист входит в комнату.", CAST)
    ok(len(p["scenes"]) == 1 and p["scenes"][0]["place"] == "" and p["beats"][0]["kind"] == "action", "«Сценарист входит» is an action")
    # hero names that LINE_RE can't read back
    names = ["2B", "Очень длинное имя героя которое не влезает в тридцать девять знаков", "Мистер: Икс", "Маша"]
    data = {"scenes": [{"place": "Кухня", "items": [{"who": k + 1, "text": f"Реплика {k + 1}"} for k in range(4)]}]}
    text, _ = sp.render(data, names)
    cast = [{"name": n, "gender": ""} for n in names]
    beats = sp.parse(text, cast)["beats"]
    ok([b["kind"] for b in beats] == ["line"] * 4 and [b["cast"] for b in beats] == [0, 1, 2, 3], "render -> parse: every hero is read back as the right hero")
    ok([b["text"] for b in beats] == ["Реплика 1", "Реплика 2", "Реплика 3", "Реплика 4"], "the lines' texts are not mangled")
    # the car's «him» / «her» / «them»
    for g, want in (("male", "him"), ("female", "her"), ("", "them")):
        c = [{"name": "Игорь", "gender": g}]
        sh = sp.shots(sp.parse("СЦЕНА 1. Шоссе.\n— Игорь стоит у чёрного маслкара.", c), c)
        t = sp.prompt_of(sh[0], c, {0: {"en": "a driver"}}, [0])[0]
        ok(sh[0]["vehicle"] and not sh[0]["in_car"] and (f"{want} " in t or f" {want}." in t or f" {want}," in t), f"by the car: gender {g!r} -> «{want}»")
    ok(sp.BY_CAR.count("{them}") >= 1, "BY_CAR keeps its {them} slot")


def cars():
    """«Полный газ: Рио» (2026-11-10): a car with no hero named had the heroine on the highway; a hero at the wheel spoke from the road."""
    text = """СЦЕНА 1. Ночное шоссе.
— Маша сидит за рулём чёрного маслкара, двигатель ревёт.
МАША: Держись.
— Чёрный маслкар проносится между машинами, из-под колёс летят искры.
— Иван выходит на обочину.
"""
    sh = sp.shots(sp.parse(text, CAST), CAST)
    looks_en = {0: {"en": "a woman"}, 1: {"en": "a man"}}
    texts = [sp.prompt_of(x, CAST, looks_en, [0, 1])[0] for x in sh]
    ok(sh[0]["vehicle"] and sh[0]["in_car"] and sh[0]["faces"] == [0] and sp.CAR_PHYSICS in texts[0], "a hero at the wheel: her face, solid cars")
    ok(sh[1]["in_car"] and "seated inside the moving car" in texts[1], "her line comes from the car's seat")
    ok(sh[2]["faces"] == [] and sp.CARS_ONLY in texts[2] and sp.CAR_PHYSICS in texts[2], "a car with no hero named: cars only, nobody on the road")
    ok(not sh[3]["vehicle"] and sh[3]["faces"] == [1], "no car words: an ordinary action")
    ok(not sp.vehicle("Он исчезает (vanish) в тумане"), "«vanish» is not a van")
    ok(sp.in_car("Маша резко ставит внедорожник поперёк моста.") and not sp.in_car("Маша и Иван стоят у машины."),
       "a hero with a car is at its wheel unless the action puts them by it")
    ok("never stands on the road" in texts[0] and "nose first" in texts[0], "in-car action: stays inside; cars drive forward")
    ok("person beside" not in texts[1] and "no passenger" in texts[1] and "no passenger" in texts[0], "alone at the wheel: no passenger drawn")
    t2 = """СЦЕНА 1. Крыша гаража.
— Маша и Иван выходят из чёрного маслкара.
"""
    s2 = sp.shots(sp.parse(t2, CAST), CAST)
    p2 = sp.prompt_of(s2[0], CAST, looks_en, [0, 1], tr={"Маша и Иван выходят из чёрного маслкара.": "Masha and Ivan step out of the black muscle car."})[0]
    ok(not s2[0]["in_car"] and "already stand outside the car" in p2 and "stand by the black" in p2 and "step out" not in p2,
       "getting out of a car: they start out of it, standing by it")


def robots():
    """«Стальные стражи» (2026-11-10): the robot that IS the car was put «inside the car»; a fight of two named robots
    pulled the heroine in."""
    cast = [{"name": "Ника", "gender": "female"}, {"name": "Вольт", "gender": "male", "kind": "robot"},
            {"name": "Крон", "gender": "male", "kind": "robot"}]
    text = """СЦЕНА 1. Ночная улица.
— Ника стоит посреди улицы.
— Белая машина в прыжке собирается в огромного робота Вольта, который приземляется перед Никой.
ВОЛЬТ: Она под моей защитой.
— Вольт и Крон бросаются друг на друга посреди улицы.
"""
    sh = sp.shots(sp.parse(text, cast), cast)
    looks_en = {0: {"en": "a woman"}, 1: {"en": "a robot"}, 2: {"en": "a robot"}}
    texts = [sp.prompt_of(x, cast, looks_en, [0, 1, 2])[0] for x in sh]
    ok(not sh[1]["in_car"] and "stays inside the car" not in texts[1] and "parked" not in texts[1], "a robot from a car is no passenger, no car parked by the heroine")
    ok(not sh[2]["in_car"] and "seated inside the moving car" not in texts[2], "the robot's line is not from a car seat")
    ok(sh[3]["faces"] == [1, 2] and "2 characters" in texts[3], "two named robots fight: only the two, «characters»")


def english_twin() -> None:
    print("the English templates: the same speakers and faces as the Russian ones")
    for tid in ("series-episode", "series-cartoon"):
        runs = {}
        for lang, base in (("ru", graph_io.BUILTIN_TEMPLATES), ("en", graph_io.BUILTIN_TEMPLATES / "en")):
            d = json.loads((base / f"{tid}.json").read_text(encoding="utf-8"))
            heroes = [{"name": n["data"]["title"], "gender": n["data"].get("gender"), "kind": n["data"].get("kind") or "person"}
                      for n in sorted((n for n in d["nodes"] if n["type"] == "hero"), key=lambda n: n["position"]["y"])]
            text = next(n for n in d["nodes"] if n["type"] == "screenplay")["data"]["text"]
            parsed = sp.parse(text, heroes)
            runs[lang] = (text, parsed, sp.shots(parsed, heroes))
        en_text, en_parsed, en_shots = runs["en"]
        ok(not sp.CYRILLIC.search(en_text), f"{tid}: the English screenplay has no Russian in it")
        ok(not en_parsed["unknown"], f"{tid}: every English speaker is a hero")
        ok([(s["kind"], s["speaker"], s["faces"]) for s in en_shots] == [(s["kind"], s["speaker"], s["faces"]) for s in runs["ru"][2]],
           f"{tid}: the same kinds, speakers and faces per shot as the Russian one")
        ok([b.get("how") for b in en_parsed["beats"]] == [b.get("how") for b in runs["ru"][1]["beats"]], f"{tid}: the same remarks")
        ok(any(s["kind"] == "action" and s["faces"] for s in en_shots), f"{tid}: an action line names a hero")


def _cartoon(name: str):
    t = next(x for x in graph_io.templates() if x["id"] == "series-cartoon")
    proj = graph_io.new_project(name, "16:9", g=graph_api._fresh_ids({"nodes": t["nodes"], "edges": t["edges"]}))
    g = graph.load(proj["id"])
    heroes = sorted((n for n in g["nodes"] if n["type"] == "hero"), key=lambda n: n["position"]["y"])
    return proj["id"], next(n for n in g["nodes"] if n["type"] == "screenplay")["id"], heroes


def _faces_of(pid: str, nid: str) -> list[str]:
    return [e["source"] for e in graph.load(pid)["edges"] if e["target"] == nid and e["targetHandle"] == "faces"]


def _scenes(pid: str) -> list[dict]:
    return sorted((n for n in graph.load(pid)["nodes"] if n["type"] == "scene"), key=lambda n: n["data"]["scene"])


def actor_without_picture() -> None:
    print("a hero with an actor that has no picture yet")
    import tempfile
    from app import actors, config
    pt = Patch()
    pids = []
    pt(config, "DATA_DIR", Path(tempfile.mkdtemp(prefix="test_sp_actors_")))
    try:
        pid, spn, heroes = _cartoon("Актёр без фото")
        pids.append(pid)
        a = actors.save({"name": "Новичок", "look_en": "a young woman"})
        graph.update(pid, lambda gg: graph.node(gg, heroes[0]["id"])["data"].update(actor=a["id"]))
        graph.expand(pid, spn)
        ok(not any(heroes[0]["id"] in _faces_of(pid, s["id"]) for s in _scenes(pid)), "no faces edge from a hero whose actor has no picture")
        pn = next(n for n in graph.load(pid)["nodes"] if n["type"] == "prompt" and n["data"]["scene"] == 0)
        ok("<Picture" not in pn["data"]["text"], "and the prompt names no <Picture N>")
        # the actor's face panel appears: the hero has a picture, the shots get the edge
        png = actors.image_path(a["id"], "face")
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(b"x")
        graph.expand(pid, spn, "replace")
        ok(heroes[0]["id"] in _faces_of(pid, _scenes(pid)[0]["id"]), "with a face panel the speaker is wired")
        # a photo file that is missing is no picture either
        actors.delete(a["id"])
        graph.update(pid, lambda gg: graph.node(gg, heroes[0]["id"])["data"].update(photo="gone.png"))
        graph.expand(pid, spn, "replace")
        ok(not any(heroes[0]["id"] in _faces_of(pid, s["id"]) for s in _scenes(pid)), "a deleted actor and a missing photo file: no picture")
    finally:
        pt.undo()
        for p in pids:
            projects.remove(p)


def reexpand_keeps_the_users_work() -> None:
    print("«Развернуть в шоты» again: what the user did stays theirs")
    pids = []
    try:
        pid, spn, heroes = _cartoon("Правки при повторе")
        pids.append(pid)
        orig = graph.node(graph.load(pid), spn)["data"]["text"]
        (projects.folder(pid) / "masha.png").write_bytes(b"x")
        graph.update(pid, lambda gg: graph.node(gg, heroes[0]["id"])["data"].update(photo="masha.png"))
        graph.expand(pid, spn)
        g = graph.load(pid)
        pn0 = next(n for n in g["nodes"] if n["type"] == "prompt" and n["data"]["scene"] == 0)
        ok(all(n["data"].get("made") for n in g["nodes"] if n["type"] in ("prompt", "scene")), "the nodes it made carry `made`")
        ok(graph.expand(pid, spn)["kept"] == [], "again with no edits: nothing asked, nothing kept")

        graph.update(pid, lambda gg: graph.node(gg, pn0["id"])["data"].update(text="MY OWN PROMPT"))
        try:
            graph.expand(pid, spn)
            ok(False, "an edited prompt: the default asks (Edited)")
        except graph.Edited as e:
            ok(pn0["data"]["title"] in e.names, f"an edited prompt: the default asks (Edited {e.names})")
        ok(graph.node(graph.load(pid), pn0["id"])["data"]["text"] == "MY OWN PROMPT", "and the refused expand changed nothing")
        r = graph.expand(pid, spn, "keep")
        ok(graph.node(graph.load(pid), pn0["id"])["data"]["text"] == "MY OWN PROMPT" and pn0["data"]["title"] in r["kept"], "«keep»: the user's text stays, the node is listed as kept")
        ok(sum(1 for n in graph.load(pid)["nodes"] if n["type"] == "prompt") == 5, "«keep»: no duplicates")
        graph.update(pid, lambda gg: graph.node(gg, spn)["data"].update(text="СЦЕНА 1. Кухня.\nМАША: Привет.\nМУРЗИК: Мяу."))
        graph.expand(pid, spn, "keep")
        ok((graph.node(graph.load(pid), pn0["id"]) or {"data": {}})["data"].get("text") == "MY OWN PROMPT", "«keep»: an edited shot survives a shorter screenplay")
        graph.update(pid, lambda gg: graph.node(gg, spn)["data"].update(text=orig))
        graph.expand(pid, spn, "replace")
        ok(graph.node(graph.load(pid), pn0["id"])["data"]["text"] != "MY OWN PROMPT", "«replace»: made again from the screenplay")
        ok(graph.expand(pid, spn)["kept"] == [], "and the next default has nothing to ask about")

        # a wire of the user's into a scene's start (a «Картинка» of a frame look) and into its faces
        g = graph.load(pid)
        sc0 = _scenes(pid)[0]
        pic = {"id": "usrpic01", "type": "picture", "position": {"x": 0, "y": 0}, "data": {"prompt": "frame"}}
        g["nodes"].append(pic)
        g["edges"].append({"id": "usr-start", "source": pic["id"], "sourceHandle": "image", "target": sc0["id"], "targetHandle": "start"})
        g["edges"].append({"id": "usr-face", "source": pic["id"], "sourceHandle": "image", "target": sc0["id"], "targetHandle": "faces"})
        graph.save(pid, g, g["rev"])
        graph.expand(pid, spn)
        into = [(e["source"], e["targetHandle"]) for e in graph.load(pid)["edges"] if e["target"] == sc0["id"]]
        ok((pic["id"], "start") in into, "a user's wire into scene.start survives")
        ok((pic["id"], "faces") in into and (heroes[0]["id"], "faces") in into, "a user's face stays beside the writer's")
        ok(_faces_of(pid, sc0["id"])[0] == heroes[0]["id"], "the speaker's own picture is still first")
        ok(sum(1 for s, h in into if h == "prompt") == 1 and sum(1 for s, h in into if s == heroes[0]["id"]) == 1, "one prompt wire, one from the speaker: nothing doubled")
        graph.expand(pid, spn)
        ok((pic["id"], "start") in [(e["source"], e["targetHandle"]) for e in graph.load(pid)["edges"] if e["target"] == sc0["id"]], "and again")
        # a scene made before `wired` existed: the writer's own wires are told by their ends, the user's start stays
        graph.update(pid, lambda gg: [graph.node(gg, s["id"])["data"].pop("wired", None) for s in _scenes(pid)])
        graph.expand(pid, spn)
        into = [(e["source"], e["targetHandle"]) for e in graph.load(pid)["edges"] if e["target"] == sc0["id"]]
        ok((pic["id"], "start") in into and sum(1 for s, h in into if h == "prompt") == 1, "an older scene: the start stays, no doubled prompt wire")
    finally:
        for p in pids:
            projects.remove(p)


if __name__ == "__main__":
    parser()
    shots()
    templates()
    writer_language()
    expansion()
    subjects_and_style()
    translation()
    late_arrival()
    scene_words_and_names()
    cars()
    robots()
    english_twin()
    actor_without_picture()
    reexpand_keeps_the_users_work()
    print("FAILED: %d" % failed if failed else "all passed")
    sys.exit(1 if failed else 0)
