#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Klasyfikacje GUI (embedded)

• Czyta klasyfikacje z folderu ./Klasyfikacje jako pary plików CSV:
    <TAG>__players.csv  oraz  <TAG>__nations.csv
  gdzie TAG to np. WC-M, WC-W, COC-M, JC-W, ... (domyślna kolejność poniżej).
• Alternatywnie potrafi wczytać arkusze z Excela (legacy).
• Każdy TAG ma własną zakładkę z dwoma tabelami: Zawodnicy i Kraje.
• Flaga PNG 18×11 z folderu ./flags (kod kraju w kolumnie NAT).

Udostępnia funkcję: build_gui(parent) → zwraca gotową ramkę ttk.Frame
Można też odpalić plik samodzielnie (python klasyfikacje_gui_embedded.py)
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
import pandas as pd

__all__ = ["build_gui", "KlasyfikacjeFrame"]

FLAGS_DIR_DEFAULT = "./flags"
CSV_DIR_DEFAULT   = "./S44/Klasyfikacje S44"
EXCEL_DEFAULT     = "Klasyfikacje2 S44 — kopia.xlsx"
TOUR_SCHEMAS = {
    "TCS":       ["LP.","JUMPER","NAT","K1","K2","K3","K4","Overall"],
    "FT":        ["LP.","JUMPER","NAT","K1","K2","K3","K4","Overall"],
    "NT":        ["LP.","JUMPER","NAT","K1","K2","K3","K4","Overall"],
    "RAWAIR-W":  ["LP.","JUMPER","NAT","K1","K2","K3","K4","Overall"],
    "BB":        ["LP.","JUMPER","NAT","K1","K2","K3","K4","Overall"],
    "WILLINGEN5":["LP.","JUMPER","NAT","Q1","K1","K2","Overall"],
    "PLANICA7":  ["LP.","JUMPER","NAT","Q1","K1","K2","Overall"],
    "RAWAIR-M":  ["LP.","JUMPER","NAT","Q1","K1","Q2","K2","Overall"],
}

MEN_TOURS  = ["TCS","FT","NT","WILLINGEN5","PLANICA7","RAWAIR-M"]
WOMEN_TOURS = ["RAWAIR-W","BB"]


