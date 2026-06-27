#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
academy_gui_embedded.py — GUI dla Akademii (M/W)

Moduł daje:
1) AcademyFrame          – zakładka z listą zawodników Akademii (MEN/WOMEN) z flagami.
2) AcademySummaryFrame   – zakładka z podsumowaniem Akademii (MEN/WOMEN):
                           Kraj, Pozostali, Nowi, Łącznie, Cena.
3) AcademyRootFrame      – główna ramka z wewnętrznym Notebookiem:
                           zakładki "Lista" + "Podsumowanie".

Standardowy entrypoint dla combined:
    build_academies_root(parent)  → AcademyRootFrame

Pliki domyślne (względem katalogu z tym plikiem):
- S51/Akademia M S51.csv
- S51/Akademia W S51.csv
- S51/Sztab M S51.csv
- S51/Sztab W S51.csv

Flagi: ./flags/XXX.png (18x11)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List
from faker import Faker
import pykakasi
from unidecode import unidecode
from transliterate import translit

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import random

APP_DIR = Path(__file__).resolve().parent
FLAGS_DIR = APP_DIR / "flags"

# Pliki logujące wyciągniętych / zwolnionych z Akademii
EXTRACTED_M_PATH = APP_DIR / "S51/Akademia Wyciągnięci M S51.csv"
EXTRACTED_W_PATH = APP_DIR / "S51/Akademia Wyciągnięci W S51.csv"
FIRED_M_PATH     = APP_DIR / "S51/Akademia Zwolnieni M S51.csv"
FIRED_W_PATH     = APP_DIR / "S51/Akademia Zwolnieni W S51.csv"

kks = pykakasi.kakasi()

__all__ = [
    "AcademyFrame",
    "AcademySummaryFrame",
    "AcademyRootFrame",
    "build_gui",
    "build_academy_summary",
    "build_academies_root",
]

# Grupy krajów do kolorowania wyciągniętych juniorów: nazwa → (zbiór NAT, kolor tła)
JUNIOR_COUNTRY_GROUPS: dict = {
    "persian":  ({"AFG", "IRI"},                                                              "#FFE0D0"),
    "azerbaij": ({"AZE"},                                                                     "#D0F0F8"),
    "bengali":  ({"BHU", "BAN"},                                                              "#D0EDDA"),
    "russian":  ({"BLR", "BUL", "KAZ", "KGZ", "MGL", "RUS", "TJK", "UZB"},                  "#E3D8F0"),
    "muslim":   ({"BRN", "IRQ", "KSA", "LBA", "QAT", "SOM", "SUD", "TUN", "UAE", "YEM"},    "#FFF3CC"),
    "egyptian": ({"EGY"},                                                                     "#FAEBD0"),
    "hindi":    ({"IND"},                                                                     "#FFE8CC"),
    "hebrew":   ({"ISR"},                                                                     "#D5E8F8"),
    "laotian":  ({"LAO"},                                                                     "#FFD5D5"),
    "moroccan": ({"MAR"},                                                                     "#E8D5F0"),
    "nepalese": ({"NEP"},                                                                     "#F8D5E8"),
    "thai":     ({"THA"},                                                                     "#D5F0EE"),
}
# Odwrotny słownik: NAT → tag
_NAT_TO_GROUP_TAG: dict = {
    nat: f"grp_{grp}"
    for grp, (nats, _) in JUNIOR_COUNTRY_GROUPS.items()
    for nat in nats
}

# Globalny schowek
_FAKER_CACHE = {}
FAKER_LOCALES = {}

def initialize_faker_data():
    global FAKER_LOCALES
    import os
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_file = os.path.join(script_dir, "ALL_NATIONS_ACADEMIES.csv")
    
    if os.path.exists(mapping_file):
        try:
            # ZMIANA: Dodajemy encoding="cp1250" zamiast utf-8
            df = pd.read_csv(mapping_file, sep=";", encoding="cp1250")
            
            # Czyszczenie danych
            df['Kraj'] = df['Kraj'].astype(str).str.strip().str.upper()
            df['Faker_Locale'] = df['Faker_Locale'].astype(str).str.strip()
            
            FAKER_LOCALES = dict(zip(df['Kraj'], df['Faker_Locale']))
            print(f"Załadowano pomyślnie {len(FAKER_LOCALES)} krajów.")
        except Exception as e:
            # Jeśli cp1250 też zawiedzie, spróbujmy bez podawania encodingu (systemowy)
            try:
                df = pd.read_csv(mapping_file, sep=";")
                FAKER_LOCALES = dict(zip(df['Kraj'].str.strip(), df['Faker_Locale'].str.strip()))
            except:
                messagebox.showerror("Błąd kodowania", f"Nie udało się odczytać pliku. Szczegóły:\n{e}")
    else:
        messagebox.showerror("Brak pliku", "Nie znaleziono ALL_NATIONS_ACADEMIES.csv")

import pykakasi
from unidecode import unidecode
from transliterate import translit

# Inicjalizacja konwertera dla Japonii
kks = pykakasi.kakasi()

def clean_and_romanize(text, locale):
    if not text:
        return ""
        
    # Japonia (ja_JP) - pykakasi zwraca małe litery, więc je czyścimy
    if locale == "ja_JP":
        result = kks.convert(text)
        return " ".join([item['hepburn'] for item in result])

    # Gruzja i kraje słowiańskie
    if locale == "ka_GE":
        return translit(text, 'ka', reversed=True)
    
    slavic_locales = {'bg_BG': 'bg', 'ru_RU': 'ru', 'uk_UA': 'uk'}
    if locale in slavic_locales:
        return translit(text, slavic_locales[locale], reversed=True)

    # Reszta świata - usuwamy tylko ślaczki
    romanized = unidecode(text)
    for char in ["'", "`", "^"]:
        romanized = romanized.replace(char, "")
    
    return romanized.strip()

# Uruchomienie ładowania bazy przy starcie
initialize_faker_data()

def get_faker_name(country_val, sex):
    val = str(country_val).strip().upper()
    locale = FAKER_LOCALES.get(val, "en_US")
    
    if locale not in _FAKER_CACHE:
        try:
            _FAKER_CACHE[locale] = Faker(locale)
        except:
            _FAKER_CACHE[locale] = Faker("en_US")
            
    fake = _FAKER_CACHE[locale]
    
    try:
        # Pobieramy imię i nazwisko jako osobne zmienne
        if str(sex).upper() == "W":
            f_name = fake.first_name_female()
            l_name = fake.last_name_female()
        else:
            f_name = fake.first_name_male()
            l_name = fake.last_name_male()
        
        # Romanizujemy oba człony osobno
        f_name_rom = clean_and_romanize(f_name, locale)
        l_name_rom = clean_and_romanize(l_name, locale)
        
        # FORMATOWANIE: NAZWISKO (wielkie) Imie (zwykłe)
        # .upper() zamieni nazwisko na DUŻE LITERY
        # .title() upewni się, że imię zaczyna się od wielkiej litery
        return f"{l_name_rom.upper()} {f_name_rom.title()}"
        
    except:
        # Fallback w razie błędu generatora
        raw_name = clean_and_romanize(fake.name(), locale)
        return raw_name.upper() # W ostateczności wszystko wielkimi
    
def _read_csv_any(path: Path) -> pd.DataFrame:
    """Próbuje różne kodowania i auto-separator; w ostateczności średnik."""
    last = None
    for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc)
        except Exception as e:
            last = e
    try:
        return pd.read_csv(path, sep=";", encoding="utf-8")
    except Exception:
        raise RuntimeError(f"Nie mogę wczytać CSV: {path}\n{last}")

def _norm_header(s: str) -> str:
    s = str(s or "").strip().lower()
    import unicodedata, re
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s

def _canon_academy_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ujednolica nagłówki na:
      Kraj, Zawodnik, Wiek, UM, Forma, Tempo, Pot
    Niczego nie usuwa, tylko przemapowuje znane kolumny.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"])

    mapping = {
        "kraj": "Kraj",
        "nat": "Kraj",
        "country": "Kraj",

        "zawodnik": "Zawodnik",
        "name": "Zawodnik",

        "wiek": "Wiek",
        "age": "Wiek",

        "um": "UM",
        "forma": "Forma",

        "tempo": "Tempo",

        "pot": "Pot",
        "potential": "Pot",
    }

    rename = {}
    for c in df.columns:
        key = _norm_header(c)
        if key in mapping:
            rename[c] = mapping[key]

    out = df.copy()
    if rename:
        out = out.rename(columns=rename)

    # dopilnuj, żeby wszystkie potrzebne kolumny istniały
    for col in ["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"]:
        if col not in out.columns:
            out[col] = ""

    # typy numeryczne – jak się nie da przekonwertować całej kolumny, zostawiamy jak było
    for col in ["Wiek", "UM", "Forma", "Tempo"]:
        try:
            out[col] = pd.to_numeric(out[col])
        except Exception:
            # odpowiednik errors="ignore" – przy problemach nic nie zmieniamy
            pass

    # uporządkuj kolejność, reszta na koniec
    base = ["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"]
    tail = [c for c in out.columns if c not in base]
    return out[base + tail]

def _append_row_to_csv(path: Path, row: pd.Series):
    """
    Dopina pojedynczego zawodnika do pliku CSV:
    - pilnuje nagłówków jak w Akademii (Kraj, Zawodnik, Wiek, UM, Forma, Tempo, Pot)
    - zapisuje w formacie ; + cp1250
    """
    import pandas as pd

    # upewnij się, że wiersz jest "kanoniczny"
    base = _canon_academy_df(pd.DataFrame([row.to_dict()]))

    if path.exists():
        try:
            old = _read_csv_any(path)
            old = _canon_academy_df(old)
            out = pd.concat([old, base], ignore_index=True)
        except Exception:
            out = base
    else:
        out = base

    # zapis jak reszta Akademii
    out.to_csv(path, sep=";", encoding="cp1250", index=False)

# ---------- losowanie Pot / UM / Forma / Tempo ----------

_POT_LEVELS = ["bw", "w", "ś", "n", "bn"]

