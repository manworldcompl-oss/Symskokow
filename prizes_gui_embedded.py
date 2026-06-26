#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import os
from pathlib import Path
import csv
import math

def _safe_int(val, default=0):
    """Konwertuje wartość na int, zwracając default dla None/NaN/pustych."""
    try:
        f = float(val)
        return default if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return default

def get_nations_from_file():
    n_map = {}
    p = Path("./ALL_NATIONS_NAT.csv")
    if p.exists():
        # Lista kodowań do przetestowania
        encodings = ['utf-8', 'cp1250', 'iso-8859-2', 'latin-1']
        df = None
        
        for enc in encodings:
            try:
                df = pd.read_csv(p, sep=';', engine='python', encoding=enc)
                # Sprawdzamy czy wczytało poprawne kolumny
                if 'NAT' in df.columns and 'NATION' in df.columns:
                    break
            except (UnicodeDecodeError, Exception):
                continue
        
        if df is not None:
            try:
                # Usuwamy ewentualne puste znaki z nazw kolumn i danych
                df.columns = df.columns.str.strip()
                n_map = dict(zip(df['NAT'].str.strip(), df['NATION'].str.strip()))
            except Exception as e:
                print(f"Błąd mapowania danych: {e}")
                
    return n_map

ALL_NATIONS_LOOKUP = get_nations_from_file()

# --- KONFIGURACJA NAGRÓD (Stałe i Słowniki) ---
# --- WC ---
PRIZES_GENERAL_WC = {
    1: 400000, 2: 300000, 3: 200000, 4: 175000, 5: 150000,
    6: 125000, 7: 100000, 8: 90000, 9: 80000, 10: 70000,
    11: 60000, 12: 60000, 13: 50000, 14: 50000, 15: 50000,
    16: 40000, 17: 40000, 18: 40000, 19: 40000, 20: 40000,
    21: 30000, 22: 30000, 23: 30000, 24: 30000, 25: 30000,
    26: 30000, 27: 30000, 28: 30000, 29: 30000, 30: 30000,
    31: 20000, 32: 20000, 33: 20000, 34: 20000, 35: 20000,
    36: 20000, 37: 20000, 38: 20000, 39: 20000, 40: 20000
}
PRIZES_NATIONS_RANK_WC = {
    1: 400000, 2: 300000, 3: 200000, 4: 175000, 5: 150000,
    6: 125000, 7: 100000, 8: 90000, 9: 80000, 10: 70000,
    11: 50000, 12: 50000, 13: 50000, 14: 50000, 15: 50000,
    16: 30000, 17: 30000, 18: 30000, 19: 30000, 20: 30000,
    21: 30000, 22: 30000, 23: 30000, 24: 30000, 25: 30000,
    26: 30000, 27: 30000, 28: 30000, 29: 30000, 30: 30000,
    31: 30000, 32: 30000, 33: 30000, 34: 30000, 35: 30000,
    36: 30000, 37: 30000, 38: 30000, 39: 30000, 40: 30000
}
PRIZES_WINS_WC = {"P1": 40000, "P2": 35000, "P3": 30000}

PRIZES_TOURNEY = {
    1: 150000, 2: 100000, 3: 75000, 4: 60000, 5: 50000,
    6: 40000, 7: 40000, 8: 40000, 9: 40000, 10: 40000,
    11: 30000, 12: 30000, 13: 30000, 14: 30000, 15: 30000,
    16: 30000, 17: 30000, 18: 30000, 19: 30000, 20: 30000,
    21: 20000, 22: 20000, 23: 20000, 24: 20000, 25: 20000,
    26: 20000, 27: 20000, 28: 20000, 29: 20000, 30: 20000
}

# --- COC ---
PRIZES_GENERAL_COC = {
    1: 250000, 2: 200000, 3: 175000, 4: 150000, 5: 125000,
    6: 100000, 7: 80000, 8: 60000, 9: 50000, 10: 40000,
    11: 30000, 12: 30000, 13: 30000, 14: 30000, 15: 30000,
    16: 20000, 17: 20000, 18: 20000, 19: 20000, 20: 20000,
    21: 10000, 22: 10000, 23: 10000, 24: 10000, 25: 10000,
    26: 10000, 27: 10000, 28: 10000, 29: 10000, 30: 10000
}
PRIZES_NATIONS_RANK_COC = PRIZES_GENERAL_COC.copy()
PRIZES_WINS_COC = {"P1": 25000, "P2": 20000, "P3": 15000}

# --- FC ---
PRIZES_GENERAL_FC = {
    1: 200000, 2: 150000, 3: 100000, 4: 80000, 5: 60000,
    6: 50000, 7: 40000, 8: 35000, 9: 30000, 10: 25000,
    11: 20000, 12: 20000, 13: 20000, 14: 20000, 15: 20000,
    16: 10000, 17: 10000, 18: 10000, 19: 10000, 20: 10000,
    21: 5000, 22: 5000, 23: 5000, 24: 5000, 25: 5000
}
PRIZES_NATIONS_RANK_FC = PRIZES_GENERAL_FC.copy()
PRIZES_WINS_FC = {"P1": 20000, "P2": 15000, "P3": 10000}

# --- GP ---
PRIZES_GENERAL_GP = {
    1: 300000, 2: 250000, 3: 200000, 4: 160000, 5: 120000,
    6: 100000, 7: 80000, 8: 60000, 9: 50000, 10: 40000,
    11: 30000, 12: 30000, 13: 30000, 14: 30000, 15: 30000,
    16: 20000, 17: 20000, 18: 20000, 19: 20000, 20: 20000,
    21: 10000, 22: 10000, 23: 10000, 24: 10000, 25: 10000,
    26: 10000, 27: 10000, 28: 10000, 29: 10000, 30: 10000
}
PRIZES_NATIONS_RANK_GP = PRIZES_GENERAL_GP.copy()
PRIZES_WINS_GP = {"P1": 30000, "P2": 25000, "P3": 20000}

# --- SCOC ---
PRIZES_GENERAL_SCOC = {
    1: 200000, 2: 150000, 3: 100000, 4: 80000, 5: 60000,
    6: 50000, 7: 40000, 8: 35000, 9: 30000, 10: 25000,
    11: 20000, 12: 20000, 13: 20000, 14: 20000, 15: 20000,
    16: 10000, 17: 10000, 18: 10000, 19: 10000, 20: 10000,
    21: 5000, 22: 5000, 23: 5000, 24: 5000, 25: 5000
}
PRIZES_NATIONS_RANK_SCOC = PRIZES_GENERAL_SCOC.copy()
PRIZES_WINS_SCOC = {"P1": 20000, "P2": 15000, "P3": 10000}

