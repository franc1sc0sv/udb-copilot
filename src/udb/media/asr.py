"""Speech to text on the GPU with faster-whisper. Local only: `asr` extra and CUDA.

Measured on Spanish class videos with human subtitles (RTX 5080, 2026-10-21):

  large-v3, sequential, beam 5, no previous-text context   2.5 % WER, 15x real time
  turbo, same settings                                      2.7 %,      42x
  large-v3 + previous-text context                          4.7 %,       9x
  large-v3, beam 10, patience 2 + context                   6.0 %,       8x
  batched decoding (any model)                              3.2-4.1 %, drops words

A vocabulary prompt made Whisper skip whole passages, so there is none. `model:
turbo` in recordings.yaml trades 0.2 points of WER for 3x speed.
"""
import json
import shutil
import subprocess
from pathlib import Path

from ..core.paths import load_yaml
from ..vault import index

MODELS = {"large": "large-v3", "turbo": "large-v3-turbo", "medium": "medium"}
# Whisper invents text when audio goes quiet or degrades: retry at higher temperature
# and drop attempts that come out too repetitive or too unlikely.
TEMPERATURES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
REPETITION_THRESHOLD = 1.35
LOGPROB_THRESHOLD = -1.0
NO_SPEECH_THRESHOLD = 0.6
BEAM = 5


def config() -> dict:
    cfg = load_yaml("recordings.yaml")
    return {"model": cfg.get("model", "large"), "ffmpeg": cfg.get("ffmpeg")}


def ffmpeg_bin() -> str:
    pinned = config().get("ffmpeg")
    if pinned and Path(pinned).exists():
        return str(pinned)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg is missing. Install it (apt install ffmpeg) or set "
                       "'ffmpeg' in config/recordings.yaml")


def load_audio(source: Path):
    """16 kHz mono float32. An array, not a path: recent PyAV rejects the options
    faster-whisper passes to open()."""
    import numpy as np
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(source), "-vn", "-ac", "1",
                          "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def preload_cuda_libs() -> None:
    """CTranslate2 needs cuBLAS 12 and cuDNN 9; the pip wheels (nvidia-cublas-cu12,
    nvidia-cudnn-cu12) are not on the loader path, so load them once by hand."""
    import ctypes
    import glob
    import site

    for pattern in ("nvidia/cublas/lib/libcublas*.so.12", "nvidia/cudnn/lib/libcudnn*.so.9"):
        for base in site.getsitepackages():
            for lib in sorted(glob.glob(f"{base}/{pattern}")):
                try:
                    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


def transcribe(source_path: Path, subject: str, source_id: str, model: str | None = None) -> Path:
    model = model or config()["model"]
    if model not in MODELS:
        raise ValueError(f"unknown model: {model} (use {', '.join(MODELS)})")
    preload_cuda_libs()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("transcription needs: uv tool install 'udb-copilot[asr]'") from exc
    whisper = WhisperModel(MODELS[model], device="cuda", compute_type="float16")
    segments, info = whisper.transcribe(
        load_audio(source_path), language="es", beam_size=BEAM, best_of=5,
        temperature=TEMPERATURES, compression_ratio_threshold=REPETITION_THRESHOLD,
        log_prob_threshold=LOGPROB_THRESHOLD, no_speech_threshold=NO_SPEECH_THRESHOLD,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 500}, word_timestamps=True,
        condition_on_previous_text=False)
    rows = [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
            for s in segments if s.text.strip()]
    out = index.transcript_file(subject, source_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"source_id": source_id, "language": info.language,
                               "model": MODELS[model], "segments": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    return out

