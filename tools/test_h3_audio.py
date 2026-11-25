"""H3 scenes drawn under a given sound (branch engine/h3-audio) without a GPU: the graph dict of graphs.scene with and
without `audio` (i2v, Ref2VA + start frame, the second pass, a trimmed piece), the old graphs unchanged, the scene's
key, the graph's «Сцена»: the «звук» input and a «Промт» line's own sound, and the lip-motion check of such a shot.

    .venv\\Scripts\\python.exe tools\\test_h3_audio.py
"""
from __future__ import annotations

import itertools
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.main as main  # noqa: E402,F401 - the routes, as the server has them
from app import graph, projects, render  # noqa: E402
from app.engine import graphs  # noqa: E402
from app.planner import prompts  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


def classes(g: dict, cls: str) -> list[str]:
    return [k for k, v in g.items() if v["class_type"] == cls]


def links_valid(g: dict) -> bool:
    return all(v[0] in g for n in g.values() for v in n["inputs"].values() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str))


def graph_shape() -> None:
    print("graphs.scene without audio: the graph as it was")
    for ff, refs, p2 in itertools.product([None, "a.png"], [[], ["r.png"]], [None, (1920, 1088)]):
        g = graphs.scene("x", 960, 544, 121, 5, "p", [], ff, refs, None, p2)
        ok(not classes(g, "LoadAudio") and not classes(g, "TrimAudioDuration") and "aguide" not in g, f"no audio nodes (first={bool(ff)} ref={bool(refs)} pass2={bool(p2)})")
        ok(g[graphs.GUIDER]["inputs"]["conditioning"] == (["guide", 0] if refs and ff else [graphs.H3, 0]), "  the guider reads the plain conditioning")
    ok(json.dumps(graphs.scene("x", 960, 544, 121, 5, "p")) == json.dumps(graphs.scene("x", 960, 544, 121, 5, "p", audio=None, audio_from=0.0)), "audio=None is the default")

    print("i2v under a line")
    g = graphs.scene("x", 960, 544, 121, 5, "p", [], "a.png", audio="line.wav")
    ag = g["aguide"]["inputs"]
    ok(g["aguide"]["class_type"] == "MiniMaxH3AddGuide" and ag["positive"] == [graphs.H3, 0] and ag["latent"] == [graphs.H3, 1], "MiniMaxH3AddGuide on H3's conditioning and latent")
    ok(ag["audio_vae"] == [graphs.AVAE, 0] and ag["frame_idx"] == 0 and "vae" not in ag and "image" not in ag, "audio VAE, frame 0, no image")
    ok(g["aguide_load"]["inputs"]["audio"] == "line.wav" and ag["audio"] == ["aguide_load", 0] and not classes(g, "TrimAudioDuration"), "LoadAudio straight in (no trim from 0)")
    ok(g[graphs.GUIDER]["inputs"]["conditioning"] == ["aguide", 0], "the guider reads the audio guide")
    ok(links_valid(g), "every link points at a node")
    ok(g[graphs.VIDEO]["inputs"]["audio"] == [graphs.ADECODE, 0], "the mp4's sound is the decoded audio of the sampler")

    print("a piece of a longer file")
    g = graphs.scene("x", 960, 544, 121, 5, "p", audio="track.mp3", audio_from=12.5)
    t = g["aguide_trim"]["inputs"]
    ok(t["audio"] == ["aguide_load", 0] and t["start_index"] == 12.5 and t["duration"] == round(121 / graphs.FPS, 3), "TrimAudioDuration from 12.5 s for the scene's length")
    ok(g["aguide"]["inputs"]["audio"] == ["aguide_trim", 0] and links_valid(g), "the guide reads the trimmed piece")

    print("Ref2VA + start frame + audio: both guides chained")
    g = graphs.scene("x", 960, 544, 121, 5, "p", [], "a.png", ["r.png"], audio="line.wav")
    ok(g["guide"]["inputs"]["positive"] == [graphs.H3, 0] and "image" in g["guide"]["inputs"], "the start-frame guide on Ref2VA's conditioning")
    ok(g["aguide"]["inputs"]["positive"] == ["guide", 0] and g["aguide"]["inputs"]["latent"] == [graphs.H3, 1], "the audio guide on top of it")
    ok(g[graphs.GUIDER]["inputs"]["conditioning"] == ["aguide", 0], "the guider reads the chain's end")
    g = graphs.scene("x", 960, 544, 121, 5, "p", [], None, ["r.png"], audio="line.wav")
    ok("guide" not in g and g["aguide"]["inputs"]["positive"] == [graphs.H3, 0], "Ref2VA without a start frame: the audio guide alone")

    print("the second pass keeps the sound")
    big = (1920, 1088)
    g = graphs.scene("x", 960, 544, 121, 5, "p", [], None, [], audio="line.wav", pass2=big)
    ok(g["p2guider"]["inputs"]["conditioning"] == ["aguide", 0], "t2v: the second pass is guided by the audio guide too")
    g = graphs.scene("x", 960, 544, 121, 5, "p", [], "a.png", [], audio="line.wav", pass2=big)
    ok(g["p2aguide"]["inputs"]["positive"] == ["p2cond", 0] and g["p2aguide"]["inputs"]["latent"] == ["p2av", 0], "i2v: the new conditioning gets its own audio guide over the re-encoded AV latent")
    ok(g["p2guider"]["inputs"]["conditioning"] == ["p2aguide", 0] and links_valid(g), "  and the guider reads it")
    g = graphs.scene("x", 960, 544, 121, 5, "p", [], "a.png", ["r.png"], audio="line.wav", pass2=big)
    ok(g["p2guider"]["inputs"]["conditioning"] == ["aguide", 0] and "p2aguide" not in g and links_valid(g), "Ref2VA: the pass-1 chain (start frame + audio) is reused")
    ok(g["p2av"]["inputs"]["audio_latent"] == ["p2aenc", 0], "the decoded audio is re-encoded for the second pass")

    print("the TE-ahead part is not touched by the audio")
    a = graphs.te_key(graphs.scene("x", 960, 544, 121, 5, "p"))
    ok(a and a == graphs.te_key(graphs.scene("x", 960, 544, 121, 5, "p", audio="line.wav")), "te_key: the same conditioning key with and without a sound")


