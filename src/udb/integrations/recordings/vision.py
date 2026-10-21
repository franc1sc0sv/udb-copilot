"""Read class boards and slides from video stills with a local vision model.

Qwen3-VL-4B (bf16, about 9 GB of VRAM) won the benchmark on real class boards:
182 of 183 formulas compiled and the boards checked by eye were exact, at about
5 s per still on an RTX 5080; PaddleOCR-VL was slower and split formulas, and
RapidOCR cannot read math. Local only: needs the `vision` extra and a GPU.

What the model writes is the teacher's board, not the teacher's words: the
text is indexed like a figure and descriptions of drawings start with
"Figura:" so notes never quote them as something the teacher said.
"""
import re

from .frames import _write_index, frame_index, frames_dir

MODEL = "Qwen/Qwen3-VL-4B-Instruct"
PROMPT = ("Transcribe everything the teacher wrote or showed on this class board or slide, "
          "top to bottom, in Spanish as it appears. Every formula in LaTeX between \\( \\) or "
          "\\[ \\]. Keep the teacher's own notation and step numbers (circled numbers, arrows "
          "that show a substitution). Ignore logos, watermarks, webcam tiles, participant "
          "names, menus and the mouse pointer. If there is a drawn figure (free-body diagram, "
          "triangle, graph, network diagram, table), describe it after the text in one "
          "paragraph starting with 'Figura:' with its labels and values; if there is none, "
          "write nothing about figures. Do not solve or explain anything.")
SPANISH_FUNCS = {"sen": "sen", "tg": "tg", "arcsen": "arcsen", "senh": "senh"}
NO_FIGURE_RE = re.compile(r"^\s*Figura:\s*(no hay|ninguna|sin)\b.*$", re.I | re.M)


def clean(text: str) -> str:
    """Spanish trig names are not TeX commands; they would render as errors."""
    for name in SPANISH_FUNCS:
        text = re.sub(rf"\\{name}(?![a-zA-Z])", rf"\\operatorname{{{name}}}", text)
    return NO_FIGURE_RE.sub("", text).strip()


class Reader:
    def __init__(self, model: str = MODEL):
        try:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor
        except ImportError as exc:
            raise RuntimeError("board reading needs: uv tool install 'udb-copilot[vision]'") from exc
        if not torch.cuda.is_available():
            raise RuntimeError("board reading needs a CUDA GPU (local only)")
        self.torch = torch
        self.model = AutoModelForImageTextToText.from_pretrained(
            model, torch_dtype=torch.bfloat16, device_map="cuda").eval()
        self.proc = AutoProcessor.from_pretrained(model)

    def read(self, image_path: str) -> str:
        msgs = [{"role": "user", "content": [{"type": "image", "image": image_path},
                                             {"type": "text", "text": PROMPT}]}]
        inputs = self.proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True,
                                               return_dict=True, return_tensors="pt"
                                               ).to(self.model.device)
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=1200, do_sample=False)
        return clean(self.proc.decode(out[0][inputs["input_ids"].shape[-1]:],
                                      skip_special_tokens=True))


BRANDING_RE = re.compile(r"udb\s*virtual|universidad\s+don\s+bosco|vitam\s+impendere|el\s+salvador",
                         re.I)


def is_branding(text: str) -> bool:
    """Intro and outro cards: only the university's name and logo, nothing taught."""
    rest = BRANDING_RE.sub("", text)
    return bool(BRANDING_RE.search(text)) and len(re.sub(r"\W+", "", rest)) < 12


def read_frames(subject: str, source_id: str, only_complete: bool = True,
                reader: Reader | None = None) -> int:
    """Fill each frame's text. Growth stills are skipped unless asked: the complete
    board before an erase already contains them."""
    frames = frame_index(subject, source_id)
    folder = frames_dir(subject, source_id)
    reader = reader or Reader()
    done = 0
    for f in frames:
        if only_complete and f.get("kind") == "growth":
            continue
        text = reader.read(str(folder / f["file"]))
        if is_branding(text):
            f["kind"], text = "branding", ""
        f["text"] = text
        done += 1
    _write_index(subject, source_id, frames)
    return done
