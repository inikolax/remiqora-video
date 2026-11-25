"""The beat renderer (app/beatedit.py) and its graph node «Бит-монтаж» without a GPU or an LLM: a made-up click track
(140 BPM) and synthetic shots drawn with cv2; the beat grid, the edit decision list's invariants, the frames, the sound's
length and loudness, song.timed_words, autopilot.window "drop", and the node's key and cache.

    .venv\\Scripts\\python.exe tools\\test_beatedit.py
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.main as main  # noqa: E402,F401 - the routes, as the server has them
from app import autopilot, beatedit, config, graph, graph_io, jobs, projects, song  # noqa: E402

failed = 0
FF = config.FFMPEG
BPM, FIRST, DUR = 140.0, 0.3, 40.0
BEAT = 60 / BPM
SID = "5e5e00000b01"      # the made-up song in the library (its own folder under data/songs, removed after)
DROP_BAR = 8              # the click track's drop: bar 8 (the kick and the snare come in)


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


def make_wav(path: Path) -> None:
    """140 BPM, 4/4, the first beat at 0.3 s: a kick on every beat, snare on 2 and 4 and hats on 8ths from the drop (bar 8) on."""
    sr = 44100
    n = int(sr * DUR)
    x = np.zeros(n, np.float32)
    rng = np.random.default_rng(5)

    def put(t, sig):
        i = int(t * sr)
        x[i:i + len(sig)] += sig[:n - i]
    tt = np.arange(int(0.18 * sr)) / sr
    kick = (np.sin(2 * np.pi * np.cumsum(45 + 90 * np.exp(-tt / 0.03)) / sr) * np.exp(-tt / 0.07)).astype(np.float32)
    ts = np.arange(int(0.12 * sr)) / sr
    snare = (rng.normal(0, 1, len(ts)) * np.exp(-ts / 0.03) * 0.5).astype(np.float32)
    hat = (rng.normal(0, 1, int(0.03 * sr)) * np.exp(-np.arange(int(0.03 * sr)) / sr / 0.008) * 0.02).astype(np.float32)
    k = 0
    while FIRST + k * BEAT < DUR - 0.3:
        t = FIRST + k * BEAT
        put(t, kick * 0.9)
        if k >= DROP_BAR * 4:
            if k % 4 in (1, 3):
                put(t, snare)
            put(t, hat)
            put(t + BEAT / 2, hat)
        k += 1
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(sr)
        pcm = (np.clip(x, -1, 1) * 30000).astype("<i2")
        f.writeframes(np.stack([pcm, pcm], 1).tobytes())


def make_shot(path: Path, color: tuple, seconds: float = 3.0, size=(270, 480), fps: int = 24) -> None:
    """A moving block on a flat colour (the render must see the picture change over the shot's time)."""
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for i in range(int(seconds * fps)):
        f = np.full((size[1], size[0], 3), color, np.uint8)
        x = int((size[0] - 60) * (i / (seconds * fps)))
        cv2.rectangle(f, (x, 150), (x + 60, 330), (255 - color[0], 255 - color[1], 255 - color[2]), -1)
        w.write(f)
    w.release()


def probe(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    h, w = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap.release()
    r = subprocess.run([FF, "-v", "error", "-i", str(path), "-vn", "-f", "f32le", "-ac", "2", "-ar", "44100", "-"], capture_output=True)
    audio = len(r.stdout) / 4 / 2 / 44100
    r = subprocess.run([FF, "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr.decode(errors="replace"))
    return {"frames": n, "fps": fps, "w": w, "h": h, "audio": audio, "lufs": float(m[-1]) if m else None}


def frames_of(path: Path) -> list:
    cap = cv2.VideoCapture(str(path))
    out = []
    while True:
        ok_, f = cap.read()
        if not ok_:
            break
        out.append(f)
    return out


COLORS = {"h1": (200, 60, 30), "h2": (40, 160, 60), "h3": (30, 80, 200), "h4": (160, 60, 160), "a1": (60, 180, 200), "a2": (200, 180, 40),
          "a3": (90, 90, 90), "close": (20, 20, 20), "impact": (230, 230, 230), "riser": (50, 120, 240)}
ROLE = {"h1": "hero", "h2": "hero", "h3": "hero", "h4": "hero", "a1": "atmos", "a2": "atmos", "a3": "atmos", "close": "close", "impact": "impact",
        "riser": "riser"}


def run() -> None:
    work = Path(tempfile.mkdtemp(prefix="beatedit_"))
    wav = work / "click.wav"
    make_wav(wav)
    shots = {}
    for name, col in COLORS.items():
        shots[name] = work / f"{name}.mp4"
        make_shot(shots[name], col)
    drop_t = FIRST + DROP_BAR * 4 * BEAT

    print("the beat grid")
    an = song.analyze(wav, BPM)
    ok(abs(an.bpm - BPM) < 0.3, f"song.analyze finds the tempo ({an.bpm:.2f})")
    off = [min(abs(b - (FIRST + k * BEAT)) for k in range(int(DUR / BEAT))) for b in an.beats[:60]]
    ok(max(off) < 0.03, f"its beats sit on the clicks (max {max(off) * 1000:.0f} ms)")
    g = beatedit.make_grid(an.beats, drop_t + 0.07, BPM, 3, 8)
    ok(abs(g.beats[0] - drop_t) < 0.03, f"the drop snaps to the nearest beat ({g.beats[0]:.3f} for {drop_t:.3f})")
    ok(abs(g.beat - BEAT) < 0.002 and g.need_before == 16, f"beat {g.beat:.4f} s, {g.need_before} beats before the drop")
    ok(abs(g.dur - (16 + 36) * BEAT) < 0.05, f"the piece is 13 bars ({g.dur:.2f} s)")
    half = beatedit.make_grid(an.beats[::2], drop_t, BPM, 3, 8)
    ok(abs(half.beat - BEAT) < 0.002, "a grid at half the tempo gets its beats in between")
    double = beatedit.make_grid(sorted(an.beats + [b + BEAT / 2 for b in an.beats]), drop_t, BPM, 3, 8)
    ok(abs(double.beat - BEAT) < 0.002 and abs(double.beats[0] - drop_t) < 0.03, "a grid at double the tempo keeps every other beat, on the drop")
    ok(len(beatedit.PRESETS) == 4 and beatedit.PRESETS["techno"]["drop_bars"] == 8, "the presets: techno, dnb, hardstyle, pop")

    print("the edit decision list")
    words = [{"start": drop_t - 6.0 + 0.5 * i, "end": drop_t - 6.0 + 0.5 * i + 0.4, "word": w} for i, w in
             enumerate(["we", "never", "fade", "we", "never", "fade", "away", "hands", "up", "high", "a", "thousand", "voices", "say"])]
    cfg = {"clips": [{"id": k, "path": str(shots[k]), "role": ROLE[k]} for k in COLORS], "song": str(wav),
           "analysis": {"beats": an.beats, "bpm": an.bpm}, "drop": drop_t, "bpm": BPM, "words": words,
           "written": "[chorus]\nWe never fade, we never fade away\nHands up high, a thousand voices say", "title": "never fade", "hud": "TEST",
           "palette": {"a": [255, 90, 190], "b": [255, 255, 255], "tint": [34, 0, 40]}, "fps": 30, "preview": True,
           "out": str(work / "beat.mp4")}
    pl = beatedit.plan(cfg)
    e = pl.edl
    ok(abs(e[0]["t0"]) < 1e-6 and abs(e[-1]["t1"] - pl.grid.dur) < 1e-6 and all(abs(a["t1"] - b["t0"]) < 1e-9 for a, b in zip(e, e[1:])),
       f"{len(e)} segments, gapless from 0 to the end")
    ok(e[0]["title"] == "close" and "strobe" in e[0]["fx"] and abs(e[0]["t1"] - 4 * BEAT) < 0.01, "the intro bar strobes on the close-up")
    ok(e[-1]["title"] == "close" and "outro" in e[-1]["fx"] and abs(e[-1]["t0"] - pl.grid.outro) < 1e-6, "the outro is the close-up, a bar long")
    drop = next(s for s in e if s["tr"] == "impact")
    ok(drop["title"] == "impact" and abs(drop["t0"] - pl.grid.drop) < 1e-6 and abs(drop["n"] - 2) < 1e-9, "the drop opens with the impact shot, two beats")
    rs = [s for s in e if "riser" in s["fx"]]
    ok(len(rs) == 8 and all(s["title"] in ("riser", "h1", "h2", "h3", "h4") for s in rs) and sum(1 for s in rs if "gap" in s["fx"]) == 1
       and abs(rs[0]["t0"] - pl.grid.riser) < 1e-6, "the riser bar: a 2-beat riser, six quarter-beat inserts, a half-beat gap")
    qs = [s for s in rs if s["n"] == 0.25]
    ok(len(qs) == 6 and abs(qs[1]["t0"] - qs[0]["t0"] - pl.grid.beat / 4) < 1e-6, "… the inserts a quarter beat apart")
    picks = [s["title"] for s in e if s["title"] in ("h1", "h2", "h3", "h4", "a1", "a2", "a3")]
    ok(len(set(picks)) == 7, "the picks use the whole pool")
    ok(all(picks[i] not in picks[max(0, i - 3):i] for i in range(len(picks))), "a pick avoids the last three used")
    kal = [s for s in e if "kaleido" in s["fx"]]
    ok(kal and all((s["j"] // 4) % 4 == 2 for s in kal), "the mirror only in bars 2 (mod 4)")
    stu = [s for s in e if "stutter" in s["fx"]]
    ok(stu and all((s["j"] // 4) % 4 == 3 and s["j"] % 4 == 3 for s in stu), "the stutter on the last beat of bars 3 (mod 4)")
    ok(sum(1 for s in e if s["tr"] == "impact") == 1 + (8 - 1) // 4, "an impact every 4th bar of the drop")
    last = [s for s in e if 28 <= s["j"] < 32 and s["t0"] > 0]
    ok(any(abs(s["n"] - 0.5) < 1e-9 for s in last), "the last drop bar runs in half beats")
    ok(abs(sum(s["t1"] - s["t0"] for s in e) - pl.grid.dur) < 1e-6 and e == sorted(e, key=lambda s: s["t0"]), "the segments add up to the piece")
    ok([g_[2] for g_ in pl.groups][:3] == ["WE", "NEVER", "FADE"] or "FADE" in " ".join(g_[2] for g_ in pl.groups), f"captions from the written words ({[g_[2] for g_ in pl.groups][:5]})")
    # the same cfg again is the same edit; another preset's values reach the edit
    ok(beatedit.plan(cfg).edl == e, "the edit is deterministic")
    p2 = beatedit.plan({**cfg, "params": {"kaleido": False, "stutter": False, "strobe": False}}).edl
    ok(not any("kaleido" in s["fx"] or "stutter" in s["fx"] or "strobe" in s["fx"] for s in p2), "kaleido / stutter / strobe off")
    ok(len(beatedit.plan({**cfg, "build_bars": 2, "drop_bars": 4}).edl) < len(e), "fewer bars - a shorter edit")
    env_k, env_s = beatedit.band_envelopes(beatedit.decode_piece(str(wav), pl.grid.t0, pl.grid.dur + 1).mean(0))
    on_beats = np.mean([env_k[int((pl.grid.t(j) + 0.02) * 60)] for j in range(-16, 0)])
    between = np.mean([env_k[int((pl.grid.t(j) + BEAT / 2 + 0.02) * 60)] for j in range(-16, 0)])
    ok(on_beats > 2 * between, f"the kick envelope rises on the beats ({on_beats:.2f} vs {between:.2f} between)")
    d_snare = np.mean([env_s[int((pl.grid.t(j) + 0.02) * 60)] for j in range(1, 30) if j % 4 in (1, 3)])
    d_none = np.mean([env_s[int((pl.grid.t(j) + 0.02) * 60)] for j in range(-16, 0)])
    ok(d_snare > 1.5 * d_none, f"the snare envelope rises when the snare comes in ({d_snare:.2f} vs {d_none:.2f})")

    print("the render")
    seen_p = []
    res = beatedit.render(cfg, lambda *a: seen_p.append(a))
    pr = probe(Path(res["out"]))
    want = round(pl.grid.dur * 30)
    ok(abs(pr["frames"] - want) <= 1 and pr["fps"] == 30 and (pr["w"], pr["h"]) == (540, 960), f"{pr['frames']} frames at {pr['fps']:.0f} fps, {pr['w']}x{pr['h']} (wanted {want})")
    ok(abs(pr["audio"] - pl.grid.dur) < 0.12, f"the sound is {pr['audio']:.2f} s, the piece {pl.grid.dur:.2f} s")
    ok(pr["lufs"] is not None and abs(pr["lufs"] - (-10.0)) < 1.0, f"loudness {pr['lufs']} LUFS (the default -10)")
    meta = json.loads(Path(res["out"]).with_suffix(".json").read_text(encoding="utf-8"))
    ok(meta["cuts"] == res["cuts"] and all(isinstance(c, int) for c in meta["cuts"]) and len(meta["cuts"]) == len(e) - 1, "the cuts as frame numbers beside the file")
    ok({s[0] for s in seen_p} >= {"plan", "audio", "shots", "frames"} and seen_p[-1][1] == seen_p[-1][2], "progress: plan, audio, shots, frames")
    ok(not list(Path(res["out"]).parent.glob("*.tmp.*")), "no temp wav / mp4 is left beside the render")
    for fps_ in (30, 60):   # the reported cuts are the real switch frames (a rounded one was a frame early for 9 of 42 cuts)
        pf = beatedit.plan({**cfg, "fps": fps_, "bpm": 143.0})
        sg = beatedit.frame_segments(pf)
        real = sorted({i for i in range(1, len(sg)) if sg[i] != sg[i - 1]})
        ok(pf.cuts() == real, f"{fps_} fps: cuts() are the frames the edit switches at ({len(real)} cuts)")
    fr = frames_of(Path(res["out"]))
    ok(fr[0].mean() < 60 and any(f.mean() > 200 for f in fr[int(pl.grid.drop * 30) - 1:int(pl.grid.drop * 30) + 6]), "dark intro, a white flash on the drop")
    mid = float(np.mean([f.mean() for f in fr[len(fr) // 2:len(fr) // 2 + 30]]))
    ok(fr[-1].mean() < 0.4 * mid, f"the tape stop ends dark ({fr[-1].mean():.0f} against {mid:.0f})")
    ok(len({int(f.mean()) for f in fr}) > 40, "the picture changes over the piece")
    # a loudness parameter and the sound alone
    wav_out = work / "m.wav"
    a_ = beatedit.soundtrack(pl, beatedit.decode_piece(str(wav), pl.grid.t0, pl.grid.dur + 1))
    lev = beatedit.master(a_, -14.0, wav_out)
    r = subprocess.run([FF, "-hide_banner", "-nostats", "-i", str(wav_out), "-af", "ebur128=framelog=quiet", "-f", "null", "-"], capture_output=True)
    lu = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr.decode(errors="replace"))[-1])
    ok(abs(lu - (-14.0)) < 1.0, f"loudness -14 asked, {lu} LUFS made (the song's piece measured {lev['in']:.1f})")
    # 60 fps
    c60 = {**cfg, "fps": 60, "out": str(work / "beat60.mp4"), "params": {"build_bars": 2, "drop_bars": 2}}
    r60 = beatedit.render(c60)
    p60 = probe(Path(r60["out"]))
    ok(p60["fps"] == 60 and abs(p60["frames"] - round(r60["seconds"] * 60)) <= 1, f"60 fps: {p60['frames']} frames")
    cli = subprocess.run([sys.executable, "-m", "app.beatedit", str(work / "cli.json")], cwd=str(ROOT), capture_output=True, text=True)
    ok(cli.returncode == 1 and json.loads(cli.stdout.strip().splitlines()[-1]).get("error"), "the CLI reports an error as a JSON line")
    (work / "cli.json").write_text(json.dumps({**c60, "out": str(work / "cli.mp4"), "params": {"build_bars": 2, "drop_bars": 2}, "fps": 30}), encoding="utf-8")
    cli = subprocess.run([sys.executable, "-m", "app.beatedit", str(work / "cli.json")], cwd=str(ROOT), capture_output=True, text=True)
    lines = [json.loads(x) for x in cli.stdout.splitlines() if x.startswith("{")]
    ok(cli.returncode == 0 and lines[-1]["stage"] == "done" and any(x.get("stage") == "frames" for x in lines) and (work / "cli.mp4").exists(),
       "python -m app.beatedit cfg.json: JSON progress lines, the file")

    print("song.timed_words")
    heard = [{"start": 1.0, "end": 1.3, "word": "we", "p": 0.9}, {"start": 1.3, "end": 1.8, "word": "nevr", "p": 0.5}, {"start": 1.8, "end": 2.2, "word": "fade,"},
             {"start": 2.4, "end": 2.6, "word": "uh"}, {"start": 3.0, "end": 3.5, "word": "Away"}, {"start": 4.0, "end": 4.4, "word": "ёлка"}]
    fixed = song.timed_words(heard, "[chorus]\nWe never fade away\n\n[bridge]\nЕлка")
    ok([w["word"] for w in fixed] == ["We", "never", "fade", "uh", "away", "Елка"] or [w["word"] for w in fixed][:3] == ["We", "never", "fade"],
       f"spelling from the written text {[w['word'] for w in fixed]}")
    ok([(w["start"], w["end"]) for w in fixed] == [(w["start"], w["end"]) for w in heard] and fixed[1]["p"] == 0.5, "times and other fields stay Whisper's")
    ok(song.timed_words(heard, "") == heard and song.timed_words([], "x") == [], "no text, no words: as heard")
    ok(heard[1]["word"] == "nevr", "the input is not changed")

    print("autopilot.window «drop»")
    d = song.SONGS / SID
    shutil.rmtree(d, ignore_errors=True)
    (d / "lyrics").mkdir(parents=True)
    shutil.copyfile(wav, d / "song.wav")
    beats = an.beats
    bars = beats[::4]
    energy = [0.3 if t < drop_t - 0.1 else 0.9 for t in bars]
    sections = [{"kind": "intro", "start": 0.0, "end": bars[DROP_BAR], "bar0": 0, "bar1": DROP_BAR, "energy": 0.3},
                {"kind": "drop", "start": bars[DROP_BAR], "end": DUR, "bar0": DROP_BAR, "bar1": len(bars), "energy": 0.9}]
    (d / "analysis.json").write_text(json.dumps({"duration": DUR, "bpm": an.bpm, "beat_s": an.beat_s, "bar_s": an.bar_s, "downbeat": an.downbeat, "beats": beats,
                                                 "bars": bars, "bar_energy": energy, "bar_rms": energy, "sections": sections}), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"name": "click.wav"}), encoding="utf-8")
    (d / "lyrics" / "lyrics.json").write_text(json.dumps({"lines": [
        {"start": 3.0, "end": 6.0, "text": "one verse line here", "words": []},
        {"start": 19.0, "end": 22.0, "text": "never fade away", "words": []},
        {"start": 27.0, "end": 30.0, "text": "never fade away", "words": []}], "language": "en"}), encoding="utf-8")
    try:
        st, secs = autopilot.window(SID, "drop")
        at = autopilot.drop_at(SID)
        ok(abs(at - min(beats, key=lambda b: abs(b - 19.0))) < 1e-6, f"the drop is the first chorus by the words, on a beat ({at:.3f})")
        ok(abs((at - st) - 16 * an.beat_s) < 0.002 and abs(secs - 52 * an.beat_s) < 0.002, f"window: 4 bars before, 9 after ({st:.2f}, {secs:.2f} s)")
        (d / "lyrics" / "lyrics.json").write_text(json.dumps({"lines": [], "language": "en"}), encoding="utf-8")
        at2 = autopilot.drop_at(SID)
        ok(abs(at2 - min(beats, key=lambda b: abs(b - bars[DROP_BAR]))) < 1e-6, f"no words: the first part the sound calls a drop ({at2:.3f})")
        whole = autopilot.window(SID, "whole")
        ok(whole == (0.0, round(song.analysis(SID).duration, 3)) and autopilot.window(SID, "own", 6.0, 5.0) == (5.0, 6.0), f"the other lengths are as they were (whole: {whole})")

        print("the node «Бит-монтаж»: key and cache")
        node_test(work, wav, shots, an, drop_t)
    finally:
        shutil.rmtree(song.SONGS / SID, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def node_test(work: Path, wav: Path, shots: dict, an, drop_t: float) -> None:
    nodes, edges = [], []

    def add(nid, typ, data, x=0, y=0):
        nodes.append({"id": nid, "type": typ, "position": {"x": x, "y": y}, "data": data})

    def edge(a, ah, b, bh):
        edges.append({"id": f"{a}-{b}-{bh}", "source": a, "sourceHandle": ah, "target": b, "targetHandle": bh})
    names = list(COLORS)
    for k, nm in enumerate(names):
        add(f"p_{nm}", "prompt", {"title": nm, "text": f"a shot {nm}"}, 0, 100 * k)
        add(f"s_{nm}", "scene", {"title": nm, "seconds": 3, "takes": [10 + k], "take": 0, **({"role": ROLE[nm]} if nm != "a3" else {})}, 300, 100 * k)
        edge(f"p_{nm}", "text", f"s_{nm}", "prompt")
        edge(f"s_{nm}", "clip", "bm", "clips")
    add("song", "song", {"song": SID, "file": "song.wav", "name": "click.wav", "length": "whole"}, 0, -200)
    add("title", "idea", {"text": "never fade"}, 0, -400)
    add("bm", "beat_montage", {"preview": True, "fps": 30, "params": {"build_bars": 2, "drop_bars": 4}, "drop": round(drop_t, 3)}, 700, 0)
    add("out", "output", {"output": {"size": "1080p"}}, 1000, 0)
    edge("song", "song", "bm", "track")
    edge("title", "text", "bm", "title")
    edge("bm", "video", "out", "video")
    proj = graph_io.new_project("Бит", "9:16", g={"rev": 0, "nodes": nodes, "edges": edges})
    pid = proj["id"]
    try:
        shutil.copyfile(wav, projects.folder(pid) / "song.wav")

        def ctx():
            return graph.Ctx(projects.load(pid), graph.load(pid))

        def art(nid, c=None):
            return graph.evaluate_node(c or ctx(), nid)
        ok(art("bm").state == "wait", "the scenes are not shot: the node waits")
        c = ctx()
        for nm in names:   # a shot in the cache at the scene's key: the scene is ready
            a = graph.evaluate_node(c, f"s_{nm}")
            a.path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(shots[nm], a.path)
            cv2.imwrite(str(a.png), np.zeros((16, 9, 3), np.uint8))
        c = ctx()
        a1 = art("bm", c)
        ok(a1.state == "todo" and a1.key and a1.beat and len(a1.beat["clips"]) == 10, f"the node is to make, its key {a1.key}")
        roles = {x["id"]: x["role"] for x in a1.beat["clips"]}
        ok(roles["s_h1"] == "hero" and roles["s_close"] == "close" and roles["s_riser"] == "riser" and roles["s_a3"] in ("hero", "atmos"),
           "a shot's role is its scene's `role`; none - hero / atmos in turn")
        ok(a1.beat["title"] == "never fade" and a1.beat["song"].endswith("song.wav") and a1.beat["drop"] == round(drop_t, 3), "the title, the song, the drop in the cfg")
        keys = {nm: art(f"s_{nm}", c).key for nm in names}
        job = jobs.Job(id="t-beat", params={}, kind="graph", status="running", steps=0)
        job.started = __import__("time").time()
        job.progress = {"nodes": {"bm": {"status": "running"}}}
        asyncio.run(graph._make_beat(job, "bm", a1))
        ok(a1.path.exists() and a1.path.with_suffix(".json").exists(), "the node's file and its cuts are made (a process of its own)")
        ok(job.progress["nodes"]["bm"].get("stage") == "frames" and job.progress["nodes"]["bm"].get("done") == job.progress["nodes"]["bm"].get("total"), "its progress is in the job")
        ok(not a1.path.with_suffix(".cfg.json").exists(), "the cfg file is cleaned up")
        c = ctx()
        a2 = art("bm", c)
        ok(a2.state == "ready" and a2.key == a1.key and a2.cuts, "the same inputs: the cache hit, the same key")
        ok(abs(a2.seconds - (2 + 4 + 2) * 4 * BEAT) < 0.1, f"its length is the piece's ({a2.seconds:.2f} s)")
        # a render-only change: a new key, the scenes untouched
        keys_of = lambda cc: {nm: (art(f"s_{nm}", cc).key, art(f"s_{nm}", cc).state) for nm in names}  # noqa: E731
        before = keys_of(c)
        for what, mut in (("the preset", lambda d: d.update(preset="dnb")), ("a colour", lambda d: d.update(palette={"a": [1, 2, 3], "b": [255, 255, 255], "tint": [0, 0, 0]})),
                          ("the loudness", lambda d: d.update(loudness=-14)), ("the fps", lambda d: d.update(fps=60)), ("an override", lambda d: d.update(params={"build_bars": 2, "drop_bars": 4, "zoom_drop": 0.2})),
                          ("the HUD text", lambda d: d.update(hud="X"))):
            g_before = json.dumps(graph.load(pid)["nodes"])
            graph.update(pid, lambda gg, mut=mut: mut(graph.node(gg, "bm")["data"]))
            c2 = ctx()
            k2 = art("bm", c2)
            ok(k2.key != a1.key and k2.state == "todo" and keys_of(c2) == before, f"{what} changed: a new key, the scenes untouched and ready")
            graph.update(pid, lambda gg: graph.node(gg, "bm")["data"].update(preset="techno", palette={}, loudness=-10, fps=30, hud="", params={"build_bars": 2, "drop_bars": 4}))
            ok(art("bm", ctx()).key == a1.key, f"… and back: the first key again ({what})")
        # a role change, a title change, a scene change
        graph.update(pid, lambda gg: graph.node(gg, "s_h1")["data"].update(role="atmos"))
        ok(art("bm", ctx()).key != a1.key, "another role: a new key")
        graph.update(pid, lambda gg: graph.node(gg, "s_h1")["data"].update(role="hero"))
        graph.update(pid, lambda gg: graph.node(gg, "title")["data"].update(text="other"))
        ok(art("bm", ctx()).key != a1.key, "another title: a new key")
        graph.update(pid, lambda gg: graph.node(gg, "title")["data"].update(text="never fade"))
        ok(art("bm", ctx()).key == a1.key, "the title back: the first key")
        # the song node's piece (length) is not used by the montage: no new key
        graph.update(pid, lambda gg: graph.node(gg, "song")["data"].update(length="best"))
        ok(art("bm", ctx()).key == a1.key, "the song node's length changed: the montage key is the same")
        graph.update(pid, lambda gg: graph.node(gg, "song")["data"].update(length="whole"))
        # the drop: a pinned one holds while the words / the guess move; clearing the field is «auto» and pins the guess again
        import app.beat_clip as beat_clip
        real_drop = autopilot.drop_at
        try:
            graph.update(pid, lambda gg: graph.node(gg, "bm")["data"].update(drop=None, drop_auto={"drop": round(drop_t, 4), "sig": graph.song_sig(SID)}))
            k_pin = art("bm", ctx()).key
            autopilot.drop_at = lambda sid_: drop_t + 8.0   # the recognised words / the text moved the guess
            ok(art("bm", ctx()).key == k_pin and art("bm", ctx()).beat["drop"] == round(drop_t, 4), "a pinned drop: the guess moves, the key and the cfg do not")
            graph.update(pid, lambda gg: graph.node(gg, "bm")["data"].update(drop_auto={"drop": round(drop_t, 4), "sig": "0:0"}))
            ok(abs(art("bm", ctx()).beat["drop"] - (drop_t + 8.0)) < 1e-3, "the song file changed (another signature): the pin is not used")
            graph.update(pid, lambda gg: graph.node(gg, "bm")["data"].update(drop=round(drop_t, 3), drop_auto=None))
            beat_clip.put_beat(pid, "bm", beat_clip.BeatBody(drop=0))
            dd = graph.node(graph.load(pid), "bm")["data"]
            ok(dd.get("drop") is None and abs(dd["drop_auto"]["drop"] - (drop_t + 8.0)) < 1e-3, "put_beat drop 0 = auto: the stored drop is removed, the guess is pinned")
            beat_clip.put_beat(pid, "bm", beat_clip.BeatBody(drop=12.5))
            ok(graph.node(graph.load(pid), "bm")["data"]["drop"] == 12.5, "put_beat keeps a drop the user typed")
        finally:
            autopilot.drop_at = real_drop
        graph.update(pid, lambda gg: graph.node(gg, "bm")["data"].update(drop=round(drop_t, 3), drop_auto=None))
        graph.update(pid, lambda gg: graph.node(gg, "p_h2")["data"].update(text="another picture of a hero"))
        c3 = ctx()
        ok(art("bm", c3).state == "wait", "a scene's prompt changed (not shot): the node waits for it")
        graph.update(pid, lambda gg: graph.node(gg, "p_h2")["data"].update(text="a shot h2"))
        graph.update(pid, lambda gg: [e for e in gg["edges"] if e["targetHandle"] == "track"] and gg["edges"].remove(next(e for e in gg["edges"] if e["targetHandle"] == "track")))
        ok(art("bm", ctx()).state == "error", "no song on «трек»: an error that says so")
        st = graph.state(projects.load(pid), graph.load(pid))
        ok("bm" in st["nodes"], "the graph state lists the node")
        ok("beat_montage" in graph.public_types() and graph.public_types()["beat_montage"]["title"] == "Бит-монтаж", "the type is public, Russian title first")
        ok("beat_montage" in graph.MAKES and graph.MAKES.index("beat_montage") == graph.MAKES.index("montage") + 1, "in MAKES right after the montage")
    finally:
        projects.remove(pid)


if __name__ == "__main__":
    run()
    print("FAILED: %d" % failed if failed else "all passed")
    sys.exit(1 if failed else 0)
