#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ranking_fis_gui_embedded.py — Ranking FIS (MEN / WOMEN / ALL + tabela punktów)

Wejście:
- Folder z klasyfikacjami generalnymi w CSV, w stylu:
    <TAG>__players.csv   (np. WC-M__players.csv, COC-W__players.csv)
    <TAG>__nations.csv   (opcjonalnie, do wyciągnięcia pełnej nazwy kraju)
  Dopuszczalne nazwy z prefiksem sezonu: S51_<TAG>__players.csv itd.

TAG-i używane tutaj:
- MEN:   WC-M, GP-M, COC-M, FC-M, SCOC-M, JC-M, MC-M, PC-M, QC-M, TC-M, AC-M, BC-M, DC-M
- WOMEN: WC-W, GP-W, COC-W, FC-W, SCOC-W, JC-W, MC-W, PC-W, QC-W, TC-W, AC-W, BC-W, DC-W

Logika:
- [I]: za miejsca 1–10 wg tabeli CUP (WC-M/WC-W/GP-M/...).
- [T]: suma PTS z klasyfikacji generalnej dla zawodników danego kraju,
       podzielona przez dzielnik zależny od cyklu:
         WC /2, GP /3, COC /5, FC /7, SCOC /9,
         JC /10, MC /12, PC /14, QC /16, TC /18,
         AC /20, BC /22, DC /24.
- SUMA = suma wszystkich kolumn [T] + [I] + ewentualnych specjalnych (na razie CC/NTC/MSC... = 0).

Zakładki:
- MEN
- WOMEN
- ALL  (Lp., *, Kraj, NAT, Suma, MEN, WOMEN)
- Punkty (sztywna tabelka z CUP 1–10)

Entry point do combined:
    from ranking_fis_gui_embedded import build_gui
    frame = build_gui(parent)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pandas as pd

# Spróbuj flag, jak wszędzie
try:
    from flags_cache import FLAG_CACHE
except Exception:
    FLAG_CACHE = None

ALL_NATIONS_PATH = Path("ALL_NATIONS.csv")
MASTER_PLAYERS_DB = Path("S51/Zawodnicy S51gpt.csv")

__all__ = ["build_gui", "RankingFISFrame"]

# ------------------ KONFIG: CUP → punkty za miejsca 1–10 ------------------ #

# słownik: CUP -> {place: points}
CUP_POINTS: Dict[str, Dict[int, float]] = {
    "WC-M":  {1:500, 2:400, 3:300, 4:200, 5:100, 6:75, 7:50, 8:25, 9:10, 10:5},
    "WC-W":  {1:500, 2:400, 3:300, 4:200, 5:100, 6:75, 7:50, 8:25, 9:10, 10:5},
    "GP-M":  {1:400, 2:250, 3:150, 4:100, 5:50},
    "GP-W":  {1:400, 2:250, 3:150, 4:100, 5:50},
    "COC-M": {1:300, 2:200, 3:150, 4:100, 5:50},
    "COC-W": {1:300, 2:200, 3:150, 4:100, 5:50},
    "FC-M":  {1:200, 2:125, 3:75, 4:50, 5:25},
    "FC-W":  {1:200, 2:125, 3:75, 4:50, 5:25},
    "SCOC-M":{1:200, 2:125, 3:75, 4:50, 5:25},
    "SCOC-W":{1:200, 2:125, 3:75, 4:50, 5:25},
    "JC-M":  {1:100, 2:80, 3:60},
    "JC-W":  {1:100, 2:80, 3:60},
    "MC-M":  {1:80,  2:60, 3:40},
    "MC-W":  {1:80,  2:60, 3:40},
    "PC-M":  {1:60,  2:40, 3:30},
    "PC-W":  {1:60,  2:40, 3:30},
    "QC-M":  {1:50,  2:35, 3:25},
    "QC-W":  {1:50,  2:35, 3:25},
    "TC-M":  {1:40,  2:30, 3:20},
    "TC-W":  {1:40,  2:30, 3:20},
    "AC-M":  {1:35,  2:25, 3:15},
    "AC-W":  {1:35,  2:25, 3:15},
    "BC-M":  {1:30,  2:20, 3:10},
    "BC-W":  {1:30,  2:20, 3:10},
    "DC-M":  {1:25,  2:15, 3:7.5},
    "DC-W":  {1:25,  2:15, 3:7.5},
    
    # --- NOWE IMPREZY DODATKOWE ---
    "OG-M":   {1:750, 2:600, 3:500, 4:400, 5:300, 6:200, 7:100, 8:75, 9:50, 10:25},
    "OG-W":   {1:750, 2:600, 3:500, 4:400, 5:300, 6:200, 7:100, 8:75, 9:50, 10:25},
    "WCH-M":  {1:600, 2:500, 3:400, 4:300, 5:200, 6:100, 7:75, 8:50, 9:25, 10:10},
    "WCH-W":  {1:600, 2:500, 3:400, 4:300, 5:200, 6:100, 7:75, 8:50, 9:25, 10:10},
    "SFWC-M": {1:500, 2:400, 3:300, 4:200, 5:100, 6:75, 7:50, 8:25, 9:10, 10:5},
    "SFWC-W": {1:500, 2:400, 3:300, 4:200, 5:100, 6:75, 7:50, 8:25, 9:10, 10:5},
    "JWC-M":  {1:400, 2:300, 3:200, 4:100, 5:80, 6:60, 7:40, 8:20, 9:10, 10:5},
    "JWC-W":  {1:400, 2:300, 3:200, 4:100, 5:80, 6:60, 7:40, 8:20, 9:10, 10:5},
    "UNI-M":  {1:300, 2:200, 3:125, 4:80, 5:60, 6:40, 7:30, 8:15, 9:10, 10:5},
    "UNI-W":  {1:300, 2:200, 3:125, 4:80, 5:60, 6:40, 7:30, 8:15, 9:10, 10:5},
    "YOG-M":  {1:200, 2:150, 3:100, 4:70, 5:50, 6:30, 7:20, 8:10, 9:5, 10:3},
    "YOG-W":  {1:200, 2:150, 3:100, 4:70, 5:50, 6:30, 7:20, 8:10, 9:5, 10:3},
    "COCH-M": {1:500, 2:400, 3:300, 4:200, 5:100, 6:75, 7:50, 8:25, 9:10, 10:5},
    "COCH-W": {1:500, 2:400, 3:300, 4:200, 5:100, 6:75, 7:50, 8:25, 9:10, 10:5},
    "NKIC-M": {1:600, 2:500, 3:400, 4:300, 5:200, 6:100, 7:75, 8:50, 9:25, 10:10},
    "NKIC-W": {1:600, 2:500, 3:400, 4:300, 5:200, 6:100, 7:75, 8:50, 9:25, 10:10},
    "IST-M":  {1:400, 2:300, 3:200, 4:100, 5:80, 6:60, 7:40, 8:20, 9:10, 10:5},
    "IST-W":  {1:400, 2:300, 3:200, 4:100, 5:80, 6:60, 7:40, 8:20, 9:10, 10:5},
    
    # Specjalne tury (bez zmian)
    "TCS":       {1:100, 2:75, 3:50},
    "PLANICA7":  {1:100, 2:75, 3:50},
    "WILL5":     {1:100, 2:75, 3:50},
    "RAWAIR_M":  {1:100, 2:75, 3:50},
    "NT":        {1:100, 2:75, 3:50},
    "FT":        {1:100, 2:75, 3:50},
    "RAWAIR_W":  {1:100, 2:75, 3:50},
    "BB":        {1:100, 2:75, 3:50},
    "CC":        {1:500, 2:400, 3:300, 4:200, 5:100, 6:75, 7:50, 8:25, 9:10, 10:5},
}

# dzielniki wg cyklu (bazowy TAG bez -M/-W)
DIVISORS = {
    "WC":   2,
    "GP":   3,
    "COC":  5,
    "FC":   7,
    "SCOC": 9,
    "JC":   10,
    "MC":   12,
    "PC":   14,
    "QC":   16,
    "TC":   18,
    "AC":   20,
    "BC":   22,
    "DC":   24,
    # specjalne tury typu TCS/CC nie są tu użyte na razie
}

MEN_TAGS = ["WC-M","GP-M","COC-M","FC-M","SCOC-M","JC-M","MC-M","PC-M","QC-M","TC-M","AC-M","BC-M","DC-M"]
WOMEN_TAGS = ["WC-W","GP-W","COC-W","FC-W","SCOC-W","JC-W","MC-W","PC-W","QC-W","TC-W","AC-W","BC-W","DC-W"]


# ------------------ HELPERY CSV / KLASYFIKACJE ------------------ #

def _load_all_nations_map(path: Path = ALL_NATIONS_PATH) -> Dict[str, str]:
    """
    Czyta ALL_NATIONS.csv (Kraj;NAT) i zwraca mapę NAT -> Kraj.
    Jeśli pliku nie ma, zwraca pusty słownik.
    """
    if not path.is_file():
        return {}

    df = _read_csv_any(path)
    df.columns = _clean_headers(df.columns)

    if "NAT" not in df.columns or "Kraj" not in df.columns:
        return {}

    mapping: Dict[str, str] = {}
    for _, r in df.iterrows():
        nat = str(r.get("NAT", "")).strip().upper()
        name = str(r.get("Kraj", "")).strip()
        if nat and name and nat not in mapping:
            mapping[nat] = name
    return mapping

def _read_csv_any(path: str | Path) -> pd.DataFrame:
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


