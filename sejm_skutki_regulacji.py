#!/usr/bin/env python3
"""Pobiera oceny skutków regulacji (OSR) publikowane jako druki sejmowe.

OSR trafiają do Sejmu jako "druki dodatkowe" (additionalPrints) z tytułem
w rodzaju "Do druku nr 1527 - ocena skutków regulacji". Skrypt pobiera listę
wszystkich druków z oficjalnego API Sejmu, filtruje druki dodatkowe po tytule
i ściąga ich załączniki PDF przez API (bez WAF-a, w przeciwieństwie do orka).

Wynik:
  SkutkiRegulacji/{numer-druku}.pdf   np. 1527-004.pdf (numeracja zawiera
                                      numer druku głównego)
  SkutkiRegulacji/manifest.json       metadane: druk główny, tytuły, daty, URL

Użycie:
  python3 sejm_skutki_regulacji.py            # cała kadencja (domyślnie 10)
  python3 sejm_skutki_regulacji.py --term 10 --out SkutkiRegulacji

Ponowne uruchomienie pomija już pobrane pliki (resume).
"""

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://api.sejm.gov.pl/sejm"
OSR_RE = re.compile(r"skutk\w*\s+regulacji", re.I)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--term", type=int, default=10, help="kadencja Sejmu (domyślnie 10)")
    ap.add_argument("--out", type=Path, default=Path("SkutkiRegulacji"),
                    help="katalog docelowy")
    ap.add_argument("--delay", type=float, default=0.8,
                    help="bazowe opóźnienie między żądaniami w sekundach")
    args = ap.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

    print(f"Pobieram listę druków (API, kadencja {args.term})...")
    r = session.get(f"{API_BASE}/term{args.term}/prints", timeout=120)
    r.raise_for_status()
    prints = r.json()
    print(f"  druków: {len(prints)}")

    osr = []
    for p in prints:
        for extra in p.get("additionalPrints", []):
            if OSR_RE.search(extra.get("title", "")):
                osr.append((p, extra))
    print(f"  z oceną skutków regulacji: {len(osr)}\n")

    args.out.mkdir(parents=True, exist_ok=True)
    manifest, failures = [], []
    summary = {"ok": 0, "skipped": 0, "failed": 0}

    for i, (parent, extra) in enumerate(osr, 1):
        for attachment in extra.get("attachments", []):
            url = f"{API_BASE}/term{args.term}/prints/{extra['number']}/{attachment}"
            dest = args.out / attachment
            manifest.append({
                "druk": parent["number"],
                "drukTitle": parent["title"],
                "number": extra["number"],
                "title": extra["title"],
                "deliveryDate": extra.get("deliveryDate"),
                "file": attachment,
                "url": url,
            })
            if dest.exists() and dest.stat().st_size > 0:
                summary["skipped"] += 1
                continue
            status = "failed"
            for attempt in range(3):
                time.sleep(args.delay + random.uniform(0, args.delay * 0.5))
                try:
                    resp = session.get(url, timeout=120)
                except requests.RequestException as e:
                    print(f"  ! {attachment}: błąd sieci ({e})")
                    time.sleep(2 ** attempt * 5)
                    continue
                if resp.status_code == 200 and resp.content[:5] == b"%PDF-":
                    dest.write_bytes(resp.content)
                    status = "ok"
                    break
                print(f"  ! {attachment}: HTTP {resp.status_code}, "
                      f"próba {attempt + 1}/3")
                time.sleep(2 ** attempt * 5)
            summary[status] += 1
            if status == "failed":
                failures.append(url)
            print(f"[{i}/{len(osr)}] druk {parent['number']:<8} {attachment}: {status}")

    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\nGotowe: {summary}, manifest: {len(manifest)} pozycji")
    if failures:
        print("Nieudane:")
        for u in failures:
            print(" ", u)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