# --- JC, MC, PC, QC, TC, AC, BC, DC ---
PRIZES_GENERAL_JC = {
    1: 100000, 2: 90000, 3: 80000, 4: 70000, 5: 60000,
    6: 50000, 7: 40000, 8: 30000, 9: 25000, 10: 20000,
    11: 15000, 12: 15000, 13: 15000, 14: 15000, 15: 15000
}
PRIZES_NATIONS_RANK_JC = PRIZES_GENERAL_JC.copy()
PRIZES_WINS_JC = {"P1": 15000, "P2": 10000, "P3": 5000}

# --- TCS i inne pod-turnieje WC (NT, FT, P7, W5, RA, BB, FNT) ---
PRIZES_SUBTOUR = {
    1: 150000, 2: 100000, 3: 75000, 4: 60000, 5: 50000,
    6: 40000, 7: 40000, 8: 40000, 9: 40000, 10: 40000,
    11: 30000, 12: 30000, 13: 30000, 14: 30000, 15: 30000,
    16: 30000, 17: 30000, 18: 30000, 19: 30000, 20: 30000,
    21: 20000, 22: 20000, 23: 20000, 24: 20000, 25: 20000,
    26: 20000, 27: 20000, 28: 20000, 29: 20000, 30: 20000
}



# Funkcja pomocnicza wybierająca zestaw nagród dla cyklu
def get_tour_prize_config(tour_code):
    if tour_code == "COC":
        # Zwraca: (nagrody_indywidualne, powyżej_30_ind, nagrody_drużynowe, powyżej_30_druż, bonusy_za_podium)
        return PRIZES_GENERAL_COC, 0, PRIZES_NATIONS_RANK_COC, 5000, PRIZES_WINS_COC
    elif tour_code == "FC":
        return PRIZES_GENERAL_FC, 0, PRIZES_NATIONS_RANK_FC, 2500, PRIZES_WINS_FC
    elif tour_code == "GP":
        return PRIZES_GENERAL_GP, 5000, PRIZES_NATIONS_RANK_GP, 5000, PRIZES_WINS_GP
    elif tour_code == "SCOC":
        return PRIZES_GENERAL_SCOC, 0, PRIZES_NATIONS_RANK_SCOC, 2500, PRIZES_WINS_SCOC
    elif tour_code in ["JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]:
        return PRIZES_GENERAL_JC, 0, PRIZES_NATIONS_RANK_JC, 2500, PRIZES_WINS_JC
    else:
        return PRIZES_GENERAL_WC, 10000, PRIZES_NATIONS_RANK_WC, 30000, PRIZES_WINS_WC
    
#KONIEC CYKLI
#POCZĄTEK CHAMPIONSHIPS
PRIZES_OG = {
    1: 500000, 2: 400000, 3: 300000, 4: 250000, 5: 200000,
    6: 150000, 7: 125000, 8: 100000, 9: 80000, 10: 70000,
    11: 60000, 12: 60000, 13: 60000, 14: 60000, 15: 60000,
    16: 50000, 17: 50000, 18: 50000, 19: 50000, 20: 50000,
    21: 40000, 22: 40000, 23: 40000, 24: 40000, 25: 40000,
    26: 35000, 27: 35000, 28: 35000, 29: 35000, 30: 35000
}
# --- WCH ---
PRIZES_WCH = {
    1: 400000, 2: 300000, 3: 250000, 4: 200000, 5: 150000,
    6: 125000, 7: 100000, 8: 80000, 9: 70000, 10: 60000,
    11: 50000, 12: 50000, 13: 50000, 14: 50000, 15: 50000,
    16: 40000, 17: 40000, 18: 40000, 19: 40000, 20: 40000,
    21: 35000, 22: 35000, 23: 35000, 24: 35000, 25: 35000,
    26: 30000, 27: 30000, 28: 30000, 29: 30000, 30: 30000
}
# --- SFWC ---
PRIZES_SFWC = {
    1: 300000, 2: 250000, 3: 200000, 4: 150000, 5: 125000,
    6: 100000, 7: 80000, 8: 70000, 9: 60000, 10: 50000,
    11: 40000, 12: 40000, 13: 40000, 14: 40000, 15: 40000,
    16: 30000, 17: 30000, 18: 30000, 19: 30000, 20: 30000,
    21: 25000, 22: 25000, 23: 25000, 24: 25000, 25: 25000,
    26: 20000, 27: 20000, 28: 20000, 29: 20000, 30: 20000
}
# --- JWC ---
PRIZES_JWC = {
    1: 150000, 2: 100000, 3: 90000, 4: 80000, 5: 70000,
    6: 60000, 7: 50000, 8: 40000, 9: 30000, 10: 25000,
    11: 20000, 12: 20000, 13: 20000, 14: 20000, 15: 20000,
    16: 15000, 17: 15000, 18: 15000, 19: 15000, 20: 15000,
    21: 10000, 22: 10000, 23: 10000, 24: 10000, 25: 10000,
    26: 5000, 27: 5000, 28: 5000, 29: 5000, 30: 5000,
    31: 2500, 32: 2500, 33: 2500, 34: 2500, 35: 2500, 
    36: 2500, 37: 2500, 38: 2500, 39: 2500, 40: 2500, 
    41: 2500, 42: 2500, 43: 2500, 44: 2500, 45: 2500, 
    46: 2500, 47: 2500, 48: 2500, 49: 2500, 50: 2500
}
# --- YOG ---
PRIZES_YOG = {
    1: 200000, 2: 150000, 3: 100000, 4: 90000, 5: 70000,
    6: 60000, 7: 50000, 8: 40000, 9: 30000, 10: 20000,
    11: 10000, 12: 10000, 13: 10000, 14: 10000, 15: 10000,
    16: 5000, 17: 5000, 18: 5000, 19: 5000, 20: 5000,
    21: 5000, 22: 5000, 23: 5000, 24: 5000, 25: 5000,
    26: 5000, 27: 5000, 28: 5000, 29: 5000, 30: 5000
}
# --- UNI ---
PRIZES_UNI = {
    1: 200000, 2: 150000, 3: 100000, 4: 90000, 5: 70000,
    6: 60000, 7: 50000, 8: 40000, 9: 30000, 10: 20000,
    11: 10000, 12: 10000, 13: 10000, 14: 10000, 15: 10000,
    16: 5000, 17: 5000, 18: 5000, 19: 5000, 20: 5000,
    21: 5000, 22: 5000, 23: 5000, 24: 5000, 25: 5000,
    26: 5000, 27: 5000, 28: 5000, 29: 5000, 30: 5000
}
# --- NKIC ---
PRIZES_NKIC = {
    1: 450000, 2: 300000, 3: 270000, 4: 240000, 5: 210000,
    6: 180000, 7: 150000, 8: 120000, 9: 100000, 10: 90000,
    11: 85000, 12: 80000, 13: 75000, 14: 70000, 15: 65000,
    16: 62500, 17: 60000, 18: 57500, 19: 55000, 20: 52500,
    21: 50000, 22: 47500, 23: 45000, 24: 42500, 25: 40000,
    26: 37500, 27: 35000, 28: 32500, 29: 30000, 30: 27500,
    31: 25000, 32: 22500, 33: 21000, 34: 20000, 35: 19000,
    36: 18000, 37: 17000, 38: 16000, 39: 15000, 40: 14500,
    41: 14000, 42: 13500, 43: 13000, 44: 12500, 45: 12000,
    46: 11500, 47: 11000, 48: 10500, 49: 10000, 50: 9500,
    51: 9000, 52: 8500, 53: 8000, 54: 7500, 55: 7000,
    56: 6500, 57: 6000, 58: 5500, 59: 5000, 60: 4500,
    61: 4000, 62: 3500, 63: 3000, 64: 2500
}
# --- IST ---
PRIZES_IST = {
    1: 300000, 2: 200000, 3: 180000, 4: 160000, 5: 140000,
    6: 120000, 7: 100000, 8: 80000, 9: 66667, 10: 60000,
    11: 56667, 12: 53333, 13: 50000, 14: 46667, 15: 43333,
    16: 41667, 17: 40000, 18: 38333, 19: 36667, 20: 35000,
    21: 33333, 22: 31667, 23: 30000, 24: 28333, 25: 26667,
    26: 25000, 27: 23333, 28: 21667, 29: 20000, 30: 18333,
    31: 16667, 32: 15000, 33: 14000, 34: 13333, 35: 12667,
    36: 12000, 37: 11333, 38: 10667, 39: 10000, 40: 9667,
    41: 9333, 42: 9000, 43: 8667, 44: 8333, 45: 8000,
    46: 7667, 47: 7333, 48: 7000, 49: 66667, 50: 6333,
    51: 6000, 52: 5667, 53: 5333, 54: 5000, 55: 4667,
    56: 4333, 57: 4000, 58: 3667, 59: 3333, 60: 3000,
    61: 2667, 62: 2333, 63: 2000, 64: 1667
}
# --- COCH ---
PRIZES_COCH = {
    1: 125000, 2: 100000, 3: 90000, 4: 80000, 5: 70000,
    6: 60000, 7: 50000, 8: 40000, 9: 30000, 10: 25000,
    11: 20000, 12: 19000, 13: 18000, 14: 17000, 15: 16000,
    16: 15000, 17: 14000, 18: 13000, 19: 12000, 20: 11000,
    21: 10000, 22: 9000, 23: 8000, 24: 7000, 25: 6000,
    26: 5000, 27: 4500, 28: 4000, 29: 3500, 30: 3000
}

# Funkcja wybierająca cennik mistrzostw
def get_champ_prize_config(champ_code):
    if champ_code == "WCH":
        return PRIZES_WCH,0,25000
    elif champ_code == "SFWC":
        return PRIZES_SFWC,0,15000
    elif champ_code == "JWC":
        return PRIZES_JWC,0,2500
    elif champ_code == "YOG":
        return PRIZES_YOG,0,2500
    elif champ_code == "UNI":
        return PRIZES_UNI,0,2500
    elif champ_code == "NKIC":
        return PRIZES_NKIC,0,0
    elif champ_code == "IST":
        return PRIZES_IST,0,0
    elif champ_code == "COCH":
        return PRIZES_COCH,0,2500
    else:
        return PRIZES_OG,0,30000

BASE_DIR_TOURNAMENTS = Path("./S51/Klasyfikacje S51")
BASE_DIR_CHAMPIONSHIPS = Path("./S51/Mistrzostwa S51")

# --- POMOCNICZE ---

def get_prize_val(rank, p_dict, default=0):
    try:
        r = int(float(rank))
        if r <= 0: return 0
        return p_dict.get(r, default)
    except:
        return 0

def load_csv(path):
    if not os.path.exists(path): return None
    try:
        df = pd.read_csv(path, sep=';', engine='python')
        if len(df.columns) <= 1:
            df = pd.read_csv(path, sep=',', engine='python')
        return df
    except:
        return None

def format_currency(val):
    return f"{int(val):,} €".replace(",", " ")

# --- GUI ---

class MultiTableTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        # --- reszta układu ---
        self.canvas = tk.Canvas(self)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
        
        self.hsb.pack(side="bottom", fill="x")
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.tables_frame = ttk.Frame(self.scrollable_frame)
        self.tables_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def _do_refresh(self):
        """Wywołuje odpowiednią metodę ładowania danych w podklasie."""
        for meth in ("load_data", "load_summary_data", "load_team_data", "load_grand_summary"):
            if hasattr(self, meth) and callable(getattr(self, meth)):
                getattr(self, meth)()
                break

    def add_table(self, title, df, columns):
        if df is None or df.empty:
            frame = ttk.LabelFrame(self.tables_frame, text=title)
            frame.pack(side="left", fill="both", expand=True, padx=5)
            ttk.Label(frame, text="Brak danych").pack(pady=10)
            return

        frame = ttk.LabelFrame(self.tables_frame, text=title)
        # Zmieniono fill na "both" i expand na True, aby ramka zajmowała miejsce
        frame.pack(side="left", fill="both", expand=True, padx=5)
        
        tree = ttk.Treeview(frame, columns=columns, show='headings', height=25)
        
        for col in columns:
            tree.heading(col, text=col)
            # Ustawienie stretch=True pozwala kolumnom rozszerzać się wraz z oknem
            if col in ["Jumper", "Zawodnik", "Nation", "Drużyna"]:
                width = 180
            elif col in ["Total", "SUMA", "Suma"]:
                width = 120
            else:
                width = 70
            tree.column(col, width=width, anchor="center", stretch=True)
        
        for _, row in df.iterrows():
            vals = [row.get(c, "-") for c in columns]
            tree.insert("", "end", values=vals)
        
        # Kluczowe: fill="both" i expand=True dla samego Treeview
        tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

class TournamentTab(MultiTableTab):
    def __init__(self, parent, tour_code, gender):
        super().__init__(parent)
        self.tour_code, self.gender = tour_code, gender
        self.load_data()

    def load_data(self):
        for w in self.tables_frame.winfo_children(): w.destroy()
        # 1. Dane podstawowe
        suffix = f"{self.tour_code}-{self.gender}"
        df_p = load_csv(BASE_DIR_TOURNAMENTS / f"S51_{suffix}__players.csv")
        df_n = load_csv(BASE_DIR_TOURNAMENTS / f"S51_{suffix}__nations.csv")
        p_gen, d_gen, p_nat, d_nat, p_wins = get_tour_prize_config(self.tour_code)

        # Mapy do zbierania sum dla 3 tabeli
        ind_country_prizes = {}
        team_country_prizes = {}

        # --- TABELA 1: INDYWIDUALNA ---
        col_p = ["Lp.", "Jumper", "NAT"]
        # Dodatkowe kolumny turniejowe
        if self.tour_code == "WC":
            extra = ["TCS", "NT", "FT", "P7", "W5", "RA"] if self.gender == "M" else ["RA", "BB", "FNT"]
            col_p += extra
        col_p += ["P1", "P2", "P3", "Suma"]

        rows_p = []
        if df_p is not None:
            # Szukamy miejsc w dodatkowych plikach (TCS, NT itd.)
            sub_maps = {}
            if self.tour_code == "WC":
                tour_list = ["TCS", "NT", "FT", "P7", "W5", "RA"] if self.gender == "M" else ["RA", "BB", "FNT"]
                # Mapowanie kodu kolumny -> rzeczywista nazwa pliku CSV
                file_map = {
                    "RA": "S51_RAWAIR-W.csv" if self.gender == "W" else "S51_RAWAIR-M.csv",
                    "P7": "S51_PLANICA7.csv",
                    "W5": "S51_WILLINGEN5.csv",
                }
                for st in tour_list:
                    fname = file_map.get(st, f"S51_{st}.csv")
                    sub_df = load_csv(BASE_DIR_TOURNAMENTS / fname)
                    if sub_df is not None:
                        sub_maps[st] = dict(zip(sub_df.iloc[:, 1].str.strip(), sub_df.iloc[:, 0]))

            for _, row in df_p.iterrows():
                name = str(row.iloc[1]).strip()
                nat = str(row.iloc[2]).strip()
                lp = row.iloc[0]

                p1 = _safe_int(row.get('1', 0))
                p2 = _safe_int(row.get('2', 0))
                p3 = _safe_int(row.get('3', 0))
                
                # Liczenie sumy
                val = get_prize_val(lp, p_gen, d_gen)
                val += (p1 * p_wins.get("P1", 0)) + (p2 * p_wins.get("P2", 0)) + (p3 * p_wins.get("P3", 0))

                # Nagrody za miejsca w pod-turniejach (TCS, NT, FT, P7, W5, RA, BB, FNT)
                # Każdy pod-turniej liczony i sumowany osobno
                for st, m in sub_maps.items():
                    sub_lp = m.get(name)
                    if sub_lp is not None:
                        val += get_prize_val(sub_lp, PRIZES_SUBTOUR, 0)
                
                r_data = {"Lp.": lp, "Jumper": name, "NAT": nat, "P1": p1, "P2": p2, "P3": p3, "Suma": format_currency(val)}
                for k, m in sub_maps.items(): r_data[k] = m.get(name, "-")
                rows_p.append(r_data)
                ind_country_prizes[nat] = ind_country_prizes.get(nat, 0) + val

        self.add_table("TABELA INDYWIDUALNA", pd.DataFrame(rows_p), col_p)

        # --- TABELA 2: DRUŻYNOWA ---
        col_n = ["Lp.", "Nation", "NAT"]
        if self.tour_code in ["WC", "GP"]: col_n += ["P1", "P2", "P3"]
        col_n += ["Suma"]

        rows_n = []
        if df_n is not None:
            for _, row in df_n.iterrows():
                nat = str(row.iloc[2]).strip()
                lp = row.iloc[0]
                
                # Podstawa: nagroda za miejsce w rankingu narodów
                val = get_prize_val(lp, p_nat, d_nat)
                
                # NOWOŚĆ: Doliczanie bonusów za podia (P1, P2, P3) dla krajów
                p1, p2, p3 = 0, 0, 0
                if self.tour_code in ["WC", "GP"]:
                    p1 = _safe_int(row.get('1', 0))
                    p2 = _safe_int(row.get('2', 0))
                    p3 = _safe_int(row.get('3', 0))
                    # Używamy tych samych stawek p_wins co dla indywidualnych
                    val += (p1 * p_wins.get("P1", 0)) + (p2 * p_wins.get("P2", 0)) + (p3 * p_wins.get("P3", 0))
                
                r_data = {"Lp.": lp, "Nation": row.iloc[1], "NAT": nat, "Suma": format_currency(val)}
                if self.tour_code in ["WC", "GP"]:
                    r_data.update({"P1": p1, "P2": p2, "P3": p3})
                
                rows_n.append(r_data)
                team_country_prizes[nat] = val # Zapisujemy powiększoną sumę do mapy zbiorczej

        self.add_table("TABELA DRUŻYNOWA", pd.DataFrame(rows_n), col_n)

        # --- TABELA 3: SUMA KRAJOWA ---
        all_nats = set(ind_country_prizes.keys()) | set(team_country_prizes.keys())
        rows_sum = []
        for n in all_nats:
            s_i = ind_country_prizes.get(n, 0)
            s_t = team_country_prizes.get(n, 0)
            rows_sum.append({
                "Nation": ALL_NATIONS_LOOKUP.get(n, n), "NAT": n,
                "IND": format_currency(s_i), "TEAM": format_currency(s_t),
                "Suma": format_currency(s_i + s_t), "_sort": s_i + s_t
            })
        df_sum = pd.DataFrame(rows_sum).sort_values("_sort", ascending=False) if rows_sum else pd.DataFrame()
        self.add_table("SUMA DLA KRAJU", df_sum, ["Nation", "NAT", "IND", "TEAM", "Suma"])

class ChampionshipTab(MultiTableTab):
    def __init__(self, parent, code, gender, region=None):
        super().__init__(parent)
        self.code, self.gender, self.region = code, gender, region
        self.load_data()

    def get_msc(self, df, name):
        """Pomocnicza funkcja do wyciągania miejsca z pliku CSV po nazwie zawodnika/kraju."""
        if df is not None and not df.empty:
            name_str = str(name).strip().lower()
            # Sprawdzamy kolumnę 1 (Zawodnik/Drużyna) i 2 (Kraj)
            for col_idx in [1, 2]:
                if col_idx < len(df.columns):
                    mask = df.iloc[:, col_idx].astype(str).str.strip().str.lower() == name_str
                    res = df[mask]
                    if not res.empty:
                        return res.iloc[0, 0]
        return "-"

    def load_data(self):
        # Czyszczenie widoku
        for widget in self.tables_frame.winfo_children():
            widget.destroy()

        reg_s = f"_{self.region}" if self.region else ""
        pref = f"S51_{self.code}{reg_s}_{self.gender}"
        pref_x = f"S51_{self.code}{reg_s}_X"
        
        p_dict, b_ind, b_team = get_champ_prize_config(self.code)
        
        nation_ind_sums = {}
        nation_team_sums = {}

        # --- 1. TABELA INDYWIDUALNA ---
        ind_rows = []
        # Domyślne kolumny, by uniknąć błędów przy braku danych
        cols_ind = ["Zawodnik", "Kraj", "N", "Suma"] 

        if self.code in ["OG", "WCH", "IST"]:
            cols_ind = ["Zawodnik", "Kraj", "LH", "NH", "Suma"]
            df_nh = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref}_IND_NORMAL.csv")
            df_lh = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref}_IND_LARGE.csv")
            
            all_players = set()
            if df_nh is not None: all_players.update(df_nh.iloc[:, 1].dropna().unique())
            if df_lh is not None: all_players.update(df_lh.iloc[:, 1].dropna().unique())

            for p in all_players:
                m_nh = self.get_msc(df_nh, p)
                m_lh = self.get_msc(df_lh, p)
                
                nat = ""
                for df in [df_nh, df_lh]:
                    if df is not None:
                        match = df[df.iloc[:, 1].astype(str).str.strip() == str(p).strip()]
                        if not match.empty:
                            nat = match.iloc[0, 2]
                            break
                
                v = get_prize_val(m_nh, p_dict, b_ind) + get_prize_val(m_lh, p_dict, b_ind)
                ind_rows.append({"Zawodnik": p, "Kraj": nat, "LH": m_lh, "NH": m_nh, "Suma": format_currency(v), "_raw": v})
                if nat: nation_ind_sums[nat] = nation_ind_sums.get(nat, 0) + v
        else:
            df_n = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref}_IND.csv")
            if df_n is not None:
                for _, row in df_n.iterrows():
                    msc, p, nat = row.iloc[0], row.iloc[1], row.iloc[2]
                    v = get_prize_val(msc, p_dict, b_ind)
                    ind_rows.append({"Zawodnik": p, "Kraj": nat, "N": msc, "Suma": format_currency(v), "_raw": v})
                    if nat: nation_ind_sums[nat] = nation_ind_sums.get(nat, 0) + v

        df_ind_final = pd.DataFrame(ind_rows)
        if not df_ind_final.empty and "_raw" in df_ind_final.columns:
            df_ind_final = df_ind_final.sort_values("_raw", ascending=False)
        self.add_table("TABELA INDYWIDUALNA", df_ind_final, cols_ind)

        # --- 2. TABELA DRUŻYNOWA ---
        if self.code not in ["NKIC", "IST"]:
            team_rows = []
            all_nations = set()
            cols_team = ["Drużyna", "Kraj", "Suma"] # Domyślne

            if self.code in ["OG", "WCH"]:
                cols_team = ["Drużyna", "Kraj", ("WL" if self.gender == "W" else "ML"), 
                             ("WN" if self.gender == "W" else "MN"), "XL", "XN", "Suma"]
                
                f_tn = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref}_TEAM_NORMAL.csv")
                f_tl = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref}_TEAM_LARGE.csv")
                f_xn = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref_x}_TEAM_NORMAL.csv")
                f_xl = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref_x}_TEAM_LARGE.csv")
                
                for df in [f_tn, f_tl, f_xn, f_xl]:
                    if df is not None: all_nations.update(df.iloc[:, 2].dropna().unique())
                
                for n in all_nations:
                    m_tn, m_tl, m_xn, m_xl = self.get_msc(f_tn, n), self.get_msc(f_tl, n), self.get_msc(f_xn, n), self.get_msc(f_xl, n)
                    s_t = (get_prize_val(m_tn, p_dict, b_team) + get_prize_val(m_tl, p_dict, b_team) + 
                          (get_prize_val(m_xn, p_dict, b_team) * 0.5) + (get_prize_val(m_xl, p_dict, b_team) * 0.5))
                    
                    row = {"Drużyna": ALL_NATIONS_LOOKUP.get(n, n), "Kraj": n, "Suma": format_currency(s_t), "_raw": s_t, "XL": m_xl, "XN": m_xn}
                    if self.gender == "W": row.update({"WL": m_tl, "WN": m_tn})
                    else: row.update({"ML": m_tl, "MN": m_tn})
                    team_rows.append(row)
                    nation_team_sums[n] = s_t
            else:
                cols_team = ["Drużyna", "Kraj", ("W" if self.gender == "W" else "M"), "X", "Suma"]
                f_t = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref}_TEAM.csv")
                f_x = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{pref_x}_TEAM.csv")
                
                for df in [f_t, f_x]:
                    if df is not None: all_nations.update(df.iloc[:, 2].dropna().unique())
                
                for n in all_nations:
                    m_t, m_x = self.get_msc(f_t, n), self.get_msc(f_x, n)
                    s_t = get_prize_val(m_t, p_dict, b_team) + (get_prize_val(m_x, p_dict, b_team) * 0.5)
                    row = {"Drużyna": ALL_NATIONS_LOOKUP.get(n, n), "Kraj": n, "Suma": format_currency(s_t), "_raw": s_t, "X": m_x}
                    if self.gender == "W": row["W"] = m_t
                    else: row["M"] = m_t
                    team_rows.append(row)
                    nation_team_sums[n] = s_t

            df_team_final = pd.DataFrame(team_rows)
            if not df_team_final.empty and "_raw" in df_team_final.columns:
                df_team_final = df_team_final.sort_values("_raw", ascending=False)
            self.add_table("TABELA DRUŻYNOWA", df_team_final, cols_team)

        # --- 3. TABELA ZBIORCZA ---
        summary_nats = set(nation_ind_sums.keys()) | set(nation_team_sums.keys())
        total_rows = []
        
        # DEFINICJA DOMYŚLNYCH KOLUMN (Rozwiązuje błąd UnboundLocalError)
        if self.code in ["NKIC", "IST"]:
            sum_cols = ["Kraj", "Suma"]
        else:
            sum_cols = ["Drużyna", "Kraj", "Suma"]

        for n in summary_nats:
            total_val = nation_ind_sums.get(n, 0) + nation_team_sums.get(n, 0)
            if self.code in ["NKIC", "IST"]:
                total_rows.append({"Kraj": n, "Suma": format_currency(total_val), "_raw": total_val})
            else:
                total_rows.append({"Drużyna": ALL_NATIONS_LOOKUP.get(n, n), "Kraj": n, "Suma": format_currency(total_val), "_raw": total_val})
        
        df_sum_final = pd.DataFrame(total_rows)
        if not df_sum_final.empty and "_raw" in df_sum_final.columns:
            df_sum_final = df_sum_final.sort_values("_raw", ascending=False)
        self.add_table("SUMA DLA KRAJU", df_sum_final, sum_cols)

