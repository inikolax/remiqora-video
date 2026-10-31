"""Lyrics from a song: Demucs separates the vocals, faster-whisper writes down
the words with their times. Runs in the engine's environment (engine/.venv), as
its own process (app/song.py starts it), so the GPU memory is given back when
it exits.

    python lyrics_worker.py SONG OUT_DIR [--model large-v3] [--language ru]
    python lyrics_worker.py CLIP OUT_DIR --vocals-only     (only vocals.wav: a scene's voice)

Writes OUT_DIR/vocals.wav and OUT_DIR/lyrics.json:
    {"version", "model", "language", "seconds",
     "lines": [{"start", "end", "text", "words": [{"start", "end", "word", "p"}]}]}
Times are in the song's own time (seconds from its start). Progress goes to
stdout as JSON lines {"stage": ..., "message": ...}, errors as {"error": ...}.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf
import torch  # first: its CUDA libraries (cuBLAS, cuDNN) are what ctranslate2 needs too

# H3 Studio's engine environment (engine/) has torch for CUDA 13 and CUDA 12's cuBLAS as a pip package for ctranslate2:
# its DLL folder, when it is there (cuDNN 9 is torch's: CUDA 12's in the path breaks Demucs - a sublibrary mismatch)
for _bin in (Path(sys.prefix) / "Lib" / "site-packages" / "nvidia").glob("cublas/bin"):
    os.add_dll_directory(str(_bin))
    os.environ["PATH"] = str(_bin) + os.pathsep + os.environ.get("PATH", "")

VERSION = 1
LINE_GAP_S = 0.6       # a pause in the voice this long starts a new line
LINE_MAX_WORDS = 12    # ...and a line this long is split at its biggest pause
WORD_MAX_S = 2.5       # a held note is fine, but Whisper sometimes stretches one word over 16 s
NO_SPEECH_MAX = 0.8    # a segment Whisper itself thinks is silence ("Продолжение следует..." had 0.89;
                       # real sung lines 0.16-0.61)
# What Whisper writes over silence - it learnt it from video subtitles.
HALLUCINATIONS = (r"субтитр|продолжение следует|спасибо за просмотр|подписывайтесь|редактор|корректор|"
                  r"dimatorzok|amara\.org|subtitles by|thanks for watching|thank you for watching")


def say(**kw) -> None:
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def load_audio(path: Path, sr: int) -> np.ndarray:
    """Any audio file -> float32 (2, n) at `sr` through ffmpeg."""
    ffmpeg = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
    proc = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"],
                          capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not decode {path}: {proc.stderr.decode(errors='replace')[-500:]}")
    return np.frombuffer(proc.stdout, np.float32).reshape(-1, 2).T.copy()


def separate(song: Path, out: Path) -> Path:
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    say(stage="separate", message="Demucs: separating the vocals")
    model = get_model("htdemucs").cuda().eval()
    wav = torch.from_numpy(load_audio(song, model.samplerate))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        sources = apply_model(model, ((wav - mean) / std)[None].cuda(), split=True, overlap=0.25, progress=False)[0]
    vocals = (sources[model.sources.index("vocals")] * std + mean).cpu().numpy().T
    path = out / "vocals.wav"
    sf.write(path, vocals, model.samplerate)
    del model, sources
    torch.cuda.empty_cache()
    return path


def _starts_line(word: str) -> bool:
    """Whisper writes each sung line with a capital letter, even with no pause
    before it ("... под откос Полчаса, не твоя полоса Полчаса ..."); "I"-like
    one-letter words don't count."""
    letters = word.lstrip("\"'«(—-")
    return len(letters) > 1 and letters[0].isupper()


def _lines(words: list[dict]) -> list[dict]:
    """Words -> lines at pauses and capitals; an overlong line is split at its
    biggest pause. Word lengths are capped first (WORD_MAX_S)."""
    for w in words:
        w["end"] = round(min(w["end"], w["start"] + WORD_MAX_S), 3)
    lines, cur = [], []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] >= LINE_GAP_S or _starts_line(w["word"])):
            lines.append(cur)
            cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    out = []
    todo = lines[::-1]
    while todo:
        line = todo.pop()
        if len(line) > LINE_MAX_WORDS:
            k = max(range(1, len(line)), key=lambda i: line[i]["start"] - line[i - 1]["end"])
            todo += [line[k:], line[:k]]
            continue
        out.append({"start": line[0]["start"], "end": line[-1]["end"],
                    "text": " ".join(w["word"] for w in line), "words": line})
    return out


