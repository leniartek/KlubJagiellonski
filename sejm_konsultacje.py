#!/usr/bin/env python3
"""Pobiera wyniki zakończonych konsultacji publicznych Sejmu RP.

Dla każdego projektu z zakończonymi konsultacjami w zadanym okresie pobiera:
  - raport statystyczny (PDF, orka.sejm.gov.pl)
  - 3 raporty z komentarzami (HTML, www.sejm.gov.pl):
      PYT5 = komentarze do całości projektu ustawy
      PYT6 = komentarze do pytań 6-12 ankiety
      ART  = komentarze do artykułów projektu ustawy
  - metadata.json z danymi projektu z oficjalnego API
  - komentarze.json - dane wyekstrahowane z tabel trzech raportów HTML

Odkrywanie projektów odbywa się przez oficjalne API Sejmu
(https://api.sejm.gov.pl/sejm/term{term}/bills?consultationResults=true),
więc nie trzeba scrape'ować strony z listą. Filtr po dacie działa na
publicConsultationEndDate.

Użycie:
  python3 sejm_konsultacje.py --from 2026-01-01 --to 2026-07-20
  python3 sejm_konsultacje.py --all          # wszystkie zakończone
  python3 sejm_konsultacje.py --list-only    # tylko pokaż, bez pobierania

Ponowne uruchomienie pomija już pobrane pliki (resume).
"""

import argparse
import json
import random
import re
import sys
import time
import unicodedata
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import requests

API_BASE = "https://api.sejm.gov.pl/sejm"
WWW_BASE = "https://www.sejm.gov.pl/Sejm{term}.nsf/agent.xsp"
ORKA_PDF = "https://orka.sejm.gov.pl/Konsultacje{term}.nsf/nazwa/{slug}_wyniki/$file/{slug}_wyniki.pdf"

COMMENT_REPORTS = {
    "PYT5": "komentarze_calosc",
    "PYT6": "komentarze_pytania_6-12",
    "ART": "komentarze_artykuly",
}

# Pełny zestaw nagłówków przeglądarki — orka.sejm.gov.pl stoi za WAF-em
# (F5/TSPD), który serwuje JS challenge klientom o niekompletnych nagłówkach.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Referer": "https://www.sejm.gov.pl/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-site",
}