def keys() -> None:
    print("render.scene_key")
    base = dict(prompt="x", seed=1, w=960, h=544, length=121, loras=[], start=None)
    k0 = render.scene_key(**base)
    f = ROOT / "tools" / "_h3_audio_a.wav"
    f2 = ROOT / "tools" / "_h3_audio_b.wav"
    f.write_bytes(b"RIFFaaaa")
    f2.write_bytes(b"RIFFbbbb")
    try:
        ok(render.scene_key(**base, audio=None, audio_from=0.0) == k0, "no audio: the key as it was")
        k1 = render.scene_key(**base, audio=f)
        ok(k1 != k0, "a sound changes the key")
        ok(render.scene_key(**base, audio=f2) != k1, "another sound, another key")
        ok(render.scene_key(**base, audio=f, audio_from=3.0) != k1, "another piece of the same file, another key")
        ok(render.scene_key(**base, audio=f, model="ltx25") == render.scene_key(**base, model="ltx25"), "LTX does not take it: its key stays")
    finally:
        f.unlink(missing_ok=True)
        f2.unlink(missing_ok=True)


def lines() -> None:
    print("prompts.clean_line keeps a line's own sound")
    ln = prompts.clean_line({"who": "The woman", "text": "Hello", "audio": "audio_1.wav"})
    ok(ln and ln["audio"] == "audio_1.wav", "the file name is kept")
    ok("audio" not in prompts.clean_line({"who": "The woman", "text": "Hello"}), "a line without one: the dict as it was")
    ok("audio" not in prompts.clean_line({"text": "Hello", "audio": "../secret.wav"}) and "audio" not in prompts.clean_line({"text": "Hello", "audio": "a/b.wav"}), "a path is not a file of the project")
    ok(prompts.weave_lines("A room.", [{"who": "The woman", "text": "Hello", "audio": "x.wav"}]) == prompts.weave_lines("A room.", [{"who": "The woman", "text": "Hello"}]), "the prompt weaves the same with or without it")


