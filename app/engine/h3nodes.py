"""Our own ComfyUI nodes for the worker (h3worker.py registers them after the core's; ComfyUI's modules are on
sys.path there, so `comfy.*` imports resolve).

RemiqoraH3ConcatAV: a video latent (VAEEncode with the H3 video VAE: [B, 24, T, H/16, W/16]) and an audio latent
(VAEEncodeAudio with the H3 audio VAE: [B, 32, 2, T40]) as the joint AV latent the H3 model samples - the pair
comfy_extras/nodes_minimax_h3.py builds empty. The core has no node for it, and a second pass of H3 (graphs.scene,
pass2: the first pass decoded, scaled up, encoded again, denoised a little at the big size) starts from one. The audio
latent is cut or padded with silence to the video's length (24 fps frames 17k+5 <-> 40 audio latent frames a second).
"""
from collections import OrderedDict

import torch

import comfy.nested_tensor

FPS, AUDIO_LATENT_FPS = 24, 40


class RemiqoraH3ConcatAV:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video_latent": ("LATENT",), "audio_latent": ("LATENT",)}}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "concat"
    CATEGORY = "latent/minimax"

    def concat(self, video_latent, audio_latent):
        video = video_latent["samples"]
        audio = audio_latent["samples"]
        frames = (video.shape[2] - 2) // 5 * 17 + 5
        audio_t = round(frames / FPS * AUDIO_LATENT_FPS)
        if audio.shape[-1] >= audio_t:
            audio = audio[..., :audio_t]
        else:
            audio = torch.cat([audio, torch.zeros(*audio.shape[:-1], audio_t - audio.shape[-1], device=audio.device, dtype=audio.dtype)], dim=-1)
        return ({"samples": comfy.nested_tensor.NestedTensor((video.to(audio.device), audio))},)


# The text-encoder pass ahead of a run's scenes (graphs.text_part, jobs.encode_ahead): each scene's H3 conditioning,
# by a key the studio makes of its inputs. Not ComfyUI's cache: under RAM pressure that drops whatever the graph being
# run doesn't use (measured 2026-11-05: the next scene's model load evicted the other scenes' conditionings). Measured:
# 0.4 MB a text-only scene, ~20 MB one with a start frame (the TE's image tokens); the oldest go beyond STORE_MAX, "free" empties it (h3worker.py).
STORE: "OrderedDict[str, list]" = OrderedDict()
STORE_MAX = 32


class RemiqoraKeep:
    """An output node (ComfyUI runs only what an output needs): the conditioning into STORE under `key`."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"conditioning": ("CONDITIONING",), "key": ("STRING", {"default": ""})}}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")   # always: STORE may have been emptied since ComfyUI cached this node

    RETURN_TYPES = ()
    FUNCTION = "keep"
    OUTPUT_NODE = True
    CATEGORY = "conditioning/minimax"

    def keep(self, conditioning, key):
        STORE[key] = conditioning
        STORE.move_to_end(key)
        while len(STORE) > STORE_MAX:
            STORE.popitem(last=False)
        size = sum(c[0].numel() * c[0].element_size() for c in conditioning if isinstance(c[0], torch.Tensor))
        print(f"[remiqora] conditioning {key[:10]} kept ahead: {size / 2 ** 20:.1f} MB, {len(STORE)} kept", flush=True)
        return {}


class RemiqoraH3Cond:
    """MiniMaxH3ImageToVideo with a STORE key: the conditioning from STORE when it is there (the TE, the VAE and the
    start frame - lazy inputs - are not touched then), else the core node's own work. The latent is the core's empty
    AV latent either way, so a scene shot through here is the scene shot without it."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"key": ("STRING", {"default": ""}), "clip": ("CLIP", {"lazy": True}), "vae": ("VAE", {"lazy": True}),
                             "prompt": ("STRING", {"multiline": True}), "width": ("INT", {"default": 1344, "min": 32, "max": 16384}),
                             "height": ("INT", {"default": 768, "min": 32, "max": 16384}), "length": ("INT", {"default": 124, "min": 5, "max": 3600})},
                "optional": {"first_frame": ("IMAGE", {"lazy": True})}}

    RETURN_TYPES = ("CONDITIONING", "LATENT")
    RETURN_NAMES = ("positive", "latent")
    FUNCTION = "cond"
    CATEGORY = "conditioning/minimax"

    def check_lazy_status(self, key, **kw):
        return [] if key in STORE else [n for n in ("clip", "vae", "first_frame") if n in kw and kw[n] is None]

    def cond(self, key, prompt, width, height, length, clip=None, vae=None, first_frame=None):
        from comfy_extras import nodes_minimax_h3 as h3
        if key in STORE:
            STORE.move_to_end(key)
            latent, _ = h3._empty_av_latent(width, height, length)
            return (STORE[key], latent)
        return tuple(h3.MiniMaxH3ImageToVideo.execute(clip, vae, prompt, width, height, length, first_frame=first_frame).args)


NODE_CLASS_MAPPINGS = {"RemiqoraH3ConcatAV": RemiqoraH3ConcatAV, "RemiqoraKeep": RemiqoraKeep, "RemiqoraH3Cond": RemiqoraH3Cond}
