# OCR

OCR outputs for the scanned PDFs in `SkutkiRegulacji/` (BEOS/OSR opinions; 261 of 264 files are image-only scans with no text layer).

## applevision_ocr.swift

OCR via the macOS Vision framework (`VNRecognizeTextRequest`, Polish, accurate mode, 300 DPI render). No dependencies beyond macOS + Xcode CLT.

```sh
swift OCR/AppleVision/applevision_ocr.swift SkutkiRegulacji/1006-003.pdf OCR/AppleVision/Results/1006-003.txt
```

Output: plain text, one `--- page N ---` section per page; observations on the same baseline are joined with tabs. ~0.5 s/page on Apple Silicon.

Known limitations (tested 2026-07-21 on 1006-003, 1000-001, 2359-004):

- body prose and legal citations are near-perfect, incl. diacritics
- intake stamps / handwriting on cover pages come out garbled
- ALL-CAPS headers occasionally lose diacritics
- embedded chart screenshots are unreadable (e.g. 1006-003 p. 17)
- occasional confusions: Cyrillic `г.` for `r.`, `ga` for `9a`, `Il` for `II`

## Results/

One `.txt` per source PDF, named after the source file.
