"""Read class boards and slides from video stills with a local vision model.

Benchmarked on real class stills (AVM, CDP; formulas, free-body diagrams,
handwriting on paper) against hand-written facts, RTX 5080, 2026-10-21:

  Qwen3-VL-4B, default resolution, no context      0.59   15 s/still
  + native resolution                               0.65   11 s
  + what the teacher said around that moment        0.85    8 s
  Qwen3-VL-4B-Thinking, native res + context        0.98   92 s

So every still is read fast with the teacher's words as context, and only stills
with a drawn figure get a second, reasoning pass (where the fast model mixed up
which side of a triangle or which axis an angle is measured from). PaddleOCR-VL
was slower and split formulas; RapidOCR cannot read math. Local only: needs the
`vision` extra and a GPU.

What the model writes is the teacher's board, not the teacher's words: the
text is indexed like a figure and descriptions of drawings start with
"Figura:" so notes never quote them as something the teacher said.
"""
import re

from udb.domain.sources import index
from udb.integrations.media.frames import _write_index, frame_index, frames_dir

FAST = "Qwen/Qwen3-VL-4B-Instruct"
DEEP = "Qwen/Qwen3-VL-4B-Thinking"
NATIVE = {"max_pixels": 1920 * 1088, "min_pixels": 1280 * 720}
CONTEXT_BEFORE, CONTEXT_AFTER = 45.0, 10.0
PROMPT = ("Transcribe everything the teacher wrote or showed on this class board or slide, top "
          "to bottom, in Spanish as it appears. Every formula in LaTeX between \\( \\) or \\[ \\]. "
          "Keep the teacher's own notation and step numbers (circled numbers, arrows that show a "
          "substitution). Ignore logos, watermarks, webcam tiles, participant names, menus and the "
          "mouse pointer. If there is a drawn figure (free-body diagram, triangle, graph, network "
          "diagram, table), describe it after the text in one paragraph starting with 'Figura:'. "
          "For a figure, state only what is drawn: every label, value and unit exactly as written, "
          "what each arrow points to, and which line or axis each angle is measured from. If "
          "something is not legible, say so instead of guessing. Do not solve or explain anything.")
CONTEXT = ("\n\nWhat the teacher was saying at this moment (speech-to-text, may contain errors; "
           "use it only to disambiguate what is drawn, never add facts that are not on the "
           "board):\n«{text}»")
MODEL = FAST
SPANISH_FUNCS = {"sen": "sen", "tg": "tg", "arcsen": "arcsen", "senh": "senh"}
NO_FIGURE_RE = re.compile(r"^\s*Figura:\s*(no hay|ninguna|sin)\b.*$", re.I | re.M)


def clean(text: str) -> str:
    """Spanish trig names are not TeX commands; they would render as errors."""
    for name in SPANISH_FUNCS:
        text = re.sub(rf"\\{name}(?![a-zA-Z])", rf"\\operatorname{{{name}}}", text)
    return NO_FIGURE_RE.sub("", text).strip()


class Reader:
    def __init__(self, model: str = FAST):
        try:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor
        except ImportError as exc:
            raise RuntimeError("board reading needs: uv tool install 'udb-copilot[vision]'") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("board reading needs a CUDA GPU (local only)")
        self.torch = torch
        self.thinking = "Thinking" in model
        self.model = AutoModelForImageTextToText.from_pretrained(
            model, dtype="auto", device_map="cuda").eval()
        self.proc = AutoProcessor.from_pretrained(model, **NATIVE)

    def read(self, image_path: str, said: str = "") -> str:
        prompt = PROMPT + (CONTEXT.format(text=said[:1500]) if said else "")
        msgs = [{"role": "user", "content": [{"type": "image", "image": image_path},
                                             {"type": "text", "text": prompt}]}]
        inputs = self.proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True,
                                               return_dict=True, return_tensors="pt"
                                               ).to(self.model.device)
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=3000 if self.thinking else 1400,
                                      do_sample=False)
        text = self.proc.decode(out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
        return clean(text.split("</think>")[-1])

    def close(self) -> None:
        del self.model
        self.torch.cuda.empty_cache()


def said_around(segments: list[dict], t: float | None) -> str:
    """What the teacher said from 45 s before a still to 10 s after it."""
    if t is None:
        return ""
    return " ".join(s["text"].strip() for s in segments
                    if s.get("end", s["start"]) >= t - CONTEXT_BEFORE
                    and s["start"] <= t + CONTEXT_AFTER)


BRANDING_RE = re.compile(r"udb\s*virtual|universidad\s+don\s+bosco|vitam\s+impendere|el\s+salvador",
                         re.I)


def is_branding(text: str) -> bool:
    """Intro and outro cards: only the university's name and logo, nothing taught."""
    rest = BRANDING_RE.sub("", text)
    return bool(BRANDING_RE.search(text)) and len(re.sub(r"\W+", "", rest)) < 12


def read_frames(subject: str, source_id: str, only_complete: bool = True,
                deep_figures: bool = True) -> int:
    """Fill each frame's text: a fast pass on every complete board with the teacher's
    words as context, then a reasoning pass on the boards that have a drawn figure.
    Growth stills are skipped unless asked: the complete board already contains them."""
    frames = frame_index(subject, source_id)
    folder = frames_dir(subject, source_id)
    segments = index.load_segments(subject, source_id)
    todo = [f for f in frames if not (only_complete and f.get("kind") == "growth")]
    reader = Reader(FAST)
    for f in todo:
        text = reader.read(str(folder / f["file"]), said_around(segments, f.get("t")))
        if is_branding(text):
            f["kind"], text = "branding", ""
        f["text"], f["reader"] = text, FAST
    reader.close()
    figures = [f for f in todo if "Figura:" in f.get("text", "")]
    if deep_figures and figures:
        reader = Reader(DEEP)
        for f in figures:
            f["text"] = reader.read(str(folder / f["file"]), said_around(segments, f.get("t")))
            f["reader"] = DEEP
        reader.close()
    _write_index(subject, source_id, frames)
    return len(todo)
