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
    "FNT":       {1:100, 2:75, 3:50},
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
        women_tours = ["RAWAIR_W", "BB", "FNT"]

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
        _dd = Path(str(default_dir))
        _parent = _dd.parent if _dd.is_dir() else Path(".")
        self.tab_stats  = FISStatsFrame(self.nb, data_dir=_parent)
        self.tab_junior = JuniorLeaguesFrame(self.nb, data_dir=_parent)

        self.nb.add(self.tab_men, text="MEN")
        self.nb.add(self.tab_women, text="WOMEN")
        self.nb.add(self.tab_all, text="ALL")
        self.nb.add(self.tab_pts, text="Punkty")
        self.nb.add(self.tab_stats, text="Statystyki")
        self.nb.add(self.tab_junior, text="Ligi juniorskie")

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
        ttk.Button(btn_frame_all, text="Zapisz Seed na następny sezon", command=self.save_swiss_seed).pack(side="left")

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

        # Wykryj tag sezonu dynamicznie z ścieżki (np. "S51")
        _stag_m = _re.search(r"S(\d+)", str(base), _re.IGNORECASE)
        _stag = f"S{_stag_m.group(1)}" if _stag_m else "S51"

        dirs = [
            base,
            base / f"Team {_stag}",
            base.parent / f"Team {_stag}",
            base / _stag / f"Team {_stag}",
            base / _stag / f"Team {_stag}" / "WC",
            base.parent / f"Klasyfikacje {_stag}",
            base.parent / f"Team {_stag}",
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
            "CC":    [f"{_stag}_CC_Klasyfikacja.csv",    "CC_Klasyfikacja.csv",    f"{_stag}_CC.csv",    "CC.csv"],
            "MSC_M": [f"{_stag}_MSC_M_Klasyfikacja.csv", "MSC_M_Klasyfikacja.csv", f"{_stag}_MSC_M.csv", "MSC_M.csv"],
            "MSC_W": [f"{_stag}_MSC_W_Klasyfikacja.csv", "MSC_W_Klasyfikacja.csv", f"{_stag}_MSC_W.csv", "MSC_W.csv"],
            "SWISS": [f"{_stag}_SWISS_Klasyfikacja.csv", "SWISS_Klasyfikacja.csv", f"{_stag}_SWISS.csv", "SWISS.csv"],
            "WC":    ["WC_Klasyfikacja.csv", "DC_Klasyfikacja.csv"],
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

        # --- synchronizuj bieżący sezon z zakładką Statystyki ---
        season_tag = calc.season_prefix  # np. "S51"
        self.tab_stats.sync_from_ranking(df_men, df_women, df_all, season_tag)



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
            "TCS","PLANICA7","WILL5","RAWAIR_M","NT","FT","RAWAIR_W","BB","FNT","CC",
        ]
        for cup in order:
            pts_map = CUP_POINTS.get(cup, {})
            row = [cup]
            for place in range(1, 11):
                val = pts_map.get(place, 0)
                # zera dalej chowamy, żeby nie było śmietnika
                row.append("" if val == 0 else val)
            tv.insert("", "end", values=row)

# ------------------ ZAKŁADKA STATYSTYK ------------------ #

import re as _re

def _season_num(tag: str) -> int:
    """Wyciąga numer sezonu z tagu np. 'S40' -> 40, 'S08' -> 8."""
    m = _re.search(r"S(\d+)", str(tag))
    return int(m.group(1)) if m else 0


def _season_tag_from_filename(fname_str: str) -> str | None:
    """
    Wyciąga tag sezonu z nazwy pliku zachowując oryginalne zera wiodące.
    'Ranking FIS S08.xlsx' -> 'S08'
    'Ranking FIS M S39.csv' -> 'S39'
    'Klasyfikacje2 S27 — kopia.xlsx' -> 'S27'
    Zwraca None jeśli nie znaleziono.
    """
    m = _re.search(r"S(\d{2,})", fname_str, _re.IGNORECASE)
    if not m:
        m = _re.search(r"S(\d+)", fname_str, _re.IGNORECASE)
    if not m:
        return None
    digits = m.group(1)
    # Zachowaj padding (S08, S39 itd.) ale normalizuj do min. 2 cyfr
    return f"S{digits.zfill(2)}"


def _load_season_data(path_or_folder: str | Path, season_tag: str) -> dict:
    """
    Wczytuje dane jednego sezonu rankingowego.
    Zwraca dict:  { 'men': df|None, 'women': df|None, 'all': df|None, 'tag': season_tag }

    Obsługuje:
    - xlsx (arkusze MEN/WOMEN/ALL, header w wierszu 1)
      · S01-S37: ./S01-S37/Ranking/Ranking FIS SXX.xlsx  (lub podobne)
    - CSV (Ranking FIS M Sxx.csv itd.)
      · S38+:    ./SXX/Ranking FIS M SXX.csv
    """
    base = Path(path_or_folder)
    result = {"men": None, "women": None, "all": None, "tag": season_tag}

    # --- próba xlsx ---
    for fname in base.glob("*.xlsx"):
        fn_up = fname.name.upper()
        # Sprawdź czy tag pasuje – obsłuż warianty z/bez zera wiodącego (S8 == S08)
        snum_local = _season_num(season_tag)
        tag_variants = {season_tag.upper(),
                        f"S{snum_local}",
                        f"S{str(snum_local).zfill(2)}"}
        if "RANKING" in fn_up and "FIS" in fn_up and any(v in fn_up for v in tag_variants):
            try:
                xl = pd.ExcelFile(fname)
                sheets = {s.upper(): s for s in xl.sheet_names}
                for key, sname in [("men", "MEN"), ("women", "WOMEN"), ("all", "ALL")]:
                    real = sheets.get(sname)
                    if real:
                        df = pd.read_excel(fname, sheet_name=real, header=1)
                        df = df.dropna(axis=1, how="all")
                        df = df.dropna(subset=["Lp."])
                        df.columns = [str(c).strip() for c in df.columns]
                        result[key] = df
            except Exception:
                pass
            if any(v is not None for v in [result["men"], result["women"], result["all"]]):
                return result

    # --- próba CSV ---
    # Generuj warianty tagu (S8, S08, S8 -> S08 i odwrotnie)
    snum_local = _season_num(season_tag)
    tag_variants_csv = list(dict.fromkeys([
        season_tag,
        f"S{snum_local}",
        f"S{str(snum_local).zfill(2)}",
    ]))
    mapping = {
        "men":   [f"Ranking FIS M {t}.csv"   for t in tag_variants_csv] +
                 [f"Ranking_FIS_M_{t}.csv"   for t in tag_variants_csv],
        "women": [f"Ranking FIS W {t}.csv"   for t in tag_variants_csv] +
                 [f"Ranking_FIS_W_{t}.csv"   for t in tag_variants_csv],
        "all":   [f"Ranking FIS ALL {t}.csv" for t in tag_variants_csv] +
                 [f"Ranking_FIS_ALL_{t}.csv" for t in tag_variants_csv],
    }
    # szukaj w folderze podanym, jego rodzicu oraz w ./S01-S37/Ranking/ względem roota projektu
    search_dirs = [base, base.parent]
    for root_cand in [base, base.parent, base.parent.parent]:
        for subdir in ["S01-S37/Ranking", "S01-S37\\Ranking"]:
            p = root_cand / subdir
            if p.is_dir() and p not in search_dirs:
                search_dirs.append(p)
    for key, candidates in mapping.items():
        for sd in search_dirs:
            if not sd.is_dir():
                continue
            for cand in candidates:
                p = sd / cand
                if p.is_file():
                    try:
                        df = _read_csv_any(p)
                        df.columns = [str(c).strip() for c in df.columns]
                        result[key] = df
                    except Exception:
                        pass
                    break
            if result[key] is not None:
                break
    return result



