"""Batch DeepSeek-OCR over rendered page PNGs via mlx-vlm.

Usage: deepseek_ocr.py <pages_dir> <output.md>
Loads the model once, OCRs page-*.png in order, writes one markdown file
with --- page N --- separators.
"""
import glob
import os
import re
import sys
import time

from pathlib import Path

from huggingface_hub import snapshot_download
from mlx_vlm import generate
from mlx_vlm.models.deepseekocr.processing_deepseekocr import DeepseekOCRProcessor
from mlx_vlm.prompt_utils import apply_chat_template
from mlx_vlm.utils import StoppingCriteria, load_config, load_model, load_tokenizer

MODEL = "mlx-community/DeepSeek-OCR-8bit"
PROMPT = "<|grounding|>Convert the document to markdown."

def main(pages_dir, out_path):
    path = Path(snapshot_download(MODEL))
    model = load_model(path)
    # mlx-vlm's load_processor forces trust_remote_code=True, which makes
    # transformers 5 try to import the repo's torch-based custom code and fail;
    # build the processor directly and wrap it the way load_processor would.
    processor = DeepseekOCRProcessor.from_pretrained(str(path), trust_remote_code=False)
    detok_cls = load_tokenizer(path, return_tokenizer=False)
    tok = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    processor.detokenizer = detok_cls(tok)
    eos = getattr(tok, "eos_token_ids", None) or getattr(tok, "eos_token_id", None)
    crit = StoppingCriteria(eos, tok)
    if hasattr(processor, "tokenizer"):
        processor.tokenizer.stopping_criteria = crit
    else:
        processor.stopping_criteria = crit
    config = load_config(path)
    pages = sorted(glob.glob(os.path.join(pages_dir, "page-*.png")))
    parts = []
    for p in pages:
        n = int(re.search(r"page-(\d+)", p).group(1))
        t0 = time.time()
        prompt = apply_chat_template(processor, config, PROMPT, num_images=1)
        res = generate(model, processor, prompt, [p], max_tokens=8192,
                       temperature=0.0, verbose=False)
        text = res.text if hasattr(res, "text") else res
        # strip grounding tags (<|ref|>label<|/ref|><|det|>[[x,y,x,y]]<|/det|>)
        text = re.sub(r"<\|ref\|>.*?<\|/ref\|>|<\|det\|>.*?<\|/det\|>", "", text, flags=re.S)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        parts.append(f"--- page {n} ---\n\n{text}\n")
        print(f"page {n}/{len(pages)} ({time.time()-t0:.1f}s, {len(text)} chars)",
              file=sys.stderr, flush=True)
    with open(out_path, "w") as f:
        f.write("\n".join(parts))
    print(f"wrote {out_path}", file=sys.stderr)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
