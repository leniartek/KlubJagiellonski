"""Merge an invisible text layer (Apple Vision word boxes) onto the original scan.

Usage: make_searchable.py <original.pdf> <boxes.json> <output.pdf>

The original page content is kept byte-for-byte (pypdf merge_page appends an
overlay content stream); text is drawn with render mode 3 (invisible) using an
embedded TTF so Polish diacritics survive extraction.
"""
import io
import json
import sys

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader  # noqa: F401  (keeps reportlab happy)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
]

def register_font():
    for path in FONT_CANDIDATES:
        try:
            pdfmetrics.registerFont(TTFont("OCRFont", path))
            return "OCRFont"
        except Exception:
            continue
    raise SystemExit("no usable TTF font found")

def main(src_path, boxes_path, out_path):
    font = register_font()
    pages = json.load(open(boxes_path))
    reader = PdfReader(src_path)

    buf = io.BytesIO()
    c = None
    for p in pages:
        w, h = p["width"], p["height"]
        if c is None:
            c = canvas.Canvas(buf, pagesize=(w, h))
        else:
            c.setPageSize((w, h))
        t = c.beginText()
        t.setTextRenderMode(3)  # invisible
        for word in p["words"]:
            bw, bh = word["w"] * w, word["h"] * h
            if not word["text"] or bw <= 0 or bh <= 0:
                continue
            size = max(bh, 1.0)
            natural = pdfmetrics.stringWidth(word["text"], font, size)
            hscale = 100.0 * bw / natural if natural > 0 else 100.0
            t.setFont(font, size)
            t.setHorizScale(hscale)
            # baseline ~20% above the box bottom approximates the descender zone
            t.setTextOrigin(word["x"] * w, word["y"] * h + 0.2 * size)
            t.textLine(word["text"])
        c.drawText(t)
        c.showPage()
    c.save()

    overlay = PdfReader(buf)
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    with open(out_path, "wb") as f:
        writer.write(f)
    print(f"wrote {out_path} ({len(reader.pages)} pages)")

if __name__ == "__main__":
    main(*sys.argv[1:4])
