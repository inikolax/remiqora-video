r"""Ref2VA sampling recipe (graphs.ref_recipe / graphs.scene), without a GPU: the final-size shot with face references
gets the 768p 8-step LoRA and MiniMaxH3SigmaShift 6/3; the draft gets er_sde + beta; a plain H3 shot is what it was;
without the 768p file the final falls back to the draft's recipe. GPU A/B 2026-11-10 (SFace +0.06..0.11 on close-ups).

    .venv\Scripts\python.exe tools\test_ref_recipe.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, render, timings  # noqa: E402
from app.engine import graphs  # noqa: E402

failed = 0


def ok(cond, what: str) -> None:
    global failed
    if cond:
        print(f"  ok  {what}")
    else:
        failed += 1
        print(f"FAIL  {what}")


def shot(w: int, h: int, refs=("a.png",), **kw) -> dict:
    return graphs.scene("a woman", w, h, 97, 1, "t", [], None, list(refs), **kw)


fake = Path(tempfile.mkdtemp())
(fake / "loras").mkdir()
saved = (config.H3_REF_DIR, config.H3_MODEL_ROOTS)
(fake / "loras" / config.H3_REF_LORA_768).write_bytes(b"x")
config.H3_REF_DIR, config.H3_MODEL_ROOTS = fake, []
try:
    print("final Ref2VA, the 768p LoRA is there")
    g = shot(1344, 768)
    ok(g["lora_turbo"]["inputs"]["lora_name"] == config.H3_REF_LORA_768, "768p LoRA")
    ok(g[graphs.SCHED]["inputs"]["steps"] == config.REF_STEPS_768 == 8, "8 steps")
    sh = g.get("shift", {})
    ok(sh.get("class_type") == "MiniMaxH3SigmaShift" and sh["inputs"]["shift_video"] == 6.0 and sh["inputs"]["shift_audio"] == 3.0, "SigmaShift 6/3")
    ok(sh["inputs"]["model"] == ["lora_turbo", 0], "the shift sits on the LoRA'd model")
    ok(g[graphs.GUIDER]["inputs"]["model"] == ["shift", 0] and g[graphs.SCHED]["inputs"]["model"] == ["shift", 0], "guider and scheduler read the shifted model")
    ok(g[graphs.SAMPLER_SEL]["inputs"]["sampler_name"] == "res_multistep" and g[graphs.SCHED]["inputs"]["scheduler"] == "simple", "the LoRA's own sampler / scheduler")
    g2 = shot(1344, 768, pass2=(1344, 768))
    ok(g2["p2guider"]["inputs"]["model"] == ["shift", 0] and g2["p2sched"]["inputs"]["model"] == ["shift", 0], "pass 2 reads the shifted model")
    k_final = render.scene_key("p", 1, 1344, 768, 97, [], None, [Path(__file__)])

    print("draft Ref2VA")
    g = shot(960, 544)
    ok(g["lora_turbo"]["inputs"]["lora_name"] == config.H3_REF_LORA, "544p LoRA")
    ok(g[graphs.SCHED]["inputs"]["steps"] == graphs.REF_STEPS == 4 and "shift" not in g, "4 steps, no shift")
    ok(g[graphs.SAMPLER_SEL]["inputs"]["sampler_name"] == "er_sde" and g[graphs.SCHED]["inputs"]["scheduler"] == "beta", "er_sde + beta")

    print("plain H3 (no references) is unchanged")
    for w, h in ((960, 544), (1344, 768)):
        g = shot(w, h, refs=())
        ok(g[graphs.SAMPLER_SEL]["inputs"]["sampler_name"] == "res_multistep" and g[graphs.SCHED]["inputs"]["scheduler"] == "simple", f"{w}x{h}: res_multistep + simple")
        ok(g[graphs.SCHED]["inputs"]["steps"] == graphs.STEPS and "shift" not in g, f"{w}x{h}: {graphs.STEPS} steps, no shift")

    print("time estimate")
    with_file = timings.scene_seconds("final_ref", 1344, 768, 124, None) if not timings._mine("final_ref") else None
    config.H3_REF_DIR = Path(tempfile.mkdtemp())   # no file
    k_nofile = render.scene_key("p", 1, 1344, 768, 97, [], None, [Path(__file__)])
    without = timings.scene_seconds("final_ref", 1344, 768, 124, None) if with_file else None
    if with_file:
        ok(abs(with_file / without - 2) < 1e-6, "the final Ref2VA guess is x2 with the 768p LoRA")
    else:
        print("  --  measured timings exist here; the guess is not used")
    ok(k_final != k_nofile, "the final shot's key changes with the 768p LoRA")

    print("no 768p file: the final falls back to today's recipe + er_sde/beta")
    g = shot(1344, 768)
    ok(g["lora_turbo"]["inputs"]["lora_name"] == config.H3_REF_LORA and "shift" not in g and g[graphs.SCHED]["inputs"]["steps"] == 4, "544p LoRA, 4 steps, no shift")
finally:
    config.H3_REF_DIR, config.H3_MODEL_ROOTS = saved

print("FAILED" if failed else "all ok")
sys.exit(1 if failed else 0)
