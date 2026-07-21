# Dane z Sejmu RP (kadencja X)

Repozytorium obejmuje dwa zbiory danych:

1. **[Konsultacje](#konsultacje)** — wyniki zakończonych konsultacji publicznych
   projektów ustaw: raporty statystyczne (PDF) i komentarze uczestników (JSON),
   katalog `Wyniki/`.
2. **[Skutki Regulacji](#skutki-regulacji)** — oceny skutków regulacji (OSR)
   opracowywane przez Biuro Ekspertyz i Oceny Skutków Regulacji Kancelarii
   Sejmu, katalog `SkutkiRegulacji/` (skany wymagające OCR — zob. `OCR/`).

# Konsultacje

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

## Najpopularniejsze konsultacje

Suma pierwszych dziesiątek według liczby ankiet i według liczby komentarzy
(stan na 2026-07-21, posortowane malejąco po liczbie komentarzy; liczba ankiet
pochodzi ze strony Sejmu, liczba komentarzy z `komentarze.json`). Tytuł linkuje
do katalogu z pobranymi wynikami:

| Projekt | Numer | Koniec konsultacji | Ankiety | Komentarze |
|---|---|---|---:|---:|
| [Poselski projekt ustawy o zawodzie psychoterapeuty oraz samorządzie zawodowym](Wyniki/2025-03-13_RPW-5317-2025_Poselski_projekt_ustawy_o_zawodzie_psychoterapeuty_oraz_samorzadzie_zawodowym/) | RPW/5317/2025 | 2025-03-13 | 7 575 | 47 788 |
| [Poselski projekt ustawy o zmianie ustawy o broni i amunicji](Wyniki/2025-10-19_RPW-31004-2025_Poselski_projekt_ustawy_o_zmianie_ustawy_o_broni_i_amunicji/) | RPW/31004/2025 | 2025-10-19 | 20 898 | 36 527 |
| [Poselski projekt ustawy o zmianie ustawy - Prawo łowieckie](Wyniki/2026-01-17_RPW-42391-2025_Poselski_projekt_ustawy_o_zmianie_ustawy_Prawo_owieckie/) | RPW/42391/2025 | 2026-01-17 | 17 325 | 19 955 |
| [Poselski projekt ustawy o zmianie ustawy o broni i amunicji](Wyniki/2024-12-07_SH-020-277-24_Poselski_projekt_ustawy_o_zmianie_ustawy_o_broni_i_amunicji/) | SH-020-277/24 | 2024-12-07 | 8 298 | 17 054 |
| [Poselski projekt ustawy o zmianie ustawy o przeciwdziałaniu narkomanii](Wyniki/2026-04-29_RPW-10875-2026_Poselski_projekt_ustawy_o_zmianie_ustawy_o_przeciwdziaaniu_narkomanii/) | RPW/10875/2026 | 2026-04-29 | 22 561 | 13 080 |
| [Poselski projekt ustawy o zmianie ustawy o ochronie przyrody](Wyniki/2026-05-16_RPW-13032-2026_Poselski_projekt_ustawy_o_zmianie_ustawy_o_ochronie_przyrody/) | RPW/13032/2026 | 2026-05-16 | 3 510 | 7 913 |
| [Poselski projekt ustawy o zmianie ustawy o obywatelstwie polskim](Wyniki/2025-06-05_RPW-15086-2025_Poselski_projekt_ustawy_o_zmianie_ustawy_o_obywatelstwie_polskim/) | RPW/15086/2025 | 2025-06-05 | 2 286 | 7 706 |
| [Poselski projekt ustawy o zmianie ustawy o obywatelstwie polskim](Wyniki/2025-11-06_RPW-32950-2025_Poselski_projekt_ustawy_o_zmianie_ustawy_o_obywatelstwie_polskim/) | RPW/32950/2025 | 2025-11-06 | 4 353 | 6 929 |
| [Poselski projekt ustawy o zmianie ustawy o obywatelstwie polskim oraz ustawy o cudzoziemcach](Wyniki/2026-05-20_RPW-13478-2026_Poselski_projekt_ustawy_o_zmianie_ustawy_o_obywatelstwie_polskim_oraz_ustawy_o_c/) | RPW/13478/2026 | 2026-05-20 | 1 242 | 6 499 |
| [Poselski projekt ustawy o zmianie ustawy - Kodeks wyborczy](Wyniki/2025-08-07_RPW-22565-2025_Poselski_projekt_ustawy_o_zmianie_ustawy_Kodeks_wyborczy/) | RPW/22565/2025 | 2025-08-07 | 2 779 | 5 333 |
| [Poselski projekt ustawy o zmianie ustawy o ochronie praw nabywcy lokalu mieszkalnego...](Wyniki/2025-03-23_RPW-6415-2025_Poselski_projekt_ustawy_o_zmianie_ustawy_o_ochronie_praw_nabywcy_lokalu_mieszkal/) | RPW/6415/2025 | 2025-03-23 | 6 201 | 3 668 |
| [Przedstawiony przez Prezydenta RP projekt ustawy o zapewnieniu...](Wyniki/2025-09-10_RPW-26832-2025_Przedstawiony_przez_Prezydenta_Rzeczypospolitej_Polskiej_projekt_ustawy_o_zapewn/) | RPW/26832/2025 | 2025-09-10 | 3 946 | 3 031 |
| [Poselski projekt ustawy o zmianie ustawy o wykonywaniu działalności gospodarczej...](Wyniki/2025-05-04_RPW-11625-2025_Poselski_projekt_ustawy_o_zmianie_ustawy_o_wykonywaniu_dziaalnosci_gospodarczej/) | RPW/11625/2025 | 2025-05-04 | 3 548 | 1 495 |

Ciekawostka: rankingi się nie pokrywają — projekt o zawodzie psychoterapeuty ma
najwięcej komentarzy (47 788) przy 7 575 ankietach, a projekt o przeciwdziałaniu
narkomanii najwięcej ankiet (22 561) przy 13 080 komentarzach.

## Brakujące dane

Kompletność zbioru (stan na 2026-07-21, 279 konsultacji):

- **3 projekty nie mają raportu statystycznego (PDF).** Raporty z komentarzami
  i `komentarze.json` są dla nich kompletne:
  - [SH-020-227/24 — ustawa o zagospodarowaniu wspólnot gruntowych](Wyniki/2025-02-09_SH-020-227-24_Senacki_projekt_ustawy_o_zmianie_ustawy_o_zagospodarowaniu_wspolnot_gruntowych/)
    — [strona wyników](https://www.sejm.gov.pl/Sejm10.nsf/agent.xsp?symbol=KONSULTACJE_WYNIKI&NrProjektu=SH-020-227/24)
    nie zawiera linku do PDF,
  - [RPW/5327/2026 — ustawa o publicznym transporcie zbiorowym](Wyniki/2026-02-19_RPW-5327-2026_Poselski_projekt_ustawy_o_zmianie_ustawy_o_publicznym_transporcie_zbiorowym/)
    — link do PDF na [stronie wyników](https://www.sejm.gov.pl/Sejm10.nsf/agent.xsp?symbol=KONSULTACJE_WYNIKI&NrProjektu=RPW/5327/2026)
    jest pusty,
  - [RPW/5184/2026 — ustawa o ubezpieczeniach obowiązkowych](Wyniki/2026-03-15_RPW-5184-2026_Poselski_projekt_ustawy_o_zmianie_ustawy_o_ubezpieczeniach_obowiazkowych_Ubezpie/)
    — [strona wyników](https://www.sejm.gov.pl/Sejm10.nsf/agent.xsp?symbol=KONSULTACJE_WYNIKI&NrProjektu=RPW/5184/2026)
    linkuje **omyłkowo do cudzego raportu** (RPW/5149/2026, "godka śląska";
    potwierdzone sumą kontrolną i treścią PDF), własny raport nie istnieje.
- **PDF bywa opublikowany pod innym numerem niż numer projektu** — raport dla
  RPW/2277/2026 (Kodeks karny) jest w pliku `RPW-2277-2025_wyniki.pdf` (literówka
  w roku po stronie Sejmu; tytuł w PDF potwierdza właściwy projekt —
  [strona wyników](https://www.sejm.gov.pl/Sejm10.nsf/agent.xsp?symbol=KONSULTACJE_WYNIKI&NrProjektu=RPW/2277/2026)).
  Skrypt wykrywa takie przypadki: przy braku pliku pod numerem projektu
  odczytuje właściwy adres ze strony wyników, ale odrzuca slug należący do
  innego projektu (ochrona przed omyłkowymi linkami jak przy RPW/5184/2026).
- **2 projekty (SH-020-227/24 i RPW/5327/2026) nie figurują na stronie Sejmu
  z listą zakończonych konsultacji**, mimo że API oznacza je jako posiadające
  wyniki — dla nich nie znamy też liczby ankiet ze strony www. To pokazuje,
  że API jest pełniejszym źródłem odkrywania projektów niż sama strona.
- Liczba ankiet nie jest dostępna w API ani w `metadata.json` — pochodzi
  wyłącznie ze strony z listą konsultacji.

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

# Skutki Regulacji

Oceny skutków regulacji (OSR) — opinie Biura Ekspertyz i Oceny Skutków
Regulacji (BEOS) Kancelarii Sejmu, publikowane jako **druki dodatkowe** do
druków sejmowych (tytuły w rodzaju "Do druku nr 1527 - ocena skutków
regulacji"). Każdy dokument to kierowana do Marszałka Sejmu "Opinia w sprawie
oceny skutków regulacji" danego projektu ustawy, zwykle 10–30 stron.

## Pobieranie

Skrypt `sejm_skutki_regulacji.py` znajduje OSR przez oficjalne API
(`/sejm/term10/prints`, filtr po tytule druku dodatkowego) i pobiera PDF-y
bezpośrednio z API:

```bash
python3 sejm_skutki_regulacji.py            # cała kadencja (domyślnie 10)
```

Wynik trafia do katalogu `SkutkiRegulacji/`: pliki PDF nazwane numerem druku
dodatkowego (np. `1527-004.pdf` — prefiks to numer druku głównego) oraz
`manifest.json` wiążący każdy plik z drukiem głównym, tytułami i datą wpływu.
Ponowne uruchomienie pomija pobrane pliki.

Stan na 2026-07-21: **264 z 265 OSR** X kadencji. Jedyny brak to OSR do druku
934 — na [stronie druku](https://orka.sejm.gov.pl/Druki10ka.nsf/dok?OpenAgent&10-934-002)
widnieje "Brak tekstu w postaci elektronicznej" (dodatkowo dwa różne druki
dodatkowe mają ten sam numer 934-002, przez co API zwraca 404).

## Charakterystyka plików (co ustaliliśmy)

Analiza wszystkich 264 PDF-ów (2026-07-21): **261 to skany bez warstwy
tekstowej** — obrazy z kserokopiarek Kancelarii Sejmu, tekstu nie da się z nich
wyszukać ani skopiować bez OCR.

| Grupa (pole Producer w PDF) | Plików | Charakter |
|---|---:|---|
| Konica Minolta bizhub C451i / C458 / 458e | 211 | surowy skan, sam obraz |
| pdf-lib (złożone programowo) | 50 | również sam obraz (np. `2359-004.pdf`: 16 stron, 1967 obiektów graficznych, 0 fontów) |
| z warstwą tekstową | 3 | zob. niżej |

Trzy pliki z tekstem to każdorazowo inna historia:

- `1528-004.pdf` — dokument cyfrowy (eksport z Worda), tekst idealny;
- `1319-001.pdf` — skan po OCR Acrobat ClearScan, tekst zaszumiony
  ("KANCElARII", "1 O czerwca") — nadaje się do wyszukiwania, nie do cytowania;
- `1526-004.pdf` — warstwa tekstowa tylko na części stron.

## OCR

Katalog [`OCR/`](OCR/) zawiera skrypt i wyniki — szczegóły w
[`OCR/AppleVision/README.md`](OCR/AppleVision/README.md).

**Wybrane podejście (test):** wbudowany w macOS framework Vision
(`VNRecognizeTextRequest`, język polski, tryb accurate, render 300 DPI) —
skrypt [`OCR/AppleVision/applevision_ocr.swift`](OCR/AppleVision/applevision_ocr.swift),
bez zewnętrznych zależności, ~0,5 s/stronę (cały korpus ~5,5 tys. stron ≈ 1 h,
za darmo). Przetestowane na trzech plikach reprezentujących wszystkie grupy
skanerów (`1006-003`, `1000-001`, `2359-004`) — wyniki w
[`OCR/AppleVision/Results/`](OCR/AppleVision/Results/)
(format: `.txt` ze znacznikami `--- page N ---`).

Jakość testu: **tekst ciągły i przypisy niemal bezbłędne** (pełne polskie
znaki, poprawne sygnatury aktów prawnych); pieczątki wpływu i odręczne
adnotacje nieczytelne; nagłówki wersalikami czasem gubią znaki diakrytyczne;
zrzuty wykresów wklejone w dokumenty (np. `1006-003` s. 17) nieczytelne;
sporadyczne pomyłki znaków (cyrylickie "г." zamiast "r.", "ga" zamiast "9a",
"Il" zamiast "II").

Rozważane alternatywy:

- **Mistral OCR 4** (API) — najlepsza jakość na rynku (szczególnie tabele,
  wyjście w Markdown), $4/1000 stron ($2 w trybie batch) → cały korpus
  ~$11–22. Model **nie jest open source** — self-hosting tylko w licencji
  enterprise. Opcja, gdyby jakość Apple Vision okazała się niewystarczająca.
- **Bielik** (SpeakLeash) — to wyłącznie tekstowy LLM, **nie ma modelu
  OCR/wizyjnego** — może służyć co najwyżej do post-processingu
  rozpoznanego tekstu.
- **tesseract/ocrmypdf** — darmowe i lokalne, jedyna droga do PDF-ów
  z przeszukiwalną warstwą tekstową "z pudełka", ale jakość polskiego druku
  słabsza od Vision; otwarte modele wizyjne (DeepSeek-OCR, olmOCR 2) —
  lokalnie na Macu wolne, jakość tabel poniżej Mistrala.