class KomentarzeParser(HTMLParser):
    """Wyciąga wiersze z tabeli raportu komentarzy (table class="konsultacje").

    Struktura tabeli: Lp. | [Nr pyt./Nr art.] | Komentarz | Nazwisko i imię.
    Kolumna z numerem pytania/artykułu występuje tylko w raportach PYT6 i ART.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.ankieta_nr: list[int | None] = []
        self._in_table = self._in_cell = False
        self._cell_text: list[str] = []
        self._row: list[str] = []
        self._row_ankieta: int | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and "konsultacje" in a.get("class", ""):
            self._in_table = True
        elif self._in_table:
            if tag == "tr":
                self._row, self._row_ankieta = [], None
            elif tag in ("td", "th"):
                self._in_cell, self._cell_text = True, []
            elif self._in_cell and tag in ("br", "p", "li"):
                self._cell_text.append("\n")
            elif self._in_cell and tag == "a":
                m = re.search(r"NrAnkiety=(\d+)", a.get("href", ""))
                if m:
                    self._row_ankieta = int(m.group(1))

    def handle_endtag(self, tag):
        if tag == "table":
            self._in_table = False
        elif self._in_table and tag in ("td", "th"):
            text = re.sub(r"[ \t]+", " ", "".join(self._cell_text))
            self._row.append(re.sub(r"\s*\n\s*", "\n", text).strip())
            self._in_cell = False
        elif self._in_table and tag == "tr" and self._row:
            self.rows.append(self._row)
            self.ankieta_nr.append(self._row_ankieta)

    def handle_data(self, data):
        if self._in_cell:
            self._cell_text.append(data)


def parse_comments_html(html_text: str) -> list[dict]:
    """Zamienia raport HTML na listę komentarzy (pomija wiersz nagłówka)."""
    p = KomentarzeParser()
    p.feed(html_text)
    out = []
    for row, nr_ankiety in zip(p.rows, p.ankieta_nr):
        if not row or not row[0].rstrip(".").isdigit():
            continue  # nagłówek albo pusty wiersz
        has_ref = len(row) == 4  # kolumna "Nr pyt."/"Nr art." tylko w PYT6/ART
        autor = row[-1]
        autor = re.sub(r"\s*ankieta nr \d+\s*$", "", autor).replace("\n", " ").strip()
        out.append({
            "lp": int(row[0].rstrip(".")),
            "nr": row[1] if has_ref else None,
            "komentarz": row[2] if has_ref else row[1],
            "autor": autor,
            "ankieta_nr": nr_ankiety,
        })
    return out


def polite_sleep(delay: float) -> None:
    time.sleep(delay + random.uniform(0, delay * 0.5))


def slugify_number(number: str) -> str:
    """RPW/22052/2026 -> RPW-22052-2026 (tak samo buduje URL-e orka)."""
    return number.replace("/", "-")


def safe_title(title: str, maxlen: int = 80) -> str:
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")
    return t[:maxlen].rstrip("_")


def fetch_bills(session: requests.Session, term: int) -> list[dict]:
    bills, offset, limit = [], 0, 200
    while True:
        r = session.get(
            f"{API_BASE}/term{term}/bills",
            params={"consultationResults": "true", "limit": limit, "offset": offset},
            timeout=60,
        )
        r.raise_for_status()
        page = r.json()
        bills.extend(page)
        if len(page) < limit:
            return bills
        offset += limit


def download(session: requests.Session, url: str, dest: Path, expect_pdf: bool,
             delay: float, retries: int = 4) -> str:
    """Pobiera URL do pliku. Zwraca status: ok / skipped / not_found / failed."""
    if dest.exists() and dest.stat().st_size > 0:
        return "skipped"
    for attempt in range(retries):
        polite_sleep(delay)
        try:
            r = session.get(url, timeout=120)
        except requests.RequestException as e:
            print(f"    ! błąd sieci ({e}), próba {attempt + 1}/{retries}")
            time.sleep(2 ** attempt * 5)
            continue
        if r.status_code == 404:
            return "not_found"
        body = r.content
        is_pdf = body[:5] == b"%PDF-"
        # Prawdziwa strona challenge zawiera "bobcmn"/"Request Rejected";
        # sam napis "TSPD" występuje też w legalnych stronach (loader WAF-a).
        challenged = (not is_pdf) and (
            b"bobcmn" in body[:4096] or b"Request Rejected" in body[:2048]
        )
        if r.status_code == 200 and (is_pdf if expect_pdf else not challenged):
            dest.write_bytes(body)
            return "ok"
        # WAF challenge albo nieoczekiwana odpowiedź — odczekaj i ponów
        print(f"    ! HTTP {r.status_code}, "
              f"{'challenge WAF' if challenged else 'nie-PDF'}, "
              f"próba {attempt + 1}/{retries}")
        time.sleep(2 ** attempt * 10)
    return "failed"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="date_from", type=date.fromisoformat,
                    help="początek okresu (data zakończenia konsultacji), YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", type=date.fromisoformat,
                    help="koniec okresu, YYYY-MM-DD")
    ap.add_argument("--all", action="store_true", help="pobierz wszystkie zakończone")
    ap.add_argument("--term", type=int, default=10, help="kadencja Sejmu (domyślnie 10)")
    ap.add_argument("--out", type=Path, default=Path("Wyniki"), help="katalog docelowy")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="bazowe opóźnienie między żądaniami w sekundach (domyślnie 1.5)")
    ap.add_argument("--list-only", action="store_true", help="tylko wypisz, nie pobieraj")
    ap.add_argument("--reparse", action="store_true",
                    help="przebuduj komentarze.json z już pobranych plików HTML")
    args = ap.parse_args()

    if not args.all and not (args.date_from or args.date_to):
        ap.error("podaj --from/--to albo --all")

    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    print(f"Pobieram listę projektów z konsultacjami (API, kadencja {args.term})...")
    bills = fetch_bills(session, args.term)
    print(f"  projektów z wynikami konsultacji: {len(bills)}")

    def in_range(b: dict) -> bool:
        end = b.get("publicConsultationEndDate")
        if not end:
            return args.all
        end_d = date.fromisoformat(end)
        if args.date_from and end_d < args.date_from:
            return False
        if args.date_to and end_d > args.date_to:
            return False
        return True

    selected = sorted((b for b in bills if in_range(b)),
                      key=lambda b: b.get("publicConsultationEndDate") or "")
    print(f"  w zadanym okresie: {len(selected)}\n")

    if args.list_only:
        for b in selected:
            print(f"{b.get('publicConsultationEndDate')}  {b['number']:<22} {b['title'][:90]}")
        return 0

    www = WWW_BASE.format(term=args.term)
    summary = {"ok": 0, "skipped": 0, "not_found": 0, "failed": 0}
    failures = []

    for i, bill in enumerate(selected, 1):
        number = bill["number"]
        slug = slugify_number(number)
        end = bill.get("publicConsultationEndDate") or "brak-daty"
        proj_dir = args.out / f"{end}_{slug}_{safe_title(bill['title'])}"
        proj_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{i}/{len(selected)}] {number} (koniec: {end})")

        meta_path = proj_dir / "metadata.json"
        if not meta_path.exists():
            meta_path.write_text(json.dumps(bill, ensure_ascii=False, indent=2))

        # 1. Raport statystyczny (PDF z orka)
        pdf_url = ORKA_PDF.format(term=args.term, slug=slug)
        status = download(session, pdf_url, proj_dir / f"{slug}_raport_statystyczny.pdf",
                          expect_pdf=True, delay=args.delay)
        print(f"    raport statystyczny (PDF): {status}")
        summary[status] += 1
        if status == "failed":
            failures.append((number, "pdf", pdf_url))

        # 2. Trzy raporty z komentarzami (HTML z www) -> podkatalog Archive
        archive_dir = proj_dir / "Archive"
        archive_dir.mkdir(exist_ok=True)
        html_paths = {}
        for typ, name in COMMENT_REPORTS.items():
            url = f"{www}?symbol=KONSULTACJE_KOMENTARZE&NrProjektu={number}&Typ={typ}"
            dest = archive_dir / f"{slug}_{name}.html"
            # migracja: starsze wersje skryptu zapisywały HTML w katalogu projektu
            legacy = proj_dir / dest.name
            if legacy.exists() and not dest.exists():
                legacy.rename(dest)
            status = download(session, url, dest, expect_pdf=False, delay=args.delay)
            print(f"    {name}: {status}")
            summary[status] += 1
            if status == "failed":
                failures.append((number, typ, url))
            elif status in ("ok", "skipped"):
                html_paths[typ] = dest

        # 3. Ekstrakcja tabel komentarzy do JSON
        json_path = proj_dir / "komentarze.json"
        if len(html_paths) == len(COMMENT_REPORTS) and (
                not json_path.exists() or args.reparse):
            data = {
                "number": number,
                "title": bill["title"],
                "publicConsultationEndDate": bill.get("publicConsultationEndDate"),
            }
            for typ, key in (("PYT5", "calosc"), ("PYT6", "pytania_6_12"),
                             ("ART", "artykuly")):
                data[key] = parse_comments_html(
                    html_paths[typ].read_text(encoding="utf-8", errors="replace"))
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            n = sum(len(data[k]) for k in ("calosc", "pytania_6_12", "artykuly"))
            print(f"    komentarze.json: {n} komentarzy")

    print(f"\nGotowe: {summary}")
    if failures:
        print("Nieudane pobrania:")
        for number, what, url in failures:
            print(f"  {number} [{what}] {url}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
