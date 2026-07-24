"""Build the research dataset from OCR outputs.

Inputs:
  SkutkiRegulacji/manifest.json          — document metadata (druk, title, date)
  OCR/AppleVision/Results/*.txt          — Apple Vision plain text (page-marked)
  OCR/DeepSeekOCR/Results/*.md           — DeepSeek-OCR markdown (page-marked)

Outputs:
  OCR/Canonical/{id}.md   — merged canonical text: DeepSeek as base (better
                            glyphs/structure), Vision-only fragments DeepSeek
                            silently dropped re-inserted as "> [Vision]:" lines
  OCR/catalog.json        — one record per manifest entry with OCR availability
  OCR/corpus.jsonl        — one record per document section (BEOS template:
                            I., II., ... headers), pandas/grep-ready

Usage: python3 OCR/build_dataset.py
"""
import difflib
import glob
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AV_DIR = os.path.join(ROOT, "OCR", "AppleVision", "Results")
DS_DIR = os.path.join(ROOT, "OCR", "DeepSeekOCR", "Results")
CANON_DIR = os.path.join(ROOT, "OCR", "Canonical")
PAGE_RE = re.compile(r"^--- page (\d+) ---\s*$", re.M)
# section headers, e.g. "## II. Rozwiązanie ..." / "IV. Rozwiązania ..."; lowercase
# 'l' allowed because Apple Vision misreads II/III/VII as Il/Ill/VIl
SECTION_RE = re.compile(r"^#{0,4}\s*\**([IVXl]{1,6})\s*\.\s+(.+?)\**\s*$", re.M)
ROMAN = {"I": 1, "V": 5, "X": 10}


def roman_to_int(tok):
    """Value of a roman numeral, or None if malformed."""
    total, prev = 0, 0
    for ch in reversed(tok):
        v = ROMAN.get(ch)
        if v is None:
            return None
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total if total > 0 else None
WORDLIKE_RE = re.compile(r"^[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż][0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż.,;:()/–-]*$")


def split_pages(text):
    """{page_number: text} from '--- page N ---' marked text."""
    parts = PAGE_RE.split(text)
    pages = {}
    for i in range(1, len(parts), 2):
        pages[int(parts[i])] = parts[i + 1].strip()
    return pages


def norm_word(w):
    w = unicodedata.normalize("NFKC", w).lower()
    return re.sub(r"[^\w]", "", w, flags=re.UNICODE)


def wordlike_ratio(words):
    if not words:
        return 0.0
    return sum(1 for w in words if WORDLIKE_RE.match(w)) / len(words)


def vision_only_runs(ds_text, av_text, min_words=3):
    """Word runs present in Vision but absent from DeepSeek (its silent omissions)."""
    ds_words = ds_text.split()
    av_words = av_text.replace("\t", " ").split()
    sm = difflib.SequenceMatcher(
        a=[norm_word(w) for w in ds_words],
        b=[norm_word(w) for w in av_words],
        autojunk=False,
    )
    runs, dropped = [], 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag not in ("insert", "replace"):
            continue
        # replace: only treat as omission when Vision side is much longer
        if tag == "replace" and (j2 - j1) <= 2 * (i2 - i1):
            continue
        run = av_words[j1:j2]
        if len(run) < min_words:
            continue
        if wordlike_ratio(run) < 0.6:  # chart garbage, not real text
            dropped += 1
            continue
        runs.append(" ".join(run))
    return runs, dropped


def build_canonical(doc_id):
    av_path = os.path.join(AV_DIR, f"{doc_id}.txt")
    ds_path = os.path.join(DS_DIR, f"{doc_id}.md")
    has_av, has_ds = os.path.exists(av_path), os.path.exists(ds_path)
    if not (has_av or has_ds):
        return None, {}
    av_pages = split_pages(open(av_path).read()) if has_av else {}
    ds_pages = split_pages(open(ds_path).read()) if has_ds else {}

    out, stats = [], {"vision_only_runs": 0, "garbage_dropped": 0}
    for n in sorted(set(av_pages) | set(ds_pages)):
        ds, av = ds_pages.get(n, ""), av_pages.get(n, "")
        base = ds if ds else av.replace("\t", " ")
        block = [f"--- page {n} ---", "", base.strip()]
        if ds and av:
            runs, dropped = vision_only_runs(ds, av)
            stats["vision_only_runs"] += len(runs)
            stats["garbage_dropped"] += dropped
            if runs:
                block += [""] + [f"> [Vision]: {r}" for r in runs]
        out.append("\n".join(block))
    return "\n\n".join(out) + "\n", stats