def _clean_headers(cols):
    return [str(c).strip() for c in cols]

def _players_from_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Wyciąga z CSV tylko niezbędne dane (Miejsce i NAT). 
    Rozwiązuje problem duplikatów nazw kolumn w plikach mistrzowskich.
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=["LP.","JUMPER","NAT","PTS"])
    
    df = df_raw.copy()
    
    # 1. Standaryzacja nazw kolumn na wielkie litery i usunięcie spacji
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # 2. Mapowanie kolumn z priorytetami, aby uniknąć duplikatów
    mapping = {}
    cols_list = list(df.columns)

    def get_first_match(aliases):
        for a in aliases:
            if a in cols_list:
                return cols_list.index(a)
        return None

    # Szukamy miejsca (LP.)
    idx_lp = get_first_match(["LP.", "LP", "MIEJSCE"])
    if idx_lp is not None:
        mapping[df.columns[idx_lp]] = "LP."

    # Szukamy kraju (NAT)
    idx_nat = get_first_match(["NAT", "KRAJ", "CODE"])
    if idx_nat is not None:
        mapping[df.columns[idx_nat]] = "NAT"

    # Szukamy zawodnika (opcjonalnie)
    idx_jumper = get_first_match(["JUMPER", "ZAWODNIK", "NAME"])
    if idx_jumper is not None:
        mapping[df.columns[idx_jumper]] = "JUMPER"

    # Zmieniamy nazwy tylko znalezionym kolumnom
    df = df.rename(columns=mapping)
    
    # 3. Wybieramy tylko to, co potrzebne do obliczeń
    keep = [c for c in ["LP.", "JUMPER", "NAT"] if c in df.columns]
    out = df[keep].copy()
    
    # Usuwamy całkowicie puste wiersze i duplikaty nazw kolumn w wyniku
    out = out.loc[:, ~out.columns.duplicated()]
    out = out.dropna(subset=["LP."])

    # 4. Konwersja miejsca na liczbę (kluczowe dla CUP_POINTS)
    out["LP."] = pd.to_numeric(out["LP."], errors="coerce").fillna(0).astype(int)
    
    if "NAT" in out.columns:
        out["NAT"] = out["NAT"].fillna("").astype(str).str.upper()
        
    return out

