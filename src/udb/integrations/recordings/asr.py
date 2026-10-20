"""Speech to text on the GPU (Whisper). Local only: needs the `asr` extra and CUDA.

Tries faster-whisper first and falls back to transformers, which supports
cards CTranslate2 does not cover yet (Blackwell, for example).
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ...core.paths import get_subject, load_yaml
from ...vault import index

MODELS = {
    "medium": {"faster": "medium", "hf": "openai/whisper-medium"},
    "large": {"faster": "large-v3", "hf": "openai/whisper-large-v3"},
    "turbo": {"faster": "large-v3-turbo", "hf": "openai/whisper-large-v3-turbo"},
}
QUALITY = {"maxima": "max", "rapida": "fast", "max": "max", "fast": "fast"}

# Whisper invents text when audio goes quiet or degrades. The defence is not a
# bigger model: retry at higher temperature and drop attempts that come out
# too repetitive or too unlikely.
TEMPERATURES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
REPETITION_THRESHOLD = 1.35
LOGPROB_THRESHOLD = -1.0
NO_SPEECH_THRESHOLD = 0.6


def config() -> dict:
    cfg = load_yaml("recordings.yaml")
    return {"model": cfg.get("model", cfg.get("modelo", "large")),
            "quality": QUALITY.get(cfg.get("quality", cfg.get("calidad", "max")), "max"),
            "backend": cfg.get("backend", "auto"),
            "compute_type": cfg.get("compute_type", "float16"),
            "beam_size": cfg.get("beam_size", 5), "batch_size": cfg.get("batch_size", 8),
            "ffmpeg": cfg.get("ffmpeg")}


def ffmpeg_bin() -> str:
    pinned = config().get("ffmpeg")
    if pinned and Path(pinned).exists():
        return str(pinned)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("ffmpeg is missing. Install it (apt install ffmpeg) or set "
                       "'ffmpeg' in config/recordings.yaml")


def expose_ffmpeg() -> None:
    """transformers calls ffmpeg itself and only looks in PATH."""
    import os
    folder = str(Path(ffmpeg_bin()).parent)
    if folder not in os.environ.get("PATH", ""):
        os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")


def read_wav(wav: Path) -> dict:
    import soundfile as sf

    data, rate = sf.read(str(wav), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return {"raw": data, "sampling_rate": rate}


def to_wav(source: Path) -> Path:
    """16 kHz mono, what Whisper expects."""
    out = Path(tempfile.gettempdir()) / f"{source.stem}.16k.wav"
    subprocess.run([ffmpeg_bin(), "-y", "-i", str(source), "-vn", "-ar", "16000", "-ac", "1",
                    str(out)], check=True, capture_output=True)
    return out


def prompt_for(subject: str) -> str:
    try:
        vocabulary = get_subject(subject).get("asr_vocabulary", "")
    except KeyError:
        vocabulary = ""
    base = "Clase universitaria en español de El Salvador."
    return f"{base} Términos: {vocabulary}." if vocabulary else base


def run_faster(wav: Path, model: str, subject: str, best: bool) -> dict:
    from faster_whisper import WhisperModel

    cfg = config()
    whisper = WhisperModel(MODELS[model]["faster"], device="cuda",
                           compute_type=cfg["compute_type"])
    segments, info = whisper.transcribe(
        str(wav), language="es", beam_size=10 if best else cfg["beam_size"], best_of=5,
        patience=2.0 if best else 1.0, temperature=TEMPERATURES,
        compression_ratio_threshold=REPETITION_THRESHOLD, log_prob_threshold=LOGPROB_THRESHOLD,
        no_speech_threshold=NO_SPEECH_THRESHOLD, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500}, word_timestamps=True,
        initial_prompt=prompt_for(subject),
        # Previous-text context chains long sentences better; the repetition
        # cut above keeps one error from propagating.
        condition_on_previous_text=best)
    return {"language": info.language,
            "segments": [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
                         for s in segments if s.text.strip()]}


def run_transformers(wav: Path, model: str, subject: str, best: bool) -> dict:
    """Best quality does not chunk the audio: chunks cut sentences in half."""
    import torch
    from transformers import pipeline

    expose_ffmpeg()
    options = dict(task="automatic-speech-recognition", model=MODELS[model]["hf"],
                   torch_dtype=torch.float16, device="cuda:0")
    if not best:
        options.update(chunk_length_s=30, batch_size=config()["batch_size"])
    pipe = pipeline(**options)
    generate = {"language": "spanish", "task": "transcribe"}
    if best:
        generate.update(num_beams=5, condition_on_prev_tokens=True, temperature=TEMPERATURES,
                        compression_ratio_threshold=REPETITION_THRESHOLD,
                        logprob_threshold=LOGPROB_THRESHOLD,
                        no_speech_threshold=NO_SPEECH_THRESHOLD)
    raw = pipe(read_wav(wav), return_timestamps=True, generate_kwargs=generate)
    segments = []
    for ch in raw.get("chunks", []):
        ts = ch.get("timestamp") or (None, None)
        if ts[0] is None or not ch.get("text", "").strip():
            continue
        segments.append({"start": float(ts[0]), "end": float(ts[1] if ts[1] is not None else ts[0]),
                         "text": ch["text"].strip()})
    return {"language": "es", "segments": segments}


def transcribe(source_path: Path, subject: str, source_id: str, model: str | None = None,
               backend: str | None = None, quality: str | None = None) -> Path:
    cfg = config()
    model = model or cfg["model"]
    backend = backend or cfg["backend"]
    quality = QUALITY.get(quality or cfg["quality"])
    if model not in MODELS:
        raise ValueError(f"unknown model: {model} (use {', '.join(MODELS)})")
    if quality is None:
        raise ValueError("quality must be 'max' or 'fast'")
    best = quality == "max"
    wav = to_wav(source_path)
    try:
        if backend in ("auto", "faster"):
            try:
                raw, used = run_faster(wav, model, subject, best), "faster-whisper"
            except Exception as exc:  # noqa: BLE001 - fall back on any engine failure
                if backend == "faster":
                    raise
                print(f"  faster-whisper did not start ({type(exc).__name__}); using transformers")
                raw, used = run_transformers(wav, model, subject, best), "transformers"
        else:
            raw, used = run_transformers(wav, model, subject, best), "transformers"
    finally:
        wav.unlink(missing_ok=True)
    out = index.transcript_file(subject, source_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"source_id": source_id, "language": raw.get("language", "es"),
                               "model": MODELS[model]["faster"], "backend": used,
                               "quality": quality, "segments": raw["segments"]},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    return out
