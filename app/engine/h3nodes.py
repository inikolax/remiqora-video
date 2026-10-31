"""Our own ComfyUI nodes for the worker (h3worker.py registers them after the core's; ComfyUI's modules are on
sys.path there, so `comfy.*` imports resolve).

RemiqoraH3ConcatAV: a video latent (VAEEncode with the H3 video VAE: [B, 24, T, H/16, W/16]) and an audio latent
(VAEEncodeAudio with the H3 audio VAE: [B, 32, 2, T40]) as the joint AV latent the H3 model samples - the pair
comfy_extras/nodes_minimax_h3.py builds empty. The core has no node for it, and a second pass of H3 (graphs.scene,
pass2: the first pass decoded, scaled up, encoded again, denoised a little at the big size) starts from one. The audio
latent is cut or padded with silence to the video's length (24 fps frames 17k+5 <-> 40 audio latent frames a second).
"""
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


NODE_CLASS_MAPPINGS = {"RemiqoraH3ConcatAV": RemiqoraH3ConcatAV}
