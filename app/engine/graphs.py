"""H3 graphs, built straight in ComfyUI's API format (no UI json, no /object_info conversion).

The recipe: the official H3 int8 with its 8-step turbo LoRA (or a TURBO fine-tune without it), 8 steps res_multistep, no CFG (BasicGuider),
video + audio in one latent. LoRA go as a chain of LoraLoaderModelOnly between the model and the sampler.
Besides the mp4 the graph saves the last decoded frame as PNG: the start frame of the next scene in a chain,
straight from the decoder, without an mp4 round trip. The loaders, the LoRA chain and that end (`tail`) are shared
with the other models' graphs (other_graphs.py).
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Optional

from .. import config

FPS = 24
STEPS = 8
SAMPLER = "res_multistep"
QUALITY_MP = {"draft": 0.5, "final": 0.98}   # 960x544 / 1344x768 at 16:9 (megapixels of 1024*1024)
ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4}

# node ids; the job maps them to phases for the progress line
UNET, CLIP, VAE, AVAE, IMAGE, H3, NOISE, GUIDER, SAMPLER_SEL, SCHED, SAMPLE, DECODE, ADECODE, VIDEO, SAVE, LAST, SAVE_LAST = (
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17")
PHASES = {UNET: "loading", CLIP: "loading", VAE: "loading", AVAE: "loading", H3: "encoding",
          SAMPLE: "sampling", DECODE: "decoding", ADECODE: "decoding", VIDEO: "saving", SAVE: "saving",
          LAST: "saving", SAVE_LAST: "saving",
          "p2scale": "encoding", "p2enc": "encoding", "p2aenc": "encoding", "p2cond": "encoding", "p2sample": "sampling",
          "p2decode": "decoding", "p2adecode": "decoding"}


def frames_for(seconds: float) -> int:
    """Frames at 24 fps on H3's 17k+5 grid, never shorter than asked (5 s -> 124)."""
    n = max(5, round(seconds * FPS))
    while n % 17 != 5:
        n += 1
    return n


def canvas(aspect: float, megapixels: float) -> tuple[int, int]:
    """Width and height in steps of 32 for an aspect and an area: 16:9 at 0.5 -> 960x544, at 0.98 -> 1344x768."""
    area = megapixels * 1024 * 1024
    w = math.sqrt(area * aspect)
    h = w / aspect
    return max(32, round(w / 32) * 32), max(32, round(h / 32) * 32)


# ---------- the parts every model's graph shares (other_graphs.py builds the others with them) ----------
def unet(name: str) -> dict:
    return {"class_type": "UNETLoader", "inputs": {"unet_name": name, "weight_dtype": "default"}}


def text_encoder(name: str, kind: str) -> dict:
    return {"class_type": "CLIPLoader", "inputs": {"clip_name": name, "type": kind, "device": "default"}}


def vae(name: str) -> dict:
    return {"class_type": "VAELoader", "inputs": {"vae_name": name}}


def lora_chain(g: dict, model: list, loras: list[tuple[str, float]]) -> list:
    """LoraLoaderModelOnly after `model`, one per LoRA (nodes lora0, lora1...). -> the model at the end of the chain."""
    for i, (name, strength) in enumerate(loras):
        nid = f"lora{i}"
        g[nid] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": name, "strength_model": strength}}
        model = [nid, 0]
    return model


def tail(g: dict, prefix: str, images: list, audio: list | None, ids: tuple[str, str, str, str] = ("video", "save", "last", "save_last")) -> None:
    """The end of every scene's graph: the mp4 (with the decoded sound when there is one) and the last decoded frame as
    PNG - the start frame of the next scene in a chain, straight from the decoder. `ids`: the four nodes' ids."""
    video, save, last, save_last = ids
    v = {"images": images, "fps": float(FPS)}
    if audio:
        v["audio"] = audio
    g[video] = {"class_type": "CreateVideo", "inputs": v}
    g[save] = {"class_type": "SaveVideo", "inputs": {"video": [video, 0], "filename_prefix": prefix, "format": "mp4", "format.codec": "auto"}}
    g[last] = {"class_type": "ImageFromBatch", "inputs": {"image": images, "batch_index": -1, "length": 1}}
    g[save_last] = {"class_type": "SaveImage", "inputs": {"images": [last, 0], "filename_prefix": prefix + "_last"}}


REF_STEPS = 4   # the ref2va turbo LoRA's (the official template: 20 steps without it)


def h3_turbo_lora() -> str | None:
    """The official H3 model shoots in 8 steps without CFG only with its turbo LoRA (lightx2v's 8-step distillation,
    Comfy-Org's ComfyUI repack); a fine-tune with the speed-up built in («TURBO» in the name) needs none."""
    return None if "turbo" in config.H3_UNET.lower() or not config.H3_TURBO_LORA else config.H3_TURBO_LORA


