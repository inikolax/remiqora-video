"""Phase 10: the other models' graphs, in ComfyUI's API format like graphs.py builds H3's - from the official ComfyUI
templates (comfyui_workflow_templates_json: video_wan2_2_5B_ti2v, video_ltx2_5_t2v / i2v, video_ltx2_3_t2v / i2v /
ia2v), their subgraphs unrolled and their prompt-enhancer switched off (we write the prompt).

Every graph ends the way H3's does: the mp4 (SaveVideo) and the last decoded frame as PNG (the start of the next scene
in a chain), so render.py shoots any model the same way. All of them at 24 fps - the montage counts frames at 24. The
loaders, the LoRA chain and that end are graphs.py's; the LTX graphs share their loaders, prompt and silence here.

- WAN 2.2 5B (ti2v): one KSampler, 20 steps, CFG 5, uni_pc, shift 8, WAN's own negative prompt. No sound.
- LTX 2.5 (distilled, int8): two stages - half size with 8 sigmas, the latent upscaled x2, 3 more sigmas at full
  size; LTXVDualCFGGuider at 1/1; picture and sound in one latent.
- LTX 2.3 (dev fp8 + the distilled LoRA at 0.5): the same two stages with CFGGuider 1. With a track (ia2v) the scene's
  piece of it is encoded into the audio latent and held by a zero noise mask: the picture is made to that sound - a
  music video, people singing the song.
"""
from __future__ import annotations

from .. import config
from . import graphs
from .graphs import FPS, lora_chain, tail, text_encoder, unet, vae

WAN_STEPS, WAN_CFG, WAN_SHIFT = 20, 5.0, 8.0
WAN_FAST_STEPS, WAN_FAST_SHIFT = 8, 5.0
WAN_NEGATIVE = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
                "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走")
LTX_NEGATIVE = "pc game, console game, video game, cartoon, childish, ugly, text, subtitles, watermark"
LTX_SIGMAS_1 = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"   # stage 1: 8 steps
LTX_SIGMAS_2 = "0.85, 0.7250, 0.4219, 0.0"                                             # stage 2: 3 steps
LTX_STEPS = 8 + 3
LTX23_LORA_STRENGTH = 0.5
IMG_COMPRESSION = 18   # LTXVPreprocess: the start frame a little like a video frame, as in the templates
# VAEDecodeTiled: each version's tiles as its templates decode
LTX25_TILES = {"tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}
LTX23_TILES = {"tile_size": 768, "overlap": 64, "temporal_size": 4096, "temporal_overlap": 4}

# the nodes whose progress is the sampling (jobs.py shows their steps); the rest map to phases by their id
SAMPLERS = ("sample", "sample1", "sample2")
PHASES = {"unet": "loading", "clip": "loading", "vae": "loading", "avae": "loading", "ckpt": "loading", "te": "loading",
          "pos": "encoding", "neg": "encoding", "cond": "encoding", "sample": "sampling", "sample1": "sampling",
          "sample2": "sampling", "ups": "sampling", "decode": "decoding", "adecode": "decoding", "video": "saving",
          "save": "saving", "last": "saving", "save_last": "saving", "voice": "loading", "vtrim": "encoding", "refaudio": "encoding"}


def phase_of(node: str) -> str:
    return "loading" if node.startswith("lora") else PHASES.get(node, "")


# ---------- the LTX parts its graphs share ----------
def _ltx25_loaders() -> dict:
    """LTX 2.5: the distilled transformer, its video and audio VAE, Gemma 4 (nodes unet, vae, avae, clip)."""
    return {"unet": unet(config.LTX25_UNET), "vae": vae(config.LTX25_VAE), "avae": vae(config.LTX25_AUDIO_VAE),
            "clip": text_encoder(config.LTX25_CLIP, "ltxv")}


def _ltx23_loaders(te: str) -> dict:
    """LTX 2.3: the dev checkpoint (model, VAE and audio VAE in one file), Gemma 3 under node id `te`, the distilled
    LoRA at LTX23_LORA_STRENGTH on the model (node lora_distilled)."""
    ck = config.LTX23_CKPT
    return {"ckpt": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ck}},
            te: {"class_type": "LTXAVTextEncoderLoader", "inputs": {"text_encoder": config.LTX23_CLIP, "ckpt_name": ck, "device": "default"}},
            "avae": {"class_type": "LTXVAudioVAELoader", "inputs": {"ckpt_name": ck}},
            "lora_distilled": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["ckpt", 0], "lora_name": config.LTX23_LORA,
                                                                              "strength_model": LTX23_LORA_STRENGTH}}}