def _nations_from_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Wyciąga (NATION, NAT, PTS) z pliku narodów."""
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=["NATION","NAT","PTS"])
    
    df = df_raw.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    cols_list = list(df.columns)
    
    mapping = {}
    def get_first_match(aliases):
        for a in [al.upper() for al in aliases]:
            if a in cols_list: return cols_list.index(a)
        return None

    idx_name = get_first_match(["NATION", "COUNTRY", "REPREZENTACJA", "DRUŻYNA"])
    if idx_name is not None: mapping[df.columns[idx_name]] = "NATION"
    
    idx_nat = get_first_match(["NAT", "CODE", "KRAJ"])
    if idx_nat is not None: mapping[df.columns[idx_nat]] = "NAT"

    idx_pts = get_first_match(["PTS", "PUNKTY FIS", "PUNKTY", "POINTS"])
    if idx_pts is not None: mapping[df.columns[idx_pts]] = "PTS"

    df = df.rename(columns=mapping)
    keep = [c for c in ["NATION", "NAT", "PTS"] if c in df.columns]
    out = df[keep].copy()
    out = out.loc[:, ~out.columns.duplicated()] # Na wypadek gdyby "Kraj" i "NAT" były obok siebie

    if "PTS" in out.columns:
        out["PTS"] = pd.to_numeric(out["PTS"], errors="coerce").fillna(0.0)
    if "NAT" in out.columns:
        out["NAT"] = out["NAT"].fillna("").astype(str).str.upper()

    return out

def _pick_classif_file(root_dir: Path, tag: str, suffix: str = "players") -> Path | None:
    """
    Dynamicznie szuka pliku dla danego TAG-u w folderze root_dir.
    Nie zakłada na sztywno numeru sezonu.
    """
    if not root_dir.exists() or not root_dir.is_dir():
        return None

    # 1. Pobieramy wszystkie pliki .csv z folderu
    try:
        all_files = list(root_dir.glob("*.csv"))
    except Exception:
        return None

    u_tag = tag.upper()
    u_suffix = suffix.upper()

    # 2. Szukamy pliku, który zawiera w nazwie TAG oraz SUFFIX (np. "WC-M" i "PLAYERS")
    # To zadziała dla: "S44_WC-M__players.csv", "WC-M__players.csv", "S51_WC-M__players.csv"
    # WAŻNE: TAG musi być poprzedzony początkiem nazwy lub '_', żeby COC-M nie matchowało SCOC-M.
    def _tag_in_fname(fname: str, tag: str) -> bool:
        """Zwraca True tylko jeśli TAG jest osobnym tokenem (poprzedzony ^ lub _, zakończony _ lub $)."""
        pattern = r'(^|_)' + re.escape(tag) + r'($|_)'
        return bool(re.search(pattern, fname))

    for f in all_files:
        fname = f.name.upper()
        if _tag_in_fname(fname, u_tag) and f"__{u_suffix}" in fname:
            return f

    # 3. Fallback: Szukamy pliku, który zawiera TAG, ale NIE zawiera "__" (stary format lub prosty plik)
    # Zapobiega to pomyleniu pliku "nations" z "players" jeśli szukamy tego drugiego
    for f in all_files:
        fname = f.name.upper()
        if _tag_in_fname(fname, u_tag) and "__" not in fname:
            # Dodatkowe sprawdzenie, żeby nie wziąć np. pliku "WC-M_backup.csv" zamiast "WC-M.csv"
            # Sprawdzamy czy TAG jest otoczony podkreślnikami lub jest na początku/końcu
            clean_name = fname.replace(".CSV", "")
            if u_tag == clean_name or f"_{u_tag}" in clean_name or f"{u_tag}_" in clean_name:
                return f

    return None

def _base_tag(tag: str) -> str:
    """'WC-M' -> 'WC', 'COC-W' -> 'COC'."""
    s = str(tag or "").strip().upper()
    if s.endswith("-M") or s.endswith("-W"):
        return s[:-2]
    return s

def _stars_for_place(place: int, suma: float) -> int:
    """
    Miejsca -> liczba gwiazdek (cyfra w kolumnie '*'):

    1          -> 15
    2-3        -> 14
    4-6        -> 13
    7-10       -> 12
    11-15      -> 11
    16-21      -> 10
    22-28      -> 9
    29-36      -> 8
    37-45      -> 7
    46-54      -> 6
    55-65      -> 5
    66-77      -> 4
    78-90      -> 3
    91+ & suma > 0 -> 2
    91+ & suma < 0 -> 1
    91+ & suma == 0 -> 0
    """
    try:
        p = int(place)
    except Exception:
        return 0
    s = float(suma)

    if p == 1:
        return 15
    elif 2 <= p <= 3:
        return 14
    elif 4 <= p <= 6:
        return 13
    elif 7 <= p <= 10:
        return 12
    elif 11 <= p <= 15:
        return 11
    elif 16 <= p <= 21:
        return 10
    elif 22 <= p <= 28:
        return 9
    elif 29 <= p <= 36:
        return 8
    elif 37 <= p <= 45:
        return 7
    elif 46 <= p <= 54:
        return 6
    elif 55 <= p <= 65:
        return 5
    elif 66 <= p <= 77:
        return 4
    elif 78 <= p <= 90:
        return 3
    else:
        if s > 0:
            return 2
        elif s == 0:
            return 1
        else:
            return 0



# ------------------ LICZENIE RANKINGU ------------------ #

class FISRankingCalculator:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.season_prefix = self._detect_prefix(self.root_dir)
        # Dynamiczny folder mistrzostw obok folderu klasyfikacji
        self.championship_dir = self.root_dir.parent / f"Mistrzostwa {self.season_prefix}"
        
        self._players_cache: Dict[str, pd.DataFrame] = {}
        self._nations_cache: Dict[str, pd.DataFrame] = {}
        self._nat_name_map: Dict[str, str] = {}
        self._all_nations_map: Dict[str, str] = _load_all_nations_map()

    def _detect_prefix(self, path: Path) -> str:
        """Wykrywa prefix S51, S51 itp. z nazwy wybranego folderu lub folderu nadrzędnego."""
        # Szukamy wzorca S + cyfry w nazwie folderu
        match = re.search(r"S\d+", path.name)
        if match: return match.group(0)
        
        # Jeśli nie ma w nazwie folderu, sprawdź folder nadrzędny
        match = re.search(r"S\d+", path.parent.name)
        return match.group(0) if match else "S51" # Fallback tylko w ostateczności

    def _get_points_from_file(self, filename: str, multiplier: float, tag_for_pts: str) -> pd.Series:
        """Pobiera punkty za miejsca z konkretnego pliku CSV."""
        path = self.championship_dir / f"{filename}.csv"
        if not path.is_file():
            path = self.root_dir / f"{filename}.csv" # Fallback
            
        if not path.is_file():
            return pd.Series(dtype=float)

        try:
            df_raw = _read_csv_any(path)
            df = _players_from_df(df_raw)
            if df.empty: return pd.Series(dtype=float)
            
            pts_map = CUP_POINTS.get(tag_for_pts, {})
            
            def row_pts(place: int) -> float:
                return float(pts_map.get(int(place), 0.0)) * multiplier

            df["I_pts"] = df["LP."].map(row_pts)
            # Sumujemy punkty dla każdego kraju (NAT) znalezionego w pliku
            return df.groupby("NAT", dropna=False)["I_pts"].sum()
        except Exception:
            return pd.Series(dtype=float)

    def _calculate_championship_points(self, tag: str) -> pd.Series:
        """Sumuje wyniki ze wszystkich plików danej imprezy (IND, TEAM, MIXED)."""
        p = self.season_prefix
        s = pd.Series(dtype=float)
        
        def add_s(new_s):
            nonlocal s
            if not new_s.empty:
                s = s.add(new_s, fill_value=0.0)

        parts = tag.split("-")
        if len(parts) < 2: return s
        base, sex = parts[0], parts[1]
        
        if base == "OG":
            for suf in ["IND_LARGE", "IND_NORMAL", "TEAM_LARGE", "TEAM_NORMAL"]:
                add_s(self._get_points_from_file(f"{p}_OG_{sex}_{suf}", 1.0, tag))
            for suf in ["TEAM_LARGE", "TEAM_NORMAL"]:
                add_s(self._get_points_from_file(f"{p}_OG_X_{suf}", 0.5, tag))

        elif base == "WCH":
            for suf in ["IND_LARGE", "IND_NORMAL", "TEAM_LARGE", "TEAM_NORMAL"]:
                fname = f"{p}_WCH_{sex}_{suf}"
                res = self._get_points_from_file(fname, 1.0, tag)
                # Obsługa specyficznej literówki ING/IND
                if res.empty and "IND_LARGE" in suf:
                    res = self._get_points_from_file(f"{p}_WCH_{sex}_ING_LARGE", 1.0, tag)
                add_s(res)
            add_s(self._get_points_from_file(f"{p}_WCH_X_TEAM_LARGE", 0.5, tag))
            add_s(self._get_points_from_file(f"{p}_WCH_X_TEAM_NORMAL", 0.5, tag))

        elif base == "SFWC":
            add_s(self._get_points_from_file(f"{p}_SFWC_{sex}_IND", 1.0, tag))
            add_s(self._get_points_from_file(f"{p}_SFWC_{sex}_TEAM", 1.0, tag))
            add_s(self._get_points_from_file(f"{p}_SFWC_X_TEAM", 0.5, tag))

        elif base == "IST":
            add_s(self._get_points_from_file(f"{p}_IST_{sex}_IND_NORMAL", 1.0, tag))
            add_s(self._get_points_from_file(f"{p}_IST_{sex}_IND_LARGE", 1.0, tag))

        elif base == "NKIC":
            add_s(self._get_points_from_file(f"{p}_NKIC_{sex}_IND", 1.0, tag))

        elif base in ["YOG", "JWC", "UNI"]:
            add_s(self._get_points_from_file(f"{p}_{base}_{sex}_IND", 1.0, tag))
            add_s(self._get_points_from_file(f"{p}_{base}_{sex}_TEAM", 1.0, tag))
            add_s(self._get_points_from_file(f"{p}_{base}_X_TEAM", 0.5, tag))

        elif base == "COCH":
            conts = ["EUROPE", "ASIA", "NORTHAMERICA", "SOUTHAMERICA", "AFRICA", "OCEANIA"]
            for c in conts:
                add_s(self._get_points_from_file(f"{p}_COCH_{c}_{sex}_IND", 1.0, tag))
                add_s(self._get_points_from_file(f"{p}_COCH_{c}_{sex}_TEAM", 1.0, tag))
                add_s(self._get_points_from_file(f"{p}_COCH_{c}_X_TEAM", 0.5, tag))

        return s
    
    def _load_players(self, tag: str) -> pd.DataFrame:
        if tag in self._players_cache:
            return self._players_cache[tag]
        path = _pick_classif_file(self.root_dir, tag, "players")
        if not path:
            self._players_cache[tag] = pd.DataFrame(columns=["LP.","JUMPER","NAT","PTS"])
            return self._players_cache[tag]
        try:
            df_raw = _read_csv_any(path)
            df = _players_from_df(df_raw)
        except Exception:
            df = pd.DataFrame(columns=["LP.","JUMPER","NAT","PTS"])
        self._players_cache[tag] = df
        return df

    def _load_nations(self, tag: str) -> pd.DataFrame:
        if tag in self._nations_cache:
            return self._nations_cache[tag]
        path = _pick_classif_file(self.root_dir, tag, "nations")
        if not path:
            self._nations_cache[tag] = pd.DataFrame(columns=["NATION","NAT"])
            return self._nations_cache[tag]
        try:
            df_raw = _read_csv_any(path)
            df = _nations_from_df(df_raw)
        except Exception:
            df = pd.DataFrame(columns=["NATION","NAT"])
        self._nations_cache[tag] = df
        return df

    def build_nat_name_map(self, tags) -> Dict[str, str]:
        """NAT -> Kraj. Najpierw ALL_NATIONS.csv, potem ewentualne nazwy z __nations.csv."""
        # start z pełnej listy krajów
        mp: Dict[str, str] = dict(self._all_nations_map)

        # uzupełnij / nadpisz z plików TAG__nations.csv
        for tag in tags:
            nat_df = self._load_nations(tag)
            if nat_df.empty:
                continue
            for _, r in nat_df.iterrows():
                nat = str(r.get("NAT", "")).strip().upper()
                name = str(r.get("NATION", "")).strip()
                if nat and name:
                    if nat not in mp:
                        mp[nat] = name

        self._nat_name_map = mp
        return mp

    def _load_master_db(self) -> pd.DataFrame | None:
        """Wczytuje główną bazę zawodników (Zawodnicy S51gpt.csv)."""
        if hasattr(self, "_master_db"):
            return self._master_db

        if not MASTER_PLAYERS_DB.is_file():
            self._master_db = None
            return self._master_db

        try:
            df = _read_csv_any(MASTER_PLAYERS_DB)
            df.columns = _clean_headers(df.columns)
            mapping = {}
            for c in df.columns:
                u = c.upper()
                if u in ("KRAJ","NAT","CODE"):
                    mapping[c] = "NAT"
                elif u in ("PŁEĆ","PLEC","SEX"):
                    mapping[c] = "SEX"
                elif u in ("WIEK","AGE"):
                    mapping[c] = "AGE"
            if mapping:
                df = df.rename(columns=mapping)

            # normalizacja
            if "NAT" in df.columns:
                df["NAT"] = df["NAT"].fillna("").astype(str).str.upper()
            if "SEX" in df.columns:
                df["SEX"] = df["SEX"].fillna("").astype(str).str.upper()
            if "AGE" in df.columns:
                df["AGE"] = pd.to_numeric(df["AGE"], errors="coerce")

            self._master_db = df
        except Exception:
            self._master_db = None

        return self._master_db

    def _senior_points_from_db(self, sex: str, min_age: int = 15) -> pd.Series:
        """
        NAT -> 20, jeśli w bazie Zawodnicy S51gpt.csv jest przynajmniej jeden zawodnik
        danego kraju o zadanej płci i wieku >= min_age.
        sex: 'M' dla MEN, 'W' dla WOMEN.
        """
        db = self._load_master_db()
        if db is None or db.empty:
            return pd.Series(dtype=float)

        # spróbuj rozpoznać kolumny po nazwach, niezależnie od tego czy były mapowane
        cols_up = {c.upper(): c for c in db.columns}

        nat_col = cols_up.get("NAT") or cols_up.get("KRAJ") or cols_up.get("CODE")
        sex_col = cols_up.get("SEX") or cols_up.get("PŁEĆ") or cols_up.get("PLEC")
        age_col = cols_up.get("AGE") or cols_up.get("WIEK")

        if not nat_col or not sex_col or not age_col:
            return pd.Series(dtype=float)

        sex = (sex or "").upper().strip()
        if sex not in ("M", "W"):
            return pd.Series(dtype=float)

        tmp = db.copy()

        # normalizacja
        tmp[sex_col] = tmp[sex_col].fillna("").astype(str).str.upper()
        tmp[nat_col] = tmp[nat_col].fillna("").astype(str).str.upper()
        tmp[age_col] = pd.to_numeric(tmp[age_col], errors="coerce")

        tmp = tmp[tmp[sex_col] == sex]
        tmp = tmp[tmp[age_col] >= float(min_age)]

        if tmp.empty:
            return pd.Series(dtype=float)

        nats = (
            tmp[nat_col]
            .dropna()
            .astype(str)
            .str.upper()
            .unique()
            .tolist()
        )
        return pd.Series({nat: 20.0 for nat in nats})

    def _points_I_for_tag(self, tag: str) -> pd.Series:
        """
        NAT -> suma punktów za miejsca wg CUP_POINTS[tag] (LP. == miejsce).
        """
        if tag not in CUP_POINTS:
            return pd.Series(dtype=float)
        pts_map = CUP_POINTS[tag]
        df = self._load_players(tag)
        if df.empty:
            return pd.Series(dtype=float)

        def row_pts(place: int) -> float:
            try:
                p = int(place)
            except Exception:
                return 0.0
            return float(pts_map.get(p, 0.0))

        tmp = df.copy()
        if "LP." not in tmp.columns or "NAT" not in tmp.columns:
            return pd.Series(dtype=float)
        tmp["I_pts"] = tmp["LP."].map(row_pts)
        out = tmp.groupby("NAT", dropna=False)["I_pts"].sum()
        return out

    def _points_T_for_tag(self, tag: str) -> pd.Series:
        """
        [T] - Punkty drużynowe.
        Pobiera sumę punktów (z pliku narodów lub od zawodników) i dzieli przez dzielnik cyklu.
        """
        # 1. Określenie dzielnika dla danego cyklu
        dividers = {
            "WC": 2, "GP": 3, "COC": 5, "FC": 7, "SCOC": 9,
            "JC": 10, "MC": 12, "PC": 14, "QC": 16, "TC": 18,
            "AC": 20, "BC": 22, "DC": 24
        }
        base = _base_tag(tag)
        div = float(dividers.get(base, 1.0))

        # 2. Próba pobrania danych z pliku narodów (__nations.csv)
        path_nations = _pick_classif_file(self.root_dir, tag, "nations")
        s = pd.Series(dtype=float)

        if path_nations and path_nations.is_file():
            try:
                df_raw = _read_csv_any(path_nations)
                df_n = _nations_from_df(df_raw) # Wykorzystuje poprawioną wersję z poprzedniego kroku
                if not df_n.empty and "PTS" in df_n.columns:
                    s = df_n.groupby("NAT")["PTS"].sum()
            except Exception:
                s = pd.Series(dtype=float)

        # 3. Jeśli plik narodów był pusty lub go nie było, bierzemy punkty od zawodników
        if s.empty:
            df_p = self._load_players(tag)
            if not df_p.empty and "PTS" in df_p.columns and "NAT" in df_p.columns:
                s = df_p.groupby("NAT")["PTS"].sum()

        # 4. Zwracamy punkty podzielone przez dzielnik
        return s / div

    def build_table_for_tags(self, tags, extra_cols: Tuple[str,...]) -> pd.DataFrame:
        data_T: Dict[Tuple[str,str], float] = {}
        data_I: Dict[Tuple[str,str], float] = {}
        all_nats = set()

        # Definicja turniejów do doliczenia do WC
        men_tours = ["TCS", "PLANICA7", "WILL5", "RAWAIR_M", "NT", "FT"]
        women_tours = ["RAWAIR_W", "BB"]

        # 1. Zbieranie standardowych punktów
        for tag in tags:
            sI = self._points_I_for_tag(tag)
            sT = self._points_T_for_tag(tag)
            for nat, val in sI.items():
                all_nats.add(nat)
                data_I[(nat, tag)] = float(val)
            for nat, val in sT.items():
                all_nats.add(nat)
                data_T[(nat, tag)] = float(val)

        # 2. DODAWANIE TURNIEJÓW DO WC-M [I]
        if "WC-M" in tags:
            for tour in men_tours:
                tour_pts = self._points_I_for_tag(tour)
                for nat, val in tour_pts.items():
                    all_nats.add(nat)
                    obecne = data_I.get((nat, "WC-M"), 0.0)
                    data_I[(nat, "WC-M")] = obecne + float(val)

        # 3. DODAWANIE TURNIEJÓW DO WC-W [I]
        if "WC-W" in tags:
            for tour in women_tours:
                tour_pts = self._points_I_for_tag(tour)
                for nat, val in tour_pts.items():
                    all_nats.add(nat)
                    obecne = data_I.get((nat, "WC-W"), 0.0)
                    data_I[(nat, "WC-W")] = obecne + float(val)

        # NAT-y z klasyfikacji
        all_nats = {str(n or "").strip().upper() for n in all_nats if str(n or "").strip()}

        # + NAT-y z ALL_NATIONS.csv (jeśli masz tę logikę)
        if self._all_nations_map:
            all_nats |= set(self._all_nations_map.keys())

        # MEN vs WOMEN -> płeć do sprawdzenia w bazie zawodników
        tags_up = [str(t).upper() for t in tags]
        sex_for_senior = None
        if tags_up and all(t.endswith("-M") for t in tags_up):
            sex_for_senior = "M"
        elif tags_up and all(t.endswith("-W") for t in tags_up):
            sex_for_senior = "W"

        if sex_for_senior:
            senior_series = self._senior_points_from_db(sex_for_senior)
        else:
            senior_series = pd.Series(dtype=float)

        # mapa NAT -> nazwa kraju
        nat_name = self.build_nat_name_map(tags)

        rows = []
        for nat in sorted(all_nats):
            row = {
                "NAT": nat,
                "Kraj": nat_name.get(nat, nat),
                "*": "",
            }
            suma = 0.0
            for tag in tags:
                colT = f"{tag} [T]"
                colI = f"{tag} [I]"
                vT = float(data_T.get((nat, tag), 0.0))
                vI = float(data_I.get((nat, tag), 0.0))
                row[colT] = vT
                row[colI] = vI
                suma += vT + vI

            # dodatkowe kolumny
            champ_bases = ["OG", "WCH", "SFWC", "IST", "NKIC", "YOG", "JWC", "UNI", "COCH"]
            for cname in extra_cols:
                if cname == "SENIOR":
                    val = float(senior_series.get(nat, 0.0))
                    row[cname] = val
                    suma += val
                elif any(base in cname for base in champ_bases):
                    # Wywołanie nowej logiki sumowania wielu plików dla mistrzostw
                    v_champ = self._calculate_championship_points(cname).get(nat, 0.0)
                    row[cname] = v_champ
                    suma += v_champ
                elif cname in CUP_POINTS:
                    vI = self._points_I_for_tag(cname).get(nat, 0.0)
                    row[cname] = vI
                    suma += vI
                else:
                    # Np. CC, NTC, MSC są doliczane później w reload_all
                    row[cname] = 0.0

            row["Suma"] = suma
            rows.append(row)

        if not rows:
            return pd.DataFrame(columns=["Lp.","*","Kraj","NAT","Suma"])

        df = pd.DataFrame(rows)

        # posprzątaj kolejność kolumn
        first_cols = ["Lp.", "*", "Kraj", "NAT", "Suma"]
        tag_cols = []
        for tag in tags:
            tag_cols.append(f"{tag} [T]")
            tag_cols.append(f"{tag} [I]")
        order = first_cols + tag_cols + list(extra_cols)

        # dołóż Lp. wg Suma malejąco, z tym samym miejscem przy remisie
        df["Suma"] = pd.to_numeric(df["Suma"], errors="coerce").fillna(0.0)
        df = df.sort_values("Suma", ascending=False, kind="mergesort").reset_index(drop=True)

        places = []
        current_place = 0
        prev_suma = None
        for i, val in enumerate(df["Suma"].tolist()):
            if prev_suma is None or val != prev_suma:
                current_place = i + 1        # 1,2,2,4 – jak w normalnym sporcie
                prev_suma = val
            places.append(current_place)
        df["Lp."] = places

        # wypełnij kolumnę '*' wg miejsca i sumy
        df["*"] = df.apply(
            lambda r: _stars_for_place(r["Lp."], r["Suma"]),
            axis=1
        )

        # zaokrąglij trochę
        for c in df.columns:
            if c not in ("Kraj","NAT","*"):
                try:
                    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                    df[c] = df[c].round(2)
                except Exception:
                    pass

        # ustaw kolejność
        for c in order:
            if c not in df.columns:
                df[c] = 0.0
        df = df[order]
        return df


# ------------------ GUI: Tabela + sortowanie ------------------ #

def _get_flag_img(code: str | None):
    if not FLAG_CACHE:
        return None
    code = (code or "").strip().upper()
    if not code:
        return None
    try:
        img = FLAG_CACHE.get(code)
        if img:
            return img
        return FLAG_CACHE.blank()
    except Exception:
        return None

class CanvasRankingGrid(ttk.Frame):
    def __init__(self, parent, columns, frozen_cols=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.frozen_cols = [c for c in (frozen_cols or []) if c in self.columns]
        self._df = None
        self._sort_state = {}
        self._img_refs = []

        self.header_h = 24
        self.row_h = 20
        self.col_widths = self._default_widths(self.columns)

        wrap = ttk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True)

        # dwa canvasy: lewy (zamrożone kolumny) + prawy (scrollowany poziomo)
        self.left_canvas = tk.Canvas(wrap, highlightthickness=0)
        self.right_canvas = tk.Canvas(wrap, highlightthickness=0)

        self.vsb = ttk.Scrollbar(wrap, orient="vertical", command=self._on_vscroll)
        self.hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.right_canvas.xview)

        self.left_canvas.configure(yscrollcommand=self._on_left_yscroll)
        self.right_canvas.configure(yscrollcommand=self._on_right_yscroll, xscrollcommand=self.hsb.set)

        self.left_canvas.grid(row=0, column=0, sticky="nsew")
        self.right_canvas.grid(row=0, column=1, sticky="nsew")
        self.vsb.grid(row=0, column=2, sticky="ns")
        self.hsb.grid(row=1, column=1, sticky="ew")

        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=0)  # lewy ma stałą szerokość
        wrap.columnconfigure(1, weight=1)  # prawy rozciąga się

        # scrollregion będzie ustawiany po narysowaniu
        self.left_canvas.bind("<Configure>", lambda e: self._update_scrollregion())
        self.right_canvas.bind("<Configure>", lambda e: self._update_scrollregion())

        # scroll kółkiem (pion) po najechaniu
        self.left_canvas.bind("<Enter>", self._bind_mousewheel)
        self.left_canvas.bind("<Leave>", self._unbind_mousewheel)
        self.right_canvas.bind("<Enter>", self._bind_mousewheel)
        self.right_canvas.bind("<Leave>", self._unbind_mousewheel)

        # kliki w nagłówki
        self.left_canvas.bind("<Button-1>", lambda e, side="left": self._on_click(e, side))
        self.right_canvas.bind("<Button-1>", lambda e, side="right": self._on_click(e, side))

        # cache prostokątów nagłówków: (side, x1, x2, col)
        self._header_hitboxes = []

    def _default_widths(self, cols):
        widths = {}
        for c in cols:
            if c == "Lp.":
                widths[c] = 40
            elif c == "*":
                widths[c] = 30
            elif c == "Kraj":
                widths[c] = 150
            elif c == "NAT":
                widths[c] = 60
            elif c in ("Suma", "MEN", "WOMEN"):
                widths[c] = 80
            else:
                widths[c] = max(70, min(130, 8 * len(str(c))))
        return widths

    # ---------- API ---------- #

    def set_dataframe(self, df: pd.DataFrame):
        self._df = df.copy() if df is not None else None
        self._img_refs.clear()
        self._draw()

    # ---------- formatowanie komórki ---------- #

    def _fmt_cell(self, col, val):
        """0 → pusto, reszta ładnie jako int / z 1 miejscem po przecinku."""
        if val is None:
            return ""
        s = str(val).strip()
        if s.lower() in {"nan", "none"}:
            return ""
        # próbujemy liczbowo
        try:
            v = float(s.replace(" ", "").replace(",", "."))
        except Exception:
            return s
        if abs(v) < 1e-9:
            return ""          # <- tu zamiast 0 / 0.0 dajemy pusto
        # prawie całkowita → bez .0
        if abs(v - round(v)) < 1e-6:
            return str(int(round(v)))
        return f"{v:.1f}"

    # ---------- rysowanie ---------- #

    def _draw(self):
        for canv in (self.left_canvas, self.right_canvas):
            canv.delete("all")
        self._header_hitboxes.clear()

        if self._df is None or self._df.empty:
            self._update_scrollregion()
            return

        df = self._df
        frozen = self.frozen_cols
        scroll_cols = [c for c in self.columns if c not in frozen]

        # nagłówki
        x_left = 0
        for c in frozen:
            w = self.col_widths.get(c, 80)
            self.left_canvas.create_rectangle(x_left, 0, x_left + w, self.header_h, fill="#dddddd", outline="#aaaaaa")
            anchor = tk.W if c == "Kraj" else tk.CENTER
            tx = x_left + (w / 2 if anchor == tk.CENTER else 4)
            self.left_canvas.create_text(tx, self.header_h / 2, text=c, anchor=anchor, font=("TkDefaultFont", 9, "bold"))
            self._header_hitboxes.append(("left", x_left, x_left + w, c))
            x_left += w

        x_right = 0
        for c in scroll_cols:
            w = self.col_widths.get(c, 80)
            self.right_canvas.create_rectangle(x_right, 0, x_right + w, self.header_h, fill="#dddddd", outline="#aaaaaa")
            anchor = tk.W if c == "Kraj" else tk.CENTER
            tx = x_right + (w / 2 if anchor == tk.CENTER else 4)
            self.right_canvas.create_text(tx, self.header_h / 2, text=c, anchor=anchor, font=("TkDefaultFont", 9, "bold"))
            self._header_hitboxes.append(("right", x_right, x_right + w, c))
            x_right += w

        # wiersze
        n_rows = len(df)
        for i in range(n_rows):
            row = df.iloc[i]
            y1 = self.header_h + i * self.row_h
            y2 = y1 + self.row_h
            fill = "#ffffff" if i % 2 == 0 else "#f8f8f8"

            # lewa część (zamrożone kolumny)
            x = 0
            for c in frozen:
                w = self.col_widths.get(c, 80)
                self.left_canvas.create_rectangle(x, y1, x + w, y2, fill=fill, outline="#dddddd")

                txt = self._fmt_cell(c, row.get(c, ""))
                if c == "Kraj":
                    # flaga przy kraju
                    nat = str(row.get("NAT", "") or "").strip().upper()
                    img = _get_flag_img(nat)
                    text_x = x + 4
                    if img is not None:
                        iy = y1 + self.row_h / 2
                        self.left_canvas.create_image(x + 4, iy, image=img, anchor=tk.W)
                        self._img_refs.append(img)
                        text_x = x + 4 + img.width() + 4
                    self.left_canvas.create_text(text_x, y1 + self.row_h / 2, text=txt, anchor=tk.W)
                else:
                    self.left_canvas.create_text(x + w / 2, y1 + self.row_h / 2, text=txt, anchor=tk.CENTER)
                x += w

            # prawa część (scrollowana poziomo)
            x = 0
            for c in scroll_cols:
                w = self.col_widths.get(c, 80)
                self.right_canvas.create_rectangle(x, y1, x + w, y2, fill=fill, outline="#dddddd")
                txt = self._fmt_cell(c, row.get(c, ""))
                anchor = tk.W if c == "Kraj" else tk.CENTER
                tx = x + (w / 2 if anchor == tk.CENTER else 4)
                self.right_canvas.create_text(tx, y1 + self.row_h / 2, text=txt, anchor=anchor)
                x += w

        self._update_scrollregion()

    def _update_scrollregion(self):
        """Dopasuj scrollregion do wysokości i szerokości obu części."""
        if self._df is None or self._df.empty:
            h = self.header_h
        else:
            h = self.header_h + len(self._df) * self.row_h

        left_w = sum(self.col_widths.get(c, 80) for c in self.frozen_cols)
        right_w = sum(self.col_widths.get(c, 80) for c in self.columns if c not in self.frozen_cols)

        self.left_canvas.configure(scrollregion=(0, 0, left_w, h))
        self.right_canvas.configure(scrollregion=(0, 0, right_w, h))

    # ---------- sortowanie ---------- #

    def _on_click(self, event, side: str):
        canv = self.left_canvas if side == "left" else self.right_canvas
        x = canv.canvasx(event.x)
        y = canv.canvasy(event.y)
        if y > self.header_h:
            return
        for src, x1, x2, col in self._header_hitboxes:
            if src == side and x1 <= x <= x2:
                self._sort_by(col)
                break

    def _sort_by(self, col):
        if self._df is None or col not in self._df.columns:
            return
        asc = self._sort_state.get(col, True)
        df = self._df.copy()
        try:
            df[col] = pd.to_numeric(df[col], errors="ignore")
        except Exception:
            pass
        try:
            df = df.sort_values(by=col, ascending=asc, kind="mergesort")
        except Exception:
            return
        self._df = df.reset_index(drop=True)
        self._sort_state[col] = not asc
        self._draw()

    # ---------- scroll pionowy / kółko ---------- #

    def _on_mousewheel(self, event):
        delta = int(-event.delta / 120)
        self.left_canvas.yview_scroll(delta, "units")
        self.right_canvas.yview_scroll(delta, "units")

    def _bind_mousewheel(self, event):
        self.left_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        self.left_canvas.unbind_all("<MouseWheel>")

    def _on_vscroll(self, *args):
        self.left_canvas.yview(*args)
        self.right_canvas.yview(*args)

    def _on_left_yscroll(self, first, last):
        self.vsb.set(first, last)
        self.right_canvas.yview_moveto(first)

    def _on_right_yscroll(self, first, last):
        self.vsb.set(first, last)
        self.left_canvas.yview_moveto(first)

# ------------------ GŁÓWNA RAMKA ------------------ #

class RankingFISFrame(ttk.Frame):
    def __init__(self, parent, default_dir: str | Path = "./S51/Klasyfikacje S51"):
        super().__init__(parent)

        self.dir_var = tk.StringVar(value=str(default_dir))
        self.nb = ttk.Notebook(self)

        self._build_header()
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)

        # Zakładki
        self.tab_men = ttk.Frame(self.nb)
        self.tab_women = ttk.Frame(self.nb)
        self.tab_all = ttk.Frame(self.nb)
        self.tab_pts = ttk.Frame(self.nb)

        self.nb.add(self.tab_men, text="MEN")
        self.nb.add(self.tab_women, text="WOMEN")
        self.nb.add(self.tab_all, text="ALL")
        self.nb.add(self.tab_pts, text="Punkty")

        # Tabele
        # dodatkowe puchary / imprezy – na razie wszystkie = 0
        cup_extra_men = ["OG-M", "WCH-M", "SFWC-M", "IST-M", "NKIC-M", "YOG-M", "JWC-M", "COCH-M", "UNI-M"]
        cup_extra_women = ["OG-W", "WCH-W", "SFWC-W", "IST-W", "NKIC-W", "YOG-W", "JWC-W", "COCH-W", "UNI-W"]

        # Tabele
        men_cols = (
            ["Lp.", "*", "Kraj", "NAT", "Suma"]
            + [x for tag in MEN_TAGS for x in (f"{tag} [T]", f"{tag} [I]")]
            + ["CC", "NTC", "MSC"]
            + cup_extra_men
            + ["SENIOR"]
        )

        women_cols = (
            ["Lp.", "*", "Kraj", "NAT", "Suma"]
            + [x for tag in WOMEN_TAGS for x in (f"{tag} [T]", f"{tag} [I]")]
            + ["CC", "NTC", "MSC"]
            + cup_extra_women
            + ["SENIOR"]
        )
        all_cols = ["Lp.", "*", "Kraj", "NAT", "Suma", "MEN", "WOMEN"]

        frozen = ["Lp.", "*", "Kraj", "NAT", "Suma"]

        self.tbl_men = CanvasRankingGrid(
            self.tab_men,
            columns=men_cols,
            frozen_cols=frozen,
        )
        self.tbl_women = CanvasRankingGrid(
            self.tab_women,
            columns=women_cols,
            frozen_cols=frozen,
        )
        # w ALL możesz zostawić bez zamrażania, albo też użyć frozen – jak wolisz
        self.tbl_all = CanvasRankingGrid(
            self.tab_all,
            columns=all_cols,
            frozen_cols=frozen,
        )

        self.tbl_men.pack(fill=tk.BOTH, expand=True)
        self.tbl_women.pack(fill=tk.BOTH, expand=True)
        self.tbl_all.pack(fill=tk.BOTH, expand=True)

        # Przycisk "Zapisz Seed" w zakładce ALL
        btn_frame_all = ttk.Frame(self.tab_all)
        btn_frame_all.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Button(btn_frame_all, text="Zapisz Seed (S46_SWISS_Seed.csv)", command=self.save_swiss_seed).pack(side="left")

        self._build_points_tab()

        # automatyczny pierwszy load (jeśli folder istnieje)
        if Path(self.dir_var.get()).is_dir():
            try:
                self.reload_all()
            except Exception as e:
                messagebox.showwarning("Ranking FIS", f"Nie udało się wczytać danych:\n{e}")

    def _build_header(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(bar, text="Folder klasyfikacji (CSV):").pack(side="left")
        ttk.Entry(bar, textvariable=self.dir_var, width=50).pack(side="left", padx=(4, 4))
        ttk.Button(bar, text="…", command=self._browse_dir).pack(side="left")
        ttk.Button(bar, text="Wczytaj", command=self.reload_all).pack(side="left", padx=(6, 0))
        
        # --- NOWY PRZYCISK EKSPORTU ---
        ttk.Button(bar, text="Eksportuj", command=self.export_to_csv).pack(side="left", padx=(6, 0))

        self.info_lbl = ttk.Label(bar, text="", foreground="#666")
        self.info_lbl.pack(side="left", padx=(10, 0))

    def _build_header(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(8, 4))

        ttk.Label(bar, text="Folder klasyfikacji (CSV):").pack(side="left")
        ttk.Entry(bar, textvariable=self.dir_var, width=50).pack(side="left", padx=(4, 4))
        ttk.Button(bar, text="…", command=self._browse_dir).pack(side="left")
        ttk.Button(bar, text="Wczytaj", command=self.reload_all).pack(side="left", padx=(6, 0))
        
        # Przyciski Eksportu i Importu
        ttk.Button(bar, text="Eksportuj", command=self.export_to_csv).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Importuj", command=self.import_from_csv).pack(side="left", padx=(6, 0))

        self.info_lbl = ttk.Label(bar, text="", foreground="#666")
        self.info_lbl.pack(side="left", padx=(10, 0))

    def import_from_csv(self):
        """Importuje dane z wcześniej wyeksportowanego pliku CSV do widoku."""
        file_path = filedialog.askopenfilename(
            title="Wybierz plik rankingu FIS do zaimportowania",
            filetypes=[("Pliki CSV", "*.csv"), ("Wszystkie pliki", "*.*")]
        )
        
        if not file_path:
            return

        try:
            # Wczytujemy plik (używając średnika i kodowania utf-8-sig)
            df = pd.read_csv(file_path, sep=";", encoding="utf-8-sig")
            
            fname = os.path.basename(file_path).upper()
            
            # Logika rozpoznawania, do której tabeli wstawić dane
            if " ALL " in fname:
                self.tbl_all.set_dataframe(df)
                self.nb.select(self.tab_all) # Przełącz na zakładkę ALL
                target = "ALL"
            elif " RANKING FIS M " in fname or " M " in fname:
                self.tbl_men.set_dataframe(df)
                self.nb.select(self.tab_men) # Przełącz na zakładkę MEN
                target = "MEN"
            elif " RANKING FIS W " in fname or " W " in fname:
                self.tbl_women.set_dataframe(df)
                self.nb.select(self.tab_women) # Przełącz na zakładkę WOMEN
                target = "WOMEN"
            else:
                # Jeśli nazwa pliku nie pasuje, pytamy użytkownika lub sprawdzamy kolumny
                if "MEN" in df.columns and "WOMEN" in df.columns:
                    self.tbl_all.set_dataframe(df)
                    target = "ALL (rozpoznano po kolumnach)"
                else:
                    # Domyślnie ładujemy tam, gdzie pasuje liczba kolumn lub do aktualnej zakładki
                    current_tab_idx = self.nb.index("current")
                    if current_tab_idx == 0: self.tbl_men.set_dataframe(df)
                    elif current_tab_idx == 1: self.tbl_women.set_dataframe(df)
                    else: self.tbl_all.set_dataframe(df)
                    target = "aktualnej zakładki"

            messagebox.showinfo("Import", f"Pomyślnie zaimportowano dane do tabeli: {target}")
            self.info_lbl.config(text=f"Zaimportowano: {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Błąd importu", f"Nie udało się wczytać pliku:\n{e}")
    
    def export_to_csv(self):
        """Eksportuje aktualne tabele dokładnie do folderu ./<sezon>/"""
        import re
        from pathlib import Path
        from tkinter import messagebox

        # Ścieżka wybrana przez użytkownika (np. C:/.../S51/Klasyfikacje S51)
        selected_path = Path(self.dir_var.get().strip())
        
        if not selected_path.exists() or self.tbl_men._df is None:
            messagebox.showwarning("Eksport", "Najpierw wczytaj poprawne dane.")
            return

        # 1. Szukamy tagu sezonu (np. S51) w nazwie folderu
        match = re.search(r"S\d+", str(selected_path))
        season_tag = match.group(0) if match else "FIS_Export"

        # 2. Ustawiamy folder docelowy na RODZICA wybranego folderu
        # Jeśli wybrałeś ".../S51/Klasyfikacje S51", to target_dir będzie ".../S51"
        target_dir = selected_path.parent
        
        # Jeśli jednak folder nadrzędny nie nazywa się tak jak sezon, 
        # wymuszamy ścieżkę relatywną ./S51 w miejscu uruchomienia skryptu:
        if season_tag not in target_dir.name:
            target_dir = Path(f"./{season_tag}")

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            
            files = {
                f"Ranking FIS M {season_tag}.csv": self.tbl_men._df,
                f"Ranking FIS W {season_tag}.csv": self.tbl_women._df,
                f"Ranking FIS ALL {season_tag}.csv": self.tbl_all._df
            }

            for filename, df in files.items():
                save_path = target_dir / filename
                # Zapis z kodowaniem utf-8-sig (polskie znaki w Excelu) i średnikiem
                df.to_csv(save_path, sep=";", index=False, encoding="utf-8-sig")
            
            messagebox.showinfo("Eksport zakończony", 
                                f"Pliki zostały zapisane w folderze nadrzędnym:\n{target_dir.absolute()}")
        except Exception as e:
            messagebox.showerror("Błąd eksportu", f"Błąd zapisu: {e}")

    def save_swiss_seed(self):
        """Zapisuje plik <sezon>_SWISS_Seed.csv z kolumnami Lp.;Drużyna;Kraj do ./<sezon>/Team <sezon>/"""
        import re
        from pathlib import Path
        from tkinter import messagebox

        if self.tbl_all._df is None or self.tbl_all._df.empty:
            messagebox.showwarning("Seed", "Brak danych w zakładce ALL. Najpierw wczytaj ranking.")
            return

        # Wykryj sezon (np. S51) ze ścieżki i zwiększ o 1 (seed na kolejny sezon)
        selected_path = Path(self.dir_var.get().strip())
        match = re.search(r"S(\d+)", str(selected_path))
        if match:
            next_num = int(match.group(1)) + 1
            season_tag = f"S{next_num}"
        else:
            season_tag = "S51"

        # Folder docelowy: ./<sezon>/Team <sezon>/
        target_dir = Path(f"./{season_tag}/Team {season_tag}")
        target_dir.mkdir(parents=True, exist_ok=True)

        df_all = self.tbl_all._df.copy()

        # Budujemy plik seed: Lp.;Drużyna;Kraj
        # "Drużyna" = NAT (kod kraju), "Kraj" = pełna nazwa kraju
        seed_df = pd.DataFrame()
        seed_df["Lp."] = df_all["Lp."] if "Lp." in df_all.columns else range(1, len(df_all) + 1)
        seed_df["Drużyna"] = df_all["Kraj"] if "Kraj" in df_all.columns else ""
        seed_df["Kraj"] = df_all["NAT"] if "NAT" in df_all.columns else ""

        out_path = target_dir / f"{season_tag}_SWISS_Seed.csv"
        try:
            seed_df.to_csv(out_path, sep=";", index=False, encoding="utf-8-sig")
            messagebox.showinfo("Seed zapisany",
                                f"Plik zapisany:\n{out_path.absolute()}")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać pliku:\n{e}")

    def _browse_dir(self):
        path = filedialog.askdirectory(title="Wybierz folder z klasyfikacjami (CSV)")
        if path:
            self.dir_var.set(path)

    def _load_external_ranking(self, selected_folder: str) -> dict:
        """
        Wczytuje pliki rankingowe z dokładnie tych miejsc:
          1) selected_folder / S51 / Team S51        -> CC, MSC, SWISS (NTC)
          2) selected_folder / S51 / Team S51 / WC   -> pliki WC...DC (opcjonalnie)
          3) selected_folder                         -> fallback
        Zwraca dict z mapami: { 'CC': {...}, 'MSC_M': {...}, 'MSC_W': {...}, 'SWISS': {...}, 'WC': {...} }
        Dokładne ścieżki są logowane (print) — dzięki temu w konsoli zobaczysz, co zostało sprawdzone.
        """
        from pathlib import Path
        import pandas as pd

        out = {"CC": {}, "MSC_M": {}, "MSC_W": {}, "SWISS": {}, "WC": {}}
        base = Path(selected_folder or ".").resolve()
        # diagnostyka szybka — pokażamy dokładnie jaką ścieżkę dostał loader
        try:
            print(f"[RankingLoader] selected_folder resolved to: {base}")
        except Exception:
            print(f"[RankingLoader] selected_folder: {selected_folder}")


        # Szukamy w: 
        # 1) selected_folder
        # 2) selected_folder/Team S51
        # 3) selected_folder/../Team S51   (czyli rodzeństwo katalogu)
        # 4) selected_folder/S51/Team S51
        # 5) selected_folder/S51/Team S51/WC
        # 6) selected_folder/../Klasyfikacje S51
        # 7) selected_folder/../Team S51

        dirs = [
            base,
            base / "Team S51",
            base.parent / "Team S51",
            base / "S51" / "Team S51",
            base / "S51" / "Team S51" / "WC",
            base.parent / "Klasyfikacje S51",
            base.parent / "Team S51",
        ]


        # Usuń duplikaty zachowując kolejność i utwórz listę faktycznie istniejących katalogów (dla diagnostyki)
        seen = set()
        search_dirs = []
        for d in dirs:
            try:
                d_res = d.resolve()
            except Exception:
                d_res = d
            if str(d_res) in seen:
                continue
            seen.add(str(d_res))
            search_dirs.append(d)

        # diagnostyka: pokaż co będziemy szukać
        print("[RankingLoader] search_dirs:")
        for d in search_dirs:
            print("  -", str(d))

        files_to_find = {
            "CC":       ["S51_CC_Klasyfikacja.csv", "CC_Klasyfikacja.csv", "S51_CC.csv"],
            "MSC_M":    ["S51_MSC_M_Klasyfikacja.csv", "MSC_M_Klasyfikacja.csv", "MSC_M.csv"],
            "MSC_W":    ["S51_MSC_W_Klasyfikacja.csv", "MSC_W_Klasyfikacja.csv", "MSC_W.csv"],
            "SWISS":    ["S51_SWISS_Klasyfikacja.csv", "SWISS_Klasyfikacja.csv", "SWISS.csv"],
            "WC":       ["WC_Klasyfikacja.csv", "DC_Klasyfikacja.csv"]
        }

        def try_read(path: Path):
            try:
                df = _read_csv_any(path)
                df.columns = _clean_headers(df.columns)
                return df
            except Exception as e:
                print(f"[RankingLoader] nie udało się wczytać {path}: {e}")
                return None

        import unicodedata

        def _norm(s: str) -> str:
            if s is None:
                return ""
            # usuń diakrytykę, spacje, kropki i zrób lowercase
            s = str(s)
            s = unicodedata.normalize("NFKD", s)
            s = s.encode("ascii", "ignore").decode("ascii")
            s = s.replace(" ", "").replace(".", "").replace("_", "").lower()
            return s

        def find_first_file(candidates):
            # 1) najpierw sprawdź dokładne nazwy w search_dirs (jak wcześniej)
            for d in search_dirs:
                try:
                    if not d.exists():
                        continue
                except Exception:
                    continue
                for name in candidates:
                    p = d / name
                    if p.is_file():
                        print(f"[RankingLoader] found exact {p}")
                        return p

            # 2) wypisz wszystkie csv w folderach (diagnostyka)
            for d in search_dirs:
                try:
                    if not d.exists():
                        continue
                except Exception:
                    continue
                csvs = list(d.rglob("*.csv"))  # rekurencyjnie
                if csvs:
                    print(f"[RankingLoader] csvs under {d}:")
                    for p in csvs:
                        print("   -", p)

            # 3) spróbuj znaleźć plik po fragmentach nazwy (tolerancyjnie, rekurencyjnie)
            cand_norms = [_norm(c) for c in candidates]
            for d in search_dirs:
                try:
                    if not d.exists():
                        continue
                except Exception:
                    continue
                for p in d.rglob("*.csv"):
                    pn = _norm(p.name)
                    for cn in cand_norms:
                        if cn in pn:
                            print(f"[RankingLoader] found by fuzzy match {p} (matched '{cn}')")
                            return p

            # 4) ostatnia deska ratunku: spróbuj dopasować po zawartości pliku (nagłówki)
            # (np. znajdź plik, który ma kolumnę 'Drużyna' lub 'Ranking' w nagłówkach)
            for d in search_dirs:
                try:
                    if not d.exists():
                        continue
                except Exception:
                    continue
                for p in d.rglob("*.csv"):
                    try:
                        df_try = _read_csv_any(p)
                        cols = [str(c).strip().lower() for c in df_try.columns]
                        if any(x in cols for x in ("drużyna","kraj","ranking","ranking fis","nat")):
                            print(f"[RankingLoader] found by header-scan {p}")
                            return p
                    except Exception:
                        continue

            return None

        # przetwarzaj każdą grupę
        for key, candidates in files_to_find.items():
            path = find_first_file(candidates)
            if not path:
                print(f"[RankingLoader] brak pliku dla klucza {key}")
                continue
            df = try_read(path)
            if df is None:
                continue

            # znajdź kolumnę rankingową tolerancyjnie
            rank_col = None
            for c in df.columns:
                cu = str(c).strip().upper()
                if cu in ("RANKING FIS", "RANKING_FIS", "RANKING"):
                    rank_col = c
                    break
            if rank_col is None:
                for c in df.columns:
                    if "RANK" in str(c).upper():
                        rank_col = c
                        break
            if rank_col is None:
                print(f"[RankingLoader] w {path} nie znaleziono kolumny z rankingiem")
                continue

            # wykryj NAT / Kraj / Drużyna
            nat_col = None
            country_col = None
            for c in df.columns:
                cu = str(c).upper()
                if cu in ("NAT", "KOD", "CODE"):
                    nat_col = c
                if cu in ("KRAJ", "COUNTRY", "NATION", "REPREZENTACJA"):
                    country_col = c

            # zapełnij mapę
            for _, r in df.iterrows():
                raw_rank = r.get(rank_col, None)
                if pd.isna(raw_rank) or raw_rank is None or str(raw_rank).strip() == "":
                    continue
                try:
                    val_rank_f = float(raw_rank)
                except Exception:
                    try:
                        val_rank_f = float(str(raw_rank).replace(",", "."))
                    except Exception:
                        continue

                key_name = None
                if nat_col is not None:
                    key_name = str(r.get(nat_col, "") or "").strip().upper()
                if not key_name and country_col is not None:
                    key_name = str(r.get(country_col, "") or "").strip()
                if not key_name and "Drużyna" in df.columns:
                    key_name = str(r.get("Drużyna", "") or "").strip()

                if not key_name:
                    continue
                out[key][key_name] = val_rank_f

        return out

    def _apply_external_rank_map(self, df: pd.DataFrame, ext_map: dict, target_col: str):
        """
        df: tabela wynikowa (z kolumną 'Kraj' i 'NAT')
        ext_map: mapa klucz->ranking (klucze mogą być NAT lub nazwy kraju)
        target_col: nazwa kolumny do nadpisania (np. 'CC' lub 'MSC' lub 'NTC')
        """
        if df is None or df.empty:
            return df
        # najpierw mapowanie po NAT (3-letter code)
        def get_val(row):
            nat = str(row.get("NAT", "") or "").strip().upper()
            kraj = str(row.get("Kraj", "") or "").strip()
            # bezpośredni NAT match
            if nat and nat in ext_map:
                return ext_map.get(nat)
            # try pełna nazwa (case-insensitive)
            for k, v in ext_map.items():
                if isinstance(k, str) and k.strip().lower() == kraj.strip().lower():
                    return v
            # jeszcze spróbuj, gdy ext_map ma klucz będący krótką wersją kraju
            for k, v in ext_map.items():
                if isinstance(k, str) and k.strip().upper() == kraj.strip().upper():
                    return v
            return None

        vals = []
        for _, r in df.iterrows():
            v = get_val(r)
            vals.append(v if v is not None else 0.0)
        df[target_col] = vals
        # jeżeli target ma zostać dodany do sumy, pozostaw to dalej (tutaj w reload_all od razu nadpisz)
        return df

    def reload_all(self):
        root = self.dir_var.get().strip()
        if not root:
            messagebox.showwarning("Ranking FIS", "Podaj folder z klasyfikacjami.")
            return
        if not Path(root).is_dir():
            messagebox.showwarning("Ranking FIS", f"Folder nie istnieje:\n{root}")
            return

        calc = FISRankingCalculator(root)

        extra_cols_men = (
            "CC", "NTC", "MSC",
            "OG-M", "WCH-M", "SFWC-M", "IST-M", "NKIC-M", "YOG-M", "JWC-M", "COCH-M", "UNI-M",
            "SENIOR",
        )

        extra_cols_women = (
            "CC", "NTC", "MSC",
            "OG-W", "WCH-W", "SFWC-W", "IST-W", "NKIC-W", "YOG-W", "JWC-W", "COCH-W", "UNI-W",
            "SENIOR",
        )

        df_men = calc.build_table_for_tags(MEN_TAGS, extra_cols=extra_cols_men)
        df_women = calc.build_table_for_tags(WOMEN_TAGS, extra_cols=extra_cols_women)

        # --- dodatkowe pliki: CC / MSC M / MSC W / SWISS (NTC) ---
        ext = self._load_external_ranking(root)  # słownik map

        # CC -> wypełnij kolumnę 'CC' (zarówno MEN jak WOMEN)
        if "CC" in ext and ext["CC"]:
            df_men = self._apply_external_rank_map(df_men, ext["CC"], "CC")
            df_women = self._apply_external_rank_map(df_women, ext["CC"], "CC")

        # MSC -> MSC_M dla MEN, MSC_W dla WOMEN -> kolumna 'MSC'
        if "MSC_M" in ext and ext["MSC_M"]:
            df_men = self._apply_external_rank_map(df_men, ext["MSC_M"], "MSC")
        if "MSC_W" in ext and ext["MSC_W"]:
            df_women = self._apply_external_rank_map(df_women, ext["MSC_W"], "MSC")

        # SWISS -> traktujemy jako NTC (NTC w extra_cols)
        if "SWISS" in ext and ext["SWISS"]:
            # w tabeli mamy kolumnę 'NTC' w extra_cols – zróbmy mapowanie do tej kolumny
            df_men = self._apply_external_rank_map(df_men, ext["SWISS"], "NTC")
            df_women = self._apply_external_rank_map(df_women, ext["SWISS"], "NTC")

        # --- po wczytaniu map i zastosowaniu _apply_external_rank_map ---
        # Upewnij się, że kolumny CC, MSC, NTC istnieją i są numeryczne, potem dodajemy je do kolumny 'Suma'.
        def _ensure_and_add_to_suma(df: pd.DataFrame, cols_to_add: list):
            if df is None or df.empty:
                return df
            # jeśli nie ma kolumny 'Suma', utwórz ją zerami
            if "Suma" not in df.columns:
                df["Suma"] = 0.0
            # upewnij się, że wszystkie kolumny są obecne
            for c in cols_to_add:
                if c not in df.columns:
                    df[c] = 0.0
            # skonwertuj na numeric (bez wybuchu przy pustych/tekstowych)
            df[cols_to_add] = df[cols_to_add].apply(lambda s: pd.to_numeric(s, errors="coerce").fillna(0.0))
            # konwertuj kolumnę Suma także do numeric na wszelki wypadek
            df["Suma"] = pd.to_numeric(df["Suma"], errors="coerce").fillna(0.0)
            # dodaj sumę kolumn (jeśli chcesz nadpisać Suma -> odkomentuj linie poniżej,
            # obecnie dodajemy wartości z dodatkowych kolumn do istniejącej Suma)
            add_vals = df[cols_to_add].sum(axis=1)
            df["Suma"] = df["Suma"] + add_vals
            return df

        # teraz zastosuj do obu tabel (zakładam nazwy kolumn CC, MSC, NTC)
        df_men = _ensure_and_add_to_suma(df_men, ["CC", "MSC", "NTC"])
        df_women = _ensure_and_add_to_suma(df_women, ["CC", "MSC", "NTC"])

        # --- sortowanie po aktualnej kolumnie 'Suma' (malejąco) i odświeżenie numeracji Lp. ---
        for name, df in (("MEN", df_men), ("WOMEN", df_women)):
            if df is None or df.empty:
                continue
            # upewnij się, że Suma jest numeric
            df["Suma"] = pd.to_numeric(df["Suma"], errors="coerce").fillna(0.0)
            # sortuj malejąco po Suma, zachowując stabilność
            df_sorted = df.sort_values(by=["Suma"], ascending=False, kind="mergesort").reset_index(drop=True)
            # odśwież kolumnę Lp. jeśli istnieje (albo utwórz ją na początku)
            if "Lp." in df_sorted.columns:
                df_sorted["Lp."] = df_sorted.index + 1
            else:
                df_sorted.insert(0, "Lp.", df_sorted.index + 1)

            # PRZELICZ gwiazdki '*' na nowo (ważne — wcześniej były liczone PRZED dodaniem CC/MSC/NTC)
            df_sorted["*"] = df_sorted.apply(
                lambda r: _stars_for_place(int(r["Lp."]) if not pd.isna(r["Lp."]) else 0, float(r["Suma"]) if not pd.isna(r["Suma"]) else 0.0),
                axis=1
            )

            # przypisz z powrotem
            if name == "MEN":
                df_men = df_sorted
            else:
                df_women = df_sorted


        # tabelka ALL
        df_all = self._build_all_table(df_men, df_women)

        self.tbl_men.set_dataframe(df_men)
        self.tbl_women.set_dataframe(df_women)
        self.tbl_all.set_dataframe(df_all)

        self.info_lbl.config(text=f"Źródło: {os.path.abspath(root)}")
        print(f"[RankingLoader] calling _load_external_ranking with: {root}")   # root to zmienna używana w reload_all
        ext = self._load_external_ranking(root)



    @staticmethod
    def _build_all_table(df_m: pd.DataFrame, df_w: pd.DataFrame) -> pd.DataFrame:
        if df_m is None:
            df_m = pd.DataFrame(columns=["NAT","Kraj","Suma"])
        if df_w is None:
            df_w = pd.DataFrame(columns=["NAT","Kraj","Suma"])

        m = df_m[["NAT","Kraj","Suma"]].copy() if not df_m.empty else pd.DataFrame(columns=["NAT","Kraj","Suma"])
        w = df_w[["NAT","Kraj","Suma"]].copy() if not df_w.empty else pd.DataFrame(columns=["NAT","Kraj","Suma"])

        m.rename(columns={"Suma":"MEN"}, inplace=True)
        w.rename(columns={"Suma":"WOMEN"}, inplace=True)

        df = pd.merge(m, w, on=["NAT","Kraj"], how="outer")
        df["MEN"] = pd.to_numeric(df.get("MEN", 0), errors="coerce").fillna(0.0)
        df["WOMEN"] = pd.to_numeric(df.get("WOMEN", 0), errors="coerce").fillna(0.0)
        df["Suma"] = (df["MEN"] + df["WOMEN"]).round(2)

        df = df.sort_values("Suma", ascending=False, kind="mergesort").reset_index(drop=True)
        df["Lp."] = df.index + 1
        df["*"] = df.apply(
            lambda r: _stars_for_place(r["Lp."], r["Suma"]),
            axis=1
        )

        cols = ["Lp.","*","Kraj","NAT","Suma","MEN","WOMEN"]
        for c in cols:
            if c not in df.columns:
                df[c] = 0.0 if c not in ("Kraj","NAT","*") else ""
        return df[cols]

    def _build_points_tab(self):
        """Zakładka 'Punkty' z tabelą CUP / miejsca 1–10."""
        cols = ["CUP"] + [str(i) for i in range(1, 11)]

        # WAŻNE: pokazujemy wszystkie kolumny, łącznie z CUP
        tv = ttk.Treeview(self.tab_pts, columns=cols, show="headings")
        tv.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(self.tab_pts, orient="vertical", command=tv.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(self.tab_pts, orient="horizontal", command=tv.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tab_pts.grid_rowconfigure(0, weight=1)
        self.tab_pts.grid_columnconfigure(0, weight=1)

        # nagłówki
        for c in cols:
            tv.heading(c, text=c)
            if c == "CUP":
                tv.column(c, width=120, anchor="w", stretch=False)
            else:
                tv.column(c, width=60, anchor="center", stretch=False)

        # wiersze w kolejności wyświetlania
        order = [
            "WC-M","WC-W","GP-M","GP-W","COC-M","COC-W","FC-M","FC-W","SCOC-M","SCOC-W",
            "JC-M","JC-W","MC-M","MC-W","PC-M","PC-W","QC-M","QC-W","TC-M","TC-W",
            "AC-M","AC-W","BC-M","BC-W","DC-M","DC-W",
            "OG-M", "OG-W", "WCH-M", "WCH-W", "SFWC-M", "SFWC-W", 
            "NKIC-M", "NKIC-W", "COCH-M", "COCH-W", "JWC-M", "JWC-W", 
            "IST-M", "IST-W", "UNI-M", "UNI-W", "YOG-M", "YOG-W",
            "TCS","PLANICA7","WILL5","RAWAIR_M","NT","FT","RAWAIR_W","BB","CC",
        ]
        for cup in order:
            pts_map = CUP_POINTS.get(cup, {})
            row = [cup]
            for place in range(1, 11):
                val = pts_map.get(place, 0)
                # zera dalej chowamy, żeby nie było śmietnika
                row.append("" if val == 0 else val)
            tv.insert("", "end", values=row)

# ------------------ entrypoint dla combined ------------------ #

def build_gui(parent) -> RankingFISFrame:
    """Standardowy entrypoint: build_gui(parent) -> Frame."""
    return RankingFISFrame(parent)

if __name__ == "__main__":
    import tkinter as tk
    from pathlib import Path

    root = tk.Tk()
    root.title("Ranking FIS")

    # próba maksymalizacji okna na starcie
    try:
        # Windows
        root.state("zoomed")
    except Exception:
        # Linux / inne
        root.attributes("-zoomed", True)

    # domyślny folder z klasyfikacjami – dopasuj do siebie
    default_dir = Path("./S51/Klasyfikacje S51")

    app = RankingFISFrame(root, default_dir=default_dir)
    app.pack(fill=tk.BOTH, expand=True)

    root.mainloop()