def extract_sections(canonical_text):
    """Split canonical text into BEOS sections; page tracked via markers."""
    sections, current = [], {"section": "0", "section_title": "Nagłówek/adresat", "pages": [], "lines": []}
    page, last_val = None, 0
    for line in canonical_text.splitlines():
        m_page = PAGE_RE.match(line)
        if m_page:
            page = int(m_page.group(1))
            continue
        m_sec = SECTION_RE.match(line)
        if m_sec and len(m_sec.group(2).split()) >= 2:  # avoid "II." list stubs
            tok = m_sec.group(1).replace("l", "I")  # Vision glyph fix: Il -> II
            val = roman_to_int(tok)
            # sections must advance monotonically; quoted headers ("I. Problem"
            # cited later in the text) and OCR misreads would otherwise split
            # the document at the wrong places
            if val is not None and val > last_val:
                last_val = val
                sections.append(current)
                current = {"section": tok, "section_title": m_sec.group(2).strip(),
                           "pages": [page] if page else [], "lines": []}
                continue
        if page and (not current["pages"] or current["pages"][-1] != page):
            current["pages"].append(page)
        current["lines"].append(line)
    sections.append(current)
    for s in sections:
        s["text"] = "\n".join(s.pop("lines")).strip()
        s["pages"] = [p for p in s["pages"] if p]
    return [s for s in sections if s["text"]]


def main():
    manifest = json.load(open(os.path.join(ROOT, "SkutkiRegulacji", "manifest.json")))
    os.makedirs(CANON_DIR, exist_ok=True)

    catalog, corpus_records = [], []
    n_canon = 0
    for entry in manifest:
        # key by filename, not API number: for druk 2602 the API registers the
        # attachment as 2601-001 but the file (and content) is 2602-001.pdf
        doc_id = os.path.splitext(entry["file"])[0]
        pdf_exists = os.path.exists(os.path.join(ROOT, "SkutkiRegulacji", entry["file"]))
        has_av = os.path.exists(os.path.join(AV_DIR, f"{doc_id}.txt"))
        has_ds = os.path.exists(os.path.join(DS_DIR, f"{doc_id}.md"))

        canonical, stats = build_canonical(doc_id)
        pages = chars = 0
        if canonical:
            with open(os.path.join(CANON_DIR, f"{doc_id}.md"), "w") as f:
                f.write(canonical)
            n_canon += 1
            pages = len(PAGE_RE.findall(canonical))
            chars = len(canonical)
            for s in extract_sections(canonical):
                corpus_records.append({
                    "id": doc_id,
                    "druk": entry["druk"],
                    "druk_title": entry["drukTitle"],
                    "delivery_date": entry["deliveryDate"],
                    "section": s["section"],
                    "section_title": s["section_title"],
                    "pages": s["pages"],
                    "text": s["text"],
                })

        catalog.append({
            "id": doc_id,
            "druk": entry["druk"],
            "druk_title": entry["drukTitle"],
            "delivery_date": entry["deliveryDate"],
            "pdf": entry["file"] if pdf_exists else None,
            "url": entry["url"],
            "ocr": {"applevision": has_av, "deepseek": has_ds,
                    "canonical": bool(canonical)},
            "pages": pages or None,
            "chars": chars or None,
            **({"merge_stats": stats} if canonical else {}),
        })

    with open(os.path.join(ROOT, "OCR", "catalog.json"), "w") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    with open(os.path.join(ROOT, "OCR", "corpus.jsonl"), "w") as f:
        for r in corpus_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"catalog: {len(catalog)} entries ({sum(1 for c in catalog if c['pdf'])} PDFs)")
    print(f"canonical: {n_canon} documents -> OCR/Canonical/")
    print(f"corpus.jsonl: {len(corpus_records)} section records")
    for c in catalog:
        if c["ocr"]["canonical"]:
            secs = [r["section"] for r in corpus_records if r["id"] == c["id"]]
            print(f"  {c['id']}: {c['pages']}p, sections: {' '.join(secs)}, "
                  f"vision-only runs: {c['merge_stats']['vision_only_runs']}, "
                  f"garbage dropped: {c['merge_stats']['garbage_dropped']}")


if __name__ == "__main__":
    sys.exit(main())
