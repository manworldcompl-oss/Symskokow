#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
staff_gui_embedded.py — „Sztab” GUI (embedded)

• Czyta dwa pliki CSV z domyślnymi nazwami:
    - "Sztab M S51.csv" → zakładka MEN
    - "Sztab W S51.csv" → zakładka WOMEN
• Każdy plik ładowany jest do tabeli (Treeview) z automatycznym dopasowaniem kolumn,
  sortowaniem po kliknięciu nagłówka i poziomymi/pionowymi paskami przewijania.
• Jeżeli w danych jest kolumna "Kraj" albo "NAT", z lewej strony pojawia się
  wąska kolumna z flagą (plik PNG 18×11 z ./flags/<kod>.png), a wiersze są
  wiązane z obrazkami tak, aby nie znikały z pamięci.
• Można wskazać inne pliki przez „…” i Wczytaj.

Udostępnia funkcję: build_gui(parent) → ttk.Frame
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Tuple

try:
    import pandas as pd
except Exception as e:  # pragma: no cover
    raise SystemExit("Ten moduł wymaga pandas: pip install pandas")

APP_DIR = Path(__file__).resolve().parent
FLAGS_DIR = APP_DIR / "flags"  # 18x11 png

PROBABILITY_TABLE = {
    15: {100: 10, 99: 9, 98: 8, 97: 7, 96: 6, 95: 5, 94: 5, 93: 4, 92: 4, 91: 4, 90: 3, 89: 3, 88: 3, 87: 3, 86: 2, 85: 2, 84: 2, 83: 2, 82: 1, 81: 1, 80: 1, 79: 1, 78: 1, 77: 1, 76: 1},
    14: {100: 7, 99: 8, 98: 8, 97: 9, 96: 9, 95: 9, 94: 10, 93: 10, 92: 10, 91: 10, 90: 9, 89: 9, 88: 9, 87: 8, 86: 8, 85: 7, 84: 7, 83: 6, 82: 6, 81: 5, 80: 5, 79: 4, 78: 4, 77: 3, 76: 3, 75: 2, 74: 2, 73: 1, 72: 1, 71: 1},
    13: {100: 4, 99: 4, 98: 5, 97: 5, 96: 6, 95: 6, 94: 7, 93: 7, 92: 8, 91: 8, 90: 9, 89: 9, 88: 10, 87: 10, 86: 10, 85: 9, 84: 9, 83: 9, 82: 8, 81: 8, 80: 7, 79: 7, 78: 6, 77: 6, 76: 5, 75: 5, 74: 4, 73: 4, 72: 3, 71: 3, 70: 2, 69: 2, 68: 1, 67: 1, 66: 1},
    12: {100: 1, 99: 1, 98: 2, 97: 2, 96: 3, 95: 3, 94: 4, 93: 4, 92: 5, 91: 5, 90: 6, 89: 6, 88: 7, 87: 7, 86: 8, 85: 8, 84: 9, 83: 9, 82: 10, 81: 10, 80: 10, 79: 9, 78: 9, 77: 8, 76: 8, 75: 7, 74: 7, 73: 6, 72: 6, 71: 5, 70: 5, 69: 4, 68: 4, 67: 3, 66: 3, 65: 2, 64: 2, 63: 2, 62: 1, 61: 1},
    11: {96: 1, 95: 1, 94: 2, 93: 2, 92: 3, 91: 3, 90: 4, 89: 4, 88: 5, 87: 5, 86: 6, 85: 6, 84: 7, 83: 7, 82: 8, 81: 8, 80: 9, 79: 9, 78: 9, 77: 10, 76: 10, 75: 10, 74: 9, 73: 9, 72: 8, 71: 8, 70: 7, 69: 7, 68: 6, 67: 6, 66: 5, 65: 5, 64: 4, 63: 4, 62: 3, 61: 3, 60: 2, 59: 2, 58: 1, 57: 1, 56: 1},
    10: {92: 1, 91: 1, 90: 2, 89: 2, 88: 3, 87: 3, 86: 4, 85: 4, 84: 5, 83: 5, 82: 6, 81: 6, 80: 7, 79: 7, 78: 8, 77: 8, 76: 9, 75: 9, 74: 9, 73: 10, 72: 10, 71: 10, 70: 9, 69: 9, 68: 8, 67: 8, 66: 7, 65: 7, 64: 6, 63: 6, 62: 5, 61: 5, 60: 4, 59: 4, 58: 3, 57: 3, 56: 2, 55: 2, 54: 1, 53: 1, 52: 1, 51: 1},
    9: {88: 1, 87: 1, 86: 2, 85: 2, 84: 3, 83: 3, 82: 4, 81: 4, 80: 5, 79: 5, 78: 6, 77: 6, 76: 7, 75: 7, 74: 8, 73: 8, 72: 9, 71: 9, 70: 9, 69: 10, 68: 10, 67: 10, 66: 9, 65: 9, 64: 8, 63: 8, 62: 7, 61: 7, 60: 6, 59: 6, 58: 5, 57: 5, 56: 4, 55: 4, 54: 3, 53: 3, 52: 2, 51: 2, 50: 1, 49: 1, 48: 1, 47: 1, 46: 1},
    8: {83: 1, 82: 1, 81: 2, 80: 2, 79: 3, 78: 3, 77: 4, 76: 4, 75: 5, 74: 5, 73: 6, 72: 6, 71: 7, 70: 7, 69: 8, 68: 8, 67: 9, 66: 9, 65: 9, 64: 10, 63: 10, 62: 10, 61: 9, 60: 9, 59: 8, 58: 8, 57: 7, 56: 7, 55: 6, 54: 6, 53: 5, 52: 5, 51: 4, 50: 4, 49: 3, 48: 3, 47: 2, 46: 2, 45: 1, 44: 1, 43: 1, 42: 1, 41: 1},
    7: {78: 1, 77: 1, 76: 2, 75: 2, 74: 3, 73: 3, 72: 4, 71: 4, 70: 5, 69: 5, 68: 6, 67: 6, 66: 7, 65: 7, 64: 8, 63: 8, 62: 9, 61: 9, 60: 9, 59: 10, 58: 10, 57: 10, 56: 9, 55: 9, 54: 8, 53: 8, 52: 7, 51: 7, 50: 6, 49: 6, 48: 5, 47: 5, 46: 4, 45: 4, 44: 3, 43: 3, 42: 2, 41: 2, 40: 1, 39: 1, 38: 1, 37: 1, 36: 1},
    6: {74: 1, 73: 1, 72: 2, 71: 2, 70: 3, 69: 3, 68: 4, 67: 4, 66: 5, 65: 5, 64: 6, 63: 6, 62: 7, 61: 7, 60: 8, 59: 8, 58: 9, 57: 9, 56: 9, 55: 10, 54: 10, 53: 10, 52: 9, 51: 9, 50: 8, 49: 8, 48: 7, 47: 7, 46: 6, 45: 6, 44: 5, 43: 5, 42: 4, 41: 4, 40: 3, 39: 3, 38: 2, 37: 2, 36: 1, 35: 1, 34: 1, 33: 1, 32: 1, 31: 1},
    5: {69: 1, 68: 1, 67: 2, 66: 2, 65: 3, 64: 3, 63: 4, 62: 4, 61: 5, 60: 5, 59: 6, 58: 6, 57: 7, 56: 7, 55: 8, 54: 8, 53: 9, 52: 9, 51: 9, 50: 10, 49: 10, 48: 10, 47: 9, 46: 9, 45: 8, 44: 8, 43: 7, 42: 7, 41: 6, 40: 6, 39: 5, 38: 5, 37: 4, 36: 4, 35: 3, 34: 3, 33: 2, 32: 2, 31: 1, 30: 1, 29: 1, 28: 1, 27: 1, 26: 1},
    4: {64: 1, 63: 1, 62: 2, 61: 2, 60: 3, 59: 3, 58: 4, 57: 4, 56: 5, 55: 5, 54: 6, 53: 6, 52: 7, 51: 7, 50: 8, 49: 8, 48: 9, 47: 9, 46: 9, 45: 10, 44: 10, 43: 10, 42: 9, 41: 9, 40: 8, 39: 8, 38: 7, 37: 7, 36: 6, 35: 6, 34: 5, 33: 5, 32: 4, 31: 4, 30: 3, 29: 3, 28: 2, 27: 2, 26: 1, 25: 1, 24: 1, 23: 1, 22: 1, 21: 1},
    3: {59: 1, 58: 1, 57: 2, 56: 2, 55: 3, 54: 3, 53: 4, 52: 4, 51: 5, 50: 5, 49: 6, 48: 6, 47: 7, 46: 7, 45: 8, 44: 8, 43: 9, 42: 9, 41: 9, 40: 10, 39: 10, 38: 10, 37: 9, 36: 9, 35: 8, 34: 8, 33: 7, 32: 7, 31: 6, 30: 6, 29: 5, 28: 5, 27: 4, 26: 4, 25: 3, 24: 3, 23: 2, 22: 2, 21: 1, 20: 1, 19: 1, 18: 1, 17: 1, 16: 1},
    2: {54: 1, 53: 1, 52: 2, 51: 2, 50: 3, 49: 3, 48: 4, 47: 4, 46: 5, 45: 5, 44: 6, 43: 6, 42: 7, 41: 7, 40: 8, 39: 8, 38: 9, 37: 9, 36: 9, 35: 10, 34: 10, 33: 10, 32: 9, 31: 9, 30: 8, 29: 8, 28: 7, 27: 7, 26: 6, 25: 6, 24: 5, 23: 5, 22: 4, 21: 4, 20: 3, 19: 3, 18: 2, 17: 2, 16: 1, 15: 1, 14: 1, 13: 1, 12: 1, 11: 1},
    1: {50: 1, 49: 1, 48: 2, 47: 2, 46: 3, 45: 3, 44: 4, 43: 4, 42: 5, 41: 5, 40: 6, 39: 6, 38: 7, 37: 7, 36: 8, 35: 8, 34: 9, 33: 9, 32: 9, 31: 10, 30: 10, 29: 10, 28: 9, 27: 9, 26: 8, 25: 8, 24: 7, 23: 7, 22: 6, 21: 6, 20: 5, 19: 5, 18: 4, 17: 4, 16: 3, 15: 3, 14: 2, 13: 2, 12: 1, 11: 1, 10: 1},
}