REF_BIG_PX = 0.9 * 1024 * 1024   # a Ref2VA shot of this many pixels or more is a final one (1344x768 = 0.98 MP; the draft is 0.5 MP)
SIGMA_SHIFT = (6.0, 3.0)         # MiniMaxH3SigmaShift video/audio: what the 768p LoRA was trained with


def ref_lora_768_here() -> bool:
    """Whether the 768p Ref2VA LoRA lies where the worker looks (H3_REF_DIR or the H3 roots, loras/ or the folder itself)."""
    name = config.H3_REF_LORA_768
    roots = [config.H3_REF_DIR, *getattr(config, "H3_MODEL_ROOTS", ())]
    return bool(name) and any((r / sub / name).is_file() for r in roots for sub in ("loras", ""))


def ref_recipe(width: int, height: int) -> dict:
    """How a Ref2VA shot is sampled. A final-size one (and the 768p LoRA is installed): that LoRA, 8 steps and
    MiniMaxH3SigmaShift 6/3 - the LoRA and the shift match the size it was trained at (GPU A/B 2026-11-10: SFace +0.06..0.11
    on close-ups). Otherwise (the 960x544 draft, or no file): the 544p 4-step LoRA, with er_sde + beta (+0.03 SFace, same time)."""
    if width * height >= REF_BIG_PX and ref_lora_768_here():
        return {"lora": config.H3_REF_LORA_768, "steps": config.REF_STEPS_768, "shift": SIGMA_SHIFT,
                "sampler": SAMPLER, "scheduler": "simple"}
    return {"lora": config.H3_REF_LORA, "steps": REF_STEPS, "shift": None, "sampler": "er_sde", "scheduler": "beta"}


PASS2_STEPS, PASS2_DENOISE = 4, 0.25   # the second pass: 4 steps over the last quarter of the turbo schedule (BasicScheduler: `steps` are run, `denoise` is the share)
PASS2_SCALE = "lanczos"


def audio_guide(g: dict, audio: str, start: float, length: int, positive: list, latent: list, nid: str = "aguide") -> None:
    """The scene's given sound as an audio guide at frame 0 (see scene()): LoadAudio -> [TrimAudioDuration when it
    starts later than the file's beginning] -> MiniMaxH3AddGuide on `positive`, over `latent`. Ids: `nid`, with
    `<nid>_load` / `<nid>_trim`."""
    g[nid + "_load"] = {"class_type": "LoadAudio", "inputs": {"audio": audio}}
    src = [nid + "_load", 0]
    if start and start > 0:
        g[nid + "_trim"] = {"class_type": "TrimAudioDuration", "inputs": {"audio": src, "start_index": round(float(start), 3),
                                                                           "duration": round(length / FPS, 3)}}
        src = [nid + "_trim", 0]
    g[nid] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": positive, "audio_vae": [AVAE, 0], "latent": latent,
                                                              "audio": src, "frame_idx": 0}}