def _ltx_prompt(g: dict, prompt: str, clip: str) -> None:
    """The prompt and LTX's negative (nodes pos, neg)."""
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": [clip, 0]}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"text": LTX_NEGATIVE, "clip": [clip, 0]}}


def _ltx_cond(g: dict, pos: list, neg: list) -> None:
    g["cond"] = {"class_type": "LTXVConditioning", "inputs": {"positive": pos, "negative": neg, "frame_rate": float(FPS)}}


def _ltx_silence(g: dict, length: int) -> None:
    """An empty audio latent for the scene's sound (node alat)."""
    g["alat"] = {"class_type": "LTXVEmptyLatentAudio", "inputs": {"frames_number": length, "frame_rate": FPS, "batch_size": 1, "audio_vae": ["avae", 0]}}


def wan(prompt: str, width: int, height: int, length: int, seed: int, prefix: str,
        loras: list[tuple[str, float]] = (), first_frame: str | None = None, fast: bool = False) -> dict:
    """WAN 2.2 5B, text or a start frame -> video without sound (template video_wan2_2_5B_ti2v). `fast`: with the
    FastWan LoRA - WAN_FAST_STEPS at CFG 1, shift 5 (the negative prompt then does nothing)."""
    g: dict = {"unet": unet(config.WAN_UNET), "clip": text_encoder(config.WAN_CLIP, "wan"), "vae": vae(config.WAN_VAE)}
    model = lora_chain(g, ["unet", 0], list(loras) + ([(config.WAN_FAST_LORA, 1.0)] if fast else []))
    g["shift"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": model, "shift": WAN_FAST_SHIFT if fast else WAN_SHIFT}}
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["clip", 0]}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"text": WAN_NEGATIVE, "clip": ["clip", 0]}}
    lat = {"vae": ["vae", 0], "width": width, "height": height, "length": length, "batch_size": 1}
    if first_frame:
        g["image"] = {"class_type": "LoadImage", "inputs": {"image": first_frame}}
        lat["start_image"] = ["image", 0]
    g["latent"] = {"class_type": "Wan22ImageToVideoLatent", "inputs": lat}
    g["sample"] = {"class_type": "KSampler", "inputs": {"model": ["shift", 0], "seed": seed, "steps": WAN_FAST_STEPS if fast else WAN_STEPS,
                                                       "cfg": 1.0 if fast else WAN_CFG,
                                                       "sampler_name": "uni_pc", "scheduler": "simple", "positive": ["pos", 0],
                                                       "negative": ["neg", 0], "latent_image": ["latent", 0], "denoise": 1.0}}
    g["decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]}}
    tail(g, prefix, ["decode", 0], None)
    return g


def _ltx_stages(g: dict, model: list, vae: list, avae: list, upscaler: list, guider: str, sampler: str,
                width: int, height: int, length: int, seed: int, first_frame: str | None, audio_latent: list,
                model1: list | None = None, last_frame: str | None = None) -> list:
    """The two stages both LTX templates share: half size, the latent x2, full size; the start frame in both.
    `model1`: the first stage's own model (ID-LoRA's, holding the voice); the second refines with `model`.
    `last_frame` (flf2v, «прийти к кадру»; templates video_ltx2_3_flf2v / video_ltx2_5_flf2v): the scene ends on that
    picture - LTXVAddGuide at the last frame (0.7 in the first stage, as the template; 1.0 in the second, as the start
    frame), its guide frames cropped off before the decode. -> the video latent to decode."""
    def guide(nid: str, pos: list, neg: list, m: list) -> None:
        if guider == "dual":
            g[nid] = {"class_type": "LTXVDualCFGGuider", "inputs": {"model": m, "positive": pos, "negative": neg, "video_cfg": 1.0, "audio_cfg": 1.0}}
        else:
            g[nid] = {"class_type": "CFGGuider", "inputs": {"model": m, "positive": pos, "negative": neg, "cfg": 1.0}}

    g["lat1"] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": width // 2, "height": height // 2, "length": length, "batch_size": 1}}
    video1 = ["lat1", 0]
    if first_frame:
        g["image"] = {"class_type": "LoadImage", "inputs": {"image": first_frame}}
        g["pre"] = {"class_type": "LTXVPreprocess", "inputs": {"image": ["image", 0], "img_compression": IMG_COMPRESSION}}
        g["in1"] = {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": vae, "image": ["pre", 0], "latent": video1, "strength": 0.7, "bypass": False}}
        video1 = ["in1", 0]
    pos1, neg1 = ["cond", 0], ["cond", 1]
    if last_frame:
        g["end_image"] = {"class_type": "LoadImage", "inputs": {"image": last_frame}}
        g["end_pre"] = {"class_type": "LTXVPreprocess", "inputs": {"image": ["end_image", 0], "img_compression": IMG_COMPRESSION}}
        g["end1"] = {"class_type": "LTXVAddGuide", "inputs": {"positive": pos1, "negative": neg1, "vae": vae, "latent": video1,
                                                             "image": ["end_pre", 0], "frame_idx": -1, "strength": 0.7}}
        pos1, neg1, video1 = ["end1", 0], ["end1", 1], ["end1", 2]
    g["av1"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": video1, "audio_latent": audio_latent}}
    guide("guide1", pos1, neg1, model1 or model)
    g["noise1"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["sampler1"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": sampler}}
    g["sigmas1"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": LTX_SIGMAS_1}}
    g["sample1"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise1", 0], "guider": ["guide1", 0], "sampler": ["sampler1", 0],
                                                                     "sigmas": ["sigmas1", 0], "latent_image": ["av1", 0]}}
    g["sep1"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["sample1", 0]}}
    g["ups"] = {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["sep1", 0], "upscale_model": upscaler, "vae": vae}}
    video2 = ["ups", 0]
    if first_frame:
        g["in2"] = {"class_type": "LTXVImgToVideoInplace", "inputs": {"vae": vae, "image": ["pre", 0], "latent": video2, "strength": 1.0, "bypass": False}}
        video2 = ["in2", 0]
    g["crop"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": pos1, "negative": neg1, "latent": ["sep1", 0]}}
    pos2, neg2 = ["crop", 0], ["crop", 1]
    if last_frame:   # the first stage's guide frames are off (crop); the last frame again at the full size
        g["ups"]["inputs"]["samples"] = ["crop", 2]
        g["end2"] = {"class_type": "LTXVAddGuide", "inputs": {"positive": pos2, "negative": neg2, "vae": vae, "latent": video2,
                                                             "image": ["end_pre", 0], "frame_idx": -1, "strength": 1.0}}
        pos2, neg2, video2 = ["end2", 0], ["end2", 1], ["end2", 2]
    g["av2"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": video2, "audio_latent": ["sep1", 1]}}
    guide("guide2", pos2, neg2, model)
    g["noise2"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed + 1}}
    g["sampler2"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": sampler}}
    g["sigmas2"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": LTX_SIGMAS_2}}
    g["sample2"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise2", 0], "guider": ["guide2", 0], "sampler": ["sampler2", 0],
                                                                     "sigmas": ["sigmas2", 0], "latent_image": ["av2", 0]}}
    g["sep2"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["sample2", 0]}}
    g["adecode"] = {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["sep2", 1], "audio_vae": avae}}
    if not last_frame:
        return ["sep2", 0]
    g["crop2"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": pos2, "negative": neg2, "latent": ["sep2", 0]}}
    return ["crop2", 2]


def ltx25(prompt: str, width: int, height: int, length: int, seed: int, prefix: str,
          loras: list[tuple[str, float]] = (), first_frame: str | None = None, last_frame: str | None = None) -> dict:
    """LTX 2.5 distilled, text or a start frame -> video with its own sound (templates video_ltx2_5_t2v / i2v).
    width and height: the full size, multiples of 64 (the first stage is half of it)."""
    g: dict = {**_ltx25_loaders(), "up": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": config.LTX25_UPSCALER}}}
    model = lora_chain(g, ["unet", 0], loras)
    _ltx_prompt(g, prompt, "clip")
    _ltx_cond(g, ["pos", 0], ["neg", 0])
    _ltx_silence(g, length)
    video = _ltx_stages(g, model, ["vae", 0], ["avae", 0], ["up", 0], "dual", "euler_ancestral", width, height, length, seed, first_frame,
                        ["alat", 0], last_frame=last_frame)
    g["decode"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": video, "vae": ["vae", 0], **LTX25_TILES}}
    tail(g, prefix, ["decode", 0], ["adecode", 0])
    return g


def ltx_ic(version: str, prompt: str, width: int, height: int, length: int, seed: int, prefix: str, video: str,
           loras: list[tuple[str, float]], guide: float = 1.0, stages: int = 1) -> dict:
    """LTX with an IC-LoRA (`version` "ltx25" or "ltx23"): a clip (`video`, a file in COMFY_INPUT of exactly width x
    height and `length` frames, 8n+1) -> that clip made again (template video_ltx2_3_ic_lora on our distilled sigmas;
    2.5: its distilled transformer, 2.3: dev + the distilled LoRA as its scenes shoot). The IC-LoRA is the last of
    `loras`: GetICLoRAParameters reads its metadata (reference_downscale_factor: LTXVAddGuide takes the clip at 1/n of
    the size, so the size must divide by 32 * n). The clip is a guide in every stage, so the result keeps its frames;
    one stage at the full size (Alpha-Gen's card: the reference stays attached for the whole denoise), or two - half
    size, the latent x2, full size again. Only the picture is saved: the sound is the clip's (v2v.py)."""
    v25 = version == "ltx25"
    if v25:
        g: dict = _ltx25_loaders()
        model, vae = lora_chain(g, ["unet", 0], loras), ["vae", 0]
    else:
        g = _ltx23_loaders("clip")
        model, vae = lora_chain(g, ["lora_distilled", 0], loras), ["ckpt", 2]
    g["ref"] = {"class_type": "LoadVideo", "inputs": {"file": video}}
    g["iclora"] = {"class_type": "GetICLoRAParameters", "inputs": {"iclora_model": model}}
    g["ref_parts"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["ref", 0]}}
    _ltx_prompt(g, prompt, "clip")
    _ltx_cond(g, ["pos", 0], ["neg", 0])
    _ltx_silence(g, length)
    two = stages == 2
    if two:
        g["up"] = {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": config.LTX25_UPSCALER if v25 else config.LTX23_UPSCALER}}
    g["lat1"] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": width // 2 if two else width, "height": height // 2 if two else height,
                                                                  "length": length, "batch_size": 1}}

    def stage(k: int, pos: list, neg: list, latent: list, audio: list, sigmas: str) -> None:
        g[f"guide{k}"] = {"class_type": "LTXVAddGuide", "inputs": {"positive": pos, "negative": neg, "vae": vae, "latent": latent,
                                                                     "image": ["ref_parts", 0], "frame_idx": 0, "strength": guide,
                                                                     "iclora_parameters": ["iclora", 0]}}
        g[f"av{k}"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": [f"guide{k}", 2], "audio_latent": audio}}
        if v25:
            g[f"cfg{k}"] = {"class_type": "LTXVDualCFGGuider", "inputs": {"model": model, "positive": [f"guide{k}", 0], "negative": [f"guide{k}", 1],
                                                                           "video_cfg": 1.0, "audio_cfg": 1.0}}
        else:
            g[f"cfg{k}"] = {"class_type": "CFGGuider", "inputs": {"model": model, "positive": [f"guide{k}", 0], "negative": [f"guide{k}", 1], "cfg": 1.0}}
        g[f"noise{k}"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed + k - 1}}
        g[f"sampler{k}"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral" if v25 else "euler"}}
        g[f"sigmas{k}"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}}
        g[f"sample{k}"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": [f"noise{k}", 0], "guider": [f"cfg{k}", 0],
                                                                             "sampler": [f"sampler{k}", 0], "sigmas": [f"sigmas{k}", 0],
                                                                             "latent_image": [f"av{k}", 0]}}
        g[f"sep{k}"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": [f"sample{k}", 0]}}
        g[f"crop{k}"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": [f"guide{k}", 0], "negative": [f"guide{k}", 1], "latent": [f"sep{k}", 0]}}

    stage(1, ["cond", 0], ["cond", 1], ["lat1", 0], ["alat", 0], LTX_SIGMAS_1)
    last = 1
    if two:
        g["ups"] = {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["crop1", 2], "upscale_model": ["up", 0], "vae": vae}}
        stage(2, ["crop1", 0], ["crop1", 1], ["ups", 0], ["sep1", 1], LTX_SIGMAS_2)
        last = 2
    g["decode"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": [f"crop{last}", 2], "vae": vae, **(LTX25_TILES if v25 else LTX23_TILES)}}
    tail(g, prefix, ["decode", 0], None)
    return g


def ltx23(prompt: str, width: int, height: int, length: int, seed: int, prefix: str,
          loras: list[tuple[str, float]] = (), first_frame: str | None = None,
          track: str | None = None, track_start: float = 0.0, voice: dict | None = None, last_frame: str | None = None) -> dict:
    """LTX 2.3 dev + its distilled LoRA, text or a start frame -> video with sound (video_ltx2_3_t2v / i2v); with
    `track` (a file in COMFY_INPUT) its piece from `track_start` is the scene's sound and the picture follows it
    (video_ltx2_3_ia2v): a music video, people singing that song. With `voice` (video_ltx2_3_id_lora) the ID-LoRA
    ({lora: its ComfyUI name, strength, voice: a file in COMFY_INPUT, from, secs, identity}) and LTXVReferenceAudio hold
    the voice of that sample's piece in the first stage; the second refines without them, as the template does."""
    g: dict = {**_ltx23_loaders("te"), "up": {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": config.LTX23_UPSCALER}}}
    model = lora_chain(g, ["lora_distilled", 0], loras)
    _ltx_prompt(g, prompt, "te")
    pos, neg, model1 = ["pos", 0], ["neg", 0], None
    if voice:
        g["lora_id"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": voice["lora"],
                                                                       "strength_model": float(voice.get("strength", 1.0))}}
        g["voice"] = {"class_type": "LoadAudio", "inputs": {"audio": voice["voice"]}}
        g["vtrim"] = {"class_type": "TrimAudioDuration", "inputs": {"audio": ["voice", 0], "start_index": float(voice.get("from", 0.0)),
                                                                    "duration": float(voice.get("secs", 5.0))}}
        g["refaudio"] = {"class_type": "LTXVReferenceAudio", "inputs": {"model": ["lora_id", 0], "positive": pos, "negative": neg,
                                                                        "reference_audio": ["vtrim", 0], "audio_vae": ["avae", 0],
                                                                        "identity_guidance_scale": float(voice.get("identity", 3.0)),
                                                                        "start_percent": 0.0, "end_percent": 1.0}}
        pos, neg, model1 = ["refaudio", 1], ["refaudio", 2], ["refaudio", 0]
    _ltx_cond(g, pos, neg)
    if track:
        g["track"] = {"class_type": "LoadAudio", "inputs": {"audio": track}}
        g["trim"] = {"class_type": "TrimAudioDuration", "inputs": {"audio": ["track", 0], "start_index": float(track_start),
                                                                   "duration": round(length / FPS, 4)}}
        g["aenc"] = {"class_type": "LTXVAudioVAEEncode", "inputs": {"audio": ["trim", 0], "audio_vae": ["avae", 0]}}
        g["amask"] = {"class_type": "SolidMask", "inputs": {"value": 0.0, "width": width, "height": height}}
        g["alat"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["aenc", 0], "mask": ["amask", 0]}}
    else:
        _ltx_silence(g, length)
    video = _ltx_stages(g, model, ["ckpt", 2], ["avae", 0], ["up", 0], "cfg", "euler", width, height, length, seed, first_frame,
                        ["alat", 0], model1, last_frame)
    g["decode"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": video, "vae": ["ckpt", 2], **LTX23_TILES}}
    tail(g, prefix, ["decode", 0], ["adecode", 0])
    return g


# ---------- Krea 2 Turbo on the worker (the A/B against sd.cpp, branch krea-comfy-ab) ----------
# From the official template image_krea2_turbo_t2i_int8 with its prompt enhancer off: UNETLoader (int8 convrot) ->
# LoraLoaderModelOnly chain -> KSampler 8 steps, CFG 1, euler / simple; the negative is the positive zeroed out
# (ConditioningZeroOut); Qwen3-VL 4B fp8 through CLIPLoader type "krea2"; the Qwen-Image VAE.
KREA_UNET_COMFY = "krea2_turbo_int8_convrot.safetensors"
KREA_CLIP_COMFY = "qwen3vl_4b_fp8_scaled.safetensors"
KREA_VAE_COMFY = "qwen_image_vae.safetensors"
KREA_STEPS = 8   # the default of config.KREA_STEPS (the page's «Параметры»)
PHASES.update(kpos="encoding", kneg="encoding", ksample="sampling", kdecode="decoding", ksave="saving", kunet="loading", kclip="loading", kvae="loading")


def krea2(prompt: str, width: int, height: int, seed: int, prefix: str, loras: list[tuple[str, float]] = (),
          unet: str = KREA_UNET_COMFY, clip: str = KREA_CLIP_COMFY, vae: str = KREA_VAE_COMFY) -> dict:
    """One Krea 2 Turbo picture (PNG) at width x height."""
    g: dict = {
        "kunet": graphs.unet(unet), "kclip": text_encoder(clip, "krea2"), "kvae": graphs.vae(vae),   # its arguments hide the helpers' names
        "kpos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["kclip", 0], "text": prompt}},
        "kneg": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["kpos", 0]}},
        "klatent": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
    }
    model = lora_chain(g, ["kunet", 0], list(loras))
    g["ksample"] = {"class_type": "KSampler", "inputs": {"model": model, "positive": ["kpos", 0], "negative": ["kneg", 0],
                                                          "latent_image": ["klatent", 0], "seed": seed, "steps": config.KREA_STEPS, "cfg": 1.0,
                                                          "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}}
    g["kdecode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ksample", 0], "vae": ["kvae", 0]}}
    g["ksave"] = {"class_type": "SaveImage", "inputs": {"images": ["kdecode", 0], "filename_prefix": prefix}}
    return g


def krea2_img2img(prompt: str, image: str, seed: int, prefix: str, denoise: float,
                  unet: str = KREA_UNET_COMFY, clip: str = KREA_CLIP_COMFY, vae: str = KREA_VAE_COMFY) -> dict:
    """A picture (`image`, a file in COMFY_INPUT) made again by Krea 2 Turbo at its own size: the same pipeline from the
    picture's latent with `denoise` of the way (0.5: the last 4 of the 8 steps) - facefix.py's anchor frames."""
    g: dict = {
        "kunet": graphs.unet(unet), "kclip": text_encoder(clip, "krea2"), "kvae": graphs.vae(vae),
        "kpos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["kclip", 0], "text": prompt}},
        "kneg": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["kpos", 0]}},
        "kimg": {"class_type": "LoadImage", "inputs": {"image": image}},
        "kenc": {"class_type": "VAEEncode", "inputs": {"pixels": ["kimg", 0], "vae": ["kvae", 0]}},
    }
    g["ksample"] = {"class_type": "KSampler", "inputs": {"model": ["kunet", 0], "positive": ["kpos", 0], "negative": ["kneg", 0],
                                                          "latent_image": ["kenc", 0], "seed": seed, "steps": KREA_STEPS, "cfg": 1.0,
                                                          "sampler_name": "euler", "scheduler": "simple", "denoise": denoise}}
    g["kdecode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ksample", 0], "vae": ["kvae", 0]}}
    g["ksave"] = {"class_type": "SaveImage", "inputs": {"images": ["kdecode", 0], "filename_prefix": prefix}}
    return g