def node(i: str, t: str, d: dict) -> dict:
    return {"id": i, "type": t, "position": {"x": 0, "y": 0}, "data": d}


def edge(i: str, a: str, ah: str, b: str, bh: str) -> dict:
    return {"id": i, "source": a, "sourceHandle": ah, "target": b, "targetHandle": bh}


def graph_node() -> None:
    print("the graph's «Сцена»")
    ok(graph.TYPES["scene"]["in"].get("sound") == ("audio", False), "the scene has a «sound» input of type audio")
    ok(graph.TYPES["scene"]["in"].get("voice") == ("audio", False), "«voice» stays for the voice sample / the song")
    proj = projects.create({"quality": "draft", "aspect": "16:9"})
    try:
        fo = projects.folder(proj["id"])
        (fo / "audio_x.wav").write_bytes(b"RIFFxxxx")
        (fo / "audio_y.wav").write_bytes(b"RIFFyyyy")
        (fo / "audio_l.wav").write_bytes(b"RIFFllll")

        def run(nodes: list, edges: list):
            c = graph.Ctx(projects.load(proj["id"]), {"nodes": nodes, "edges": edges})
            return c, graph.evaluate_node(c, "sc")

        pr = node("pr", "prompt", {"text": "A woman at a window, she speaks to the camera.", "seconds": 5})
        sc = node("sc", "scene", {})
        e_pr = edge("e1", "pr", "text", "sc", "prompt")
        c0, a0 = run([pr, sc], [e_pr])
        card, w, h = graph.scene_card(c0, sc)
        ok(card.id == "h3", "the default graph model is H3")
        ok(a0.state in ("todo", "ready"), f"a scene without sound evaluates ({a0.state}{': ' + a0.error if a0.error else ''})")
        plain = render.scene_key(a0.text, graph.seed_of(sc), w, h, graph.videomodels.frames(card, a0.seconds), [], None, [], card.id)
        ok(a0.key == plain, "no sound: the scene's key is the old formula's")

        tk = node("tk", "track", {"file": "audio_x.wav"})
        c1, a1 = run([pr, sc, tk], [e_pr, edge("e2", "tk", "audio", "sc", "sound")])
        ok(a1.key != a0.key, "a «Трек» on «звук» changes the scene's key")
        ok(graph.scene_sound(c1, sc, card)[0] == fo / "audio_x.wav" and graph.scene_sound(c1, sc, card)[1] == 0.0, "scene_sound: the track, from 0")
        kw = graph._scene_kw(c1, "sc", a1)
        ok(kw["audio"] == fo / "audio_x.wav" and kw["audio_from"] == 0.0, "the shot's arguments carry the sound")
        ok("audio" not in graph._scene_kw(c0, "sc", a0), "without a sound the arguments are as they were")
        sc2 = node("sc", "scene", {"sound_from": 4.5})
        c2, a2 = run([pr, sc2, tk], [e_pr, edge("e2", "tk", "audio", "sc", "sound")])
        ok(a2.key not in (a0.key, a1.key) and graph._scene_kw(c2, "sc", a2)["audio_from"] == 4.5, "«sound_from» moves the piece and the key")
        tk2 = node("tk", "track", {"file": "audio_y.wav"})
        c3, a3 = run([pr, sc, tk2], [e_pr, edge("e2", "tk", "audio", "sc", "sound")])
        ok(a3.key != a1.key, "another file, another key")
        c4, a4 = run([pr, sc, tk], [e_pr, edge("e2", "tk", "audio", "sc", "voice")])
        ok(graph.scene_sound(c4, sc, card)[0] is None, "a track on «голос» is not the scene's sound (the voice sample)")

        print("a «Промт» line's own sound")
        one = node("pr", "prompt", {"text": "A woman at a window.", "seconds": 5,
                                     "lines": [{"who": "The woman", "text": "I am here.", "how": "", "audio": "audio_l.wav"}]})
        c5, a5 = run([one, sc], [e_pr])
        ok(graph.scene_sound(c5, sc, card)[0] == fo / "audio_l.wav", "one line with its sound and no «звук»: the scene uses it")
        ok(a5.key != render.scene_key(a5.text, graph.seed_of(sc), w, h, graph.videomodels.frames(card, a5.seconds), [], None, [], card.id), "  and its key has it")
        ok("I am here." in (a5.text or ""), "  the line is woven into the prompt as before")
        c6, a6 = run([one, sc, tk2], [e_pr, edge("e2", "tk", "audio", "sc", "sound")])
        ok(graph.scene_sound(c6, sc, card)[0] == fo / "audio_y.wav", "the «звук» input wins over the line's sound")
        two = node("pr", "prompt", {"text": "A woman at a window.", "seconds": 5,
                                     "lines": [{"who": "The woman", "text": "I am here.", "audio": "audio_l.wav"}, {"who": "The woman", "text": "Hello."}]})
        c7, _ = run([two, sc], [e_pr])
        ok(graph.scene_sound(c7, sc, card)[0] is None, "two lines: no sound is picked (a scene is drawn under one sound)")
        gone = node("pr", "prompt", {"text": "A woman at a window.", "seconds": 5, "lines": [{"who": "The woman", "text": "I am here.", "audio": "nope.wav"}]})
        c8, _ = run([gone, sc], [e_pr])
        ok(graph.scene_sound(c8, sc, card)[0] is None, "a missing file: no sound, the scene shoots as without")
        ltx = node("sc", "scene", {"model": "ltx25"})
        c9 = graph.Ctx(projects.load(proj["id"]), {"nodes": [one, ltx], "edges": [e_pr]})
        ok(graph.scene_sound(c9, ltx, graph.videomodels.card("ltx25")) == (None, 0.0, []), "LTX does not take it")
    finally:
        shutil.rmtree(projects.folder(proj["id"]), ignore_errors=True)


