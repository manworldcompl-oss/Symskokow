#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
players_db_gui_embedded
Wersja: 2025-10-31
- Samodzielna zakładka "Baza zawodników" do wpięcia w combined przez build_gui(parent)
- Edycja w miejscu (double-click), filtry niezależne od zapisu
- Zapis zawsze pełnej bazy (nie widoku), do tej samej ścieżki/arkusza co wczytano
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import pandas as pd
import os
from PIL import Image, ImageTk

PREFERRED_COL_ORDER = [
    "Zawodnik","Kraj","Płeć","JUN/SEN","Wiek","UM","Forma","PrawoStartu","Kontuzja"
]

COUNTRY_COL_ALIASES = {"kraj","country","nation","narod"}
NAME_COL_ALIASES = {"zawodnik","name","nazwisko","imie i nazwisko"}

def _safe_to_numeric_series(s):
    """Attempt to convert a Series to numeric. If it fails, return the original Series."""
    try:
        return pd.to_numeric(s)
    except Exception:
        return s

def _canonicalize_headers_editor(df: pd.DataFrame) -> pd.DataFrame:
    """Normalizacja nagłówków do kanonu projektu."""
    if df is None or df.empty:
        return pd.DataFrame(columns=PREFERRED_COL_ORDER)
    # mapowanie nazw
    mapping = {}
    for c in list(df.columns):
        lc = str(c).strip().lower()
        if lc in NAME_COL_ALIASES: mapping[c] = "Zawodnik"
        elif lc in COUNTRY_COL_ALIASES: mapping[c] = "Kraj"
        elif lc in {"plec","płeć","sex","gender"}: mapping[c] = "Płeć"
        elif lc in {"jun/sen","jun","sen","kategoria"}: mapping[c] = "JUN/SEN"
        elif lc in {"wiek","age"}: mapping[c] = "Wiek"
        elif lc in {"um","umiejętność","umiejetnosc","ability"}: mapping[c] = "UM"
        elif lc in {"forma","form"}: mapping[c] = "Forma"
        elif lc in {"prawostartu","ps","prawo startu"}: mapping[c] = "PrawoStartu"
        elif lc in {"kontuzja","injury"}: mapping[c] = "Kontuzja"
        else:
            mapping[c] = c
    df = df.rename(columns=mapping)
    for c in PREFERRED_COL_ORDER:
        if c not in df.columns:
            df[c] = pd.NA
    ordered = [c for c in PREFERRED_COL_ORDER] + [c for c in df.columns if c not in PREFERRED_COL_ORDER]
    df = df[ordered]
    for c in ("Wiek","UM","Forma","PrawoStartu","Kontuzja"):
        if c in df.columns:
            df[c] = _safe_to_numeric_series(df[c])
    return df