class SummaryTab(MultiTableTab):
    def __init__(self, parent, gender):
        super().__init__(parent)
        self.gender = gender
        self.load_summary_data()

    def load_summary_data(self):
        for w in self.tables_frame.winfo_children(): w.destroy()
        summary_dict = {}
        tournaments = ["GP", "SCOC", "WC", "COC", "FC", "JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]
        championships = ["OG", "WCH", "SFWC", "NKIC", "IST", "YOG", "UNI", "JWC", "COCH"]
        all_keys = tournaments + championships

        # Inicjalizacja wszystkich krajów z bazy (żeby pokazać nawet te z 0 €)
        for nat_code, full_name in ALL_NATIONS_LOOKUP.items():
            summary_dict[nat_code] = {"Nation": full_name, "NAT": nat_code, "_raw_total": 0}
            for k in all_keys: summary_dict[nat_code][k] = 0

        def add_val(nat, amount, key):
            if not nat or pd.isna(nat): return
            nat = str(nat).strip().upper()
            if nat not in summary_dict:
                summary_dict[nat] = {"Nation": nat, "NAT": nat, "_raw_total": 0}
                for k in all_keys: summary_dict[nat][k] = 0
            summary_dict[nat][key] += amount
            summary_dict[nat]["_raw_total"] += amount

        # --- PRZETWARZANIE TURNIEJÓW (GP, WC, COC, FC itd.) ---
        for t in tournaments:
            suffix = f"{t}-{self.gender}"
            # Pobieramy zestaw nagród dla konkretnego cyklu (np. inne dla COC)
            p_gen, d_gen, p_nat, d_nat, p_wins = get_tour_prize_config(t)
            
            # Zawodnicy
            df_p = load_csv(BASE_DIR_TOURNAMENTS / f"S51_{suffix}__players.csv")
            if df_p is not None:
                c_idx = next((i for i, c in enumerate(df_p.columns) if str(c).upper() in ["NAT", "KRAJ"]), 2)
                for _, row in df_p.iterrows():
                    try:
                        if pd.isna(row.iloc[0]) or str(row.iloc[0]).strip() == "": continue
                        val = get_prize_val(row.iloc[0], p_gen, d_gen)
                        # Bonusy za podium w konkursach
                        for i, p_code in enumerate(['P1', 'P2', 'P3'], 4):
                            if i < len(row): 
                                bonus = float(str(row.iloc[i]).replace(',', '.')) * p_wins.get(p_code, 0)
                                val += bonus
                        add_val(row.iloc[c_idx], val, t)
                    except: pass

            # Narody
            df_n = load_csv(BASE_DIR_TOURNAMENTS / f"S51_{suffix}__nations.csv")
            if df_n is not None:
                c_idx = next((i for i, c in enumerate(df_n.columns) if str(c).upper() in ["NAT", "KRAJ"]), 2)
                for _, row in df_n.iterrows():
                    try:
                        if pd.isna(row.iloc[0]) or str(row.iloc[0]).strip() == "": continue
                        
                        # Podstawa za ranking
                        val = get_prize_val(row.iloc[0], p_nat, d_nat)
                        
                        # NOWOŚĆ: Doliczanie bonusów za podia w podsumowaniu zbiorczym
                        if t in ["WC", "GP"]:
                            p1 = int(float(row.get('1', 0)))
                            p2 = int(float(row.get('2', 0)))
                            p3 = int(float(row.get('3', 0)))
                            val += (p1 * p_wins.get("P1", 0)) + (p2 * p_wins.get("P2", 0)) + (p3 * p_wins.get("P3", 0))
                            
                        add_val(row.iloc[c_idx], val, t)
                    except: pass

        # --- PRZETWARZANIE MISTRZOSTW (OG, WCH, itd.) ---
        for c_code in championships:
            # Pobieramy cennik dla danych mistrzostw
            p_dict, b_ind, b_team = get_champ_prize_config(c_code)
            
            regs = ["EUROPE", "ASIA", "NORTHAMERICA", "SOUTHAMERICA", "OCEANIA", "AFRICA"] if c_code == "COCH" else [""]
            for reg in regs:
                reg_s = f"_{reg}" if reg else ""
                
                # Pliki M/W (100% stawki) oraz MIX (50% stawki)
                sources = [
                    (f"S51_{c_code}{reg_s}_{self.gender}", 1.0),
                    (f"S51_{c_code}{reg_s}_X", 0.5)
                ]
                
                sufs = ["_IND.csv", "_IND_NORMAL.csv", "_IND_LARGE.csv", 
                        "_TEAM.csv", "_TEAM_NORMAL.csv", "_TEAM_LARGE.csv"]

                for prefix, multiplier in sources:
                    for s in sufs:
                        df = load_csv(BASE_DIR_CHAMPIONSHIPS / f"{prefix}{s}")
                        if df is not None:
                            is_team_file = "_TEAM" in s
                            bonus = b_team if is_team_file else b_ind
                            
                            for _, row in df.iterrows():
                                try:
                                    # Używamy odpowiedniego bonusu (dla YOG: 2500 dla TEAM, 0 dla IND)
                                    val = get_prize_val(row.iloc[0], p_dict, bonus) * multiplier
                                    add_val(row.iloc[2], val, c_code)
                                except: pass

        # FINALIZACJA I SORTOWANIE
        self.summary_dict = summary_dict
        final_list = []
        for nat, data in summary_dict.items():
            row = {"Nation": data["Nation"], "NAT": data["NAT"], 
                  "Total": format_currency(data["_raw_total"]), "_raw_total": data["_raw_total"]}
            for k in all_keys:
                row[k] = format_currency(data[k]) if data[k] > 0 else "-"
            final_list.append(row)

        df_final = pd.DataFrame(final_list)
        if not df_final.empty:
            df_final = df_final.sort_values(by=["_raw_total", "Nation"], ascending=[False, True])
            self.add_table("ZBIORCZE PODSUMOWANIE ZAROBKÓW", df_final, ["Nation", "NAT", "Total"] + all_keys)

class TeamTab(MultiTableTab):
    def __init__(self, parent, tour_type):
        super().__init__(parent)
        self.tour_type = tour_type
        self.load_team_data()

    def load_team_data(self):
        for w in self.tables_frame.winfo_children(): w.destroy()
        team_dir = Path("./S51/Team S51")
        if self.tour_type == "CC":
            files = [("Continental Cup", "S51_CC_Klasyfikacja.csv")]
        elif self.tour_type == "SWISS":
            files = [("Swiss Cup", "S51_SWISS_Klasyfikacja.csv")]
        elif self.tour_type == "MSC":
            files = [("MSC Men", "S51_MSC_M_Klasyfikacja.csv"), 
                     ("MSC Women", "S51_MSC_W_Klasyfikacja.csv")]
        else: return

        for title, f_name in files:
            df = load_csv(team_dir / f_name)
            if df is not None:
                fin_col = next((c for c in df.columns if "Finanse" in c), None)
                if fin_col:
                    df["_raw_total"] = df[fin_col].apply(lambda x: float(str(x).replace(' ', '').replace(',', '.')) if pd.notna(x) else 0)
                    df["Suma"] = df["_raw_total"].apply(format_currency)
                df = df.rename(columns={"Lp.": "Lp.", "Drużyna": "Drużyna", "Kraj": "Kraj"})
                self.add_table(title, df, ["Lp.", "Drużyna", "Kraj", "Suma"])

class TeamSummaryTab(MultiTableTab):
    def __init__(self, parent):
        super().__init__(parent)
        self.load_summary_data()

    def load_summary_data(self):
        for w in self.tables_frame.winfo_children(): w.destroy()
        team_dir = Path("./S51/Team S51")
        # Mapowanie kluczy na nazwy plików
        files_map = {
            "CC": "S51_CC_Klasyfikacja.csv",
            "MSC-M": "S51_MSC_M_Klasyfikacja.csv",
            "MSC-W": "S51_MSC_W_Klasyfikacja.csv",
            "SWISS": "S51_SWISS_Klasyfikacja.csv"
        }
        
        summary = {} # klucz: (Druzyna, Kraj)

        for key, f_name in files_map.items():
            df = load_csv(team_dir / f_name)
            if df is not None:
                fin_col = next((c for c in df.columns if "Finanse" in c), None)
                for _, row in df.iterrows():
                    try:
                        team = str(row.get("Drużyna", "")).strip()
                        nat = str(row.get("Kraj", "")).strip()
                        if not team: continue
                        
                        val = 0
                        if fin_col and pd.notna(row[fin_col]):
                            val = float(str(row[fin_col]).replace(' ', '').replace(',', '.'))
                        
                        id_key = (team, nat)
                        if id_key not in summary:
                            summary[id_key] = {"Drużyna": team, "Kraj": nat, "Suma_raw": 0, 
                                              "CC": 0, "MSC-M": 0, "MSC-W": 0, "SWISS": 0}
                        
                        summary[id_key][key] = val
                        summary[id_key]["Suma_raw"] += val
                    except: continue

        # Przygotowanie listy do DataFrame
        final_data = []
        for item in summary.values():
            row = {
                "Drużyna": item["Drużyna"],
                "Kraj": item["Kraj"],
                "Suma": format_currency(item["Suma_raw"]),
                "_sort": item["Suma_raw"],
                "CC": format_currency(item["CC"]) if item["CC"] > 0 else "-",
                "MSC-M": format_currency(item["MSC-M"]) if item["MSC-M"] > 0 else "-",
                "MSC-W": format_currency(item["MSC-W"]) if item["MSC-W"] > 0 else "-",
                "SWISS": format_currency(item["SWISS"]) if item["SWISS"] > 0 else "-"
            }
            final_data.append(row)

        self.summary = summary

        df_final = pd.DataFrame(final_data)
        if not df_final.empty:
            df_final = df_final.sort_values(by="_sort", ascending=False)
            self.add_table("ZBIORCZE ZESTAWIENIE DRUŻYNOWE", df_final, 
                          ["Drużyna", "Kraj", "Suma", "CC", "MSC-M", "MSC-W", "SWISS"])
            
class GrandSummaryTab(MultiTableTab):
    def __init__(self, parent):
        super().__init__(parent)
        self.final_df = None # Tutaj będziemy trzymać dane do eksportu
        self.load_grand_summary()

    def load_grand_summary(self):
        # --- (Logika zbierania danych - pozostaje bez zmian) ---
        grand_map = {}
        for nat_code, full_name in ALL_NATIONS_LOOKUP.items():
            grand_map[nat_code] = {
                "Nation": full_name, "NAT": nat_code,
                "MEN_raw": 0, "WOMEN_raw": 0, "TEAM_raw": 0
            }

        def collect_individual(gender, key_raw):
            temp_tab = SummaryTab(tk.Frame(), gender) 
            if hasattr(temp_tab, 'summary_dict'):
                for nat, data in temp_tab.summary_dict.items():
                    if nat in grand_map:
                        grand_map[nat][key_raw] = data["_raw_total"]

        def collect_teams():
            temp_team = TeamSummaryTab(tk.Frame())
            if hasattr(temp_team, 'summary'):
                for item in temp_team.summary.values():
                    nat = item["Kraj"].strip().upper()
                    if nat in grand_map:
                        grand_map[nat]["TEAM_raw"] += item["Suma_raw"]

        collect_individual("M", "MEN_raw")
        collect_individual("W", "WOMEN_raw")
        collect_teams()

        final_list = []
        for nat, d in grand_map.items():
            total = d["MEN_raw"] + d["WOMEN_raw"] + d["TEAM_raw"]
            if total > 0:
                final_list.append({
                    "Nation": d["Nation"], "NAT": d["NAT"],
                    "SUMA": format_currency(total),
                    "MEN": format_currency(d["MEN_raw"]) if d["MEN_raw"] > 0 else "-",
                    "WOMEN": format_currency(d["WOMEN_raw"]) if d["WOMEN_raw"] > 0 else "-",
                    "TEAM": format_currency(d["TEAM_raw"]) if d["TEAM_raw"] > 0 else "-",
                    "SUMA_val": total, "MEN_val": d["MEN_raw"], 
                    "WOMEN_val": d["WOMEN_raw"], "TEAM_val": d["TEAM_raw"]
                })

        self.final_df = pd.DataFrame(final_list)
        
        # Czyścimy widżety przed ponownym rysowaniem
        for widget in self.tables_frame.winfo_children():
            widget.destroy()

        # Przycisk Eksportu (zostaje na górze)
        btn_frame = ttk.Frame(self.tables_frame)
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        export_btn = ttk.Button(btn_frame, text="EKSPORTUJ DO CSV (Nagrody S51.csv)", command=self.export_to_csv)
        export_btn.pack(side="left")

        if not self.final_df.empty:
            self.final_df = self.final_df.sort_values(by="SUMA_val", ascending=False)
            
            # Tworzymy kontener, który wymusi rozciągnięcie tabeli w pionie i poziomie
            container = ttk.Frame(self.tables_frame)
            container.pack(fill="both", expand=True)
            
            # Wywołujemy add_table, która dzięki poprawkom powyżej rozciągnie się na całość
            self.add_table("RANKING FINANSOWY NARODÓW - SEZON S51", 
                          self.final_df, 
                          ["Nation", "NAT", "SUMA", "MEN", "WOMEN", "TEAM"])
            
    def export_to_csv(self):
        if self.final_df is None or self.final_df.empty:
            messagebox.showwarning("Eksport", "Brak danych do eksportu!")
            return
            
        try:
            # Tworzymy folder docelowy, jeśli nie istnieje
            export_dir = Path("./S51")
            os.makedirs(export_dir, exist_ok=True)
            
            # Pełna ścieżka do pliku
            file_name = export_dir / "Nagrody S51.csv"
            
            # Przygotowanie danych do zapisu (wartości liczbowe do obliczeń)
            export_data = self.final_df[["Nation", "NAT", "SUMA_val", "MEN_val", "WOMEN_val", "TEAM_val"]].copy()
            export_data.columns = ["Nation", "NAT", "SUMA", "MEN", "WOMEN", "TEAM"]
            
            # Zapis: separator średnik, kodowanie cp1250 (dla polskiego Excela)
            export_data.to_csv(file_name, sep=';', index=False, encoding='cp1250')
            
            messagebox.showinfo("Eksport", f"Pomyślnie zapisano dane do folderu ./S51:\n{file_name.name}")
        except Exception as e:
            messagebox.showerror("Błąd eksportu", f"Nie udało się zapisać pliku w folderze ./S51: {e}")

def build_gui(parent):
    # Kontener - to on jest "zakładką Nagrody" w głównym Notebooku,
    # żeby pasek z przyciskiem nie wyciekał poza tę zakładkę.
    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)

    # --- Wspólny pasek z jednym przyciskiem odświeżania dla wszystkich zakładek ---
    toolbar = ttk.Frame(container)
    toolbar.pack(side="top", fill="x", padx=6, pady=(4, 0))
    refresh_btn = ttk.Button(toolbar, text="🔄 Odśwież wszystkie zakładki")
    refresh_btn.pack(side="left")
    status_lbl = ttk.Label(toolbar, text="")
    status_lbl.pack(side="left", padx=8)

    all_tabs: list = []

    nb_main = ttk.Notebook(container)
    nb_main.pack(fill="both", expand=True)
    for g_text, g_code in [("MEN", "M"), ("WOMEN", "W")]:
        tab_g = ttk.Frame(nb_main)
        nb_main.add(tab_g, text=g_text)
        nb_sub = ttk.Notebook(tab_g)
        nb_sub.pack(fill="both", expand=True)
        # Turnieje
        for t in ["GP", "SCOC", "WC", "COC", "FC", "JC", "MC", "PC", "QC", "TC", "AC", "BC", "DC"]:
            tab = TournamentTab(nb_sub, t, g_code)
            nb_sub.add(tab, text=t)
            all_tabs.append(tab)
        # Mistrzostwa
        for c in ["OG", "WCH", "SFWC", "NKIC", "IST", "YOG", "UNI", "JWC", "COCH"]:
            if c == "COCH":
                tab_coch = ttk.Frame(nb_sub); nb_sub.add(tab_coch, text="COCH")
                nb_c = ttk.Notebook(tab_coch); nb_c.pack(fill="both", expand=True)
                for reg in ["EUROPE", "ASIA", "NORTHAMERICA", "SOUTHAMERICA", "OCEANIA", "AFRICA"]:
                    tab = ChampionshipTab(nb_c, "COCH", g_code, reg)
                    nb_c.add(tab, text=reg)
                    all_tabs.append(tab)
            else:
                tab = ChampionshipTab(nb_sub, c, g_code)
                nb_sub.add(tab, text=c)
                all_tabs.append(tab)
        tab = SummaryTab(nb_sub, g_code)
        nb_sub.add(tab, text="SUMA")
        all_tabs.append(tab)
    # Sekcja TEAM w głównym Notebooku (nb_main)
    tab_team_root = ttk.Frame(nb_main)
    nb_main.add(tab_team_root, text="TEAM")
    nb_team_sub = ttk.Notebook(tab_team_root)
    nb_team_sub.pack(fill="both", expand=True)

    # Podzakładki turniejowe
    for t in ["CC", "MSC", "SWISS"]:
        tab = TeamTab(nb_team_sub, t)
        nb_team_sub.add(tab, text=t)
        all_tabs.append(tab)

    # NOWA podzakładka SUMA na końcu sekcji TEAM
    tab = TeamSummaryTab(nb_team_sub)
    nb_team_sub.add(tab, text="SUMA")
    all_tabs.append(tab)

    # NOWA GŁÓWNA ZAKŁADKA ALL
    tab = GrandSummaryTab(nb_main)
    nb_main.add(tab, text="ALL")
    all_tabs.append(tab)

    def _refresh_all():
        refresh_btn.config(state="disabled")
        errors = []
        for i, t in enumerate(all_tabs, start=1):
            status_lbl.config(text=f"Odświeżanie... ({i}/{len(all_tabs)})")
            status_lbl.update_idletasks()
            try:
                t._do_refresh()
            except Exception as e:
                errors.append(str(e))
        if errors:
            status_lbl.config(text=f"✓ Odświeżono ({len(all_tabs)}) – błędy: {len(errors)}")
        else:
            status_lbl.config(text=f"✓ Odświeżono wszystkie zakładki ({len(all_tabs)})")
        refresh_btn.config(state="normal")
        status_lbl.after(4000, lambda: status_lbl.config(text=""))

    refresh_btn.config(command=_refresh_all)

    return container

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Nagrody")
    
    # Ta linia odpowiada za maksymalizację okna na starcie:
    root.state('zoomed') 
    
    # Alternatywnie dla Linux/macOS (jeśli 'zoomed' nie zadziała):
    # root.attributes('-zoomed', True)
    
    build_gui(root)
    root.mainloop()