def lips() -> None:
    import struct
    import wave
    from app import checks
    print("checks.audio_lips (the lips' motion in voiced / silent frames)")
    f = ROOT / "tools" / "_h3_audio_tone.wav"
    sr = 16000
    with wave.open(str(f), "wb") as w:   # 2 s of a loud tone, 2 s of silence
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        import math
        w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * 220 * i / sr))) for i in range(2 * sr)) + bytes(4 * sr))
    seen = []
    real = checks.lip_motion
    checks.lip_motion = lambda video, n, voice, fps=24.0: (seen.append(list(voice)) or (0.08 if voice[5] else 0.02))
    try:
        r = checks.audio_lips(Path("x.mp4"), f, 0.0, 96, 24.0)
        ok(r and r["voiced"] == 0.08 and r["silent"] == 0.02 and r["ratio"] == 4.0 and not r["mute"], f"voiced 0.08, silent 0.02: ratio 4 ({r})")
        ok(len(seen) == 2 and sum(seen[0]) in range(44, 50) and sum(seen[1]) == 96 - sum(seen[0]), "the first 2 s are voiced, the rest silent")
        checks.lip_motion = lambda video, n, voice, fps=24.0: 0.01 if voice[5] else 0.02
        ok(checks.audio_lips(Path("x.mp4"), f, 0.0, 96, 24.0)["mute"], "a still mouth in the speech is marked mute")
        checks.lip_motion = lambda video, n, voice, fps=24.0: None
        ok(checks.audio_lips(Path("x.mp4"), f, 0.0, 96, 24.0) is None, "no face: not judged")
        mp4 = ROOT / "tools" / "_h3_audio_shot.mp4"
        checks.save_lips(mp4, {"voiced": 0.08, "silent": 0.02, "ratio": 4.0, "mute": False})
        ok(checks.saved_lips(mp4)["ratio"] == 4.0, "kept next to the shot and read back")
        checks.save_lips(mp4, None)
        ok(checks.saved_lips(mp4) is None, "removed when there is nothing")
    finally:
        checks.lip_motion = real
        f.unlink(missing_ok=True)
        mp4.with_suffix(".lips.json").unlink(missing_ok=True)


def main_() -> None:
    lips()
    graph_shape()
    keys()
    lines()
    graph_node()
    print("FAILED" if failed else "all ok", failed or "")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main_()