# ---------- FLUX.2 Klein 4B: a picture from reference pictures ----------
# From the official template image_flux2_klein_image_edit_4b_distilled: UNETLoader -> CFGGuider 1; Qwen3 4B through
# CLIPLoader type "flux2"; every reference (scaled to 1 Mp) VAE-encoded and hung on both the prompt and its zeroed-out
# copy as ReferenceLatent; EmptyFlux2LatentImage at the picture's size, Flux2Scheduler 4 steps, euler.
FLUX2_STEPS = 4   # the default of config.FLUX2_STEPS (the page's «Параметры»)
PHASES.update(funet="loading", fclip="loading", fvae="loading", fpos="encoding", fsample="sampling", fdecode="decoding", fsave="saving")


def flux2_edit(prompt: str, refs: list[str], width: int, height: int, seed: int, prefix: str,
               unet: str = "flux-2-klein-4b.safetensors", clip: str = "qwen_3_4b_fp8_mixed.safetensors", vae: str = "flux2-vae.safetensors",
               loras: list[tuple[str, float]] = ()) -> dict:
    """One FLUX.2 Klein picture (PNG) at width x height made from `refs` (files in COMFY_INPUT, in the prompt's order:
    the first is what "the woman in the first image" means) and the prompt; `loras` [(name as the worker lists it, strength)]."""
    g: dict = {
        "funet": graphs.unet(unet), "fclip": text_encoder(clip, "flux2"), "fvae": graphs.vae(vae),   # its arguments hide the helpers' names
        "fpos": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["fclip", 0], "text": prompt}},
        "fneg": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["fpos", 0]}},
        "flatent": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
    }
    pos, neg = ["fpos", 0], ["fneg", 0]
    for k, name in enumerate(refs):
        g[f"fimg{k}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
        g[f"fscale{k}"] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": [f"fimg{k}", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 1}}
        g[f"fenc{k}"] = {"class_type": "VAEEncode", "inputs": {"pixels": [f"fscale{k}", 0], "vae": ["fvae", 0]}}
        g[f"fref{k}"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": pos, "latent": [f"fenc{k}", 0]}}
        g[f"frefn{k}"] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": neg, "latent": [f"fenc{k}", 0]}}
        pos, neg = [f"fref{k}", 0], [f"frefn{k}", 0]
    g["fguider"] = {"class_type": "CFGGuider", "inputs": {"model": lora_chain(g, ["funet", 0], list(loras)), "positive": pos, "negative": neg, "cfg": 1.0}}
    g["fnoise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["fsampler"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
    g["fsigmas"] = {"class_type": "Flux2Scheduler", "inputs": {"steps": config.FLUX2_STEPS, "width": width, "height": height}}
    g["fsample"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["fnoise", 0], "guider": ["fguider", 0], "sampler": ["fsampler", 0],
                                                                      "sigmas": ["fsigmas", 0], "latent_image": ["flatent", 0]}}
    g["fdecode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["fsample", 0], "vae": ["fvae", 0]}}
    g["fsave"] = {"class_type": "SaveImage", "inputs": {"images": ["fdecode", 0], "filename_prefix": prefix}}
    return g


# ---------- LTX 2.3 as video-to-video on a face's crop (facefix.py) ----------
def ltx_facefix(prompt: str, width: int, height: int, length: int, seed: int, prefix: str, video: str,
                anchors: list[tuple[str, int]], guide: float, sigmas: str) -> dict:
    """A clip (`video` in COMFY_INPUT, width × height, `length` frames of 8n+1) made again by LTX 2.3 from its own latent
    with `sigmas` (the schedule's tail: a little noise, the picture and motion kept), the `anchors` (PNG in COMFY_INPUT,
    frame index - never 8n+1) held as guides at `guide` (LTXVAddGuide, as the start frame of a scene). One stage at
    the full size, dev fp8 + the distilled LoRA as the scenes; the sound an empty latent, only the picture saved."""
    g: dict = _ltx23_loaders("clip")
    model, vae = ["lora_distilled", 0], ["ckpt", 2]
    g["ref"] = {"class_type": "LoadVideo", "inputs": {"file": video}}
    g["ref_parts"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["ref", 0]}}
    g["enc"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["ref_parts", 0], "vae": vae}}
    _ltx_prompt(g, prompt, "clip")
    _ltx_cond(g, ["pos", 0], ["neg", 0])
    _ltx_silence(g, length)
    pos, neg, lat = ["cond", 0], ["cond", 1], ["enc", 0]
    for k, (png, idx) in enumerate(anchors):
        g[f"aimg{k}"] = {"class_type": "LoadImage", "inputs": {"image": png}}
        g[f"apre{k}"] = {"class_type": "LTXVPreprocess", "inputs": {"image": [f"aimg{k}", 0], "img_compression": IMG_COMPRESSION}}
        g[f"guide{k}"] = {"class_type": "LTXVAddGuide", "inputs": {"positive": pos, "negative": neg, "vae": vae, "latent": lat,
                                                                   "image": [f"apre{k}", 0], "frame_idx": int(idx), "strength": guide}}
        pos, neg, lat = [f"guide{k}", 0], [f"guide{k}", 1], [f"guide{k}", 2]
    g["av1"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": lat, "audio_latent": ["alat", 0]}}
    g["cfg1"] = {"class_type": "CFGGuider", "inputs": {"model": model, "positive": pos, "negative": neg, "cfg": 1.0}}
    g["noise1"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    g["sampler1"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}}
    g["sigmas1"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}}
    g["sample1"] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["noise1", 0], "guider": ["cfg1", 0], "sampler": ["sampler1", 0],
                                                                     "sigmas": ["sigmas1", 0], "latent_image": ["av1", 0]}}
    g["sep1"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["sample1", 0]}}
    g["crop1"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": pos, "negative": neg, "latent": ["sep1", 0]}}
    g["decode"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["crop1", 2], "vae": vae, **LTX23_TILES}}
    tail(g, prefix, ["decode", 0], None)
    return g