class EditableTable(ttk.Frame):
    """Prosta tabela z edycją komórek (double-click)."""
    def __init__(self, master, columns=None, on_cell_commit=None):
        super().__init__(master)
        self._on_cell_commit = on_cell_commit  # (iid, col_name, new_value) -> None
        self._flag_images = {}
        self._tree = ttk.Treeview(self, columns=columns or [], show="tree headings")
        self._tree.column("#0", width=40, stretch=False, anchor="center")
        self._tree.heading("#0", text="")
        vs = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        hs = ttk.Scrollbar(self, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._editor = None
        self._tree.bind("<Double-1>", self._begin_edit)
        # sortowanie po kliknięciu w nagłówek
        self._sort_state = {}
        self._tree.bind("<Button-1>", self._on_heading_click_pre)

    @property
    def tv_main(self):
        return self._tree
    
    def _get_flag(self, country_code):
        """Pobiera obraz flagi na podstawie kodu kraju."""
        if not country_code:
            return ""
        
        code = str(country_code).lower().strip()
        if code in self._flag_images:
            return self._flag_images[code]
        
        # Ścieżka do pliku np. ./flags/pol.png
        flag_path = os.path.join("flags", f"{code}.png")
        
        if os.path.exists(flag_path):
            try:
                img = Image.open(flag_path)
                img = img.resize((16, 11)) # Dopasowanie rozmiaru do wiersza
                photo = ImageTk.PhotoImage(img)
                self._flag_images[code] = photo
                return photo
            except Exception:
                return ""
        return ""

    def set_columns(self, columns):
        self._tree["columns"] = columns
        for c in columns:
            self._tree.heading(c, text=c, anchor="w")
            self._tree.column(c, width=max(60, int(10*len(str(c)))), anchor="w")
        self._tree.update_idletasks()

    def set_dataframe(self, df: pd.DataFrame):
        self._tree.delete(*self._tree.get_children())
        cols = list(df.columns)
        self.set_columns(cols)
        
        # Sprawdzamy, czy mamy kolumnę 'Kraj' do wyświetlenia flagi
        country_col = "Kraj" if "Kraj" in df.columns else None

        for _, r in df.iterrows():
            flag_img = ""
            if country_col:
                # Pobieramy obiekt obrazka na podstawie kodu kraju
                flag_img = self._get_flag(r[country_col])
            
            # ZMIANA: Przekazujemy flag_img do parametru image
            # Wartości tekstowe trafiają do 'values', a ikona do kolumny #0
            self._tree.insert("", "end", values=[r.get(c, "") for c in cols], image=flag_img)

    def dataframe(self) -> pd.DataFrame:
        cols = list(self._tree["columns"]); rows = []
        for iid in self._tree.get_children():
            vals = self._tree.item(iid, "values")
            rows.append({c: vals[i] if i < len(vals) else "" for i, c in enumerate(cols)})
        out = pd.DataFrame(rows, columns=cols)
        for c in ("Wiek","UM","Forma","PrawoStartu","Kontuzja"):
            if c in out.columns:
                out[c] = _safe_to_numeric_series(out[c])
        return out

    # --- edycja komórki ---
    def _begin_edit(self, event):
        if self._tree.identify("region", event.x, event.y) != "cell" : return
        row = self._tree.identify_row(event.y); col_id = self._tree.identify_column(event.x)
        if not row or not col_id or col_id == "#0": return
        col_index = int(col_id.replace("#",""))-1
        col_name = self._tree["columns"][col_index]
        x, y, w, h = self._tree.bbox(row, col_id)
        old = self._tree.set(row, col_name)

        if self._editor is not None:
            try: self._editor.destroy()
            except Exception: pass

        self._editor = tk.Entry(self._tree)
        self._editor.insert(0, old if old is not None else "")
        self._editor.select_range(0, tk.END)
        self._editor.focus_set()
        self._editor.place(x=x, y=y, width=w, height=h)

        def commit(event=None):
            val = self._editor.get()
            self._tree.set(row, col_name, val)
            if callable(self._on_cell_commit):
                self._on_cell_commit(row, col_name, val)
            try: self._editor.destroy()
            except Exception: pass

        def cancel(event=None):
            try: self._editor.destroy()
            except Exception: pass

        self._editor.bind("<Return>", commit)
        self._editor.bind("<Escape>", cancel)

    # --- sort po nagłówku (toggle) ---
    def _on_heading_click_pre(self, event):
        region = self._tree.identify("region", event.x, event.y)
        if region != "heading": return
        col_id = self._tree.identify_column(event.x)
        if not col_id: return
        col_index = int(col_id.replace("#",""))-1
        cols = list(self._tree["columns"])
        if col_index < 0 or col_index >= len(cols): return
        col_name = cols[col_index]
        df = self.dataframe()
        asc = self._sort_state.get(col_name, True)
        try:
            df_sorted = df.sort_values(by=col_name, ascending=asc, kind="mergesort")
        except Exception:
            df_sorted = df.astype({col_name:str}).sort_values(by=col_name, ascending=asc, kind="mergesort")
        self.set_dataframe(df_sorted)
        self._sort_state[col_name] = not asc

class PlayerDBFrame(ttk.Frame):
    """Główna ramka edytora bazy zawodników."""
    def __init__(self, parent):
        super().__init__(parent)
        # --- stan ---
        self._db_path: Path|None = None
        self._db_sheet: str|None = None
        self._full_df: pd.DataFrame|None = None
        self._last_view: pd.DataFrame|None = None
        self._row_map: dict[str,int] = {}

        # --- UI ---
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=(8,4))

        # pole ścieżki + przycisk Wczytaj + przeglądaj
        default_path = None
        try:
            # preferowany plik domyślny
            cand = Path("S45/Zawodnicy S45gpt.csv")
            cand2 = Path("/mnt/data/Zawodnicy S45gpt.csv")
            if cand.exists():
                default_path = str(cand.resolve())
            elif cand2.exists():
                default_path = str(cand2.resolve())
        except Exception:
            default_path = None

        self._path_var = tk.StringVar(value=default_path or (str(self._db_path) if self._db_path else ""))
        ttk.Label(top, text="Plik:").pack(side="left")
        self._path_entry = ttk.Entry(top, textvariable=self._path_var, width=56)
        self._path_entry.pack(side="left", padx=(4,6))

        ttk.Button(top, text="Wczytaj", command=self._load_from_entry).pack(side="left", padx=(0,6))
        ttk.Button(top, text="…", width=3, command=self._browse_and_fill).pack(side="left", padx=(0,12))

        ttk.Button(top, text="Zapisz", command=self._save_db_edit).pack(side="left")

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(
            top, text="🏔 Nowy sezon", command=self._new_season
        ).pack(side="left", padx=(0, 6))

        # filtry
        filt = ttk.Frame(self); filt.pack(fill="x", padx=8, pady=(0,4))
        ttk.Label(filt, text="Kraj").pack(side="left")
        self._flt_country = ttk.Entry(filt, width=10); self._flt_country.pack(side="left", padx=(4,8))

        ttk.Label(filt, text="Płeć").pack(side="left")
        self._flt_sex = ttk.Combobox(filt, values=["","M","W"], width=4, state="readonly")
        self._flt_sex.set("")
        self._flt_sex.pack(side="left", padx=(4,8))

        ttk.Label(filt, text="JUN/SEN").pack(side="left")
        self._flt_junsen = ttk.Combobox(filt, values=["","JUN","SEN"], width=6, state="readonly")
        self._flt_junsen.set("")
        self._flt_junsen.pack(side="left", padx=(4,8))

        ttk.Label(filt, text="Szukaj").pack(side="left")
        self._flt_search = ttk.Entry(filt, width=16); self._flt_search.pack(side="left", padx=(4,8))

        # --- NOWE: Wiek min/max ---
        ttk.Label(filt, text="Wiek").pack(side="left")
        self._flt_age_min = ttk.Entry(filt, width=4)
        self._flt_age_min.insert(0, "10")
        self._flt_age_min.pack(side="left", padx=(4,2))
        ttk.Label(filt, text="–").pack(side="left")
        self._flt_age_max = ttk.Entry(filt, width=4)
        self._flt_age_max.insert(0, "40")
        self._flt_age_max.pack(side="left", padx=(2,8))

        # --- NOWE: filtr Praw Startu ---
        ttk.Label(filt, text="Prawo startu").pack(side="left")
        self._flt_ps = ttk.Combobox(
            filt,
            values=["", "Only WC (1)", "WC (1-3)", "COC (1-6)", "FC (1-7)", "JUN (8)"],
            width=12,
            state="readonly"
        )
        self._flt_ps.set("")
        self._flt_ps.pack(side="left", padx=(4,8))

        ttk.Button(filt, text="Filtruj", command=self._apply_filters).pack(side="left", padx=(4,4))
        ttk.Button(filt, text="Wyczyść filtry", command=self._clear_filters).pack(side="left")
        ttk.Button(filt, text="📊 Raport", command=self._show_country_report).pack(side="left", padx=(8,0))
        # --- operacje masowe na kolumnach ---
        ops = ttk.Frame(self); ops.pack(fill="x", padx=8, pady=(0,6))
        ttk.Label(ops, text="Usuń z 'Kontuzja' dokładną wartość:").pack(side="left")
        self._injury_remove_var = tk.StringVar(value="")
        ttk.Entry(ops, textvariable=self._injury_remove_var, width=6).pack(side="left", padx=(4,6))
        ttk.Button(
            ops, text="Wykonaj",
            command=self._bulk_remove_injury_value
        ).pack(side="left")
        ttk.Separator(ops, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(ops, text="Folder Klasyfikacje:").pack(side="left")
        self._cls_dir_var = tk.StringVar(value="./S45/Klasyfikacje S45")
        ttk.Entry(ops, textvariable=self._cls_dir_var, width=28).pack(side="left", padx=(4,6))
        ttk.Button(ops, text="…", command=self._browse_cls_dir).pack(side="left", padx=(0,6))

        ttk.Button(
            ops, text="Aktualizuj PrawoStartu wg Klasyfikacji",
            command=self._update_rights_from_classif
        ).pack(side="left")
        ttk.Button(
            ops, text="Licz Ability & Sortuj", 
            command=self._calc_and_sort_custom).pack(side="left", padx=5)
        # tabela
        self._db_edit_table = EditableTable(self, on_cell_commit=self._on_cell_commit)
        self._db_edit_table.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # inicjalne puste kolumny
        self._db_edit_table.set_columns(PREFERRED_COL_ORDER)

    def _browse_cls_dir(self):
        from tkinter import filedialog
        start = self._cls_dir_var.get().strip() or "."
        chosen = filedialog.askdirectory(parent=self, initialdir=start, title="Wybierz folder z klasyfikacjami (CSV)")
        if chosen:
            self._cls_dir_var.set(chosen)

    def _bulk_remove_injury_value(self):
        import re
        import pandas as pd
        full = getattr(self, "_full_df", None)
        if full is None or not isinstance(full, pd.DataFrame) or full.empty:
            messagebox.showwarning("Operacja", "Brak wczytanej bazy.", parent=self)
            return
        if "Kontuzja" not in full.columns:
            messagebox.showwarning("Operacja", "Brak kolumny 'Kontuzja' w bazie.", parent=self)
            return

        raw = (self._injury_remove_var.get() or "").strip()
        if not raw:
            messagebox.showwarning("Operacja", "Podaj wartość do usunięcia (np. 3).", parent=self)
            return

        # spróbuj jako liczba
        try:
            x = int(raw)
        except Exception:
            try:
                x = float(raw)
            except Exception:
                messagebox.showwarning("Operacja", f"'{raw}' nie jest liczbą.", parent=self)
                return

        # 1) ścieżka numeryczna: prosto i szybko
        s_num = pd.to_numeric(full["Kontuzja"], errors="coerce")
        mask_num = s_num.eq(x)
        changed_num = int(mask_num.sum())
        if changed_num:
            full.loc[mask_num, "Kontuzja"] = 0

        # 2) ścieżka tekstowa (awaryjnie): usuń TYLKO samotne 'x' (np. '... 3 ...'),
        #    nie zmieniaj '13', '30', '203' itd.
        #    Używamy granic słowa dla cyfr: (?<!\d) i (?!\d)
        pattern = re.compile(rf"(?<!\d){re.escape(str(int(x)))}(?!\d)")
        changed_txt = 0
        if full["Kontuzja"].dtype == object or full["Kontuzja"].dtype.name == "string":
            new_col = []
            for val in full["Kontuzja"]:
                s = "" if val is None else str(val)
                s2 = pattern.sub("", s).strip()
                if s2 != s:
                    changed_txt += 1
                # jeżeli po wycięciu nic sensownego nie zostało, wpisz 0
                try:
                    v = float(s2) if s2 else 0.0
                    new_col.append(v)
                except Exception:
                    new_col.append(0)
            full["Kontuzja"] = new_col

        # sprzątanie typu
        full["Kontuzja"] = pd.to_numeric(full["Kontuzja"], errors="coerce").fillna(0).astype(int)

        # odśwież tabelę według aktywnych filtrów (Twoje filtry pracują na _full_df) :contentReference[oaicite:1]{index=1}
        try:
            self._apply_filters()
        except Exception:
            try:
                self._rebuild_table(full)  # fallback, jeśli filtrów brak
            except Exception:
                pass

        total_changed = changed_num + changed_txt
        messagebox.showinfo(
            "Operacja zakończona",
            f"Wyzerowano {total_changed} wierszy, gdzie Kontuzja == {x}.",
            parent=self
        )

    def _update_rights_from_classif(self):
        import os
        import pandas as pd
        from tkinter import messagebox
        import glob

        full = getattr(self, "_full_df", None)
        if full is None or not isinstance(full, pd.DataFrame) or full.empty:
            messagebox.showwarning("Prawa Startów", "Brak wczytanej bazy zawodników.", parent=self)
            return

        # Kanon nagłówków, porządek typów
        full = full.copy()
        full = _canonicalize_headers_editor(full)
        for c in ["Zawodnik","Kraj"]:
            if c not in full.columns:
                messagebox.showerror("Prawa Startów", f"Brak kolumny '{c}' w bazie.", parent=self)
                return
        if "PrawoStartu" not in full.columns:
            full["PrawoStartu"] = 0

        base_dir = (self._cls_dir_var.get() or "").strip()
        if not base_dir or not os.path.isdir(base_dir):
            messagebox.showwarning("Prawa Startów", "Podaj poprawny folder z klasyfikacjami (CSV).", parent=self)
            return

        # Mapowanie tag → prawo
        tag_right = {
            "WC": 1, "GP": 1,
            "COC": 2, "SCOC": 2,
            "FC": 5,
        }
        prefixes = ["WC","COC","FC","GP","SCOC"]
        sexes = ["M","W"]

        # Zbuduj: (Zawodnik_clean, Kraj_clean) → max_prawo
        rights_map = {}

        def _clean_name(s):
            return str(s or "").strip()

        def _clean_nat(s):
            return str(s or "").upper().strip()

        for pref in prefixes:
            want = tag_right.get(pref, 0)
            if want <= 0:
                continue
            for sx in sexes:
                # akceptuj: <TAG>-<M/W>__players.csv oraz *_<TAG>-<M/W>__players.csv (np. S45_WC-M__players.csv)
                pat1 = os.path.join(base_dir, f"{pref}-{sx}__players.csv")
                pat2 = os.path.join(base_dir, f"*_{pref}-{sx}__players.csv")
                matches = [p for p in (glob.glob(pat1) + glob.glob(pat2)) if os.path.isfile(p)]

                if not matches:
                    continue

                for path in matches:
                    try:
                        # autodetekcja separatora ("," albo ";")
                        df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
                    except Exception:
                        continue

                    cols = {str(c).strip().lower(): c for c in df.columns}
                    name_col = cols.get("jumper") or cols.get("zawodnik")
                    nat_col  = cols.get("nat")    or cols.get("kraj")
                    pts_col  = cols.get("pts")    or cols.get("punkty") or cols.get("points")

                    if not name_col or not nat_col or not pts_col:
                        continue

                    pts = pd.to_numeric(df[pts_col], errors="coerce").fillna(0)
                    has_pts = df.loc[pts > 0]

                    for _, r in has_pts.iterrows():
                        nm = _clean_name(r[name_col])
                        nt = _clean_nat(r[nat_col])
                        if not nm or not nt:
                            continue
                        key = (nm, nt)
                        prev = rights_map.get(key)
                        rights_map[key] = want if prev is None else min(prev, want)

        if not rights_map:
            messagebox.showinfo("Prawa Startów", "Nie znaleziono żadnych punktujących zawodników w CSV.", parent=self)
            return

        # Aktualizacja w bazie: bierz maksimum z obecnego PrawoStartu i wyliczonego
        changed = 0
        for i, row in full.iterrows():
            nm = _clean_name(row.get("Zawodnik"))
            nt = _clean_nat(row.get("Kraj"))
            key = (nm, nt)
            new_ps = rights_map.get(key, None)
            if new_ps is not None:
                cur = pd.to_numeric(row.get("PrawoStartu", 0), errors="coerce")
                cur = int(cur) if pd.notna(cur) else 0
                if cur == 0:
                    full.at[i, "PrawoStartu"] = new_ps
                    changed += 1
                else:
                    better = min(cur, new_ps)
                    if better != cur:
                        full.at[i, "PrawoStartu"] = better
                        changed += 1

        # Zapis do stanu i odśwież widok z aktywnymi filtrami
        self._full_df = full
        try:
            self._apply_filters()
        except Exception:
            self._rebuild_table(full)

        messagebox.showinfo("Prawa Startów", f"Zaktualizowano {changed} wierszy (PrawoStartu).", parent=self)
    
    def _calc_and_sort_custom(self):
        """
        Oblicza parametr ability i sortuje bazę wg wytycznych:
        Kraj (A-Z) -> Płeć (A-Z) -> Ability (od największego)
        Uwzględnia karę -400 za kontuzję.
        """
        if self._full_df is None or self._full_df.empty:
            messagebox.showwarning("Błąd", "Najpierw wczytaj bazę zawodników!")
            return

        # 1. Przygotowanie kopii danych i konwersja na liczby dla obliczeń
        df = self._full_df.copy()
        um = pd.to_numeric(df["UM"], errors='coerce').fillna(0)
        forma = pd.to_numeric(df["Forma"], errors='coerce').fillna(0)
        wiek = pd.to_numeric(df["Wiek"], errors='coerce').fillna(0)
        kontuzja = pd.to_numeric(df["Kontuzja"], errors='coerce').fillna(0)

        # a) wylicza bazowe ability: 0,7 * UM + 0,3 * Forma - Wiek * (-0,001)
        ability = 0.7 * um + 0.3 * forma - wiek * (-0.001)

        # b) Dodanie kary -400, jeżeli kontuzja > 0
        # Używamy np.where: jeśli warunek spełniony -> ability - 400, w przeciwnym razie -> ability
        import numpy as np
        df["_tmp_ability"] = np.where(kontuzja > 0, ability - 400, ability)

        # c, d, e) Sortowanie wielopoziomowe: Kraj (A-Z), Płeć (A-Z), Ability (desc)
        df = df.sort_values(
            by=["Kraj", "Płeć", "_tmp_ability"], 
            ascending=[True, True, False]
        )

        # Usuwamy kolumnę tymczasową przed zapisem do stanu głównego
        self._full_df = df.drop(columns=["_tmp_ability"])

        # Odświeżamy widok w tabeli
        try:
            self._apply_filters()
        except Exception:
            self._rebuild_table(self._full_df)
            
        messagebox.showinfo("Sukces", "Wyliczono ability (z uwzględnieniem kontuzji) i posortowano!")

    def _load_from_entry(self):
        path_str = (self._path_var.get() or "").strip()
        if not path_str:
            messagebox.showwarning("Wczytywanie", "Podaj ścieżkę do pliku bazy (CSV/XLSX).")
            return
        self._load_db_from_path(Path(path_str))

    def _browse_and_fill(self):
        initial = str(Path(self._path_var.get()).parent) if self._path_var.get() else (str(self._db_path.parent) if self._db_path else str(Path.cwd()))
        chosen = filedialog.askopenfilename(
            parent=self, title="Wybierz plik bazy zawodników",
            filetypes=[("Arkusze Excel","*.xlsx *.xlsm *.xls"),("CSV","*.csv"),("Wszystkie pliki","*.*")],
            initialdir=initial
        )
        if not chosen:
            return
        self._path_var.set(chosen)
        self._load_db_from_path(Path(chosen))
    # --- budulec tabeli + mapowanie ---
    def _rebuild_table(self, df_view: pd.DataFrame):
        if self._full_df is not None and "_ROWID" not in self._full_df.columns:
            self._full_df["_ROWID"] = self._full_df.index

        df_v = df_view.copy()
        if "_ROWID" not in df_v.columns and self._full_df is not None:
            key_cols = [c for c in ["Zawodnik","Kraj"] if c in df_v.columns and c in self._full_df.columns]
            if key_cols:
                tmp = self._full_df[key_cols + ["_ROWID"]].drop_duplicates()
                df_v = df_v.merge(tmp, on=key_cols, how="left")
            else:
                df_v["_ROWID"] = pd.NA

        self._db_edit_table.set_dataframe(df_v.drop(columns=["_ROWID"], errors="ignore"))

        self._row_map.clear()
        tv = self._db_edit_table.tv_main
        rowids = list(df_v["_ROWID"]) if "_ROWID" in df_v.columns else [None]*len(tv.get_children())
        for iid, rowid in zip(tv.get_children(), rowids):
            self._row_map[iid] = int(rowid) if (rowid is not None and pd.notna(rowid)) else None

        self._last_view = df_v

    # --- edycja pojedynczej komórki
    def _on_cell_commit(self, iid: str, col_name: str, new_value):
        import pandas as pd

        if not isinstance(getattr(self, "_full_df", None), pd.DataFrame) or self._full_df.empty:
            return

        # 1) Zbierz wartości z aktualnego wiersza w Treeview (po sortowaniu to JEST prawda)
        tv = self._db_edit_table.tv_main  # Treeview
        vals = tv.item(iid, "values")
        cols = list(tv["columns"])  # kolejność kolumn w widoku
        row_dict = {c: vals[i] for i, c in enumerate(cols) if i < len(vals)}

        # 2) Ustal index w _full_df:
        base_idx = None

        # (a) jeśli mamy ukryty _ROWID w widoku – to najpewniejsze
        if "_ROWID" in row_dict and pd.notna(row_dict["_ROWID"]):
            try:
                base_idx = int(row_dict["_ROWID"])
            except Exception:
                base_idx = None

        # (b) w przeciwnym wypadku – po kluczach: Zawodnik + Kraj (najczęściej unikalne)
        if base_idx is None:
            key_name = row_dict.get("Zawodnik", None)
            key_nat  = None
            for c in ("Kraj", "NAT", "Nation", "NATION"):
                if c in row_dict:
                    key_nat = row_dict[c]
                    break
            if key_name is not None:
                mask = (self._full_df["Zawodnik"].astype(str) == str(key_name))
                if key_nat is not None and any(c in self._full_df.columns for c in ("Kraj","NAT","Nation","NATION")):
                    for c in ("Kraj","NAT","Nation","NATION"):
                        if c in self._full_df.columns:
                            mask = mask & (self._full_df[c].astype(str) == str(key_nat))
                            break
                idxs = self._full_df.index[mask]
                if len(idxs):
                    base_idx = idxs[0]

        # (c) ostatni fallback – stara mapa, jeśli istnieje
        if base_idx is None:
            base_idx = getattr(self, "_row_map", {}).get(iid, None)

        if base_idx is None or col_name not in self._full_df.columns:
            return

        # 3) Zapis do _full_df z typowaniem liczbowym jeśli trzeba
        old = self._full_df.at[base_idx, col_name]
        if pd.api.types.is_numeric_dtype(self._full_df[col_name]) or isinstance(old, (int, float)):
            try:
                self._full_df.at[base_idx, col_name] = (
                    pd.to_numeric([new_value])[0] if new_value not in ("", None) else pd.NA
                )
            except Exception:
                self._full_df.at[base_idx, col_name] = new_value
        else:
            self._full_df.at[base_idx, col_name] = new_value

    @staticmethod
    def _read_csv_any(path: Path) -> pd.DataFrame:
        last = None
        for enc in ("utf-8-sig", "utf-8", "cp1250", "latin1"):
            try:
                return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
            except Exception as e:
                last = e
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8")
        except Exception:
            raise RuntimeError(f"Nie mogę wczytać CSV: {path}\n{last}")
        
    # --- wczytanie ---
    def _browse_and_load(self):
        # legacy: keep, but sync with entry
        initial = str(self._db_path.parent) if self._db_path else str(Path.cwd())
        path = filedialog.askopenfilename(
            parent=self, title="Wybierz plik bazy zawodników",
            filetypes=[("Arkusze Excel","*.xlsx *.xlsm *.xls"),("CSV","*.csv"),("Wszystkie pliki","*.*")],
            initialdir=initial
        )
        if not path: return
        self._load_db_from_path(Path(path))

    def _load_db_from_path(self, p: Path):
        self._db_path = Path(p)
        self._db_sheet = None
        if not self._db_path.exists():
            messagebox.showerror("Wczytywanie", f"Plik nie istnieje:\n{self._db_path}")
            return
        if self._db_path.suffix.lower() == ".csv":
            df = self._read_csv_any(self._db_path)
        elif self._db_path.suffix.lower() in (".xlsx",".xlsm",".xls"):
            x = pd.ExcelFile(self._db_path)
            sheet_name = "Zawodnicy" if "Zawodnicy" in x.sheet_names else x.sheet_names[0]
            self._db_sheet = sheet_name
            df = pd.read_excel(self._db_path, sheet_name=sheet_name)
        else:
            messagebox.showerror("Wczytywanie", f"Nieobsługiwane rozszerzenie: {self._db_path.suffix}")
            return

        df = _canonicalize_headers_editor(df)
        self._full_df = df.copy()
        self._rebuild_table(self._full_df)

    # --- zapis ---
    def _save_db_edit(self):
        from pathlib import Path
        import pandas as pd

        is_filtered = (
            self._flt_country.get().strip() != "" or
            self._flt_sex.get().strip() != "" or
            self._flt_junsen.get().strip() != "" or
            self._flt_search.get().strip() != "" or
            (hasattr(self, "_flt_ps") and self._flt_ps.get().strip() != "")
        )
        
        # Sprawdzamy filtry wieku z uwzględnieniem Twoich wyjątków
        age_min = self._flt_age_min.get().strip()
        age_max = self._flt_age_max.get().strip()
        
        if age_min not in ("", "10"):
            is_filtered = True
        
        if age_max not in ("", "40"):
            is_filtered = True

        if is_filtered:
            messagebox.showwarning(
                "Zapis zablokowany", 
                "Masz aktywne filtry, które ukrywają część zawodników!\n\n"
                "Wyczyść filtry przed zapisem, aby nie stracić danych osób, "
                "których obecnie nie widzisz w tabeli.", 
                parent=self
            )
            return
        
        path_str = (self._path_var.get() or "").strip()
        if not path_str:
            messagebox.showwarning("Zapis", "Podaj ścieżkę do pliku (CSV/XLSX).", parent=self)
            return
        path = Path(path_str)

        try:
            # KLUCZOWA ZMIANA: Pobieramy dane z widoku tabeli, a nie z pamięci bazy
            # Dzięki temu zachowujemy aktualną kolejność (sortowanie) i aktywne filtry
            out_df = self._db_edit_table.dataframe()

            if out_df.empty:
                messagebox.showwarning("Zapis", "Tabela jest pusta. Nic nie zapisano.", parent=self)
                return

            # Opcjonalnie: normalizacja nagłówków przed samym zapisem
            out_df = _canonicalize_headers_editor(out_df)

            # Zapis do odpowiedniego formatu
            if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
                out_df.to_excel(path, index=False)
            else:
                # utf-8-sig zapewnia poprawne wyświetlanie polskich znaków w Excelu
                out_df.to_csv(path, index=False, encoding="utf-8-sig")

            messagebox.showinfo("Zapis", f"Zapisano aktualny widok: {path.name} ({len(out_df)} wierszy)", parent=self)
        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e), parent=self)

    def _apply_filters(self):
        """Zastosuj filtry (jeśli są zdefiniowane) i odśwież tabelę."""
        import pandas as pd

        full = getattr(self, "_full_df", None)
        if full is None or not isinstance(full, pd.DataFrame) or full.empty:
            # nic nie wczytane – nic nie rób, żeby nie wywalić GUI
            return

        df = full.copy()

        # pobierz wartości z pól filtrów tylko jeśli istnieją
        name_q = getattr(self, "_flt_name", None)
        nat_q  = getattr(self, "_flt_nat",  getattr(self, "_flt_country", None))
        sex_q  = getattr(self, "_flt_sex", None)

        um_min = getattr(self, "_flt_um_min", None)
        um_max = getattr(self, "_flt_um_max", None)
        fo_min = getattr(self, "_flt_forma_min", None)
        fo_max = getattr(self, "_flt_forma_max", None)

        # tekstowe – zawiera (case-insensitive)
        if name_q and "Zawodnik" in df.columns:
            q = str(name_q.get()).strip().lower()
            if q:
                df = df[df["Zawodnik"].astype(str).str.lower().str.contains(q, na=False)]

        if nat_q and any(c in df.columns for c in ("Kraj","NAT","Nation","NATION")):
            q = str(nat_q.get()).strip().lower()
            if q:
                for c in ("Kraj","NAT","Nation","NATION"):
                    if c in df.columns:
                        df = df[df[c].astype(str).str.lower().str.contains(q, na=False)]
                        break

        if sex_q and any(c in df.columns for c in ("Płeć","Sex","SEX")):
            q = str(sex_q.get()).strip().upper()
            if q:
                for c in ("Płeć","Sex","SEX"):
                    if c in df.columns:
                        df = df[df[c].astype(str).str.upper().str.contains(q, na=False)]
                        break

        # --- JUN/SEN ---
        j_val = ""
        try:
            j_val = (self._flt_junsen.get() or "").strip().upper()
        except Exception:
            j_val = ""

        if j_val:
            # znajdź kolumnę JUN/SEN (różne wersje pliku mogą mieć różne nagłówki)
            col_js = None
            for c in df.columns:
                lc = str(c).strip().lower()
                if lc in ("JUN/SEN", "jun/sen", "jun", "sen", "kategoria"):
                    col_js = c
                    break
            if col_js is not None:
                df = df[df[col_js].astype(str).str.upper().eq(j_val)]

        # --- NOWE: WIEK min/max ---
        if "Wiek" in df.columns:
            vmin = (self._flt_age_min.get() or "").strip()
            if vmin:
                try:
                    age = pd.to_numeric(df["Wiek"], errors="coerce")
                    df = df[age >= float(vmin)]
                except Exception:
                    pass

            vmax = (self._flt_age_max.get() or "").strip()
            if vmax:
                try:
                    age = pd.to_numeric(df["Wiek"], errors="coerce")
                    df = df[age <= float(vmax)]
                except Exception:
                    pass

        # --- NOWE: PRAWO STARTU ---
        if "PrawoStartu" in df.columns:
            ps = pd.to_numeric(df["PrawoStartu"], errors="coerce").fillna(999).astype(int)
            sel = (self._flt_ps.get() or "").strip()

            if sel == "Only WC (1)":
                df = df[ps == 1]
            elif sel == "WC (1-3)":
                df = df[(ps >= 1) & (ps <= 3)]
            elif sel == "COC (1-6)":
                df = df[(ps >= 1) & (ps <= 6)]
            elif sel == "FC (1-7)":
                df = df[(ps >= 1) & (ps <= 7)]
            elif sel == "JUN (8)":
                df = df[ps == 8]

        # numeryczne – zakresy
        def _num(col):
            if col in df.columns:
                return pd.to_numeric(df[col], errors="coerce")
            return None

        um = _num("UM")
        if um is not None:
            v = um_min.get() if um_min else ""
            if str(v).strip():
                try: df = df[um >= float(v)]
                except: pass
            v = um_max.get() if um_max else ""
            if str(v).strip():
                try: df = df[um <= float(v)]
                except: pass

        fo = _num("Forma")
        if fo is not None:
            v = fo_min.get() if fo_min else ""
            if str(v).strip():
                try: df = df[fo >= float(v)]
                except: pass
            v = fo_max.get() if fo_max else ""
            if str(v).strip():
                try: df = df[fo <= float(v)]
                except: pass

        # odśwież tabelę – różne wersje pliku mają różny podpis _rebuild_table
        try:
            self._rebuild_table(self._full_df, df_view=df)
        except TypeError:
            self._rebuild_table(df_view=df)

        # licznik/info jeśli jest label
        info = getattr(self, "_db_edit_info", None)
        if info:
            info.config(text=f"Widok: {len(df)} / {len(full)}")

    def _show_country_report(self):
        """Otwiera nowe okno z raportem: Kraj | Flaga | M | W dla aktualnego widoku (po filtrach)."""
        import os
        from PIL import Image, ImageTk

        # Pobierz aktualnie wyświetlane dane (po filtrach)
        last = getattr(self, "_last_view", None)
        full = getattr(self, "_full_df", None)

        # Jeśli nie ma widoku po filtrach, weź pełną bazę
        if last is not None and isinstance(last, pd.DataFrame) and not last.empty:
            df = last.copy()
        elif full is not None and isinstance(full, pd.DataFrame) and not full.empty:
            df = full.copy()
        else:
            messagebox.showwarning("Raport", "Brak danych do raportu. Wczytaj bazę zawodników.", parent=self)
            return

        if "Kraj" not in df.columns or "Płeć" not in df.columns:
            messagebox.showwarning("Raport", "Brak kolumn 'Kraj' lub 'Płeć' w danych.", parent=self)
            return

        # Upewnij się że płeć jest uppercase
        df["_plec"] = df["Płeć"].astype(str).str.strip().str.upper()
        df["_kraj"] = df["Kraj"].astype(str).str.strip()

        # Zgrupuj po kraju
        grouped = df.groupby("_kraj")
        report_rows = []
        for kraj, group in sorted(grouped, key=lambda x: x[0]):
            m_count = int((group["_plec"] == "M").sum())
            w_count = int((group["_plec"] == "W").sum())
            report_rows.append((kraj, m_count, w_count))

        total_m = sum(r[1] for r in report_rows)
        total_w = sum(r[2] for r in report_rows)
        total_all = total_m + total_w

        # --- Okno raportu ---
        win = tk.Toplevel(self)
        win.title("📊 Raport — zawodnicy wg kraju")
        win.geometry("520x500")
        win.resizable(True, True)

        # Nagłówek z info o filtrach
        hdr = ttk.Frame(win)
        hdr.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(
            hdr,
            text=f"Łącznie: {total_all} zawodników  |  M: {total_m}  |  W: {total_w}",
            font=("TkDefaultFont", 10, "bold")
        ).pack(side="left")

        # Tabela wyników
        cols = ("Kraj", "M", "W", "Razem")
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        tv = ttk.Treeview(frame, columns=cols, show="tree headings", selectmode="browse")
        tv.column("#0", width=28, stretch=False, anchor="center")
        tv.heading("#0", text="")
        tv.column("Kraj",   width=200, anchor="w")
        tv.column("M",      width=70,  anchor="center")
        tv.column("W",      width=70,  anchor="center")
        tv.column("Razem",  width=80,  anchor="center")

        tv.heading("Kraj",  text="Kraj")
        tv.heading("M",     text="M ♂")
        tv.heading("W",     text="W ♀")
        tv.heading("Razem", text="Razem")

        vs = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        tv.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Cache na obrazki flag (żeby nie były zbierane przez GC)
        _flag_cache = {}

        def _get_flag(country_code):
            code = str(country_code).lower().strip()
            if code in _flag_cache:
                return _flag_cache[code]
            flag_path = os.path.join("flags", f"{code}.png")
            if os.path.exists(flag_path):
                try:
                    img = Image.open(flag_path).resize((16, 11))
                    photo = ImageTk.PhotoImage(img)
                    _flag_cache[code] = photo
                    return photo
                except Exception:
                    pass
            return ""

        # Wypełnij tabelę
        for kraj, m_c, w_c in report_rows:
            flag = _get_flag(kraj)
            tv.insert("", "end",
                      values=(kraj, m_c if m_c else "–", w_c if w_c else "–", m_c + w_c),
                      image=flag)

        # Wiersz sumy na dole (poza Treeview — w osobnym pasku)
        footer = ttk.Frame(win)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Separator(footer).pack(fill="x", pady=(0, 4))
        ttk.Label(footer, text=f"SUMA   M: {total_m}   W: {total_w}   Razem: {total_all}",
                  font=("TkDefaultFont", 9, "bold")).pack(side="left")

        # Przycisk zamknij
        ttk.Button(footer, text="Zamknij", command=win.destroy).pack(side="right")

        # Zatrzymaj referencje do flag żeby GC ich nie zebrał
        win._flag_cache = _flag_cache

    def _clear_filters(self):
        """Wyczyść pola filtrów (jeśli istnieją) i odśwież pełen widok."""
        # wyzeruj Entry/Combobox/Spinbox jeśli są
        for attr in ("_flt_name","_flt_nat","_flt_country","_flt_sex","_flt_junsen",
            "_flt_um_min","_flt_um_max","_flt_forma_min","_flt_forma_max",
            "_flt_age_min","_flt_age_max","_flt_ps"):
            w = getattr(self, attr, None)
            try:
                w.set("")   # dla tk.StringVar / tk.Variable
            except Exception:
                try:
                    w.delete(0, "end")  # dla widgetów Entry
                except Exception:
                    pass

        # odśwież pełen DF
        try:
            self._rebuild_table(self._full_df, df_view=self._full_df)
        except TypeError:
            self._rebuild_table(df_view=self._full_df)

        info = getattr(self, "_db_edit_info", None)
        if info and hasattr(self, "_full_df"):
            info.config(text=f"Widok: {len(self._full_df)} / {len(self._full_df)}")

    # -----------------------------------------------------------------------
    # NOWY SEZON
    # -----------------------------------------------------------------------
    def _new_season(self):
        """Obsługa przycisku 'Nowy sezon':
        a) Kopiuje plik do ./S{N+1}/Zawodnicy S{N+1}gpt.csv
        b) +1 do Wiek
        c) Czyści Kontuzja (→ 0)
        d) PrawoStartu: 2→3, 3→4, 5→6, 6→7
        e) Zmniejsza UM i Forma wg tabeli wiek/płeć (min 0)
        f) Zawodnicy z UM==0 lub Forma==0 → Zakończone kariery
        g) Zawodnik osiąga 15 lat → PrawoStartu=7, JUN/SEN→SEN
        """
        import re, shutil
        import pandas as pd
        from pathlib import Path
        from tkinter import messagebox

        # ---------- 1. Sprawdź, czy mamy załadowaną bazę ----------
        full = getattr(self, "_full_df", None)
        if full is None or not isinstance(full, pd.DataFrame) or full.empty:
            messagebox.showwarning("Nowy sezon", "Najpierw wczytaj bazę zawodników.", parent=self)
            return

        # ---------- 2. Wykryj numer sezonu z nazwy pliku ----------
        path_str = (self._path_var.get() or "").strip()
        if not path_str:
            messagebox.showwarning("Nowy sezon", "Brak ścieżki do pliku.", parent=self)
            return
        current_path = Path(path_str)

        # Szukamy numeru sezonu (np. S45 → 38)
        m = re.search(r"[Ss](\d+)", current_path.name)
        if not m:
            messagebox.showerror(
                "Nowy sezon",
                f"Nie mogę wykryć numeru sezonu z nazwy pliku:\n{current_path.name}\n"
                "Oczekiwana konwencja: …S45….csv",
                parent=self
            )
            return
        old_num = int(m.group(1))
        new_num = old_num + 1
        old_tag = f"S{old_num}"
        new_tag = f"S{new_num}"

        # ---------- 3. Ścieżka docelowa ----------
        new_dir = Path(f"./{new_tag}")
        new_filename = current_path.name.replace(old_tag, new_tag)
        new_path = new_dir / new_filename

        # ---------- 4. Potwierdzenie ----------
        careers_path_default = current_path.parent / "Zakończone kariery.csv"
        # szukamy pliku karier – może być w tym samym folderze lub obok
        careers_candidates = [
            careers_path_default,
            Path("./Zakończone kariery.csv"),
            Path("Zakończone_kariery.csv"),
            current_path.parent.parent / "Zakończone kariery.csv",
        ]
        careers_path = None
        for c in careers_candidates:
            if c.exists():
                careers_path = c
                break

        confirm = messagebox.askyesno(
            "Nowy sezon",
            f"Rozpocząć nowy sezon {new_tag}?\n\n"
            f"• Plik zostanie skopiowany do:\n  {new_path.resolve()}\n"
            f"• Wiek +1, kontuzje wyczyszczone\n"
            f"• PrawoStartu zaktualizowane\n"
            f"• UM i Forma obniżone wg tabel\n"
            f"• Zakończone kariery → {careers_path or 'Zakończone kariery.csv'}\n\n"
            "Kontynuować?",
            parent=self
        )
        if not confirm:
            return

        # ---------- 5. Praca na kopii df ----------
        df = full.copy()

        # Upewnij się, że kolumny numeryczne są liczbami
        for col in ("Wiek", "UM", "Forma", "PrawoStartu", "Kontuzja"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        # ---- b) Wiek +1 ----
        df["Wiek"] = df["Wiek"] + 1

        # ---- c) Usuń kontuzje ----
        df["Kontuzja"] = 0

        # ---- d) PrawoStartu: 2→3, 3→4, 5→6, 6→7 ----
        ps_map = {2: 3, 3: 4, 5: 6, 6: 7}
        df["PrawoStartu"] = df["PrawoStartu"].map(lambda x: ps_map.get(x, x))

        # ---- g) Zawodnicy, którzy osiągnęli dokładnie 15 lat: PrawoStartu=7, JUN→SEN ----
        mask_15 = df["Wiek"] >= 15
        df.loc[mask_15 & (df["JUN/SEN"] == "JUN"), "PrawoStartu"] = 7
        df.loc[mask_15 & (df["JUN/SEN"] == "JUN"), "JUN/SEN"] = "SEN"

        # ---- e) Tabele spadku UM/Forma wg wieku i płci ----
        # Format: wiek -> (spadek_UM, spadek_Forma)
        _DROP_M = {
            11: (9, 12), 12: (9, 12), 13: (9, 12),
            14: (10, 13), 15: (10, 13), 16: (10, 13), 17: (10, 13), 18: (10, 13),
            19: (11, 14), 20: (11, 14), 21: (11, 14),
            22: (12, 16), 23: (12, 16), 24: (12, 16),
            25: (13, 17), 26: (13, 17),
            27: (14, 18), 28: (14, 18),
            29: (16, 21), 30: (16, 21),
            31: (17, 22),
            32: (18, 24),
            33: (19, 25),
            34: (20, 26),
            35: (21, 28),
            36: (22, 29),
            37: (23, 30),
            38: (24, 32),
            39: (25, 33),
        }
        _DROP_M_OVER40 = (27, 36)

        _DROP_W = {
            11: (9, 12), 12: (9, 12), 13: (9, 12),
            14: (10, 13), 15: (10, 13), 16: (10, 13), 17: (10, 13), 18: (10, 13),
            19: (11, 14), 20: (11, 14), 21: (11, 14),
            22: (12, 16), 23: (12, 16),
            24: (13, 17), 25: (13, 17),
            26: (14, 18), 27: (14, 18),
            28: (16, 21), 29: (16, 21),
            30: (18, 24), 31: (18, 24),
            32: (20, 26),
            33: (21, 28),
            34: (22, 29),
            35: (23, 30),
            36: (24, 32),
            37: (25, 33),
            38: (26, 34),
            39: (27, 36),
        }
        _DROP_W_OVER40 = (30, 40)

        def _get_drop(plec, wiek):
            if plec == "M":
                if wiek >= 40:
                    return _DROP_M_OVER40
                return _DROP_M.get(wiek, (0, 0))
            else:  # W
                if wiek >= 40:
                    return _DROP_W_OVER40
                return _DROP_W.get(wiek, (0, 0))

        for idx, row in df.iterrows():
            plec = str(row.get("Płeć", "M")).strip().upper()
            wiek = int(row.get("Wiek", 0))
            drop_um, drop_forma = _get_drop(plec, wiek)
            new_um = max(0, int(row.get("UM", 0)) - drop_um)
            new_forma = max(0, int(row.get("Forma", 0)) - drop_forma)
            df.at[idx, "UM"] = new_um
            df.at[idx, "Forma"] = new_forma

        # ---- f) Zawodnicy z UM==0 lub Forma==0 → Zakończone kariery ----
        mask_retired = (df["UM"] <= 0) | (df["Forma"] <= 0)
        retired = df[mask_retired].copy()
        df = df[~mask_retired].copy()

        # Zapis do Zakończone kariery
        if not retired.empty:
            # Ustal ścieżkę do pliku karier (szukamy go względem bieżącego pliku)
            if careers_path is None:
                careers_path = current_path.parent / "Zakończone kariery.csv"

            # Buduj rekordy karier
            new_careers_rows = []
            for _, row in retired.iterrows():
                new_careers_rows.append({
                    "Kraj": row.get("Kraj", ""),
                    "Płeć": row.get("Płeć", ""),
                    "Zawodnik": row.get("Zawodnik", ""),
                    "Sezon": new_tag,
                    "Wiek": row.get("Wiek", ""),
                })

            # Dołącz do istniejącego pliku lub utwórz nowy
            if careers_path.exists():
                try:
                    existing = pd.read_csv(careers_path, sep=";", encoding="utf-8-sig")
                except Exception:
                    try:
                        existing = pd.read_csv(careers_path, sep=";", encoding="cp1250")
                    except Exception:
                        existing = pd.DataFrame(columns=["Kraj", "Płeć", "Zawodnik", "Sezon", "Wiek"])
                new_careers_df = pd.DataFrame(new_careers_rows)
                careers_df = pd.concat([existing, new_careers_df], ignore_index=True)
            else:
                careers_df = pd.DataFrame(new_careers_rows)

            careers_df.to_csv(careers_path, sep=";", index=False, encoding="utf-8-sig")

        # ---------- 6. Zapisz nowy plik sezonu ----------
        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            df = _canonicalize_headers_editor(df)
            df.to_csv(new_path, index=False, encoding="utf-8-sig")
        except Exception as e:
            messagebox.showerror("Nowy sezon", f"Błąd zapisu pliku:\n{e}", parent=self)
            return

        # ---------- 7. Załaduj nowy sezon do GUI ----------
        self._path_var.set(str(new_path.resolve()))
        self._full_df = df.copy()
        self._db_path = new_path
        self._rebuild_table(self._full_df)

        # Zaktualizuj domyślny folder klasyfikacji jeśli jest ustawiony wg starego sezonu
        cls_dir = self._cls_dir_var.get()
        if old_tag in cls_dir:
            self._cls_dir_var.set(cls_dir.replace(old_tag, new_tag))

        summary = (
            f"Sezon {new_tag} gotowy!\n\n"
            f"Zawodnicy aktywni: {len(df)}\n"
            f"Zakończone kariery: {len(retired)}\n"
            f"Plik: {new_path.resolve()}"
        )
        messagebox.showinfo("Nowy sezon", summary, parent=self)


def build_gui(parent):
    """Punkt wejścia dla combined: zwraca gotową ramkę edytora."""
    return PlayerDBFrame(parent)

if __name__ == "__main__":
    # Tworzymy główne okno aplikacji
    root = tk.Tk()
    root.title("Edytor Bazy Zawodników")
    root.geometry("1000x600")

    # Wywołujemy funkcję budującą GUI z Twojego pliku
    # Funkcja build_gui(parent) zwraca obiekt PlayerDBFrame
    app = build_gui(root)
    app.pack(fill="both", expand=True)

    # Uruchamiamy pętlę zdarzeń Tkinter
    root.mainloop()