# bazowe "wagi" potencjału dla słabego / mocnego scouta
# (UM=1 → BASE_LOW, UM=100 → BASE_HIGH, reszta liniowa)
_BASE_LOW_POT = {
    "bw": 1,
    "w":  3,
    "ś":  8,
    "n":  13,
    "bn": 25,
}
_BASE_HIGH_POT = {
    "bw": 25,
    "w":  13,
    "ś":  8,
    "n":  3,
    "bn": 1,
}


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _pot_weights_for_um(um_val) -> dict:
    """Interpoluje wagi Pot w zależności od UM scouta (1–100)."""
    try:
        um = float(um_val)
    except Exception:
        um = 0.0
    # mapujemy 1–100 → 0–1
    t = 0.0
    if um > 1:
        t = max(0.0, min(1.0, (um - 1.0) / 99.0))

    out = {}
    for lvl in _POT_LEVELS:
        lo = _BASE_LOW_POT[lvl]
        hi = _BASE_HIGH_POT[lvl]
        w = _lerp(lo, hi, t)
        out[lvl] = max(0.0001, float(w))
    return out


def _weighted_choice(items, weights):
    """Prosty weighted random z użyciem random.uniform."""
    total = float(sum(weights))
    if total <= 0:
        return items[-1]
    r = random.uniform(0.0, total)
    acc = 0.0
    for item, w in zip(items, weights):
        acc += w
        if r <= acc:
            return item
    return items[-1]


def _draw_pot_for_scout(um_scout) -> str:
    """Losuje Pot (bw/w/ś/n/bn) na podstawie UM scouta."""
    wmap = _pot_weights_for_um(um_scout)
    items = list(_POT_LEVELS)
    weights = [wmap[k] for k in items]
    return _weighted_choice(items, weights)


def _um_range_for_pot_and_sex(pot: str, sex: str) -> tuple[int, int]:
    """
    Zwraca (min_um, max_um) dla danej płci i potencjału.
    sex: 'M' lub 'W'
    """
    pot = str(pot or "").strip().lower()
    sex = str(sex or "").strip().upper()[:1]

    ranges_m = {
        "bw": (13, 16),
        "w":  (10, 13),
        "ś":  (7, 10),
        "n":  (4, 7),
        "bn": (1, 4),
    }
    ranges_w = {
        "bw": (9, 12),
        "w":  (7, 10),
        "ś":  (5, 8),
        "n":  (3, 6),
        "bn": (1, 4),
    }

    base = ranges_m if sex == "M" else ranges_w
    lo, hi = base.get(pot, base["n"])
    return int(lo), int(hi)


def _draw_um_and_forma_for_pot(pot: str, sex: str) -> tuple[int, int]:
    """
    Losuje UM i Formę z tego samego zakresu zależnego od (Pot, płeć).
    Osobne losowanie dla UM i Formy.
    """
    lo, hi = _um_range_for_pot_and_sex(pot, sex)
    if hi < lo:
        hi = lo
    um = random.randint(lo, hi)
    forma = random.randint(lo, hi)
    return um, forma


def _tempo_min_max_for_um(um_val) -> tuple[int, int]:
    """
    Zakres tempa:
    - min rośnie ~liniowo od 1 (UM=1) do 10 (UM=100)
    - max = 20 od UM>=40 w górę, poniżej rośnie stopniowo
    """
    try:
        um = float(um_val)
    except Exception:
        um = 0.0

    # min: 1 → 10
    if um <= 1:
        t = 0.0
    elif um >= 100:
        t = 1.0
    else:
        t = (um - 1.0) / 99.0
    min_t = int(round(1.0 + 9.0 * t))
    min_t = max(1, min_t)

    # max: rośnie 12 → 20 do UM=40, potem stałe 20
    if um >= 40:
        max_t = 20
    else:
        tt = max(0.0, min(1.0, um / 40.0))
        max_t = int(round(12.0 + (20.0 - 12.0) * tt))
        max_t = max(min_t + 1, max_t)

    max_t = max(min_t + 1, min(20, max_t))
    return min_t, max_t


def _build_tempo_column(um_val) -> list[int]:
    """
    Buduje 20-elementową kolumnę tempa dla danego UM scouta.
    Wyższy UM → więcej wartości blisko max_t.
    UM≈40 ma pojedynczą 20-tkę (minimalna szansa na max).
    """
    min_t, max_t = _tempo_min_max_for_um(um_val)
    vals = list(range(min_t, max_t + 1))
    span = max(1, max_t - min_t)

    column: list[int] = []
    # bias rośnie z UM
    try:
        um = float(um_val)
    except Exception:
        um = 0.0
    t = max(0.0, min(1.0, (um - 1.0) / 99.0))

    for _ in range(20):
        weights = []
        for v in vals:
            x = (v - min_t) / span  # 0..1
            # niski UM → preferencja niskich temp
            # wysoki UM → preferencja wysokich temp
            w_low = (1.0 - x) + 0.1
            w_high = (x * x) + 0.1
            w = _lerp(w_low, w_high, t)
            weights.append(max(0.0001, w))
        column.append(_weighted_choice(vals, weights))

    # special case: UM ≈ 40 -> dokładnie jedna 20-tka
    if 39.5 <= um <= 40.5:
        # ustaw ostatnią wartość na 20
        column[-1] = 20
        # wszystkie wcześniejsze maxy >19 obcinamy do 19
        for i in range(len(column) - 1):
            if column[i] > 19:
                column[i] = 19

    return column


def _draw_tempo_for_scout(um_val) -> float:
    """
    Losuje Tempo:
    - buduje 20-elementową kolumnę (1–20)
    - wybiera losowy element
    - dzieli przez 10 → zakres 0.1–2.0
    """
    col = _build_tempo_column(um_val)
    if not col:
        return 0.1
    raw = float(random.choice(col))
    tempo = raw / 10.0
    # zaokrąglamy do jednego miejsca po przecinku, żeby uniknąć śmieci typu 1.799999
    return round(tempo, 1)


def _academy_new_from_um(um_val) -> int:
    """Zwraca liczbę nowych zawodników na podstawie UM scouta."""
    try:
        um = float(um_val)
    except Exception:
        return 0

    if um < 0:
        return 0
    if um <= 39:
        return 2
    if um <= 49:
        return 3
    if um <= 59:
        return 4
    if um <= 69:
        return 5
    if um <= 77:
        return 6
    if um <= 85:
        return 7
    if um <= 93:
        return 8
    return 10


def _fmt_money_eur(val: int | float) -> str:
    """Format: 123 456"""
    try:
        n = int(round(float(val)))
    except Exception:
        return ""
    return f"{n:,}".replace(",", " ")


# ---------- helpers: struktury ----------

@dataclass
class _TabState:
    frame: ttk.Frame
    tv: ttk.Treeview
    vsb: ttk.Scrollbar
    hsb: ttk.Scrollbar
    df: pd.DataFrame
    images: List[tk.PhotoImage]  # referencje do flag (żeby GC ich nie zjadł)


# ---------- GŁÓWNA ZAKŁADKA AKADEMII (lista zawodników) ----------