class FISStatsFrame(ttk.Frame):
    """
    Zakładka statystyk historycznych Rankingu FIS.
    Dane są wczytywane RĘCZNIE przez użytkownika (lazy loading).

    Zawiera 35 statystyk podzielonych na zakładki tematyczne:
    1.  Historia kraju          – miejsca i punkty przez sezony + wykres
    2.  Top-N krajów            – ranking wg średniej punktów/miejsc
    3.  Porównanie krajów       – dwa kraje na jednym wykresie
    4.  Rekordy / Nr 1          – liderzy sezonów, rekordy wszech czasów
    5.  Passy i serie           – streak lidera, longest run w top-3/top-5
    6.  Awanse i spadki         – największy skok / regres między sezonami
    7.  Stabilność              – odchylenie standardowe miejsc
    8.  Debiutanci / odejścia   – nowe kraje, znikające kraje
    9.  Trendy punktowe         – regresja liniowa (rośnie/spada/stabilny)
    10. Dominacja               – % łącznych punktów zdobytych przez lidera
    11. Macierz sezon×kraj      – tabela krzyżowa miejsc
    12. Sumy historyczne        – łączne punkty ze wszystkich sezonów
    13. Najlepszy/najgorszy sezon– dla każdego kraju
    14. MEN vs WOMEN            – porównanie per kraj
    15. Punkty wg cyklu         – który kraj zarabia najwięcej z danego cyklu
    """

    # ========== INIT ==========

    def __init__(self, parent, data_dir: str | Path = "."):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self._seasons: list[dict] = []
        self._season_tags: list[str] = []
        self._nat_to_kraj: dict[str, str] = {}
        self._loaded = False
        self._build_ui()

    # ========== UI SHELL ==========

    def _build_ui(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(6, 2))

        ttk.Label(bar, text="Folder danych (xlsx/csv):").pack(side="left")
        self.dir_var = tk.StringVar(value=str(self.data_dir))
        ttk.Entry(bar, textvariable=self.dir_var, width=46).pack(side="left", padx=(4, 2))
        ttk.Button(bar, text="…", command=self._browse).pack(side="left")
        ttk.Button(bar, text="▶ Wczytaj sezony", command=self.load_seasons,
                   style="Accent.TButton" if True else "TButton").pack(side="left", padx=(8, 0))

        self.status_lbl = ttk.Label(bar, text="⚠  Kliknij 'Wczytaj sezony' aby załadować dane historyczne.",
                                    foreground="#b06000")
        self.status_lbl.pack(side="left", padx=(10, 0))

        self.inner_nb = ttk.Notebook(self)
        self.inner_nb.pack(fill="both", expand=True, padx=8, pady=4)

        # -- zakładki --
        names = [
            ("tab_history",  "Historia kraju"),
            ("tab_topn",     "Top-N krajów"),
            ("tab_compare",  "Porównanie krajów"),
            ("tab_records",  "Rekordy / Nr 1"),
            ("tab_streaks",  "Passy i serie"),
            ("tab_moves",    "Awanse i spadki"),
            ("tab_stable",   "Stabilność"),
            ("tab_debuts",   "Debiutanci"),
            ("tab_trends",   "Trendy punktowe"),
            ("tab_dom",      "Dominacja"),
            ("tab_matrix",   "Macierz sezon×kraj"),
            ("tab_totals",   "Sumy historyczne"),
            ("tab_bestworst","Najlepszy/najgorszy"),
            ("tab_mvsw",     "MEN vs WOMEN"),
            ("tab_cycles",   "Punkty wg cyklu"),
        ]
        for attr, label in names:
            f = ttk.Frame(self.inner_nb)
            setattr(self, attr, f)
            self.inner_nb.add(f, text=label)

        self._build_tab_history()
        self._build_tab_topn()
        self._build_tab_compare()
        self._build_tab_records()
        self._build_tab_streaks()
        self._build_tab_moves()
        self._build_tab_stable()
        self._build_tab_debuts()
        self._build_tab_trends()
        self._build_tab_dom()
        self._build_tab_matrix()
        self._build_tab_totals()
        self._build_tab_bestworst()
        self._build_tab_mvsw()
        self._build_tab_cycles()

    # ========== BROWSE ==========

    def _browse(self):
        path = filedialog.askdirectory(title="Wybierz folder z danymi rankingów FIS")
        if path:
            self.dir_var.set(path)

    # ========== HELPERS ==========

    def _tv(self, parent, cols, widths=None, height=22):
        """Tworzy Treeview z scrollbarem pionowym."""
        f = ttk.Frame(parent)
        f.pack(fill="both", expand=True, padx=4, pady=4)
        tv = ttk.Treeview(f, columns=cols, show="headings", height=height)
        vsb = ttk.Scrollbar(f, orient="vertical", command=tv.yview)
        hsb = ttk.Scrollbar(f, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tv.pack(fill="both", expand=True)
        for i, c in enumerate(cols):
            w = widths[i] if widths and i < len(widths) else max(80, min(160, 9 * len(str(c))))
            tv.heading(c, text=c, command=lambda _c=c, _tv=tv: self._sort_tv(_tv, _c))
            tv.column(c, width=w, anchor="center")
        return tv

    def _sort_tv(self, tv, col):
        data = [(tv.set(child, col), child) for child in tv.get_children("")]
        try:
            data.sort(key=lambda x: float(x[0].replace(" ", "").replace(",", ".")), reverse=True)
        except Exception:
            data.sort(key=lambda x: x[0])
        for i, (_, child) in enumerate(data):
            tv.move(child, "", i)

    def _clear_tv(self, tv):
        for row in tv.get_children():
            tv.delete(row)

    def _ctrl(self, parent):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=6, pady=4)
        return f

    def _rad(self, parent, var, default="ALL", label="Tabela:"):
        ttk.Label(parent, text=label).pack(side="left")
        var.set(default)
        for val in ("MEN", "WOMEN", "ALL"):
            ttk.Radiobutton(parent, text=val, variable=var, value=val).pack(side="left")

    def _season_cb(self, parent, var, label):
        ttk.Label(parent, text=label).pack(side="left")
        cb = ttk.Combobox(parent, textvariable=var, width=7, state="readonly")
        cb.pack(side="left", padx=(2, 6))
        return cb

    def _nat_cb(self, parent, var, label="Kraj (NAT):"):
        ttk.Label(parent, text=label).pack(side="left")
        cb = ttk.Combobox(parent, textvariable=var, width=8, state="readonly")
        cb.pack(side="left", padx=(2, 8))
        return cb

    def _get_df(self, season_dict, key):
        return season_dict.get(key.lower())

    def _place_pts(self, df, nat):
        if df is None or df.empty or "NAT" not in df.columns:
            return None, None
        row = df[df["NAT"].astype(str).str.upper() == nat.upper()]
        if row.empty:
            return None, None
        r = row.iloc[0]
        place = next((int(float(r[c])) for c in ("Lp.", "LP.", "LP") if c in df.columns and not pd.isna(r.get(c))), None)
        pts   = next((float(r[c]) for c in ("Suma", "SUMA") if c in df.columns and not pd.isna(r.get(c))), None)
        return place, pts

    def _iter_seasons(self, key, from_tag=None, to_tag=None):
        """Iteruje (season_dict) filtrując zakres sezonów."""
        f = _season_num(from_tag) if from_tag else 0
        t = _season_num(to_tag)   if to_tag   else 9999
        return [d for d in self._seasons if f <= _season_num(d["tag"]) <= t]

    def _all_nats(self, key):
        nats = set()
        for d in self._seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            for v in df["NAT"].tolist():
                s = str(v).strip().upper()
                if s and s not in ("NAN", "NONE", ""):
                    nats.add(s)
        return sorted(nats)

    def _no_data(self, widget=None):
        messagebox.showinfo("Statystyki FIS", "Brak danych. Najpierw kliknij 'Wczytaj sezony'.")

    # ========== WCZYTYWANIE ==========

    def load_seasons(self, data_dir=None):
        root = Path(data_dir or self.dir_var.get().strip())
        if not root.is_dir():
            messagebox.showwarning("Statystyki FIS", f"Folder nie istnieje:\n{root}")
            return

        # Foldery do przeskanowania:
        # - S38+: root i podfoldery (np. ./S40/, ./S41/ ...)
        # - S01-S37: ./S01-S37/Ranking/  (względem roota lub roota rodzica)
        scan_roots = [root]
        for base_cand in [root, root.parent, root.parent.parent]:
            for subdir in ["S01-S37/Ranking"]:
                p = base_cand / subdir
                if p.is_dir() and p not in scan_roots:
                    scan_roots.append(p)

        found: dict[int, dict] = {}

        def _scan(scan_root: Path):
            for ext in ("*.xlsx", "*.csv"):
                for fname in scan_root.rglob(ext):
                    fn_up = fname.name.upper()
                    if "RANKING" not in fn_up or "FIS" not in fn_up:
                        continue
                    tag = _season_tag_from_filename(fname.name)
                    if not tag:
                        continue
                    snum = _season_num(tag)
                    if snum not in found:
                        d = _load_season_data(fname.parent, tag)
                        if any(v is not None for v in [d["men"], d["women"], d["all"]]):
                            found[snum] = d

        # Dorzuć foldery sąsiednie (S39, S40 ... leżące obok wskazanego folderu)
        for base_cand in [root, root.parent, root.parent.parent]:
            if base_cand.is_dir():
                for child in base_cand.iterdir():
                    if child.is_dir() and _re.match(r"S\d+", child.name, _re.IGNORECASE):
                        if child not in scan_roots:
                            scan_roots.append(child)

        for sr in scan_roots:
            _scan(sr)

        self._seasons = [found[k] for k in sorted(found.keys())]
        self._season_tags = [d["tag"] for d in self._seasons]
        self._loaded = True

        if not self._seasons:
            self.status_lbl.config(text="Nie znaleziono plików rankingowych.", foreground="#c00")
            return

        self.status_lbl.config(
            text=f"✓  Wczytano {len(self._seasons)} sezon(ów): {self._season_tags[0]} – {self._season_tags[-1]}",
            foreground="#006600")

        # zbierz NAT → Kraj
        for d in self._seasons:
            for key in ("men", "women", "all"):
                df = d.get(key)
                if df is None or "NAT" not in df.columns:
                    continue
                for _, r in df.iterrows():
                    n = str(r.get("NAT", "") or "").strip().upper()
                    k = str(r.get("Kraj", "") or "").strip()
                    if n and k:
                        self._nat_to_kraj[n] = k

        self._refresh_combos()

    def _refresh_combos(self):
        nats = sorted(self._nat_to_kraj.keys())
        tags = self._season_tags
        # historia
        self.hist_nat_cb["values"] = nats
        if nats and not self.hist_nat_var.get():
            self.hist_nat_var.set(nats[0])
        # compare
        self.cmp_nat1_cb["values"] = nats
        self.cmp_nat2_cb["values"] = nats
        if len(nats) >= 2:
            self.cmp_nat1_var.set(nats[0])
            self.cmp_nat2_var.set(nats[1])
        # topn zakres
        self.topn_from_cb["values"] = tags
        self.topn_to_cb["values"]   = tags
        if tags:
            self.topn_from_cb.set(tags[0])
            self.topn_to_cb.set(tags[-1])
        # streaks
        self.streak_tab_var.set("ALL")
        # moves
        self.moves_nat_cb["values"] = nats
        if nats:
            self.moves_nat_var.set(nats[0])
        # stable
        self.stable_from_cb["values"] = tags
        self.stable_to_cb["values"]   = tags
        if tags:
            self.stable_from_cb.set(tags[0])
            self.stable_to_cb.set(tags[-1])
        # debuts
        # trends
        self.trends_nat_cb["values"] = nats
        if nats:
            self.trends_nat_var.set(nats[0])
        # matrix
        self.matrix_from_cb["values"] = tags
        self.matrix_to_cb["values"]   = tags
        if tags:
            self.matrix_from_cb.set(tags[0])
            self.matrix_to_cb.set(tags[-1])
        # bestworst
        self.bw_nat_cb["values"] = nats
        if nats:
            self.bw_nat_var.set(nats[0])
        # cycles
        self.cyc_nat_cb["values"] = nats
        if nats:
            self.cyc_nat_var.set(nats[0])

    # ========== CANVAS HELPERS ==========

    def _line_chart(self, canvas, series, title="", y_label="", invert_y=False, colors=None):
        """
        series: list of { 'label': str, 'points': [(tag, value), ...] }
        colors: list of hex colors (domyślnie automatyczne)
        """
        canvas.delete("all")
        canvas.update_idletasks()
        W = max(canvas.winfo_width(), 400)
        H = max(canvas.winfo_height(), 300)
        PAD_L, PAD_R, PAD_T, PAD_B = 52, 16, 36, 46

        DEFAULT_COLORS = ["#1a7abf", "#e0542a", "#2ca02c", "#9467bd",
                          "#8c564b", "#e377c2", "#bcbd22", "#17becf"]
        colors = colors or DEFAULT_COLORS

        # zbierz wszystkie wartości
        all_vals = [v for s in series for _, v in s["points"] if v is not None]
        all_tags = []
        for s in series:
            for tag, _ in s["points"]:
                if tag not in all_tags:
                    all_tags.append(tag)
        all_tags.sort(key=_season_num)

        if not all_vals or not all_tags:
            canvas.create_text(W // 2, H // 2, text="Brak danych", fill="#888")
            return

        vmin, vmax = min(all_vals), max(all_vals)
        if vmin == vmax:
            vmax += 1
        n = len(all_tags)
        tag_idx = {t: i for i, t in enumerate(all_tags)}

        cw = W - PAD_L - PAD_R
        ch = H - PAD_T - PAD_B

        def cx(tag): return PAD_L + tag_idx.get(tag, 0) * cw / max(n - 1, 1)
        def cy(v):
            frac = (v - vmin) / (vmax - vmin)
            if invert_y:
                frac = 1 - frac
            return PAD_T + (1 - frac) * ch

        # title
        canvas.create_text(W // 2, 14, text=title, font=("TkDefaultFont", 9, "bold"))

        # axes
        canvas.create_line(PAD_L, PAD_T, PAD_L, H - PAD_B, fill="#aaa")
        canvas.create_line(PAD_L, H - PAD_B, W - PAD_R, H - PAD_B, fill="#aaa")

        # y-axis ticks (5 levels)
        for i in range(6):
            v = vmin + i * (vmax - vmin) / 5
            y = cy(v)
            canvas.create_line(PAD_L - 4, y, PAD_L, y, fill="#999")
            canvas.create_text(PAD_L - 6, y, text=f"{v:.0f}", anchor="e",
                                font=("TkDefaultFont", 7))
            canvas.create_line(PAD_L, y, W - PAD_R, y, fill="#f0f0f0")

        # y label
        if y_label:
            canvas.create_text(10, H // 2, text=y_label, angle=90,
                                font=("TkDefaultFont", 8), fill="#666")

        # x ticks
        step = max(1, n // 10)
        for i, tag in enumerate(all_tags):
            if i % step == 0:
                x = cx(tag)
                canvas.create_line(x, H - PAD_B, x, H - PAD_B + 4, fill="#999")
                canvas.create_text(x, H - PAD_B + 14, text=tag,
                                   font=("TkDefaultFont", 7), angle=45, anchor="ne")

        # series
        for si, s in enumerate(series):
            color = colors[si % len(colors)]
            pts = [(cx(tag), cy(v)) for tag, v in s["points"] if v is not None]
            if len(pts) >= 2:
                flat = [c for p in pts for c in p]
                canvas.create_line(*flat, fill=color, width=2)
            for x, y in pts:
                canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline="white")

        # legend
        lx = PAD_L + 4
        for si, s in enumerate(series):
            color = colors[si % len(colors)]
            canvas.create_rectangle(lx, PAD_T + 4, lx + 14, PAD_T + 14, fill=color, outline="")
            canvas.create_text(lx + 18, PAD_T + 9, text=s["label"], anchor="w",
                                font=("TkDefaultFont", 8))
            lx += 14 + 6 + max(60, 7 * len(s["label"]))

    # ==================== TAB 1: Historia kraju ====================

    def _build_tab_history(self):
        t = self.tab_history
        c = self._ctrl(t)
        self.hist_nat_var = tk.StringVar()
        self.hist_nat_cb = self._nat_cb(c, self.hist_nat_var)
        self.hist_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.hist_tab_var)
        ttk.Button(c, text="Pokaż", command=self._show_history).pack(side="left", padx=(10, 0))

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        cols = ["Sezon", "Miejsce", "Suma pkt", "Zmiana miejsc", "Zmiana pkt"]
        self.hist_tv = self._tv(left, cols, [80, 80, 100, 110, 110], height=20)

        right = ttk.Frame(pane)
        pane.add(right, weight=2)
        self.hist_canvas = tk.Canvas(right, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.hist_canvas.pack(fill="both", expand=True, padx=4, pady=4)

    def _show_history(self):
        if not self._loaded:
            return self._no_data()
        nat = self.hist_nat_var.get().strip().upper()
        key = self.hist_tab_var.get().lower()
        if not nat:
            return
        self._clear_tv(self.hist_tv)
        rows = []
        for d in self._seasons:
            p, s = self._place_pts(self._get_df(d, key), nat)
            rows.append({"tag": d["tag"], "place": p, "pts": s})
        prev_p = None
        prev_s = None
        for r in rows:
            p, s = r["place"], r["pts"]
            ch_p = "–" if (p is None or prev_p is None) else (f"↑{prev_p - p}" if prev_p > p else (f"↓{p - prev_p}" if p > prev_p else "="))
            ch_s = "–" if (s is None or prev_s is None) else (f"+{s - prev_s:.0f}" if s >= prev_s else f"{s - prev_s:.0f}")
            self.hist_tv.insert("", "end", values=(
                r["tag"],
                "–" if p is None else p,
                "–" if s is None else f"{s:.1f}",
                ch_p, ch_s
            ))
            if p is not None:
                prev_p = p
            if s is not None:
                prev_s = s
        # wykres miejsc
        pts_data = [(r["tag"], r["place"]) for r in rows]
        self._line_chart(self.hist_canvas,
                         [{"label": nat, "points": pts_data}],
                         title=f"{nat} – miejsca ({key.upper()})",
                         y_label="Miejsce", invert_y=True)

    # ==================== TAB 2: Top-N krajów ====================

    def _build_tab_topn(self):
        t = self.tab_topn
        c = self._ctrl(t)
        self.topn_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.topn_tab_var)
        ttk.Label(c, text="  Top-N:").pack(side="left")
        self.topn_n_var = tk.IntVar(value=10)
        ttk.Spinbox(c, from_=3, to=50, textvariable=self.topn_n_var, width=4).pack(side="left", padx=(2, 8))
        self.topn_from_var = tk.StringVar()
        self.topn_to_var   = tk.StringVar()
        self.topn_from_cb  = self._season_cb(c, self.topn_from_var, "Od:")
        self.topn_to_cb    = self._season_cb(c, self.topn_to_var,   "Do:")
        ttk.Button(c, text="Pokaż", command=self._show_topn).pack(side="left")

        cols = ["Lp.", "Kraj", "NAT", "Śr. pkt", "Śr. miejsce", "Max pkt", "Min miejsce", "Sezony"]
        self.topn_tv = self._tv(t, cols, [40, 140, 55, 90, 100, 90, 100, 70])

    def _show_topn(self):
        if not self._loaded:
            return self._no_data()
        key = self.topn_tab_var.get().lower()
        n   = self.topn_n_var.get()
        seasons = self._iter_seasons(key, self.topn_from_var.get(), self.topn_to_var.get())
        stats = {}
        for d in seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            for _, r in df.iterrows():
                nat = str(r.get("NAT", "") or "").strip().upper()
                if not nat or nat == "NAN":
                    continue
                kraj = str(r.get("Kraj", "") or "").strip()
                if nat not in stats:
                    stats[nat] = {"kraj": kraj or nat, "pts": [], "places": []}
                if nat not in self._nat_to_kraj and kraj:
                    self._nat_to_kraj[nat] = kraj
                for sc in ("Suma", "SUMA"):
                    if sc in df.columns:
                        try:
                            stats[nat]["pts"].append(float(r[sc]))
                        except Exception:
                            pass
                        break
                for pc in ("Lp.", "LP.", "LP"):
                    if pc in df.columns:
                        try:
                            stats[nat]["places"].append(int(float(r[pc])))
                        except Exception:
                            pass
                        break
        rows = []
        for nat, s in stats.items():
            if not s["pts"]:
                continue
            rows.append((nat, s["kraj"],
                         sum(s["pts"]) / len(s["pts"]),
                         sum(s["places"]) / len(s["places"]) if s["places"] else 9999,
                         max(s["pts"]),
                         min(s["places"]) if s["places"] else 9999,
                         len(s["pts"])))
        rows.sort(key=lambda x: -x[2])
        rows = rows[:n]
        self._clear_tv(self.topn_tv)
        for i, (nat, kraj, avg_pts, avg_pl, max_pts, min_pl, cnt) in enumerate(rows, 1):
            self.topn_tv.insert("", "end", values=(
                i, self._nat_to_kraj.get(nat, kraj), nat,
                f"{avg_pts:.1f}", f"{avg_pl:.1f}",
                f"{max_pts:.1f}", min_pl, cnt))

    # ==================== TAB 3: Porównanie krajów ====================

    def _build_tab_compare(self):
        t = self.tab_compare
        c = self._ctrl(t)
        self.cmp_nat1_var = tk.StringVar()
        self.cmp_nat2_var = tk.StringVar()
        self.cmp_nat1_cb  = self._nat_cb(c, self.cmp_nat1_var, "Kraj 1:")
        self.cmp_nat2_cb  = self._nat_cb(c, self.cmp_nat2_var, "Kraj 2:")
        self.cmp_tab_var  = tk.StringVar(value="ALL")
        self._rad(c, self.cmp_tab_var)
        self.cmp_mode_var = tk.StringVar(value="pts")
        ttk.Label(c, text="  Oś Y:").pack(side="left")
        ttk.Radiobutton(c, text="Punkty", variable=self.cmp_mode_var, value="pts").pack(side="left")
        ttk.Radiobutton(c, text="Miejsca", variable=self.cmp_mode_var, value="place").pack(side="left")
        ttk.Button(c, text="Porównaj", command=self._show_compare).pack(side="left", padx=(10, 0))

        self.cmp_canvas = tk.Canvas(t, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.cmp_canvas.pack(fill="both", expand=True, padx=6, pady=4)

    def _show_compare(self):
        if not self._loaded:
            return self._no_data()
        nat1 = self.cmp_nat1_var.get().strip().upper()
        nat2 = self.cmp_nat2_var.get().strip().upper()
        key  = self.cmp_tab_var.get().lower()
        mode = self.cmp_mode_var.get()
        if not nat1 or not nat2:
            return
        pts1 = [(d["tag"], self._place_pts(self._get_df(d, key), nat1)[1 if mode == "pts" else 0])
                for d in self._seasons]
        pts2 = [(d["tag"], self._place_pts(self._get_df(d, key), nat2)[1 if mode == "pts" else 0])
                for d in self._seasons]
        lbl1 = self._nat_to_kraj.get(nat1, nat1)
        lbl2 = self._nat_to_kraj.get(nat2, nat2)
        self._line_chart(
            self.cmp_canvas,
            [{"label": lbl1, "points": pts1}, {"label": lbl2, "points": pts2}],
            title=f"Porównanie: {lbl1} vs {lbl2}  ({key.upper()} – {'Punkty' if mode == 'pts' else 'Miejsca'})",
            y_label="Punkty" if mode == "pts" else "Miejsce",
            invert_y=(mode == "place"))

    # ==================== TAB 4: Rekordy / Nr 1 ====================

    def _build_tab_records(self):
        t = self.tab_records
        c = self._ctrl(t)
        ttk.Button(c, text="Oblicz rekordy", command=self._show_records).pack(side="left")

        cols = ["Kategoria", "Kraj", "NAT", "Wartość", "Sezon"]
        self.rec_tv = self._tv(t, cols, [300, 140, 55, 130, 70])

    def _show_records(self):
        if not self._loaded:
            return self._no_data()
        self._clear_tv(self.rec_tv)
        rows = []
        for key_label, key in [("MEN", "men"), ("WOMEN", "women"), ("ALL", "all")]:
            nr1_count = {}
            best_pts  = {}
            most_top10 = {}
            nr1_list   = []
            for d in self._seasons:
                df = self._get_df(d, key)
                if df is None or "NAT" not in df.columns:
                    continue
                pc = next((c for c in ("Lp.", "LP.", "LP") if c in df.columns), None)
                sc = next((c for c in ("Suma", "SUMA") if c in df.columns), None)
                if pc is None:
                    continue
                tmp = df.copy()
                tmp[pc] = pd.to_numeric(tmp[pc], errors="coerce")
                if sc:
                    tmp[sc] = pd.to_numeric(tmp[sc], errors="coerce")
                top1 = tmp[tmp[pc] == 1]
                if not top1.empty:
                    r = top1.iloc[0]
                    nat  = str(r.get("NAT", "") or "").strip().upper()
                    kraj = self._nat_to_kraj.get(nat, nat)
                    pts  = float(r[sc]) if sc and not pd.isna(r.get(sc)) else 0.0
                    nr1_list.append((d["tag"], nat, kraj, pts))
                    nr1_count[nat] = nr1_count.get(nat, 0) + 1
                for _, r in tmp[tmp[pc] <= 10].iterrows():
                    nat = str(r.get("NAT", "") or "").strip().upper()
                    if nat:
                        most_top10[nat] = most_top10.get(nat, 0) + 1
                if sc:
                    for _, r in tmp.iterrows():
                        nat = str(r.get("NAT", "") or "").strip().upper()
                        try:
                            v = float(r[sc])
                        except Exception:
                            continue
                        if nat not in best_pts or v > best_pts[nat][0]:
                            best_pts[nat] = (v, d["tag"])
            if nr1_count:
                champ = max(nr1_count, key=lambda k: nr1_count[k])
                rows.append((f"{key_label}: Najczęściej na 1. miejscu",
                              self._nat_to_kraj.get(champ, champ), champ,
                              f"{nr1_count[champ]}× razy", "–"))
            if best_pts:
                best = max(best_pts, key=lambda k: best_pts[k][0])
                rows.append((f"{key_label}: Rekordowa suma punktów",
                              self._nat_to_kraj.get(best, best), best,
                              f"{best_pts[best][0]:.1f} pkt", best_pts[best][1]))
            if most_top10:
                top = max(most_top10, key=lambda k: most_top10[k])
                rows.append((f"{key_label}: Najczęściej w top-10",
                              self._nat_to_kraj.get(top, top), top,
                              f"{most_top10[top]} razy", "–"))
            for tag, nat, kraj, pts in nr1_list:
                rows.append((f"{key_label}: Nr 1 sezonu {tag}", kraj, nat, f"{pts:.1f} pkt", tag))
        for row in rows:
            self.rec_tv.insert("", "end", values=row)

    # ==================== TAB 5: Passy i serie ====================

    def _build_tab_streaks(self):
        t = self.tab_streaks
        c = self._ctrl(t)
        self.streak_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.streak_tab_var)
        self.streak_top_var = tk.IntVar(value=3)
        ttk.Label(c, text="  Streak top-N:").pack(side="left")
        ttk.Spinbox(c, from_=1, to=10, textvariable=self.streak_top_var, width=4).pack(side="left", padx=(2, 8))
        ttk.Button(c, text="Oblicz", command=self._show_streaks).pack(side="left")

        cols = ["Kraj", "NAT", "Typ streaka", "Długość", "Sezony (od–do)", "Max pkt w passie"]
        self.streak_tv = self._tv(t, cols, [140, 55, 160, 70, 160, 130])

    def _show_streaks(self):
        if not self._loaded:
            return self._no_data()
        key   = self.streak_tab_var.get().lower()
        top_n = self.streak_top_var.get()
        self._clear_tv(self.streak_tv)

        # zbierz miejsca per kraj per sezon
        nats = self._all_nats(key)
        rows = []
        for nat in nats:
            places_by_season = []
            for d in self._seasons:
                p, s = self._place_pts(self._get_df(d, key), nat)
                places_by_season.append((d["tag"], p, s))

            # Streak na 1. miejscu
            streak1 = self._longest_streak(places_by_season, lambda p: p == 1)
            if streak1:
                rows.append(self._streak_row(nat, "Nr 1 z rzędu", streak1))

            # Streak w top-N
            streakN = self._longest_streak(places_by_season, lambda p: p is not None and p <= top_n)
            if streakN and streakN["len"] >= 2:
                rows.append(self._streak_row(nat, f"Top-{top_n} z rzędu", streakN))

            # Streak poza top-10 (regresja)
            streak_out = self._longest_streak(places_by_season, lambda p: p is None or p > 10)
            if streak_out and streak_out["len"] >= 3:
                rows.append(self._streak_row(nat, "Poza top-10 z rzędu", streak_out))

        rows.sort(key=lambda x: -x[3])
        for row in rows[:60]:
            self.streak_tv.insert("", "end", values=row)

    def _longest_streak(self, data, cond):
        best = None
        cur_start = None
        cur_len   = 0
        cur_pts   = []
        for tag, p, s in data:
            if cond(p):
                if cur_start is None:
                    cur_start = tag
                cur_len += 1
                if s is not None:
                    cur_pts.append(s)
            else:
                if cur_len > 0:
                    if best is None or cur_len > best["len"]:
                        best = {"len": cur_len, "from": cur_start, "to": tag, "max_pts": max(cur_pts) if cur_pts else 0}
                cur_start = None
                cur_len   = 0
                cur_pts   = []
        if cur_len > 0:
            if best is None or cur_len > best["len"]:
                best = {"len": cur_len, "from": cur_start, "to": data[-1][0], "max_pts": max(cur_pts) if cur_pts else 0}
        return best

    def _streak_row(self, nat, label, streak):
        kraj = self._nat_to_kraj.get(nat, nat)
        return (kraj, nat, label, streak["len"],
                f"{streak['from']} – {streak['to']}",
                f"{streak['max_pts']:.0f}")

    # ==================== TAB 6: Awanse i spadki ====================

    def _build_tab_moves(self):
        t = self.tab_moves
        c = self._ctrl(t)
        self.moves_nat_var = tk.StringVar()
        self.moves_nat_cb  = self._nat_cb(c, self.moves_nat_var)
        self.moves_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.moves_tab_var)
        ttk.Button(c, text="Historia awansów", command=self._show_moves_nat).pack(side="left", padx=(8, 4))

        ttk.Separator(c, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Label(c, text="Ranking awansów/spadków:").pack(side="left")
        self.moves_all_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.moves_all_tab_var, label=" ")
        ttk.Button(c, text="Pokaż wszystkich", command=self._show_moves_all).pack(side="left", padx=(4, 0))

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        cols = ["Sezon", "Miejsce", "Zmiana", "Zmiana pkt"]
        self.moves_hist_tv = self._tv(left, cols, [80, 80, 90, 100])

        right = ttk.Frame(pane)
        pane.add(right, weight=2)
        cols2 = ["Kraj", "NAT", "Maks. awans", "W sezonie", "Maks. spadek", "W sezonie "]
        self.moves_all_tv = self._tv(right, cols2, [130, 55, 100, 80, 100, 80])

    def _show_moves_nat(self):
        if not self._loaded:
            return self._no_data()
        nat = self.moves_nat_var.get().strip().upper()
        key = self.moves_tab_var.get().lower()
        self._clear_tv(self.moves_hist_tv)
        prev_p = None
        prev_s = None
        for d in self._seasons:
            p, s = self._place_pts(self._get_df(d, key), nat)
            ch_p = "–"
            ch_s = "–"
            if p is not None and prev_p is not None:
                diff = prev_p - p
                ch_p = f"↑{diff}" if diff > 0 else (f"↓{-diff}" if diff < 0 else "=")
            if s is not None and prev_s is not None:
                ch_s = f"+{s - prev_s:.0f}" if s >= prev_s else f"{s - prev_s:.0f}"
            self.moves_hist_tv.insert("", "end", values=(
                d["tag"], "–" if p is None else p, ch_p, ch_s))
            if p is not None:
                prev_p = p
            if s is not None:
                prev_s = s

    def _show_moves_all(self):
        if not self._loaded:
            return self._no_data()
        key = self.moves_all_tab_var.get().lower()
        self._clear_tv(self.moves_all_tv)
        # best_rise[nat] = (delta, season)
        best_rise  = {}
        best_fall  = {}
        for d in self._seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
        # potrzebujemy dwóch kolejnych sezonów
        for i in range(1, len(self._seasons)):
            prev_d = self._seasons[i - 1]
            cur_d  = self._seasons[i]
            prev_df = self._get_df(prev_d, key)
            cur_df  = self._get_df(cur_d,  key)
            if prev_df is None or cur_df is None:
                continue
            nats = self._all_nats(key)
            for nat in nats:
                pp, _ = self._place_pts(prev_df, nat)
                cp, _ = self._place_pts(cur_df,  nat)
                if pp is None or cp is None:
                    continue
                delta = pp - cp  # dodatni = awans
                if delta > 0:
                    if nat not in best_rise or delta > best_rise[nat][0]:
                        best_rise[nat] = (delta, cur_d["tag"])
                elif delta < 0:
                    if nat not in best_fall or (-delta) > best_fall[nat][0]:
                        best_fall[nat] = (-delta, cur_d["tag"])
        all_nats = set(best_rise) | set(best_fall)
        rows = []
        for nat in all_nats:
            kraj = self._nat_to_kraj.get(nat, nat)
            rise = best_rise.get(nat, (0, "–"))
            fall = best_fall.get(nat, (0, "–"))
            rows.append((kraj, nat, f"+{rise[0]}", rise[1], f"-{fall[0]}", fall[1]))
        rows.sort(key=lambda x: -int(str(x[2]).replace("+", "") or 0))
        for row in rows:
            self.moves_all_tv.insert("", "end", values=row)

    # ==================== TAB 7: Stabilność ====================

    def _build_tab_stable(self):
        t = self.tab_stable
        c = self._ctrl(t)
        self.stable_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.stable_tab_var)
        self.stable_from_var = tk.StringVar()
        self.stable_to_var   = tk.StringVar()
        self.stable_from_cb  = self._season_cb(c, self.stable_from_var, "Od:")
        self.stable_to_cb    = self._season_cb(c, self.stable_to_var,   "Do:")
        ttk.Button(c, text="Oblicz", command=self._show_stable).pack(side="left")

        cols = ["Kraj", "NAT", "Śr. miejsce", "Std. dev. miejsce", "Min miejsce", "Max miejsce",
                "Śr. pkt", "Std. dev. pkt", "Ocena stabilności"]
        self.stable_tv = self._tv(t, cols, [130, 55, 100, 140, 100, 100, 90, 110, 140])

    def _show_stable(self):
        if not self._loaded:
            return self._no_data()
        import math
        key     = self.stable_tab_var.get().lower()
        seasons = self._iter_seasons(key, self.stable_from_var.get(), self.stable_to_var.get())
        self._clear_tv(self.stable_tv)
        stats = {}
        for d in seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            for _, r in df.iterrows():
                nat = str(r.get("NAT", "") or "").strip().upper()
                if not nat or nat == "NAN":
                    continue
                if nat not in stats:
                    stats[nat] = {"places": [], "pts": []}
                for pc in ("Lp.", "LP.", "LP"):
                    if pc in df.columns:
                        try:
                            stats[nat]["places"].append(int(float(r[pc])))
                        except Exception:
                            pass
                        break
                for sc in ("Suma", "SUMA"):
                    if sc in df.columns:
                        try:
                            stats[nat]["pts"].append(float(r[sc]))
                        except Exception:
                            pass
                        break
        rows = []
        for nat, s in stats.items():
            if len(s["places"]) < 2:
                continue
            pl = s["places"]
            pt = s["pts"] if s["pts"] else [0]
            mean_pl = sum(pl) / len(pl)
            std_pl  = math.sqrt(sum((x - mean_pl) ** 2 for x in pl) / len(pl))
            mean_pt = sum(pt) / len(pt)
            std_pt  = math.sqrt(sum((x - mean_pt) ** 2 for x in pt) / len(pt)) if len(pt) > 1 else 0
            # ocena słowna
            if std_pl < 2:
                label = "⭐ Bardzo stabilny"
            elif std_pl < 5:
                label = "Stabilny"
            elif std_pl < 10:
                label = "Umiarkowany"
            else:
                label = "Niestabilny"
            rows.append((nat, self._nat_to_kraj.get(nat, nat),
                         mean_pl, std_pl, min(pl), max(pl), mean_pt, std_pt, label))
        rows.sort(key=lambda x: x[3])
        for _, kraj, mean_pl, std_pl, min_pl, max_pl, mean_pt, std_pt, label in rows:
            self.stable_tv.insert("", "end", values=(
                kraj, _,
                f"{mean_pl:.1f}", f"{std_pl:.2f}",
                min_pl, max_pl,
                f"{mean_pt:.0f}", f"{std_pt:.0f}", label))

    # ==================== TAB 8: Debiutanci / odejścia ====================

    def _build_tab_debuts(self):
        t = self.tab_debuts
        c = self._ctrl(t)
        self.debut_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.debut_tab_var)
        ttk.Button(c, text="Pokaż debiutantów i odejścia", command=self._show_debuts).pack(side="left", padx=(8, 0))

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        ttk.Label(left, text="Debiutanci (pierwsze pojawienie się):").pack(anchor="w", padx=4)
        cols = ["Sezon debiutu", "Kraj", "NAT", "Miejsce debiutu", "Pkt debiutu"]
        self.debut_tv = self._tv(left, cols, [110, 130, 55, 120, 100])

        right = ttk.Frame(pane)
        pane.add(right, weight=1)
        ttk.Label(right, text="Ostatnie pojawienie się (możliwe odejścia):").pack(anchor="w", padx=4)
        cols2 = ["Ostatni sezon", "Kraj", "NAT", "Ostatnie miejsce", "Ostatnie pkt"]
        self.last_tv = self._tv(right, cols2, [110, 130, 55, 120, 100])

    def _show_debuts(self):
        if not self._loaded:
            return self._no_data()
        key = self.debut_tab_var.get().lower()
        self._clear_tv(self.debut_tv)
        self._clear_tv(self.last_tv)
        first_seen = {}
        last_seen  = {}
        for d in self._seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            for _, r in df.iterrows():
                nat = str(r.get("NAT", "") or "").strip().upper()
                if not nat or nat == "NAN":
                    continue
                kraj = self._nat_to_kraj.get(nat, nat)
                p, s = self._place_pts(df, nat)
                if nat not in first_seen:
                    first_seen[nat] = (d["tag"], kraj, p, s)
                last_seen[nat] = (d["tag"], kraj, p, s)
        last_tag = self._season_tags[-1] if self._season_tags else ""
        # debiutanci (nie od pierwszego sezonu)
        first_season = self._season_tags[0] if self._season_tags else ""
        debut_rows = sorted(
            [(nat, info) for nat, info in first_seen.items() if info[0] != first_season],
            key=lambda x: x[1][0])
        for nat, (tag, kraj, p, s) in debut_rows:
            self.debut_tv.insert("", "end", values=(tag, kraj, nat,
                                                    "–" if p is None else p,
                                                    "–" if s is None else f"{s:.0f}"))
        # znikające (ostatni sezon ≠ aktualny)
        gone_rows = sorted(
            [(nat, info) for nat, info in last_seen.items() if info[0] != last_tag],
            key=lambda x: x[1][0], reverse=True)
        for nat, (tag, kraj, p, s) in gone_rows:
            self.last_tv.insert("", "end", values=(tag, kraj, nat,
                                                   "–" if p is None else p,
                                                   "–" if s is None else f"{s:.0f}"))

    # ==================== TAB 9: Trendy punktowe ====================

    def _build_tab_trends(self):
        t = self.tab_trends
        c = self._ctrl(t)
        self.trends_nat_var = tk.StringVar()
        self.trends_nat_cb  = self._nat_cb(c, self.trends_nat_var)
        self.trends_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.trends_tab_var)
        ttk.Button(c, text="Pokaż trend", command=self._show_trend_nat).pack(side="left", padx=(8, 4))
        ttk.Separator(c, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(c, text="Ranking trendów (wszyscy)", command=self._show_trends_all).pack(side="left")

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=2)
        self.trend_canvas = tk.Canvas(left, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.trend_canvas.pack(fill="both", expand=True, padx=4, pady=4)

        right = ttk.Frame(pane)
        pane.add(right, weight=1)
        cols = ["Kraj", "NAT", "Nachylenie", "Trend", "Sezony"]
        self.trends_tv = self._tv(right, cols, [130, 55, 100, 120, 70])

    def _linreg(self, xs, ys):
        """Prosta regresja liniowa, zwraca (slope, intercept)."""
        n = len(xs)
        if n < 2:
            return 0, ys[0] if ys else 0
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num   = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denom = sum((x - mean_x) ** 2 for x in xs)
        slope = num / denom if denom != 0 else 0
        return slope, mean_y - slope * mean_x

    def _show_trend_nat(self):
        if not self._loaded:
            return self._no_data()
        nat = self.trends_nat_var.get().strip().upper()
        key = self.trends_tab_var.get().lower()
        pts_data = [(d["tag"], self._place_pts(self._get_df(d, key), nat)[1])
                    for d in self._seasons]
        valid = [(i, v) for i, (_, v) in enumerate(pts_data) if v is not None]
        if not valid:
            self.trend_canvas.delete("all")
            self.trend_canvas.create_text(200, 150, text="Brak danych", fill="#888")
            return
        xs = [i for i, _ in valid]
        ys = [v for _, v in valid]
        slope, intercept = self._linreg(xs, ys)
        trend_pts = [(pts_data[i][0], slope * i + intercept) for i in range(len(pts_data))]
        lbl = self._nat_to_kraj.get(nat, nat)
        trend_label = "⬆ Rosnący" if slope > 20 else ("⬇ Malejący" if slope < -20 else "➡ Stabilny")
        self._line_chart(
            self.trend_canvas,
            [{"label": f"{lbl} (dane)", "points": pts_data},
             {"label": f"Trend ({trend_label}, slope={slope:.1f})", "points": trend_pts}],
            title=f"Trend punktowy: {lbl} ({key.upper()})",
            y_label="Punkty")

    def _show_trends_all(self):
        if not self._loaded:
            return self._no_data()
        key = self.trends_tab_var.get().lower()
        self._clear_tv(self.trends_tv)
        rows = []
        for nat in self._all_nats(key):
            pts_list = []
            for i, d in enumerate(self._seasons):
                _, s = self._place_pts(self._get_df(d, key), nat)
                if s is not None:
                    pts_list.append((i, s))
            if len(pts_list) < 3:
                continue
            xs = [x for x, _ in pts_list]
            ys = [y for _, y in pts_list]
            slope, _ = self._linreg(xs, ys)
            label = "⬆ Rosnący" if slope > 20 else ("⬇ Malejący" if slope < -20 else "➡ Stabilny")
            rows.append((nat, self._nat_to_kraj.get(nat, nat), slope, label, len(pts_list)))
        rows.sort(key=lambda x: -x[2])
        for nat, kraj, slope, label, cnt in rows:
            self.trends_tv.insert("", "end", values=(kraj, nat, f"{slope:+.1f}", label, cnt))

    # ==================== TAB 10: Dominacja ====================

    def _build_tab_dom(self):
        t = self.tab_dom
        c = self._ctrl(t)
        self.dom_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.dom_tab_var)
        ttk.Button(c, text="Oblicz dominację", command=self._show_dom).pack(side="left", padx=(8, 0))

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        cols = ["Sezon", "Kraj", "NAT", "Pkt lidera", "Suma wszystkich", "% udział"]
        self.dom_tv = self._tv(left, cols, [80, 130, 55, 100, 130, 90])

        right = ttk.Frame(pane)
        pane.add(right, weight=2)
        self.dom_canvas = tk.Canvas(right, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.dom_canvas.pack(fill="both", expand=True, padx=4, pady=4)

    def _show_dom(self):
        if not self._loaded:
            return self._no_data()
        key = self.dom_tab_var.get().lower()
        self._clear_tv(self.dom_tv)
        dom_pts = []
        for d in self._seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            sc = next((c for c in ("Suma", "SUMA") if c in df.columns), None)
            pc = next((c for c in ("Lp.", "LP.", "LP") if c in df.columns), None)
            if sc is None or pc is None:
                continue
            tmp = df.copy()
            tmp[sc] = pd.to_numeric(tmp[sc], errors="coerce").fillna(0)
            tmp[pc] = pd.to_numeric(tmp[pc], errors="coerce")
            total = tmp[sc].sum()
            if total == 0:
                continue
            top1 = tmp[tmp[pc] == 1]
            if top1.empty:
                continue
            r = top1.iloc[0]
            nat  = str(r.get("NAT", "") or "").strip().upper()
            kraj = self._nat_to_kraj.get(nat, nat)
            pts  = float(r[sc])
            pct  = pts / total * 100
            self.dom_tv.insert("", "end", values=(
                d["tag"], kraj, nat, f"{pts:.0f}", f"{total:.0f}", f"{pct:.1f}%"))
            dom_pts.append((d["tag"], pct))
        # wykres % dominacji
        self._line_chart(
            self.dom_canvas,
            [{"label": "% pkt lidera", "points": dom_pts}],
            title="Dominacja lidera (% łącznych punktów)", y_label="%")

    # ==================== TAB 11: Macierz sezon×kraj ====================

    def _build_tab_matrix(self):
        t = self.tab_matrix
        c = self._ctrl(t)
        self.matrix_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.matrix_tab_var)
        self.matrix_from_var = tk.StringVar()
        self.matrix_to_var   = tk.StringVar()
        self.matrix_from_cb  = self._season_cb(c, self.matrix_from_var, "Od:")
        self.matrix_to_cb    = self._season_cb(c, self.matrix_to_var,   "Do:")
        self.matrix_mode_var = tk.StringVar(value="place")
        ttk.Label(c, text="Wartość:").pack(side="left")
        ttk.Radiobutton(c, text="Miejsce", variable=self.matrix_mode_var, value="place").pack(side="left")
        ttk.Radiobutton(c, text="Punkty",  variable=self.matrix_mode_var, value="pts").pack(side="left")
        ttk.Button(c, text="Buduj macierz", command=self._show_matrix).pack(side="left", padx=(8, 0))

        f = ttk.Frame(t)
        f.pack(fill="both", expand=True, padx=4, pady=4)
        self._matrix_frame = f

    def _show_matrix(self):
        if not self._loaded:
            return self._no_data()
        # usuń poprzednią tabelę
        for w in self._matrix_frame.winfo_children():
            w.destroy()

        key     = self.matrix_tab_var.get().lower()
        mode    = self.matrix_mode_var.get()
        seasons = self._iter_seasons(key, self.matrix_from_var.get(), self.matrix_to_var.get())
        tags    = [d["tag"] for d in seasons]
        nats    = self._all_nats(key)

        # buduj macierz
        data = {}
        for d in seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            for _, r in df.iterrows():
                nat = str(r.get("NAT", "") or "").strip().upper()
                p, s = self._place_pts(df, nat)
                val = p if mode == "place" else s
                data[(d["tag"], nat)] = val

        cols = ["Kraj / Sezon"] + tags
        tv = ttk.Treeview(self._matrix_frame, columns=cols, show="headings")
        vsb = ttk.Scrollbar(self._matrix_frame, orient="vertical",   command=tv.yview)
        hsb = ttk.Scrollbar(self._matrix_frame, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tv.pack(fill="both", expand=True)

        tv.heading("Kraj / Sezon", text="Kraj / Sezon")
        tv.column("Kraj / Sezon", width=130, anchor="w")
        for tag in tags:
            tv.heading(tag, text=tag)
            tv.column(tag, width=60, anchor="center")

        # filtruj tylko te kraje, które mają ≥1 wartość
        active_nats = [n for n in nats if any(data.get((t, n)) is not None for t in tags)]
        for nat in active_nats:
            kraj = self._nat_to_kraj.get(nat, nat)
            row_vals = [kraj]
            for tag in tags:
                v = data.get((tag, nat))
                row_vals.append("–" if v is None else (int(v) if mode == "place" else f"{v:.0f}"))
            tv.insert("", "end", values=row_vals)

    # ==================== TAB 12: Sumy historyczne ====================

    def _build_tab_totals(self):
        t = self.tab_totals
        c = self._ctrl(t)
        self.tot_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.tot_tab_var)
        self.tot_from_var = tk.StringVar()
        self.tot_to_var   = tk.StringVar()
        self.tot_from_cb  = self._season_cb(c, self.tot_from_var, "Od:")
        self.tot_to_cb    = self._season_cb(c, self.tot_to_var,   "Do:")
        ttk.Button(c, text="Oblicz sumy", command=self._show_totals).pack(side="left")

        cols = ["Lp.", "Kraj", "NAT", "Suma pkt (hist.)", "Liczba sezonów",
                "Śr. pkt", "Podium (top-3)", "Top-1", "Nigdy poza top-10"]
        self.tot_tv = self._tv(t, cols, [40, 130, 55, 130, 120, 90, 110, 60, 150])

    def _show_totals(self):
        if not self._loaded:
            return self._no_data()
        key     = self.tot_tab_var.get().lower()
        seasons = self._iter_seasons(key, self.tot_from_var.get(), self.tot_to_var.get())
        self._clear_tv(self.tot_tv)
        stats = {}
        for d in seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            for _, r in df.iterrows():
                nat = str(r.get("NAT", "") or "").strip().upper()
                if not nat or nat == "NAN":
                    continue
                p, s = self._place_pts(df, nat)
                if nat not in stats:
                    stats[nat] = {"pts": 0.0, "cnt": 0, "top1": 0, "top3": 0, "always_top10": True}
                if s is not None:
                    stats[nat]["pts"] += s
                    stats[nat]["cnt"] += 1
                if p is not None:
                    if p == 1:
                        stats[nat]["top1"] += 1
                    if p <= 3:
                        stats[nat]["top3"] += 1
                    if p > 10:
                        stats[nat]["always_top10"] = False
                else:
                    stats[nat]["always_top10"] = False
        rows = [(nat, s) for nat, s in stats.items() if s["cnt"] > 0]
        rows.sort(key=lambda x: -x[1]["pts"])
        for i, (nat, s) in enumerate(rows, 1):
            kraj = self._nat_to_kraj.get(nat, nat)
            avg  = s["pts"] / s["cnt"] if s["cnt"] else 0
            always = "✓" if s["always_top10"] else ""
            self.tot_tv.insert("", "end", values=(
                i, kraj, nat,
                f"{s['pts']:.0f}", s["cnt"],
                f"{avg:.0f}", s["top3"], s["top1"], always))

    # ==================== TAB 13: Najlepszy / najgorszy sezon ====================

    def _build_tab_bestworst(self):
        t = self.tab_bestworst
        c = self._ctrl(t)
        self.bw_nat_var = tk.StringVar()
        self.bw_nat_cb  = self._nat_cb(c, self.bw_nat_var)
        self.bw_tab_var = tk.StringVar(value="ALL")
        self._rad(c, self.bw_tab_var)
        ttk.Button(c, text="Pokaż kraj", command=self._show_bw_nat).pack(side="left", padx=(8, 4))
        ttk.Separator(c, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(c, text="Tabela wszystkich krajów", command=self._show_bw_all).pack(side="left")

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        ttk.Label(left, text="Szczegóły dla wybranego kraju:").pack(anchor="w", padx=4)
        cols = ["Sezon", "Miejsce", "Suma pkt", "Ocena"]
        self.bw_detail_tv = self._tv(left, cols, [80, 80, 100, 100])

        right = ttk.Frame(pane)
        pane.add(right, weight=2)
        ttk.Label(right, text="Każdy kraj – najlepszy i najgorszy sezon:").pack(anchor="w", padx=4)
        cols2 = ["Kraj", "NAT", "Najlepszy sezon", "Najl. miejsce", "Najl. pkt",
                 "Najgorszy sezon", "Najg. miejsce", "Najg. pkt"]
        self.bw_all_tv = self._tv(right, cols2, [120, 55, 110, 110, 100, 110, 110, 100])

    def _show_bw_nat(self):
        if not self._loaded:
            return self._no_data()
        nat = self.bw_nat_var.get().strip().upper()
        key = self.bw_tab_var.get().lower()
        self._clear_tv(self.bw_detail_tv)
        rows = []
        for d in self._seasons:
            p, s = self._place_pts(self._get_df(d, key), nat)
            rows.append((d["tag"], p, s))
        if not rows:
            return
        best_p  = min((p for _, p, _ in rows if p is not None), default=None)
        worst_p = max((p for _, p, _ in rows if p is not None), default=None)
        best_s  = max((s for _, _, s in rows if s is not None), default=None)
        for tag, p, s in rows:
            ocena = ""
            if p == best_p:
                ocena = "⭐ Najlepsze miejsce"
            elif p == worst_p:
                ocena = "👎 Najgorsze miejsce"
            if s == best_s:
                ocena = ("⭐ " if ocena else "") + "Max pkt"
            self.bw_detail_tv.insert("", "end", values=(
                tag, "–" if p is None else p,
                "–" if s is None else f"{s:.0f}", ocena))

    def _show_bw_all(self):
        if not self._loaded:
            return self._no_data()
        key = self.bw_tab_var.get().lower()
        self._clear_tv(self.bw_all_tv)
        bests  = {}
        worsts = {}
        for d in self._seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            for _, r in df.iterrows():
                nat = str(r.get("NAT", "") or "").strip().upper()
                if not nat or nat == "NAN":
                    continue
                p, s = self._place_pts(df, nat)
                if p is None:
                    continue
                if nat not in bests or p < bests[nat][1]:
                    bests[nat]  = (d["tag"], p, s)
                if nat not in worsts or p > worsts[nat][1]:
                    worsts[nat] = (d["tag"], p, s)
        nats = sorted(set(bests) | set(worsts))
        for nat in nats:
            kraj = self._nat_to_kraj.get(nat, nat)
            b = bests.get(nat,  ("–", "–", "–"))
            w = worsts.get(nat, ("–", "–", "–"))
            self.bw_all_tv.insert("", "end", values=(
                kraj, nat,
                b[0], b[1], "–" if b[2] is None else f"{b[2]:.0f}",
                w[0], w[1], "–" if w[2] is None else f"{w[2]:.0f}"))

    # ==================== TAB 14: MEN vs WOMEN ====================

    def _build_tab_mvsw(self):
        t = self.tab_mvsw
        c = self._ctrl(t)
        self.mvsw_nat_var = tk.StringVar()
        self.mvsw_nat_cb  = self._nat_cb(c, self.mvsw_nat_var)
        self.mvsw_mode_var = tk.StringVar(value="pts")
        ttk.Label(c, text="Oś Y:").pack(side="left")
        ttk.Radiobutton(c, text="Punkty",  variable=self.mvsw_mode_var, value="pts").pack(side="left")
        ttk.Radiobutton(c, text="Miejsca", variable=self.mvsw_mode_var, value="place").pack(side="left")
        ttk.Button(c, text="Pokaż kraj", command=self._show_mvsw_nat).pack(side="left", padx=(8, 4))
        ttk.Separator(c, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(c, text="Tabela wszystkich", command=self._show_mvsw_all).pack(side="left")

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=2)
        self.mvsw_canvas = tk.Canvas(left, bg="white", highlightthickness=1, highlightbackground="#ccc")
        self.mvsw_canvas.pack(fill="both", expand=True, padx=4, pady=4)

        right = ttk.Frame(pane)
        pane.add(right, weight=1)
        cols = ["Kraj", "NAT", "Śr. pkt M", "Śr. pkt W", "Przewaga M/W", "Lepszy w sezonach"]
        self.mvsw_tv = self._tv(right, cols, [120, 55, 90, 90, 110, 140])

    def _show_mvsw_nat(self):
        if not self._loaded:
            return self._no_data()
        nat  = self.mvsw_nat_var.get().strip().upper()
        mode = self.mvsw_mode_var.get()
        idx  = 1 if mode == "pts" else 0
        pts_m = [(d["tag"], self._place_pts(self._get_df(d, "men"),   nat)[idx]) for d in self._seasons]
        pts_w = [(d["tag"], self._place_pts(self._get_df(d, "women"), nat)[idx]) for d in self._seasons]
        lbl = self._nat_to_kraj.get(nat, nat)
        self._line_chart(
            self.mvsw_canvas,
            [{"label": f"{lbl} MEN",   "points": pts_m},
             {"label": f"{lbl} WOMEN", "points": pts_w}],
            title=f"{lbl} – MEN vs WOMEN ({'Punkty' if mode == 'pts' else 'Miejsca'})",
            y_label="Punkty" if mode == "pts" else "Miejsce",
            invert_y=(mode == "place"),
            colors=["#1a7abf", "#e0542a"])

    def _show_mvsw_all(self):
        if not self._loaded:
            return self._no_data()
        self._clear_tv(self.mvsw_tv)
        rows = []
        for nat in self._all_nats("all"):
            m_pts = [self._place_pts(self._get_df(d, "men"),   nat)[1] for d in self._seasons]
            w_pts = [self._place_pts(self._get_df(d, "women"), nat)[1] for d in self._seasons]
            m_valid = [v for v in m_pts if v is not None]
            w_valid = [v for v in w_pts if v is not None]
            if not m_valid and not w_valid:
                continue
            avg_m = sum(m_valid) / len(m_valid) if m_valid else 0
            avg_w = sum(w_valid) / len(w_valid) if w_valid else 0
            diff  = avg_m - avg_w
            label = f"MEN +{diff:.0f}" if diff > 0 else (f"WOMEN +{-diff:.0f}" if diff < 0 else "Równo")
            m_better = sum(1 for mv, wv in zip(m_pts, w_pts) if mv is not None and wv is not None and mv > wv)
            rows.append((nat, self._nat_to_kraj.get(nat, nat), avg_m, avg_w, label, f"MEN w {m_better} sezonach"))
        rows.sort(key=lambda x: -(x[2] + x[3]))
        for nat, kraj, avg_m, avg_w, label, detail in rows:
            self.mvsw_tv.insert("", "end", values=(
                kraj, nat, f"{avg_m:.0f}", f"{avg_w:.0f}", label, detail))

    # ==================== TAB 15: Punkty wg cyklu ====================

    def _build_tab_cycles(self):
        t = self.tab_cycles
        c = self._ctrl(t)
        self.cyc_nat_var = tk.StringVar()
        self.cyc_nat_cb  = self._nat_cb(c, self.cyc_nat_var)
        self.cyc_sex_var = tk.StringVar(value="M")
        ttk.Label(c, text="Płeć:").pack(side="left")
        ttk.Radiobutton(c, text="MEN",   variable=self.cyc_sex_var, value="M").pack(side="left")
        ttk.Radiobutton(c, text="WOMEN", variable=self.cyc_sex_var, value="W").pack(side="left")
        ttk.Button(c, text="Pokaż kraj", command=self._show_cycles_nat).pack(side="left", padx=(8, 4))
        ttk.Separator(c, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(c, text="Ranking cyklu (wszyscy)", command=self._show_cycles_rank).pack(side="left")

        self.cyc_cycle_var = tk.StringVar()
        self._season_cb(c, self.cyc_cycle_var, "  Cykl:")
        # wypełnimy listę cykli po wczytaniu danych

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        ttk.Label(left, text="Punkty z cykli dla wybranego kraju (suma sezonów):").pack(anchor="w", padx=4)
        cols = ["Cykl", "Suma pkt [T]", "Suma pkt [I]", "Razem", "Sezony"]
        self.cyc_nat_tv = self._tv(left, cols, [90, 100, 100, 90, 70])

        right = ttk.Frame(pane)
        pane.add(right, weight=1)
        ttk.Label(right, text="Ranking krajów wg wybranego cyklu:").pack(anchor="w", padx=4)
        cols2 = ["Lp.", "Kraj", "NAT", "Suma pkt z cyklu", "Sezony"]
        self.cyc_rank_tv = self._tv(right, cols2, [40, 130, 55, 130, 70])

    def _cycle_cols(self, df, sex):
        """Zwraca listę cykli (np. WC, GP, COC...) dostępnych w df dla danej płci."""
        suffix = f"-{sex} [T]"
        return [c.replace(suffix, "") for c in df.columns if c.upper().endswith(suffix.upper())]

    def _show_cycles_nat(self):
        if not self._loaded:
            return self._no_data()
        nat = self.cyc_nat_var.get().strip().upper()
        sex = self.cyc_sex_var.get()
        key = "men" if sex == "M" else "women"
        self._clear_tv(self.cyc_nat_tv)
        totals = {}
        for d in self._seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            rows_nat = df[df["NAT"].astype(str).str.upper() == nat]
            if rows_nat.empty:
                continue
            r = rows_nat.iloc[0]
            for cyc in self._cycle_cols(df, sex):
                col_t = f"{cyc}-{sex} [T]"
                col_i = f"{cyc}-{sex} [I]"
                vt = float(r[col_t]) if col_t in df.columns and not pd.isna(r.get(col_t)) else 0.0
                vi = float(r[col_i]) if col_i in df.columns and not pd.isna(r.get(col_i)) else 0.0
                if cyc not in totals:
                    totals[cyc] = {"T": 0.0, "I": 0.0, "cnt": 0}
                totals[cyc]["T"]   += vt
                totals[cyc]["I"]   += vi
                totals[cyc]["cnt"] += 1
        rows = [(cyc, d["T"], d["I"], d["T"] + d["I"], d["cnt"])
                for cyc, d in totals.items()]
        rows.sort(key=lambda x: -x[3])
        for cyc, t, i, total, cnt in rows:
            self.cyc_nat_tv.insert("", "end", values=(cyc, f"{t:.1f}", f"{i:.1f}", f"{total:.1f}", cnt))

        # aktualizuj combobox cykli
        all_cycles = sorted(set(c for d in self._seasons
                                for df_key in (("men" if sex == "M" else "women"),)
                                for df in (self._get_df(d, df_key),)
                                if df is not None
                                for c in self._cycle_cols(df, sex)))
        self.cyc_cycle_var.set(all_cycles[0] if all_cycles else "")

    def _show_cycles_rank(self):
        if not self._loaded:
            return self._no_data()
        cyc = self.cyc_cycle_var.get().strip()
        sex = self.cyc_sex_var.get()
        key = "men" if sex == "M" else "women"
        if not cyc:
            messagebox.showinfo("Cykl", "Najpierw kliknij 'Pokaż kraj' aby załadować listę cykli.")
            return
        self._clear_tv(self.cyc_rank_tv)
        col_t = f"{cyc}-{sex} [T]"
        col_i = f"{cyc}-{sex} [I]"
        totals = {}
        for d in self._seasons:
            df = self._get_df(d, key)
            if df is None or "NAT" not in df.columns:
                continue
            for _, r in df.iterrows():
                nat = str(r.get("NAT", "") or "").strip().upper()
                if not nat or nat == "NAN":
                    continue
                vt = float(r[col_t]) if col_t in df.columns and not pd.isna(r.get(col_t)) else 0.0
                vi = float(r[col_i]) if col_i in df.columns and not pd.isna(r.get(col_i)) else 0.0
                if nat not in totals:
                    totals[nat] = {"pts": 0.0, "cnt": 0}
                totals[nat]["pts"] += vt + vi
                totals[nat]["cnt"] += 1
        rows = [(nat, d["pts"], d["cnt"]) for nat, d in totals.items() if d["pts"] > 0]
        rows.sort(key=lambda x: -x[1])
        for i, (nat, pts, cnt) in enumerate(rows, 1):
            kraj = self._nat_to_kraj.get(nat, nat)
            self.cyc_rank_tv.insert("", "end", values=(i, kraj, nat, f"{pts:.1f}", cnt))

    # ==================== SYNC (bez auto-odświeżania) ====================

    def sync_from_ranking(self, df_men, df_women, df_all, season_tag):
        """
        Wywoływane z reload_all() po każdym wczytaniu sezonu.
        Dodaje/aktualizuje dane bieżącego sezonu w cache TYLKO — nie odświeża żadnych widoków.
        Użytkownik musi ręcznie kliknąć 'Wczytaj sezony' lub przyciski w zakładkach.
        """
        snum = _season_num(season_tag)
        new_entry = {"men": df_men, "women": df_women, "all": df_all, "tag": season_tag}
        for i, d in enumerate(self._seasons):
            if _season_num(d["tag"]) == snum:
                self._seasons[i] = new_entry
                break
        else:
            self._seasons.append(new_entry)
            self._seasons.sort(key=lambda d: _season_num(d["tag"]))
        self._season_tags = [d["tag"] for d in self._seasons]
        for df in (df_men, df_women, df_all):
            if df is None or df.empty or "NAT" not in df.columns:
                continue
            for _, r in df.iterrows():
                n = str(r.get("NAT", "") or "").strip().upper()
                k = str(r.get("Kraj", "") or "").strip()
                if n and k:
                    self._nat_to_kraj[n] = k
        self._loaded = True
        self._refresh_combos()
        self.status_lbl.config(
            text=(f"✓  Dane bieżącego sezonu ({season_tag}) gotowe. "
                  f"Wczytano łącznie {len(self._seasons)} sezon(ów). "
                  "Kliknij 'Wczytaj sezony' dla pełnej historii."),
            foreground="#006600")

# =====================================================================
# ZAKŁADKA: Ligi juniorskie (JC / MC / PC / QC / TC / AC / BC / DC)
# =====================================================================

# Kolejność lig od najwyższej do najniższej
_JUN_LEAGUES   = ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]
# Liczba krajów spadających/awansujących
_JUN_PROMOTIONS = {
    "JC": 3,   # 3 awansuje z MC do JC (i 3 spada z JC do MC)
    "MC": 4,
    "PC": 4,
    "QC": 4,
    "TC": 4,
    "AC": 4,
    "BC": 4,
    "DC": 4,   # najniższa – brak spadku
}


def _read_nations_xlsx_sheet(fpath: Path, sheet: str) -> pd.DataFrame | None:
    """
    Wczytuje tabelę krajów z arkusza xlsx (format jak Klasyfikacje_SXX.xlsx).
    Tabela krajów zaczyna się od kolumny 7 z nagłówkiem w wierszu 1 (index=1 po header=1).
    Zwraca df z kolumnami: Lp., NATION, NAT, PTS
    """
    try:
        df = pd.read_excel(fpath, sheet_name=sheet, header=1)
        # Tabela krajów leży w kolumnach 7,8,9,10 (0-indexed)
        sub = df.iloc[:, 7:12].copy()
        sub.columns = ["Lp.", "NATION", "NAT", "PTS", "_extra"][:sub.shape[1]]
        if "_extra" in sub.columns:
            sub = sub.drop(columns=["_extra"])
        sub = sub.dropna(subset=["Lp."])
        sub["Lp."] = pd.to_numeric(sub["Lp."], errors="coerce")
        sub = sub[sub["Lp."].notna()].copy()
        sub["Lp."]  = sub["Lp."].astype(int)
        sub["PTS"]  = pd.to_numeric(sub["PTS"], errors="coerce").fillna(0)
        sub["NAT"]  = sub["NAT"].astype(str).str.strip().str.upper()
        sub["NATION"] = sub["NATION"].astype(str).str.strip()
        return sub.reset_index(drop=True)
    except Exception:
        return None


def _read_nations_csv(fpath: Path) -> pd.DataFrame | None:
    """
    Wczytuje tabelę krajów z pliku CSV (format: LP., NATION, NAT, PTS).
    """
    try:
        df = pd.read_csv(fpath, sep=None, engine="python", encoding="utf-8-sig")
        df.columns = [str(c).strip().upper() for c in df.columns]
        rename = {}
        for c in df.columns:
            if c in ("LP.", "LP", "LP..1"):
                rename[c] = "Lp."
            elif c in ("NATION",):
                rename[c] = "NATION"
            elif c in ("NAT", "NAT.1"):
                rename[c] = "NAT"
            elif c in ("PTS", "PTS.1"):
                rename[c] = "PTS"
        df = df.rename(columns=rename)
        for col in ("Lp.", "NATION", "NAT", "PTS"):
            if col not in df.columns:
                return None
        df["Lp."] = pd.to_numeric(df["Lp."], errors="coerce")
        df = df[df["Lp."].notna()].copy()
        df["Lp."]  = df["Lp."].astype(int)
        df["PTS"]  = pd.to_numeric(df["PTS"], errors="coerce").fillna(0)
        df["NAT"]  = df["NAT"].astype(str).str.strip().str.upper()
        df["NATION"] = df["NATION"].astype(str).str.strip()
        return df.reset_index(drop=True)
    except Exception:
        return None


def _is_klasyfikacje_xlsx(fname: Path, season_tag: str) -> bool:
    """
    Sprawdza czy plik xlsx to plik z klasyfikacjami dla danego sezonu.
    Obsługuje wzorce:
      S01-S16:  "Klasyfikacje S01.xlsx", "Klasyfikacje S16.xlsx"
      S17-S37:  "Klasyfikacje2 S27 — kopia.xlsx", "Klasyfikacje2 S36 — kopia.xlsx"
      S38+:     "Klasyfikacje_S40.xlsx" (lub inne warianty z podkreślnikiem)
    Obsługuje warianty z/bez zera wiodącego (S8 == S08).
    """
    fn_up  = fname.name.upper()
    if "KLASYFIKACJE" not in fn_up:
        return False
    snum_local = _season_num(season_tag)
    tag_variants = {season_tag.upper(), f"S{snum_local}", f"S{str(snum_local).zfill(2)}"}
    return any(v in fn_up for v in tag_variants)


def _load_junior_season(folder: Path, season_tag: str) -> dict:
    """
    Wczytuje dane juniorskie dla jednego sezonu.
    Obsługuje:
      S01-S16:  Klasyfikacje SXX.xlsx         (folder ./S01-S37/Klasyfikacje/)
      S17-S37:  Klasyfikacje2 SXX — kopia.xlsx (folder ./S01-S37/Klasyfikacje/)
      S38+:     SXX_JC-M__nations.csv          (folder ./SXX/)
    """
    result: dict = {"tag": season_tag, "M": {}, "W": {}}
    snum_str = season_tag.upper()  # "S40"

    # --- próba xlsx (szukaj w podanym folderze i jego rodzicu) ---
    for search_dir in [folder, folder.parent]:
        if not search_dir.is_dir():
            continue
        for fname in search_dir.glob("*.xlsx"):
            if not _is_klasyfikacje_xlsx(fname, season_tag):
                continue
            try:
                xl = pd.ExcelFile(fname)
                sheets = {s.upper(): s for s in xl.sheet_names}
                for league in _JUN_LEAGUES:
                    for sex in ("M", "W"):
                        sheet_key = f"{league}-{sex}"
                        real = sheets.get(sheet_key)
                        if real:
                            df = _read_nations_xlsx_sheet(fname, real)
                            if df is not None and not df.empty:
                                result[sex][league] = df
            except Exception:
                pass
        if any(v is not None for v in result["M"].values()) or any(v is not None for v in result["W"].values()):
            return result

    # --- próba CSV ---
    # wzorzec: SXX_JC-M__nations.csv  lub  SXX_JC-W__nations.csv
    # Warianty tagu: S8, S08 itp.
    snum_local = _season_num(season_tag)
    tag_variants_set = {snum_str, f"S{snum_local}", f"S{str(snum_local).zfill(2)}"}

    for search_dir in [folder, folder.parent]:
        if not search_dir.is_dir():
            continue
        for fname in search_dir.glob("*.csv"):
            fn_up = fname.name.upper()
            if "NATIONS" not in fn_up:
                continue
            if not any(v in fn_up for v in tag_variants_set):
                continue
            m = _re.search(r"([A-Z]{2,3})-([MW])__NATIONS", fn_up)
            if not m:
                continue
            league = m.group(1)
            sex    = m.group(2)
            if league not in _JUN_LEAGUES:
                continue
            df = _read_nations_csv(fname)
            if df is not None and not df.empty:
                result[sex][league] = df

    return result


def _overall_place(league: str, place_in_league: int,
                   league_sizes: dict[str, int]) -> int:
    """
    Oblicza miejsce ogólne: suma krajów w ligach wyższych + miejsce w lidze.
    league_sizes: { "JC": 20, "MC": 20, "PC": 28, ... }
    """
    league_idx = _JUN_LEAGUES.index(league)
    offset = sum(league_sizes.get(l, 0) for l in _JUN_LEAGUES[:league_idx])
    return offset + place_in_league


class JuniorLeaguesFrame(ttk.Frame):
    """
    Zakładka statystyk lig juniorskich.
    Obsługuje JC / MC / PC / QC / TC / AC / BC / DC, podział M/W,
    awanse i spadki, miejsce w lidze i ogólne.
    """

    _LEAGUE_COLORS = {
        "JC": "#FFD700",   # złoty
        "MC": "#C0C0C0",   # srebrny
        "PC": "#CD7F32",   # brązowy
        "QC": "#6699cc",
        "TC": "#66bb66",
        "AC": "#dd9933",
        "BC": "#cc6666",
        "DC": "#999999",
    }

    def __init__(self, parent, data_dir: str | Path = "."):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self._seasons: list[dict] = []   # lista z _load_junior_season
        self._season_tags: list[str] = []
        self._nat_to_nation: dict[str, str] = {}
        self._loaded = False
        self._build_ui()

    # ==================== UI ====================

    def _build_ui(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(6, 2))

        ttk.Label(bar, text="Folder danych:").pack(side="left")
        self.dir_var = tk.StringVar(value=str(self.data_dir))
        ttk.Entry(bar, textvariable=self.dir_var, width=46).pack(side="left", padx=(4, 2))
        ttk.Button(bar, text="…", command=self._browse).pack(side="left")
        ttk.Button(bar, text="▶ Wczytaj sezony", command=self.load_seasons).pack(side="left", padx=(8, 0))

        self.status_lbl = ttk.Label(
            bar,
            text="⚠  Kliknij 'Wczytaj sezony' aby załadować dane lig juniorskich.",
            foreground="#b06000")
        self.status_lbl.pack(side="left", padx=(10, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=4)
        self.inner_nb = nb

        tabs = [
            ("tab_current",  "Bieżące miejsce"),
            ("tab_history",  "Historia kraju"),
            ("tab_overview", "Przegląd sezonu"),
            ("tab_promotions","Awanse / Spadki"),
            ("tab_overall",  "Ranking ogólny"),
            ("tab_domination","Dominacja ligi"),
        ]
        for attr, label in tabs:
            f = ttk.Frame(nb)
            setattr(self, attr, f)
            nb.add(f, text=label)

        self._build_current()
        self._build_history()
        self._build_overview()
        self._build_promotions()
        self._build_overall()
        self._build_domination()

    def _browse(self):
        p = filedialog.askdirectory(title="Wybierz folder z danymi")
        if p:
            self.dir_var.set(p)

    # ==================== HELPERS ====================

    def _tv(self, parent, cols, widths=None, height=22):
        f = ttk.Frame(parent)
        f.pack(fill="both", expand=True, padx=4, pady=4)
        tv = ttk.Treeview(f, columns=cols, show="headings", height=height)
        vsb = ttk.Scrollbar(f, orient="vertical",   command=tv.yview)
        hsb = ttk.Scrollbar(f, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tv.pack(fill="both", expand=True)
        for i, c in enumerate(cols):
            w = widths[i] if widths and i < len(widths) else max(70, 8 * len(str(c)))
            tv.heading(c, text=c)
            tv.column(c, width=w, anchor="center")
        return tv

    def _ctrl(self, parent):
        f = ttk.Frame(parent)
        f.pack(fill="x", padx=6, pady=4)
        return f

    def _clear(self, tv):
        for r in tv.get_children():
            tv.delete(r)

    def _nat_cb(self, parent, var, label="Kraj (NAT):"):
        ttk.Label(parent, text=label).pack(side="left")
        cb = ttk.Combobox(parent, textvariable=var, width=8, state="readonly")
        cb.pack(side="left", padx=(2, 8))
        return cb

    def _season_cb(self, parent, var, label):
        ttk.Label(parent, text=label).pack(side="left")
        cb = ttk.Combobox(parent, textvariable=var, width=7, state="readonly")
        cb.pack(side="left", padx=(2, 6))
        return cb

    def _no_data(self):
        messagebox.showinfo("Ligi juniorskie", "Brak danych. Najpierw kliknij 'Wczytaj sezony'.")

    def _get_df(self, season_dict: dict, league: str, sex: str) -> pd.DataFrame | None:
        return season_dict.get(sex, {}).get(league)

    def _league_sizes(self, season_dict: dict, sex: str) -> dict[str, int]:
        return {lg: len(season_dict[sex][lg]) for lg in _JUN_LEAGUES if lg in season_dict[sex] and season_dict[sex][lg] is not None}

    def _place_in_league(self, season_dict: dict, league: str, sex: str, nat: str) -> tuple[int | None, float | None]:
        df = self._get_df(season_dict, league, sex)
        if df is None or df.empty:
            return None, None
        row = df[df["NAT"].str.upper() == nat.upper()]
        if row.empty:
            return None, None
        r = row.iloc[0]
        return int(r["Lp."]), float(r["PTS"])

    def _find_country(self, season_dict: dict, sex: str, nat: str) -> tuple[str | None, int | None, float | None, int | None]:
        """
        Szuka kraju we wszystkich ligach.
        Zwraca (league, place_in_league, pts, overall_place) lub (None,None,None,None)
        """
        sizes = self._league_sizes(season_dict, sex)
        for lg in _JUN_LEAGUES:
            p, pts = self._place_in_league(season_dict, lg, sex, nat)
            if p is not None:
                overall = _overall_place(lg, p, sizes)
                return lg, p, pts, overall
        return None, None, None, None

    def _all_nats(self, sex: str) -> list[str]:
        nats = set()
        for d in self._seasons:
            for lg in _JUN_LEAGUES:
                df = self._get_df(d, lg, sex)
                if df is not None and "NAT" in df.columns:
                    for v in df["NAT"].tolist():
                        s = str(v).strip().upper()
                        if s and s not in ("NAN", "NONE", ""):
                            nats.add(s)
        return sorted(nats)

    # ==================== WCZYTYWANIE ====================

    def load_seasons(self, data_dir=None):
        root = Path(data_dir or self.dir_var.get().strip())
        if not root.is_dir():
            messagebox.showwarning("Ligi juniorskie", f"Folder nie istnieje:\n{root}")
            return

        found: dict[int, dict] = {}

        def _scan(d: Path):
            # xlsx z Klasyfikacjami
            for fname in d.rglob("*.xlsx"):
                fn_up = fname.name.upper()
                if "KLASYFIKACJE" not in fn_up:
                    continue
                tag = _season_tag_from_filename(fname.name)
                if not tag:
                    continue
                snum = _season_num(tag)
                if snum not in found:
                    s = _load_junior_season(fname.parent, tag)
                    if any(v is not None for v in s["M"].values()) or any(v is not None for v in s["W"].values()):
                        found[snum] = s

            # CSV nations
            for fname in d.rglob("*.csv"):
                fn_up = fname.name.upper()
                if "NATIONS" not in fn_up:
                    continue
                tag = _season_tag_from_filename(fname.name)
                if not tag:
                    continue
                snum = _season_num(tag)
                if snum not in found:
                    s = _load_junior_season(fname.parent, tag)
                    if any(v is not None for v in s["M"].values()) or any(v is not None for v in s["W"].values()):
                        found[snum] = s

        # Foldery do przeskanowania:
        # - S01-S37: ./S01-S37/Klasyfikacje/
        # - S38+: wszystkie foldery SXX obok wskazanego folderu
        scan_roots = [root]
        for base_cand in [root, root.parent, root.parent.parent]:
            # stare sezony
            for subdir in ["S01-S37/Klasyfikacje"]:
                p = base_cand / subdir
                if p.is_dir() and p not in scan_roots:
                    scan_roots.append(p)
            # nowe sezony – podfoldery o nazwie SXX
            if base_cand.is_dir():
                for child in base_cand.iterdir():
                    if child.is_dir() and _re.match(r"^S\d+$", child.name, _re.IGNORECASE):
                        if child not in scan_roots:
                            scan_roots.append(child)
        for sr in scan_roots:
            _scan(sr)

        self._seasons = [found[k] for k in sorted(found.keys())]
        self._season_tags = [d["tag"] for d in self._seasons]
        self._loaded = True

        if not self._seasons:
            self.status_lbl.config(text="Nie znaleziono danych juniorskich.", foreground="#c00")
            return

        # zbierz NAT → NATION
        for d in self._seasons:
            for sex in ("M", "W"):
                for lg in _JUN_LEAGUES:
                    df = self._get_df(d, lg, sex)
                    if df is None:
                        continue
                    for _, r in df.iterrows():
                        n = str(r.get("NAT", "") or "").strip().upper()
                        k = str(r.get("NATION", "") or "").strip()
                        if n and k:
                            self._nat_to_nation[n] = k

        self.status_lbl.config(
            text=f"✓  Wczytano {len(self._seasons)} sezon(ów): {self._season_tags[0]} – {self._season_tags[-1]}",
            foreground="#006600")
        self._refresh_combos()

    def _refresh_combos(self):
        tags = self._season_tags
        for cb, var in [(self.cur_season_cb, self.cur_season_var),
                        (self.ov_season_cb,  self.ov_season_var),
                        (self.prom_season_cb, self.prom_season_var)]:
            cb["values"] = tags
            if tags:
                var.set(tags[-1])

        for sex in ("M", "W"):
            nats = self._all_nats(sex)
            for cb, var, s in [(self.hist_nat_cb_m, self.hist_nat_var_m, "M"),
                               (self.hist_nat_cb_w, self.hist_nat_var_w, "W")]:
                if s == sex:
                    cb["values"] = nats
                    if nats and not var.get():
                        var.set(nats[0])

        # overall
        for cb, var in [(self.overall_from_cb, self.overall_from_var),
                        (self.overall_to_cb,   self.overall_to_var)]:
            cb["values"] = tags
            if tags:
                var.set(tags[0] if cb == self.overall_from_cb else tags[-1])

    # ==================== TAB 1: Bieżące miejsce ====================

    def _build_current(self):
        t = self.tab_current
        c = self._ctrl(t)
        ttk.Label(c, text="Sezon:").pack(side="left")
        self.cur_season_var = tk.StringVar()
        self.cur_season_cb  = ttk.Combobox(c, textvariable=self.cur_season_var, width=7, state="readonly")
        self.cur_season_cb.pack(side="left", padx=(2, 8))
        ttk.Button(c, text="Pokaż", command=self._show_current).pack(side="left")

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        ttk.Label(left, text="MEN", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", padx=4)
        cols = ["Liga", "Kraj", "NAT", "Miejsce w lidze", "Miejsce ogólne", "Punkty", "Status"]
        self.cur_tv_m = self._tv(left, cols, [50, 140, 50, 120, 120, 90, 120])

        right = ttk.Frame(pane)
        pane.add(right, weight=1)
        ttk.Label(right, text="WOMEN", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", padx=4)
        self.cur_tv_w = self._tv(right, cols, [50, 140, 50, 120, 120, 90, 120])

    def _show_current(self):
        if not self._loaded:
            return self._no_data()
        tag = self.cur_season_var.get()
        d = next((x for x in self._seasons if x["tag"] == tag), None)
        if d is None:
            return
        for tv, sex in [(self.cur_tv_m, "M"), (self.cur_tv_w, "W")]:
            self._clear(tv)
            sizes = self._league_sizes(d, sex)
            # zbierz wszystkie kraje z danymi
            rows = []
            for lg in _JUN_LEAGUES:
                df = self._get_df(d, lg, sex)
                if df is None:
                    continue
                total_in_league = len(df)
                prom_n = _JUN_PROMOTIONS.get(lg, 4)
                for _, r in df.iterrows():
                    place = int(r["Lp."])
                    overall = _overall_place(lg, place, sizes)
                    # status
                    lg_idx = _JUN_LEAGUES.index(lg)
                    if lg_idx > 0 and place <= prom_n:
                        status = f"⬆ Awans do {_JUN_LEAGUES[lg_idx - 1]}"
                    elif lg_idx < len(_JUN_LEAGUES) - 1 and place > total_in_league - prom_n:
                        lower_prom = _JUN_PROMOTIONS.get(_JUN_LEAGUES[lg_idx + 1], 4)
                        if place > total_in_league - lower_prom:
                            status = f"⬇ Spadek do {_JUN_LEAGUES[lg_idx + 1]}"
                        else:
                            status = "–"
                    else:
                        status = "–"
                    rows.append((lg, str(r["NATION"]), str(r["NAT"]), place, overall, float(r["PTS"]), status))
            rows.sort(key=lambda x: x[4])  # sortuj po miejscu ogólnym
            for lg, nation, nat, place, overall, pts, status in rows:
                color = self._LEAGUE_COLORS.get(lg, "#ffffff")
                iid = tv.insert("", "end", values=(lg, nation, nat, place, overall, f"{pts:.0f}", status))
                tv.tag_configure(lg, background=color)
                tv.item(iid, tags=(lg,))

    # ==================== TAB 2: Historia kraju ====================

    def _build_history(self):
        t = self.tab_history
        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        self._build_history_sex(left, "M")

        right = ttk.Frame(pane)
        pane.add(right, weight=1)
        self._build_history_sex(right, "W")

    def _build_history_sex(self, parent, sex: str):
        ttk.Label(parent, text=f"{'MEN' if sex == 'M' else 'WOMEN'}",
                  font=("TkDefaultFont", 9, "bold")).pack(anchor="w", padx=4)
        c = self._ctrl(parent)
        var = tk.StringVar()
        cb  = self._nat_cb(c, var)
        if sex == "M":
            self.hist_nat_var_m = var
            self.hist_nat_cb_m  = cb
        else:
            self.hist_nat_var_w = var
            self.hist_nat_cb_w  = cb
        btn = ttk.Button(c, text="Pokaż",
                         command=lambda s=sex: self._show_history(s))
        btn.pack(side="left")

        cols = ["Sezon", "Liga", "Miejsce", "Miejsce ogólne", "Punkty", "Zmiana ligi"]
        tv = self._tv(parent, cols, [70, 55, 70, 120, 90, 130])
        if sex == "M":
            self.hist_tv_m = tv
        else:
            self.hist_tv_w = tv

    def _show_history(self, sex: str):
        if not self._loaded:
            return self._no_data()
        tv  = self.hist_tv_m  if sex == "M" else self.hist_tv_w
        var = self.hist_nat_var_m if sex == "M" else self.hist_nat_var_w
        nat = var.get().strip().upper()
        if not nat:
            return
        self._clear(tv)
        prev_lg = None
        for d in self._seasons:
            lg, place, pts, overall = self._find_country(d, sex, nat)
            if lg is None:
                tv.insert("", "end", values=(d["tag"], "–", "–", "–", "–", "–"))
                prev_lg = None
                continue
            # zmiana ligi
            if prev_lg is None:
                change = "Debiut" if d == self._seasons[0] else "Powrót"
            elif lg == prev_lg:
                change = "="
            else:
                pi = _JUN_LEAGUES.index(prev_lg)
                ci = _JUN_LEAGUES.index(lg)
                change = f"⬆ {prev_lg}→{lg}" if ci < pi else f"⬇ {prev_lg}→{lg}"
            iid = tv.insert("", "end", values=(
                d["tag"], lg, place, overall,
                f"{pts:.0f}" if pts is not None else "–", change))
            color = self._LEAGUE_COLORS.get(lg, "#ffffff")
            tv.tag_configure(lg, background=color)
            tv.item(iid, tags=(lg,))
            prev_lg = lg

    # ==================== TAB 3: Przegląd sezonu ====================

    def _build_overview(self):
        t = self.tab_overview
        c = self._ctrl(t)
        ttk.Label(c, text="Sezon:").pack(side="left")
        self.ov_season_var = tk.StringVar()
        self.ov_season_cb  = ttk.Combobox(c, textvariable=self.ov_season_var, width=7, state="readonly")
        self.ov_season_cb.pack(side="left", padx=(2, 8))
        self.ov_sex_var = tk.StringVar(value="M")
        ttk.Radiobutton(c, text="MEN",   variable=self.ov_sex_var, value="M").pack(side="left")
        ttk.Radiobutton(c, text="WOMEN", variable=self.ov_sex_var, value="W").pack(side="left")
        ttk.Button(c, text="Pokaż", command=self._show_overview).pack(side="left", padx=(8, 0))

        # Dynamicznie budujemy kolumny – jeden Treeview z kolumnami per liga
        f = ttk.Frame(t)
        f.pack(fill="both", expand=True, padx=4, pady=4)
        self._ov_frame = f

    def _show_overview(self):
        if not self._loaded:
            return self._no_data()
        tag = self.ov_season_var.get()
        sex = self.ov_sex_var.get()
        d   = next((x for x in self._seasons if x["tag"] == tag), None)
        if d is None:
            return

        for w in self._ov_frame.winfo_children():
            w.destroy()

        avail_leagues = [lg for lg in _JUN_LEAGUES if self._get_df(d, lg, sex) is not None]
        if not avail_leagues:
            ttk.Label(self._ov_frame, text="Brak danych juniorskich dla tego sezonu.").pack(padx=10, pady=10)
            return

        # Jeden duży treeview: rzędy = miejsca, kolumny = ligi (para: kraj+pkt)
        max_rows = max(len(self._get_df(d, lg, sex)) for lg in avail_leagues)
        cols = ["Miejsce"] + [f"{lg} – kraj" for lg in avail_leagues] + [f"{lg} – pkt" for lg in avail_leagues]
        widths = [65] + [120] * len(avail_leagues) + [70] * len(avail_leagues)

        tv = ttk.Treeview(self._ov_frame, columns=cols, show="headings")
        vsb = ttk.Scrollbar(self._ov_frame, orient="vertical",   command=tv.yview)
        hsb = ttk.Scrollbar(self._ov_frame, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tv.pack(fill="both", expand=True)

        for i, col in enumerate(cols):
            w = widths[i] if i < len(widths) else 80
            tv.heading(col, text=col)
            tv.column(col, width=w, anchor="center")

        for place in range(1, max_rows + 1):
            row = [place]
            for lg in avail_leagues:
                df = self._get_df(d, lg, sex)
                r  = df[df["Lp."] == place]
                row.append(r.iloc[0]["NATION"] if not r.empty else "–")
            for lg in avail_leagues:
                df = self._get_df(d, lg, sex)
                r  = df[df["Lp."] == place]
                row.append(f"{r.iloc[0]['PTS']:.0f}" if not r.empty else "–")
            tv.insert("", "end", values=row)

    # ==================== TAB 4: Awanse / Spadki ====================

    def _build_promotions(self):
        t = self.tab_promotions
        c = self._ctrl(t)
        ttk.Label(c, text="Sezon:").pack(side="left")
        self.prom_season_var = tk.StringVar()
        self.prom_season_cb  = ttk.Combobox(c, textvariable=self.prom_season_var, width=7, state="readonly")
        self.prom_season_cb.pack(side="left", padx=(2, 8))
        self.prom_sex_var = tk.StringVar(value="M")
        ttk.Radiobutton(c, text="MEN",   variable=self.prom_sex_var, value="M").pack(side="left")
        ttk.Radiobutton(c, text="WOMEN", variable=self.prom_sex_var, value="W").pack(side="left")
        ttk.Button(c, text="Pokaż awanse/spadki", command=self._show_promotions).pack(side="left", padx=(8, 0))

        cols = ["Liga", "Kraj", "NAT", "Miejsce", "Ruch", "Do ligi"]
        self.prom_tv = self._tv(t, cols, [55, 160, 55, 80, 100, 80])

    def _show_promotions(self):
        if not self._loaded:
            return self._no_data()
        tag = self.prom_season_var.get()
        sex = self.prom_sex_var.get()
        d   = next((x for x in self._seasons if x["tag"] == tag), None)
        if d is None:
            return
        self._clear(self.prom_tv)
        for li, lg in enumerate(_JUN_LEAGUES):
            df = self._get_df(d, lg, sex)
            if df is None:
                continue
            total = len(df)
            prom_up   = _JUN_PROMOTIONS.get(_JUN_LEAGUES[li - 1] if li > 0 else "JC", 4)
            prom_down = _JUN_PROMOTIONS.get(_JUN_LEAGUES[li + 1] if li < len(_JUN_LEAGUES) - 1 else "DC", 4)
            for _, r in df.iterrows():
                place = int(r["Lp."])
                nat   = str(r["NAT"])
                nation = str(r["NATION"])
                # awans
                if li > 0 and place <= prom_up:
                    target = _JUN_LEAGUES[li - 1]
                    iid = self.prom_tv.insert("", "end", values=(lg, nation, nat, place, "⬆ AWANS", target))
                    self.prom_tv.tag_configure("up", foreground="#006600")
                    self.prom_tv.item(iid, tags=("up",))
                # spadek
                elif li < len(_JUN_LEAGUES) - 1 and place > total - prom_down:
                    target = _JUN_LEAGUES[li + 1]
                    iid = self.prom_tv.insert("", "end", values=(lg, nation, nat, place, "⬇ SPADEK", target))
                    self.prom_tv.tag_configure("down", foreground="#cc0000")
                    self.prom_tv.item(iid, tags=("down",))

    # ==================== TAB 5: Ranking ogólny ====================

    def _build_overall(self):
        t = self.tab_overall
        c = self._ctrl(t)
        self.overall_sex_var  = tk.StringVar(value="M")
        ttk.Radiobutton(c, text="MEN",   variable=self.overall_sex_var, value="M").pack(side="left")
        ttk.Radiobutton(c, text="WOMEN", variable=self.overall_sex_var, value="W").pack(side="left")
        self.overall_from_var = tk.StringVar()
        self.overall_to_var   = tk.StringVar()
        self.overall_from_cb  = self._season_cb(c, self.overall_from_var, "  Od:")
        self.overall_to_cb    = self._season_cb(c, self.overall_to_var,   "Do:")
        ttk.Button(c, text="Pokaż", command=self._show_overall).pack(side="left", padx=(8, 0))
        ttk.Label(c, text="  (Śr. ogólne miejsce przez sezony)").pack(side="left")

        cols = ["Lp.", "Kraj", "NAT", "Śr. miejsce ogólne", "Śr. liga",
                "Najlepsza liga", "Najl. miejsce ogólne", "Sezony"]
        self.overall_tv = self._tv(t, cols, [40, 140, 55, 160, 90, 110, 160, 70])

    def _show_overall(self):
        if not self._loaded:
            return self._no_data()
        sex  = self.overall_sex_var.get()
        f_num = _season_num(self.overall_from_var.get()) if self.overall_from_var.get() else 0
        t_num = _season_num(self.overall_to_var.get())   if self.overall_to_var.get()   else 9999
        seasons = [d for d in self._seasons if f_num <= _season_num(d["tag"]) <= t_num]
        self._clear(self.overall_tv)

        stats: dict[str, dict] = {}
        for d in seasons:
            sizes = self._league_sizes(d, sex)
            for lg in _JUN_LEAGUES:
                df = self._get_df(d, lg, sex)
                if df is None:
                    continue
                for _, r in df.iterrows():
                    nat = str(r["NAT"]).strip().upper()
                    if not nat or nat == "NAN":
                        continue
                    place = int(r["Lp."])
                    overall = _overall_place(lg, place, sizes)
                    if nat not in stats:
                        stats[nat] = {"overall": [], "leagues": [], "best_overall": 9999, "best_league": "–"}
                    stats[nat]["overall"].append(overall)
                    stats[nat]["leagues"].append(lg)
                    if overall < stats[nat]["best_overall"]:
                        stats[nat]["best_overall"] = overall
                        stats[nat]["best_league"]  = lg

        rows = []
        for nat, s in stats.items():
            if not s["overall"]:
                continue
            avg_overall = sum(s["overall"]) / len(s["overall"])
            # najczęstsza liga
            from collections import Counter
            most_common_lg = Counter(s["leagues"]).most_common(1)[0][0]
            rows.append((nat, self._nat_to_nation.get(nat, nat),
                         avg_overall, most_common_lg,
                         s["best_league"], s["best_overall"],
                         len(s["overall"])))
        rows.sort(key=lambda x: x[2])
        for i, (nat, nation, avg_ov, common_lg, best_lg, best_ov, cnt) in enumerate(rows, 1):
            self.overall_tv.insert("", "end", values=(
                i, nation, nat,
                f"{avg_ov:.1f}", common_lg, best_lg, best_ov, cnt))

    # ==================== TAB 6: Dominacja ligi ====================

    def _build_domination(self):
        t = self.tab_domination
        c = self._ctrl(t)
        self.dom_sex_var   = tk.StringVar(value="M")
        ttk.Radiobutton(c, text="MEN",   variable=self.dom_sex_var, value="M").pack(side="left")
        ttk.Radiobutton(c, text="WOMEN", variable=self.dom_sex_var, value="W").pack(side="left")
        self.dom_league_var = tk.StringVar(value="JC")
        ttk.Label(c, text="  Liga:").pack(side="left")
        ttk.Combobox(c, textvariable=self.dom_league_var, values=_JUN_LEAGUES,
                     width=5, state="readonly").pack(side="left", padx=(2, 8))
        ttk.Button(c, text="Pokaż dominację", command=self._show_domination).pack(side="left")

        pane = ttk.PanedWindow(t, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        ttk.Label(left, text="Kto najczęściej wygrywał ligę:").pack(anchor="w", padx=4)
        cols = ["Kraj", "NAT", "Razy na 1. miejscu", "Sezony", "Śr. miejsce"]
        self.dom_tv = self._tv(left, cols, [140, 55, 160, 200, 110])

        right = ttk.Frame(pane)
        pane.add(right, weight=1)
        ttk.Label(right, text="Historia Nr 1 w lidze per sezon:").pack(anchor="w", padx=4)
        cols2 = ["Sezon", "Kraj", "NAT", "Punkty"]
        self.dom_hist_tv = self._tv(right, cols2, [80, 160, 55, 90])

    def _show_domination(self):
        if not self._loaded:
            return self._no_data()
        sex = self.dom_sex_var.get()
        lg  = self.dom_league_var.get()
        self._clear(self.dom_tv)
        self._clear(self.dom_hist_tv)

        wins: dict[str, int]       = {}
        season_list: list[str]     = []
        appearances: dict[str, list] = {}

        for d in self._seasons:
            df = self._get_df(d, lg, sex)
            if df is None:
                continue
            top1 = df[df["Lp."] == 1]
            if top1.empty:
                continue
            r   = top1.iloc[0]
            nat = str(r["NAT"]).strip().upper()
            nation = str(r["NATION"]).strip()
            pts    = float(r["PTS"])
            wins[nat]   = wins.get(nat, 0) + 1
            season_list.append((d["tag"], nation, nat, pts))
            if nat not in appearances:
                appearances[nat] = []
            appearances[nat].append(int(df[df["NAT"].str.upper() == nat]["Lp."].iloc[0]) if not df[df["NAT"].str.upper() == nat].empty else 99)

        # tabela dominacji
        rows = [(nat, self._nat_to_nation.get(nat, nat), wins[nat],
                 ", ".join(t for t, _, n, _ in season_list if n == nat),
                 sum(appearances[nat]) / len(appearances[nat]) if appearances.get(nat) else 99)
                for nat in wins]
        rows.sort(key=lambda x: -x[2])
        for nat, nation, w, seasons_str, avg in rows:
            self.dom_tv.insert("", "end", values=(nation, nat, w, seasons_str, f"{avg:.1f}"))

        # historia nr 1
        for tag, nation, nat, pts in season_list:
            self.dom_hist_tv.insert("", "end", values=(tag, nation, nat, f"{pts:.0f}"))


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