def scene(prompt: str, width: int, height: int, length: int, seed: int, prefix: str,
          loras: list[tuple[str, float]] = (), first_frame: str | None = None, ref_images: list[str] = (),
          ref_video: str | None = None, pass2: tuple[int, int] | None = None, audio: str | None = None,
          audio_from: float = 0.0) -> dict:
    """One scene. `loras` = [(name as ComfyUI lists it, strength)], `first_frame` = a file name in COMFY_INPUT (i2v).
    `ref_images` (files in COMFY_INPUT): Ref2VA - the official ref2va weights with their 4-step turbo LoRA, the photos
    as <Picture 1>, <Picture 2>... in MiniMaxH3ReferenceToVideo (up to 9), so the people keep their faces (the recipe
    of ComfyUI's video_minimax_h3_r2v template). `ref_video` (a file in COMFY_INPUT, with its sound): <Video 1> of
    Ref2VA - «Видео → видео» (v2v.py) makes that clip again with a LoRA that reads it.
    `audio` (a file in COMFY_INPUT): the scene is drawn UNDER that sound - a given spoken line, a piece of a track. The
    core node MiniMaxH3AddGuide anchors it at frame 0 (its audio keyframe) on top of the conditioning, so the lips follow
    it (proven on the GPU 2026-11-09: lip motion 3.2x higher in voiced frames than in silent ones). It chains after the
    start-frame guide of Ref2VA / i2v (the node appends keyframes), and in the second pass it is on the conditioning too.
    `audio_from` (seconds): where in the file the scene's piece begins (TrimAudioDuration to the scene's length); the
    node itself crops a longer sound to the video's duration. The mp4's sound stays the DECODED audio of the sampler
    (as without `audio`: the sound the model made under the guide, re-encoded for the second pass) - it IS the line,
    and muxing the original back would need the audio exactly as long as the picture, which a trimmed or short line
    isn't. Without `audio` the graph is exactly what it was."""
    ref = bool(ref_images) or bool(ref_video)
    g: dict = {UNET: unet(config.H3_REF_UNET if ref else config.H3_UNET), CLIP: text_encoder(config.H3_CLIP, "minimax"),
               VAE: vae(config.H3_VAE), AVAE: vae(config.H3_AUDIO_VAE)}
    model = [UNET, 0]
    recipe = ref_recipe(width, height) if ref else {"steps": STEPS, "shift": None, "sampler": SAMPLER, "scheduler": "simple"}
    if turbo := (recipe["lora"] if ref else h3_turbo_lora()):
        g["lora_turbo"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": turbo, "strength_model": 1.0}}
        model = ["lora_turbo", 0]
    model = lora_chain(g, model, loras)
    if recipe["shift"]:   # after every LoRA: the sampler's guider and scheduler read the shifted model
        g["shift"] = {"class_type": "MiniMaxH3SigmaShift", "inputs": {"model": model, "shift_video": recipe["shift"][0],
                                                                       "shift_audio": recipe["shift"][1]}}
        model = ["shift", 0]

    h3 = {"clip": [CLIP, 0], "vae": [VAE, 0], "prompt": prompt, "width": width, "height": height, "length": length}
    if ref:
        h3.update({"audio_vae": [AVAE, 0], "ref_image_size": "match"})
        for k, name in enumerate(ref_images[:9], 1):
            nid = IMAGE if k == 1 else f"{IMAGE}_{k}"
            g[nid] = {"class_type": "LoadImage", "inputs": {"image": name}}
            h3[f"ref_images.ref_image_{k}"] = [nid, 0]
        if ref_video:
            g["ref_video"] = {"class_type": "LoadVideo", "inputs": {"file": ref_video}}
            g["ref_parts"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["ref_video", 0]}}
            h3["ref_videos.ref_video_1"] = ["ref_parts", 0]
            h3["ref_video_audios.ref_video_audio_1"] = ["ref_parts", 1]
        g[H3] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": h3}
        if first_frame:
            # a continuation (or a scene from a photo) with Ref2VA: the start frame anchored at frame 0 on top of the
            # reference conditioning - the place and pose from the frame, the face from the photos every scene anew
            g["start"] = {"class_type": "LoadImage", "inputs": {"image": first_frame}}
            g["guide"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {"positive": [H3, 0], "vae": [VAE, 0], "latent": [H3, 1],
                                                                         "image": ["start", 0], "frame_idx": 0}}
    else:
        if first_frame:
            g[IMAGE] = {"class_type": "LoadImage", "inputs": {"image": first_frame}}
            h3["first_frame"] = [IMAGE, 0]
        g[H3] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": h3}

    if audio:
        audio_guide(g, audio, audio_from, length, ["guide" if "guide" in g else H3, 0], [H3, 1])
    cond1 = "aguide" if audio else "guide" if "guide" in g else H3
    g[NOISE] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g[GUIDER] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": [cond1, 0]}}
    g[SAMPLER_SEL] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": recipe["sampler"]}}
    g[SCHED] = {"class_type": "BasicScheduler", "inputs": {"model": model, "scheduler": recipe["scheduler"], "steps": recipe["steps"], "denoise": 1.0}}
    g[SAMPLE] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": [NOISE, 0], "guider": [GUIDER, 0], "sampler": [SAMPLER_SEL, 0], "sigmas": [SCHED, 0], "latent_image": [H3, 1]}}

    g[DECODE] = {"class_type": "VAEDecode", "inputs": {"samples": [SAMPLE, 0], "vae": [VAE, 0]}}
    g[ADECODE] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": [SAMPLE, 0], "vae": [AVAE, 0]}}
    if not pass2:
        tail(g, prefix, [DECODE, 0], [ADECODE, 0], (VIDEO, SAVE, LAST, SAVE_LAST))
        return g
    # the second pass: the first pass's picture scaled up to `pass2` and encoded again with its
    # own sound (RemiqoraH3ConcatAV, h3nodes.py), then denoised a little at the big size under the same prompt - the
    # keyframe (a continuation's start) encoded anew at that size, as a keyframe is tied to its patch grid
    w2, h2 = pass2
    g["p2scale"] = {"class_type": "ImageScale", "inputs": {"image": [DECODE, 0], "upscale_method": PASS2_SCALE, "width": w2, "height": h2, "crop": "disabled"}}
    g["p2enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["p2scale", 0], "vae": [VAE, 0]}}
    g["p2aenc"] = {"class_type": "VAEEncodeAudio", "inputs": {"audio": [ADECODE, 0], "vae": [AVAE, 0]}}
    g["p2av"] = {"class_type": "RemiqoraH3ConcatAV", "inputs": {"video_latent": ["p2enc", 0], "audio_latent": ["p2aenc", 0]}}
    cond = [cond1, 0]
    if not ref and first_frame:
        g["p2cond"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": {**h3, "width": w2, "height": h2}}
        cond = ["p2cond", 0]
        if audio:   # the new conditioning has no guide yet: the line goes on it too (the audio keyframe is size-free)
            audio_guide(g, audio, audio_from, length, cond, ["p2av", 0], "p2aguide")
            cond = ["p2aguide", 0]
    g["p2guider"] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": cond}}
    g["p2noise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed + 1}}
    g["p2sched"] = {"class_type": "BasicScheduler", "inputs": {"model": model, "scheduler": "simple", "steps": PASS2_STEPS, "denoise": PASS2_DENOISE}}
    g["p2sample"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["p2noise", 0], "guider": ["p2guider", 0], "sampler": [SAMPLER_SEL, 0], "sigmas": ["p2sched", 0], "latent_image": ["p2av", 0]}}
    g["p2decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["p2sample", 0], "vae": [VAE, 0]}}
    g["p2adecode"] = {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["p2sample", 0], "vae": [AVAE, 0]}}
    tail(g, prefix, ["p2decode", 0], ["p2adecode", 0], (VIDEO, SAVE, LAST, SAVE_LAST))
    return g


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def te_key(g: dict) -> Optional[str]:
    """The key of a scene graph's conditioning (the text encoder's work): its H3 node, the nodes it is made of and the
    contents of the files they load, ids aside. None: not a plain H3 scene (Ref2VA's conditioning isn't kept ahead)."""
    if g.get(H3, {}).get("class_type") != "MiniMaxH3ImageToVideo":
        return None
    order: dict[str, int] = {}

    def walk(nid: str) -> None:
        if nid not in order:
            order[nid] = len(order)
            for k in sorted(g[nid]["inputs"]):
                if _is_link(v := g[nid]["inputs"][k]):
                    walk(v[0])
    walk(H3)
    parts = []
    for nid in order:
        node = g[nid]
        ins = {k: ("link", order[v[0]], v[1]) if _is_link(v) else v for k, v in node["inputs"].items()}
        if node["class_type"] == "LoadImage":   # the same name may hold another picture (h3s_<key>_start.png is per shot, still)
            f = config.COMFY_INPUT / str(node["inputs"]["image"])
            ins["sha"] = hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else None
        parts.append([node["class_type"], ins])
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def text_part(g: dict, tag: str, key: str) -> dict:
    """What the text encoder works for in a plain H3 scene graph: its conditioning node (the TE reads the prompt there,
    with the start frame) and the nodes it is made of, ended in a RemiqoraKeep (h3nodes.py) that keeps the
    conditioning in the worker under `key` (te_key). The node's own inputs get ids `<tag><id>`; the loaders keep theirs,
    so the parts of several scenes in one graph share one TE load."""
    shared = {UNET, CLIP, VAE, AVAE}
    need, todo = set(), [H3]
    while todo:
        nid = todo.pop()
        if nid not in need:
            need.add(nid)
            todo += [v[0] for v in g[nid]["inputs"].values() if _is_link(v)]

    def name(nid: str) -> str:
        return nid if nid in shared else tag + nid
    out = {name(nid): {"class_type": g[nid]["class_type"],
                       "inputs": {k: [name(v[0]), v[1]] if _is_link(v) else v for k, v in g[nid]["inputs"].items()}} for nid in need}
    out[tag + "keep"] = {"class_type": "RemiqoraKeep", "inputs": {"conditioning": [name(H3), 0], "key": key}}
    return out


def use_kept(g: dict, key: str) -> None:
    """A plain H3 scene graph whose conditioning was kept ahead (text_part): its H3 node becomes RemiqoraH3Cond, which
    takes it from the worker (and does the core node's work itself when the worker has lost it)."""
    g[H3] = {"class_type": "RemiqoraH3Cond", "inputs": {**g[H3]["inputs"], "key": key}}


def phase_of(node: str) -> str:
    return "loading" if node.startswith("lora") else PHASES.get(node, "")
