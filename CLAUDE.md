# CLAUDE.md

Two datasets scraped from the Sejm RP (term X) plus OCR tooling. Human docs are
in Polish (README.md); code and code comments in English.

## Datasets

1. **Konsultacje** (`Wyniki/`) — public-consultation results per bill:
   `metadata.json` (API record), `komentarze.json` (structured comments),
   statistical report PDF, raw HTML in `Archive/`. Downloader:
   `sejm_konsultacje.py`. Schema details: README.md § Konsultacje.
2. **Skutki Regulacji** (`SkutkiRegulacji/`) — BEOS regulatory-impact opinions
   (OSR), one PDF per druk dodatkowy + `manifest.json`. Downloader:
   `sejm_skutki_regulacji.py`. 261 of 264 PDFs are image-only scans — never
   read them expecting a text layer; use the OCR outputs below.

## Researching the OSR corpus — start here

- `OCR/catalog.json` — one record per document: id, druk, title, date, which
  OCR outputs exist (`ocr.applevision/deepseek/canonical`), pages, chars.
  Filter this first; only then open transcripts.
- `OCR/corpus.jsonl` — one record per document **section** (2726 records,
  264 docs), so cross-document questions are usually one grep/jq over this
  file: `{"id","druk","druk_title","delivery_date","section","section_title","pages","text"}`.
  Section templates VARY: BEOS opinions use I–X, the RCL government OSR form
  uses I–XIII ("Jaki problem jest rozwiązywany?"), 2208-005 numbers sections
  in arabic (unparsed, single section "0"); section 0 = preamble. Don't
  assume section N means the same thing in every document — check
  `section_title`.
- `OCR/Canonical/{id}.md` — best-quality full text per document,
  `--- page N ---` markers preserved for citing back to the scan.
- Prefer Canonical > DeepSeekOCR > AppleVision when several exist.

## OCR ground truth & caveats

- `OCR/AppleVision/Results/*.txt` — Apple Vision. Near-perfect prose; known
  glyph errors: `Il`→`II`, `ga`→`9a`, Cyrillic `г.`; emits garbage on chart
  images; captures stamps and "Do druku nr" headers (messily).
- `OCR/DeepSeekOCR/Results/*.md` — DeepSeek-OCR (local, mlx-vlm). Clean
  markdown, correct glyphs, BUT **silently omits** stamps, "Do druku nr"
  headers and some footnote blocks.
- `OCR/Canonical/*.md` — for the 3 dual-OCR docs (1006-003, 1000-001,
  2359-004): DeepSeek base + Vision-only fragments as `> [Vision]: …` lines.
  For the remaining 261 docs canonical == Apple Vision text verbatim (glyph
  caveats apply). Built by `OCR/build_dataset.py`.
- `OCR/AppleVision/Results/*.pdf` — original scans + invisible text layer,
  for humans; don't parse these when the .txt/.md exists.
- All 264 documents have Apple Vision OCR (txt + searchable PDF); only the
  3 test docs also have DeepSeek-OCR. To add DeepSeek coverage, see
  `OCR/DeepSeekOCR/README.md` (~9 s/page), then re-run
  `python3 OCR/build_dataset.py` (stdlib-only) to refresh
  Canonical/catalog/corpus.
- ID quirk: the attachment to druk 2602 is registered in the Sejm API as
  number `2601-001` but the file/content is `2602-001` — dataset ids follow
  the **filename**.

## Environment notes

- macOS. `poppler` is NOT installed — the Read tool cannot render PDF pages
  visually (`brew install poppler` enables it). Probe PDFs programmatically
  (pypdf) instead.
- No repo-level venv. Per-task deps: `pypdf`/`reportlab` (searchable PDFs),
  `mlx-vlm` (DeepSeek-OCR, needs ~5.5 GB RAM). Swift scripts run with bare
  `swift` (Xcode CLT), no packages.
- Requests to sejm.gov.pl need browser-like headers and rate limiting;
  `orka.sejm.gov.pl` sits behind a WAF — reuse helpers in the downloaders,
  don't hand-roll fetches.

## Conventions

- Personal data: consultation comments carry real names published by the
  Sejm — keep that in mind before exporting data elsewhere.
- Commits so far: short imperative subject + brief body (see `git log`).
- Keep README.md (Polish) as the source of truth for dataset findings;
  update it when new corpus facts are established.