class KlasyfikacjeFrame(ttk.Frame):
    BASE_PREFIXES = ["WC","COC","FC","GP","SCOC","JC","MC","PC","QC","TC","AC","BC","DC"]
    DEFAULT_ORDER = [f"{p}-M" for p in BASE_PREFIXES] + [f"{p}-W" for p in BASE_PREFIXES]

    def __init__(self, parent, default_excel=EXCEL_DEFAULT, flags_dir=FLAGS_DIR_DEFAULT, default_dir=CSV_DIR_DEFAULT):
        super().__init__(parent)
        self.excel_var = tk.StringVar(value=default_excel)
        self.dir_var   = tk.StringVar(value=default_dir)
        self.nb_sheets = ttk.Notebook(self)
        self.flag_dir  = flags_dir
        self._flag_cache = {}
        self._blank_flag = None
        self.sheet_data  = {}
        # Turnieje: TCS / FT / RAW AIR / itd.
        self._tour_men_var = tk.StringVar(value="TCS")
        self._tour_women_var = tk.StringVar(value="RAWAIR-W")
        self._tour_men_container = None
        self._tour_women_container = None


        self._build_header()
        self.nb_sheets.pack(fill=tk.BOTH, expand=True)

        # Auto: spróbuj CSV‑y; jeśli brak/dziura – nie przerywaj.
        try:
            self.load_csv_dir()
        except Exception:
            try:
                self.load_excel()
            except Exception:
                pass

    # ---------- header ----------
    def _build_header(self):
        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=8, pady=(8,4))

        ttk.Label(bar, text="Folder CSV:").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.dir_var, width=38).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="…", command=self._browse_dir).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(bar, text="Wczytaj CSV", command=self.load_csv_dir).pack(side=tk.LEFT, padx=(0,12))

        ttk.Label(bar, text="Excel (legacy):").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self.excel_var, width=36).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="…", command=self._browse_excel).pack(side=tk.LEFT)
        ttk.Button(bar, text="Wczytaj z Excela", command=self.load_excel).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="Awanse/Spadki juniorów", command=self.awanse_spadki_juniorow).pack(side=tk.LEFT, padx=6)

        self.info_lbl = ttk.Label(bar, text="", foreground="#666")
        self.info_lbl.pack(side=tk.LEFT, padx=10)

    def awanse_spadki_juniorow(self):
        """
        Kopiuje Juniorzy_S<X>.csv z ./<sezon>/ do ./<sezon+1>/,
        zmienia mu nazwę na Juniorzy_S<X+1>.csv i wykonuje awanse/spadki
        na podstawie klasyfikacji narodów z bieżącego sezonu.

        Zasady (M i W osobno):
          JC  -> TOP 3 awansuje do JC z MC; ostatnie 3 z JC spada do MC  (tylko 3!)
          MC  -> PC   po 4
          PC  -> QC   po 4
          QC  -> TC   po 4
          TC  -> AC   po 4
          AC  -> BC   po 4
          BC  -> DC   po 4
          DC  -> nikt nie spada; TOP 4 z DC awansuje do BC
        """
        import re, shutil
        from pathlib import Path
        from tkinter import messagebox

        # --- wykryj sezon ze ścieżki ---
        selected_path = Path(self.dir_var.get().strip())
        match = re.search(r"S(\d+)", str(selected_path))
        if not match:
            messagebox.showerror("Błąd", "Nie udało się wykryć numeru sezonu ze ścieżki folderu.")
            return
        cur_num  = int(match.group(1))
        next_num = cur_num + 1
        cur_tag  = f"S{cur_num}"
        next_tag = f"S{next_num}"

        # --- znajdź plik Juniorzy ---
        cur_dir  = Path(f"./{cur_tag}")
        next_dir = Path(f"./{next_tag}")
        # Szukaj pliku zarówno z podkreślnikiem jak i spacją
        src_file = cur_dir / f"Juniorzy {cur_tag}.csv"
        if not src_file.is_file():
            src_file = cur_dir / f"Juniorzy_{cur_tag}.csv"
        if not src_file.is_file():
            messagebox.showerror("Błąd", f"Nie znaleziono pliku:\nJuniorzy {cur_tag}.csv ani Juniorzy_{cur_tag}.csv w:\n{cur_dir.absolute()}")
            return

        next_dir.mkdir(parents=True, exist_ok=True)
        dst_file = next_dir / f"Juniorzy {next_tag}.csv"

        # --- odczytaj plik juniorów ---
        try:
            df_raw = pd.read_csv(src_file, sep=";", header=0, encoding="utf-8-sig", dtype=str)
        except Exception:
            df_raw = pd.read_csv(src_file, sep=";", header=0, encoding="cp1250", dtype=str)

        # Kolumny: JC-M;MC-M;...;DC-M;;JC-W;MC-W;...;DC-W
        # Pomijamy pustą kolumnę separatora
        TOURS_M = ["JC-M","MC-M","PC-M","QC-M","TC-M","AC-M","BC-M","DC-M"]
        TOURS_W = ["JC-W","MC-W","PC-W","QC-W","TC-W","AC-W","BC-W","DC-W"]

        # Zbuduj słownik tour -> lista drużyn (bez pustych)
        def col_teams(df, col):
            if col not in df.columns:
                return []
            return [str(v).strip() for v in df[col] if str(v).strip() not in ("", "nan")]

        teams = {t: col_teams(df_raw, t) for t in TOURS_M + TOURS_W}

        # --- wczytaj klasyfikacje narodów z pliku nations ---
        csv_root = Path(self.dir_var.get().strip())

        def load_nations_ranking(tag):
            """Zwraca listę NAT posortowaną od najlepszego (1.) do ostatniego."""
            import glob as _glob
            candidates = sorted(_glob.glob(str(csv_root / f"*{tag}__nations.csv")))
            candidates += sorted(_glob.glob(str(csv_root / f"{tag}__nations.csv")))
            path = next((p for p in candidates if Path(p).is_file()), None)
            if not path:
                return []
            try:
                df = self._read_csv_any(path)
            except Exception:
                return []
            df.columns = self._clean_headers(df.columns)
            # normalizuj nazwy kolumn
            col_map = {}
            for c in df.columns:
                u = c.upper().strip()
                if u in ("NAT","CODE","KRAJ"):
                    col_map[c] = "NAT"
                elif u in ("PTS","PUNKTY","POINTS"):
                    col_map[c] = "PTS"
                elif u in ("LP","LP."):
                    col_map[c] = "LP."
            df = df.rename(columns=col_map)
            if "NAT" not in df.columns:
                return []
            if "PTS" in df.columns:
                df["PTS"] = pd.to_numeric(df["PTS"], errors="coerce").fillna(0)
                df = df.sort_values("PTS", ascending=False, kind="stable")
            elif "LP." in df.columns:
                df["LP."] = pd.to_numeric(df["LP."], errors="coerce").fillna(999)
                df = df.sort_values("LP.", ascending=True, kind="stable")
            return [str(v).strip().upper() for v in df["NAT"] if str(v).strip() not in ("", "nan")]

        # --- logika awansów/spadków dla jednej płci ---
        def process_gender(tour_list):
            """
            Oblicza awanse/spadki dla jednej płci.
            Logika per-para, wyniki składane z oryginalnych danych.

            JC <-> MC  : 3 drużyny
            MC..BC pary: 4 drużyny
            DC         : nikt nie spada; TOP 4 z DC awansuje do BC
            """
            def rank_pos(nat, ranking):
                try: return ranking.index(nat)
                except ValueError: return 9999

            pairs  = list(zip(tour_list[:-1], tour_list[1:]))
            n_move = {pairs[0]: 3}
            for p in pairs[1:]:
                n_move[p] = 4

            # Dla każdej pary oblicz na oryginalnych danych:
            #   relegated[pair] = kto spada z WYŻSZEGO do NIŻSZEGO
            #   promoted[pair]  = kto awansuje z NIŻSZEGO do WYŻSZEGO
            relegated = {}
            promoted  = {}
            for higher, lower in pairs:
                n = n_move[(higher, lower)]
                rank_h = load_nations_ranking(higher)
                rank_l = load_nations_ranking(lower)
                sorted_h = sorted(teams[higher], key=lambda x: rank_pos(x, rank_h))
                sorted_l = sorted(teams[lower],  key=lambda x: rank_pos(x, rank_l))
                relegated[(higher, lower)] = sorted_h[-n:]   # ostatnie n z wyższego
                promoted[(higher, lower)]  = sorted_l[:n]    # TOP n z niższego

            # Złóż wyniki: każdy tag traci tych co awansują w górę LUB spadają w dół,
            # zyskuje tych co awansują Z niższego LUB spadają Z wyższego.
            new_teams = {}
            for i, tag in enumerate(tour_list):
                leaving = set()
                arriving = []

                # Jako HIGHER w parze (tag -> lower): traci relegated, zyskuje promoted
                if i < len(tour_list) - 1:
                    pair = (tag, tour_list[i + 1])
                    leaving  |= set(relegated[pair])   # ci spadają w dół
                    arriving += promoted[pair]          # ci awansują z dołu

                # Jako LOWER w parze (higher -> tag): traci promoted, zyskuje relegated
                if i > 0:
                    pair = (tour_list[i - 1], tag)
                    leaving  |= set(promoted[pair])    # ci awansują w górę
                    arriving += relegated[pair]         # ci spadają z góry

                staying = [t for t in teams[tag] if t not in leaving]
                new_teams[tag] = staying + arriving

            return new_teams
        new_m = process_gender(TOURS_M)
        new_w = process_gender(TOURS_W)

        # --- zapisz wynikowy CSV w tym samym formacie ---
        # Długość każdej kolumny
        max_len = max(max(len(v) for v in new_m.values()), max(len(v) for v in new_w.values()))

        def padded(lst, n):
            return lst + [""] * (n - len(lst))

        rows = []
        header = TOURS_M + [""] + TOURS_W
        rows.append(header)
        rows.append([""] * len(header))  # pusta linia 2
        for i in range(max_len):
            row = [padded(new_m[t], max_len)[i] for t in TOURS_M]
            row.append("")  # separator
            row += [padded(new_w[t], max_len)[i] for t in TOURS_W]
            rows.append(row)

        import csv
        try:
            with open(dst_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerows(rows)
            messagebox.showinfo(
                "Awanse/Spadki zakończone",
                f"Plik zapisany:\n{dst_file.absolute()}\n\n"
                f"Awanse/spadki wykonane na podstawie klasyfikacji z:\n{csv_root.absolute()}"
            )
            self.info_lbl.config(text=f"Zapisano: {dst_file.name}")
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać pliku:\n{e}")

    def _browse_dir(self):
        path = filedialog.askdirectory(title="Wybierz folder z klasyfikacjami (CSV)")
        if path:
            self.dir_var.set(path)

    def _browse_excel(self):
        path = filedialog.askopenfilename(
            title="Wybierz plik klasyfikacji (XLSX)",
            filetypes=[("Excel (*.xlsx)", "*.xlsx"), ("Wszystkie pliki", "*.*")]
        )
        if path:
            self.excel_var.set(path)

    # ---------- helpers: flags ----------
    def _get_blank_flag(self):
        if self._blank_flag is None:
            try:
                img = tk.PhotoImage(width=1, height=1)
                img.put("{#FFFFFF}")
                self._blank_flag = img
            except Exception:
                self._blank_flag = None
        return self._blank_flag

    def _get_flag_img(self, nat_code):
        if nat_code is None: return self._get_blank_flag()
        code = str(nat_code).strip().lower()
        if not code: return self._get_blank_flag()
        path = os.path.join(self.flag_dir, f"{code}.png")
        if not os.path.isfile(path):
            return self._get_blank_flag()
        if path not in self._flag_cache:
            try:
                self._flag_cache[path] = tk.PhotoImage(file=path)
            except Exception:
                return self._get_blank_flag()
        return self._flag_cache[path]

    # ---------- table with flags (Lp. frozen on the left) ----------
    def _make_table_with_flags(self, parent, df, name_col, code_col, lp_heading="Lp.", height=24):
        wrap = ttk.Frame(parent)
        wrap.pack(fill=tk.BOTH, expand=True)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=0)
        wrap.grid_columnconfigure(1, weight=1)
        vsb = ttk.Scrollbar(wrap, orient="vertical")
        vsb.grid(row=0, column=2, sticky="ns")

        tvL = ttk.Treeview(wrap, show="tree headings", height=height, selectmode="browse")
        tvL.heading("#0", text=lp_heading)
        tvL.column("#0", width=60, anchor=tk.CENTER, stretch=False)
        tvL.grid(row=0, column=0, sticky="ns")

        tvR = ttk.Treeview(wrap, show="tree headings", height=height)
        tvR.heading("#0", text=name_col)
        tvR.column("#0", width=240, anchor=tk.W, stretch=True)

        right_cols = [c for c in df.columns if c not in ("LP.", "Lp.", name_col)]
        tvR["columns"] = right_cols
        for c in right_cols:
            is_num = (str(getattr(df[c].dtype, "kind", "O")) in "if") or (c.upper() in ("PTS","T","I"))
            anchor = tk.E if is_num else tk.W
            if c.upper() == "PTS":
                anchor = tk.CENTER
            try:
                width = max(60, min(220, int(df[c].astype(str).map(len).max() * 7.0) if len(df) else 100))
            except Exception:
                width = 100
            tvR.column(c, width=width, anchor=anchor, stretch=False)
            tvR.heading(c, text=c)

        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tvR.xview)
        tvR.configure(xscroll=hsb.set)
        hsb.grid(row=1, column=1, sticky="ew")

        def _on_vscroll(*args):
            tvL.yview(*args); tvR.yview(*args)
        vsb.config(command=_on_vscroll)
        tvL.configure(yscroll=lambda *a: vsb.set(*a))
        tvR.configure(yscroll=lambda *a: vsb.set(*a))

        def _wheel(e):
            delta = -1 * (e.delta // 120) if hasattr(e, "delta") else 0
            tvL.yview_scroll(delta, "units")
            tvR.yview_scroll(delta, "units")
            return "break"
        for w in (tvL, tvR):
            w.bind("<MouseWheel>", _wheel)

        tvR.img_refs = []
        lp_col = "LP." if "LP." in df.columns else ("Lp." if "Lp." in df.columns else None)

        def _cell(v):
            if v is None: return ""
            try:
                if pd.isna(v): return ""
            except Exception:
                pass
            if isinstance(v, int) and not isinstance(v, bool): return v
            if isinstance(v, float):
                return int(v) if abs(v - int(v)) < 1e-9 else round(v, 2)
            return v

        for _, row in df.iterrows():
            lp_val = _cell(row.get(lp_col, "")) if lp_col else ""
            tvL.insert("", "end", text=lp_val)

            flag = self._get_flag_img(row.get(code_col))
            tvR.img_refs.append(flag)
            label_text = " " + str(row.get(name_col, ""))
            values = [_cell(row.get(c, "")) for c in right_cols]
            tvR.insert("", "end", text=label_text, image=flag, values=values)

        tvR.grid(row=0, column=1, sticky="nsew")
        return wrap

    # ---------- utils ----------
    @staticmethod
    def _clean_headers(cols):
        return [str(c).strip() for c in cols]

    @staticmethod
    def _read_csv_any(path):
        last = None
        for enc in ("utf-8-sig", "utf-8", "cp1250"):
            try:
                return pd.read_csv(path, sep=None, engine="python", encoding=enc)
            except Exception as e:
                last = e
        # awaryjnie średnik
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8")
        except Exception:
            raise RuntimeError(f"Nie mogę wczytać CSV: {path}\n{last}")

    @staticmethod
    def _players_from_df(df_raw):
        if df_raw is None or df_raw.empty:
            return None
        df = df_raw.copy()
        df.columns = KlasyfikacjeFrame._clean_headers(df.columns)
        mapping = {}
        for c in df.columns:
            u = c.upper()
            if u in ("LP", "LP."):
                mapping[c] = "LP."
            elif u in ("JUMPER","ZAWODNIK","Jumper","jumper"):
                mapping[c] = "JUMPER"
            elif u in ("NAT","KRAJ","Nation Code","Code"):
                mapping[c] = "NAT"
            elif u in ("PTS","PUNKTY","Points"):
                mapping[c] = "PTS"
        if mapping:
            df = df.rename(columns=mapping)
        if "LP." not in df.columns:
            df.insert(0, "LP.", range(1, len(df)+1))
        keep = [c for c in ["LP.", "JUMPER", "NAT", "PTS"] if c in df.columns]
        out = df[keep].copy().dropna(how="all")
        if "PTS" in out.columns:
            out["PTS"] = pd.to_numeric(out["PTS"], errors="coerce").fillna(0.0)
        if "NAT" in out.columns:
            out["NAT"] = out["NAT"].fillna("").astype(str).str.upper()
        return out

    @staticmethod
    def _nations_from_df(df_raw):
        if df_raw is None or df_raw.empty:
            return None
        df = df_raw.copy()
        df.columns = KlasyfikacjeFrame._clean_headers(df.columns)
        mapping = {}
        for c in df.columns:
            u = c.upper()
            if u in ("LP","LP."):
                mapping[c] = "LP."
            elif u in ("NATION","KRAJ","Country"):
                mapping[c] = "NATION"
            elif u in ("NAT","Code"):
                mapping[c] = "NAT"
            elif u in ("T","TEAMS","Team"):
                mapping[c] = "T"
            elif u in ("I","IND","Ind"):
                mapping[c] = "I"
            elif u in ("PTS","PUNKTY","Points"):
                mapping[c] = "PTS"
        if mapping:
            df = df.rename(columns=mapping)
        base_n = ["LP.", "NATION", "NAT", "PTS"]
        with_ti = ["LP.", "NATION", "NAT", "T", "I", "PTS"]
        if set(with_ti).issubset(set(df.columns)):
            keep = with_ti
        else:
            keep = [c for c in base_n if c in df.columns]
        out = df[keep].copy().dropna(how="all")
        if "PTS" in out.columns:
            out["PTS"] = pd.to_numeric(out["PTS"], errors="coerce").fillna(0.0)
        if "NAT" in out.columns:
            out["NAT"] = out["NAT"].fillna("").astype(str).str.upper()
        if "LP." not in out.columns:
            out.insert(0, "LP.", range(1, len(out)+1))
        return out

    def _clear_notebook(self):
        for child in self.nb_sheets.winfo_children():
            child.destroy()
        for tab_id in self.nb_sheets.tabs():
            self.nb_sheets.forget(tab_id)

    # ---------- public: for quotas tab (opcjonalne w Combined) ----------
    def get_nation_ranking(self, tag: str) -> pd.DataFrame:
        d = self.sheet_data.get(tag) or {}
        nations = d.get("nations")
        if nations is None or len(nations) == 0:
            return pd.DataFrame(columns=["NATION","NAT","PTS"])
        df = nations.copy()
        if "PTS" not in df.columns:
            df["PTS"] = 0
        df["PTS"] = pd.to_numeric(df["PTS"], errors="coerce").fillna(0.0)
        df = df.sort_values("PTS", ascending=False, kind="stable").reset_index(drop=True)
        keep = [c for c in ["NATION","NAT","PTS"] if c in df.columns]
        return df[keep]

    # ---------- loaders ----------
    def load_csv_dir(self):
        import os, glob
        root = self.dir_var.get().strip() or CSV_DIR_DEFAULT
        tags = [t for t in self.DEFAULT_ORDER]
        self.sheet_data = {}
        self._clear_notebook()
        missing = 0

        def _pick_classif_file(root: str, tag: str, kind: str) -> str | None:
            """
            Szuka pliku <tag>__{kind}.csv z opcjonalnym prefiksem, np.:
            - {tag}__{kind}.csv
            - S51_{tag}__{kind}.csv
            - (dowolny inny) *_<tag>__{kind}.csv
            Zwraca pełną ścieżkę lub None.
            """
            base = os.path.join(root, f"{tag}__{kind}.csv")
            if os.path.isfile(base):
                return base
            # typowy prefiks sezonu (np. S51_)
            pref = os.path.join(root, f"S51_{tag}__{kind}.csv")
            if os.path.isfile(pref):
                return pref
            # fallback: dowolny prefiks zakończony "_"
            candidates = sorted(glob.glob(os.path.join(root, f"*_{tag}__{kind}.csv")))
            return candidates[0] if candidates else None

        # standardowe zakładki: WC-M, WC-W, COC-M, ...
        for tag in tags:
            tab = ttk.Frame(self.nb_sheets)
            self.nb_sheets.add(tab, text=tag)

            players_path = _pick_classif_file(root, tag, "players")
            nations_path = _pick_classif_file(root, tag, "nations")

            players_df = None
            nations_df = None

            try:
                if players_path:
                    players_df = self._players_from_df(self._read_csv_any(players_path))
                if nations_path:
                    nations_df = self._nations_from_df(self._read_csv_any(nations_path))
            except Exception:
                pass

            self.sheet_data[tag] = {"players": players_df, "nations": nations_df}

            grid = ttk.Frame(tab); grid.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            grid.columnconfigure(0, weight=1); grid.columnconfigure(1, weight=1)

            boxL = ttk.Labelframe(grid, text="Zawodnicy"); boxL.grid(row=0, column=0, sticky="nsew", padx=(0,8))
            if players_df is not None and len(players_df) > 0:
                self._make_table_with_flags(boxL, players_df, name_col="JUMPER", code_col="NAT", lp_heading="Lp.")
            else:
                ttk.Label(boxL, text="Brak danych (players)").pack(padx=8, pady=8, anchor="w")

            boxR = ttk.Labelframe(grid, text="Kraje"); boxR.grid(row=0, column=1, sticky="nsew", padx=(8,0))
            if nations_df is not None and len(nations_df) > 0:
                self._make_table_with_flags(boxR, nations_df, name_col="NATION", code_col="NAT", lp_heading="Lp.")
            else:
                ttk.Label(boxR, text="Brak danych (nations)").pack(padx=8, pady=8, anchor="w")

        # --- dodatkowe zakładki: klasyfikacje turniejów (TCS / FT / RAW AIR / ...) ---

        # MEN
        tab_men = ttk.Frame(self.nb_sheets)
        self.nb_sheets.add(tab_men, text="Turnieje MEN")

        bar_m = ttk.Frame(tab_men); bar_m.pack(fill=tk.X, padx=8, pady=(8,4))
        ttk.Label(bar_m, text="Turniej:").pack(side=tk.LEFT)
        cb_m = ttk.Combobox(
            bar_m,
            textvariable=self._tour_men_var,
            values=MEN_TOURS,
            state="readonly",
            width=14,
        )
        cb_m.pack(side=tk.LEFT, padx=(4,8))
        cb_m.bind("<<ComboboxSelected>>", lambda e: self._reload_tour_men())
        ttk.Button(bar_m, text="Odśwież", command=self._reload_tour_men).pack(side=tk.LEFT)

        self._tour_men_container = ttk.Frame(tab_men)
        self._tour_men_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))

        # WOMEN
        tab_w = ttk.Frame(self.nb_sheets)
        self.nb_sheets.add(tab_w, text="Turnieje WOMEN")

        bar_w = ttk.Frame(tab_w); bar_w.pack(fill=tk.X, padx=8, pady=(8,4))
        ttk.Label(bar_w, text="Turniej:").pack(side=tk.LEFT)
        cb_w = ttk.Combobox(
            bar_w,
            textvariable=self._tour_women_var,
            values=WOMEN_TOURS,
            state="readonly",
            width=14,
        )
        cb_w.pack(side=tk.LEFT, padx=(4,8))
        cb_w.bind("<<ComboboxSelected>>", lambda e: self._reload_tour_women())
        ttk.Button(bar_w, text="Odśwież", command=self._reload_tour_women).pack(side=tk.LEFT)

        self._tour_women_container = ttk.Frame(tab_w)
        self._tour_women_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))

        # info + pierwsze wczytanie turniejów (jeśli pliki istnieją)
        self.info_lbl.config(text=f"Wczytano CSV z: {os.path.abspath(root)}")

        try:
            self._reload_tour_men()
            self._reload_tour_women()
        except Exception:
            pass

    def _load_tour_df(self, tour_code: str) -> pd.DataFrame:
        """Wczytuje i normalizuje klasyfikację turnieju (TCS / FT / RAW AIR / itd.)
        z pliku w folderze z klasyfikacjami (np. S51/Klasyfikacje S51/S51_TCS.csv)."""
        import os, glob
        import pandas as pd

        tour_code = (tour_code or "").strip().upper()
        schema = TOUR_SCHEMAS.get(tour_code)
        if not schema:
            return pd.DataFrame()

        root = self.dir_var.get().strip() or CSV_DIR_DEFAULT
        if not os.path.isdir(root):
            return pd.DataFrame(columns=schema)

        # spróbuj zgadnąć sezon z nazwy katalogu nadrzędnego (np. S51)
        season = os.path.basename(os.path.dirname(root)) if os.path.dirname(root) else ""

        candidates = []
        if season:
            candidates.append(os.path.join(root, f"{season}_{tour_code}.csv"))
        candidates.append(os.path.join(root, f"{tour_code}.csv"))
        candidates.extend(sorted(glob.glob(os.path.join(root, f"*_{tour_code}.csv"))))

        path = next((p for p in candidates if os.path.isfile(p)), None)
        if path is None:
            return pd.DataFrame(columns=schema)

        df = self._read_csv_any(path)
        df.columns = KlasyfikacjeFrame._clean_headers(df.columns)

        # mapowanie podstawowych nagłówków
        mapping = {}
        for c in list(df.columns):
            u = c.upper()
            if u in ("LP","LP."):
                mapping[c] = "LP."
            elif u in ("JUMPER","ZAWODNIK","NAME"):
                mapping[c] = "JUMPER"
            elif u in ("NAT","KRAJ","CODE","NATION CODE"):
                mapping[c] = "NAT"
        if mapping:
            df = df.rename(columns=mapping)

        # dopisz brakujące kolumny ze schematu
        for c in schema:
            if c not in df.columns:
                if c in ("LP.","JUMPER","NAT"):
                    df[c] = ""
                else:
                    df[c] = 0.0

        if "LP." in df.columns:
            df["LP."] = pd.to_numeric(df["LP."], errors="coerce").fillna(0).astype(int)
        else:
            df.insert(0, "LP.", range(1, len(df) + 1))

        if "NAT" in df.columns:
            df["NAT"] = df["NAT"].fillna("").astype(str).str.upper().str.strip()
        if "JUMPER" in df.columns:
            df["JUMPER"] = df["JUMPER"].fillna("").astype(str)

        for c in schema:
            if c in ("LP.","JUMPER","NAT"):
                continue
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

        return df[schema].copy()

    def _reload_tour_men(self):
        from tkinter import ttk
        if self._tour_men_container is None:
            return
        for w in self._tour_men_container.winfo_children():
            w.destroy()
        code = (self._tour_men_var.get() or "").strip().upper()
        df = self._load_tour_df(code)
        if df is None or df.empty:
            ttk.Label(self._tour_men_container, text="Brak danych dla wybranego turnieju.").pack(padx=8, pady=8, anchor="w")
        else:
            self._make_table_with_flags(self._tour_men_container, df, name_col="JUMPER", code_col="NAT", lp_heading="LP.")

    def _reload_tour_women(self):
        from tkinter import ttk
        if self._tour_women_container is None:
            return
        for w in self._tour_women_container.winfo_children():
            w.destroy()
        code = (self._tour_women_var.get() or "").strip().upper()
        df = self._load_tour_df(code)
        if df is None or df.empty:
            ttk.Label(self._tour_women_container, text="Brak danych dla wybranego turnieju.").pack(padx=8, pady=8, anchor="w")
        else:
            self._make_table_with_flags(self._tour_women_container, df, name_col="JUMPER", code_col="NAT", lp_heading="LP.")

    # Legacy Excel loader — kompatybilność wsteczna
    def load_excel(self):
        from pandas import ExcelFile
        path = self.excel_var.get()
        try:
            xls = ExcelFile(path, engine="openpyxl")
        except Exception as e:
            self.info_lbl.config(text=f"Nie mogę wczytać: {e}")
            return

        sheets = [s for s in self.DEFAULT_ORDER if s in xls.sheet_names]
        self._clear_notebook()
        self.info_lbl.config(text=f"Arkuszy: {len(sheets)}")

        def _simple_blocks(df_raw: pd.DataFrame):
            df = df_raw.copy()
            df.columns = [str(c).strip().upper() for c in df.columns]
            p_cols = [c for c in ("LP.","LP", "JUMPER","NAT","PTS") if c in df.columns]
            players = df[p_cols].copy() if {"JUMPER","NAT"}.issubset(set(p_cols)) else None
            if isinstance(players, pd.DataFrame) and "LP." not in players.columns and "LP" in players.columns:
                players.rename(columns={"LP":"LP."}, inplace=True)
            n_cols_ti = [c for c in ("LP.","LP","NATION","NAT","T","I","PTS") if c in df.columns]
            n_cols = [c for c in ("LP.","LP","NATION","NAT","PTS") if c in df.columns]
            nations = df[n_cols_ti].copy() if {"NATION","NAT","T","I"}.issubset(set(n_cols_ti)) else (df[n_cols].copy() if {"NATION","NAT"}.issubset(set(n_cols)) else None)
            if isinstance(nations, pd.DataFrame):
                if "LP." not in nations.columns and "LP" in nations.columns:
                    nations.rename(columns={"LP":"LP."}, inplace=True)
            return players, nations

        for sheet in sheets:
            tab = ttk.Frame(self.nb_sheets); self.nb_sheets.add(tab, text=sheet)
            try:
                df_raw = pd.read_excel(path, sheet_name=sheet, header=0, engine="openpyxl")
                players, nations = _simple_blocks(df_raw)
                self.sheet_data[sheet] = {"players": players, "nations": nations}
            except Exception as e:
                ttk.Label(tab, text=f"Błąd wczytywania arkusza: {e}", foreground="red").pack(fill=tk.X, padx=8, pady=8)
                continue

            grid = ttk.Frame(tab); grid.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
            grid.columnconfigure(0, weight=1); grid.columnconfigure(1, weight=1)

            boxL = ttk.Labelframe(grid, text="Zawodnicy"); boxL.grid(row=0, column=0, sticky="nsew", padx=(0,8))
            if players is not None and len(players) > 0:
                self._make_table_with_flags(boxL, players, name_col="JUMPER", code_col="NAT", lp_heading="Lp.")
            else:
                ttk.Label(boxL, text="Brak danych").pack(padx=8, pady=8, anchor="w")

            boxR = ttk.Labelframe(grid, text="Kraje"); boxR.grid(row=0, column=1, sticky="nsew", padx=(8,0))
            if nations is not None and len(nations) > 0:
                self._make_table_with_flags(boxR, nations, name_col="NATION", code_col="NAT", lp_heading="Lp.")
            else:
                ttk.Label(boxR, text="Brak danych").pack(padx=8, pady=8, anchor="w")

def build_gui(parent):
    """Factory używana przez Combined.import_from(...)."""
    return KlasyfikacjeFrame(parent)

# --- samodzielny podgląd ---
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Klasyfikacje – podgląd")
    try:
        root.state("zoomed")
    except Exception:
        root.geometry("1200x800")
    frm = KlasyfikacjeFrame(root)
    frm.pack(fill=tk.BOTH, expand=True)
    root.mainloop()