class AcademyFrame(ttk.Frame):
    """
    Zakładka z listą zawodników Akademii.
    Dwie podzakładki: MEN / WOMEN, dane z:
    - S51/Akademia M S51.csv
    - S51/Akademia W S51.csv
    """

    def __init__(
        self,
        parent,
        men_path: Path | str = APP_DIR / "S51/Akademia M S51.csv",
        women_path: Path | str = APP_DIR / "S51/Akademia W S51.csv",
        flags_dir: Path | str = FLAGS_DIR,
    ):
        super().__init__(parent)
        self.flags_dir = Path(flags_dir)
        self._flag_cache: Dict[str, Optional[tk.PhotoImage]] = {}

        self.men_var = tk.StringVar(value=str(men_path))
        self.women_var = tk.StringVar(value=str(women_path))

        self._tabs: Dict[str, _TabState] = {}
        self._build_ui()

    # ---- flag loader ----
    def _get_flag(self, code: Optional[str]) -> Optional[tk.PhotoImage]:
        if not code:
            return None
        key = str(code).strip().upper()
        if not key:
            return None
        if key in self._flag_cache:
            return self._flag_cache[key]

        candidates = [
            self.flags_dir / f"{key}.png",
            self.flags_dir / f"{key}.gif",
            self.flags_dir / f"{key.lower()}.png",
            self.flags_dir / f"{key.lower()}.gif",
        ]
        img = None
        for p in candidates:
            if p.exists():
                try:
                    img = tk.PhotoImage(file=str(p))
                    break
                except Exception:
                    img = None
        self._flag_cache[key] = img
        return img

    # ---- UI ----
    def _build_ui(self):
        # Pasek na górze z plikami
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(bar, text="MEN:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.men_var, width=28).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Button(bar, text="…", width=3, command=self._pick_men).pack(side=tk.LEFT)
        ttk.Button(bar, text="Wczytaj MEN", command=lambda: self._reload_tab("MEN")).pack(side=tk.LEFT, padx=(6, 4))
        ttk.Button(
            bar,
            text="Rozwój MEN (nowy sezon)",
            command=lambda: self._advance_season("MEN"),
        ).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(bar, text="WOMEN:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.women_var, width=28).pack(side=tk.LEFT, padx=(4, 2))
        ttk.Button(bar, text="…", width=3, command=self._pick_women).pack(side=tk.LEFT)
        ttk.Button(bar, text="Wczytaj WOMEN", command=lambda: self._reload_tab("WOMEN")).pack(side=tk.LEFT, padx=(6, 4))
        ttk.Button(
            bar,
            text="Rozwój WOMEN (nowy sezon)",
            command=lambda: self._advance_season("WOMEN"),
        ).pack(side=tk.LEFT, padx=(4, 0))

        # Drugi wiersz - przeniesienie plików Akademii (M+W) do nowego sezonu (czysta kopia)
        bar2 = ttk.Frame(self)
        bar2.pack(fill=tk.X, padx=8, pady=(0, 4))

        ttk.Button(
            bar2,
            text="Nowy sezon →",
            command=self._kopiuj_na_nowy_sezon,
        ).pack(side=tk.LEFT)
        ttk.Label(
            bar2,
            text="(kopiuje Akademia M i Akademia W do folderu kolejnego sezonu i zmienia nazwy plików)",
            foreground="#666",
        ).pack(side=tk.LEFT, padx=(8, 0))

        # menu kontekstowe (prawy klik) – będzie używane przez konkretne tv z MEN/WOMEN
        self._ctx_tv = None
        self._ctx_tag = None
        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(
            label="Wyciągnij do kadry",
            command=lambda: self._move_selected("extracted"),
        )
        self._menu.add_command(
            label="Zwolnij",
            command=lambda: self._move_selected("fired"),
        )

        # Notebook z dwiema zakładkami
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        for tag in ("MEN", "WOMEN"):
            page = ttk.Frame(self.nb)
            self.nb.add(page, text=tag)

            tv = ttk.Treeview(
                page,
                show="tree headings",      # tree (#0) + nagłówki kolumn
                selectmode="extended",
                height=22,
            )
            vsb = ttk.Scrollbar(page, orient="vertical", command=tv.yview)
            hsb = ttk.Scrollbar(page, orient="horizontal", command=tv.xview)
            tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            tv.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            page.grid_rowconfigure(0, weight=1)
            page.grid_columnconfigure(0, weight=1)

            tv.tag_configure("mark_14",   background="#FFB366")  # 14-latkowie
            tv.tag_configure("mark_need", background="#CCFFCC")  # potrzebni do kadry
            tv.tag_configure("mark_both", background="#FF9933")  # oboje

            st = _TabState(page, tv, vsb, hsb, pd.DataFrame(), [])
            self._tabs[tag] = st
            tv.bind("<Button-3>", lambda e, tag=tag, tv=tv: self._on_right_click(e, tag, tv))

            btn_bar = ttk.Frame(page)
            btn_bar.grid(row=2, column=0, columnspan=2, sticky="w", padx=4, pady=3)
            ttk.Button(
                btn_bar,
                text="Zaznacz kandydatów do kadry",
                command=lambda t=tag: self._mark_promotion_candidates(t),
            ).pack(side=tk.LEFT, padx=2)
            ttk.Button(
                btn_bar,
                text="Wyczyść oznaczenia",
                command=lambda t=tag: self._clear_marks(t),
            ).pack(side=tk.LEFT, padx=2)

        # pierwsze wczytanie, nie płacz jeśli pliku brak
        self._reload_tab("MEN", initial=True)
        self._reload_tab("WOMEN", initial=True)

    # ---- file pickers ----
    def _pick_men(self):
        p = filedialog.askopenfilename(
            title="Wybierz plik Akademia M",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
        )
        if not p:
            return
        self.men_var.set(p)
        self._reload_tab("MEN")

    def _pick_women(self):
        p = filedialog.askopenfilename(
            title="Wybierz plik Akademia W",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
        )
        if not p:
            return
        self.women_var.set(p)
        self._reload_tab("WOMEN")

    def _kopiuj_na_nowy_sezon(self):
        """
        Przenosi pliki Akademia M S<X>.csv i Akademia W S<X>.csv z folderu ./S<X>/
        do ./S<X+1>/ i zmienia im nazwy na Akademia M/W S<X+1>.csv.
        Bez żadnych modyfikacji zawartości - czysta kopia + zmiana nazwy
        (analogicznie do przycisku 'Nowy sezon' w zakładce Infrastruktura).
        """
        import re as _re2
        import shutil as _shutil
        from pathlib import Path as _Path

        sukcesy: List[str] = []
        bledy: List[str] = []

        for label, var in (("Akademia M", self.men_var), ("Akademia W", self.women_var)):
            cur_path = _Path(var.get().strip())
            if not cur_path.is_file():
                bledy.append(f"{label}: nie znaleziono pliku\n{cur_path}")
                continue

            # Wykryj numer sezonu z nazwy pliku / folderu, np. ".../S51/Akademia M S51.csv" -> S51
            match = _re2.search(r"S(\d+)", str(cur_path))
            if not match:
                bledy.append(f"{label}: nie udało się wykryć numeru sezonu ze ścieżki")
                continue

            cur_num = int(match.group(1))
            next_num = cur_num + 1
            cur_tag = f"S{cur_num}"
            next_tag = f"S{next_num}"

            # Folder docelowy (jak w zakładce Infrastruktura)
            next_dir = cur_path.parent.parent / next_tag
            next_dir.mkdir(parents=True, exist_ok=True)
            dst_path = next_dir / f"{label} {next_tag}.csv"

            try:
                _shutil.copyfile(cur_path, dst_path)
            except Exception as e:
                bledy.append(f"{label}: błąd zapisu\n{e}")
                continue

            var.set(str(dst_path))
            sukcesy.append(f"{label}: {cur_tag} → {next_tag}\n  {dst_path}")

        if sukcesy:
            self._reload_tab("MEN")
            self._reload_tab("WOMEN")

        parts = []
        if sukcesy:
            parts.append("Skopiowano bez zmian:\n" + "\n".join(sukcesy))
        if bledy:
            parts.append("Błędy:\n" + "\n".join(bledy))

        if bledy and not sukcesy:
            messagebox.showerror("Nowy sezon", "\n\n".join(parts), parent=self)
        elif bledy:
            messagebox.showwarning("Nowy sezon – częściowo", "\n\n".join(parts), parent=self)
        else:
            messagebox.showinfo("Nowy sezon – gotowe", "\n\n".join(parts), parent=self)

    # ---- reload + fill ----
    def _reload_tab(self, tag: str, initial: bool = False):
        st = self._tabs.get(tag)
        if not st:
            return

        path_str = self.men_var.get() if tag == "MEN" else self.women_var.get()
        path = Path(path_str)

        if not path.exists():
            if not initial:
                messagebox.showwarning("Brak pliku", f"Nie znaleziono pliku:\n{path}", parent=self)
            st.df = pd.DataFrame(columns=["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"])
            self._fill_tree(st)
            return

        try:
            df_raw = _read_csv_any(path)
            df = _canon_academy_df(df_raw)
        except Exception as e:
            if not initial:
                messagebox.showerror("Błąd wczytywania", str(e), parent=self)
            st.df = pd.DataFrame(columns=["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"])
            self._fill_tree(st)
            return

        st.df = df.reset_index(drop=True)
        self._fill_tree(st)

    def _load_junior_trainers(self, tag: str) -> Dict[str, float]:
        """
        Zwraca mapę {NAT: UM trenera juniorów} dla danej płci.
        Szuka w plikach:
            S51/Sztab M S51.csv  (MEN)
            S51/Sztab W S51.csv  (WOMEN)

        Filtrowanie po kodzie 'TJ' albo nazwie zawierającej 'trener junior'.
        Jeśli nic nie znajdzie – zwraca pusty dict i zawodnicy rosną tylko z RNG.
        """
        import pandas as pd

        sex = "M" if tag == "MEN" else "W"
        staff_path = APP_DIR / "S51" / f"Sztab {sex} S51.csv"

        if not staff_path.exists():
            return {}

        try:
            df = _read_csv_any(staff_path)
        except Exception:
            return {}

        # rozpoznanie podstawowych kolumn
        rename: Dict[str, str] = {}
        nat_col = None
        um_col = None
        code_col = None
        name_col = None

        for c in df.columns:
            key = _norm_header(c)
            if key in ("nat", "kraj", "country"):
                nat_col = nat_col or c
            elif key == "um":
                um_col = um_col or c
            elif key in ("code", "kod", "rola", "stanowisko", "pozycja", "funkcja"):
                code_col = code_col or c
            elif key in ("name", "imieinazwisko", "nazwisko"):
                name_col = name_col or c

        if nat_col and nat_col != "NAT":
            rename[nat_col] = "NAT"
            nat_col = "NAT"
        if um_col and um_col != "UM":
            rename[um_col] = "UM"
            um_col = "UM"

        if rename:
            df = df.rename(columns=rename)

        if nat_col is None or um_col is None:
            return {}

        # filtr na trenerów juniorów: Code zawiera 'TJ' lub nazwa zawiera 'trener junior'
        import pandas as _pd
        mask = _pd.Series(False, index=df.index)

        if code_col and code_col in df.columns:
            mask |= df[code_col].astype(str).str.upper().str.contains("TJ")

        if name_col and name_col in df.columns:
            mask |= df[name_col].astype(str).str.lower().str.contains("trener junior")

        df = df[mask]
        if df.empty:
            return {}

        df = df.dropna(subset=[nat_col, "UM"])
        if df.empty:
            return {}

        out: Dict[str, float] = {}
        gb = df.groupby(nat_col)["UM"].max()
        for nat, um in gb.items():
            try:
                out[str(nat).upper()] = float(um)
            except Exception:
                continue
        return out

    def _advance_season(self, tag: str):
        """
        Rozwój zawodników Akademii na nowy sezon.

        Dla każdego zawodnika:
          wiek   = wiek + 1
          UM     = UM + (UM_trenera_juniorów / 20 * Tempo) + RNG[0..2]
          Forma  = Forma + (UM_trenera_juniorów / 20 * Tempo) + RNG[0..2]
          Tempo  = bez zmian
          Pot    = bez zmian

        Wyniki są zaokrąglane do int i zapisywane z powrotem do pliku CSV.
        """
        import random
        from pathlib import Path
        import pandas as pd

        path_str = self.men_var.get() if tag == "MEN" else self.women_var.get()
        path = Path(path_str)

        if not path.exists():
            messagebox.showwarning("Akademia", f"Plik nie istnieje:\n{path}")
            return

        try:
            df = _read_csv_any(path)
            df = _canon_academy_df(df)
        except Exception as e:
            messagebox.showerror("Akademia", f"Nie mogę wczytać pliku:\n{path}\n\n{e}")
            return

        if df.empty:
            messagebox.showinfo("Akademia", "Brak zawodników do aktualizacji.")
            return

        # mapa {NAT: UM trenera juniorów}
        trainers = self._load_junior_trainers(tag)

        # dopilnuj typów
        for col in ["Wiek", "UM", "Forma"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        rng = random.Random()

        new_age = []
        new_um = []
        new_forma = []

        for _, row in df.iterrows():
            nat = str(row.get("Kraj", "") or "").upper()
            trener_um = float(trainers.get(nat, 0.0) or 0.0)

            # wiek +1
            age = row.get("Wiek")
            try:
                age_f = float(age) if pd.notna(age) else None
            except Exception:
                age_f = None
            if age_f is not None:
                new_age.append(int(round(age_f + 1)))
            else:
                new_age.append(age)

            # parametry do wzoru
            def _to_float(x, default=0.0):
                try:
                    return float(x) if pd.notna(x) else default
                except Exception:
                    return default

            um0 = _to_float(row.get("UM"), 0.0)
            forma0 = _to_float(row.get("Forma"), 0.0)

            tempo_raw = row.get("Tempo")
            if isinstance(tempo_raw, str):
                tempo_raw = tempo_raw.replace(",", ".")
            tempo = _to_float(tempo_raw, 0.0)

            base_gain = (trener_um / 20.0) * tempo

            rand_gain_um = rng.randint(0, 2)
            rand_gain_forma = rng.randint(0, 2)

            um_new_f = um0 + base_gain + rand_gain_um
            forma_new_f = forma0 + base_gain + rand_gain_forma

            um_new = int(round(um_new_f))
            forma_new = int(round(forma_new_f))

            if um_new < 0:
                um_new = 0
            if forma_new < 0:
                forma_new = 0

            new_um.append(um_new)
            new_forma.append(forma_new)

        df["Wiek"] = new_age
        df["UM"] = new_um
        df["Forma"] = new_forma

        # zapis – standardowo CSV z ';' i cp1250 (pod Excela)
        try:
            df.to_csv(path, sep=";", encoding="cp1250", index=False)
        except Exception as e:
            messagebox.showerror("Akademia", f"Nie udało się zapisać pliku:\n{path}\n\n{e}")
            return

        # odśwież widok
        self._reload_tab(tag)
        messagebox.showinfo(
            "Akademia",
            f"Zaktualizowano rozwój zawodników ({tag})."
        )

    def _fill_tree(self, st: _TabState):
        tv = st.tv
        df = st.df if isinstance(st.df, pd.DataFrame) else pd.DataFrame()

        # wyczyść wszystko
        for iid in tv.get_children(""):
            tv.delete(iid)
        st.images.clear()

        # ustaw kolumny: tree (#0) = "Kraj" z flagą, reszta jako columns
        base_cols = ["Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"]
        extra_cols = [c for c in df.columns if c not in (["Kraj"] + base_cols)]
        cols = base_cols + extra_cols

        tv["columns"] = cols

        # nagłówek #0
        tv.heading("#0", text="Kraj", command=lambda st=st: self._sort_by(st, "Kraj", False))
        tv.column("#0", width=70, anchor=tk.W, stretch=False)

        # nagłówki pozostałe
        for c in cols:
            tv.heading(c, text=str(c), command=lambda col=c, st=st: self._sort_by(st, col, False))
            series = df.get(c, pd.Series(dtype="object"))
            is_num = str(series.dtype).startswith(("int", "float"))
            anchor = tk.E if is_num else tk.W
            tv.column(c, anchor=anchor, width=90, stretch=True)

        # wiersze
        if df.empty:
            return

        kraj_series = df["Kraj"].astype(str).fillna("").str.strip()
        for idx, row in df.iterrows():
            nat = str(kraj_series.iloc[idx] or "").upper()
            img = self._get_flag(nat)
            if img is not None:
                st.images.append(img)  # pilnujemy referencji

            values = []
            for c in cols:
                v = row.get(c, "")
                # przecinek zamiast kropki dla Tempo jeżeli float
                if c == "Tempo":
                    try:
                        vv = float(v)
                        v = str(vv).replace(".", ",")
                    except Exception:
                        pass
                values.append(v)

            tv.insert("", "end", text=nat, image=img, values=values)

    # ---- zaznaczanie kandydatów do kadr ----

    def _load_juniors_count(self, sex: str) -> dict:
        """
        Zlicza {NAT: liczba zawodników <15 lat} z Zawodnicy S<X>gpt.csv
        dla danej płci (M lub W).
        """
        import re as _re
        path_str = self.men_var.get() if sex == "M" else self.women_var.get()
        m = _re.search(r"(S\d+)", str(path_str))
        if not m:
            return {}
        season_tag = m.group(1)
        base_dir = Path(path_str).parent
        p = base_dir / f"Zawodnicy {season_tag}gpt.csv"
        if not p.exists():
            return {}
        try:
            try:
                df = pd.read_csv(p, sep=";", dtype=str, encoding="utf-8-sig")
            except Exception:
                df = pd.read_csv(p, sep=";", dtype=str, encoding="cp1250")
        except Exception:
            return {}
        df.columns = [str(c).strip() for c in df.columns]
        # normalizuj nazwy kolumn
        rename = {}
        for c in df.columns:
            lc = c.lower().replace(" ", "").replace("/", "")
            if lc in ("kraj", "country", "nat"):
                rename[c] = "Kraj"
            elif lc in ("płeć", "plec", "sex", "gender"):
                rename[c] = "Płeć"
            elif lc in ("wiek", "age"):
                rename[c] = "Wiek"
        df = df.rename(columns=rename)
        if "Kraj" not in df.columns or "Wiek" not in df.columns:
            return {}
        df["Wiek"] = pd.to_numeric(df["Wiek"], errors="coerce")
        # filtr: odpowiednia płeć (jeśli kolumna istnieje) i wiek < 15
        if "Płeć" in df.columns:
            df = df[df["Płeć"].astype(str).str.strip().str.upper() == sex]
        df = df[df["Wiek"] < 15]
        count: dict = {}
        for nat in df["Kraj"].astype(str).str.strip().str.upper():
            if nat and nat != "NAN":
                count[nat] = count.get(nat, 0) + 1
        return count

    def _mark_promotion_candidates(self, tag: str):
        """
        Koloruje wiersze w zakładce MEN/WOMEN:
        - pomarańczowe (#FFB366): 14-latkowie → zawsze do kadry
        - zielone (#CCFFCC): top N per kraj wg UM+Forma → do uzupełnienia min. 4 juniorów w kadrze
        - ciemno-pomarańczowe (#FF9933): oboje jednocześnie
        """
        st = self._tabs.get(tag)
        if st is None or st.df is None or st.df.empty:
            messagebox.showinfo("Kandydaci", "Brak danych w tabeli.", parent=self)
            return
        tv = st.tv
        df = st.df.copy().reset_index(drop=True)
        sex = "M" if tag == "MEN" else "W"
        juniors_per_country = self._load_juniors_count(sex)

        df["_wiek"] = pd.to_numeric(df.get("Wiek", pd.Series(dtype=float)), errors="coerce").fillna(0)
        df["_sila"] = (
            pd.to_numeric(df.get("UM",    pd.Series(dtype=float)), errors="coerce").fillna(0)
            + pd.to_numeric(df.get("Forma", pd.Series(dtype=float)), errors="coerce").fillna(0)
        )

        idx_14   = set(df[df["_wiek"] == 14].index.tolist())
        idx_need: set = set()

        for kraj, grp in df.groupby("Kraj"):
            cur = juniors_per_country.get(str(kraj).strip().upper(), 0)
            needed = max(0, 4 - cur)
            if needed > 0:
                grp_sorted = grp.sort_values("_sila", ascending=False)
                non14 = grp_sorted[~grp_sorted.index.isin(idx_14)]
                idx_need.update(non14.head(needed).index.tolist())

        mark_tags = {"mark_14", "mark_need", "mark_both"}
        to_select = []
        for pos, iid in enumerate(tv.get_children("")):
            is14   = pos in idx_14
            is_need = pos in idx_need
            existing = [t for t in (tv.item(iid, "tags") or ()) if t not in mark_tags]
            if is14 and is_need:
                existing.append("mark_both")
                to_select.append(iid)
            elif is14:
                existing.append("mark_14")
                to_select.append(iid)
            elif is_need:
                existing.append("mark_need")
                to_select.append(iid)
            tv.item(iid, tags=tuple(existing))

        tv.selection_set(to_select)

        if not juniors_per_country:
            note = "\n(Nie znaleziono pliku Zawodnicy gpt — zaznaczono tylko 14-latków)"
        else:
            note = ""
        messagebox.showinfo(
            f"Kandydaci do kadry — {tag}",
            f"14-latków (pomarańczowe): {len(idx_14)}\n"
            f"Potrzebnych do uzupełnienia min. 4 (zielone): {len(idx_need)}\n"
            f"Łącznie do zaznaczenia: {len(to_select)}{note}",
            parent=self,
        )

    def _clear_marks(self, tag: str):
        st = self._tabs.get(tag)
        if st is None:
            return
        tv = st.tv
        mark_tags = {"mark_14", "mark_need", "mark_both"}
        for iid in tv.get_children(""):
            existing = [t for t in (tv.item(iid, "tags") or ()) if t not in mark_tags]
            tv.item(iid, tags=tuple(existing))
        tv.selection_remove(*tv.get_children(""))

    # ---- sortowanie ----
    def _sort_by(self, st: _TabState, col: str, descending: bool):
        df = st.df if isinstance(st.df, pd.DataFrame) else pd.DataFrame()
        if df is None or df.empty or col not in df.columns:
            return

        try:
            sorted_df = df.copy()
            sorted_df[col] = pd.to_numeric(sorted_df[col], errors="ignore")
            sorted_df = sorted_df.sort_values(col, ascending=not descending, kind="mergesort")
        except Exception:
            # sortuj jako string
            sorted_df = df.copy()
            sorted_df[col] = sorted_df[col].astype(str)
            sorted_df = sorted_df.sort_values(col, ascending=not descending, kind="mergesort")

        st.df = sorted_df.reset_index(drop=True)
        self._fill_tree(st)

        # odwróć kierunek na kolejny klik
        # "Kraj" jest w kolumnie drzewa (#0), nie w tv["columns"] – trzeba użyć "#0"
        heading_col = "#0" if col == "Kraj" else col
        try:
            st.tv.heading(heading_col, command=lambda st=st, col=col: self._sort_by(st, col, not descending))
        except Exception:
            pass

    def _on_right_click(self, event, tag: str, tv: ttk.Treeview):
        row = tv.identify_row(event.y)
        if not row:
            return

        # jeśli mamy już multi-select i klikamy w jednego z zaznaczonych,
        # to zostawiamy istniejące zaznaczenie
        sel = tv.selection()
        if row not in sel:
            tv.selection_set(row)

        self._ctx_tv = tv
        self._ctx_tag = tag
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _move_selected(self, target: str):
        """
        Przenieś wszystkich zaznaczonych zawodników z aktualnej tabeli MEN/WOMEN:
        - usuwa ich z DF + zapisuje z powrotem do pliku Akademii
        - dopina do odpowiedniego pliku logu (Wyciągnięci / Zwolnieni, M/W)
        - wrzuca wiersze do tabeli w zakładce Wyciągnięci / Zwolnieni
        """
        tv = getattr(self, "_ctx_tv", None)
        tag = getattr(self, "_ctx_tag", None)
        if tv is None or not tag:
            return

        st = self._tabs.get(tag)
        if not st or st.df is None or st.df.empty:
            return

        sel = list(tv.selection())
        if not sel:
            return

        # indeksy w DF odpowiadają kolejności w Treeview
        indices = sorted(tv.index(iid) for iid in sel)
        try:
            rows = st.df.iloc[indices].copy()
        except Exception:
            return

        # M / W z tagu MEN/WOMEN
        sex = "M" if tag == "MEN" else "W"

        # wybór pliku logu
        if target == "extracted":
            csv_path = EXTRACTED_M_PATH if sex == "M" else EXTRACTED_W_PATH
        else:
            csv_path = FIRED_M_PATH if sex == "M" else FIRED_W_PATH

        # dopisz wszystkich do CSV logu
        for _, row in rows.iterrows():
            try:
                _append_row_to_csv(csv_path, row)
            except Exception as e:
                messagebox.showerror(
                    "Akademie",
                    f"Nie udało się dopisać zawodnika do pliku:\n{csv_path}\n\n{e}",
                    parent=self,
                )
                # nie psujemy dalej logiki GUI, więc przerywamy tylko dopisywanie
                break

        # usuń z DF Akademii zaznaczone wiersze
        to_drop = st.df.index[indices]
        st.df = st.df.drop(to_drop).reset_index(drop=True)

        # zapis pliku głównego Akademii
        path_str = self.men_var.get() if tag == "MEN" else self.women_var.get()
        if path_str:
            try:
                st.df.to_csv(path_str, sep=";", encoding="cp1250", index=False)
            except Exception as e:
                messagebox.showerror(
                    "Akademia",
                    f"Nie udało się zapisać pliku Akademii:\n{path_str}\n\n{e}",
                    parent=self,
                )

        # odśwież widok źródłowy
        self._fill_tree(st)

        # wstaw do tabel MEN/WOMEN w zakładkach Wyciągnięci / Zwolnieni
        root = self.master.master
        sex_key = "M" if tag == "MEN" else "W"

        tv_dict = root.tv_extracted if target == "extracted" else root.tv_fired
        img_dict = root._img_extracted if target == "extracted" else root._img_fired

        tv_target = tv_dict.get(sex_key)
        if tv_target is None:
            return

        cols = ["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"]

        # dla każdej przenoszonej osoby dodaj osobny wiersz
        for _, row in rows.iterrows():
            values = []
            for c in cols:
                v = row.get(c, "")
                if c == "Tempo":
                    try:
                        vv = float(v)
                        v = str(vv).replace(".", ",")
                    except Exception:
                        pass
                values.append(v)

            nat = str(row.get("Kraj", "") or "").upper()
            # flaga – korzystamy z loadera z root (te same pliki flag)
            flag_img = root._get_flag(nat)
            if flag_img is not None:
                img_dict[sex_key].append(flag_img)

            tv_target.insert("", "end", text=nat, image=flag_img, values=values)

# ---------- ZAKŁADKA PODSUMOWANIA AKADEMII ----------

class AcademySummaryFrame(ttk.Frame):
    """
    Zakładka z podsumowaniem Akademii:
    Dwie tabelki: MEN / WOMEN

    Kolumny: Kraj, Pozostali, Nowi, Łącznie, Cena
    • Pozostali – liczba zawodników w Akademii (per Kraj)
    • Nowi – liczba nowych na podstawie UM scouta (z pliku Sztab)
    • Łącznie = Pozostali + Nowi
    • Cena = Łącznie * 35000
    """

    def __init__(
        self,
        parent,
        academy_m_path: Path | str = APP_DIR / "S51/Akademia M S51.csv",
        academy_w_path: Path | str = APP_DIR / "S51/Akademia W S51.csv",
        staff_m_path: Path | str = APP_DIR / "S51/Sztab M S51.csv",
        staff_w_path: Path | str = APP_DIR / "S51/Sztab W S51.csv",
        flags_dir: Path | str = FLAGS_DIR,
    ):
        super().__init__(parent)
        self.flags_dir = Path(flags_dir)
        self._flag_cache: Dict[str, Optional[tk.PhotoImage]] = {}

        self.academy_m_var = tk.StringVar(value=str(academy_m_path))
        self.academy_w_var = tk.StringVar(value=str(academy_w_path))
        self.staff_m_var = tk.StringVar(value=str(staff_m_path))
        self.staff_w_var = tk.StringVar(value=str(staff_w_path))

        self._tv_men: Optional[ttk.Treeview] = None
        self._tv_women: Optional[ttk.Treeview] = None
        self._img_men: List[tk.PhotoImage] = []
        self._img_women: List[tk.PhotoImage] = []
        self._df_men: pd.DataFrame = pd.DataFrame()
        self._df_women: pd.DataFrame = pd.DataFrame()

        self._build_ui()
        self._recalc_all(initial=True)

    # ----- flagi -----
    def _get_flag(self, code: Optional[str]) -> Optional[tk.PhotoImage]:
        if not code:
            return None
        key = str(code).strip().upper()
        if not key:
            return None
        if key in self._flag_cache:
            return self._flag_cache[key]

        candidates = [
            self.flags_dir / f"{key}.png",
            self.flags_dir / f"{key}.gif",
            self.flags_dir / f"{key.lower()}.png",
            self.flags_dir / f"{key.lower()}.gif",
        ]
        img = None
        for p in candidates:
            if p.exists():
                try:
                    img = tk.PhotoImage(file=str(p))
                    break
                except Exception:
                    img = None
        self._flag_cache[key] = img
        return img

    # ----- UI -----
    def _build_ui(self):
        # Pasek ścieżek + przycisk "Przelicz"
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(bar, text="Akademia M:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.academy_m_var, width=28).pack(side=tk.LEFT, padx=(4, 8))

        ttk.Label(bar, text="Akademia W:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.academy_w_var, width=28).pack(side=tk.LEFT, padx=(4, 8))

        ttk.Label(bar, text="Sztab M:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.staff_m_var, width=24).pack(side=tk.LEFT, padx=(4, 8))

        ttk.Label(bar, text="Sztab W:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.staff_w_var, width=24).pack(side=tk.LEFT, padx=(4, 8))

        ttk.Button(bar, text="Eksportuj Podsumowanie", command=self._export_combined_summary).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bar, text="Przelicz", command=self._recalc_all).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bar, text="Dodaj nowych juniorów", command=self._add_new_juniors).pack(side=tk.RIGHT, padx=(8, 0))

        # Dwie tabelki obok siebie
        pan = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        pan.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        frame_m = ttk.Labelframe(pan, text="MEN")
        frame_w = ttk.Labelframe(pan, text="WOMEN")
        pan.add(frame_m, weight=1)
        pan.add(frame_w, weight=1)

        self._tv_men = self._build_table(frame_m)
        self._tv_women = self._build_table(frame_w)

    def _build_table(self, parent: ttk.Frame) -> ttk.Treeview:
        tv = ttk.Treeview(
            parent,
            show="tree headings",
            selectmode="browse",
            height=22,
        )
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tv.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        cols = ["Pozostali", "Nowi", "Łącznie", "Cena"]
        tv["columns"] = cols

        # sortowanie po Kraj (kolumna #0)
        tv.heading(
            "#0",
            text="Kraj",
            command=lambda tv=tv: self._sort_summary(tv, "Kraj", False),
        )
        tv.column("#0", width=70, anchor=tk.W, stretch=False)

        for c in cols:
            anchor = tk.E
            tv.heading(
                c,
                text=c,
                command=lambda col=c, tv=tv: self._sort_summary(tv, col, False),
            )
            tv.column(c, width=90, anchor=anchor, stretch=True)

        return tv

    def _export_combined_summary(self):
        """Automatyczny eksport danych do folderu sezonu bez otwierania okna dialogowego."""
        if self._df_men.empty and self._df_women.empty:
            messagebox.showwarning("Eksport", "Brak danych do eksportu!")
            return

        # 1. Wykrywanie sezonu z nazwy wczytanego pliku
        input_path_str = self.academy_m_var.get()
        input_path = Path(input_path_str)
        file_name = input_path.name
        
        import re
        match = re.search(r"S\d+", file_name, re.IGNORECASE)
        season_tag = match.group(0).upper() if match else "Global"
        
        # 2. Przygotowanie ścieżki (./SXX/Koszty Juniorów SXX.csv)
        target_dir = APP_DIR / season_tag
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            
        file_name_out = f"Koszty Juniorów {season_tag}.csv"
        final_path = target_dir / file_name_out

        # 3. Łączenie danych MEN i WOMEN
        df_m = self._df_men.copy()
        df_w = self._df_women.copy()

        # Mapowanie kolumn dla czytelności w Excelu
        df_m = df_m.rename(columns={
            "Pozostali": "Pozostali M",
            "Nowi": "Nowi M",
            "Łącznie": "Łącznie M",
            "Cena": "Cena M"
        })
        df_w = df_w.rename(columns={
            "Pozostali": "Pozostali W",
            "Nowi": "Nowi W",
            "Łącznie": "Łącznie W",
            "Cena": "Cena W"
        })

        # Złączenie tabel po kolumnie Kraj
        combined = pd.merge(df_m, df_w, on="Kraj", how="outer").fillna(0)
        
        # Obliczenie sumy kosztów (M+W)
        combined["Suma Kosztów"] = combined["Cena M"] + combined["Cena W"]

        # Ustalenie kolejności kolumn
        cols_order = [
            "Kraj", 
            "Pozostali M", "Nowi M", "Łącznie M", 
            "Pozostali W", "Nowi W", "Łącznie W", 
            "Suma Kosztów"
        ]
        
        # Filtrowanie tylko istniejących kolumn
        final_cols = [c for c in cols_order if c in combined.columns]
        combined = combined[final_cols]

        # 4. Automatyczny zapis
        try:
            combined.to_csv(final_path, sep=";", encoding="cp1250", index=False)
            
            # Opcjonalne powiadomienie w pasku statusu lub krótkie info
            messagebox.showinfo("Eksport Automatyczny", 
                                f"Plik zapisany pomyślnie!\n\nLokalizacja: {season_tag}/{file_name_out}")
        except Exception as e:
            messagebox.showerror("Błąd Zapisu", f"Nie udało się zapisać pliku automatycznie:\n{e}")

    # ----- logika ładowania danych -----
    def _load_academy(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame(columns=["Kraj", "Zawodnik"])
        df_raw = _read_csv_any(path)
        df = _canon_academy_df(df_raw)
        return df

    def _load_scouts(self, path: Path) -> Dict[str, float]:
        """
        Zwraca dict {NAT: max_UM_scouta}.
        Szuka wierszy gdzie kolumna z nazwą stanowiska zawiera 'scout'.
        """
        if not path.exists():
            return {}

        df = _read_csv_any(path)
        # Oczyść BOM i niewidoczne znaki z nagłówków
        df.columns = [str(c).encode('utf-8', 'ignore').decode('utf-8').strip().lstrip('﻿').lstrip('ď»ż') for c in df.columns]

        # ujednolicanie nagłówków
        rename: Dict[str, str] = {}
        name_col = None
        nat_col = None
        um_col = None

        for c in df.columns:
            key = _norm_header(c)
            if key in ("nat", "kraj", "country"):
                nat_col = nat_col or c
            elif key == "um":
                um_col = um_col or c
            elif key in ("name", "stanowisko", "rola", "pozycja", "funkcja"):
                name_col = name_col or c

        if nat_col and nat_col != "NAT":
            rename[nat_col] = "NAT"
            nat_col = "NAT"
        if um_col and um_col != "UM":
            rename[um_col] = "UM"
            um_col = "UM"

        if rename:
            df = df.rename(columns=rename)

        # filtr na scoutów
        if name_col and name_col in df.columns:
            mask = df[name_col].astype(str).str.lower().str.contains("scout|skaut")
            df = df[mask]

        if "NAT" not in df.columns or "UM" not in df.columns:
            return {}

        df = df.dropna(subset=["NAT", "UM"])
        if df.empty:
            return {}

        out: Dict[str, float] = {}
        gb = df.groupby("NAT")["UM"].max()
        for nat, um in gb.items():
            try:
                out[str(nat).upper()] = float(um)
            except Exception:
                continue
        return out

    def _compute_summary_rows(self, academy_df: pd.DataFrame, scouts: Dict[str, float]):
        # Pozostali (tylko ci powyżej 10 lat, czyli od 11 w górę)
        remaining: Dict[str, int] = {}
        if not academy_df.empty:
            df_active = academy_df.copy()
            
            # Filtrowanie po wieku
            if "Wiek" in df_active.columns:
                df_active["Wiek"] = pd.to_numeric(df_active["Wiek"], errors="coerce")
                df_active = df_active[df_active["Wiek"] > 10]
            
            if "Kraj" in df_active.columns:
                grp = df_active.groupby("Kraj")["Zawodnik"].count()
                for nat, cnt in grp.items():
                    remaining[str(nat).upper()] = int(cnt)

        # Pobranie listy krajów ze sztabu i akademii
        countries = sorted(set(remaining.keys()) | set(k.upper() for k in scouts.keys()))

        rows = []
        for nat in countries:
            poz = int(remaining.get(nat, 0))
            um_scout = scouts.get(nat)
            new = _academy_new_from_um(um_scout) if um_scout is not None else 0
            total = poz + new
            price = total * 35000
            rows.append({
                "Kraj": nat,
                "Pozostali": poz,
                "Nowi": new,
                "Łącznie": total,
                "Cena": price,
            })
        return rows

    # ----- główna aktualizacja -----
    def _recalc_all(self, initial: bool = False):
        try:
            m_path = Path(self.academy_m_var.get())
            w_path = Path(self.academy_w_var.get())
            sm_path = Path(self.staff_m_var.get())
            sw_path = Path(self.staff_w_var.get())

            df_m = self._load_academy(m_path)
            df_w = self._load_academy(w_path)
            scouts_m = self._load_scouts(sm_path)
            scouts_w = self._load_scouts(sw_path)

            rows_m = self._compute_summary_rows(df_m, scouts_m)
            rows_w = self._compute_summary_rows(df_w, scouts_w)

            self._df_men = pd.DataFrame(rows_m)
            self._df_women = pd.DataFrame(rows_w)

            self._fill_table(self._tv_men, self._df_men, self._img_men)
            self._fill_table(self._tv_women, self._df_women, self._img_women)

        except Exception as e:
            if not initial:
                messagebox.showerror("Błąd", f"Nie udało się przeliczyć Akademii:\n{e}", parent=self)

    def _fill_table(self, tv: Optional[ttk.Treeview], df: pd.DataFrame, img_store: List[tk.PhotoImage]):
        if tv is None:
            return

        for iid in tv.get_children(""):
            tv.delete(iid)
        img_store.clear()

        if df is None or df.empty:
            return

        for _, row in df.iterrows():
            nat = row.get("Kraj", "")
            img = self._get_flag(nat)
            if img is not None:
                img_store.append(img)

            values = [
                row.get("Pozostali", 0),
                row.get("Nowi", 0),
                row.get("Łącznie", 0),
                _fmt_money_eur(row.get("Cena", 0)),
            ]
            tv.insert("", "end", text=nat, image=img, values=values)

    def _generate_new_juniors_for_sex(
        self,
        academy_df: pd.DataFrame,
        scouts: Dict[str, float],
        sex: str,
    ) -> pd.DataFrame:
        """
        Tworzy DataFrame z nowymi juniorami dla danej płci:
        - liczba nowych = _academy_new_from_um(UM scouta) dla kraju
        - Kraj = kod kraju
        - Zawodnik = '{Kraj} M' / '{Kraj} W'
        - Wiek = 10
        - UM, Forma, Tempo, Pot losowane wg reguł
        """
        sex = str(sex or "").strip().upper()[:1]
        if sex not in ("M", "W"):
            return pd.DataFrame(columns=["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"])

        rows = []
        # upewnij się, że akademia ma kanoniczne nagłówki
        base_df = _canon_academy_df(academy_df) if isinstance(academy_df, pd.DataFrame) else pd.DataFrame()

        for nat_raw, um_scout in scouts.items():
            nat = str(nat_raw or "").strip().upper()
            if not nat:
                continue
            new_cnt = _academy_new_from_um(um_scout)
            if new_cnt <= 0:
                continue

            for _ in range(new_cnt):
                pot = _draw_pot_for_scout(um_scout)
                um, forma = _draw_um_and_forma_for_pot(pot, sex)
                tempo = _draw_tempo_for_scout(um_scout)

                name = f"{nat} {'M' if sex == 'M' else 'W'}"
                rows.append({
                    "Kraj": nat,
                    "Zawodnik": name,
                    "Wiek": 10,
                    "UM": um,
                    "Forma": forma,
                    "Tempo": tempo,
                    "Pot": pot,
                })

        if not rows:
            return pd.DataFrame(columns=["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"])

        df_new = pd.DataFrame(rows)
        df_new = _canon_academy_df(df_new)

        # opcjonalnie możesz tu posortować, np. po Kraj, Zawodnik
        df_new = df_new.sort_values(["Kraj", "Zawodnik"]).reset_index(drop=True)
        return df_new

    def _add_new_juniors(self):
        """
        Wczytuje Akademia M/W + Sztab M/W,
        generuje nowych juniorów wg kolumn 'Nowi',
        dopisuje do plików Akademii i odświeża podsumowanie.
        """
        from pathlib import Path

        try:
            m_path = Path(self.academy_m_var.get())
            w_path = Path(self.academy_w_var.get())
            sm_path = Path(self.staff_m_var.get())
            sw_path = Path(self.staff_w_var.get())

            df_m = self._load_academy(m_path)
            df_w = self._load_academy(w_path)
            scouts_m = self._load_scouts(sm_path)
            scouts_w = self._load_scouts(sw_path)

            new_m = self._generate_new_juniors_for_sex(df_m, scouts_m, sex="M")
            new_w = self._generate_new_juniors_for_sex(df_w, scouts_w, sex="W")

            if (new_m is None or new_m.empty) and (new_w is None or new_w.empty):
                messagebox.showinfo(
                    "Akademie",
                    "Brak nowych juniorów do dodania (wszędzie Nowi = 0 albo brak scoutów).",
                    parent=self,
                )
                return

            # dopięcie do istniejących danych
            if isinstance(df_m, pd.DataFrame) and not df_m.empty and isinstance(new_m, pd.DataFrame) and not new_m.empty:
                out_m = pd.concat([_canon_academy_df(df_m), new_m], ignore_index=True)
            elif isinstance(new_m, pd.DataFrame) and not new_m.empty:
                out_m = new_m.copy()
            else:
                out_m = df_m

            if isinstance(df_w, pd.DataFrame) and not df_w.empty and isinstance(new_w, pd.DataFrame) and not new_w.empty:
                out_w = pd.concat([_canon_academy_df(df_w), new_w], ignore_index=True)
            elif isinstance(new_w, pd.DataFrame) and not new_w.empty:
                out_w = new_w.copy()
            else:
                out_w = df_w

            # zapis CSV (spójnie z resztą – średnik + cp1250)
            if m_path:
                try:
                    out_m.to_csv(m_path, sep=";", encoding="cp1250", index=False)
                except Exception as e:
                    messagebox.showerror(
                        "Akademia M",
                        f"Nie udało się zapisać pliku Akademii M:\n{e}",
                        parent=self,
                    )
                    return

            if w_path:
                try:
                    out_w.to_csv(w_path, sep=";", encoding="cp1250", index=False)
                except Exception as e:
                    messagebox.showerror(
                        "Akademia W",
                        f"Nie udało się zapisać pliku Akademii W:\n{e}",
                        parent=self,
                    )
                    return

            # przelicz po dodaniu
            self._recalc_all(initial=False)

            cnt_m = 0 if new_m is None or new_m.empty else len(new_m)
            cnt_w = 0 if new_w is None or new_w.empty else len(new_w)
            parts = []
            if cnt_m:
                parts.append(f"MEN: {cnt_m}")
            if cnt_w:
                parts.append(f"WOMEN: {cnt_w}")
            info = ", ".join(parts) if parts else "0"

            messagebox.showinfo(
                "Akademie",
                f"Dodano nowych juniorów: {info}",
                parent=self,
            )

        except Exception as e:
            messagebox.showerror("Akademie", f"Błąd podczas dodawania juniorów:\n{e}", parent=self)

    def _sort_summary(self, tv: ttk.Treeview, col: str, descending: bool):
        """
        Sortowanie po dowolnej kolumnie w podsumowaniu:
        - tv: którą tabelkę sortujemy (MEN / WOMEN)
        - col: 'Kraj', 'Pozostali', 'Nowi', 'Łącznie' albo 'Cena'
        """
        # wybór DF i magazynu flag
        if tv is self._tv_men:
            df = self._df_men
            img_store = self._img_men
        elif tv is self._tv_women:
            df = self._df_women
            img_store = self._img_women
        else:
            return

        if df is None or df.empty:
            return

        sorted_df = df.copy()

        if col == "Kraj":
            sorted_df = sorted_df.sort_values(
                "Kraj",
                ascending=not descending,
                kind="mergesort",
            )
        else:
            # próba sortowania numerycznie
            try:
                sorted_df[col] = pd.to_numeric(sorted_df[col], errors="ignore")
            except Exception:
                pass
            sorted_df = sorted_df.sort_values(
                col,
                ascending=not descending,
                kind="mergesort",
            )

        sorted_df = sorted_df.reset_index(drop=True)

        # zapisz z powrotem
        if tv is self._tv_men:
            self._df_men = sorted_df
        else:
            self._df_women = sorted_df

        # odśwież widok
        self._fill_table(tv, sorted_df, img_store)

        # podmień callback nagłówka na przeciwny kierunek
        if col == "Kraj":
            tv.heading("#0", command=lambda tv=tv: self._sort_summary(tv, "Kraj", not descending))
        else:
            tv.heading(col, command=lambda col=col, tv=tv: self._sort_summary(tv, col, not descending))

# ---------- ROOT: Akademie (Lista + Podsumowanie + logi) ----------

# ---------- ROOT: Akademie (Lista + Podsumowanie + logi) ----------

class AcademyRootFrame(ttk.Frame):
    """
    Główna ramka Akademii: wewnętrzny Notebook z zakładkami:
    - "Lista"         → AcademyFrame
    - "Podsumowanie"  → AcademySummaryFrame
    - "Wyciągnięci"   → log wyciągniętych z Akademii (MEN/WOMEN)
    - "Zwolnieni"     → log zwolnionych z Akademii (MEN/WOMEN)
    """

    def __init__(self, parent):
        super().__init__(parent)

        # flagi dla logów
        self.flags_dir = FLAGS_DIR
        self._flag_cache: Dict[str, Optional[tk.PhotoImage]] = {}

        # osobne listy na obrazki per płeć, żeby GC ich nie zjadł
        self._img_extracted: Dict[str, List[tk.PhotoImage]] = {"M": [], "W": []}
        self._img_fired: Dict[str, List[tk.PhotoImage]] = {"M": [], "W": []}

        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True)

        # --- Lista ---
        self.tab_list = AcademyFrame(nb)
        nb.add(self.tab_list, text="Lista")

        # --- Podsumowanie ---
        self.tab_sum = AcademySummaryFrame(nb)
        nb.add(self.tab_sum, text="Podsumowanie")

        # --- Wyciągnięci ---
        self.tab_extracted = ttk.Frame(nb)
        nb.add(self.tab_extracted, text="Wyciągnięci")

        # --- Zwolnieni ---
        self.tab_fired = ttk.Frame(nb)
        nb.add(self.tab_fired, text="Zwolnieni")

        # pod-notebooki MEN/WOMEN
        self.nb_extracted = ttk.Notebook(self.tab_extracted)
        self.nb_extracted.pack(fill=tk.BOTH, expand=True)

        self.nb_fired = ttk.Notebook(self.tab_fired)
        self.nb_fired.pack(fill=tk.BOTH, expand=True)

        # słowniki: {"M": Treeview, "W": Treeview}
        self.tv_extracted: Dict[str, ttk.Treeview] = {}
        self.tv_fired: Dict[str, ttk.Treeview] = {}

        for sex, label in (("M", "MEN"), ("W", "WOMEN")):
            # --- Wyciągnięci ---
            frm_e = ttk.Frame(self.nb_extracted)
            self.nb_extracted.add(frm_e, text=label)
            self.tv_extracted[sex] = self._build_simple_table(frm_e)
            
            # Kontener na przyciski
            btn_frame_e = ttk.Frame(frm_e)
            btn_frame_e.grid(row=2, column=0, columnspan=2, pady=5, sticky="w")

            ttk.Button(btn_frame_e, text="Odśwież", command=self._load_logs_into_tables).pack(side=tk.LEFT, padx=2)
            ttk.Button(btn_frame_e, text="Generuj imiona", command=lambda s=sex: self._fix_names_in_csv(s)).pack(side=tk.LEFT, padx=2)
            
            # NOWY PRZYCISK
            ttk.Button(
                btn_frame_e, 
                text="Przenieś do bazy głównej", 
                command=lambda s=sex: self._export_to_main_database(s)
            ).pack(side=tk.LEFT, padx=2)

            # --- Zwolnieni ---
            frm_f = ttk.Frame(self.nb_fired)
            self.nb_fired.add(frm_f, text=label)
            self.tv_fired[sex] = self._build_simple_table(frm_f)

            # Przycisk odświeżania pod tabelą Zwolnionych
            ttk.Button(
                frm_f, 
                text="Odśwież z pliku", 
                command=self._load_logs_into_tables
            ).grid(row=2, column=0, pady=5, sticky="w", padx=5)
        # po zbudowaniu – wczytaj dane z CSV
        self._load_logs_into_tables()

    def _on_double_click(self, event, tv):
        """Otwiera pole edycji dla kolumny Zawodnik."""
        region = tv.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = tv.identify_column(event.x)
        item_id = tv.identify_row(event.y)
        
        # Sprawdzamy, czy kliknięto w kolumnę "Zawodnik" 
        # (W Twoim kodzie to kolumna #2, bo #0 to ikona, #1 to Kraj)
        if column != "#2":
            return

        # Pobieramy współrzędne komórki
        x, y, width, height = tv.bbox(item_id, column)

        # Tworzymy tymczasowe pole Entry nałożone na tabelę
        val_at_now = tv.item(item_id, "values")[1] # Indeks 1 to Zawodnik
        entry = ttk.Entry(tv)
        entry.insert(0, val_at_now)
        entry.select_range(0, tk.END)
        entry.focus_set()

        # Umieszczamy Entry dokładnie nad komórką
        entry.place(x=x, y=y, width=width, height=height)

        def save_edit(event=None):
            new_val = entry.get()
            old_values = list(tv.item(item_id, "values"))
            old_values[1] = new_val # Aktualizujemy imię i nazwisko
            tv.item(item_id, values=old_values)
            
            # Po edycji w GUI musimy zapisać zmiany do pliku CSV
            self._save_after_edit(tv, item_id, new_val)
            entry.destroy()

        # Zatwierdzenie Enterem, anulowanie Escapem lub kliknięciem obok
        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", lambda e: entry.destroy())
        entry.bind("<Escape>", lambda e: entry.destroy())

    def _save_after_edit(self, tv, item_id, new_name):
        """Zapisuje zmienione imię do odpowiedniego pliku CSV z obsługą kodowania."""
        sex = "M"
        # Sprawdzamy, do którego słownika należy tabela (M czy W)
        for s, tree in self.tv_extracted.items():
            if tree == tv: sex = s
        
        # Wybieramy ścieżkę na podstawie płci
        path = EXTRACTED_M_PATH if sex == "M" else EXTRACTED_W_PATH
        
        if path.exists():
            try:
                # Pobieramy wszystkie wiersze z Treeview, aby zaktualizować cały plik
                all_rows = []
                for iid in tv.get_children():
                    row_vals = tv.item(iid, "values")
                    all_rows.append(row_vals)
                
                # Tworzymy DataFrame i zapisujemy wymuszając cp1250 (standard Twoich plików)
                new_df = pd.DataFrame(all_rows, columns=["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"])
                new_df.to_csv(path, sep=";", index=False, encoding="cp1250")
            except Exception as e:
                print(f"Błąd zapisu po edycji: {e}")

    # ---- flagi dla logów ----
    def _get_flag(self, code: Optional[str]) -> Optional[tk.PhotoImage]:
        if not code:
            return None
        key = str(code).strip().upper()
        if not key:
            return None
        if key in self._flag_cache:
            return self._flag_cache[key]

        candidates = [
            self.flags_dir / f"{key}.png",
            self.flags_dir / f"{key}.gif",
            self.flags_dir / f"{key.lower()}.png",
            self.flags_dir / f"{key.lower()}.gif",
        ]
        img = None
        for p in candidates:
            if p.exists():
                try:
                    img = tk.PhotoImage(file=str(p))
                    break
                except Exception:
                    img = None
        self._flag_cache[key] = img
        return img

    def _build_simple_table(self, parent: ttk.Frame) -> ttk.Treeview:
        """
        Prosta tabelka logów:
        - #0: flaga + Kraj (tekst)
        - kolumny: Kraj (schowana), Zawodnik, Wiek, UM, Forma, Tempo, Pot
        - sortowanie po kliknięciu w nagłówek
        """
        tv = ttk.Treeview(
            parent,
            show="tree headings",   # tree (#0) + nagłówki kolumn
            selectmode="browse",
            height=22,
        )
        for grp, (_, color) in JUNIOR_COUNTRY_GROUPS.items():
            tv.tag_configure(f"grp_{grp}", background=color)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tv.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        cols = ["Kraj", "Zawodnik", "Wiek", "UM", "Forma", "Tempo", "Pot"]
        tv["columns"] = cols

        # kolumna #0 – flaga + Kraj, nagłówek pusty
        tv.heading("#0", text="Kraj", command=lambda: self._sort_log(tv, "Kraj", False))
        tv.column("#0", width=70, anchor=tk.W, stretch=False)

        for c in cols:
            anchor = tk.E if c in ("Wiek", "UM", "Forma", "Tempo") else tk.W

            tv.heading(
                c,
                text=c,
                command=lambda _c=c: self._sort_log(tv, _c, False),
            )

            if c == "Kraj":
                tv.column(c, width=1, anchor=anchor, stretch=False)
            else:
                tv.column(c, width=90, anchor=anchor, stretch=True)

        tv.bind("<Double-1>", lambda event: self._on_double_click(event, tv))

        return tv

    def _load_logs_into_tables(self) -> None:
        specs = [
            ("M", EXTRACTED_M_PATH, self.tv_extracted, self._img_extracted),
            ("W", EXTRACTED_W_PATH, self.tv_extracted, self._img_extracted),
            ("M", FIRED_M_PATH,     self.tv_fired,     self._img_fired),
            ("W", FIRED_W_PATH,     self.tv_fired,     self._img_fired),
        ]

        for sex, path, tv_dict, img_dict in specs:
            tv = tv_dict.get(sex)
            if tv is None or not path.exists():
                continue

            # WYCZYŚĆ TABELĘ PRZED ŁADOWANIEM (zapobiega dublowaniu)
            for iid in tv.get_children():
                tv.delete(iid)
            img_dict[sex].clear()

            try:
                # Próba wczytania (utf-8-sig obsłuży Twoje nowe zapisy z BOM)
                try:
                    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
                except:
                    df = pd.read_csv(path, sep=";", encoding="cp1250")

                for _, row in df.iterrows():
                    kraj = str(row['Kraj']).strip().upper()
                    
                    row_tag = _NAT_TO_GROUP_TAG.get(kraj, "")

                    img = self._get_flag(kraj)
                    if img:
                        img_dict[sex].append(img)

                    tv.insert(
                        "", "end",
                        text=f" {kraj}",
                        image=img if img else "",
                        values=list(row),
                        tags=(row_tag,)
                    )
                # TUTAJ BYŁ RETURN - USUNĄŁEM GO
            except Exception as e:
                print(f"Błąd ładowania {path}: {e}")

    def _sort_log(self, tv: ttk.Treeview, col: str, descending: bool) -> None:
        """
        Sortuje zawartość logów i przełącza kierunek sortowania.
        """
        items = list(tv.get_children(""))
        if not items:
            return

        # Pobieranie wartości do sortowania
        def get_value(iid: str):
            # Jeśli sortujemy po 'Kraj', bierzemy wartość z pierwszej kolumny (index 0)
            vals = tv.item(iid, "values") or []
            if col == "Kraj":
                return vals[0] if len(vals) > 0 else ""
            
            # Dla pozostałych kolumn szukamy indeksu
            cols = list(tv["columns"])
            try:
                idx = cols.index(col)
                return vals[idx]
            except (ValueError, IndexError):
                return ""

        data = [(get_value(iid), iid) for iid in items]

        # Funkcja pomocnicza do konwersji na liczby (dla UM, Wieku itp.)
        def to_num(v):
            s = str(v).strip().replace(",", ".")
            try:
                return float(s)
            except:
                return None

        # Sprawdzamy czy kolumna jest numeryczna
        nums = [to_num(v) for v, _ in data]
        if any(n is not None for n in nums):
            # Sortowanie numeryczne
            keyed = [(n if n is not None else -1.0, iid) for (v, iid), n in zip(data, nums)]
            keyed.sort(key=lambda x: x[0], reverse=descending)
            ordered = [iid for _, iid in keyed]
        else:
            # Sortowanie alfabetyczne
            data.sort(key=lambda x: str(x[0]).lower(), reverse=descending)
            ordered = [iid for _, iid in data]

        # Reorganizacja wierszy w tabeli
        for index, iid in enumerate(ordered):
            tv.move(iid, "", index)

        # --- KLUCZOWE: Zmiana kierunku dla następnego kliknięcia ---
        # Jeśli to kolumna Kraj (którą wyświetlamy w #0)
        if col == "Kraj":
            tv.heading("#0", command=lambda: self._sort_log(tv, "Kraj", not descending))
        
        # Aktualizacja nagłówka klikniętej kolumny
        tv.heading(col, command=lambda: self._sort_log(tv, col, not descending))

    def _fix_names_in_csv(self, sex: str):
        path = EXTRACTED_M_PATH if sex == "M" else EXTRACTED_W_PATH
        if not path.exists(): return

        try:
            # Wczytujemy (teraz już bezpiecznie)
            df = pd.read_csv(path, sep=";", encoding="cp1250")
            
            # Generujemy imiona (już przefiltrowane przez unidecode)
            df['Zawodnik'] = df.apply(lambda row: get_faker_name(row['Kraj'], sex), axis=1)
            
            # Zapisujemy do zwykłego CSV, który wszędzie zadziała
            df.to_csv(path, sep=";", index=False, encoding="cp1250")
            
            self._load_logs_into_tables()
            messagebox.showinfo("Sukces", "Imiona wygenerowane i zamienione na alfabet łaciński!")
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Szczegóły: {e}")

    def _export_to_main_database(self, sex: str):
        """Przenosi zawodników do bazy głównej Zawodnicy <sezon>gpt.csv"""
        # 1. Ustalenie ścieżek
        source_path = EXTRACTED_M_PATH if sex == "M" else EXTRACTED_W_PATH
        if not source_path.exists():
            messagebox.showwarning("Błąd", f"Nie znaleziono pliku: {source_path.name}")
            return

        import re
        match = re.search(r"S\d+", source_path.name)
        season = match.group(0) if match else "S51" # fallback na S51
        
        # Zakładamy, że baza główna jest w tym samym folderze co logi (S51)
        target_path = APP_DIR / "S51" / f"Zawodnicy {season}gpt.csv"
        
        try:
            # 2. Wczytanie wyciągniętych juniorów (Średnik, cp1250)
            df_extracted = pd.read_csv(source_path, sep=";", encoding="cp1250")
            if df_extracted.empty:
                messagebox.showinfo("Info", "Brak zawodników w tym pliku.")
                return

            # 3. Wczytanie bazy głównej (Przecinek, UTF-8), aby sprawdzić _ROWID
            if target_path.exists():
                # Używamy utf-8, bo tak wygląda Twój plik gpt.csv
                df_main = pd.read_csv(target_path, sep=",", encoding="utf-8")
                last_id = df_main['_ROWID'].max() if '_ROWID' in df_main.columns else -1
            else:
                df_main = pd.DataFrame(columns=['Zawodnik','Kraj','Płeć','JUN/SEN','Wiek','UM','Forma','PrawoStartu','Kontuzja','_ROWID'])
                last_id = -1

            if pd.isna(last_id): last_id = -1

            # 4. Mapowanie danych na format bazy głównej
            new_entries = pd.DataFrame({
                'Zawodnik': df_extracted['Zawodnik'],
                'Kraj': df_extracted['Kraj'],
                'Płeć': sex,
                'JUN/SEN': 'JUN',
                'Wiek': df_extracted['Wiek'],
                'UM': df_extracted['UM'],
                'Forma': df_extracted['Forma'],
                'PrawoStartu': 8,
                'Kontuzja': 0
            })

            # Nadanie kolejnych _ROWID
            start_id = int(last_id) + 1
            new_entries['_ROWID'] = range(start_id, start_id + len(new_entries))

            # Pomocnicza: unikalna nazwa z sufiksem II/III/IV (źródłem prawdy jest SQLite)
            _SUFFIXES = ["II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

            def _unique_name(base, cur_db, seen_batch):
                """Zwraca unikalną nazwę sprawdzając SQLite + nazwy już dodane w tej paczce."""
                def _free(candidate):
                    if candidate in seen_batch:
                        return False
                    cur_db.execute(
                        "SELECT COUNT(*) FROM zawodnicy WHERE zawodnik = ? COLLATE NOCASE",
                        (candidate,)
                    )
                    return cur_db.fetchone()[0] == 0
                if _free(base):
                    return base
                for suf in _SUFFIXES:
                    candidate = f"{base} {suf}"
                    if _free(candidate):
                        return candidate
                return f"{base} X+"

            # 5+6. SQLite → ustal nazwy → zapisz CSV i bazę jednocześnie
            db_path = APP_DIR / "manager_skokow.db"
            dodano_db = 0
            przemianowani = []
            seen_batch = set()

            if db_path.exists():
                import sqlite3 as _sqlite3
                conn_db = _sqlite3.connect(str(db_path))
                conn_db.row_factory = _sqlite3.Row
                cur_db = conn_db.cursor()

                for idx_r in new_entries.index:
                    orig  = str(new_entries.at[idx_r, "Zawodnik"]).strip()
                    kraj  = str(new_entries.at[idx_r, "Kraj"]).strip()
                    nazwa = _unique_name(orig, cur_db, seen_batch)
                    seen_batch.add(nazwa)
                    # Ujednolicona nazwa trafia i do CSV i do SQLite
                    new_entries.at[idx_r, "Zawodnik"] = nazwa
                    if nazwa != orig:
                        przemianowani.append(f"{orig} → {nazwa}")
                    cur_db.execute(
                        "INSERT INTO zawodnicy (zawodnik, kraj, \"płeć\") VALUES (?, ?, ?)",
                        (nazwa, kraj, sex)
                    )
                    zawodnik_id = cur_db.lastrowid
                    cur_db.execute(
                        "INSERT INTO statystyki_kariery (zawodnik_id) VALUES (?)",
                        (zawodnik_id,)
                    )
                    dodano_db += 1

                conn_db.commit()
                conn_db.close()
                db_info = f"\nSQLite: dodano {dodano_db} zawodników"
            else:
                db_info = "\nSQLite: nie znaleziono manager_skokow.db"

            # Zapis CSV z już ujednoliconymi nazwami
            final_df = pd.concat([df_main, new_entries], ignore_index=True)
            final_df.to_csv(target_path, sep=",", index=False, encoding="utf-8")

            rename_info = ""
            if przemianowani:
                rename_info = "\nPrzemianowani: " + ", ".join(przemianowani)

            messagebox.showinfo("Sukces",
                f"Przeniesiono {len(new_entries)} osób do {target_path.name}.\n"
                f"Nowe ID od {start_id} do {new_entries['_ROWID'].max()}."
                + db_info + rename_info)
            
        except Exception as e:
            messagebox.showerror("Błąd kodowania/zapisu", 
                f"Nie udało się wyeksportować danych.\nUpewnij się, że plik docelowy nie jest otwarty w Excelu.\n\nSzczegóły: {e}")
            
# ---------- PUBLIC API ----------

def build_gui(parent) -> AcademyRootFrame:
    """Domyślny builder: zwraca główną ramkę Akademii (Lista + Podsumowanie)."""
    return AcademyRootFrame(parent)


def build_academy_summary(parent) -> AcademySummaryFrame:
    """Buduje samą zakładkę z podsumowaniem Akademii (MEN/WOMEN)."""
    return AcademySummaryFrame(parent)


def build_academies_root(parent) -> AcademyRootFrame:
    """Główny entrypoint dla combined – to wykorzystuj w połączeniu."""
    return AcademyRootFrame(parent)


# ---------- standalone (do szybkiego testu modułu) ----------

class _App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Akademie – test GUI")
        try:
            self.state("zoomed")
        except Exception:
            self.geometry("1400x800")

        root = AcademyRootFrame(self)
        root.pack(fill=tk.BOTH, expand=True)


if __name__ == "__main__":
    _App().mainloop()
