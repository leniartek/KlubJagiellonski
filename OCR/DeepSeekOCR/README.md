# DeepSeek-OCR

Second OCR engine for comparison with `../AppleVision/`: [DeepSeek-OCR](https://huggingface.co/deepseek-ai/DeepSeek-OCR)
(open weights, ~3B) running fully locally on Apple Silicon via
[mlx-vlm](https://github.com/Blaizzy/mlx-vlm) and the 8-bit quantization
[mlx-community/DeepSeek-OCR-8bit](https://huggingface.co/mlx-community/DeepSeek-OCR-8bit)
(~5.5 GB RAM).

## Pipeline

```sh
# 1. render PDF pages to PNG (Vision-independent, PDFKit only)
swift OCR/DeepSeekOCR/render_pages.swift SkutkiRegulacji/1006-003.pdf pages/1006-003 200

# 2. OCR the pages to markdown (needs: pip install mlx-vlm)
python3 OCR/DeepSeekOCR/deepseek_ocr.py pages/1006-003 OCR/DeepSeekOCR/Results/1006-003.md
```

Prompt: `<|grounding|>Convert the document to markdown.` — the model returns
markdown with block classification and bounding boxes; the script strips the
grounding tags and keeps clean markdown with `--- page N ---` separators.

Notes:

- `deepseek_ocr.py` loads the processor directly instead of via
  `mlx_vlm.load()` — the stock loader forces `trust_remote_code=True`, which
  under transformers 5 tries to import the repo's torch-based custom code and
  fails (mlx-vlm 0.6.6, transformers 5.14).
- Unlike Apple Vision, output is structured markdown (headings, tables),
  which matters for OSR-style tabular content.

Quality vs Apple Vision (same 3 test files, ~9 s/page on M3 16 GB):

- better on hard spots: correct `II.`/`9a` where Vision reads `Il`/`ga`;
  chart pages get a correctly-read caption instead of garbage
- **silently omits content**: in all 3 files it dropped the "Do druku nr ..."
  header and the intake stamps that Vision does capture (badly). For data
  extraction, cross-check both engines' outputs.

## Results/

One `.md` per source PDF, named after the source file.
