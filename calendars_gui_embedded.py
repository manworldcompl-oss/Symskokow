#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calendars GUI (embedded)

• Czyta wszystkie pliki CSV z folderu ./Kalendarze i tworzy zakładkę na każdy plik.
• Nazwy zakładek bez prefiksu: "Kalendarze_S51_" / "Kalendarz_S51_" / "Kalendarze_" / "Kalendarz_".
• Tabela jest sortowalna, z autosizing kolumn.
• Kolorowanie wierszy wg wartości w wybranej kolumnie (np. IND/TEAM/MIX/KO…):
  - domyślna kolumna: pierwsza pasująca z ["Typ","Rodzaj","Zawody","Tryb","Event"].
  - domyślne reguły kolorów (można przeładować):
        IND → #d7ecff, TEAM → #e6f7d6, MIX → #f3e6ff, KO → #ffe6cc,
        KO64 → #ffe6cc, KO50 → #ffe6cc, T4S → #fff4b3, QUAL → #f0f0f0
• Moduł udostępnia funkcję build_gui(parent), oraz uruchamia się samodzielnie (main).

Uwaga: brak zależności od własnych klas Table/FrozenFirstColTable — czysty Tkinter + pandas.
"""

from __future__ import annotations
import os
import pandas as pd
import re
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional
import random


def _desired_tab_index_fallback(parent_nb, nbM, nbW, nbC, tab_name: str) -> int:
    name = str(tab_name).upper()
    if parent_nb is nbC:
        order = ['WCH','NKIC','UNI','JWC']
    else:
        order = ['GP','SCOC','WC','COC','FC','JC','MC','PC','QC','TC','AC','BC','DC']
    prefix = name.split('-')[0]
    try:
        pos = order.index(prefix)
    except ValueError:
        return 'end'
    try:
        end = parent_nb.index('end') or 0
    except Exception:
        end = 0
    existing = [parent_nb.tab(i, 'text') for i in range(end)]
    idx = 0
    for t in existing:
        p2 = str(t).upper().split('-')[0]
        try:
            if order.index(p2) <= pos:
                idx += 1
        except ValueError:
            idx += 1
    return idx

try:
    from PIL import Image, ImageTk  # lepsza obsługa PNG
except Exception:
    Image = ImageTk = None

try:
    import pandas as pd
except Exception as e:  # pragma: no cover
    raise SystemExit("Ten moduł wymaga pandas: pip install pandas")

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DIR = APP_DIR / "./S51/Kalendarze"
FLAG_DIR = APP_DIR / "flags"  # 18x11 px

# ===================== helpers =====================

def _strip_prefixes(stem: str) -> str:
    s = str(stem)
    for pref in ("Kalendarze_S51_", "Kalendarz_S51_", "Kalendarze_", "Kalendarz_"):
        if s.startswith(pref):
            return s[len(pref):]
    return s

_DEF_COLOR_RULES = {
    r"\bIND\b": "#d7ecff",
    r"\bTEAM\b": "#e6f7d6",
    r"\bMIX\b": "#f3e6ff",
    r"\bKO(?:64|50)?\b": "#ffe6cc",
    r"\bT4S\b": "#fff4b3",
    r"\bQUAL|Q\b": "#f0f0f0",
}

_POSSIBLE_TYPE_COLS = ["Typ", "Rodzaj", "Zawody", "Tryb", "Event"]

# ===================== Frekwencja (attendance) =====================

_FREKWENCJA_BASE: dict[str, float] = {
    "WC-M": 0.70, "WC-W": 0.70,
    "GP-M": 0.60, "GP-W": 0.60,
    "COC-M": 0.60, "COC-W": 0.60,
    "FC-M": 0.50, "FC-W": 0.50,
    "SCOC-M": 0.50, "SCOC-W": 0.50,
    "JC-M": 0.40, "JC-W": 0.40,
    "MC-M": 0.35, "MC-W": 0.35,
    "PC-M": 0.32, "PC-W": 0.32,
    "QC-M": 0.29, "QC-W": 0.29,
    "TC-M": 0.26, "TC-W": 0.26,
    "AC-M": 0.24, "AC-W": 0.24,
    "BC-M": 0.22, "BC-W": 0.22,
    "DC-M": 0.20, "DC-W": 0.20,
    # Mistrzostwa (klucz = base_seria)
    "OG": 1.00, "WCH": 0.90, "SFWC": 0.80,
    "NKIC": 0.80, "IST": 0.80, "COCH": 0.75,
    "JWC": 0.65, "YOG": 0.50, "UNI": 0.50,
}

_TURNIEJE_BONUS: dict[str, float] = {
    "TCS": 0.22, "RA": 0.13, "NT": 0.10,
    "FT": 0.08, "BB": 0.08, "W5": 0.07, "P7": 0.06,
}

# (rank_max_inclusive, bonus)
_KRAJ_BONUS_TIERS: list[tuple[int, float]] = [
    (5,  0.00),
    (10, 0.03),
    (20, 0.07),
    (35, 0.12),
    (9999, 0.18),
]

def _reorder_columns_case_insensitive(df: pd.DataFrame, desired: list[str]) -> list[str]:
    """Zwraca listę kolumn DF w kolejności desired (case-insensitive),
    a na końcu dorzuca resztę kolumn w ich obecnej kolejności.
    """
    # mapowanie lower->oryginał
    lower_map = {c.lower(): c for c in df.columns}
    picked = []
    used = set()
    for want in desired:
        key = want.lower()
        if key in lower_map:
            picked.append(lower_map[key]); used.add(lower_map[key])
        else:
            # spróbuj też wariantów bez kropek/spacji
            compact = key.replace(".", "").replace(" ", "")
            for c in df.columns:
                ck = c.lower(); ck2 = ck.replace(".", "").replace(" ", "")
                if ck == key or ck2 == compact:
                    picked.append(c); used.add(c); break
    # reszta w kolejności wystąpienia
    picked += [c for c in df.columns if c not in used]
    return picked

@dataclass
class TabState:
    frame: ttk.Frame
    tree: ttk.Treeview
    vsb: ttk.Scrollbar
    hsb: ttk.Scrollbar
    df: pd.DataFrame
    type_col: tk.StringVar

# ===================== GUI core =====================

def _canonicalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    # Ujednolica nazwy kolumn niezależnie od wielkości liter/spacji/kropek.
    # Docelowe: 'Week', 'NAT', 'Skocznia', 'HS', 'Rodzaj', 'Dod. inf.'
    MAP = {
        r"^week$": "Week",
        r"^nat$|^kraj$": "NAT",
        r"^skocznia$": "Skocznia",
        r"^hs$": "HS",
        r"^rodzaj$|^typ$|^tryb$|^event$": "Rodzaj",
        r"^dod\.?\s*inf\.?$|^dodatkowe.*info.*$": "Dod. inf.",
    }
    new_cols = []
    for c in df.columns:
        key = str(c).strip()
        low = key.lower()
        replaced = None
        for pat, target in MAP.items():
            if re.match(pat, low, flags=re.I):
                replaced = target
                break
        new_cols.append(replaced or key)
    df = df.copy()
    df.columns = new_cols
    return df

class CalendarsFrame(ttk.Frame):
    def _init_sync(self, tvL, tvR, vsb):
        # Guard to avoid recursive yscroll callbacks
        self._ysync_flag = False
        def yset_left(first, last):
            try:
                vsb.set(first, last)
                if not self._ysync_flag:
                    self._ysync_flag = True
                    tvR.yview_moveto(first)
                    self._ysync_flag = False
            except Exception:
                pass
        def yset_right(first, last):
            try:
                vsb.set(first, last)
                if not self._ysync_flag:
                    self._ysync_flag = True
                    tvL.yview_moveto(first)
                    self._ysync_flag = False
            except Exception:
                pass
        tvL.configure(yscrollcommand=yset_left)
        tvR.configure(yscrollcommand=yset_right)
        vsb.configure(command=lambda *a: (tvL.yview(*a), tvR.yview(*a)))
        def _mw(evt):
            delta = -1 if getattr(evt, 'delta', 0) > 0 else 1
            try:
                tvL.yview_scroll(delta, 'units')
                tvR.yview_scroll(delta, 'units')
            except Exception:
                pass
            return 'break'
        for tv in (tvL, tvR):
            tv.bind('<MouseWheel>', _mw)
            tv.bind('<Button-4>', lambda e: (_mw(type('E',(),{'delta':120})()), 'break'))
            tv.bind('<Button-5>', lambda e: (_mw(type('E',(),{'delta':-120})()), 'break'))
        # Selection mirroring disabled to prevent hangs
        try:
            tvL.unbind("<<TreeviewSelect>>")
        except Exception:
            pass
        try:
            tvR.unbind("<<TreeviewSelect>>")
        except Exception:
            pass

    def __init__(self, parent, calendars_dir: Path | str = DEFAULT_DIR):
        super().__init__(parent)
        self.cal_dir = Path(calendars_dir)
        self._tabs: dict[str, TabState] = {}
        self._flag_cache: dict[str, tk.PhotoImage] = {}
        self._build()

    # ---------- UI ----------
    def _build(self):
        top = ttk.Frame(self); top.pack(fill=tk.X, padx=8, pady=(8,4))

        ttk.Label(top, text="Folder z kalendarzami:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=str(self.cal_dir))
        ttk.Entry(top, textvariable=self.dir_var, width=46).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="…", command=self._pick_dir).pack(side=tk.LEFT)
        ttk.Button(top, text="Wczytaj", command=self.reload_all).pack(side=tk.LEFT, padx=(8,0))

        ttk.Separator(self).pack(fill=tk.X, padx=8, pady=(4,0))

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # start
        self.reload_all()

    # ---------- actions ----------
    def _pick_dir(self):
        p = filedialog.askdirectory(title="Wybierz folder z kalendarzami (CSV)")
        if p:
            self.dir_var.set(p)
            self.reload_all()

    def reload_all(self):
        root = Path(self.dir_var.get())
        
        # Inicjalizacja głównych kategorii
        if not hasattr(self, 'nbM'):
            self.nbM = ttk.Notebook(self.nb)
            self.nb.add(self.nbM, text='MEN')
        if not hasattr(self, 'nbW'):
            self.nbW = ttk.Notebook(self.nb)
            self.nb.add(self.nbW, text='WOMEN')
        if not hasattr(self, 'nbC'):
            self.nbC = ttk.Notebook(self.nb)
            self.nb.add(self.nbC, text='CHAMPIONSHIPS')
            
        # --- NOWOŚĆ: Zakładka TYGODNIE ---
        if not hasattr(self, 'nbT'):
            self.nbT = ttk.Notebook(self.nb)
            self.nb.add(self.nbT, text='TYGODNIE')
        # ---------------------------------
        # --- NOWOŚĆ: Zakładka HISTORIA TURNIEJÓW ---
        if not hasattr(self, 'history_tab_frame'):
            # Tworzymy ramkę i dodajemy ją do głównego notebooka (self.nb)
            self.history_tab_frame = HistoryFrame(self.nb, self, "Historia Turniejów.csv")
            self.nb.add(self.history_tab_frame, text='HISTORIA TURNIEJÓW')
        else:
            # Jeśli już istnieje, po prostu odśwież dane
            self.history_tab_frame.load_data()
        # --- NOWOŚĆ: Zakładka ZAROBKI ---
        if not hasattr(self, 'earnings_tab'):
            self.earnings_tab = EarningsFrame(self.nb, self)
            self.nb.add(self.earnings_tab, text='ZAROBKI')
        if not hasattr(self, 'total_earnings_tab'):
            self.total_earnings_tab = TotalEarningsFrame(self.nb, self)
            self.nb.add(self.total_earnings_tab, text='ZYSK KRAJE')
        # 1. Wczytaj skocznie
        try:
            import pandas as pd
            _hills_candidates = [
                APP_DIR / "S51" / "Skocznie_S51.csv",
                APP_DIR / "S51" / "Skocznie S51.csv",
                APP_DIR / "Skocznie_S51.csv",
                APP_DIR / "Skocznie S51.csv",
                Path("S51") / "Skocznie_S51.csv",
                Path("Skocznie_S51.csv"),
            ]
            _hills_path = next((p for p in _hills_candidates if p.exists()), None)
            if _hills_path is None:
                raise FileNotFoundError("Nie znaleziono pliku Skocznie S51.csv obok aplikacji")
            hills_df = pd.read_csv(_hills_path, sep=';', encoding='cp1250')
        except Exception as e:
            print(f"Błąd wczytywania skoczni: {e}")
            hills_df = pd.DataFrame()

        # 2. Dodaj zakładkę WYMAGANIA (tylko tekst)
        if not hasattr(self, 'requirements_tab'):
            self.requirements_tab = RequirementsFrame(self.nb)
            self.nb.add(self.requirements_tab, text='WYMAGANIA')

        # 3. Dodaj zakładkę WYBÓR GOSPODARZA (interaktywna)
        if not hasattr(self, 'host_tab'):
            self.host_tab = HostSelectionFrame(self.nb, hills_df)
            self.nb.add(self.host_tab, text='WYBÓR GOSPODARZA')
        else:
            self.host_tab.hills_df = hills_df
        
        if not hasattr(self, 'planner_tab'):
            self.planner_tab = SeasonPlannerFrame(self.nb, self)
            self.nb.add(self.planner_tab, text='PLANOWANIE SEZONU')

        if not root.exists():
            messagebox.showerror("Błąd", f"Folder nie istnieje:\n{root}")
            return

        # Czyszczenie starych danych
        for nb in (self.nbM, self.nbW, self.nbC, self.nbT):
            for child in nb.winfo_children():
                child.destroy()
        
        self._tabs.clear()
        self._all_weeks_data = [] # Lista na wszystkie wiersze ze wszystkich plików

        csvs = sorted([p for p in root.iterdir() if p.is_file() and p.suffix.lower()==".csv"], key=lambda x: x.name.lower())
        if not csvs:
            return

        for p in csvs:
            # POMIŃ PLIK HISTORII, aby nie próbował tworzyć z niego zakładki kalendarza
            if p.name == "Historia Turniejów.csv":
                continue
            self._add_tab_from_csv(p)
            
        self._build_weekly_view()
        self.earnings_tab.refresh_data()

# ---------- one tab ----------
    def _pick_parent_notebook(self, path: Path):
        """Wybiera notebook MEN/WOMEN/CHAMPIONSHIPS na podstawie nazwy pliku."""
        stem = path.stem                 # oryginalny case
        base = _strip_prefixes(stem).upper()   # najpierw wytnij prefiksy, potem UPPER
        name_up = stem.upper()

        # najpierw: pliki mistrzostw do CHAMPIONSHIPS
        if any(base.startswith(tag) for tag in ('WCH', 'JWC', 'NKIC', 'UNI', 'OG', 'SFWC', 'IST', 'YOG', 'COCH')):
            return self.nbC
        # potem: WOMEN po sufiksie -W
        if name_up.endswith('-W'):
            return self.nbW
        # reszta: MEN
        return self.nbM

    def _add_tab_from_csv(self, path: Path):
        # 1. Definiujemy tab_name na samym początku, aby uniknąć błędu UnboundLocalError
        tab_name = _strip_prefixes(path.stem)
        
        try:
            df = self._read_csv_any(path)
            df = _canonicalize_headers(df)
        except Exception as e:
            parent_nb = self._pick_parent_notebook(path)
            page = ttk.Frame(parent_nb)
            # Używamy zdefiniowanego wyżej tab_name
            err_tab = tab_name
            try:
                idx = (self._desired_tab_index(parent_nb, err_tab) if hasattr(self, '_desired_tab_index') else _desired_tab_index_fallback(parent_nb, getattr(self, 'nbM', None), getattr(self, 'nbW', None), getattr(self, 'nbC', None), err_tab))
                parent_nb.insert(idx, page, text=err_tab)
            except Exception:
                parent_nb.add(page, text=err_tab)
            ttk.Label(page, text=f"Błąd wczytywania: {e}", foreground="red").pack(padx=10, pady=10, anchor="w")
            return

        import numpy as np
        if "Dod. inf." in df.columns:
            df["Dod. inf."] = (
                df["Dod. inf."]
                .replace({np.nan: "", "nan": "", "NaN": ""})
                .fillna("")
            )

        # 2. Ustalanie kolejności kolumn
        desired = ["Week", "NAT", "Skocznia", "HS", "Rodzaj", "Dod. inf."]
        cols = _reorder_columns_case_insensitive(df, desired)
        df = df[cols]

        # 3. Zbieranie danych do widoku zbiorczego "TYGODNIE"
        temp_df = df.copy()
        temp_df['Seria'] = tab_name 
        self._all_weeks_data.append(temp_df)

        # 4. Tworzenie wizualnej zakładki w odpowiednim notebooku (MEN/WOMEN/CHAMPIONSHIPS)
        parent_nb = self._pick_parent_notebook(path)
        page = ttk.Frame(parent_nb)
        
        idx = (self._desired_tab_index(parent_nb, tab_name) if hasattr(self, '_desired_tab_index') else _desired_tab_index_fallback(parent_nb, getattr(self, 'nbM', None), getattr(self, 'nbW', None), getattr(self, 'nbC', None), tab_name))
        try:
            parent_nb.insert(idx, page, text=tab_name)
        except Exception:
            parent_nb.add(page, text=tab_name)

        # Górny pasek narzędzi (kolorowanie)
        bar = ttk.Frame(page); bar.pack(fill=tk.X, padx=8, pady=(8,4))
        ttk.Label(bar, text="Kolumna typu:").pack(side=tk.LEFT)
        type_col = tk.StringVar(value=self._guess_type_col(df))
        cb = ttk.Combobox(bar, textvariable=type_col, state="readonly", width=18, values=[""] + list(df.columns))
        cb.pack(side=tk.LEFT, padx=(6,10))
        ttk.Button(bar, text="Pokoloruj", command=lambda: self._apply_row_colors(tab_name)).pack(side=tk.LEFT)
        ttk.Button(bar, text="Reguły domyślne", command=lambda: self._load_default_rules(tab_name)).pack(side=tk.LEFT, padx=(6,0))
        ttk.Label(bar, text=" (IND/TEAM/MIX/KO/T4S/QUAL)", foreground="#666").pack(side=tk.LEFT, padx=(6,0))

        # --- DWIE TABELE (Podział na Week i resztę danych) ---
        wrap = ttk.Frame(page); wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        vsb = ttk.Scrollbar(wrap, orient="vertical")
        hsb = ttk.Scrollbar(wrap, orient="horizontal")

        tvL = ttk.Treeview(wrap, show="headings", yscrollcommand=vsb.set)
        tvL.configure(selectmode="none")
        tvR = ttk.Treeview(wrap, show="tree headings", yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        try:
            self._init_sync(tvL, tvR, vsb)
        except Exception:
            pass
            
        vsb.config(command=lambda *a: (tvL.yview(*a), tvR.yview(*a)))
        hsb.config(command=tvR.xview)

        tvL.grid(row=0, column=0, sticky="nsew")
        tvR.grid(row=0, column=1, sticky="nsew")
        vsb.grid(row=0, column=2, sticky="ns")
        hsb.grid(row=1, column=1, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(1, weight=1)

        # Kolumny lewej tabeli (Week)
        tvL["columns"] = ["Week"] if "Week" in df.columns else []
        if "Week" in df.columns:
            tvL.heading("Week", text="Week", command=lambda n=tab_name: self._sort_column(n, "Week", False))
            tvL.column("Week", width=max(60, self._calc_col_width(df["Week"])), minwidth=50, stretch=False, anchor=tk.CENTER)

        # Kolumny prawej tabeli
        right_cols = [c for c in df.columns if c not in ("Week", "NAT")]
        tvR["columns"] = right_cols
        tvR.column("#0", width=70, minwidth=60, stretch=False, anchor=tk.W)
        tvR.heading("#0", text="NAT")
        for c in right_cols:
            tvR.heading(c, text=c, command=lambda col=c, n=tab_name: self._sort_column(n, col, False))
            tvR.column(c, width=self._calc_col_width(df[c]), minwidth=60, stretch=False, anchor=(tk.E if str(getattr(df[c], "dtype", "")).startswith(("int","float")) else tk.W))

        # Wypełnianie tabel danymi
        for _, row in df.iterrows():
            week_val_item = self._fmt_cell(row.get("Week", ""))
            nat = str(row.get("NAT", "") or "").strip()
            img = self._get_flag_image(nat) if nat else None
            
            # 1. Przygotowanie wartości dla PRAWEJ tabeli (rzutowanie na string/int)
            # Upewniamy się, że nie ma tam obiektów typu None ani pustych krotek w dziwnym formacie
            values_right_safe = []
            for c in right_cols:
                val = self._fmt_cell(row.get(c, ""))
                values_right_safe.append(val if val is not None else "")
        
            # 2. Bezpieczne przygotowanie wartości dla tygodnia (LEWA tabela)
            week_val_safe = [week_val_item] if "Week" in df.columns else []

            # 3. Wstawienie danych z jawnym przekazaniem list
            # Używamy list zamiast krotek, co jest stabilniejsze w nowszych wersjach Tkintera
            new_id = tvL.insert("", "end", values=list(week_val_safe))
            tvR.insert("", "end", iid=new_id, text=f" {nat}", image=img, values=list(values_right_safe))

            
        # Zapamiętanie stanu zakładki
        self._tabs[tab_name] = TabState(frame=page, tree=tvR, vsb=vsb, hsb=hsb, df=df, type_col=type_col)
        self._load_default_rules(tab_name)

    # ---------- utils ----------
    @staticmethod
    def _read_csv_any(path: Path) -> pd.DataFrame:
        last = None
        # Najpierw próbujemy wymusić średnik, który jest w Twoich plikach 
        for enc in ("utf-8-sig", "utf-8", "cp1250"):
            try:
                # Wymuszamy separator ';' aby uniknąć zlewania się kolumn 
                df = pd.read_csv(path, sep=";", encoding=enc, engine="python")
                # Sprawdzamy czy faktycznie podzielił na kolumny
                if len(df.columns) > 1:
                    return df
            except Exception as e:
                last = e
        
        # Jeśli średnik zawiódł, próbujemy automatycznej detekcji jako ostateczność
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding="utf-8")
        except Exception:
            raise RuntimeError(f"Nie mogę wczytać CSV: {path}\n{last}")
        
    @staticmethod
    def _fmt_cell(v):
        try:
            import math
            if v is None: return ""
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return ""
        except Exception:
            pass
        if isinstance(v, float):
            return int(v) if abs(v - int(v)) < 1e-9 else round(v, 2)
        return v

    @staticmethod
    def _calc_col_width(series: pd.Series) -> int:
        try:
            maxlen = int(series.astype(str).map(len).max())
            return max(70, min(260, int(maxlen * 8)))
        except Exception:
            return 100

    @staticmethod
    def _guess_type_col(df: pd.DataFrame) -> str:
        for c in _POSSIBLE_TYPE_COLS:
            if c in df.columns: return c
        # fallback: spróbuj czegoś co wygląda na rodzaj
        for c in df.columns:
            if re.search(r"typ|rodz|zawod|tryb|event", c, flags=re.I):
                return c
        return ""


    def _build_weekly_view(self):
        if not self._all_weeks_data:
            return
        
        import pandas as pd
        full_df = pd.concat(self._all_weeks_data, ignore_index=True)

        # 1. Definicje grup do sortowania i separatorów
        championships = ['OG', 'WCH', 'SFWC', 'NKIC', 'IST', 'YOG', 'JWC', 'UNI', 'COCH']
        pro_men = ['GP-M', 'SCOC-M', 'WC-M', 'COC-M', 'FC-M']
        jun_men = ['JC-M', 'MC-M', 'PC-M', 'QC-M', 'TC-M', 'AC-M', 'BC-M', 'DC-M']
        pro_women = ['GP-W', 'SCOC-W', 'WC-W', 'COC-W', 'FC-W']
        jun_women = ['JC-W', 'MC-W', 'PC-W', 'QC-W', 'TC-W', 'AC-W', 'BC-W', 'DC-W']

        hierarchy = championships + pro_men + jun_men + pro_women + jun_women
        
        SERIES_COLORS = {
            'WC': '#ffd1d1', 'GP': '#ffffd1', 'SCOC': '#d1e9ff', 
            'COC': '#d1ffd1', 'FC': '#e9d1ff', 
            'WCH': '#ffd8b1', 'OG': '#ffd8b1', 'JWC': '#ffd8b1', 
            'SFWC': '#ffd8b1', 'NKIC': '#ffd8b1', 'IST': '#ffd8b1', 
            'YOG': '#ffd8b1', 'UNI': '#ffd8b1', 'COCH': '#ffd8b1',
            'JC': "#75ff8c", 'MC': '#e3f2fd', 'PC': '#f3e5f5', 
            'QC': '#fff3e0', 'TC': '#f1f8e9', 'AC': '#efebe9', 
            'BC': '#e8eaf6', 'DC': '#fffde7',
        }
        
        def sort_key(seria):
            try: return hierarchy.index(seria)
            except ValueError: return len(hierarchy)

        for w in range(1, 33):
            week_df = full_df[full_df['Week'] == w].copy()
            if week_df.empty: continue
            
            week_df['sort_rank'] = week_df['Seria'].apply(sort_key)
            week_df = week_df.sort_values('sort_rank').drop(columns=['sort_rank'])

            page = ttk.Frame(self.nbT)
            self.nbT.add(page, text=f"{w}")
            wrap = ttk.Frame(page); wrap.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            vsb = ttk.Scrollbar(wrap, orient="vertical")
            hsb = ttk.Scrollbar(wrap, orient="horizontal")

            tvL = ttk.Treeview(wrap, show="headings", columns=["Seria"], yscrollcommand=vsb.set, height=10)
            tvL.heading("Seria", text="Seria"); tvL.column("Seria", width=90, stretch=False)

            right_cols = ["Skocznia", "HS", "Rodzaj", "Dod. inf."]
            tvR = ttk.Treeview(wrap, show="tree headings", columns=right_cols, yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tvR.column("#0", width=80, stretch=False); tvR.heading("#0", text="NAT")

            # Konfiguracja kolorów i SEPARATORA
            for tag, color in SERIES_COLORS.items():
                tvL.tag_configure(tag, background=color)
                tvR.tag_configure(tag, background=color)
            
            # Kolor linii oddzielającej (ciemny szary)
            tvL.tag_configure("SEP", background="#808080")
            tvR.tag_configure("SEP", background="#808080")

            for c in right_cols:
                tvR.heading(c, text=c); tvR.column(c, width=150 if c != "HS" else 60, stretch=False)

            self._init_sync(tvL, tvR, vsb)
            vsb.config(command=lambda *a: (tvL.yview(*a), tvR.yview(*a)))
            hsb.config(command=tvR.xview)
            tvL.grid(row=0, column=0, sticky="nsew"); tvR.grid(row=0, column=1, sticky="nsew")
            vsb.grid(row=0, column=2, sticky="ns"); hsb.grid(row=1, column=1, sticky="ew")
            wrap.rowconfigure(0, weight=1); wrap.columnconfigure(1, weight=1)

            # 4. Wypełnianie z logiką separatorów
            last_group = None
            for idx, row in week_df.iterrows():
                seria_val = str(row.get("Seria", ""))
                
                # Określanie grupy aktualnego wiersza
                if seria_val in championships: current_group = "CHAMP"
                elif seria_val in pro_men: current_group = "PRO_M"
                elif seria_val in jun_men: current_group = "JUN_M"
                elif seria_val in pro_women: current_group = "PRO_W"
                elif seria_val in jun_women: current_group = "JUN_W"
                else: current_group = "OTHER"

                # Wstaw separator, jeśli grupa się zmieniła (ale nie przed pierwszym wierszem)
                if last_group is not None and last_group != current_group:
                    tvL.insert("", "end", values=["---"], tags=("SEP",))
                    tvR.insert("", "end", text="---", values=["", "", "", ""], tags=("SEP",))

                last_group = current_group

                # Standardowe wstawianie wiersza
                base_seria = seria_val.split('-')[0]
                tag = base_seria if base_seria in SERIES_COLORS else ""
                
                iid = tvL.insert("", "end", values=[seria_val], tags=(tag,))
                nat_val = str(row.get("NAT", "")).strip()
                img = self._get_flag_image(nat_val) if nat_val else None
                vals_right = [self._fmt_cell(row.get(c, "")) for c in right_cols]
                tvR.insert("", "end", iid=iid, text=f" {nat_val}", image=img, values=vals_right, tags=(tag,))

    # ---------- sort ----------
    def _sort_column(self, tab: str, col: str, reverse: bool):
        st = self._tabs.get(tab)
        if not st: return
        tvR, df = st.tree, st.df
        # posortuj DF i odśwież obie tablice
        try:
            sdf = df.sort_values(col, ascending=not reverse, kind="mergesort")
        except Exception:
            return
        # uzupełnij TV: lewy to pierwszy child (week) – szukamy po kontenerze
        wrap = tvR.master  # Frame z gridem
        tvL: Optional[ttk.Treeview] = None
        for w in wrap.winfo_children():
            if isinstance(w, ttk.Treeview) and w is not tvR and str(w.cget("show")) == "headings":
                tvL = w; break
        self._set_df_to_two_trees(tvL, tvR, sdf)
        st.df = sdf.reset_index(drop=True)
        tvR.heading(col, command=lambda: self._sort_column(tab, col, not reverse))

    def _set_df_to_two_trees(self, tvL: Optional[ttk.Treeview], tvR: ttk.Treeview, df: pd.DataFrame):
        # Napraw puste w 'Dod. inf.'
        try:
            import numpy as np
            if "Dod. inf." in df.columns:
                df["Dod. inf."] = df["Dod. inf."].replace({np.nan: "", "nan": "", "NaN": ""}).fillna("")
        except Exception:
            pass
        # LEFT
        if tvL is not None:
            if "Week" in df.columns:
                tvL["columns"] = ["Week"]
                tvL.heading("Week", text="Week")
                tvL.column("Week", width=max(60, self._calc_col_width(df["Week"])), minwidth=50, stretch=False, anchor=tk.CENTER)
            else:
                tvL["columns"] = []
            for iid in tvL.get_children(""):
                tvL.delete(iid)
        # RIGHT
        right_cols = [c for c in df.columns if c not in ("Week", "NAT")]
        tvR["columns"] = right_cols
        tvR.column("#0", width=70, minwidth=60, stretch=False, anchor=tk.W)
        tvR.heading("#0", text="NAT")
        for c in right_cols:
            tvR.heading(c, text=c)
            tvR.column(c, width=self._calc_col_width(df[c]), minwidth=60, stretch=False, anchor=(tk.E if str(getattr(df[c], "dtype", "")).startswith(("int","float")) else tk.W))
        for iid in tvR.get_children(""):
            tvR.delete(iid)
        for _, row in df.iterrows():
            week_val = self._fmt_cell(row.get("Week", ""))
            iid = None
            if tvL is not None:
                # Używamy krotki (week_val,)
                iid = tvL.insert("", "end", values=(week_val,) if "Week" in df.columns else ())
            
            nat = str(row.get("NAT", "") or "").strip()
            img = self._get_flag_image(nat) if nat else None
            
            # Konwersja na tuple dla prawej tabeli
            vals = tuple(self._fmt_cell(row.get(c, "")) for c in right_cols)
            tvR.insert("", "end", iid=iid, text=f" {nat}", image=img, values=vals)

    # ---------- coloring ----------
    def _load_default_rules(self, tab: str):
        st = self._tabs.get(tab)
        if not st: return
        # skonfiguruj tagi (raz)
        tv = st.tree
        for tname in ("IND","TEAM","MIX","KO","T4S","QUAL"):
            if not tv.tag_has(tname):
                tv.tag_configure(tname, background=self._color_for_tag(tname))
        # zastosuj
        self._apply_row_colors(tab)

    @staticmethod
    def _color_for_tag(tag: str) -> str:
        tag = tag.upper()
        return {
            "IND": "#d7ecff",
            "TEAM": "#e6f7d6",
            "MIX": "#f3e6ff",
            "KO": "#ffe6cc",
            "T4S": "#fff4b3",
            "QUAL": "#f0f0f0",
        }.get(tag, "#ffffff")

    # ---------- flags ----------
    def _get_flag_image(self, nat: str | None) -> tk.PhotoImage | None:
        if not nat:
            return None
        key = nat.upper()
        if key in self._flag_cache:
            return self._flag_cache[key]
        png = FLAG_DIR / f"{key}.png"
        gif = FLAG_DIR / f"{key}.gif"
        img = None
        try:
            if Image and png.exists():
                im = Image.open(png)
                img = ImageTk.PhotoImage(im)
            elif Image and gif.exists():
                im = Image.open(gif)
                img = ImageTk.PhotoImage(im)
            elif png.exists():
                img = tk.PhotoImage(file=str(png))
            elif gif.exists():
                img = tk.PhotoImage(file=str(gif))
        except Exception:
            img = None
        self._flag_cache[key] = img if img else None
        return self._flag_cache[key]

    def _apply_row_colors(self, tab: str):
        st = self._tabs.get(tab)
        if not st: return
        tv, df, type_col = st.tree, st.df, st.type_col.get()
        # zdejmij istniejące tagi
        for iid in tv.get_children(""):
            tv.item(iid, tags=())
        if not type_col or type_col not in df.columns:
            return
        # przygotuj regex → tag
        rules = [
            (re.compile(r"\bIND\b", re.I), "IND"),
            (re.compile(r"\bTEAM\b", re.I), "TEAM"),
            (re.compile(r"\bMIX\b", re.I), "MIX"),
            (re.compile(r"\bKO(?:64|50)?\b", re.I), "KO"),
            (re.compile(r"\bT4S\b", re.I), "T4S"),
            (re.compile(r"\bQUAL|\bQ\b", re.I), "QUAL"),
        ]
        # zbuduj mapę wartości kolumny per wiersz
        vals = [str(v or "") for v in df[type_col].tolist()]
        iids = tv.get_children("")
        for iid, s in zip(iids, vals):
            upper = s.upper()
            for rx, tag in rules:
                if rx.search(upper):
                    tv.item(iid, tags=(tag,))
                    break

# ===================== public API =====================

def build_gui(parent) -> CalendarsFrame:
    """Buduje i zwraca gotową zakładkę z kalendarzami.
    Użycie w combined: from calendars_gui_embedded import build_gui
    ... nb.add(build_gui(nb), text="Kalendarze")
    """
    return CalendarsFrame(parent, calendars_dir=DEFAULT_DIR)

# ===================== standalone =====================

class HistoryFrame(ttk.Frame):
    def __init__(self, parent, main_app, file_path="Historia Turniejów.csv"):
        super().__init__(parent)
        self.main_app = main_app
        self.file_path = Path(file_path)
        self.full_df = pd.DataFrame()
        self.filtered_df = pd.DataFrame()
        
        self._setup_ui()
        self.load_data()

    def _setup_ui(self):
        # Panel filtrów
        filter_bar = ttk.LabelFrame(self, text=" Filtrowanie ")
        filter_bar.pack(fill=tk.X, padx=10, pady=5)
        
        self.filters = {}
        cols = ["Turniej", "Sezon", "NAT", "Miejsce"]
        for i, col in enumerate(cols):
            frame = ttk.Frame(filter_bar)
            frame.pack(side=tk.LEFT, padx=10, pady=5)
            ttk.Label(frame, text=f"{col}:").pack(side=tk.LEFT)
            var = tk.StringVar()
            var.trace_add("write", lambda *args: self.apply_filters())
            entry = ttk.Entry(frame, textvariable=var, width=12)
            entry.pack(side=tk.LEFT, padx=5)
            self.filters[col] = var

        # Przycisk Pomoc
        ttk.Button(filter_bar, text="?", width=3, command=self.show_filter_help).pack(side=tk.LEFT, padx=10)

        # Przycisk Uaktualnij plik
        ttk.Button(filter_bar, text="🔄 Uaktualnij plik", command=self.update_history_file).pack(side=tk.LEFT, padx=10)

        # Tabela
        wrap = ttk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Definiujemy 3 kolumny tekstowe (+ kolumna #0 na Turniej i flagę)
        self.tv = ttk.Treeview(wrap, columns=("Sezon", "NAT_col", "Miejsce"), show="tree headings")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Konfiguracja nagłówków i sortowania
        self.tv.heading("#0", text="Turniej", command=lambda: self.sort_by("Turniej"))
        self.tv.heading("Sezon", text="Sezon", command=lambda: self.sort_by("Sezon"))
        self.tv.heading("NAT_col", text="NAT", command=lambda: self.sort_by("NAT"))
        self.tv.heading("Miejsce", text="Miejsce", command=lambda: self.sort_by("Miejsce"))
        
        self.tv.column("#0", width=180)
        self.tv.column("Sezon", width=70, anchor=tk.CENTER)
        self.tv.column("NAT_col", width=60, anchor=tk.CENTER)
        self.tv.column("Miejsce", width=250)
        
        self.tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

    def show_filter_help(self):
        help_text = (
            "INSTRUKCJA FILTROWANIA:\n\n"
            "1. POJEDYNCZO: 'S1' lub 'POL'\n"
            "2. LISTA (przecinek): 'S1, S5, S10' lub 'POL, GER'\n"
            "3. ZAKRES (tylko Sezon): 'S1-S20'\n\n"
            "Kliknij nagłówek tabeli, aby sortować kolumny."
        )
        messagebox.showinfo("Pomoc filtrowania", help_text)

    def update_history_file(self):
        """Wyskakujące okienko do wpisania sezonu, potem czyta pliki z ./<sezon>/Kalendarze i uzupełnia Historia Turniejów.csv."""
        dialog = tk.Toplevel(self)
        dialog.title("Uaktualnij Historia Turniejów")
        dialog.grab_set()
        dialog.resizable(False, False)

        ttk.Label(dialog, text="Podaj numer sezonu (np. S51):").pack(padx=20, pady=(16, 4))
        season_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=season_var, width=10)
        entry.pack(padx=20, pady=4)
        entry.focus_set()

        result_label = ttk.Label(dialog, text="", foreground="gray")
        result_label.pack(padx=20, pady=4)

        def do_update():
            season = season_var.get().strip().upper()
            if not season.startswith("S") or not season[1:].isdigit():
                result_label.config(text="❌ Nieprawidłowy format sezonu!", foreground="red")
                return

            app_dir = Path(__file__).resolve().parent
            cal_dir = app_dir / season / "Kalendarze"
            if not cal_dir.exists():
                result_label.config(text=f"❌ Nie znaleziono folderu: {cal_dir}", foreground="red")
                return

            # Wczytaj pliki CSV z folderu Kalendarze
            cal_files = list(cal_dir.glob("*.csv"))
            if not cal_files:
                result_label.config(text=f"❌ Brak plików CSV w: {cal_dir}", foreground="red")
                return

            # Parsuj pliki kalendarza — zbierz dane do dodania
            # Klucz: nazwa turnieju (np. NKIC, COCH-EU), wartość: (NAT, Miejsce)
            new_entries = {}

            # Mapowanie kontynent -> klucz COCH
            COCH_MAP = {
                "europe":        "COCH-EU",
                "asia":          "COCH-AS",
                "north america": "COCH-NA",
                "south america": "COCH-SA",
                "africa":        "COCH-AF",
                "oceania":       "COCH-OC",
            }

            for csv_file in cal_files:
                # Wyznacz nazwę turnieju z nazwy pliku
                stem = csv_file.stem
                for pref in (f"Kalendarze_{season}_", f"Kalendarz_{season}_", "Kalendarze_", "Kalendarz_"):
                    if stem.startswith(pref):
                        stem = stem[len(pref):]
                        break
                tourney_name = stem.upper()

                # Wczytaj plik
                content = None
                for enc in ['utf-8-sig', 'cp1250', 'iso-8859-2']:
                    try:
                        with open(csv_file, 'r', encoding=enc) as f:
                            lines = f.readlines()
                        content = lines
                        break
                    except Exception:
                        continue
                if not content or len(content) < 2:
                    continue

                if tourney_name == "COCH":
                    # COCH ma 6 skoczni — każda w innym wierszu (2, 6, 11, 16, 21, 26 = indeks 1,5,10,15,20,25)
                    coch_row_indices = {
                        "COCH-EU": 1,
                        "COCH-AS": 5,
                        "COCH-NA": 10,
                        "COCH-SA": 15,
                        "COCH-AF": 20,
                        "COCH-OC": 25,
                    }
                    for coch_key, row_idx in coch_row_indices.items():
                        if row_idx < len(content):
                            parts = content[row_idx].strip().split(';')
                            if len(parts) >= 3 and parts[1].strip():
                                new_entries[coch_key] = (parts[1].strip(), parts[2].strip())
                else:
                    # Zwykły turniej — dane z wiersza 2 (indeks 1)
                    parts = content[1].strip().split(';')
                    if len(parts) >= 3 and parts[1].strip():
                        new_entries[tourney_name] = (parts[1].strip(), parts[2].strip())

            if not new_entries:
                result_label.config(text="❌ Nie znaleziono danych do dodania.", foreground="red")
                return

            # Wczytaj Historia Turniejów.csv jako surowy tekst
            hist_path = self.file_path
            if not hist_path.exists():
                result_label.config(text=f"❌ Nie znaleziono pliku: {hist_path}", foreground="red")
                return

            raw_bytes = None
            used_enc = 'utf-8-sig'
            for enc in ['utf-8-sig', 'cp1250', 'iso-8859-2']:
                try:
                    with open(hist_path, 'r', encoding=enc) as f:
                        raw_lines = f.readlines()
                    used_enc = enc
                    break
                except Exception:
                    continue

            added = []
            skipped = []

            for tourney_key, (nat, miejsce) in new_entries.items():
                new_line = f"{tourney_key};{season};{nat};{miejsce}\r\n"

                # Znajdź ostatni wiersz danego turnieju
                last_idx = None
                for i, line in enumerate(raw_lines):
                    stripped = line.strip()
                    if stripped.startswith(tourney_key + ";") or stripped == tourney_key + ";;;":
                        last_idx = i

                if last_idx is None:
                    skipped.append(f"{tourney_key} (nie znaleziono sekcji)")
                    continue

                # Sprawdź czy sezon już istnieje
                already = any(
                    line.strip().startswith(tourney_key + ";" + season + ";")
                    for line in raw_lines
                )
                if already:
                    skipped.append(f"{tourney_key};{season} (już istnieje)")
                    continue

                # Wstaw nowy wiersz PO ostatnim wierszu tego turnieju
                raw_lines.insert(last_idx + 1, new_line)
                added.append(f"{tourney_key};{season};{nat};{miejsce}")

            # Zapisz z powrotem
            try:
                with open(hist_path, 'w', encoding=used_enc) as f:
                    f.writelines(raw_lines)
            except Exception as e:
                result_label.config(text=f"❌ Błąd zapisu: {e}", foreground="red")
                return

            # Odśwież dane w tabeli
            self.load_data()

            msg_parts = []
            if added:
                msg_parts.append(f"✅ Dodano ({len(added)}):\n" + "\n".join(f"  • {a}" for a in added))
            if skipped:
                msg_parts.append(f"⚠️ Pominięto ({len(skipped)}):\n" + "\n".join(f"  • {s}" for s in skipped))
            summary = "\n\n".join(msg_parts) if msg_parts else "Brak zmian."
            result_label.config(text=f"✅ Gotowe! Dodano: {len(added)}, pominięto: {len(skipped)}", foreground="green")
            messagebox.showinfo("Wynik aktualizacji", summary, parent=dialog)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(4, 16))
        ttk.Button(btn_frame, text="Aktualizuj", command=do_update).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="Zamknij", command=dialog.destroy).pack(side=tk.LEFT, padx=6)

        entry.bind("<Return>", lambda e: do_update())

    def load_data(self):
        if not self.file_path.exists(): return
        
        rows = []
        encodings = ['utf-8-sig', 'cp1250', 'iso-8859-2']
        content = None
        
        for enc in encodings:
            try:
                with open(self.file_path, 'r', encoding=enc) as f:
                    content = f.readlines()
                break
            except Exception: continue
        
        if not content: return

        for line in content:
            parts = line.strip().split(';')
            if len(parts) >= 4 and parts[1].strip() != "" and parts[2].strip() != "":
                tourney = parts[0].split()[-1] 
                rows.append([tourney, parts[1], parts[2], parts[3]])
        
        self.full_df = pd.DataFrame(rows, columns=["Turniej", "Sezon", "NAT", "Miejsce"])
        self.apply_filters()

    def apply_filters(self):
        df = self.full_df.copy()
        for col, var in self.filters.items():
            val = var.get().strip().upper()
            if not val: continue

            if col == "Sezon":
                selected = set()
                for part in [p.strip() for p in val.split(',')]:
                    if '-' in part:
                        try:
                            s, e = [int(''.join(filter(str.isdigit, x))) for x in part.split('-')]
                            for i in range(s, e + 1): selected.add(f"S{i}")
                        except Exception: selected.add(part)
                    else: selected.add(part)
                df = df[df[col].astype(str).str.upper().isin(selected)]
            elif col == "NAT":
                countries = [c.strip() for c in val.split(',')]
                df = df[df[col].astype(str).str.upper().isin(countries)]
            else:
                df = df[df[col].astype(str).str.upper().str.contains(val)]
        
        self.filtered_df = df
        self.refresh_table()

    def refresh_table(self):
        for item in self.tv.get_children(): self.tv.delete(item)
        for _, row in self.filtered_df.iterrows():
            nat = str(row["NAT"]).strip()
            img = self.main_app._get_flag_image(nat)
            self.tv.insert("", "end", text=f" {row['Turniej']}", image=img,
                           values=[row["Sezon"], nat, row["Miejsce"]])

    def sort_by(self, col):
        """Sortuje dane i odświeża tabelę."""
        if col == "Sezon":
            # Wykorzystujemy raw string r'(\d+)' aby uniknąć ostrzeżenia SyntaxWarning
            self.filtered_df['sort_key'] = self.filtered_df['Sezon'].str.extract(r'(\d+)').fillna(0).astype(int)
            self.filtered_df = self.filtered_df.sort_values('sort_key', ascending=True).drop('sort_key', axis=1)
        else:
            self.filtered_df = self.filtered_df.sort_values(col, ascending=True)
        self.refresh_table()

    def update_history_file(self):
        """Pyta o sezon, szuka plików w ./<sezon>/Kalendarze i aktualizuje Historia Turniejów.csv."""
        # --- Dialog z polem tekstowym ---
        dialog = tk.Toplevel(self)
        dialog.title("Aktualizuj plik historii")
        dialog.resizable(False, False)
        dialog.grab_set()

        ttk.Label(dialog, text="Podaj sezon (np. S51):").pack(padx=20, pady=(16, 4))
        season_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=season_var, width=12)
        entry.pack(padx=20, pady=(0, 12))
        entry.focus_set()

        result = {"ok": False}

        def confirm():
            result["ok"] = True
            dialog.destroy()

        def on_enter(event):
            confirm()

        entry.bind("<Return>", on_enter)
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(0, 14))
        ttk.Button(btn_frame, text="OK", command=confirm).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="Anuluj", command=dialog.destroy).pack(side=tk.LEFT, padx=6)
        dialog.wait_window()

        if not result["ok"]:
            return

        season = season_var.get().strip().upper()
        if not season:
            messagebox.showwarning("Brak sezonu", "Nie podano sezonu.")
            return

        # --- Szukaj plików kalendarzy ---
        app_dir = Path(__file__).resolve().parent
        cal_dir = app_dir / season / "Kalendarze"
        if not cal_dir.exists():
            messagebox.showerror("Błąd", f"Folder nie istnieje:\n{cal_dir}")
            return

        # Mapa: kod turnieju -> dane (NAT, Miejsce) do wpisania
        # Dla COCH parsujemy 6 kontynentów z jednego pliku
        COCH_CONTINENT_ROWS = {
            "Europe":        "COCH-EU",
            "Asia":          "COCH-AS",
            "North America": "COCH-NA",
            "South America": "COCH-SA",
            "Africa":        "COCH-AF",
            "Oceania":       "COCH-OC",
        }

        updates = {}  # turniej_code -> (NAT, Miejsce)

        cal_files = list(cal_dir.glob("*.csv"))
        if not cal_files:
            messagebox.showwarning("Brak plików", f"Brak plików CSV w:\n{cal_dir}")
            return

        encodings = ['utf-8-sig', 'cp1250', 'iso-8859-2', 'utf-8']

        for cal_file in cal_files:
            # Wyciągnij kod turnieju z nazwy pliku
            stem = cal_file.stem
            # Usuń prefiks np. "Kalendarz_S51_" lub "Kalendarze_S51_"
            for pref in (f"Kalendarze_{season}_", f"Kalendarz_{season}_",
                         f"Kalendarze_{season.lower()}_", f"Kalendarz_{season.lower()}_",
                         "Kalendarze_", "Kalendarz_"):
                if stem.startswith(pref):
                    stem = stem[len(pref):]
                    break
            tourney_code = stem.upper()

            # Wczytaj plik
            df = None
            for enc in encodings:
                try:
                    df = pd.read_csv(cal_file, sep=';', encoding=enc)
                    break
                except Exception:
                    continue
            if df is None or df.empty:
                continue

            # Kolumny NAT i Skocznia (miasto)
            nat_col = next((c for c in df.columns if c.upper() == "NAT"), None)
            city_col = next((c for c in df.columns if c.upper() in ("SKOCZNIA", "MIASTO", "PLACE", "CITY")), None)
            if city_col is None:
                # fallback: trzecia kolumna (indeks 2)
                if len(df.columns) >= 3:
                    city_col = df.columns[2]

            if nat_col is None or city_col is None:
                continue

            if tourney_code == "COCH":
                # Szukamy 6 kontynentów po kolumnie "Dod. Inf." lub ostatniej kolumnie
                dod_col = next((c for c in df.columns if "DOD" in c.upper() or "INF" in c.upper()), None)
                if dod_col is None and len(df.columns) >= 6:
                    dod_col = df.columns[-1]

                for continent_keyword, hist_code in COCH_CONTINENT_ROWS.items():
                    if dod_col:
                        mask = df[dod_col].astype(str).str.contains(continent_keyword, case=False, na=False)
                        subset = df[mask]
                    else:
                        subset = pd.DataFrame()

                    if not subset.empty:
                        row2 = subset.iloc[0]
                        nat_val = str(row2[nat_col]).strip()
                        city_val = str(row2[city_col]).strip()
                        updates[hist_code] = (nat_val, city_val)
            else:
                # Drugi wiersz danych (iloc[1] gdyby był nagłówek, ale po read_csv – iloc[0] to już dane wiersz 1)
                # Wymagany: wiersz o indeksie 1 (drugi wiersz danych, czyli trzecia linia pliku łącznie z nagłówkiem)
                if len(df) >= 2:
                    row2 = df.iloc[1]
                else:
                    row2 = df.iloc[0]
                nat_val = str(row2[nat_col]).strip()
                city_val = str(row2[city_col]).strip()
                updates[tourney_code] = (nat_val, city_val)

        if not updates:
            messagebox.showwarning("Brak danych", "Nie znaleziono żadnych danych do aktualizacji.")
            return

        # --- Wczytaj Historia Turniejów.csv jako surowe linie ---
        hist_path = app_dir / "Historia Turniejów.csv"
        if not hist_path.exists():
            messagebox.showerror("Błąd", f"Nie znaleziono pliku:\n{hist_path}")
            return

        enc_used = 'utf-8-sig'
        raw_lines = []
        for enc in encodings:
            try:
                with open(hist_path, 'r', encoding=enc) as f:
                    raw_lines = f.readlines()
                enc_used = enc
                break
            except Exception:
                continue

        if not raw_lines:
            messagebox.showerror("Błąd", "Nie udało się odczytać pliku historii.")
            return

        # --- Dla każdego turnieju znajdź ostatni wiersz z tym kodem i wstaw nowy po nim ---
        added = []
        skipped = []

        for tourney_code, (nat_val, city_val) in updates.items():
            new_line = f"{tourney_code};{season};{nat_val};{city_val}\r\n"

            # Sprawdź czy taki wpis już istnieje
            already = any(
                line.strip() == f"{tourney_code};{season};{nat_val};{city_val}"
                for line in raw_lines
            )
            if already:
                skipped.append(tourney_code)
                continue

            # Znajdź ostatni wiersz należący do tego turnieju
            last_idx = None
            for i, line in enumerate(raw_lines):
                parts = line.strip().split(';')
                if parts and parts[0].strip().upper() == tourney_code:
                    last_idx = i

            if last_idx is None:
                skipped.append(f"{tourney_code} (brak sekcji)")
                continue

            # Wstaw nowy wiersz po ostatnim
            raw_lines.insert(last_idx + 1, new_line)
            added.append(tourney_code)

        if not added:
            msg = "Nie dodano żadnych wpisów."
            if skipped:
                msg += f"\nPominięte (już istnieją lub brak sekcji): {', '.join(skipped)}"
            messagebox.showinfo("Brak zmian", msg)
            return

        # --- Zapisz plik ---
        try:
            with open(hist_path, 'w', encoding=enc_used, newline='') as f:
                f.writelines(raw_lines)
        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e))
            return

        # Odśwież dane w tabeli
        self.load_data()

        msg = f"✅ Dodano wpisy dla sezonu {season}:\n" + ", ".join(added)
        if skipped:
            msg += f"\n\nPominięte: {', '.join(skipped)}"
        messagebox.showinfo("Aktualizacja zakończona", msg)


class SeasonPlannerFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.hills_df = main_app.host_tab.hills_df.copy()
        self.season_var = tk.StringVar(value="S51")
        
        # --- KLUCZOWA POPRAWKA: Inicjalizacja słownika na samym starcie ---
        self.all_limits_data = {} 
        self.country_limits = {}
        self.championship_data = {}
        self.rankings_by_cycle = {}
        # -----------------------------------------------------------------
        
        self._setup_ui()
        self._setup_events()
        self.tree_limits.bind("<<TreeviewSelect>>", self._on_limit_select)

    def _setup_ui(self):
        # --- GÓRNY PANEL ---
        top_bar = ttk.LabelFrame(self, text=" Konfiguracja Nowego Sezonu ", padding=10)
        top_bar.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(top_bar, text="Docelowy Sezon:").pack(side=tk.LEFT)
        ttk.Entry(top_bar, textvariable=self.season_var, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="🏆 Ustaw Gospodarzy Mistrzostw", 
                   command=self.open_championships_dialog).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(top_bar, text="Gospodarz Mistrzostw (Miasto):").pack(side=tk.LEFT, padx=(15, 0))
        self.champ_host_var = tk.StringVar()
        ttk.Entry(top_bar, textvariable=self.champ_host_var, width=20).pack(side=tk.LEFT, padx=5)

        ttk.Button(top_bar, text="🚀 Generuj Folder i Bazę Gospodarzy", 
                   command=self.init_season_process).pack(side=tk.LEFT, padx=20)
        ttk.Button(top_bar, text="💾 Zapisz Ustalone Kalendarze", 
                   command=self.save_planned_calendars).pack(side=tk.LEFT, padx=5)
        
        # --- GŁÓWNY UKŁAD (Trzy Kolumny w PanedWindow) ---
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 1. LEWA KOLUMNA: Wybory Gospodarzy
        self.f_left = ttk.LabelFrame(paned, text=" Kompleksy i Użycia ")
        paned.add(self.f_left, weight=1)

        # Panel filtrów (u góry lewej kolumny)
        filter_frame = ttk.Frame(self.f_left)
        filter_frame.pack(fill=tk.X, padx=5, pady=5)

        self.filter_kraj_var = tk.StringVar()
        self.filter_kraj_var.trace_add("write", lambda *a: self.apply_host_filters())
        
        f_nat = ttk.Frame(filter_frame)
        f_nat.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        
        ttk.Label(f_nat, text="Szukaj NAT:").pack(side=tk.LEFT)
        self.ent_filter_kraj = ttk.Entry(f_nat, textvariable=self.filter_kraj_var, width=6)
        self.ent_filter_kraj.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(f_nat, text="X", width=2, 
                   command=lambda: self.filter_kraj_var.set("")).pack(side=tk.LEFT)
        
        self.filter_usage_var = tk.BooleanVar(value=True)
        self.filter_wc_var = tk.BooleanVar(value=False)
        self.filter_normal_var = tk.BooleanVar(value=False)
        self.filter_fly_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(filter_frame, text="Użycia <2", variable=self.filter_usage_var, 
                        command=self.apply_host_filters).grid(row=1, column=0, sticky=tk.W)
        ttk.Checkbutton(filter_frame, text="WC CLASS", variable=self.filter_wc_var, 
                        command=self.apply_host_filters).grid(row=2, column=0, sticky=tk.W)
        ttk.Checkbutton(filter_frame, text="Normalne", variable=self.filter_normal_var, 
                        command=self.apply_host_filters).grid(row=1, column=1, sticky=tk.W)
        ttk.Checkbutton(filter_frame, text="Mamuty", variable=self.filter_fly_var, 
                        command=self.apply_host_filters).grid(row=2, column=1, sticky=tk.W)

        # TO JEST KLUCZOWE: Definicja self.tree_hosts
        self.tree_hosts = ttk.Treeview(self.f_left, columns=("Miasto", "HS", "Bilety", "Uzycia"), show="headings tree")
        
        # Konfiguracja kolumny #0 (Kraj)
        self.tree_hosts.heading("#0", text="Kraj")
        self.tree_hosts.column("#0", width=80)

        # Konfiguracja pozostałych
        for col in ("Miasto", "HS", "Bilety", "Uzycia"):
            self.tree_hosts.heading(col, text=col)
            width = 110 if col == "Miasto" else 70
            self.tree_hosts.column(col, width=width, anchor=tk.CENTER if col in ["Bilety", "Uzycia"] else tk.W)
        self.tree_hosts.pack(fill=tk.BOTH, expand=True)

        # --- KLUCZOWA ZMIANA: PRZENOSIMY PRAWĄ KOLUMNĘ TUTAJ (PRZED ŚRODKOWĄ) ---
        # 3. PRAWA KOLUMNA: Licznik Praw (musi istnieć przed generowaniem TCS w środku)
        self.f_right = ttk.LabelFrame(paned, text=" Pozostałe Prawa (Limit) ")
        paned.add(self.f_right, weight=1)
        
        self.tree_limits = ttk.Treeview(self.f_right, columns=("Kraj", "Limit", "Uzyte"), show="headings")
        for col in ("Kraj", "Limit", "Uzyte"):
            self.tree_limits.heading(col, text=col)
            self.tree_limits.column(col, width=70, anchor=tk.CENTER)
        self.tree_limits.pack(fill=tk.BOTH, expand=True)

        # 2. ŚRODKOWA KOLUMNA: Szablony Cykli (NA KOŃCU)
        self.f_mid = ttk.LabelFrame(paned, text=" Szablony Tygodni ")
        paned.add(self.f_mid, weight=2)
        
        self.nb_gender = ttk.Notebook(self.f_mid)
        self.nb_gender.pack(fill=tk.BOTH, expand=True)
        
        self.planner_tabs = {"MEN": {}, "WOMEN": {}}
        self.gender_notebooks = {}

        for gender in ["MEN", "WOMEN"]:
            gender_nb = ttk.Notebook(self.nb_gender)
            self.nb_gender.add(gender_nb, text=gender)
            self.gender_notebooks[gender] = gender_nb
            
            cycles = ["GP", "SCOC", "WC", "COC", "FC", "JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]
            for cyc in cycles:
                frame = ttk.Frame(gender_nb)
                gender_nb.add(frame, text=cyc)
                tree = ttk.Treeview(frame, columns=("Week", "Gospodarz"), show="headings")
                tree.heading("Week", text="Tydzień")
                tree.heading("Gospodarz", text="Przypisane Miasto")
                tree.pack(fill=tk.BOTH, expand=True)
                
                self.planner_tabs[gender][cyc] = tree
                # Teraz wywołanie tej funkcji nie spowoduje błędu, bo tree_limits już istnieje
                self._fill_cycle_template(gender, cyc, tree)

    def _on_limit_select(self, event):
        """Filtruje listę skoczni po kliknięciu w kraj w tabeli limitów."""
        selected = self.tree_limits.selection()
        if not selected:
            return
            
        item_id = selected[0]
        # Pobieramy tekst z kolumny #0 (tam gdzie wstawiliśmy nazwę kraju obok flagi)
        nat_raw = self.tree_limits.item(item_id, "text").strip()
        
        # Jeśli w nazwie jest kropka (np. "1. JAM"), wyciągamy tylko JAM
        if "." in nat_raw:
            nat_raw = nat_raw.split(".")[-1].strip()
            
        # Ustawiamy filtr i odświeżamy widok skoczni
        self.filter_kraj_var.set(nat_raw)
        self.apply_host_filters()

    def _setup_events(self):
        """Podpina zdarzenia pod zmiany i kliknięcia."""
        # Odświeżanie limitów przy zmianie zakładki
        self.nb_gender.bind("<<NotebookTabChanged>>", self._on_cycle_tab_changed)
        for gender_nb in self.gender_notebooks.values():
            gender_nb.bind("<<NotebookTabChanged>>", self._on_cycle_tab_changed)
            
        # PRZYPISYWANIE: Dwuklik na skocznię (lewa strona) wywołuje akcję
        self.tree_hosts.bind("<Double-1>", self.assign_host_to_cycle)
        for gender in ["MEN", "WOMEN"]:
            for tree in self.planner_tabs[gender].values():
                tree.bind("<Delete>", self.remove_host_from_cycle)

    def _on_cycle_tab_changed(self, event):
        """Aktualizuje tabelę limitów przy każdej zmianie zakładki."""
        try:
            # Pobierz aktualnie wybraną płeć
            gender_idx = self.nb_gender.select()
            gender = self.nb_gender.tab(gender_idx, "text")
            
            # Pobierz aktualnie wybrany cykl wewnątrz tej płci
            current_gender_nb = self.gender_notebooks[gender]
            cycle_idx = current_gender_nb.select()
            cycle = current_gender_nb.tab(cycle_idx, "text")
            
            # Odśwież limity dla tej kombinacji
            self.refresh_limits_for_cycle(gender, cycle)
        except Exception as e:
            # Może wystąpić przy inicjalizacji, gdy zakładki nie są jeszcze gotowe
            pass

    def _fill_cycle_template(self, gender, cycle, tree):
        """Wstawia tygodnie do tabeli, usuwając T15 w sezonach z OG/COCH."""
        s_str = self.season_var.get()
        try:
            s_num = int(re.search(r'\d+', s_str).group())
        except:
            s_num = 0

        # Sprawdzamy, czy w tym sezonie obowiązuje blokada Tygodnia 15
        active_tours = self.get_active_tournaments(s_num)
        is_major_season = "OG" in active_tours or "COCH" in active_tours

        # 1. Definicja tygodni
        weeks = []
        if cycle == "GP": 
            weeks = [1, 2, 3, 5, 6]
        elif cycle == "SCOC": 
            weeks = [1, 2, 3]
        elif cycle == "WC": 
            weeks = [7, 9, 10, 11, 13, 14, 15, 17, 18, 19, 22, 23, 25, 26, 29, 30, 31, 32]
        elif cycle == "COC": 
            weeks = [7, 9, 10, 11, 13, 15, 17, 18, 19, 21, 22, 23, 25, 26, 27, 29, 30, 31]
        elif cycle == "FC": 
            weeks = [7, 10, 11, 13, 15, 17, 18, 19, 21, 22, 23, 25, 26, 27, 29]
        
        # --- FILTRACJA TYGODNIA 15 (OG/COCH) ---
        if is_major_season and cycle in ["WC", "COC", "FC"]:
            weeks = [w for w in weeks if w != 15]

        # --- FILTRACJA TYGODNI DLA KOBIET (Istniejąca logika) ---
        if gender == "WOMEN":
            if cycle == "COC":
                weeks = [w for w in weeks if w != 31]
            elif cycle == "FC":
                weeks = [w for w in weeks if w != 29]

        # 2. Specjalna obsługa zawodów juniorskich
        if cycle in ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]:
            for _ in range(5):
                tree.insert("", tk.END, values=(2, ""))
            return 

        # 3. Standardowe wstawianie tygodni do tabeli
        for w in weeks:
            if cycle == "WC" and gender == "MEN" and w == 14:
                for _ in range(4):
                    tree.insert("", tk.END, values=(w, ""))
            else:
                tree.insert("", tk.END, values=(w, ""))

        # 4. Automatyka TCS
        if cycle == "WC" and gender == "MEN":
            self._apply_automatic_tcs(tree)

    def calculate_nations_limits(self, season_num):
        """Wczytuje plik nations.csv i przelicza limity z uwzględnieniem OG/COCH."""
        prev_s = f"S{season_num - 1}"
        # Dopasowanie ścieżki do Twojej struktury folderów
        path = Path(f"./{prev_s}/Klasyfikacje {prev_s}/{prev_s}_WC-M__nations.csv")
        
        # Sprawdzenie czy sezon ma cięcia (OG lub COCH)
        active_tours = self.get_active_tournaments(season_num)
        has_cuts = "OG" in active_tours or "COCH" in active_tours
        
        if not path.exists():
            print(f"DEBUG: Nie znaleziono pliku pod ścieżką: {path.absolute()}")
            return {}

        try:
            # Zmieniamy sep na ',' ponieważ tak sugeruje Twój komunikat o błędzie
            df = pd.read_csv(path, sep=",", encoding="utf-8-sig")
            df.columns = df.columns.str.strip() 
            
            # Jeśli po przecinku nadal nie widzi NAT, spróbujmy automatycznej detekcji
            if 'NAT' not in df.columns:
                df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
                df.columns = df.columns.str.strip()

            if 'NAT' not in df.columns:
                print(f"Błąd krytyczny: Nadal brak kolumny NAT. Kolumny: {df.columns.tolist()}")
                return {}

            limits = {}
            for i, row in df.iterrows():
                rank = i + 1
                # Używamy .get(), aby bezpiecznie pobrać wartość
                nat_val = row.get('NAT')
                if pd.isna(nat_val): continue
                
                nat = str(nat_val).strip()
                lim = 0
                
                # --- TWOJA LOGIKA LIMITÓW ---
                if rank == 1: 
                    lim = 5
                elif 2 <= rank <= 5: 
                    lim = 2 if (has_cuts and rank == 5) else 4
                elif 6 <= rank <= 14: 
                    lim = 2
                
                # Gwarancja TCS dla GER/AUT
                if nat in ['GER', 'AUT'] and lim < 2: 
                    lim = 2
                
                limits[nat] = lim
            return limits

        except Exception as e:
            print(f"Błąd podczas wczytywania klasyfikacji: {e}")
            return {}
    
    def get_active_tournaments(self, s_num):
        active = ["JWC"]
        if (s_num - 31) % 4 == 0: active.append("OG")
        if s_num % 2 == 0: active.append("WCH")
        if (s_num - 33) % 2 == 0: active.append("SFWC")
        if s_num % 4 == 0: active.append("COCH")
        if (s_num - 35) % 2 == 0: active.append("IST")
        if s_num % 2 == 0: active.append("NKIC")
        if (s_num - 33) % 4 == 0: active.append("YOG")
        if (s_num - 34) % 4 == 0: active.append("UNI")
        return active

    def init_season_process(self):
        s_str = self.season_var.get()
        try:
            s_num = int(re.search(r'\d+', s_str).group())
        except:
            messagebox.showerror("Błąd", "Nieprawidłowy numer sezonu.")
            return
        
        # 1. Tworzenie folderów docelowych
        target_dir = Path(f"./{s_str}/Kalendarze")
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Generowanie bazy Wybory_Gospodarzy_SXX.csv
        self._generate_host_csv(s_str, s_num)
        
        # 3. Wyliczanie limitów narodowych (prawa organizacyjne)
        limits = self.calculate_nations_limits(s_num)
        self._refresh_limits_tree(limits)
        
        # 4. NOWOŚĆ: Generowanie fizycznych plików kalendarzy (.csv)
        self._create_all_calendar_files(s_str, s_num)
        
        messagebox.showinfo("Generator", f"Sezon {s_str} gotowy!\nUtworzono foldery, bazę gospodarzy oraz szablony kalendarzy.")

    def _generate_host_csv(self, s_str, s_num):
        complexes = self.hills_df.groupby(['Kraj', 'Miasto']).agg({
            'Miejsca dla kibiców': 'first',
            'Homologacja': 'first',
            'HS': lambda x: ", ".join(map(str, sorted(x.unique(), reverse=True)))
        }).reset_index()
        
        complexes['Uzycia'] = 0
        tcs_cities = ['Oberstdorf', 'Garmisch-Partenkirchen', 'Innsbruck', 'Bischofschofen']
        champ_data = getattr(self, 'championship_data', {})

        for idx, row in complexes.iterrows():
            count = 0
            city = row['Miasto']
            
            for tour, data in champ_data.items():
                if tour == "COCH":
                    if any(d['city'] == city for d in data.values()):
                        count = 1
                        break
                elif data['city'] == city:
                    count = 2
                    break
            
            if count == 0 and city in tcs_cities:
                count = 1
                
            complexes.at[idx, 'Uzycia'] = count

        for i in self.tree_hosts.get_children(): self.tree_hosts.delete(i)
        for _, r in complexes.iterrows():
            self.tree_hosts.insert("", tk.END, values=(r['Kraj'], r['Miasto'], r['HS'], r['Uzycia']))
        
        file_path = Path(f"./{s_str}/Wybory_Gospodarzy_{s_str}.csv")
        self.apply_host_filters()

    def _refresh_limits_tree(self, limits):
        for i in self.tree_limits.get_children(): self.tree_limits.delete(i)
        for nat, lim in limits.items():
            self.tree_limits.insert("", tk.END, values=(nat, lim, 0))

    def refresh_limits_for_cycle(self, gender, cycle):
        """Ładuje limity. Obsługuje przeplatanie GP/SCOC oraz elastyczne nazwy plików (np. S51_WC-M)."""
        import re
        from pathlib import Path
        
        s_str = self.season_var.get()
        s_match = re.search(r'\d+', s_str)
        s_num = int(s_match.group()) if s_match else 0
        
        # Kluczowe: Szukamy danych z POPRZEDNIEGO sezonu
        prev_s_num = s_num - 1
        prev_s = f"S{prev_s_num}"
        search_dir = Path(f"./{prev_s}/Klasyfikacje {prev_s}")
        
        key = (gender, cycle)
        if not hasattr(self, 'rankings_by_cycle'): self.rankings_by_cycle = {}
        if not hasattr(self, 'all_limits_data'): self.all_limits_data = {}

        # 1. CZYSZCZENIE I CACHE
        for i in self.tree_limits.get_children(): self.tree_limits.delete(i)
        if key in self.all_limits_data and self.all_limits_data[key]:
            self._update_limits_ui(self.all_limits_data[key])
            return

        ranking_list = []
        limits_raw = {}

        # Pomocnicza funkcja do szukania pliku z różnymi nazwami
        def find_nations_file(c, suf):
            # Próbuje: S51_WC-M__nations.csv, WC-M__nations.csv, S51_WC_M... itd.
            possible_names = [
                f"{prev_s}_{c}-{suf}__nations.csv",
                f"{prev_s}_{c}_{suf}__nations.csv",
                f"{c}-{suf}__nations.csv",
                f"{c}_{suf}__nations.csv"
            ]
            for name in possible_names:
                p = search_dir / name
                if p.exists():
                    return p
            return None

        # --- SEKCJA A: GP I SCOC (RANKING PRZEPLATANY M + W) ---
        if cycle in ["GP", "SCOC"]:
            m_list, w_list = [], []
            for suf, lst in [("M", m_list), ("W", w_list)]:
                p = find_nations_file(cycle, suf)
                if p:
                    try:
                        df = pd.read_csv(p, sep=None, engine="python", encoding="utf-8-sig")
                        df.columns = [str(c).strip().upper() for c in df.columns]
                        c_nat = next((c for c in ['NAT','KRAJ','NATION'] if c in df.columns), None)
                        if c_nat: lst.extend(df[c_nat].dropna().map(lambda x: str(x).strip()).tolist())
                    except: pass

            combined = []
            for m, w in zip(m_list, w_list): combined.extend([m, w])
            longer = m_list if len(m_list) > len(w_list) else w_list
            combined.extend(longer[min(len(m_list), len(w_list)):])

            seen = set()
            ranking_list = [x for x in combined if not (x in seen or seen.add(x))]
            
            top_n = 5 if cycle == "GP" else 3
            for i, nat in enumerate(ranking_list):
                if i < top_n: limits_raw[nat] = 2

        # --- SEKCJA B: JC, MC, PC, QC, TC, AC, BC, DC (OSOBNE) ---
        elif cycle in ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]:
            suffix = "M" if gender == "MEN" else "W"
            p = find_nations_file(cycle, suffix)
            if p:
                try:
                    df = pd.read_csv(p, sep=None, engine="python", encoding="utf-8-sig")
                    df.columns = [str(c).strip().upper() for c in df.columns]
                    c_nat = next((c for c in ['NAT','KRAJ','NATION'] if c in df.columns), None)
                    if c_nat:
                        ranking_list = df[c_nat].dropna().map(lambda x: str(x).strip()).unique().tolist()
                        for i, nat in enumerate(ranking_list):
                            if i < 5: limits_raw[nat] = 2
                except: pass

        # --- SEKCJA C: WC, COC, FC (STANDARDOWO) ---
        else:
            suffix = "M" if gender == "MEN" else "W"
            p = find_nations_file(cycle, suffix)
            if p:
                try:
                    df = pd.read_csv(p, sep=None, engine="python", encoding="utf-8-sig")
                    df.columns = [str(c).strip().upper() for c in df.columns]
                    c_nat = next((c for c in ['NAT','KRAJ','NATION'] if c in df.columns), None)
                    if c_nat:
                        ranking_list = df[c_nat].dropna().map(lambda x: str(x).strip()).unique().tolist()
                        active_tours = self.get_active_tournaments(s_num) if hasattr(self, 'get_active_tournaments') else []
                        has_cuts = "OG" in active_tours or "COCH" in active_tours
                        for i, nat in enumerate(ranking_list):
                            rank = i + 1
                            lim = 0
                            if cycle == "WC":
                                if gender == "MEN":
                                    if rank == 1: lim = 5
                                    elif rank <= 5: lim = 2 if (has_cuts and rank == 5) else 4
                                    elif rank <= 14: lim = 2
                                else: # WOMEN
                                    if rank <= 4: lim = 3 if (has_cuts and rank == 4) else 4
                                    elif rank == 5: lim = 2 if has_cuts else 3
                                    elif rank <= 14: lim = 2
                            elif cycle == "COC":
                                top = 3 if gender == "MEN" else 2
                                if rank <= top: lim = 2 if (has_cuts and rank == top) else 4
                                elif rank <= 15: lim = 2
                            elif cycle == "FC":
                                if rank <= (15 if gender == "MEN" else 14):
                                    lim = 0 if (has_cuts and rank == (15 if gender == "MEN" else 14)) else 2
                            if lim > 0: limits_raw[nat] = lim
                except: pass

        self.rankings_by_cycle[key] = ranking_list
        final_data = {n: [l, 0] for n, l in limits_raw.items()}
        if cycle == "WC" and gender == "MEN":
            for n in ['GER','AUT']: 
                if n in final_data: final_data[n][1] = 2
                
        self.all_limits_data[key] = final_data
        self._update_limits_ui(final_data)

    def _update_limits_ui(self, limits_dict):
        """
        Odświeża widok tabeli limitów. 
        Wstawia flagę i kod do kolumny #0, zachowując poprawne wyrównanie pozostałych danych.
        """
        # 1. Włączamy pokazywanie kolumny z obrazkami (tree) i ustawiamy nagłówek
        self.tree_limits["show"] = "tree headings"
        self.tree_limits.heading("#0", text=" Kraj")
        self.tree_limits.column("#0", width=80, anchor=tk.W) # Szerokość dla flagi i kodu

        # 2. Ukrywamy starą kolumnę tekstową "Kraj", żeby nie było dwóch takich samych
        # (Zmieniamy jej szerokość na 0 i wykluczamy z widoku, jeśli to możliwe)
        self.tree_limits.column("Kraj", width=0, stretch=tk.NO)

        # 3. Bezwzględne czyszczenie
        for i in self.tree_limits.get_children(): 
            self.tree_limits.delete(i)
        
        # 4. Pobranie kontekstu
        try:
            gender_idx = self.nb_gender.select()
            gender = self.nb_gender.tab(gender_idx, "text")
            tab_nb = self.gender_notebooks[gender]
            cycle = tab_nb.tab(tab_nb.select(), "text")
        except Exception:
            return

        # 5. Spisujemy kraje z dostępnymi skoczniami
        nations_with_hills = set()
        for item_id in self.tree_hosts.get_children():
            nat = self.tree_hosts.item(item_id)['text'].strip()
            nations_with_hills.add(nat)

        ranking = getattr(self, 'rankings_by_cycle', {}).get((gender, cycle), [])
        if not ranking:
            ranking = list(limits_dict.keys())

        # --- TWOJA KONFIGURACJA TAGÓW ---
        self.tree_limits.tag_configure("has_hill", foreground="#000000")
        self.tree_limits.tag_configure("RESERVE_WITH_HILL", background="#DBFFF3", foreground="#170a4d")
        self.tree_limits.tag_configure("BLOCKED", background="#efefef", foreground="#aaaaaa")
        self.tree_limits.tag_configure("RESERVE", background="#efefef", foreground="#aaaaaa")
        self.tree_limits.tag_configure("NORMAL", foreground="#000000")

        # 6. Wypełnianie
        for i, nat in enumerate(ranking):
            data = limits_dict.get(nat, [0, 0])
            limit_val, uzyte_val = data[0], data[1]
            
            is_available = nat in nations_with_hills
            has_slots = uzyte_val < limit_val

            # Logika tagu
            if limit_val > 0:
                if is_available and has_slots: tag = "has_hill"
                elif not is_available and has_slots: tag = "BLOCKED"
                else: tag = "NORMAL"
            else:
                tag = "RESERVE_WITH_HILL" if is_available else "RESERVE"

            # Pobranie obrazka flagi
            flag_img = self.main_app._get_flag_image(nat) if hasattr(self, 'main_app') else None
            
            # Formatuje nazwę (możesz dodać i+1 jeśli chcesz numerację)
            display_name = f"{nat}"

            # WSTAWIANIE:
            # text i image idą do kolumny #0 (nasz nowy Kraj)
            # values uzupełnia pozostałe kolumny (Kraj-ukryta, Limit, Uzyte)
            self.tree_limits.insert(
                "", 
                tk.END, 
                text=f" {display_name}", 
                image=flag_img,
                values=("", limit_val, uzyte_val), # Pusty string dla ukrytej kolumny "Kraj"
                tags=(tag,)
            )

    def _ask_for_hs(self, city, hs_string):
        """Jeśli miasto ma kilka HS, otwiera okno wyboru."""
        hss = [h.strip() for h in hs_string.split(",")]
        if len(hss) <= 1:
            return hss[0]
        
        selected_hs = tk.StringVar(value=hss[0])
        dialog = tk.Toplevel(self)
        dialog.title(f"Wybierz HS - {city}")
        dialog.geometry("300x200")
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"Miasto {city} ma kilka skoczni.\nKtórą wybierasz?", 
                  padding=10).pack()
        
        for h in hss:
            ttk.Radiobutton(dialog, text=f"HS {h}", variable=selected_hs, value=h).pack(anchor=tk.W, padx=50)
            
        res = None
        def confirm():
            nonlocal res
            res = selected_hs.get()
            dialog.destroy()
            
        ttk.Button(dialog, text="OK", command=confirm).pack(pady=10)
        self.wait_window(dialog)
        return res

    def assign_host_to_cycle(self, event):
        """Przypisuje skocznię i synchronizuje GP/SCOC między płciami."""
        sel_hill = self.tree_hosts.selection()
        if not sel_hill: return
        
        item_id = sel_hill[0]
        kraj_nowy = self.tree_hosts.item(item_id)['text'].strip()
        hill_values = self.tree_hosts.item(item_id)['values']
        miasto_nowe = str(hill_values[0])
        hs_raw = str(hill_values[1])

        # 1. Wybór HS
        wybrany_hs = self._ask_for_hs(miasto_nowe, hs_raw)
        if not wybrany_hs: return

        # 2. Ustalenie kontekstu (Płeć, Cykl, Tydzień)
        gender_idx = self.nb_gender.select()
        gender = self.nb_gender.tab(gender_idx, "text")
        tab_nb = self.gender_notebooks[gender]
        cycle = tab_nb.tab(tab_nb.select(), "text")
        tree_dest = self.planner_tabs[gender][cycle]
        
        sel_target = tree_dest.selection()
        if not sel_target: return

        target_item = sel_target[0]
        tydzien = str(tree_dest.item(target_item)['values'][0])
        gospodarz_stary_raw = str(tree_dest.item(target_item)['values'][1])

        # --- LOGIKA PUNKTACJI (Ustalenie punktów eventu) ---
        if cycle == "WC" and tydzien == "11":
            punkty_eventu = 3
        elif cycle == "WC" and gender == "MEN" and tydzien == "14":
            punkty_eventu = 1
        else:
            punkty_eventu = 2

        key = (gender, cycle)

        # 3. NADPISYWANIE: Zwrot punktów staremu gospodarzowi
        if gospodarz_stary_raw and "(" in gospodarz_stary_raw:
            miasto_stare = gospodarz_stary_raw.split(" (")[0].strip()
            kraj_stary = self._get_country_by_city(miasto_stare)
            if key in self.all_limits_data and kraj_stary in self.all_limits_data[key]:
                self.all_limits_data[key][kraj_stary][1] -= punkty_eventu
                # Synchronizacja zwrotu u drugiej płci (GP/SCOC)
                if cycle in ["GP", "SCOC"]:
                    other_g = "WOMEN" if gender == "MEN" else "MEN"
                    other_key = (other_g, cycle)
                    if other_key in self.all_limits_data and kraj_stary in self.all_limits_data[other_key]:
                        self.all_limits_data[other_key][kraj_stary][1] -= punkty_eventu

        # 4. PRZYPISANIE NOWEGO GOSPODARZA
        if self._check_and_update_limit(kraj_nowy, punkty_eventu):
            # Ustawienie tekstu w aktualnej tabeli
            tekst_gospodarza = f"{miasto_nowe} ({wybrany_hs})"
            tree_dest.set(target_item, "Gospodarz", tekst_gospodarza)
            
            # --- SYNCHRONIZACJA WIDOKU (GP / SCOC) ---
            if cycle in ["GP", "SCOC"]:
                other_gender = "WOMEN" if gender == "MEN" else "MEN"
                if other_gender in self.planner_tabs and cycle in self.planner_tabs[other_gender]:
                    other_tree = self.planner_tabs[other_gender][cycle]
                    # Wpisujemy to samo miasto w ten sam wiersz u drugiej płci
                    other_tree.set(target_item, "Gospodarz", tekst_gospodarza)
                    
                    # Synchronizacja limitu w pamięci dla drugiej płci
                    other_key = (other_gender, cycle)
                    if other_key in self.all_limits_data and kraj_nowy in self.all_limits_data[other_key]:
                        # Kopiujemy stan użycia z aktualnej płci
                        self.all_limits_data[other_key][kraj_nowy][1] = self.all_limits_data[key][kraj_nowy][1]

            self.apply_host_filters()
            self._auto_save_host_data()
        else:
            # Rollback punktów starego gospodarza w razie błędu
            if gospodarz_stary_raw and "(" in gospodarz_stary_raw:
                self.all_limits_data[key][kraj_stary][1] += punkty_eventu
            messagebox.showerror("Limit", f"Kraj {kraj_nowy} nie ma wystarczającego limitu!")

    def _apply_automatic_tcs(self, tree_dest):
        """Automatycznie wypełnia Tydzień 14 dla WC-M i odejmuje po 1 punkcie limitu."""
        tcs_data = [
            ("Oberstdorf", "137", "GER"),
            ("Garmisch-Partenkirchen", "142", "GER"),
            ("Innsbruck", "130", "AUT"),
            ("Bischofschofen", "142", "AUT")
        ]
        
        # Pobierz wszystkie wiersze dla tygodnia 14
        items_w14 = [i for i in tree_dest.get_children() if str(tree_dest.item(i)['values'][0]) == "14"]
        
        for i, (city, hs, nat) in enumerate(tcs_data):
            if i < len(items_w14):
                # Wpisujemy dane do tabeli
                tree_dest.set(items_w14[i], "Gospodarz", f"{city} ({hs})")
                # Odejmujemy 1 punkt z limitu kraju (TCS to specyficzny wyjątek)
                self._check_and_update_limit(nat, 1)

    def _check_and_update_limit(self, country, points=1):
        """
        Logika limitów z blokadami grupowymi:
        1. Juniorzy (JC, MC...) - jeden kraj na całą grupę.
        2. Lato (GP, SCOC) - jeden kraj na całą grupę.
        3. Shift Down - przesuwanie limitów w rankingu, jeśli dawca nie ma skoczni.
        """
        try:
            gender_idx = self.nb_gender.select()
            gender = self.nb_gender.tab(gender_idx, "text")
            cycle = self.gender_notebooks[gender].tab(self.gender_notebooks[gender].select(), "text")
            key = (gender, cycle)
        except Exception:
            return False

        if key not in self.all_limits_data:
            return False
        
        # 1. Pobieramy wszystkie 3 liczniki "na żywo" z planera
        live_usage, junior_usage, summer_usage = self._count_current_usage_from_planner()

        # --- BLOKADA GRUPOWA: JUNIORZY ---
        if cycle in ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]:
            if junior_usage.get(country, 0) >= 2:
                # Opcjonalnie: messagebox.showwarning("Limit", f"Kraj {country} ma już zawody juniorskie!")
                return False

        # --- BLOKADA GRUPOWA: LATO (GP + SCOC) ---
        if cycle in ["GP", "SCOC"]:
            if summer_usage.get(country, 0) >= 2:
                # Opcjonalnie: messagebox.showwarning("Limit", f"Kraj {country} ma już zawody w grupie GP/SCOC!")
                return False

        # 2. Sprawdzamy dostępność skoczni na liście (do logiki Shift)
        nations_with_available_hills = set()
        for item_id in self.tree_hosts.get_children():
            nat = self.tree_hosts.item(item_id)['text'].strip()
            nations_with_available_hills.add(nat)

        # 3. Jeśli kraj skoczni ma własny limit w tym cyklu, po prostu go używamy
        if country in self.all_limits_data[key]:
            limit, uzyte = self.all_limits_data[key][country]
            if uzyte + points <= limit:
                self.all_limits_data[key][country][1] += points
                return True

        # 4. LOGIKA SHIFT (PRZESUNIĘCIA)
        ranking = self.rankings_by_cycle.get(key, [])
        try:
            idx_current = ranking.index(country)
        except ValueError:
            idx_current = len(ranking)

        for i in range(idx_current):
            donor_nat = ranking[i]
            if donor_nat not in self.all_limits_data[key]: continue
            
            d_limit, d_uzyte = self.all_limits_data[key][donor_nat]
            
            # Jeśli dawca ma wolny limit, ale nie ma już wolnych skoczni na liście
            if (d_uzyte < d_limit) and (donor_nat not in nations_with_available_hills):
                # Następuje SHIFT:
                donor_package = d_limit
                recipient_package = self.all_limits_data[key].get(country, [0, 0])[0]
                
                # Dawca oddaje wszystko (przesunięcie rankingu)
                self.all_limits_data[key][donor_nat][0] = 0 
                self.all_limits_data[key][donor_nat][1] = 0
                
                # Biorca otrzymuje pakiet dawcy
                if country not in self.all_limits_data[key]:
                    self.all_limits_data[key][country] = [0, 0]
                
                self.all_limits_data[key][country][0] = donor_package
                self.all_limits_data[key][country][1] += points 
                
                # Przesunięcie "nadmiaru" do pierwszej wolnej rezerwy
                if recipient_package > 0:
                    for res_nat in ranking[idx_current+1:]:
                        res_data = self.all_limits_data[key].get(res_nat, [0, 0])
                        if res_data[0] == 0: 
                            if res_nat not in self.all_limits_data[key]:
                                self.all_limits_data[key][res_nat] = [0, 0]
                            self.all_limits_data[key][res_nat][0] = recipient_package
                            print(f"SHIFT: {country} przejął {donor_package} pkt. Stary limit spadł do {res_nat}")
                            break
                
                return True

        return False
    
    def open_championships_dialog(self):
        """Otwiera okno wpisywania gospodarzy mistrzostw dla danego sezonu."""
        s_str = self.season_var.get()
        try:
            s_num = int(re.search(r'\d+', s_str).group())
        except:
            messagebox.showerror("Błąd", "Wpisz poprawny numer sezonu (np. S51)")
            return

        active_tours = self.get_active_tournaments(s_num)
        dialog = tk.Toplevel(self)
        dialog.title(f"Gospodarze Mistrzostw - {s_str}")
        dialog.geometry("600x650")
        dialog.transient(self)
        dialog.grab_set()

        # Scrollbar dla długiej listy (szczególnie przy COCH)
        canvas = tk.Canvas(dialog)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        container = ttk.Frame(canvas, padding=20)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.create_window((0, 0), window=container, anchor="nw")

        ttk.Label(container, text=f"Konfiguracja turniejów dla sezonu {s_str}", 
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=5, pady=(0, 20))

        self.temp_entries = {}
        row_idx = 1
        double_hs_tours = ["OG", "WCH", "IST"]
        continents = ["Europe", "Asia", "North America", "South America", "Africa", "Oceania"]

        for tour in active_tours:
            if tour == "COCH":
                ttk.Label(container, text="COCH (Kontynenty):", font=("Segoe UI", 9, "bold")).grid(
                    row=row_idx, column=0, columnspan=5, sticky=tk.W, pady=(10, 5))
                row_idx += 1
                self.temp_entries["COCH"] = {}
                for cont in continents:
                    ttk.Label(container, text=f"  {cont}:").grid(row=row_idx, column=0, sticky=tk.W)
                    e_nat = ttk.Entry(container, width=6)
                    e_nat.grid(row=row_idx, column=1, padx=2)
                    e_city = ttk.Entry(container, width=18)
                    e_city.grid(row=row_idx, column=2, padx=2)
                    e_hs = ttk.Entry(container, width=6)
                    e_hs.grid(row=row_idx, column=3, padx=2)
                    self.temp_entries["COCH"][cont] = {'nat': e_nat, 'city': e_city, 'hs1': e_hs}
                    
                    if hasattr(self, 'championship_data') and "COCH" in self.championship_data:
                        d = self.championship_data["COCH"].get(cont, {})
                        if d:
                            e_nat.insert(0, d.get('nat', ''))
                            e_city.insert(0, d.get('city', ''))
                            e_hs.insert(0, d.get('hs1', ''))
                    row_idx += 1
            else:
                ttk.Label(container, text=f"{tour}:").grid(row=row_idx, column=0, sticky=tk.W, pady=5)
                e_nat = ttk.Entry(container, width=6)
                e_nat.grid(row=row_idx, column=1, padx=2)
                e_city = ttk.Entry(container, width=18)
                e_city.grid(row=row_idx, column=2, padx=2)
                e_hs1 = ttk.Entry(container, width=6)
                e_hs1.grid(row=row_idx, column=3, padx=2)
                e_hs2 = None
                if tour in double_hs_tours:
                    e_hs2 = ttk.Entry(container, width=6)
                    e_hs2.grid(row=row_idx, column=4, padx=2)
                else:
                    ttk.Label(container, text="-").grid(row=row_idx, column=4)

                self.temp_entries[tour] = {'nat': e_nat, 'city': e_city, 'hs1': e_hs1, 'hs2': e_hs2}
                if hasattr(self, 'championship_data') and tour in self.championship_data:
                    d = self.championship_data[tour]
                    e_nat.insert(0, d['nat']); e_city.insert(0, d['city']); e_hs1.insert(0, d['hs1'])
                    if e_hs2 and d['hs2']: e_hs2.insert(0, d['hs2'])
                row_idx += 1

        def save_and_close():
            self.championship_data = {}
            for tour, entries in self.temp_entries.items():
                if tour == "COCH":
                    self.championship_data["COCH"] = {cont: {
                        'nat': e['nat'].get().upper(), 'city': e['city'].get(), 'hs1': e['hs1'].get()
                    } for cont, e in entries.items()}
                else:
                    self.championship_data[tour] = {
                        'nat': entries['nat'].get().upper(), 'city': entries['city'].get(),
                        'hs1': entries['hs1'].get(), 'hs2': entries['hs2'].get() if entries['hs2'] else ""
                    }
            dialog.destroy()
            self.apply_host_filters()
            messagebox.showinfo("Zapisano", "Dane gospodarzy mistrzostw zostały zapamiętane.")

        ttk.Button(container, text="Zapisz Dane", command=save_and_close).grid(
            row=row_idx, column=0, columnspan=5, pady=20)
        container.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

    def _create_all_calendar_files(self, s_str, s_num):
        base_path = Path(f"./{s_str}/Kalendarze")
        active_tours = self.get_active_tournaments(s_num)
        header = "WEEK;NAT;Skocznia;HS;Rodzaj;Dod. Inf.\n"
        champ_data = getattr(self, 'championship_data', {})
        
        for tour in active_tours:
            path = base_path / f"Kalendarz_{s_str}_{tour}.csv"
            with open(path, "w", encoding="utf-8") as f:
                f.write(header)
                
                # --- POPRAWKA: Prawidłowe pobieranie danych dla COCH i reszty ---
                if tour == "COCH":
                    d = champ_data.get("COCH", {})
                else:
                    d = champ_data.get(tour, {'nat': 'KRAJ', 'city': 'MIASTO', 'hs1': 'HS', 'hs2': 'HS'})
                
                # --- ZAWSZE używamy szablonu, który ma wbudowaną logikę fmt_hs i 6 kolumn ---
                f.write(self._get_championship_template(tour, d))

        # --- Reszta funkcji (Cykle GP, WC, itp.) pozostaje bez zmian ---
        cycles = ["GP", "SCOC", "WC", "COC", "FC", "JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]
        active_tours = self.get_active_tournaments(s_num)
        skip_w15 = "OG" in active_tours or "COCH" in active_tours

        for gender in ["M", "W"]:
            gen_full = "MEN" if gender == "M" else "WOMEN"
            for cyc in cycles:
                path = base_path / f"Kalendarz_{s_str}_{cyc}-{gender}.csv"
                weeks = self._get_cycle_weeks(gen_full, cyc)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(header)
                    for w in weeks:
                        if skip_w15 and w == 15 and cyc in ["WC", "COC", "FC"]: continue
                        f.write(f"{w};;;;;\n{w};;;;;\n")
                        
    def _get_cycle_weeks(self, gender, cycle):
        """Pomocnicza funkcja zwracająca listę tygodni (powielona logika z UI)."""
        weeks = []
        if cycle == "GP": weeks = [1, 2, 3, 5, 6]
        elif cycle == "SCOC": weeks = [1, 2, 3]
        elif cycle == "WC": weeks = [7, 9, 10, 11, 13, 14, 15, 17, 18, 19, 22, 23, 25, 26, 29, 30, 31, 32]
        elif cycle == "COC": weeks = [7, 9, 10, 11, 13, 15, 17, 18, 19, 21, 22, 23, 25, 26, 27, 29, 30, 31]
        elif cycle == "FC": weeks = [7, 10, 11, 13, 15, 17, 18, 19, 21, 22, 23, 25, 26, 27, 29]
        elif cycle in ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]: weeks = [2, 2, 2, 2]
        return weeks

    def _get_championship_template(self, tour, d):
        """Zwraca treść pliku CSV dla konkretnego turnieju z przedrostkiem HS i kontynentem w Dod. Inf."""
        w = "15" 
        if tour in ["WCH", "SFWC"]: w = "27"
        if tour in ["IST", "NKIC"]: w = "21"
        if tour == "JWC": w = "9"

        # Pomocnicza funkcja do formatowania HS
        def fmt_hs(val):
            if not val: return ""
            s_val = str(val).strip()
            return f"HS{s_val}" if not s_val.upper().startswith("HS") else s_val

        if tour == "COCH":
            res = ""
            # d to słownik kontynentów (d['Europe'], d['Asia'] itd.)
            for cont, data in d.items():
                c_nat = data.get('nat', '')
                c_city = data.get('city', '')
                c_hs = fmt_hs(data.get('hs1', ''))
                
                if not c_city: continue 

                # Każdy kontynent dostaje 5 konkursów
                # Format: WEEK;NAT;Skocznia;HS;Rodzaj;Dod. Inf.
                res += f"15;{c_nat};{c_city};{c_hs};IND;W - {cont}\n"
                res += f"15;{c_nat};{c_city};{c_hs};IND;M - {cont}\n"
                res += f"15;{c_nat};{c_city};{c_hs};TEAM;W - {cont}\n"
                res += f"15;{c_nat};{c_city};{c_hs};TEAM;M - {cont}\n"
                res += f"15;{c_nat};{c_city};{c_hs};TEAM;MIX - {cont}\n"
            return res

        # Pozostałe turnieje (OG, WCH itd.)
        h1 = fmt_hs(d.get('hs1', ''))
        h2 = fmt_hs(d.get('hs2', ''))

        if tour in ["OG", "WCH"]:
            return (f"{w};{d['nat']};{d['city']};{h1};IND;W\n"
                    f"{w};{d['nat']};{d['city']};{h1};IND;M\n"
                    f"{w};{d['nat']};{d['city']};{h1};TEAM;W\n"
                    f"{w};{d['nat']};{d['city']};{h1};TEAM;M\n"
                    f"{w};{d['nat']};{d['city']};{h1};TEAM;MIX\n"
                    f"{w};{d['nat']};{d['city']};{h2};IND;W\n"
                    f"{w};{d['nat']};{d['city']};{h2};IND;M\n"
                    f"{w};{d['nat']};{d['city']};{h2};TEAM;W\n"
                    f"{w};{d['nat']};{d['city']};{h2};TEAM;M\n"
                    f"{w};{d['nat']};{d['city']};{h2};TEAM;MIX\n")
        
        elif tour == "SFWC":
            return (f"27;{d['nat']};{d['city']};{h1};IND;W - 1st day\n"
                    f"27;{d['nat']};{d['city']};{h1};IND;W - 2nd day\n"
                    f"27;{d['nat']};{d['city']};{h1};IND;M - 1st day\n"
                    f"27;{d['nat']};{d['city']};{h1};IND;M - 2nd day\n"
                    f"27;{d['nat']};{d['city']};{h1};TEAM;W\n"
                    f"27;{d['nat']};{d['city']};{h1};TEAM;M\n"
                    f"27;{d['nat']};{d['city']};{h1};TEAM;MIX\n")
        
        elif tour in ["NKIC", "IST"]:
            res = ""
            # Dla NKIC/IST generujemy listę rund KO64/32 itd.
            for gender in ["MEN", "WOMEN"]:
                for stage in ["Qualifications", "Round 1 / 64", "Round 1 / 32", "Round 1 / 16", "Quarterfinal", "Semifinal", "Final"]:
                    res += f"21;{d['nat']};{d['city']};{h1};{stage};{gender}\n"
            if tour == "IST" and h2:
                for gender in ["MEN", "WOMEN"]:
                    for stage in ["Qualifications", "Round 1 / 64", "Round 1 / 32", "Round 1 / 16", "Quarterfinal", "Semifinal", "Final"]:
                        res += f"21;{d['nat']};{d['city']};{h2};{stage};{gender}\n"
            return res

        elif tour in ["JWC", "YOG", "UNI"]:
            # Dla JWC tydzień to 9, dla reszty 15 zgodnie z logiką 'w' powyżej
            return (f"{w};{d['nat']};{d['city']};{h1};IND;W\n"
                    f"{w};{d['nat']};{d['city']};{h1};IND;M\n"
                    f"{w};{d['nat']};{d['city']};{h1};TEAM;W\n"
                    f"{w};{d['nat']};{d['city']};{h1};TEAM;M\n"
                    f"{w};{d['nat']};{d['city']};{h1};TEAM;MIX\n")
        
        return ""
    
    def save_planned_calendars(self):
        """Pobiera dane z zakładek i nadpisuje pliki CSV z zaawansowaną logiką rodzajów i Dod. Inf."""
        s_str = self.season_var.get()
        base_path = Path(f"./{s_str}/Kalendarze")
        
        if not base_path.exists():
            messagebox.showerror("Błąd", "Folder kalendarzy nie istnieje.")
            return

        try:
            for gender in ["MEN", "WOMEN"]:
                suffix = "M" if gender == "MEN" else "W"
                for cycle, tree in self.planner_tabs[gender].items():
                    items = tree.get_children()
                    if not items: continue

                    file_name = f"Kalendarz_{s_str}_{cycle}-{suffix}.csv"
                    path = base_path / file_name
                    rows = []

                    # Licznik konkursów w Norwegii dla RAW AIR (WC-M)
                    nor_count = 0
                    if cycle == "WC" and suffix == "M":
                        for iid in items:
                            g_val = str(tree.item(iid)['values'][1])
                            if "(" in g_val:
                                city = g_val.split(" (")[0].strip()
                                if self._get_country_by_city(city) == "NOR":
                                    nor_count += 2 # Standardowo 2 konkursy na tydzień

                    for item_id in items:
                        vals = tree.item(item_id)['values']
                        week = int(vals[0])
                        gospodarz_raw = str(vals[1])
                        
                        nat, city, hs = "", "", ""
                        if "(" in gospodarz_raw:
                            city = gospodarz_raw.split(" (")[0].strip()
                            raw_hs = gospodarz_raw.split(" (")[1].replace(")", "").strip()
                            nat = self._get_country_by_city(city) or ""

                            if raw_hs and not raw_hs.upper().startswith("HS"):
                                hs = f"HS{raw_hs}"
                            else:
                                hs = raw_hs

                        # --- LOGIKA TYGODNIA 14 (TCS / 4HT) ---
                        if cycle == "WC" and suffix == "M" and week == 14:
                            # Tylko 1 konkurs na wiersz w tabeli dla TCS
                            rows.append([week, nat, city, hs, "KO50", "4HT"])
                            continue # Przejdź do następnego wiersza (nie dubluj)

                        # --- LOGIKA RODZAJU (IND / TEAM / MIXED) ---
                        r1, r2 = "IND", "IND"
                        if week in [22, 23, 25, 26] and cycle == "WC":
                            r1, r2 = "TEAM", "IND"
                        elif cycle == "GP" and week == 5:
                            r1, r2 = "MIXED", "IND"
                        elif cycle == "GP" and week == 6:
                            r1, r2 = "TEAM", "IND"

                        # --- LOGIKA DOD. INF ---
                        inf1, inf2 = "", ""
                        if cycle == "WC" and suffix == "M":
                            if week in [18, 19]: inf1 = inf2 = "NT"
                            if week in [31, 32]: inf1 = inf2 = "FT"
                            if city == "Planica": inf1 = inf2 = "P7"
                            if city == "Willingen": inf1 = inf2 = "W5"
                            if nat == "NOR" and nor_count >= 4: inf1 = inf2 = "RAW AIR"
                        
                        elif cycle == "WC" and suffix == "W":
                            if week in [29, 30]: inf1 = inf2 = "RAW AIR"
                            if week in [31, 32]: inf1 = inf2 = "BLUE BIRD"

                        # --- DODAWANIE WIERSZY ---
                        # Tydzień 11 ma 3 konkursy TYLKO w cyklu WC
                        if cycle == "WC" and week == 11:
                            num_events = 3
                        else:
                            num_events = 2 # Standardowo 2 konkursy na tydzień

                        for _ in range(num_events):
                            # Jeśli to tydzień z TEAM/IND, przypisz odpowiednio
                            current_r = r1 if _ == 0 and r1 != "IND" else r2
                            rows.append([week, nat, city, hs, current_r, inf1])

                    df_to_save = pd.DataFrame(rows, columns=["WEEK", "NAT", "Skocznia", "HS", "Rodzaj", "Dod. Inf."])
                    df_to_save.to_csv(path, sep=";", index=False, encoding="utf-8-sig")

            messagebox.showinfo("Sukces", "Kalendarze zostały zapisane z uwzględnieniem turniejów i rodzajów zawodów.")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Błąd: {e}")

    def _get_country_by_city(self, city):
        """Pobiera kod kraju dla danego miasta z bazy skoczni hills_df."""
        # Szukamy w DataFrame hills_df wiersza, gdzie Miasto zgadza się z city
        res = self.hills_df[self.hills_df['Miasto'] == city]
        if not res.empty:
            return res.iloc[0]['Kraj']
        return "" # Zwraca pusty ciąg, jeśli nie znaleziono miasta

    def apply_host_filters(self):
        """Filtruje listę skoczni, dbając o to, by liczniki nie zerowały się między cyklami."""
        try:
            gender_idx = self.nb_gender.select()
            gender = self.nb_gender.tab(gender_idx, "text")
            cycle = self.gender_notebooks[gender].tab(self.gender_notebooks[gender].select(), "text")
        except: return

        # 1. Pobieramy wszystkie liczniki
        live_usage, junior_usage, summer_usage = self._count_current_usage_from_planner()
        junior_group = ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]
        summer_group = ["GP", "SCOC"]

        self.tree_hosts.delete(*self.tree_hosts.get_children())
        if not hasattr(self, 'hills_df'): return

        df = self.hills_df.groupby(['Kraj', 'Miasto']).agg({
            'HS': lambda x: sorted(x.unique(), reverse=True),
            'Homologacja': lambda x: [str(i).strip().upper() for i in x.unique()],
            'Miejsca dla kibiców': 'first'
        }).reset_index()

        for _, row in df.iterrows():
            kraj, miasto = str(row['Kraj']), str(row['Miasto'])
            hss = row['HS']

            f_kraj = self.filter_kraj_var.get().strip().upper()
            if f_kraj and f_kraj != kraj.upper():
                continue
            
            # --- KLUCZOWA ZMIANA: Globalne użycie miasta ---
            # Zawsze pokazujemy faktyczną liczbę użyć skoczni (z WC, COC, GP itd.)
            uzycia_skoczni = live_usage.get(miasto, 0)
            
            # --- DODATKOWE BLOKADY KRAJOWE (GRUPY) ---
            kraj_zablokowany = False
            if cycle in junior_group:
                if junior_usage.get(kraj, 0) >= 2:
                    kraj_zablokowany = True
            elif cycle in summer_group:
                if summer_usage.get(kraj, 0) >= 2:
                    kraj_zablokowany = True

            # --- FILTR UŻYCIA (Checkbox "Ukryj użyte") ---
            # Ukrywamy jeśli: 
            # 1. Skocznia osiągnęła limit sezonowy (2/2)
            # 2. LUB kraj jest zablokowany przez zasadę grupową (Juniorzy/Lato)
            if self.filter_usage_var.get():
                if uzycia_skoczni >= 2 or kraj_zablokowany:
                    continue

            # --- FILTRY WC CLASS / WIELKOŚĆ (Poprzednie poprawki) ---
            if self.filter_wc_var.get():
                if not any('WORLD CUP' in h or 'OLYMPIC' in h for h in row['Homologacja']):
                    continue
            
            try:
                hs_numbers = [float(str(h).replace(',', '.')) for h in hss]
                if self.filter_normal_var.get() and not any(85 <= h < 110 for h in hs_numbers):
                    continue
                if self.filter_fly_var.get() and not any(h > 185 for h in hs_numbers):
                    continue
            except: pass

            # --- WSTAWIANIE DO TABELI ---
            raw_t = str(row['Miejsca dla kibiców']).replace(" ", "")
            try: b_str = f"{int(float(raw_t)):,}".replace(",", " ")
            except: b_str = "0"

            hs_str = ", ".join(map(str, hss))
            
            # W kolumnie "Użycia" zawsze pokazujemy uzycia_skoczni, 
            # żeby użytkownik wiedział, dlaczego nie może wybrać danej skoczni
            self.tree_hosts.insert("", "end", text=f" {kraj}", 
                                   image=self.main_app._get_flag_image(kraj),
                                   values=(miasto, hs_str, b_str, uzycia_skoczni))

        # Odświeżenie limitów po prawej
        try:
            key = (gender, cycle)
            if hasattr(self, 'all_limits_data') and key in self.all_limits_data:
                self._update_limits_ui(self.all_limits_data[key])
        except: pass

    def _auto_save_host_data(self):
        """Pobiera aktualne dane z tabeli i nadpisuje plik CSV."""
        s_str = self.season_var.get()
        path_hosts = Path(f"./{s_str}/Wybory_Gospodarzy_{s_str}.csv")
        
        # Przygotowanie danych do zapisu
        rows = []
        for item_id in self.tree_hosts.get_children():
            nat = self.tree_hosts.item(item_id)['text'].strip()
            vals = self.tree_hosts.item(item_id)['values']
            # vals: 0:Miasto, 1:HS, 2:Bilety, 3:Uzycia
            rows.append({
                "Kraj": nat,
                "Miasto": vals[0],
                "HS": vals[1],
                "Uzycia": vals[3]
            })
        
        # Zapis do pliku
        df_to_save = pd.DataFrame(rows)
        df_to_save.to_csv(path_hosts, sep=";", index=False, encoding="utf-8-sig")
        
    def _count_current_usage_from_planner(self):
        """Skanuje wszystkie szablony i zlicza użycia miast, juniorów oraz grupy letniej (GP+SCOC)."""
        live_usage = {}        # Zliczanie miast (WC, COC, itd.)
        junior_usage = {}      # Zliczanie krajów (JC, MC, ..., DC)
        summer_usage = {}      # Zliczanie krajów (GP, SCOC)
        
        junior_group = ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]
        summer_group = ["GP", "SCOC"]
        
        for gender in ["MEN", "WOMEN"]:
            if gender not in self.planner_tabs: continue
            for cycle, tree in self.planner_tabs[gender].items():
                for item_id in tree.get_children():
                    g_val = str(tree.item(item_id)['values'][1])
                    
                    if "(" in g_val:
                        city = g_val.split(" (")[0].strip()
                        live_usage[city] = live_usage.get(city, 0) + 1
                        
                        kraj = self._get_country_by_city(city)
                        if not kraj: continue

                        # LOGIKA JUNIORSKA
                        if cycle in junior_group:
                            junior_usage[kraj] = junior_usage.get(kraj, 0) + 2
                        
                        # LOGIKA LETNIA (GP + SCOC)
                        if cycle in summer_group:
                            # Ponieważ GP-M i GP-W są zsynchronizowane, liczymy tylko raz (np. dla MEN),
                            # aby jeden weekend zawodów (M+W) liczył się jako 1 zużycie limitu.
                            if gender == "MEN":
                                summer_usage[kraj] = summer_usage.get(kraj, 0) + 2
                                
        # Dodajemy użycia z Mistrzostw (tylko do miast)
        if hasattr(self, 'championship_data'):
            for tour, data in self.championship_data.items():
                if tour == "COCH":
                    for cont_data in data.values():
                        if cont_data.get('city'):
                            city = cont_data['city']
                            live_usage[city] = live_usage.get(city, 0) + 1
                elif data.get('city'):
                    city = data['city']
                    live_usage[city] = live_usage.get(city, 0) + 2
                    
        return live_usage, junior_usage, summer_usage

    def remove_host_from_cycle(self, event=None):
        """Usuwa przypisanie skoczni, oddaje punkty limitu i odświeża widok."""
        # 1. Pobranie aktywnej zakładki
        gender_idx = self.nb_gender.select()
        gender = self.nb_gender.tab(gender_idx, "text")
        tab_nb = self.gender_notebooks[gender]
        cycle = tab_nb.tab(tab_nb.select(), "text")
        tree_dest = self.planner_tabs[gender][cycle]
        
        # 2. Sprawdzenie zaznaczenia
        sel_target = tree_dest.selection()
        if not sel_target:
            return

        target_item = sel_target[0]
        vals = tree_dest.item(target_item)['values']
        tydzien = str(vals[0])
        gospodarz_raw = str(vals[1])

        # Jeśli wiersz jest już pusty, nie rób nic
        if not gospodarz_raw or "(" not in gospodarz_raw:
            return

        # 3. Wyciągnięcie danych do zwrotu limitu
        city = gospodarz_raw.split(" (")[0].strip()
        nat = self._get_country_by_city(city)
        if cycle == "WC" and gender == "MEN" and tydzien == "14":
            punkty_do_oddania = 1
        elif cycle == "WC" and tydzien == "11":
            punkty_do_oddania = 3 # Zwracamy 3 pkt tylko w cyklu WC
        else:
            punkty_do_oddania = 2

        # 4. Zwrot limitu w pamięci
        key = (gender, cycle)
        if key in self.all_limits_data and nat in self.all_limits_data[key]:
            # Zmniejszamy 'Uzyte' (indeks 1)
            self.all_limits_data[key][nat][1] -= punkty_do_oddania
            # Zabezpieczenie, żeby nie spaść poniżej 0
            if self.all_limits_data[key][nat][1] < 0:
                self.all_limits_data[key][nat][1] = 0

        # 5. Wyczyszczenie wiersza w UI
        tree_dest.set(target_item, "Gospodarz", "")

        # --- SYNC: Jeśli GP lub SCOC, usuń też u drugiej płci ---
        if cycle in ["GP", "SCOC"]:
            other_gender = "WOMEN" if gender == "MEN" else "MEN"
            try:
                other_tree = self.planner_tabs[other_gender][cycle]
                other_tree.set(target_item, "Gospodarz", "")
                # Zwrot limitu u drugiej płci
                other_key = (other_gender, cycle)
                if other_key in self.all_limits_data and nat in self.all_limits_data[other_key]:
                    self.all_limits_data[other_key][nat][1] -= punkty_do_oddania
            except: pass
        
        # 6. Pełne odświeżenie (skocznia wróci na listę, limity się zaktualizują)
        self.apply_host_filters()
        self._auto_save_host_data()

class RequirementsFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        txt_frame = ttk.Frame(self)
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        vsb = ttk.Scrollbar(txt_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.text_area = tk.Text(txt_frame, wrap=tk.WORD, yscrollcommand=vsb.set, 
                                 font=("Segoe UI", 10), padx=15, pady=15, bg="#ffffff")
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=self.text_area.yview)
        
        # Definicja stylów
        self.text_area.tag_configure("header", font=("Segoe UI", 12, "bold"), foreground="#003366", spacing1=15)
        self.text_area.tag_configure("rule", font=("Segoe UI", 10), lmargin1=20, lmargin2=20, spacing1=2)
        self.text_area.tag_configure("sub", font=("Segoe UI", 9, "italic"), foreground="#555555")
        
        self._insert_content()
        self.text_area.config(state=tk.DISABLED)

    def _insert_content(self):
        content = [
            ("Olimpiada (OG)", "header"),
            ("- Klasa: Olympic Class [cite: 1]\n- Skocznie: Kompleks Duża (110-160) + Normalna (85-109) [cite: 1]\n- Historia NAT: Ostatnie 5 OG + 5 WCH [cite: 1]\n- Historia Place: Ostatnie 10 OG + 10 WCH [cite: 1]\n- Max użycie: 2 razy w sezonie [cite: 1]", "rule"),
            
            ("Mistrzostwa Świata (WCH)", "header"),
            ("- Klasa: World Cup / Olympic Class [cite: 1]\n- Skocznie: Kompleks Duża (110-160) + Normalna (85-109) [cite: 1]\n- Historia NAT: Ostatnie 5 WCH + 2 OG [cite: 1]\n- Historia Place: Ostatnie 10 WCH + 3 OG [cite: 1]\n- Max użycie: 2 razy w sezonie [cite: 1]", "rule"),
            
            ("Mistrzostwa Świata w Lotach (SFWC)", "header"),
            ("- Klasa: World Cup Class [cite: 1]\n- Skocznie: Mamucia (HS > 160) [cite: 1]\n- Historia: Ostatnie 5 SFWC (NAT i Place) [cite: 1]\n- Max użycie: 2 razy w sezonie ", "rule"),
            
            ("NKIC", "header"),
            ("- Klasa: World Cup / Olympic Class \n- Skocznie: Duża (110-160) \n- Historia NAT: Ostatnie 5 NKIC + 5 IST [cite: 2]\n- Historia Place: Ostatnie 10 NKIC + 10 IST [cite: 2]\n- Max użycie: 2 razy w sezonie [cite: 2]", "rule"),
            
            ("IST", "header"),
            ("- Klasa: World Cup / Olympic Class [cite: 2]\n- Skocznie: Kompleks Duża (110-160) + Normalna (85-109) [cite: 2]\n- Historia NAT: Ostatnie 5 IST + 5 NKIC [cite: 2]\n- Historia Place: Ostatnie 10 IST + 10 NKIC [cite: 2]\n- Max użycie: 2 razy w sezonie [cite: 2]", "rule"),
            
            ("YOG", "header"),
            ("- Klasa: Continental Cup Class [cite: 2, 3]\n- Skocznie: Normalna (85-109) [cite: 2, 3]\n- Historia NAT: Ostatnie 5 YOG + 5 JWC + 2 UNI [cite: 2, 3]\n- Historia Place: Ostatnie 10 YOG + 5 JWC + 2 UNI [cite: 2, 3]\n- Max użycie: 2 razy w sezonie [cite: 3]", "rule"),
            
            ("UNI", "header"),
            ("- Klasa: Continental Cup Class [cite: 3]\n- Skocznie: Normalna (85-109) [cite: 3]\n- Historia NAT: Ostatnie 5 UNI + 5 JWC + 2 YOG [cite: 3]\n- Historia Place: Ostatnie 10 UNI + 5 JWC + 2 YOG [cite: 3]\n- Max użycie: 2 razy w sezonie [cite: 3]", "rule"),
            
            ("JWC", "header"),
            ("- Klasa: Junior / Continental Class \n- Skocznie: Normalna (85-109) \n- Historia NAT: Ostatnie 10 JWC + 2 UNI + 2 YOG \n- Historia Place: Ostatnie 20 JWC + 2 UNI + 2 YOG [cite: 4]\n- Max użycie: 2 razy w sezonie [cite: 4]", "rule"),
            
            ("COCH", "header"),
            ("- Klasa: Junior Class [cite: 4]\n- Skocznie: Normalna (85-109) [cite: 4]\n- Historia: Ostatnie 2 turnieje COCH (NAT i Place) [cite: 4]\n- Max użycie: Możliwe 2 występy w sezonie (1 raz jako COCH) [cite: 4]", "rule"),
        ]
        
        for text, tag in content:
            self.text_area.insert(tk.END, text + "\n", tag)
            
class HostSelectionFrame(ttk.Frame):
    def __init__(self, parent, hills_df):
        super().__init__(parent)
        self.hills_df = hills_df.copy()
        # Ścieżka do historii potrzebna do wykluczeń
        self.history_path = Path("Historia Turniejów.csv")
        
        # Wewnątrz __init__ klasy HostSelectionFrame:
        try:
            # Wczytanie z jawnym usunięciem spacji z nazw kolumn
            _cont_candidates = [
                APP_DIR / "S51" / "ALL_NATIONS_CONTINENTS.csv",
                APP_DIR / "ALL_NATIONS_CONTINENTS.csv",
                Path("S51") / "ALL_NATIONS_CONTINENTS.csv",
                Path("ALL_NATIONS_CONTINENTS.csv"),
            ]
            _cont_path = next((p for p in _cont_candidates if p.exists()), None)
            if _cont_path is None:
                raise FileNotFoundError("Nie znaleziono ALL_NATIONS_CONTINENTS.csv")
            self.continents_df = pd.read_csv(_cont_path, sep=";", encoding='cp1250')
            self.continents_df.columns = self.continents_df.columns.str.strip()
            
            # Normalizacja klucza łączącego (Kraj)
            self.hills_df['Kraj_Link'] = self.hills_df['Kraj'].astype(str).str.strip().str.upper()
            self.continents_df['Kraj_Link'] = self.continents_df['Kraj'].astype(str).str.strip().str.upper()
            
            # Łączenie i czyszczenie kolumny Continent
            self.hills_df = pd.merge(self.hills_df, self.continents_df[['Kraj_Link', 'Continent']], on='Kraj_Link', how='left')
            self.hills_df['Continent'] = self.hills_df['Continent'].fillna('Unknown').str.strip()
            
            # DEBUG: sprawdź w konsoli co widzi program
            print("Dostępne kontynenty:", self.hills_df['Continent'].unique().tolist())
        except Exception as e:
            print(f"Błąd danych kontynentalnych: {e}")
            self.hills_df['Continent'] = 'Unknown'
            
        self._setup_ui()

    def _load_history(self):
        try:
            # Wczytywanie historii z polskimi znakami
            if not self.history_path.exists(): return pd.DataFrame(columns=['Type', 'Season', 'NAT', 'Place'])
            df = pd.read_csv(self.history_path, sep=';', encoding='cp1250', header=None)
            df.columns = ['Type', 'Season', 'NAT', 'Place']
            return df.dropna(subset=['NAT', 'Place'])
        except Exception as e:
            print(f"Błąd wczytywania historii: {e}")
            return pd.DataFrame(columns=['Type', 'Season', 'NAT', 'Place'])
        
    def _setup_ui(self):
        top = ttk.LabelFrame(self, text="Parametry Turnieju", padding=10)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top, text="Typ turnieju:").pack(side=tk.LEFT)
        self.tour_var = tk.StringVar()
        self.combo = ttk.Combobox(top, textvariable=self.tour_var, state="readonly", width=25)
        self.combo['values'] = (
            "OG", "WCH", "SFWC", "NKIC", "IST", "YOG", "UNI", "JWC",
            "COCH-EU", "COCH-AS", "COCH-NA", "COCH-SA", "COCH-AF", "COCH-OC"
        )
        self.combo.pack(side=tk.LEFT, padx=10)
        self.combo.bind("<<ComboboxSelected>>", self.refresh_list)

        # --- NOWOŚĆ: Przycisk losowania ---
        self.btn_random = ttk.Button(top, text="🎲 Losuj Gospodarza", command=self.pick_random_host)
        self.btn_random.pack(side=tk.LEFT, padx=5)
        # ---------------------------------

        self.info_area = tk.Text(self, height=5, font=("Segoe UI", 9), background="#f0f4f7", padx=10, pady=5)
        self.info_area.pack(fill=tk.X, padx=10, pady=5)
        
        self.tree = ttk.Treeview(self, columns=("Miasto", "Skocznia", "HS", "H"), show='tree headings')
        
        # Konfiguracja kolumny #0 (Kraj + Flaga)
        self.tree.heading("#0", text="Kraj")
        self.tree.column("#0", width=150)

        # Konfiguracja pozostałych kolumn
        for col, head in zip(("Miasto", "Skocznia", "HS", "H"), ("Miasto", "Skocznia", "HS", "Homologacja")):
            self.tree.heading(col, text=head)
            self.tree.column(col, width=120)
        
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10,0), pady=10)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=10, padx=(0,10))

    def pick_random_host(self):
        """Wybiera losowego gospodarza, uwzględniając wymóg dwóch skoczni dla wybranych turniejów."""
        selection = self.tour_var.get()
        items = self.tree.get_children()
        
        if not items:
            messagebox.showwarning("Losowanie", "Lista jest pusta! Najpierw wybierz typ turnieju.")
            return

        # Turnieje wymagające kompleksu dwóch skoczni (Duża + Normalna)
        requires_pair = ["OG", "WCH", "IST"]

        if selection in requires_pair:
            # 1. Grupowanie skoczni według miast
            from collections import defaultdict
            city_map = defaultdict(list)
            
            for item_id in items:
                item_data = self.tree.item(item_id)
                kraj = item_data['text'].strip() # Kraj jest w kolumnie #0
                vals = item_data['values']       # values[0]=Miasto, values[1]=Skocznia, values[2]=HS
                
                city_name = vals[0] 
                city_map[city_name].append({
                    'kraj': kraj,
                    'skocznia': vals[1],
                    'hs': vals[2]
                })

            # 2. Filtrowanie miast, które mają przynajmniej 2 skocznie
            valid_cities = [name for name, hills in city_map.items() if len(hills) >= 2]

            if not valid_cities:
                messagebox.showwarning("Losowanie", f"Dla {selection} wymagane są 2 skocznie w jednym mieście (N+D), ale żadne miasto na liście nie spełnia tego warunku!")
                return

            # 3. Losowanie miasta i pobranie dwóch pierwszych skoczni
            chosen_city = random.choice(valid_cities)
            hills = city_map[chosen_city]
            h1, h2 = hills[0], hills[1]
            
            winner_text = (
                f"🎰 Wylosowano KOMPLEKS dla {selection}:\n"
                f"📍 Kraj: {h1['kraj']} | Miasto: {chosen_city}\n\n"
                f"1️⃣ {h1['skocznia']} (HS: {h1['hs']})\n"
                f"2️⃣ {h2['skocznia']} (HS: {h2['hs']})"
            )
            
            # Zaznaczenie w tabeli (opcjonalne, zaznacza pierwszy element pary)
            # Szukamy ID wiersza dla wybranego miasta
            for item_id in items:
                if self.tree.item(item_id)['values'][0] == chosen_city:
                    self.tree.selection_set(item_id)
                    self.tree.see(item_id)
                    break
        else:
            # Standardowe losowanie jednej skoczni dla pozostałych turniejów
            winner_id = random.choice(items)
            item_data = self.tree.item(winner_id)
            
            kraj = item_data['text'].strip()
            v = item_data['values']
            
            winner_text = (
                f"🎰 Wylosowano gospodarza:\n\n"
                f"📍 {kraj} - {v[0]}\n"
                f"🏗 {v[1]} (HS: {v[2]})"
            )
            
            # Podświetlenie wylosowanej skoczni w tabeli
            self.tree.selection_set(winner_id)
            self.tree.see(winner_id)

        messagebox.showinfo("Wynik Losowania", winner_text)

    def refresh_list(self, event=None):
        selection = self.tour_var.get()
        if not selection: return

        history = self._load_history()
        hills = self.hills_df.copy()
        hills['HS_val'] = pd.to_numeric(hills['HS'], errors='coerce').fillna(0)
        
        ex_nat, ex_place = [], []
        info_text = ""

        # Wewnątrz refresh_list, w sekcji if selection.startswith("COCH-"):
        if selection.startswith("COCH-"):
            cont_code = selection.split("-")[1]
            
            # Mapowanie na fragmenty nazw (bardziej odporne na błędy)
            cont_map = {
                "EU": "Europe", "AS": "Asia", "NA": "North America", 
                "SA": "South America", "AF": "Africa", "OC": "Oceania"
            }
            target_continent = cont_map.get(cont_code, "")

            # Wykluczenia z historii
            ex_nat, ex_place = self._get_exclusions(history, [selection], 2, 2)

            # Filtry techniczne: 
            # Zmieniamy: dopuszczamy Junior LUB Continental, jeśli Juniorów brakuje
            allowed_classes = ['JUNIOR CLASS', 'CONTINENTAL CLASS', 'WORLD CUP CLASS', 'OLYMPIC CLASS']
            hills = hills[hills['Homologacja'].isin(allowed_classes)]
            
            # Zakres HS dla skoczni normalnych
            hills = hills[(hills['HS_val'] >= 85) & (hills['HS_val'] < 110)]
            
            # Filtr kontynentu (wielkość liter nie ma znaczenia)
            hills = hills[hills['Continent'].str.contains(target_continent, case=False, na=False)]
            
            info_text = f"{selection}: Junior/Conti Class, HS 85-109, Kontynent: {target_continent}. Historia: 2 edycje."

        # Reszta logiki (OG, WCH itd. - bez zmian względem Twojego kodu)
        elif selection == "OG":
            og_nat_5, _ = self._get_exclusions(history, ["OG"], 5, 0)
            wch_nat_5, _ = self._get_exclusions(history, ["WCH"], 5, 0)
            ex_nat = list(set(og_nat_5 + wch_nat_5))
            _, og_place_10 = self._get_exclusions(history, ["OG"], 0, 10)
            _, wch_place_10 = self._get_exclusions(history, ["WCH"], 0, 10)
            ex_place = list(set(og_place_10 + wch_place_10))
            hills = hills[hills['Homologacja'] == 'OLYMPIC CLASS']
            hills = self._filter_complex(hills)
            info_text = "OG: Olympic Class + Kompleks (D+N). Historia: NAT(5 OG + 5 WCH), Place(10 OG + 10 WCH)."

        elif selection == "WCH":
            # Historia: OG (2/3) + WCH (5/10)
            og_n, og_p = self._get_exclusions(history, ["OG"], 2, 3)
            wch_n, wch_p = self._get_exclusions(history, ["WCH"], 5, 10)
            ex_nat = list(set(og_n + wch_n))
            ex_place = list(set(og_p + wch_p))
            hills = hills[hills['Homologacja'].isin(['WORLD CUP CLASS', 'OLYMPIC CLASS'])]
            hills = self._filter_complex(hills)
            info_text = "WCH: WC/Olympic Class + Kompleks (D+N). Historia: OG(2/3), WCH(5/10)."

        elif selection == "NKIC":
            # 1. Pobieramy kraje (NAT) - ostatnie 5 z NKIC oraz ostatnie 5 z IST
            nkic_nat_5, _ = self._get_exclusions(history, ["NKIC"], 5, 0)
            ist_nat_5, _ = self._get_exclusions(history, ["IST"], 5, 0)
            ex_nat = list(set(nkic_nat_5 + ist_nat_5))

            # 2. Pobieramy miejsca (Place) - ostatnie 10 z NKIC oraz ostatnie 10 z IST
            _, nkic_place_10 = self._get_exclusions(history, ["NKIC"], 0, 10)
            _, ist_place_10 = self._get_exclusions(history, ["IST"], 0, 10)
            ex_place = list(set(nkic_place_10 + ist_place_10))
            
            # 3. Filtry techniczne: Skocznia DUŻA (110-160), World Cup/Olympic Class
            hills = hills[(hills['HS_val'] >= 110) & (hills['HS_val'] <= 160)]
            hills = hills[hills['Homologacja'].isin(['WORLD CUP CLASS', 'OLYMPIC CLASS'])]
            
            info_text = "NKIC: Skocznia DUŻA (110-160). Wykluczenia NAT (5 NKIC + 5 IST) oraz Place (10 NKIC + 10 IST)."

        elif selection == "IST":
            # 1. Ta sama historia co powyżej
            nkic_nat_5, _ = self._get_exclusions(history, ["NKIC"], 5, 0)
            ist_nat_5, _ = self._get_exclusions(history, ["IST"], 5, 0)
            ex_nat = list(set(nkic_nat_5 + ist_nat_5))

            _, nkic_place_10 = self._get_exclusions(history, ["NKIC"], 0, 10)
            _, ist_place_10 = self._get_exclusions(history, ["IST"], 0, 10)
            ex_place = list(set(nkic_place_10 + ist_place_10))
            
            # 2. Filtry techniczne: Kompleks D+N (D: 110-160), World Cup/Olympic Class
            hills = hills[hills['Homologacja'].isin(['WORLD CUP CLASS', 'OLYMPIC CLASS'])]
            hills = self._filter_complex(hills) 
            
            info_text = "IST: Kompleks (D 110-160 + N). Wykluczenia NAT (5 NKIC + 5 IST) oraz Place (10 NKIC + 10 IST)."

        elif selection == "SFWC":
            ex_nat, ex_place = self._get_exclusions(history, ["SFWC"], 5, 5)
            hills = hills[hills['HS_val'] > 160]
            info_text = "SFWC: Skocznia mamucia (HS>160)."

        elif selection == "YOG":
            # --- LOGIKA YOG ---
            # Kraje (NAT): 5 YOG + 5 JWC + 2 UNI
            y_n, _ = self._get_exclusions(history, ["YOG"], 5, 0)
            j_n, _ = self._get_exclusions(history, ["JWC"], 5, 0)
            u_n, _ = self._get_exclusions(history, ["UNI"], 2, 0)
            ex_nat = list(set(y_n + j_n + u_n))

            # Miejsca (Place): 10 YOG + 5 JWC + 2 UNI
            _, y_p = self._get_exclusions(history, ["YOG"], 0, 10)
            _, j_p = self._get_exclusions(history, ["JWC"], 0, 5)
            _, u_p = self._get_exclusions(history, ["UNI"], 0, 2)
            ex_place = list(set(y_p + j_p + u_p))
            
            hills = hills[(hills['HS_val'] >= 85) & (hills['HS_val'] < 110)]
            info_text = "YOG: Skocznia normalna. Historia: NAT(5Y/5J/2U), Place(10Y/5J/2U)."

        elif selection == "UNI":
            # --- LOGIKA UNI ---
            # Kraje (NAT): 5 UNI + 5 JWC + 2 YOG
            u_n, _ = self._get_exclusions(history, ["UNI"], 5, 0)
            j_n, _ = self._get_exclusions(history, ["JWC"], 5, 0)
            y_n, _ = self._get_exclusions(history, ["YOG"], 2, 0)
            ex_nat = list(set(u_n + j_n + y_n))

            # Miejsca (Place): 10 UNI + 5 JWC + 2 YOG
            _, u_p = self._get_exclusions(history, ["UNI"], 0, 10)
            _, j_p = self._get_exclusions(history, ["JWC"], 0, 5)
            _, y_p = self._get_exclusions(history, ["YOG"], 0, 2)
            ex_place = list(set(u_p + j_p + y_p))
            
            hills = hills[(hills['HS_val'] >= 85) & (hills['HS_val'] < 110)]
            info_text = "UNI: Skocznia normalna. Historia: NAT(5U/5J/2Y), Place(10U/5J/2Y)."

        elif selection == "JWC":
            # --- LOGIKA JWC ---
            # Kraje (NAT): 10 JWC + 2 UNI + 2 YOG
            j_n, _ = self._get_exclusions(history, ["JWC"], 10, 0)
            u_n, _ = self._get_exclusions(history, ["UNI"], 2, 0)
            y_n, _ = self._get_exclusions(history, ["YOG"], 2, 0)
            ex_nat = list(set(j_n + u_n + y_n))

            # Miejsca (Place): 20 JWC + 2 UNI + 2 YOG
            _, j_p = self._get_exclusions(history, ["JWC"], 0, 20)
            _, u_p = self._get_exclusions(history, ["UNI"], 0, 2)
            _, y_p = self._get_exclusions(history, ["YOG"], 0, 2)
            ex_place = list(set(j_p + u_p + y_p))
            
            hills = hills[(hills['HS_val'] >= 85) & (hills['HS_val'] < 110)]
            info_text = "JWC: Skocznia normalna. Historia: NAT(10J/2U/2Y), Place(20J/2U/2Y)."

        # FINALNE FILTRY I AKTUALIZACJA
        hills = hills[~hills['Kraj'].isin(ex_nat)]
        hills = hills[~hills['Miasto'].isin(ex_place)]

        self._update_info(info_text, ex_nat, ex_place)
        
        # Czyścimy stare dane
        for i in self.tree.get_children(): 
            self.tree.delete(i)
            
        # Wstawiamy nowe dane z flagami
        for _, r in hills.iterrows():
            kraj = str(r['Kraj']).strip()
            # Pobieramy flagę z głównej aplikacji (CalendarsFrame przekazuje się jako parent w Twoim kodzie)
            # Uwaga: Zakładamy, że self.master (Notebook) -> self.master.master to CalendarsFrame
            # Ale bezpieczniej użyć metody, którą już masz w głównej klasie:
            img = None
            if hasattr(self.master.master, "_get_flag_image"):
                img = self.master.master._get_flag_image(kraj)

            # Wstawiamy: Kraj jako tekst w #0 (z obrazkiem), reszta w values
            self.tree.insert("", tk.END, text=f" {kraj}", image=img, 
                             values=(r['Miasto'], r['Skocznia'], r['HS'], r['Homologacja']))
            
    def _filter_complex(self, df):
        """Zostawia tylko miasta posiadające Dużą (HS 110-160) ORAZ Normalną (85-109)."""
        def city_has_both(group):
            # Sprawdzamy czy w mieście jest przynajmniej jedna duża (110-160)
            has_large = ((group['HS_val'] >= 110) & (group['HS_val'] <= 160)).any()
            # Sprawdzamy czy w mieście jest przynajmniej jedna normalna (85-109)
            has_normal = ((group['HS_val'] >= 85) & (group['HS_val'] < 110)).any()
            return has_large and has_normal

        # 1. Znajdź miasta spełniające wymóg kompleksu (N + L)
        valid_cities = df.groupby('Miasto').filter(city_has_both)['Miasto'].unique()
        
        # 2. Zwróć skocznie z tych miast, ale WYŁĄCZNIE te o HS <= 160 (wycinamy mamuty)
        return df[(df['Miasto'].isin(valid_cities)) & (df['HS_val'] <= 160)]
    
    def _update_info(self, main_text, ex_nat, ex_place):
        """Aktualizuje pole tekstowe z informacjami o zablokowanych krajach i miastach."""
        self.info_area.config(state=tk.NORMAL)
        self.info_area.delete("1.0", tk.END)
        self.info_area.insert(tk.END, f"{main_text}\n")
        
        # Wyświetlanie unikalnych zablokowanych jednostek
        if ex_nat:
            self.info_area.insert(tk.END, f"Zablokowane kraje (NAT): {', '.join(set(ex_nat))}\n", "small")
        if ex_place:
            self.info_area.insert(tk.END, f"Zablokowane miasta (Place): {', '.join(set(ex_place))}", "small")
            
        self.info_area.tag_configure("small", foreground="gray", font=("Segoe UI", 8))
        self.info_area.config(state=tk.DISABLED)

    def _update_treeview(self, df, is_coch=False):
        if is_coch:
            self.tree.pack_forget()
            if not hasattr(self, 'coch_notebook'): self._setup_coch_ui()
            self.coch_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            self._fill_coch_tabs(df)
        else:
            if hasattr(self, 'coch_notebook'): self.coch_notebook.pack_forget()
            self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            for i in self.tree.get_children(): self.tree.delete(i)
            for _, r in df.iterrows():
                self.tree.insert("", tk.END, values=(r['Kraj'], r['Miasto'], r['Skocznia'], r['HS'], r['Homologacja']))

    def _fill_coch_tabs(self, df):
        """Rozdziela skocznie do zakładek Europe, Asia itd."""
        for cont, tree in self.coch_trees.items():
            for i in tree.get_children(): tree.delete(i)
            
            # Filtr kontynentalny
            cont_df = df[df['Continent'].astype(str).str.strip().str.lower() == cont.lower()]
            
            for _, r in cont_df.iterrows():
                tree.insert("", tk.END, values=(r['Kraj'], r['Miasto'], r['Skocznia'], r['HS'], r['Homologacja']))

    def _setup_coch_ui(self):
        """Tworzy system 6 zakładek kontynentalnych."""
        if hasattr(self, 'coch_notebook'):
            self.coch_notebook.destroy()

        self.coch_notebook = ttk.Notebook(self)
        self.coch_trees = {}
        
        continents = ["Europe", "Asia", "North America", "South America", "Africa", "Oceania"]
        cols = ("Kraj", "Miasto", "Skocznia", "HS", "Homologacja")
        
        for cont in continents:
            frame = ttk.Frame(self.coch_notebook)
            self.coch_notebook.add(frame, text=cont)
            
            tree = ttk.Treeview(frame, columns=cols, show='headings', height=15)
            for c in cols:
                tree.heading(c, text=c)
                tree.column(c, width=120, anchor=tk.W if c in ["Miasto", "Skocznia"] else tk.CENTER)
            
            vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            self.coch_trees[cont] = tree

    def _get_exclusions(self, history_df, types, nat_limit, place_limit):
        """Pobiera listy wykluczeń z historii dla zadanych limitów."""
        relevant = history_df[history_df['Type'].isin(types)]
        
        # Pobieramy unikalne kraje z ostatnich N rekordów
        ex_nat = relevant.tail(nat_limit)['NAT'].unique().tolist() if nat_limit > 0 else []
        
        # Pobieramy unikalne miasta z ostatnich M rekordów
        ex_place = relevant.tail(place_limit)['Place'].unique().tolist() if place_limit > 0 else []
        
        return ex_nat, ex_place

class EarningsFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.sort_reverse = {} 

        self.stats_regular = {
            "WC-M": (20, 100000, 3000), "WC-W": (20, 100000, 3000),
            "COC-M": (15, 50000, 2000), "COC-W": (15, 50000, 2000),
            "GP-M": (14, 40000, 1800), "GP-W": (14, 40000, 1800),
            "FC-M": (12, 25000, 1500), "FC-W": (12, 25000, 1500),
            "SCOC-M": (11, 20000, 1250), "SCOC-W": (11, 20000, 1250),
            "JC-M": (10, 10000, 1000), "JC-W": (10, 10000, 1000),
            "MC-M": (9, 8500, 850), "MC-W": (9, 8500, 850),
            "PC-M": (8, 7500, 750), "PC-W": (8, 7500, 750),
            "QC-M": (7, 6500, 650), "QC-W": (7, 6500, 650),
            "TC-M": (6, 5500, 550), "TC-W": (6, 5500, 550),
            "AC-M": (5, 4500, 450), "AC-W": (5, 4500, 450),
            "BC-M": (4, 3500, 350), "BC-W": (4, 3500, 350),
            "DC-M": (3, 2500, 250), "DC-W": (3, 2500, 250)
        }
        
        self.stats_champs = {
            "OG": (250, 1500000, 32000), "WCH": (200, 1000000, 27000),
            "SFWC": (150, 750000, 22000), "IST": (120, 600000, 17500),
            "NKIC": (100, 500000, 15000), "YOG": (90, 450000, 13000),
            "JWC": (80, 400000, 11000), "COCH": (70, 350000, 9000),
            "UNI": (60, 300000, 7000)
        }

        self._setup_ui()

    def _setup_ui(self):
        wrap = ttk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.cols = ("NAT", "Miasto", "Pojemność", "Frekwencja", "TV", "Ochrona", "Przygotowanie", "Suma_Netto", "Podatek", "Suma_Brutto")
        self.tv = ttk.Treeview(wrap, columns=self.cols, show="tree headings")

        self.tv.heading("#0", text="Cykl", command=lambda: self.sort_column("#0"))
        self.tv.column("#0", width=120)

        display_headers = ["NAT", "Miasto", "Pojemność", "Frekwencja %", "TV", "Ochrona", "Przygotowanie", "Suma (Netto)", "Podatek", "Suma (Finał)"]
        col_widths = {"NAT": 60, "Miasto": 110, "Pojemność": 90, "Frekwencja": 85}
        for col_id, text in zip(self.cols, display_headers):
            self.tv.heading(col_id, text=text, command=lambda c=col_id: self.sort_column(c))
            anchor = tk.W if col_id in ["NAT", "Miasto"] else tk.E
            width = col_widths.get(col_id, 110)
            self.tv.column(col_id, width=width, anchor=anchor)

        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

    def sort_column(self, col):
        l = [(self.tv.set(k, col) if col != "#0" else self.tv.item(k, "text"), k) for k in self.tv.get_children('')]
        try:
            l.sort(key=lambda t: float(t[0].replace(' ', '')), reverse=self.sort_reverse.get(col, False))
        except ValueError:
            l.sort(reverse=self.sort_reverse.get(col, False))

        for index, (val, k) in enumerate(l):
            self.tv.move(k, '', index)
        self.sort_reverse[col] = not self.sort_reverse.get(col, False)

    def calculate_tax(self, pre_tax):
        if pre_tax <= 100000: return 0
        elif pre_tax <= 150000: return pre_tax * 0.03
        elif pre_tax <= 200000: return pre_tax * 0.06
        elif pre_tax <= 300000: return pre_tax * 0.12
        elif pre_tax <= 500000: return pre_tax * 0.18
        elif pre_tax <= 600000: return pre_tax * 0.24
        else: return pre_tax * 0.30

    def _get_season_suffix(self) -> str:
        if hasattr(self.main_app, 'dir_var'):
            folder_name = str(self.main_app.dir_var.get())
        else:
            folder_name = str(getattr(self.main_app, 'cal_dir', 'S51'))
        m = re.search(r'S\d+', folder_name, re.IGNORECASE)
        return m.group(0).upper() if m else "S51"

    def _load_nations_ranking(self) -> dict[str, int]:
        """Wczytuje klasyfikację WC-M narody → {NAT: pozycja}."""
        try:
            season = self._get_season_suffix()
            path = Path(f"./{season}/Klasyfikacje {season}/{season}_WC-M__nations.csv")
            if not path.exists():
                return {}
            import pandas as pd
            df = pd.read_csv(path, sep=';', encoding='utf-8-sig', dtype=str)
            df.columns = [c.strip().upper() for c in df.columns]
            nat_col = next((c for c in df.columns if c in ('NAT', 'KRAJ')), None)
            if nat_col is None:
                return {}
            lp_col = next((c for c in df.columns if c in ('LP.', 'LP')), None)
            result: dict[str, int] = {}
            for i, (_, row) in enumerate(df.iterrows()):
                nat = str(row[nat_col]).strip()
                if not nat or nat == 'nan':
                    continue
                if lp_col:
                    try:
                        pos = int(float(str(row[lp_col]).replace(' ', '')))
                    except Exception:
                        pos = i + 1
                else:
                    pos = i + 1
                result[nat] = pos
            return result
        except Exception:
            return {}

    def _compute_frekwencja(self, lookup_seria: str, dod_inf: str,
                            kraj: str, nations_rank: dict[str, int],
                            is_champ: bool) -> float:
        base = _FREKWENCJA_BASE.get(lookup_seria, 0.20)
        turniej_bonus = _TURNIEJE_BONUS.get(str(dod_inf).strip().upper(), 0.0) if not is_champ else 0.0
        rank = nations_rank.get(kraj, 9999)
        kraj_bonus = next(bonus for cap, bonus in _KRAJ_BONUS_TIERS if rank <= cap)
        max_cap = 1.00 if lookup_seria == "OG" else 0.97
        return min(max_cap, base + turniej_bonus + kraj_bonus)

    def refresh_data(self):
        for i in self.tv.get_children(): self.tv.delete(i)
        if not hasattr(self.main_app, '_all_weeks_data') or not self.main_app._all_weeks_data:
            return

        import pandas as pd
        import math

        df = pd.concat(self.main_app._all_weeks_data, ignore_index=True)
        df.columns = df.columns.str.strip()
        h_df = self.main_app.host_tab.hills_df.copy()
        h_df.columns = h_df.columns.str.strip()

        target_col = 'Miejsca dla kibiców'
        if target_col in h_df.columns:
            h_df = h_df.rename(columns={target_col: 'Bilety'})
        if 'Bilety' not in h_df.columns:
            h_df['Bilety'] = 0
        if 'Miasto' not in h_df.columns:
            h_df['Miasto'] = ""

        hills = h_df[['Miasto', 'Bilety']].drop_duplicates(subset=['Miasto'])

        try:
            df = pd.merge(df, hills, left_on='Skocznia', right_on='Miasto', how='left')
        except Exception:
            return

        df['Bilety'] = pd.to_numeric(df['Bilety'].astype(str).str.replace(' ', ''), errors='coerce').fillna(0)

        order = [
            'GP-M', 'GP-W', 'SCOC-M', 'SCOC-W', 'WC-M', 'WC-W', 'COC-M', 'COC-W',
            'FC-M', 'FC-W', 'JC-M', 'JC-W', 'MC-M', 'MC-W', 'PC-M', 'PC-W',
            'QC-M', 'QC-W', 'TC-M', 'TC-W', 'AC-M', 'BC-M', 'CC-M', 'DC-M',
            'OG', 'WCH', 'SFWC', 'NKIC', 'IST', 'YOG', 'UNI', 'JWC',
            'COCH-EU', 'COCH-AS', 'COCH-NA', 'COCH-SA', 'COCH-AF', 'COCH-OC'
        ]

        nations_rank = self._load_nations_ranking()
        processed_data = []
        unique_champs = set()

        for _, row in df.iterrows():
            seria = str(row['Seria'])
            miasto_z_bazy = str(row['Miasto_y'] if 'Miasto_y' in row else row['Miasto'])
            if miasto_z_bazy == "nan":
                miasto_z_bazy = str(row['Skocznia'])
            kraj = str(row.get('NAT', '')).strip()
            dod_inf = str(row.get('Dod. inf.', '')).strip()

            base_seria = seria.split('-')[0]
            is_champ = base_seria in self.stats_champs
            lookup_seria = base_seria if is_champ else seria

            if is_champ:
                key = (base_seria, miasto_z_bazy)
                if key in unique_champs:
                    continue
                unique_champs.add(key)

            stats = self.stats_champs.get(lookup_seria) or self.stats_regular.get(lookup_seria)
            if not stats:
                continue

            cena_bil, tv_val, personel = stats
            poj_skoczni = int(row['Bilety'])
            frekwencja = self._compute_frekwencja(lookup_seria, dod_inf, kraj, nations_rank, is_champ)
            kibice = int(poj_skoczni * frekwencja)
            mnoznik = math.floor(poj_skoczni / 1000)
            koszt_personelu = mnoznik * personel

            suma_bez_podatku = (kibice * cena_bil) + tv_val - (2 * koszt_personelu)
            podatek = self.calculate_tax(suma_bez_podatku)
            suma_final = suma_bez_podatku - podatek

            processed_data.append({
                "Cykl": lookup_seria if is_champ else seria,
                "Kraj": kraj,
                "Miasto": miasto_z_bazy,
                "Bilety_Poj": poj_skoczni,
                "Frekwencja": frekwencja,
                "TV": tv_val,
                "Ochrona": koszt_personelu,
                "Przygotowanie": koszt_personelu,
                "Netto": suma_bez_podatku,
                "Podatek": podatek,
                "Finał": suma_final
            })

        processed_data.sort(key=lambda item: order.index(item['Cykl']) if item['Cykl'] in order else 999)

        for d in processed_data:
            img = self.main_app._get_flag_image(d['Kraj'])
            self.tv.insert("", "end", text=f" {d['Cykl']}", image=img,
                           values=(
                               d['Kraj'],
                               d['Miasto'],
                               f"{d['Bilety_Poj']:,}".replace(",", " "),
                               f"{int(d['Frekwencja'] * 100)}%",
                               f"{d['TV']:,}".replace(",", " "),
                               f"{d['Ochrona']:,}".replace(",", " "),
                               f"{d['Przygotowanie']:,}".replace(",", " "),
                               f"{int(d['Netto']):,}".replace(",", " "),
                               f"{int(d['Podatek']):,}".replace(",", " "),
                               f"{int(d['Finał']):,}".replace(",", " ")
                           ))
        if hasattr(self.main_app, 'total_earnings_tab'):
            self.main_app.total_earnings_tab.refresh_data(processed_data)

class TotalEarningsFrame(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.sort_reverse = {}
        self._setup_ui()

    def _get_season_suffix(self):
        """Wyciąga numer sezonu (np. S51) z aktualnie wybranego folderu."""
        # Używamy dir_var.get(), ponieważ to tam tkinter przechowuje aktualną ścieżkę
        if hasattr(self.main_app, 'dir_var'):
            folder_name = str(self.main_app.dir_var.get())
        else:
            folder_name = str(self.main_app.cal_dir) # fallback do domyślnej ścieżki
            
        match = re.search(r'S\d+', folder_name, re.IGNORECASE)
        if match:
            return match.group(0).upper()
        return "S51"

    def _load_prev_season_earnings(self):
        """Wczytuje Zysk Finalny krajów z poprzedniego sezonu."""
        season = self._get_season_suffix()
        match = re.search(r'(\d+)', season)
        if not match:
            return {}
        prev_num = int(match.group(1)) - 1
        prev_season = f"S{prev_num}"
        prev_path = Path(f"./{prev_season}/Zysk Konkursy {prev_season}.csv")
        if not prev_path.exists():
            return {}
        try:
            import pandas as pd
            df = pd.read_csv(prev_path, sep=';', encoding='utf-8-sig', dtype=str)
            df.columns = [c.strip() for c in df.columns]
            # Szukamy kolumny NAT i Zysk Finalny
            nat_col = next((c for c in df.columns if c.upper() in ('NAT', 'KRAJ')), None)
            fin_col = next((c for c in df.columns if 'ZYSK' in c.upper() and 'FIN' in c.upper()), None)
            if nat_col is None or fin_col is None:
                return {}
            result = {}
            for _, row in df.iterrows():
                nat = str(row[nat_col]).strip()
                try:
                    val = float(str(row[fin_col]).replace(' ', '').replace(',', '.'))
                    result[nat] = val
                except Exception:
                    pass
            return result
        except Exception:
            return {}

    def _setup_ui(self):
        top_bar = ttk.Frame(self)
        top_bar.pack(fill=tk.X, padx=10, pady=5)
        
        # Przycisk eksportu
        self.btn_export = ttk.Button(top_bar, text="💾 Eksportuj do CSV", command=self.export_to_csv)
        self.btn_export.pack(side=tk.LEFT)
        
        self.lbl_info = ttk.Label(top_bar, text="", foreground="gray")
        self.lbl_info.pack(side=tk.LEFT, padx=10)

        wrap = ttk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Dodajemy kolumnę NAT jako identyfikator tekstowy, #0 będzie flagą
        self.cols = ("NAT", "Liczba_Konkursów", "Suma_Netto", "Suma_Podatek", "Bonus_Zeszły_Sezon", "Zysk_Finalny")
        self.tv = ttk.Treeview(wrap, columns=self.cols, show="tree headings")
        
        # Kolumna #0 dla flagi
        self.tv.heading("#0", text="Flaga")
        self.tv.column("#0", width=50, anchor=tk.CENTER)

        headers = ["NAT", "Liczba Konkursów", "Suma (Netto)", "Suma Podatku", "Bonus za zeszły sezon", "Zysk Finalny"]
        widths  = [60, 130, 140, 140, 160, 140]
        for col, head, w in zip(self.cols, headers, widths):
            self.tv.heading(col, text=head, command=lambda c=col: self.sort_column(c))
            anchor = tk.CENTER if col in ["NAT", "Liczba_Konkursów"] else tk.E
            self.tv.column(col, width=w, anchor=anchor)

        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=vsb.set)
        self.tv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

    def sort_column(self, col):
        l = [(self.tv.set(k, col), k) for k in self.tv.get_children('')]
        try:
            l.sort(key=lambda t: float(t[0].replace(' ', '')), reverse=self.sort_reverse.get(col, True))
        except ValueError:
            l.sort(reverse=self.sort_reverse.get(col, True))
        for index, (val, k) in enumerate(l):
            self.tv.move(k, '', index)
        self.sort_reverse[col] = not self.sort_reverse.get(col, True)

    def refresh_data(self, processed_data):
        for i in self.tv.get_children(): self.tv.delete(i)
        if not processed_data: return

        # Dynamiczna aktualizacja napisu na przycisku i info
        season = self._get_season_suffix()
        self.btn_export.config(text=f"💾 Eksportuj do Zysk Konkursy {season}.csv")

        # Wczytaj zarobki z poprzedniego sezonu
        prev_earnings = self._load_prev_season_earnings()

        summary = {}
        for d in processed_data:
            nat = d['Kraj']
            if nat not in summary:
                summary[nat] = {'count': 0, 'netto': 0, 'tax': 0, 'final': 0}
            summary[nat]['count'] += 1
            summary[nat]['netto'] += d['Netto']
            summary[nat]['tax'] += d['Podatek']
            summary[nat]['final'] += d['Finał']

        for nat, s in sorted(summary.items(), key=lambda x: x[1]['final'], reverse=True):
            img = self.main_app._get_flag_image(nat)

            # Oblicz bonus: jeśli obecny zysk finalny < połowy zarobków z poprzedniego sezonu
            prev_final = prev_earnings.get(nat, None)
            bonus = 0
            if prev_final is not None and prev_final > 0:
                if s['final'] < prev_final / 2:
                    bonus = s['final'] / 2

            final_with_bonus = s['final'] + bonus

            self.tv.insert("", "end", text="", image=img, values=(
                nat,
                s['count'],
                f"{int(s['netto']):,}".replace(",", " "),
                f"{int(s['tax']):,}".replace(",", " "),
                f"{int(bonus):,}".replace(",", " ") if bonus else "—",
                f"{int(final_with_bonus):,}".replace(",", " ")
            ))

    def export_to_csv(self):
        import csv
        import os
        season = self._get_season_suffix()  # Pobiera np. "S51"
        
        # Tworzenie ścieżki do folderu (np. ./S51)
        folder_path = f"./{season}"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            
        # Pełna ścieżka do pliku
        file_name = f"Zysk Konkursy {season}.csv"
        path = os.path.join(folder_path, file_name)
        
        try:
            # Używamy utf-8-sig, aby Excel poprawnie czytał polskie znaki i separatory
            with open(path, mode='w', newline='', encoding='utf-8-sig') as f:
                # Opcjonalnie: wymuszenie na Excelu czytania średnika poprzez 'sep=;'
                # f.write("sep=;\n") # Możesz odkomentować tę linię, jeśli nadal byłby problem
                
                writer = csv.writer(f, delimiter=';')
                
                # Nagłówki
                writer.writerow(["NAT", "Liczba Konkursow", "Suma Netto", "Suma Podatku", "Bonus za zeszly sezon", "Zysk Finalny"])
                
                # Dane z tabeli
                for iid in self.tv.get_children():
                    vals = self.tv.item(iid)['values']
                    # Usuwamy spacje z liczb, aby Excel traktował je jako wartości do obliczeń
                    clean_row = [str(v).replace(' ', '') for v in vals]
                    writer.writerow(clean_row)
                    
            messagebox.showinfo("Eksport", f"Pomyślnie wyeksportowano do folderu {folder_path}:\n{file_name}")
        except Exception as e:
            messagebox.showerror("Błąd", f"Błąd zapisu: {e}")
            
class _App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Kalendarze – GUI")
        try:
            self.state("zoomed")
        except Exception:
            self.geometry("1200x800")
        frm = CalendarsFrame(self)
        frm.pack(fill=tk.BOTH, expand=True)

if __name__ == "__main__":
    _App().mainloop()

def _desired_tab_index_fallback(parent_nb, nbM, nbW, nbC, tab_name: str) -> int:
    name = str(tab_name).upper()
    if parent_nb is nbC:
        order = ['WCH','NKIC','UNI','JWC']
    else:
        order = ['GP','SCOC','WC','COC','FC','JC','MC','PC','QC','TC','AC','BC','DC']
    prefix = name.split('-')[0]
    try:
        pos = order.index(prefix)
    except ValueError:
        return 'end'
    try:
        end = parent_nb.index('end') or 0
    except Exception:
        end = 0
    existing = [parent_nb.tab(i, 'text') for i in range(end)]
    idx = 0
    for t in existing:
        p2 = str(t).upper().split('-')[0]
        try:
            if order.index(p2) <= pos:
                idx += 1
        except ValueError:
            idx += 1
    return idx
