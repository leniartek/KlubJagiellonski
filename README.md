# Konsultacje publiczne Sejmu RP — pobieranie wyników

Narzędzie do automatycznego pobierania wyników zakończonych konsultacji publicznych
projektów ustaw w Sejmie RP (kadencja X) — raportów statystycznych (PDF) oraz
komentarzy uczestników konsultacji (dane ustrukturyzowane w JSON).

Strona źródłowa: [Konsultowane projekty ustaw — zakończone](https://www.sejm.gov.pl/Sejm10.nsf/agent.xsp?symbol=KONSULTACJE_PROJEKTY&NrKadencji=10&Wsk=Z)

## Jak to działa (co ustaliliśmy)

**Sejm ma oficjalne API** — nie trzeba scrape'ować strony z listą konsultacji.

1. **Odkrywanie projektów:** `https://api.sejm.gov.pl/sejm/term10/bills?consultationResults=true`
   zwraca wszystkie projekty z opublikowanymi wynikami konsultacji, wraz z datami
   rozpoczęcia i zakończenia konsultacji (`publicConsultationStartDate` /
   `publicConsultationEndDate`) oraz numerem projektu (pole `number`, np.
   `RPW/22052/2026` albo `SH-020-277/24`). Ten numer to dokładnie `NrProjektu`
   używany w adresach stron z wynikami. Filtrowanie po okresie odbywa się po
   stronie skryptu, po dacie **zakończenia** konsultacji.

2. **Samych plików nie ma w API**, ale ich adresy są w pełni deterministyczne
   (slug = numer projektu z `/` zamienionym na `-`):
   - **Raport statystyczny (PDF):**
     `https://orka.sejm.gov.pl/Konsultacje10.nsf/nazwa/{slug}_wyniki/$file/{slug}_wyniki.pdf`
   - **3 raporty z komentarzami (tylko HTML, nie mają wersji PDF):**
     `https://www.sejm.gov.pl/Sejm10.nsf/agent.xsp?symbol=KONSULTACJE_KOMENTARZE&NrProjektu={numer}&Typ={TYP}`
     gdzie `Typ` to: `PYT5` (komentarze do całości projektu), `PYT6` (komentarze
     do pytań 6–12 ankiety), `ART` (komentarze do artykułów projektu).
     Strony zwracają cały raport w jednym dokumencie — bez paginacji, nawet przy
     ponad 20 tys. ankiet.

3. **Zabezpieczenia serwera:** `orka.sejm.gov.pl` stoi za WAF-em (F5/TSPD), który
   serwuje challenge JavaScript klientom o niekompletnych nagłówkach (goły `curl`
   jest blokowany). Wystarczy jednak pełny zestaw nagłówków przeglądarki
   (User-Agent, Accept, Accept-Language, Referer, Sec-Fetch-\*) — bez ciasteczek
   i bez wykonywania JS. API oraz `www.sejm.gov.pl` są otwarte. Skrypt dodatkowo
   ogranicza tempo żądań (losowe opóźnienie ~1,5–2,25 s), waliduje pobrane PDF-y
   (magic bytes `%PDF`), wykrywa strony challenge (`bobcmn` / "Request Rejected")
   i ponawia próby z wykładniczym odczekiwaniem — dzięki temu nie zostaniemy zablokowani.

## Wymagania

- Python 3.10+
- pakiet `requests` (`pip install requests`)

## Użycie

```bash
# Konsultacje zakończone w zadanym okresie (po dacie zakończenia konsultacji)
python3 sejm_konsultacje.py --from 2026-01-01 --to 2026-07-20

# Wszystkie zakończone konsultacje (obecnie ~280 projektów, ~40 min)
python3 sejm_konsultacje.py --all

# Podgląd listy bez pobierania
python3 sejm_konsultacje.py --from 2026-07-01 --to 2026-07-20 --list-only

# Przebudowa komentarze.json z już pobranych HTML (bez sieci),
# np. po zmianie schematu ekstrakcji
python3 sejm_konsultacje.py --from 2026-07-01 --to 2026-07-20 --reparse
```

Pozostałe opcje: `--term` (kadencja, domyślnie 10), `--out` (katalog docelowy,
domyślnie `Wyniki`), `--delay` (bazowe opóźnienie między żądaniami w sekundach,
domyślnie 1,5).

**Wznawianie:** ponowne uruchomienie pomija pliki już obecne na dysku, więc skrypt
można bezpiecznie uruchamiać cyklicznie (np. z crona), aby dobierać nowo
zakończone konsultacje. Przerwany run wystarczy uruchomić ponownie.

## Struktura wyników

Każda konsultacja trafia do osobnego katalogu nazwanego datą zakończenia,
numerem projektu i skróconym tytułem:

```
Wyniki/
└── 2026-07-07_RPW-22052-2026_Senacki_projekt_ustawy_o_organach_wasciwych.../
    ├── RPW-22052-2026_raport_statystyczny.pdf   # oficjalny raport PDF z orka
    ├── metadata.json                            # rekord projektu z API Sejmu
    ├── komentarze.json                          # komentarze wyekstrahowane z tabel
    └── Archive/                                 # surowe strony HTML (źródło prawdy)
        ├── RPW-22052-2026_komentarze_calosc.html
        ├── RPW-22052-2026_komentarze_pytania_6-12.html
        └── RPW-22052-2026_komentarze_artykuly.html
```

## Jak interpretować dane

### `metadata.json`

Rekord projektu z oficjalnego API: tytuł, numer, numer druku (`print`),
wnioskodawca (`applicantType`), status procesu legislacyjnego (`status`),
daty rozpoczęcia i zakończenia konsultacji.

### `komentarze.json`

Trzy listy komentarzy odpowiadające trzem raportom ze strony wyników:

```json
{
  "number": "SH-020-277/24",
  "title": "Poselski projekt ustawy o zmianie ustawy o broni i amunicji",
  "publicConsultationEndDate": "2024-12-07",
  "calosc":       [ ... ],   // komentarze do całości projektu ustawy
  "pytania_6_12": [ ... ],   // komentarze do pytań 6-12 ankiety
  "artykuly":     [ ... ]    // komentarze do artykułów projektu ustawy
}
```

Pojedynczy komentarz:

```json
{
  "lp": 1,                     // liczba porządkowa w raporcie
  "nr": "Pyt. 6",              // nr pytania ("Pyt. 6") lub artykułu ("Art. 14");
                               // null dla komentarzy do całości projektu
  "komentarz": "Ustawa...",    // pełna treść, z zachowanymi podziałami wierszy
  "autor": "Sędłak Tomasz",    // nazwisko i imię uczestnika konsultacji
  "ankieta_nr": 94             // identyfikator ankiety uczestnika
}
```

`ankieta_nr` jest wspólny dla wszystkich komentarzy tej samej osoby w ramach
jednej konsultacji — pozwala łączyć wypowiedzi jednego uczestnika pomiędzy
trzema raportami (np. jego uwagi ogólne z uwagami do konkretnych artykułów).

### Raport statystyczny (PDF)

Oficjalny dokument Kancelarii Sejmu z podsumowaniem ilościowym: liczba ankiet,
rozkłady odpowiedzi na pytania zamknięte ankiety itd. Pobierany bez zmian.

### Analiza zbiorcza

Połączenie wszystkich konsultacji w jedną ramkę danych:

```python
import json, glob
import pandas as pd

rows = []
for f in glob.glob("Wyniki/*/komentarze.json"):
    d = json.load(open(f))
    for typ in ("calosc", "pytania_6_12", "artykuly"):
        rows += [{"projekt": d["number"], "typ": typ, **r} for r in d[typ]]
df = pd.DataFrame(rows)

df.groupby("projekt").size().sort_values(ascending=False)  # aktywność per projekt
```

## Uwagi

- Skala danych bywa bardzo różna: od kilku komentarzy do kilkunastu tysięcy na
  projekt (rekordzista w testach: 17 054 komentarzy przy 8 298 ankietach).
- Raporty z komentarzami istnieją wyłącznie jako HTML — `komentarze.json` to ich
  wierna, ustrukturyzowana reprezentacja, a oryginały zostają w `Archive/`.
- Weryfikacja ekstrakcji: liczba rekordów zgadza się z liczbą wierszy tabel
  źródłowych, numeracja `lp` jest ciągła, każdy rekord ma autora i numer ankiety,
  komentarze wielowierszowe zachowują podziały wierszy.
- Dane osobowe: raporty zawierają imiona i nazwiska uczestników konsultacji
  opublikowane przez Sejm — przy dalszym udostępnianiu danych trzeba to uwzględnić.