__all__ = ["build_gui", "StaffFrame"]
_ROLE_LABELS = {
    "L":  "Lekarz",
    "F":  "Fizjo",
    "TS": "Trener Seniorów",
    "TJ": "Trener Juniorów",
    "S":  "Skaut",
}

def _canon_cols(df: pd.DataFrame) -> tuple[str|None, str|None, str|None]:
    """Zwraca (nat_col, code_col, sex_col) wykryte w df."""
    nat_col  = next((c for c in df.columns if str(c).strip().lower() in {"nat","kraj","reprezentacja","country","code"}), None)
    code_col = next((c for c in df.columns if str(c).strip().lower() in {"code","kod","rola","funkcja"}), None)
    sex_col  = next((c for c in df.columns if str(c).strip().lower() in {"sex","płeć","pleć","plec"}), None)
    return nat_col, code_col, sex_col

def _role_label(code: str) -> str:
    c = str(code or "").strip().upper()
    return _ROLE_LABELS.get(c, c or "?")


# ---------- helpers ----------

def _read_csv_any(path: Path) -> pd.DataFrame:
    """Próbuje różne kodowania i auto-separator; w ostateczności średnik."""
    last = None
    for enc in ("utf-8-sig", "utf-8", "cp1250"):
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc)
        except Exception as e:
            last = e
    try:
        return pd.read_csv(path, sep=";", encoding="utf-8")
    except Exception:
        raise RuntimeError(f"Nie mogę wczytać CSV: {path}\n{last}")