def _loudest(audio: np.ndarray, sr: int = 16000, seconds: int = 30) -> np.ndarray:
    """The 30 s of the vocals track where the voice is loudest."""
    n = len(audio) // sr
    rms = np.sqrt((audio[:n * sr].astype(np.float64) ** 2).reshape(n, sr).mean(axis=1))  # per second
    if n <= seconds:
        return audio
    best = int(np.argmax(np.convolve(rms, np.ones(seconds), "valid")))
    return audio[best * sr:(best + seconds) * sr]


def load_whisper(model_name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device="cuda", compute_type="float16")


def transcribe(vocals: Path, model, language: str | None) -> tuple[list[dict], str]:
    """Two passes over the vocals, merged. Measured on two songs (2026-09-28):
    - no VAD: Silero is made for speech and took most of the singing for silence
      ("Тридцать лет": 37 words with it, 295 - nearly all - without);
    - but without it Whisper itself skips some windows it thinks are empty
      ("30 минут": the middle verse lost); a pass with the default VAD finds
      that verse, and its words fill the gaps of the first pass.
    The language is detected on the loudest 30 s of the vocals: Whisper's own
    guess from the first 30 s (an instrumental intro) said "en" for a Russian
    song - and then translated it."""
    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(vocals), sampling_rate=16000)
    if not language:
        language, _, _ = model.detect_language(_loudest(audio))
    common = dict(language=language, task="transcribe", word_timestamps=True, beam_size=5,
                  condition_on_previous_text=False)  # one misheard line doesn't drag the next ones along

    def keep(segments) -> list:
        return [s for s in segments
                if s.no_speech_prob <= NO_SPEECH_MAX and not re.search(HALLUCINATIONS, s.text, re.I)]

    def words_of(segments) -> list[dict]:
        return [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip(), "p": round(w.probability, 3)}
                for s in segments for w in (s.words or []) if w.word.strip()]

    say(stage="transcribe", message="Whisper: recognising the words (pass 1 of 2)")
    main = keep(model.transcribe(audio, vad_filter=False, **common)[0])
    say(stage="transcribe", message="Whisper: recognising the words (pass 2 of 2)")
    # The default VAD (not a softer one: that one missed the same verse) - it only fills gaps.
    extra = keep(model.transcribe(audio, vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
                                  **common)[0])
    busy = [(s.start - 0.3, s.end + 0.3) for s in main]
    words = words_of(main) + [w for w in words_of(extra)  # word by word: only where pass 1 heard nothing
                              if not any(a <= (w["start"] + w["end"]) / 2 <= b for a, b in busy)]
    words.sort(key=lambda w: w["start"])
    return _lines(words), language


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("song", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--language", default=None, help="e.g. ru; default: detected")
    ap.add_argument("--vocals-only", action="store_true", help="only OUT_DIR/vocals.wav, no words (a scene's voice)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available to torch in the lyrics environment")
        if args.vocals_only:
            separate(args.song, args.out)
            say(stage="done", message=f"vocals in {time.time() - t0:.1f} s")
            return 0
        # Whisper's 3 GB are read from disk while Demucs works (~3 s of ~20, measured 2026-10-06)
        say(stage="load", message=f"Whisper {args.model}: loading (the first time it is downloaded, ~3 GB)")
        with ThreadPoolExecutor(1) as pool:
            whisper = pool.submit(load_whisper, args.model)
            vocals = separate(args.song, args.out)
            t_sep = time.time() - t0
            model = whisper.result()
        lines, language = transcribe(vocals, model, args.language)
    except Exception as exc:  # noqa: BLE001 - reported to the caller as JSON
        say(error=f"{type(exc).__name__}: {exc}")
        return 1
    result = {"version": VERSION, "model": args.model, "language": language,
              "seconds": {"separate": round(t_sep, 1), "total": round(time.time() - t0, 1)}, "lines": lines}
    (args.out / "lyrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    say(stage="done", message=f"{len(lines)} lines, {sum(len(l['words']) for l in lines)} words", lines=len(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
