"""Paths and settings. Machine-specific paths (ComfyUI, its model config, LoRA, llama-server, rtx_vsr) come from .env; see .env.example."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

_HOME = Path.home()
_LOCAL = Path(os.environ.get("LOCALAPPDATA", _HOME / "AppData" / "Local"))


def _paths(var: str, default: str) -> list[Path]:
    return [Path(p.strip()) for p in os.environ.get(var, default).split(";") if p.strip()]


def engine_python(folder: Path) -> Path:
    """The python of an engine folder: its own venv (H3 Studio's engine/.venv), else the one inside its ComfyUI
    (Comfy Desktop's layout)."""
    own = folder / ".venv" / "Scripts" / "python.exe"
    return own if own.exists() else folder / "ComfyUI" / ".venv" / "Scripts" / "python.exe"


# Phase 7: the engine - ComfyUI's core as a library (<COMFY_DIR>\ComfyUI\comfy) and a python with torch for it.
# H3 Studio's own: engine\ (install.bat: the core at the commit of engine\core.txt, engine\.venv by uv); until it is
# set up - Comfy Desktop's installation, as before
OWN_ENGINE = ROOT / "engine"
_DESKTOP = _LOCAL / "Comfy-Desktop" / "ComfyUI-Installs" / "ComfyUI"
COMFY_DIR = Path(os.environ.get("COMFY_DIR", str(OWN_ENGINE if (OWN_ENGINE / "ComfyUI" / "comfy").is_dir() else _DESKTOP)))
COMFY_PYTHON = Path(os.environ.get("COMFY_PYTHON", str(engine_python(COMFY_DIR))))
COMFY_INPUT = Path(os.environ.get("COMFY_INPUT", str(ROOT / "data" / "comfy" / "input")))
COMFY_OUTPUT = Path(os.environ.get("COMFY_OUTPUT", str(ROOT / "data" / "comfy" / "output")))

# Phase 7: every model shoots in our own worker (h3worker.py: ComfyUI's core as a library, no server). It finds the
# weights in these roots' diffusion_models / text_encoders / vae / loras (unet / clip too); H3_REF_DIR and LORA_DIRS
# are added to them - no extra_model_paths yaml. By default one folder beside the app (the installer writes its own
# into .env); every other folder below defaults to a place inside the first root.
H3_MODEL_ROOTS = _paths("H3_MODEL_ROOTS", str(ROOT / "models"))
MODELS = H3_MODEL_ROOTS[0] if H3_MODEL_ROOTS else ROOT / "models"

# H3 files (names only; ComfyUI finds them through its model paths). The default is the official model (Comfy-Org's
# repack of MiniMaxAI/MiniMax-H3) with its 8-step turbo LoRA; a fine-tune with the speed-up built in («TURBO»
# in its name) shoots without that LoRA (graphs.h3_turbo_lora)
H3_UNET = os.environ.get("H3_UNET", "minimax_h3_fl2va_pruned_int8_convrot.safetensors")
H3_TURBO_LORA = os.environ.get("H3_TURBO_LORA", "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors")
H3_CLIP = os.environ.get("H3_CLIP", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors")
H3_VAE = os.environ.get("H3_VAE", "minimax_h3_video_vae_fp16.safetensors")
H3_AUDIO_VAE = os.environ.get("H3_AUDIO_VAE", "minimax_h3_audio_vae_fp32.safetensors")
# Ref2VA: the hero held by a reference photo (official H3 ref2va weights + its 4-step turbo LoRA). Where they lie is
# added to ComfyUI's model paths (diffusion_models/, loras/ under it).
H3_REF_UNET = os.environ.get("H3_REF_UNET", "minimax_h3_ref2va_pruned_int8_convrot.safetensors")
H3_REF_LORA = os.environ.get("H3_REF_LORA", "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors")
H3_REF_DIR = Path(os.environ.get("H3_REF_DIR", str(MODELS)))

# Phase 10: the other models, on the same worker (names only; the worker finds them in the model roots' sub-folders,
# checkpoints/ and latent_upscale_models/ too). WAN 2.2 5B - picture only; LTX 2.5 - picture and its own sound;
# LTX 2.3 - picture and sound, or the picture to a given track (ia2v: music videos, singing).
WAN_UNET = os.environ.get("WAN_UNET", "wan2.2_ti2v_5B_fp16.safetensors")
WAN_CLIP = os.environ.get("WAN_CLIP", "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
WAN_VAE = os.environ.get("WAN_VAE", "wan2.2_vae.safetensors")
# FastWan (FastVideo's distillation of WAN 2.2 5B as a LoRA, Kijai's repack): 8 steps at CFG 1 instead of 20 at CFG 5
WAN_FAST_LORA = os.environ.get("WAN_FAST_LORA", "Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors")
LTX25_UNET = os.environ.get("LTX25_UNET", "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors")
LTX25_CLIP = os.environ.get("LTX25_CLIP", "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors")
LTX25_VAE = os.environ.get("LTX25_VAE", "ltx-2.5-video-vae-bf16.safetensors")
LTX25_AUDIO_VAE = os.environ.get("LTX25_AUDIO_VAE", "ltx-2.5-audio-vae-bf16.safetensors")
LTX25_UPSCALER = os.environ.get("LTX25_UPSCALER", "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors")
LTX23_CKPT = os.environ.get("LTX23_CKPT", "ltx-2.3-22b-dev-fp8.safetensors")
LTX23_CLIP = os.environ.get("LTX23_CLIP", "gemma_3_12B_it_fp4_mixed.safetensors")
LTX23_LORA = os.environ.get("LTX23_LORA", "ltx_2.3_22b_distilled_1.1_lora_dynamic_fro09_avg_rank_111_bf16.safetensors")
LTX23_UPSCALER = os.environ.get("LTX23_UPSCALER", "ltx-2.3-spatial-upscaler-x2-1.1.safetensors")

# The style LoRA, each model its own folders (loras.py): the worker sees them with the other LoRA folders
LORA_DIRS = _paths("LORA_DIRS", str(MODELS / "loras" / "h3"))
LTX23_LORA_DIRS = _paths("LTX23_LORA_DIRS", str(MODELS / "loras" / "ltx23"))
LTX25_LORA_DIRS = _paths("LTX25_LORA_DIRS", str(MODELS / "loras" / "ltx25"))
WAN_LORA_DIRS = _paths("WAN_LORA_DIRS", str(MODELS / "loras" / "wan5b"))   # WAN 2.2 5B's (FastWan has its own slot)
WORKER_LOG = Path(os.environ.get("WORKER_LOG", str(ROOT / "data" / "h3worker.log")))
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")   # on PATH by default (winget's Gyan.FFmpeg)
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
RIFE_BIN = Path(os.environ.get("RIFE_BIN", str(ROOT / "tools" / "rife" / "rife-ncnn-vulkan.exe")))
RIFE_MODEL = os.environ.get("RIFE_MODEL", "rife-v4.6")   # a folder beside the exe
RTX_VSR = Path(os.environ.get("RTX_VSR", str(ROOT / "tools" / "rtxvsr" / "rtx_vsr.exe")))
# Phase 11: the words of a song (Demucs + faster-whisper), tools/lyrics, in the engine's environment (engine\.venv has
# them since 2026-10-23); LYRICS_PYTHON can point to another environment with them
LYRICS_TOOL_DIR = ROOT / "tools" / "lyrics"
LYRICS_PYTHON = Path(os.environ.get("LYRICS_PYTHON", str(LYRICS_TOOL_DIR / ".venv" / "Scripts" / "python.exe")))
LYRICS_MODEL = os.environ.get("LYRICS_MODEL", "large-v3")
# Krea 2, the pictures (the graph's «Картинка», a clip's singer): on the video models' worker, its weights in the same
# folders (diffusion_models, text_encoders, vae under H3_MODEL_ROOTS), its LoRA in KREA_LORA_DIRS (the worker sees them
# with the other LoRA folders). sd.cpp drew them until an A/B test on 2026-10-23
KREA_UNET = os.environ.get("KREA_UNET", "krea2_turbo_int8_convrot.safetensors")
KREA_CLIP = os.environ.get("KREA_CLIP", "qwen3vl_4b_fp8_scaled.safetensors")
KREA_VAE = os.environ.get("KREA_VAE", "qwen_image_vae.safetensors")
KREA_LORA_DIRS = _paths("KREA_LORA_DIRS", str(MODELS / "loras" / "krea2"))
# FLUX.2 Klein 4B (Apache-2.0; the 9B is non-commercial), the picture-by-reference model: a scene's start frame from the
# hero's photo in the scene's place (frames.py). Its text encoder is Z-Image's Qwen3 4B (the same file, CLIPLoader "flux2").
FLUX2_UNET = os.environ.get("FLUX2_UNET", "flux-2-klein-4b.safetensors")
FLUX2_CLIP = os.environ.get("FLUX2_CLIP", "qwen_3_4b_fp8_mixed.safetensors")
FLUX2_VAE = os.environ.get("FLUX2_VAE", "flux2-vae.safetensors")
FLUX2_LORA_DIRS = _paths("FLUX2_LORA_DIRS", str(MODELS / "loras" / "flux2"))   # its LoRA (loras.py, the «Картинка» node)
# the picture models' parameters («Модели и настройки» → Параметры; settings.py keeps them like the weights)
KREA_STEPS = int(os.environ.get("KREA_STEPS", "8"))          # Krea 2 Turbo: 8 without CFG
FLUX2_STEPS = int(os.environ.get("FLUX2_STEPS", "4"))        # FLUX.2 Klein distilled: 4
FRAME_FACE_MIN = float(os.environ.get("FRAME_FACE_MIN", "0.3"))   # frames.py: SFace cosine frame ↔ photo below this - not the hero
FRAME_TRIES = int(os.environ.get("FRAME_TRIES", "3"))        # frames.py: seeds tried for a face that doesn't pass


def _lmstudio_models() -> str:
    """Where LM Studio downloads models (`downloadsFolder` in its settings.json): what is fetched there is offered here too."""
    try:
        folder = json.loads((_HOME / ".lmstudio" / "settings.json").read_text(encoding="utf-8")).get("downloadsFolder")
    except (OSError, ValueError):
        folder = None
    return folder or str(_HOME / ".lmstudio" / "models")


# The writer: our own llama-server (llama.cpp) per LLM job, as in Remiqora; LM Studio itself is not needed.
# Windows' Smart App Control may block an unsigned llama.cpp build at any time («Bad Image», 0xc0e90002), even an
# official release, so it is looked for in this order: LLAMA_SERVER_BIN (.env, «Модели и настройки»), tools/llama
# (with its DLLs beside it), the CUDA engine of an installed LM Studio (signed; LM Studio itself need not run).
# Nothing found: tools/llama, for the message.
# GGUF files are looked for in every LLM_DIRS folder, sub-folders included; an mmproj (the part that sees pictures) is
# paired by folder or by name.
def _llama_server() -> Path:
    ours = ROOT / "tools" / "llama" / "llama-server.exe"
    lms = list((_HOME / ".lmstudio" / "extensions" / "backends").glob("llama.cpp-win-x86_64-nvidia-cuda*/llama-server.exe"))
    return ours if ours.exists() or not lms else max(lms, key=lambda f: f.stat().st_mtime)   # LM Studio's newest


LLAMA_SERVER_BIN = Path(os.environ["LLAMA_SERVER_BIN"]) if os.environ.get("LLAMA_SERVER_BIN") else _llama_server()
LLM_DIRS = _paths("LLM_DIRS", f"{MODELS / 'llm'};{_lmstudio_models()}")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma-4-E4B")   # the default: the first model whose file name contains this
LLM_PORT = int(os.environ.get("LLM_PORT", "8191"))
LLM_CTX = int(os.environ.get("LLM_CTX", "16384"))

OUTPUT_DIR = ROOT / "outputs"
DATA_DIR = ROOT / "data"
LLM_LOG = DATA_DIR / "llama-server.log"
LLM_CACHE = DATA_DIR / "cache" / "llm"   # answers by a hash of the whole request

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8810"))

for d in (OUTPUT_DIR, DATA_DIR, COMFY_INPUT, COMFY_OUTPUT, LLM_CACHE):
    d.mkdir(parents=True, exist_ok=True)