def _auto_primary_name_col(cols) -> Optional[str]:
    """Szuka rozsądnej kolumny „nazwiska/imienia” do podglądu obok flagi (opcjonalnie)."""
    preferred = ["Osoba", "Imię i nazwisko", "Nazwisko", "Imię", "Trener", "Funkcja", "Name", "Coach"]
    low = {c.lower(): c for c in cols}
    for p in preferred:
        if p.lower() in low:
            return low[p.lower()]
    # jeśli nic nie pasuje, użyj pierwszej nie‑krajowej kolumny
    for c in cols:
        if str(c).strip().lower() not in ("kraj", "nat"):
            return c
    return None

def _is_numeric_dtype(s: pd.Series) -> bool:
    try:
        import numpy as _np
        return s.dtype.kind in "if" or _np.issubdtype(s.dtype, _np.number)
    except Exception:
        return False

@dataclass
class _TabState:
    frame: ttk.Frame
    tv: ttk.Treeview
    vsb: ttk.Scrollbar
    hsb: ttk.Scrollbar
    df: pd.DataFrame
    images: list  # przechowuje referencje do flag

# ---------- core GUI ----------

class StaffFrame(ttk.Frame):
    def __init__(self, parent, flags_dir: Path | str = FLAGS_DIR):
        super().__init__(parent)
        self.flags_dir = Path(flags_dir)
        self.men_var = tk.StringVar(value="S51/Sztab M S51.csv")
        self.women_var = tk.StringVar(value="S51/Sztab W S51.csv")
        self.season_var = tk.StringVar(value="S51") 
        self._flag_cache = {}
        self._build()

    # ---- flags ----
    def _get_flag(self, code: Optional[str]) -> Optional[tk.PhotoImage]:
        if not code:
            return None
        key = str(code).strip().lower()
        if not key:
            return None
        if key in self._flag_cache:
            return self._flag_cache[key]
        # spróbuj png/gif
        candidates = [self.flags_dir / f"{key}.png", self.flags_dir / f"{key}.gif"]
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

    # ---- UI build ----
    def _build(self):
        # Pasek narzędzi
        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=8, pady=(8,4))
        ttk.Label(bar, text="MEN:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.men_var, width=42).pack(side=tk.LEFT, padx=(4,4))
        ttk.Button(bar, text="…", command=self._pick_men).pack(side=tk.LEFT)
        ttk.Button(bar, text="Wczytaj MEN", command=lambda: self._reload_tab("MEN")).pack(side=tk.LEFT, padx=(6,16))

        ttk.Label(bar, text="WOMEN:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.women_var, width=42).pack(side=tk.LEFT, padx=(4,4))
        ttk.Button(bar, text="…", command=self._pick_women).pack(side=tk.LEFT)
        ttk.Button(bar, text="Wczytaj WOMEN", command=lambda: self._reload_tab("WOMEN")).pack(side=tk.LEFT, padx=(6,0))

        gen_bar = ttk.LabelFrame(bar, text="Generator")
        gen_bar.pack(side=tk.RIGHT, padx=10)
        ttk.Label(gen_bar, text="Nowy Sezon:").pack(side=tk.LEFT, padx=2)
        ttk.Entry(gen_bar, textvariable=self.season_var, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(gen_bar, text="LOSUJ", command=self._run_generator).pack(side=tk.LEFT, padx=5)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)



        self._tabs: dict[str, _TabState] = {}
        for tag in ("MEN", "WOMEN", "Losowanie MEN", "Losowanie WOMEN"):
            page = ttk.Frame(self.nb)
            self.nb.add(page, text=tag)
            tv = ttk.Treeview(page, show="tree headings", height=22, selectmode="browse")
            vsb = ttk.Scrollbar(page, orient="vertical", command=tv.yview)
            hsb = ttk.Scrollbar(page, orient="horizontal", command=tv.xview)
            tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tv.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            page.grid_rowconfigure(0, weight=1); page.grid_columnconfigure(0, weight=1)
            st = _TabState(page, tv, vsb, hsb, pd.DataFrame(), [])
            self._tabs[tag] = st
        
        self._role_tab_ids: list[ttk.Frame] = []

        # załaduj startowo (jeśli pliki istnieją)
        self._reload_tab("MEN", initial=True)
        self._reload_tab("WOMEN", initial=True)

        # NOWE: zbuduj zakładki rola/płeć
        self._rebuild_role_tabs()
        self._rebuild_costs_tab()
    
    def _rebuild_role_tabs(self):
        """Tworzy/odświeża karty per (Rola, Sex) W TYM SAMYM notebooku co MEN/WOMEN."""
        import pandas as pd

        # 0) Usuń poprzednie karty ról z self.nb
        if hasattr(self, "_role_tab_ids") and self._role_tab_ids:
            for frm in self._role_tab_ids:
                try:
                    self.nb.forget(frm)
                    frm.destroy()
                except Exception:
                    pass
            self._role_tab_ids.clear()
        else:
            self._role_tab_ids = []

        # 1) Wczytaj oba pliki, dołóż kolumnę Sex (M/W) i __Code__
        dfs = []
        for tag, path_str in (("M", self.men_var.get()), ("W", self.women_var.get())):
            p = Path(path_str)
            if p.exists():
                try:
                    d = _read_csv_any(p).copy()
                    _, code_col, sex_col = _canon_cols(d)
                    if sex_col is None:
                        d["Sex"] = tag
                    else:
                        d["Sex"] = (d[sex_col].astype(str)
                                    .str.strip().str.upper().str[:1]
                                    .map(lambda x: "W" if x == "F" else x).fillna(tag))
                    if code_col is not None:
                        d["__Code__"] = d[code_col].astype(str).str.strip().str.upper()
                        dfs.append(d)
                except Exception:
                    continue

        if not dfs:
            return

        all_df = pd.concat(dfs, ignore_index=True)
        if "__Code__" not in all_df.columns or "Sex" not in all_df.columns:
            return

        role_list = sorted(
            x for x in all_df["__Code__"].dropna().astype(str).str.strip().str.upper().unique() if x
        )

        # 2) Helper do tworzenia jednej karty
        def _make_role_tab(role_code: str, sex_tag: str):
            page = ttk.Frame(self.nb)
            label = f"{_role_label(role_code)} {sex_tag}"
            self.nb.add(page, text=label)

            tv = ttk.Treeview(page, show="tree headings", height=20, selectmode="browse")
            vsb = ttk.Scrollbar(page, orient="vertical", command=tv.yview)
            hsb = ttk.Scrollbar(page, orient="horizontal", command=tv.xview)
            tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            tv.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            page.grid_rowconfigure(0, weight=1)
            page.grid_columnconfigure(0, weight=1)

            st = _TabState(page, tv, vsb, hsb, pd.DataFrame(), [])
            df_sub = all_df[
                (all_df["__Code__"] == role_code)
                & (all_df["Sex"].astype(str).str.upper().str[:1] == sex_tag)
            ]
            st.df = df_sub.copy()

            # zapamiętaj, żeby móc usunąć przy kolejnym przebudowaniu
            self._role_tab_ids.append(page)

            # opcjonalnie: mapa stanu (nie jest konieczna, ale spójna z resztą kodu)
            if not hasattr(self, "_role_tabs"):
                self._role_tabs = {}
            self._role_tabs[(role_code, sex_tag)] = st

            self._fill_tree(st)

        # 3) Dodaj karty: po WOMEN pojawią się „Lekarz M”, „Fizjo W”, itd.
        for rc in role_list:
            for sx in ("M", "W"):
                _make_role_tab(rc, sx)

    def _rebuild_costs_tab(self):
        """Tworzy/odświeża kartę 'Koszty' z kolumnami:
           NAT, Suma, <Rola> M, <Rola> W (np. Fizjo M, Lekarz W, ...).
           Źródło: Sztab M/W S51, kolumna 'Money' (case-insensitive).
        """
        import pandas as pd

        # 1) Wczytaj MEN/WOMEN z rozpoznaniem podstawowych kolumn
        def _load_one(path_str: str, sex_tag: str) -> pd.DataFrame:
            p = Path(path_str)
            if not p.exists():
                return pd.DataFrame()
            try:
                df = _read_csv_any(p).copy()
            except Exception:
                return pd.DataFrame()

            nat_col = next((c for c in df.columns if str(c).strip().lower() in ["kraj", "nat", "nation"]), None)
            code_col = next((c for c in df.columns if str(c).strip().lower() in ["code", "kod", "rola", "role"]), None)
            money_col = next((c for c in df.columns if "money" in str(c).strip().lower()), None)
            if not (nat_col and code_col and money_col):
                return pd.DataFrame()

            out = df[[nat_col, code_col, money_col]].copy()
            out.columns = ["NAT", "Code", "Money"]
            out["NAT"] = out["NAT"].astype(str).str.upper().str.strip()
            out["Code"] = out["Code"].astype(str).str.strip()
            out["Sex"]  = sex_tag

            # usuń spacje tysięcy i zamień przecinki na kropki, jeśli są
            out["Money"] = (out["Money"].astype(str)
                            .str.replace(" ", "", regex=False)
                            .str.replace(",", ".", regex=False))
            out["Money"] = pd.to_numeric(out["Money"], errors="coerce").fillna(0.0)
            return out

        df_m = _load_one(self.men_var.get(), "M")
        df_w = _load_one(self.women_var.get(), "W")
        if df_m.empty and df_w.empty:
            # jeśli karta już istnieje, wyczyść ją
            try:
                self._set_empty(self._costs_tab_state)
            except Exception:
                pass
            return

        all_df = pd.concat([df_m, df_w], ignore_index=True)

        def _canon_role(val: str) -> str:
            s = str(val or "").strip().upper()
            if s in {"F", "FIZJO", "FIZJOTERAPEUTA"}:
                return "Fizjo"
            if s in {"L", "LEK", "LEKARZ", "DOCTOR", "DR"}:
                return "Lekarz"
            if s in {"TS", "TRENER SENIORÓW", "HEAD COACH"}:
                return "Trener Seniorów"
            if s in {"TJ", "TRENER JUNIORÓW", "JUNIOR COACH"}:
                return "Trener Juniorów"
            if s in {"S", "SKAUT", "SCOUT"}:
                return "Skaut"
            return s.title()

        all_df["RolePretty"] = all_df["Code"].map(_canon_role)


        # suma per NAT per rola/płeć
        piv = (all_df
               .groupby(["NAT", "RolePretty", "Sex"], as_index=False)["Money"]
               .sum())

        # rozlej na kolumny "<Rola> <Sex>"
        piv["Col"] = piv["RolePretty"].astype(str) + " " + piv["Sex"].astype(str)
        wide = piv.pivot_table(index="NAT", columns="Col", values="Money", aggfunc="sum").fillna(0.0)

        # kolumna 'Suma' (łączna)
        wide["Suma"] = wide.sum(axis=1)

        # porządek kolumn: NAT, Suma, [Fizjo M, Lekarz M, Trener Seniorów M, Trener Juniorów M, Skaut M, ... W]
        # Zbuduj listę ról ze słownika, żeby zachować sensowną kolejność
        roles = ["Fizjo", "Lekarz", "Trener Seniorów", "Trener Juniorów", "Skaut"]
        cols_m = [f"{r} M" for r in roles if f"{r} M" in wide.columns]
        cols_w = [f"{r} W" for r in roles if f"{r} W" in wide.columns]
        known = set(["Suma"] + cols_m + cols_w)
        extra = [c for c in wide.columns if c not in known]
        ordered_cols = ["Suma"] + cols_m + cols_w + extra

        out_df = wide[ordered_cols].reset_index()

        # 3) Zaokrąglenia do 2 miejsc (ale trzymaj jako liczby, żeby sort działał)
        num_cols = [c for c in out_df.columns if c != "NAT"]
        out_df[num_cols] = out_df[num_cols].apply(lambda s: pd.to_numeric(s, errors="coerce").fillna(0.0).round(2))

        # 4) Wstaw/odśwież kartę w notebooku
        # jeśli karta już istniała: odśwież; w przeciwnym razie – stwórz
        if not hasattr(self, "_costs_tab"):
            self._costs_tab = ttk.Frame(self.nb)
            self.nb.add(self._costs_tab, text="Koszty")

            tv = ttk.Treeview(self._costs_tab, show="tree headings", height=22, selectmode="browse")
            vsb = ttk.Scrollbar(self._costs_tab, orient="vertical", command=tv.yview)
            hsb = ttk.Scrollbar(self._costs_tab, orient="horizontal", command=tv.xview)
            tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tv.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            self._costs_tab.rowconfigure(0, weight=1)
            self._costs_tab.columnconfigure(0, weight=1)

            self._costs_tab_state = _TabState(self._costs_tab, tv, vsb, hsb, pd.DataFrame(), [])
        # zaktualizuj dane i narysuj
                # 5) Formatowanie kwot do czytelnej formy z odstępami co 3 cyfry
        def _fmt_num(val):
            try:
                v = float(val)
                return f"{v:,.0f}".replace(",", " ")
            except Exception:
                return val

        out_df_fmt = out_df.copy()
        for c in out_df_fmt.columns:
            if c != "NAT":
                out_df_fmt[c] = out_df_fmt[c].apply(_fmt_num)

        self._costs_tab_state.df = out_df_fmt
        self._fill_tree(self._costs_tab_state)

    def _pick_men(self):
        p = filedialog.askopenfilename(
            title="Wybierz plik Sztab MEN (CSV)",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")])
        if p:
            self.men_var.set(p)

    def _pick_women(self):
        p = filedialog.askopenfilename(
            title="Wybierz plik Sztab WOMEN (CSV)",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")])
        if p:
            self.women_var.set(p)

    # ---- data load ----
    def _reload_tab(self, tag: str, initial: bool = False):
        st = self._tabs[tag]
        path = Path(self.men_var.get() if tag == "MEN" else self.women_var.get())
        if not path.exists():
            if not initial:
                messagebox.showerror("Sztab", f"Plik nie istnieje:\n{path}")
            self._set_empty(st)
            return
        try:
            df = _read_csv_any(path)
        except Exception as e:
            messagebox.showerror("Sztab", f"Nie mogę wczytać pliku:\n{path}\n\n{e}")
            self._set_empty(st)
            return
        st.df = df
        self._fill_tree(st)
        try:
            self._rebuild_role_tabs()
        except Exception:
            pass
        try:
            self._rebuild_costs_tab()
        except Exception:
            pass

    def _run_generator(self):
        import random, re
        new_season = self.season_var.get().strip().upper()
        if not new_season: return
        
        try:
            num = int(re.search(r'\d+', new_season).group())
            prev_season = f"S{num-1}"
        except:
            messagebox.showerror("Błąd", "Format sezonu to np. S51")
            return

        for sex_tag, sex_full in [("M", "MEN"), ("W", "WOMEN")]:
            rank_file = Path(prev_season) / f"Ranking FIS {sex_tag} {prev_season}.csv"
            if not rank_file.exists():
                messagebox.showwarning("Pominięto", f"Brak pliku: {rank_file}")
                continue

            df_rank = _read_csv_any(rank_file)
            new_rows = []
            roles = [("TS","Trener Seniorów"), ("TJ","Trener Juniorów"), ("F","Fizjoterapeuta"), ("L","Lekarz"), ("S","Skaut")]

            for _, row in df_rank.iterrows():
                nat = str(row.get("NAT", "")).strip()
                stars = int(row.get("*", 0))
                if not nat or stars == 0: continue

                for code, name_pref in roles:
                    pool = PROBABILITY_TABLE.get(stars, {50: 1})
                    drawn_um = random.choices(list(pool.keys()), weights=list(pool.values()), k=1)[0]
                    new_rows.append({
                        "Name": f"{name_pref} {sex_tag}",
                        "Code": code, "Sex": sex_tag, "NAT": nat,
                        "UM": drawn_um, "Money": f"{drawn_um * 1000:,}".replace(",", " ")
                    })

            out_df = pd.DataFrame(new_rows)
            out_path = Path(new_season) / f"Sztab {sex_tag} {new_season}.csv"
            out_path.parent.mkdir(exist_ok=True)
            out_df.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig")
            
            tab_tag = f"Losowanie {sex_full}"
            self._tabs[tab_tag].df = out_df
            self._fill_tree(self._tabs[tab_tag])

        messagebox.showinfo("Sukces", f"Wylosowano sztaby dla {new_season}")

    def _set_empty(self, st: _TabState):
        st.df = pd.DataFrame()
        self._fill_tree(st)

    # ---- tree render ----
    def _fill_tree(self, st: _TabState):
        tv = st.tv
        # wyczyść
        for iid in tv.get_children(""):
            tv.delete(iid)
        tv["columns"] = ()

        df = st.df if isinstance(st.df, pd.DataFrame) else pd.DataFrame()
        if df is None or df.empty:
            tv.heading("#0", text="")
            tv.column("#0", width=24, stretch=False, anchor="center")
            return

        # Rozpoznaj kolumny krajowe i „główną” do wyświetlenia obok flagi
        cols = list(df.columns)
        code_col = None
        for c in cols:
            if str(c).strip().lower() in ("kraj", "nat"):
                code_col = c; break
        primary = _auto_primary_name_col(cols)

        # #0 — mała kolumna na flagi (gdy jest kraj), inaczej pusta
        if code_col:
            tv.heading("#0", text="")
            tv.column("#0", width=38, minwidth=38, stretch=False, anchor="center")
        else:
            tv.heading("#0", text=primary or "")
            tv.column("#0", width=180, stretch=True, anchor="w")

        # kolumny „headings” — wszystkie kolumny danych
        tv["columns"] = cols
        for c in cols:
            tv.heading(c, text=str(c), command=lambda cc=c: self._sort_by(st, cc, False))
            # szerokości
            try:
                maxlen = int(df[c].astype(str).map(len).max())
            except Exception:
                maxlen = 10
            width = max(60, min(260, int(maxlen * 8.2)))
            anchor = tk.E if _is_numeric_dtype(df[c]) else tk.W
            tv.column(c, width=width, stretch=False, anchor=anchor)

        # dane + flagi
        st.images = []
        for _, row in df.iterrows():
            # label w #0
            label = ""
            if primary and primary in df.columns:
                v = row.get(primary, "")
                label = "" if code_col else str(v)
            # flaga
            img = None
            if code_col:
                code = str(row.get(code_col, "")).strip()
                if code:
                    img = self._get_flag(code)
            if img is not None:
                st.images.append(img)
                iid = tv.insert("", "end", text=label, image=img, values=[row.get(c, "") for c in cols])
            else:
                iid = tv.insert("", "end", text=label, values=[row.get(c, "") for c in cols])

        # poziomy pasek działa tylko dla „columns”
        st.hsb.configure(command=tv.xview)
        tv.configure(xscrollcommand=st.hsb.set)

    # ---- sorting ----
    def _sort_by(self, st: _TabState, col: str, descending: bool):
        tv = st.tv
        df = st.df if isinstance(st.df, pd.DataFrame) else pd.DataFrame()
        
        if df is None or df.empty or col not in df.columns:
            return

        try:
            sorted_df = df.copy()
            
            # NOWA LOGIKA: Bezpieczna konwersja na liczby
            # errors='coerce' zamieni nieliczbowe wartości na NaN
            numeric_vals = pd.to_numeric(sorted_df[col], errors='coerce')
            
            # Jeśli kolumna faktycznie zawiera liczby (nie wszystkie są NaN), 
            # używamy wersji numerycznej do sortowania
            if not numeric_vals.isna().all():
                sorted_df[col] = numeric_vals
            
            sorted_df = sorted_df.sort_values(col, ascending=not descending, kind="mergesort")
            
        except Exception:
            # Rezerwowy sposób: sortowanie jako tekst (jeśli konwersja numeryczna zawiedzie)
            sorted_df = df.copy()
            sorted_df[col] = sorted_df[col].astype(str)
            sorted_df = sorted_df.sort_values(col, ascending=not descending, kind="mergesort")

        st.df = sorted_df.reset_index(drop=True)
        self._fill_tree(st)
        
        # Ustawienie nagłówka na kolejny klik (odwrócenie sortowania)
        tv.heading(col, command=lambda c=col: self._sort_by(st, c, not descending))

# ---------- public API ----------

def build_gui(parent) -> StaffFrame:
    return StaffFrame(parent)


# ---------- standalone ----------

class _App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sztab – GUI")
        try:
            self.state("zoomed")
        except Exception:
            self.geometry("1200x800")
        frm = StaffFrame(self)
        frm.pack(fill=tk.BOTH, expand=True)

if __name__ == "__main__":
    _App().mainloop()
